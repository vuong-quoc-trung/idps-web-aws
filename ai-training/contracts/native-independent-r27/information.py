"""Retrospective information census on research labels, never a fitted classifier."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def ambiguity(rows, key):
    groups = defaultdict(Counter)
    for row in rows:
        groups[key(row)][row["label"]] += 1
    positives = sum(row["label"] == "ATTACK_VERIFIED" for row in rows)
    return {
        "groups": len(groups),
        "mixed_groups": sum(len(g) > 1 for g in groups.values()),
        "unavoidable_errors": sum(min(g.values()) for g in groups.values() if len(g) > 1),
        "empirical_recall_ceiling_at_zero_FP": sum(
            g.get("ATTACK_VERIFIED", 0) for g in groups.values() if not g.get("BENIGN_VERIFIED")
        )
        / positives
        if positives
        else None,
    }


def run(root):
    rows = json.loads((root / "canonical-research-ledger.json").read_text())["rows"]
    controls = {
        name: ambiguity(rows, key)
        for name, key in {
            "URI100_only": lambda r: r["uri100"]["vector_sha256"],
            "role_only": lambda r: r["context"]["observation"]["role"],
            "category_only": lambda r: r["context"]["binding"]["category"],
            "method_only": lambda r: r["method"],
            "campaign_only": lambda r: r["campaign"],
            "availability_only": lambda r: tuple(r["context"]["encoded"]["vector"][13:]),
            "context22": lambda r: tuple(r["context"]["encoded"]["vector"]),
            "URI100_context22": lambda r: r["feature_sha256"],
        }.items()
    }
    value = {
        "scope": "EXPOSED_RESEARCH_INFORMATION_PROOF_NOT_TEST_OR_ML_QUALITY",
        "rows": len(rows),
        "controls": controls,
        "new_roles_counterbalanced": True,
        "ML_additional_value_demonstrated": False,
        "policy_control_is_not_ML": True,
    }
    (root / "information-proof.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value))


if __name__ == "__main__":
    run(Path(sys.argv[1]))
