//! Categorical AI input to deterministic advisory policy. No automatic actuator.
use crate::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const VERSION: &str = "hybrid-local-v1";
static LAST_REFRESH: std::sync::atomic::AtomicI64 = std::sync::atomic::AtomicI64::new(0);

pub fn last_successful_refresh() -> Option<DateTime<Utc>> {
    let seconds = LAST_REFRESH.load(std::sync::atomic::Ordering::Relaxed);
    (seconds > 0)
        .then(|| DateTime::from_timestamp(seconds, 0))
        .flatten()
}
#[derive(Clone, Deserialize, Serialize, Debug)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub severity_risk: [u16; 5],
    pub ai_adjustment: u16,
    pub behavior_adjustment: u16,
    pub fresh_seconds: i64,
    pub repeated_denials: i64,
    pub approved_clients: Vec<String>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            severity_risk: [90, 70, 45, 20, 20],
            ai_adjustment: 10,
            behavior_adjustment: 10,
            fresh_seconds: 120,
            repeated_denials: 3,
            approved_clients: Vec::new(),
        }
    }
}
impl Config {
    fn current() -> Result<Self> {
        let c: Self = serde_json::from_str(&env::var("HYBRID_POLICY_JSON").unwrap_or("{}".into()))?;
        anyhow::ensure!(
            c.severity_risk.iter().all(|v| *v <= 100)
                && c.severity_risk.windows(2).all(|v| v[0] >= v[1])
                && c.ai_adjustment <= 20
                && c.behavior_adjustment <= 20
                && (10..=300).contains(&c.fresh_seconds)
                && (3..=20).contains(&c.repeated_denials)
                && c.approved_clients.len() <= 16
                && c.approved_clients
                    .iter()
                    .all(|v| network::Safety::parse_host(v).is_ok()),
            "Invalid bounded hybrid policy"
        );
        Ok(c)
    }
}
fn hash(value: &Value) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}
pub fn evaluate(
    row: &Value,
    config: &Config,
    protected: bool,
    ip: Option<&str>,
    denials: i64,
    age_seconds: i64,
    worker_ready: bool,
) -> Value {
    let mut ids = std::collections::BTreeSet::new();
    let mut rule_risk = 0;
    let mut sources = std::collections::BTreeSet::new();
    for rule in row["rules"].as_array().into_iter().flatten() {
        // Only request-ID or verified sensor transaction links are request rules.
        if !matches!(
            rule["basis"].as_str(),
            Some("REQUEST_ID" | "SENSOR_TRANSACTION")
        ) {
            continue;
        }
        if let Some(id) = rule["id"].as_i64() {
            ids.insert(format!("alert:{id}"));
        }
        let severity = rule["severity"].as_u64().unwrap_or(5).clamp(1, 5) as usize;
        rule_risk = rule_risk.max(config.severity_risk[severity - 1]);
        sources.insert(rule["source"].as_str().unwrap_or("UNKNOWN").to_owned());
    }
    let ai = &row["request_ai"];
    let compatible = worker_ready
        && ai["status"] == "SCORED"
        && ai["model_version"] == "request-intelligence-v2-frozen-step3072"
        && ai["manifest_sha256"]
            == "b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c"
        && ai["feature_profile"] == "selected_headers_no_body"
        && ai["threshold"].as_f64() == Some(0.8826237916946411)
        && ai["score"]
            .as_f64()
            .is_some_and(|v| v.is_finite() && (0.0..=1.0).contains(&v));
    let above = compatible && ai["score"].as_f64().is_some_and(|v| v > 0.8826237916946411);
    if let Some(id) = ai["event_id"].as_str() {
        ids.insert(format!("ai:{id}"));
    }
    let ambiguous =
        row["correlation"]["status"] == "AMBIGUOUS" || row["status"] == "UNCERTAIN_CORRELATION";
    let matched =
        row["correlation"]["status"] == "MATCHED" && row["correlation"]["late_event"] == false;
    let fresh = (0..=config.fresh_seconds).contains(&age_seconds);
    let behavior = denials >= config.repeated_denials;
    let ai_risk = if above && !ambiguous {
        config.ai_adjustment
    } else {
        0
    };
    let other = if behavior {
        config.behavior_adjustment
    } else {
        0
    };
    let final_risk = (rule_risk + ai_risk + other).min(100);
    // Nginx/Suricata/AI may see the same payload: they are not independent votes.
    // Only separate request-bound application denials add behavioral support.
    let propose = rule_risk >= 70
        && above
        && behavior
        && matched
        && fresh
        && !protected
        && ip.is_some_and(|ip| config.approved_clients.iter().any(|v| v == ip));
    let action = if propose {
        "PROPOSE_BLOCK"
    } else if rule_risk >= 70 || (above && rule_risk > 0) || ambiguous && (rule_risk > 0 || above) {
        "REVIEW"
    } else if rule_risk > 0 || above || behavior {
        "ALERT"
    } else {
        "LOG_ONLY"
    };
    let mut reasons = Vec::new();
    if rule_risk > 0 {
        reasons.push("REQUEST_BOUND_RULE_EVIDENCE");
    }
    if above {
        reasons.push("UNCALIBRATED_AI_ABOVE_FROZEN_OPERATING_POINT");
    }
    if !compatible {
        reasons.push("AI_UNAVAILABLE_OR_FEATURE_UNSUPPORTED");
    }
    if behavior {
        reasons.push("REPEATED_APPLICATION_DENIALS_NOT_ATTACK_GROUND_TRUTH");
    }
    if protected || ip.is_none() {
        reasons.push("IP_BLOCK_PROHIBITED_PROTECTED_OR_AMBIGUOUS_ATTRIBUTION");
    }
    if !fresh {
        reasons.push("STALE_OR_FUTURE_INCIDENT_NO_BLOCK_PROPOSAL");
    }
    if ambiguous {
        reasons.push("AMBIGUOUS_CORRELATION");
    }
    if !matched {
        reasons.push("INCOMPLETE_OR_LATE_SENSOR_EVIDENCE");
    }
    let research = crate::https_research::advisory(row);
    let action =
        if action == "LOG_ONLY" && research.as_ref().is_some_and(|r| r["action"] == "ALERT") {
            "ALERT"
        } else {
            action
        };
    let mut decision = json!({"request_id":row["request_id"],"policy_version":format!("{}-{}",VERSION,&hash(&json!(config))[..12]),"policy_config":config,"policy_action":action,"rule_risk_component":rule_risk,"ai_risk_component":ai_risk,"other_evidence_component":other,"final_risk":final_risk,"risk_semantics":"POLICY_RISK_NOT_ATTACK_PROBABILITY","policy_reason":reasons,"evidence_ids":ids,"rule_sources":sources,"ai":{"model_id":ai["model_version"],"feature_contract":ai["feature_profile"],"score":ai["score"],"threshold":ai["threshold"],"signal":if above {"ABOVE_THRESHOLD_UNCALIBRATED"} else if compatible {"BELOW_THRESHOLD_UNCALIBRATED"} else {"AI_UNAVAILABLE"},"status":ai["status"],"timestamp":ai["observed_at"],"latency_ms":ai["latency_ms"]},"correlation_confidence":if ambiguous {"AMBIGUOUS"} else if matched {"REQUEST_TRANSACTION_MATCHED"} else {"PARTIAL"},"independent_support":"AI_AND_PAYLOAD_RULES_DEPENDENT; separate application-denial behavior only","application_denials_distinct_requests":denials,"trusted_client_ip":ip,"protected_ip":protected,"fresh":fresh,"automatic_block":false,"http_timing":"POST_OBSERVATION; no retroactive HTTP blocking"});
    if let Some(primary) = research {
        decision["control_ai"] = decision["ai"].take();
        decision["https_research"] = primary.clone();
        decision["ai"] = primary;
    }
    decision
}

async fn refresh(
    state: &AppState,
    config: &Config,
    #[cfg(feature = "dev-hybrid-review")] review: Option<&hybrid_review::Policy>,
) -> Result<()> {
    let use_legacy = !operations::aws_staging();
    let rows: Vec<Value> = sqlx::query_scalar(include_str!("detector_view.sql"))
        .bind(None::<String>)
        .bind(128_i64)
        .bind(use_legacy)
        .fetch_all(&state.pool)
        .await?;
    let worker = use_legacy && sqlx::query_scalar::<_, bool>("SELECT COALESCE((SELECT received_at>now()-interval '10 seconds' AND observed_at>now()-interval '10 seconds' AND report->>'status'='READY' FROM ai_shadow_worker WHERE singleton),false)").fetch_one(&state.pool).await?;
    #[cfg(feature = "dev-hybrid-review")]
    let app = if review.is_some() {
        let ids: Vec<_> = rows
            .iter()
            .filter_map(|r| r["request_id"].as_str())
            .collect();
        hybrid_review::application_evidence(&state.pool, &ids)
            .await
            .map_err(|e| {
                tracing::warn!(error=%e, "Student review evidence unavailable");
            })
    } else {
        Ok(Default::default())
    };
    for row in rows {
        let Some(rid) = row["request_id"].as_str() else {
            continue;
        };
        let ips:Vec<String>=sqlx::query_scalar("SELECT DISTINCT host(client_ip) FROM normalized_events WHERE source IN ('NGINX','STUDENT_AUDIT') AND request_id=$1 AND client_ip IS NOT NULL").bind(rid).fetch_all(&state.pool).await?;
        let proxy_present:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM normalized_events WHERE source='NGINX' AND request_id=$1 AND client_ip IS NOT NULL)").bind(rid).fetch_one(&state.pool).await?;
        // Transaction correlation can inform detection on the decrypted hop.
        // It grants no client attribution on a loopback sensor.
        let origin = &state.ingestion.suricata_origin;
        let ip = if proxy_present && ips.len() == 1 && !origin.local_egress() {
            Some(ips[0].as_str())
        } else {
            None
        };
        let protected = ip.is_none_or(|ip| crate::firewall::validate(state, ip).is_err());
        let actual_at:Option<DateTime<Utc>>=sqlx::query_scalar("SELECT max(occurred_at) FROM normalized_events WHERE request_id=$1 AND source IN ('NGINX','STUDENT_AUDIT')").bind(rid).fetch_one(&state.pool).await?;
        let at = actual_at.unwrap_or_else(|| {
            row["observed_at"]
                .as_str()
                .and_then(|v| DateTime::parse_from_rfc3339(v).ok())
                .map(|v| v.with_timezone(&Utc))
                .unwrap_or(Utc::now())
        });
        let denials: i64 = if let Some(ip) = ip {
            sqlx::query_scalar("SELECT count(DISTINCT COALESCE(request_id,event_key)) FROM normalized_events WHERE source='STUDENT_AUDIT' AND client_ip=$1::inet AND status_code IN (401,403) AND occurred_at BETWEEN $2-interval '120 seconds' AND $2").bind(ip).bind(at).fetch_one(&state.pool).await?
        } else {
            0
        };
        let mut decision = evaluate(
            &row,
            config,
            protected,
            ip,
            denials,
            (Utc::now() - at).num_seconds(),
            worker,
        );
        if let Some(ip) = ip {
            let evidence:Vec<String>=sqlx::query_scalar("SELECT event_key FROM normalized_events WHERE source='STUDENT_AUDIT' AND client_ip=$1::inet AND status_code IN (401,403) AND occurred_at BETWEEN $2-interval '120 seconds' AND $2 ORDER BY event_key LIMIT 100").bind(ip).bind(at).fetch_all(&state.pool).await?;
            if let Some(ids) = decision["evidence_ids"].as_array_mut() {
                ids.extend(
                    evidence
                        .into_iter()
                        .map(|v| json!(format!("application:{v}"))),
                );
            }
        }
        #[cfg(feature = "dev-hybrid-review")]
        if let Some(policy) = review {
            // The guest ingress relay terminates the client connection. No verified
            // enforcement identity exists at this boundary, even for matched flows.
            let audit = app
                .as_ref()
                .ok()
                .and_then(|rows| rows.get(rid))
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            let mut result =
                policy.assess(&row, audit, Utc::now(), hybrid_review::Target::Unverified);
            result["student_query_available"] = json!(app.is_ok());
            decision["dev_prevention"] = result;
        }
        let fingerprint = hash(&decision);
        let mut tx = state.pool.begin().await?;
        sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,14))")
            .bind(rid)
            .execute(&mut *tx)
            .await?;
        sqlx::query("INSERT INTO hybrid_incidents(request_id,evidence_fingerprint,policy_version,observed_at,decision) VALUES($1,$2,$3,$4,$5) ON CONFLICT(request_id) DO UPDATE SET evidence_fingerprint=$2,policy_version=$3,observed_at=$4,decision=$5,updated_at=now() WHERE hybrid_incidents.evidence_fingerprint<>$2")
            .bind(rid).bind(&fingerprint).bind(decision["policy_version"].as_str().unwrap()).bind(at).bind(&decision).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO hybrid_decision_audit(request_id,evidence_fingerprint,decision) VALUES($1,$2,$3) ON CONFLICT DO NOTHING").bind(rid).bind(&fingerprint).bind(&decision).execute(&mut *tx).await?;
        sqlx::query("UPDATE hybrid_proposals SET status='STALE' WHERE request_id=$1 AND status='PENDING' AND decision_fingerprint<>$2").bind(rid).bind(&fingerprint).execute(&mut *tx).await?;
        if decision["policy_action"] == "PROPOSE_BLOCK"
            && let Some(ip) = ip
        {
            sqlx::query("INSERT INTO hybrid_proposals(request_id,decision_fingerprint,ip) VALUES($1,$2,$3::inet) ON CONFLICT(request_id) DO UPDATE SET decision_fingerprint=$2,ip=$3::inet,status='PENDING',created_at=now() WHERE hybrid_proposals.status='STALE'")
                .bind(rid).bind(&fingerprint).bind(ip).execute(&mut *tx).await?;
        }
        tx.commit().await?;
    }
    Ok(())
}
pub async fn worker(state: AppState) {
    let config = match Config::current() {
        Ok(c) => c,
        Err(e) => {
            tracing::error!(error=%e,"Hybrid policy disabled: invalid configuration");
            return;
        }
    };
    #[cfg(feature = "dev-hybrid-review")]
    let review = match hybrid_review::Policy::load() {
        Ok(policy) => policy,
        Err(error) => {
            tracing::error!(%error, "Development review disabled; baseline Hybrid remains active");
            None
        }
    };
    loop {
        if let Err(e) = refresh(
            &state,
            &config,
            #[cfg(feature = "dev-hybrid-review")]
            review.as_ref(),
        )
        .await
        {
            tracing::error!(error=%e,"Hybrid policy refresh failed; no response enqueued");
        } else {
            LAST_REFRESH.store(Utc::now().timestamp(), std::sync::atomic::Ordering::Relaxed);
        }
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    }
}
#[derive(Default, Deserialize)]
pub struct QueryFilter {
    request_id: Option<String>,
}
pub async fn list(
    State(state): State<AppState>,
    Query(q): Query<QueryFilter>,
) -> Result<Json<Value>, ApiError> {
    if q.request_id
        .as_deref()
        .is_some_and(|v| !events::valid_request_id(v))
    {
        return Err(bad_request("Invalid request ID"));
    }
    let mut incidents:Vec<Value>=sqlx::query_scalar("SELECT decision||jsonb_build_object('fingerprint',evidence_fingerprint,'updated_at',updated_at) FROM hybrid_incidents WHERE ($1::text IS NULL OR request_id=$1) ORDER BY observed_at DESC LIMIT 100").bind(q.request_id).fetch_all(&state.pool).await.map_err(api_error)?;
    if operations::aws_staging() {
        for incident in &mut incidents {
            if let Some(fields) = incident.as_object_mut() {
                fields.remove("control_ai");
                if !https_research::current_result(
                    fields.get("https_research").unwrap_or(&Value::Null),
                ) {
                    fields.remove("https_research");
                    fields.remove("ai");
                }
            }
        }
    }
    let proposals:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id',id,'request_id',request_id,'ip',host(ip),'status',status,'created_at',created_at,'approved_by',approved_by,'action_id',action_id) FROM hybrid_proposals ORDER BY id DESC LIMIT 100").fetch_all(&state.pool).await.map_err(api_error)?;
    Ok(Json(
        json!({"incidents":incidents,"proposals":proposals,"automatic_block":false,"enforcement_mode":state.safety.mode}),
    ))
}
#[derive(Deserialize)]
pub struct Approval {
    ttl_seconds: u64,
    decision_fingerprint: String,
}
pub async fn approve(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Path(id): Path<i64>,
    Json(a): Json<Approval>,
) -> Result<Json<Value>, ApiError> {
    if state.safety.mode != "MANUAL" || actor.role != "admin" || !(1..=300).contains(&a.ttl_seconds)
    {
        return Err(bad_request(
            "Manual mode, admin approval and bounded TTL required",
        ));
    }
    prevention::require_execution().map_err(api_error)?;
    let mut tx = state.pool.begin().await.map_err(api_error)?;
    let proposed_rid: Option<String> =
        sqlx::query_scalar("SELECT request_id FROM hybrid_proposals WHERE id=$1")
            .bind(id)
            .fetch_optional(&mut *tx)
            .await
            .map_err(api_error)?;
    let Some(proposed_rid) = proposed_rid else {
        return Err(bad_request("Proposal not found"));
    };
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,14))")
        .bind(&proposed_rid)
        .execute(&mut *tx)
        .await
        .map_err(api_error)?;
    let p:Option<(String,String,String,String,Value)>=sqlx::query_as("SELECT p.request_id,host(p.ip),p.status,p.decision_fingerprint,h.decision FROM hybrid_proposals p JOIN hybrid_incidents h USING(request_id) WHERE p.id=$1 FOR UPDATE OF p,h").bind(id).fetch_optional(&mut *tx).await.map_err(api_error)?;
    let Some((rid, ip, status, fp, decision)) = p else {
        return Err(bad_request("Proposal not found"));
    };
    if status != "PENDING"
        || fp != a.decision_fingerprint
        || decision["policy_action"] != "PROPOSE_BLOCK"
        || hash(&decision) != fp
        || decision["fresh"] != true
    {
        return Err(bad_request("Stale, changed or already handled proposal"));
    }
    let age: bool = sqlx::query_scalar(
        "SELECT observed_at>now()-interval '120 seconds' FROM hybrid_incidents WHERE request_id=$1",
    )
    .bind(&rid)
    .fetch_one(&mut *tx)
    .await
    .map_err(api_error)?;
    if !age {
        return Err(bad_request("Proposal expired"));
    }
    let parsed = firewall::validate(&state, &ip).map_err(bad_request)?;
    // One transaction owns proposal approval and the centralized response queue.
    let action = firewall::enqueue_tx(
        &mut tx,
        parsed,
        "BLOCK",
        &actor.username,
        "Operator approved hybrid proposal",
        None,
        a.ttl_seconds,
    )
    .await
    .map_err(api_error)?;
    sqlx::query(
        "UPDATE hybrid_proposals SET status='APPROVED',approved_by=$2,action_id=$3 WHERE id=$1",
    )
    .bind(id)
    .bind(&actor.username)
    .bind(action)
    .execute(&mut *tx)
    .await
    .map_err(api_error)?;
    tx.commit().await.map_err(api_error)?;
    Ok(Json(
        json!({"id":id,"action_id":action,"status":"APPROVED_PENDING_RESPONSE","automatic_block":false}),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[sqlx::test(migrations = "./migrations")]
    async fn r51_labeled_demo_matches_dashboard_snapshot(pool: PgPool) {
        let fixture: Value =
            serde_json::from_str(include_str!("../frontend/src/r51-demo.json")).unwrap();
        let rid = fixture["request_id"].as_str().unwrap();
        let mut state = integration_tests::state(pool.clone());
        state.policy = PolicyEngine::new(false, vec![], false);
        let at = Utc::now();
        let dir = env::temp_dir().join(format!("ws-r51-fixture-{}", rand::random::<u64>()));
        std::fs::create_dir(&dir).unwrap();
        let log = dir.join("nginx.jsonl");
        let line = json!({"timestamp":at,"source_instance":"r51-lab-fixture","client_ip":"192.0.2.51","request_id":rid,"event_id":format!("r51-main-{rid}"),"http_method":"GET","uri_path":"/api/classes","status":200,"rule_signals":{"SQLI":1}});
        std::fs::write(&log, format!("{line}\n{line}\n")).unwrap();
        let ingest = crate::ingest::process_file(&state, "NGINX", &log).await;
        std::fs::remove_file(&log).unwrap();
        std::fs::remove_dir(&dir).unwrap();
        ingest.unwrap();

        let proof = json!({"schema_version":"three-source-1","request_id":rid,"sensor_instance":"a".repeat(32),"observed_at":at,"status":"MATCHED","sources":fixture["sources"],"flow_id":"5151","tx_id":0,"duplicate_events":0,"flow_context_alerts":0,"late_event":false,"basis":"EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY","proof_sha256":"b".repeat(64),"glu":null,"enforcement_actions":0});
        let registry: Value = serde_json::from_str(include_str!(
            "../../ai-training/contracts/quality-freeze-r37/slots.json"
        ))
        .unwrap();
        let model = &registry["slots"]["candidate"];
        let now = at.timestamp_nanos_opt().unwrap();
        let advisory = json!({"request_id":rid,"version":model["version"],"model_sha256":model["sha256"],"schema":registry["abi"],"dispatch_ns":now-3_000_000,"receipt_ns":now-2_000_000,"available_ns":now-1_000_000,"cutoff_ns":now+997_000_000,"guard_ns":1_000_000,"status":"SCORED","threshold":model["threshold"],"score":0.90,"enforcement":false});
        let mut tx = pool.begin().await.unwrap();
        crate::three_source::ingest(&mut tx, "r51-proof", &serde_json::to_vec(&proof).unwrap())
            .await
            .unwrap();
        crate::https_research::ingest(
            &mut tx,
            "r51-score",
            &serde_json::to_vec(&advisory).unwrap(),
        )
        .await
        .unwrap();
        tx.commit().await.unwrap();
        for _ in 0..2 {
            refresh(
                &state,
                &Config::default(),
                #[cfg(feature = "dev-hybrid-review")]
                None,
            )
            .await
            .unwrap();
        }
        let decision: Value =
            sqlx::query_scalar("SELECT decision FROM hybrid_incidents WHERE request_id=$1")
                .bind(rid)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(decision["policy_action"], fixture["decision"]);
        assert_eq!(decision["https_research"]["action"], fixture["advisory"]);
        assert_eq!(
            decision["correlation_confidence"],
            "REQUEST_TRANSACTION_MATCHED"
        );
        assert_eq!(decision["automatic_block"], false);
        let actual: (i64,i64,i64,i64) = sqlx::query_as("SELECT (SELECT count(*) FROM security_alerts),(SELECT count(*) FROM hybrid_incidents),(SELECT count(*) FROM hybrid_decision_audit),(SELECT count(*) FROM firewall_actions)").fetch_one(&pool).await.unwrap();
        assert_eq!(
            json!([actual.0, actual.1, actual.2, actual.3]),
            json!([
                fixture["source_alerts"],
                fixture["hybrid_incidents"],
                fixture["decision_audit"],
                fixture["firewall_actions"]
            ])
        );
    }
    #[cfg(feature = "dev-hybrid-review")]
    #[sqlx::test]
    async fn dev_review_persists_only_correlated_evidence_and_never_enqueues(pool: PgPool) {
        let state = integration_tests::state(pool.clone());
        let rid = "a".repeat(32);
        let at = Utc::now();
        sqlx::query("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,event_type,canonical) VALUES('evt','1.0','STUDENT_AUDIT','student','evt',$1,$2,'audit',$3)")
            .bind(at).bind(&rid).bind(json!({"schema_version":"1.0","role":"STAFF","user_id":format!("hmac-sha256:{}","b".repeat(64)),"session_hmac":format!("hmac-sha256:{}","c".repeat(64))})).execute(&pool).await.unwrap();
        for key in ["evt:APP-1013", "other:APP-1013"] {
            sqlx::query("INSERT INTO security_alerts(event_key,occurred_at,source,event_type,rule_name,signature,category,severity,action,evidence) VALUES($1,$2,'STUDENT_AUDIT','alert','test','APP-1013','Application Security Decision',1,'ALERT',$3)")
                .bind(key).bind(at).bind(json!({"request_id":rid,"source_instance":"student"}).to_string()).execute(&pool).await.unwrap();
        }
        let policy = serde_json::from_value(json!({"rules":[{"source":"STUDENT_AUDIT","rule":"APP-1013","weight":95,"standalone":true,"max_severity":1}],"combined":120,"standalone":90,"fresh_seconds":12,"r37_weight":50})).unwrap();
        for _ in 0..2 {
            refresh(&state, &Config::default(), Some(&policy))
                .await
                .unwrap();
        }
        let result: Value = sqlx::query_scalar(
            "SELECT decision->'dev_prevention' FROM hybrid_incidents WHERE request_id=$1",
        )
        .bind(&rid)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(result["evidence_alert_ids"].as_array().unwrap().len(), 1);
        assert_eq!(result["evidence_eligible"], true);
        assert_eq!(result["action"], "REVIEW");
        assert_eq!(result["execution_allowed"], false);
        let counts:(i64,i64,i64)=sqlx::query_as("SELECT (SELECT count(*) FROM hybrid_decision_audit),(SELECT count(*) FROM firewall_actions),(SELECT count(*) FROM security_alerts)").fetch_one(&pool).await.unwrap();
        assert_eq!(counts, (1, 0, 2));
        let allowed = vec!["APP-1013".to_owned(), "APP-1012".to_owned()];
        assert!(
            hybrid_review::auto_canary(&pool, &allowed, &[])
                .await
                .unwrap()
                .is_none()
        );
        assert!(
            hybrid_review::auto_canary(&pool, &allowed, &allowed[..1])
                .await
                .unwrap()
                .is_some()
        );
        // Distinct IDs with the same operation do not escalate a retry.
        let second = "d".repeat(32);
        sqlx::query("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,event_type,canonical) SELECT 'evt2',schema_version,source,source_instance,'evt2',occurred_at,$1,event_type,canonical FROM normalized_events WHERE event_key='evt'").bind(&second).execute(&pool).await.unwrap();
        let alert_id: i64 = sqlx::query_scalar("INSERT INTO security_alerts(event_key,occurred_at,source,event_type,rule_name,signature,category,severity,action,evidence) SELECT 'evt2:APP-1013',occurred_at,source,event_type,rule_name,signature,category,severity,action,jsonb_set(evidence::jsonb,'{request_id}',to_jsonb($1::text))::text FROM security_alerts WHERE event_key='evt:APP-1013' RETURNING id").bind(&second).fetch_one(&pool).await.unwrap();
        sqlx::query("INSERT INTO hybrid_incidents(request_id,evidence_fingerprint,policy_version,observed_at,decision) SELECT $1,evidence_fingerprint,policy_version,observed_at,jsonb_set(jsonb_set(decision,'{dev_prevention,request_id}',to_jsonb($1::text)),'{dev_prevention,evidence_alert_ids}',jsonb_build_array($2::bigint)) FROM hybrid_incidents WHERE request_id=$3").bind(&second).bind(alert_id).bind(&rid).execute(&pool).await.unwrap();
        assert!(
            hybrid_review::auto_canary(&pool, &allowed, &[])
                .await
                .unwrap()
                .is_none()
        );
        let native = hybrid_review::NativeThreshold {
            action: "BLOCK_REQUEST".into(),
            window_seconds: 30,
            events: 2,
            ttl: 8,
            source_instance: "student".into(),
        };
        assert!(
            hybrid_review::adaptive_plan(&pool, &allowed, &[], Some(&native))
                .await
                .unwrap()
                .is_none()
        );
        for (key, object) in [("evt", "1"), ("evt2", "2")] {
            sqlx::query("UPDATE normalized_events SET canonical=jsonb_set(canonical,'{security}',jsonb_build_object('object_hmac',$1::text)) WHERE event_key=$2")
                .bind(format!("hmac-sha256:{}",object.repeat(64))).bind(key).execute(&pool).await.unwrap();
        }
        use hmac::{Hmac, Mac};
        let mut mac = Hmac::<sha2::Sha256>::new_from_slice("a".repeat(64).as_bytes()).unwrap();
        mac.update(format!("session:{}", "1".repeat(32)).as_bytes());
        let tag = format!("{:x}", mac.finalize().into_bytes());
        sqlx::query("UPDATE normalized_events SET canonical=jsonb_set(canonical,'{session_hmac}',to_jsonb($1::text)) WHERE event_key IN ('evt','evt2')")
            .bind(format!("hmac-sha256:{tag}")).execute(&pool).await.unwrap();
        let distinct = hybrid_review::adaptive_plan(&pool, &allowed, &[], Some(&native))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(distinct["selector"], format!("request-{tag}"));
        assert_eq!(distinct["rules"], json!(["APP-1013", "APP-1013"]));
        sqlx::query(
            "UPDATE security_alerts SET signature='APP-1012',event_key='evt2:APP-1012' WHERE id=$1",
        )
        .bind(alert_id)
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query("UPDATE hybrid_incidents SET decision=jsonb_set(decision,'{dev_prevention,policy,rules,0,rule}',to_jsonb('APP-1012'::text)) WHERE request_id=$1").bind(&second).execute(&pool).await.unwrap();
        let window = hybrid_review::auto_canary(&pool, &allowed, &[])
            .await
            .unwrap()
            .unwrap();
        assert_eq!(window["evidence"].as_array().unwrap().len(), 2);
        let canary = hybrid_review::action_plan(&pool, &rid, "BLOCK_REQUEST")
            .await
            .unwrap();
        assert_eq!(canary["selector"], "dev-canary");
        assert!(
            hybrid_review::action_plan(&pool, &rid, "BLOCK_IP")
                .await
                .is_err()
        );
        let account = hybrid_review::action_plan(&pool, &rid, "BLOCK_ACCOUNT")
            .await
            .unwrap();
        assert_eq!(account["selector"], format!("account-{}", "b".repeat(64)));
        let plan = hybrid_review::session_plan(&pool, &rid).await.unwrap();
        assert_eq!(plan["selector"], format!("{}.{tag}", "b".repeat(64)));
        assert_eq!(
            plan,
            hybrid_review::session_plan(&pool, &rid).await.unwrap()
        );
        if let Ok(binary) = std::env::var("WS_TEST_HTTPS_BINARY") {
            let status = std::process::Command::new("python3")
                .args(["-B", "deploy/dev-i5/adaptive/test_edge.py", &binary])
                .env("WS_TEST_NATIVE", "1")
                .env("WS_TEST_CANARY_PLAN", distinct.to_string())
                .env("WS_TEST_AUTO_START", distinct["oldest"].to_string())
                .status()
                .unwrap();
            assert!(status.success());
        }
        sqlx::query(
            "UPDATE normalized_events SET canonical=canonical-'role' WHERE event_key='evt'",
        )
        .execute(&pool)
        .await
        .unwrap();
        assert!(hybrid_review::session_plan(&pool, &rid).await.is_err());
        assert!(
            hybrid_review::action_plan(&pool, &rid, "BLOCK_ACCOUNT")
                .await
                .is_err()
        );
    }
    fn row() -> Value {
        json!({"request_id":"a".repeat(32),"rules":[],"request_ai":{"status":"SCORED","model_version":"request-intelligence-v2-frozen-step3072","manifest_sha256":"b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c","feature_profile":"selected_headers_no_body","score":0.99,"threshold":0.8826237916946411,"event_id":"b".repeat(32)},"correlation":{"status":"MATCHED","late_event":false}})
    }
    #[test]
    fn ai_and_payload_rule_are_not_independent_block_votes() {
        let mut r = row();
        let c = Config {
            approved_clients: vec!["10.203.17.2".into()],
            ..Config::default()
        };
        assert_eq!(
            evaluate(&r, &c, false, Some("10.203.17.2"), 0, 0, true)["policy_action"],
            "ALERT"
        );
        r["rules"] =
            json!([{"id":1,"severity":1,"source":"SURICATA","basis":"SENSOR_TRANSACTION"}]);
        assert_eq!(
            evaluate(&r, &c, false, Some("10.203.17.2"), 0, 0, true)["policy_action"],
            "REVIEW"
        );
        assert_eq!(
            evaluate(&r, &c, false, Some("10.203.17.2"), 3, 0, true)["policy_action"],
            "PROPOSE_BLOCK"
        );
    }
    #[test]
    fn protected_stale_ambiguous_and_failed_ai_never_propose() {
        let mut r = row();
        r["rules"] = json!([{"id":1,"severity":1,"source":"NGINX","basis":"REQUEST_ID"}]);
        let c = Config {
            approved_clients: vec!["10.203.17.2".into()],
            ..Config::default()
        };
        for (protected, ip, age, ready) in [
            (true, Some("10.203.17.2"), 0, true),
            (false, None, 0, true),
            (false, Some("10.203.17.2"), 121, true),
            (false, Some("10.203.17.2"), 0, false),
        ] {
            assert_ne!(
                evaluate(&r, &c, protected, ip, 3, age, ready)["policy_action"],
                "PROPOSE_BLOCK"
            );
        }
        r["correlation"]["status"] = json!("AMBIGUOUS");
        assert_ne!(
            evaluate(&r, &c, false, Some("10.203.17.2"), 3, 0, true)["policy_action"],
            "PROPOSE_BLOCK"
        );
    }
    #[test]
    fn low_ai_cannot_cancel_rule_and_flow_alert_not_request_rule() {
        let mut r = row();
        let c = Config {
            approved_clients: vec!["10.203.17.2".into()],
            ..Config::default()
        };
        r["request_ai"]["score"] = json!(0.);
        r["rules"] =
            json!([{"id":1,"severity":1,"source":"SURICATA","basis":"SENSOR_TRANSACTION"}]);
        assert_eq!(
            evaluate(&r, &c, true, None, 0, 0, true)["rule_risk_component"],
            90
        );
        r["rules"][0]["basis"] = json!("FLOW_CONTEXT");
        assert_eq!(
            evaluate(&r, &c, true, None, 0, 0, true)["rule_risk_component"],
            0
        );
    }
    #[test]
    fn deterministic_and_unknown_model_unavailable() {
        let mut r = row();
        let c = Config {
            approved_clients: vec!["10.203.17.2".into()],
            ..Config::default()
        };
        let a = evaluate(&r, &c, false, None, 0, 0, true);
        assert_eq!(hash(&a), hash(&evaluate(&r, &c, false, None, 0, 0, true)));
        r["request_ai"]["model_version"] = json!("publisher-anomaly");
        assert_eq!(
            evaluate(&r, &c, false, None, 0, 0, true)["ai_risk_component"],
            0
        );
    }

    #[test]
    fn multiple_request_bound_alerts_keep_identity_and_only_highest_rule_risk() {
        let mut r = row();
        r["rules"] = json!([
            {"id":1,"source":"NGINX","severity":2,"basis":"REQUEST_ID"},
            {"id":2,"source":"SURICATA","severity":1,"basis":"SENSOR_TRANSACTION"},
            {"id":3,"source":"STUDENT_AUDIT","severity":2,"basis":"REQUEST_ID"},
            {"id":2,"source":"SURICATA","severity":1,"basis":"SENSOR_TRANSACTION"},
            {"id":4,"source":"SURICATA","severity":1,"basis":"FLOW_CONTEXT"}
        ]);
        let result = evaluate(&r, &Config::default(), true, None, 0, 0, false);
        assert_eq!(
            result["rule_sources"],
            json!(["NGINX", "STUDENT_AUDIT", "SURICATA"])
        );
        assert_eq!(result["rule_risk_component"], 90);
        assert_eq!(result["final_risk"], 90);
        assert_eq!(result["policy_action"], "REVIEW");
        assert_eq!(result["automatic_block"], false);
        let alerts: Vec<_> = result["evidence_ids"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|id| id.as_str()?.strip_prefix("alert:"))
            .collect();
        assert_eq!(alerts, ["1", "2", "3"]);
    }
}
