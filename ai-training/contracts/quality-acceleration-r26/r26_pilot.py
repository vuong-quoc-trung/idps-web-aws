"""Two feature pilots plus a new-source URI100 data-recovery control."""

# isort: skip_file

import argparse
import os
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from r26_common import R25, R25_ONNX_SHA, atomic_json, check, file_sha256, status
from r26_features import FULL_WIDTH, URI_WIDTH, schema
from r26_learning import assessment, epoch, make_training, schedule_for, source_data, warm
from idps_ai.export.onnx import cpu_session
from r16_train import batched_predict
from r21_quality import R20, R20_ONNX


def run(out):
    started = time.monotonic()
    train, tune = source_data(out, pilot=True)
    plan = {
        "schema": schema(),
        "epochs": 4,
        "widths": [100, URI_WIDTH, FULL_WIDTH],
        "warm_start": "R25 best step81; new input rows zero; reset Adam",
        "optimizer": "AdamW, 0.0003 warmup-cosine, seed2601, inherited regularization",
        "source_class_mass": "Equal per source/class. Pilot preserves old URI76 parent mass; body-missing auxiliary views do not add originals.",
        "selection": "TUNING only: macro source URI-only request recall at one global dual <=1% threshold, vector recall, AP; report all content profiles separately",
        "heldout_or_calibration_roles_read": False,
        "pilot_code_sha256": file_sha256(__file__),
        "feature_code_sha256": file_sha256(Path(__file__).with_name("r26_features.py")),
        "waf_manifest_sha256": file_sha256(out / "data-v2/waf-manifest.json"),
        "new_source_manifest_sha256": file_sha256(out / "notes/manifest.json"),
    }
    atomic_json(out / "pilot-plan.json", plan)
    arms, records = {}, {}
    for name, path, width, expected in (
        ("R20", R20 / "bundle/swiglu.onnx", 76, R20_ONNX),
        ("R25", R25 / "swiglu-uri100-r25.onnx", 100, R25_ONNX_SHA),
    ):
        check(file_sha256(path) == expected, "Frozen baseline digest")
        session = cpu_session(path, 1)
        arms[name] = assessment(lambda x: session.run(["score"], {"input": x})[0], tune, width)
    for width in plan["widths"]:
        x, y, weight, meta = make_training(train, width)
        status(out, "RUNNING", "PILOT", width=width, training_cells=len(y))
        logistic = LogisticRegression(C=1, max_iter=600, random_state=2601).fit(
            x, y, sample_weight=weight
        )
        check(logistic.n_iter_.max() < 600, "Pilot logistic convergence")
        arms[f"logistic_{width}"] = assessment(
            lambda a: logistic.predict_proba(a)[:, 1], tune, width
        )
        model = warm(width)
        schedule = schedule_for(len(y), plan["epochs"])
        losses = []
        for number in range(plan["epochs"]):
            _, loss = epoch(model, x, y, weight, number, schedule)
            losses.append(loss)
        name = f"swiglu_{width}"
        arms[name] = assessment(lambda a: batched_predict(model, a), tune, width)
        records[name] = {
            "source_counts": meta,
            "loss": losses,
            "global_step": model.steps,
            "parameters": sum(v.size for v in model.parameters.values()),
        }
        model_path = out / f"pilot-{width}.npz"
        np.savez_compressed(model_path, **model.arrays())
    # Shortcuts are diagnostic controls only, never release candidates.
    x, y, weight, _ = make_training(train, FULL_WIDTH)
    controls = {"method_only": np.arange(100), "availability_only": np.array([228, 229, 242, 243])}
    # The method control extracts precisely the one-hot method columns in URI76.
    from idps_ai.features.request_time import schema as uri_schema

    controls["method_only"] = np.array(
        [i for i, n in enumerate(uri_schema()["columns"]) if n.startswith("method_")]
    )
    for name, columns in controls.items():
        control = LogisticRegression(C=1, max_iter=400).fit(x[:, columns], y, sample_weight=weight)
        arms[name] = assessment(
            lambda a: control.predict_proba(a[:, columns])[:, 1], tune, FULL_WIDTH
        )
    candidates = [name for name in arms if name.startswith("swiglu_")]
    selected = max(candidates, key=lambda name: arms[name]["selection_rank"])
    gain = arms[selected]["selection_rank"][0] - arms["R25"]["selection_rank"][0]
    atomic_json(
        out / "pilot.json",
        {
            "arms": arms,
            "training": records,
            "selected": selected,
            "macro_recall_gain_vs_r25": gain,
            "full_training_allowed": gain >= 0.05,
            "seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
