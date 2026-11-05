//! Server-confirmed decisions only: never infer ownership/privilege from generic 401/403.
use crate::*;
use events::{CanonicalEvent, SecuritySignals};
use serde_json::json;

#[derive(FromRow)]
struct Observation {
    occurred_at: DateTime<Utc>,
    signals: sqlx::types::Json<SecuritySignals>,
    status_code: i32,
}
fn has(s: &SecuritySignals, reason: &str) -> bool {
    s.reasons.iter().any(|r| r == reason)
}
fn matches(code: &str, s: &SecuritySignals, status: i32) -> bool {
    match code {
        "APP-1011" => has(s, "LOGIN_FAILED") && status == 401 && s.account_hmac.is_some(),
        "APP-1012" => {
            has(s, "OBJECT_ACCESS_DENIED") && matches!(status, 403 | 404) && s.object_hmac.is_some()
        }
        "APP-1013" => has(s, "MASS_ASSIGNMENT") && status == 400 && !s.forbidden_fields.is_empty(),
        "APP-1014" => has(s, "PRIVILEGE_DENIED") && status == 403,
        "APP-1015" => (has(s, "INVALID_SESSION") || has(s, "SESSION_REVOKED")) && status == 401,
        "APP-1016" => has(s, "WORKFLOW_DENIED") && matches!(status, 401 | 403 | 409),
        _ => false,
    }
}
pub async fn observe(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    event: &CanonicalEvent,
    key: &str,
) -> Result<()> {
    let Some(signals) = &event.security else {
        return Ok(());
    };
    if event.source != "STUDENT_AUDIT"
        || event.timestamp > Utc::now() + chrono::Duration::seconds(5)
    {
        return Ok(());
    }
    let Some(status) = event.status_code else {
        return Ok(());
    };
    sqlx::query("SELECT pg_advisory_xact_lock(7141002)")
        .execute(&mut **tx)
        .await?;
    sqlx::query("DELETE FROM application_security_observations WHERE received_at < now()-interval '10 minutes'").execute(&mut **tx).await?;
    let inserted=sqlx::query("INSERT INTO application_security_observations(event_key,source_instance,client_ip,actor_hmac,occurred_at,signals,status_code) VALUES($1,$2,$3::inet,$4,$5,$6,$7) ON CONFLICT DO NOTHING")
        .bind(key).bind(&event.source_instance).bind(event.client_ip.map(|ip|ip.to_string())).bind(&event.user_id).bind(event.timestamp).bind(sqlx::types::Json(signals)).bind(i32::from(status)).execute(&mut **tx).await?.rows_affected();
    if inserted == 0 {
        return Ok(());
    }
    sqlx::query("DELETE FROM application_security_observations WHERE event_key IN (SELECT event_key FROM application_security_observations ORDER BY received_at DESC,event_key DESC OFFSET 100000)").execute(&mut **tx).await?;
    for rule in application_detection::RULES.iter().skip(10) {
        if !matches(rule.code, signals, i32::from(status)) {
            continue;
        }
        let actor_group = rule.code == "APP-1012";
        let subject = if actor_group {
            event.user_id.clone()
        } else {
            event.client_ip.map(|ip| ip.to_string())
        };
        let Some(subject) = subject else {
            continue;
        };
        let watermark: DateTime<Utc> = sqlx::query_scalar("SELECT max(occurred_at) FROM application_security_observations WHERE source_instance=$1 AND (CASE WHEN $2 THEN actor_hmac=$3 ELSE host(client_ip)=$3 END)")
            .bind(&event.source_instance).bind(actor_group).bind(&subject).fetch_one(&mut **tx).await?;
        let rows=sqlx::query_as::<_,Observation>("SELECT occurred_at,signals,status_code FROM application_security_observations WHERE source_instance=$1 AND (CASE WHEN $2 THEN actor_hmac=$3 ELSE host(client_ip)=$3 END) AND occurred_at>$4 AND occurred_at<=$5 ORDER BY occurred_at")
            .bind(&event.source_instance).bind(actor_group).bind(&subject).bind(watermark-chrono::Duration::seconds(rule.seconds)).bind(watermark).fetch_all(&mut **tx).await?;
        let rows: Vec<_> = rows
            .iter()
            .filter(|o| matches(rule.code, &o.signals, o.status_code))
            .collect();
        let distinct: std::collections::BTreeSet<_> = rows
            .iter()
            .filter_map(|o| {
                if actor_group {
                    o.signals.object_hmac.as_deref()
                } else {
                    o.signals.account_hmac.as_deref()
                }
            })
            .collect();
        let count = if matches!(rule.code, "APP-1011" | "APP-1012") {
            distinct.len()
        } else {
            rows.len()
        };
        if count < rule.threshold as usize {
            continue;
        }
        let severity: i16 = if matches!(rule.code, "APP-1013" | "APP-1014") {
            1
        } else {
            2
        };
        let evidence = json!({"rule_code":rule.code,"source":"STUDENT_AUDIT","source_instance":event.source_instance,"subject_hmac_or_ip":subject,"first_seen":rows[0].occurred_at,"last_seen":watermark,"event_count":rows.len(),"window_event_count":rows.len(),"distinct_count":distinct.len(),"window_seconds":rule.seconds,"uri_path":event.uri_path,"request_id":event.request_id,"reason":format!("{}: {} server-confirmed {} in {} seconds; no IP/account auto-block",rule.name,count,if actor_group {"distinct objects"} else if rule.code=="APP-1011" {"attempted account pseudonyms"} else {"denials"},rule.seconds),"security_reasons":signals.reasons,"forbidden_fields":signals.forbidden_fields,"recommended_action":"ALERT_ONLY","action_mode":"ALERT_ONLY"});
        // Include a future episode for out-of-order arrival so late data never creates a second episode.
        let existing:Option<(i64,String)>=sqlx::query_as("SELECT id,evidence FROM security_alerts WHERE source='STUDENT_AUDIT' AND signature=$1 AND evidence::jsonb->>'source_instance'=$2 AND evidence::jsonb->>'subject_hmac_or_ip'=$3 AND occurred_at>$4 AND occurred_at<$5 ORDER BY occurred_at DESC LIMIT 1 FOR UPDATE")
            .bind(rule.code).bind(&event.source_instance).bind(&subject).bind(watermark-chrono::Duration::seconds(rule.seconds)).bind(watermark+chrono::Duration::seconds(rule.seconds)).fetch_optional(&mut **tx).await?;
        if let Some((id, old)) = existing {
            let old: serde_json::Value = serde_json::from_str(&old)?;
            let mut evidence = evidence;
            if old["event_count"].as_u64() > evidence["event_count"].as_u64() {
                evidence["event_count"] = old["event_count"].clone();
            }
            if old["last_seen"]
                .as_str()
                .and_then(|v| DateTime::parse_from_rfc3339(v).ok())
                .is_some_and(|v| v > watermark)
            {
                continue;
            }
            evidence["first_seen"] = old["first_seen"].clone();
            sqlx::query("UPDATE security_alerts SET evidence=$2 WHERE id=$1")
                .bind(id)
                .bind(evidence.to_string())
                .execute(&mut **tx)
                .await?;
        } else {
            sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,proto,rule_name,signature,category,severity,action,evidence,event_key) VALUES($1,'STUDENT_AUDIT','alert',$2::inet,'HTTP',$3,$4,'Application Security Decision',$5,'ALERT',$6,$7) ON CONFLICT(event_key) DO NOTHING")
                .bind(watermark).bind(event.client_ip.map(|ip|ip.to_string())).bind(format!("{}: {}",rule.code,rule.name)).bind(rule.code).bind(severity).bind(evidence.to_string()).bind(format!("{key}:{}",rule.code)).execute(&mut **tx).await?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn event(reason: &str, n: usize, status: u16) -> CanonicalEvent {
        let mut e = CanonicalEvent::new("STUDENT_AUDIT", Utc::now());
        e.client_ip = Some("192.0.2.10".parse().unwrap());
        e.user_id = Some(format!("hmac-sha256:{}", "a".repeat(64)));
        e.status_code = Some(status);
        e.security = Some(SecuritySignals {
            reasons: vec![reason.into()],
            account_hmac: Some(format!("hmac-sha256:{n:064x}")),
            object_hmac: Some(format!("hmac-sha256:{n:064x}")),
            forbidden_fields: vec!["role".into()],
        });
        e
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn thresholds_distinct_subjects_replay_and_out_of_order(pool: PgPool) {
        for (code, reason, threshold, status) in [
            ("APP-1011", "LOGIN_FAILED", 8, 401),
            ("APP-1012", "OBJECT_ACCESS_DENIED", 5, 404),
            ("APP-1013", "MASS_ASSIGNMENT", 1, 400),
            ("APP-1014", "PRIVILEGE_DENIED", 1, 403),
            ("APP-1015", "SESSION_REVOKED", 10, 401),
            ("APP-1016", "WORKFLOW_DENIED", 1, 403),
        ] {
            let mut tx = pool.begin().await.unwrap();
            for n in 0..threshold {
                let mut e = event(reason, n, status);
                e.source_instance = code.into();
                // A late final observation must complete the window, not be discarded.
                if n == threshold - 1 {
                    e.timestamp -= chrono::Duration::seconds(1);
                }
                if code == "APP-1012" {
                    e.client_ip = Some(format!("192.0.2.{}", n + 1).parse().unwrap());
                }
                let key = format!("{code}-{n}");
                observe(&mut tx, &e, &key).await.unwrap();
                observe(&mut tx, &e, &key).await.unwrap();
                let count: i64 =
                    sqlx::query_scalar("SELECT count(*) FROM security_alerts WHERE signature=$1")
                        .bind(code)
                        .fetch_one(&mut *tx)
                        .await
                        .unwrap();
                assert_eq!(count, i64::from(n == threshold - 1), "{code}, n={n}");
            }
            tx.commit().await.unwrap();
        }
        let actions: Vec<String> =
            sqlx::query_scalar("SELECT DISTINCT action FROM security_alerts")
                .fetch_all(&pool)
                .await
                .unwrap();
        assert_eq!(actions, vec!["ALERT"]);
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn repeated_one_identity_and_generic_errors_do_not_trigger(pool: PgPool) {
        let mut tx = pool.begin().await.unwrap();
        for n in 0..20 {
            let e = event("LOGIN_FAILED", 1, 401);
            observe(&mut tx, &e, &format!("repeated-{n}"))
                .await
                .unwrap();
            let mut generic = e.clone();
            generic.security = None;
            observe(&mut tx, &generic, &format!("generic-{n}"))
                .await
                .unwrap();
        }
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM security_alerts")
            .fetch_one(&mut *tx)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }
    #[test]
    fn requires_explicit_decision_and_matching_status() {
        let e = event("MASS_ASSIGNMENT", 1, 400);
        let s = e.security.unwrap();
        assert!(matches("APP-1013", &s, 400));
        assert!(!matches("APP-1013", &s, 200));
        assert!(!matches("APP-1014", &s, 403));
        assert!(!matches("APP-1015", &s, 401));
    }
}
