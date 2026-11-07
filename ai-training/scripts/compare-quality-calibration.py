#!/usr/bin/env python3
"""Compare preselected calibration-only threshold on exposed diagnostics only."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.mvp_inference import ResearchMVP


def compare(assessment, output):
    assert not output.exists()
    protocol = json.loads((assessment / "analysis-protocol.json").read_text())
    assert protocol["protocol_sha256"] == digest(
        {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    )
    assert (
        file_sha256(assessment / "feature-views.npz") == protocol["feature_file_sha256"]
        and file_sha256(assessment / "role-audit.jsonl") == protocol["role_ledger_sha256"]
    )
    report_path = assessment / "report-corrected.json"
    if not report_path.exists():
        report_path = assessment / "report.json"
    r = json.loads(report_path.read_text())
    assert r["report_sha256"] == digest({k: v for k, v in r.items() if k != "report_sha256"})
    threshold = r["calibration_only"]["threshold"]
    assert threshold is not None
    rows = [json.loads(line) for line in (assessment / "role-audit.jsonl").read_text().splitlines()]
    with np.load(assessment / "feature-views.npz", allow_pickle=False) as data:
        x = data["x"]
        ids = data["request_id"].astype(str)
    assert ids.tolist() == [r["request_id"] for r in rows]
    m = ResearchMVP("request-v2", cpus=1)
    selected = [
        i
        for i, r in enumerate(rows)
        if r["role"] in ["TRAIN", "CALIBRATION", "DEVELOPMENT"] and r["intent"] != "UNKNOWN"
    ]
    with threadpool_limits(limits=1):
        scores = m.v2_model.predict(x[selected])[0]
    assert np.isfinite(scores).all()
    summaries = {}
    for name, t in [("frozen", m.v2_threshold), ("calibration_only", threshold)]:
        counters = {}
        for dimension, fn in [
            ("role", lambda r: r["role"]),
            ("method", lambda r: r["method"]),
            ("family", lambda r: r["family"]),
            ("environment", lambda r: r["environment"]),
        ]:
            c = {}
            for i, s in zip(selected, scores, strict=True):
                row = rows[i]
                group = fn(row)
                c.setdefault(group, Counter())
                flag = bool(s > t)
                attack = row["intent"] == "ATTACK_ATTEMPT"
                c[group][("T" if flag == attack else "F") + ("P" if flag else "N")] += 1
            counters[dimension] = {k: dict(v) for k, v in c.items()}
        summaries[name] = {"threshold": t, "comparator": ">", "counts": counters}
    report = {
        "schema_version": "calibration-comparison-1",
        "status": "RESEARCH_DIAGNOSTIC_NOT_ACCEPTANCE",
        "protocol_sha256": protocol["protocol_sha256"],
        "threshold_selected_from": "Only3unique eligible CALIBRATION benign views,9physicalrows; allGET; poor coverage",
        "threshold_unchanged_after_diagnostic": True,
        "results": summaries,
        "scored_diagnostic_rows": len(selected),
        "prospective_rows_scored": 0,
        "frozen_weights_and_threshold_modified": False,
        "decision": "REJECT_FOR_DEPLOYMENT_AND_QUALITY_CLAIM; calibration support lacks benignPOST and cannot establish<=1%FPR; no new weights fit",
        "training_started": False,
        "limits": [
            "TRAIN metrics here are frozen-model diagnostics, not fit/generalization performance",
            "DEVELOPMENT includes P0-like patterns; never called blind evaluation",
            "Scores use recorded full offline headers/body; live worker body remains missing",
            "Internal Oracle labels and collector intent, human review pending; no independent population Recall/FPR",
        ],
    }
    atomic_json(output, report)
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "role_comparison": {k: v["counts"]["role"] for k, v in summaries.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assessment", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    compare(a.assessment, a.output)
