# Request v3 controlled pilot — 2026-11-08

Actual-data training authorized. Prepared run `request-v3-pilot-20261108-r1`.
This source handoff precedes launch; runtime status is authoritative.

Frozen dataset fingerprint:
`f6aa5b60b0c7d0291dfa123fe82a8e0870bb9fbacd36ac6eb27f3d6e9dfae22f`.
Frozen design fingerprint:
`5656548503f15afae512bcf47e2976afefd7148a1cea696e44bd2aa88555e32c`.

634→64→64→64→64→8, 53,640 parameters. Warm-start maps frozen W0[588,64]
into [634,64] with 46 zero rows; fresh AdamW, lr0.0001, W-only decay0.0001,
partial binary smoothing0.005/family_weight0. Seed17, batch16, no dropped tail,
20epochs or128steps first; current42canonical views imply60steps.

Prepare verified parameter/tensor/objective compatibility, initial function parity,
fresh moments, finite forward/backward, hashes and dataset contract. No CAL/DEV
arrays participate in fit. Actual update1 will be checkpointed and resumed in a
separate process as part of this same run. Recovery checkpoint every3updates;
final60step checkpoint alone is evaluated. No automatic failed-run restart.

Sampler interleaves recorded lineage components, without replacement, every
canonical view exactly once per epoch. This preserves the frozen exposure budget;
near variants are not resampled for extra weight. Correlated retained views still
limit effective sample size; evaluation reports near-component sensitivity.

Local private artifacts:
`ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1/`:

- `plan.json`: immutable hashes/configuration/sampler binding.
- `status.json`, `heartbeat`, `loss.jsonl`: persisted state/progress.
- `model/`: resumable checkpoint generations with Adam/RNG/cursor/epoch/scheduler.
- `resource/`: independent watchdog and active-window CPU/RAM/thermal telemetry.
- `completion.json`, `supervisor-result.json`: verified final status, if completed.
- `evaluation/`: final-checkpoint comparison, when authorized execution completes.

Supervisor service `idps-request-v3-pilot-20261108-r1.service`; independent inner
workload cgroup and watchdog use the existing integration guard, initial quota25%
one core, MemoryMax2GiB, no swap,4GiB system reserve, rolling80°C/instant85°C.
No source/model/threshold promotion or enforcement. Sealed samples remain closed.

Status command:

```bash
cat ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1/status.json
systemctl --user status idps-request-v3-pilot-20261108-r1.service
```

Locked comparison: frozen v2, calibration-only control, one challenger; strict `>`
thresholds, control/challenger max eligible CAL benign only. Identical canonical
candidate-view IDs, receipt and lineage sensitivity. Retention screen unchanged:
XSS+2,command+2 versus better reference, no new benign ID flagged versus either,
no SQLi/file TP-count loss. No DEV-selected checkpoint, threshold or retries.

Human review PENDING; independent quality not certified. Only source/tests/docs
are public; data, per-record scores and checkpoints remain local ignored.
