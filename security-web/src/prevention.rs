//! C1 read-only proposal evaluation. No actuator, queue, approval or database writes.
use crate::*;
use serde_json::{Value, json};

fn decide(
    source: &str,
    severity: i32,
    client: Option<&str>,
    verified: bool,
    safe: bool,
    evidence: bool,
) -> Value {
    let mut reasons = Vec::new();
    let ip = client.and_then(|s| s.parse::<IpAddr>().ok());
    if !verified {
        reasons.push("CLIENT_IP_UNVERIFIED");
    }
    if ip.is_none() {
        reasons.push("NO_TRUSTED_CLIENT_IP");
    }
    // Internal address space is protected in C1, even if lab enforcement allows it.
    let public = matches!(ip, Some(IpAddr::V4(v)) if !v.is_private() && !v.is_loopback() && !v.is_link_local() && !v.is_unspecified() && !v.is_multicast() && !v.is_broadcast());
    if !public || !safe {
        reasons.push("PROTECTED_OR_OUT_OF_SCOPE_IP");
    }
    let decision = if !reasons.is_empty() {
        "DENY"
    } else if source != "SURICATA" || !evidence || !(1..=2).contains(&severity) {
        reasons.push("SOURCE_SEVERITY_OR_EVIDENCE_REQUIRES_REVIEW");
        "REVIEW"
    } else {
        reasons.push("TRUSTED_CLIENT_AND_NATIVE_ALERT_POLICY_MATCH");
        "ALLOW"
    };
    json!({"decision":decision,"reasons":reasons,"dry_run":true,"execution_allowed":false,
        "approval_enabled":false,"requires_admin_approval":true,"proposed_ttl_seconds":300,
        "policy_version":"C1-v1","client_ip":client,
        "note":"ALLOW is eligibility only; Shadow correlation never grants verified identity"})
}

pub async fn evaluate(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<i64>,
) -> Result<Json<Value>, ApiError> {
    let alert = sqlx::query_scalar::<_, Value>("SELECT to_jsonb(a) || jsonb_build_object('client_ip',host(a.client_ip)) FROM security_alerts a WHERE id=$1")
        .bind(id).fetch_optional(&state.pool).await.map_err(api_error)?
        .ok_or((StatusCode::NOT_FOUND,Json(json!({"message":"Alert not found"}))))?;
    let mut result = assess(&state, &alert);
    result["alert_id"] = json!(id);
    result["evaluated_at"] = json!(Utc::now());
    Ok(Json(result))
}

// One policy gate shared by proposal creation and approval re-evaluation.
pub(crate) fn assess(state: &AppState, alert: &Value) -> Value {
    let client = alert["client_ip"].as_str();
    let safe = client.is_some_and(|ip| firewall::validate(state, ip).is_ok());
    let mut result = decide(
        alert["source"].as_str().unwrap_or(""),
        alert["severity"].as_i64().unwrap_or(0) as i32,
        client,
        alert["client_ip_verified"].as_bool().unwrap_or(false),
        safe,
        alert["rule_name"]
            .as_str()
            .is_some_and(|s| s.starts_with("SURICATA: SID ")),
    );
    if state.safety.mode != "OFF" || state.policy.auto_block_enabled {
        result["decision"] = json!("DENY");
        result["reasons"]
            .as_array_mut()
            .unwrap()
            .push(json!("C1_REQUIRES_ENFORCEMENT_OFF"));
    }
    let fresh = alert["occurred_at"]
        .as_str()
        .and_then(|v| DateTime::parse_from_rfc3339(v).ok())
        .is_some_and(|t| {
            let age = Utc::now().signed_duration_since(t);
            age.num_seconds() >= 0 && age.num_seconds() <= 300
        });
    if !fresh {
        result["decision"] = json!("DENY");
        result["reasons"]
            .as_array_mut()
            .unwrap()
            .push(json!("ALERT_STALE_OR_FUTURE"));
    }
    result["policy_version"] = json!("C2-v2");
    result
}

/// Only the separately built isolated profile can acquire a capability.
pub fn execution_enabled() -> bool {
    #[cfg(feature = "isolated-c2")]
    {
        use std::os::unix::fs::{FileTypeExt, MetadataExt};
        let root = std::path::Path::new("/run/websentinel-r56-lab");
        let attestation = root.join("host-netns");
        let private = std::fs::symlink_metadata(root)
            .is_ok_and(|st| st.is_dir() && st.uid() == 0 && st.mode() & 0o022 == 0)
            && std::fs::symlink_metadata(&attestation).is_ok_and(|st| {
                st.is_file() && st.uid() == 0 && st.mode() & 0o022 == 0 && st.len() < 64
            })
            && std::fs::metadata("/proc/self/ns/net")
                .ok()
                .zip(
                    std::fs::read_to_string(attestation)
                        .ok()
                        .and_then(|s| s.trim().parse::<u64>().ok()),
                )
                .is_some_and(|(current, host)| host != 0 && current.ino() != host);
        return private
            && env::var("ENFORCEMENT_MODE").as_deref() == Ok("MANUAL")
            && env::var("AUTO_BLOCK").as_deref() == Ok("false")
            && std::fs::symlink_metadata(firewall::LAB_SOCKET).is_ok_and(|st| {
                st.uid() == 0 && st.file_type().is_socket() && st.mode() & 0o007 == 0
            });
    }
    #[cfg(not(feature = "isolated-c2"))]
    false
}
pub fn require_execution() -> Result<()> {
    anyhow::ensure!(execution_enabled(), "C2_EXECUTION_DISABLED");
    Ok(())
}

#[derive(serde::Deserialize)]
pub struct ProposalRequest {
    alert_id: i64,
    reason: String,
    idempotency_key: String,
    ttl_seconds: i32,
}
#[derive(serde::Deserialize)]
pub struct ReviewRequest {
    approve: bool,
    reason: String,
}
fn admin(actor: &auth::Identity) -> Result<(), ApiError> {
    if actor.role != "admin" {
        return Err((
            StatusCode::FORBIDDEN,
            Json(json!({"message":"Admin required"})),
        ));
    }
    Ok(())
}
fn valid_reason(s: &str) -> bool {
    !s.trim().is_empty() && s.len() <= 500 && !s.chars().any(char::is_control)
}

pub async fn propose(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Json(req): Json<ProposalRequest>,
) -> Result<Json<Value>, ApiError> {
    admin(&actor)?;
    if !valid_reason(&req.reason)
        || !(1..=300).contains(&req.ttl_seconds)
        || req.idempotency_key.is_empty()
        || req.idempotency_key.len() > 64
        || !req
            .idempotency_key
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-')
    {
        return Err(bad_request("Invalid proposal"));
    }
    let mut tx = state.pool.begin().await.map_err(api_error)?;
    // Serialize retries for this actor/key before checking the unique constraint.
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
        .bind(format!("{}:{}", actor.username, req.idempotency_key))
        .execute(&mut *tx)
        .await
        .map_err(api_error)?;
    let old = sqlx::query_scalar::<_, Value>(
        "SELECT to_jsonb(p) FROM prevention_proposals p WHERE creator=$1 AND idempotency_key=$2",
    )
    .bind(&actor.username)
    .bind(&req.idempotency_key)
    .fetch_optional(&mut *tx)
    .await
    .map_err(api_error)?;
    if let Some(old) = old {
        if old["alert_id"] != json!(req.alert_id)
            || old["reason"] != json!(req.reason)
            || old["ttl_seconds"] != json!(req.ttl_seconds)
        {
            return Err(bad_request("Idempotency key reused with different input"));
        }
        return Ok(Json(json!({"proposal":old,"execution_allowed":false})));
    }
    let alert=sqlx::query_scalar::<_,Value>("SELECT to_jsonb(a)||jsonb_build_object('client_ip',host(client_ip)) FROM security_alerts a WHERE id=$1 FOR SHARE").bind(req.alert_id).fetch_optional(&mut *tx).await.map_err(api_error)?.ok_or_else(||bad_request("Alert not found"))?;
    let eval = assess(&state, &alert);
    let status = match eval["decision"].as_str() {
        Some("ALLOW") => "PROPOSED",
        Some("REVIEW") => "REVIEW",
        _ => "DENIED",
    };
    let id: i64=sqlx::query_scalar("INSERT INTO prevention_proposals(alert_id,creator,idempotency_key,reason,ttl_seconds,status,evaluation) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id").bind(req.alert_id).bind(&actor.username).bind(req.idempotency_key).bind(&req.reason).bind(req.ttl_seconds).bind(status).bind(&eval).fetch_one(&mut *tx).await.map_err(api_error)?;
    sqlx::query("INSERT INTO prevention_decisions(proposal_id,actor,decision,reason,evaluation) VALUES($1,$2,$3,$4,$5)").bind(id).bind(actor.username).bind(status).bind(req.reason).bind(&eval).execute(&mut *tx).await.map_err(api_error)?;
    tx.commit().await.map_err(api_error)?;
    Ok(Json(
        json!({"id":id,"status":status,"evaluation":eval,"execution_allowed":false}),
    ))
}

pub async fn review(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Path(id): Path<i64>,
    Json(req): Json<ReviewRequest>,
) -> Result<Json<Value>, ApiError> {
    admin(&actor)?;
    if !valid_reason(&req.reason) {
        return Err(bad_request("Invalid reason"));
    }
    let mut tx = state.pool.begin().await.map_err(api_error)?;
    let row=sqlx::query_as::<_,(i64,String,String,bool)>("SELECT alert_id,creator,status,expires_at<=clock_timestamp() FROM prevention_proposals WHERE id=$1 FOR UPDATE").bind(id).fetch_optional(&mut *tx).await.map_err(api_error)?.ok_or_else(||bad_request("Proposal not found"))?;
    if !matches!(row.2.as_str(), "PROPOSED" | "REVIEW") {
        return Err(bad_request("Proposal already terminal"));
    }
    if req.approve && row.1 == actor.username {
        return Err(bad_request("Independent Admin reviewer required"));
    }
    let alert=sqlx::query_scalar::<_,Value>("SELECT to_jsonb(a)||jsonb_build_object('client_ip',host(client_ip)) FROM security_alerts a WHERE id=$1 FOR SHARE").bind(row.0).fetch_one(&mut *tx).await.map_err(api_error)?;
    let mut eval = assess(&state, &alert);
    let original: Value =
        sqlx::query_scalar("SELECT evaluation FROM prevention_proposals WHERE id=$1")
            .bind(id)
            .fetch_one(&mut *tx)
            .await
            .map_err(api_error)?;
    if original["client_ip"] != eval["client_ip"] {
        eval["decision"] = json!("DENY");
        eval["reasons"]
            .as_array_mut()
            .unwrap()
            .push(json!("CLIENT_CHANGED_AFTER_PROPOSAL"));
    }
    let expired: bool = sqlx::query_scalar(
        "SELECT expires_at<=clock_timestamp() FROM prevention_proposals WHERE id=$1",
    )
    .bind(id)
    .fetch_one(&mut *tx)
    .await
    .map_err(api_error)?;
    let status = if row.3 || expired {
        "EXPIRED"
    } else if !req.approve {
        "REJECTED"
    } else if eval["decision"] == "ALLOW" {
        "APPROVED_DRY_RUN"
    } else {
        "DENIED"
    };
    sqlx::query("UPDATE prevention_proposals SET status=$2,reviewer=$3,reviewed_at=clock_timestamp(),evaluation=$4 WHERE id=$1").bind(id).bind(status).bind(&actor.username).bind(&eval).execute(&mut *tx).await.map_err(api_error)?;
    sqlx::query("INSERT INTO prevention_decisions(proposal_id,actor,decision,reason,evaluation) VALUES($1,$2,$3,$4,$5)").bind(id).bind(actor.username).bind(status).bind(req.reason).bind(&eval).execute(&mut *tx).await.map_err(api_error)?;
    tx.commit().await.map_err(api_error)?;
    Ok(Json(
        json!({"id":id,"status":status,"evaluation":eval,"execution_allowed":false}),
    ))
}

pub async fn proposals(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
) -> Result<Json<Value>, ApiError> {
    admin(&actor)?;
    let rows=sqlx::query_scalar::<_,Value>("SELECT to_jsonb(p)||jsonb_build_object('expired',expires_at<=now(),'execution_allowed',false,'audit',(SELECT coalesce(jsonb_agg(d ORDER BY d.id),'[]'::jsonb) FROM prevention_decisions d WHERE proposal_id=p.id)) FROM prevention_proposals p ORDER BY id DESC LIMIT 100").fetch_all(&state.pool).await.map_err(api_error)?;
    Ok(Json(json!(rows)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn c2_cannot_execute_or_accept_invalid_reason() {
        assert!(!execution_enabled());
        assert!(require_execution().is_err());
        assert!(!valid_reason(""));
        assert!(!valid_reason("bad\nreason"));
        assert!(valid_reason("Lab review"));
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn c2_proposal_audit_and_bypass(pool: PgPool) {
        let state = crate::integration_tests::state(pool.clone());
        assert!(
            !crate::firewall::process_one(&state, |_, _, _| async { panic!("actuator reached") })
                .await
                .unwrap()
        );
        assert!(
            crate::firewall::enqueue(
                &pool,
                "8.8.8.8".parse().unwrap(),
                "BLOCK",
                "admin",
                "test",
                None
            )
            .await
            .is_err()
        );
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM prevention_proposals")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn c2_approval_idempotency_conflict_expiry_rbac(pool: PgPool) {
        let mut state = crate::integration_tests::state(pool.clone());
        let mut safety = network::Safety::test();
        safety.mode = "OFF".into();
        safety.allowed = vec![network::Subnet::parse("8.8.8.8/32").unwrap()];
        state.safety = Arc::new(safety);
        state.policy = PolicyEngine::new(false, vec![], false);
        let id:i64=sqlx::query_scalar("INSERT INTO security_alerts(occurred_at,source,event_type,rule_name,severity,action,evidence,client_ip,client_ip_verified,network_src_ip,suricata_post_proxy) VALUES(now(),'SURICATA','alert','SURICATA: SID 1000003',2,'ALERT','{}','8.8.8.8',true,'192.168.20.1',true) RETURNING id").fetch_one(&pool).await.unwrap();
        let actor = |name: &str, role: &str| {
            Extension(auth::Identity {
                username: name.into(),
                role: role.into(),
            })
        };
        let req = |key: &str| {
            Json(ProposalRequest {
                alert_id: id,
                reason: "test".into(),
                idempotency_key: key.into(),
                ttl_seconds: 60,
            })
        };
        assert!(
            propose(State(state.clone()), actor("v", "viewer"), req("v"))
                .await
                .is_err()
        );
        let first = propose(State(state.clone()), actor("a", "admin"), req("one"))
            .await
            .unwrap()
            .0;
        let pid = first["id"].as_i64().unwrap();
        assert_eq!(first["status"], "PROPOSED");
        let repeated = propose(State(state.clone()), actor("a", "admin"), req("one"))
            .await
            .unwrap()
            .0;
        assert_eq!(repeated["proposal"]["id"], pid);
        assert!(
            review(
                State(state.clone()),
                actor("a", "admin"),
                Path(pid),
                Json(ReviewRequest {
                    approve: true,
                    reason: "self".into()
                })
            )
            .await
            .is_err()
        );
        // Identity revocation after proposal must be re-evaluated from the DB.
        sqlx::query("UPDATE security_alerts SET client_ip_verified=false WHERE id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
        let denied = review(
            State(state.clone()),
            actor("b", "admin"),
            Path(pid),
            Json(ReviewRequest {
                approve: true,
                reason: "review".into(),
            }),
        )
        .await
        .unwrap()
        .0;
        assert_eq!(denied["status"], "DENIED");
        sqlx::query("UPDATE security_alerts SET client_ip_verified=true WHERE id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
        let p = propose(State(state.clone()), actor("a", "admin"), req("two"))
            .await
            .unwrap()
            .0["id"]
            .as_i64()
            .unwrap();
        let review_req = || {
            Json(ReviewRequest {
                approve: true,
                reason: "review".into(),
            })
        };
        let (r1, r2) = tokio::join!(
            review(
                State(state.clone()),
                actor("b", "admin"),
                Path(p),
                review_req()
            ),
            review(
                State(state.clone()),
                actor("c", "admin"),
                Path(p),
                review_req()
            )
        );
        assert_eq!(usize::from(r1.is_ok()) + usize::from(r2.is_ok()), 1);
        let status: String =
            sqlx::query_scalar("SELECT status FROM prevention_proposals WHERE id=$1")
                .bind(p)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(status, "APPROVED_DRY_RUN");
        let p = propose(State(state.clone()), actor("a", "admin"), req("three"))
            .await
            .unwrap()
            .0["id"]
            .as_i64()
            .unwrap();
        sqlx::query(
            "UPDATE prevention_proposals SET expires_at=now()-interval '1 second' WHERE id=$1",
        )
        .bind(p)
        .execute(&pool)
        .await
        .unwrap();
        let expired = review(
            State(state.clone()),
            actor("b", "admin"),
            Path(p),
            review_req(),
        )
        .await
        .unwrap()
        .0;
        assert_eq!(expired["status"], "EXPIRED");
        let audit: i64 = sqlx::query_scalar("SELECT count(*) FROM prevention_decisions")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(audit, 6);
        let jobs: i64 = sqlx::query_scalar("SELECT count(*) FROM firewall_actions")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(jobs, 0);
    }

    #[test]
    fn shadow_never_substitutes_verification() {
        assert_eq!(
            decide("SURICATA", 1, Some("8.8.8.8"), false, true, true)["decision"],
            "DENY"
        );
    }
    #[test]
    fn protected_addresses_always_denied() {
        for ip in [
            "127.77.0.1",
            "127.77.0.2",
            "192.168.10.1",
            "192.168.20.10",
            "10.0.0.1",
            "::1",
            "::ffff:127.0.0.1",
        ] {
            assert_eq!(
                decide("SURICATA", 1, Some(ip), true, true, true)["decision"],
                "DENY"
            );
        }
        assert_eq!(
            decide("SURICATA", 1, Some("8.8.8.8"), true, false, true)["decision"],
            "DENY"
        );
    }
    #[test]
    fn eligible_remains_non_executable() {
        let r = decide("SURICATA", 1, Some("8.8.8.8"), true, true, true);
        assert_eq!(r["decision"], "ALLOW");
        assert_eq!(r["execution_allowed"], false);
        assert_eq!(r["approval_enabled"], false);
    }
    #[test]
    fn missing_identity_denied_other_evidence_reviewed() {
        assert_eq!(
            decide("SURICATA", 1, None, true, true, true)["decision"],
            "DENY"
        );
        for (source, severity, evidence) in [
            ("AI", 1, true),
            ("NGINX", 1, true),
            ("STUDENT_AUDIT", 1, true),
            ("SURICATA", 3, true),
            ("SURICATA", 1, false),
        ] {
            assert_eq!(
                decide(source, severity, Some("8.8.8.8"), true, true, evidence)["decision"],
                "REVIEW"
            );
        }
    }
}
