# R26 research execution

Run: `t09-r26-acceleration-zfyPqyt3`. Results reside in
`ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/`. The final report is
`docs/108_T09_R26_FINAL_AI_QUALITY_ACCELERATION.md`.

The completed research candidate is **R26A SwiGLU URI100**, 400,256 parameters,
401,745 distinct publisher original requests. It is **not release-ready**.
No serving model, policy, source role or historical holdout was changed.

Two feature hypotheses were tested, with URI100 data recovery as the control:
URI164 finite-symbol contextual structure and HTTP244 observed content with
privacy/availability masks. Neither beat the control on the locked TUNING
selection criterion. The delivered model uses URI100 only.

## Drivers and evidence

| Driver | Purpose |
| --- | --- |
| `r26_data.py` | Incremental pinned WAF FIT/TUNING projection, atomic chunks and rebuild |
| `r26_notes.py` | New MIT synthetic publisher TRAIN intake, historical role fences and connected split |
| `r26_overlap.py` | Cross-publisher canonical request digest check |
| `r26_pilot.py`, `r26_learning.py` | Two feature pilots, URI100 control, source/class balancing |
| `r26_train.py` | Completed A training, atomic checkpoint and TUNING selection |
| `r26_calibration.py`, `r26_evaluate.py` | Namespaced ONNX calibration and pre-scoring evaluation lock |
| `r26_transfer.py` | Frozen source-transfer stress, without protected source payloads |
| `r26_verify.py` | Exact epoch replay and ETL reconciliation |
| `r26_runtime.py`, `r26_rust/` | Raw-target URI100 Rust preprocessing/inference parity, restart and ABSTAIN |
| `r26_augment.py`, `r26_recovery_pilot.py` | Three-source recovery using only previously permitted SR-BH FIT |
| `r26_recovery_train.py` | B training **interrupted by guardian watchdog**, checkpoint at epoch 16 |
| `r26_recovery_evaluate.py` | Prepared B evaluation; **not executed**, B has no completed selection/export |
| `r26_finalize.py` | JSON/digest/readback finalizer; starts no model worker or services |

Historical training/checkpoint binding code is immutable after execution. The
completed ETL is `data-v2/`; the first derivative and failed calibration/runtime
attempts remain available for diagnosis. Identity keys and raw HTTP data are
private artifacts and must not be committed.

## Safety and continuation

Every ETL/training/scoring/build phase used the existing Resource Adapter under
systemd: 1 CPU, 4 GiB, 16 tasks, unchanged 90/100 °C policy and hardware checks.
Completed results include kernel limits, invocation and cleanup evidence.

**Do not restart B automatically.** The guardian missed its watchdog; a bounded
read-only follow-up identified a stall at
`/sys/class/thermal/thermal_zone0/temp` (`acpitz`). RI and shadow Local services
also reached their own watchdog restart limits. `host-safety/` retains the
diagnosis, read trace and journals. The collector/receiver remained active.

Restore valid bounded hardware sensor reads and review the terminal stop before
launching any fresh guarded attempt or continuing a checkpoint. Keep sensor
checks, hardware alarms and watchdogs enabled. A successful mathematical epoch
replay is not permission to auto-resume after a safety stop. B's committed
checkpoint may be reviewed later; its new grouped source-FIT research holdout
must not be presented as pristine independent/native evaluation.

Lightweight regression:

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=ai-training/src ai-training/.venv/bin/python -m pytest -q \
  ai-training/contracts/quality-acceleration-r26/test_r26.py
```

Do not invoke the full training drivers directly as an unguarded workload. All
future compute must use a fresh owned Resource Adapter attempt after the safety
review. `artifact-index.json`, `model-manifest.json`, `feature-schema.json`,
`source-ledger.json`, `acceptance.json` and the source commit identify the exact
completed research result. The separate Rust scorer accepts private stdin
frames only in `OFFLINE_RAW_REQUEST_REPLAY`; it has no Hybrid/enforcement path.
