//! Manual AWS prevention on a dedicated directly attached ingress.
use crate::*;
use std::{
    collections::BTreeSet,
    os::unix::fs::{FileTypeExt, MetadataExt},
    path::Path,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::UnixStream,
    time::{Duration, timeout},
};

pub const PEER: &str = "10.254.63.2";
pub const SCOPE: &str = "aws-private-ingress";
pub const MIN_MANUAL_TTL: u64 = 60;
pub const MAX_TTL: u64 = 300;
const SOCKET: &str = "/run/websentinel-aws-prevention/actuator.sock";

pub fn valid_manual_ttl(ttl: u64) -> bool {
    (MIN_MANUAL_TTL..=MAX_TTL).contains(&ttl)
}

pub fn configured() -> bool {
    operations::aws_staging()
        && env::var("WS_AWS_SCOPED_PREVENTION").as_deref() == Ok("1")
        && env::var("ENFORCEMENT_MODE").as_deref() == Ok("MANUAL")
        && env::var("AUTO_BLOCK").as_deref() == Ok("false")
}

pub fn available() -> bool {
    configured()
        && Path::new(SOCKET)
            .parent()
            .and_then(|dir| dir.symlink_metadata().ok())
            .is_some_and(|meta| meta.is_dir() && meta.uid() == 0 && meta.mode() & 0o022 == 0)
        && std::fs::symlink_metadata(SOCKET).is_ok_and(|meta| {
            meta.file_type().is_socket() && meta.uid() == 0 && meta.mode() & 0o007 == 0
        })
}

fn operation(action: &str, ip: Option<IpAddr>, ttl: Option<u64>) -> Result<String> {
    match (action, ip, ttl) {
        ("list-json", None, None) => Ok("STATUS\n".into()),
        ("block", Some(ip), Some(ttl))
            if ip.to_string() == PEER && (1..=MAX_TTL).contains(&ttl) =>
        {
            Ok(format!("BLOCK {PEER} {ttl}\n"))
        }
        ("unblock", Some(ip), None) if ip.to_string() == PEER => Ok(format!("UNBLOCK {PEER}\n")),
        _ => bail!("FIREWALL_SCOPE_MISMATCH"),
    }
}

fn read_set(response: &str) -> Result<BTreeSet<String>> {
    let value: serde_json::Value =
        serde_json::from_str(response).context("FIREWALL_SCOPE_UNVERIFIED")?;
    let mut sets = value["nftables"]
        .as_array()
        .context("FIREWALL_SCOPE_UNVERIFIED")?
        .iter()
        .filter_map(|entry| entry.get("set"));
    anyhow::ensure!(
        sets.next().is_some_and(|set| {
            set["family"] == "inet"
                && set["table"] == "ws_aws_prevention"
                && set["name"] == "blocked_ips"
                && set["type"] == "ipv4_addr"
        }) && sets.next().is_none(),
        "FIREWALL_SCOPE_MISMATCH"
    );
    let addresses = firewall::parse_set(response)?;
    anyhow::ensure!(
        addresses.iter().all(|ip| ip == PEER),
        "FIREWALL_SCOPE_MISMATCH"
    );
    Ok(addresses)
}

pub async fn run(action: &str, ip: Option<IpAddr>, ttl: Option<u64>) -> Result<String> {
    anyhow::ensure!(available(), "ACTUATOR_OFFLINE");
    let operation = operation(action, ip, ttl)?;
    timeout(Duration::from_secs(4), async {
        let mut stream = UnixStream::connect(SOCKET)
            .await
            .context("ACTUATOR_OFFLINE")?;
        anyhow::ensure!(stream.peer_cred()?.uid() == 0, "FIREWALL_SCOPE_UNVERIFIED");
        stream.write_all(operation.as_bytes()).await?;
        stream.shutdown().await?;
        let mut response = String::new();
        stream.take(8193).read_to_string(&mut response).await?;
        anyhow::ensure!(response.len() <= 8192, "FIREWALL_SCOPE_UNVERIFIED");
        read_set(&response)?;
        Ok(response)
    })
    .await
    .context("ACTUATOR_TIMEOUT")?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_approved_peer_and_short_lease_are_accepted() {
        let peer = Some(PEER.parse().unwrap());
        assert!(operation("block", peer, Some(MAX_TTL)).is_ok());
        assert!(operation("block", peer, Some(MAX_TTL + 1)).is_err());
        assert!(!valid_manual_ttl(59));
        assert!(valid_manual_ttl(60));
        assert!(valid_manual_ttl(300));
        assert!(!valid_manual_ttl(301));
        // Workers send the remaining lease, which can be less than one minute.
        assert!(operation("block", peer, Some(1)).is_ok());
        assert!(operation("block", Some("127.0.0.1".parse().unwrap()), Some(3)).is_err());
        assert!(operation("unblock", Some("10.254.63.1".parse().unwrap()), None).is_err());
        for table in ["r56_prevention", "ws_aws_prevention"] {
            let snapshot = serde_json::json!({"nftables":[{"set":{"family":"inet", "table":table,"name":"blocked_ips","type":"ipv4_addr","elem":[PEER]}}]});
            assert_eq!(
                read_set(&snapshot.to_string()).is_ok(),
                table == "ws_aws_prevention"
            );
        }
    }
}
