# R26.1 recovery and research candidate

Run: `t09-r261-recovery-drliluc_`. Final decision:
**QUALITY_IMPROVED_NATIVE_BLOCKED**. RI v2 stays the default; R20 stays the
existing shadow. B16 URI100 is research-only, not installed or promoted.

The immutable parent is `../quality-acceleration-r26` and its artifact run
`ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/`. No parent checkpoint,
holdout role, original dataset or historical verdict was rewritten.

## Execution

- `sensor_health.py`: bounded, traced reads through the real SensorReader.
- `benchmark.py`: discarded scratch updates comparing 1/2/4 BLAS threads.
- `checkpoint_audit.py`: binding/digest/cursor verification and exact B15→B16 replay.
- `precalibrate.py`, `calibration.py`: initial fixed B16/A CAL comparison, no TEST feedback.
- `continue_b.py`: one continuation in a copied checkpoint namespace, same sampler,
  optimizer and schedule; early-stop at epoch21, best remains epoch16.
- `evaluate.py`: common CAL protocol, immutable evaluation lock, then one opening
  of the source2 research holdout. Old Notes research TEST is not reopened.
- `diagnose.py`: fixed-threshold transfer, mixed-label and method diagnostics.
- `replay.py`, `rust_tests.py`, `verify.py`: separately bounded replay/compiler
  workers and final composition of raw-target parity. Never compile in a live
  model worker that is close to its task limit.
- `thermal_probe.py`: injected boundary temperatures on an owned sleep child;
  actual cgroup quota readback, not an attempt to heat the CPU.
- `allocation_probe.py`: verifies actual thread pools and kernel limits after
  correcting the legacy barrier's hardcoded one-thread environment.
- `native.py`: read-only reconciliation of old receipts and authorization proofs.
- `native_authorization.py`, `native_capture.py`, `lab_auth.py`: one disposable
  authorization-pair campaign with real role/owner/policy/Audit evidence and
  URI100 projection in the trusted mirror before cutoff.
- `recover_native.py`: one reviewed fresh-campaign repair. First eight receipts
  remain untouched; new guest/H2/sessions and twelve new requests. No HTTP replay
  within an old campaign and no further automatic acquisition retries.
- `live.py`, `warm.py`: synthetic private-UDS protocol liveness, never counted as
  HTTP/native capture or training data.
- `finalize.py`: digest/readback verification and a research bundle; no promotion.

`supervisor.py` is a finite phase driver over the existing Resource Adapter.
It has a lock, per-attempt logs/status, immutable checkpoints, finite deadlines,
new invocation identity and explicit failure handling. No idle waiting jobs or
automatic restart after an unidentified watchdog/sensor/task failure are created.

## Safety and resource integration

The default Adapter path remains one-thread and retains its original resource
limits. An explicit pinned R26.1 allocation review can authorize the measured
4-core research envelope within a freshly computed host ceiling. The new
`--blas-threads` parameter reaches the worker after the start barrier; caller
environment alone does not grant more threads. Runtime quotas, thermal guard,
ownership, counters, watchdog and cleanup remain mandatory.

The short benchmark path is **not** evidence of the contract's 300-second
production scaling gate. Cold-start and runtime use the existing 90/100°C policy
with hardware protection taking priority. A software-pause recovery eligibility
predicate requires complete no-alarm trip evidence, verified checkpoint/cleanup
and fresh stable ≤90°C readings. It is not permission to resume a hardware alarm,
unknown watchdog, sensor outage or task-limit stop. No live over-temperature
auto-resume was attempted or claimed in this run.

## Data and model scope

Publisher training: 433,261 original requests, 50,230 URI100 vectors, equal-source
weighting Kish count about 10,257. The source2 research holdout is a grouped
derivative of historically exposed R13 FIT, not pristine independent native TEST.
The new first-party labels concern **authorization-policy violation attempts**;
they are not silently merged with publisher payload-anomaly labels.

The repaired guest made 12 requests with 12 Oracle/projection proofs, including
3 benign and 3 denied policy-violation witnesses. All are research candidates in
one campaign with shared templates. Native TRAIN/DEV/CAL/TEST remains 0/0/0/0.
Machine policy/Oracle verification does not fabricate an independent-human review
attestation. The legacy admission protocol is not weakened.

Original execution bytes for numerical drivers are retained privately alongside
AST-equivalence evidence after formatting. `artifact-index.json`,
`research-bundle/manifest.json` and `r261-evidence.json` bind the delivered results.
Private artifacts, checkpoints, model weights, raw logs and identity keys are not
committed to Git. Clean-checkout release installation is not certified while the
release gates remain blocked.
