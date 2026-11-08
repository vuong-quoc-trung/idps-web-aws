//! Opt-in research receiver, built only with `cargo build --example body_syntax_lab`.
//! Separate schema/API/journal. No normalizer, model, alert, rule or policy calls.
use anyhow::{Context, Result, ensure};
use axum::{
    Json, Router,
    extract::State,
    http::{HeaderMap, StatusCode},
    routing::get,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::{PgPool, postgres::PgPoolOptions};
use std::{
    env,
    fs::{self, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    net::SocketAddr,
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    time::Duration,
};

const SPEC: &str = include_str!("../../ai-training/configs/research/http-body-syntax-v1.json");

#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    schema_version: String,
    contract_sha256: String,
    request_id: String,
    features: Vec<u8>,
}

fn decode(raw: &[u8]) -> Result<Event> {
    ensure!(raw.len() <= 4096, "event too large");
    let e: Event = serde_json::from_slice(raw)?;
    let spec: Value = serde_json::from_str(SPEC)?;
    ensure!(
        e.schema_version == spec["version"] && e.contract_sha256 == spec["contract_sha256"],
        "version mismatch"
    );
    ensure!(
        e.request_id.len() == 32
            && e.request_id
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
        "identity mismatch"
    );
    let caps = spec["maxima"].as_array().context("contract maxima")?;
    ensure!(
        e.features.len() == caps.len() && caps.len() == 46,
        "dimension mismatch"
    );
    ensure!(
        e.features
            .iter()
            .zip(caps)
            .all(|(x, cap)| u64::from(*x) <= cap.as_u64().unwrap()),
        "range mismatch"
    );
    ensure!(
        e.features[..11].iter().map(|x| *x as u32).sum::<u32>() == 1
            && e.features[11..15].iter().map(|x| *x as u32).sum::<u32>() == 1,
        "state mismatch"
    );
    ensure!(
        e.features[2] == 1 || e.features[15..].iter().all(|x| *x == 0),
        "unavailable content"
    );
    Ok(e)
}

#[derive(Clone)]
struct Lab {
    pool: PgPool,
    token: Arc<String>,
    accepted: Arc<AtomicU64>,
    rejected: Arc<AtomicU64>,
}

async fn observations(
    State(lab): State<Lab>,
    headers: HeaderMap,
) -> Result<Json<Value>, StatusCode> {
    if headers.get("authorization").and_then(|x| x.to_str().ok())
        != Some(&format!("Bearer {}", lab.token))
    {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let items: Vec<Value> = sqlx::query_scalar("SELECT event FROM idps_body_syntax_lab.observations ORDER BY received_at DESC,request_id LIMIT 128")
        .fetch_all(&lab.pool).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(
        json!({"scope":"ISOLATED_RESEARCH_ONLY","enforcement":"DISCONNECTED",
        "accepted":lab.accepted.load(Ordering::Relaxed),"rejected":lab.rejected.load(Ordering::Relaxed),"items":items}),
    ))
}

async fn consume(lab: Lab, input: PathBuf, journal: PathBuf) -> Result<()> {
    let mut offset = 0;
    loop {
        tokio::time::sleep(Duration::from_millis(50)).await;
        if !input.exists() {
            continue;
        }
        ensure!(
            !fs::symlink_metadata(&input)?.file_type().is_symlink(),
            "input symlink rejected"
        );
        let mut file = fs::File::open(&input)?;
        ensure!(file.metadata()?.len() >= offset, "input truncated");
        file.seek(SeekFrom::Start(offset))?;
        let mut bytes = Vec::new();
        file.take(1_048_577).read_to_end(&mut bytes)?;
        ensure!(bytes.len() <= 1_048_576, "input backlog exceeded");
        for line in bytes.split_inclusive(|x| *x == b'\n') {
            if line.last() != Some(&b'\n') {
                break;
            }
            offset += line.len() as u64;
            let event = match decode(line) {
                Ok(e) => e,
                Err(_) => {
                    lab.rejected.fetch_add(1, Ordering::Relaxed);
                    continue;
                }
            };
            ensure!(
                lab.accepted.load(Ordering::Relaxed) < 512,
                "research event budget exhausted"
            );
            let safe = serde_json::to_value(&event)?;
            let n = sqlx::query("INSERT INTO idps_body_syntax_lab.observations(request_id,event) VALUES($1,$2) ON CONFLICT DO NOTHING")
                .bind(&event.request_id).bind(&safe).execute(&lab.pool).await?.rows_affected();
            if n == 0 {
                let prior: Value = sqlx::query_scalar(
                    "SELECT event FROM idps_body_syntax_lab.observations WHERE request_id=$1",
                )
                .bind(&event.request_id)
                .fetch_one(&lab.pool)
                .await?;
                ensure!(prior == safe, "conflicting request identity");
                continue;
            }
            let mut sink = OpenOptions::new()
                .create(true)
                .append(true)
                .mode(0o600)
                .open(&journal)?;
            serde_json::to_writer(&mut sink, &event)?;
            sink.write_all(b"\n")?;
            lab.accepted.fetch_add(1, Ordering::Relaxed);
        }
    }
}

async fn run() -> Result<()> {
    ensure!(
        env::var("IDPS_BODY_LAB_OPT_IN").as_deref() == Ok("YES"),
        "explicit lab opt-in required"
    );
    let address: SocketAddr = env::var("IDPS_BODY_LAB_ADDR")?.parse()?;
    ensure!(address.ip().is_loopback(), "loopback only");
    let token = env::var("IDPS_BODY_LAB_TOKEN")?;
    ensure!(
        token.len() >= 32 && token.bytes().all(|x| x.is_ascii_alphanumeric()),
        "private lab token required"
    );
    let input = PathBuf::from(env::var("IDPS_BODY_LAB_INPUT")?);
    let journal = PathBuf::from(env::var("IDPS_BODY_LAB_JOURNAL")?);
    for path in [&input, &journal] {
        ensure!(
            path.is_absolute() && !path.exists(),
            "fresh private paths required"
        );
        let parent = path.parent().context("parent")?;
        ensure!(
            parent.is_dir() && parent.metadata()?.permissions().mode() & 0o077 == 0,
            "private directory required"
        );
    }
    let pool = PgPoolOptions::new()
        .max_connections(2)
        .connect(&env::var("IDPS_BODY_LAB_DATABASE_URL")?)
        .await?;
    sqlx::query("CREATE SCHEMA IF NOT EXISTS idps_body_syntax_lab")
        .execute(&pool)
        .await?;
    sqlx::query("CREATE TABLE IF NOT EXISTS idps_body_syntax_lab.observations(request_id text PRIMARY KEY,event jsonb NOT NULL,received_at timestamptz NOT NULL DEFAULT now())").execute(&pool).await?;
    let lab = Lab {
        pool,
        token: Arc::new(token),
        accepted: Arc::new(AtomicU64::new(0)),
        rejected: Arc::new(AtomicU64::new(0)),
    };
    let listener = tokio::net::TcpListener::bind(address).await?;
    let server = axum::serve(
        listener,
        Router::new()
            .route("/observations", get(observations))
            .with_state(lab.clone()),
    );
    tokio::select! {
        result = async { server.await } => { result?; },
        result = consume(lab, input, journal) => { result?; },
        _ = tokio::signal::ctrl_c() => {},
    }
    Ok(())
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    if run().await.is_err() {
        eprintln!("Isolated body-syntax receiver stopped; input/error details suppressed");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn missing() -> Value {
        let spec: Value = serde_json::from_str(SPEC).unwrap();
        let mut x = vec![0u8; 46];
        x[0] = 1;
        x[14] = 1;
        json!({"schema_version":spec["version"],"contract_sha256":spec["contract_sha256"],"request_id":"a".repeat(32),"features":x})
    }
    #[test]
    fn strict_numeric_contract_rejects_raw_fields_and_inconsistent_states() {
        assert!(decode(&serde_json::to_vec(&missing()).unwrap()).is_ok());
        for (key, value) in [
            ("body", json!("private-canary")),
            ("score", json!(0.9)),
            ("contract_sha256", json!("wrong")),
        ] {
            let mut v = missing();
            v[key] = value;
            assert!(decode(&serde_json::to_vec(&v).unwrap()).is_err());
        }
        for (index, value) in [
            (1, json!(1)),
            (15, json!(1)),
            (0, json!(true)),
            (20, json!(7)),
        ] {
            let mut v = missing();
            v["features"][index] = value;
            assert!(decode(&serde_json::to_vec(&v).unwrap()).is_err());
        }
    }
}
