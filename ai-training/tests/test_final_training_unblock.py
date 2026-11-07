"""Boundaries for finite calibration and a single pilot."""

import importlib.util
import json
from pathlib import Path

import pytest


def script(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / name
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_state_oracle_requires_selected_option_not_status_or_echo():
    m = script("final-calibration-capture.py")
    assert (
        m.selected(
            b'<option value="low">low</option><option value="medium" selected="selected">medium</option>'
        )
        == "medium"
    )
    assert m.selected(b"<p>Security medium requested</p>") is None
    assert m.token(b'<input name="user_token" value="fixture-token" />') == "fixture-token"
    assert m.token(b"<p>Token missing</p>") is None


def test_strict_threshold_equality_does_not_flag():
    m = script("final-request-pilot.py")
    assert m.counts([0.5, 0.6, 0.4], [0, 2, 2], 0.5) == {"TP": 1, "FN": 1, "FP": 0, "TN": 1}


def test_dataset_tampering_rejected_before_training(tmp_path):
    m = script("final-request-pilot.py")
    r = {"dataset_fingerprint": "tampered", "files_sha256": {}}
    (tmp_path / "dataset-release.json").write_text(json.dumps(r))
    with pytest.raises(AssertionError):
        m.materials(tmp_path)
