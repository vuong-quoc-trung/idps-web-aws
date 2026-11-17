"""Reconcile R22 checkpoints against the guest ledger and verify calibration."""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from bundle import verify
from evidence import VERSION, read, require, summarize

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.export.onnx import cpu_session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "development-bulk-v1"))
from r20_calibration import apply  # noqa: E402

RAW_SHA = "f5b70f45e826e593a7a1581835ff42c816a54699e0a9dded7f79d16acdd7bdc1"


def run(out, raw_model, calibration):
    scope = verify(out / "bundle")
    path = out / "quality-ledger.json"
    checkpoint, summary = read(path), read(out / "quality-summary.json")
    require(file_sha256(path) == summary["ledger_sha256"], "Checkpoint file digest mismatch")
    rows = checkpoint["rows"]
    require(
        checkpoint["version"] == VERSION
        and checkpoint["run_id"] == out.name
        and checkpoint["cursor"] == len(rows) == checkpoint["limit"]
        and digest(rows) == checkpoint["rows_sha256"],
        "Checkpoint content mismatch",
    )
    guest = out / "guest-resource/guest/receipt-ledger.jsonl"
    require(file_sha256(guest) == summary["guest_ledger_sha256"], "Guest ledger digest mismatch")
    with guest.open(encoding="utf-8") as stream:
        receipts = [row for line in stream if (row := json.loads(line))["kind"] == "ATTEMPT"]
    require(
        len(receipts) == len(rows)
        and all(
            r["attempt"] == g["attempt"]
            and r["request_key"] == g["request_key"]
            and r["receipt_sha256"] == digest(g)
            for r, g in zip(rows, receipts, strict=True)
        ),
        "Committed quality evidence does not match actual receipts",
    )
    require(
        all(summary[k] == val for k, val in summarize(rows).items()),
        "Quality summary differs from checkpoint",
    )
    require(
        file_sha256(calibration) == scope["tuning_calibration"]["selection_sha256"]
        and file_sha256(raw_model) == RAW_SHA,
        "Calibration source digest mismatch",
    )
    mapping = read(calibration)["model"]
    require(mapping["kind"] == "isotonic", "Unsupported calibration")
    scored = [row for row in rows if row["r20"]["status"] == "SCORED"]
    x = np.array([r["uri76"]["vector"] for r in scored], dtype=np.float32)
    scores = np.array([r["r20"]["score"] for r in scored], dtype=np.float64)
    raw = cpu_session(raw_model, 1).run(["score"], {"input": x})[0]
    calibrated = apply(mapping, raw)
    cutoff = scope["tuning_calibration"]["threshold"]
    np.testing.assert_allclose(scores, calibrated, rtol=0, atol=1e-7)
    np.testing.assert_array_equal(scores > cutoff, calibrated > cutoff)
    atomic_json(
        out / "verification.json",
        {
            "state": "PASS",
            "reconciled_requests": len(rows),
            "calibration_cases": len(x),
            "calibration_max_abs_error": float(np.max(np.abs(scores - calibrated))),
            "threshold_decisions_match": True,
            "calibration_sha256": file_sha256(calibration),
            "raw_model_sha256": RAW_SHA,
            "quality_summary_sha256": file_sha256(out / "quality-summary.json"),
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    p.add_argument("--raw-model", type=Path, required=True)
    p.add_argument("--calibration-selection", type=Path, required=True)
    args = p.parse_args()
    run(args.out, args.raw_model, args.calibration_selection)
