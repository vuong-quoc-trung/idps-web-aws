mod application_audit;
mod application_detection;
mod auth;
mod detection;
mod events;
mod firewall;
mod ingest;
mod metrics;
mod network;
use anyhow::{Context, Result, bail};
use axum::{
    Extension, Json, Router,
    extract::{Path, Query, State},
    http::StatusCode,
    middleware,
    routing::{delete, get, post},
};
use chrono::{DateTime, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool, postgres::PgPoolOptions};
use std::{
    collections::BTreeMap,
    env,
    net::IpAddr,
    sync::{Arc, OnceLock},
};
use tokio::sync::RwLock;
use tower_http::{services::ServeDir, trace::TraceLayer};
use tracing::{info, warn};
#[derive(Clone)]
struct AppState {
    pool: PgPool,
    ingestion: Arc<ingest::Config>,
    sensor_id: String,
    safety: Arc<network::Safety>,
    auth: auth::Auth,
    policy: PolicyEngine,
    firewall_cmd: String,
    whitelist: Arc<Vec<IpAddr>>,
    watchers: Arc<RwLock<BTreeMap<String, ingest::WatcherStatus>>>,
}
type ApiError = (StatusCode, Json<serde_json::Value>);
fn api_error(e: impl std::fmt::Display) -> ApiError {
    tracing::error!(error=%e, "request failed");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(serde_json::json!({"message":"Operation failed; check server logs and audit status"})),
    )
}
fn bad_request(e: impl std::fmt::Display) -> ApiError {
    (
        StatusCode::BAD_REQUEST,
        Json(serde_json::json!({"message":e.to_string()})),
    )
}
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

        // Default response candidate: SQLi only; SYN burst is an observation, not proof of scan.
        // Can be overridden or extended via AUTO_BLOCK_SIDS="1000001,1000002"
        let sids_str = env::var("AUTO_BLOCK_SIDS").unwrap_or_else(|_| "1000002".into());
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
    offset: Option<i64>,
    search: Option<String>,
    severity: Option<i16>,
    from: Option<DateTime<Utc>>,
    to: Option<DateTime<Utc>>,
    source: Option<String>,
    action: Option<String>,
    dest_ip: Option<std::net::IpAddr>,
}

#[derive(Debug, Deserialize)]
struct BlockRequest {
    ip: String,
    reason: String,
    event_id: Option<i64>,
}

#[derive(Debug, Serialize)]
struct RuleInfo {
    sid: u32,
    name: &'static str,
    category: &'static str,
    severity: i16,
    auto_block_eligible: bool,
}

#[cfg(test)]
#[derive(Debug)]
struct NginxRequest {
    src_ip: IpAddr,
    target: String,
}

#[cfg(test)]
static NGINX_LOG_RE: OnceLock<Regex> = OnceLock::new();
#[cfg(test)]
static SQLI_RE: OnceLock<Regex> = OnceLock::new();

#[tokio::main]
async fn main() -> Result<()> {
    if env::args().any(|a| a == "--hash-password") {
        return auth::print_password_hash();
    }
    dotenvy::dotenv().ok();
    tracing_subscriber::fmt()
        .with_env_filter(env::var("RUST_LOG").unwrap_or("info".into()))
        .init();
    let auth = auth::Auth::from_env()?;
    if env::args().any(|a| a == "--check-config") {
        info!("Authentication configuration is valid");
        return Ok(());
    }
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect(&env::var("DATABASE_URL")?)
        .await?;
    sqlx::migrate!("./migrations").run(&pool).await?;
    let whitelist = env::var("IP_WHITELIST")
        .unwrap_or("127.0.0.1,192.168.10.1,192.168.20.1,192.168.20.10".into())
        .split(',')
        .filter(|s| !s.trim().is_empty())
        .map(|s| s.trim().parse())
        .collect::<std::result::Result<Vec<IpAddr>, _>>()?;
    let state = AppState {
        pool,
        ingestion: Arc::new(ingest::Config::from_env()?),
        sensor_id: env::var("SECURITY_SENSOR_ID").unwrap_or_else(|_| "local".into()),
        safety: Arc::new(network::Safety::from_env().await?),
        auth,
        policy: PolicyEngine::from_env(),
        firewall_cmd: env::var("PBL4_FIREWALL_CMD")
            .unwrap_or("/usr/local/bin/pbl4-firewall".into()),
        whitelist: Arc::new(whitelist),
        watchers: Default::default(),
    };
    anyhow::ensure!(
        events::valid_request_id(&state.sensor_id),
        "SECURITY_SENSOR_ID must be 1..128 safe ASCII characters"
    );
    let mut sources = vec![
        (
            "SURICATA",
            env::var("SURICATA_EVE_PATH").unwrap_or("/var/log/suricata/eve.json".into()),
        ),
        (
            "NGINX",
            env::var("NGINX_ACCESS_PATH").unwrap_or("/var/log/nginx/access.log".into()),
        ),
    ];
    if let Ok(path) = env::var("STUDENT_AUDIT_LOG_PATH")
        && !path.trim().is_empty()
    {
        sources.push(("STUDENT_AUDIT", path));
    }
    for (name, path) in sources {
        state
            .watchers
            .write()
            .await
            .insert(name.into(), ingest::WatcherStatus::default());
        tokio::spawn(ingest::watch(state.clone(), name.into(), path));
    }
    tokio::spawn(ingest::retention_worker(state.clone()));
    tokio::spawn(metrics::sample_resources());
    tokio::spawn(firewall::worker(state.clone()));
    let addr = env::var("APP_ADDR").unwrap_or("127.0.0.1:3000".into());
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    info!(%addr, "security dashboard starting");
    axum::serve(listener, router(state))
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
fn router(state: AppState) -> Router {
    let api = Router::new()
        .route(
            "/api/auth/me",
            get(|Extension(user): Extension<auth::Identity>| async { Json(user) }),
        )
        .route("/api/auth/logout", post(auth::logout))
        .route("/api/alerts", get(list_alerts))
        .route("/api/alerts/search", get(search_alerts))
        .route("/api/alerts/{id}", get(alert_detail))
        .route("/api/stats", get(metrics::stats))
        .route("/api/status", get(metrics::status))
        .route("/api/ready", get(metrics::readiness))
        .route("/api/rules", get(api_rules))
        .route("/api/blocked-ips", get(firewall::list).post(block_ip))
        .route("/api/blocked-ips/{ip}", delete(unblock_ip))
        .route("/api/audit", get(firewall::audit))
        .route("/api/application-audit", get(application_audit::list))
        .route(
            "/api/application-audit/{id}",
            get(application_audit::detail),
        )
        .route_layer(middleware::from_fn_with_state(state.clone(), auth::guard));
    Router::new()
        .merge(api)
        .route("/api/auth/login", post(auth::login))
        .route(
            "/health",
            get(|| async { Json(serde_json::json!({"status":"alive"})) }),
        )
        .fallback_service(ServeDir::new("frontend/dist").append_index_html_on_directories(true))
        .layer(axum::extract::DefaultBodyLimit::max(16 * 1024))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}
async fn search_alerts(
    State(state): State<AppState>,
    Query(q): Query<AlertQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if matches!((q.from, q.to), (Some(from), Some(to)) if from >= to) {
        return Err(bad_request(
            "Thời gian bắt đầu phải trước thời gian kết thúc",
        ));
    }
    let result = sqlx::query_scalar::<_, serde_json::Value>(include_str!("alert_search.sql"))
        .bind(q.limit.unwrap_or(50).clamp(1, 200))
        .bind(q.offset.unwrap_or(0).max(0))
        .bind(q.search)
        .bind(q.severity)
        .bind(q.from)
        .bind(q.to)
        .bind(q.source)
        .bind(q.action)
        .bind(q.dest_ip.map(|ip| ip.to_string()))
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
    Ok(Json(result))
}
// Preserve the original array response for existing clients.
async fn list_alerts(
    state: State<AppState>,
    query: Query<AlertQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let Json(report) = search_alerts(state, query).await?;
    Ok(Json(report["items"].clone()))
}
async fn alert_detail(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<i64>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let result = sqlx::query_scalar::<_, serde_json::Value>(include_str!("alert_detail.sql"))
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(api_error)?;
    result.map(Json).ok_or((
        StatusCode::NOT_FOUND,
        Json(serde_json::json!({"message":"Không tìm thấy cảnh báo"})),
    ))
}
async fn block_ip(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Json(req): Json<BlockRequest>,
) -> Result<(StatusCode, Json<serde_json::Value>), ApiError> {
    let ip = firewall::validate(&state, &req.ip).map_err(bad_request)?;
    if req.reason.trim().is_empty() || req.reason.len() > 500 {
        return Err(bad_request("Reason must contain 1–500 characters"));
    }
    if let Some(event_id) = req.event_id {
        let matches: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM security_alerts WHERE id=$1 AND src_ip=$2::inet)",
        )
        .bind(event_id)
        .bind(ip.to_string())
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
        if !matches {
            return Err(bad_request("Source alert does not match IP"));
        }
    }
    let id = firewall::enqueue(
        &state.pool,
        ip,
        "BLOCK",
        &actor.username,
        &req.reason,
        req.event_id,
    )
    .await
    .map_err(api_error)?;
    Ok((
        StatusCode::ACCEPTED,
        Json(serde_json::json!({"id":id,"status":"PENDING"})),
    ))
}
async fn unblock_ip(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Path(ip): Path<String>,
) -> Result<(StatusCode, Json<serde_json::Value>), ApiError> {
    let ip = network::Safety::parse_host(&ip).map_err(bad_request)?;
    let id = firewall::enqueue(
        &state.pool,
        ip,
        "UNBLOCK",
        &actor.username,
        "manual unblock",
        None,
    )
    .await
    .map_err(api_error)?;
    Ok((
        StatusCode::ACCEPTED,
        Json(serde_json::json!({"id":id,"status":"PENDING"})),
    ))
}
async fn api_rules(State(state): State<AppState>) -> Json<Vec<serde_json::Value>> {
    let mut rules: Vec<_> = suricata_rule_catalog(&state.policy)
        .into_iter()
        .map(|r| {
            let mut v = serde_json::to_value(&r).expect("rule metadata");
            v["code"] = serde_json::json!(format!("SID {}", r.sid));
            v["source"] = serde_json::json!("SURICATA");
            v["action_mode"] = serde_json::json!(if r.auto_block_eligible {
                "POLICY_CONTROLLED"
            } else {
                "ALERT_ONLY"
            });
            v
        })
        .collect();
    rules.extend(application_detection::RULES.iter().map(|r| {
        serde_json::json!({
            "sid":null,"code":r.code,"source":"STUDENT_AUDIT","name":r.name,
            "category":"Application Behavior","severity":2,"auto_block_eligible":false,
            "action_mode":"ALERT_ONLY","threshold":r.threshold,"window_seconds":r.seconds
        })
    }));
    Json(rules)
}

fn suricata_rule_catalog(policy: &PolicyEngine) -> Vec<RuleInfo> {
    vec![
        RuleInfo {
            sid: 1000001,
            name: "TCP SYN Burst Threshold",
            category: "Reconnaissance",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000001))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000002,
            name: "SQL Injection - Boolean or Union Attempt",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000002))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000008,
            name: "SQL Injection - Time/Blind, Error or Statement (URI)",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000008))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000003,
            name: "Cross-Site Scripting (XSS) Attempt",
            category: "Web Application Attack",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000003))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000004,
            name: "Path Traversal (Directory Traversal) Attempt",
            category: "Web Application Attack",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000004))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000005,
            name: "OS Command Injection Attempt",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000005))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000006,
            name: "Sensitive Configuration / Credential Probing",
            category: "Reconnaissance",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000006))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000007,
            name: "Automated Vulnerability Scanner Tool Detected",
            category: "Reconnaissance",
            severity: 3,
            auto_block_eligible: policy.evaluate_suricata(Some(1000007))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000009,
            name: "Repeated Login 401 or 403 Responses",
            category: "Authentication Abuse",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000009))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000010,
            name: "HTTP Request Flood (100 requests / 10s per source)",
            category: "Denial of Service",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000010))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000011,
            name: "Suspicious Web Shell File Upload",
            category: "Malicious File Upload",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000011))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000012,
            name: "Possible SSRF to Internal/Metadata Target (URI)",
            category: "Server-Side Request Forgery",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000012))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000013,
            name: "SQL Injection - Time/Blind Request Body",
            category: "Web Application Attack",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000013))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000014,
            name: "Possible SSRF to Internal/Metadata Target (Request Body)",
            category: "Server-Side Request Forgery",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000014))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000015,
            name: "Possible HTTP Request Smuggling CL TE",
            category: "HTTP Request Smuggling",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000015))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000016,
            name: "Possible XML External Entity Declaration",
            category: "XML External Entity",
            severity: 1,
            auto_block_eligible: policy.evaluate_suricata(Some(1000016))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000017,
            name: "Possible Host Header Injection Invalid Authority",
            category: "Host Header Injection",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000017))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
        RuleInfo {
            sid: 1000018,
            name: "Dangerous HTTP Method or WebDAV Observation",
            category: "HTTP Method Policy",
            severity: 2,
            auto_block_eligible: policy.evaluate_suricata(Some(1000018))
                == EventPolicyDecision::EligibleForAutoBlock,
        },
    ]
}

#[cfg(test)]
fn parse_suricata_timestamp(value: &str) -> Result<DateTime<Utc>> {
    Ok(DateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S%.f%z")?.with_timezone(&Utc))
}

#[cfg(test)]
fn parse_nginx_request(line: &str) -> Option<NginxRequest> {
    let re = NGINX_LOG_RE.get_or_init(|| {
        Regex::new(r#"^(\S+) \S+ \S+ \[[^\]]+\] \"(\S+) ([^\"]+) HTTP/[0-9.]+\" (\d{3}) "#)
            .expect("valid nginx regex")
    });
    let caps = re.captures(line)?;
    Some(NginxRequest {
        src_ip: caps.get(1)?.as_str().parse().ok()?,
        target: caps.get(3)?.as_str().to_string(),
    })
}

#[cfg(test)]
fn sql_injection_re() -> &'static Regex {
    SQLI_RE.get_or_init(|| {
        Regex::new(
            r#"(?i)(union\s+select|(?:'|")?\s*(?:or|and)\s+(?:'|")?\d+(?:'|")?\s*=\s*(?:'|")?\d+(?:'|")?|sleep\s*\(|information_schema)"#
        ).expect("valid SQLi regex")
    })
}

#[cfg(test)]
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

#[cfg(test)]
mod integration_tests;

#[cfg(test)]
mod parser_tests {
    use super::*;
    #[test]
    fn catalog_sids_and_severity_match_the_installed_rule_source() {
        let rules = suricata_rule_catalog(&PolicyEngine::new(false, vec![], false));
        let pattern = Regex::new(r"priority:(\d+); sid:(\d+);").unwrap();
        let sensor: std::collections::BTreeMap<u32, i16> = pattern
            .captures_iter(include_str!("../suricata/pbl4.rules"))
            .map(|m| (m[2].parse().unwrap(), m[1].parse().unwrap()))
            .collect();
        assert_eq!(rules.len(), sensor.len());
        for rule in rules {
            assert_eq!(sensor.get(&rule.sid), Some(&rule.severity));
            assert!(!rule.auto_block_eligible);
        }
    }

    #[test]
    fn extended_rules_require_explicit_response_opt_in() {
        let sids = vec![
            1000008, 1000010, 1000011, 1000012, 1000013, 1000014, 1000015, 1000016, 1000017,
            1000018,
        ];
        let off = PolicyEngine::new(false, sids.clone(), false);
        let original = PolicyEngine::new(true, vec![1000002], false);
        let enabled = PolicyEngine::new(true, sids.clone(), false);
        for sid in sids {
            assert_eq!(
                off.evaluate_suricata(Some(sid)),
                EventPolicyDecision::AlertOnly
            );
            assert_eq!(
                original.evaluate_suricata(Some(sid)),
                EventPolicyDecision::AlertOnly
            );
            assert_eq!(
                enabled.evaluate_suricata(Some(sid)),
                EventPolicyDecision::EligibleForAutoBlock
            );
        }
    }

    #[test]
    fn extended_alerts_have_named_metadata_without_raw_payloads() {
        for (sid, severity) in [
            (1000008, 1),
            (1000010, 2),
            (1000011, 1),
            (1000012, 2),
            (1000013, 1),
            (1000014, 2),
            (1000015, 1),
            (1000016, 1),
            (1000017, 2),
            (1000018, 2),
        ] {
            let parsed = events::parse("SURICATA", &serde_json::json!({
                "timestamp":"2026-10-29T10:00:00Z", "event_type":"alert",
                "src_ip":"192.168.10.10", "dest_ip":"192.168.10.1", "proto":"TCP",
                "alert":{"signature_id":sid,"severity":severity,"signature":"RAW_CANARY_SECRET"},
                "payload":"RAW_CANARY_SECRET"
            }).to_string()).unwrap();
            let native = parsed.native_alert.unwrap();
            assert_eq!(native.sid, Some(sid));
            assert_eq!(native.severity, severity);
            assert_ne!(native.category.as_deref(), Some("Sensor Alert"));
            assert!(!native.signature.contains("RAW_CANARY_SECRET"));
            assert!(
                !serde_json::to_string(&parsed.canonical)
                    .unwrap()
                    .contains("RAW_CANARY_SECRET")
            );
        }
    }

    #[test]
    fn validates_lab_hosts_and_rejects_subnets() {
        for ip in ["192.168.10.2", "192.168.10.254", "192.168.10.10/32"] {
            assert!(validate_lab_attacker_ip(ip).is_ok());
        }
        for ip in [
            "192.168.10.1",
            "192.168.10.255",
            "192.168.10.10/24",
            "127.0.0.1",
            "::1",
            "not-ip",
        ] {
            assert!(validate_lab_attacker_ip(ip).is_err());
        }
    }
    #[test]
    fn parses_timestamp_and_nginx_combined() {
        assert!(parse_suricata_timestamp("2026-10-23T12:00:00.123456+0000").is_ok());
        assert!(parse_suricata_timestamp("invalid").is_err());
        let parsed=parse_nginx_request(r#"192.168.10.10 - - [23/Oct/2026:12:00:00 +0000] "GET /login?q=hello HTTP/1.1" 200 15 "-" "curl""#).unwrap();
        assert_eq!(parsed.target, "/login?q=hello");
        assert_eq!(parsed.src_ip.to_string(), "192.168.10.10");
        assert!(parse_nginx_request("invalid").is_none());
    }
    #[test]
    fn sqli_signatures_do_not_match_normal_routes() {
        for target in [
            "/students?q=1' union select 1,2--",
            "/login?user=admin' or 1=1--",
            "/api?id=sleep(5)",
        ] {
            assert!(sql_injection_re().is_match(target));
        }
        for target in ["/api/v1/students", "/dashboard", "/style.css"] {
            assert!(!sql_injection_re().is_match(target));
        }
    }
}

#[cfg(test)]
mod foundation_tests;
