//! Isolated contract prototype. Not an HTTP endpoint or production authorizer.
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::collections::HashSet;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Verdict {
    version: u8,
    issuer: String,
    key_id: String,
    epoch: String,
    nonce: String,
    alert_id: i64,
    generation: String,
    flow_id: String,
    tx_id: i64,
    request_id: String,
    client_ip: String,
    issued_at: i64,
    expires_at: i64,
    recommend_block: bool,
}
struct Binding<'a> {
    alert_id: i64,
    generation: &'a str,
    flow_id: &'a str,
    tx_id: i64,
    request_id: &'a str,
    client_ip: &'a str,
    verified: bool,
}
fn verify(
    raw: &[u8],
    tag: &[u8],
    key: &[u8],
    epoch: &str,
    now: i64,
    binding: &Binding<'_>,
    seen: &mut HashSet<String>,
) -> bool {
    if raw.len() > 4096 || key.len() < 32 || !binding.verified {
        return false;
    }
    let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(key) else {
        return false;
    };
    mac.update(b"WebSentinel-AI-verdict-v1\0");
    mac.update(raw);
    if mac.verify_slice(tag).is_err() {
        return false;
    }
    let Ok(v) = serde_json::from_slice::<Verdict>(raw) else {
        return false;
    };
    if v.version != 1
        || v.issuer != "websentinel-ai"
        || v.key_id != "lab-key-v1"
        || v.epoch != epoch
        || v.nonce.len() != 32
        || !v.nonce.bytes().all(|b| b.is_ascii_hexdigit())
        || v.issued_at > now
        || v.expires_at <= now
        || v.expires_at.saturating_sub(v.issued_at) > 60
        || v.alert_id != binding.alert_id
        || v.generation != binding.generation
        || v.flow_id != binding.flow_id
        || v.tx_id != binding.tx_id
        || v.request_id != binding.request_id
        || v.client_ip != binding.client_ip
        || !v.recommend_block
    {
        return false;
    }
    seen.insert(format!("{}:{}:{}", v.key_id, v.epoch, v.nonce))
}
#[test]
fn authenticated_bound_expiring_non_replayable_contract() {
    let key = [7u8; 32];
    let mut seen = HashSet::new();
    let mut v = Verdict {
        version: 1,
        issuer: "websentinel-ai".into(),
        key_id: "lab-key-v1".into(),
        epoch: "epoch1".into(),
        nonce: "a".repeat(32),
        alert_id: 5,
        generation: "g".into(),
        flow_id: "123".into(),
        tx_id: 0,
        request_id: "rid".into(),
        client_ip: "8.8.8.8".into(),
        issued_at: 100,
        expires_at: 130,
        recommend_block: true,
    };
    let mut b = Binding {
        alert_id: 5,
        generation: "g",
        flow_id: "123",
        tx_id: 0,
        request_id: "rid",
        client_ip: "8.8.8.8",
        verified: true,
    };
    let sign = |v: &Verdict| {
        let raw = serde_json::to_vec(v).unwrap();
        let mut m = Hmac::<Sha256>::new_from_slice(&key).unwrap();
        m.update(b"WebSentinel-AI-verdict-v1\0");
        m.update(&raw);
        (raw, m.finalize().into_bytes().to_vec())
    };
    let (raw, tag) = sign(&v);
    assert!(verify(&raw, &tag, &key, "epoch1", 110, &b, &mut seen));
    assert!(!verify(&raw, &tag, &key, "epoch1", 110, &b, &mut seen));
    assert!(!verify(
        &raw,
        &tag,
        &key,
        "epoch2",
        110,
        &b,
        &mut HashSet::new()
    ));
    assert!(!verify(
        &raw,
        &tag,
        &key,
        "epoch1",
        130,
        &b,
        &mut HashSet::new()
    ));
    assert!(!verify(
        &raw,
        &[0; 32],
        &key,
        "epoch1",
        110,
        &b,
        &mut HashSet::new()
    ));
    b.verified = false;
    assert!(!verify(
        &raw,
        &tag,
        &key,
        "epoch1",
        110,
        &b,
        &mut HashSet::new()
    ));
    b.verified = true;
    b.tx_id = 1;
    assert!(!verify(
        &raw,
        &tag,
        &key,
        "epoch1",
        110,
        &b,
        &mut HashSet::new()
    ));
    b.tx_id = 0;
    v.recommend_block = false;
    let (raw, tag) = sign(&v);
    assert!(!verify(
        &raw,
        &tag,
        &key,
        "epoch1",
        110,
        &b,
        &mut HashSet::new()
    ));
}
