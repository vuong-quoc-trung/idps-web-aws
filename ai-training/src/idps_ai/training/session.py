"""One bounded train session in a delegated systemd user cgroup v2."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import psutil
import yaml

from idps_ai.common import AI_ROOT, REPO_ROOT, PipelineError
from idps_ai.training.resources import effective_cpus


def session_command(arguments):
    from idps_ai.cli import parser

    options = parser().parse_args(["train", *arguments])
    if not options.readiness_report:
        raise PipelineError(
            "Formal sessions require --readiness-report bound to the current source and dataset"
        )
    config = yaml.safe_load(Path(options.config).read_text())
    envelope = config.get("resources", {})
    cpus = effective_cpus()
    threads = (
        options.max_threads if options.max_threads is not None else envelope.get("max_threads", 8)
    )
    memory = (
        options.memory_limit_gib
        if options.memory_limit_gib is not None
        else envelope.get("memory_limit_gib", 16)
    )
    duration = (
        options.max_duration_minutes
        if options.max_duration_minutes is not None
        else envelope.get("max_duration_minutes", 150)
    )
    if not 1 <= threads <= min(8, max(1, len(cpus) // 2)):
        raise PipelineError("Session CPU request exceeds 50% of effective host affinity")
    # The operator explicitly requested16GiB. Report its actual OS-visible
    # fraction rather than treating32GB and32GiB as interchangeable.
    if not 0.125 <= memory <= min(16, psutil.virtual_memory().total / 1024**3):
        raise PipelineError("Session RAM request exceeds the explicit16GiB ceiling or host RAM")
    if not 1 <= duration <= 180:
        raise PipelineError("Formal sessions must have a positive duration cap <=180 minutes")
    memory_bytes = int(memory * 1024**3)
    cpu_quota = min(float(threads), len(cpus) / 2)
    memory_high = min(15 * 1024**3, int(memory_bytes * 15 / 16))
    policy = {
        "cpu_quota_cores": cpu_quota,
        "memory_max_bytes": memory_bytes,
        "memory_high_bytes": memory_high,
        "memory_budget_basis": "explicit operator16GiB ceiling; not an assumed50% of OS-visible RAM",
        "memory_fraction_of_os_visible": memory_bytes / psutil.virtual_memory().total,
        "host_affinity_before_cap": cpus,
        "host_memory_bytes": psutil.virtual_memory().total,
    }
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        "--service-type=exec",
        "--unit=idps-ai-train-" + uuid.uuid4().hex[:10],
        "--working-directory=" + str(REPO_ROOT),
        "-p",
        f"CPUQuota={cpu_quota * 100:g}%",
        "-p",
        f"MemoryMax={memory_bytes}",
        "-p",
        f"MemoryHigh={memory_high}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "TasksMax=64",
        "-p",
        f"RuntimeMaxSec={int((duration + 10) * 60)}",
        "-p",
        "TimeoutStopSec=90",
        "-p",
        "Nice=10",
        "-E",
        "IDPS_AI_CGROUP_POLICY=" + json.dumps(policy, separators=(",", ":")),
        str(AI_ROOT / ".venv/bin/idps-ai"),
        "train",
        *arguments,
        "--max-threads",
        str(threads),
        "--memory-limit-gib",
        str(memory),
        "--max-duration-minutes",
        str(duration),
    ]
    return command, policy


def validate_formal_readiness(report_path, dataset):
    from idps_ai.data.capacity import validate_training_report

    report = validate_training_report(report_path, dataset)
    checks = {c["id"]: c["pass"] for c in report["checks"]}
    required = {"input_availability_profile", "real_eve_evidence", "window_300s_depth"}
    required.update(
        part + suffix
        for part in ("train", "val", "test")
        for suffix in ("_three_source_correlation", "_past_flow_coverage", "_long_campaigns")
    )
    if not all(checks.get(name) is True for name in required):
        raise PipelineError("Formal sessions require the three-source, long-window data gate")
    return report


def launch_session(arguments):
    from idps_ai.cli import parser

    options = parser().parse_args(["train", *arguments])
    command, _ = session_command(arguments)
    validate_formal_readiness(options.readiness_report, options.dataset)
    return subprocess.run(command, check=False).returncode


def probe_session(arguments, output):
    """Launch exactly the session cgroup envelope with a zero-optimizer probe."""
    command, policy = session_command(arguments)
    command = [
        part.replace("--unit=idps-ai-train-", "--unit=idps-ai-guard-probe-") for part in command
    ]
    child = command.index(str(AI_ROOT / ".venv/bin/idps-ai"))
    command = command[:child] + [
        str(AI_ROOT / ".venv/bin/python"),
        "-m",
        "idps_ai.training.resources",
        "--probe-output",
        str(Path(output).resolve()),
        "--cpus",
        str(int(policy["cpu_quota_cores"])),
        "--memory-limit-gib",
        str(policy["memory_max_bytes"] / 1024**3),
    ]
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise PipelineError("Resource guard probe failed; no training was started")
    return policy


if __name__ == "__main__":
    try:
        raise SystemExit(launch_session(sys.argv[1:]))
    except PipelineError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
