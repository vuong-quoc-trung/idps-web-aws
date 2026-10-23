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
fn network_bytes() -> Option<u64> {
    let iface = env::var("ATTACKER_IFACE").unwrap_or("enp1s0".into());
    let text = std::fs::read_to_string("/proc/net/dev").ok()?;
    text.lines().find_map(|line| {
        let (name, values) = line.split_once(':')?;
        if name.trim() != iface {
            return None;
        }
        values.split_whitespace().next()?.parse().ok()
    })
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
pub async fn stats(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let (total,critical,blocked):(i64,i64,i64)=sqlx::query_as("SELECT count(*),count(*) FILTER(WHERE severity=1),count(*) FILTER(WHERE action='AUTO-BLOCK') FROM security_alerts").fetch_one(&state.pool).await.map_err(api_error)?;
    let trend=sqlx::query_scalar::<_,Value>("SELECT jsonb_build_object('hour',hours.h,'count',count(a.id)) FROM generate_series(date_trunc('hour',now())-interval '23 hours',date_trunc('hour',now()),interval '1 hour') hours(h) LEFT JOIN security_alerts a ON a.occurred_at>=hours.h AND a.occurred_at<hours.h+interval '1 hour' GROUP BY hours.h ORDER BY hours.h").fetch_all(&state.pool).await.map_err(api_error)?;
    let types=sqlx::query_scalar::<_,Value>("SELECT jsonb_build_object('name',rule_name,'count',count(*)) FROM security_alerts GROUP BY rule_name ORDER BY count(*) DESC LIMIT 8").fetch_all(&state.pool).await.map_err(api_error)?;
    let load = std::fs::read_to_string("/proc/loadavg")
        .ok()
        .and_then(|s| s.split_whitespace().next()?.parse::<f64>().ok());
    Ok(Json(
        json!({"total_alerts":total,"critical_alerts":critical,"blocked_attacks":blocked,"trend":trend,"types":types,
        "system":{"load_average_1m":load,"memory_percent":memory_percent(),"interface_rx_bytes":network_bytes(),"established_tcp_connections":connections()}}),
    ))
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
        && watchers.values().all(|s| s == "watching");
    (
        if healthy {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        Json(
            json!({"healthy":healthy,"database":database,"firewall":fw.is_ok(),"firewall_in_sync":in_sync,"watchers":watchers,"ingestion_errors":ingestion_errors}),
        ),
    )
}
