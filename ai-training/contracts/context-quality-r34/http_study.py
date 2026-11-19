"""Compare typed request fields to frozen payload baselines using R32's admitted coordinates."""

import argparse
import hashlib
import sys
from pathlib import Path

import joblib
import numpy as np
from field_schema import FEATURES, WIDTH, project
from scipy import sparse
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingClassifier

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "information-r32"))
from dataset import B16_PIN, BASELINE, NAMES, need, origin_view, roster, rows  # noqa: E402
from experiment import census, cluster_delta, logodds, probabilities, sparse_head  # noqa: E402
from rank_pilot import collision_bound, gate, macro, metrics  # noqa: E402

OLD = REPO_ROOT / "ai-training/.artifacts/t09-r32-information-TIu0kTGQ/verified"
R20 = Path.home() / ".local/state/idps-r22-local/bundle/swiglu.onnx"
R20_PIN = "1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525"


def shard(run, name, full):
    dest = run / ("http-full" if full else "http-pilot")
    dest.mkdir(exist_ok=True)
    x, y, coords, groups, n, m = roster(name, full)
    loc = {int(c): j for j, c in enumerate(coords)}
    need(len(loc) == len(x) and not set(groups[:n]) & set(groups[n:]), "ROLE_OVERLAP")
    path = dest / (name + ".npz")
    marker = dest / (name + ".json")
    binding = {
        "plan": file_sha256(HERE / "plan.json"),
        "raw_manifest": file_sha256(OLD / "plan.json"),
        "schema": file_sha256(HERE / "field_schema.py"),
        "coordinates": hashlib.sha256(np.asarray(coords, dtype="<i8").tobytes()).hexdigest(),
    }
    if marker.exists():
        record = load_json(marker)
        need(
            record["binding"] == binding and file_sha256(path) == record["sha256"],
            "DERIVATIVE_CHANGED",
        )
    else:
        z = np.zeros((len(x), len(FEATURES)), dtype=np.uint8)
        present = np.zeros(len(x), bool)
        for c, method, raw, body, label in rows(name, coords):
            j = loc[c]
            target = origin_view(raw)
            need(not present[j] and target and (label is None or label == y[j]), "RECORD_BINDING")
            target = target[0]
            need(np.array_equal(from_request(target, method), x[j, :76]), "URI76_BINDING")
            z[j] = project(target, body)
            present[j] = True
        need(present.all(), "MISSING_RECORD")
        np.savez_compressed(path, z=z)
        atomic_json(
            marker,
            {
                "sha256": file_sha256(path),
                "fit": n,
                "total": len(x),
                "bindings": int(present.sum()),
                "binding": binding,
            },
        )
    with np.load(path) as a:
        z = a["z"]
    return x, y, groups, n, m, z


def identity(a):
    b = np.ascontiguousarray(a)
    return b.view(np.dtype((np.void, b.shape[1] * b.itemsize))).reshape(-1)


def field_probability(fields, coefficients):
    supported = fields.any(axis=1)
    # Strict score > cutoff; a nonnegative cutoff never alerts an unsupported observation.
    return np.where(supported, expit(fields @ coefficients), 0.0)


def study(run, full=False):
    if full:
        need(load_json(run / "http-pilot-result.json")["advance"], "FULL_GATE")
    old = load_json(OLD / "plan.json")
    for path, digest in old["pins"].items():
        need(file_sha256(Path(path)) == digest, "HISTORICAL_INPUT_CHANGED: " + Path(path).name)
    need(file_sha256(BASELINE) == B16_PIN and file_sha256(R20) == R20_PIN, "MODEL_PIN")
    base, ref = cpu_session(BASELINE, 1), cpu_session(R20, 1)
    data = {}
    cens = {}
    overlap = [[], []]
    for name in NAMES:
        x, y, g, n, m, z = shard(run, name, full)
        b = probabilities(base, x)
        r20 = probabilities(ref, np.ascontiguousarray(x[:, :76]))
        for role, idx in (("FIT", slice(None, n)), ("TUNING", slice(n, None))):
            v, h, lab = x[idx], z[idx], y[idx]
            key = identity(v)
            overlap[0 if role == "FIT" else 1].append(key)
            _, inv, count = np.unique(key, return_inverse=True, return_counts=True)
            w = m.copy().astype(float) if role == "FIT" else 1 / count[inv.ravel()]
            if role == "FIT":
                for label in (0, 1):
                    w[lab == label] /= 2 * w[lab == label].sum()
            data[name, role] = {
                "z": h,
                "base": b[idx],
                "r20": r20[idx],
                "y": lab,
                "group": g[idx],
                "w": w,
            }
            augmented = np.c_[np.ascontiguousarray(v).view(np.uint8).reshape(len(v), -1), h]
            both = np.intersect1d(key[lab == 1], key[lab == 0])
            ix = np.isin(key, both)
            detail = identity(augmented)
            _, detail_inv = np.unique(detail, return_inverse=True)
            cens[name + "_" + role] = {
                "class_counts": np.bincount(lab, minlength=2).tolist(),
                "groups": len(np.unique(g[idx])),
                "base_hindsight_ceiling": collision_bound(lab, inv.ravel(), len(count)),
                "augmented_hindsight_ceiling": collision_bound(
                    lab, detail_inv.ravel(), 1 + int(detail_inv.max())
                ),
                "roster": len(v),
                "URI100": census(key, lab),
                "augmented": census(identity(augmented), lab),
                "additional_views_in_mixed_base_groups": int(
                    len(np.unique(identity(augmented[ix]))) - len(both)
                ),
                "query_supported": int(np.any(h[:, :WIDTH], axis=1).sum()),
                "body_supported": int(np.any(h[:, WIDTH:], axis=1).sum()),
                "any_supported": int(np.any(h, axis=1).sum()),
            }
    need(not np.intersect1d(*[np.concatenate(v) for v in overlap]).size, "CROSS_SOURCE_OVERLAP")
    # Include only arms with actual new observations. A zero residual leaves B16 unchanged.
    info = any(cens[s + "_FIT"]["additional_views_in_mixed_base_groups"] > 0 for s in NAMES)
    frames = {s: data[s, "TUNING"] for s in NAMES}
    weights = {
        s: {"original_request": np.ones(len(f["y"])), "vector_balanced": f["w"]}
        for s, f in frames.items()
    }
    result = {}
    predictions = {}
    frozen = {}

    def save(arm, p):
        predictions[arm] = p
        result[arm] = metrics(p, frames, weights)

    save("B16", {s: f["base"] for s, f in frames.items()})
    save("R20", {s: f["r20"] for s, f in frames.items()})

    def rule(z):
        # Share a predeclared rule: quantity/type mismatch or conflicting duplicates.
        return z[:, [WIDTH - 4, WIDTH - 3, 2 * WIDTH - 4, 2 * WIDTH - 3]].astype(float).sum(axis=1)

    save("SCHEMA_RULE", {s: rule(f["z"]) for s, f in frames.items()})
    fs = [data[s, "FIT"] for s in NAMES]
    z = np.concatenate([f["z"] for f in fs])
    y = np.concatenate([f["y"] for f in fs])
    w = np.concatenate([f["w"] for f in fs]) / len(fs)
    offset = logodds(np.concatenate([f["base"] for f in fs]))
    winner = load_json(run / "http-pilot-result.json")["selected"] if full else None
    for arm in ("SCHEMA_LR", "B16_SCHEMA_RESIDUAL", "B16_SCHEMA_TREE"):
        if (full and arm != winner) or (arm != "SCHEMA_LR" and not info):
            continue
        if arm.endswith("TREE"):
            # Train only on fields with support. Fallback is exactly B16 on unobserved requests.
            have = z.any(axis=1)
            model = HistGradientBoostingClassifier(
                max_iter=60,
                max_leaf_nodes=7,
                min_samples_leaf=40,
                l2_regularization=2,
                early_stopping=False,
                random_state=34,
            )
            model.fit(np.c_[offset[have], z[have]], y[have], sample_weight=w[have] * len(y))

            def predict(f):
                a = f["z"].any(axis=1)
                p = f["base"].copy()
                if a.any():
                    p[a] = model.predict_proba(np.c_[logodds(p[a]), f["z"][a]])[:, 1]
                return p
        else:
            standalone = arm == "SCHEMA_LR"
            model, _ = sparse_head(
                sparse.csr_matrix(z, dtype=float), y, w, np.zeros(len(y)) if standalone else offset
            )

            def predict(f):
                if standalone:
                    return field_probability(f["z"], model)
                p = f["base"].copy()
                a = f["z"].any(axis=1)
                p[a] = expit(logodds(p[a]) + f["z"][a] @ model)
                return p

        dest = run / ("http-full" if full else "http-pilot") / (arm + ".joblib")
        joblib.dump(model, dest)
        frozen[arm] = file_sha256(dest)
        save(arm, {s: predict(f) for s, f in frames.items()})
    excluded = {}
    if not full:
        for omitted in NAMES:
            training = [data[s, "FIT"] for s in NAMES if s != omitted]
            zz = np.concatenate([f["z"] for f in training])
            yy = np.concatenate([f["y"] for f in training])
            ww = np.concatenate([f["w"] for f in training]) / len(training)
            head, _ = sparse_head(sparse.csr_matrix(zz, dtype=float), yy, ww, np.zeros(len(yy)))
            pred = {s: field_probability(f["z"], head) for s, f in frames.items()}
            excluded[omitted] = metrics(pred, frames, weights)["held_source_transfer"][omitted]
    comparisons = {k: gate(result["B16"], result[k], old) for k in frozen}
    selected = max(
        frozen, key=lambda k: (comparisons[k]["advance"], macro(result[k]["common_budget"]))
    )
    cut = result[selected]["development_threshold"]
    bcut = result["B16"]["development_threshold"]
    paired = {}
    for s, f in frames.items():
        p = predictions[selected][s]
        base_pred = f["base"] > bcut
        fired = p > cut
        rule_fired = predictions["SCHEMA_RULE"][s] > result["SCHEMA_RULE"]["development_threshold"]
        paired[s] = {
            **cluster_delta(f, p, f["base"], cut, bcut),
            "added_TP_vs_B16": int(np.sum((f["y"] == 1) & fired & ~base_pred)),
            "lost_TP_vs_B16": int(np.sum((f["y"] == 1) & ~fired & base_pred)),
            "candidate_only_TP_vs_schema_rule": int(np.sum((f["y"] == 1) & fired & ~rule_fired)),
            "candidate_only_FP_vs_schema_rule": int(np.sum((f["y"] == 0) & fired & ~rule_fired)),
        }
    atomic_json(
        run / ("http-full-result.json" if full else "http-pilot-result.json"),
        {
            "census": cens,
            "results": result,
            "comparison": comparisons,
            "selected": selected,
            "advance": bool(comparisons[selected]["advance"]),
            "paired": paired,
            "unseen_source_schema_LR": excluded,
            "model_shas": frozen,
            "B16_sha": B16_PIN,
            "R20_sha": R20_PIN,
            "new_information": info,
            "plan_sha": file_sha256(HERE / "plan.json"),
            "schema_code_sha": file_sha256(HERE / "field_schema.py"),
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    a = p.parse_args()
    study(a.run)
    if load_json(a.run / "http-pilot-result.json")["advance"]:
        study(a.run, True)
