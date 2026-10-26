//! Fail-closed enforcement policy. Packet capture/listening and enforcement scope are separate.
use crate::*;
use std::collections::BTreeSet;

#[derive(Clone, Debug)]
pub struct Subnet {
    address: u32,
    mask: u32,
}
impl Subnet {
    pub fn parse(raw: &str) -> Result<Self> {
        let (ip, prefix) = raw
            .trim()
            .split_once('/')
            .context("Enforcement networks require IPv4 CIDR notation")?;
        let ip = ip
            .parse::<std::net::Ipv4Addr>()
            .context("Invalid enforcement network")?;
        let prefix: u32 = prefix.parse()?;
        anyhow::ensure!(prefix <= 32, "Invalid CIDR prefix");
        let mask = if prefix == 0 {
            0
        } else {
            u32::MAX << (32 - prefix)
        };
        Ok(Self {
            address: u32::from(ip) & mask,
            mask,
        })
    }
    fn contains(&self, ip: std::net::Ipv4Addr) -> bool {
        u32::from(ip) & self.mask == self.address
    }
}
#[derive(Clone, Debug)]
pub struct Safety {
    pub allowed: Vec<Subnet>,
    pub protected: BTreeSet<IpAddr>,
    pub discovery_ok: bool,
    pub discover_before_apply: bool,
    pub mode: String,
}
impl Safety {
    #[cfg(test)]
    pub fn test() -> Self {
        Self {
            allowed: vec![
                Subnet::parse("192.168.0.0/16").unwrap(),
                Subnet::parse("10.0.0.0/8").unwrap(),
                Subnet::parse("172.16.0.0/12").unwrap(),
            ],
            protected: ["127.0.0.1".parse().unwrap(), "::1".parse().unwrap()].into(),
            discovery_ok: true,
            discover_before_apply: false,
            mode: "ENFORCE".into(),
        }
    }
    pub async fn from_env() -> Result<Self> {
        let allowed = env::var("ENFORCE_ALLOWED_SUBNETS")
            .unwrap_or("192.168.0.0/16,10.0.0.0/8,172.16.0.0/12".into())
            .split(',')
            .map(Subnet::parse)
            .collect::<Result<Vec<_>>>()?;
        let mode = env::var("ENFORCEMENT_MODE").unwrap_or("OFF".into());
        anyhow::ensure!(
            matches!(mode.as_str(), "OFF" | "MANUAL" | "ENFORCE"),
            "ENFORCEMENT_MODE must be OFF/MANUAL/ENFORCE"
        );
        let mut protected: BTreeSet<IpAddr> = [
            "127.0.0.1".parse()?,
            "::1".parse()?,
            env::var("WEB_SERVER_IP")
                .unwrap_or("192.168.20.10".into())
                .parse()?,
            env::var("PROTECTED_GATEWAY_IP")
                .unwrap_or("192.168.20.1".into())
                .parse()?,
        ]
        .into();
        let discovery = discover().await;
        if let Ok(ips) = &discovery {
            protected.extend(ips);
        } else {
            warn!(
                "Host/gateway discovery failed; BLOCK enforcement disabled until discovery recovers"
            );
        }
        Ok(Self {
            allowed,
            protected,
            discovery_ok: discovery.is_ok(),
            discover_before_apply: true,
            mode,
        })
    }
    pub fn parse_host(raw: &str) -> Result<IpAddr> {
        let value = raw.trim();
        let ip = if let Some((ip, prefix)) = value.split_once('/') {
            anyhow::ensure!(prefix == "32", "Only individual IPv4 hosts may be enforced");
            ip
        } else {
            value
        };
        let ip: IpAddr = ip.parse().context("Invalid host IP")?;
        anyhow::ensure!(
            ip.is_ipv4(),
            "Enforcement currently supports IPv4 only; IPv6 hosts are never blocked"
        );
        Ok(ip)
    }
    pub fn validate(&self, raw: &str) -> Result<IpAddr> {
        let ip = Self::parse_host(raw)?;
        anyhow::ensure!(
            self.discovery_ok,
            "Protected host/gateway addresses are unknown; refusing BLOCK"
        );
        let IpAddr::V4(v4) = ip else { unreachable!() };
        anyhow::ensure!(
            !v4.is_loopback()
                && !v4.is_unspecified()
                && !v4.is_multicast()
                && !v4.is_broadcast()
                && !v4.is_link_local(),
            "Protected or non-unicast target"
        );
        anyhow::ensure!(
            self.allowed.iter().any(|n| n.contains(v4)),
            "Target outside ENFORCE_ALLOWED_SUBNETS"
        );
        anyhow::ensure!(
            !self.protected.contains(&ip),
            "Host, gateway or upstream IP is protected"
        );
        Ok(ip)
    }
}
async fn ip_json(args: &[&str]) -> Result<serde_json::Value> {
    let mut command = tokio::process::Command::new("ip");
    command.args(args).kill_on_drop(true);
    let output =
        tokio::time::timeout(std::time::Duration::from_secs(2), command.output()).await??;
    anyhow::ensure!(output.status.success(), "IP discovery command failed");
    Ok(serde_json::from_slice(&output.stdout)?)
}
pub async fn discover() -> Result<BTreeSet<IpAddr>> {
    let addresses = ip_json(&["-j", "address", "show"]).await?;
    let gateways = ip_json(&["-j", "route", "show", "default"]).await?;
    let gateways6 = ip_json(&["-6", "-j", "route", "show", "default"]).await?;
    let mut protected = BTreeSet::new();
    for interface in addresses.as_array().context("Malformed IP discovery")? {
        for address in interface["addr_info"]
            .as_array()
            .context("Missing interface addresses")?
        {
            if let Some(local) = address["local"].as_str() {
                protected.insert(local.parse()?);
            }
        }
    }
    for routes in [&gateways, &gateways6] {
        for route in routes.as_array().context("Malformed gateway discovery")? {
            if let Some(ip) = route["gateway"].as_str() {
                protected.insert(ip.parse()?);
            }
            if let Some(hops) = route["nexthops"].as_array() {
                for hop in hops {
                    if let Some(ip) = hop["gateway"].as_str() {
                        protected.insert(ip.parse()?);
                    }
                }
            }
        }
    }
    anyhow::ensure!(!protected.is_empty(), "Empty address discovery");
    Ok(protected)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_scope_and_safety_are_separate() {
        let mut safety = Safety::test();
        safety.protected.insert("192.168.1.1".parse().unwrap());
        safety.protected.insert("192.168.20.10".parse().unwrap());
        for ip in ["192.168.2.5", "10.2.3.4", "172.31.1.3", "192.168.10.10/32"] {
            assert!(safety.validate(ip).is_ok(), "{ip}");
        }
        for ip in [
            "192.168.1.1",
            "192.168.20.10",
            "127.0.0.1",
            "::1",
            "8.8.8.8",
            "172.32.1.3",
            "0.0.0.0",
            "169.254.1.2",
            "192.168.10.10/24",
        ] {
            assert!(safety.validate(ip).is_err(), "{ip}");
        }
        safety.discovery_ok = false;
        assert!(safety.validate("192.168.1.55").is_err());
        assert!(Subnet::parse("192.168.0.0/33").is_err());
        assert!(Subnet::parse("localhost/32").is_err());
    }
    #[tokio::test]
    async fn native_discovery_includes_loopback_when_available() {
        if let Ok(ips) = discover().await {
            assert!(ips.contains(&"127.0.0.1".parse().unwrap()));
        }
    }
}
