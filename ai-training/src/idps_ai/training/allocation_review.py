"""Explicit bounded-benchmark allocation review, without changing default budgets."""

import math

from idps_ai.common import PipelineError


def reviewed_plan(plan, evidence, cpu_cores, memory_bytes):
    """Authorize only the measured, explicitly reviewed request and fresh host cap.

    This is the short-experiment path explicitly authorized in R26.1. It does not
    replace the contract's 300-second production scale evidence or thermal gates.
    Evidence is pinned by digest in the Resource Adapter request before launch.
    """
    try:
        values = (
            cpu_cores,
            memory_bytes,
            evidence["reviewed_cpu_cores"],
            evidence["reviewed_memory_bytes"],
        )
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Invalid numeric allocation")
        benchmark = evidence["benchmark"]
        baseline = next(a for a in benchmark["arms"] if a["threads"] == 1)
        selected = next(
            a for a in benchmark["arms"] if a["threads"] == benchmark["selected_threads"]
        )
        safe = (
            evidence["version"] == "idps-r261-bounded-allocation-review-v1"
            and evidence["authorization_request_sha256"]
            and evidence["phase"] == plan["phase"]
            and evidence["hardware_hash"] == plan["hardware_hash"]
            and evidence["benchmark_guardian_verified"] is True
            and evidence["benchmark_cleanup_verified"] is True
            and evidence["benchmark_kernel_cpu_max"] == "400000 100000"
            and selected["threads"] == evidence["reviewed_cpu_cores"] == cpu_cores
            and memory_bytes
            <= evidence["reviewed_memory_bytes"]
            <= plan["worker_memory_ceiling_bytes"]
            and cpu_cores <= plan["worker_cpu_ceiling"]
            and selected["seconds"] > 0
            and selected["seconds"] <= baseline["seconds"] * 0.9
            and evidence["allow_production_scale_claim"] is False
        )
        if not safe:
            raise ValueError("Allocation review failed")
    except (KeyError, TypeError, StopIteration, ValueError) as exc:
        raise PipelineError("Unverified bounded allocation review") from exc
    return dict(
        plan,
        approved_cpu_cores=cpu_cores,
        approved_memory_bytes=memory_bytes,
        allocation_scope="R261_EXPLICIT_BOUNDED_RESEARCH_BENCHMARK",
    )


def worker_environment(spec, environment):
    """Thread limits must follow the validated worker request, not its caller env."""
    threads = spec.get("blas_threads", 1)
    if (
        type(threads) is not int
        or not 1 <= threads <= max(1, math.ceil(spec["cpu_percent"] / 100))
        or threads > 1
        and not spec.get("allocation_review")
    ):
        raise PipelineError("BLAS thread count exceeds reviewed worker allocation")
    result = dict(environment)
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        result[key] = str(threads)
    return result
