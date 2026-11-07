"""Matched representation and active-time thermal safety invariants."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from idps_ai.features.normalization_ablation import from_symbols, reference
from idps_ai.features.rich_content_v2 import rich_request_v2


def test_shared_is_bitwise_original_char_hashing():
    texts = [
        rich_request_v2(
            "POST", "/api/search?q=" + q, "Accept: application/json\r\nUser-Agent: " + h, body
        )[0]
        for q, h, body in [
            ("one", "browser", ""),
            ("one%27OR+1=1", "browser " * 100, "ip=127.0.0.1;printf+x"),
            ("plain", "agent", '{"password":"secret","email":"\' or 1=1--"}'),
        ]
    ]
    shared, separate = from_symbols(texts)
    assert np.array_equal(shared, reference(texts))
    assert np.isfinite(separate).all() and np.allclose(np.linalg.norm(separate, axis=1), 1)
    assert not np.array_equal(shared, separate)


def test_pause_cannot_dilute_active_temperature_window():
    folder = Path(__file__).parents[1] / "scripts"

    def mod(name):
        spec = importlib.util.spec_from_file_location(name, folder / (name + ".py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    w = mod("scaled-active-supervisor").active_policy(mod("rolling-resource-policy"))()
    w.add(0, 79, False)
    w.add(1, 40, True)
    for t in range(2, 305):
        r = w.add(t, 40, True)
    assert r["rolling_300s_c"] == 79 and r["wall_rolling_300s_c"] == 40


@pytest.mark.parametrize(
    "name", ["prepare-scaled-normalization.py", "finalize-scaled-normalization.py"]
)
def test_projected_near_filter_covers_full_cosine_neighbors(tmp_path, name):
    p = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location("scaled_preparation", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    rng = np.random.default_rng(17)
    reference = rng.random((32, 512)).astype(np.float32)
    reference /= np.linalg.norm(reference, axis=1, keepdims=True)
    queries = np.stack([reference[3], reference[5] + 1e-5, np.eye(1, 512, dtype=np.float32)[0]])
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    mask, _ = m.near_mask(reference, queries, tmp_path / "progress.json")
    expected = (reference.astype(np.float64) @ queries.astype(np.float64).T >= 0.995 - 1e-7).any(
        axis=0
    )
    assert np.array_equal(mask, expected)


def test_matched_models_have_identical_initial_parameters_and_objective():
    p = Path(__file__).parents[1] / "scripts/scaled-normalization-experiment.py"
    spec = importlib.util.spec_from_file_location("scaled_experiment", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    a, b = m.model(), m.model()
    assert sum(v.size for v in a.parameters.values()) == 50696
    assert a.metadata() == b.metadata() and a.objective["family_weight"] == 0
    assert all(np.array_equal(v, b.arrays()[k]) for k, v in a.arrays().items())
