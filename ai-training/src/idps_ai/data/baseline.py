"""Validation-only baseline of the four actual Nginx map flags; no model fitting."""

import json
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256
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
