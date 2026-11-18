"""Audit R28 candidate-source metadata using historical summaries and role pins."""

import argparse
import json
import math
from hashlib import sha256
from pathlib import Path

from screen import protected_registry

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256

ARTIFACTS = REPO_ROOT / "ai-training/.artifacts"
METADATA = {
    "older_three_source": ARTIFACTS / "devgt1/run/oracle-verification/report.json",
    "review_queue": ARTIFACTS / "evidence_campaign_20261102/auto-review-v3/report.json",
    "grounded_research": ARTIFACTS / "data_scaling_20261109/pilot-r2/summary.json",
    "body_observability": REPO_ROOT
    / "ai-training/reports/BODY_SYNTAX_LIVE_ACCEPTANCE_20261108.json",
    "soc_queue": ARTIFACTS / "attack_evidence_20261101/soc-pending-review-final-v2/report.json",
    "publisher_waf": ARTIFACTS / "attack_evidence_20261101/modsec-wp-audit-final/report.json",
}


def zero_false_alert_support(endpoints):
    """Planning minimum when every independent benign anchor is correctly unflagged."""
    return math.ceil(math.log(0.05 / endpoints) / math.log1p(-0.01))


def audit():
    pin, protected_keys = protected_registry()
    handoff = ARTIFACTS / "defensive-intake/index.json"
    metadata, pins, missing = {}, {}, []
    for name, path in METADATA.items():
        if not path.is_file():
            missing.append(name)
            continue
        raw = path.read_bytes()
        metadata[name] = json.loads(raw)
        pins[str(path.relative_to(REPO_ROOT))] = sha256(raw).hexdigest()
    wanted = {
        "older_three_source": (
            "physical_requests_verified",
            "three_source_correlated_requests",
            "intent_unknown",
            "formal_training_admission",
        ),
        "review_queue": (
            "verified_physical_request_ids_in_this_registry",
            "independently_reviewed_labels",
            "objective_oracle_verified_labels",
            "training_admission",
        ),
        "grounded_research": ("strict_feature_views", "formal_admission_changed"),
        "body_observability": ("LIVE_OBSERVABILITY", "independent_review", "TRAINING_READY"),
        "soc_queue": ("pending_records", "labels_approved", "verified_independent_campaigns"),
        "publisher_waf": (
            "rows",
            "trusted_positive",
            "trusted_benign",
            "verified_independent_campaigns",
        ),
    }
    return {
        "version": "idps-r28-source-inventory-v1",
        "state": "BLOCKED_NO_DEFENSIVE_HANDOFF"
        if not handoff.exists()
        else "HANDOFF_REQUIRES_EXTERNAL_PINS_AND_INTAKE",
        "handoff_index_present": handoff.exists(),
        "historical_sources": {
            name: {key: report[key] for key in wanted[name]} for name, report in metadata.items()
        },
        "counts_scope": "HISTORICAL_METADATA_NON_ADDITIVE",
        "metadata_sha256": pins,
        "missing_metadata": missing,
        "R27_DEV_keys_protected": len(protected_keys),
        "R27_registry_sha256": pin,
        "new_HTTP_requests": 0,
        "new_native_verified_attack": 0,
        "new_native_verified_benign": 0,
        "new_independent_clusters": 0,
        "formal_native_TRAIN_DEV_CAL_FIT_CAL_OP_TEST": [0, 0, 0, 0, 0],
        "metrics": {"recall": None, "FPR": None, "confidence_bounds": None},
        "T07_support_planning": {
            "min_attack_requests_per_binary_claim": 100,
            "min_attack_clusters_per_binary_claim": 20,
            "zero_false_alert_benign_anchors_K1": zero_false_alert_support(1),
            "zero_false_alert_benign_anchors_K7": zero_false_alert_support(7),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Require a fresh output path")
    report = audit()
    report["inventory_code_sha256"] = file_sha256(__file__)
    atomic_json(args.output, report)
