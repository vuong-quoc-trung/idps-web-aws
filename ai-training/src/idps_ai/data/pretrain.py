"""Finish an owned lab capture through dataset readiness, stopping before fitting."""

import os
import secrets
import shlex
from pathlib import Path

import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.baseline import nginx_rule_baseline, three_source_rule_baseline
from idps_ai.data.capacity import capacity_check
from idps_ai.data.dataset import collect
from idps_ai.data.lab_runtime import stop_lab
from idps_ai.data.provenance import (
    derive_provenance,
    observer_labels,
    register_provenance,
    scope_capture_inputs,
)
from idps_ai.data.readers import Input
from idps_ai.data.readiness import audit_readiness
from idps_ai.data.review import export_review
from idps_ai.data.snapshot import new_destination, snapshot
from idps_ai.data.split import prepare


def finish_lab(lab_dir, output, resource_inventory=None, policy_path=None):
    lab = Path(lab_dir).resolve()
    output = new_destination(output)
    capture = load_json(lab / "capture-result.json")
    if capture.get("campaigns") != 15 or capture.get("data_kind") != "lab_capture":
        raise PipelineError("Lab capture must complete before finalizing its dataset")
    stop_lab(lab)
    output.mkdir(mode=0o700)
    key = secrets.token_bytes(32)
    (output / "training-redaction.key").write_bytes(key)
    os.chmod(output / "training-redaction.key", 0o600)
    three_source = capture.get("query_profile") == "edge_masked_v1"
    source_inputs = [
        Input("student", lab / "student-audit.log"),
        Input("nginx", lab / ("access.log" if three_source else "access-lab.log")),
    ]
    sensor_evidence = None
    if three_source:
        sensor_evidence = load_json(lab / "eve/decode-manifest.json")
        pcap_evidence = load_json(lab / "pcap-manifest.json")
        if (
            sensor_evidence["pcap_sha256"] != pcap_evidence["pcap_sha256"]
            or sensor_evidence["eve_sha256"] != file_sha256(lab / "eve/eve.json")
            or sensor_evidence["pcap_sha256"] != file_sha256(lab / "traffic.pcap")
        ):
            raise PipelineError("PCAP/EVE evidence checksum mismatch")
        source_inputs.append(Input("suricata", lab / "eve/eve.json"))
        policy_path = policy_path or AI_ROOT / "configs/three_source_policy.yaml"
    scope = scope_capture_inputs(
        source_inputs, lab / "observer.jsonl", lab / "capture-result.json", output / "scoped-inputs"
    )
    scoped_inputs = [
        Input(entry["source"], output / "scoped-inputs" / entry["file"])
        for entry in scope["inputs"]
    ]
    snap = snapshot(scoped_inputs, output / "snapshot", "lab_capture")
    labels = observer_labels(
        lab / "observer.jsonl", lab / "capture-result.json", output / "labels", key
    )
    inputs = [
        Input(entry["source"], output / "snapshot" / entry["file"]) for entry in snap["inputs"]
    ]
    collected = collect(
        inputs,
        output / "collected",
        key,
        output / "labels/labels.jsonl",
        input_profile="edge_masked_v1" if three_source else "native",
    )
    limits = [
        "Isolated real Student HTTP execution with synthetic accounts/data, not representative production traffic",
        "Private lab-only Nginx query view preserves scripted non-sensitive probes; current edge template masks query. Deployment feature availability must be reviewed or model input profile revised",
        "EVE capture NOT_RUN because packet-socket permission was unavailable; flow features are missing, no fake EVE used",
        "Role and missing-profile cases are fixture workloads; representative real user sessions and benign hard negatives need later coverage review",
        "Labels prove scripted intent/expected HTTP outcomes, not successful SQLi/XSS/RCE/IDOR exploitation",
        "Only three payload/agent views per family and loopback lab identities; this is an offline pilot corpus, not a production benchmark",
        "No independent human label/realism review; observer contract checks and review-export are available",
    ]
    if three_source:
        limits = [
            "Actual HTTP and PCAP/EVE on isolated loopback fixture; not representative production traffic",
            "edge_masked_v1 drops query lexical/original counters from every source; hidden query payload families may be indistinguishable to AI",
            "Completed-client-flow context reserves 65s after packet end; event-time replay is not acceptance of live sensor receipt delays",
            "420s campaigns with real 620s gaps; three temporal bands and disjoint identities; only one host/topology",
            "Scenario labels describe intent/expected outcomes; no exploit success or independent human realism review",
            "No Rust inference, production champion, shadow or firewall enforcement accepted",
        ]
    register_provenance(
        output / "collected",
        output / "snapshot",
        lab / "capture-result.json",
        output / "labels/label_evidence.json",
        output / "collected_provenance.json",
        limits,
        sensor_evidence=sensor_evidence,
    )
    prepared = prepare(output / "collected", output / "prepared")
    derive_provenance(
        output / "prepared",
        output / "collected_provenance.json",
        output / "prepared_provenance.json",
    )
    report = audit_readiness(
        output / "prepared",
        output / "readiness",
        "lab_capture",
        provenance=output / "prepared_provenance.json",
        policy_path=policy_path,
    )
    baseline = nginx_rule_baseline(
        output / "prepared",
        output / "snapshot/01-nginx.jsonl",
        key,
        output / "nginx-rule-baseline-val.json",
    )
    if three_source:
        three_source_rule_baseline(
            output / "prepared",
            output / "snapshot/01-nginx.jsonl",
            output / "snapshot/02-suricata.jsonl",
            key,
            output / "three-source-rule-baseline-val.json",
        )
    capacity = capacity_check(
        output / "prepared",
        output / "capacity.json",
        min(
            8,
            max(
                1,
                len(
                    (resource_inventory or {}).get(
                        "effective_cpus_before_cap", os.sched_getaffinity(0)
                    )
                )
                // 2,
            ),
        ),
        effective_cpus_before_cap=(resource_inventory or {}).get("effective_cpus_before_cap"),
    )
    export_review(output / "collected", output / "human-review", limit=1000)
    plan = yaml.safe_load((AI_ROOT / "configs/experiment_plan.yaml").read_text())
    commands = {}
    for name, config in [
        ("mlp", "train_config.yaml"),
        ("autoencoder", "anomaly_config.yaml"),
        ("residual", "residual_config.yaml"),
    ]:
        commands[name] = [
            str(AI_ROOT / ".venv/bin/idps-ai"),
            "train",
            "--dataset",
            str(output / "prepared"),
            "--config",
            str(AI_ROOT / "configs" / config),
            "--run-dir",
            str(output / "runs" / name),
            "--readiness-report",
            str(output / "readiness/readiness.json"),
            "--epochs",
            str(plan["initial_total_epochs"]),
            "--cpus",
            "8",
            "--memory-limit-gib",
            "16",
            "--max-duration-minutes",
            "150",
        ]
    result = {
        "format_version": 1,
        "status": report["status"],
        "training_executed": False,
        "real_training_hours": 0,
        "collected_dataset_sha256": collected["dataset_sha256"],
        "scope_manifest_sha256": file_sha256(output / "scoped-inputs/scope_manifest.json"),
        "scope": scope,
        "prepared_dataset_sha256": prepared["dataset_sha256"],
        "readiness_report_sha256": file_sha256(output / "readiness/readiness.json"),
        "capacity_status": capacity["status"],
        "nginx_rule_baseline": {
            "partition": "val",
            "matched_rows": baseline["matched_rows"],
            "scope": baseline["engine"],
        },
        "approved_label_rows": labels["approved_rows"],
        "unknown_label_rows": labels["unknown_rows"],
        "rows": prepared["rows"],
        "feature_count": prepared["feature_count"],
        "planned_initial_total_epochs": plan["initial_total_epochs"],
        "experiment_plan_sha256": file_sha256(AI_ROOT / "configs/experiment_plan.yaml"),
        "next_training_commands": commands,
        "limits": limits,
    }
    atomic_json(output / "handoff.json", result)
    (output / "NEXT_COMMANDS.txt").write_text(
        "NOT EXECUTED: run only when choosing to begin the offline pilot.\n\n"
        + "\n\n".join(shlex.join(v) for v in commands.values())
        + "\n"
    )
    return result
