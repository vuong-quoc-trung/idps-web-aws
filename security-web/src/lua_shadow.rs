//! Passive metadata journal. Never verifies HMAC or changes client IP/alerts.
use crate::*;
use sha2::{Digest, Sha256};

struct Record {
    generation: String,
    flow: String,
    tx: i64,
    request: String,
    digest: String,
    proof: bool,
    receipt: bool,
}
fn parse(raw: &[u8]) -> Result<Record> {
    let line = std::str::from_utf8(raw)?.trim_end_matches(['\r', '\n']);
    let f: Vec<_> = line.split('\t').collect();
    anyhow::ensure!(
        f.len() == 9
            && f.iter()
                .all(|s| s.len() <= 4096 && !s.chars().any(char::is_control)),
        "Invalid Lua shape"
    );
    let flow = f[0].parse::<u64>()?;
    let tx = f[1].parse::<i64>()?;
    anyhow::ensure!((0..=9007199254740991).contains(&tx), "Invalid transaction");
    anyhow::ensure!(
        f[8].len() == 32
            && f[8]
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "Invalid generation"
    );
    anyhow::ensure!(
        events::valid_request_id(f[5]) && !f[5].is_empty(),
        "Invalid request ID"
    );
    let _: IpAddr = f[4].parse()?;
    anyhow::ensure!(matches!(f[6], "http" | "https"), "Invalid scheme");
    Ok(Record {
        generation: f[8].into(),
        flow: flow.to_string(),
        tx,
        request: f[5].into(),
        digest: format!("{:x}", Sha256::digest(line.as_bytes())),
        proof: !f[2].is_empty(),
        receipt: !f[3].is_empty(),
    })
}
pub async fn ingest(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    key: &str,
    raw: &[u8],
) -> Result<()> {
    let r = match parse(raw) {
        Ok(r) => r,
        Err(_) => {
            sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,'SURICATA_LUA','invalid Lua metadata; raw content suppressed') ON CONFLICT DO NOTHING")
                .bind(key).execute(&mut **tx).await?;
            return Ok(());
        }
    };
    let new = sqlx::query(
        "INSERT INTO suricata_lua_seen(physical_key) VALUES($1) ON CONFLICT DO NOTHING",
    )
    .bind(key)
    .execute(&mut **tx)
    .await?
    .rows_affected();
    if new == 0 {
        return Ok(());
    }
    sqlx::query("INSERT INTO suricata_lua_shadow(generation,flow_id,tx_id,request_id,record_hash,proof_present,receipt_present) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(generation,flow_id,tx_id) DO UPDATE SET mismatched=suricata_lua_shadow.mismatched OR suricata_lua_shadow.record_hash<>EXCLUDED.record_hash, duplicate_count=suricata_lua_shadow.duplicate_count+1,last_seen=now()")
        .bind(r.generation).bind(r.flow).bind(r.tx).bind(r.request).bind(r.digest).bind(r.proof).bind(r.receipt)
        .execute(&mut **tx).await?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn row() -> String {
        format!(
            "123\t0\tproof\treceipt\t192.0.2.1\trid\thttps\tlab\t{}\n",
            "a".repeat(32)
        )
    }
    #[test]
    fn parses_and_hashes_without_preserving_proof() {
        let r = parse(row().as_bytes()).unwrap();
        assert!(r.proof && r.receipt);
        assert_eq!(r.flow, "123");
        assert_eq!(r.digest.len(), 64);
    }
    #[test]
    fn missing_receipt_is_not_invented() {
        assert!(
            !parse(row().replace("\treceipt\t", "\t\t").as_bytes())
                .unwrap()
                .receipt
        );
    }
    #[test]
    fn rejects_legacy_invalid_generation_and_tx() {
        for row in [
            "x".into(),
            row().replace(&"a".repeat(32), "bad"),
            row().replace("123\t0", "123\t-1"),
        ] {
            assert!(parse(row.as_bytes()).is_err());
        }
    }
}
