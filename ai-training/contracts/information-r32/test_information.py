import numpy as np
import pytest
from dataset import ROOT  # noqa: F401 - initialize frozen research paths
from experiment import sparse_head
from external import measure, uri
from neighbors import local_evidence
from scipy import sparse
from symbols import BODY_START, STRIDE, WIDTH, project


def test_adjacent_pairs_are_field_scoped_and_ordered():
    assert project("/api/select/from", None) != project("/api/select.from", None)
    assert project("/query?q=select.from", None) != project("/query?q=from.select", None)
    assert all(i < STRIDE for i in project("/select", None))
    assert all(i >= BODY_START for i in project("/", "select.from"))
    assert max(project("/", "select.from")) < WIDTH


@pytest.mark.parametrize(
    "key", ["pwd", "%70assphrase", "ticket", "api_key", "csrf", "email", "pin"]
)
def test_private_content_does_not_contribute_even_allowlisted_values(key):
    assert project("/health?" + key + "=select.from", None) == project("/health", None)
    assert project("/health", key + "=select.from") == project("/health", None)


def test_unknown_literals_have_identical_numeric_symbols():
    assert project("/giraffe?fruit=kiwi", None) == project("/kestrel?fruit=mango", None)


def test_weighted_loss_matches_summed_repeated_originals():
    a = sparse.csr_matrix([[1.0, 0], [0, 1], [1.0, 0]])
    b, _ = sparse_head(a, np.array([0, 1, 1]), np.array([0.25, 0.5, 0.25]), np.zeros(3))
    c, _ = sparse_head(a[[0, 1, 1, 2]], np.array([0, 1, 1, 1]), np.full(4, 0.25), np.zeros(4))
    np.testing.assert_allclose(b, c, atol=1e-8)


def test_neighbors_require_distinct_templates_in_radius():
    near = np.array([[0, 1, 2, 3]])
    dist = np.array([[0.1, 0.11, 0.2, 0.3]])
    args = near, dist, np.array([1, 1, 2, 3]), np.array([1.0, 0.0, 1.0, 1.0])
    v, s, _ = local_evidence(*args, 0.3)
    assert v[0] == s[0] == 1
    assert local_evidence(*args, 0.29)[1][0] == 0
    assert local_evidence(*args, 0.3, excluded=[2])[1][0] == 0


def test_abstention_preserves_denominator_and_threshold_is_strict():
    m = measure(np.array([1, 1, 1, 0]), np.array([0.7, 0.5, np.nan, 0.5]), 0.5)
    assert m["effective_recall"] == 1 / 3 and m["coverage"] == 0.75 and m["false_alert_rate"] == 0


def test_runtime_abi_rejects_decoded_non_ascii():
    with pytest.raises(ValueError):
        uri("/docs/%C3%A9", "GET")


def test_optimistic_ceiling_keeps_abstentions_and_fractional_group():
    from verification import ceiling

    # One supported mixed group, one positive group and ten rejected positives.
    result = ceiling({"a": [50, 40], "b": [0, 50], "c": [50, 0]}, [100, 100])
    assert result["benign_budget_integer"] == 1
    assert result["zero_FPR_recall"] == 0.5
    assert result["optimistic_max_recall_at_1pct"] == pytest.approx(0.508)
    assert result["optimistic_min_FPR_for_90pct"] == 0.5
    assert ceiling({"a": [100, 20]}, [100, 100])["optimistic_min_FPR_for_90pct"] is None
