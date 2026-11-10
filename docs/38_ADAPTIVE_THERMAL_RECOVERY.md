# Adaptive thermal control and student-data recovery — 2026-11-10

The new execution policy supports cooling and gradual recovery above the former
85°C cutoff. It applies only to the isolated student-data workload. **No model
training, new source frame,500K run, system-wide power change or promotion.**

[Machine-readable evidence](../ai-training/reports/ADAPTIVE_THERMAL_RECOVERY_20261110.json).
Baseline `940c052`, branch `feature/ai-idps-shadow-integration`; local and remote
matched, working tree initially clean.

## Hardware and sensor evidence

The host is an ASUS Zenbook14 UX3405CA, BIOS UX3405CA.314, with an Intel Core Ultra9
285H/16 logical CPUs. The [Intel specification](https://www.intel.com/content/www/us/en/products/sku/241747/intel-core-ultra-9-processor-285h-24m-cache-up-to-5-40-ghz/specifications.html)
reports110°C maximum operating temperature. All17 `coretemp` core/package channels
on this machine report105°C critical. [Kernel coretemp documentation](https://www.kernel.org/doc/html/latest/hwmon/coretemp.html)
defines that critical value as maximum junction temperature. The lower locally
reported105°C bound takes precedence over the vendor maximum. CPU-related exposed
ACPI TCPU trips are110.05°C; generic ACPI hot/critical trips108°C.

**Effective CPU emergency cutoff96°C** is below those reported CPU limits. This
checks exposed platform limits, not hidden firmware behavior or physical sensor
calibration. Hardware/kernel protections remain active and untouched.

Other domains are not CPU junction limits: SEN1/2/6/7/8 report0.05°C with hot75.05°C
and critical80.05°C, while NVMe Composite reports critical84.85°C. The SEN readings
are recorded as unmapped/possibly placeholder firmware values, not presented as
CPU temperatures. Their own reported hot/critical trips, and the NVMe's own critical
trip, remain monitored as separate stop conditions. They never raise a CPU cutoff.
CPU-critical alarms, missing sensors, invalid values, changed lower CPU limits or
missing monitor heartbeat fail safely. No thermal sysfs value is written.

The old watchdog genuinely sampled `coretemp`, not NVMe/GPU. It saw52→92°C over
about0.20s and a fresh0.048s supervisor heartbeat, then killed the worker at the
old85°C cutoff. Its max-only history cannot identify which core produced the spike.
The slower/out-of-phase main monitor peaked71°C; that does not negate the independent
92°C observation. Prior95°C preparation spike also remains in the historical report.
Neither low CPU quota nor a50.5°C active average proves who caused those spikes.
The new independent controller persists every mapped CPU value, maximum-sensor
identity and unsmoothed trend at a nominal100ms cadence; auxiliary domains and
resource metrics update each second. Sampling/scheduling latency can still permit
overshoot, and this controller cannot cool unrelated applications.

## Adaptive policy

[Policy and sensor code](../ai-training/src/idps_ai/training/adaptive_thermal.py),
[independent controller](../ai-training/scripts/adaptive-thermal-guard.py),
[recovery launcher](../ai-training/scripts/student-data-recovery.py).
Thresholds, emergency limit, quota ceiling/minimum, cooldown/ramp and timeout are
explicit constructor parameters; the versioned recovery manifest records the
activated values. Original pinned85°C infrastructure is left unchanged.

| Measured CPU temperature | Response |
|---|---|
|<85°C|NORMAL; previously stable quota ceiling20% of one CPU, never raised by this milestone|
|85–<90°C|WARNING; rising temperature reduces quota to at most10%|
|90–<93°C|THROTTLE; halve current quota on entry, minimum1%|
|93–<96°C|STRONG_THROTTLE at1%; pause if rising>0.5°C/s, >=95°C, or sustained for2s|
|>=96°C, or own-domain hardware trip/alarm|THERMAL_EMERGENCY; kill only owned AI worker cgroup, preserve commits, no restart|

During a thermal pause status is `THERMAL_COOLDOWN`. Below85°C continuously15s,
resume at1% and add2 percentage points each5s, at most20%. A single cool sample
never restores full quota. Unsuccessful cooling after300s stops safely. A fast
rise below85°C can reduce quota proactively. Current instantaneous readings and
trend take precedence over averages. Active/wall averages remain disclosed;
this explicit new attempt policy replaces the former85°C/rolling-hard-stop policy
for this workload, without changing the historical policy file.

Shared RAM reserve4GiB, job cap<=8GiB, no swap, <=8 affinity CPUs and one math thread.
Memory pressure pauses the worker; OOM, invalid sensors and loss of monitoring stop
safely. The controller can address only `idps-student-adaptive-work-*.service` in the
current user's cgroup. Kernel quota/frozen-state readbacks must match commands.
Kill precedes thaw during an emergency. Nothing changes global CPU limits, fan
settings, hardware trip points or unrelated processes.

## Independence and recovery correctness

The supervisor, worker and thermal controller are separate systemd services.
The worker waits for the independent controller's first valid sample before doing
actual work. The controller checks the supervisor heartbeat outside the worker
cgroup. The supervisor checks controller service/heartbeat; controller loss kills
the owned worker. Missing supervisor heartbeat also fails closed. A frozen worker's
own heartbeat is deliberately not treated as monitor failure. Monitoring status
uses the atomic progress projection, never a potentially locked/frozen SQLite
writer. Actual cursor/integrity decisions still use committed SQLite at safe phase
boundaries. Unit lifetime deadlines and global RunLocks bound the workload.

Same run: `student-training-v1-100k-r2`; same plan fingerprint
`b6d337f5b2a50ff3477012711e7bff60e7d5856007e8b067ed17626552673cd5`.
Resume cursor23,040; the completed4,096 boundary is skipped. Original data code,
encoder, policy, source windows, labels, roles, identity key and plan bytes remain
unchanged. The new execution code is bound by a separate recovery manifest; it
calls the original verified ingest/finalize commands. No source positions are added
or reassigned because of teacher outputs.

Attempt `attempts/recovery-a1/` holds new telemetry and status. Old `resource/`,
old supervisor-result and failed preflight directories remain untouched. The old
root status was byte-copied to `attempts/recovery-a1/history/` before a live status
projection may replace it. The original service remains failed historical evidence;
the new service is `idps-student-adaptive-recovery-a1.service`.

Recovery continues to100K then independently rebuilds the same frame. Existing90
feature shards must retain their recorded hashes, new/rebuilt ledgers and all
shards must match, semantic summaries must agree and source fingerprints must
still pass. Completion requires worker exit0, verified outputs and successful
controller completion. `completion.json` alone is not enough: inspect the new
attempt's `result.json` and `thermal-report.json` too. The earlier root
`supervisor-result.json` remains the failed old attempt, not the recovery result.

## Validation and actual preflight

31 targeted/relevant tests PASS, Ruff PASS. Simulated sequences cover80 normal,
88 warning,91 throttle,94 strong,63→92→95 pause,96 emergency, lower hardware cutoff,
cooldown hysteresis, gradual resume, failed cooling, missing sensors, watchdog loss,
intentional-pause heartbeat, cgroup scope and committed-boundary selection.
No actual CPU was deliberately heated to those temperatures.

Preflight-a1 safely stopped at55°C because its own probe mistook intentional
COOLDOWN for inadequate headroom. That implementation error and its artifacts are
retained. The fixed test checks the heat band separately from pause state.
An additional regression verifies that an exclusive SQLite lock cannot block the
status monitor and create a false heartbeat failure.

**Preflight-a2 PASS:**25.66s, peak56°C, real systemd quota20→10→5→20%, real
freeze/thaw confirmed by `cgroup.events`, independent monitoring maintained.
SQLite quick_check OK;90 shards readable, finite float32/588, no partial/orphan
files, cursor unchanged23,040; complete existing source/code/policy/key bindings
verified under the capped worker. Auto-cooldown/resume is established by simulation
and real cool-temperature actuator checks, not a claim of observed cooling from
96°C. Full100K dataset/rebuild is still pending.

## Live and final evidence

Private root:
`ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2/`.

- Current root `status.json`, or `attempts/recovery-a1/status.json`.
- `attempts/recovery-a1/worker.log`, `thermal-status.json`, `thermal-samples.jsonl`.
- `attempts/recovery-a1/services.json`, `launch-verification.json` and `recovery-plan.json`.
- `materialized/progress.json` and committed `materialized/index.sqlite`.
- Final `completion.json`, new attempt `result.json` and `thermal-report.json`.

Only code/tests and aggregate metadata are public. Raw HTTP, native IDs, sessions,
features, pseudo-label ledgers and identity keys remain local. All Frozen Requestv2,
GLU207, v3 checkpoints, strict dataset roles, sealed samples, Web, Rules/Policy,
Nginx/Suricata, releases and production inference remain unchanged.

This document records verified preflight and prepared recovery. After an independently
verified launch, live status is authoritative. No training or500K job is started.
