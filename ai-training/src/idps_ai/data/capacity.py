"""Pre-training hardware/data capacity estimate; never performs optimization."""

import os
import platform
import shutil
import time
from pathlib import Path

import psutil

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.snapshot import new_destination


def capacity_check(dataset, output, max_threads=8, effective_cpus_before_cap=None):
    manifest = verify_dataset(dataset, "prepared")
    output = new_destination(output)
    current_affinity = sorted(os.sched_getaffinity(0))
    available_cpus = (
        list(effective_cpus_before_cap)
        if effective_cpus_before_cap is not None
        else current_affinity
    )
    if not 1 <= max_threads <= max(1, len(available_cpus) // 2):
        raise PipelineError("Thread request exceeds half effective affinity")
    before = time.monotonic()
    rows = 0
    for row in iter_rows(Path(dataset) / "features.parquet", columns=["x"]):
        rows += 1
        if len(row["x"]) != manifest["feature_count"]:
            raise PipelineError("Invalid feature width")
    elapsed = time.monotonic() - before
    n_features = manifest["feature_count"]
    cache_bytes = rows * (n_features * 4 + 8)
    free = shutil.disk_usage(Path(dataset)).free
    memory = psutil.virtual_memory()
    enough = free > max(256 * 1024**2, cache_bytes * 6) and memory.available > 512 * 1024**2
    result = {
        "format_version": 1,
        "status": "CAPACITY_ESTIMATE_PASS" if enough else "NOT_READY",
        "training_executed": False,
        "dataset_sha256": manifest["dataset_sha256"],
        "python": platform.python_version(),
        "platform": platform.system(),
        "host_total_memory_bytes": memory.total,
        "available_memory_bytes": memory.available,
        "available_cpus_before_cap": available_cpus,
        "current_affinity": current_affinity,
        "requested_max_threads": max_threads,
        "proposed_memory_limit_gib": 16,
        "disk_free_bytes": free,
        "feature_rows": rows,
        "feature_count": n_features,
        "feature_cache_estimate_bytes": cache_bytes,
        "stream_read_wall_seconds": elapsed,
        "stream_rows_per_second": rows / max(elapsed, 1e-9),
        "sampled_process_rss_bytes": psutil.Process().memory_info().rss,
        "requirements_sha256": file_sha256(AI_ROOT / "requirements.txt"),
        "limits": [
            "Read-only I/O/capacity estimate, not a training-speed/thermal/endurance benchmark",
            "No cgroup controller or machine power profile changed",
            "This host is not assumed to be the target Zenbook",
            "Actual epoch duration must be measured by a later authorized pilot training run",
        ],
    }
    result["report_sha256"] = digest(result)
    atomic_json(output, result)
    return result


def validate_training_report(report_path, dataset):
    report = load_json(report_path)
    checksum = report.pop("report_sha256", None)
    if (
        digest(report) != checksum
        or report.get("status") != "READY_FOR_OFFLINE_PILOT"
        or report.get("offline_pilot_training_permitted") is not True
        or not all(c["pass"] for c in report["checks"])
    ):
        raise PipelineError("Training readiness report is invalid or NOT_READY")
    if report["dataset_sha256"] != verify_dataset(dataset, "prepared")["dataset_sha256"]:
        raise PipelineError("Training readiness references a different dataset")
    actual = {
        str(p.relative_to(AI_ROOT)): file_sha256(p) for p in sorted((AI_ROOT / "src").rglob("*.py"))
    }
    if report.get("source_files_sha256") != actual:
        raise PipelineError("Source changed after readiness; rerun the data gate")
    return report
