"""A new derivative must not repurpose old heldout or duplicate source windows."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from idps_ai.data.local_release import (
    requalified_reasons,
    role_for_component,
    verify_windows,
)


def test_source_windows_disjoint_and_bounded():
    assert verify_windows() == ((49964, 99964), (1098539, 1148539))
    with pytest.raises(AssertionError):
        verify_windows(((0, 100000),))
    with pytest.raises(AssertionError):
        verify_windows(((100000, 150000), (100000, 150000)))


def test_requalification_preserves_other_reasons_and_heldout():
    old = ["PROTECTED_EXISTING_TEMPLATE_VIEW_OR_ROUTE", "EXACT_CONFLICT"]
    clean = dict(candidate=True, exact_protected=False, legacy_near=False, new_heldout=False)
    assert requalified_reasons(old, **clean) == ["EXACT_CONFLICT"]
    for flag in ["candidate", "exact_protected", "legacy_near", "new_heldout"]:
        values = {**clean, flag: not clean[flag]}
        assert "PROTECTED_EXISTING_TEMPLATE_VIEW_OR_ROUTE" in requalified_reasons(old, **values)


def test_recovered_components_cannot_become_evaluation():
    assert {role_for_component(i, True) for i in range(1000)} == {"TRAIN"}
    assert {role_for_component(i, False) for i in range(1000)} == {
        "TRAIN",
        "CALIBRATION",
        "EVALUATION",
    }


def test_legacy_heldout_checks_use_each_original_encoder_and_fail_closed(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "local_release_driver", Path(__file__).parents[1] / "scripts/local-release-200k.py"
    )
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    request = {"method": "GET", "url": "/course?q=ordinary", "headers": None, "body": None}
    vectorizer = driver.HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=512,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    encoded = [
        vectorizer.transform([encoder(**request)[0]]).toarray().astype(np.float32)
        for encoder in [driver.symbolic_request, driver.rich_request]
    ]
    np.savez(tmp_path / "legacy-heldout.npz", safe=encoded[0], rich=encoded[1])
    check = driver.LegacyCheck(tmp_path)
    assert check.check([request]).tolist() == [True]
    assert check.check([{**request, "url": None}]).tolist() == [True]
