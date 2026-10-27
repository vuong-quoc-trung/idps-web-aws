"""Limits affect this training process only; never changes IDPS or host services."""

import os
import platform
import resource
from contextlib import contextmanager

import psutil

from idps_ai.common import PipelineError


def effective_cpus():
    return (
        sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else list(range(os.cpu_count() or 1))
    )


def configure_threads(requested=4):
    count = len(effective_cpus())
    threads = max(1, min(int(requested), max(1, count // 2)))
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


class MemoryGuard:
    def __init__(self, limit_bytes):
        self.limit_bytes = limit_bytes
        self.peak_rss_bytes = 0
        self.peak_tree_rss_bytes = 0

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
        return total >= self.limit_bytes


@contextmanager
def resource_envelope(max_threads=4, memory_limit_gib=12):
    if not 0.125 <= float(memory_limit_gib) <= 12:
        raise PipelineError("Memory limit must be 0.125–12 GiB (strictly below 16 GB)")
    if max_threads < 1:
        raise PipelineError("max-threads must be positive")
    cpus = effective_cpus()
    threads = configure_threads(max_threads)
    old_as = resource.getrlimit(resource.RLIMIT_AS)
    limit = int(memory_limit_gib * 1024**3)
    if old_as[0] != resource.RLIM_INFINITY:
        limit = min(limit, old_as[0])
    guard = MemoryGuard(limit)
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "effective_cpus_before_cap": cpus,
        "max_threads": threads,
        "memory_limit_bytes": limit,
        "total_host_memory_bytes": psutil.virtual_memory().total,
        "memory_guard": "process-tree RSS at optimizer boundaries",
        "hard_allocation_limit": "RLIMIT_AS soft ceiling, inherited by children; this trainer spawns none",
        "thermal_policy": "record sensors when available; no unverified universal temperature threshold",
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
        report.update(
            peak_rss_bytes=guard.peak_rss_bytes, peak_tree_rss_bytes=guard.peak_tree_rss_bytes
        )
        resource.setrlimit(resource.RLIMIT_AS, old_as)
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, set(cpus))
