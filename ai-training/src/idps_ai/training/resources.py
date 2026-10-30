"""Limits affect this training process only; never changes IDPS or host services."""

import json
import math
import os
import platform
import resource
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

from idps_ai.common import PipelineError


def effective_cpus():
    return (
        sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else list(range(os.cpu_count() or 1))
    )


def configure_threads(requested=8):
    count = len(effective_cpus())
    threads = max(1, min(int(requested), 8, max(1, count // 2)))
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[name] = str(threads)
    os.environ["OMP_MAX_ACTIVE_LEVELS"] = "1"
    return threads


def cgroup_readback():
    try:
        membership = Path("/proc/self/cgroup").read_text().strip().split(":", 2)[2]
        root = Path("/sys/fs/cgroup") / membership.lstrip("/")
        return {
            "path": membership,
            **{
                name: (root / name).read_text().strip()
                for name in (
                    "cpu.max",
                    "memory.max",
                    "memory.high",
                    "memory.swap.max",
                    "memory.current",
                    "memory.peak",
                    "memory.events",
                    "cpu.stat",
                )
            },
        }
    except (OSError, IndexError):
        return {"status": "unavailable"}


class MemoryGuard:
    def __init__(self, limit_bytes):
        self.limit_bytes = limit_bytes
        self.peak_rss_bytes = 0
        self.peak_tree_rss_bytes = 0
        self.thermal_limit_reached = False
        self.last_sensor_sample = -math.inf
        self.peak_cpu_temperature_celsius = None
        self.thermal_stop_threshold_celsius = None
        self.temperature_monitoring = "unavailable"

    def metrics(self):
        return {
            name: getattr(self, name)
            for name in (
                "peak_rss_bytes",
                "peak_tree_rss_bytes",
                "peak_cpu_temperature_celsius",
                "thermal_stop_threshold_celsius",
                "temperature_monitoring",
                "thermal_limit_reached",
            )
        }

    def check(self):
        process = psutil.Process()
        rss = process.memory_info().rss
        total = rss
        for child in process.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                pass
        self.peak_rss_bytes = max(rss, self.peak_rss_bytes)
        self.peak_tree_rss_bytes = max(total, self.peak_tree_rss_bytes)
        if time.monotonic() - self.last_sensor_sample >= 5:
            self.last_sensor_sample = time.monotonic()
            try:
                sensors = psutil.sensors_temperatures()
            except (AttributeError, OSError, RuntimeError):
                sensors = {}
            for driver, readings in sensors.items():
                if driver not in ("coretemp", "k10temp", "zenpower"):
                    continue
                for sensor in readings:
                    if sensor.current is None or not math.isfinite(sensor.current):
                        continue
                    self.temperature_monitoring = "available_no_hardware_critical_limit"
                    self.peak_cpu_temperature_celsius = max(
                        self.peak_cpu_temperature_celsius or sensor.current, sensor.current
                    )
                    if sensor.critical and math.isfinite(sensor.critical):
                        threshold = float(sensor.critical) - 5.0
                        self.thermal_stop_threshold_celsius = min(
                            self.thermal_stop_threshold_celsius or threshold, threshold
                        )
                        self.thermal_limit_reached |= sensor.current >= threshold
            if self.thermal_stop_threshold_celsius is not None:
                self.temperature_monitoring = "hardware_critical_limit_available"
        return total >= self.limit_bytes


@contextmanager
def resource_envelope(max_threads=8, memory_limit_gib=16):
    if not 0.125 <= float(memory_limit_gib) <= 16:
        raise PipelineError("Memory limit must be 0.125–16 GiB (explicit operator ceiling)")
    if max_threads < 1:
        raise PipelineError("max-threads must be positive")
    cpus = effective_cpus()
    threads = configure_threads(max_threads)
    old_as = resource.getrlimit(resource.RLIMIT_AS)
    limit = int(memory_limit_gib * 1024**3)
    if old_as[0] != resource.RLIM_INFINITY:
        limit = min(limit, old_as[0])
    if limit > psutil.virtual_memory().total:
        raise PipelineError("Requested RAM limit exceeds OS-visible host memory")
    guard = MemoryGuard(limit)
    cgroup = cgroup_readback()
    if os.environ.get("IDPS_AI_CGROUP_POLICY"):
        policy = json.loads(os.environ["IDPS_AI_CGROUP_POLICY"])
        try:
            quota, period = cgroup["cpu.max"].split()
            valid = (
                quota != "max"
                and int(quota) / int(period) <= policy["cpu_quota_cores"]
                and int(cgroup["memory.max"]) <= policy["memory_max_bytes"]
                and cgroup["memory.swap.max"] == "0"
                and (
                    policy.get("memory_high_bytes") is None
                    or int(cgroup["memory.high"]) <= policy["memory_high_bytes"]
                )
            )
        except (KeyError, ValueError):
            valid = False
        if not valid:
            raise PipelineError(
                "Delegated CPU/RAM/swap cgroup limits failed readback; refusing training"
            )
    report = {
        "cgroup_v2": cgroup,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "effective_cpus_before_cap": cpus,
        "max_threads": threads,
        "memory_limit_bytes": limit,
        "total_host_memory_bytes": psutil.virtual_memory().total,
        "memory_guard": "process-tree RSS at optimizer boundaries",
        "hard_allocation_limit": "RLIMIT_AS soft ceiling, inherited by children; this trainer spawns none",
        "thermal_policy": "sample CPU sensors at most every5seconds; clean stop within5C of sensor-reported critical limit; unavailable sensors explicitly recorded",
    }
    try:
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, set(cpus[:threads]))
            report["affinity_effective"] = effective_cpus()
        resource.setrlimit(resource.RLIMIT_AS, (limit, old_as[1]))
        report["address_space_limit_effective"] = resource.getrlimit(resource.RLIMIT_AS)[0]
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=threads):
            yield guard, report
    finally:
        guard.check()
        report.update(guard.metrics())
        resource.setrlimit(resource.RLIMIT_AS, old_as)
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, set(cpus))


def probe_resources(output, max_threads=8, memory_limit_gib=16):
    """Read actual controller/thread limits; no dataset, optimizer or fitted model."""
    from idps_ai.common import atomic_json

    with resource_envelope(max_threads, memory_limit_gib) as (_, report):
        import numpy as np
        from threadpoolctl import threadpool_info

        from idps_ai.export.onnx import session_options

        # Load BLAS but perform no training or model creation.
        np.zeros((1,), dtype=np.float32)
        options = session_options(report["max_threads"])
        report.update(
            purpose="resource guard initialization only",
            optimizer_steps=0,
            training_executed=False,
            thread_environment={
                name: os.environ[name]
                for name in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            },
            blas_pools=threadpool_info(),
            onnx_intra_op_threads=options.intra_op_num_threads,
            onnx_inter_op_threads=options.inter_op_num_threads,
            onnx_execution_mode=str(options.execution_mode),
        )
        if any(p["num_threads"] > report["max_threads"] for p in report["blas_pools"]):
            raise PipelineError("BLAS pool exceeds the requested CPU budget")
    atomic_json(output, report)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize a resource guard without training")
    parser.add_argument("--probe-output", required=True)
    parser.add_argument("--cpus", type=int, default=8)
    parser.add_argument("--memory-limit-gib", type=float, default=16)
    args = parser.parse_args()
    probe_resources(args.probe_output, args.cpus, args.memory_limit_gib)
