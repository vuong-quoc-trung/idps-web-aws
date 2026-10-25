use crate::*;
use serde_json::{Value, json};
fn memory_percent() -> Option<u64> {
    let text = std::fs::read_to_string("/proc/meminfo").ok()?;
    let read = |key: &str| {
        text.lines()
            .find(|s| s.starts_with(key))?
            .split_whitespace()
            .nth(1)?
            .parse::<u64>()
            .ok()
    };
    let total = read("MemTotal:")?;
    let available = read("MemAvailable:")?;
    if total == 0 || available > total {
        return None;
    }
    Some((total - available) * 100 / total)
}
static RESOURCE_SAMPLE: std::sync::OnceLock<tokio::sync::RwLock<Value>> =
    std::sync::OnceLock::new();
fn resource_sample() -> &'static tokio::sync::RwLock<Value> {
    RESOURCE_SAMPLE.get_or_init(|| tokio::sync::RwLock::new(json!({})))
}
fn network_bytes(iface: &str) -> Option<(u64, u64)> {
    let text = std::fs::read_to_string("/proc/net/dev").ok()?;
    text.lines().find_map(|line| {
        let (name, values) = line.split_once(':')?;
        if name.trim() != iface {
            return None;
        }
        let fields: Vec<_> = values.split_whitespace().collect();
        Some((fields.first()?.parse().ok()?, fields.get(8)?.parse().ok()?))
    })
}
fn rate(previous: u64, current: u64, elapsed: f64) -> Option<f64> {
    if elapsed <= 0.0 {
        return None;
    }
    current
        .checked_sub(previous)
        .map(|delta| delta as f64 / elapsed)
}
fn parse_disk(text: &str) -> Option<Value> {
    let fields: Vec<_> = text.lines().nth(1)?.split_whitespace().collect();
    Some(json!({"total_bytes":fields.first()?.parse::<u64>().ok()?,
        "available_bytes":fields.get(1)?.parse::<u64>().ok()?}))
}
pub async fn sample_resources() {
    let iface = env::var("ATTACKER_IFACE").unwrap_or("vmnet2".into());
    let disk_path = env::var("METRICS_DISK_PATH").unwrap_or("/".into());
    let mut previous: Option<(std::time::Instant, u64, u64)> = None;
    loop {
        let now = std::time::Instant::now();
        let counters = network_bytes(&iface);
        let (rx_rate, tx_rate) = match (previous, counters) {
            (Some((at, rx, tx)), Some((new_rx, new_tx))) => (
                rate(rx, new_rx, now.duration_since(at).as_secs_f64()),
                rate(tx, new_tx, now.duration_since(at).as_secs_f64()),
            ),
            _ => (None, None),
        };
        previous = counters.map(|(rx, tx)| (now, rx, tx));
        let mut command = tokio::process::Command::new("df");
        command
            .args(["-B1", "--output=size,avail", "--", &disk_path])
            .env("LC_ALL", "C")
            .kill_on_drop(true);
        let disk =
            match tokio::time::timeout(std::time::Duration::from_secs(2), command.output()).await {
                Ok(Ok(output)) if output.status.success() => {
                    parse_disk(&String::from_utf8_lossy(&output.stdout))
                }
                _ => None,
            };
        let hostname = std::fs::read_to_string("/proc/sys/kernel/hostname")
            .ok()
            .map(|s| s.trim().to_owned());
        *resource_sample().write().await = json!({"hostname":hostname,"interface":iface,"sampled_at":Utc::now(),
            "interface_rx_bytes":counters.map(|c|c.0),"interface_tx_bytes":counters.map(|c|c.1),
            "rx_bytes_per_second":rx_rate,"tx_bytes_per_second":tx_rate,
            "network_error":if counters.is_none() {Some("Không đọc được interface đã cấu hình")} else {None},
            "disk_path":disk_path,"disk":disk,"disk_error":if disk.is_none() {Some("Không đọc được dung lượng filesystem")} else {None}});
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}
fn connections() -> Option<usize> {
    let tcp = std::fs::read_to_string("/proc/net/tcp").ok()?;
    let tcp6 = std::fs::read_to_string("/proc/net/tcp6").unwrap_or_default();
    Some(
        tcp.lines()
            .chain(tcp6.lines())
            .filter(|l| l.split_whitespace().nth(3) == Some("01"))
            .count(),
    )
}
#[derive(Deserialize)]
pub struct StatsQuery {
    range: Option<String>,
}
pub async fn stats(
    State(state): State<AppState>,
    Query(query): Query<StatsQuery>,
) -> Result<Json<Value>, ApiError> {
    let range = query.range.as_deref().unwrap_or("24h");
    let (seconds, buckets) = match range {
        "1h" => (3600_i64, 12_i64),
        "24h" => (86400, 24),
        "7d" => (604800, 28),
        _ => return Err(bad_request("range must be 1h, 24h or 7d")),
    };
    let mut report = sqlx::query_scalar::<_, Value>(include_str!("overview.sql"))
        .bind(seconds)
        .bind(buckets)
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
    report["range"] = json!(range);
    let load = std::fs::read_to_string("/proc/loadavg")
        .ok()
        .and_then(|s| s.split_whitespace().next()?.parse::<f64>().ok());
    let mut system = resource_sample().read().await.clone();
    system["load_average_1m"] = json!(load);
    system["memory_percent"] = json!(memory_percent());
    system["established_tcp_connections"] = json!(connections());
    report["system"] = system;
    Ok(Json(report))
}
// Dashboard polling retrieves a report successfully even when a component is degraded.
pub async fn status(state: State<AppState>) -> Json<Value> {
    readiness(state).await.1
}

// Monitoring clients can use the HTTP code to check readiness.
pub async fn readiness(State(state): State<AppState>) -> (StatusCode, Json<Value>) {
    let database = sqlx::query("SELECT 1").execute(&state.pool).await.is_ok();
    let fw = firewall::kernel(&state).await;
    let watchers = state.watchers.read().await.clone();
    let ingestion_errors = sqlx::query_scalar::<_, i64>("SELECT count(*) FROM ingestion_errors")
        .fetch_one(&state.pool)
        .await
        .ok();
    let collection = sqlx::query_scalar::<_, Value>(r#"
        SELECT jsonb_object_agg(source, jsonb_build_object(
          'last_alert_at', (SELECT max(created_at) FROM security_alerts a WHERE a.source=s.source),
          'error_count', (SELECT count(*) FROM ingestion_errors e WHERE e.source=s.source),
          'last_error', (SELECT jsonb_build_object('at',created_at,'reason',reason) FROM ingestion_errors e WHERE e.source=s.source ORDER BY created_at DESC,event_key DESC LIMIT 1)
        )) FROM (VALUES ('NGINX'),('SURICATA')) s(source)
    "#).fetch_one(&state.pool).await.ok();
    let desired = sqlx::query_scalar::<_, String>("SELECT host(ip) FROM blocked_ips WHERE active")
        .fetch_all(&state.pool)
        .await
        .ok();
    let in_sync = match (&fw, &desired) {
        (Ok(actual), Some(desired)) => actual == &desired.iter().cloned().collect(),
        _ => false,
    };
    let healthy = database
        && fw.is_ok()
        && in_sync
        && watchers.len() == 2
        && watchers.values().all(|s| s.state == "watching");
    (
        if healthy {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        Json(
            json!({"healthy":healthy,"database":database,"firewall":fw.is_ok(),"firewall_in_sync":in_sync,"watchers":watchers,"collection":collection,"ingestion_errors":ingestion_errors}),
        ),
    )
}

#[cfg(test)]
mod resource_tests {
    use super::*;
    #[tokio::test]
    async fn sampler_publishes_context() {
        let task = tokio::spawn(sample_resources());
        let sampled = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            loop {
                let sample = resource_sample().read().await.clone();
                if sample.get("sampled_at").is_some() {
                    break sample;
                }
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        })
        .await;
        task.abort();
        let sample = sampled.expect("sampler should publish even when probes fail");
        assert!(sample["interface"].is_string());
        assert!(sample["disk_path"].is_string());
        assert!(sample.get("rx_bytes_per_second").is_some());
        assert!(sample["disk"].is_object() || sample["disk_error"].is_string());
    }
    #[test]
    fn rates_and_disk_values() {
        assert_eq!(rate(100, 300, 2.0), Some(100.0));
        assert_eq!(rate(300, 100, 2.0), None);
        assert_eq!(rate(1, 2, 0.0), None);
        assert_eq!(
            parse_disk(" Size Avail\n1000 400\n").unwrap()["available_bytes"],
            400
        );
        assert!(parse_disk("invalid").is_none());
    }
}
