"""Three-source round calibration, then a source2 grouped research holdout.

The first Notes RESEARCH_TEST is never reopened for model B. Source2 is an
already-exposed publisher FIT source, so these results are not a pristine native
or independent final acceptance, even though B's roles are component-disjoint.
"""

# isort: skip_file

import argparse
import os
import struct
from pathlib import Path

import numpy as np
import onnx

from r26_common import R25, R25_ONNX_SHA, atomic_json, check, file_sha256, read
from r26_calibration import append_sigmoid
from r26_evaluate import profile_metrics
from r26_train import export
from idps_ai.export.onnx import cpu_session
from r20_calibration import fit, threshold
from r21_quality import R20, R20_ONNX
from r23_pilot import grouped_scores


def load_role(parent, folder, role):
    manifest = read(parent / folder / "manifest.json")
    path = parent / folder / f"{role.lower()}.npz"
    check(
        file_sha256(path) == manifest["roles"][role]["sha256"],
        "Recovery calibration/holdout binding",
    )
    with np.load(path, allow_pickle=False) as z:
        return {name: z[name] for name in z.files}


def run(parent):
    out = parent / "augmentation-b"
    check(not (out / "evaluation.json").exists(), "Recovery evaluation already committed")
    selected = read(out / "model-selection.json")
    a = read(parent / "model-selection.json")
    models = {
        "R20": (R20 / "bundle/swiglu.onnx", R20_ONNX, 76),
        "R25": (R25 / "swiglu-uri100-r25.onnx", R25_ONNX_SHA, 100),
        "R26A": (parent / "bundle/swiglu.onnx", a["sha256"]["swiglu"], 100),
        "R26B_SWIGLU": (out / "bundle/swiglu.onnx", selected["sha256"]["swiglu"], 100),
        "R26B_LOGISTIC": (out / "bundle/logistic.onnx", selected["sha256"]["logistic"], 100),
    }
    cal_fit = {
        name: load_role(parent, folder, "CAL_FIT")
        for name, folder in (("NOTES", "notes"), ("SRBH", "source2-recovery"))
    }
    cal_op = {
        name: load_role(parent, folder, "CAL_OP")
        for name, folder in (("NOTES", "notes"), ("SRBH", "source2-recovery"))
    }
    lock = {
        "selection_sha256": file_sha256(out / "model-selection.json"),
        "candidate": f"R26B_{selected['selected'].upper()}",
        "calibration_protocol": "Positive-slope Platt, equal source mass preserving within-source prevalence on CAL_FIT; single global strict > float32 cut, per-source request/vector FPR<=0.5% on CAL_OP",
        "old_NOTES_RESEARCH_TEST_opened": False,
        "source2_holdout_scope": "Previously exposed allowed FIT source; grouped unseen-to-model-B, not pristine independent native TEST",
        "code_sha256": file_sha256(__file__),
        "models": {},
    }
    cal_metrics = {}
    for name, (path, expected, width) in models.items():
        check(file_sha256(path) == expected, "Recovery raw model digest")
        raw = cpu_session(path, 1)
        matrix = np.concatenate([f["x"][:, :width] for f in cal_fit.values()])
        labels = np.concatenate([f["y"] for f in cal_fit.values()])
        weights = np.concatenate(
            [np.full(len(f["y"]), 1 / (2 * len(f["y"]))) for f in cal_fit.values()]
        )
        scores = raw.run(["score"], {"input": matrix})[0]
        unique, inverse = np.unique(matrix, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        counts = np.zeros((len(unique), 2), np.float64)
        np.add.at(counts, (inverse, labels), weights)
        first = np.unique(inverse, return_index=True)[1]
        np.testing.assert_allclose(scores[first][inverse], scores, atol=1e-6)
        calibration = fit("platt", scores[first], counts)
        path_cal = out / "bundle" / f"{name.lower()}-calibrated.onnx"
        export(path_cal, append_sigmoid(calibration, onnx.load(path)))
        deployed = cpu_session(path_cal, 1)
        predictions = {
            source: deployed.run(["score"], {"input": frame["x"][:, :width]})[0]
            for source, frame in cal_op.items()
        }
        cutoffs = []
        for source, frame in cal_op.items():
            truth, values = grouped_scores(frame["x"][:, :width], frame["y"], predictions[source])
            cutoffs.extend(
                (
                    threshold(truth, values, target=0.005),
                    threshold(truth, values, True, target=0.005),
                )
            )
        cut = max(cutoffs)
        lock["models"][name] = {
            "raw_sha256": expected,
            "width": width,
            "calibration": calibration,
            "calibrated_file": path_cal.name,
            "calibrated_sha256": file_sha256(path_cal),
            "cutoff": cut,
            "cutoff_float32_le_hex": struct.pack("<f", cut).hex(),
        }
        cal_metrics[name] = {
            source: profile_metrics(frame, predictions[source], width, cut)
            for source, frame in cal_op.items()
        }
    atomic_json(out / "evaluation-lock.json", lock)
    # All parameter and threshold choices are sealed before loading this file.
    frame = load_role(parent, "source2-recovery", "RESEARCH_TEST")
    report, archive = {}, {}
    for name, spec in lock["models"].items():
        scores = cpu_session(out / "bundle" / spec["calibrated_file"], 1).run(
            ["score"], {"input": frame["x"][:, : spec["width"]]}
        )[0]
        archive[name] = scores
        report[name] = profile_metrics(frame, scores, spec["width"], spec["cutoff"])
    np.savez_compressed(out / "research-test-scores.npz", **archive)
    candidate = report[lock["candidate"]]["original_request"]
    atomic_json(
        out / "evaluation.json",
        {
            "selected_before_holdout": lock["candidate"],
            "evaluation_lock_sha256": file_sha256(out / "evaluation-lock.json"),
            "CAL_OP": cal_metrics,
            "SRBH_GROUPED_RESEARCH_HOLDOUT": report,
            "target_point_estimate_met": candidate["recall"] >= 0.9 and candidate["fpr"] <= 0.01,
            "fresh_native_acceptance": "BLOCKED_NO_NATIVE_REVIEWED_CAL_TEST",
            "independent_final_acceptance": False,
            "old_NOTES_RESEARCH_TEST_not_reopened": True,
            "source2_historical_global_role": "EXISTING_R13_FIT_RESEARCH_DEVELOPMENT_ONLY",
            "no_historical_CAL_DEV_TEST_payloads": True,
            "release_ready": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
