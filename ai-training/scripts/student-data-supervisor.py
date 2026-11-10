#!/usr/bin/env python3
"""Reuse active-time guard + independent service watchdog, force85C, no training."""

import argparse
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

from idps_ai.common import atomic_json


def main(root, quota=20):
    s = importlib.util.spec_from_file_location(
        "active", Path(__file__).with_name("scaled-active-supervisor.py")
    )
    active = importlib.util.module_from_spec(s)
    s.loader.exec_module(active)
    original = active.module

    def module(name):
        m = original(name)
        if name == "integration-guard":
            run = m.run

            def guarded(*args, **kw):
                kw["cutoff"] = 85
                return run(*args, **kw)

            m.run = guarded
        return m

    active.module = module
    try:
        active.run(
            SimpleNamespace(
                output=str(root / "resource"),
                experiment_root=str(root),
                quota=quota,
                memory_gib=8,
                max_seconds=10800,
                command=[
                    "--",
                    str(Path(__import__("sys").executable)),
                    str(Path(__file__).with_name("student-data-pipeline.py")),
                    "--root",
                    str(root),
                    "--action",
                    "worker",
                ],
            )
        )
        assert json.loads((root / "completion.json").read_text())["state"] == "COMPLETED"
        resource = json.loads((root / "resource/resource-report.json").read_text())
        assert resource["status"] == "PASS"
        atomic_json(
            root / "supervisor-result.json",
            {
                "state": "COMPLETED",
                "verified_completion": True,
                "resource_status": "PASS",
                "completed_at": time.time(),
            },
        )
    except BaseException as exc:
        rpath = root / "resource/resource-report.json"
        resource = json.loads(rpath.read_text()) if rpath.exists() else {}
        reason = str(resource.get("failure") or "")
        state = (
            "THERMAL_STOPPED"
            if any(k in reason.lower() for k in ["thermal", "temperature"])
            or (root / "resource/active-thermal-stop.json").exists()
            else "FAILED"
        )
        prior = (
            json.loads((root / "status.json").read_text())
            if (root / "status.json").exists()
            else {}
        )
        atomic_json(
            root / "status.json",
            {
                **prior,
                "state": state,
                "error_type": type(exc).__name__,
                "last_heartbeat": time.time(),
                "model_training": "NOT_STARTED",
            },
        )
        atomic_json(
            root / "supervisor-result.json",
            {"state": state, "resource_failure": reason, "error_type": type(exc).__name__},
        )
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--quota", type=int, default=20)
    a = p.parse_args()
    main(a.root.resolve(), a.quota)
