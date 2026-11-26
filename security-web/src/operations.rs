// Read-only operational probes. Never invoke sudo, SSH, restart or sensor reload.
use crate::*;
use serde_json::{Value, json};
static SAMPLE: OnceLock<RwLock<Value>> = OnceLock::new();
fn sample() -> &'static RwLock<Value> {
    SAMPLE.get_or_init(|| RwLock::new(json!({})))
}
pub async fn snapshot() -> Value {
    sample().read().await.clone()
}
pub fn aws_staging() -> bool {
    env::var("WS_OPERATIONS_PROFILE").as_deref() == Ok("aws-staging")
}

const AWS_UNITS: [(&str, &str); 6] = [
    ("nginx", "nginx.service"),
    ("student", "websentinel-r47-student.service"),
    ("postgresql", "postgresql@18-main.service"),
    ("suricata", "websentinel-r48-sensor.service"),
    ("correlator", "websentinel-r48-correlator.service"),
    ("r37", "websentinel-r47-scorer.service"),
];

async fn aws_services() -> Value {
    let probes = futures_util::future::join_all(
        AWS_UNITS
            .iter()
            .map(|(key, unit)| async { (key.to_string(), service(unit).await) }),
    )
    .await;
    Value::Object(probes.into_iter().collect())
}

async fn service(unit: &str) -> Value {
    let mut command = tokio::process::Command::new("systemctl");
    command
        .args([
            "show",
            unit,
            "--property=LoadState,ActiveState,SubState,WatchdogTimestampMonotonic",
        ])
        .kill_on_drop(true);
    match tokio::time::timeout(std::time::Duration::from_secs(2), command.output()).await {
        Ok(Ok(output)) if output.status.success() => {
            let text = String::from_utf8_lossy(&output.stdout);
            let field = |key: &str| {
                text.lines()
                    .find_map(|line| line.strip_prefix(key))
                    .unwrap_or("unknown")
                    .to_owned()
            };
            let watchdog_us = field("WatchdogTimestampMonotonic=").parse::<u64>().ok();
            let uptime = tokio::fs::read_to_string("/proc/uptime").await.ok();
            let watchdog_age_seconds = uptime
                .as_deref()
                .and_then(|s| s.split_whitespace().next()?.parse::<f64>().ok())
                .zip(watchdog_us.filter(|t| *t > 0))
                .map(|(up, stamp)| (up - stamp as f64 / 1_000_000.0).max(0.0));
            json!({"load":field("LoadState="),"active":field("ActiveState="),"sub":field("SubState="),
                "watchdog_age_seconds":watchdog_age_seconds})
        }
        _ => json!({"load":"unknown","active":"unknown","sub":"unknown"}),
    }
}
async fn native_mode() -> &'static str {
    let bytes = match tokio::fs::read("/etc/ws-native/approval.json").await {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return "OFF",
        Err(_) => return "UNVERIFIED",
    };
    let Ok(policy) = serde_json::from_slice::<Value>(&bytes) else {
        return "UNVERIFIED";
    };
    let Some(start) = policy["start"].as_i64() else {
        return "UNVERIFIED";
    };
    let now = Utc::now().timestamp();
    let Some(actions) = policy["actions"].as_object() else {
        return "UNVERIFIED";
    };
    if actions.is_empty() || start > now {
        return "OFF";
    }
    let mode = match policy.get("mode").and_then(Value::as_str).unwrap_or("LAB") {
        "LAB" => match policy["end"].as_i64() {
            Some(end) if end > start && end.saturating_sub(start) <= 600 => {
                if now >= end {
                    return "OFF";
                }
                "LAB"
            }
            _ => return "UNVERIFIED",
        },
        "CONTINUOUS" => {
            if service("ws-native-continuous.service").await["active"] != "active" {
                return "UNVERIFIED";
            }
            "CONTINUOUS"
        }
        _ => return "UNVERIFIED",
    };
    match service("ws-native-worker.timer").await["active"].as_str() {
        Some("active") => mode,
        Some("inactive") => "OFF",
        _ => "UNVERIFIED",
    }
}

pub async fn monitor() {
    let cloud = aws_staging();
    let path = env::var("SURICATA_RULES_DEPLOYED_PATH").unwrap_or_else(|_| {
        if cloud {
            "/opt/websentinel-r48/runtime/pbl4.rules"
        } else {
            "/var/lib/suricata/rules/pbl4.rules"
        }
        .into()
    });
    loop {
        let services = if cloud {
            let units = aws_services().await;
            json!({"profile":"aws-staging","services":units,"suricata":units["suricata"]})
        } else {
            let (receiver, sensor) = tokio::join!(
                service("pbl4-audit-receiver.service"),
                service(if firewall::native_status() {
                    "ws-native-sensor.service"
                } else {
                    "suricata.service"
                })
            );
            json!({"profile":"local","receiver":receiver,"suricata":sensor,
                "sender":{"active":"unknown","reason":"Remote sender is not probed from Security host"}})
        };
        // Bound the read even if the configured path unexpectedly points to a large file.
        use tokio::io::AsyncReadExt;
        let file = tokio::time::timeout(std::time::Duration::from_secs(2), async {
            let file = tokio::fs::File::open(&path).await?;
            let mut bytes = Vec::new();
            file.take(2 * 1024 * 1024 + 1)
                .read_to_end(&mut bytes)
                .await?;
            Ok::<_, std::io::Error>(bytes)
        })
        .await;
        let matches = match file {
            Ok(Ok(bytes)) if bytes.len() <= 2 * 1024 * 1024 => {
                Some(bytes == include_bytes!("../suricata/pbl4.rules"))
            }
            _ => None,
        };
        let mut report = services;
        report["native_authorization"] = json!(if !cloud && firewall::native_status() {
            Some(native_mode().await)
        } else {
            None
        });
        report["sampled_at"] = json!(Utc::now());
        report["suricata_rules_file"] = json!({"path":path,"matches_build":matches});
        report["suricata_loaded_rules_verified"] = json!(false);
        *sample().write().await = report;
        tokio::time::sleep(std::time::Duration::from_secs(15)).await;
    }
}
pub async fn annotate_rules(state: &AppState, rules: &mut [Value]) {
    // Latest persisted alert per exact code. Legacy records lacking a reliable code
    // remain unclassified rather than guessing from human-readable names.
    let evidence=sqlx::query_as::<_,(String,String,i64,DateTime<Utc>,DateTime<Utc>)>(
        "SELECT DISTINCT ON(source,rule_code) source,rule_code,id,occurred_at,created_at FROM security_alerts WHERE rule_code IS NOT NULL ORDER BY source,rule_code,created_at DESC,id DESC"
    ).fetch_all(&state.pool).await;
    let probe = snapshot().await;
    for rule in rules {
        let source = rule["source"].as_str().unwrap_or_default().to_owned();
        let code = rule["code"].as_str().unwrap_or_default();
        let last = evidence
            .as_ref()
            .ok()
            .and_then(|rows| rows.iter().find(|r| r.0 == source && r.1 == code));
        let observation = last.map(|r| json!({"alert_id":r.2,"occurred_at":r.3,"ingested_at":r.4}));
        rule["verification"] = json!({
            "catalog":true,
            "implementation":if source=="SURICATA" {"EXTERNAL_SENSOR"} else {"RUNNING_BACKEND"},
            "deployment":if source=="SURICATA" {"UNVERIFIED"} else {"BUILT_IN"},
            "deployed_file_matches_build":if source=="SURICATA" {probe["suricata_rules_file"]["matches_build"].clone()} else {Value::Null},
            "evidence_available":evidence.is_ok(),
            "last_alert":observation,
            "tested_current_deployment":false
        });
    }
}
