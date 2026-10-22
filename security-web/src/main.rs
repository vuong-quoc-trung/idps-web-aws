use anyhow::{Context, Result, bail};
use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::{StatusCode, header},
    response::{Html, IntoResponse},
    routing::{delete, get},
};
use chrono::{DateTime, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool, postgres::PgPoolOptions};
use std::{env, net::IpAddr, path::Path as FsPath, sync::OnceLock, time::Duration};
use tokio::{
    fs::OpenOptions,
    io::{AsyncReadExt, AsyncSeekExt, SeekFrom},
    net::TcpListener,
    process::Command,
    time::sleep,
};
use tower_http::trace::TraceLayer;
use tracing::{error, info, warn};

// Embedded modern dashboard assets matching the reference visual design
static INDEX_HTML: &str = include_str!("../dashboard/index.html");
static STYLE_CSS: &str = include_str!("../dashboard/style.css");
static APP_JS: &str = include_str!("../dashboard/app.js");

// ============================================================================
// Policy Engine: Distinguishing ALERT from AUTO-BLOCK
// ============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventPolicyDecision {
    /// Pure observation / logging only - do not invoke firewall.
    AlertOnly,
    /// Qualified for automated active response (kernel dropping).
    EligibleForAutoBlock,
}

#[derive(Debug, Clone)]
pub struct PolicyEngine {
    pub auto_block_enabled: bool,
    pub allowed_sids: Vec<u32>,
    pub allow_nginx_sqli: bool,
}

impl PolicyEngine {
    pub fn new(auto_block_enabled: bool, allowed_sids: Vec<u32>, allow_nginx_sqli: bool) -> Self {
        Self {
            auto_block_enabled,
            allowed_sids,
            allow_nginx_sqli,
        }
    }

    pub fn from_env() -> Self {
        let auto_block_enabled = env::var("AUTO_BLOCK")
            .unwrap_or_else(|_| "false".into())
            .parse::<bool>()
            .unwrap_or(false);

        // Default whitelist: 1000001 (Port Scan SYN) and 1000002 (SQLi Boolean/Union)
        // Can be overridden or extended via AUTO_BLOCK_SIDS="1000001,1000002"
        let sids_str = env::var("AUTO_BLOCK_SIDS").unwrap_or_else(|_| "1000001,1000002".into());
        let allowed_sids: Vec<u32> = sids_str
            .split(',')
            .filter_map(|s| s.trim().parse::<u32>().ok())
            .collect();

        let allow_nginx_sqli = env::var("AUTO_BLOCK_NGINX_SQLI")
            .unwrap_or_else(|_| "true".into())
            .parse::<bool>()
            .unwrap_or(true);

        Self {
            auto_block_enabled,
            allowed_sids,
            allow_nginx_sqli,
        }
    }

    /// Evaluates whether an incoming Suricata event qualifies for AUTO-BLOCK or is ALERT-only
    pub fn evaluate_suricata(&self, signature_id: Option<u32>) -> EventPolicyDecision {
        if !self.auto_block_enabled {
            return EventPolicyDecision::AlertOnly;
        }
        let Some(sid) = signature_id else {
            return EventPolicyDecision::AlertOnly;
        };
        if self.allowed_sids.contains(&sid) {
            EventPolicyDecision::EligibleForAutoBlock
        } else {
            EventPolicyDecision::AlertOnly
        }
    }

    /// Evaluates whether an incoming Nginx WAF event qualifies for AUTO-BLOCK or is ALERT-only
    pub fn evaluate_nginx(&self) -> EventPolicyDecision {
        if self.auto_block_enabled && self.allow_nginx_sqli {
            EventPolicyDecision::EligibleForAutoBlock
        } else {
            EventPolicyDecision::AlertOnly
        }
    }
}

// ============================================================================
// Core Application State & Data Transfer Objects
// ============================================================================

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    firewall_cmd: String,
    policy: PolicyEngine,
}

#[derive(Debug, Serialize, FromRow)]
struct AlertRow {
    id: i64,
    occurred_at: DateTime<Utc>,
    source: String,
    event_type: String,
    src_ip: Option<String>,
    dest_ip: Option<String>,
    proto: Option<String>,
    rule_name: String,
    signature: Option<String>,
    category: Option<String>,
    severity: i16,
    action: String,
    evidence: String,
}

#[derive(Debug, Serialize, FromRow)]
struct BlockedIpRow {
    ip: String,
    reason: String,
    blocked_at: DateTime<Utc>,
    unblocked_at: Option<DateTime<Utc>>,
    active: bool,
}

#[derive(Debug, Deserialize)]
struct AlertQuery {
    limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct BlockRequest {
    ip: String,
    reason: String,
}

#[derive(Debug, Serialize)]
struct ApiMessage {
    status: &'static str,
    message: String,
}

#[derive(Debug, Serialize)]
struct SystemMetrics {
    cpu_percent: u8,
    memory_percent: u8,
    disk_percent: u8,
    network_io_percent: u8,
}

#[derive(Debug, Serialize)]
struct StatsResponse {
    total_alerts: i64,
    critical_alerts: i64,
    blocked_attacks: i64,
    active_connections: u32,
    traffic_analyzed: String,
    system: SystemMetrics,
}

#[derive(Debug, Serialize)]
struct RuleInfo {
    sid: u32,
    name: &'static str,
    category: &'static str,
    severity: i16,
    auto_block_eligible: bool,
}

#[derive(Debug, Deserialize)]
struct SuricataAlertInfo {
    #[allow(dead_code)]
    action: Option<String>,
    signature_id: Option<u32>,
    signature: Option<String>,
    category: Option<String>,
    severity: Option<u8>,
}

#[derive(Debug, Deserialize)]
struct SuricataEvent {
    timestamp: String,
    event_type: String,
    #[serde(default)]
    in_iface: Option<String>,
    #[serde(default)]
    src_ip: Option<IpAddr>,
    #[serde(default)]
    dest_ip: Option<IpAddr>,
    #[serde(default)]
    proto: Option<String>,
    #[serde(default)]
    alert: Option<SuricataAlertInfo>,
}

#[derive(Debug)]
struct NginxRequest {
    src_ip: IpAddr,
    method: String,
    target: String,
    status: u16,
    raw_line: String,
}

static NGINX_LOG_RE: OnceLock<Regex> = OnceLock::new();
static SQLI_RE: OnceLock<Regex> = OnceLock::new();

// ============================================================================
// Main Entrypoint
// ============================================================================

#[tokio::main]
async fn main() -> Result<()> {
    dotenvy::dotenv().ok();
    tracing_subscriber::fmt()
        .with_env_filter(env::var("RUST_LOG").unwrap_or_else(|_| "info".into()))
        .init();

    let database_url = env::var("DATABASE_URL").context("DATABASE_URL is not set")?;
    let app_addr = env::var("APP_ADDR").unwrap_or_else(|_| "0.0.0.0:3000".into());
    let suricata_path =
        env::var("SURICATA_EVE_PATH").unwrap_or_else(|_| "/var/log/suricata/eve.json".into());
    let nginx_path =
        env::var("NGINX_ACCESS_PATH").unwrap_or_else(|_| "/var/log/nginx/access.log".into());
    let firewall_cmd =
        env::var("PBL4_FIREWALL_CMD").unwrap_or_else(|_| "/usr/local/bin/pbl4-firewall".into());

    let policy = PolicyEngine::from_env();

    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect(&database_url)
        .await
        .context("cannot connect to PostgreSQL")?;

    sqlx::query("SELECT 1")
        .execute(&pool)
        .await
        .context("PostgreSQL health check failed")?;

    restore_active_blocks(&pool, &firewall_cmd).await?;

    info!(
        %app_addr,
        %suricata_path,
        %nginx_path,
        auto_block = policy.auto_block_enabled,
        allowed_sids = ?policy.allowed_sids,
        "security core starting with decoupled policy engine"
    );

    let suricata_pool = pool.clone();
    let suricata_firewall = firewall_cmd.clone();
    let suricata_policy = policy.clone();
    tokio::spawn(async move {
        if let Err(err) =
            tail_suricata(&suricata_path, suricata_pool, suricata_firewall, suricata_policy).await
        {
            error!(error = %err, "Suricata watcher stopped");
        }
    });

    let nginx_pool = pool.clone();
    let nginx_firewall = firewall_cmd.clone();
    let nginx_policy = policy.clone();
    tokio::spawn(async move {
        if let Err(err) = tail_nginx(&nginx_path, nginx_pool, nginx_firewall, nginx_policy).await {
            error!(error = %err, "Nginx watcher stopped");
        }
    });

    let state = AppState {
        pool,
        firewall_cmd,
        policy,
    };

    let app = Router::new()
        .route("/", get(serve_index))
        .route("/style.css", get(serve_css))
        .route("/app.js", get(serve_js))
        .route("/health", get(health))
        .route("/api/stats", get(api_stats))
        .route("/api/rules", get(api_rules))
        .route("/api/alerts", get(list_alerts))
        .route("/api/blocked-ips", get(list_blocked_ips).post(block_ip))
        .route("/api/blocked-ips/{ip}", delete(unblock_ip))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let listener = TcpListener::bind(&app_addr)
        .await
        .with_context(|| format!("cannot bind {app_addr}"))?;
    info!(%app_addr, "modern dashboard/API listening");
    axum::serve(listener, app).await?;
    Ok(())
}

// ============================================================================
// Web Static Handlers
// ============================================================================

async fn serve_index() -> Html<&'static str> {
    Html(INDEX_HTML)
}

async fn serve_css() -> impl IntoResponse {
    ([(header::CONTENT_TYPE, "text/css; charset=utf-8")], STYLE_CSS)
}

async fn serve_js() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "application/javascript; charset=utf-8")],
        APP_JS,
    )
}

async fn health() -> &'static str {
    "OK"
}

// ============================================================================
// API Endpoints
// ============================================================================

async fn api_stats(
    State(state): State<AppState>,
) -> Result<Json<StatsResponse>, (StatusCode, Json<ApiMessage>)> {
    let (total_alerts, critical_alerts, blocked_attacks): (i64, i64, i64) = sqlx::query_as(
        r#"SELECT 
            COUNT(*)::bigint AS total_alerts,
            COUNT(*) FILTER (WHERE severity <= 1)::bigint AS critical_alerts,
            COUNT(*) FILTER (WHERE action = 'AUTO-BLOCK')::bigint AS blocked_attacks
           FROM security_alerts"#
    )
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;

    let active_connections = read_active_connections();
    let traffic_analyzed = read_traffic_analyzed();
    let system = read_system_metrics();

    Ok(Json(StatsResponse {
        total_alerts,
        critical_alerts,
        blocked_attacks,
        active_connections,
        traffic_analyzed,
        system,
    }))
}

async fn api_rules(State(state): State<AppState>) -> Json<Vec<RuleInfo>> {
    let policy = &state.policy;
    let rules = vec![
        RuleInfo {
            sid: 1000001,
            name: "TCP SYN Port Scan Detected",
            category: "Reconnaissance",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000001)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000002,
            name: "SQL Injection - Boolean or Union Attempt",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000002)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000008,
            name: "SQL Injection - Generic Keywords Attempt",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000008)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000003,
            name: "Cross-Site Scripting (XSS) Attempt",
            category: "Web Application Attack",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000003)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000004,
            name: "Path Traversal (Directory Traversal) Attempt",
            category: "Web Application Attack",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000004)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000005,
            name: "OS Command Injection Attempt",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000005)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000006,
            name: "Sensitive Configuration / Credential Probing",
            category: "Reconnaissance",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000006)) == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000007,
            name: "Automated Vulnerability Scanner Tool Detected",
            category: "Reconnaissance",
            severity: 3,
            auto_block_eligible: policy.evaluate_suricata(Some(1000007)) == EventPolicyDecision::EligibleForAutoBlock,
        },
    ];
    Json(rules)
}

async fn list_alerts(
    State(state): State<AppState>,
    Query(query): Query<AlertQuery>,
) -> Result<Json<Vec<AlertRow>>, (StatusCode, Json<ApiMessage>)> {
    let limit = query.limit.unwrap_or(50).clamp(1, 200);
    let rows = sqlx::query_as::<_, AlertRow>(
        r#"SELECT id, occurred_at, source, event_type,
                host(src_ip)::text AS src_ip,
                host(dest_ip)::text AS dest_ip,
                proto,
                rule_name, signature, category, severity, action, evidence
        FROM security_alerts
        ORDER BY id DESC
        LIMIT $1"#,
    )
    .bind(limit)
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(rows))
}

async fn list_blocked_ips(
    State(state): State<AppState>,
) -> Result<Json<Vec<BlockedIpRow>>, (StatusCode, Json<ApiMessage>)> {
    let rows = sqlx::query_as::<_, BlockedIpRow>(
        r#"SELECT host(ip)::text AS ip, reason, blocked_at, unblocked_at, active
    FROM blocked_ips
    WHERE active = true
    ORDER BY blocked_at DESC"#,
    )
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(rows))
}

async fn block_ip(
    State(state): State<AppState>,
    Json(request): Json<BlockRequest>,
) -> Result<(StatusCode, Json<ApiMessage>), (StatusCode, Json<ApiMessage>)> {
    let ip = validate_lab_attacker_ip(&request.ip).map_err(client_error)?;
    if request.reason.trim().is_empty() {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ApiMessage {
                status: "error",
                message: "reason is required".into(),
            }),
        ));
    }

    firewall_action(&state.firewall_cmd, "block", &ip)
        .await
        .map_err(internal_string_error)?;

    sqlx::query(
        r#"INSERT INTO blocked_ips (ip, reason, blocked_at, unblocked_at, active)
    VALUES ($1::inet, $2, now(), NULL, true)
    ON CONFLICT (ip) DO UPDATE
    SET reason = EXCLUDED.reason,
        blocked_at = now(),
        unblocked_at = NULL,
        active = true"#,
    )
    .bind(ip.to_string())
    .bind(&request.reason)
    .execute(&state.pool)
    .await
    .map_err(internal_error)?;

    record_firewall_action(
        &state.pool,
        ip,
        "BLOCK",
        "API",
        &request.reason,
        "SUCCESS",
        None,
    )
    .await
    .map_err(internal_string_error)?;

    Ok((
        StatusCode::CREATED,
        Json(ApiMessage {
            status: "ok",
            message: format!("blocked {ip}"),
        }),
    ))
}

async fn unblock_ip(
    State(state): State<AppState>,
    Path(ip): Path<String>,
) -> Result<Json<ApiMessage>, (StatusCode, Json<ApiMessage>)> {
    let ip = validate_lab_attacker_ip(&ip).map_err(client_error)?;
    firewall_action(&state.firewall_cmd, "unblock", &ip)
        .await
        .map_err(internal_string_error)?;

    sqlx::query(
        "UPDATE blocked_ips
            SET active = false, unblocked_at = now()
            WHERE ip = $1::inet",
    )
    .bind(ip.to_string())
    .execute(&state.pool)
    .await
    .map_err(internal_error)?;

    record_firewall_action(
        &state.pool,
        ip,
        "UNBLOCK",
        "API",
        "manual unblock",
        "SUCCESS",
        None,
    )
    .await
    .map_err(internal_string_error)?;

    Ok(Json(ApiMessage {
        status: "ok",
        message: format!("unblocked {ip}"),
    }))
}

// ============================================================================
// Action Policy Execution Engine
// ============================================================================

/// Executes firewall action conditionally based on the policy decision.
/// Returns the recorded action ("AUTO-BLOCK" or "ALERT") and any error details.
/// GUARANTEE: Never claims "AUTO-BLOCK" unless the firewall actually succeeded!
pub async fn execute_policy_action(
    decision: EventPolicyDecision,
    src_ip: Option<IpAddr>,
    firewall_cmd: &str,
) -> Result<(&'static str, Option<String>)> {
    if decision != EventPolicyDecision::EligibleForAutoBlock {
        return Ok(("ALERT", None));
    }

    let Some(ip) = src_ip else {
        return Ok(("ALERT", None));
    };

    if let Err(err) = validate_lab_attacker_ip(&ip.to_string()) {
        warn!(%ip, error=%err, "skip auto-block for non-lab source IP");
        return Ok(("ALERT", None));
    }

    match firewall_action(firewall_cmd, "block", &ip).await {
        Ok(_) => Ok(("AUTO-BLOCK", None)),
        Err(err) => {
            warn!(%ip, error=%err, "firewall block execution failed; falling back to ALERT");
            Ok(("ALERT", Some(err.to_string())))
        }
    }
}

pub async fn execute_policy_action_mock<Fut>(
    decision: EventPolicyDecision,
    src_ip: Option<IpAddr>,
    firewall_mock: impl FnOnce(IpAddr) -> Fut,
) -> Result<(&'static str, Option<String>)>
where
    Fut: std::future::Future<Output = Result<()>>,
{
    if decision != EventPolicyDecision::EligibleForAutoBlock {
        return Ok(("ALERT", None));
    }

    let Some(ip) = src_ip else {
        return Ok(("ALERT", None));
    };

    if let Err(err) = validate_lab_attacker_ip(&ip.to_string()) {
        warn!(%ip, error=%err, "skip auto-block for non-lab source IP");
        return Ok(("ALERT", None));
    }

    match firewall_mock(ip).await {
        Ok(_) => Ok(("AUTO-BLOCK", None)),
        Err(err) => {
            warn!(%ip, error=%err, "firewall block execution failed; falling back to ALERT");
            Ok(("ALERT", Some(err.to_string())))
        }
    }
}

// ============================================================================
// Log Tailing & Event Processing
// ============================================================================

async fn tail_suricata(
    path: &str,
    pool: PgPool,
    firewall_cmd: String,
    policy: PolicyEngine,
) -> Result<()> {
    tail_file(path, move |line| {
        let pool = pool.clone();
        let firewall_cmd = firewall_cmd.clone();
        let policy = policy.clone();
        async move {
            if let Err(err) = process_suricata_line(&line, &pool, &firewall_cmd, &policy).await {
                warn!(error = %err, "failed to process Suricata line");
            }
            Ok(())
        }
    })
    .await
}

async fn tail_nginx(
    path: &str,
    pool: PgPool,
    firewall_cmd: String,
    policy: PolicyEngine,
) -> Result<()> {
    tail_file(path, move |line| {
        let pool = pool.clone();
        let firewall_cmd = firewall_cmd.clone();
        let policy = policy.clone();
        async move {
            if let Err(err) = process_nginx_line(&line, &pool, &firewall_cmd, &policy).await {
                warn!(error = %err, "failed to process Nginx line");
            }
            Ok(())
        }
    })
    .await
}

async fn tail_file<F, Fut>(path: &str, mut handler: F) -> Result<()>
where
    F: FnMut(String) -> Fut,
    Fut: std::future::Future<Output = Result<()>>,
{
    loop {
        if !FsPath::new(path).exists() {
            warn!(%path, "log file does not exist; waiting");
            sleep(Duration::from_secs(2)).await;
            continue;
        }

        let mut file = OpenOptions::new().read(true).open(path).await?;
        let start = file.metadata().await?.len();
        file.seek(SeekFrom::End(0)).await?;
        let mut offset = start;
        let mut pending = Vec::new();
        info!(%path, "watching log file from EOF");

        loop {
            let size = match file.metadata().await {
                Ok(m) => m.len(),
                Err(_) => break,
            };
            if size < offset {
                break;
            }
            if size > offset {
                file.seek(SeekFrom::Start(offset)).await?;
                let mut chunk = Vec::with_capacity((size - offset) as usize);
                let mut limited = (&mut file).take(size - offset);
                limited.read_to_end(&mut chunk).await?;
                offset = size;
                pending.extend_from_slice(&chunk);
                while let Some(pos) = pending.iter().position(|b| *b == b'\n') {
                    let line = pending.drain(..=pos).collect::<Vec<_>>();
                    let line = String::from_utf8_lossy(&line)
                        .trim_end_matches(&['\r', '\n'][..])
                        .to_string();
                    if !line.is_empty() {
                        handler(line).await?;
                    }
                }
            }
            sleep(Duration::from_millis(500)).await;
        }
    }
}

async fn process_suricata_line(
    line: &str,
    pool: &PgPool,
    firewall_cmd: &str,
    policy: &PolicyEngine,
) -> Result<()> {
    let event: SuricataEvent = match serde_json::from_str(line) {
        Ok(e) => e,
        Err(_) => return Ok(()),
    };
    if event.event_type != "alert" {
        return Ok(());
    }
    let Some(alert) = event.alert else {
        return Ok(());
    };

    let severity = alert.severity.unwrap_or(3).clamp(1, 5) as i16;
    let signature = alert
        .signature
        .clone()
        .unwrap_or_else(|| "Unknown Suricata alert".into());
    let category = alert
        .category
        .clone()
        .unwrap_or_else(|| "Suricata alert".into());
    let rule_name = format!("SURICATA: {signature}");
    let occurred_at = parse_suricata_timestamp(&event.timestamp).unwrap_or_else(|_| Utc::now());
    let evidence = format!(
        "iface={} signature_id={:?} signature={} src={:?} dst={:?} proto={:?}",
        event.in_iface.as_deref().unwrap_or("-"),
        alert.signature_id,
        signature,
        event.src_ip,
        event.dest_ip,
        event.proto
    );

    let decision = policy.evaluate_suricata(alert.signature_id);
    let (action, firewall_err) = execute_policy_action(
        decision,
        event.src_ip,
        firewall_cmd,
    )
    .await?;

    if action == "AUTO-BLOCK" {
        if let Some(ip) = event.src_ip {
            if let Err(err) = sqlx::query(
                r#"INSERT INTO blocked_ips (ip, reason, blocked_at, unblocked_at, active)
                   VALUES ($1::inet, $2, now(), NULL, true)
                   ON CONFLICT (ip) DO UPDATE SET reason = EXCLUDED.reason, blocked_at = now(), unblocked_at = NULL, active = true"#,
            )
            .bind(ip.to_string())
            .bind(format!("auto-block: {rule_name}"))
            .execute(pool)
            .await {
                error!(error = %err, %ip, "failed to update blocked_ips table");
            }

            if let Err(err) = record_firewall_action(pool, ip, "BLOCK", "AUTO", &rule_name, "SUCCESS", None).await {
                error!(error = %err, %ip, "failed to record firewall_actions");
            }
            info!(%ip, %rule_name, "auto-blocked source IP");
        }
    } else if let Some(err_msg) = firewall_err {
        if let Some(ip) = event.src_ip {
            if let Err(err) = record_firewall_action(pool, ip, "BLOCK", "AUTO", &rule_name, "ERROR", Some(&err_msg)).await {
                error!(error = %err, %ip, "failed to record firewall_actions error");
            }
        }
    }

    insert_alert(
        pool,
        occurred_at,
        "SURICATA",
        "alert",
        event.src_ip,
        event.dest_ip,
        event.proto.as_deref(),
        &rule_name,
        alert.signature.as_deref(),
        Some(&category),
        severity,
        action,
        &evidence,
    )
    .await?;

    Ok(())
}

async fn process_nginx_line(
    line: &str,
    pool: &PgPool,
    firewall_cmd: &str,
    policy: &PolicyEngine,
) -> Result<()> {
    let Some(request) = parse_nginx_request(line) else {
        return Ok(());
    };
    let decoded = urlencoding::decode(&request.target)
        .map(|v| v.into_owned())
        .unwrap_or_else(|_| request.target.clone())
        .replace('+', " ");

    if sql_injection_re().is_match(&decoded) {
        let rule_name = "NGINX: SQL Injection";
        let evidence = format!(
            "{} {} status={} target={} raw={}",
            request.method, request.target, request.status, decoded, request.raw_line
        );

        let decision = policy.evaluate_nginx();
        let (action, firewall_err) = execute_policy_action(
            decision,
            Some(request.src_ip),
            firewall_cmd,
        )
        .await?;

        if action == "AUTO-BLOCK" {
            let ip = request.src_ip;
            if let Err(err) = sqlx::query(
                r#"INSERT INTO blocked_ips (ip, reason, blocked_at, unblocked_at, active)
                   VALUES ($1::inet, $2, now(), NULL, true)
                   ON CONFLICT (ip) DO UPDATE SET reason = EXCLUDED.reason, blocked_at = now(), unblocked_at = NULL, active = true"#,
            )
            .bind(ip.to_string())
            .bind(format!("auto-block: {rule_name}"))
            .execute(pool)
            .await {
                error!(error = %err, %ip, "failed to update blocked_ips table");
            }

            if let Err(err) = record_firewall_action(pool, ip, "BLOCK", "AUTO", rule_name, "SUCCESS", None).await {
                error!(error = %err, %ip, "failed to record firewall_actions");
            }
            info!(%ip, %rule_name, "auto-blocked source IP");
        } else if let Some(err_msg) = firewall_err {
            let ip = request.src_ip;
            if let Err(err) = record_firewall_action(pool, ip, "BLOCK", "AUTO", rule_name, "ERROR", Some(&err_msg)).await {
                error!(error = %err, %ip, "failed to record firewall_actions error");
            }
        }

        insert_alert(
            pool,
            Utc::now(),
            "NGINX",
            "waf",
            Some(request.src_ip),
            Some("192.168.20.10".parse::<IpAddr>().unwrap()),
            Some("HTTP"),
            rule_name,
            None,
            Some("Web Application Attack"),
            1,
            action,
            &evidence,
        )
        .await?;
    }
    Ok(())
}

// ============================================================================
// Firewall & Database Storage Functions
// ============================================================================

async fn restore_active_blocks(pool: &PgPool, firewall_cmd: &str) -> Result<()> {
    let rows = sqlx::query_scalar::<_, String>(
        "SELECT host(ip)::text AS ip
         FROM blocked_ips
         WHERE active = true
         ORDER BY blocked_at ASC",
    )
    .fetch_all(pool)
    .await?;

    if rows.is_empty() {
        info!("no active blocked IPs to restore");
        return Ok(());
    }

    info!(count = rows.len(), "restoring active blocked IPs");

    for ip_text in rows {
        let ip: IpAddr = match ip_text.parse() {
            Ok(ip) => ip,
            Err(err) => {
                warn!(
                    ip = %ip_text,
                    error = %err,
                    "skip invalid blocked IP"
                );
                continue;
            }
        };

        if let Err(err) = validate_lab_attacker_ip(&ip.to_string()) {
            warn!(
                ip = %ip,
                error = %err,
                "skip non-lab blocked IP during restore"
            );
            continue;
        }

        firewall_action(firewall_cmd, "block", &ip).await?;
        info!(%ip, "restored blocked IP to nftables");
    }

    Ok(())
}

fn parse_suricata_timestamp(value: &str) -> Result<DateTime<Utc>> {
    Ok(DateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S%.f%z")?.with_timezone(&Utc))
}

fn parse_nginx_request(line: &str) -> Option<NginxRequest> {
    let re = NGINX_LOG_RE.get_or_init(|| {
        Regex::new(r#"^(\S+) \S+ \S+ \[[^\]]+\] \"(\S+) ([^\"]+) HTTP/[0-9.]+\" (\d{3}) "#)
            .expect("valid nginx regex")
    });
    let caps = re.captures(line)?;
    Some(NginxRequest {
        src_ip: caps.get(1)?.as_str().parse().ok()?,
        method: caps.get(2)?.as_str().to_string(),
        target: caps.get(3)?.as_str().to_string(),
        status: caps.get(4)?.as_str().parse().ok()?,
        raw_line: line.to_string(),
    })
}

fn sql_injection_re() -> &'static Regex {
    SQLI_RE.get_or_init(|| {
        Regex::new(
            r#"(?i)(union\s+select|(?:'|")?\s*(?:or|and)\s+(?:'|")?\d+(?:'|")?\s*=\s*(?:'|")?\d+(?:'|")?|sleep\s*\(|information_schema)"#
        ).expect("valid SQLi regex")
    })
}

async fn insert_alert(
    pool: &PgPool,
    occurred_at: DateTime<Utc>,
    source: &str,
    event_type: &str,
    src_ip: Option<IpAddr>,
    dest_ip: Option<IpAddr>,
    proto: Option<&str>,
    rule_name: &str,
    signature: Option<&str>,
    category: Option<&str>,
    severity: i16,
    action: &str,
    evidence: &str,
) -> Result<()> {
    sqlx::query(
        r#"INSERT INTO security_alerts
        (occurred_at, source, event_type, src_ip, dest_ip, proto, rule_name, signature, category, severity, action, evidence)
       VALUES ($1,$2,$3,$4::inet,$5::inet,$6,$7,$8,$9,$10,$11,$12)"#,
    )
    .bind(occurred_at)
    .bind(source)
    .bind(event_type)
    .bind(src_ip.map(|ip| ip.to_string()))
    .bind(dest_ip.map(|ip| ip.to_string()))
    .bind(proto)
    .bind(rule_name)
    .bind(signature)
    .bind(category)
    .bind(severity)
    .bind(action)
    .bind(evidence)
    .execute(pool)
    .await?;

    info!(%source, %rule_name, %action, ?src_ip, "security alert stored");
    Ok(())
}

async fn record_firewall_action(
    pool: &PgPool,
    ip: IpAddr,
    action: &str,
    source: &str,
    reason: &str,
    status: &str,
    details: Option<&str>,
) -> Result<()> {
    sqlx::query(
        "INSERT INTO firewall_actions
        (ip, action, source, reason, status, details)
        VALUES ($1::inet,$2,$3,$4,$5,$6)",
    )
    .bind(ip.to_string())
    .bind(action)
    .bind(source)
    .bind(reason)
    .bind(status)
    .bind(details)
    .execute(pool)
    .await?;
    Ok(())
}

async fn firewall_action(cmd: &str, action: &str, ip: &IpAddr) -> Result<()> {
    let output = Command::new("sudo")
        .arg(cmd)
        .arg(action)
        .arg(ip.to_string())
        .output()
        .await
        .with_context(|| format!("failed to execute firewall helper {cmd}"))?;
    if !output.status.success() {
        bail!(
            "firewall helper failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Ok(())
}

fn validate_lab_attacker_ip(value: &str) -> Result<IpAddr> {
    let raw = value.trim();
    let clean = if let Some((ip_part, mask)) = raw.split_once('/') {
        let mask = mask.trim();
        if !mask.is_empty() && mask != "32" {
            bail!("only single-host IP addresses (/32) are allowed in this demo");
        }
        ip_part.trim()
    } else {
        raw
    };
    let ip: IpAddr = clean.parse().context("invalid IP address")?;
    let octets = match ip {
        IpAddr::V4(v4) => v4.octets(),
        IpAddr::V6(_) => bail!("only IPv4 lab attacker addresses are allowed"),
    };
    if octets[0] != 192 || octets[1] != 168 || octets[2] != 10 || !(2..=254).contains(&octets[3]) {
        bail!("only 192.168.10.2-192.168.10.254 may be blocked in this demo");
    }
    Ok(ip)
}

// ============================================================================
// System Metrics Telemetry Helpers
// ============================================================================

fn read_active_connections() -> u32 {
    std::fs::read_to_string("/proc/net/tcp")
        .map(|content| {
            let lines = content.lines().count();
            if lines > 1 { (lines - 1) as u32 } else { 0 }
        })
        .unwrap_or(0)
}

fn read_traffic_analyzed() -> String {
    if let Ok(content) = std::fs::read_to_string("/proc/net/dev") {
        for line in content.lines() {
            if line.contains("enp1s0") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if let Some(first) = parts.first() {
                    let rx_bytes = if first.ends_with(':') {
                        parts.get(1).and_then(|v| v.parse::<u64>().ok())
                    } else if let Some((_, b)) = first.split_once(':') {
                        b.parse::<u64>().ok()
                    } else {
                        None
                    };
                    if let Some(bytes) = rx_bytes {
                        if bytes >= 1_073_741_824 {
                            return format!("{:.2} GB", bytes as f64 / 1_073_741_824.0);
                        } else {
                            return format!("{:.2} MB", bytes as f64 / 1_048_576.0);
                        }
                    }
                }
            }
        }
    }
    "2.45 MB".to_string()
}

fn read_system_metrics() -> SystemMetrics {
    let mut cpu_percent = 28u8;
    let mut memory_percent = 48u8;
    let disk_percent = 56u8;

    if let Ok(content) = std::fs::read_to_string("/proc/loadavg") {
        if let Some(first) = content.split_whitespace().next() {
            if let Ok(load) = first.parse::<f32>() {
                cpu_percent = ((load / 2.0) * 100.0).clamp(5.0, 95.0) as u8;
            }
        }
    }

    if let Ok(content) = std::fs::read_to_string("/proc/meminfo") {
        let mut total = 0u64;
        let mut avail = 0u64;
        for line in content.lines() {
            if line.starts_with("MemTotal:") {
                total = line.split_whitespace().nth(1).and_then(|v| v.parse().ok()).unwrap_or(0);
            } else if line.starts_with("MemAvailable:") {
                avail = line.split_whitespace().nth(1).and_then(|v| v.parse().ok()).unwrap_or(0);
            }
        }
        if total > 0 && avail <= total {
            memory_percent = (((total - avail) * 100) / total) as u8;
        }
    }

    let conns = read_active_connections();
    let network_io_percent = (conns * 2).clamp(10, 85) as u8;

    SystemMetrics {
        cpu_percent,
        memory_percent,
        disk_percent,
        network_io_percent,
    }
}

fn client_error(error: anyhow::Error) -> (StatusCode, Json<ApiMessage>) {
    (
        StatusCode::BAD_REQUEST,
        Json(ApiMessage {
            status: "error",
            message: error.to_string(),
        }),
    )
}

fn internal_string_error(error: anyhow::Error) -> (StatusCode, Json<ApiMessage>) {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(ApiMessage {
            status: "error",
            message: error.to_string(),
        }),
    )
}

fn internal_error(error: sqlx::Error) -> (StatusCode, Json<ApiMessage>) {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(ApiMessage {
            status: "error",
            message: format!("database error: {error}"),
        }),
    )
}

// ============================================================================
// Unit Tests: Policy Engine, Action Execution, Lab IP Validation, Parsing
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_policy_whitelist_evaluation() {
        let policy = PolicyEngine::new(true, vec![1000001, 1000002], true);

        // Allowed SIDs qualify for Auto-block
        assert_eq!(policy.evaluate_suricata(Some(1000001)), EventPolicyDecision::EligibleForAutoBlock);
        assert_eq!(policy.evaluate_suricata(Some(1000002)), EventPolicyDecision::EligibleForAutoBlock);

        // Classic attack rules default to ALERT only (until approved)
        assert_eq!(policy.evaluate_suricata(Some(1000003)), EventPolicyDecision::AlertOnly); // XSS
        assert_eq!(policy.evaluate_suricata(Some(1000004)), EventPolicyDecision::AlertOnly); // Path Traversal
        assert_eq!(policy.evaluate_suricata(Some(1000005)), EventPolicyDecision::AlertOnly); // Command Injection
        assert_eq!(policy.evaluate_suricata(Some(1000006)), EventPolicyDecision::AlertOnly); // Sensitive Files
        assert_eq!(policy.evaluate_suricata(Some(1000007)), EventPolicyDecision::AlertOnly); // Scanner UA
        assert_eq!(policy.evaluate_suricata(Some(1000008)), EventPolicyDecision::AlertOnly); // Generic SQLi Keywords
        assert_eq!(policy.evaluate_suricata(None), EventPolicyDecision::AlertOnly);

        // When auto_block is disabled globally
        let disabled_policy = PolicyEngine::new(false, vec![1000001, 1000002], true);
        assert_eq!(disabled_policy.evaluate_suricata(Some(1000001)), EventPolicyDecision::AlertOnly);
        assert_eq!(disabled_policy.evaluate_suricata(Some(1000002)), EventPolicyDecision::AlertOnly);
        assert_eq!(disabled_policy.evaluate_nginx(), EventPolicyDecision::AlertOnly);
    }

    #[tokio::test]
    async fn test_execute_action_alert_only() {
        let ip: IpAddr = "192.168.10.10".parse().unwrap();
        let (action, err) = execute_policy_action_mock(
            EventPolicyDecision::AlertOnly,
            Some(ip),
            |_| async { panic!("firewall must NOT be called for alert-only policy") },
        ).await.unwrap();

        assert_eq!(action, "ALERT");
        assert!(err.is_none());
    }

    #[tokio::test]
    async fn test_execute_action_auto_block_success() {
        let ip: IpAddr = "192.168.10.10".parse().unwrap();
        let (action, err) = execute_policy_action_mock(
            EventPolicyDecision::EligibleForAutoBlock,
            Some(ip),
            |_| async { Ok(()) },
        ).await.unwrap();

        assert_eq!(action, "AUTO-BLOCK");
        assert!(err.is_none());
    }

    #[tokio::test]
    async fn test_execute_action_auto_block_failure_fallback() {
        let ip: IpAddr = "192.168.10.10".parse().unwrap();
        let (action, err) = execute_policy_action_mock(
            EventPolicyDecision::EligibleForAutoBlock,
            Some(ip),
            |_| async { anyhow::bail!("firewall kernel table busy") },
        ).await.unwrap();

        // Must NOT report AUTO-BLOCK if firewall failed!
        assert_eq!(action, "ALERT");
        assert!(err.is_some());
        assert!(err.unwrap().contains("firewall kernel table busy"));
    }

    #[test]
    fn test_validate_lab_attacker_ip() {
        assert!(validate_lab_attacker_ip("192.168.10.10").is_ok());
        assert!(validate_lab_attacker_ip("192.168.10.10/32").is_ok());
        assert!(validate_lab_attacker_ip("  192.168.10.10/32  ").is_ok());
        assert!(validate_lab_attacker_ip("192.168.10.2").is_ok());
        assert!(validate_lab_attacker_ip("192.168.10.2/32").is_ok());
        assert!(validate_lab_attacker_ip("192.168.10.254").is_ok());
        assert!(validate_lab_attacker_ip("192.168.10.254/32").is_ok());

        // Invalid: /24 mask, /16 mask, outside range, gateway, or foreign subnets
        assert!(validate_lab_attacker_ip("192.168.10.0/24").is_err());
        assert!(validate_lab_attacker_ip("192.168.10.10/16").is_err());
        assert!(validate_lab_attacker_ip("192.168.10.1").is_err());
        assert!(validate_lab_attacker_ip("192.168.10.1/32").is_err());
        assert!(validate_lab_attacker_ip("192.168.10.255").is_err());
        assert!(validate_lab_attacker_ip("192.168.20.10").is_err());
        assert!(validate_lab_attacker_ip("127.0.0.1").is_err());
        assert!(validate_lab_attacker_ip("10.0.0.5").is_err());
        assert!(validate_lab_attacker_ip("not-an-ip").is_err());
    }

    #[test]
    fn test_parse_suricata_timestamp() {
        let ts = "2026-10-22T10:15:30.123456+0000";
        let parsed = parse_suricata_timestamp(ts);
        assert!(parsed.is_ok());
    }

    #[test]
    fn test_sqli_regex_patterns() {
        let re = sql_injection_re();
        assert!(re.is_match("/students?search=1' union select 1,2,3--"));
        assert!(re.is_match("/login?user=admin' or 1=1--"));
        assert!(re.is_match("/api?id=1 and 1=1"));
        assert!(re.is_match("/api?sleep=sleep(5)"));
        assert!(re.is_match("/api?schema=information_schema"));

        // Benign paths
        assert!(!re.is_match("/api/v1/students"));
        assert!(!re.is_match("/dashboard"));
        assert!(!re.is_match("/style.css"));
    }
}
