//! Offline batch verifier only. Deliberately not compiled into runtime ingest.
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(deny_unknown_fields)]
struct Tx {
    generation: String,
    flow_id: String,
    tx_id: u64,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Evidence {
    tx: Tx,
    proof: String,
    receipt: String,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Observation {
    #[serde(default)]
    response_complete: bool,
    tx: Tx,
    client: String,
    request_id: String,
    method: String,
    scheme: String,
    host: String,
    target_sha256: String,
    observed_ms: u64,
}
#[derive(Deserialize, Serialize)]
struct Request(
    u8,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
    u64,
    u64,
);
#[derive(Deserialize, Serialize)]
struct Receipt(u8, String, String, String, String, String, u64);
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn unhex(s: &str) -> Option<Vec<u8>> {
    if !s.len().is_multiple_of(2)
        || !s
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect()
}
fn fixed_hex(s: &str, n: usize) -> bool {
    s.len() == n && unhex(s).is_some()
}
fn decode<T: for<'a> Deserialize<'a> + Serialize>(
    wire: &str,
    domain: &str,
    key: &[u8],
) -> Option<T> {
    if wire.len() > 4096 || key.len() != 32 {
        return None;
    }
    let (body, tag) = wire.split_once('.')?;
    if tag.len() != 64 {
        return None;
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(key).ok()?;
    mac.update(domain.as_bytes());
    mac.update(body.as_bytes());
    mac.verify_slice(&unhex(tag)?).ok()?; // constant-time MAC verification
    let bytes = URL_SAFE_NO_PAD.decode(body).ok()?;
    let value: T = serde_json::from_slice(&bytes).ok()?;
    if URL_SAFE_NO_PAD.encode(serde_json::to_vec(&value).ok()?) != body {
        return None;
    }
    Some(value)
}
fn verify(
    e: &Evidence,
    o: &Observation,
    keys: &BTreeMap<(String, String), Vec<u8>>,
) -> Option<(String, String, String)> {
    if !o.response_complete
        || e.tx != o.tx
        || !fixed_hex(&e.tx.generation, 32)
        || e.tx.flow_id.parse::<u64>().is_err()
        || e.tx.tx_id > (1u64 << 53) - 1
    {
        return None;
    }
    // Untrusted header is used only to select a bounded known key, never as proof.
    let (body, _) = e.proof.split_once('.')?;
    if body.len() > 4096 {
        return None;
    }
    let hint: Request = serde_json::from_slice(&URL_SAFE_NO_PAD.decode(body).ok()?).ok()?;
    let key = keys.get(&(hint.1.clone(), hint.2.clone()))?;
    let p: Request = decode(&e.proof, "ws-request-v1:", key)?;
    let r: Receipt = decode(&e.receipt, "ws-receipt-v1:", key)?;
    let ip: std::net::IpAddr = p.4.parse().ok()?;
    if ip.is_loopback() || ip.is_unspecified() || ip.is_multicast() || p.4 != ip.to_string() {
        return None;
    }
    if p.0 != 1
        || !fixed_hex(&p.2, 32)
        || !fixed_hex(&p.3, 32)
        || !fixed_hex(&p.5, 32)
        || !fixed_hex(&p.9, 64)
        || p.1.is_empty()
        || p.1.len() > 64
        || !p.1.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
        || p.6.is_empty()
        || p.6.len() > 32
        || !p.6.bytes().all(|c| c.is_ascii_uppercase() || c == b'-')
        || !matches!(p.7.as_str(), "http" | "https")
        || p.8.is_empty()
        || p.8.len() > 255
        || !p
            .8
            .bytes()
            .all(|c| c.is_ascii_graphic() && c != b'"' && c != b'\\')
        || p.11.checked_sub(p.10) != Some(60000)
        || p.11 > (1u64 << 53) - 1
        || o.observed_ms.saturating_add(1000) < p.10
        || o.observed_ms > p.11
        || (
            p.4.as_str(),
            p.5.as_str(),
            p.6.as_str(),
            p.7.as_str(),
            p.8.as_str(),
            p.9.as_str(),
        ) != (
            o.client.as_str(),
            o.request_id.as_str(),
            o.method.as_str(),
            o.scheme.as_str(),
            o.host.as_str(),
            o.target_sha256.as_str(),
        )
        || r.0 != 1
        || r.1 != p.1
        || r.2 != p.2
        || r.3 != p.3
        || r.4 != hex(&Sha256::digest(e.proof.as_bytes()))
        || r.5 != "accepted"
        || r.6.saturating_add(1000) < p.10
        || r.6 > p.11
    {
        return None;
    }
    Some((p.1, p.2, p.3))
}
/// Complete batch: reject ALL transactions sharing a nonce, independent of arrival
/// order. A streaming implementation needs durable conflict/retraction semantics.
fn resolve(
    rows: &[Evidence],
    observations: &[Observation],
    keys: &BTreeMap<(String, String), Vec<u8>>,
) -> BTreeSet<Tx> {
    let mut claims: BTreeMap<_, BTreeSet<Tx>> = BTreeMap::new();
    let mut candidates = BTreeMap::new();
    for e in rows {
        let mut matching = Vec::new();
        for observation in observations.iter().filter(|o| o.tx == e.tx) {
            if !matching.contains(&observation) {
                matching.push(observation);
            }
        }
        if matching.len() != 1
            || rows
                .iter()
                .any(|x| x.tx == e.tx && (x.proof != e.proof || x.receipt != e.receipt))
        {
            continue;
        }
        if let Some(nonce) = verify(e, matching[0], keys) {
            claims
                .entry(nonce.clone())
                .or_insert_with(BTreeSet::new)
                .insert(e.tx.clone());
            candidates.insert(e.tx.clone(), nonce);
        }
    }
    candidates
        .into_iter()
        .filter_map(|(tx, n)| (claims[&n].len() == 1).then_some(tx))
        .collect()
}

#[derive(Deserialize)]
struct Fixture {
    #[serde(default)]
    rejected: Vec<Evidence>,
    #[serde(default)]
    rejected_observations: Vec<Observation>,
    key_hex: String,
    kid: String,
    epoch: String,
    rows: Vec<Evidence>,
    observations: Vec<Observation>,
}
#[test]
#[ignore = "requires private fixture generated by test-njs-proof.py --proof-chain"]
fn external_njs_suricata_batch() {
    let path = std::env::var("WS_PROOF_TEST_FIXTURE").expect("private fixture required");
    let f: Fixture = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    let keys = BTreeMap::from([((f.kid, f.epoch), unhex(&f.key_hex).unwrap())]);
    assert!(resolve(&f.rejected, &f.rejected_observations, &keys).is_empty());
    let expected = f.rows.len();
    assert!(expected >= 2);
    assert_eq!(resolve(&f.rows, &f.observations, &keys).len(), expected);
    let mut reversed = f.rows.clone();
    reversed.reverse();
    assert_eq!(
        resolve(&reversed, &f.observations, &keys),
        resolve(&f.rows, &f.observations, &keys)
    );
    let mut duplicates = f.rows.clone();
    duplicates.extend(f.rows.clone());
    assert_eq!(resolve(&duplicates, &f.observations, &keys).len(), expected);
    let mut incomplete = f.observations.clone();
    incomplete[0].response_complete = false;
    assert_eq!(resolve(&f.rows, &incomplete, &keys).len(), expected - 1);
    let mut missing = f.rows.clone();
    missing[0].receipt.clear();
    assert_eq!(
        resolve(&missing, &f.observations, &keys).len(),
        expected - 1
    );
    let mut bad = f.rows.clone();
    bad[0].receipt.push('0');
    assert_eq!(resolve(&bad, &f.observations, &keys).len(), expected - 1);
    let mut replay = f.rows.clone();
    let mut copy = replay[0].clone();
    copy.tx.tx_id += 1000;
    let mut obs = f.observations.clone();
    let mut other = obs[0].clone();
    other.tx = copy.tx.clone();
    obs.push(other);
    replay.push(copy);
    assert_eq!(resolve(&replay, &obs, &keys).len(), expected - 1);
    // Recovery runs against the real captured proof, not a newly minted fixture.
    let journal = std::path::Path::new(&std::env::var("WS_PROOF_TEST_FIXTURE").unwrap())
        .with_extension("journal");
    assert!(!journal.exists());
    for (evidence, observation) in f.rows.iter().zip(&f.observations) {
        append_journal(
            &journal,
            &JournalEntry {
                evidence: evidence.clone(),
                observation: observation.clone(),
            },
        )
        .unwrap();
    }
    let recovered = recover_journal(&journal).unwrap();
    let mut durable_rows: Vec<_> = recovered.iter().map(|x| x.evidence.clone()).collect();
    let durable_obs: Vec<_> = recovered.iter().map(|x| x.observation.clone()).collect();
    assert_eq!(resolve(&durable_rows, &durable_obs, &keys).len(), expected);
    // A contradictory receipt arriving after recovery revokes the candidate.
    let mut conflict = f.rows[0].clone();
    conflict.receipt.push('0');
    append_journal(
        &journal,
        &JournalEntry {
            evidence: conflict,
            observation: f.observations[0].clone(),
        },
    )
    .unwrap();
    durable_rows = recover_journal(&journal)
        .unwrap()
        .into_iter()
        .map(|x| x.evidence)
        .collect();
    assert_eq!(
        resolve(&durable_rows, &durable_obs, &keys).len(),
        expected - 1
    );
    std::fs::remove_file(journal).unwrap();
    let mut wrong = f.observations.clone();
    wrong[0].client = "192.0.2.99".into();
    assert_eq!(resolve(&f.rows, &wrong, &keys).len(), expected - 1);
}

/// Test-only append journal. Every acknowledgement follows sync_all. Rebuild the
/// complete decision set after recovery: a late conflict can revoke an earlier
/// candidate. Never use this as an immutable streaming Verified decision.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct JournalEntry {
    evidence: Evidence,
    observation: Observation,
}
fn append_journal(path: &std::path::Path, entry: &JournalEntry) -> std::io::Result<()> {
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    // create_new is atomic and available at the declared Rust 1.88 MSRV.
    // A crash leaves a stale lock: operator recovery required, never auto-unlock.
    let lock_path = path.with_extension("lock");
    let lock = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&lock_path)?;
    struct Lock(std::path::PathBuf, std::fs::File);
    impl Drop for Lock {
        fn drop(&mut self) {
            let _ = self.1.sync_all();
            let _ = std::fs::remove_file(&self.0);
        }
    }
    let _lock = Lock(lock_path, lock);
    if path.exists() {
        use std::os::unix::fs::PermissionsExt;
        let metadata = std::fs::symlink_metadata(path)?;
        if !metadata.is_file() || metadata.permissions().mode() & 0o077 != 0 {
            return Err(std::io::Error::other("unsafe trust journal"));
        }
        recover_journal(path)?;
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(path)?;
    let mut bytes = serde_json::to_vec(entry)?;
    bytes.push(b'\n');
    if file.metadata()?.len() + bytes.len() as u64 > 16 * 1024 * 1024 {
        return Err(std::io::Error::other("trust journal capacity exceeded"));
    }
    file.write_all(&bytes)?;
    file.sync_all()?;
    std::fs::File::open(
        path.parent()
            .ok_or_else(|| std::io::Error::other("journal parent required"))?,
    )?
    .sync_all()
}
fn recover_journal(path: &std::path::Path) -> std::io::Result<Vec<JournalEntry>> {
    if std::fs::metadata(path)?.len() > 16 * 1024 * 1024 {
        return Err(std::io::Error::other("trust journal capacity exceeded"));
    }
    let bytes = std::fs::read(path)?;
    if !bytes.is_empty() && !bytes.ends_with(b"\n") {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "incomplete trust journal",
        ));
    }
    bytes
        .split(|b| *b == b'\n')
        .filter(|line| !line.is_empty())
        .map(|line| serde_json::from_slice(line).map_err(std::io::Error::other))
        .collect()
}

#[test]
fn durable_journal_rejects_partial_or_corrupt_recovery() {
    let path = std::env::temp_dir().join(format!("ws-trust-corrupt-{}", std::process::id()));
    std::fs::write(&path, b"{\"partial\":").unwrap();
    assert!(recover_journal(&path).is_err());
    std::fs::write(&path, b"{}\n").unwrap();
    assert!(recover_journal(&path).is_err());
    std::fs::remove_file(path).unwrap();
}
