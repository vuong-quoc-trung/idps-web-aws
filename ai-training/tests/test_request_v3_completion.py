"""Fixture amendment rejects status-only certification and preserves protocol."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "completion", Path(__file__).parents[1] / "scripts/complete-request-v3-campaign.py"
)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def state():
    return {
        **{
            k: True
            for k in [
                "user_exists",
                "basket_exists",
                "basket_owned_by_authenticated_user",
                "product_exists",
                "quantity_record_exists",
                "stock_at_least_requested",
                "limit_allows_requested",
            ]
        },
        "existing_pair_rows": 0,
        "existing_pair_quantities": [],
        "owned_basket_total_items": 0,
    }


def test_positive_requires_absent_pair_and_new_persisted_quantity():
    before = state()
    after = dict(
        before, existing_pair_rows=1, existing_pair_quantities=[1], owned_basket_total_items=1
    )
    assert f.positive(before, after, True)
    assert not f.positive(before, after, False)
    assert not f.positive(before, before, True)
    assert not f.positive(dict(before, existing_pair_rows=1), after, True)
    assert not f.positive(before, dict(after, existing_pair_quantities=[2]), True)
    assert not f.positive(before, dict(after, basket_owned_by_authenticated_user=False), True)
    for key in [
        "user_exists",
        "product_exists",
        "quantity_record_exists",
        "limit_allows_requested",
    ]:
        assert not f.positive(dict(before, **{key: False}), after, True)


def test_identity_requires_actual_authenticated_response_not_token_decode():
    c = SimpleNamespace(PORT=1, UA="test")
    session = SimpleNamespace(identity="secret@example.invalid", uid=8, token="private-token")
    setup = [0]
    c.http = lambda *a: (
        200,
        [],
        json.dumps({"user": {"email": session.identity, "id": 8}}).encode(),
        {},
    )
    assert f.identity(c, session, setup) and setup == [1]
    c.http = lambda *a: (200, [], b'{"user":{}}', {})
    assert not f.identity(c, session, setup)
    c.http = lambda *a: (401, [], b'{"user":{}}', {})
    assert not f.identity(c, session, setup)


def test_fixture_is_finite_and_only_valid_old_dvwa_representatives_reused(tmp_path):
    c = f.configure(tmp_path)
    assert c.RUN == f.RUN
    assert len(c.cases()) == 12
    assert f.REUSED == ["control-00", "control-01", "control-02", "control-10", "control-11"]
    assert all(r["environment"] == "dvwa" for r in c.cases() if r["case_id"] in f.REUSED)


def test_negative_rejection_is_separate_from_exception_taxonomy():
    before = dict(
        state(),
        existing_pair_rows=1,
        existing_pair_quantities=[1],
        owned_basket_total_items=1,
        indexes=[{"unique": True, "columns": ["ProductId", "BasketId"]}],
    )
    # HTTP rejection and unchanged readonly state are sufficient for non-creation.
    assert f.negative_control(500, before, dict(before))
    assert not f.negative_control(200, before, dict(before))
    assert not f.negative_control(500, before, dict(before, existing_pair_quantities=[2]))
    assert not f.negative_control(500, dict(before, existing_pair_rows=0), before)
    assert not f.negative_control(500, dict(before, indexes=[]), dict(before, indexes=[]))
    d = f.module("diagnose-basket-oracle")
    unknown = d.safe_error(b"non-JSON error representation")
    assert unknown["exception_class"] == "UNKNOWN"
    assert not d.classify(500, unknown, before, dict(before))["verified"]
    # Non-creation proof does NOT silently assert a Sequelize root cause.


def test_whoami_cookie_binding_is_transient_and_only_for_identity_endpoint(tmp_path, monkeypatch):
    c = f.configure(tmp_path)
    seen = []

    class Connection:
        def __init__(self, *a, **kw):
            pass

        def putrequest(self, *a, **kw):
            pass

        def putheader(self, k, v):
            seen.append((k, v))

        def endheaders(self, raw):
            pass

        def getresponse(self):
            return SimpleNamespace(status=200, getheaders=lambda: [], read=lambda n: b"{}")

        def close(self):
            pass

    monkeypatch.setattr(c, "HTTPConnection", Connection)
    c.http(1, "GET", "/rest/user/whoami", None, {"Authorization": "Bearer private-test-token"})
    assert ("Cookie", "token=private-test-token") in seen
    seen.clear()
    c.http(1, "POST", "/api/BasketItems/", b"{}", {"Authorization": "Bearer private-test-token"})
    assert not any(k == "Cookie" for k, v in seen)
    assert not list(tmp_path.iterdir())
    c.privacy_check()
    proof = json.loads((tmp_path / "actual-value-privacy-check.json").read_text())
    assert proof["status"] == "PASS_FOR_RESEARCH"
    assert proof["actual_private_values_scanned_in_RAM"] > 0
    (tmp_path / "bad-metadata.json").write_text(
        json.dumps({"session_group": hashlib.sha256(b"private-test-token").hexdigest()})
    )
    with pytest.raises(AssertionError, match="Private value"):
        c.privacy_check()


def test_unknown_error_taxonomy_does_not_overwrite_positive_oracle(tmp_path, monkeypatch):
    from idps_ai.common import digest

    before = state()
    after = dict(
        before,
        existing_pair_rows=1,
        existing_pair_quantities=[1],
        owned_basket_total_items=1,
        indexes=[{"unique": True, "columns": ["ProductId", "BasketId"]}],
    )
    admin = dict(after, existing_pair_quantities=[2], owned_basket_total_items=3)
    counter = [0]

    def db(app, bid, uid):
        if bid == 1:
            return admin
        counter[0] += 1
        return before if counter[0] == 1 else after

    diag = f.module("diagnose-basket-oracle")
    monkeypatch.setattr(diag, "db_state", db)
    c = SimpleNamespace(PORT=1, UA="test")
    c.http = lambda port, method, path, raw, headers: (
        (200, [], b'{"user":{"email":"private@example.invalid","id":8}}', headers)
        if path.endswith("whoami")
        else (500, [], b"non-JSON error representation", headers)
    )
    c.open_fixture_session = lambda *a: None
    c.representation = lambda *a, **kw: None
    c.run_case = lambda case, *a: (
        {
            "oracle_verified": True,
            "intent": "BENIGN_INTENT",
            "outcome": "BENIGN_SUCCESS",
            "HTTP_status": 200,
            "inclusion_exclusion_reasons": [],
            "request_id": digest([f.RUN, "preflight", case["case_id"]])[:32],
            "oracle_checks": {},
            "evidence_levels": ["APPLICATION_ORACLE_VERIFIED"],
        },
        None,
    )
    monkeypatch.setattr(f, "module", lambda n: c if n == "request-v3-final-controls" else diag)
    c = f.configure(tmp_path)
    ss = SimpleNamespace(
        token="private-token", bid=2, uid=8, identity="private@example.invalid", admin_before=admin
    )
    row = c.run_case(
        {"case_id": "control-03", "operation": "basket-add"},
        ss,
        None,
        SimpleNamespace(APP="fixture"),
        [0],
        "preflight",
    )[0]
    assert row["oracle_verified"] and row["intent"] == "BENIGN_INTENT"
    negative = json.loads((tmp_path / "basket-negative-diagnostic.json").read_text())
    assert negative["negative_control_PASS"]
    assert negative["classification"]["root_cause"] == "UNKNOWN"
    assert not negative["supervised_eligible"]
    assert "private-token" not in "".join(p.read_text() for p in tmp_path.iterdir())
    assert "private@example.invalid" not in "".join(p.read_text() for p in tmp_path.iterdir())
