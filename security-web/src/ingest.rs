use crate::events::{self, CanonicalEvent};
use crate::*;
use sha2::{Digest, Sha256};
use std::{os::unix::fs::MetadataExt, path::Path as FsPath};
use tokio::{
    fs,
    io::{AsyncReadExt, AsyncSeekExt, SeekFrom},
};

const SCAN_BYTES: usize = 1024 * 1024;
#[derive(Clone, Debug)]
pub struct Config {
    pub collect_all: bool,
    pub max_line_bytes: usize,
    pub auth_threshold: i64,
    pub auth_window_seconds: i64,
    pub retention_days: i64,
    pub max_events: i64,
    pub max_response_age_seconds: i64,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            collect_all: false,
            max_line_bytes: 64 * 1024,
            auth_threshold: 10,
            auth_window_seconds: 60,
            retention_days: 7,
            max_events: 1_000_000,
            max_response_age_seconds: 60,
        }
    }
}
impl Config {
    pub fn from_env() -> Result<Self> {
        let mut c = Self::default();
        if let Ok(v) = env::var("COLLECT_ALL_EVENTS") {
            c.collect_all = v.parse().context("COLLECT_ALL_EVENTS must be true/false")?;
        }
        if let Ok(v) = env::var("INGEST_MAX_LINE_BYTES") {
            c.max_line_bytes = v.parse()?;
        }
        if let Ok(v) = env::var("AUTH_FAILURE_THRESHOLD") {
            c.auth_threshold = v.parse()?;
        }
        if let Ok(v) = env::var("AUTH_FAILURE_WINDOW_SECONDS") {
            c.auth_window_seconds = v.parse()?;
        }
        if let Ok(v) = env::var("DATASET_RETENTION_DAYS") {
            c.retention_days = v.parse()?;
        }
        if let Ok(v) = env::var("ENFORCE_MAX_EVENT_AGE_SECONDS") {
            c.max_response_age_seconds = v.parse()?;
        }
        anyhow::ensure!(
            (1..=300).contains(&c.max_response_age_seconds),
            "Invalid event freshness limit"
        );
        if let Ok(v) = env::var("DATASET_MAX_EVENTS") {
            c.max_events = v.parse()?;
        }
        anyhow::ensure!(
            (1024..=SCAN_BYTES / 2).contains(&c.max_line_bytes),
            "INGEST_MAX_LINE_BYTES must be 1024..524288"
        );
        anyhow::ensure!(
            (2..=1000).contains(&c.auth_threshold) && (1..=3600).contains(&c.auth_window_seconds),
            "Invalid authentication threshold/window"
        );
        anyhow::ensure!(
            (1..=365).contains(&c.retention_days) && (1..=10_000_000).contains(&c.max_events),
            "Invalid dataset retention/capacity"
        );
        Ok(c)
    }
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
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

async fn quarantine(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    source: &str,
    file_key: &str,
    generation: i64,
    start: i64,
    raw: &[u8],
) -> Result<()> {
    let key = hash(format!("{file_key}:{generation}:{start}:{}", hash(raw)).as_bytes());
    sqlx::query("INSERT INTO ingestion_quarantine(event_key,source,file_key,generation,byte_start,byte_end,reason) VALUES($1,$2,$3,$4,$5,$6,'oversized record discarded; byte range only') ON CONFLICT DO NOTHING")
        .bind(&key).bind(source).bind(file_key).bind(generation).bind(start).bind(start+raw.len() as i64).execute(&mut **tx).await?;
    sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,$2,'oversized record quarantined; no raw content retained') ON CONFLICT DO NOTHING")
        .bind(key).bind(source).execute(&mut **tx).await?;
    Ok(())
}

struct AlertSpec<'a> {
    key: &'a str,
    name: &'a str,
    category: Option<&'a str>,
    severity: i16,
    auto: bool,
}
async fn save_alert(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    state: &AppState,
    event: &CanonicalEvent,
    alert: AlertSpec<'_>,
) -> Result<()> {
    let AlertSpec {
        key,
        name,
        category,
        severity,
        auto,
    } = alert;
    let evidence = serde_json::to_string(event)?;
    let name: String = name.chars().take(160).collect();
    let age = Utc::now() - event.timestamp;
    let auto = auto
        && age >= chrono::Duration::seconds(-5)
        && age <= chrono::Duration::seconds(state.ingestion.max_response_age_seconds);
    let id = sqlx::query_scalar::<_, i64>("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,dest_ip,proto,rule_name,signature,category,severity,action,evidence,event_key) VALUES($1,$2,'alert',$3::inet,$4::inet,$5,$6,$6,$7,$8,'ALERT',$9,$10) ON CONFLICT(event_key) DO NOTHING RETURNING id")
        .bind(event.timestamp).bind(&event.source).bind(event.client_ip.map(|p|p.to_string())).bind(event.dest_ip.map(|p|p.to_string())).bind(&event.transport).bind(&name).bind(category).bind(severity).bind(evidence).bind(key).fetch_optional(&mut **tx).await?;
    if let (Some(id), Some(ip)) = (id, event.client_ip)
        && auto
        && firewall::validate(state, &ip.to_string()).is_ok()
    {
        sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,actor,event_id,expires_at) VALUES($1::inet,'BLOCK','AUTO',$2,'PENDING','system',$3,$4) ON CONFLICT(event_id) DO NOTHING")
            .bind(ip.to_string()).bind(name).bind(id).bind(event.timestamp + chrono::Duration::seconds(state.ingestion.max_response_age_seconds)).execute(&mut **tx).await?;
    }
    Ok(())
}

async fn auth_failure(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    state: &AppState,
    event: &CanonicalEvent,
    event_key: &str,
) -> Result<bool> {
    let Some(ip) = event.client_ip else {
        return Ok(false);
    };
    let Some(path) = &event.uri_path else {
        return Ok(false);
    };
    let Some(status) = event.status_code else {
        return Ok(false);
    };
    if event.source == "SURICATA"
        || event.http_method.as_deref() != Some("POST")
        || !(path.starts_with("/api/auth/") || path == "/login")
        || !(status < 400 || matches!(status, 401 | 403))
    {
        return Ok(false);
    }
    // Serialize the small per-client state transaction across both log watchers.
    let client = ip.to_string();
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1, 4197))")
        .bind(format!("{client}:{path}"))
        .execute(&mut **tx)
        .await?;
    let identity = event
        .request_id
        .as_ref()
        .map(|id| hash(format!("{client}:{path}:{id}").as_bytes()))
        .unwrap_or_else(|| event_key.into());
    let changed = sqlx::query("INSERT INTO auth_observations(observation_key,client_ip,uri_path,occurred_at,status_code) VALUES($1,$2::inet,$3,$4,$5) ON CONFLICT DO NOTHING")
        .bind(identity).bind(&client).bind(path).bind(event.timestamp).bind(status as i32).execute(&mut **tx).await?.rows_affected();
    if changed == 0 || status < 400 {
        return Ok(false);
    }
    let since = event.timestamp - chrono::Duration::seconds(state.ingestion.auth_window_seconds);
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM auth_observations WHERE client_ip=$1::inet AND uri_path=$2 AND status_code IN (401,403) AND occurred_at >= $3 AND occurred_at <= $4 AND occurred_at > COALESCE((SELECT max(occurred_at) FROM auth_observations WHERE client_ip=$1::inet AND uri_path=$2 AND status_code<400 AND occurred_at <= $4),'-infinity'::timestamptz)")
        .bind(&client).bind(path).bind(since).bind(event.timestamp).fetch_one(&mut **tx).await?;
    if count < state.ingestion.auth_threshold {
        return Ok(false);
    }
    let last: Option<DateTime<Utc>> = sqlx::query_scalar(
        "SELECT last_alert_at FROM auth_detection_state WHERE client_ip=$1::inet AND uri_path=$2",
    )
    .bind(&client)
    .bind(path)
    .fetch_optional(&mut **tx)
    .await?
    .flatten();
    if last.is_some_and(|t| {
        event.timestamp - t < chrono::Duration::seconds(state.ingestion.auth_window_seconds)
    }) {
        return Ok(false);
    }
    sqlx::query("INSERT INTO auth_detection_state(client_ip,uri_path,last_alert_at) VALUES($1::inet,$2,$3) ON CONFLICT(client_ip,uri_path) DO UPDATE SET last_alert_at=$3")
        .bind(client).bind(path).bind(event.timestamp).execute(&mut **tx).await?;
    Ok(true)
}

async fn ingest_line(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    state: &AppState,
    source: &str,
    physical_key: &str,
    raw: &[u8],
) -> Result<()> {
    let parsed = std::str::from_utf8(raw)
        .map_err(anyhow::Error::from)
        .and_then(|line| events::parse(source, line.trim_end()));
    let mut parsed = match parsed {
        Ok(event) => event,
        Err(_) => {
            // Error messages from JSON parsers can echo attacker-controlled values.
            sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,$2,'invalid source record or unsupported schema; raw content suppressed') ON CONFLICT DO NOTHING")
                .bind(physical_key).bind(source).execute(&mut **tx).await?;
            return Ok(());
        }
    };
    let event = &mut parsed.canonical;
    if event.event_id.is_empty() {
        event.event_id = physical_key.into();
    }
    if event.source != "STUDENT_AUDIT" && event.source_instance == "local" {
        event.source_instance = state.sensor_id.clone();
    }
    if event.validate().is_err() {
        sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,$2,'canonical validation failed; raw content suppressed') ON CONFLICT DO NOTHING")
            .bind(physical_key).bind(source).execute(&mut **tx).await?;
        return Ok(());
    }
    let key = hash(
        format!(
            "{}:{}:{}",
            event.source, event.source_instance, event.event_id
        )
        .as_bytes(),
    );
    if state.ingestion.collect_all {
        let receipt = sqlx::query(
            "INSERT INTO source_event_receipts(event_key) VALUES($1) ON CONFLICT DO NOTHING",
        )
        .bind(&key)
        .execute(&mut **tx)
        .await?
        .rows_affected();
        if receipt == 0 {
            return Ok(());
        }
        sqlx::query("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,client_ip,dest_ip,event_type,http_method,uri_path,status_code,canonical) VALUES($1,$2,$3,$4,$5,$6,$7,$8::inet,$9::inet,$10,$11,$12,$13,$14) ON CONFLICT DO NOTHING")
            .bind(&key).bind(&event.schema_version).bind(&event.source).bind(&event.source_instance).bind(&event.event_id).bind(event.timestamp).bind(&event.request_id).bind(event.client_ip.map(|v|v.to_string())).bind(event.dest_ip.map(|v|v.to_string())).bind(&event.event_type).bind(&event.http_method).bind(&event.uri_path).bind(event.status_code.map(i32::from)).bind(serde_json::to_value(&event)?).execute(&mut **tx).await?;
    }
    if let Some(native) = &parsed.native_alert {
        save_alert(
            tx,
            state,
            event,
            AlertSpec {
                key: &format!("{key}:SURICATA"),
                name: &format!("SURICATA: {}", native.signature),
                category: native.category.as_deref(),
                severity: native.severity,
                auto: state.policy.evaluate_suricata(native.sid)
                    == EventPolicyDecision::EligibleForAutoBlock,
            },
        )
        .await?;
    }
    for rule in &parsed.detections {
        let auto = source == "NGINX"
            && rule.rule_id == "SQLI"
            && state.policy.evaluate_nginx() == EventPolicyDecision::EligibleForAutoBlock;
        save_alert(
            tx,
            state,
            event,
            AlertSpec {
                key: &format!("{key}:{}", rule.rule_id),
                name: &format!("{source}: {}", rule.name),
                category: Some(rule.category),
                severity: rule.severity,
                auto,
            },
        )
        .await?;
    }
    if auth_failure(tx, state, event, &key).await? {
        save_alert(
            tx,
            state,
            event,
            AlertSpec {
                key: &format!("{key}:AUTH_BRUTE_FORCE"),
                name: &format!("{source}: Repeated Authentication Failures"),
                category: Some("Authentication Abuse"),
                severity: 2,
                auto: false,
            },
        )
        .await?;
    }
    Ok(())
}

pub async fn process_file(state: &AppState, source: &str, path: &FsPath) -> Result<()> {
    let mut file = fs::File::open(path).await?;
    let metadata = file.metadata().await?;
    let key = format!("{source}:{}:{}", metadata.dev(), metadata.ino());
    let mut tx = state.pool.begin().await?;
    sqlx::query("INSERT INTO log_cursors(file_key,path) VALUES($1,$2) ON CONFLICT DO NOTHING")
        .bind(&key)
        .bind(path.to_string_lossy().as_ref())
        .execute(&mut *tx)
        .await?;
    let (mut offset,mut generation,anchor,mut discarding):(i64,i64,String,bool)=sqlx::query_as("SELECT byte_offset,generation,anchor,discarding_oversized FROM log_cursors WHERE file_key=$1 FOR UPDATE").bind(&key).fetch_one(&mut *tx).await?;
    let current_anchor = read_anchor(&mut file, offset).await.ok();
    if metadata.len() < offset as u64
        || (offset > 0 && current_anchor.as_deref() != Some(anchor.as_str()))
    {
        offset = 0;
        generation += 1;
        discarding = false;
    }
    file.seek(SeekFrom::Start(offset as u64)).await?;
    let mut bytes = Vec::new();
    (&mut file)
        .take(SCAN_BYTES as u64)
        .read_to_end(&mut bytes)
        .await?;
    let mut start = 0;
    while start < bytes.len() {
        let tail = &bytes[start..];
        let newline = tail.iter().position(|b| *b == b'\n');
        let length = newline.map(|p| p + 1).unwrap_or(tail.len());
        if discarding
            || length > state.ingestion.max_line_bytes
            || (newline.is_none() && length >= state.ingestion.max_line_bytes)
        {
            quarantine(
                &mut tx,
                source,
                &key,
                generation,
                offset + start as i64,
                &tail[..length],
            )
            .await?;
            discarding = newline.is_none();
            start += length;
        } else if newline.is_some() {
            let raw = &tail[..length];
            let event_key = hash(
                format!("{key}:{generation}:{}:{}", offset + start as i64, hash(raw)).as_bytes(),
            );
            ingest_line(&mut tx, state, source, &event_key, raw).await?;
            start += length;
        } else {
            break;
        }
    }
    offset += start as i64;
    let anchor = read_anchor(&mut file, offset).await?;
    sqlx::query("UPDATE log_cursors SET byte_offset=$2,generation=$3,anchor=$4,path=$5,updated_at=now(),discarding_oversized=$6 WHERE file_key=$1")
        .bind(key).bind(offset).bind(generation).bind(anchor).bind(path.to_string_lossy().as_ref()).bind(discarding).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}

pub async fn prune(state: &AppState) -> Result<()> {
    sqlx::query(
        "UPDATE blocked_ips SET active=false,unblocked_at=now() WHERE active AND expires_at<=now()",
    )
    .execute(&state.pool)
    .await?;
    let cutoff = Utc::now() - chrono::Duration::days(state.ingestion.retention_days);
    sqlx::query("DELETE FROM normalized_events WHERE occurred_at<$1")
        .bind(cutoff)
        .execute(&state.pool)
        .await?;
    sqlx::query("DELETE FROM normalized_events WHERE id IN (SELECT id FROM normalized_events ORDER BY id DESC OFFSET $1)").bind(state.ingestion.max_events).execute(&state.pool).await?;
    // Origin receipts outlive dataset rows within the retention window.
    sqlx::query("DELETE FROM source_event_receipts WHERE created_at<$1")
        .bind(cutoff)
        .execute(&state.pool)
        .await?;
    sqlx::query("DELETE FROM auth_observations WHERE occurred_at<now()-interval '1 day'")
        .execute(&state.pool)
        .await?;
    sqlx::query("DELETE FROM auth_detection_state WHERE last_alert_at<now()-interval '1 day'")
        .execute(&state.pool)
        .await?;
    Ok(())
}

pub async fn retention_worker(state: AppState) {
    loop {
        if let Err(error) = prune(&state).await {
            warn!(%error,"Dataset retention failed");
        }
        tokio::time::sleep(std::time::Duration::from_secs(60)).await;
    }
}
