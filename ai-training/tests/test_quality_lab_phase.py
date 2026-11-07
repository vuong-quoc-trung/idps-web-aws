"""Evidence and ownership boundaries for the finite research cohort."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "scripts" / name)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_plan_is_finite_unique_and_has_both_intents_per_app():
    m = load("quality-lab-cohort.py")
    cases = m.cases()
    assert len(cases) == 75 and len({c["request_id"] for c in cases}) == 75
    for env in ["dvwa", "juice"]:
        assert {c["intent"] for c in cases if c["environment"] == env} == {
            "BENIGN",
            "ATTACK_ATTEMPT",
        }
        assert any(
            c["method"] == "POST" and c["intent"] == "BENIGN"
            for c in cases
            if c["environment"] == env
        )
    assert all(
        c["role"] == "DEVELOPMENT"
        for c in cases
        if c["family"] in ["cmd_injection", "path_traversal"]
    )


def test_watchdog_sensor_loss_only_stops_owned_targets(tmp_path, monkeypatch):
    m = load("quality-lab-cohort.py")
    (tmp_path / "heartbeat").touch()
    stopped = []

    def broken():
        raise RuntimeError("sensor unavailable")

    monkeypatch.setattr(m, "module", lambda _: SimpleNamespace(cpu_sensors=broken))
    monkeypatch.setattr(m, "stop_owned", lambda: stopped.append(True))
    m.watchdog(tmp_path)
    assert stopped == [True]
    assert (
        json.loads((tmp_path / "lab-watchdog-result.json").read_text())["reason"]
        == "SENSOR_OR_SUPERVISOR_FAILURE"
    )


@pytest.mark.parametrize("exists_code,raises", [(1, False), (0, True), (125, True)])
def test_cleanup_nonzero_is_not_success_without_verified_absence(
    tmp_path, monkeypatch, exists_code, raises
):
    m = load("quality-lab-cohort.py")
    calls = []

    def execute(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=125 if cmd[1] == "rm" else exists_code, stderr="runtime diagnostic"
        )

    monkeypatch.setattr(m.subprocess, "run", execute)
    if raises:
        with pytest.raises(RuntimeError):
            m.remove_finished_container("owned-test", tmp_path / "diagnostic.json")
    else:
        m.remove_finished_container("owned-test", tmp_path / "diagnostic.json")
    assert len(calls) == 2 and (tmp_path / "diagnostic.json").exists()


def test_valid_json_does_not_prove_exploit_execution(tmp_path):
    m = load("assess-quality-cohort.py")
    # Source/runtime result must remain multi-dimensional; an unsafe reflection
    # is not accepted by any search/auth success oracle.
    (tmp_path / "juice-catalog.json").write_text("[]")
    case = {
        "oracle": "catalog_search",
        "expected": "unmatched",
        "intent": "ATTACK_ATTEMPT",
        "role": "DEVELOPMENT",
    }
    result = m.recover_juice(tmp_path, case, b'{"status":"success","data":[]}', 200)
    assert result["outcome"] == "UNKNOWN" and not result["independent_human_verified"]


def test_receipt_body_tampering_cannot_create_a_label(tmp_path):
    m = load("assess-quality-cohort.py")
    from idps_ai.common import digest

    rid = "a" * 32
    case = {
        "environment": "dvwa",
        "request_id": rid,
        "method": "POST",
        "path": "/lab",
        "body": "expected",
    }
    from idps_ai.common import file_sha256

    scripts = Path(__file__).parents[1] / "scripts"
    plan = {
        "cases": [case],
        "helper_sha256": {
            n: file_sha256(scripts / (n + ".py"))
            for n in ["p0-dvwa-capture", "juice-gt-factory", "p0-thermal-run"]
        },
    }
    plan["plan_sha256"] = digest(plan)
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    base = tmp_path / "dvwa/receipts" / rid
    base.mkdir(parents=True)
    (base / "receipt.json").write_text(
        json.dumps(
            {"request_id": rid, "method": "POST", "path": "/lab", "request_body_sha256": "forged"}
        )
    )
    (base / "request-headers.json").write_text("{}")
    (base / "response-headers.json").write_text("[]")
    (base / "request-body.bin").write_bytes(b"tampered")
    (base / "response-body.bin").write_bytes(b"HTTP200 is not an Oracle")
    with pytest.raises(AssertionError):
        m.recover(tmp_path)


def test_search_success_requires_catalog_identities_not_just_count(tmp_path):
    m = load("assess-quality-cohort.py")
    catalog = [{"id": i} for i in range(12)]
    (tmp_path / "juice-catalog.json").write_text(json.dumps(catalog))
    control_id = "control"
    base = tmp_path / "juice/receipts" / control_id
    base.mkdir(parents=True)
    (base / "response-body.bin").write_text('{"data":[]}')
    (tmp_path / "plan.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "oracle": "catalog_search",
                        "expected": "zzn7missingitem",
                        "request_id": control_id,
                    }
                ]
            }
        )
    )
    case = {
        "oracle": "search_injection",
        "intent": "ATTACK_ATTEMPT",
        "role": "PROSPECTIVE_EVALUATION",
    }
    unrelated = json.dumps({"data": [{"id": i + 100} for i in range(12)]}).encode()
    assert m.recover_juice(tmp_path, case, unrelated, 200)["outcome"] == "UNKNOWN"
    # The exploit may also expose soft-deleted products absent from the public catalog.
    matching = json.dumps({"data": catalog + [{"id": 100}]}).encode()
    assert m.recover_juice(tmp_path, case, matching, 200)["outcome"] == (
        "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
    )
