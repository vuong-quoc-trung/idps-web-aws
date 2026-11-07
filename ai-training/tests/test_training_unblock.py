"""Pre-capture boundaries for the single finite training-unblock campaign."""

import importlib.util
from pathlib import Path


def collector():
    p = Path(__file__).parents[1] / "scripts/training-unblock-cohort.py"
    spec = importlib.util.spec_from_file_location("unblock", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_roles_fixed_and_all_families_have_prospective_coverage():
    m = collector()
    cases = m.cases()
    assert len(cases) == 43 and len({c["request_id"] for c in cases}) == len(cases)
    assert {
        c["family"]
        for c in cases
        if c["role"] == "PROSPECTIVE_EVALUATION" and c["intent"] == "ATTACK_ATTEMPT"
    } == {"xss", "sqli", "cmd_injection", "path_traversal"}
    sessions = {}
    for c in cases:
        sessions.setdefault(c["session_plan"], set()).add(c["role"])
    assert all(len(roles) == 1 for roles in sessions.values())
    assert any(
        c["environment"] == "juice"
        and c["method"] == "POST"
        and c["intent"] == "BENIGN"
        and c["role"] == "CALIBRATION"
        for c in cases
    )


def test_captcha_is_arithmetic_not_response_code_execution():
    m = collector()
    assert m.arithmetic_answer("2+3*4") == "14"
    for text in ['__import__("os").getcwd()', "(2).__class__", "2**1000000", "2/0", "x+2", None]:
        assert m.arithmetic_answer(text) is None


def test_lab_ownership_does_not_touch_previous_run():
    m = collector()
    base = m.configure_helpers()
    assert base.RUN == "training-unblock-20261107-v1"
    assert base.LABEL == "idps.research-run=training-unblock-20261107-v1"
    assert base.RUN != "quality-lab-20261107-v1"


def test_channel_privacy_and_header_normalization():
    import numpy as np

    from idps_ai.features.research_request_channels import encode

    req = dict(
        method="POST",
        url="/api/search?q=one",
        body='{"password":"short","comment":"<script>alert(1)</script>"}',
        headers="Cookie: secret-one\r\nAuthorization: Bearer one\r\nAccept: application/json",
    )
    x = encode(req)
    req2 = dict(
        req,
        body=req["body"].replace("short", "a-different-very-long-credential"),
        headers="Cookie: different\r\nAuthorization: Bearer two\r\nAccept: application/json",
    )
    assert np.array_equal(x, encode(req2))
    long_headers = dict(req, headers=req["headers"] + "\r\nUser-Agent: " + "Browser " * 200)
    y = encode(long_headers)
    assert np.array_equal(x[:524], y[:524])
    assert not np.array_equal(x[524:], y[524:])
    assert not np.array_equal(encode(dict(req, body=None)), encode(dict(req, body="")))


def test_unknown_form_oracle_cannot_satisfy_calibration_gate():
    p = Path(__file__).parents[1] / "scripts/audit-training-unblock.py"
    spec = importlib.util.spec_from_file_location("audit_unblock", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    row = dict(
        role="CALIBRATION",
        exclusions=[],
        intent="UNKNOWN",
        workflow="form",
        method="POST",
        environment="dvwa",
        keys={"view": "v", "template": "t"},
        candidate_view="c",
        family="benign",
    )
    result = m.coverage(
        [row], {"coverage_gates": {"CALIBRATION": {"benign_POST_groups": 1, "form_and_JSON": True}}}
    )
    assert result["CALIBRATION"]["status"] == "FAIL"
    assert result["CALIBRATION"]["actual"]["eligible_cases"] == 0


def test_cross_process_recovery_preserves_exact_next_update(tmp_path):
    import json
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "synthetic-recovery"
    subprocess.run(
        [
            sys.executable,
            str(root / "ai-training/scripts/verify-request-channel-recovery.py"),
            "--output",
            str(output),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        env=dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1"),
    )
    proof = json.loads((output / "proof.json").read_text())
    assert proof["status"] == "PASS" and proof["parameter_Adam_m_v_loss_bitwise_equal"]
    assert proof["actual_cohort_fit_updates"] == 0
