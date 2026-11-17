//! Request-only URI100 projection. The validated raw decoder scope is ASCII.
use regex::Regex;
use std::{collections::HashMap, sync::LazyLock};

static SENSITIVE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)password|passwd|secret|token|cookie|authorization|session|csrf|otp|proof|code|email|username|phone|name|address|cccd").unwrap()
});
static PRIVATE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:pwd|passphrase|credential|api.?key|access.?key|jwt|bearer|ticket|signature|private.?key|^pin$|^pass$|^auth$)").unwrap()
});
static PII: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[\w.+-]+@[\w.-]+|\b(?:\d[ -]?){9,}\b|eyJ[\w-]+\.[\w-]+\.[\w-]+|(?i:bearer|basic)[\x09-\x0d\x1c-\x20]+[^\x09-\x0d\x1c-\x20]+|[A-Za-z0-9_-]{40,}").unwrap()
});
static ESCAPE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"%[0-9a-fA-F]{2}").unwrap());
const METHODS: [&str; 10] = [
    "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "CONNECT", "TRACE", "OTHER",
];
const SYMBOLS: &[u8] = b"/=?&-_.:+*{}[]();!%,~";
static COUNTERS: LazyLock<HashMap<&'static str, Regex>> = LazyLock::new(|| {
    [
        r"\b(?:union|select|sleep|benchmark|or|and|drop|extractvalue)\b",
        r"<script|onerror|onload|javascript:",
        r"\b(?:or|and|not)\b",
        r"(?:!=|<>|<=|>=|=|<|>)",
        r"<[\x09-\x0d\x1c-\x20]*[a-z]",
        r"&(?:#x?[0-9a-f]+|[a-z]+);",
        r"\bon[a-z]+[\x09-\x0d\x1c-\x20]*=",
        r"\b[a-z]+:",
    ]
    .into_iter()
    .map(|p| (p, Regex::new(p).unwrap()))
    .collect()
});

pub fn decode(value: &str, rounds: usize, plus: bool) -> String {
    let mut value = if plus {
        value.replace('+', " ")
    } else {
        value.to_owned()
    };
    for _ in 0..rounds {
        let raw = value.as_bytes();
        let mut out = Vec::with_capacity(raw.len());
        let mut i = 0;
        while i < raw.len() {
            if raw[i] == b'%' && i + 2 < raw.len() {
                if let (Some(a), Some(b)) = (
                    (raw[i + 1] as char).to_digit(16),
                    (raw[i + 2] as char).to_digit(16),
                ) {
                    out.push((a * 16 + b) as u8);
                    i += 3;
                    continue;
                }
            }
            out.push(raw[i]);
            i += 1;
        }
        let next = String::from_utf8_lossy(&out).into_owned();
        if next == value {
            break;
        }
        value = next;
    }
    value
}

fn count(value: &str, token: &str) -> f64 {
    value.matches(token).count() as f64
}
fn matches(value: &str, pattern: &str) -> f64 {
    COUNTERS[pattern].find_iter(value).count() as f64
}
fn flag(value: bool) -> f64 {
    if value { 1.0 } else { 0.0 }
}
fn put(map: &mut HashMap<String, f64>, key: &str, value: f64) {
    map.insert(key.to_owned(), value);
}
fn entropy(value: &str) -> f64 {
    let mut counts: Vec<(char, usize)> = Vec::new();
    for c in value.chars() {
        if let Some((_, n)) = counts.iter_mut().find(|(existing, _)| *existing == c) {
            *n += 1;
        } else {
            counts.push((c, 1));
        }
    }
    let n = value.chars().count() as f64;
    counts
        .into_iter()
        .map(|(_, c)| {
            let p = c as f64 / n;
            -p * p.log2()
        })
        .sum()
}

fn safe_path(raw: &str) -> String {
    let parts: Vec<_> = raw.split('/').collect();
    let mut end = parts.len();
    for (i, p) in parts.iter().enumerate() {
        let text = decode(p, 2, true);
        let inner: Vec<_> = text.split(['/', '\\']).collect();
        if PII.is_match(&text)
            || text.to_lowercase().contains("[redacted]")
            || (SENSITIVE.is_match(&text)
                && (i + 1 < parts.len()
                    || inner
                        .iter()
                        .take(inner.len().saturating_sub(1))
                        .any(|s| SENSITIVE.is_match(s))))
        {
            end = i;
            break;
        }
    }
    let initial = parts[..end].join("/");
    let parts: Vec<_> = initial.split('/').collect();
    for (i, p) in parts.iter().enumerate() {
        let text = decode(p, 3, true);
        if PII.is_match(&text) || PRIVATE.is_match(&text) {
            return parts[..i].join("/");
        }
    }
    initial
}

fn opaque(value: &str) -> bool {
    (value.len() >= 16
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)))
        || (value.len() >= 9 && value.bytes().all(|c| c.is_ascii_digit()))
        || (value.len() >= 17
            && value
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
            && value.bytes().any(|c| c.is_ascii_alphabetic())
            && value.bytes().any(|c| c.is_ascii_digit()))
}

fn private(value: &str, key: bool) -> bool {
    value.len() > 192
        || PII.is_match(value)
        || PRIVATE.is_match(value)
        || opaque(value)
        || ESCAPE.is_match(value)
        || (key && SENSITIVE.is_match(value))
}

fn collapse(value: &str) -> Vec<u8> {
    let mut out = Vec::new();
    let mut previous = 0;
    let mut run = 0;
    for &c in value.as_bytes().iter().take(192) {
        let symbol = if c.is_ascii_uppercase() {
            b'A'
        } else if c.is_ascii_lowercase() {
            b'a'
        } else if c.is_ascii_digit() {
            b'0'
        } else if SYMBOLS.contains(&c) {
            c
        } else {
            b'?'
        };
        run = if symbol == previous { run + 1 } else { 1 };
        previous = symbol;
        if run <= 4 {
            out.push(symbol);
        }
    }
    out
}

fn shape(target: &str) -> Vec<f32> {
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    let mut p: Vec<Vec<u8>> = Vec::new();
    for part in path.split('/').skip(1).take(24) {
        let text = decode(part, 3, false);
        if private(&text, true) || text.contains('@') {
            break;
        }
        p.push(collapse(&text));
    }
    let mut q: Vec<Vec<u8>> = Vec::new();
    if !query.is_empty() {
        for field in query.split('&').take(32) {
            let (key, value) = field.split_once('=').unwrap_or((field, ""));
            let (key, value) = (decode(key, 3, false), decode(value, 3, false));
            if private(&key, true)
                || private(&value, false)
                || key.contains('@')
                || value.contains('@')
            {
                continue;
            }
            let mut part = collapse(&key);
            if field.contains('=') {
                part.push(b'=');
                part.extend(collapse(&value));
            }
            q.push(part);
        }
    }
    let p = p.join(&b'/');
    let q = q.join(&b'&');
    fn describe(v: &[u8], separator: u8) -> Vec<f32> {
        let v = &v[..v.len().min(512)];
        let items: Vec<_> = if v.is_empty() {
            Vec::new()
        } else {
            v.split(|&c| c == separator).map(|i| i.len()).collect()
        };
        let count = |c| v.iter().filter(|&&i| i == c).count();
        [
            usize::from(!v.is_empty()),
            items.len(),
            v.len(),
            items.iter().copied().max().unwrap_or(0),
            items.first().copied().unwrap_or(0),
            items.last().copied().unwrap_or(0),
            count(b'0'),
            count(b'A'),
            count(b'a'),
            v.iter().filter(|c| SYMBOLS.contains(c)).count(),
            count(b'?'),
            v.windows(2).filter(|s| s[0] != s[1]).count(),
        ]
        .into_iter()
        .map(|n| n.min(31) as f32 / 31.0)
        .collect()
    }
    let mut result = describe(&p, b'/');
    result.extend(describe(&q, b'&'));
    result
}

pub fn project(method: &str, target: &str) -> Result<Vec<f32>, &'static str> {
    if !METHODS[..9].contains(&method)
        || target.len() > 4096
        || !target.starts_with('/')
        || target.starts_with("//")
        || !target.is_ascii()
        || target.contains('#')
        || target.bytes().any(|c| c < 0x21 || c == 0x7f)
    {
        return Err("UNSUPPORTED_REQUEST_ENVELOPE");
    }
    // Scope is explicit. Percent-decoded non-ASCII is refused instead of using
    // a subtly different Unicode regex/numeric definition from Python.
    if !decode(target, 3, true).is_ascii() {
        return Err("UNVALIDATED_DECODED_UNICODE");
    }
    let (raw_path, raw_query) = target.split_once('?').unwrap_or((target, ""));
    let path = safe_path(raw_path);
    let mut aliases: HashMap<String, usize> = HashMap::new();
    let mut fields = Vec::new();
    if !raw_query.is_empty() {
        for field in raw_query.split('&').take(64) {
            let (key, value) = field.split_once('=').unwrap_or((field, ""));
            let inspected_key = decode(key, 3, true).to_lowercase();
            let inspected_value = decode(value, 3, true);
            if SENSITIVE.is_match(&inspected_key)
                || PRIVATE.is_match(&inspected_key)
                || PII.is_match(&inspected_key)
                || PII.is_match(&inspected_value)
                || inspected_value.to_lowercase().contains("[redacted]")
                || ESCAPE.is_match(&inspected_key)
            {
                continue;
            }
            let next = aliases.len();
            let alias = *aliases.entry(inspected_key).or_insert(next);
            fields.push(format!("field{alias}={value}"));
        }
    }
    let query = fields.join("&");
    let query_available = raw_query.is_empty() || !fields.is_empty();
    let path_numeric = PII
        .replace_all(if path.is_empty() { "/" } else { &path }, "[redacted]")
        .into_owned();
    let visible: Vec<_> = query
        .split('&')
        .filter(|f| !f.is_empty())
        .take(64)
        .map(|f| {
            let (_, v) = f.split_once('=').unwrap_or((f, ""));
            format!("[key]={}", PII.replace_all(v, "[redacted]"))
        })
        .collect();
    let visible_query = visible
        .iter()
        .filter(|v| !v.to_lowercase().contains("[redacted]"))
        .cloned()
        .collect::<Vec<_>>()
        .join("&");
    let path_masked = path_numeric.to_lowercase().contains("[redacted]")
        || path_numeric.to_lowercase().contains("[id]");
    let view = format!(
        "{}?{}",
        if path_masked { "" } else { &path_numeric },
        visible_query
    );
    let decoded = decode(&view, 2, false).to_lowercase();
    let n = view.len().max(1) as f64;
    let mut v = HashMap::new();
    put(&mut v, "query_length", visible_query.len() as f64);
    put(&mut v, "parameter_count", visible.len() as f64);
    put(
        &mut v,
        "uri_entropy",
        if path_masked {
            0.0
        } else {
            entropy(&path_numeric)
        },
    );
    put(&mut v, "query_entropy", entropy(&visible_query));
    put(
        &mut v,
        "digit_ratio",
        view.bytes().filter(|c| c.is_ascii_digit()).count() as f64 / n,
    );
    put(
        &mut v,
        "special_ratio",
        view.bytes().filter(|c| !c.is_ascii_alphanumeric()).count() as f64 / n,
    );
    put(
        &mut v,
        "uri_lexical_available",
        if path_masked { 0.0 } else { 1.0 },
    );
    put(
        &mut v,
        "query_lexical_available",
        if query_available && (visible.is_empty() || !visible_query.is_empty()) {
            1.0
        } else {
            0.0
        },
    );
    put(
        &mut v,
        "sqli_keywords",
        matches(
            &decoded,
            r"\b(?:union|select|sleep|benchmark|or|and|drop|extractvalue)\b",
        ),
    );
    put(
        &mut v,
        "xss_tokens",
        matches(&decoded, r"<script|onerror|onload|javascript:"),
    );
    put(&mut v, "traversal_tokens", count(&decoded, "../"));
    for (name, token) in [
        ("quote_single", "'"),
        ("quote_double", "\""),
        ("semicolon", ";"),
        ("percent", "%"),
        ("lt", "<"),
        ("gt", ">"),
        ("dollar", "$"),
        ("pipe", "|"),
    ] {
        put(
            &mut v,
            name,
            count(if name == "percent" { &view } else { &decoded }, token),
        );
    }
    let raw = format!("{path}?{query}");
    let once = decode(&raw, 1, true);
    let twice = decode(&once, 1, false);
    let lower = twice.to_lowercase();
    let vals: Vec<_> = query
        .split('&')
        .filter(|s| !s.is_empty())
        .map(|f| decode(f.split_once('=').map(|(_, v)| v).unwrap_or(""), 2, true))
        .collect();
    let keys: Vec<_> = query
        .split('&')
        .filter(|s| !s.is_empty())
        .map(|f| f.split_once('=').map(|(k, _)| k).unwrap_or(f))
        .collect();
    let lengths: Vec<_> = vals.iter().map(|s| s.len() as f64).collect();
    let mean = lengths.iter().sum::<f64>() / lengths.len().max(1) as f64;
    let std = (lengths.iter().map(|n| (n - mean).powi(2)).sum::<f64>()
        / lengths.len().max(1) as f64)
        .sqrt();
    let n = twice.len().max(1) as f64;
    for (key, value) in [
        ("structure_available", 1.0),
        ("decoded_uri_length", twice.len() as f64),
        ("decoded_query_length", decode(&query, 2, true).len() as f64),
        ("encoding_rounds", flag(once != raw) + flag(twice != once)),
        (
            "percent_escape_count",
            ESCAPE.find_iter(&raw).count() as f64,
        ),
        (
            "encoding_contraction_ratio",
            ((raw.len() as f64 - twice.len() as f64) / raw.len().max(1) as f64).max(0.0),
        ),
        ("non_ascii_ratio", 0.0),
        (
            "uppercase_ratio",
            twice.bytes().filter(|c| c.is_ascii_uppercase()).count() as f64 / n,
        ),
        (
            "whitespace_ratio",
            twice
                .bytes()
                .filter(|&c| matches!(c,9..=13|28..=32))
                .count() as f64
                / n,
        ),
        (
            "max_parameter_length",
            lengths.iter().copied().fold(0.0, f64::max),
        ),
        ("mean_parameter_length", mean),
        ("parameter_length_std", std),
        (
            "duplicate_parameter_count",
            (keys.len() - keys.iter().collect::<std::collections::HashSet<_>>().len()) as f64,
        ),
        (
            "empty_parameter_count",
            vals.iter().filter(|s| s.is_empty()).count() as f64,
        ),
        (
            "numeric_parameter_ratio",
            vals.iter()
                .filter(|s| !s.is_empty() && s.bytes().all(|c| c.is_ascii_digit()))
                .count() as f64
                / vals.len().max(1) as f64,
        ),
        (
            "boolean_operator_count",
            matches(&lower, r"\b(?:or|and|not)\b"),
        ),
        (
            "comparison_operator_count",
            matches(&vals.join(" "), r"(?:!=|<>|<=|>=|=|<|>)"),
        ),
        (
            "html_tag_open_count",
            matches(&lower, r"<[\x09-\x0d\x1c-\x20]*[a-z]"),
        ),
        (
            "html_entity_count",
            matches(&lower, r"&(?:#x?[0-9a-f]+|[a-z]+);"),
        ),
        (
            "event_assignment_count",
            matches(&lower, r"\bon[a-z]+[\x09-\x0d\x1c-\x20]*="),
        ),
        ("uri_scheme_count", matches(&lower, r"\b[a-z]+:")),
    ] {
        put(&mut v, key, value);
    }
    let bytes = raw.as_bytes();
    let invalid = (0..bytes.len())
        .filter(|&i| {
            bytes[i] == b'%'
                && !(i + 2 < bytes.len()
                    && bytes[i + 1].is_ascii_hexdigit()
                    && bytes[i + 2].is_ascii_hexdigit())
        })
        .count();
    put(&mut v, "invalid_escape_count", invalid as f64);
    let mut depth = 0usize;
    let mut maximum = 0usize;
    for c in twice.chars() {
        if c == '(' {
            depth += 1;
        } else if c == ')' {
            depth = depth.saturating_sub(1);
        }
        maximum = maximum.max(depth);
    }
    put(&mut v, "parenthesis_max_depth", maximum as f64);
    for (key, token) in [
        ("sql_comment_open_count", "/*"),
        ("sql_comment_close_count", "*/"),
        ("sql_line_comment_count", "--"),
        ("comma_count", ","),
        ("parenthesis_open_count", "("),
        ("parenthesis_close_count", ")"),
        ("html_tag_close_count", "</"),
        ("path_dot_segment_count", "./"),
        ("backslash_count", "\\"),
        ("slash_count", "/"),
        ("dot_count", "."),
        ("shell_and_count", "&&"),
        ("shell_or_count", "||"),
        ("shell_substitution_count", "$("),
        ("backtick_count", "`"),
        ("newline_count", "\n"),
        ("null_byte_count", "\0"),
    ] {
        put(&mut v, key, count(&lower, token));
    }
    put(
        &mut v,
        "path_parent_segment_count",
        count(&lower, "../") + count(&lower, "..\\"),
    );
    for m in METHODS {
        put(&mut v, &format!("method_{m}"), flag(method == m));
    }
    for (name, a, b) in [
        ("quote_boolean", "quote_single", "boolean_operator_count"),
        (
            "quote_comparison",
            "quote_single",
            "comparison_operator_count",
        ),
        ("tag_event", "html_tag_open_count", "event_assignment_count"),
        ("tag_scheme", "html_tag_open_count", "uri_scheme_count"),
        (
            "parent_backslash",
            "path_parent_segment_count",
            "backslash_count",
        ),
        ("dollar_parenthesis", "dollar", "parenthesis_open_count"),
    ] {
        let value = v[a].min(v[b]);
        put(&mut v, name, value);
    }
    let columns: Vec<String> = serde_json::from_str(include_str!("../uri76-columns.json")).unwrap();
    let mut result = Vec::with_capacity(100);
    for name in columns {
        let value = *v.get(&name).ok_or("FEATURE_CONTRACT_INCOMPLETE")?;
        let value = if name.starts_with("method_")
            || name.ends_with("_ratio")
            || name.ends_with("_available")
        {
            value
        } else {
            let z = value.ln_1p();
            z / (1.0 + z)
        };
        result.push(value as f32);
    }
    result.extend(shape(target));
    if result.len() != 100 || result.iter().any(|n| !n.is_finite()) {
        return Err("INVALID_PROJECTED_VECTOR");
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn envelope_and_privacy() {
        assert_eq!(project("GET", "/").unwrap().len(), 100);
        assert_eq!(
            project("GET", "/a?password=secret").unwrap(),
            project("GET", "/a?password=other").unwrap()
        );
        assert!(project("OTHER", "/").is_err());
        assert!(project("GET", "//other").is_err());
        assert!(project("GET", "/a?q=%E4%B8%80").is_err());
    }
    #[test]
    fn raw_value_masking_and_python_control_whitespace() {
        let target = format!("/a?q=%2f{}", "A".repeat(38));
        assert_eq!(project("GET", &target).unwrap()[51], 0.0);
        assert_eq!(project("GET", "/a?q=Bearer%1cabc").unwrap()[51], 0.0);
    }
}
