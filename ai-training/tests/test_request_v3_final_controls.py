"""Finite campaign/Oracle invariants and separate synthetic missingness fixtures."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from idps_ai.features import body_syntax_v1 as body

spec = importlib.util.spec_from_file_location(
    "final_controls", Path(__file__).parents[1] / "scripts/request-v3-final-controls.py"
)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_fixed_campaign_budget_and_roles():
    rows = c.cases()
    assert len(rows) == 12
    assert len({r["case_id"] for r in rows}) == 12
    assert {r["role"] for r in rows} == {"TRAIN", "DEVELOPMENT"}
    preflight = len([r for r in rows if r["operation"] != "product"]) + 1
    assert len(rows) + preflight == 21 <= 24
    assert sum(r["planned_intent"] == "ATTACK_INTENT" for r in rows) == 1
    assert sum(r["method"] == "POST" and r["role"] == "DEVELOPMENT" for r in rows) == 6
    assert (
        len({r["workflow"] for r in rows if r["method"] == "POST" and r["role"] == "DEVELOPMENT"})
        == 3
    )


def test_HTTP200_without_ping_oracle_stays_unknown(monkeypatch):
    case = c.cases()[0]

    def bad(port, method, path, raw, headers):
        return 200, [], b"generic success page", headers

    monkeypatch.setattr(c, "http", bad)
    r, *_ = c.run_case(
        case, SimpleNamespace(cookies={"PHPSESSID": "fixture-only"}), None, None, [], "test"
    )
    assert r["intent"] == "UNKNOWN_INTENT" and r["outcome"] == "UNKNOWN_OUTCOME"
    assert (
        r["session_group"].startswith("session_group-")
        and r["session_group"].split("-")[-1].isdigit()
    )
    assert r["campaign_group"].startswith("campaign_group-")
    assert not r["oracle_verified"] and r["inclusion_exclusion_reasons"]
    assert "fixture-only" not in str({k: v for k, v in r.items() if k != "transient_checksums"})


def test_bad_product_response_not_status_only_benign(monkeypatch):
    case = next(r for r in c.cases() if r["operation"] == "product")
    monkeypatch.setattr(
        c, "http", lambda port, method, path, raw, headers: (200, [], b"not-json", headers)
    )
    r, *_ = c.run_case(
        case,
        SimpleNamespace(token="private-test-token"),
        None,
        SimpleNamespace(APP="unused"),
        [],
        "test",
    )
    assert r["intent"] == "UNKNOWN_INTENT" and not r["oracle_verified"]


def test_missingness_faults_are_separate_fixtures_not_intent_labels():
    samples = [
        (body.extract(None, "application/json"), "MISSING"),
        (body.extract(b"", "application/json"), "EMPTY"),
        (body.extract(b"{", "application/json"), "MALFORMED"),
        (body.extract(b"x", "multipart/form-data"), "UNSUPPORTED_TYPE"),
        (body.extract(b"{", "application/json", truncated=True), "TRUNCATED"),
    ]
    assert all(body.state_of(v) == state for v, state in samples)
    assert {r["operation"] for r in c.cases()}.isdisjoint(
        {"parser-error", "worker-unavailable", "telemetry-loss", "truncated"}
    )


def test_cleanup_nonzero_exit_requires_actual_absence(monkeypatch):
    import json

    import pytest

    d = SimpleNamespace(APP="owned-app", DB="owned-db", NET="owned-net")

    def run(args, **kwargs):
        if args == ["podman", "inspect", "owned-app"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"Config": {"Labels": {"idps.research-run": c.RUN}}}]).encode(),
            )
        if args[:3] == ["podman", "rm", "-f"]:
            return SimpleNamespace(returncode=125, stdout=b"")
        return SimpleNamespace(returncode=1, stdout=b"")

    monkeypatch.setattr(c.subprocess, "run", run)
    c.cleanup(None, d)
    assert c.CLEANUP_EVENTS[-1]["returncode"] == 125 and c.CLEANUP_EVENTS[-1]["verified_absent"]

    def remains(args, **kwargs):
        if args[:3] == ["podman", "container", "exists"]:
            return SimpleNamespace(returncode=0, stdout=b"")
        return run(args, **kwargs)

    monkeypatch.setattr(c.subprocess, "run", remains)
    with pytest.raises(RuntimeError):
        c.cleanup(None, d)


def test_dispatch_receipt_precedes_transport_and_never_contains_secret(monkeypatch, tmp_path):
    import json

    import pytest

    monkeypatch.setattr(c, "DISPATCH_ROOT", tmp_path)
    monkeypatch.setattr(c, "DISPATCHES", [])

    class Refuse:
        def __init__(self, *args, **kwargs):
            receipt = json.loads((tmp_path / "dispatch-ledger.json").read_text())
            assert receipt[0]["state"] == "ISSUED_RESPONSE_UNCONFIRMED"
            raise OSError("fixture transport failure")

    monkeypatch.setattr(c, "HTTPConnection", Refuse)
    with pytest.raises(OSError):
        c.http(
            1,
            "POST",
            "/fixture",
            b"password=private-fixture",
            {"X-Request-Id": "a" * 32, "Authorization": "Bearer private-fixture"},
        )
    assert "private-fixture" not in (tmp_path / "dispatch-ledger.json").read_text()
    monkeypatch.setattr(c, "DISPATCHES", [{}] * 23)
    with pytest.raises(AssertionError):
        c.http(1, "GET", "/fixture", None, {"X-Request-Id": "b" * 32})


def test_capture_rejects_wrong_physical_execution_before_any_lab_action(tmp_path):
    import json

    import pytest

    from idps_ai.common import digest, file_sha256

    plan = {
        "source_sha256": file_sha256(c.__file__),
        "preaudit": {},
        "run_id": "wrong-physical-execution",
    }
    plan["fingerprint"] = digest(plan)
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(AssertionError):
        c.capture(tmp_path)
    assert not (tmp_path / "heartbeat").exists()
    assert not (tmp_path / "dispatch-ledger.json").exists()


def test_rebind_keeps_logical_templates_and_Oracle_function_bodies_unchanged():
    import ast
    import subprocess

    baseline = ast.parse(
        subprocess.check_output(
            ["git", "show", "33e0b0d:ai-training/scripts/request-v3-final-controls.py"], text=True
        )
    )
    current = ast.parse(Path(c.__file__).read_text())

    def functions(tree):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
        }

    a, b = functions(baseline), functions(current)
    assert all(
        a[name] == b[name] for name in ["cases", "run_case", "preaudit", "php_authenticated"]
    )
