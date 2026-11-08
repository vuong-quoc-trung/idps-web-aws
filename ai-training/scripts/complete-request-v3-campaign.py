#!/usr/bin/env python3
"""Versioned empty-owned-basket fixture; reuse five valid DVWA preflights.

One remaining preflight campaign and one locked main campaign. Credentials and
identities exist in RAM only. No training, scores, seed repair or new templates.
"""

import argparse
import ast
import importlib.util
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from types import SimpleNamespace

from idps_ai.common import atomic_json, digest, file_sha256

ROOT = Path(__file__).resolve().parents[2]
RUN = "request-v3-completion-20261108-r2"
FIXTURE = "dedicated-empty-owned-basket-v2.1"
PREVIOUS = ROOT / "ai-training/.artifacts/request_v3_grounded_20261108/campaign-final-r1"
REUSED = ["control-00", "control-01", "control-02", "control-10", "control-11"]


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def positive(before, after, response_ok):
    prerequisites = all(
        before.get(k)
        for k in [
            "user_exists",
            "basket_exists",
            "basket_owned_by_authenticated_user",
            "product_exists",
            "quantity_record_exists",
            "stock_at_least_requested",
            "limit_allows_requested",
        ]
    )
    return bool(
        response_ok
        and prerequisites
        and before.get("existing_pair_rows") == 0
        and before.get("owned_basket_total_items") == 0
        and after.get("existing_pair_rows") == 1
        and after.get("existing_pair_quantities") == [1]
        and after.get("owned_basket_total_items") == 1
        and after.get("basket_owned_by_authenticated_user")
    )


def negative_control(status, before, after):
    """Rejection/non-creation proof, separate from exact exception taxonomy.

    Do not require a JSON exception body to prove that this duplicate CREATE
    failed. No attack/benign label or causal exception claim is produced here.
    """
    return bool(
        status == 500
        and before.get("existing_pair_rows") == 1
        and before.get("existing_pair_quantities") == [1]
        and before.get("basket_owned_by_authenticated_user")
        and before.get("product_exists")
        and before.get("user_exists")
        and any(
            i.get("unique") and set(i.get("columns", [])) == {"BasketId", "ProductId"}
            for i in before.get("indexes", [])
        )
        and before == after
    )


def identity(c, session, setup):
    status, _, data, _ = c.http(
        c.PORT,
        "GET",
        "/rest/user/whoami",
        None,
        {"Authorization": "Bearer " + session.token, "User-Agent": c.UA},
    )
    setup[0] += 1
    user = json.loads(data).get("user", {})
    return status == 200 and user.get("email") == session.identity and user.get("id") == session.uid


def configure(root):
    c = module("request-v3-final-controls")
    diagnosis = module("diagnose-basket-oracle")
    c.RUN = RUN
    old_open, old_case = c.open_fixture_session, c.run_case
    transport = c.http

    def authenticated_http(port, method, path, raw, headers):
        # Pinned currentUser.js authenticates req.cookies.token, not Bearer.
        # Ordinary lab-session binding only; never persist its value or digest.
        if path == "/rest/user/whoami":
            token = headers.get("Authorization", "")
            assert token.startswith("Bearer ")
            headers = dict(headers, Cookie="token=" + token[7:])
        return transport(port, method, path, raw, headers)

    c.http = authenticated_http
    encode = c.representation

    def representation(case, raw=None, headers=None, path=None):
        if case["operation"] == "whoami" and headers is None:
            headers = {
                "Host": f"127.0.0.1:{c.PORT}",
                "User-Agent": c.UA,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer WITHHELD",
                "Cookie": "token=WITHHELD",
            }
        return encode(case, raw=raw, headers=headers, path=path)

    c.representation = representation

    def open_session(env, q, d, role, setup):
        if env != "juice":
            return old_open(env, q, d, role, setup)
        # Ordinary registration/login, no privileged role or database writes.
        email = secrets.token_hex(12) + "@example.invalid"
        password = secrets.token_urlsafe(24)
        status, _, data, _ = c.http(
            c.PORT,
            "POST",
            "/api/Users/",
            json.dumps({"email": email, "password": password, "passwordRepeat": password}).encode(),
            {"Content-Type": "application/json", "User-Agent": c.UA},
        )
        setup[0] += 1
        assert status == 201, "Dedicated registration failed"
        uid = json.loads(data)["data"]["id"]
        status, _, data, _ = c.http(
            c.PORT,
            "POST",
            "/rest/user/login",
            json.dumps({"email": email, "password": password}).encode(),
            {"Content-Type": "application/json", "User-Agent": c.UA},
        )
        setup[0] += 1
        assert status == 200, "Dedicated login failed"
        auth = json.loads(data)["authentication"]
        ss = SimpleNamespace(
            token=auth["token"], bid=auth["bid"], identity=email, uid=uid, basket_added=False
        )
        assert auth["umail"] == email and identity(c, ss, setup), "Session identity unverified"
        before = diagnosis.db_state(d.APP, ss.bid, ss.uid)
        assert (
            before["basket_owned_by_authenticated_user"] and before["owned_basket_total_items"] == 0
        )
        assert before["existing_pair_rows"] == 0
        ss.admin_before = diagnosis.db_state(d.APP, 1, 1)
        assert ss.admin_before["existing_pair_quantities"] == [2]
        n = len(list(root.glob("fixture-state-*.json")))
        atomic_json(
            root / f"fixture-state-{n:02}.json",
            {
                "fixture_version": FIXTURE,
                "role": role,
                "authenticated_identity_verified": True,
                "before": before,
                "seeded_admin_before": ss.admin_before,
                "credentials_persisted": False,
                "identifiers": "Ordinal session group in receipts only",
            },
        )
        return ss

    def run_case(case, session, q, d, setup, phase):
        if case["operation"] != "basket-add":
            return old_case(case, session, q, d, setup, phase)
        auth_ok = identity(c, session, setup)
        before = diagnosis.db_state(d.APP, session.bid, session.uid)
        # Fail before issuing CREATE if the amendment's empty-basket precondition is invalid.
        assert (
            auth_ok
            and before["existing_pair_rows"] == 0
            and before["owned_basket_total_items"] == 0
        )
        result = old_case(case, session, q, d, setup, phase)
        row = result[0]
        after = diagnosis.db_state(d.APP, session.bid, session.uid)
        admin_after = diagnosis.db_state(d.APP, 1, 1)
        ok = positive(before, after, row["oracle_verified"]) and admin_after == session.admin_before
        ok = ok and row["request_id"] == digest([RUN, phase, case["case_id"]])[:32]
        row["oracle_checks"].update(
            readonly_new_pair_persisted=ok,
            authenticated_identity_verified=auth_ok,
            seeded_admin_unchanged=admin_after == session.admin_before,
        )
        atomic_json(
            root / (phase + "-basket-positive.json"),
            {
                "request_id": row["request_id"],
                "fixture_version": FIXTURE,
                "HTTP_status": row["HTTP_status"],
                "before": before,
                "after": after,
                "seeded_admin_unchanged": admin_after == session.admin_before,
                "authenticated_identity_verified": auth_ok,
                "positive_CREATE_verified": ok,
                "transaction_identity": "Collector request ID; RAM session; independent readonly DB witness, no packet-capture claim",
            },
        )
        if ok and phase == "preflight":
            rid = digest([RUN, "DIAGNOSTIC_ONLY", "duplicate-create-negative"])[:32]
            status, _, data, _ = c.http(
                c.PORT,
                "POST",
                "/api/BasketItems/",
                json.dumps({"ProductId": 1, "BasketId": session.bid, "quantity": 1}).encode(),
                {
                    "Content-Type": "application/json",
                    "User-Agent": c.UA,
                    "Authorization": "Bearer " + session.token,
                    "X-Request-Id": rid,
                },
            )
            error = diagnosis.safe_error(data)
            after_negative = diagnosis.db_state(d.APP, session.bid, session.uid)
            neg = diagnosis.classify(status, error, after, after_negative)
            rejected = negative_control(status, after, after_negative)
            atomic_json(
                root / "basket-negative-diagnostic.json",
                {
                    "request_id": rid,
                    "HTTP_status": status,
                    "sanitized_error": error,
                    "classification": neg,
                    "negative_control_PASS": rejected,
                    "exception_taxonomy_required_for_rejection_proof": False,
                    "supervised_eligible": False,
                    "intent_label": "NO_SUPERVISED_LABEL",
                    "state": after_negative,
                    "fixture_version": FIXTURE,
                },
            )
            if not rejected:
                # Preserve a verified positive result, but stop the campaign.
                row["campaign_gate_failure"] = "NEGATIVE_CONTROL_UNVERIFIED"
        if not ok:
            row.update(
                oracle_verified=False,
                intent="UNKNOWN_INTENT",
                outcome="UNKNOWN_OUTCOME",
                evidence_levels=["REVIEW_PENDING", "INSUFFICIENT_EVIDENCE"],
            )
            row["inclusion_exclusion_reasons"].append("BASKET_FIXTURE_OR_STATE_UNVERIFIED")
        session.basket_added = ok
        return result

    c.open_fixture_session, c.run_case = open_session, run_case
    return c


def lock(root):
    c = configure(root)
    parent = c.load(PREVIOUS / "plan.json")
    old_source = ast.parse(
        subprocess.check_output(
            ["git", "show", "514bedf:ai-training/scripts/request-v3-final-controls.py"], text=True
        )
    )
    new_source = ast.parse(Path(c.__file__).read_text())

    def fs(tree):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
        }

    assert all(
        fs(old_source)[k] == fs(new_source)[k]
        for k in ["cases", "run_case", "preaudit", "php_authenticated"]
    )
    c.prepare(root)
    plan = c.load(root / "plan.json")
    for key in [
        "cases",
        "preflight_case_ids",
        "oracles",
        "coverage",
        "expected_availability",
        "duplicates",
        "images",
    ]:
        assert plan[key] == parent[key], key
    previous = c.load(PREVIOUS / "preflight-oracle-receipts.json")
    assert len(previous) == 6 and not previous[-1]["oracle_verified"]
    assert all(
        r["oracle_verified"] and r["environment"] == "dvwa"
        for r in previous
        if r["case_id"] in REUSED
    )
    images = {
        k: json.loads(subprocess.check_output(["podman", "image", "inspect", v]))[0]["Id"]
        for k, v in plan["images"].items()
    }
    env = {
        "schema_version": "request-v3-fixture-amendment-2",
        "execution_id": RUN,
        "previous_fixture_version": "seeded-admin-owned-basket-v1",
        "fixture_version": FIXTURE,
        "reason": "Verified existing ProductId1 seeded pair violates CREATE unique constraint",
        "change": "Register ordinary dedicated account in each fresh lab role; authenticate; verify initially empty own basket before unchanged CREATE",
        "unchanged": "ProductId1,quantity1,POST endpoint,expected200,roles,templates,Oracle semantics,coverage,dedup,model contract",
        "oracle_strengthening": "Readonly precondition/new-row/persisted quantity witness; duplicate-CREATE negative diagnostic; seeded admin unchanged",
        "tooling_correction": "Product readonly witness uses pinned distroless /nodejs/bin/node; SQL and equality semantics unchanged",
        "session_binding_correction": "Pinned currentUser.js requires token cookie; bind same authenticated RAM token to whoami cookie as well as Bearer. Identity/Oracle meaning unchanged; actual transmitted headers audited",
        "setup_abort_preserved": "r1 registered/logged in but Bearer-only whoami failed setup identity check; zero targeted preflight/main dispatches. No representative relabel or campaign retry after an Oracle receipt failure",
        "current_user_source_sha256": file_sha256(
            ROOT / ".local-dev/request-v3-completion-20261108/pinned-currentUser.js"
        ),
        "source_sha256": {
            str(p.relative_to(ROOT)): file_sha256(p)
            for p in [
                Path(__file__),
                Path(c.__file__),
                Path(__file__).with_name("diagnose-basket-oracle.py"),
            ]
        },
        "images": images,
        "command_namespace": "net.ipv4.ping_group_range=33 33 app only",
        "host_sysctl_before": Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip(),
        "parent_plan_fingerprint": parent["fingerprint"],
        "root_cause_report_sha256": file_sha256(
            ROOT / "ai-training/reports/BASKET_ORACLE_ROOT_CAUSE_20261108.json"
        ),
        "protocol_integrity": "PRESERVED_NO_ROLE_TEMPLATE_OR_ORACLE_MEANING_CHANGE",
        "new_preflight_representatives": 4,
        "reused_preflight_representatives": 5,
        "negative_diagnostics": 1,
        "new_main_templates": 12,
        "main_receipt_cap": 24,
        "no_replacement_or_retry_campaign": True,
    }
    env["fingerprint"] = digest(env)
    atomic_json(root / "fixture-amendment.json", env)
    plan.update(
        environment_fingerprint=env["fingerprint"],
        fixture_version=FIXTURE,
        logical_parent_plan_fingerprint=parent["fingerprint"],
        fixture_driver_sha256=file_sha256(__file__),
        reuse_preflight={
            "file": str(PREVIOUS / "preflight-oracle-receipts.json"),
            "sha256": file_sha256(PREVIOUS / "preflight-oracle-receipts.json"),
            "case_ids": REUSED,
        },
        bookkeeping_note="5 valid DVWA preflights reused,4 new Juice representatives,1 negative diagnostic,12 fixed main; no old UNKNOWN relabel or duplicate evidence inflation",
    )
    plan.pop("fingerprint")
    plan["fingerprint"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    print(
        json.dumps(
            {
                "plan_fingerprint": plan["fingerprint"],
                "amendment_fingerprint": env["fingerprint"],
                "preaudit": plan["preaudit"],
            }
        )
    )


def capture(root):
    c = configure(root)
    plan = c.load(root / "plan.json")
    assert plan["fixture_driver_sha256"] == file_sha256(__file__)
    env = c.load(root / "fixture-amendment.json")
    assert env["fingerprint"] == digest({k: v for k, v in env.items() if k != "fingerprint"})
    assert plan["environment_fingerprint"] == env["fingerprint"]
    for p, sha in env["source_sha256"].items():
        assert file_sha256(ROOT / p) == sha
    c.capture(root)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["lock", "capture"])
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--execution-id", required=True)
    a = p.parse_args()
    assert re.fullmatch(r"request-v3-[a-z0-9-]{1,64}", a.execution_id)
    RUN = a.execution_id
    os.umask(0o077)
    {"lock": lock, "capture": capture}[a.action](a.output.resolve())
