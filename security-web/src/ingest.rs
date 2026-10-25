use crate::*;
use sha2::{Digest, Sha256};
use std::{os::unix::fs::MetadataExt, path::Path as FsPath};
use tokio::{
    fs,
    io::{AsyncReadExt, AsyncSeekExt, SeekFrom},
};

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
#[derive(Debug)]
struct Event {
    time: DateTime<Utc>,
    src: Option<IpAddr>,
    dst: Option<IpAddr>,
    proto: Option<String>,
    rule: String,
    signature: Option<String>,
    category: Option<String>,
    severity: i16,
    evidence: String,
    auto: bool,
}
fn parse(source: &str, line: &str, policy: &PolicyEngine) -> Result<Option<Event>> {
    if source == "SURICATA" {
        let event: SuricataEvent = serde_json::from_str(line)?;
        if event.event_type != "alert" {
            return Ok(None);
        }
        let a = event.alert.context("Alert payload missing")?;
        let signature = a
            .signature
            .unwrap_or_else(|| "Unknown Suricata alert".into());
        Ok(Some(Event {
            time: parse_suricata_timestamp(&event.timestamp)?,
            src: event.src_ip,
            dst: event.dest_ip,
            proto: event.proto,
            rule: format!("SURICATA: {signature}"),
            signature: Some(signature),
            category: a.category,
            severity: a.severity.unwrap_or(3).clamp(1, 5) as i16,
            evidence: line.into(),
            auto: policy.evaluate_suricata(a.signature_id)
                == EventPolicyDecision::EligibleForAutoBlock,
        }))
    } else {
        let req = parse_nginx_request(line).context("Malformed Nginx combined log")?;
        let decoded = urlencoding::decode(&req.target)?.replace('+', " ");
        if !sql_injection_re().is_match(&decoded) {
            return Ok(None);
        }
        let timestamp = line
            .split_once('[')
            .and_then(|(_, s)| s.split_once(']'))
            .map(|(s, _)| s)
            .context("Missing Nginx time")?;
        Ok(Some(Event {
            time: DateTime::parse_from_str(timestamp, "%d/%b/%Y:%H:%M:%S %z")?.with_timezone(&Utc),
            src: Some(req.src_ip),
            dst: None,
            proto: Some("HTTP".into()),
            rule: "NGINX: SQL Injection".into(),
            signature: None,
            category: Some("Web Application Attack".into()),
            severity: 1,
            evidence: line.into(),
            auto: policy.evaluate_nginx() == EventPolicyDecision::EligibleForAutoBlock,
        }))
    }
}
#[derive(Clone, Serialize)]
pub struct WatcherStatus {
    pub state: String,
    pub last_success_at: Option<DateTime<Utc>>,
    pub last_data_at: Option<DateTime<Utc>>,
    pub pending_bytes: Option<u64>,
    pub error: Option<String>,
    #[serde(skip)]
    observed: BTreeMap<String, (u64, i64, i64)>,
}
impl Default for WatcherStatus {
    fn default() -> Self {
        Self {
            state: "starting".into(),
            last_success_at: None,
            last_data_at: None,
            pending_bytes: None,
            error: None,
            observed: BTreeMap::new(),
        }
    }
}
pub async fn watch(state: AppState, source: String, path: String) {
    loop {
        if let Err(e) = scan(&state, &source, &path).await {
            warn!(%source,error=%e,"Log watcher will retry");
        }
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    }
}
pub async fn scan(state: &AppState, source: &str, path: &str) -> Result<()> {
    let result = scan_source(state, source, path).await;
    if let Err(error) = &result {
        let mut statuses = state.watchers.write().await;
        let status = statuses.entry(source.into()).or_default();
        status.state = "error".into();
        status.error = Some(error.to_string());
        status.pending_bytes = None;
    }
    result
}
async fn scan_source(state: &AppState, source: &str, path: &str) -> Result<()> {
    let path = FsPath::new(path);
    let parent = path.parent().context("Log directory missing")?;
    let name = path
        .file_name()
        .context("Log filename missing")?
        .to_string_lossy();
    let mut entries = fs::read_dir(parent).await?;
    let mut paths = Vec::new();
    while let Some(entry) = entries.next_entry().await? {
        let file_name = entry.file_name().to_string_lossy().into_owned();
        if (file_name == name || file_name.starts_with(&format!("{name}.")))
            && !file_name.ends_with(".gz")
            && entry.file_type().await?.is_file()
        {
            paths.push(entry.path());
        }
    }
    paths.sort();
    let mut pending = 0_u64;
    let mut observed = BTreeMap::new();
    for candidate in paths {
        process_file(state, source, &candidate).await?;
        let meta = fs::metadata(&candidate).await?;
        let key = format!("{source}:{}:{}", meta.dev(), meta.ino());
        let offset =
            sqlx::query_scalar::<_, i64>("SELECT byte_offset FROM log_cursors WHERE file_key=$1")
                .bind(&key)
                .fetch_one(&state.pool)
                .await?;
        pending = pending.saturating_add(meta.len().saturating_sub(offset as u64));
        observed.insert(key, (meta.len(), meta.mtime(), meta.mtime_nsec()));
    }
    anyhow::ensure!(path.exists(), "Active log file is missing");
    let mut statuses = state.watchers.write().await;
    let status = statuses.entry(source.into()).or_default();
    if observed
        .iter()
        .any(|(key, version)| version.0 > 0 && status.observed.get(key) != Some(version))
    {
        status.last_data_at = Some(Utc::now());
    }
    status.observed = observed;
    status.last_success_at = Some(Utc::now());
    status.pending_bytes = Some(pending);
    status.state = "watching".into();
    status.error = None;
    Ok(())
}
async fn read_anchor(file: &mut fs::File, offset: i64) -> Result<String> {
    file.seek(SeekFrom::Start(0)).await?;
    let mut prefix = vec![0; offset.min(256) as usize];
    file.read_exact(&mut prefix).await?;
    file.seek(SeekFrom::Start(offset.saturating_sub(64).max(0) as u64))
        .await?;
    let mut tail = vec![0; offset.min(64) as usize];
    file.read_exact(&mut tail).await?;
    prefix.extend(tail);
    Ok(hash(&prefix))
}
pub async fn process_file(state: &AppState, source: &str, path: &FsPath) -> Result<()> {
    let mut file = fs::File::open(path).await?;
    let metadata = file.metadata().await?;
    let key = format!("{source}:{}:{}", metadata.dev(), metadata.ino());
    // A transaction locks the cursor, ingests at most 1 MiB, and commits alerts,
    // durable response jobs and the cursor together. Retries never advance on failure.
    let mut tx = state.pool.begin().await?;
    sqlx::query("INSERT INTO log_cursors(file_key,path) VALUES($1,$2) ON CONFLICT DO NOTHING")
        .bind(&key)
        .bind(path.to_string_lossy().as_ref())
        .execute(&mut *tx)
        .await?;
    let (mut offset, mut generation, anchor): (i64, i64, String) = sqlx::query_as(
        "SELECT byte_offset,generation,anchor FROM log_cursors WHERE file_key=$1 FOR UPDATE",
    )
    .bind(&key)
    .fetch_one(&mut *tx)
    .await?;
    let current_anchor = read_anchor(&mut file, offset).await.ok();
    if metadata.len() < offset as u64
        || (offset > 0 && current_anchor.as_deref() != Some(anchor.as_str()))
    {
        offset = 0;
        generation += 1;
    }
    file.seek(SeekFrom::Start(offset as u64)).await?;
    let mut bytes = Vec::new();
    (&mut file)
        .take(1024 * 1024)
        .read_to_end(&mut bytes)
        .await?;
    let Some(last) = bytes.iter().rposition(|&b| b == b'\n') else {
        anyhow::ensure!(
            bytes.len() < 1024 * 1024,
            "Log line exceeds 1 MiB; cursor retained for operator review"
        );
        // Persist a truncation reset even when the replacement file only has a partial line.
        let anchor_value = read_anchor(&mut file, offset).await?;
        sqlx::query(
            "UPDATE log_cursors SET byte_offset=$2,generation=$3,anchor=$4 WHERE file_key=$1",
        )
        .bind(&key)
        .bind(offset)
        .bind(generation)
        .bind(anchor_value)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        return Ok(());
    };
    let mut position = offset;
    for raw in bytes[..=last].split_inclusive(|&b| b == b'\n') {
        let event_key = hash(format!("{key}:{generation}:{position}:{}", hash(raw)).as_bytes());
        let parsed = std::str::from_utf8(raw)
            .map_err(anyhow::Error::from)
            .and_then(|s| parse(source, s.trim_end(), &state.policy));
        match parsed {
            Ok(Some(e)) => {
                let id=sqlx::query_scalar::<_,i64>("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,dest_ip,proto,rule_name,signature,category,severity,action,evidence,event_key) VALUES($1,$2,'alert',$3::inet,$4::inet,$5,$6,$7,$8,$9,'ALERT',$10,$11) ON CONFLICT(event_key) DO NOTHING RETURNING id")
                    .bind(e.time).bind(source).bind(e.src.map(|i|i.to_string())).bind(e.dst.map(|i|i.to_string())).bind(e.proto).bind(&e.rule).bind(e.signature).bind(e.category).bind(e.severity).bind(e.evidence).bind(&event_key)
                    .fetch_optional(&mut *tx).await?;
                if let (Some(id), Some(ip)) = (id, e.src)
                    && e.auto
                    && firewall::validate(state, &ip.to_string()).is_ok()
                {
                    sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,event_id) VALUES($1::inet,'BLOCK','AUTO',$2,'PENDING','system',$3) ON CONFLICT(event_id) DO NOTHING")
                            .bind(ip.to_string()).bind(e.rule).bind(id).execute(&mut *tx).await?;
                }
            }
            Ok(None) => {}
            Err(e) => {
                sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,$2,$3) ON CONFLICT DO NOTHING")
                    .bind(event_key).bind(source).bind(e.to_string()).execute(&mut *tx).await?;
            }
        }
        position += raw.len() as i64;
    }
    let anchor_value = read_anchor(&mut file, position).await?;
    sqlx::query("UPDATE log_cursors SET byte_offset=$2,generation=$3,anchor=$4,path=$5,updated_at=now() WHERE file_key=$1")
        .bind(key).bind(position).bind(generation).bind(anchor_value).bind(path.to_string_lossy().as_ref()).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_and_non_alert_events() {
        let p = PolicyEngine::new(false, vec![], false);
        assert!(parse("SURICATA", "invalid", &p).is_err());
        assert!(
            parse(
                "SURICATA",
                r#"{"timestamp":"2026-10-23T01:00:00.000000+0000","event_type":"flow"}"#,
                &p
            )
            .unwrap()
            .is_none()
        );
    }
    #[test]
    fn policy_is_opt_in() {
        let enabled = PolicyEngine::new(true, vec![1000001, 1000002], false);
        assert_eq!(
            enabled.evaluate_suricata(Some(1000003)),
            EventPolicyDecision::AlertOnly
        );
        assert_eq!(
            enabled.evaluate_suricata(Some(1000002)),
            EventPolicyDecision::EligibleForAutoBlock
        );
    }
}
