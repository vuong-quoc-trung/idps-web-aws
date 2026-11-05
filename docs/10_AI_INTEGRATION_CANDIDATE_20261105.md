# AI Integration Candidate — controlled training and reproducible handoff

**INTEGRATION_CANDIDATE_READY = TRUE** for a local **request-only shadow demo**. The default is **Frozen Request Intelligence v2**, not the newly trained candidate. This is technical readiness for starting an integration branch, not production readiness or independent quality acceptance. No branch/integration/deployment was started.

Machine-readable report: [INTEGRATION_CANDIDATE_20261105.json](../ai-training/reports/INTEGRATION_CANDIDATE_20261105.json).
Local artifact root: `ai-training/.artifacts/integration_candidate_20261105/`.

## Decision and bounded experiment

P0.5 established that numeric privacy projection removes DVWA XSS `name` values, while header/content mixing attenuates command-payload evidence. The shortest data-compatible experiment was **train-time numeric-channel masking**, with the original encoder and existing50,696-parameter MLP unchanged. Masking first76 features for25% of training rows tests whether the content channel can become useful when numeric evidence is missing. It is a robustness augmentation, not exact simulation of all production missingness.

One main hypothesis, one seed and one final3072-update candidate were used. There was no hyperparameter search, model-size increase, new dataset, DVWA fitting or encoder edit. GLU207 remained frozen because the request-only corpus cannot provide its true207-feature three-source context.

The training plan and selection criterion were written before the candidate fit. A candidate could replace the demo default only if it kept WAF development positive sensitivity within1pp and normal flags within0.2pp of baseline and gained at least4 DVWA attempts with no additional benign flags. DVWA is explicitly exposed regression selection, not independent evaluation. No post-result threshold search or additional candidate was run.

## Actual fitting and checkpoint evidence

| Item | Result |
| --- | --- |
| Source | Existing curated WAF v2 tensor SHA `279dca7d…`, original publisher train split |
| Fitting role | role0 only, materialized separately before trainer runs |
| Unique train views | **120,435**, all actually encountered |
| Labels | 34,282 publisher NORMAL;86,153 publisher ANOMALOUS |
| Excluded from fitting | role1 calibration, role2 development, DVWA, Juice, all sealed holdouts |
| Model | Existing deep MLP588→64→64→64→64→8, partial binary objective |
| Parameters | **50,696** |
| Main optimization | **3,072 updates**, batch256, constant LR0.001, seed31 |
| Exposure accounting | 786,432 sample exposures, approximately6.5299 effective passes;196,223 masked row exposures |
| Mean first/last100 augmented batch losses | **0.413377 → 0.087496** |
| Checkpoints | Existing atomic NPZ/JSON; latest/previous/best retention; save every256 steps |

These are feature views, not verified distinct physical requests. Augmented batch loss is not directly comparable with the unaugmented baseline's training loss and does not measure detection quality. `best.json` initially points to the first saved checkpoint by the existing utility; this is not a validation-selected champion.

New final checkpoint: `candidate-run/checkpoints/step-000000003072-ce01c352a9df/`.
Manifest SHA256: `09ae4a6900806c87b5f277c97e9b0b30403700d4c185e112455b000a2761f2d3`.

The main run used fresh processes0→256→1024→3072. Exact continuation was checked in two stronger ways:

1. Continuous128 versus64→save→new process→128: every parameter, Adam moment, sampler permutation/cursor, RNG state and loss history equal.
2. A relocated source/material recovery kit resumed the preserved2816 checkpoint to3072 in a fresh process. The entire final model/optimizer/sampler/history is exactly equal to the original3072 result.

**RESUME_EXACT applies to the new research candidate in the same pinned environment.** It does not apply retroactively to the selected historical frozen model. The final3072 target is terminal under this plan; extending the target/schedule requires a new explicit experiment. Additional resume verification accounts for512 replayed updates, not new unique data or additional candidate searches.

## Evaluation and model choice

The candidate's threshold **0.9068083763122559** was fixed using only role1 publisher-NORMAL p99 (`higher`, strict greater-than), before role2 or DVWA scoring. Frozen baseline threshold remains **0.8826237916946411**.

| Evidence | Frozen Request v2 | Numeric-mask candidate |
| --- | ---: | ---: |
| WAF development positive flagged | 13,894/14,481 =95.946% | 13,816/14,481 =95.408% |
| WAF development NORMAL flagged | 56/5,602 =0.9996% | 60/5,602 =1.0710% |
| WAF development PR-AUC/AP | 0.998836 | 0.998783 |
| DVWA TP/FN | 18/30 | 17/31 |
| DVWA FP/TN | 0/59 | 0/59 |
| DVWA SQLi detected | 12/12 | 11/12 |
| DVWA XSS / command detected | 0/12 /0/12 | 0/12 /0/12 |
| DVWA file inclusion detected | 6/12 | 6/12 |

The new candidate did not improve the measured development/regression evidence and failed the precommitted gain criterion. It remains an **unselected research artifact**. Numeric masking alone did not repair the P0.5 failure mechanisms. No second candidate, threshold adjustment or repeated study was used to force a favorable outcome.

WAF labels remain publisher NORMAL/ANOMALOUS with related-template/near-duplicate dependence. DVWA remains one exposed lab cohort with4 UNKNOWN and independent human review pending. No new independent Recall/FPR, population quality, production champion or Ground Truth training claim is established. Existing cross-source retrospective evidence is retained; it was not rerun or presented as a new result in this task.

## Thermal control: actual training workload, bounded scope

Before fitting, the cgroup supervisor was checked using real sleeping tasks and threads, including a descendant with a separate process group. Kernel cgroup freeze halted their CPU progress; thaw followed a stable cooldown; injected>=80°C killed the complete cgroup. An independently running watchdog also stopped the workload when the main monitor was deliberately suspended until its heartbeat became stale. Injected temperatures were control tests, not measured physical heating.

The real training kernel then ran256 updates at0.25 CPU and768 more at0.5 CPU before the final2048-update segment at the stable0.5 CPU setting. Every stage read back `cpu.max` and swap/RAM limits. One BLAS worker and all observed task affinities wereCPU0. This is a conservative task-specific choice, not a fixed50%-of-host utilization policy.

- Actual monitored CPU package/core range: **46–48°C**, time-weighted mean approximately**46.85°C**. GPU/NVMe sensors and simulated test values are excluded.
- No thermal reduction, freeze or hard-stop during actual preparation/training/evaluation/verification.
- Main training wall time including startup/checkpoint/monitoring: **37.88s**; CPU time16.42s. Observed utilization averaged0.237/0.477/0.483 cores across the three stages, consistent with kernel quotas.
- Peak cgroup-charged memory across main task stages: approximately**0.994GB**, during material preparation. This is not equivalent to RSS and may differ under shared file-cache accounting.
- Peak shared-system `MemTotal−MemAvailable`: approximately**9.04GB**, below the shared30GB budget. A2GiB kernel ceiling and zero swap were used for each unit.
- Independent watchdog samples CPU every0.2s and kills on>=79°C or monitor heartbeat stale>3s. The primary monitor freezes/reduces at72°C or rapid temperature rise, kills at80°C, and only resumes after<68°C for5s.

This verifies control and observed stability **for this bounded50k MLP workload at the tested quotas**. It does not certify arbitrary heavy GLU training, all hardware conditions, supervisor/watchdog simultaneous failure, or absolute absence of thermal spikes. No OS/firmware power or thermal protection was changed, and no physical overheat stress was induced.

## Portable integration handoff

Selected demo bundle: `demo-request-bundle/` (approximately2.7MiB).
Transfer archive: `demo-request-integration.tar.gz`.
Archive SHA256: `cd41d153997cd254fae53d091a708538d99c66625b39fc554148d3ce7b1664d0`.

Contents include the native frozen checkpoint, unmodified Python encoder/model source, exact dependency lock, feature/threshold provenance, optional ONNX, sample input and evaluation decision. ONNX/native technical parity passed on128 sampled train vectors: score error0, maximum probability error5.96e−8.

```bash
bundle=/home/trung/projects/idps-web-aws/ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle
/home/trung/projects/idps-web-aws/ai-training/.venv/bin/python -I -B "$bundle/infer.py" \
  --input "$bundle/sample-input.jsonl" \
  --output /tmp/ai-idps-new-private-shadow-output.jsonl
```

The output must be a new path; existing files are never overwritten.

Input contract:

```json
{"schema_version":"integration-request-1","record_id":"opaque-001","http_request":{"method":"GET","url":"/api/health","headers":"Accept: application/json","body":""}}
```

`headers`/`body` may be `null` if unobserved; do not fabricate values. The output includes score, threshold/rule, model/encoder versions, availability (including numeric dropped-query count), `combined_score:null`, and `enforcement_actions:0`. Scores are not independently calibrated attack probabilities.

A fresh isolated Python CLI in a relocated bundle, launched from `/tmp`, reproduced all111 frozen DVWA scores and decisions exactly. Two fresh-process outputs were byte-identical. Invalid JSON/schema/body, duplicates, empty/mixed-invalid input, existing/symlink output and tampered checkpoints were rejected without partial output. The checks used the existing pinned environment; a different machine/clean installation has not been physically tested.

On another machine, privately copy/extract the archive, create Python3.12 venv, install `requirements.lock.txt`, and run the same relative bundle command. No repository checkout, original `.artifacts` path or training data is needed for inference. Use a dedicated worker that loads `RequestPredictor` once; the package CLI is finite-batch, not a deployed HTTP service.

The new rejected candidate also has `research-candidate-bundle/` with the same inference entry point, but must not become the default demo. Its recovery source, actual hashed train-only material and2816 checkpoint are in `training-recovery/`; follow that private kit's README. Do not try to resume the selected historical frozen baseline with the new augmentation trainer. Selected baseline training status is explicitly **INFERENCE_ONLY**.

## Integration branch boundary and final verification

The next integration branch can use the selected request bundle in shadow mode. It must provide allowed HTTP observations after TLS termination, send rule-negative as well as rule-positive requests, and own bounded queues, backpressure, timeout/restart and metrics. Missing headers/body and the known XSS/command weaknesses remain visible limitations. The CLI's dedup set grows with the finite batch; do not present it as an unbounded production stream service.

GLU207 remains a separate frozen reference requiring complete, chronological three-source post-response input. No request-only data was padded into207 features. No AI score aggregation, IPS blocking or integration with either Web occurred.

Nineteen targeted tests passed; Ruff/format/diff checks passed. All19 protected frozen checksums and1,406 preexisting source/config/P0/P0.5 evidence files remained unchanged. Student/Security Web, canonical contracts, Docker, formal configs and frozen AI source diff remain empty. Git HEAD stayed `09a12e46329fbb98ccba1fd1c884a79bf49ab2b4`; existing uncommitted files were retained. No sealed holdout, commit/push/reset or production action occurred.

The controlled experiment and handoff are complete. **INTEGRATION_CANDIDATE_READY = TRUE** means the preserved frozen request model is technically ready for a local shadow integration branch; it does not promote the unsuccessful new candidate or certify detection quality. Work stops here.
