//! Private, isolated raw URI100 scorer. This binary has no enforcement path.
mod features;

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

const SCHEMA: &str = "idps-uri100-raw-ascii-r26-v1";
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Frame {
    schema: String,
    mode: String,
    method: String,
    target: String,
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let project_only = args == ["--project-only"];
    ensure!(
        project_only || args.len() == 3,
        "usage: --project-only OR MODEL SHA256 ORT_LIBRARY"
    );
    let mut session = None;
    let mut model_sha = String::new();
    let mut load_ns = 0u64;
    if !project_only {
        let metadata = std::fs::symlink_metadata(&args[0])?;
        ensure!(
            metadata.is_file() && metadata.len() <= 2 * 1024 * 1024,
            "Invalid model artifact bounds"
        );
        let content = std::fs::read(&args[0])?;
        model_sha = format!("{:x}", Sha256::digest(&content));
        ensure!(model_sha == args[1], "Model digest mismatch");
        ort::init_from(&args[2])?.with_telemetry(false).commit();
        let started = Instant::now();
        let model = Session::builder()?
            .with_intra_threads(1)
            .map_err(|e| anyhow::anyhow!(e.to_string()))?
            .with_inter_threads(1)
            .map_err(|e| anyhow::anyhow!(e.to_string()))?
            .commit_from_memory(&content)?;
        ensure!(
            model.inputs().len() == 1
                && model.inputs()[0].name() == "input"
                && matches!(model.inputs()[0].dtype(),ValueType::Tensor{ty:TensorElementType::Float32,shape,..} if &shape[..]==[-1,100]),
            "URI100 model ABI mismatch"
        );
        ensure!(model.outputs().iter().any(|o|o.name()=="score" && matches!(o.dtype(),ValueType::Tensor{ty:TensorElementType::Float32,shape,..} if &shape[..]==[-1])),"Score ABI mismatch");
        load_ns = started.elapsed().as_nanos() as u64;
        session = Some(model);
    }
    let mut stream = io::stdin().lock();
    loop {
        let mut line = Vec::new();
        if stream.by_ref().take(16385).read_until(b'\n', &mut line)? == 0 {
            break;
        }
        if line.len() > 16384 || line.last() != Some(&b'\n') {
            println!("{}", json!({"status":"ABSTAIN","reason":"FRAME_BOUND"}));
            break;
        }
        let frame = serde_json::from_slice::<Frame>(&line)
            .ok()
            .filter(|f| f.schema == SCHEMA && f.mode == "OFFLINE_RAW_REQUEST_REPLAY");
        let Some(frame) = frame else {
            println!(
                "{}",
                json!({"status":"ABSTAIN","reason":"INVALID_ENVELOPE"})
            );
            continue;
        };
        let started = Instant::now();
        let vector = match features::project(&frame.method, &frame.target) {
            Ok(v) => v,
            Err(reason) => {
                println!("{}", json!({"status":"ABSTAIN","reason":reason}));
                continue;
            }
        };
        let preprocessing_ns = started.elapsed().as_nanos() as u64;
        let mut score = None;
        let mut inference_ns = 0u64;
        if let Some(model) = session.as_mut() {
            let started = Instant::now();
            let input = Tensor::from_array(([1, 100], vector.clone().into_boxed_slice()))?;
            let result = model.run(ort::inputs!["input"=>input])?;
            let (_, scores) = result["score"].try_extract_tensor::<f32>()?;
            if let [value] = scores
                && (0.0..=1.0).contains(value)
            {
                score = Some(*value);
            }
            inference_ns = started.elapsed().as_nanos() as u64;
            ensure!(score.is_some(), "Invalid model score");
        }
        println!(
            "{}",
            json!({"status":"SCORED","schema":SCHEMA,"features":vector,"score":score,
            "preprocessing_ns":preprocessing_ns,"inference_ns":inference_ns,"model_load_ns":load_ns,
            "model_sha256":model_sha,"hybrid_allowed":false,"mode":"OFFLINE_RAW_REQUEST_REPLAY"})
        );
    }
    Ok(())
}
