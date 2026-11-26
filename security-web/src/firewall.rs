use crate::*;
use std::collections::BTreeSet;
use tokio::time::{Duration, timeout};

#[cfg(feature = "isolated-c2")]
pub const LAB_SOCKET: &str = "/run/websentinel-r56-lab/actuator.sock";
#[cfg(feature = "isolated-c2")]
pub const LAB_PEER: &str = "10.254.56.2";

#[cfg(feature = "isolated-c2")]
pub async fn lab_rule_matches(pool: &sqlx::PgPool, event_id: i64, ip: IpAddr) -> Result<bool> {
    prevention::require_execution()?;
    Ok(sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM security_alerts
          WHERE id=$1 AND client_ip=$2::inet AND network_src_ip=$2::inet
            AND source='SURICATA' AND suricata_post_proxy IS FALSE
            AND occurred_at BETWEEN now()-interval '120 seconds' AND now()
            AND rule_code LIKE 'SID %'
            AND evidence::jsonb->>'flow_id' IS NOT NULL
            AND evidence::jsonb#>>'{suricata_origin,tx_id}' IS NOT NULL
            AND evidence::jsonb->'suricata_origin' @> jsonb_build_object(
                'network_src_ip',host($2::inet),'client_ip_verified',true,'post_proxy',false))",
    )
    .bind(event_id)
    .bind(ip.to_string())
    .fetch_one(pool)
    .await?)
}

pub async fn admit_manual(state: &AppState) -> Result<()> {
    prevention::require_execution()?;
    anyhow::ensure!(state.safety.mode == "MANUAL", "Manual mode required");
    parse_set(&run(&state.firewall_cmd, "list-json", None, None).await?)?;
    Ok(())
}

pub fn validate(state: &AppState, value: &str) -> Result<IpAddr> {
    let ip = state.safety.validate(value)?;
    #[cfg(feature = "isolated-c2")]
    if prevention::execution_enabled() {
        anyhow::ensure!(
            ip.to_string() == LAB_PEER,
            "Target is outside the approved lab peer"
        );
    }
    anyhow::ensure!(
        ip != state.ingestion.suricata_origin.proxy_ip,
        "Trusted proxy IP is protected"
    );
    anyhow::ensure!(
        !state.whitelist.contains(&ip),
        "IP is protected by whitelist"
    );
    Ok(ip)
}
pub async fn run(_cmd: &str, action: &str, ip: Option<IpAddr>, ttl: Option<u64>) -> Result<String> {
    #[cfg(feature = "isolated-c2")]
    if prevention::execution_enabled() {
        return lab_call(action, ip, ttl).await;
    }
    let _ = (ip, ttl);
    if action == "list-json" {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        return timeout(Duration::from_secs(4), async {
            let mut stream = tokio::net::UnixStream::connect("/run/ws-native-fw-status.sock")
                .await
                .context("ACTUATOR_OFFLINE")?;
            stream.write_all(b"STATUS\n").await?;
            stream.shutdown().await?;
            let mut reply = String::new();
            stream.take(262145).read_to_string(&mut reply).await?;
            anyhow::ensure!(reply.len() <= 262144, "ACTUATOR_ERROR");
            match reply.trim() {
                "SCOPE_UNVERIFIED" => bail!("FIREWALL_SCOPE_UNVERIFIED"),
                "SCOPE_MISMATCH" => bail!("FIREWALL_SCOPE_MISMATCH"),
                "UNINITIALIZED" => bail!("FIREWALL_UNINITIALIZED"),
                _ if !reply.starts_with('{') => bail!("ACTUATOR_ERROR"),
                _ => Ok(reply),
            }
        })
        .await
        .context("ACTUATOR_TIMEOUT")?;
    }
    bail!("C2_EXECUTION_DISABLED")
}

#[cfg(feature = "isolated-c2")]
async fn lab_call(action: &str, ip: Option<IpAddr>, ttl: Option<u64>) -> Result<String> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let request = match (action, ip, ttl) {
        ("list-json", None, None) => "STATUS\n".to_owned(),
        ("block", Some(target), Some(seconds))
            if target.to_string() == LAB_PEER && (1..=300).contains(&seconds) =>
        {
            format!("BLOCK {target} {seconds}\n")
        }
        ("unblock", Some(target), None) if target.to_string() == LAB_PEER => {
            format!("UNBLOCK {target}\n")
        }
        _ => bail!("C2_SCOPE_MISMATCH"),
    };
    timeout(Duration::from_secs(4), async {
        let mut stream = tokio::net::UnixStream::connect(LAB_SOCKET)
            .await
            .context("ACTUATOR_OFFLINE")?;
        anyhow::ensure!(stream.peer_cred()?.uid() == 0, "Untrusted actuator peer");
        stream.write_all(request.as_bytes()).await?;
        stream.shutdown().await?;
        let mut response = String::new();
        stream.take(32_769).read_to_string(&mut response).await?;
        anyhow::ensure!(
            response.len() <= 32_768 && response.starts_with('{'),
            "C2_ACTUATOR_REFUSED"
        );
        let snapshot: serde_json::Value = serde_json::from_str(&response)?;
        anyhow::ensure!(
            snapshot["nftables"]
                .as_array()
                .is_some_and(|items| items.iter().any(|item| {
                    let set = &item["set"];
                    set["family"] == "inet"
                        && set["table"] == "r56_prevention"
                        && set["name"] == "blocked_ips"
                        && set["type"] == "ipv4_addr"
                })),
            "C2_SCOPE_MISMATCH"
        );
        Ok(response)
    })
    .await
    .context("ACTUATOR_TIMEOUT")?
}
pub fn parse_set(text: &str) -> Result<BTreeSet<String>> {
    parse_named_set(text, false)
}

fn parse_named_set(text: &str, native: bool) -> Result<BTreeSet<String>> {
    let value: serde_json::Value = serde_json::from_str(text)?;
    let items = value["nftables"]
        .as_array()
        .context("Missing nftables array")?;
    let set = items
        .iter()
        .find_map(|item| {
            item.get("set").filter(|s| {
                if native {
                    s["family"] == "inet"
                        && s["table"] == "ws_native_lab_peer"
                        && s["name"] == "edge_peers"
                        && s["type"] == "ipv4_addr"
                } else {
                    s["name"] == "blocked_ips"
                }
            })
        })
        .context("Missing expected nftables set")?;
    let mut ips = BTreeSet::new();
    if let Some(elements) = set.get("elem") {
        for value in elements
            .as_array()
            .context("Unexpected nftables elements")?
        {
            let value = value
                .get("elem")
                .and_then(|e| e.get("val"))
                .unwrap_or(value);
            if let Some(ip) = value.as_str() {
                ips.insert(ip.parse::<IpAddr>()?.to_string());
            } else if let Some(range) = value.get("range").and_then(|r| r.as_array()) {
                anyhow::ensure!(range.len() == 2, "Invalid nftables range");
                let first = u32::from(
                    range[0]
                        .as_str()
                        .context("Invalid range start")?
                        .parse::<std::net::Ipv4Addr>()?,
                );
                let last = u32::from(
                    range[1]
                        .as_str()
                        .context("Invalid range end")?
                        .parse::<std::net::Ipv4Addr>()?,
                );
                anyhow::ensure!(
                    last >= first && last - first <= 4096,
                    "Firewall range too large to enumerate"
                );
                for ip in first..=last {
                    ips.insert(std::net::Ipv4Addr::from(ip).to_string());
                }
            } else if let Some(prefix) = value.get("prefix") {
                let addr = u32::from(
                    prefix["addr"]
                        .as_str()
                        .context("Invalid prefix address")?
                        .parse::<std::net::Ipv4Addr>()?,
                );
                let len = prefix["len"].as_u64().context("Invalid prefix length")?;
                anyhow::ensure!(
                    (20..=32).contains(&len),
                    "Firewall prefix too large to enumerate"
                );
                let size = 1u32 << (32 - len);
                let first = addr & !(size - 1);
                for offset in 0..size {
                    ips.insert(std::net::Ipv4Addr::from(first + offset).to_string());
                }
            } else {
                bail!("Unsupported nftables element; inspect ruleset");
            }
        }
    }
    Ok(ips)
}
pub fn native_status() -> bool {
    env::var("WS_NATIVE_FIREWALL_SOCKET").as_deref() == Ok("1")
}
pub async fn enqueue(
    pool: &PgPool,
    ip: IpAddr,
    action: &str,
    actor: &str,
    reason: &str,
    event: Option<i64>,
) -> Result<i64> {
    prevention::require_execution()?;
    let mut tx = pool.begin().await?;
    let id = enqueue_tx(&mut tx, ip, action, actor, reason, event, 300).await?;
    tx.commit().await?;
    Ok(id)
}
pub async fn enqueue_tx(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    ip: IpAddr,
    action: &str,
    actor: &str,
    reason: &str,
    event: Option<i64>,
    ttl: u64,
) -> Result<i64> {
    prevention::require_execution()?;
    anyhow::ensure!(
        matches!(action, "BLOCK" | "UNBLOCK") && (1..=300).contains(&ttl),
        "Invalid response action/TTL"
    );
    sqlx::query("SELECT pg_advisory_xact_lock(7272402)")
        .execute(&mut **tx)
        .await?;
    if action == "BLOCK" {
        let duplicate:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM blocked_ips WHERE ip=$1::inet AND active AND expires_at>now()) OR EXISTS(SELECT 1 FROM firewall_actions WHERE ip=$1::inet AND action='BLOCK' AND (status='PENDING' OR created_at>now()-interval '30 seconds'))").bind(ip.to_string()).fetch_one(&mut **tx).await?;
        anyhow::ensure!(!duplicate, "Duplicate block or response cooldown");
        let rate:i64=sqlx::query_scalar("SELECT count(*) FROM firewall_actions WHERE action='BLOCK' AND created_at>now()-interval '60 seconds'").fetch_one(&mut **tx).await?;
        anyhow::ensure!(rate < 10, "Response rate limit reached");
    }
    Ok(sqlx::query_scalar("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,event_id,expires_at) VALUES($1::inet,$2,'API',$3,'PENDING',$4,$5,now()+make_interval(secs=>$6)) RETURNING id")
        .bind(ip.to_string()).bind(action).bind(reason).bind(actor).bind(event).bind(ttl as f64).fetch_one(&mut **tx).await?)
}
#[derive(FromRow)]
struct Job {
    id: i64,
    ip: String,
    action: String,
    reason: String,
    event_id: Option<i64>,
    source: String,
    expires_at: Option<DateTime<Utc>>,
}
pub async fn process_one<F, Fut>(state: &AppState, execute: F) -> Result<bool>
where
    F: FnOnce(String, IpAddr, Option<u64>) -> Fut,
    Fut: std::future::Future<Output = Result<()>>,
{
    if !prevention::execution_enabled() || state.safety.mode == "OFF" {
        return Ok(false);
    }
    let mut tx = state.pool.begin().await?;
    let locked: bool = sqlx::query_scalar("SELECT pg_try_advisory_xact_lock(7272401)")
        .fetch_one(&mut *tx)
        .await?;
    if !locked {
        return Ok(false);
    }
    let job = sqlx::query_as::<_, Job>("SELECT id,host(ip)::text ip,action,reason,event_id,source,expires_at FROM firewall_actions WHERE status='PENDING' ORDER BY id LIMIT 1 FOR UPDATE")
        .fetch_optional(&mut *tx).await?;
    let Some(job) = job else {
        return Ok(false);
    };
    let validation = validate(state, &job.ip);
    let approved_restore = if job.action == "BLOCK" && job.source == "RESTORE" {
        sqlx::query_scalar::<_,bool>("SELECT EXISTS(SELECT 1 FROM firewall_actions WHERE ip=$1::inet AND source='API' AND action='BLOCK' AND status='SUCCESS' AND expires_at=$2)")
            .bind(&job.ip).bind(job.expires_at).fetch_one(&mut *tx).await?
    } else {
        false
    };
    let validation = if job.action == "BLOCK"
        && ((job.source == "AUTO" && !prevention::automatic_execution_enabled(&state.safety.mode))
            || (state.safety.mode == "MANUAL" && job.source != "API" && !approved_restore))
    {
        Err(anyhow::anyhow!("Automatic BLOCK capability not available"))
    } else if job.action == "BLOCK" && state.safety.discover_before_apply {
        match network::discover().await {
            Ok(protected) if protected.contains(&job.ip.parse::<IpAddr>()?) => {
                Err(anyhow::anyhow!("Current host/gateway IP is protected"))
            }
            Ok(_) => validation,
            Err(_) => Err(anyhow::anyhow!(
                "Safety discovery unavailable; BLOCK refused"
            )),
        }
    } else {
        validation
    };
    let validation = if job.action == "BLOCK" && job.expires_at.is_none_or(|at| at <= Utc::now()) {
        Err(anyhow::anyhow!(
            "BLOCK job expired or predates the response deadline contract"
        ))
    } else {
        validation
    };
    let ttl = if job.action == "BLOCK" {
        job.expires_at
            .map(|at| (at - Utc::now()).num_seconds().clamp(1, 300) as u64)
    } else {
        None
    };
    let result = match validation {
        Ok(ip) => execute(job.action.to_lowercase(), ip, ttl).await,
        Err(e) => Err(e),
    };
    let (status, details) = match result {
        Ok(()) => ("SUCCESS", None),
        Err(e) => ("ERROR", Some(e.to_string())),
    };
    if status == "SUCCESS" {
        sqlx::query("INSERT INTO blocked_ips(ip,reason,active,unblocked_at,expires_at) VALUES($1::inet,$2,$3,CASE WHEN $3 THEN NULL ELSE now() END,CASE WHEN $3 THEN $4 ELSE NULL END) ON CONFLICT(ip) DO UPDATE SET reason=$2,active=$3,blocked_at=CASE WHEN $3 THEN now() ELSE blocked_ips.blocked_at END,unblocked_at=CASE WHEN $3 THEN NULL ELSE now() END,expires_at=CASE WHEN $3 THEN $4 ELSE NULL END")
            .bind(&job.ip).bind(&job.reason).bind(job.action=="BLOCK").bind(job.expires_at).execute(&mut *tx).await?;
        if let Some(id) = job.event_id {
            sqlx::query("UPDATE security_alerts SET action=$2 WHERE id=$1")
                .bind(id)
                .bind(if job.source == "API" {
                    "BLOCK"
                } else {
                    "AUTO-BLOCK"
                })
                .execute(&mut *tx)
                .await?;
        }
    }
    sqlx::query("UPDATE firewall_actions SET status=$2,details=$3,completed_at=now() WHERE id=$1")
        .bind(job.id)
        .bind(status)
        .bind(details)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(true)
}
pub async fn restore_jobs(pool: &PgPool) -> Result<()> {
    if !prevention::execution_enabled() || cfg!(feature = "isolated-c2") {
        return Ok(());
    }
    sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,expires_at) SELECT b.ip,'BLOCK','RESTORE','Restore active block after backend restart','PENDING','system',b.expires_at FROM blocked_ips b WHERE b.active AND b.expires_at > now() AND NOT EXISTS (SELECT 1 FROM firewall_actions a WHERE a.ip=b.ip AND a.status='PENDING')")
        .execute(pool).await?;
    Ok(())
}
pub async fn worker(state: AppState) {
    if !prevention::execution_enabled() {
        return;
    }
    loop {
        match restore_jobs(&state.pool).await {
            Ok(()) => break,
            Err(e) => tracing::error!(error=%e, "Cannot prepare restore jobs; retrying"),
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
    loop {
        if let Err(e)=sqlx::query("UPDATE blocked_ips SET active=false,unblocked_at=now() WHERE active AND expires_at<=now()").execute(&state.pool).await {
            tracing::error!(error=%e,"Cannot reconcile expired response deadlines");
        }
        let cmd = state.firewall_cmd.clone();
        match process_one(&state, move |action, ip, ttl| async move {
            run(&cmd, &action, Some(ip), ttl).await?;
            let actual = match run(&cmd, "list-json", None, None)
                .await
                .and_then(|text| parse_set(&text))
            {
                Ok(actual) => actual,
                Err(e) => {
                    if action == "block" {
                        let _ = run(&cmd, "unblock", Some(ip), None).await;
                    }
                    return Err(e.context("Kernel verification failed; attempted BLOCK rollback"));
                }
            };
            if actual.contains(&ip.to_string()) != (action == "block") {
                if action == "block" {
                    let _ = run(&cmd, "unblock", Some(ip), None).await;
                }
                bail!("Kernel response verification failed; attempted BLOCK rollback");
            }
            Ok(())
        })
        .await
        {
            Ok(true) => continue,
            Err(e) => tracing::error!(error=%e,"Firewall worker failed; pending job retained"),
            _ => {}
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}
#[derive(Deserialize)]
struct Lease {
    ip: String,
    rid: String,
    issued: i64,
    expires: i64,
}

fn reconcile(
    db_read: bool,
    kernel: Option<&BTreeSet<String>>,
    leases: Option<&[Lease]>,
    tags: &serde_json::Value,
    bound: bool,
) -> serde_json::Value {
    use serde_json::json;
    let scope = if native_status() {
        "inet ws_native_lab_peer/edge_peers"
    } else {
        "legacy"
    };
    let result = |status, reason, differences: Vec<String>| {
        json!({
            "status":status, "reason":reason, "scope":scope, "differences":differences
        })
    };
    let unknown = |reason| result("UNVERIFIED", reason, vec![]);
    let Some(actual) = kernel else {
        return unknown("KERNEL_UNAVAILABLE");
    };
    if !db_read {
        return unknown("DATABASE_UNAVAILABLE");
    }
    let Some(leases) = leases else {
        return unknown("JOURNAL_UNAVAILABLE");
    };
    if !bound {
        return unknown("DATABASE_BINDING_UNVERIFIED");
    }
    let mut expected = BTreeSet::new();
    let mut differences = Vec::new();
    for lease in leases {
        if lease.expires <= Utc::now().timestamp() + 1 || !expected.insert(lease.ip.clone()) {
            return unknown("LEASE_TRANSITION");
        }
        if !actual.contains(&lease.ip) {
            differences.push(format!(
                "{} · DB và journal có lease đã ACK; thiếu IP trong kernel",
                lease.ip
            ));
        } else {
            match tags[&lease.ip].as_str() {
                None => return unknown("KERNEL_LEASE_BINDING_UNVERIFIED"),
                Some(tag) if tag != lease.rid => differences.push(format!(
                    "{} · Request ID của kernel khác lease đã ACK",
                    lease.ip
                )),
                _ => {}
            }
        }
    }
    for ip in actual.difference(&expected) {
        differences.push(format!(
            "{ip} · có trong kernel; thiếu lease BLOCK_IP hiệu lực trong journal"
        ));
    }
    if differences.is_empty() {
        result("SYNCED", "MATCH", differences)
    } else {
        result("OUT_OF_SYNC", "DIFFERENCE", differences)
    }
}

pub async fn observation(state: &AppState) -> serde_json::Value {
    use serde_json::{Value, json};
    // blocked_ips has no native table/chain or request ID. Keep its rows for
    // inspection; the native worker persists applied leases in SQLite instead.
    let rows=sqlx::query_as::<_,BlockedIpRow>("SELECT host(ip)::text ip,reason,blocked_at,unblocked_at,active,expires_at FROM blocked_ips WHERE active AND (expires_at IS NULL OR expires_at>now()) ORDER BY blocked_at DESC")
        .fetch_all(&state.pool).await.ok();
    let snapshot = run(&state.firewall_cmd, "list-json", None, None)
        .await
        .and_then(|s| {
            let ips = parse_named_set(&s, native_status())?;
            Ok((ips, serde_json::from_str::<Value>(&s)?))
        });
    let mut tags = json!({});
    let mut leases = None;
    if let Ok((_, ref value)) = snapshot
        && native_status()
    {
        leases = serde_json::from_value::<Vec<Lease>>(value["worker_leases"].clone()).ok();
        for item in value["nftables"].as_array().into_iter().flatten() {
            let set = &item["set"];
            if set["family"] == "inet"
                && set["table"] == "ws_native_lab_peer"
                && set["name"] == "edge_peers"
            {
                for elem in set["elem"].as_array().into_iter().flatten() {
                    if let Some(ip) = elem["elem"]["val"].as_str() {
                        tags[ip] = elem["elem"]["comment"].clone();
                    }
                }
            }
        }
    }
    let mut bound = rows.is_some();
    // Legacy blocked_ips rows do not describe the native scope. For a
    // native ACK, bind the trigger back to one Student Audit transaction.
    if bound && let Some(records) = &leases {
        for lease in records {
            let matched=sqlx::query_scalar::<_,bool>("SELECT count(*)=1 FROM normalized_events WHERE source='STUDENT_AUDIT' AND request_id=$1 AND occurred_at BETWEEN to_timestamp($2::bigint)-interval '62 seconds' AND to_timestamp($2::bigint)+interval '2 seconds'")
                .bind(&lease.rid).bind(lease.issued).fetch_one(&state.pool).await;
            if !matches!(matched, Ok(true)) {
                bound = false;
                break;
            }
        }
    }
    let kernel = snapshot.as_ref().ok().map(|(ips, _)| ips);
    #[cfg(feature = "isolated-c2")]
    let sync = if prevention::execution_enabled() {
        match (&rows, kernel) {
            (Some(db), Some(actual)) => {
                let expected: BTreeSet<_> = db.iter().map(|row| row.ip.clone()).collect();
                json!({"status": if expected == *actual {"SYNCED"} else {"OUT_OF_SYNC"},
                    "reason":"LAB_DB_KERNEL_READBACK", "scope":"inet r56_prevention/blocked_ips",
                    "differences": expected.symmetric_difference(actual).collect::<Vec<_>>()})
            }
            _ => {
                json!({"status":"UNVERIFIED","reason":"LAB_READBACK_UNAVAILABLE","differences":[]})
            }
        }
    } else {
        reconcile(rows.is_some(), kernel, leases.as_deref(), &tags, bound)
    };
    #[cfg(not(feature = "isolated-c2"))]
    let sync = reconcile(rows.is_some(), kernel, leases.as_deref(), &tags, bound);
    let compatible = match sync["status"].as_str() {
        Some("SYNCED") => Some(true),
        Some("OUT_OF_SYNC") => Some(false),
        _ => None,
    };
    json!({"database":rows,"kernel":kernel,"sync":sync,"in_sync":compatible,
        "error":snapshot.as_ref().err().map(ToString::to_string)})
}
pub async fn list(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    Ok(Json(observation(&state).await))
}
#[derive(Deserialize)]
pub struct AuditQuery {
    event_id: Option<i64>,
}
pub async fn audit(
    State(state): State<AppState>,
    Query(query): Query<AuditQuery>,
) -> Result<Json<Vec<serde_json::Value>>, ApiError> {
    let rows=sqlx::query_scalar::<_,serde_json::Value>("SELECT to_jsonb(a) FROM (SELECT id,host(ip) ip,action,actor,source,reason,status,details,created_at,completed_at,event_id FROM firewall_actions WHERE ($1::bigint IS NULL OR event_id=$1) ORDER BY id DESC LIMIT 100) a")
        .bind(query.event_id).fetch_all(&state.pool).await.map_err(api_error)?;
    Ok(Json(rows))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sync_api_contract() {
        let empty = BTreeSet::new();
        let ip = "192.168.1.19".to_string();
        let actual = BTreeSet::from([ip.clone()]);
        let tags = serde_json::json!({&ip:"request"});
        let live = [Lease {
            ip: ip.clone(),
            rid: "request".into(),
            issued: Utc::now().timestamp(),
            expires: Utc::now().timestamp() + 15,
        }];
        assert_eq!(
            reconcile(true, Some(&empty), None, &tags, true)["status"],
            "UNVERIFIED"
        );
        assert_eq!(
            reconcile(true, Some(&actual), Some(&live), &tags, true)["status"],
            "SYNCED"
        );
        for (kernel, journal) in [(&empty, live.as_slice()), (&actual, &[][..])] {
            let report = reconcile(true, Some(kernel), Some(journal), &tags, true);
            assert_eq!(report["status"], "OUT_OF_SYNC");
            assert!(report["differences"][0].as_str().unwrap().contains(&ip));
        }
        assert_eq!(
            reconcile(false, Some(&empty), Some(&[]), &tags, true)["status"],
            "UNVERIFIED"
        );
        assert_eq!(
            reconcile(true, None, Some(&[]), &tags, true)["status"],
            "UNVERIFIED"
        );
        assert_eq!(
            reconcile(true, Some(&actual), Some(&live), &tags, false)["status"],
            "UNVERIFIED"
        );
        // OFF/CONTINUOUS and the timer are not execution evidence.
        assert_eq!(
            reconcile(true, Some(&empty), Some(&[]), &tags, true)["status"],
            "SYNCED"
        );
    }
    #[test]
    fn native_peer_set_status() {
        let mut snapshot = serde_json::json!({"nftables":[{"set":{
            "family":"inet","table":"ws_native_lab_peer","type":"ipv4_addr","name":"edge_peers"
        }}]});
        assert!(
            parse_named_set(&snapshot.to_string(), true)
                .unwrap()
                .is_empty()
        );
        let elements = serde_json::json!([{"elem":{"val":"192.168.1.19","expires":7000}}]);
        snapshot["nftables"][0]["set"]["elem"] = elements;
        assert!(
            parse_named_set(&snapshot.to_string(), true)
                .unwrap()
                .contains("192.168.1.19")
        );
        snapshot["nftables"][0]["set"]["table"] = "other".into();
        assert!(parse_named_set(&snapshot.to_string(), true).is_err());
    }
    #[test]
    fn empty_and_populated_sets() {
        assert!(
            parse_set(r#"{"nftables":[{"set":{"name":"blocked_ips"}}]}"#)
                .unwrap()
                .is_empty()
        );
        assert!(
            parse_set(r#"{"nftables":[{"set":{"name":"blocked_ips","elem":["192.168.10.10"]}}]}"#)
                .unwrap()
                .contains("192.168.10.10")
        );
        assert!(parse_set("{}").is_err());
        assert_eq!(parse_set(r#"{"nftables":[{"set":{"name":"blocked_ips","elem":[{"range":["192.168.10.10","192.168.10.11"]}]}}]}"#).unwrap().len(),2);
        assert_eq!(parse_set(r#"{"nftables":[{"set":{"name":"blocked_ips","elem":[{"prefix":{"addr":"192.168.10.10","len":32}}]}}]}"#).unwrap().len(),1);
    }
}
