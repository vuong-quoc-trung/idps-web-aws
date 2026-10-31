//! Application behavior observations are transactional with ingestion/checkpoints.
//! State survives restart, but expires after 5 minutes of receipt time and is capped
//! at 100,000 rows. Historical event time is preserved; late data beyond a window
//! is ignored for detection. No automatic actuator call exists in this module.
use crate::*;
use events::CanonicalEvent;
use serde_json::json;

pub struct Rule {
    pub code: &'static str,
    pub name: &'static str,
    pub threshold: i64,
    pub seconds: i64,
}
pub const RULES: [Rule; 5] = [
    Rule {
        code: "APP-1001",
        name: "Repeated Authentication Failures",
        threshold: 10,
        seconds: 60,
    },
    Rule {
        code: "APP-1002",
        name: "Repeated Authorization Violations",
        threshold: 8,
        seconds: 60,
    },
    Rule {
        code: "APP-1003",
        name: "Sensitive Endpoint Probing",
        threshold: 5,
        seconds: 60,
    },
    Rule {
        code: "APP-1004",
        name: "Application Request Burst",
        threshold: 100,
        seconds: 10,
    },
    Rule {
        code: "APP-1005",
        name: "Repeated Failed Requests",
        threshold: 15,
        seconds: 60,
    },
];
#[derive(FromRow)]
struct Observation {
    occurred_at: DateTime<Utc>,
    uri_path: Option<String>,
    status_code: Option<i32>,
    outcome: String,
}
fn matches(index: usize, o: &Observation, path: Option<&str>) -> bool {
    let uri = o.uri_path.as_deref().unwrap_or("");
    match index {
        0 => uri.starts_with("/api/auth/") && matches!(o.status_code, Some(401 | 403)),
        1 => uri.starts_with("/api/") && o.status_code == Some(403),
        // Only distinct paths visible in the redacted schema count. Unknown paths
        // collapsed to [redacted] cannot be reconstructed or counted as different.
        2 => {
            matches!(o.status_code, Some(401 | 403 | 404))
                && (o.status_code == Some(404)
                    || [
                        "/admin",
                        "/actuator",
                        "/swagger",
                        "/api/admin",
                        "/config",
                        "/.env",
                        "/api/users",
                        "/api/access-logs",
                    ]
                    .iter()
                    .any(|p| uri == *p || uri.starts_with(&format!("{p}/"))))
        }
        3 => true,
        4 => {
            o.uri_path.as_deref() == path
                && path.is_some()
                && o.outcome == "failure"
                && matches!(o.status_code, Some(400 | 401 | 403 | 404))
        }
        _ => false,
    }
}

pub async fn observe(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    state: &AppState,
    event: &CanonicalEvent,
    key: &str,
) -> Result<()> {
    if event.source != "STUDENT_AUDIT" || event.event_type != "http_request" {
        return Ok(());
    }
    let Some(ip) = event.client_ip else {
        return Ok(());
    };
    if event.timestamp > Utc::now() + chrono::Duration::seconds(5) {
        return Ok(());
    }
    // A global transaction lock bounds state even with concurrent log generations.
    // This deliberately favors simple correctness over distributed throughput in this lab.
    sqlx::query("SELECT pg_advisory_xact_lock(7141001)")
        .execute(&mut **tx)
        .await?;
    sqlx::query(
        "DELETE FROM application_observations WHERE received_at<now()-interval '5 minutes'",
    )
    .execute(&mut **tx)
    .await?;
    let inserted=sqlx::query("INSERT INTO application_observations(event_key,source_instance,client_ip,occurred_at,uri_path,status_code,outcome) VALUES($1,$2,$3::inet,$4,$5,$6,$7) ON CONFLICT DO NOTHING")
        .bind(key).bind(&event.source_instance).bind(ip.to_string()).bind(event.timestamp).bind(&event.uri_path).bind(event.status_code.map(i32::from)).bind(&event.outcome).execute(&mut **tx).await?.rows_affected();
    if inserted == 0 {
        return Ok(());
    }
    sqlx::query("DELETE FROM application_observations WHERE event_key IN (SELECT event_key FROM application_observations ORDER BY received_at DESC,event_key DESC OFFSET 100000)").execute(&mut **tx).await?;
    let watermark:Option<DateTime<Utc>>=sqlx::query_scalar("SELECT max(occurred_at) FROM application_observations WHERE source_instance=$1 AND client_ip=$2::inet").bind(&event.source_instance).bind(ip.to_string()).fetch_one(&mut **tx).await?;
    let Some(watermark) = watermark else {
        return Ok(());
    };
    if event.timestamp < watermark - chrono::Duration::seconds(60) {
        return Ok(());
    }
    let rows=sqlx::query_as::<_,Observation>("SELECT occurred_at,uri_path,status_code,outcome FROM application_observations WHERE source_instance=$1 AND client_ip=$2::inet AND occurred_at>$3 AND occurred_at<=$4 ORDER BY occurred_at")
        .bind(&event.source_instance).bind(ip.to_string()).bind(watermark-chrono::Duration::seconds(60)).bind(watermark).fetch_all(&mut **tx).await?;
    for (index, rule) in RULES.iter().enumerate() {
        let current = Observation {
            occurred_at: event.timestamp,
            uri_path: event.uri_path.clone(),
            status_code: event.status_code.map(i32::from),
            outcome: event.outcome.clone(),
        };
        if !matches(index, &current, event.uri_path.as_deref()) {
            continue;
        }
        let matching: Vec<_> = rows
            .iter()
            .filter(|o| {
                o.occurred_at > watermark - chrono::Duration::seconds(rule.seconds)
                    && matches(index, o, event.uri_path.as_deref())
            })
            .collect();
        let endpoints: std::collections::BTreeSet<_> = matching
            .iter()
            .filter_map(|o| o.uri_path.as_deref())
            .collect();
        let count = if index == 2 {
            endpoints.len() as i64
        } else {
            matching.len() as i64
        };
        if count < rule.threshold {
            continue;
        }
        let severity = if (index == 0 && count >= 20) || (index == 3 && count >= 300) {
            1
        } else if index == 4
            && !matching
                .iter()
                .any(|o| matches!(o.status_code, Some(401 | 403)))
        {
            3
        } else {
            2
        };
        let recommendation = if severity == 1 && firewall::validate(state, &ip.to_string()).is_ok()
        {
            "BLOCK"
        } else {
            "ALERT_ONLY"
        };
        let group = if index == 4 {
            event.uri_path.as_deref().unwrap_or("")
        } else {
            ""
        };
        let name = format!("{}: {}", rule.code, rule.name);
        let existing:Option<(i64,i16,String)>=sqlx::query_as("SELECT id,severity,evidence FROM security_alerts WHERE source='STUDENT_AUDIT' AND rule_name=$1 AND src_ip=$2::inet AND evidence::jsonb->>'source_instance'=$3 AND evidence::jsonb->>'group_endpoint'=$4 AND occurred_at<=$5 AND occurred_at>$6 ORDER BY occurred_at DESC,id DESC LIMIT 1 FOR UPDATE")
            .bind(&name).bind(ip.to_string()).bind(&event.source_instance).bind(group).bind(watermark).bind(watermark-chrono::Duration::seconds(rule.seconds)).fetch_optional(&mut **tx).await?;
        let mut evidence = json!({"rule_code":rule.code,"source":"STUDENT_AUDIT","source_instance":event.source_instance,"first_seen":matching[0].occurred_at,"last_seen":matching.last().unwrap().occurred_at,"event_count":matching.len(),"window_event_count":matching.len(),"distinct_endpoints":endpoints.len(),"window_seconds":rule.seconds,"group_endpoint":group,"uri_path":event.uri_path,"endpoints":endpoints.into_iter().take(10).collect::<Vec<_>>(),"status_codes":matching.iter().filter_map(|o|o.status_code).collect::<std::collections::BTreeSet<_>>(),"reason":format!("{}: {} {} in {} seconds (threshold {})",rule.name,count,if index==2 {"distinct endpoints"} else {"observations"},rule.seconds,rule.threshold),"recommended_action":recommendation,"request_id":event.request_id,"action_mode":"ALERT_ONLY"});
        if let Some((id, old_severity, old)) = existing {
            let old: serde_json::Value = serde_json::from_str(&old)?;
            // Keep peak window count/severity during cooldown; never downgrade an episode.
            if old["event_count"].as_u64() > evidence["event_count"].as_u64() {
                evidence["event_count"] = old["event_count"].clone();
            }
            evidence["first_seen"] = old["first_seen"].clone();
            if old["recommended_action"] == "BLOCK"
                && firewall::validate(state, &ip.to_string()).is_ok()
            {
                evidence["recommended_action"] = json!("BLOCK");
            }
            sqlx::query("UPDATE security_alerts SET severity=$2,evidence=$3 WHERE id=$1")
                .bind(id)
                .bind(severity.min(old_severity))
                .bind(evidence.to_string())
                .execute(&mut **tx)
                .await?;
        } else {
            sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,proto,rule_name,signature,category,severity,action,evidence,event_key) VALUES($1,'STUDENT_AUDIT','alert',$2::inet,'HTTP',$3,$4,'Application Behavior',$5,'ALERT',$6,$7) ON CONFLICT(event_key) DO NOTHING")
                .bind(watermark).bind(ip.to_string()).bind(&name).bind(rule.code).bind(severity).bind(evidence.to_string()).bind(format!("{key}:{}:{group}",rule.code)).execute(&mut **tx).await?;
        }
    }
    Ok(())
}
