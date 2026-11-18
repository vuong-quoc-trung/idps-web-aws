# isort: skip_file

"""B16 evaluation before continuation; no TEST and no model-selection feedback."""

import os

from common import PARENT, atomic_json, output_arg, read
from calibration import calibrate


def run(out):
    audit = read(out / "checkpoint-audit.json")
    specs, metrics = calibrate(
        [
            ("B16", out / "bundle/b16.onnx", audit["onnx_sha256"], 100),
            (
                "R26A",
                PARENT / "bundle/swiglu.onnx",
                read(PARENT / "model-selection.json")["sha256"]["swiglu"],
                100,
            ),
        ],
        out / "precalibration",
    )
    atomic_json(
        out / "precalibration.json",
        {
            "models": specs,
            "CAL_OP": metrics,
            "TEST_read": False,
            "continuation_decision_already_locked_from_TUNING": True,
            "candidate_parameters_or_thresholds_not_selected_from_this_report": True,
            "calibration_scope": "Fixed research publisher calibration; not native final acceptance",
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())
