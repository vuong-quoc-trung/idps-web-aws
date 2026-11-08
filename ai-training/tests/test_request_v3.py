"""Research feature, privacy and leakage invariants; no dataset or training access."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3 as candidate
from idps_ai.training.models import Model

spec = importlib.util.spec_from_file_location(
    "materialize_v3", Path(__file__).parents[1] / "scripts/materialize-request-v3.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(i, role, intent="ATTACK_INTENT"):
    return dict(
        sample_id=str(i),
        request_id=f"{i:032x}",
        split=role,
        intent=intent,
        method="POST",
        endpoint_template="/surface",
        checksums={"raw": str(i), "template": str(i), "full_view": str(i)},
        session_group=f"session-{i}",
        campaign_group=f"campaign-{i}",
        inclusion_exclusion_reasons=[],
    )


def runtime():
    x = np.zeros(588, np.float32)
    x[76] = 1
    return x


def test_fixed_scale_shape_and_missingness():
    x = runtime()
    v = body.extract(
        b"message=%3Cimg+src%3Dx+onerror%3Dalert%281%29%3E", "application/x-www-form-urlencoded"
    )
    z = candidate.assemble(x, v)
    assert z.shape == (634,) and z.dtype == np.float32
    assert np.array_equal(z[:588], x)
    assert np.all(z >= 0) and np.all(z <= 1)
    assert np.array_equal(z[588:], np.array(v, np.float32) / np.array(body.MAXIMA, np.float32))
    assert not np.array_equal(
        candidate.assemble(x, body.extract(None, None)),
        candidate.assemble(x, body.extract(b"", None)),
    )
    assert candidate.contract()["fit_rows"] == 0


@pytest.mark.parametrize("kind", ["bool", "float", "range", "dimension", "nan", "state"])
def test_invalid_vectors_fail_closed(kind):
    x = runtime()
    b = body.extract(None, None)
    if kind == "bool":
        b[0] = True
    if kind == "float":
        b[0] = 1.0
    if kind == "range":
        b[15] = 7
    if kind == "dimension":
        x = x[:-1]
    if kind == "nan":
        x[0] = np.nan
    if kind == "state":
        b[1] = 1
    with pytest.raises(ValueError):
        candidate.assemble(x, b)


def test_secret_values_are_not_new_model_inputs():
    a = body.extract(
        b'{"email":"first@example.invalid","password":"alpha","token":"abc"}', "application/json"
    )
    b = body.extract(
        b'{"email":"other@example.invalid","password":"different","token":"xyz"}',
        "application/json",
    )
    assert a == b
    assert np.array_equal(candidate.assemble(runtime(), a), candidate.assemble(runtime(), b))


def test_warm_start_expands_actual_deep_model_first_layer_without_training():
    old = Model(588, 64, "deep_mlp", 17)
    new = Model(634, 64, "deep_mlp", 17)
    new.parameters = candidate.expanded_parameters(old.parameters)
    rng = np.random.default_rng(9)
    x = rng.random((3, 588), dtype=np.float32)
    joint = np.concatenate([x, rng.random((3, 46), dtype=np.float32)], axis=1)
    assert np.allclose(old.forward(x)[1], new.forward(joint)[1], rtol=0, atol=1e-7)
    assert np.count_nonzero(new.parameters["W0"][588:]) == 0
    assert sum(v.size for v in new.parameters.values()) == 53640
    assert old.steps == new.steps == 0
    assert not np.shares_memory(old.parameters["W0"], new.parameters["W0"])


def test_body_separation_does_not_lift_raw_or_prior_admission_exclusions():
    rows = [row(0, "TRAIN"), row(1, "DEVELOPMENT")]
    rows[0]["checksums"]["raw"] = rows[1]["checksums"]["raw"]
    rows[0]["inclusion_exclusion_reasons"] = [
        "PRIOR_TRAIN_ADMISSION_EXCLUDED",
        "CROSS_ROLE_RUNTIME_VIEW",
    ]
    x = np.stack([runtime(), runtime()])
    a = body.extract(b"message=hello", "application/x-www-form-urlencoded")
    b = body.extract(
        b"message=%3Cscript%3Ealert%281%29%3C%2Fscript%3E", "application/x-www-form-urlencoded"
    )
    z = np.stack([candidate.assemble(x[0], a), candidate.assemble(x[1], b)])
    reasons, _, near = audit.audit(rows, x, z)
    assert all("CROSS_ROLE_RAW" in r for r in reasons)
    assert "PRIOR_TRAIN_ADMISSION_EXCLUDED" in reasons[0]
    assert "CROSS_ROLE_RUNTIME_VIEW" not in reasons[0]
    assert not near


def test_excluded_bridge_still_connects_lineage_and_quarantines_both_roles():
    rows = [row(0, "TRAIN"), row(1, "DEVELOPMENT"), row(2, "TRAIN")]
    rows[1]["session_group"] = rows[0]["session_group"]
    rows[1]["campaign_group"] = rows[2]["campaign_group"]
    rows[1]["inclusion_exclusion_reasons"] = ["OUTCOME_ORACLE_UNVERIFIED"]
    x = np.stack([runtime()] * 3)
    z = np.stack([candidate.assemble(v, body.extract(None, None)) for v in x])
    reasons, _, _ = audit.audit(rows, x, z)
    assert all("CROSS_ROLE_LINEAGE_COMPONENT" in r for r in reasons)
    assert audit.components(rows, [0, 2]) == 1
    with pytest.raises((ValueError, AssertionError)):
        audit.validate_split(rows, [set(), {"excluded"}, set()], z, [])


def test_near_body_rule_detects_count_variants_but_not_flag_changes():
    rows = [row(0, "TRAIN"), row(1, "DEVELOPMENT")]
    x = np.stack([runtime(), runtime()])
    b = np.zeros((2, 46), np.float32)
    b[1, 21] = 1 / 3
    assert audit.near_pairs(rows, x, b, use_body=True) == [(0, 1)]
    b[1, 38] = 1
    assert audit.near_pairs(rows, x, b, use_body=True) == []


def test_surrogate_lineage_preserves_groups_without_emitting_cookie_digests():
    rows = [row(0, "TRAIN"), row(1, "TRAIN"), row(2, "DEVELOPMENT")]
    rows[0]["session_group"] = "f" * 64
    rows[1]["session_group"] = "f" * 64
    rows[2]["session_group"] = "e" * 64
    aliases = audit.surrogate_groups(rows)
    assert aliases[0]["session_group"] == aliases[1]["session_group"]
    assert aliases[0]["session_group"] != aliases[2]["session_group"]
    assert all(r["session_group"] not in str(aliases) for r in rows)
    assert aliases == audit.surrogate_groups(rows)
