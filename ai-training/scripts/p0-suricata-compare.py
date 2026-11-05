#!/usr/bin/env python3
"""Unchanged repository HTTP signatures on real P0 PCAP; request-bound comparison."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from idps_ai.common import AI_ROOT, REPO_ROOT, atomic_json, digest, file_sha256, load_json


def compare(capture, evaluation, output):
    capture, evaluation, output = [Path(p).resolve() for p in [capture, evaluation, output]]
    output.mkdir(mode=0o700, exist_ok=False)
    os.umask(0o077)
    runtime = AI_ROOT / ".artifacts/upgrade_20261028/tools/runtime"
    binary = runtime / "usr/bin/suricata"
    original = REPO_ROOT / "security-web/config/suricata/suricata.yaml"
    rules = REPO_ROOT / "security-web/suricata/pbl4.rules"
    pcap = capture / "traffic.pcap"
    plan = load_json(capture / "plan.json")
    inspection = load_json(next(capture.glob("*-app-inspect.json")))
    app_ip = next(iter(inspection["NetworkSettings"]["Networks"].values()))["IPAddress"]
    config = yaml.safe_load(original.read_text())
    config["vars"]["address-groups"]["HOME_NET"] = f"[{app_ip}/32]"
    config["vars"]["port-groups"]["HTTP_PORTS"] = "80"
    config["outputs"] = [
        {
            "eve-log": {
                "enabled": True,
                "filetype": "regular",
                "filename": "eve.json",
                "types": [
                    {"alert": {"payload": False, "packet": False}},
                    {"http": {"extended": True, "dump-all-headers": "both"}},
                    "flow",
                    {"stats": {"totals": True, "threads": False}},
                ],
            }
        }
    ]
    config["default-rule-path"] = str(rules.parent)
    config["rule-files"] = [str(rules)]
    for filename in ["classification", "reference-config", "threshold"]:
        config[filename + "-file"] = str(
            runtime
            / "etc/suricata"
            / {
                "classification": "classification.config",
                "reference-config": "reference.config",
                "threshold": "threshold.config",
            }[filename]
        )
    config["unix-command"] = {"enabled": False}
    config.setdefault("detect", {})["sgh-mpm-caching"] = False
    config["logging"] = {"default-log-level": "notice", "outputs": [{"console": {"enabled": True}}]}
    config["default-log-dir"] = str(output)
    (output / "suricata.yaml").write_text(
        "%YAML 1.1\n---\n" + yaml.safe_dump(config, sort_keys=False)
    )
    comparison_plan = {
        "capture_plan_sha256": plan["plan_sha256"],
        "pcap_sha256": file_sha256(pcap),
        "rules_sha256": file_sha256(rules),
        "binary_sha256": file_sha256(binary),
        "original_config_sha256": file_sha256(original),
        "config_sha256": file_sha256(output / "suricata.yaml"),
        "script_sha256": file_sha256(__file__),
        "included_sids": list(range(1000002, 1000010)),
        "excluded_from_http_baseline": {
            "1000001": "SYN-rate signature; not request semantic classifier; all alerts still reported"
        },
        "binding": "X-Request-Id request header on EVE HTTP transaction; flow_id+tx_id for HTTP alerts",
        "scope": "offline real packet HTTP-signature baseline; not Rust stateful rules, app rules, production or independent Ground Truth",
        "tuning": False,
    }
    comparison_plan["plan_sha256"] = digest(comparison_plan)
    atomic_json(output / "comparison-plan.json", comparison_plan)
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / "usr/lib/x86_64-linux-gnu"))
    command = [
        str(binary),
        "-c",
        str(output / "suricata.yaml"),
        "--runmode",
        "single",
        "-k",
        "none",
        "-r",
        str(pcap),
        "-l",
        str(output),
        "--set",
        "detect.profile=low",
        "--set",
        "max-pending-packets=1024",
    ]
    with (output / "decode.log").open("xb") as log:
        subprocess.run(command, env=env, stdout=log, stderr=log, timeout=180, check=True)
    events = [json.loads(line) for line in (output / "eve.json").read_text().splitlines()]
    transaction_ids = {}
    for event in events:
        if event["event_type"] != "http":
            continue
        headers = event.get("http", {}).get("request_headers", [])
        ids = [h["value"] for h in headers if h.get("name", "").lower() == "x-request-id"]
        if len(ids) == 1:
            key = (event["flow_id"], event.get("tx_id", event["http"].get("tx_id", 0)))
            if key in transaction_ids:
                raise RuntimeError("Ambiguous Suricata transaction binding")
            transaction_ids[key] = ids[0]
    expected = {c["request_id"] for c in plan["cases"]}
    if set(transaction_ids.values()) != expected or len(transaction_ids) != len(expected):
        atomic_json(
            output / "binding-failure.json",
            {
                "expected": len(expected),
                "bound": len(transaction_ids),
                "http_fields_seen": [
                    list(e.get("http", {}).keys()) for e in events if e["event_type"] == "http"
                ][:2],
            },
        )
        raise RuntimeError("Cannot compare signatures without complete unique request-ID binding")
    flagged, unbound, all_sids = defaultdict(list), [], Counter()
    for event in events:
        if event["event_type"] != "alert":
            continue
        sid = event["alert"]["signature_id"]
        all_sids[sid] += 1
        if sid not in comparison_plan["included_sids"]:
            continue
        key = (event["flow_id"], event.get("tx_id", 0))
        rid = transaction_ids.get(key)
        if rid is None:
            unbound.append(sid)
        else:
            flagged[rid].append(sid)
    if unbound:
        raise RuntimeError("HTTP alert cannot be bound to a cohort request")
    spec = importlib.util.spec_from_file_location(
        "p0_eval", AI_ROOT / "scripts/p0-request-evaluate.py"
    )
    evaluation_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation_module)
    ai = [json.loads(line) for line in (evaluation / "predictions.jsonl").read_text().splitlines()]
    rows = [
        dict(
            r,
            ai_flagged=r["flagged"],
            flagged=r["request_id"] in flagged,
            signature_ids=flagged[r["request_id"]],
        )
        for r in ai
    ]
    joined = {
        "AI_only_attack_case_ids": [
            r["case_id"]
            for r in rows
            if r["lab_intent"] == "attack" and r["ai_flagged"] and not r["flagged"]
        ],
        "rules_only_attack_case_ids": [
            r["case_id"]
            for r in rows
            if r["lab_intent"] == "attack" and r["flagged"] and not r["ai_flagged"]
        ],
        "both_attack_case_ids": [
            r["case_id"]
            for r in rows
            if r["lab_intent"] == "attack" and r["flagged"] and r["ai_flagged"]
        ],
        "neither_attack_case_ids": [
            r["case_id"]
            for r in rows
            if r["lab_intent"] == "attack" and not r["flagged"] and not r["ai_flagged"]
        ],
    }
    report = {
        "status": "COMPLETE_REQUEST_BOUND_HTTP_SIGNATURE_COMPARISON",
        "requests_bound": len(rows),
        "events": dict(Counter(e["event_type"] for e in events)),
        "signature_alert_counts": dict(all_sids),
        "request_baseline": evaluation_module.confusion(rows),
        "by_family": {
            f: evaluation_module.confusion([r for r in rows if r["family"] == f])
            for f in sorted({r["family"] for r in rows})
        },
        "incremental_detection": joined,
        "comparison_plan_sha256": comparison_plan["plan_sha256"],
        "independent_review": "PENDING",
        "threshold_tuning": False,
        "equal_alert_budget": "NOT_ESTABLISHED; fixed existing rule set and frozen model threshold; no tuning on111 requests",
        "rules_sha256_after": file_sha256(rules),
        "eve_sha256": file_sha256(output / "eve.json"),
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "comparison-report.json", report)
    atomic_json(output / "request-alerts.json", rows)
    print(
        json.dumps(
            {
                "bound": len(rows),
                "rule_confusion": report["request_baseline"],
                "incremental_counts": {k: len(v) for k, v in joined.items()},
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compare(args.capture, args.evaluation, args.output)
