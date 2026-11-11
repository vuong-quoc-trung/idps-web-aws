use crate::*;
use std::collections::BTreeSet;
use tokio::{
    process::Command,
    time::{Duration, timeout},
};

pub fn validate(state: &AppState, value: &str) -> Result<IpAddr> {
    let ip = state.safety.validate(value)?;
    anyhow::ensure!(
        !state.whitelist.contains(&ip),
        "IP is protected by whitelist"
    );
    Ok(ip)
}
pub async fn run(cmd: &str, action: &str, ip: Option<IpAddr>, ttl: Option<u64>) -> Result<String> {
    let mut command = if env::var("PBL4_DISPOSABLE_NAMESPACE_RESPONSE").as_deref() == Ok("true") {
        // sudo cannot initialize inside this unprivileged user namespace. This
        // opt-in is impossible in the initial/host user namespace: only a single
        // non-root host UID mapped to namespace root is accepted.
        let mapping = std::fs::read_to_string("/proc/self/uid_map")?;
        anyhow::ensure!(
            namespace_mapping_safe(&mapping),
            "Direct response requires a disposable unprivileged user namespace"
        );
        Command::new(cmd)
    } else {
        let mut c = Command::new("sudo");
        c.arg("-n").arg(cmd);
        c
    };
    command.arg(action);
    if let Some(ip) = ip {
        command.arg(ip.to_string());
    }
    if let Some(ttl) = ttl {
        command.arg(ttl.to_string());
    }
    command.kill_on_drop(true);
    let out = timeout(Duration::from_secs(5), command.output())
        .await
        .context("Firewall command timed out")??;
    anyhow::ensure!(
        out.status.success(),
        "Firewall command failed: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    Ok(String::from_utf8(out.stdout)?)
}
pub fn namespace_mapping_safe(mapping: &str) -> bool {
    let values: Vec<_> = mapping.split_whitespace().collect();
    values.len() == 3
        && values[0] == "0"
        && values[1].parse::<u32>().is_ok_and(|v| v > 0)
        && values[2] == "1"
}
pub fn parse_set(text: &str) -> Result<BTreeSet<String>> {
    let value: serde_json::Value = serde_json::from_str(text)?;
    let items = value["nftables"]
        .as_array()
        .context("Missing nftables array")?;
    let set = items
        .iter()
        .find_map(|item| item.get("set").filter(|s| s["name"] == "blocked_ips"))
        .context("Missing blocked_ips set")?;
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
pub async fn kernel(state: &AppState) -> Result<BTreeSet<String>> {
    parse_set(&run(&state.firewall_cmd, "list-json", None, None).await?)
}
pub async fn enqueue(
    pool: &PgPool,
    ip: IpAddr,
    action: &str,
    actor: &str,
    reason: &str,
    event: Option<i64>,
) -> Result<i64> {
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
    if state.safety.mode == "OFF" {
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
    let validation = if job.action == "BLOCK" {
        validate(state, &job.ip)
    } else {
        network::Safety::parse_host(&job.ip)
    };
    let approved_restore = if job.action == "BLOCK" && job.source == "RESTORE" {
        sqlx::query_scalar::<_,bool>("SELECT EXISTS(SELECT 1 FROM firewall_actions WHERE ip=$1::inet AND source='API' AND action='BLOCK' AND status='SUCCESS' AND expires_at=$2)")
            .bind(&job.ip).bind(job.expires_at).fetch_one(&mut *tx).await?
    } else {
        false
    };
    let validation = if job.action == "BLOCK"
        && state.safety.mode == "MANUAL"
        && job.source != "API"
        && !approved_restore
    {
        Err(anyhow::anyhow!("Automatic BLOCK disabled in MANUAL mode"))
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
    sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,expires_at) SELECT b.ip,'BLOCK','RESTORE','Restore active block after backend restart','PENDING','system',b.expires_at FROM blocked_ips b WHERE b.active AND b.expires_at > now() AND NOT EXISTS (SELECT 1 FROM firewall_actions a WHERE a.ip=b.ip AND a.status='PENDING')")
        .execute(pool).await?;
    Ok(())
}
pub async fn worker(state: AppState) {
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
pub async fn list(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let rows=sqlx::query_as::<_,BlockedIpRow>("SELECT host(ip)::text ip,reason,blocked_at,unblocked_at,active FROM blocked_ips WHERE active ORDER BY blocked_at DESC")
        .fetch_all(&state.pool).await.map_err(api_error)?;
    let result = kernel(&state).await;
    let desired: BTreeSet<String> = rows.iter().map(|r| r.ip.clone()).collect();
    Ok(Json(match result {
        Ok(actual) => {
            serde_json::json!({"database":rows,"kernel":actual,"in_sync":desired==actual,"error":null})
        }
        Err(e) => {
            serde_json::json!({"database":rows,"kernel":null,"in_sync":false,"error":e.to_string()})
        }
    }))
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
    fn direct_response_never_allowed_in_host_user_namespace() {
        assert!(!namespace_mapping_safe("0 0 4294967295"));
        assert!(!namespace_mapping_safe("0 1000 65536"));
        assert!(namespace_mapping_safe("0 1000 1"));
        assert!(!namespace_mapping_safe("0 1000 1\n1 0 1"));
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
