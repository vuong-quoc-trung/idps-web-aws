//! Attribution is local configuration plus transaction-local EVE evidence, never an XFF guess.
use crate::*;
use serde_json::Value;

/// EVE HTTP transaction records may omit app_proto (Suricata 8.0.3).
/// Native alerts still require explicit HTTP protocol classification.
pub fn http_context(v: &Value) -> bool {
    if v["proto"] != "TCP"
        || v["flow_id"].as_u64().is_none()
        || v["tx_id"].as_u64().is_none()
        || !v.get("direction").is_none_or(|d| d == "to_server")
    {
        return false;
    }
    match v["event_type"].as_str() {
        Some("alert") => v["app_proto"] == "http",
        Some("http") => {
            v.get("app_proto").is_none_or(|p| p == "http")
                && v["http"]["http_method"].as_str().is_some_and(|m| {
                    !m.is_empty() && m.bytes().all(|c| c.is_ascii_uppercase() || c == b'-')
                })
        }
        _ => false,
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Origin {
    pub network_src_ip: Option<IpAddr>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub interface: Option<String>,
    pub client_ip_verified: bool,
    pub post_proxy: bool,
    pub tx_id: Option<u64>,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub generation_host: bool,
    pub post_proxy: bool,
    pub trusted_edge: bool,
    pub proxy_ip: IpAddr,
    pub server_ip: IpAddr,
    pub interface: String,
    pub server_port: u64,
}
impl Default for Policy {
    fn default() -> Self {
        Self {
            generation_host: false,
            post_proxy: false,
            trusted_edge: false,
            proxy_ip: "192.168.20.1".parse().unwrap(),
            server_ip: "192.168.20.10".parse().unwrap(),
            interface: "vmnet3".into(),
            server_port: 80,
        }
    }
}
impl Policy {
    pub fn from_env() -> Result<Self> {
        let mut p = Self::default();
        if let Ok(v) = env::var("SURICATA_EVE_GENERATION_HOST") {
            p.generation_host = v.parse()?;
        }
        if let Ok(v) = env::var("SURICATA_CAPTURE_MODE") {
            anyhow::ensure!(
                matches!(v.as_str(), "pre-proxy" | "post-proxy"),
                "Invalid Suricata capture mode"
            );
            p.post_proxy = v == "post-proxy";
        }
        if let Ok(v) = env::var("SURICATA_TRUSTED_EDGE_CONFIRMED") {
            p.trusted_edge = v.parse()?;
        }
        if let Ok(v) = env::var("SURICATA_PROXY_IP") {
            p.proxy_ip = v.parse()?;
        }
        if let Ok(v) = env::var("SURICATA_WEB_IP") {
            p.server_ip = v.parse()?;
        }
        if let Ok(v) = env::var("SURICATA_POST_PROXY_INTERFACE") {
            p.interface = v;
        }
        if let Ok(v) = env::var("SURICATA_WEB_PORT") {
            p.server_port = v.parse()?;
        }
        anyhow::ensure!(
            !p.interface.is_empty()
                && (1..=65535).contains(&p.server_port)
                && p.proxy_ip != p.server_ip,
            "Invalid Suricata trust boundary"
        );
        if p.post_proxy {
            anyhow::ensure!(
                env::var("AUTO_BLOCK").unwrap_or_else(|_| "false".into()) == "false"
                    && (env::var("ENFORCEMENT_MODE").unwrap_or_else(|_| "OFF".into()) == "OFF"
                        || aws_firewall::configured()),
                "Post-proxy capture requires OFF or the dedicated AWS manual scope with AUTO_BLOCK=false"
            );
        }
        Ok(p)
    }
    pub fn local_egress(&self) -> bool {
        self.proxy_ip.is_loopback() || self.server_ip.is_loopback() || self.interface == "lo"
    }
    pub fn resolve(&self, v: &Value, network: Option<IpAddr>) -> (Option<IpAddr>, Origin) {
        // Also suppress the known proxy when a post-proxy file is accidentally read in pre mode.
        let post = self.post_proxy
            || network == Some(self.proxy_ip)
            || network.is_some_and(|ip| ip.is_loopback());
        let mut o = Origin {
            network_src_ip: network,
            interface: v["in_iface"]
                .as_str()
                .filter(|name| {
                    (1..=15).contains(&name.len())
                        && name
                            .bytes()
                            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
                })
                .map(str::to_owned),
            client_ip_verified: false,
            post_proxy: post,
            tx_id: v["tx_id"].as_u64(),
        };
        if !post {
            // This direct identity is limited to the private, capability-bound test build.
            #[cfg(feature = "isolated-c2")]
            if crate::prevention::execution_enabled()
                && self.interface == "r56-edge"
                && self.server_ip.to_string() == "10.254.56.1"
                && self.server_port == 18456
                && network.is_some_and(|ip| ip.to_string() == crate::firewall::LAB_PEER)
                && v["in_iface"] == "r56-edge"
                && v["dest_ip"] == "10.254.56.1"
                && v["dest_port"] == 18456
                && v["proto"] == "TCP"
                && v["event_type"] == "alert"
                && v["flow_id"].as_u64().is_some()
                && o.tx_id.is_some()
            {
                o.client_ip_verified = true;
            }
            return (network, o);
        } // Legacy: observed source, NOT verified XFF.
        let kind = v["event_type"].as_str().unwrap_or("");
        let xff = match kind {
            "alert" => &v["alert"]["xff"],
            "http" => &v["http"]["xff"],
            _ => &Value::Null,
        };
        let client = xff.as_str().and_then(|s| s.parse::<IpAddr>().ok());
        // A current nft snapshot cannot prove the trust state when a delayed EVE
        // event was generated. Never enable loopback attribution with a static
        // flag, even after a policy has been restored. Preserve native alerts.
        let local_boundary = self.local_egress();
        let valid = !local_boundary && self.post_proxy && self.trusted_edge && network == Some(self.proxy_ip)
            && v["dest_ip"].as_str().and_then(|s|s.parse::<IpAddr>().ok()) == Some(self.server_ip)
            && v["dest_port"].as_u64() == Some(self.server_port)
            && http_context(v)
            && v["in_iface"].as_str() == Some(self.interface.as_str())
            && o.tx_id.is_some() && v["flow_id"].as_u64().is_some()
            && client.is_some_and(|ip| !ip.is_unspecified() && !ip.is_multicast() && !ip.is_loopback() && ip != self.proxy_ip && ip != self.server_ip)
            // Reject contradictory extra-data rather than choosing one representation.
            && v.get("xff").is_none_or(|x| x == xff)
            && (kind != "alert" || v["http"].get("xff").is_none_or(|x| x == xff));
        o.client_ip_verified = valid;
        (if valid { client } else { None }, o)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    pub fn policy() -> Policy {
        Policy {
            post_proxy: true,
            trusted_edge: true,
            ..Default::default()
        }
    }
    pub fn eve(tx: u64, client: &str) -> Value {
        json!({"timestamp":"2026-11-15T00:00:00Z","event_type":"alert","src_ip":"192.168.20.1","dest_ip":"192.168.20.10","src_port":40000,"dest_port":80,"proto":"TCP","app_proto":"http","in_iface":"vmnet3","flow_id":123,"tx_id":tx,"alert":{"signature_id":1000002,"signature":"SQLi","severity":1,"xff":client},"http":{"url":"/api/probe","http_method":"GET"}})
    }
    #[test]
    fn loopback_is_never_a_client_even_with_legacy_policy() {
        for address in ["127.77.0.1", "127.77.0.2", "::1"] {
            let network = Some(address.parse().unwrap());
            let (client, origin) = Policy::default().resolve(&json!({}), network);
            assert_eq!(client, None);
            assert_eq!(origin.network_src_ip, network);
            assert!(!origin.client_ip_verified);
            assert!(origin.post_proxy);
        }
    }

    #[test]
    fn keepalive_reverse_order_and_replay_are_transaction_local() {
        for tx in [3, 0, 2, 1, 0] {
            let client = format!("192.168.10.{}", 10 + tx);
            let parsed =
                events::parse_with_origin("SURICATA", &eve(tx, &client).to_string(), &policy())
                    .unwrap();
            assert_eq!(parsed.canonical.client_ip.unwrap().to_string(), client);
            let o = parsed.canonical.suricata_origin.unwrap();
            assert!(o.client_ip_verified);
            assert_eq!(o.tx_id, Some(tx));
            assert_eq!(o.network_src_ip.unwrap().to_string(), "192.168.20.1");
        }
    }
    #[test]
    fn missing_malformed_and_conflicting_evidence_stays_unknown() {
        let p = policy();
        for field in ["tx_id", "flow_id", "in_iface", "app_proto", "dest_port"] {
            let mut v = eve(0, "192.168.10.10");
            v.as_object_mut().unwrap().remove(field);
            assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None, "{field}");
        }
        for xff in [
            "",
            "unknown",
            "192.168.10.10, 1.2.3.4",
            " 192.168.10.10",
            "127.0.0.1",
            "192.168.20.1",
            "999.1.1.1",
        ] {
            assert_eq!(p.resolve(&eve(0, xff), Some(p.proxy_ip)).0, None);
        }
        let mut v = eve(0, "192.168.10.10");
        v["http"]["xff"] = json!("192.168.10.11");
        assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None);
        v["alert"].as_object_mut().unwrap().remove("xff");
        assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None); // Never borrow from separate HTTP.
    }
    #[test]
    fn forged_xff_wrong_boundary_and_default_config_fail_closed() {
        let mut p = policy();
        let mut v = eve(0, "192.168.10.10");
        assert_eq!(
            p.resolve(&v, Some("192.168.10.99".parse().unwrap())).0,
            None
        );
        for (field, value) in [
            ("in_iface", "vmnet2"),
            ("dest_ip", "192.168.20.11"),
            ("proto", "UDP"),
        ] {
            let mut altered = v.clone();
            altered[field] = json!(value);
            assert_eq!(p.resolve(&altered, Some(p.proxy_ip)).0, None);
        }
        p.trusted_edge = false;
        assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None);
        assert_eq!(Policy::default().resolve(&v, Some(p.proxy_ip)).0, None);
        v["src_ip"] = json!("192.168.10.10");
        let legacy = events::parse("SURICATA", &v.to_string()).unwrap().canonical;
        assert_eq!(legacy.client_ip.unwrap().to_string(), "192.168.10.10");
        assert!(!legacy.suricata_origin.unwrap().client_ip_verified);
    }
    #[test]
    fn captured_local_egress_eve_remains_unverified_without_trust() {
        let p = Policy {
            generation_host: false,
            post_proxy: true,
            trusted_edge: false,
            proxy_ip: "127.77.0.1".parse().unwrap(),
            server_ip: "127.77.0.2".parse().unwrap(),
            server_port: 18080,
            interface: "lo".into(),
        };
        let mut alerts = 0;
        let mut http = 0;
        for line in include_str!("../tests/fixtures/local-egress-capture/eve.jsonl").lines() {
            let raw: Value = serde_json::from_str(line).unwrap();
            let parsed = events::parse_with_origin("SURICATA", line, &p).unwrap();
            assert!(parsed.canonical.client_ip.is_none());
            let origin = parsed.canonical.suricata_origin.unwrap();
            assert!(!origin.client_ip_verified);
            assert_eq!(origin.network_src_ip, Some(p.proxy_ip));
            assert_eq!(origin.tx_id, raw["tx_id"].as_u64());
            assert_eq!(parsed.canonical.dest_ip, Some(p.server_ip));
            assert!(parsed.canonical.flow_id.is_some());
            if raw["event_type"] == "alert" {
                alerts += 1;
                assert_eq!(
                    parsed.native_alert.unwrap().sid.map(u64::from),
                    raw["alert"]["signature_id"].as_u64()
                );
            } else {
                http += 1;
                // Actual 8.0.3 HTTP records lack app_proto; do not silently synthesize it.
                assert!(raw.get("app_proto").is_none());
                assert!(parsed.native_alert.is_none());
            }
            assert!(parsed.detections.is_empty());
        }
        assert_eq!((alerts, http), (4, 5));
    }

    #[test]
    fn local_egress_without_proven_trust_keeps_identity_unknown() {
        // Synthetic EVE: parser test only, not evidence of live AF_PACKET capture.
        let p = Policy {
            generation_host: false,
            post_proxy: true,
            trusted_edge: false,
            proxy_ip: "127.77.0.1".parse().unwrap(),
            server_ip: "127.77.0.2".parse().unwrap(),
            server_port: 18080,
            interface: "lo".into(),
        };
        for claimed_client in ["192.168.10.10", "192.168.10.99"] {
            let mut v = eve(0, claimed_client);
            v["src_ip"] = json!("127.77.0.1");
            v["dest_ip"] = json!("127.77.0.2");
            v["dest_port"] = json!(18080);
            v["in_iface"] = json!("lo");
            v["http"]["url"] = json!("/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E");
            for kind in ["alert", "http", "fileinfo"] {
                v["event_type"] = json!(kind);
                v["http"]["xff"] = json!(claimed_client);
                let parsed = events::parse_with_origin("SURICATA", &v.to_string(), &p).unwrap();
                assert!(parsed.canonical.client_ip.is_none());
                let origin = parsed.canonical.suricata_origin.unwrap();
                assert!(!origin.client_ip_verified);
                assert_eq!(origin.network_src_ip, Some(p.proxy_ip));
                assert_eq!(origin.tx_id, Some(0));
                assert_eq!(parsed.native_alert.is_some(), kind == "alert");
                if kind != "http" {
                    assert!(parsed.detections.is_empty());
                }
            }
        }
    }

    #[test]
    fn http_extra_data_and_non_http_alerts() {
        let p = policy();
        let mut v = eve(0, "192.168.10.10");
        v["event_type"] = json!("http");
        v["http"]["xff"] = json!("192.168.10.11");
        assert_eq!(
            p.resolve(&v, Some(p.proxy_ip)).0.unwrap().to_string(),
            "192.168.10.11"
        );
        v["event_type"] = json!("flow");
        assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None);
    }
    #[test]
    fn local_static_trust_cannot_verify_even_after_policy_restore() {
        let mut p = policy();
        p.proxy_ip = "127.77.0.1".parse().unwrap();
        p.server_ip = "127.77.0.2".parse().unwrap();
        p.interface = "lo".into();
        p.server_port = 18080;
        let mut v = eve(0, "192.168.10.10");
        v["src_ip"] = json!("127.77.0.1");
        v["dest_ip"] = json!("127.77.0.2");
        v["dest_port"] = json!(18080);
        v["in_iface"] = json!("lo");
        assert!(p.trusted_edge);
        assert_eq!(p.resolve(&v, Some(p.proxy_ip)).0, None);
    }
    #[test]
    fn http_without_protocol_is_type_scoped() {
        let mut v = eve(0, "192.168.10.10");
        v.as_object_mut().unwrap().remove("app_proto");
        assert!(!http_context(&v));
        v["event_type"] = json!("http");
        assert!(http_context(&v));
        v["app_proto"] = json!("tls");
        assert!(!http_context(&v));
        v.as_object_mut().unwrap().remove("app_proto");
        v["http"]["http_method"] = json!("");
        assert!(!http_context(&v));
    }
}
