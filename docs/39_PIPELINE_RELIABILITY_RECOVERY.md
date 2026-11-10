# Pipeline reliability and 100K finalization recovery — 2026-11-10

This recovery fixes the demonstrated heartbeat race and makes the near-audit
restartable with its accumulator. **The100K ingestion is complete and is not rerun.
No model training,500K processing, promotion or deployment is performed.**

[Machine-readable evidence](../ai-training/reports/PIPELINE_RELIABILITY_RECOVERY_20261110.json).
Baseline `8e1d2b6`, branch `feature/ai-idps-shadow-integration`; local/remote matched
and the working tree was clean before these changes.

## Incident and heartbeat fix

The previous attempt `recovery-a1` stopped at54°C with
`SUPERVISOR_HEARTBEAT_LOST`, after100,000 positions and30,272/99,927 old audit anchors.
There was no OOM or emergency-temperature event. The old function captured
`time.time()` before reading heartbeat `mtime`: a concurrent writer could produce
an apparently future timestamp and a negative age. The failure mode was reproduced.
**Historical causation is not proven:** the old decision log omitted observed age,
PID identity and clock values, so another actual liveness delay cannot be excluded.

The active protocol now uses a complete atomic JSON snapshot, same-boot monotonic
nanoseconds and PID+`/proc` start ticks. It reads the snapshot and PID identity before
sampling the current monotonic clock. PID reuse, dead/zombie supervisors, changed
boot, reversed sequence, genuinely stale data and stale main-loop progress fail
closed. The heartbeat and main-loop deadline remain3 seconds; this is not a timeout
increase. A250ms writer thread runs outside the worker cgroup, while main-loop
progress must still advance. Thermal freezing cannot stale that supervisor record.
The controller's own heartbeat age also uses monotonic time in the supervisor.

Every thermal sample and stop now includes observed/current timestamps, measured
age, main-loop age, observed file mtime, PID/liveness, sequence, decision reason and
consecutive-failure count. Wall time is diagnostic, not the active age clock.
The retained legacy filesystem helper samples `mtime` before current time and allows
only50ms future skew; arbitrary future-dated files and stale files remain invalid.
The active monotonic protocol permits at most1ms ordering tolerance.

[Heartbeat implementation](../ai-training/src/idps_ai/training/heartbeat.py),
[watchdog integration](../ai-training/scripts/adaptive-thermal-guard.py),
[supervisor/recovery](../ai-training/scripts/student-data-recovery.py).

## Exact, bounded near-audit with real checkpoints

The metric stays **FP64 content dot >=0.995−1e−7** over the frozen L2-normalized
512 content features. The old audit computed all row pairs, including many identical
content vectors. Current committed data has33,949 distinct full588 views across
99,927 feature rows; exact content uniqueness is measured by the new cache.

The new [audit module](../ai-training/src/idps_ai/data/resumable_near.py) groups only
numerically identical float32 content vectors, using deterministic `np.unique`.
For each distinct-vector pair, its qualifying indicator is multiplied by
`count_i*count_j`. Within an identical group, count `c*(c−1)/2` only if its self-dot
qualifies. Zero vectors are handled explicitly by that same metric. Thus all
original unordered pairs are represented, without approximate LSH or capped buckets.
This grouping is a computation optimization, not a declaration of physical identity
or a change to which observations are training eligible.

Memory is bounded by the fixed100K input/cache and128×2048 score blocks. Complexity
is O(NlogN*d+U²*d), where U is exact unique content count. Worst-case quadratic work
has not disappeared; no generic exact subquadratic guarantee is claimed. The repeated
row calculations are removed, and the lower triangle is not counted twice.

For unit-L2 vectors of dimension<=512, floating-point reduction differences are
bounded well below the chosen1e−12 ambiguity band. Any computed score within that
band of the cutoff stops explicitly for investigation rather than silently changing
a boundary decision. This guard and numeric-contract checks preserve honest coverage;
full-cohort completion is not asserted before the background audit finishes.

Immutable vector/count arrays carry hashes and a source binding derived from the
original plan fingerprint, normalized metadata stream and every feature-shard hash.
Each atomic fsynced checkpoint contains **both `next_unique_anchor` and cumulative
integer `pairs`**, algorithm/implementation/cache bindings and a checksum. The
within-identical contribution is initialized once; each cross-chunk contribution
and its advanced cursor commit together. A crash before commit recomputes that chunk
from the previous accumulator; a crash after commit cannot count it again. Progress
JSON is reconciled from the checkpoint if it lagged. Invalid checksums, schema,
input/policy changes or corrupted arrays fail closed, preserving evidence.

The old30,272 cursor has no persisted pair accumulator and is **not reused**.
Only the near-audit restarts at zero in a separate `near-resumable-v1` namespace.
Old `near-progress.json`, scratch arrays, failure logs and attempts remain preserved.
New progress uses unique-vector anchors plus multiplicity-weighted original-anchor
coverage; its ordering differs from the old row anchors. This is not new HTTP data.

## Performance and validation evidence

40 targeted/relevant tests PASS; Ruff PASS. Tests cover filesystem ordering races,
bounded future skew, wall-clock changes, dead/reused PIDs, stale heartbeat/main loop,
invalid records, clock/boot identity and existing adaptive thermal behavior.
An actual child process performs two checkpointed chunks then `os._exit(9)`;
resuming in a fresh process yields exactly the uninterrupted final result and
byte-identical checkpoint. Tests also cover interruption before commit, lagging
progress, corrupt cache/checkpoint, changed bindings/block size, zero vectors,
near-threshold fixtures and derivative rebuild equivalence without ingestion.

**Preflight-a3 PASS:**35.74s supervisor wall time, peak70°C,20% maximum of one core,
real quota/freeze/thaw readbacks and independent watchdog. All100K source coordinates,
391 finite float32/588 shards, original code/policy/key/source bindings and absence
of orphan/partial files were checked inside the capped monitored worker.

On the deterministic already-exposed4,096-content-row prefix:

| Measurement | Result |
|---|---:|
|Exact unique content vectors|2,801|
|Original audit pair count|54,910|
|Weighted audit pair count|54,910|
|Original audit wall time|3.031s|
|Weighted audit wall time|1.786s|

The new timing excludes cache construction; this is an audit-kernel comparison,
not an end-to-end speedup guarantee or a linear100K forecast. No scores, labels,
thresholds or cohort roles were selected based on this performance probe.

## Recovery and rebuild scope

Original run `student-training-v1-100k-r2`; new attempt `recovery-a2`.
Original plan fingerprint remains
`b6d337f5b2a50ff3477012711e7bff60e7d5856007e8b067ed17626552673cd5`.
The new execution manifest binds the fixes separately; pinned original ingestion
and encoder code are unchanged. Existing normalized rows, label tiers, teacher
outputs, source frame, identity key,391 shards and SQLite data are preserved.
Derived finalization tables may be added normally; the DB is not deleted/replaced.

The worker finalizes the committed materialized dataset, then reconstructs the
exact graph and ledger from its committed normalized records in a fresh derivative
index, copies immutable feature bytes, independently recomputes near-pair results
and verifies summaries/ledgers/feature hashes. It **does not call source ingestion,
teacher labeling or raw feature extraction again**. This verifies deterministic
normalized-derivative finalization. It is not an independent raw-source feature
rematerialization; that stronger historical rebuild claim is not made here.

Publisher anomaly remains SILVER publisher anomaly, not verified attack intent.
The73 unsupported first-party receipts remain UNKNOWN. Global raw/campaign overlap
and incompatible legacy-encoder near checks remain PARTIAL. This audit does not
upgrade labels or create independent evaluation evidence.

Thermal policy remains85/90/93°C warning/throttle/strong, effective emergency96°C
or a lower applicable hardware limit. CPU ceiling20% of one core, job RAM<=8GiB,
4GiB system reserve, one math thread, independent watchdog and pause/ramp hysteresis
remain unchanged. There is no automatic retry after a safety stop.

## Live evidence and completion

Private run root:
`ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2/`.

- Supervisor: `idps-student-adaptive-recovery-a2.service`.
- New attempt `attempts/recovery-a2/status.json`, `worker.log`, `thermal-status.json`,
  `thermal-samples.jsonl`, `supervisor-heartbeat.json`, `services.json` and
  `launch-verification.json`.
- **Current audit:** `materialized/near-resumable-v1/progress.json` and `checkpoint.json`.
  The old `materialized/near-progress.json` is historical and stays30,272.
- Rebuild: `rebuild/progress.json` and `rebuild/near-resumable-v1/`.
- Completion requires both finalizations, independent derivative rebuild equality,
  unchanged original shard hashes, worker exit0 and successful watchdog completion:
  inspect `completion.json` plus this new attempt's `result.json` and thermal report.

This report records tested fixes and verified preflight before background launch.
Live private status is authoritative after launch. No training or500K processing is
started automatically. Raw HTTP, per-example labels/vectors, session IDs and keys
stay local; only reviewed code/tests and aggregate metadata enter Git.
