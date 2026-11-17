"""Raw URI100 Python/Rust parity on fixtures and allowed TUNING/CAL inputs."""

# isort: skip_file

import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote

import numpy as np
import onnxruntime
import pyarrow.parquet as pq

from r26_common import SEED, atomic_json, check, file_sha256, read
from r26_notes import parse_request
from idps_ai.common import REPO_ROOT
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request
from r16_waf import BATCH, origin_view, source
from r23_features import describe_lane, sketch

SCHEMA = "idps-uri100-raw-ascii-r26-v1"


def python_uri100(target, method):
    lane = sketch(target)
    shape = (
        np.minimum(31, describe_lane(lane[0], b"/") + describe_lane(lane[1], b"&")).astype(
            np.float32
        )
        / 31
    )
    return np.r_[from_request(target, method), shape].astype(np.float32)


def frame(method, target):
    return {
        "schema": SCHEMA,
        "mode": "OFFLINE_RAW_REQUEST_REPLAY",
        "method": method,
        "target": target,
    }


def fixtures():
    targets = [
        "/",
        "/shop?q=hello",
        "/a?x=1&x=2",
        "/a?x=&x&=&&",
        "/a?q=%00%0a%1c",
        "/a?q=%GG%",
        "/a?q=%2f" + "A" * 38,
        "/a?q=Bearer%1cabc",
        "/api/secret/value?q=sleep%285%29",
        "/a?password=fixture&email=x@example.com",
        "/a?q=%252527or%25201%253D1--",
        "/foo/%2e%2e/%2f?q=%253Cscript%253E",
        "/a?code=drop+table",
        "/a?q=%2B",
        "/a?q=http%3A%2F%2Fexample.com%2Fa",
        "/a/1234567890123456?q=123456789",
        "/a/ABC/abc/1111?a=%25252527",
    ]
    rng = np.random.default_rng(SEED)
    values = [
        "hello",
        "123",
        "../etc/passwd",
        "'or 1=1--",
        "<img src=x onerror=alert(1)>",
        "a+b",
        "$(id)",
        "name@example.com",
        "",
        "x%gg",
    ]
    for i in range(150):
        key = ["q", "id", "filter", "secret", "name", "pwd"][i % 6]
        value = values[int(rng.integers(len(values)))]
        targets.append(f"/api/items/{i % 13}?{key}={quote(value, safe='')}&page={i % 3}")
    return [frame(["GET", "POST", "PUT"][i % 3], t) for i, t in enumerate(targets)]


def source_cases(out):
    with np.load(out / "data-v2/waf-r26.npz", allow_pickle=False) as z:
        nfit = int(z["nfit"])
        coord = z["coordinates"][nfit:]
        selected = np.sort(np.random.default_rng(SEED).choice(len(coord), 512, replace=False))
        coordinates = coord[selected]
        expected = z["x"][nfit:][selected, :100]
    order = np.argsort(coordinates)
    ordered = coordinates[order]
    cases, vectors = [], []
    offset = 0
    for batch in source().iter_batches(
        batch_size=BATCH, columns=["method", "url"], use_threads=False
    ):
        end = offset + batch.num_rows
        lo, hi = np.searchsorted(ordered, [offset, end])
        rows = batch.take(ordered[lo:hi] - offset).to_pylist() if hi > lo else ()
        for i, raw in zip(order[lo:hi], rows, strict=True):
            target = origin_view(raw["url"])[0]
            actual = python_uri100(target, raw["method"])
            np.testing.assert_array_equal(actual, expected[i])
            cases.append(frame(raw["method"], target))
            vectors.append(actual)
        offset = end
    for role in ("tuning", "cal_op"):
        with np.load(out / "notes" / f"{role}.npz", allow_pickle=False) as z:
            coord = z["coordinate"]
            expected = z["x"][:, :100]
        rows = pq.read_table(out / "notes-train.parquet", columns=["text"]).take(coord).to_pylist()
        for raw, vector in zip(rows, expected, strict=True):
            method, target, _, _, _ = parse_request(raw["text"])
            target = origin_view(target)[0]
            np.testing.assert_array_equal(python_uri100(target, method), vector)
            cases.append(frame(method, target))
            vectors.append(vector)
    return cases, vectors


def decoded_ascii(target):
    value = target.replace("+", " ")
    for _ in range(3):
        value = unquote(value)
    return value.isascii()


def run(out):
    binary = REPO_ROOT / "security-web/target/debug/idps-r26-uri100-shadow"
    lock = read(out / "evaluation-lock.json")
    spec = lock["models"][lock["selected_before_calibration"]]
    model = out / "bundle" / spec["calibrated_file"]
    check(file_sha256(model) == spec["calibrated_sha256"], "Frozen candidate digest")
    runtime = next((Path(onnxruntime.__file__).parent / "capi").glob("libonnxruntime.so.*"))
    cases = fixtures()
    expected = [python_uri100(row["target"], row["method"]) for row in cases]
    actual_cases, actual_vectors = source_cases(out)
    synthetic_count = len(cases)
    cases += actual_cases
    expected += actual_vectors
    payload = "".join(json.dumps(row) + "\n" for row in cases)
    command = [str(binary), str(model), spec["calibrated_sha256"], str(runtime)]
    session = cpu_session(model, 1)
    accepted = np.array([decoded_ascii(row["target"]) for row in cases], bool)
    reference = session.run(["score"], {"input": np.asarray(expected, np.float32)[accepted]})[0]
    values = []
    max_feature_error, max_score_error = 0.0, 0.0
    cold, prep, inference = [], [], []
    for _ in range(3):
        child = subprocess.run(
            command, input=payload, text=True, capture_output=True, timeout=30, check=True
        )
        rows = [json.loads(line) for line in child.stdout.splitlines()]
        check(len(rows) == len(cases), "Raw scorer response count")
        scores = []
        for i, row in enumerate(rows):
            if not accepted[i]:
                check(
                    row["status"] == "ABSTAIN" and row["reason"] == "UNVALIDATED_DECODED_UNICODE",
                    "Explicit unsupported scope",
                )
                continue
            check(row["status"] == "SCORED" and not row["hybrid_allowed"], "Scorer integrity")
            projected = np.asarray(row["features"], np.float32)
            error = float(np.max(np.abs(projected - expected[i])))
            max_feature_error = max(max_feature_error, error)
            np.testing.assert_allclose(
                projected,
                expected[i],
                rtol=1e-6,
                atol=1e-7,
                err_msg=f"Raw projection drift in case ordinal {i}",
            )
            scores.append(row["score"])
            if i >= 8:
                prep.append(row["preprocessing_ns"])
                inference.append(row["inference_ns"])
        scores = np.asarray(scores, np.float32)
        np.testing.assert_allclose(scores, reference, rtol=1e-5, atol=1e-6)
        max_score_error = max(max_score_error, float(np.max(np.abs(scores - reference))))
        np.testing.assert_array_equal(scores > spec["cutoff"], reference > spec["cutoff"])
        values.append(scores)
        cold.append(rows[0]["model_load_ns"])
    for scores in values[1:]:
        np.testing.assert_array_equal(scores, values[0])
    valid = cases[0]
    invalid = [
        "not json",
        json.dumps({**valid, "mode": "UNKNOWN"}),
        json.dumps({**valid, "method": "OTHER"}),
        json.dumps({**valid, "target": "//host"}),
        json.dumps({**valid, "target": "/a#fragment"}),
        json.dumps({**valid, "target": "/a?q=%E4%B8%80"}),
    ]
    result = subprocess.run(
        command,
        input="\n".join(invalid + [json.dumps(valid)]) + "\n",
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    check(
        all(r["status"] == "ABSTAIN" for r in rows[:-1]) and rows[-1]["status"] == "SCORED",
        "ABSTAIN/recovery",
    )
    wrong = subprocess.run(
        [str(binary), str(model), "0" * 64, str(runtime)],
        input="",
        text=True,
        capture_output=True,
        timeout=10,
    )
    check(wrong.returncode != 0, "Wrong model SHA must be refused")
    atomic_json(
        out / "runtime.json",
        {
            "state": "PASS_SCOPED_RAW_URI100_PARITY",
            "schema": SCHEMA,
            "synthetic_fixtures": synthetic_count,
            "publisher_tuning_calibration_cases": len(actual_cases),
            "cases_total": len(cases),
            "scored_per_process": int(accepted.sum()),
            "unsupported_decoded_unicode_per_process": int((~accepted).sum()),
            "fresh_processes": 3,
            "max_feature_abs_error": max_feature_error,
            "max_score_abs_error": max_score_error,
            "threshold_decisions": "IDENTICAL",
            "restart_scores": "BIT_EXACT",
            "abstain_cases": len(invalid),
            "malformed_frame_recovery": "PASS",
            "wrong_sha": "REFUSED",
            "model_sha256": spec["calibrated_sha256"],
            "binary_sha256": file_sha256(binary),
            "ort_library_sha256": file_sha256(runtime),
            "preprocessing_ns_p50_p95": np.percentile(prep, [50, 95]).tolist(),
            "inference_ns_p50_p95": np.percentile(inference, [50, 95]).tolist(),
            "combined_ns_p50_p95": np.percentile(np.asarray(prep) + inference, [50, 95]).tolist(),
            "cold_model_load_ns": cold,
            "scope_limit": "Raw URI and its three-round percent-decoded form must be ASCII. Unicode/invalid UTF8 is explicit ABSTAIN, not a fabricated vector.",
            "live_http_requests": 0,
            "native_cutoff_proof": "NOT_CLAIMED_BY_OFFLINE_REPLAY",
            "local_RI_V2_R20_services": "UNCHANGED",
            "hybrid_allowed": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
