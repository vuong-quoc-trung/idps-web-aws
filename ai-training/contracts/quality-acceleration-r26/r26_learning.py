"""Shared count-preserving research objectives and source/profile evaluation."""

# isort: skip_file

import math

import numpy as np

from r26_common import R25, SEED, check, file_sha256, read
from r26_features import FULL_WIDTH, URI_WIDTH
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.schedule import learning_rate
from r18_train import WeightedSwiGLU
from r19_metrics import metrics_both
from r20_calibration import threshold
from r23_pilot import grouped_scores

BATCH = 2048


def source_data(out, pilot=False):
    path = out / "data-v2/waf-r26.npz"
    manifest = read(out / "data-v2/waf-manifest.json")
    check(file_sha256(path) == manifest["dataset_sha256"], "WAF R26 tensor binding")
    with np.load(path, allow_pickle=False) as z:
        nfit = int(z["nfit"])
        if pilot:
            position = z["pilot_position"]
            fit, y, mass = z["x"][position], z["y"][position], z["pilot_mass"]
        else:
            fit, y, mass = z["x"][:nfit], z["y"][:nfit], None
        tune = {
            "x": z["x"][nfit:],
            "y": z["y"][nfit:],
            "group": z["component"][nfit:],
            "method": z["context"][nfit:, 0],
        }
    new = read(out / "notes/manifest.json")
    parts = {}
    for role in ("FIT", "TUNING"):
        p = out / "notes" / f"{role.lower()}.npz"
        check(file_sha256(p) == new["roles"][role]["sha256"], "Synthetic source role pin")
        with np.load(p, allow_pickle=False) as z:
            parts[role] = {name: z[name] for name in z.files}
    train = [(fit, y, mass), (parts["FIT"]["x"], parts["FIT"]["y"], None)]
    return train, {"WAF": tune, "NOTES_SYNTHETIC": parts["TUNING"]}


def cells(x, y, width, original_mass=None):
    unique, inverse = np.unique(x[:, :width], axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    counts = np.zeros((len(unique), 2), np.int64)
    np.add.at(counts, (inverse, y), 1)
    if original_mass is None:
        each = np.minimum(8, np.sqrt(counts.sum(axis=1))) / counts.sum(axis=1)
        mass = counts * each[:, None]
    else:
        mass = np.zeros_like(counts, dtype=np.float64)
        np.add.at(mass, (inverse, y), original_mass)
    row, label = np.nonzero(counts)
    value = mass[row, label]
    for cls in (0, 1):
        included = label == cls
        check(included.any() and value[included].sum() > 0, "Both source classes required")
        value[included] /= 2 * value[included].sum()
    return (
        unique[row],
        label.astype(np.int8),
        value,
        {
            "originals": len(y),
            "unique_vectors": len(unique),
            "mixed_vectors": int(np.all(counts > 0, axis=1).sum()),
            "minority_mass": int(counts.min(axis=1).sum()),
            "original_normal_anomalous": np.bincount(y, minlength=2).tolist(),
        },
    )


def make_training(train, width):
    xs, ys, weights, report = [], [], [], []
    for x, y, mass in train:
        cx, cy, cw, meta = cells(x, y, width, mass)
        if width == FULL_WIDTH:
            missing = cx.copy()
            missing[:, URI_WIDTH:] = 0
            xs.extend((cx, missing))
            ys.extend((cy, cy))
            weights.extend((cw / 2, cw / 2))
            meta["auxiliary_missing_content_views"] = (
                "Half loss mass, same original identities and role"
            )
        else:
            xs.append(cx)
            ys.append(cy)
            weights.append(cw)
        report.append(meta)
    x, y, weight = np.concatenate(xs), np.concatenate(ys), np.concatenate(weights)
    # Each source contributes equal mass, each source/class contributes half.
    weight *= len(weight) / weight.sum()
    return x, y, weight, report


def warm(width):
    root = R25 / "training/uri100"
    pointer = read(root / "best.json")
    check(
        pointer["manifest_sha256"]
        == "b96f2d8e686519160261b6305a4b1ce896722cebfe9240bf084d646af654e20b",
        "R25 warm-start checkpoint pin",
    )
    saved = load_checkpoint(root / pointer["path"])
    source = saved.model
    model = WeightedSwiGLU(
        width,
        204,
        "residual_glu",
        SEED,
        objective=dict(source.objective, binary_class_weights=[1.0, 1.0]),
        regularization={
            k: source.regularization[k] for k in ("dropout", "label_smoothing", "weight_decay")
        },
    )
    for name, value in source.parameters.items():
        if name == "Win":
            model.parameters[name].fill(0)
            model.parameters[name][:100] = value
        else:
            model.parameters[name][:] = value
    return model


def schedule_for(cells_count, epochs):
    return {
        "scheduler": "warmup_cosine",
        "learning_rate": 0.0003,
        "warmup_steps": 5,
        "total_steps": epochs * math.ceil(cells_count / BATCH),
        "min_lr_ratio": 0.1,
    }


def epoch(model, x, y, mass, number, schedule):
    permutation = np.random.default_rng(SEED + number).permutation(len(y))
    losses = [
        model.train_original_batch(x[p], y[p], mass[p], learning_rate(schedule, model.steps))
        for p in np.array_split(permutation, math.ceil(len(y) / BATCH))
    ]
    return permutation, float(np.mean(losses))


def views(x, width):
    uri = x[:, :width].copy()
    if width == FULL_WIDTH:
        uri[:, URI_WIDTH:] = 0
        return {"URI_ONLY": uri, "OBSERVED_CONTENT": x[:, :width]}
    return {"URI_ONLY": uri}


def assessment(predict, tune, width):
    scores, cutoffs = {}, []
    for source, frame in tune.items():
        scores[source] = {}
        for profile, x in views(frame["x"], width).items():
            values = np.asarray(predict(x), np.float32).reshape(-1)
            check(len(values) == len(x) and np.isfinite(values).all(), "Scorer coverage/integrity")
            truth, values_by_group = grouped_scores(x, frame["y"], values)
            cutoffs.extend(
                (threshold(truth, values_by_group), threshold(truth, values_by_group, True))
            )
            scores[source][profile] = (values, truth, values_by_group)
    cut = max(cutoffs)
    result = {"cutoff": cut, "sources": {}}
    for source, profiles in scores.items():
        result["sources"][source] = {}
        for profile, (values, truth, grouped) in profiles.items():
            result["sources"][source][profile] = metrics_both(truth, grouped, cut)
    # Give the Local URI-only profile equal importance for all architectures.
    values = [
        profiles["URI_ONLY"]["original_request"]["recall"]
        for profiles in result["sources"].values()
    ]
    vector = [
        profiles["URI_ONLY"]["vector_balanced"]["recall"] for profiles in result["sources"].values()
    ]
    ap = [profiles["URI_ONLY"]["original_request"]["ap"] for profiles in result["sources"].values()]
    result["selection_rank"] = [float(np.mean(values)), float(np.mean(vector)), float(np.mean(ap))]
    return result
