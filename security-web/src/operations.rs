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
async fn service(unit: &str) -> Value {
    let mut command = tokio::process::Command::new("systemctl");
    command
        .args(["show", unit, "--property=LoadState,ActiveState,SubState"])
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
            json!({"load":field("LoadState="),"active":field("ActiveState="),"sub":field("SubState=")})
        }
        _ => json!({"load":"unknown","active":"unknown","sub":"unknown"}),
    }
}
pub async fn monitor() {
    let path = env::var("SURICATA_RULES_DEPLOYED_PATH")
        .unwrap_or("/var/lib/suricata/rules/pbl4.rules".into());
    loop {
        let (receiver, sensor) = tokio::join!(
            service("pbl4-audit-receiver.service"),
            service("suricata.service")
        );
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
        *sample().write().await = json!({
            "sampled_at":Utc::now(), "receiver":receiver, "suricata":sensor,
            "sender":{"active":"unknown","reason":"Remote sender is not probed from Security host"},
            "suricata_rules_file":{"path":path,"matches_build":matches},
            "suricata_loaded_rules_verified":false
        });
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
