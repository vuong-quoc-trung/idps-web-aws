#!/usr/bin/env python3
"""Bind a fresh execution to immutable logical templates; never redesign or score."""

import argparse
import ast
import importlib.util
import json
import os
import subprocess
from pathlib import Path

from idps_ai.common import atomic_json, digest, file_sha256

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "ai-training/.artifacts/request_v3_final_20261108/campaign-v3/plan.json"
EXECUTION = "request-v3-grounded-20261108-r1"


def collector():
    p = Path(__file__).with_name("request-v3-final-controls.py")
    s = importlib.util.spec_from_file_location("grounded_collector", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    m.RUN = EXECUTION
    return m


def lock(output):
    c = collector()
    # Verify template/role/Oracle functions against committed logical parent.
    old = ast.parse(
        subprocess.check_output(
            ["git", "show", "33e0b0d:ai-training/scripts/request-v3-final-controls.py"], text=True
        )
    )
    new = ast.parse(Path(c.__file__).read_text())

    def functions(tree):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
        }

    a, b = functions(old), functions(new)
    assert all(a[k] == b[k] for k in ["cases", "run_case", "preaudit", "php_authenticated"])
    parent = json.loads(PARENT.read_text())
    addendum = json.loads(
        (ROOT / "ai-training/configs/research/command-oracle-sandbox-20261108.json").read_text()
    )
    assert addendum["parent_precommit"]["plan_fingerprint"] == parent["fingerprint"]
    assert addendum["fingerprint"] == digest(
        {k: v for k, v in addendum.items() if k != "fingerprint"}
    )
    c.prepare(output)
    p = output / "plan.json"
    plan = json.loads(p.read_text())
    assert all(
        plan[k] == parent[k]
        for k in [
            "cases",
            "preflight_case_ids",
            "oracles",
            "coverage",
            "expected_availability",
            "duplicates",
            "images",
        ]
    )
    images = {}
    for kind, image in plan["images"].items():
        d = json.loads(subprocess.check_output(["podman", "image", "inspect", image]))[0]
        images[kind] = {"image_id": d["Id"], "repo_digests": d["RepoDigests"]}
    env = {
        "schema_version": "grounded-capture-environment-1",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "execution_id": EXECUTION,
        "images": images,
        "addendum_fingerprint": addendum["fingerprint"],
        "namespace_app_sysctl": "net.ipv4.ping_group_range=33 33",
        "host_sysctl_before": Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip(),
        "security": "Same internal lab,no-new-privileges,no cap-add,UID33app,loopback19280",
        "oracle_contract_version": "locked-final-controls-v1",
        "recovery_report_sha256": file_sha256(
            ROOT / "ai-training/reports/COMMAND_ORACLE_SANDBOX_RECOVERY_20261108.json"
        ),
    }
    env["fingerprint"] = digest(env)
    atomic_json(output / "environment-rebind.json", env)
    plan.update(
        logical_parent_plan_fingerprint=parent["fingerprint"],
        logical_parent_plan_file_sha256=file_sha256(PARENT),
        environment_fingerprint=env["fingerprint"],
        execution_rebind_source_sha256=file_sha256(__file__),
        previous_preflight_accounting={
            "previous_campaign_completed_receipts": 1,
            "previous_possible_dispatch_upper_bound": 2,
            "recovery_HTTP_diagnostics": 2,
            "new_preflight_representatives": 9,
            "reused_old_UNKNOWN": False,
            "main_cohort_previous": 0,
            "remaining_main_budget": 24,
        },
        execution_source_bindings={c.__file__: file_sha256(c.__file__)},
        bookkeeping_note="Physical IDs/environment revision only. Parent roles/templates/Oracle/coverage immutable. Conservative new21targeted receipts incl9preflight,12main; no replacement/filler.",
    )
    plan.pop("fingerprint")
    plan["fingerprint"] = digest(plan)
    atomic_json(p, plan)
    print(
        json.dumps(
            {
                "plan_fingerprint": plan["fingerprint"],
                "environment_fingerprint": env["fingerprint"],
                "execution_id": EXECUTION,
                "preaudit": plan["preaudit"],
                "templates": len(plan["cases"]),
                "preflight": len(plan["preflight_case_ids"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    lock(a.output.resolve())
