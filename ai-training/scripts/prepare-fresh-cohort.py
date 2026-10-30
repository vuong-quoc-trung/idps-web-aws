#!/usr/bin/env python3
"""Collect a single immutable held-out cohort; never manufacture train/val roles."""

import argparse
import json
import os
import secrets
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import collect
from idps_ai.data.provenance import scope_capture_inputs
from idps_ai.data.readers import Input
from idps_ai.data.snapshot import new_destination
from idps_ai.training.resources import resource_envelope


def run(lab, eve, output):
    lab = Path(lab)
    output = new_destination(output)
    marker = load_json(lab / "owned-lab.json")
    capture = load_json(lab / "capture-result.json")
    if (
        marker.get("purpose") != "ai-pretrain-disposable"
        or capture.get("scenario_version") != "request-challenge-1"
    ):
        raise PipelineError("Explicitly owned new temporal cohort is required")
    if file_sha256(lab / "observer.jsonl") != capture["observer_sha256"]:
        raise PipelineError("Fresh observer changed after capture")
    output.mkdir(mode=0o700)
    key = secrets.token_bytes(32)
    (output / "redaction.key").write_bytes(key)
    os.chmod(output / "redaction.key", 0o600)
    approved = pending = 0
    with (output / "labels.jsonl").open("x") as dest, (lab / "observer.jsonl").open() as source:
        for line in source:
            row = json.loads(line)
            if (
                row["review_status"] != "approved"
                or row["status_code"] not in row["expected_status_codes"]
            ):
                pending += 1
                continue
            # Carry the existing automated annotation; never upgrade pending cases.
            value = {
                k: row[k]
                for k in [
                    "request_id",
                    "campaign_id",
                    "label",
                    "attack_family",
                    "label_source",
                    "label_confidence",
                    "review_status",
                ]
            }
            dest.write(json.dumps(value) + "\n")
            approved += 1
    (output / "labels.jsonl").chmod(0o600)
    inputs = [
        Input("student", lab / "student-audit.log"),
        Input("nginx", lab / "access.log"),
        Input("suricata", Path(eve)),
    ]
    scope = scope_capture_inputs(
        inputs, lab / "observer.jsonl", lab / "capture-result.json", output / "scoped"
    )
    scoped = [Input(v["source"], output / "scoped" / v["file"]) for v in scope["inputs"]]
    collected = collect(
        scoped,
        output / "collected",
        key,
        output / "labels.jsonl",
        input_profile="safe_query_numeric_v2",
    )
    result = {
        "status": "COLLECTED_HELD_OUT_ONLY",
        "approved_automated_intent_contracts": approved,
        "pending": pending,
        "capture_sha256": file_sha256(lab / "capture-result.json"),
        "observer_sha256": capture["observer_sha256"],
        "dataset_sha256": collected["dataset_sha256"],
        "no_training_partition_created": True,
        "human_review": False,
        "scope_manifest_sha256": file_sha256(output / "scoped/scope_manifest.json"),
    }
    atomic_json(output / "manifest.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab", required=True)
    p.add_argument("--eve", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with resource_envelope(2, 12):
        print(json.dumps(run(a.lab, a.eve, a.output), sort_keys=True))
