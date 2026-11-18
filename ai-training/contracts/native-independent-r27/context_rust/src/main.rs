//! Private offline context projector; not an unauthenticated context ingestion API.
use serde_json::{Value, json};
use std::io::{self, BufRead, Read};

const STATES: [&str; 6] = [
    "AVAILABLE_BEFORE_CUTOFF",
    "OBSERVED_LATE",
    "MISSING",
    "WITHHELD",
    "UNTRUSTED",
    "GROUND_TRUTH_ONLY",
];
const ROLES: [&str; 4] = ["ADMIN", "STAFF", "STUDENT", "OTHER"];
const CATEGORIES: [&str; 6] = [
    "STUDENT_DIRECTORY",
    "SELF_PRINCIPAL",
    "USER_ADMIN",
    "SELF_PROFILE",
    "ACADEMIC_WRITE",
    "OTHER",
];
const BIND: [&str; 10] = [
    "request_key",
    "scope",
    "event_id",
    "proof_sha256",
    "identity_verified",
    "clock_valid",
    "source_mask",
    "category",
    "method",
    "disposition",
];
const OBS: [&str; 10] = [
    "request_key",
    "scope",
    "event_id",
    "proof_sha256",
    "receipt_offset_ns",
    "available_offset_ns",
    "role",
    "actor_session_bound",
    "anonymous",
    "phase",
];

fn exact(v: &Value, keys: &[&str]) -> bool {
    v.as_object()
        .is_some_and(|m| m.len() == keys.len() && keys.iter().all(|k| m.contains_key(*k)))
}
fn hex(v: &Value, n: usize) -> bool {
    v.as_str().is_some_and(|s| {
        s.len() == n
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn uuid(v: &Value) -> bool {
    v.as_str().is_some_and(|s| {
        s.len() == 36
            && s.bytes().enumerate().all(|(i, c)| {
                if [8, 13, 18, 23].contains(&i) {
                    c == b'-'
                } else {
                    c.is_ascii_digit() || (b'a'..=b'f').contains(&c)
                }
            })
    })
}

fn encode(o: &Value, b: &Value) -> Value {
    let mask = b["source_mask"].as_str().unwrap_or("");
    let category = b["category"].as_str().unwrap_or("");
    let disposition = b["disposition"].as_str().unwrap_or("UNTRUSTED");
    let method = b["method"].as_str().unwrap_or("");
    let valid = exact(b, &BIND)
        && b["identity_verified"] == true
        && b["clock_valid"] == true
        && b["request_key"].as_str().is_some_and(|s| !s.is_empty())
        && b["scope"].as_str().is_some_and(|s| !s.is_empty())
        && ["N", "S", "A", "NS", "NA", "SA", "NSA", "NONE"].contains(&mask)
        && CATEGORIES.contains(&category)
        && STATES.contains(&disposition)
        && ["GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"].contains(&method);
    let mut state = if valid { disposition } else { "UNTRUSTED" };
    let role = o["role"].as_str().unwrap_or("");
    let anon = o["anonymous"].as_bool();
    let actor = o["actor_session_bound"].as_bool();
    let observation = exact(o, &OBS)
        && uuid(&o["event_id"])
        && hex(&o["proof_sha256"], 64)
        && ["request_key", "scope", "event_id", "proof_sha256"]
            .iter()
            .all(|k| o[k] == b[k])
        && o["phase"] == "CURRENT_REQUEST_AUDIT"
        && o["receipt_offset_ns"]
            .as_u64()
            .zip(o["available_offset_ns"].as_u64())
            .is_some_and(|(r, a)| r <= a)
        && ((anon == Some(true) && o["role"].is_null() && actor == Some(false))
            || (anon == Some(false) && ROLES.contains(&role) && actor == Some(true)));
    if state == STATES[0] {
        state = if o.is_null() {
            "MISSING"
        } else if !observation {
            "UNTRUSTED"
        } else if o["available_offset_ns"].as_u64().unwrap() > 999_000_000 {
            "OBSERVED_LATE"
        } else if !mask.contains('A') {
            "UNTRUSTED"
        } else if !((method == "GET" && CATEGORIES[..4].contains(&category))
            || (method == "POST" && category == "ACADEMIC_WRITE"))
        {
            "WITHHELD"
        } else {
            STATES[0]
        };
    }
    let available = state == STATES[0];
    let mut v = vec![
        i32::from(available),
        i32::from(available && anon == Some(false)),
    ];
    v.extend(ROLES.iter().map(|r| i32::from(available && role == *r)));
    v.push(i32::from(available && actor == Some(true)));
    v.extend(
        CATEGORIES
            .iter()
            .map(|c| i32::from(available && category == *c)),
    );
    v.extend(STATES.iter().map(|s| i32::from(state == *s)));
    v.extend(
        "NSA"
            .chars()
            .map(|s| i32::from(valid && mask != "NONE" && mask.contains(s))),
    );
    let control = if !available || !ROLES.contains(&role) {
        "ABSTAIN"
    } else if ["STUDENT_DIRECTORY", "ACADEMIC_WRITE"].contains(&category) {
        if ["ADMIN", "STAFF"].contains(&role) {
            "ALLOW"
        } else {
            "DENY"
        }
    } else if category == "USER_ADMIN" {
        if role == "ADMIN" { "ALLOW" } else { "DENY" }
    } else if category == "SELF_PROFILE" {
        if role == "STUDENT" { "ALLOW" } else { "DENY" }
    } else if category == "SELF_PRINCIPAL" {
        "ALLOW"
    } else {
        "ABSTAIN"
    };
    json!({"schema":"idps-trusted-context22-r27-v1","state":state,"vector":v,
           "status":if available{"CONTEXT_AVAILABLE"}else{"ABSTAIN"},"policy_control":control})
}

fn main() -> io::Result<()> {
    let mut input = io::stdin().lock();
    loop {
        let mut buf = Vec::new();
        if input.by_ref().take(16385).read_until(b'\n', &mut buf)? == 0 {
            break;
        }
        if buf.len() > 16384 || buf.last() != Some(&b'\n') {
            println!("{}", json!({"status":"ABSTAIN","reason":"FRAME_BOUND"}));
            break;
        }
        let response = match serde_json::from_slice::<Value>(&buf) {
            Ok(v) if exact(&v, &["observation", "binding"]) => {
                encode(&v["observation"], &v["binding"])
            }
            _ => json!({"status":"ABSTAIN","reason":"INVALID_ENVELOPE"}),
        };
        println!("{response}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn binding() -> Value {
        json!({"request_key":"a","scope":"guest","event_id":null,"proof_sha256":null,
        "identity_verified":true,"clock_valid":true,"source_mask":"NONE","category":"SELF_PRINCIPAL",
        "method":"GET","disposition":"AVAILABLE_BEFORE_CUTOFF"})
    }

    #[test]
    fn none_is_missing_not_an_observed_nginx() {
        let result = encode(&Value::Null, &binding());
        assert_eq!(result["state"], "MISSING");
        assert_eq!(
            &result["vector"].as_array().unwrap()[19..],
            &[json!(0), json!(0), json!(0)]
        );
        assert_eq!(result["policy_control"], "ABSTAIN");
    }

    #[test]
    fn invalid_binding_and_future_snapshot_fail_closed() {
        assert_eq!(encode(&Value::Null, &Value::Null)["state"], "UNTRUSTED");
        let mut b = binding();
        b["clock_valid"] = json!(false);
        assert_eq!(encode(&Value::Null, &b)["state"], "UNTRUSTED");
    }

    #[test]
    fn canonical_identifiers_and_exact_keys() {
        assert!(uuid(&json!("a1234567-1234-1234-1234-123456789abc")));
        assert!(!uuid(&json!("A1234567-1234-1234-1234-123456789abc")));
        let mut b = binding();
        b["X-Role"] = json!("ADMIN");
        assert_eq!(encode(&Value::Null, &b)["state"], "UNTRUSTED");
    }
}
