"""Bounded R23 capacity audit and same-roster WAF TUNING evaluation."""

import argparse
import os
import secrets
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import blake2s
from pathlib import Path

import numpy as np
import r16_waf as waf
from r18_data import check, read, status
from r19_metrics import metrics_both
from r19_train import training_cells
from r20_calibration import uri76_oracle
from r20_quality import PINS, R19
from r21_quality import BASE, R20, R20_ONNX, R20_SELECTION, advances, dual_cut
from r23_features import LANES, VERSION, numeric, sketch
from sklearn.linear_model import LogisticRegression

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request, schema

SEED = 2301
CAP = 8  # Degree of original diversity per URI76/label cell in small FIT.


def equivalent(groups, labels, values, positives=None):
    unique, inv = np.unique(values, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    counts = np.zeros((len(unique), 2), dtype=np.int64)
    np.add.at(counts, (inv, labels), 1)
    mixed = np.all(counts > 0, axis=1)
    sizes = counts.sum(axis=1)
    result = {
        "originals": len(labels),
        "unique": len(unique),
        "mixed": int(mixed.sum()),
        "originals_in_mixed": int(sizes[mixed].sum()),
        "anomalous_in_mixed": int(counts[mixed, 1].sum()),
        "originals_in_colliding_vectors": int(sizes[sizes > 1].sum()),
        "minority_label_mass": int(counts.min(axis=1).sum()),
        "max_originals_sharing_vector": int(sizes.max()),
    }
    if positives is not None:
        result["anchor_false_negatives_with_no_normal_in_new_vector"] = int(
            np.count_nonzero(positives & (counts[inv, 0] == 0))
        )
        result["within_old_mixed_group_anchor_fn_now_anomalous_only"] = int(
            np.count_nonzero(positives & groups & (counts[inv, 0] == 0))
        )
    return result, unique, inv, counts


def tally_targets(counts, pairs):
    diversity = Counter(group for group, _ in pairs)
    targets = defaultdict(int)
    for (_, opaque), label in pairs.items():
        targets[opaque] |= label
    peak = int(np.argmax(counts.sum(axis=1)))
    return {
        "originals": int(counts.sum()),
        "uri76_vectors": len(diversity),
        "distinct_normalized_method_target": len(targets),
        "method_target_mixed_label": sum(v == 3 for v in targets.values()),
        "uri76_groups_merging_distinct_targets": sum(size > 1 for size in diversity.values()),
        "max_distinct_targets_in_one_uri76": max(diversity.values()),
        "largest_uri76_group_original_count": int(counts[peak].sum()),
        "largest_uri76_group_distinct_method_target": diversity[peak],
    }


def select_fit(index, labels):
    rng = np.random.default_rng(SEED)
    # NPZ coordinates are ordered by cell, but make the grouping explicit.
    key = index.astype(np.int64) * 2 + labels
    order = np.argsort(key, kind="stable")
    starts = np.r_[0, np.flatnonzero(np.diff(key[order])) + 1, len(key)]
    result = np.zeros(len(key), dtype=bool)
    for a, b in zip(starts, starts[1:]):
        subset = order[a:b]
        picked = rng.choice(subset, CAP, replace=False) if len(subset) > CAP else subset
        result[picked] = True
    return result


def scan(out, x, counts, index, coords, y, num_fit, picked):
    status(out, "JOIN_PINNED_WAF_TRAIN")
    order = np.argsort(coords)
    ordinals = coords[order]
    check(len(np.unique(ordinals)) == len(coords), "Duplicate original coordinate")
    positions = np.full(len(coords), -1, dtype=np.int64)
    positions[picked] = np.arange(picked.sum())
    features = {
        name: np.zeros((picked.sum(), width), dtype=np.uint8) for name, width in LANES.items()
    }
    key = secrets.token_bytes(32)
    pairs = [{}, {}]
    offsets = 0
    measured_ns = []
    parity_sketches = set()
    seen = 0

    @lru_cache(maxsize=32768)
    def encode(method, target):
        start = time.perf_counter_ns()
        base = from_request(target, method).tobytes()
        lane = sketch(target)
        result = numeric(*lane)
        measured_ns.append(time.perf_counter_ns() - start)
        if len(parity_sketches) < 256:
            parity_sketches.add(lane)
        return base, result

    for batch in waf.source().iter_batches(
        batch_size=waf.BATCH, columns=["method", "url", "label"], use_threads=False
    ):
        end = offsets + batch.num_rows
        low, high = np.searchsorted(ordinals, [offsets, end])
        if high > low:
            records = batch.take(ordinals[low:high] - offsets).to_pylist()
            for own, raw in zip(order[low:high], records, strict=True):
                origin = waf.origin_view(raw["url"])
                check(
                    origin and waf.LABEL[raw["label"]] == y[own], "Pinned publisher join mismatch"
                )
                target, _, _ = origin
                method = raw["method"]
                # Salted diagnostic key stays in memory. No target hash is a feature.
                opaque = blake2s(
                    method.encode() + b"\0" + target.encode(), key=key, digest_size=16
                ).digest()
                pair = pairs[int(own >= num_fit)]
                k = (int(index[own]), opaque)
                pair[k] = pair.get(k, 0) | (1 << int(y[own]))
                if picked[own]:
                    expected, extra = encode(method, target)
                    check(expected == x[index[own]].tobytes(), "URI76 bytes disagree with R19")
                    for (name, values), extension in zip(features.items(), extra, strict=True):
                        values[positions[own]] = extension
                seen += 1
        offsets = end
    check(seen == len(coords), "Missing source coordinate")
    target_sets = [{opaque for _, opaque in part} for part in pairs]
    overlap = len(set.intersection(*target_sets))
    check(overlap == 0, "Method/target overlaps development partitions")
    result = {
        "fit": tally_targets(
            counts * np.isin(np.arange(len(counts)), index[:num_fit])[:, None], pairs[0]
        ),
        "tuning": tally_targets(
            counts * np.isin(np.arange(len(counts)), index[num_fit:])[:, None], pairs[1]
        ),
        "normalized_method_target_exact_overlap": overlap,
        "publisher_exact_original_conflicts_already_quarantined": 10,
        "publisher_noise_rate": "UNIDENTIFIABLE_WITHOUT_INDEPENDENT_REVIEW",
        "cold_projection_ns_p50_p95_including_uri76": [
            float(v) for v in np.percentile(measured_ns, [50, 95])
        ],
        "raw_inputs_persisted": False,
        "selected_original_coordinates": int(picked.sum()),
    }
    # Retain only the public finite-alphabet sketch for independent Rust parity.
    with (out / "parity-sketch.tsv").open("w", encoding="ascii") as f:
        for path, query in sorted(parity_sketches):
            f.write(path.decode() + "\t" + query.decode() + "\n")
    return features, result


def grouped_scores(matrix, labels, scores):
    _, _, inv, counts = equivalent(None, labels, matrix)
    first = np.unique(inv, return_index=True)[1]
    vector_scores = scores[first]
    np.testing.assert_allclose(vector_scores[inv], scores, rtol=1e-6, atol=1e-6)
    return counts, vector_scores


def run(out, blend=False):
    for name, sha in PINS.items():
        check(file_sha256(R19 / name) == sha, f"R19 pin mismatch {name}")
    check(file_sha256(waf.WAF) == waf.WAF_SHA, "WAF publisher TRAIN hash mismatch")
    check(
        file_sha256(R20 / "bundle/swiglu.onnx") == R20_ONNX
        and file_sha256(R20 / "calibration-selection.json") == R20_SELECTION,
        "R20 pin mismatch",
    )
    atomic_json(
        out / "plan.json",
        {
            "schema": VERSION,
            "uri76": schema(),
            "lanes": LANES,
            "pins": PINS | {"publisher_train": waf.WAF_SHA, "r20_onnx": R20_ONNX},
            "runner_sha256": file_sha256(__file__),
            "feature_sha256": file_sha256(Path(__file__).with_name("r23_features.py")),
            "roles": "R19 FIT sampled at 8 originals per vector/label; full R19 TUNING; no sealed or exposed HOLDOUT scored",
            "weighting": "R19 class-balanced capped vector mass restored exactly over sampled originals",
            "scale_gate": "At least 5% tuning unique gain, >=2pp request recall over frozen R20 and no vector recall or AP loss beyond R21 tolerances, FPR <=1% on both development estimands",
            "selection": "FIT→TUNING only. Independence beyond publisher grouped split unavailable",
            "sample_seed": SEED,
            "sample_cap": CAP,
            "blend_protocol": (
                {
                    "anchor": "raw frozen R19 SwiGLU",
                    "structure_score_weights": [0.15, 0.30],
                    "scope": "Only TUNING, predeclared finite grid, retain R20 if scale gate fails",
                }
                if blend
                else None
            ),
        },
    )
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as sealed:
        # Read only the admitted FIT and TUNING coordinates, never the holdout arrays.
        groups = {name: sealed[name] for name in ("x", "counts", "component", "role")}
        x, counts = groups["x"], groups["counts"]
        source = [
            [sealed[f"{role}_{name}"] for name in ("index", "row", "label")]
            for role in ("fit", "tuning")
        ]
    index, coords, labels = [
        np.concatenate((left, right)) for left, right in zip(*source, strict=True)
    ]
    nfit = len(source[0][0])
    check(
        len(np.intersect1d(groups["component"][index[:nfit]], groups["component"][index[nfit:]]))
        == 0,
        "Lineage overlap",
    )
    picked = np.r_[select_fit(index[:nfit], labels[:nfit]), np.ones(len(index) - nfit, dtype=bool)]
    features, census = scan(out, x, counts, index, coords, labels, nfit, picked)
    atomic_json(out / "collision-audit.json", census)
    status(out, "FIT_PAIRED_LOGISTIC_ARMS")
    fit_groups, fit_pick = np.unique(index[:nfit]), int(picked[:nfit].sum())
    x, y, group = x[index[picked]], labels[picked], index[picked]
    sample_counts = np.zeros_like(counts)
    np.add.at(sample_counts, (group[:fit_pick], y[:fit_pick]), 1)
    cells, cell_labels, weights, balance, _ = training_cells(counts[fit_groups])
    mass = np.zeros_like(counts, dtype=np.float64)
    mass[fit_groups[cells], cell_labels] = weights * balance[cell_labels]
    sample_weight = (
        mass[group[:fit_pick], y[:fit_pick]] / sample_counts[group[:fit_pick], y[:fit_pick]]
    )
    arms, capacities = {}, {}
    xt, yt = x[fit_pick:], y[fit_pick:]
    for name, path, cutoff in (
        (
            "r19_logistic",
            R19 / "bundle/logistic.onnx",
            read(R19 / "selection.json")["tuning"]["logistic"]["vector_balanced"]["threshold"],
        ),
        (BASE, R20 / "bundle/swiglu.onnx", read(R20 / "calibration-selection.json")["cutoff"]),
    ):
        scores = cpu_session(path, 1).run(["score"], {"input": xt})[0]
        truth, scores_per = grouped_scores(xt, yt, scores)
        arms[name] = metrics_both(truth, scores_per, cutoff)
        if name == BASE:
            missed = (scores <= cutoff) & (yt == 1)
    old_mixed = np.all(counts[group[fit_pick:]] > 0, axis=1)
    models = {"pilot_uri76": x} | {
        name: np.column_stack((x, values.astype(np.float32) / (31 if name == "structure" else 15)))
        for name, values in features.items()
    }
    for name, matrix in models.items():
        model = LogisticRegression(C=1, max_iter=600, random_state=SEED).fit(
            matrix[:fit_pick], y[:fit_pick], sample_weight=sample_weight
        )
        check(model.n_iter_.max() < 600, f"Logistic convergence {name}")
        tune_matrix = matrix[fit_pick:]
        stats, unique, inv, counts_t = equivalent(old_mixed, yt, tune_matrix, missed)
        fit_stats, _, _, _ = equivalent(None, y[:fit_pick], matrix[:fit_pick])
        coarse_fit = {v.tobytes() for v in np.unique(np.floor(matrix[:fit_pick] * 16), axis=0)}
        coarse_tune = {v.tobytes() for v in np.unique(np.floor(tune_matrix * 16), axis=0)}
        check(not coarse_tune.intersection(coarse_fit), "Inherited coarse overlap")
        scores = model.predict_proba(unique)[:, 1].astype(np.float32)
        cut = dual_cut(counts_t, scores)
        arms[name] = metrics_both(counts_t, scores, cut)
        stats["ceiling_from_tuning_labels"] = uri76_oracle(counts_t)
        stats["mixed_uri76_panel_detected_anomalous"] = int(
            np.sum((scores[inv] > cut) & (yt == 1) & old_mixed)
        )
        capacities[name] = {"fit_sample": fit_stats, "tuning": stats}
        if name == "structure" and blend:
            raw = cpu_session(R19 / "bundle/swiglu.onnx", 1).run(["score"], {"input": xt})[0]
            # Every combined input keeps the URI76 prefix so the anchor score
            # is constant within each extension representation.
            _, raw_group = grouped_scores(tune_matrix, yt, raw)
            for weight in (0.15, 0.30):
                key = f"structure_blend_{int(weight * 100)}"
                combined = ((1 - weight) * raw_group + weight * scores).astype(np.float32)
                cut = dual_cut(counts_t, combined)
                arms[key] = metrics_both(counts_t, combined, cut)
                capacities[key] = {
                    "fit_sample": fit_stats,
                    "tuning": stats
                    | {
                        "mixed_uri76_panel_detected_anomalous": int(
                            np.sum((combined[inv] > cut) & (yt == 1) & old_mixed)
                        )
                    },
                }
    base = capacities["pilot_uri76"]["tuning"]["unique"]
    candidates = [
        name
        for name in capacities
        if name != "pilot_uri76"
        if capacities[name]["tuning"]["unique"] >= 1.05 * base
        and advances(arms[name], arms[BASE], tuning=True)
    ]
    sys.path.insert(0, str(REPO_ROOT / "ai-training/contracts/local-acceptance-v1"))
    from readiness import reviewed

    native = reviewed()
    atomic_json(
        out / "pilot.json",
        {
            "scope": "WAF_PUBLISHER_NORMAL_ANOMALOUS_TUNING_ONLY",
            "fit_sample_size": fit_pick,
            "metrics": arms,
            "capacity": capacities,
            "eligible_to_scale": candidates,
            "best_reference": BASE,
            "native": {k: v for k, v in native.items() if k != "requests"},
            "sealed_test_read": False,
            "r19_exposed_holdout_read": False,
        },
    )
    atomic_json(
        out / "status.json",
        {"state": "PILOT_COMPLETED", "run_id": out.name, "eligible_to_scale": candidates},
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--blend", action="store_true")
    args = parser.parse_args()
    run(args.out, args.blend)
