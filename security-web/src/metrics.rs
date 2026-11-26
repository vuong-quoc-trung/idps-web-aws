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
fn default_interface(routes: &str) -> Option<String> {
    let routes = routes.lines().skip(1).filter_map(|line| {
        let parts: Vec<_> = line.split_whitespace().collect();
        let flags = u32::from_str_radix(parts.get(3)?, 16).ok()?;
        if parts[1] != "00000000"
            || *parts.get(7)? != "00000000"
            || flags & 1 == 0
            || flags & 0x200 != 0
            || parts[0] == "lo"
        {
            return None;
        }
        Some((parts.get(6)?.parse::<u32>().ok()?, parts[0]))
    });
    let mut best = None;
    let mut ambiguous = false;
    for (metric, interface) in routes {
        match best {
            None => best = Some((metric, interface)),
            Some((m, _)) if metric < m => {
                best = Some((metric, interface));
                ambiguous = false;
            }
            Some((m, i)) if metric == m && i != interface => ambiguous = true,
            _ => {}
        }
    }
    if ambiguous {
        None
    } else {
        best.map(|(_, name)| name.to_owned())
    }
}

fn cpu_ticks(stat: &str) -> Option<(u64, u64)> {
    let mut cpu = stat.lines().next()?.split_whitespace();
    if cpu.next()? != "cpu" {
        return None;
    }
    // guest and guest_nice are already counted in user and nice.
    let ticks = cpu
        .take(8)
        .map(str::parse::<u64>)
        .collect::<Result<Vec<_>, _>>()
        .ok()?;
    let idle = ticks.get(3)?.checked_add(*ticks.get(4)?)?;
    Some((ticks.iter().sum(), idle))
}

fn cpu_percent(previous: (u64, u64), current: (u64, u64)) -> Option<f64> {
    let total = current.0.checked_sub(previous.0)?;
    let idle = current.1.checked_sub(previous.1)?;
    let active = total.checked_sub(idle)?;
    (total > 0).then(|| active as f64 * 100.0 / total as f64)
}

pub async fn sample_resources() {
    let cloud = operations::aws_staging();
    let configured = if cloud {
        env::var("METRICS_INTERFACE").ok()
    } else {
        Some(env::var("ATTACKER_IFACE").unwrap_or("vmnet2".into()))
    };
    let disk_path = env::var("METRICS_DISK_PATH").unwrap_or("/".into());
    let mut previous: Option<(String, std::time::Instant, u64, u64)> = None;
    let mut previous_cpu = None;
    loop {
        let now = std::time::Instant::now();
        let iface = configured.clone().or_else(|| {
            std::fs::read_to_string("/proc/net/route")
                .ok()
                .and_then(|routes| default_interface(&routes))
        });
        let counters = iface.as_deref().and_then(network_bytes);
        let (rx_rate, tx_rate) = match (&previous, &iface, counters) {
            (Some((old_iface, at, rx, tx)), Some(name), Some((new_rx, new_tx)))
                if old_iface == name =>
            {
                (
                    rate(*rx, new_rx, now.duration_since(*at).as_secs_f64()),
                    rate(*tx, new_tx, now.duration_since(*at).as_secs_f64()),
                )
            }
            _ => (None, None),
        };
        previous = iface
            .clone()
            .zip(counters)
            .map(|(name, (rx, tx))| (name, now, rx, tx));
        let current_cpu = std::fs::read_to_string("/proc/stat")
            .ok()
            .and_then(|value| cpu_ticks(&value));
        let cpu = previous_cpu
            .zip(current_cpu)
            .and_then(|(old, current)| cpu_percent(old, current));
        previous_cpu = current_cpu;
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
        *resource_sample().write().await = json!({"hostname":hostname,"interface":iface,"sampled_at":Utc::now(),"cpu_percent":cpu,
            "interface_rx_bytes":counters.map(|c|c.0),"interface_tx_bytes":counters.map(|c|c.1),
            "rx_bytes_per_second":rx_rate,"tx_bytes_per_second":tx_rate,
            "network_error":if iface.is_none() {Some("Chưa xác định được giao diện mạng từ tuyến mặc định")} else if counters.is_none() {Some("Không đọc được bộ đếm của giao diện mạng")} else {None},
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
    after_alert_id: Option<i64>,
}
pub async fn stats(
    State(state): State<AppState>,
    Query(query): Query<StatsQuery>,
) -> Result<Json<Value>, ApiError> {
    let range = query.range.as_deref().unwrap_or("24h");
    let (seconds, buckets) = match range {
        "1h" => (3600_i64, 12_i64),
        "24h" => (86400, 24),
        "7d" => (604800, 7),
        _ => return Err(bad_request("range must be 1h, 24h or 7d")),
    };
    if query.after_alert_id.is_some_and(|id| id < 0) {
        return Err(bad_request("after_alert_id must be non-negative"));
    }
    let mut report = sqlx::query_scalar::<_, Value>(include_str!("overview.sql"))
        .bind(seconds)
        .bind(buckets)
        .bind(query.after_alert_id)
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

pub async fn monitoring_readiness(state: State<AppState>) -> (StatusCode, Json<Value>) {
    let (_, report) = readiness(state).await;
    let ready = report["monitoring_ready"].as_bool() == Some(true);
    (
        if ready {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        report,
    )
}

fn readiness_state(
    database: bool,
    watchers_ready: bool,
    mode: &str,
    verified: bool,
    execution_enabled: bool,
) -> (bool, &'static str) {
    let monitoring_ready = database && watchers_ready;
    let prevention = if mode == "OFF" {
        "DISABLED"
    } else if !execution_enabled {
        "BLOCKED"
    } else if monitoring_ready && verified {
        "READY"
    } else {
        "UNAVAILABLE"
    };
    (monitoring_ready, prevention)
}

// Legacy full-profile readiness still requires firewall readback.
pub async fn readiness(State(state): State<AppState>) -> (StatusCode, Json<Value>) {
    let database = sqlx::query("SELECT 1").execute(&state.pool).await.is_ok();
    let fw = firewall::observation(&state).await;
    let readable = fw["kernel"].is_array();
    let watchers = state.watchers.read().await.clone();
    let ingestion_errors = sqlx::query_scalar::<_, i64>("SELECT count(*) FROM ingestion_errors")
        .fetch_one(&state.pool)
        .await
        .ok();
    let collection = sqlx::query_scalar::<_, Value>(r#"
        SELECT jsonb_object_agg(source, jsonb_build_object(
          'last_ingested_at', CASE WHEN s.source='SURICATA_LUA' THEN (SELECT max(last_seen) FROM suricata_lua_shadow) ELSE (SELECT observed_at FROM normalized_events n WHERE n.source=s.source ORDER BY observed_at DESC,id DESC LIMIT 1) END,
          'last_ingested_event_at', (SELECT occurred_at FROM normalized_events n WHERE n.source=s.source ORDER BY observed_at DESC,id DESC LIMIT 1),
          'last_alert_at', (SELECT max(created_at) FROM security_alerts a WHERE a.source=s.source),
          'error_count', (SELECT count(*) FROM ingestion_errors e WHERE e.source=s.source),
          'last_error', (SELECT jsonb_build_object('at',created_at,'reason',reason) FROM ingestion_errors e WHERE e.source=s.source ORDER BY created_at DESC,event_key DESC LIMIT 1)
        )) FROM (VALUES ('NGINX'),('SURICATA'),('STUDENT_AUDIT'),('SURICATA_LUA')) s(source)
    "#).fetch_one(&state.pool).await.ok();
    let mut operations = operations::snapshot().await;
    if operations::aws_staging() {
        operations["profile"] = json!("aws-staging");
    }
    operations["hybrid_last_success_at"] = json!(hybrid::last_successful_refresh());
    let in_sync = fw["in_sync"].as_bool();
    let firewall_initialized = match fw["error"].as_str() {
        None if readable => Some(true),
        Some("FIREWALL_UNINITIALIZED") => Some(false),
        Some("FIREWALL_SCOPE_MISMATCH" | "FIREWALL_SCOPE_UNVERIFIED") => Some(true),
        _ => None,
    };
    let (monitoring_ready, prevention_state) = readiness_state(
        database,
        !watchers.is_empty() && watchers.values().all(|s| s.state == "watching"),
        &state.safety.mode,
        readable && in_sync == Some(true) && state.safety.discovery_ok,
        prevention::execution_enabled(),
    );
    let healthy = monitoring_ready && readable && in_sync != Some(false);
    (
        if healthy {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        Json(
            json!({"checked_at":Utc::now(),"operations":operations,"healthy":healthy,"monitoring_ready":monitoring_ready,"prevention_state":prevention_state,"database":database,"firewall":readable,"firewall_status":fw["error"].as_str().unwrap_or("READY"),"firewall_initialized":firewall_initialized,"kernel_blocked_count":fw["kernel"].as_array().map(Vec::len),"sync":fw["sync"],"firewall_in_sync":in_sync,"watchers":watchers,"collection":collection,"ingestion_errors":ingestion_errors,"dataset_collection":state.ingestion.collect_all,"schema_version":events::SCHEMA_VERSION,"enforcement_mode":state.safety.mode,"safety_discovery":state.safety.discovery_ok}),
        ),
    )
}

#[cfg(test)]
mod resource_tests {
    use super::*;
    #[test]
    fn monitoring_and_prevention_have_independent_status() {
        assert_eq!(
            readiness_state(true, true, "OFF", false, false),
            (true, "DISABLED")
        );
        assert_eq!(
            readiness_state(true, true, "MANUAL", false, true),
            (true, "UNAVAILABLE")
        );
        assert_eq!(
            readiness_state(true, true, "ENFORCE", true, true),
            (true, "READY")
        );
        assert_eq!(
            readiness_state(false, true, "ENFORCE", true, true),
            (false, "UNAVAILABLE")
        );
        assert_eq!(
            readiness_state(true, false, "OFF", true, false),
            (false, "DISABLED")
        );
        assert_eq!(
            readiness_state(true, true, "MANUAL", true, false),
            (true, "BLOCKED")
        );
    }
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

    #[test]
    fn host_metrics_require_a_valid_default_route_and_two_cpu_samples() {
        let routes = concat!(
            "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n",
            "lo 00000000 00000000 0001 0 0 0 00000000 0 0 0\n",
            "ens9 00000000 00000001 0002 0 0 0 00000000 0 0 0\n",
            "enp1s0 00000000 00000001 0003 0 0 100 00000000 0 0 0\n",
            "enp2s0 00000000 00000001 0003 0 0 10 00000000 0 0 0\n",
        );
        assert_eq!(default_interface(routes).as_deref(), Some("enp2s0"));
        let tie = format!("{routes}enp3s0 00000000 00000001 0003 0 0 10 00000000 0 0 0\n");
        assert!(default_interface(&tie).is_none());
        let old = cpu_ticks("cpu 10 0 0 90 0 0 0 0 9 0\n").unwrap();
        let new = cpu_ticks("cpu 35 0 0 165 0 0 0 0 20 0\n").unwrap();
        assert_eq!(cpu_percent(old, new), Some(25.0));
        assert_eq!(cpu_percent(old, old), None);
        assert_eq!(cpu_percent(new, old), None);
    }
}
