"""Frozen-threshold source transfer diagnostics, never a training admission."""

# isort: skip_file

import argparse
import csv
import hashlib
import hmac
import os
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from r26_common import ARTIFACTS, atomic_json, check, file_sha256, read
from r26_evaluate import profile_metrics
from r26_notes import ROLES, parse_request
from idps_ai.export.onnx import cpu_session
from r14_audit import PINS as SOURCE_PINS, R6, R13
from r16_waf import coarse, origin_view, project as old_projection, write_array
from r19_data import R18
from r20_quality import R19
from r25_external import SOURCES, load as external_benign
from r23_features import describe_lane, sketch
from idps_ai.features.request_time import from_request


def frozen_models(out):
    lock = read(out / "evaluation-lock.json")
    models = {}
    for name, spec in lock["models"].items():
        path = out / "bundle" / spec["calibrated_file"]
        check(file_sha256(path) == spec["calibrated_sha256"], "Locked calibrated graph")
        models[name] = (cpu_session(path, 1), spec["width"], spec["cutoff"])
    return models


def embargo(out):
    with np.load(out / "data-v2/waf-r26.npz", allow_pickle=False) as z:
        buckets = {row.tobytes() for row in coarse(z["x"][:, :76])}
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as z:
        use = z["role"] <= 1
        ids = {bytes(v) for v in z["vector_id"][use]}
    templates = set()
    with sqlite3.connect(
        (R18 / "requests.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as db:
        templates.update(
            t for v, t in db.execute("SELECT vector_id,template FROM original") if v in ids
        )
    note_coords = set()
    for role in ROLES:
        # Metadata/embargo access only: no labels or model outputs used here.
        with np.load(out / "notes" / f"{role.lower()}.npz", allow_pickle=False) as z:
            buckets.update(row.tobytes() for row in coarse(z["x"][:, :76]))
            note_coords.update(z["coordinate"].tolist())
    rows = (
        pq.read_table(out / "notes-train.parquet", columns=["text"])
        .take(sorted(note_coords))
        .to_pylist()
    )
    for row in rows:
        method, target, _, _, _ = parse_request(row["text"])
        original = origin_view(target)
        projection = old_projection(method, original[0]) if original else None
        if projection:
            templates.add(projection[2])
    return buckets, templates


def srbh_frame(out):
    archive = ARTIFACTS / "generalization_20261031"
    source = archive / "srbh-public/data_capec_multilabel.csv"
    source_sha = "9c73c90ce6564ae48b14f7179cd864d037a6a130ef69c68c1626ec5d7ce4a910"
    check(file_sha256(source) == source_sha, "SR-BH source pin")
    for p in (R6 / "development.npz", R13 / "partition.npz"):
        check(file_sha256(p) == SOURCE_PINS[p], "Approved FIT source pin")
    cohort = read(R6 / "cohort.json")
    identity_path = R6 / "fit-identities.json"
    check(
        file_sha256(identity_path) == cohort["fit_identities_sha256"],
        "Approved identity coordinate pin",
    )
    with np.load(R13 / "partition.npz", allow_pickle=False) as z:
        approved = z["fit"]
    with np.load(R6 / "development.npz", allow_pickle=False) as z:
        expected_x = z["fit"][approved]
        expected_y = z["fit_targets"][approved]
    identities = [item for i, item in enumerate(read(identity_path)) if approved[i]]
    lookup = {item["event"]: i for i, item in enumerate(identities)}
    check(len(lookup) == len(expected_y) == 58241, "Only R13 FIT is allowed")
    key = (archive / "srbh-identity.key").read_bytes()
    audit = read(archive / "srbh-audit-v2/manifest.json")
    check(
        hashlib.sha256(key).hexdigest() == audit["identity_key_fingerprint"],
        "SR-BH identity domain",
    )
    buckets, templates = embargo(out)
    counters = Counter()
    vectors, targets, groups = [], [], []
    csv.field_size_limit(1048576)
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, strict=True)
        for ordinal, row in enumerate(reader):
            event = hmac.new(
                key, f"{source_sha}:record:{ordinal}".encode(), hashlib.sha256
            ).hexdigest()
            if event not in lookup:
                continue
            i = lookup[event]
            counters["approved_fit_originals_found"] += 1
            try:
                method = row["request_http_method"]
                original = origin_view(row["request_http_request"])
                if not original:
                    raise ValueError("Unsupported source envelope")
                target = original[0]
                base = from_request(target, method)
                np.testing.assert_array_equal(base, expected_x[i])
                _, bucket, template = old_projection(method, target)
            except ValueError:
                counters["unsupported_envelope"] += 1
                continue
            if bucket in buckets or template in templates:
                counters["training_selection_calibration_overlap_embargo"] += 1
                continue
            lane = sketch(target)
            shape = (
                np.minimum(31, describe_lane(lane[0], b"/") + describe_lane(lane[1], b"&")).astype(
                    np.float32
                )
                / 31
            )
            vectors.append(np.r_[base, shape].astype(np.float32))
            targets.append(expected_y[i])
            groups.append(hashlib.sha256(bucket).digest())
    check(counters["approved_fit_originals_found"] == 58241, "Approved source identity recovery")
    x = np.asarray(vectors, np.float32)
    y = np.asarray(targets, np.int8)
    if not len(y):
        return None, {
            "source": "SR_BH_ALLOWED_FIT",
            "counters": dict(counters),
            "state": "BLOCKED_ALL_OVERLAP",
        }
    _, group_id = np.unique(np.asarray(groups, dtype="S32"), return_inverse=True)
    frame = {"x": x, "y": y, "group": group_id.reshape(-1), "coordinate": np.arange(len(y))}
    report = {
        "source": "SR_BH_ALLOWED_FIT",
        "source_sha256": source_sha,
        "counters": dict(counters),
        "retained": len(y),
        "normal_anomalous": np.bincount(y, minlength=2).tolist(),
        "unique_uri100": len(np.unique(x, axis=0)),
        "source_role": "EXISTING_FIT_TRANSFER_DIAGNOSTIC_ONLY_NO_TRAINING_ADDITION",
        "preprocessing": "URI100 request-only; no body or headers reconstructed",
        "no_old_DEV_CAL_TEST_payloads": True,
        "independent_final_acceptance": False,
        "lineage_limit": "Historical single WordPress environment; source generator relation to WAF is not independently certified. Exact/coarse/template overlap fenced before scores.",
    }
    return frame, report


def run(out):
    models = frozen_models(out)
    result = {
        "evaluation_lock_sha256": file_sha256(out / "evaluation-lock.json"),
        "benign_stress": {},
    }
    for source in SOURCES:
        x, method, metadata = external_benign(source)
        report = {}
        for name, (session, width, cutoff) in models.items():
            scores = np.concatenate(
                [
                    session.run(["score"], {"input": x[i : i + 4096, :width]})[0]
                    for i in range(0, len(x), 4096)
                ]
            )
            flags = scores > cutoff
            _, first = np.unique(x[:, :width], axis=0, return_index=True)
            report[name] = {
                "cutoff": cutoff,
                "false_positives": int(flags.sum()),
                "fpr_by_projectable_record": float(flags.mean()),
                "fpr_vector_balanced": float(flags[first].mean()),
                "by_method": {
                    n: {
                        "normal_records": int((method == i).sum()),
                        "fp": int(flags[method == i].sum()),
                    }
                    for i, n in enumerate(("GET", "POST", "OTHER"))
                },
            }
        result["benign_stress"][source] = {
            "metadata": metadata,
            "matched_new_calibration_protocol": report,
        }
    frame, source = srbh_frame(out)
    result["SR_BH_transfer"] = {"metadata": source}
    if frame is not None and min(np.bincount(frame["y"], minlength=2)) >= 32:
        result["SR_BH_transfer"]["models"] = {
            name: profile_metrics(
                frame, session.run(["score"], {"input": frame["x"][:, :width]})[0], width, cutoff
            )
            for name, (session, width, cutoff) in models.items()
        }
        write_array(out / "srbh-transfer-numeric.npz", **frame)
    else:
        result["SR_BH_transfer"]["status"] = "INCONCLUSIVE_CLASS_SUPPORT"
    result["fit_calibration_thresholds_changed"] = False
    result["RI_V2_AND_HYBRID"] = "NOT_SCORED_WITH_UNOBSERVED_NATIVE_207_INPUTS"
    atomic_json(out / "transfer.json", result)


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
