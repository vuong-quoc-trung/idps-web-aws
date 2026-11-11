//! Categorical AI input to deterministic advisory policy. No automatic actuator.
use crate::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const VERSION: &str = "hybrid-local-v1";
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
    json!({"request_id":row["request_id"],"policy_version":format!("{}-{}",VERSION,&hash(&json!(config))[..12]),"policy_config":config,"policy_action":action,"rule_risk_component":rule_risk,"ai_risk_component":ai_risk,"other_evidence_component":other,"final_risk":final_risk,"risk_semantics":"POLICY_RISK_NOT_ATTACK_PROBABILITY","policy_reason":reasons,"evidence_ids":ids,"rule_sources":sources,"ai":{"model_id":ai["model_version"],"feature_contract":ai["feature_profile"],"score":ai["score"],"threshold":ai["threshold"],"signal":if above {"ABOVE_THRESHOLD_UNCALIBRATED"} else if compatible {"BELOW_THRESHOLD_UNCALIBRATED"} else {"AI_UNAVAILABLE"},"status":ai["status"],"timestamp":ai["observed_at"],"latency_ms":ai["latency_ms"]},"correlation_confidence":if ambiguous {"AMBIGUOUS"} else if matched {"REQUEST_TRANSACTION_MATCHED"} else {"PARTIAL"},"independent_support":"AI_AND_PAYLOAD_RULES_DEPENDENT; separate application-denial behavior only","application_denials_distinct_requests":denials,"trusted_client_ip":ip,"protected_ip":protected,"fresh":fresh,"automatic_block":false,"http_timing":"POST_OBSERVATION; no retroactive HTTP blocking"})
}

async fn refresh(state: &AppState, config: &Config) -> Result<()> {
    let rows: Vec<Value> = sqlx::query_scalar(include_str!("detector_view.sql"))
        .bind(None::<String>)
        .bind(128_i64)
        .fetch_all(&state.pool)
        .await?;
    let worker:bool=sqlx::query_scalar("SELECT COALESCE((SELECT received_at>now()-interval '10 seconds' AND observed_at>now()-interval '10 seconds' AND report->>'status'='READY' FROM ai_shadow_worker WHERE singleton),false)").fetch_one(&state.pool).await?;
    for row in rows {
        let Some(rid) = row["request_id"].as_str() else {
            continue;
        };
        let ips:Vec<String>=sqlx::query_scalar("SELECT DISTINCT host(client_ip) FROM normalized_events WHERE source IN ('NGINX','STUDENT_AUDIT') AND request_id=$1 AND client_ip IS NOT NULL").bind(rid).fetch_all(&state.pool).await?;
        let proxy_present:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM normalized_events WHERE source='NGINX' AND request_id=$1 AND client_ip IS NOT NULL)").bind(rid).fetch_one(&state.pool).await?;
        let ip = if proxy_present && ips.len() == 1 {
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
    loop {
        if let Err(e) = refresh(&state, &config).await {
            tracing::error!(error=%e,"Hybrid policy refresh failed; no response enqueued");
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
    let incidents:Vec<Value>=sqlx::query_scalar("SELECT decision||jsonb_build_object('fingerprint',evidence_fingerprint,'updated_at',updated_at) FROM hybrid_incidents WHERE ($1::text IS NULL OR request_id=$1) ORDER BY observed_at DESC LIMIT 100").bind(q.request_id).fetch_all(&state.pool).await.map_err(api_error)?;
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
    fn row() -> Value {
        json!({"request_id":"a".repeat(32),"rules":[],"request_ai":{"status":"SCORED","model_version":"request-intelligence-v2-frozen-step3072","manifest_sha256":"b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f6b9ecc0ae96c","feature_profile":"selected_headers_no_body","score":0.99,"threshold":0.8826237916946411,"event_id":"b".repeat(32)},"correlation":{"status":"MATCHED","late_event":false}})
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
}
