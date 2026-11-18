//! Offline parity probe on trusted numeric observations from the two owned lab sessions.
use anyhow::{anyhow, ensure, Result};
use ort::{session::Session, value::Tensor};
use sha2::{Digest, Sha256};
use std::collections::{HashSet, VecDeque};
use std::io::{self, BufRead};
use std::path::PathBuf;

#[derive(Default)]
struct Prefix {
    watermark: Option<u64>,
    pending: Option<u8>,
    history: VecDeque<(u64, Option<u8>)>,
}

impl Prefix {
    fn observe(&mut self, second: u64, route: u8) -> Option<[f32; 8]> {
        match self.watermark {
            Some(w) if second < w => {
                self.history.clear();
                self.pending = None;
                return None;
            }
            Some(w) if second == w => self.pending = None,
            _ => {
                if let Some(w) = self.watermark {
                    self.history.push_back((w, self.pending));
                    if self.history.len() > 5 {
                        self.history.pop_front();
                    }
                }
                self.watermark = Some(second);
                self.pending = Some(route);
            }
        }
        if self.history.len() != 5 {
            return None;
        }
        let routes: Vec<u8> = self
            .history
            .iter()
            .map(|(_, r)| *r)
            .collect::<Option<_>>()?;
        let times: Vec<u64> = self
            .history
            .iter()
            .map(|(t, _)| *t)
            .chain([second])
            .collect();
        let gaps: Vec<u64> = times.windows(2).map(|p| p[1] - p[0]).collect();
        if gaps.iter().any(|&g| g == 0 || g > 1800) {
            return None;
        }
        let mut sorted = gaps.clone();
        sorted.sort_unstable();
        let median = sorted[2];
        let mut dev: Vec<_> = gaps.iter().map(|g| g.abs_diff(median)).collect();
        dev.sort_unstable();
        Some([
            routes.iter().collect::<HashSet<_>>().len() as f32 / 5.,
            routes.windows(2).filter(|r| r[0] != r[1]).count() as f32 / 4.,
            routes.iter().filter(|r| **r == route).count() as f32 / 5.,
            routes
                .iter()
                .rposition(|&r| r == route)
                .map_or(0., |i| (i + 1) as f32 / 5.),
            (gaps[4] as f64).ln_1p() as f32,
            (median as f64).ln_1p() as f32,
            (dev[2] as f64).ln_1p() as f32,
            ((sorted[4] - sorted[0]) as f64).ln_1p() as f32,
        ])
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    ensure!(args.len() == 3, "expected model, SHA and ORT library");
    let bytes = std::fs::read(&args[0])?;
    ensure!(
        format!("{:x}", Sha256::digest(&bytes)) == args[1],
        "model SHA mismatch"
    );
    ort::init_from(PathBuf::from(&args[2]))?
        .with_telemetry(false)
        .commit();
    let mut model = Session::builder()?
        .with_intra_threads(1)
        .map_err(|e| anyhow!(e.to_string()))?
        .with_inter_threads(1)
        .map_err(|e| anyhow!(e.to_string()))?
        .commit_from_memory(&bytes)?;
    let mut sessions = [Prefix::default(), Prefix::default()];
    for line in io::stdin().lock().lines() {
        let line = line?;
        let values = line
            .split_ascii_whitespace()
            .map(str::parse::<u64>)
            .collect::<Result<Vec<_>, _>>();
        let Ok(fields) = values else {
            println!("ABSTAIN");
            continue;
        };
        let vector = match fields.as_slice() {
            [slot @ 0..=1, time, route @ 1..=3] => {
                sessions[*slot as usize].observe(*time, *route as u8)
            }
            _ => None,
        };
        let Some(v) = vector else {
            println!("ABSTAIN");
            continue;
        };
        let tensor = Tensor::from_array(([1, 8], v.to_vec().into_boxed_slice()))?;
        let outputs = model.run(ort::inputs!["input"=>tensor])?;
        let (_, scores) = outputs["score"].try_extract_tensor::<f32>()?;
        ensure!(
            scores.len() == 1 && scores[0].is_finite(),
            "invalid ONNX score"
        );
        println!("{:?} {}", v, scores[0]);
    }
    Ok(())
}
