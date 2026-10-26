//! Canonical Event Schema 1.0. The matching language-neutral contract lives in contracts/.
use crate::detection::{self, Detection};
use crate::*;
use serde_json::Value;

pub const SCHEMA_VERSION: &str = "1.0";
pub const MAX_TARGET_CHARS: usize = 8192;

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FlowFeatures {
    pub duration_seconds: Option<f64>,
    pub bytes_to_server: Option<u64>,
    pub bytes_to_client: Option<u64>,
    pub packets_to_server: Option<u64>,
    pub packets_to_client: Option<u64>,
    pub state: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct QueryFeatures {
    pub length: u64,
    pub parameter_count: u64,
    pub percent_count: u64,
    pub quote_count: u64,
    pub operator_count: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CanonicalEvent {
    pub schema_version: String,
    pub event_id: String,
    pub source: String,
    pub source_instance: String,
    pub timestamp: DateTime<Utc>,
    pub request_id: Option<String>,
    #[serde(default)]
    pub client_ip: Option<IpAddr>,
    #[serde(default)]
    pub peer_ip: Option<IpAddr>,
    pub user_id: Option<String>,
    pub username: Option<String>,
    pub role: Option<String>,
    pub session_hmac: Option<String>,
    pub http_method: Option<String>,
    pub uri_path: Option<String>,
    pub query_string: Option<String>,
    pub status_code: Option<u16>,
    pub latency_ms: Option<f64>,
    pub user_agent: Option<String>,
    pub event_type: String,
    pub outcome: String,
    #[serde(default)]
    pub dest_ip: Option<IpAddr>,
    #[serde(default)]
    pub src_port: Option<u16>,
    #[serde(default)]
    pub dest_port: Option<u16>,
    #[serde(default)]
    pub transport: Option<String>,
    #[serde(default)]
    pub flow_id: Option<String>,
    #[serde(default)]
    pub request_bytes: Option<u64>,
    #[serde(default)]
    pub response_bytes: Option<u64>,
    #[serde(default)]
    pub flow: Option<FlowFeatures>,
    #[serde(default)]
    pub query_features: Option<QueryFeatures>,
    pub redacted: bool,
    pub truncated: bool,
}

impl CanonicalEvent {
    pub fn new(source: &str, timestamp: DateTime<Utc>) -> Self {
        Self {
            schema_version: SCHEMA_VERSION.into(),
            event_id: String::new(),
            source: source.into(),
            source_instance: "local".into(),
            timestamp,
            request_id: None,
            client_ip: None,
            peer_ip: None,
            user_id: None,
            username: None,
            role: None,
            session_hmac: None,
            http_method: None,
            uri_path: None,
            query_string: None,
            status_code: None,
            latency_ms: None,
            user_agent: None,
            event_type: "http_request".into(),
            outcome: "unknown".into(),
            dest_ip: None,
            src_port: None,
            dest_port: None,
            transport: None,
            flow_id: None,
            request_bytes: None,
            response_bytes: None,
            flow: None,
            query_features: None,
            redacted: false,
            truncated: false,
        }
    }

    pub fn validate(&self) -> Result<()> {
        anyhow::ensure!(
            self.schema_version == SCHEMA_VERSION,
            "Unsupported schema version"
        );
        anyhow::ensure!(
            matches!(self.source.as_str(), "STUDENT_AUDIT" | "NGINX" | "SURICATA"),
            "Invalid source"
        );
        for id in [&self.event_id, &self.source_instance] {
            anyhow::ensure!(
                !id.is_empty()
                    && id.len() <= 128
                    && id
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b)),
                "Invalid event identity"
            );
        }
        if let Some(id) = &self.request_id {
            anyhow::ensure!(valid_request_id(id), "Invalid request ID");
        }
        for value in [&self.user_id, &self.username, &self.session_hmac]
            .into_iter()
            .flatten()
        {
            anyhow::ensure!(
                value
                    .strip_prefix("hmac-sha256:")
                    .is_some_and(|h| h.len() == 64
                        && h.bytes()
                            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())),
                "Identity must be an HMAC pseudonym"
            );
        }
        anyhow::ensure!(
            self.role
                .as_deref()
                .is_none_or(|r| matches!(r, "ADMIN" | "STAFF" | "STUDENT" | "ANONYMOUS")),
            "Invalid role"
        );
        anyhow::ensure!(
            self.status_code.is_none_or(|s| (100..=599).contains(&s)),
            "Invalid HTTP status"
        );
        anyhow::ensure!(
            self.latency_ms.is_none_or(|n| n.is_finite() && n >= 0.0),
            "Invalid latency"
        );
        anyhow::ensure!(
            matches!(self.outcome.as_str(), "success" | "failure" | "unknown"),
            "Invalid outcome"
        );
        anyhow::ensure!(
            matches!(
                self.event_type.as_str(),
                "http_request" | "flow" | "alert" | "dns" | "tls" | "other"
            ),
            "Invalid event type"
        );
        if let Some(flow) = &self.flow {
            anyhow::ensure!(
                flow.duration_seconds
                    .is_none_or(|n| n.is_finite() && n >= 0.0),
                "Invalid flow duration"
            );
        }
        Ok(())
    }

    fn sanitize(&mut self, target: Option<&str>) {
        if let Some(target) = target {
            self.truncated |= target.chars().count() > MAX_TARGET_CHARS;
            let (path, query, redacted) = detection::redact_target(target);
            self.uri_path = Some(path);
            self.query_string = query;
            self.redacted |= redacted;
        }
        if let Some(ua) = &self.user_agent {
            let clean = detection::redact_text(ua, 1024);
            self.truncated |= ua.chars().count() > 1024;
            self.redacted |= &clean != ua;
            self.user_agent = Some(clean);
        }
        if let Some(method) = &self.http_method {
            let safe = if matches!(
                method.as_str(),
                "GET"
                    | "HEAD"
                    | "OPTIONS"
                    | "POST"
                    | "PUT"
                    | "PATCH"
                    | "DELETE"
                    | "CONNECT"
                    | "TRACE"
                    | "OTHER"
            ) {
                method.clone()
            } else {
                "OTHER".into()
            };
            self.redacted |= safe != *method;
            self.http_method = Some(safe);
        }
        if let Some(flow) = &mut self.flow {
            flow.state = flow.state.as_ref().map(|s| {
                if matches!(s.as_str(), "new" | "established" | "closed" | "bypassed") {
                    s.clone()
                } else {
                    "unknown".into()
                }
            });
        }
        self.transport = self.transport.as_ref().map(|s| {
            if matches!(
                s.as_str(),
                "HTTP" | "HTTP2" | "TCP" | "UDP" | "ICMP" | "ICMPv6" | "SCTP" | "TLS"
            ) {
                s.clone()
            } else {
                "UNKNOWN".into()
            }
        });
        self.flow_id = self
            .flow_id
            .as_ref()
            .filter(|s| {
                s.len() <= 128
                    && s.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b))
            })
            .cloned();
    }
}

pub fn valid_request_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b))
}

pub struct NativeAlert {
    pub signature: String,
    pub category: Option<String>,
    pub severity: i16,
    pub sid: Option<u32>,
}

pub struct ParsedEvent {
    pub canonical: CanonicalEvent,
    pub detections: Vec<Detection>,
    pub native_alert: Option<NativeAlert>,
}

fn text(value: &Value, key: &str) -> Option<String> {
    value.get(key)?.as_str().map(str::to_owned)
}
fn ip(value: &Value, key: &str) -> Result<Option<IpAddr>> {
    value
        .get(key)
        .filter(|v| !v.is_null())
        .map(|v| {
            v.as_str()
                .context("IP must be text")?
                .parse()
                .context("Invalid IP")
        })
        .transpose()
}
fn status(value: &Value) -> Result<Option<u16>> {
    let raw = value.get("status_code").or_else(|| value.get("status"));
    raw.filter(|v| !v.is_null())
        .map(|v| {
            let n = v
                .as_u64()
                .or_else(|| v.as_str()?.parse().ok())
                .context("Invalid HTTP status")?;
            anyhow::ensure!((100..=599).contains(&n), "Invalid HTTP status");
            Ok(n as u16)
        })
        .transpose()
}
fn outcome(status: Option<u16>) -> String {
    match status {
        Some(s) if s >= 400 => "failure",
        Some(_) => "success",
        None => "unknown",
    }
    .into()
}
fn timestamp(raw: &str) -> Result<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(raw)
        .or_else(|_| DateTime::parse_from_str(raw, "%Y-%m-%dT%H:%M:%S%.f%z"))
        .map(|t| t.with_timezone(&Utc))
        .context("Invalid timestamp")
}
fn query_features(target: &str) -> Option<QueryFeatures> {
    let query = target
        .split_once('?')?
        .1
        .split('#')
        .next()
        .unwrap_or_default();
    Some(QueryFeatures {
        length: query.len() as u64,
        parameter_count: query.split(['&', ';']).filter(|p| !p.is_empty()).count() as u64,
        percent_count: query.bytes().filter(|b| *b == b'%').count() as u64,
        quote_count: query.bytes().filter(|b| b"'\"".contains(b)).count() as u64,
        operator_count: query.bytes().filter(|b| b";|&`$".contains(b)).count() as u64,
    })
}

pub fn parse(source: &str, line: &str) -> Result<ParsedEvent> {
    let mut event;
    let target;
    let mut native_alert = None;
    let mut signals = None;
    match source {
        "STUDENT_AUDIT" => {
            event = serde_json::from_str::<CanonicalEvent>(line)
                .context("Invalid student audit JSONL")?;
            anyhow::ensure!(event.source == source, "Student source mismatch");
            event.validate()?;
            target = event
                .uri_path
                .as_ref()
                .map(|path| match &event.query_string {
                    Some(q) => format!("{path}?{q}"),
                    None => path.clone(),
                });
        }
        "NGINX" if line.trim_start().starts_with('{') => {
            let value: Value = serde_json::from_str(line).context("Invalid Nginx JSON")?;
            event = CanonicalEvent::new(
                source,
                timestamp(
                    value["timestamp"]
                        .as_str()
                        .context("Missing Nginx timestamp")?,
                )?,
            );
            event.client_ip = ip(&value, "client_ip")?;
            event.request_id = text(&value, "request_id").filter(|s| valid_request_id(s));
            event.http_method = text(&value, "http_method");
            let path = text(&value, "uri_path").context("Missing Nginx path")?;
            target = Some(match text(&value, "query_string") {
                Some(q) => format!("{path}?{q}"),
                None => path,
            });
            event.status_code = status(&value)?;
            event.latency_ms = value["latency_ms"]
                .as_f64()
                .or_else(|| value["latency_seconds"].as_f64().map(|n| n * 1000.0));
            event.user_agent = text(&value, "user_agent");
            event.transport = Some("HTTP".into());
            event.request_bytes = value["request_bytes"].as_u64();
            event.response_bytes = value["response_bytes"].as_u64();
            signals = value.get("rule_signals").cloned();
        }
        "NGINX" => {
            static COMBINED: OnceLock<Regex> = OnceLock::new();
            let caps = COMBINED.get_or_init(|| Regex::new(r#"^(\S+) \S+ \S+ \[([^\]]+)\] "([A-Z]+) ([^"]+) HTTP/[0-9.]+" (\d{3}) (\d+|-) "(?:[^"\\]|\\.)*" "((?:[^"\\]|\\.)*)"$"#).expect("combined regex")).captures(line).context("Malformed Nginx combined log")?;
            event = CanonicalEvent::new(
                source,
                DateTime::parse_from_str(&caps[2], "%d/%b/%Y:%H:%M:%S %z")?.with_timezone(&Utc),
            );
            event.client_ip = Some(caps[1].parse().context("Invalid Nginx IP")?);
            event.http_method = Some(caps[3].into());
            target = Some(caps[4].into());
            event.status_code = Some(caps[5].parse()?);
            event.response_bytes = caps[6].parse().ok();
            event.user_agent = Some(caps[7].into());
            event.transport = Some("HTTP".into());
        }
        "SURICATA" => {
            let value: Value = serde_json::from_str(line).context("Invalid Suricata JSON")?;
            event = CanonicalEvent::new(
                source,
                timestamp(
                    value["timestamp"]
                        .as_str()
                        .context("Missing EVE timestamp")?,
                )?,
            );
            event.event_type = match value["event_type"]
                .as_str()
                .context("Missing EVE event_type")?
            {
                "http" => "http_request",
                "alert" => "alert",
                "flow" => "flow",
                "dns" => "dns",
                "tls" => "tls",
                _ => "other",
            }
            .into();
            event.client_ip = ip(&value, "src_ip")?;
            event.dest_ip = ip(&value, "dest_ip")?;
            event.src_port = value["src_port"].as_u64().map(u16::try_from).transpose()?;
            event.dest_port = value["dest_port"].as_u64().map(u16::try_from).transpose()?;
            event.transport = text(&value, "proto");
            event.flow_id = value
                .get("flow_id")
                .filter(|v| v.is_number())
                .map(Value::to_string);
            if let Some(http) = value.get("http") {
                target = text(http, "url");
                event.http_method = text(http, "http_method");
                event.user_agent = text(http, "http_user_agent");
                event.status_code = status(http)?;
                event.response_bytes = http["length"].as_u64();
                event.request_id = http["request_id"]
                    .as_str()
                    .filter(|s| valid_request_id(s))
                    .map(str::to_owned);
            } else {
                target = None;
            }
            if let Some(flow) = value.get("flow") {
                event.flow = Some(FlowFeatures {
                    duration_seconds: flow["age"].as_f64(),
                    bytes_to_server: flow["bytes_toserver"].as_u64(),
                    bytes_to_client: flow["bytes_toclient"].as_u64(),
                    packets_to_server: flow["pkts_toserver"].as_u64(),
                    packets_to_client: flow["pkts_toclient"].as_u64(),
                    state: text(flow, "state"),
                });
            }
            if event.event_type == "alert" {
                let alert = value
                    .get("alert")
                    .filter(|v| v.is_object())
                    .context("Missing EVE alert")?;
                let sid = alert["signature_id"]
                    .as_u64()
                    .map(u32::try_from)
                    .transpose()?;
                let (name, category) = match sid {
                    Some(1000001) => ("TCP SYN Burst Threshold", "Reconnaissance"),
                    Some(1000002) => (
                        "SQL Injection Boolean or Union Attempt",
                        "Web Application Attack",
                    ),
                    Some(1000003) => ("Cross-Site Scripting Attempt", "Web Application Attack"),
                    Some(1000004) => ("Path Traversal or LFI Attempt", "Web Application Attack"),
                    Some(1000005) => ("Command Injection Attempt", "Web Application Attack"),
                    Some(1000006) => ("Sensitive File Probe", "Reconnaissance"),
                    Some(1000007) => ("Automated Scanner User-Agent", "Reconnaissance"),
                    Some(1000008) => (
                        "SQL Injection Time or Error Attempt",
                        "Web Application Attack",
                    ),
                    Some(1000009) => ("Repeated Authentication Failures", "Authentication Abuse"),
                    _ => ("Suricata Alert", "Sensor Alert"),
                };
                native_alert = Some(NativeAlert {
                    signature: format!("SID {}: {name}", sid.unwrap_or(0)),
                    category: Some(category.into()),
                    severity: alert["severity"].as_u64().unwrap_or(3).clamp(1, 5) as i16,
                    sid,
                });
            }
        }
        _ => bail!("Unsupported source"),
    }
    let mut detections = detection::detect(
        target.as_deref().unwrap_or_default(),
        event.user_agent.as_deref(),
    );
    if let Some(signals) = signals {
        // These are derived by the trusted Nginx log_format/maps, never HTTP headers.
        for (id, name, severity) in [
            ("SQLI", "SQL Injection", 1),
            ("XSS", "Cross-Site Scripting", 2),
            ("PATH_TRAVERSAL", "Path Traversal / LFI", 2),
            ("COMMAND_INJECTION", "Command Injection", 1),
        ] {
            if (signals[id].as_bool() == Some(true) || signals[id].as_u64() == Some(1))
                && !detections.iter().any(|d| d.rule_id == id)
            {
                detections.push(Detection {
                    rule_id: id,
                    name,
                    category: "Web Application Attack",
                    severity,
                });
            }
        }
    }
    // Hints, labels and arbitrary EVE attributes never become model input or stored raw payload.
    if event.source != "STUDENT_AUDIT" {
        event.outcome = outcome(event.status_code);
    }
    if event.source != "STUDENT_AUDIT" && event.query_features.is_none() {
        event.query_features = target.as_deref().and_then(query_features);
    }
    event.sanitize(target.as_deref());
    Ok(ParsedEvent {
        canonical: event,
        detections,
        native_alert,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_http_methods_never_persist_arbitrary_header_text() {
        let parsed = parse("NGINX", r#"{"timestamp":"2026-10-26T00:00:00Z","http_method":"CANARY_SECRET","uri_path":"/api/faculties","status":405}"#).unwrap();
        assert_eq!(parsed.canonical.http_method.as_deref(), Some("OTHER"));
        assert!(parsed.canonical.redacted);
        assert!(
            !serde_json::to_string(&parsed.canonical)
                .unwrap()
                .contains("CANARY_SECRET")
        );
    }

    #[test]
    fn normal_http_and_flow_preserve_features_without_invented_labels() {
        let http = parse("NGINX", r#"{"timestamp":"2026-10-26T03:00:00+07:00","client_ip":"2001:db8::1","request_id":"a123","http_method":"GET","uri_path":"/api/students","query_string":"page=1&token=private-canary","status":200,"latency_seconds":0.125,"response_bytes":42,"user_agent":"Mozilla/5.0"}"#).unwrap();
        assert_eq!(
            http.canonical.timestamp.to_rfc3339(),
            "2026-10-25T20:00:00+00:00"
        );
        assert_eq!(http.canonical.latency_ms, Some(125.0));
        assert_eq!(http.canonical.outcome, "success");
        assert!(http.detections.is_empty());
        assert!(
            !serde_json::to_string(&http.canonical)
                .unwrap()
                .contains("private-canary")
        );
        let flow = parse("SURICATA", r#"{"timestamp":"2026-10-26T00:00:00.000000+0000","event_type":"flow","src_ip":"192.0.2.1","dest_ip":"192.0.2.2","src_port":12345,"dest_port":443,"proto":"TCP","flow_id":1234567890123456789,"flow":{"age":12,"bytes_toserver":100,"bytes_toclient":200,"pkts_toserver":2,"pkts_toclient":3,"state":"closed"},"payload":"discard-this-secret"}"#).unwrap();
        assert_eq!(flow.canonical.flow.unwrap().bytes_to_server, Some(100));
        assert_eq!(
            flow.canonical.flow_id.as_deref(),
            Some("1234567890123456789")
        );
        assert_eq!(flow.canonical.outcome, "unknown");
        assert!(flow.native_alert.is_none());
    }

    #[test]
    fn accepts_combined_and_redacts_alert_evidence() {
        let parsed = parse("NGINX", r#"192.168.10.10 - - [23/Oct/2026:12:00:00 +0000] "GET /api/students?q=1%27%20union%20select%201&token=canary-secret HTTP/1.1" 400 15 "-" "sqlmap""#).unwrap();
        assert!(parsed.detections.iter().any(|d| d.rule_id == "SQLI"));
        assert!(parsed.detections.iter().any(|d| d.rule_id == "SCANNER_UA"));
        assert!(
            !serde_json::to_string(&parsed.canonical)
                .unwrap()
                .contains("canary-secret")
        );
        assert_eq!(parsed.canonical.query_features.unwrap().parameter_count, 2);
    }

    #[test]
    fn safe_nginx_edge_hints_do_not_require_logging_query_values() {
        let parsed = parse("NGINX", r#"{"timestamp":"2026-10-26T00:00:00Z","client_ip":"192.0.2.1","http_method":"GET","uri_path":"/api/students","query_string":null,"status":200,"rule_signals":{"SQLI":1,"XSS":0}}"#).unwrap();
        assert_eq!(parsed.detections[0].rule_id, "SQLI");
        assert!(parsed.canonical.query_string.is_none());
        assert!(
            serde_json::to_value(parsed.canonical)
                .unwrap()
                .get("rule_signals")
                .is_none()
        );
    }

    #[test]
    fn rejects_invalid_sources_timestamps_and_identity() {
        assert!(parse("OTHER", "{}").is_err());
        assert!(parse("SURICATA", r#"{"timestamp":"bad","event_type":"flow"}"#).is_err());
        assert!(
            parse(
                "NGINX",
                r#"{"timestamp":"2026-10-26T00:00:00Z","client_ip":"not-ip","uri_path":"/"}"#
            )
            .is_err()
        );
        let mut e = CanonicalEvent::new("STUDENT_AUDIT", Utc::now());
        e.event_id = "event-1".into();
        e.source_instance = "student-web".into();
        e.username = Some("plaintext-user".into());
        assert!(e.validate().is_err());
        e.username = Some(format!("hmac-sha256:{}", "a".repeat(64)));
        assert!(e.validate().is_ok());
        e.schema_version = "2.0".into();
        assert!(e.validate().is_err());
    }
}

#[cfg(test)]
mod contract_tests {
    use super::*;
    #[test]
    fn canonical_fixture_and_typed_fields_match_the_frozen_contract() {
        let fixture = include_str!("../../contracts/fixtures/student-audit-v1.jsonl");
        let event: CanonicalEvent = serde_json::from_str(fixture).unwrap();
        event.validate().unwrap();
        let schema: Value = serde_json::from_str(include_str!(
            "../../contracts/canonical-event-v1.schema.json"
        ))
        .unwrap();
        let value = serde_json::to_value(event).unwrap();
        let actual: std::collections::BTreeSet<_> =
            value.as_object().unwrap().keys().cloned().collect();
        let expected: std::collections::BTreeSet<_> = schema["properties"]
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        assert_eq!(actual, expected);
        assert_eq!(schema["additionalProperties"], false);
    }
}
