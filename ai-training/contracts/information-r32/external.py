"""One post-selection offline evaluation of a frozen external campaign-labelled archive."""
# isort: skip_file

import argparse
import hashlib
import io
import tarfile
import time
import zipfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pyarrow.parquet as pq
from dataset import BASELINE, B16_PIN, FOLDERS, ROOT, WAF, need
from calibration_pilot import PUBLISHED_CUTOFF
from experiment import census, predict, probabilities
from scipy import sparse
from sklearn.metrics import average_precision_score
from symbols import WIDTH, decoded, project

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request

from r23_features import describe_lane, sketch

ARCHIVE_SHA = "9126e43da413bee16cb543a8d0b9187819d312303f83c83e57d8bda3b1ecfd86"
COLS = [
    "capture_id",
    "http_method",
    "url_path_raw",
    "url_query",
    "request_body",
    "label",
    "campaign_id",
    "label_source",
    "app",
]


@lru_cache(maxsize=16384)
def uri(target, method):
    if not target.isascii() or not decoded(target).isascii():
        raise ValueError("OUTSIDE_RAW_ASCII_ABI")
    base = from_request(target, method)
    path, query = sketch(target)
    shape = (
        np.minimum(31, describe_lane(path, b"/") + describe_lane(query, b"&")).astype(np.float32)
        / 31
    )
    return np.r_[base, shape].astype("<f4", copy=False)


def embargo():
    # Read only historical FIT/TUNING URI100 prefixes. Never touch native TEST
    # or publisher evaluation content to diagnose external generalization.
    seen = set()
    with zipfile.ZipFile(WAF) as arc, arc.open("x.npy") as stream:
        need(np.lib.format.read_magic(stream) == (1, 0), "NUMERIC_POOL_VERSION")
        shape, order, dtype = np.lib.format.read_array_header_1_0(stream)
        need(shape == (406042, 244) and dtype == np.dtype("<f4") and not order, "NUMERIC_POOL_ABI")
        for i in range(0, shape[0], 4096):
            chunk = stream.read(min(4096, shape[0] - i) * shape[1] * 4)
            values = np.frombuffer(chunk, dtype=dtype).reshape(-1, shape[1])
            seen.update(v[:100].tobytes() for v in values)
    for folder in FOLDERS.values():
        for role in ("fit", "tuning"):
            with np.load(ROOT / folder / (role + ".npz"), allow_pickle=False) as a:
                seen.update(v[:100].tobytes() for v in a["x"])
    return seen


def lock(out):
    path = out / "external-lock.json"
    need(not path.exists(), "ALREADY_LOCKED")
    prior = load_json(out / "pilot-result.json")
    again = load_json(out / "neighbors-pilot.json")
    need(not prior["advance"] and not again["advance"], "FINALIZE_ADVANCED_MODEL_FIRST")
    arm = prior["selected"]
    need(
        prior["comparison"][arm]["macro_recall_gain"]
        >= max(v["macro_recall_gain"] for v in again["comparison"].values()),
        "LOCK_WINNING_COMPARATOR_FIRST",
    )
    model = prior["models"][arm]
    atomic_json(
        path,
        {
            "schema": "r32-external-transfer-v1",
            "frozen_archive": ARCHIVE_SHA,
            "code": file_sha256(__file__),
            "plan": file_sha256(out / "plan.json"),
            "pilot": file_sha256(out / "pilot-result.json"),
            "neighbors": file_sha256(out / "neighbors-pilot.json"),
            "model": model,
            "arm": arm,
            "base_sha": B16_PIN,
            "thresholds": {
                "B16_PUBLISHED": PUBLISHED_CUTOFF,
                "B16_TUNING": prior["results"]["B16"]["development_threshold"],
                arm: prior["results"][arm]["development_threshold"],
            },
            "comparators": "Best pilot only as frozen diagnostic. Keep B16 decision made before external labels.",
            "role": "NEW_EXTERNAL_PUBLISHER_TRANSFER_ONLY_NO_FITTING_OR_SELECTION_NO_NATIVE_CUSTODY",
            "release_source_commit": "b0cc45b33b640dc061aaeda5a47751f678e7c26c",
            "external_topology": "campaign class by source and time, two lab applications",
            "coverage": "All publisher rows accountable; quarantine all rows of every non-unique capture_id before scoring. Report singleton-ID and all-row denominators separately. Empty query reconstructed by publisher convention with alternative projection sensitivity.",
            "overlap": "Report full roster and scored views not overlapping any WAF/Notes/SRBH FIT or TUNING URI100. Near, calibration and campaign independence not proven.",
            "analysis": "effective rates all; score metrics scored only; sampled campaign bootstrap conditional on this corpus. No threshold changes after lock.",
        },
    )


def measure(y, score, cut, weights=None):
    w = np.ones(len(y)) if weights is None else weights
    present = np.isfinite(score)
    flag = present & (score > cut)
    cells = [float(w[(y == c) & (flag == a)].sum()) for c in (0, 1) for a in (False, True)]
    tn, fp, fn, tp = cells
    sw = w[present]
    obs = y[present]
    p = score[present]

    def ratio(a, b):
        return float(a / b) if b else None

    cal = 0.0
    for i in range(10):
        sel = np.minimum((p * 10).astype(int), 9) == i
        if sel.any():
            cal += abs(np.dot(sw[sel], p[sel] - obs[sel]))
    return {
        "counts_tn_fp_fn_tp": cells,
        "coverage": ratio(sw.sum(), w.sum()),
        "effective_recall": ratio(tp, tp + fn),
        "false_alert_rate": ratio(fp, fp + tn),
        "precision": ratio(tp, tp + fp),
        "AP_scored": float(average_precision_score(obs, p, sample_weight=sw))
        if len(np.unique(obs)) == 2
        else None,
        "Brier_scored": ratio(np.dot(sw, (p - obs) ** 2), sw.sum()),
        "ECE10_scored": ratio(cal, sw.sum()),
    }


def interval(y, score, cut, groups):
    # Resample whole campaigns; preserve all requests within the unit. This
    # quantifies within-dataset heterogeneity, not native sampling uncertainty.
    unique, idx = np.unique(groups, return_inverse=True)
    idx = idx.reshape(-1)
    flag = (score > cut) & np.isfinite(score)
    stats = np.stack(
        [
            np.bincount(idx, weights=m, minlength=len(unique))
            for m in ((y == 1) & flag, y == 1, (y == 0) & flag, y == 0)
        ]
    )
    rng = np.random.default_rng(3203)
    draws = rng.integers(len(unique), size=(1000, len(unique)))
    counts = stats[:, draws].sum(axis=2)
    result = {}
    for label, a, b in (("recall", 0, 1), ("FPR", 2, 3)):
        valid = counts[b] > 0
        result[label] = {
            "valid_draws": int(valid.sum()),
            "percentile_95": np.quantile(
                counts[a, valid] / counts[b, valid], [0.025, 0.975]
            ).tolist()
            if valid.any()
            else None,
            "support_campaigns": int(np.count_nonzero(stats[b])),
        }
    return result


def evaluate(out):
    since = time.monotonic()
    spec = load_json(out / "external-lock.json")
    need(
        spec["code"] == file_sha256(__file__) and spec["base_sha"] == file_sha256(BASELINE),
        "LOCK_CHANGED",
    )
    need(
        file_sha256(out / "pilot-result.json") == spec["pilot"]
        and file_sha256(out / "neighbors-pilot.json") == spec["neighbors"],
        "PRESELECTION_CHANGED",
    )
    parent = load_json(out / "plan.json")
    for p, sha in parent["pins"].items():
        if p.endswith(".py") or p.endswith(".npz"):
            need(file_sha256(p) == sha, "FROZEN_INPUT_CHANGED")
    archive = out / "testbed_corpus.tar.gz"
    need(file_sha256(archive) == spec["frozen_archive"], "EXTERNAL_SOURCE_SHA")
    model_file = out / "pilot" / spec["model"]["file"]
    need(file_sha256(model_file) == spec["model"]["sha256"], "MODEL_SCOPE")
    model = joblib.load(model_file)  # Locally trained, pinned coefficient file.
    blocked = embargo()
    with tarfile.open(archive) as arc:
        members = arc.getmembers()
        need(
            len(members) == 1
            and members[0].isfile()
            and members[0].name == "data/corpus/labelled/testbed.parquet"
            and members[0].size < 2_000_000,
            "ARCHIVE_SCHEMA",
        )
        table = pq.ParquetFile(io.BytesIO(arc.extractfile(members[0]).read()))
        need(table.metadata.num_rows == 21136, "PUBLISHER_CARDINALITY")
        rows = table.read(columns=COLS, use_threads=False).to_pylist()
    id_counts = Counter(row["capture_id"] for row in rows)
    repeated_labels = {}
    for row in rows:
        if id_counts[row["capture_id"]] > 1:
            repeated_labels.setdefault(row["capture_id"], set()).add(row["label"])
    eligible_id = np.array([id_counts[row["capture_id"]] == 1 for row in rows])
    labels = []
    apps = []
    campaigns = []
    methods = []
    x = []
    pos = []
    cols = []
    ptr = [0]
    seen_in_fit = []
    ambiguous = []
    reasons = Counter()
    for i, row in enumerate(rows):
        key = row["capture_id"]
        need(
            key and row["campaign_id"] and row["label"] in ("benign", "attack"),
            "EXTERNAL_ID_OR_LABEL",
        )
        y = int(row["label"] == "attack")
        labels.append(y)
        apps.append(row["app"])
        campaigns.append(row["campaign_id"])
        method = row["http_method"]
        methods.append(method if method in ("GET", "POST") else "OTHER")
        if not eligible_id[i]:
            reasons["repeated_capture_id_entire_group_quarantined"] += 1
            continue
        if not str(row["label_source"]).startswith("campaign=" + row["campaign_id"] + " "):
            reasons["publisher_campaign_binding_unresolved"] += 1
            continue
        query = row["url_query"]
        path = row["url_path_raw"]
        if not isinstance(path, str) or not isinstance(query, str) or "?" in path:
            reasons["unavailable_or_ambiguous_path_query"] += 1
            continue
        target = path + ("?" + query if query else "")
        try:
            features = uri(target, method)
        except (PipelineError, ValueError):
            reasons["outside_pinned_raw_URI_ABI"] += 1
            continue
        if not query:
            try:
                different = not np.array_equal(features, uri(target + "?", method))
            except (PipelineError, ValueError):
                different = True
            if different:
                ambiguous.append(i)
        pos.append(i)
        x.append(features)
        seen_in_fit.append(features.tobytes() in blocked)
        cols.extend(project(target, row["request_body"]))
        ptr.append(len(cols))
    y = np.asarray(labels)
    pos = np.asarray(pos, dtype=int)
    x = np.asarray(x, np.float32)
    z = sparse.csr_matrix((np.ones(len(cols), np.float32), cols, ptr), shape=(len(pos), WIDTH))
    base = probabilities(cpu_session(BASELINE, 1), x)
    new = predict(model, spec["arm"], {"base": base, "x": x, "z": z})
    overlap = np.zeros(len(y), bool)
    overlap[pos] = seen_in_fit
    scored = np.zeros(len(y), bool)
    scored[pos] = True
    exact = np.ones(len(y), bool)
    exact[ambiguous] = False
    views = x.view(dtype=np.dtype((np.void, x.shape[1] * 4))).reshape(-1)
    _, inv, ct = np.unique(views, return_inverse=True, return_counts=True)
    weights = 1 / ct[inv.reshape(-1)]
    src = np.asarray(campaigns)
    summary = {}
    for arm, cut in spec["thresholds"].items():
        s = np.full(len(y), np.nan)
        s[pos] = new if arm == spec["arm"] else base
        summary[arm] = {
            "all": measure(y, s, cut),
            "singleton_id_roster": measure(y[eligible_id], s[eligible_id], cut),
            "scored_disjoint_URI100": measure(y[scored & ~overlap], s[scored & ~overlap], cut),
            "scored_reference_view_balanced": measure(y[pos], s[pos], cut, weights),
            "campaign_bootstrap": interval(y, s, cut, src),
            "without_empty_query_ambiguity": measure(y[exact], s[exact], cut),
            "applications": {
                a: measure(y[np.array(apps) == a], s[np.array(apps) == a], cut)
                for a in sorted(set(apps))
            },
            "methods": {
                a: measure(y[np.array(methods) == a], s[np.array(methods) == a], cut)
                for a in sorted(set(methods))
            },
        }
    augmented = [
        hashlib.sha256(
            v.tobytes() + z.indices[z.indptr[i] : z.indptr[i + 1]].astype("<i4").tobytes()
        ).digest()
        for i, v in enumerate(x)
    ]
    atomic_json(
        out / "external-result.json",
        {
            "lock_sha256": file_sha256(out / "external-lock.json"),
            "publisher_rows": len(y),
            "unique_capture_ids": len(id_counts),
            "keys_repeated": len(repeated_labels),
            "repeated_keys_with_conflicting_labels": sum(
                len(v) > 1 for v in repeated_labels.values()
            ),
            "singleton_roster_class_counts": np.bincount(y[eligible_id], minlength=2).tolist(),
            "class_benign_attack": np.bincount(y).tolist(),
            "campaigns": len(set(campaigns)),
            "apps": sorted(set(apps)),
            "scored": len(pos),
            "abstain": dict(reasons),
            "ABI_scored_rows_overlapping_development_URI100": int(overlap.sum()),
            "empty_query_alternate_changes_URI100": len(ambiguous),
            "indistinguishability": {
                "URI100": census(views, y[pos]),
                "plus_safe_uri_body": census(np.asarray(augmented, dtype="V32"), y[pos]),
            },
            "metrics": summary,
            "seconds": time.monotonic() - since,
            "native_admission": 0,
            "release_eligible": False,
        },
    )
    uri.cache_clear()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("lock", "evaluate"))
    p.add_argument("out", type=Path)
    args = p.parse_args()
    if args.mode == "lock":
        lock(args.out)
    else:
        need(not (args.out / "external-result.json").exists(), "EXTERNAL_ALREADY_EVALUATED")
        evaluate(args.out)
