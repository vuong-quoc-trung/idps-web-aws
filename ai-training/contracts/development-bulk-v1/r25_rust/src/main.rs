//! Isolated URI100 tensor replay. No HTTP ingress or Hybrid Policy integration.
use anyhow::{Result, ensure};
use ort::{
    session::Session,
    value::{Tensor, TensorElementType, ValueType},
};
use serde::Deserialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    io::{self, BufRead, Read},
    time::Instant,
};

const VERSION: &str = "idps-request-time-uri76-shape-r23-v1";
const LIMIT: u64 = 16384;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Frame {
    version: String,
    source: String,
    vectors: Vec<f32>,
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    ensure!(args.len() == 3, "usage: MODEL SHA256 ORT_LIBRARY");
    let path = std::path::Path::new(&args[0]);
    let metadata = path.symlink_metadata()?;
    ensure!(
        metadata.is_file() && metadata.len() <= 2 * 1024 * 1024,
        "Artifact bounds"
    );
    let bytes = std::fs::read(path)?;
    let sha = format!("{:x}", Sha256::digest(&bytes));
    ensure!(sha == args[1], "Model digest mismatch");
    ort::init_from(&args[2])?.with_telemetry(false).commit();
    let load = Instant::now();
    let mut session = Session::builder()?
        .with_intra_threads(1)
        .map_err(|e| anyhow::anyhow!(e.to_string()))?
        .with_inter_threads(1)
        .map_err(|e| anyhow::anyhow!(e.to_string()))?
        .commit_from_memory(&bytes)?;
    ensure!(
        session.inputs().len() == 1 && session.inputs()[0].name() == "input",
        "Input count/name"
    );
    ensure!(
        matches!(session.inputs()[0].dtype(),ValueType::Tensor{ty:TensorElementType::Float32,shape,..} if &shape[..]==[-1,100]),
        "URI100 ABI mismatch"
    );
    ensure!(session.outputs().iter().any(|x| x.name()=="score" && matches!(x.dtype(),ValueType::Tensor{ty:TensorElementType::Float32,shape,..} if &shape[..]==[-1])),"Score ABI mismatch");
    let load_ns = load.elapsed().as_nanos() as u64;
    let mut input = io::stdin().lock();
    loop {
        let mut line = Vec::new();
        if input
            .by_ref()
            .take(LIMIT + 1)
            .read_until(b'\n', &mut line)?
            == 0
        {
            break;
        }
        if line.len() > LIMIT as usize || line.last() != Some(&b'\n') {
            println!("{}", json!({"status":"ABSTAIN","reason":"FRAME_BOUND"}));
            break;
        }
        let frame = serde_json::from_slice::<Frame>(&line).ok().filter(|x| {
            x.version == VERSION
                && x.source == "OFFLINE_TENSOR_REPLAY"
                && x.vectors.len() == 100
                && x.vectors.iter().all(|v| v.is_finite())
        });
        if let Some(frame) = frame {
            let started = Instant::now();
            let tensor = Tensor::from_array(([1, 100], frame.vectors.into_boxed_slice()))?;
            let output = session.run(ort::inputs!["input"=>tensor])?;
            let (_, scores) = output["score"].try_extract_tensor::<f32>()?;
            if let [score] = scores
                && (0.0..=1.0).contains(score)
            {
                println!(
                    "{}",
                    json!({"status":"SCORED","score":score,"model_sha256":sha,"version":VERSION,"inference_ns":started.elapsed().as_nanos() as u64,"model_load_ns":load_ns,"hybrid_allowed":false,"evidence_scope":"OFFLINE_TENSOR_REPLAY"})
                );
            } else {
                println!("{}", json!({"status":"ABSTAIN","reason":"INVALID_SCORE"}));
            }
        } else {
            println!(
                "{}",
                json!({"status":"ABSTAIN","reason":"INVALID_ENVELOPE"})
            );
        }
    }
    Ok(())
}
