"""Numerical checks for the new ranking objective and hard-negative selection."""

import numpy as np
from rank_pilot import SAMPLE, objective, weighted_tail
from scipy.optimize import check_grad


def test_pairwise_gradient_with_repeated_negative_representatives():
    features = np.array([[1.0, -1.0], [0.0, 2.0], [0.5, -2.0], [1.5, 0.5]])
    base = np.array([-1.0, 0.5, 0.0, 1.0])
    mass = np.array([0.15, 0.2, 0.25, 0.4])
    pairs = [
        (np.array([0, 1]), np.array([0.25, 0.75]), np.array([2, 2, 3])),
        (np.array([1]), np.array([1.0]), np.array([3, 2, 3])),
    ]
    args = (features, base, mass, pairs)
    assert (
        check_grad(
            lambda theta: objective(theta, *args)[0],
            lambda theta: objective(theta, *args)[1],
            np.array([0.1, -0.3]),
        )
        < 1e-6
    )


def test_weighted_tail_keeps_repeated_mass_instead_of_skipping_top_negative():
    scores = np.array([0.1, 0.9, 0.8, -0.1])
    weights = np.array([0.50, 0.1, 0.05, 0.35])
    result = weighted_tail(np.array([0, 1, 2, 3]), scores, weights)
    np.testing.assert_array_equal(result, np.full(SAMPLE, 1))
