"""T03 pure resource planning/validation. No process, cgroup or service mutations.

Live adapters must attest all supplied readbacks, ownership and benchmark inputs.
Plans are not launch permission; this module never loads a dataset or model.
CPU quantities here are core-equivalents, not host-normalized percentages.
"""

import math
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from idps_ai.common import PipelineError, digest
from idps_ai.training.adaptive_thermal import ThermalMachine
from idps_ai.training.thermal_policy import HARDWARE_MARGIN_C, STOP_C, THROTTLE_C

GIB = 1024**3
MIB = 1024**2
VERSION = "idps-resource-contract-1.1.0"
PHASES = {"DATA": (1.0, 4), "TRAIN": (1.0, 8), "EVALUATE": (1.0, 4), "SERVE": (1.0, 2)}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class HostBudget:
    cpu_ids: tuple[int, ...]
    total_bytes: int
    available_bytes: int
    cpu_critical_c: float
    ancestor_cpu_cap: float | None = None
    ancestor_memory_headroom: int | None = None
    external_reserved_cores: float = 0
    external_growth_bytes: int = 0


def plan_resources(host: HostBudget, phase: str):
    """Candidate capacity, not an assertion that a larger allocation is efficient.

    Available memory already subtracts resident external memory. Only its unused
    reservation/growth is subtracted again. External CPU uses bounded reservations;
    observed idle utilization alone cannot reserve capacity for this job.
    """
    if phase not in PHASES:
        raise PipelineError("Unknown resource phase")
    numeric = [
        host.total_bytes,
        host.available_bytes,
        host.cpu_critical_c,
        host.external_reserved_cores,
        host.external_growth_bytes,
    ]
    numeric += [v for v in (host.ancestor_cpu_cap, host.ancestor_memory_headroom) if v is not None]
    if not all(finite(v) and v >= 0 for v in numeric):
        raise PipelineError("Invalid host budget")
    if (
        not host.cpu_ids
        or len(set(host.cpu_ids)) != len(host.cpu_ids)
        or any(type(v) is not int or v < 0 for v in host.cpu_ids)
        or not 0 < host.available_bytes <= host.total_bytes
        or not 40 <= host.cpu_critical_c <= 130
    ):
        raise PipelineError("Unverified host/CPU thermal capacity")
    count = len(host.cpu_ids)
    reserve_cores = max(1, math.ceil(count * 0.125))
    reserve_bytes = max(4 * GIB, math.ceil(host.total_bytes * 0.15 / GIB) * GIB)
    # Controllers are outside the freezeable worker subtree, but inside accounting.
    monitor_cores, monitor_bytes = 0.25, 256 * MIB
    usable = count - reserve_cores - host.external_reserved_cores - monitor_cores
    if host.ancestor_cpu_cap is not None:
        usable = min(usable, host.ancestor_cpu_cap - monitor_cores)
    cpu_ceiling = math.floor(usable * 4) / 4
    memory = min(
        host.total_bytes * 0.75, host.available_bytes - reserve_bytes - host.external_growth_bytes
    )
    if host.ancestor_memory_headroom is not None:
        memory = min(memory, host.ancestor_memory_headroom)
    memory_ceiling = math.floor((memory - monitor_bytes) / (256 * MIB)) * 256 * MIB
    if cpu_ceiling < 0.25 or memory_ceiling < GIB:
        raise PipelineError("Insufficient reserved headroom; no workload admitted")
    hardware_stop = host.cpu_critical_c - HARDWARE_MARGIN_C
    if hardware_stop <= 50:
        raise PipelineError("Hardware requires a separately reviewed lower-temperature profile")
    starter_cpu, starter_gib = PHASES[phase]
    return {
        "version": VERSION,
        "phase": phase,
        "cpu_ids": sorted(host.cpu_ids),
        "os_reserve_cores": reserve_cores,
        "os_reserve_bytes": reserve_bytes,
        "monitor_cores": monitor_cores,
        "monitor_memory_bytes": monitor_bytes,
        "worker_cpu_ceiling": cpu_ceiling,
        "worker_memory_ceiling_bytes": memory_ceiling,
        "starter_cpu_cores": min(starter_cpu, cpu_ceiling),
        "starter_memory_bytes": min(starter_gib * GIB, memory_ceiling),
        "approved_cpu_cores": min(starter_cpu, cpu_ceiling),
        "approved_memory_bytes": min(starter_gib * GIB, memory_ceiling),
        "hardware_hash": digest(
            {
                "cpu_ids": sorted(host.cpu_ids),
                "total_bytes": host.total_bytes,
                "cpu_critical_c": host.cpu_critical_c,
            }
        ),
        "memory_high_fraction": 0.8,
        "memory_swap_max": 0,
        "tasks_max": 256,
        "thermal": {
            "throttle": THROTTLE_C,
            "emergency": STOP_C,
            "hardware_stop_at_c": hardware_stop,
            "strict_software_boundaries": True,
        },
        "cpu_critical_c": host.cpu_critical_c,
        "sample_max_age_seconds": 1.0,
        "larger_allocations": "REQUIRE_MATCHED_BOUNDED_BENCHMARK_AND_FRESH_PREFLIGHT",
        "activation": "NOT_INSTALLED_OR_LIVE_VALIDATED_BY_T03",
    }


def scale_evidence(reference, candidate):
    """Evaluate a recorded experiment; callers must verify its hash/provenance.

    At least300 seconds of active measurements per arm. Startup/cooldown excluded.
    Memory scaling may justify fewer spills, but must still improve useful rate.
    No experiment is executed here and fixtures never constitute real evidence.
    """
    reasons = []
    for key in ("hardware_hash", "workload_hash", "implementation_hash", "phase"):
        if not reference.get(key) or reference.get(key) != candidate.get(key):
            reasons.append("UNMATCHED_" + key.upper())
    numeric = (
        "active_seconds",
        "useful_per_second",
        "p95_latency_ms",
        "cpu_cores",
        "memory_max_bytes",
        "peak_memory_bytes",
        "peak_c",
        "psi_full_avg10_max",
    )
    for arm in (reference, candidate):
        if any(not finite(arm.get(k)) or arm[k] < 0 for k in numeric):
            return {"eligible": False, "reasons": ["INVALID_MEASUREMENT"]}
        if (
            arm["active_seconds"] < 300
            or arm["useful_per_second"] <= 0
            or arm["cpu_cores"] <= 0
            or arm["memory_max_bytes"] <= 0
            or arm["p95_latency_ms"] <= 0
        ):
            reasons.append("INSUFFICIENT_ACTIVE_MEASUREMENT")
        if (
            arm.get("safety_events") != 0
            or arm.get("errors") != 0
            or arm.get("sensor_complete") is not True
            or arm.get("containment_verified") is not True
            or arm["peak_memory_bytes"] >= arm["memory_max_bytes"] * 0.8
            or arm["psi_full_avg10_max"] >= 1
        ):
            reasons.append("UNSAFE_OR_INCOMPLETE_MEASUREMENT")
        warning = arm.get("warning_c")
        if not finite(warning) or arm["peak_c"] >= warning:
            reasons.append("NO_THERMAL_HEADROOM")
    if candidate["useful_per_second"] < reference["useful_per_second"] * 1.10:
        reasons.append("NO_TEN_PERCENT_USEFUL_THROUGHPUT_GAIN")
    if candidate["p95_latency_ms"] > reference["p95_latency_ms"] * 1.05:
        reasons.append("LATENCY_REGRESSION")
    return {"eligible": not reasons, "reasons": sorted(set(reasons))}


def approve_allocation(plan, reference, candidate):
    """Derive a higher plan only from a matched, safe, useful measured step."""
    verdict = scale_evidence(reference, candidate)
    if (
        not verdict["eligible"]
        or candidate.get("hardware_hash") != plan["hardware_hash"]
        or candidate.get("phase") != plan["phase"]
        or not 0 < candidate["cpu_cores"] <= plan["worker_cpu_ceiling"]
        or not 0 < candidate["memory_max_bytes"] <= plan["worker_memory_ceiling_bytes"]
        or reference["cpu_cores"] != plan["approved_cpu_cores"]
        or reference["memory_max_bytes"] != plan["approved_memory_bytes"]
        or candidate["cpu_cores"] > 2 * reference["cpu_cores"]
        or candidate["memory_max_bytes"] > 2 * reference["memory_max_bytes"]
        or any(arm.get("warning_c") != plan["thermal"]["throttle"] for arm in (reference, candidate))
    ):
        raise PipelineError("Scale step lacks matching safe evidence or exceeds host headroom")
    return {
        **plan,
        "approved_cpu_cores": candidate["cpu_cores"],
        "approved_memory_bytes": candidate["memory_max_bytes"],
        "scale_evidence_sha256": digest({"reference": reference, "candidate": candidate}),
    }


def cgroup_path(value):
    if not isinstance(value, str) or not value.startswith("/") or ".." in value.split("/"):
        raise PipelineError("Invalid cgroup path")
    path = PurePosixPath(value)
    if len(path.parts) < 4:
        raise PipelineError("Refuse broad host/user cgroup ownership")
    return path


def verify_containment(plan, roots, members):
    """Validate a complete adapter-supplied inventory with kernel readbacks.

    Roots may include separately bounded, owned containers. Nested roots are
    rejected to avoid double accounting. Unrelated services are never targets.
    Members include children/grandchildren and container init PIDs, not just PPID.
    """
    errors, paths, cpu_sum, memory_sum, pids_sum = [], [], 0.0, 0, 0
    if not roots or not members:
        return ["EMPTY_CONTAINMENT_INVENTORY"]
    try:
        for r in roots:
            path = cgroup_path(r["path"])
            if r.get("owned") is not True or not re.fullmatch(
                r"[a-f0-9]{64}", r.get("ownership_proof_sha256", "")
            ):
                errors.append("OWNERSHIP_UNVERIFIED")
            if any(path.is_relative_to(p) or p.is_relative_to(path) for p in paths):
                errors.append("OVERLAPPING_ACCOUNTING_ROOTS")
            paths.append(path)
            q, period = r["cpu.max"].split()
            q, period = int(q), int(period)
            maximum, high, swap, pids = (
                int(r[k]) for k in ("memory.max", "memory.high", "memory.swap.max", "pids.max")
            )
            if (
                q <= 0
                or period <= 0
                or not 0 < high <= maximum * 0.8
                or swap != 0
                or not 1 <= pids <= plan["tasks_max"]
            ):
                errors.append("LIMIT_READBACK_INVALID")
            cpu_sum += q / period
            memory_sum += maximum
            pids_sum += pids
            if (
                not r["cpuset"]
                or not set(r["cpuset"]) <= set(plan["cpu_ids"])
                or r.get("descendants_complete") is not True
                or r.get("KillMode") != "control-group"
                or r.get("Restart") != "no"
            ):
                errors.append("DESCENDANT_OR_LIFECYCLE_CONTROL_INVALID")
        seen = set()
        for member in members:
            identity = (member["pid"], member["start_ticks"])
            if identity in seen or any(type(x) is not int or x <= 0 for x in identity):
                errors.append("MEMBER_IDENTITY_INVALID")
            seen.add(identity)
            if member.get("owned") is not True:
                errors.append("UNRELATED_PROCESS_IN_TARGETS")
            path = cgroup_path(member["cgroup"])
            covering = [i for i, p in enumerate(paths) if path.is_relative_to(p)]
            if len(covering) != 1:
                errors.append("UNCOVERED_MEMBER_OR_CONTAINER")
            elif not member["affinity"] or not set(member["affinity"]) <= set(
                roots[covering[0]]["cpuset"]
            ):
                errors.append("AFFINITY_ESCAPE")
        if (
            cpu_sum > plan["approved_cpu_cores"] + 1e-9
            or memory_sum > plan["approved_memory_bytes"]
            or pids_sum > plan["tasks_max"]
        ):
            errors.append("AGGREGATE_BUDGET_EXCEEDED")
    except (KeyError, ValueError, TypeError, ZeroDivisionError, PipelineError):
        errors.append("INCOMPLETE_OR_UNBOUNDED_READBACK")
    return sorted(set(errors))


@dataclass(frozen=True)
class ResourceSample:
    now: float
    sampled_at: float
    temperature_c: float | None
    cpu_critical_c: float
    available_bytes: int
    cgroup_memory_bytes: int
    psi_full_avg10: float
    swap_bytes_per_second: float
    disk_free_bytes: int
    supervisor_healthy: bool
    watchdog_healthy: bool
    containment_verified: bool
    sensor_mapping_verified: bool
    hardware_alarm: bool = False
    oom_kill_delta: int = 0
    pids_max_delta: int = 0


class ResourceController:
    """Pure decisions; adapters must apply/read back actions before more work.

    Controller/supervisor heartbeat is checked even while worker is frozen.
    Critical stops latch for the attempt. Cooling alone cannot clear the latch.
    """

    def __init__(self, plan, *, cpu_cores=None, memory_bytes=None, slice_seconds=3600):
        self.plan = plan
        self.cpu = plan["approved_cpu_cores"] if cpu_cores is None else cpu_cores
        self.memory = plan["approved_memory_bytes"] if memory_bytes is None else memory_bytes
        if (
            not finite(self.cpu)
            or not 0 < self.cpu <= plan["approved_cpu_cores"]
            or not finite(self.memory)
            or not 0 < self.memory <= plan["approved_memory_bytes"]
            or not finite(slice_seconds)
            or not 0 < slice_seconds <= 3600
        ):
            raise PipelineError("Controller allocation exceeds contract")
        self.machine = ThermalMachine(
            ceiling=self.cpu * 100,
            maximum_ceiling=plan["approved_cpu_cores"] * 100,
        )
        self.started = self.last = self.checkpoint_since = None
        self.slice_seconds = slice_seconds
        self.terminal = None

    def stop(self, reason):
        if self.terminal is None:
            self.terminal = reason
        return {
            "state": "STOP_LATCHED",
            "reason": self.terminal,
            "action": "STOP_OWNED_CGROUPS",
            "auto_restart": False,
            "checkpoint_wait_allowed": False,
        }

    def update(self, sample: ResourceSample):
        if self.terminal:
            return self.stop(self.terminal)
        values = asdict(sample)
        required_numbers = [
            v
            for k, v in values.items()
            if k
            not in {
                "supervisor_healthy",
                "watchdog_healthy",
                "containment_verified",
                "sensor_mapping_verified",
                "hardware_alarm",
            }
        ]
        if any(not finite(v) or v < 0 for v in required_numbers):
            return self.stop("INVALID_TELEMETRY")
        if (
            not 0 < sample.temperature_c < 130
            or not 40 <= sample.cpu_critical_c <= 130
            or not 0 <= sample.now - sample.sampled_at <= self.plan["sample_max_age_seconds"]
            or self.last is not None
            and not 0 < sample.now - self.last <= 1
        ):
            return self.stop("SENSOR_STALE_OR_INVALID")
        self.last = sample.now
        if self.started is None:
            self.started = sample.now
        if sample.sensor_mapping_verified is not True:
            return self.stop("SENSOR_MAPPING_LOST")
        if sample.cpu_critical_c < self.plan["cpu_critical_c"]:
            return self.stop("HARDWARE_LIMIT_LOWERED")
        if sample.supervisor_healthy is not True or sample.watchdog_healthy is not True:
            return self.stop("WATCHDOG_OR_SUPERVISOR_LOST")
        if sample.containment_verified is not True:
            return self.stop("CONTAINMENT_LOST")
        if sample.oom_kill_delta or sample.pids_max_delta:
            return self.stop("OOM_OR_TASK_LIMIT")
        if sample.disk_free_bytes < 2 * GIB:
            return self.stop("CHECKPOINT_DISK_RESERVE_LOST")
        pressure = (
            sample.available_bytes < self.plan["os_reserve_bytes"]
            or sample.cgroup_memory_bytes >= self.memory * 0.8
            or sample.psi_full_avg10 >= 1
            or sample.swap_bytes_per_second >= 16 * MIB
        )
        result = self.machine.update(
            sample.now,
            sample.temperature_c,
            memory_pressure=pressure,
            hardware_emergency=(sample.hardware_alarm
                                or sample.temperature_c >= self.plan["thermal"]["hardware_stop_at_c"]),
        )
        if result["stop"]:
            return self.stop(result["reason"])
        # No grace period can overrule a thermal/sensor/containment stop.
        if sample.now - self.started >= self.slice_seconds:
            if self.checkpoint_since is None:
                self.checkpoint_since = sample.now
            if result["paused"] or sample.now - self.checkpoint_since >= 20:
                return self.stop("SLICE_CHECKPOINT_DEADLINE")
            return {
                "state": "DRAINING",
                "action": "CHECKPOINT_AND_EXIT",
                "auto_restart": False,
                "cpu_quota_percent_one_cpu": min(5, result["quota"]),
            }
        return {
            "state": result["state"],
            "action": "FREEZE" if result["paused"] else "APPLY_QUOTA",
            "cpu_quota_percent_one_cpu": result["quota"],
            "auto_restart": False,
            "pressure": pressure,
            "checkpoint_wait_allowed": not result["paused"],
        }


def resume_gate(
    *,
    terminal_reason,
    bindings_match,
    checkpoint_valid,
    used_previous,
    fresh_preflight,
    explicit_resume_request,
):
    """Same-attempt resume after a severe safety stop is always denied.

    A future reviewed child attempt must record a new resource/environment binding.
    Corrupt-latest fallback is disclosed and reviewed, never silently continued.
    """
    reasons = []
    if terminal_reason not in {"USER_PAUSE", "SLICE_COMPLETE", "GRACEFUL_PREEMPTION"}:
        reasons.append("TERMINAL_REQUIRES_REVIEWED_NEW_ATTEMPT")
    if any(
        v is not True
        for v in (bindings_match, checkpoint_valid, fresh_preflight, explicit_resume_request)
    ):
        reasons.append("RESUME_PREREQUISITE_FAILED")
    if used_previous is not False:
        reasons.append("ROLLBACK_REQUIRES_CURSOR_RECONCILIATION")
    return {"allowed": not reasons, "reasons": reasons}
