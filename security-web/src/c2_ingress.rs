//! Bounded ingress canary. The normal serving build has no actuator capability.
use crate::*;
use serde_json::{Value, json};
use std::{fs, os::unix::fs::MetadataExt, path::Path};

pub const MAX_TTL: u64 = 6;

#[derive(Clone, Copy)]
pub enum Source {
    Rule,
    Hybrid,
}

impl Source {
    pub fn parse(source: &str) -> Option<Self> {
        match source {
            "CANARY_RULE" => Some(Self::Rule),
            "CANARY_HYBRID" => Some(Self::Hybrid),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Rule => "CANARY_RULE",
            Self::Hybrid => "CANARY_HYBRID",
        }
    }
}

pub fn enabled() -> bool {
    if env::var("WS_C2_INGRESS_CANARY").as_deref() != Ok("1") || !prevention::execution_enabled() {
        return false;
    }
    let approval = Path::new("/run/websentinel-r56-lab/ingress-canary");
    fs::symlink_metadata(approval)
        .is_ok_and(|m| m.is_file() && m.uid() == 0 && m.mode() & 0o022 == 0 && m.len() == 7)
        && fs::read(approval).is_ok_and(|value| value == b"R61-v1\n")
}

fn request_id(rid: &str) -> bool {
    rid.len() == 32
        && rid
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Proof {
    pub request_id: String,
    pub ip: IpAddr,
    pub path: String,
    pub status: i32,
    pub flow_id: u64,
    pub tx_id: u64,
    pub sid: u32,
    pub application_denied: bool,
}

impl Proof {
    pub fn source(&self) -> Option<Source> {
        match (
            self.path.as_str(),
            self.status,
            self.sid,
            self.application_denied,
        ) {
            ("/health", 204, 161001, false) => Some(Source::Rule),
            ("/api/profile", 403, 161002, true) => Some(Source::Hybrid),
            _ => None,
        }
    }

    fn matches(&self, rid: &str, ip: &str, uri: &str, status: i32) -> bool {
        request_id(rid)
            && self.request_id == rid
            && ip == firewall::LAB_PEER
            && self.ip.to_string() == ip
            && self.path == uri
            && self.status == status
            && self.flow_id != 0
            && self.source().is_some()
    }

    pub fn evidence(&self) -> Value {
        json!({"scope":"AWS_ISOLATED_INGRESS_CANARY", "request_id":self.request_id,
               "peer":self.ip, "suricata_flow":self.flow_id, "suricata_tx":self.tx_id,
               "sid":self.sid, "application_denied":self.application_denied})
    }
}

pub async fn verified(state: &AppState, rid: &str) -> Result<Option<Proof>> {
    if !enabled() || !request_id(rid) {
        return Ok(None);
    }
    // Require a single NGINX observation even when a conflicting row has a
    // different path/IP. Request ID is a lookup key and provides no authority.
    let observed = sqlx::query_as::<_, (Option<String>, Option<String>, Option<i32>, Option<String>)>(
        "SELECT host(client_ip),uri_path,status_code,http_method FROM normalized_events
         WHERE request_id=$1 AND source='NGINX' AND occurred_at BETWEEN now()-interval '10 seconds' AND now()
         LIMIT 2",
    )
    .bind(rid)
    .fetch_all(&state.pool)
    .await?;
    let [(Some(ip), Some(path), Some(status), Some(method))] = observed.as_slice() else {
        return Ok(None);
    };
    if method != "GET" || !matches!(path.as_str(), "/health" | "/api/profile") {
        return Ok(None);
    }
    if firewall::validate(state, ip).is_err() {
        return Ok(None);
    }
    let reply = firewall::lab_request(format!("PROOF {rid}\n"), 1024).await?;
    if reply.is_empty() {
        return Ok(None);
    }
    let proof: Proof = serde_json::from_str(&reply)?;
    Ok(proof.matches(rid, ip, path, *status).then_some(proof))
}

pub async fn apply(source: Source, rid: &str, ip: IpAddr, ttl: Option<u64>) -> Result<()> {
    anyhow::ensure!(
        enabled() && request_id(rid) && ip.to_string() == firewall::LAB_PEER,
        "C2_CANARY_SCOPE_UNVERIFIED"
    );
    let ttl = ttl
        .filter(|v| (1..=MAX_TTL).contains(v))
        .context("C2_CANARY_DEADLINE")?;
    let response =
        firewall::lab_request(format!("APPLY {} {rid} {ttl}\n", source.as_str()), 8192).await?;
    anyhow::ensure!(
        firewall::lab_set(&response)?.contains(&ip.to_string()),
        "C2_CANARY_READBACK_MISMATCH"
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rule_and_application_evidence_are_bound_to_one_request() {
        let rid = "abcd".repeat(8);
        let mut proof = Proof {
            request_id: rid.clone(),
            ip: firewall::LAB_PEER.parse().unwrap(),
            path: "/api/profile".into(),
            status: 403,
            flow_id: 22,
            tx_id: 0,
            sid: 161002,
            application_denied: true,
        };
        for path in ["/health", "/api/profile"] {
            assert_eq!(detection::redact_target(path).0, path);
        }
        assert!(proof.matches(&rid, firewall::LAB_PEER, "/api/profile", 403));
        assert!(!proof.matches(&rid, "127.0.0.1", "/api/profile", 403));
        assert!(!proof.matches(&"0".repeat(32), firewall::LAB_PEER, "/api/profile", 403));
        assert!(!proof.matches(&rid, firewall::LAB_PEER, "/api/profile", 204));
        proof.application_denied = false;
        assert!(proof.source().is_none());
        proof.path = "/health".into();
        proof.status = 204;
        proof.sid = 161001;
        assert!(matches!(proof.source(), Some(Source::Rule)));
        proof.flow_id = 0;
        assert!(!proof.matches(&rid, firewall::LAB_PEER, "/health", 204));
    }
}
