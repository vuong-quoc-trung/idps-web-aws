import numpy as np
import pytest

from experiment import threshold


def test_component_cap_protects_against_duplicate_dilution():
    easy = np.zeros(1000)
    rare = np.linspace(0.1, 0.9, 100, dtype=np.float32)
    scores = np.r_[easy, rare]
    component = np.r_[np.zeros(1000, dtype=int), np.arange(1, 101)]
    t = threshold(scores, component)
    assert t == rare[-2]
    assert threshold(np.r_[scores, easy], np.r_[component, component[:1000]]) == t
    assert np.sum(scores > t) == 1


def test_strict_threshold_does_not_split_ties():
    assert threshold(np.ones(100), np.arange(100)) == 1
    with pytest.raises(ValueError):
        threshold(np.array([np.nan]), np.array([1]))
