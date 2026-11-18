"""Post-lock feature bounds and B16 runtime smoke tests without changing any model."""

import argparse
import io
import json
import subprocess
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import onnxruntime
import pyarrow.parquet as pq
from dataset import B16_PIN, BASELINE, need
from external import ARCHIVE_SHA, COLS, uri
from r20_calibration import apply
from rank_pilot import PARENT, PARENT_PIN
from symbols import project

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint, validate_generation
from idps_ai.training.tabular import forward


def ceiling(cells, totals):
    # A fractional final mixed group is allowed: this is an optimistic upper
    # bound even when no deterministic threshold can reach the fractional point.
    values = np.asarray(list(cells.values()), dtype=int)
    neg, pos = totals
    safe = int(values[values[:, 0] == 0, 1].sum())
    mixed = values[(values > 0).all(axis=1)]
    by_ratio = sorted(mixed, key=lambda v: v[1] / v[0], reverse=True)
    budget = int(np.floor(0.01 * neg))
    remaining = budget
    upper = float(safe)
    required = max(0, int(np.ceil(0.9 * pos)) - safe)
    cost = 0.0
    for n, p in by_ratio:
        taken = min(remaining, n)
        upper += taken * p / n
        remaining -= taken
        gain = min(required, p)
        cost += gain * n / p
        required -= gain
    return {
        "reference_normal_positive": list(map(int, totals)),
        "supported": values.sum(axis=0).tolist(),
        "distinct": len(values),
        "mixed_groups": len(mixed),
        "minority_mass": int(values.min(axis=1).sum()),
        "zero_FPR_recall": safe / pos,
        "benign_budget_integer": budget,
        "optimistic_max_recall_at_1pct": upper / pos,
        "optimistic_min_FPR_for_90pct": cost / neg if required == 0 else None,
    }


def postmortem(out):
    previous = load_json(out / "external-result.json")
    path = out / "testbed_corpus.tar.gz"
    need(file_sha256(path) == ARCHIVE_SHA, "POSTMORTEM_ARCHIVE")
    with tarfile.open(path) as t:
        member = t.getmembers()[0]
        records = pq.read_table(
            io.BytesIO(t.extractfile(member).read()), columns=COLS, use_threads=False
        ).to_pylist()
    counts = Counter(r["capture_id"] for r in records)
    tables = {name: defaultdict(lambda: [0, 0]) for name in ("URI100", "URI_AND_BODY")}
    for row in records:
        if counts[row["capture_id"]] != 1 or not row["label_source"].startswith(
            "campaign=" + row["campaign_id"] + " "
        ):
            continue
        path, query = row["url_path_raw"], row["url_query"]
        if not isinstance(path, str) or not isinstance(query, str) or "?" in path:
            continue
        target = path + ("?" + query if query else "")
        try:
            base = uri(target, row["http_method"]).tobytes()
        except (PipelineError, ValueError):
            continue
        label = int(row["label"] == "attack")
        tables["URI100"][base][label] += 1
        extra = project(target, row["request_body"])
        tables["URI_AND_BODY"][base + np.asarray(extra, dtype="<i4").tobytes()][label] += 1
    result = {n: ceiling(c, previous["singleton_roster_class_counts"]) for n, c in tables.items()}
    for name, old in (("URI100", "URI100"), ("URI_AND_BODY", "plus_safe_uri_body")):
        row = result[name]
        need(
            row["distinct"] == previous["indistinguishability"][old]["distinct"]
            and row["minority_mass"] == previous["indistinguishability"][old]["minority_mass"]
            and sum(row["supported"]) == previous["scored"],
            "BOUND_ROSTER_DIFFERENCE",
        )
    return result


def runtime():
    receipt = load_json(BASELINE.parent.parent / "raw-runtime/runtime.json")
    binary = REPO_ROOT / "security-web/target/debug/idps-r26-uri100-shadow"
    lib = next((Path(onnxruntime.__file__).parent / "capi").glob("libonnxruntime.so.*"))
    need(
        file_sha256(binary) == receipt["binary_sha256"]
        and file_sha256(lib) == receipt["ort_library_sha256"]
        and file_sha256(BASELINE) == B16_PIN,
        "SCORER_PIN",
    )
    validate_generation(PARENT, PARENT_PIN)
    model = load_checkpoint(PARENT).model
    manifest = load_json(BASELINE.parent / "manifest.json")
    targets = ["/catalog/items?page=" + str(i) + "&view=list" for i in range(1, 25)] + [
        "/health",
        "/assets/logo.png",
    ]
    req = [
        {
            "schema": manifest["schema"],
            "mode": "OFFLINE_RAW_REQUEST_REPLAY",
            "method": "GET",
            "target": t,
        }
        for t in targets
    ]
    payload = "{}\n" + "".join(json.dumps(f) + "\n" for f in req)
    x = np.asarray([uri(t, "GET") for t in targets])
    raw = forward(model, x)[1]
    ref = apply(manifest["calibration"], 1 - raw[:, 0])
    ort = cpu_session(BASELINE, 1).run(["score"], {"input": x})[0].reshape(-1)
    np.testing.assert_allclose(ort, ref, atol=2e-6, rtol=1e-5)
    runs = []
    inference = []
    prep = []
    cold = []
    for _ in range(2):
        proc = subprocess.run(
            [str(binary), str(BASELINE), B16_PIN, str(lib)],
            text=True,
            input=payload,
            capture_output=True,
            check=True,
            timeout=30,
        )
        rows = [json.loads(r) for r in proc.stdout.splitlines()]
        need(len(rows) == 1 + len(x) and rows[0]["status"] == "ABSTAIN", "INVALID_FRAME_ABSTAIN")
        scored = rows[1:]
        need(
            all(
                r["status"] == "SCORED" and r["model_sha256"] == B16_PIN and not r["hybrid_allowed"]
                for r in scored
            ),
            "RUST_HEALTH",
        )
        np.testing.assert_array_equal(np.array([r["features"] for r in scored], np.float32), x)
        runs.append(np.asarray([r["score"] for r in scored]))
        np.testing.assert_allclose(runs[-1], ort, atol=1e-6, rtol=1e-5)
        cold.append(scored[0]["model_load_ns"] / 1e6)
        inference.extend(r["inference_ns"] / 1e6 for r in scored[1:])
        prep.extend(r["preprocessing_ns"] / 1e6 for r in scored[1:])
    np.testing.assert_array_equal(*runs)
    wrong = subprocess.run(
        [str(binary), str(BASELINE), "0" * 64, str(lib)],
        input="",
        text=True,
        capture_output=True,
        timeout=5,
    )
    need(
        wrong.returncode != 0 and "digest mismatch" in wrong.stderr.lower(), "WRONG_SHA_NOT_REFUSED"
    )
    return {
        "model_sha256": B16_PIN,
        "checkpoint_sha256": PARENT_PIN,
        "rust_binary_sha256": file_sha256(binary),
        "ort_library_sha256": file_sha256(lib),
        "offline_frames_per_process": len(x),
        "processes": 2,
        "http_sent": 0,
        "negative_cases": ["ABSTAIN_THEN_RECOVER", "WRONG_SHA_REFUSED"],
        "checkpoint_onnx_max_abs": float(np.max(abs(ref - ort))),
        "rust_onnx_max_abs": float(np.max(abs(runs[0] - ort))),
        "restart_bit_exact": True,
        "warm_inference_ms_p50_p95": np.percentile(inference, [50, 95]).tolist(),
        "warm_projection_ms_p50_p95": np.percentile(prep, [50, 95]).tolist(),
        "cold_load_ms": cold,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    out = p.parse_args().out
    atomic_json(
        out / "verification.json",
        {
            "external_result_sha256": file_sha256(out / "external-result.json"),
            "hindsight_bounds": postmortem(out),
            "B16_runtime": runtime(),
        },
    )
