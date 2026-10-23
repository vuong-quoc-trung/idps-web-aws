use crate::*;
use std::collections::BTreeSet;
use tokio::{
    process::Command,
    time::{Duration, timeout},
};

pub fn validate(state: &AppState, value: &str) -> Result<IpAddr> {
    let ip = validate_lab_attacker_ip(value)?;
    anyhow::ensure!(
        !state.whitelist.contains(&ip),
        "IP is protected by whitelist"
    );
    Ok(ip)
}
pub async fn run(cmd: &str, action: &str, ip: Option<IpAddr>) -> Result<String> {
    let mut command = Command::new("sudo");
    command.arg("-n").arg(cmd).arg(action);
    if let Some(ip) = ip {
        command.arg(ip.to_string());
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
    parse_set(&run(&state.firewall_cmd, "list-json", None).await?)
}
pub async fn enqueue(
    pool: &PgPool,
    ip: IpAddr,
    action: &str,
    actor: &str,
    reason: &str,
    event: Option<i64>,
) -> Result<i64> {
    Ok(sqlx::query_scalar("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,event_id) VALUES($1::inet,$2,$3,$4,'PENDING',$5,$6) RETURNING id")
        .bind(ip.to_string()).bind(action).bind(if event.is_some() {"AUTO"} else {"API"}).bind(reason).bind(actor).bind(event).fetch_one(pool).await?)
}
#[derive(FromRow)]
struct Job {
    id: i64,
    ip: String,
    action: String,
    reason: String,
    event_id: Option<i64>,
}
pub async fn process_one<F, Fut>(state: &AppState, execute: F) -> Result<bool>
where
    F: FnOnce(String, IpAddr) -> Fut,
    Fut: std::future::Future<Output = Result<()>>,
{
    let mut tx = state.pool.begin().await?;
    let locked: bool = sqlx::query_scalar("SELECT pg_try_advisory_xact_lock(7272401)")
        .fetch_one(&mut *tx)
        .await?;
    if !locked {
        return Ok(false);
    }
    let job = sqlx::query_as::<_, Job>("SELECT id,host(ip)::text ip,action,reason,event_id FROM firewall_actions WHERE status='PENDING' ORDER BY id LIMIT 1 FOR UPDATE")
        .fetch_optional(&mut *tx).await?;
    let Some(job) = job else {
        return Ok(false);
    };
    let validation = if job.action == "BLOCK" {
        validate(state, &job.ip)
    } else {
        validate_lab_attacker_ip(&job.ip)
    };
    let result = match validation {
        Ok(ip) => execute(job.action.to_lowercase(), ip).await,
        Err(e) => Err(e),
    };
    let (status, details) = match result {
        Ok(()) => ("SUCCESS", None),
        Err(e) => ("ERROR", Some(e.to_string())),
    };
    if status == "SUCCESS" {
        sqlx::query("INSERT INTO blocked_ips(ip,reason,active,unblocked_at) VALUES($1::inet,$2,$3,CASE WHEN $3 THEN NULL ELSE now() END) ON CONFLICT(ip) DO UPDATE SET reason=$2,active=$3,blocked_at=CASE WHEN $3 THEN now() ELSE blocked_ips.blocked_at END,unblocked_at=CASE WHEN $3 THEN NULL ELSE now() END")
            .bind(&job.ip).bind(&job.reason).bind(job.action=="BLOCK").execute(&mut *tx).await?;
        if let Some(id) = job.event_id {
            sqlx::query("UPDATE security_alerts SET action='AUTO-BLOCK' WHERE id=$1")
                .bind(id)
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
    sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,actor) SELECT b.ip,'BLOCK','RESTORE','Restore active block after backend restart','PENDING','system' FROM blocked_ips b WHERE b.active AND NOT EXISTS (SELECT 1 FROM firewall_actions a WHERE a.ip=b.ip AND a.status='PENDING')")
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
        let cmd = state.firewall_cmd.clone();
        match process_one(&state, move |action, ip| async move {
            run(&cmd, &action, Some(ip)).await.map(|_| ())
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
pub async fn audit(
    State(state): State<AppState>,
) -> Result<Json<Vec<serde_json::Value>>, ApiError> {
    let rows=sqlx::query_scalar::<_,serde_json::Value>("SELECT to_jsonb(a) FROM (SELECT id,host(ip) ip,action,actor,source,reason,status,details,created_at,completed_at FROM firewall_actions ORDER BY id DESC LIMIT 100) a")
        .fetch_all(&state.pool).await.map_err(api_error)?;
    Ok(Json(rows))
}
#[cfg(test)]
mod tests {
    use super::*;
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
