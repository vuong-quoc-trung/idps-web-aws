"""One frozen B16 method-tail calibration experiment on authorized research roles."""

import argparse
import time
import zipfile
from pathlib import Path

import numpy as np
from scipy.special import logit
from sklearn.metrics import average_precision_score

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import schema

ROOT = REPO_ROOT / "ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3"
BASELINE = (
    REPO_ROOT / "ai-training/.artifacts/t09-r261-recovery-drliluc_/research-bundle/model.onnx"
)
B16_PIN = "fdff05ee91f181268121ee7c72e573a4b2d771c3a8ee60cfa28e9d11860f2271"
FOLDERS = {"NOTES": "notes", "SRBH": "source2-recovery"}
CAP = 0.01
MIN_NEGATIVE_VIEWS = 200
MIN_GROUPS = 10
METHODS = ("GET", "POST", "OTHER")
PUBLISHED_CUTOFF = 0.9420260190963745


def need(condition, reason):
    if not condition:
        raise PipelineError(reason)


def plan(run):
    pins = {}
    waf = ROOT / "data-v2"
    manifest = load_json(waf / "waf-manifest.json")
    need(
        manifest["roles_preserved"] is True
        and manifest["protected_payloads_read"] is False
        and manifest["publisher_eval_test_heldout_read"] is False,
        "WAF_ROLE_SCOPE_MISMATCH",
    )
    pins[str(waf / "waf-r26.npz")] = manifest["dataset_sha256"]
    for directory in FOLDERS.values():
        path = ROOT / directory
        manifest = load_json(path / "manifest.json")
        for role in ("CAL_FIT", "TUNING"):
            pins[str(path / f"{role.lower()}.npz")] = manifest["roles"][role]["sha256"]
    pins[str(BASELINE)] = B16_PIN
    forensics = load_json(run / "forensic-census.json")
    pins[str(run / "forensic-unlabeled-uri100.npz")] = forensics[
        "unlabeled_numeric_derivative_sha256"
    ]
    for name, expected in pins.items():
        need(file_sha256(name) == expected, "RESEARCH_INPUT_SHA_MISMATCH")
    path = run / "calibration-plan.json"
    need(not path.exists(), "FROZEN_PLAN_ALREADY_EXISTS")
    atomic_json(
        path,
        {
            "experiment": "ONE_METHOD_CONDITIONAL_BENIGN_TAIL_OFFSET",
            "inputs": pins,
            "code_sha256": file_sha256(__file__),
            "baseline": "Frozen B16 calibrated ONNX and published strict threshold",
            "calibration_role": "Existing NOTES/SRBH CAL_FIT only; exact TUNING-vector overlap removed from fit",
            "evaluation_role": "WAF/NOTES/SRBH TUNING only; thresholds discarded",
            "tail_fpr": CAP,
            "method_groups": list(METHODS),
            "minimum_method_negatives": {
                "distinct_views": MIN_NEGATIVE_VIEWS,
                "groups": MIN_GROUPS,
            },
            "selection": {
                "minimum_macro_recall_gain": 0.05,
                "maximum_per_source_recall_loss": 0.02,
                "held_source_transfer_fpr_cap": CAP,
                "minimum_held_source_macro_recall_gain": 0.0,
            },
            "transfer": "Diagnostic strict cut from other TUNING sources; original and vector caps applied jointly",
            "weights_retrained": False,
            "external_profile": "Frozen B16 unlabeled coverage only; excluded from fit and selection",
        },
    )


def waf_tuning(path):
    # Stream only the x.npy suffix into memory. The archive roles are FIT/TUNING.
    with np.load(path, allow_pickle=False) as data:
        nfit = int(data["nfit"])
        y = data["y"][nfit:].copy()
        group = data["component"][nfit:].copy()
    with zipfile.ZipFile(path) as archive, archive.open("x.npy") as stream:
        need(np.lib.format.read_magic(stream) == (1, 0), "WAF_NPY_HEADER_VERSION")
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
        need(
            not fortran and dtype == np.dtype("<f4") and shape == (nfit + len(y), 244),
            "WAF_ARRAY_SCOPE_MISMATCH",
        )
        stride = shape[1] * dtype.itemsize
        stream.seek(stream.tell() + nfit * stride)
        raw = stream.read(len(y) * stride)
        need(len(raw) == len(y) * stride, "WAF_TUNING_TRUNCATED")
    return make_frame(np.frombuffer(raw, dtype=dtype).reshape(len(y), 244), y, group)


def make_frame(values, y, group):
    x = np.ascontiguousarray(values[:, :100], dtype=np.float32)
    need(
        x.shape == (len(y), 100)
        and len(y) == len(group)
        and np.isfinite(x).all()
        and set(np.unique(y)) <= {0, 1},
        "BAD_RESEARCH_FRAME",
    )
    columns = schema()["columns"]
    get, post = (x[:, columns.index("method_" + name)] == 1 for name in METHODS[:2])
    need(not (get & post).any(), "INVALID_METHOD_FEATURES")
    method = np.where(get, 0, np.where(post, 1, 2))
    return {"x": x, "y": y, "group": group, "method": method}


def role(folder, role_name):
    with np.load(ROOT / folder / f"{role_name.lower()}.npz", allow_pickle=False) as z:
        return make_frame(z["x"], z["y"], z["group"])


def vectors(x):
    return np.unique(x, axis=0, return_inverse=True, return_counts=True)


def score(session, frame):
    unique, inverse, counts = vectors(frame["x"])
    scores = session.run(["score"], {"input": unique})[0].astype(np.float64).reshape(-1)
    need(
        len(scores) == len(unique)
        and np.isfinite(scores).all()
        and ((scores >= 0) & (scores <= 1)).all(),
        "INVALID_B16_SCORES",
    )
    inverse = inverse.reshape(-1)
    return scores[inverse], 1.0 / counts[inverse], inverse, counts


def cut_at_cap(scores, negative_weights, target=CAP):
    values, pos = np.unique(scores, return_inverse=True)
    mass = np.bincount(pos, weights=negative_weights)
    support = mass.sum()
    need(support > 0, "NO_BENIGN_SUPPORT")
    upper = np.cumsum(mass[::-1])[::-1]
    return float(values[np.flatnonzero(upper > support * target)[-1]])


def compare(y, scores, cutoff, weight):
    p = scores > cutoff
    neg, pos = y == 0, y == 1
    n, a = weight[neg].sum(), weight[pos].sum()
    fp, tp = weight[neg & p].sum(), weight[pos & p].sum()
    return {
        "recall": float(tp / a),
        "FPR": float(fp / n),
        "precision": float(tp / (tp + fp)) if tp + fp else None,
        "AP": float(average_precision_score(y, scores, sample_weight=weight)),
        "confusion": [float(n - fp), float(fp), float(a - tp), float(tp)],
    }


def collision_bound(y, inverse, num_views):
    counts = np.zeros((num_views, 2), dtype=np.int64)
    np.add.at(counts, (inverse, y), 1)
    mixed = (counts > 0).all(axis=1)
    neg, pos = counts[mixed].T
    safe_pos = counts[counts[:, 0] == 0, 1].sum()
    remaining = int(np.floor(CAP * counts[:, 0].sum()))
    best = float(safe_pos)
    for index in np.argsort(-(pos / neg), kind="stable"):
        take = min(remaining, neg[index])
        best += take * pos[index] / neg[index]
        remaining -= take
        if not remaining:
            break
    return {
        "unique_vectors": num_views,
        "mixed_label_vectors": int(mixed.sum()),
        "positive_in_mixed_vectors": int(pos.sum()),
        "hindsight_zero_FPR_URI100_recall_ceiling": float(safe_pos / counts[:, 1].sum()),
        "hindsight_fractional_upper_bound_at_1pct_FPR": float(best / counts[:, 1].sum()),
    }


def unlabeled_profile(run, session, tuning_views):
    with np.load(run / "forensic-unlabeled-uri100.npz", allow_pickle=False) as archive:
        values = archive["x"]
        mass = archive["observed_count"]
    scores = session.run(["score"], {"input": values})[0].reshape(-1)
    common = np.array([view.tobytes() in tuning_views for view in values])
    flagged = scores > PUBLISHED_CUTOFF
    return {
        "scope": "UNLABELED_NOT_FPR_OR_RECALL",
        "exact_uri100_overlap_with_tuning": int(common.sum()),
        "uri100_views_outside_tuning": int((~common).sum()),
        "frozen_B16_flag_rate_by_log_observation": float(mass[flagged].sum() / mass.sum()),
        "frozen_B16_flag_rate_by_view": float(flagged.mean()),
    }


def execute(run):
    started = time.monotonic()
    plan_path = run / "calibration-plan.json"
    spec = load_json(plan_path)
    need(spec["code_sha256"] == file_sha256(__file__), "CALIBRATION_CODE_DIGEST_CHANGED")
    for name, expected in spec["inputs"].items():
        need(file_sha256(name) == expected, "RESEARCH_INPUT_SHA_MISMATCH")
    cohort = {"WAF": waf_tuning(ROOT / "data-v2/waf-r26.npz")}
    cohort.update({name: role(folder, "TUNING") for name, folder in FOLDERS.items()})
    held_views = {row.tobytes() for frame in cohort.values() for row in frame["x"]}
    session = cpu_session(BASELINE, 1)
    fit, removed, group_count = [], {}, 0
    for name, folder in FOLDERS.items():
        frame = role(folder, "CAL_FIT")
        y = frame["y"]
        selected = (y == 0) & np.array([row.tobytes() not in held_views for row in frame["x"]])
        removed[name] = int((y == 0).sum() - selected.sum())
        frame = {key: value[selected] for key, value in frame.items()}
        scores, weights, *_ = score(session, frame)
        group_count += len(np.unique(frame["group"]))
        fit.append((scores, weights, frame["method"], frame["x"], frame["group"], name))
    all_scores, all_weights, all_methods, all_views = (
        np.concatenate([item[i] for item in fit]) for i in range(4)
    )
    group_tokens = np.concatenate(
        [np.array([f"{item[5]}:{value}" for value in item[4]]) for item in fit]
    )
    need(len(np.unique(group_tokens)) == group_count, "CAL_GROUP_NAMESPACE_MISMATCH")
    offset_summary = {}
    offsets = np.zeros(3)
    global_cut = cut_at_cap(all_scores, all_weights)
    to_logit = lambda s: logit(np.clip(s, 1e-12, 1 - 1e-12))  # noqa: E731
    for i, name in enumerate(METHODS):
        keep = all_methods == i
        support = len(np.unique(all_views[keep], axis=0))
        components = len(np.unique(group_tokens[keep]))
        eligible = support >= MIN_NEGATIVE_VIEWS and components >= MIN_GROUPS
        cut = cut_at_cap(all_scores[keep], all_weights[keep]) if eligible else global_cut
        offsets[i] = to_logit(cut) - to_logit(global_cut)
        offset_summary[name] = {
            "support_distinct_benign_views": support,
            "groups": components,
            "fallback_to_pooled": not eligible,
            "logit_offset": float(offsets[i]),
        }

    scores_by_source, weights, collisions = {}, {}, {}
    for name, frame in cohort.items():
        base, vector_weight, ids, counts = score(session, frame)
        scores_by_source[name] = {
            "B16": to_logit(base),
            "METHOD_TAIL": to_logit(base) - offsets[frame["method"]],
        }
        weights[name] = {"original_request": np.ones(len(base)), "vector_balanced": vector_weight}
        collisions[name] = collision_bound(frame["y"], ids, len(counts))

    def threshold(arm, names):
        return max(
            cut_at_cap(scores_by_source[name][arm], w * (cohort[name]["y"] == 0))
            for name in names
            for w in weights[name].values()
        )

    def evaluate(arm, source, cutoff):
        return {
            metric: compare(cohort[source]["y"], scores_by_source[source][arm], cutoff, w)
            for metric, w in weights[source].items()
        }

    primary, transfer = {}, {}
    for arm in ("B16", "METHOD_TAIL"):
        cutoff = threshold(arm, cohort)
        primary[arm] = {
            "threshold_experiment_only": cutoff,
            "sources": {name: evaluate(arm, name, cutoff) for name in cohort},
        }
        transfer[arm] = {
            target: evaluate(arm, target, threshold(arm, set(cohort) - {target}))
            for target in cohort
        }
    macro = lambda d: float(np.mean([v["original_request"]["recall"] for v in d.values()]))  # noqa: E731
    gain = macro(primary["METHOD_TAIL"]["sources"]) - macro(primary["B16"]["sources"])
    losses = {
        name: primary["METHOD_TAIL"]["sources"][name]["original_request"]["recall"]
        - primary["B16"]["sources"][name]["original_request"]["recall"]
        for name in cohort
    }
    transfer_gain = macro(transfer["METHOD_TAIL"]) - macro(transfer["B16"])
    worst_transfer_fpr = max(
        m["FPR"] for cell in transfer["METHOD_TAIL"].values() for m in cell.values()
    )
    advance = (
        gain >= 0.05
        and min(losses.values()) >= -0.02
        and worst_transfer_fpr <= CAP
        and transfer_gain > 0
    )
    return {
        "version": "idps-r30-calibration-pilot-v1",
        "plan_sha256": file_sha256(plan_path),
        "time_seconds": time.monotonic() - started,
        "rows_by_source": {
            n: np.bincount(frame["y"], minlength=2).tolist() for n, frame in cohort.items()
        },
        "overlapping_negative_cal_fit_rows_removed": removed,
        "method_offset_fit": offset_summary,
        "TUNING_matched_fpr": primary,
        "TUNING_held_source_threshold_transfer": transfer,
        "B16_frozen_operating_point": {
            name: evaluate("B16", name, float(to_logit(PUBLISHED_CUTOFF))) for name in cohort
        },
        "external_unlabeled_profile": unlabeled_profile(run, session, held_views),
        "URI100_collision_diagnostics": collisions,
        "macro_recall_gain": gain,
        "recall_delta_by_source": losses,
        "held_source_macro_recall_gain": transfer_gain,
        "worst_candidate_held_source_fpr": worst_transfer_fpr,
        "decision": "RESEARCH_FOLLOWUP_JUSTIFIED" if advance else "RETAIN_B16_REJECT_METHOD_TAIL",
        "scope": "PUBLISHER_DEVELOPMENT_ONLY",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "run"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "plan":
        plan(args.output)
    else:
        output = args.output / "calibration-pilot.json"
        need(not output.exists(), "PILOT_ALREADY_RUN")
        atomic_json(output, execute(args.output))
