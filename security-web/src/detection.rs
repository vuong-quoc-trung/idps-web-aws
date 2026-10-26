//! Bounded, stateless HTTP signatures and privacy-first storage views.
//!
//! Detection must run on the request target before redaction. The returned
//! detections contain fixed metadata only; they never carry the matched payload.
//! These signatures identify attempts, not successful exploitation.

use regex::Regex;
use std::sync::OnceLock;

const INPUT_CHARS: usize = 8_192;
const PATH_CHARS: usize = 512;
const QUERY_FIELDS: usize = 64;

#[derive(Clone, Debug)]
pub struct Detection {
    pub rule_id: &'static str,
    pub name: &'static str,
    pub category: &'static str,
    pub severity: i16,
}

struct Signatures {
    comments: Regex,
    sqli: Regex,
    xss: Regex,
    traversal: Regex,
    command: Regex,
    scanner: Regex,
}

fn signatures() -> &'static Signatures {
    static SIGNATURES: OnceLock<Signatures> = OnceLock::new();
    SIGNATURES.get_or_init(|| Signatures {
        comments: Regex::new(r"(?s)/\*.*?\*/").expect("static SQL comment regex"),
        sqli: Regex::new(concat!(
            r#"(?ix)(?:\bunion\s*(?:all\s*)?select\b"#,
            r#"|['"]\s*(?:or|and)\s*(?:\d+\s*=\s*\d+|'[^']{0,32}'\s*=\s*'[^']{0,32}'?|"[^"]{0,32}"\s*=\s*"[^"]{0,32}"?)"#,
            r#"|\b\d+\s+(?:or|and)\s+\d+\s*=\s*\d+"#,
            r#"|\b(?:sleep|pg_sleep|benchmark)\s*\(\s*\d"#,
            r#"|\bwaitfor\s+delay\s*['"]"#,
            r#"|\b(?:extractvalue|updatexml|load_file|xp_cmdshell)\s*\("#,
            r#"|\b(?:from|join)\s+information_schema\b)"#,
        ))
        .expect("static SQLi regex"),
        xss: Regex::new(concat!(
            r"(?ix)(?:<\s*(?:script|iframe|svg|img|object|embed)\b",
            r"|\bjava\s*script\s*:",
            r"|<[^>]{0,256}\bon(?:error|load|click|mouseover|focus|animationstart)\s*=",
            r"|\bon(?:error|load|click|mouseover|focus|animationstart)\s*=\s*(?:alert|confirm|prompt|eval|fetch|document|window)\b",
            r"|\bdata\s*:\s*text/html)",
        ))
        .expect("static XSS regex"),
        traversal: Regex::new(concat!(
            r"(?ix)(?:\.\.[/\\]",
            r"|[/\\](?:etc[/\\](?:passwd|shadow)|proc[/\\]self[/\\]environ|windows[/\\](?:win\.ini|system32))\b",
            r"|(?:^|[/\\=])\.env(?:[./\\?;&]|$)",
            r"|(?:^|[/\\=])\.(?:git|ssh)(?:[/\\?;&]|$))",
        ))
        .expect("static traversal regex"),
        command: Regex::new(concat!(
            r"(?ix)(?:;|\|\|?|&&|`|\$\(|[\r\n])\s*",
            r"(?:cat|id|whoami|uname|nc|netcat|sh|bash|curl|wget|powershell|cmd(?:\.exe)?|python(?:3)?|perl)\b",
        ))
        .expect("static command injection regex"),
        scanner: Regex::new(concat!(
            r"(?i)(?:^|[^a-z0-9])",
            r"(?:sqlmap|nikto|dirbuster|gobuster|masscan|acunetix|nmap|zgrab|nuclei|ffuf)",
            r"(?:[^a-z0-9]|$)",
        ))
        .expect("static scanner UA regex"),
    })
}

fn bounded(value: &str, max_chars: usize) -> String {
    value.chars().take(max_chars).collect()
}

fn hex(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

// Tolerate malformed escapes and invalid UTF-8 without abandoning the rest of
// the target. Decoding only shrinks bytes; input and output have explicit caps.
fn decode_twice(value: &str, form_query: bool) -> String {
    let mut current = bounded(value, INPUT_CHARS);
    if form_query {
        current = current.replace('+', " ");
    }
    for _ in 0..2 {
        let bytes = current.as_bytes();
        let mut decoded = Vec::with_capacity(bytes.len());
        let mut at = 0;
        while at < bytes.len() {
            if bytes[at] == b'%'
                && let (Some(&a), Some(&b)) = (bytes.get(at + 1), bytes.get(at + 2))
                && let (Some(a), Some(b)) = (hex(a), hex(b))
            {
                decoded.push((a << 4) | b);
                at += 3;
            } else {
                decoded.push(bytes[at]);
                at += 1;
            }
        }
        let next = bounded(&String::from_utf8_lossy(&decoded), INPUT_CHARS);
        if next == current {
            break;
        }
        current = next;
    }
    current
}

// HTTP absolute-form targets may contain credentials in the authority. Neither
// the authority nor a fragment belongs in a persisted application path.
fn origin_target(value: &str) -> &str {
    let authority = if value
        .get(..7)
        .is_some_and(|s| s.eq_ignore_ascii_case("http://"))
    {
        Some(&value[7..])
    } else if value
        .get(..8)
        .is_some_and(|s| s.eq_ignore_ascii_case("https://"))
    {
        Some(&value[8..])
    } else {
        value.strip_prefix("//")
    };
    match authority {
        Some(authority) => authority
            .find(['/', '?', '#'])
            .map(|at| &authority[at..])
            .unwrap_or("/"),
        None => value,
    }
}

fn normalized_parts(target: &str) -> (String, Option<String>) {
    let limited = bounded(target, INPUT_CHARS);
    let origin = origin_target(&limited);
    let no_fragment = origin.split('#').next().unwrap_or("");
    let (path, query) = no_fragment
        .split_once('?')
        .map(|(path, query)| (path, Some(query)))
        .unwrap_or((no_fragment, None));
    (
        decode_twice(path, false),
        query.map(|q| decode_twice(q, true)),
    )
}

/// Return each matching family once in a stable order. All families are
/// alert-only facts; response eligibility remains the policy engine's concern.
pub fn detect(target: &str, user_agent: Option<&str>) -> Vec<Detection> {
    let rules = signatures();
    let (path, query) = normalized_parts(target);
    let combined = match &query {
        Some(query) => format!("{path}?{query}"),
        None => path,
    };
    let printable: String = combined
        .chars()
        .filter(|c| !c.is_control() || c.is_whitespace())
        .collect();
    let sql_view = rules.comments.replace_all(&printable, "");
    let mut found = Vec::new();
    for (matches, rule_id, name, category, severity) in [
        (
            rules.sqli.is_match(&sql_view),
            "SQLI",
            "SQL Injection Attempt",
            "Web Application Attack",
            1,
        ),
        (
            rules.xss.is_match(&printable),
            "XSS",
            "Cross-Site Scripting Attempt",
            "Web Application Attack",
            2,
        ),
        (
            rules.traversal.is_match(&printable),
            "PATH_TRAVERSAL",
            "Path Traversal or Sensitive File Probe",
            "Web Application Attack",
            2,
        ),
        (
            query.as_ref().is_some_and(|q| rules.command.is_match(q)),
            "COMMAND_INJECTION",
            "OS Command Injection Attempt",
            "Web Application Attack",
            1,
        ),
        (
            user_agent.is_some_and(|ua| rules.scanner.is_match(&bounded(ua, INPUT_CHARS))),
            "SCANNER_UA",
            "Automated Scanner User-Agent",
            "Reconnaissance",
            3,
        ),
    ] {
        if matches {
            found.push(Detection {
                rule_id,
                name,
                category,
                severity,
            });
        }
    }
    found
}

fn safe_route_segment(value: &str) -> bool {
    matches!(
        value.to_ascii_lowercase().as_str(),
        "api"
            | "auth"
            | "login"
            | "logout"
            | "csrf"
            | "me"
            | "profile"
            | "completion"
            | "academic"
            | "classmates"
            | "students"
            | "users"
            | "faculties"
            | "majors"
            | "classes"
            | "training-programs"
            | "addresses"
            | "family-members"
            | "emergency-contacts"
            | "post-graduation-contacts"
            | "profile-options"
            | "activate"
            | "activation"
            | "verify"
            | "send"
            | "forgot-password"
            | "reset-password"
            | "change-password"
            | "reissue-token"
            | "access-logs"
            | "dashboard"
            | "catalog"
            | "assets"
            | "images"
            | "public"
            | "favicon.ico"
            | "favicon.svg"
            | "icons.svg"
            | "index.html"
            | "robots.txt"
            | "health"
    )
}

fn sensitive_segment(value: &str) -> bool {
    matches!(
        value.to_ascii_lowercase().as_str(),
        "token"
            | "tokens"
            | "password"
            | "secret"
            | "session"
            | "sessions"
            | "jsessionid"
            | "authorization"
            | "bearer"
            | "otp"
            | "code"
    )
}

fn safe_query_key(value: &str) -> bool {
    matches!(
        value.to_ascii_lowercase().as_str(),
        "q" | "search"
            | "query"
            | "filter"
            | "page"
            | "size"
            | "sort"
            | "limit"
            | "offset"
            | "id"
            | "studentid"
            | "studentcode"
            | "facultyid"
            | "majorid"
            | "classid"
            | "status"
            | "role"
            | "from"
            | "to"
            | "fields"
            | "token"
            | "access_token"
            | "refresh_token"
            | "password"
            | "secret"
            | "code"
            | "otp"
            | "csrf"
            | "_csrf"
            | "email"
            | "username"
            | "session"
            | "jsessionid"
    )
}

/// Produce a storage-safe path and query. Only known route/key literals are
/// retained: numeric path segments become `[id]`, other dynamic segments are
/// suppressed, every query value is masked, and fragments/URL authorities are
/// discarded. Unknown parameter names are also suppressed because a secret or
/// payload can occur in the key itself. Duplicate query fields are preserved.
///
/// The bool records any redaction, normalization or truncation. This is not a
/// reversible representation and must never be used for routing or detection.
pub fn redact_target(target: &str) -> (String, Option<String>, bool) {
    let (decoded_path, decoded_query) = normalized_parts(target);
    let mut changed = target.chars().count() > INPUT_CHARS;
    let mut tail_sensitive = false;
    let path_without_suffix = decoded_path.split(['?', '#']).next().unwrap_or("");
    let mut segments = Vec::new();
    for segment in path_without_suffix.split('/') {
        if segment.is_empty() {
            segments.push(String::new());
            continue;
        }
        let (base, had_parameters) = segment
            .split_once(';')
            .map(|(base, _)| (base, true))
            .unwrap_or((segment, false));
        let safe = if tail_sensitive {
            "[redacted]".into()
        } else if sensitive_segment(base) {
            tail_sensitive = true;
            "[redacted]".into()
        } else if safe_route_segment(base) || matches!(base, "[id]" | "[redacted]") {
            base.to_owned()
        } else if base.len() <= 20 && base.bytes().all(|b| b.is_ascii_digit()) {
            "[id]".into()
        } else {
            "[redacted]".into()
        };
        changed |= had_parameters || safe != segment;
        segments.push(safe);
    }
    let mut path = segments.join("/");
    if !path.starts_with('/') {
        path.insert(0, '/');
    }
    if path.is_empty() {
        path.push('/');
    }
    // Truncate at a character boundary and never propagate attacker controls.
    path = bounded(&path, PATH_CHARS);
    changed |= path != decoded_path;
    let query = decoded_query.map(|query| {
        let mut fields = Vec::new();
        for field in query.split(['&', ';']).filter(|field| !field.is_empty()) {
            if fields.len() == QUERY_FIELDS {
                changed = true;
                break;
            }
            let key = field.split('=').next().unwrap_or("").trim();
            let key = if safe_query_key(key) {
                key.to_ascii_lowercase()
            } else {
                "[key]".into()
            };
            fields.push(format!("{key}=[REDACTED]"));
        }
        changed |= !query.is_empty();
        fields.join("&")
    });
    let original_path = target.split(['?', '#']).next().unwrap_or("");
    changed |= path != original_path || target.contains('#');
    (path, query, changed)
}

/// Reduce untrusted free text (primarily User-Agent) to known product families.
/// Arbitrary prose, versions, URLs, header values and unknown products are not
/// retained: filtering only CR/LF would still leak credentials in a forged UA.
pub fn redact_text(value: &str, max_chars: usize) -> String {
    if max_chars == 0 || value.trim().is_empty() {
        return String::new();
    }
    let lower = bounded(value, INPUT_CHARS).to_ascii_lowercase();
    const PRODUCTS: &[(&str, &str)] = &[
        ("sqlmap", "sqlmap"),
        ("nikto", "nikto"),
        ("dirbuster", "dirbuster"),
        ("gobuster", "gobuster"),
        ("masscan", "masscan"),
        ("acunetix", "acunetix"),
        ("nmap", "nmap"),
        ("zgrab", "zgrab"),
        ("nuclei", "nuclei"),
        ("ffuf", "ffuf"),
        ("mozilla", "Mozilla"),
        ("chromium", "Chromium"),
        ("chrome", "Chrome"),
        ("firefox", "Firefox"),
        ("safari", "Safari"),
        ("edg/", "Edge"),
        ("curl", "curl"),
        ("wget", "wget"),
        ("python-requests", "python-requests"),
        ("postmanruntime", "PostmanRuntime"),
        ("go-http-client", "Go-http-client"),
    ];
    let products: Vec<_> = PRODUCTS
        .iter()
        .filter_map(|(needle, name)| lower.contains(needle).then_some(*name))
        .collect();
    bounded(
        &if products.is_empty() {
            "[REDACTED]".into()
        } else {
            products.join(" ")
        },
        max_chars,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ids(target: &str, ua: Option<&str>) -> Vec<&'static str> {
        detect(target, ua).iter().map(|d| d.rule_id).collect()
    }

    #[test]
    fn detects_contextual_sqli_and_bounded_comment_encoding_variants() {
        for target in [
            "/api/students?q=1%27%20OR%201%3D1--",
            "/api/students?q=1 OR 1=1",
            "/api/students?q=' or 'a'='a'--",
            "/api/students?q=UN/**/ION/**/SEL/**/ECT 1,2",
            "/api/students?q=%2527%2520OR%25201%253D1--",
            "/api/students?q=pg_sleep(5)",
            "/api/students?q=extractvalue(1,concat(0x7e,version()))",
            "/api/students?q=%ff%27 OR 1=1",
        ] {
            assert!(ids(target, None).contains(&"SQLI"), "{target}");
        }
    }

    #[test]
    fn detects_xss_scripts_handlers_schemes_and_double_encoding() {
        for target in [
            "/api/students?q=%3Cscript%3Ealert(1)%3C/script%3E",
            "/api/students?q=%253Csvg%2520onload%253Dconfirm(1)%253E",
            "/api/students?q=java%00script:alert(1)",
            "/api/students?q=onerror=alert(1)",
            "/api/students?q=<a onfocus=document.cookie>",
        ] {
            assert!(ids(target, None).contains(&"XSS"), "{target}");
        }
    }

    #[test]
    fn detects_traversal_and_sensitive_file_probes() {
        for target in [
            "/../../etc/passwd",
            "/api/students?file=%252e%252e%252fetc%252fpasswd",
            "/api/students?file=..%5c..%5cwindows%5cwin.ini",
            "/.env",
            "/.env.production",
            "/.git/HEAD",
            "/api/students?file=/.ssh/id_rsa",
        ] {
            assert!(ids(target, None).contains(&"PATH_TRAVERSAL"), "{target}");
        }
    }

    #[test]
    fn command_signatures_require_query_and_shell_command_context() {
        for target in [
            "/api/students?q=ok;whoami",
            "/api/students?q=ok%26%26id",
            "/api/students?q=$(cat /etc/passwd)",
            "/api/students?q=ok%0aid",
            "/api/students?q=ok|curl https://example.invalid",
        ] {
            assert!(ids(target, None).contains(&"COMMAND_INJECTION"), "{target}");
        }
        for target in [
            "/people/O'Connor",
            "/people/cat;whoami",
            "/api/students?fields=id&classid=12&sort=name",
            "/api/students?search=cat behavior; students",
        ] {
            assert!(
                !ids(target, None).contains(&"COMMAND_INJECTION"),
                "{target}"
            );
        }
    }

    #[test]
    fn scanner_user_agents_include_nuclei_and_ffuf_without_substring_matches() {
        for ua in [
            "sqlmap/1.0",
            "Nuclei - test",
            "ffuf v2",
            "Nmap Scripting Engine",
        ] {
            assert!(ids("/", Some(ua)).contains(&"SCANNER_UA"));
        }
        for ua in [
            "Mozilla/5.0 Chrome/123.0",
            "campus-nmaple-browser",
            "pbl4-lab-probe/1.0",
        ] {
            assert!(!ids("/", Some(ua)).contains(&"SCANNER_UA"));
        }
    }

    #[test]
    fn benign_academic_unicode_apostrophes_and_search_words_do_not_alert() {
        for target in [
            "/api/students?search=Nguy%E1%BB%85n+V%C4%83n+An",
            "/api/students?search=O%27Connor",
            "/api/students?search=student+union+meeting",
            "/api/students?search=selection+and+analysis",
            "/api/students?fields=id&sort=name&classid=12",
            "/api/students?search=100%25+progress",
            "/api/me/academic/classmates",
        ] {
            assert!(
                ids(target, Some("Mozilla/5.0 Chrome/123.0")).is_empty(),
                "{target}"
            );
        }
    }

    #[test]
    fn percent_decoding_is_bounded_and_plus_only_applies_to_raw_query() {
        assert_eq!(
            normalized_parts("/a+b?q=C%2B%2B+language"),
            ("/a+b".into(), Some("q=C++ language".into()))
        );
        assert!(!ids("/api/students?q=%25253Cscript%25253E", None).contains(&"XSS"));
        for target in ["/%", "/%x", "/%zz?q=%FF%", "/đại-học?q=%E0%A4"] {
            let _ = detect(target, None);
            let _ = redact_target(target);
        }
        let long = format!("/api/students?q={}", "đ".repeat(INPUT_CHARS * 4));
        let (path, query) = normalized_parts(&long);
        assert!(path.chars().count() + query.unwrap().chars().count() <= INPUT_CHARS);
        let (path, query, redacted) = redact_target(&long);
        assert!(path.chars().count() <= PATH_CHARS);
        assert!(query.unwrap().len() <= QUERY_FIELDS * 40);
        assert!(redacted);
    }

    #[test]
    fn each_detection_has_fixed_metadata_and_a_stable_unique_family() {
        let detections = detect(
            "/api/students?q=<script>;id UNION SELECT 1 UNION SELECT 2",
            Some("ffuf"),
        );
        assert_eq!(
            detections.iter().map(|d| d.rule_id).collect::<Vec<_>>(),
            ["SQLI", "XSS", "COMMAND_INJECTION", "SCANNER_UA"]
        );
        for detection in detections {
            assert!(!detection.name.is_empty());
            assert!(!detection.category.is_empty());
            assert!((1..=5).contains(&detection.severity));
            assert!(!detection.name.contains("<script>"));
        }
    }

    #[test]
    fn query_redaction_masks_all_values_and_untrusted_keys_with_duplicates() {
        let (path, query, redacted) = redact_target(
            "/api/students?q=CANARY1&q=CANARY2;%2574oken=CANARY3&CANARYKEY=CANARY4&bareCANARY",
        );
        assert_eq!(path, "/api/students");
        assert_eq!(
            query.unwrap(),
            "q=[REDACTED]&q=[REDACTED]&token=[REDACTED]&[key]=[REDACTED]&[key]=[REDACTED]"
        );
        assert!(redacted);
    }

    #[test]
    fn path_redaction_keeps_auth_routes_and_masks_ids_tokens_and_matrix_params() {
        for path in [
            "/api/auth/login",
            "/api/auth/activation/verify",
            "/api/auth/activation/send",
            "/api/auth/forgot-password",
            "/api/auth/reset-password",
            "/api/auth/change-password",
            "/api/auth/csrf",
            "/api/auth/logout",
            "/api/auth/me",
            "/api/me/academic/classmates",
        ] {
            assert_eq!(redact_target(path), (path.into(), None, false));
        }
        for target in [
            "/api/students/123456",
            "/api/token/CANARYTOKEN",
            "/api/session/CANARYSESSION/students",
            "/api/students;jsessionid=CANARYSESSION",
            "/api/students;jsessionid%3dCANARYSESSION/77",
            "/api/CANARYTOKEN",
            "/api/%3Cscript%3ECANARYPAYLOAD%3C/script%3E",
        ] {
            let (path, _, redacted) = redact_target(target);
            assert!(!path.contains("CANARY"), "{target}");
            assert!(!path.contains("<script>"), "{target}");
            assert!(redacted);
        }
        assert_eq!(redact_target("/api/students/123").0, "/api/students/[id]");
    }

    #[test]
    fn url_authority_fragments_controls_and_encoded_suffixes_do_not_leak() {
        for target in [
            "https://user:CANARYAUTH@example.invalid/api/students?token=CANARYQUERY#CANARYFRAGMENT",
            "//user:CANARYAUTH@example.invalid/api/students#CANARYFRAGMENT",
            "/api/students%3ftoken%3dCANARYQUERY",
            "/api/students%23CANARYFRAGMENT",
            "/api/students\r\nAuthorization: Bearer CANARYHEADER",
            "/api/students?q=%0d%0aAuthorization%3aCANARYHEADER",
        ] {
            let (path, query, redacted) = redact_target(target);
            let stored = format!("{path}{query:?}");
            assert!(!stored.contains("CANARY"), "{target}");
            assert!(!stored.chars().any(char::is_control));
            assert!(redacted);
        }
    }

    #[test]
    fn arbitrary_ua_or_error_text_is_suppressed_and_known_products_are_safe() {
        assert_eq!(
            redact_text(
                "Mozilla/5.0 Chrome/123\r\nAuthorization: Bearer CANARYHEADER",
                100
            ),
            "Mozilla Chrome"
        );
        assert_eq!(
            redact_text(
                "CANARYSECRET https://user:CANARYPASS@host/?token=CANARYTOKEN <script>",
                100
            ),
            "[REDACTED]"
        );
        assert_eq!(redact_text("ffuf/2.1 (CANARYSECRET)", 100), "ffuf");
        assert_eq!(redact_text("Mozilla", 3), "Moz");
        assert_eq!(redact_text("Mozilla", 0), "");
        assert_eq!(redact_text("\r\n\t", 10), "");
    }

    #[test]
    fn query_field_count_and_dynamic_path_output_are_bounded() {
        let target = format!("/{}?{}", "CANARY/".repeat(500), "q=CANARY&".repeat(500));
        let (path, query, redacted) = redact_target(&target);
        assert!(path.chars().count() <= PATH_CHARS);
        assert!(query.unwrap_or_default().split('&').count() <= QUERY_FIELDS);
        assert!(!path.contains("CANARY"));
        assert!(redacted);
    }
}
