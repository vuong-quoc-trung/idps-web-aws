import numpy as np
from r23_features import LANES, numeric, project, sketch
from r23_pilot import equivalent, select_fit, tally_targets


def test_private_fields_never_enter_shape_vector():
    first = project("/catalog?category=books&password=Secret12345&email=test%40example.org")
    changed = project(
        "/catalog?category=books&password=AnotherLength987&email=someone%40example.org"
    )
    for a, b in zip(first, changed, strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(
        project("/catalog/credentials/placeholder")[-1],
        project("/catalog/credentials/othernumber001")[-1],
    )
    safe = b"".join(sketch("/catalog?category=books&password=Secret12345"))
    assert b"catalog" not in safe and b"Secret" not in safe and b"books" not in safe


def test_numeric_extension_is_deterministic_and_bounded():
    small = numeric(*sketch("/catalog/NEW-12.json?sort=a&sort=2"))
    repeat = numeric(*sketch("/catalog/NEW-12.json?sort=a&sort=2"))
    for arm, a, b in zip(LANES, small, repeat, strict=True):
        assert a.shape == (LANES[arm],) and a.dtype == np.uint8
        np.testing.assert_array_equal(a, b)
    assert small[0].max() <= 31 and small[1].max() <= 15


def test_sample_keeps_label_cells_and_is_repeatable():
    index = np.repeat([1, 2, 3], 22)
    labels = np.tile(np.repeat([0, 1], 11), 3)
    a = select_fit(index, labels)
    np.testing.assert_array_equal(a, select_fit(index, labels))
    assert a.sum() == 48
    assert np.bincount(labels[a]).tolist() == [24, 24]


def test_collision_diagnostic_distinguishes_same_target_label_ambiguity():
    counts = np.array([[1, 2], [1, 0]])
    pairs = {(0, b"a"): 3, (0, b"b"): 2, (1, b"c"): 1}
    stats = tally_targets(counts, pairs)
    assert stats["uri76_groups_merging_distinct_targets"] == 1
    assert stats["method_target_mixed_label"] == 1
    assert stats["largest_uri76_group_original_count"] == 3
    result, _, _, _ = equivalent(
        np.array([True, True, False]),
        np.array([0, 1, 1]),
        np.array([[0], [1], [1]]),
        np.array([False, True, True]),
    )
    assert (
        result["mixed"] == 0 and result["within_old_mixed_group_anchor_fn_now_anomalous_only"] == 1
    )
