# isort: skip_file

"""Fixed research calibration, shared by the initial B16 and final comparison."""

import struct

import numpy as np
import onnx

from common import PARENT, check, file_sha256, read
from idps_ai.export.onnx import cpu_session
from r20_calibration import fit, threshold
from r23_pilot import grouped_scores
from r26_calibration import append_sigmoid
from r26_evaluate import profile_metrics
from r26_train import export


def role(folder, name):
    manifest = read(PARENT / folder / "manifest.json")
    path = PARENT / folder / f"{name.lower()}.npz"
    check(
        file_sha256(path) == manifest["roles"][name]["sha256"], "Research calibration role binding"
    )
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def calibrate(models, destination):
    destination.mkdir(exist_ok=True, parents=True)
    fit_frames = {
        name: role(folder, "CAL_FIT")
        for name, folder in (("NOTES", "notes"), ("SRBH", "source2-recovery"))
    }
    op_frames = {
        name: role(folder, "CAL_OP")
        for name, folder in (("NOTES", "notes"), ("SRBH", "source2-recovery"))
    }
    specs, reports = {}, {}
    for name, path, expected, width in models:
        check(file_sha256(path) == expected, "Raw model digest changed")
        session = cpu_session(path, 1)
        x = np.concatenate([frame["x"][:, :width] for frame in fit_frames.values()])
        y = np.concatenate([frame["y"] for frame in fit_frames.values()])
        weight = np.concatenate(
            [np.full(len(frame["y"]), 1 / (2 * len(frame["y"]))) for frame in fit_frames.values()]
        )
        unique, inverse = np.unique(x, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        counts = np.zeros((len(unique), 2), np.float64)
        np.add.at(counts, (inverse, y), weight)
        raw = session.run(["score"], {"input": unique})[0]
        mapping = fit("platt", raw, counts)
        target = destination / f"{name.lower()}-calibrated.onnx"
        export(target, append_sigmoid(mapping, onnx.load(path)))
        deployed = cpu_session(target, 1)
        outputs = {
            source: deployed.run(["score"], {"input": frame["x"][:, :width]})[0]
            for source, frame in op_frames.items()
        }
        cuts = []
        for source, frame in op_frames.items():
            truth, values = grouped_scores(frame["x"][:, :width], frame["y"], outputs[source])
            cuts.extend(
                [
                    threshold(truth, values, target=0.005),
                    threshold(truth, values, True, target=0.005),
                ]
            )
        cut = max(cuts)
        specs[name] = {
            "raw_sha256": expected,
            "calibrated_file": target.name,
            "calibrated_sha256": file_sha256(target),
            "calibration": mapping,
            "width": width,
            "cutoff": cut,
            "cutoff_float32_le_hex": struct.pack("<f", cut).hex(),
        }
        reports[name] = {
            source: profile_metrics(frame, outputs[source], width, cut)
            for source, frame in op_frames.items()
        }
    return specs, reports
