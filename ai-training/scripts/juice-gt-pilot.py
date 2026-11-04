#!/usr/bin/env python3
"""Bounded, local-only Juice Shop evidence pilot; never formal admission."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from idps_ai.common import (
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.training.resources import resource_envelope

CONTAINER = "ai-idps-juice-gt-20261104"
NETWORK = "ai-idps-gt-lab-20261104"
IMAGE = "sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f"
PORT = 13080
CASES = (
    ("benign-apple", "benign", "apple", "apple", None),
    ("benign-orange", "benign", "orange", "orange", None),
    ("benign-banana", "benign", "banana", "banana", None),
    ("benign-apostrophe", "benign", "O'Connor", None, None),
    ("attack-sqli", "attack", "' OR 1=1--", None, "sqli"),
    ("attack-xss", "attack", "<script>alert(1)</script>", None, "xss"),
    ("attack-traversal", "attack", "../../etc/passwd", None, "traversal"),
    ("attack-command", "attack", ";id", None, "command"),
)


def _podman(*args):
    return subprocess.check_output(["podman", *args], text=True, timeout=15).strip()


def _preflight():
    info = json.loads(_podman("inspect", CONTAINER))[0]
    network = json.loads(_podman("network", "inspect", NETWORK))[0]
    ports = info["NetworkSettings"]["Ports"]["3000/tcp"]
    image_id = info["Image"]
    if (
        info["State"]["Status"] != "running"
        or NETWORK not in info["NetworkSettings"]["Networks"]
        or not network["internal"]
        or ports != [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]
        or IMAGE not in _podman("image", "inspect", image_id, "--format", "{{json .RepoDigests}}")
    ):
        raise PipelineError("Juice Shop is not the pinned loopback-only internal-network lab")
    return {
        "container_id": info["Id"],
        "image_id": image_id,
        "network": NETWORK,
        "internal": True,
        "host": "127.0.0.1",
        "port": PORT,
    }


def prepare(output):
    output = Path(output)
    if output.exists():
        raise PipelineError("Pilot plan output exists")
    identity = _preflight()
    plan = {
        "format_version": 1,
        "scope": "controlled_local_juice_shop_development_pilot_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": identity,
        "image_digest": IMAGE,
        "script_sha256": file_sha256(__file__),
        "label_rules": {
            "benign_verified": "Precommitted ordinary product search, matching application JSON response and expected product name where specified; HTTP 200 alone insufficient",
            "attack_attempt_verified": "Precommitted security test query reaches pinned local target and gets target response; request-bound test intent only, not independent semantic review or exploit success",
            "exploit_success_verified": "Requires separate application-state or challenge Oracle; this pilot has no such Oracle and must report zero",
            "unknown": "Any missing/mismatched request, target, response or JSON semantic evidence",
        },
        "cases": [
            {
                "case_id": name,
                "campaign_id": "juice-gt-pilot-20261104-"
                + ("benign" if intent == "benign" else family),
                "intent": intent,
                "family": family,
                "method": "GET",
                "path": "/rest/products/search?q=" + quote(query, safe=""),
                "query": query,
                "expected_product_name_contains": expected,
                "request_id": hashlib.sha256((name + ":" + query).encode()).hexdigest()[:32],
            }
            for name, intent, query, expected, family in CASES
        ],
        "partition": "development_pilot_only_no_train_or_evaluation_assignment",
        "fpr_budget": 0.01,
        "formal_admission": False,
    }
    plan["plan_sha256"] = digest(plan)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, plan)
    output.chmod(0o600)
    return plan


def run(plan_path, output):
    plan_path, output = Path(plan_path), Path(output)
    if output.exists():
        raise PipelineError("Pilot run output exists")
    plan = load_json(plan_path)
    if plan.get("plan_sha256") != digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise PipelineError("Pilot plan hash mismatch")
    if plan["script_sha256"] != file_sha256(__file__) or plan["target"] != _preflight():
        raise PipelineError("Pilot code or isolated target changed after plan lock")
    expected = [
        (name, intent, query, product, family) for name, intent, query, product, family in CASES
    ]
    actual = [
        (c["case_id"], c["intent"], c["query"], c["expected_product_name_contains"], c["family"])
        for c in plan["cases"]
    ]
    if actual != expected or len({c["request_id"] for c in plan["cases"]}) != len(CASES):
        raise PipelineError("Pilot cases differ from approved local-only script")
    output.mkdir(parents=True, mode=0o700)
    observations = []
    for case in plan["cases"]:
        started = datetime.now(timezone.utc).isoformat()
        connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
        request_headers = {"X-Request-Id": case["request_id"], "Accept": "application/json"}
        response = None
        body = b""
        error = None
        try:
            connection.request("GET", case["path"], headers=request_headers)
            response = connection.getresponse()
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise PipelineError("Oversized Juice Shop response")
        except (OSError, PipelineError) as exc:
            error = type(exc).__name__
        finally:
            connection.close()
        ended = datetime.now(timezone.utc).isoformat()
        response_path = output / (case["case_id"] + ".response")
        with response_path.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        response_path.chmod(0o600)
        parsed = None
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            pass
        valid_json = (
            isinstance(parsed, dict)
            and parsed.get("status") == "success"
            and isinstance(parsed.get("data"), list)
        )
        product_match = (
            bool(
                valid_json
                and any(
                    case["expected_product_name_contains"] in str(x.get("name", "")).lower()
                    for x in parsed["data"]
                )
            )
            if case["expected_product_name_contains"]
            else None
        )
        response_observed = response is not None and body and error is None
        if case["intent"] == "benign":
            label = (
                "BENIGN_VERIFIED_LAB"
                if response_observed and valid_json and (product_match is not False)
                else "UNKNOWN"
            )
        else:
            label = "ATTACK_ATTEMPT_VERIFIED_LAB" if response_observed and valid_json else "UNKNOWN"
        observations.append(
            {
                "case_id": case["case_id"],
                "campaign_id": case["campaign_id"],
                "request_id": case["request_id"],
                "started_at": started,
                "ended_at": ended,
                "method": "GET",
                "path": case["path"],
                "request_sha256": hashlib.sha256(
                    canonical_bytes(["GET", case["path"], request_headers])
                ).hexdigest(),
                "response_status": response.status if response else None,
                "response_sha256": file_sha256(response_path),
                "response_bytes": len(body),
                "app_json_semantics": valid_json,
                "expected_product_match": product_match,
                "publisher_or_model_label_used": False,
                "intent_label": label,
                "exploit_outcome": "UNKNOWN",
                "student_log": False,
                "nginx_log": False,
                "suricata_eve": False,
                "error": error,
            }
        )
    report = {
        "format_version": 1,
        "scope": "single isolated Juice Shop lab, controlled researcher intent; development only",
        "plan_file_sha256": file_sha256(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "script_sha256": file_sha256(__file__),
        "target": plan["target"],
        "image_digest": IMAGE,
        "requests_sent": len(observations),
        "unique_request_representations": len({x["request_sha256"] for x in observations}),
        "benign_verified_lab": sum(
            x["intent_label"] == "BENIGN_VERIFIED_LAB" for x in observations
        ),
        "attack_attempt_verified_lab": sum(
            x["intent_label"] == "ATTACK_ATTEMPT_VERIFIED_LAB" for x in observations
        ),
        "exploit_success_verified": 0,
        "unknown_intent": sum(x["intent_label"] == "UNKNOWN" for x in observations),
        "three_source_correlated": 0,
        "formal_admitted": 0,
        "evidence": observations,
        "limits": "Target response confirms local HTTP execution, but no application challenge/state oracle, Nginx, Student or EVE; collector-controlled intent is not independent or formal Ground Truth. No training/evaluation on this tiny pilot.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    with resource_envelope(2, 4):
        result = prepare(args.plan) if args.action == "prepare" else run(args.plan, args.output)
    print(
        {k: result[k] for k in ("plan_sha256",) if k in result}
        | {
            k: result[k]
            for k in (
                "requests_sent",
                "benign_verified_lab",
                "attack_attempt_verified_lab",
                "unknown_intent",
            )
            if k in result
        }
    )
