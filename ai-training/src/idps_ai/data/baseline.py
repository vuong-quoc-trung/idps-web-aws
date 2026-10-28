"""Validation-only baseline of the four actual Nginx map flags; no model fitting."""

import json
from pathlib import Path

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.privacy import pseudonym
from idps_ai.data.snapshot import new_destination

SIGNALS = ("SQLI", "XSS", "PATH_TRAVERSAL", "COMMAND_INJECTION")


def nginx_rule_baseline(dataset, log_path, key, output):
    manifest = verify_dataset(dataset, "prepared")
    output = new_destination(output)
    if pseudonym(key, "fingerprint", "v1") != manifest["redaction_key_fingerprint"]:
        raise PipelineError("Baseline key differs from the dataset redaction key")
    log_path = Path(log_path)
    before = file_sha256(log_path)
    facts = {}
    with log_path.open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536:
                raise PipelineError("Oversized baseline input")
            value = json.loads(line)
            rid = pseudonym(key, "request", value.get("request_id"))
            if rid is None:
                continue
            flags = value.get("rule_signals", {})
            if any(flags.get(name, 0) not in (0, 1) for name in SIGNALS):
                raise PipelineError("Invalid fixed rule flags")
            if rid in facts:
                raise PipelineError("Duplicate request ID in rule baseline")
            facts[rid] = [name for name in SIGNALS if flags.get(name, 0) == 1]
    if file_sha256(log_path) != before:
        raise PipelineError("Baseline log changed")
    tp = fp = tn = fn = unmatched = 0
    families = {}
    signal_counts = {name: 0 for name in SIGNALS}
    for row in iter_rows(Path(dataset) / "requests.parquet"):
        if row["split"] != "val" or row["label"] is None:
            continue
        if row["request_key"] not in facts:
            unmatched += 1
            continue
        signals = facts[row["request_key"]]
        predicted = bool(signals)
        label = bool(row["label"])
        tp += predicted and label
        fp += predicted and not label
        fn += not predicted and label
        tn += not predicted and not label
        family = families.setdefault(row["attack_family"], {"count": 0, "flagged": 0})
        family["count"] += 1
        family["flagged"] += predicted
        for name in signals:
            signal_counts[name] += 1
    total = tp + fp + tn + fn
    result = {
        "format_version": 1,
        "dataset_sha256": manifest["dataset_sha256"],
        "source_file_sha256": before,
        "partition": "val",
        "training_executed": False,
        "engine": "Nginx four-map flags only, not the full Rust/Suricata rule ensemble",
        "signals": list(SIGNALS),
        "matched_rows": total,
        "unmatched_rows": unmatched,
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "per_family": families,
        "signal_counts": signal_counts,
        "limits": [
            "No final-test metrics computed or threshold tuning performed",
            "Scanner/auth/stateful/Suricata detections are not represented by these four flags",
            "Labels come from reviewed scenario intent, never from these flags",
        ],
    }
    atomic_json(output, result)
    return result


def three_source_rule_baseline(dataset, nginx_path, eve_path, key, output):
    """Diagnostic Nginx+Suricata union. Rust stateful engine is not executed."""
    import numpy as np

    from idps_ai.data.readers import eve_request_id
    from idps_ai.training.evaluation import evaluate

    manifest = verify_dataset(dataset, "prepared")
    if pseudonym(key, "fingerprint", "v1") != manifest["redaction_key_fingerprint"]:
        raise PipelineError("Baseline redaction key mismatch")
    paths = [Path(nginx_path), Path(eve_path)]
    before = [file_sha256(p) for p in paths]
    nginx, flows, alerts = {}, {}, []
    for line in paths[0].open():
        value = json.loads(line)
        rid = pseudonym(key, "request", value.get("request_id"))
        if rid in nginx:
            raise PipelineError("Duplicate edge request identity")
        nginx[rid] = any(value.get("rule_signals", {}).get(s) == 1 for s in SIGNALS)
    for line in paths[1].open():
        value = json.loads(line)
        flow = value.get("flow_id")
        if value.get("event_type") == "http":
            rid = pseudonym(key, "request", eve_request_id(value.get("http") or {}))
            flows.setdefault(flow, set()).add(rid)
        if value.get("event_type") == "alert":
            alerts.append((flow, value.get("alert", {}).get("signature_id")))
    sids = {}
    ambiguous = 0
    for flow, sid in alerts:
        identities = flows.get(flow, set()) - {None}
        if len(identities) != 1:
            ambiguous += 1
            continue
        sids.setdefault(next(iter(identities)), set()).add(sid)
    labels, all_rules, web_rules, facts = [], [], [], []
    campaign_cases = {}
    for row in iter_rows(Path(dataset) / "requests.parquet"):
        if row["split"] != "val" or row["label"] is None:
            continue
        rid = row["request_key"]
        if rid not in nginx:
            raise PipelineError("Validation request lacks edge rule evidence")
        hits = sids.get(rid, set())
        all_hit = nginx[rid] or bool(hits)
        web_hit = nginx[rid] or any(sid != 1000001 for sid in hits)
        case = campaign_cases.setdefault(
            (row["campaign_key"], row["attack_family"]), [False, False]
        )
        case[0] |= all_hit
        case[1] |= web_hit
        labels.append(CLASSES.index(row["attack_family"]))
        all_rules.append(int(all_hit))
        web_rules.append(int(web_hit))
        facts.append({"request_key": rid, "all_rules": all_hit, "web_rules": web_hit})
    if before != [file_sha256(p) for p in paths]:
        raise PipelineError("Rule source changed during comparison")
    campaign_summary = {}
    for (_, family), (all_hit, web_hit) in campaign_cases.items():
        item = campaign_summary.setdefault(
            family,
            {
                "campaign_family_cases": 0,
                "all_rules_detected_cases": 0,
                "web_rules_detected_cases": 0,
            },
        )
        item["campaign_family_cases"] += 1
        item["all_rules_detected_cases"] += all_hit
        item["web_rules_detected_cases"] += web_hit
    result = {
        "format_version": 1,
        "dataset_sha256": manifest["dataset_sha256"],
        "partition": "val",
        "campaign_family_summary": campaign_summary,
        "source_sha256": before,
        "scope": "Nginx four maps + actual Suricata; no Rust stateful execution",
        "all_nine_sids": evaluate(np.asarray(labels), np.asarray(all_rules), 0.5),
        "web_sids_excluding_syn_rate": evaluate(np.asarray(labels), np.asarray(web_rules), 0.5),
        "unmatched_or_ambiguous_alerts": ambiguous,
        "limits": [
            "HTTP/flow joining is retrospective diagnostic, not a live alert-latency acceptance",
            "Web subset is predefined to exclude SID1000001 SYN-rate observations",
            "No rule facts or alert labels enter model training",
        ],
    }
    output = new_destination(output)
    atomic_json(output, result)
    atomic_json(
        output.with_name("validation-rule-facts.json"),
        {"dataset_sha256": manifest["dataset_sha256"], "partition": "val", "facts": facts},
    )
    return result
