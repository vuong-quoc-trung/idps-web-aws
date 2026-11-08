#!/usr/bin/env python3
"""Finite local Oracle controls. Only approved numeric receipts leave transient RAM.

No raw HTTP bodies/headers/responses, session values or their digests are written.
The complete bounded template catalog is source-pinned before HTTP, not score-selected.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import raw_key, runtime_request, vector_hash
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.features.request_preprocessing import bounded_spec

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "ai-training/.artifacts/request_v3_body_syntax_20261108/release-v2"
ORIGINAL = ROOT / "ai-training/.artifacts/attack_intent_20261107/release-v3"
RUN = "request-v3-final-20261108"
PORT = 19280
UA = "Mozilla/5.0 LabResearch"
DISPATCH_ROOT = None
DISPATCHES = []
CLEANUP_EVENTS = []


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(p.read_text())


def cases():
    """Fixed operations, no nonce/identity/header padding for feature novelty."""
    out = []

    def add(env, role, workflow, operation, method, path, fields=None, family="benign"):
        out.append(
            dict(
                case_id=f"control-{len(out):02d}",
                environment=env,
                role=role,
                workflow=workflow,
                operation=operation,
                method=method,
                path=path,
                fields=fields,
                family=family,
                planned_intent="BENIGN_INTENT" if family == "benign" else "ATTACK_INTENT",
            )
        )

    add(
        "dvwa",
        "TRAIN",
        "legitimate-loopback-command",
        "ping",
        "POST",
        "/vulnerabilities/exec/",
        {"ip": '"localhost"', "Submit": "Submit"},
    )
    add(
        "dvwa",
        "TRAIN",
        "authorized-public-file",
        "file",
        "GET",
        "/vulnerabilities/fi/?" + urlencode({"page": "/var/www/html/vulnerabilities/fi/file1.php"}),
    )
    # One new attempt is needed to avoid making natural MISSING a benign-only signal.
    add(
        "dvwa",
        "TRAIN",
        "missing-body-union-oracle",
        "union",
        "GET",
        "/vulnerabilities/sqli/?"
        + urlencode(
            {
                "id": "0' UNION SELECT CONCAT('safe','probe'),CONCAT('coverage','query')#",
                "Submit": "Submit",
            }
        ),
        family="sqli",
    )
    add(
        "juice",
        "TRAIN",
        "owned-basket-json",
        "basket-add",
        "POST",
        "/api/BasketItems/",
        {"ProductId": 1, "BasketId": 1, "quantity": 1},
    )
    add("juice", "TRAIN", "owned-basket-read", "basket-read", "GET", "/rest/basket/1")
    descriptions = [
        "Recipe: mix fruit; cost = 3",
        "Shell manual: printf '%s' item | cat",
        "Path documentation: /srv/catalog/{item}.json",
        "Escaped HTML example: &lt;strong&gt;fruit&lt;/strong&gt;",
    ]
    for desc in descriptions:
        add(
            "juice",
            "DEVELOPMENT",
            "catalog-product-json",
            "product",
            "POST",
            "/api/Products/",
            {
                "name": "Research control product",
                "description": desc,
                "price": 2.5,
                "image": "apple_juice.jpg",
            },
        )
    add("juice", "DEVELOPMENT", "authenticated-identity-read", "whoami", "GET", "/rest/user/whoami")
    add(
        "dvwa",
        "DEVELOPMENT",
        "authenticated-login-form",
        "login",
        "POST",
        "/login.php",
        {"username": "admin", "password": "WITHHELD", "Login": "Login", "user_token": "WITHHELD"},
    )
    add("dvwa", "DEVELOPMENT", "authenticated-logout-form", "logout", "POST", "/logout.php", {})
    return out


def configured_helpers():
    q = module("quality-lab-cohort")
    d = module("p0-dvwa-capture")
    q.RUN = RUN
    q.LABEL = "idps.research-run=" + RUN
    d.PORT = PORT
    d.DB = RUN + "-db"
    d.APP = RUN + "-app"
    d.NET = RUN + "-net"
    return q, d


def predictor():
    from sklearn.feature_extraction.text import HashingVectorizer

    return SimpleNamespace(
        numeric_spec=bounded_spec(),
        vectorizer=HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        ),
    )


def representation(case, raw=None, headers=None, path=None):
    if raw is None and case["method"] == "POST":
        fields = case["fields"] or {}
        raw = (json.dumps(fields) if case["environment"] == "juice" else urlencode(fields)).encode()
    headers = headers or {
        "Host": f"127.0.0.1:{PORT}",
        "User-Agent": UA,
        "Accept": "application/json" if case["environment"] == "juice" else "text/html",
        "Content-Type": "application/json"
        if case["environment"] == "juice"
        else "application/x-www-form-urlencoded",
        **({"Content-Length": str(len(raw))} if raw is not None else {}),
        **(
            {"Authorization": "Bearer WITHHELD"}
            if case["environment"] == "juice"
            else {"Cookie": "WITHHELD"}
        ),
    }
    req = {
        "method": case["method"],
        "url": path or case["path"],
        "body": raw.decode() if raw is not None else None,
        "headers": "\r\n".join(f"{k}: {v}" for k, v in headers.items()),
    }
    pv = module("p0-request-evaluate")
    uc = module("training-unblock-cohort")
    pred = predictor()
    full = pv.vector(pred, req)[0]
    runtime = pv.vector(pred, runtime_request(req))[0]
    keys = uc.keys(req, pred, pv)[0]
    keys["raw"] = raw_key(req)
    # Only equality/near relations are emitted later, never these raw/template keys.
    b = body.extract(raw, headers.get("Content-Type"))
    return runtime, request_v3.assemble(runtime, b), full, keys, b


def parent_inputs():
    report = load(PARENT / "dataset-release.json")
    for name, sha in report["files_sha256"].items():
        assert file_sha256(PARENT / name) == sha
    rows = [json.loads(x) for x in (PARENT / "records.jsonl").read_text().splitlines()]
    original = {
        r["sample_id"]: r
        for r in (json.loads(x) for x in (ORIGINAL / "records.jsonl").read_text().splitlines())
    }
    original_full = {}
    base = {}
    for role in ["train", "calibration", "development"]:
        with np.load(ORIGINAL / (role + ".npz"), allow_pickle=False) as z:
            original_full.update(
                {str(i): v.copy() for i, v in zip(z["ids"], z["full"], strict=True)}
            )
        with np.load(PARENT / (role + ".npz"), allow_pickle=False) as z:
            base.update(
                {
                    str(i): (x.copy(), f.copy(), b.copy())
                    for i, x, f, b in zip(
                        z["ids"], z["x"], z["frozen_runtime"], z["body_syntax"], strict=True
                    )
                }
            )
    return rows, original, original_full, base


def preaudit(selected):
    old, original, fulls, base = parent_inputs()
    m = module("materialize-request-v3")
    rows = []
    runtime = []
    joint = []
    full = []
    for r in old:
        rows.append(
            dict(r, split=r["original_role"], checksums=original[r["sample_id"]]["checksums"])
        )
        x, f, _ = base[r["sample_id"]]
        runtime.append(f)
        joint.append(x)
        full.append(fulls[r["sample_id"]])
    for k, c in enumerate(selected):
        f, x, v, keys, b = representation(c)
        rows.append(
            dict(
                sample_id="new-" + str(k),
                split=c["role"],
                method=c["method"],
                endpoint_template=re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(c["path"]).path),
                intent=c["planned_intent"],
                checksums={
                    "raw": keys["raw"],
                    "template": keys["template"],
                    "full_view": vector_hash(v),
                },
            )
        )
        runtime.append(f)
        joint.append(x)
        full.append(v)
    x = np.stack(joint)
    f = np.stack(runtime)
    v = np.stack(full)
    near_candidate = m.near_pairs(rows, f, x[:, 588:], use_body=True)
    near_full = m.near_pairs(rows, v, x[:, 588:], use_body=False)
    issues = {c["case_id"]: set() for c in selected}
    for i in range(len(old), len(rows)):
        c = selected[i - len(old)]
        for j in range(i):
            cross = rows[i]["split"] != rows[j]["split"]
            same_old = j < len(old)
            if not (cross or same_old):
                continue
            for key in ["raw", "template", "full_view"]:
                if rows[i]["checksums"][key] == rows[j]["checksums"][key]:
                    issues[c["case_id"]].add("EXACT_" + key)
            if np.array_equal(x[i], x[j]):
                issues[c["case_id"]].add("EXACT_CANDIDATE")
        for name, pairs in [("NEAR_CANDIDATE", near_candidate), ("NEAR_FULL", near_full)]:
            for a, b in pairs:
                if b == i and (a < len(old) or rows[a]["split"] != rows[b]["split"]):
                    issues[c["case_id"]].add(name)
    return {k: sorted(v) for k, v in issues.items()}


def prepare(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    selected = cases()
    overlap = preaudit(selected)
    q, d = configured_helpers()
    plan = {
        "schema_version": "request-v3-final-controls-plan-1",
        "run_id": RUN,
        "source_sha256": file_sha256(__file__),
        "helper_sha256": {
            name: file_sha256(Path(__file__).with_name(name + ".py"))
            for name in [
                "quality-lab-cohort",
                "p0-dvwa-capture",
                "attack-intent-capture",
                "training-unblock-cohort",
                "materialize-request-v3",
                "p0-request-evaluate",
            ]
        },
        "parent_fingerprint": load(PARENT / "dataset-release.json")["dataset_fingerprint"],
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "main_receipts": len(selected),
        "total_targeted_receipt_cap": 24,
        "prior_dispatch_upper_bound_reserved": 1,
        "operational_correction": "Two pre-target setup aborts retained; corrected Oracle reads nested dvwa session from pinned source; nonzero removal exit checked against actual absence; no template/label/role/coverage changes",
        "setup_call_cap": 120,
        "preflight_case_ids": [c["case_id"] for c in selected if c["operation"] != "product"]
        + [next(c["case_id"] for c in selected if c["operation"] == "product")],
        "cases": [
            {k: v for k, v in c.items() if k not in {"fields", "path"}}
            | {"endpoint_template": re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(c["path"]).path)}
            for c in selected
        ],
        "template_binding": "Exact fixed templates in source; dynamic own basket/CSRF bindings transient RAM only; no source raw body evidence persisted",
        "expected_availability": {
            c["case_id"]: (
                "MISSING"
                if c["method"] == "GET"
                else "EMPTY"
                if c["operation"] == "logout"
                else "OK"
            )
            for c in selected
        },
        "preaudit": overlap,
        "roles": "Preflight only diagnostics, fresh instances for main; separate app instances/sessions per role. CAL and sealed untouched. No scores",
        "labels": "Precommitted intent, internal application state/response Oracle; unmatched UNKNOWN, review PENDING",
        "oracles": {
            "ping": "Literal localhost quoted as one shell argument, no operators/substitution/options; four transmitted and four received, zero loss",
            "file": "Only declared public file1.php, normal PHP include render File1/Hello, not raw source/private-file disclosure",
            "union": "One deliberate new UNION query yields declared synthetic columns; MISSING is not benign-only",
            "basket": "Owned basket add response identity plus authenticated own-basket read confirms product/quantity",
            "product": "Product response plus independent read-only DB-state witness equals all declared legitimate fields",
            "login": "Valid fixture credential response and server-side authenticated-session witness",
            "logout": "Session witness absent after normal logout",
            "whoami": "Authenticated account identity in response, compare in RAM only",
        },
        "coverage": {
            "inherit_previous_minimums": True,
            "TRAIN_new_JSON_POST_views": 1,
            "TRAIN_command_counterpart_views": 1,
            "TRAIN_file_counterpart_views": 1,
            "DEV_benign_POST_unique_views": 6,
            "DEV_benign_POST_workflows": 3,
            "DEV_benign_POST_media": ["FORM", "JSON"],
            "natural_MISSING_not_benign_only": True,
        },
        "duplicates": "Use inherited raw/template/full/full-near/candidate-near and lineage rules, quarantine both sides; no reassignment or threshold tuning",
        "privacy": "Only634vectors,numeric receipts,Oracle booleans/counts and ordinal groups. No raw requests/responses, header values, direct secret digests or per-record data in public Git",
        "stop": "One preflight and one main campaign only; stop on essential Oracle/ownership/thermal failure, cap24targetedreceipts, no replacement or filler",
        "images": {"dvwa": d.APP_IMAGE, "db": d.DB_IMAGE, "juice": q.JUICE},
        "resource": {
            "quota_percent_one_core": 25,
            "ownership_watchdog_stop_c": 80,
            "outer_guard_cutoff_c": 85,
            "reserve_GiB": 4,
        },
        "training": False,
        "sealed_opened": False,
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    print(
        json.dumps(
            {
                "plan_fingerprint": plan["fingerprint"],
                "planned_main": len(selected),
                "preflight": len(plan["preflight_case_ids"]),
                "overlap": overlap,
            },
            indent=2,
        )
    )


class RAMSession:
    """Existing DVWA setup protocol with all receipts/session material held in RAM."""

    def __init__(self, output=None):
        self.cookies = {}
        self.setup_requests = 0
        self.last_headers = {}

    def call(self, method, path, body="", extra=None, port=PORT):
        raw = body.encode() if isinstance(body, str) else body
        headers = {
            "User-Agent": UA,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            **(extra or {}),
        }
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        status, returned, data, sent = http(port, method, path, raw, headers)
        for name, value in returned:
            if name.lower() == "set-cookie":
                c = SimpleCookie()
                c.load(value)
                self.cookies.update({k: v.value for k, v in c.items()})
        self.setup_requests += 1
        self.last_headers = sent
        return status, returned, data, sent


def http(port, method, path, raw, headers):
    if DISPATCH_ROOT is not None and "X-Request-Id" in headers:
        assert (
            len(DISPATCHES) + 1 < 24
        )  # reserve one uncertain dispatch from the aborted first setup
        DISPATCHES.append(
            {
                "request_id": headers["X-Request-Id"],
                "method": method,
                "state": "ISSUED_RESPONSE_UNCONFIRMED",
            }
        )
        atomic_json(DISPATCH_ROOT / "dispatch-ledger.json", DISPATCHES)
    c = HTTPConnection("127.0.0.1", port, timeout=15)
    sent = {"Host": f"127.0.0.1:{port}", **headers}
    if raw is not None:
        sent["Content-Length"] = str(len(raw))
    try:
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in sent.items():
            c.putheader(k, v)
        c.endheaders(raw)
        r = c.getresponse()
        data = r.read(1_000_001)
        if len(data) > 1_000_000:
            raise RuntimeError("Response bound exceeded")
        if DISPATCH_ROOT is not None and "X-Request-Id" in headers:
            DISPATCHES[-1].update(state="RESPONSE_RECEIVED", status=r.status)
            atomic_json(DISPATCH_ROOT / "dispatch-ledger.json", DISPATCHES)
        return r.status, r.getheaders(), data, sent
    finally:
        c.close()


def php_authenticated(q, d, session):
    code = """$v=json_decode(stream_get_contents(STDIN),true);$id=$v['id'];if(!preg_match('/^[A-Za-z0-9,-]+$/',$id)){exit(2);} $ok=false;foreach(array_filter([session_save_path(),'/var/lib/php/sessions','/tmp']) as $p){$s=@file_get_contents($p.'/sess_'.$id);if($s!==false){$i=strpos($s,'dvwa|');if($i!==false){$a=@unserialize(substr($s,$i+5),['allowed_classes'=>false]);$ok=$ok||(is_array($a)&&($a['username']??null)==='admin');}}}echo json_encode(['authenticated'=>$ok]);"""
    proc = subprocess.run(
        ["podman", "exec", "-i", d.APP, "php", "-r", code],
        input=json.dumps({"id": session.cookies.get("PHPSESSID", "")}).encode(),
        capture_output=True,
        timeout=10,
        check=True,
    )
    return json.loads(proc.stdout)["authenticated"]


def product_witness(name, expected):
    code = """let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>{let v=JSON.parse(s);let sql=require('sqlite3');let db=new sql.Database('data/juiceshop.sqlite',sql.OPEN_READONLY);db.get('SELECT id,name,description,price,image FROM Products WHERE id=?',[v.id],(e,r)=>{console.log(JSON.stringify({match:!e&&!!r&&r.name===v.name&&r.description===v.description&&Number(r.price)===v.price&&r.image===v.image}));db.close();});});"""
    p = subprocess.run(
        ["podman", "exec", "-i", name, "node", "-e", code],
        input=json.dumps(expected).encode(),
        capture_output=True,
        timeout=10,
        check=True,
    )
    return json.loads(p.stdout)["match"]


def open_fixture_session(env, q, d, case_role, setup):
    if env == "dvwa":
        ss = RAMSession()
        _, _, page, _ = ss.call("GET", "/login.php")
        setup[0] += 1
        token = re.search(rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page)
        assert token
        ss.token = token[1].decode()
        if case_role == "TRAIN":
            status, _, _, _ = ss.call(
                "POST",
                "/login.php",
                urlencode(
                    {
                        "username": "admin",
                        "password": "password",
                        "Login": "Login",
                        "user_token": ss.token,
                    }
                ),
            )
            setup[0] += 1
            assert status == 302 and php_authenticated(q, d, ss)
        ss.cookies["security"] = "low"
        return ss
    status, _, data, _ = http(
        PORT,
        "POST",
        "/rest/user/login",
        json.dumps({"email": "admin@juice-sh.op", "password": "admin123"}).encode(),
        {"Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"},
    )
    setup[0] += 1
    assert status == 200
    auth = json.loads(data)["authentication"]
    return SimpleNamespace(
        token=auth["token"], bid=auth["bid"], identity=auth["umail"], basket_added=False
    )


def run_case(c, session, q, d, setup, phase):
    case = dict(c)
    path = c["path"]
    fields = dict(c["fields"] or {})
    env = c["environment"]
    op = c["operation"]
    if op == "basket-add":
        fields["BasketId"] = session.bid
    if op == "basket-read":
        path = f"/rest/basket/{session.bid}"
    if op == "login":
        fields.update(password="password", user_token=session.token)
    raw = (
        None
        if c["method"] == "GET"
        else (json.dumps(fields) if env == "juice" else urlencode(fields)).encode()
    )
    rid = digest([RUN, phase, c["case_id"]])[:32]
    headers = {
        "User-Agent": UA,
        "Accept": "application/json" if env == "juice" else "text/html",
        "Content-Type": "application/json"
        if env == "juice"
        else "application/x-www-form-urlencoded",
        "X-Request-Id": rid,
    }
    if env == "juice":
        headers["Authorization"] = "Bearer " + session.token
    else:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in session.cookies.items())
    start = time.monotonic()
    status, returned, data, sent = http(PORT, c["method"], path, raw, headers)
    if env == "dvwa":
        for key, value in returned:
            if key.lower() == "set-cookie":
                cookie = SimpleCookie()
                cookie.load(value)
                session.cookies.update({k: v.value for k, v in cookie.items()})
    proof = {}
    matched = False
    try:
        if op == "ping":
            proof = {
                "localhost_resolved": bool(re.search(rb"PING localhost\b", data)),
                "four_transmitted": b"4 packets transmitted" in data,
                "four_received": bool(re.search(rb"4 (?:packets )?received", data)),
                "zero_loss": b"0% packet loss" in data,
            }
            matched = status == 200 and all(proof.values())
        elif op == "file":
            proof = {
                "declared_public_file_render": b"<h3>File 1</h3>" in data,
                "normal_public_greeting": b"Hello <em>admin</em>" in data,
                "no_raw_php_source": b"<?php" not in data,
            }
            matched = status == 200 and all(proof.values())
        elif op == "union":
            proof = {
                "declared_first_column": b"First name: safeprobe" in data,
                "declared_second_column": b"Surname: coveragequery" in data,
            }
            matched = status == 200 and all(proof.values())
        elif op == "basket-add":
            value = json.loads(data).get("data", {})
            matched = (
                status == 200
                and int(value.get("ProductId", -1)) == 1
                and int(value.get("BasketId", -1)) == int(session.bid)
                and int(value.get("quantity", -1)) == 1
            )
            proof = {"owned_product_quantity_response": matched}
            session.basket_added = matched
        elif op == "basket-read":
            value = json.loads(data).get("data", {})
            products = value.get("Products", [])
            proof = {
                "prior_owned_add": session.basket_added,
                "owned_product_quantity_state": any(
                    int(p.get("id", -1)) == 1
                    and int(p.get("BasketItem", {}).get("quantity", -1)) == 1
                    for p in products
                ),
            }
            matched = status == 200 and all(proof.values())
        elif op == "product":
            value = json.loads(data).get("data", {})
            response_ok = (
                status in {200, 201}
                and value.get("id") is not None
                and all(
                    value.get(k) == v or k == "price" and float(value.get(k, -1)) == v
                    for k, v in fields.items()
                )
            )
            state_ok = (
                product_witness(d.APP, dict(fields, id=value.get("id", -1)))
                if response_ok
                else False
            )
            proof = {
                "response_schema_and_declared_fields": response_ok,
                "independent_readonly_DB_state_witness": state_ok,
            }
            matched = all(proof.values())
        elif op == "whoami":
            value = json.loads(data).get("user", {})
            proof = {"authenticated_identity_match_in_RAM": value.get("email") == session.identity}
            matched = status == 200 and all(proof.values())
        elif op == "login":
            proof = {
                "normal_login_redirect": status == 302,
                "server_authenticated_session": php_authenticated(q, d, session),
            }
            matched = all(proof.values())
        elif op == "logout":
            proof = {
                "normal_logout_redirect": status == 302,
                "server_session_no_longer_authenticated": not php_authenticated(q, d, session),
            }
            matched = all(proof.values())
    except (ValueError, KeyError, TypeError, subprocess.SubprocessError):
        proof = {"application_Oracle_verified": False, "evidence_gap": True}
        matched = False
    f, x, full, keys, b = representation(case, raw=raw, headers=sent, path=path)
    intent = c["planned_intent"] if matched else "UNKNOWN_INTENT"
    outcome = (
        "BENIGN_SUCCESS"
        if matched and intent == "BENIGN_INTENT"
        else "VERIFIED_EXPLOIT_SUCCESS"
        if matched
        else "UNKNOWN_OUTCOME"
    )
    row = {
        "sample_id": digest([RUN, phase, rid]),
        "request_id": rid,
        "case_id": c["case_id"],
        "environment": env,
        "source": "FINITE_ORACLE_CONTROLS_20261108",
        "split": c["role"],
        "original_role": c["role"],
        "workflow_group": c["workflow"],
        "session_group": "session_group-"
        + str(101 + (phase == "main") * 4 + (c["role"] == "DEVELOPMENT") * 2 + (env == "juice")),
        "campaign_group": "campaign_group-"
        + str(101 + (phase == "main") * 4 + (c["role"] == "DEVELOPMENT") * 2 + (env == "juice")),
        "intent": intent,
        "planned_intent": c["planned_intent"],
        "outcome": outcome,
        "family": c["family"],
        "oracle_verified": matched,
        "oracle_checks": proof,
        "evidence_levels": ["APPLICATION_ORACLE_VERIFIED", "REVIEW_PENDING"]
        if matched
        else ["REVIEW_PENDING", "INSUFFICIENT_EVIDENCE"],
        "oracle_replay": "CLIENT_RECEIPT_PLUS_TRANSIENT_APPLICATION_STATE_WITNESS",
        "review_status": "PENDING",
        "independent_human_verified": False,
        "method": c["method"],
        "endpoint_template": re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(path).path),
        "inclusion_exclusion_reasons": []
        if matched
        else ["UNKNOWN_INTENT_NO_ORACLE_LABEL", "OUTCOME_ORACLE_UNVERIFIED"],
        "prior_exposure": "PRECOMMITTED_CONTROL_AFTER_ORACLE_PREFLIGHT",
        "HTTP_status": status,
        "HTTP_transaction_identity": "COLLECTOR_REQUEST_ID_SENT_NO_INDEPENDENT_PACKET_CAPTURE",
        "latency_ms": (time.monotonic() - start) * 1000,
        "body_state": body.state_of(b),
        "body_available": raw is not None,
        "body_contract_sha256": body.CONTRACT_SHA256,
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "feature_compatibility": {
            "request_v3": True,
            "frozen_runtime_prefix": True,
            "GLU207": False,
        },
        "transient_checksums": {
            "raw": keys["raw"],
            "template": keys["template"],
            "full_view": vector_hash(full),
        },
    }
    return row, f, x, full, b


def launch(q, d, env):
    pm = q.pm
    pm("network", "create", "--internal", "--label", q.LABEL, d.NET)
    common = [
        "--label",
        q.LABEL,
        "--network",
        d.NET,
        "--cpus=.25",
        "--pids-limit=256",
        "--security-opt=no-new-privileges",
        "--log-driver=none",
    ]
    if env == "dvwa":
        pm(
            "run",
            "-d",
            "--name",
            d.DB,
            *common,
            "--network-alias",
            "db",
            "--memory=1g",
            "--memory-swap=1g",
            "-e",
            "MYSQL_ROOT_PASSWORD=dvwa",
            "-e",
            "MYSQL_DATABASE=dvwa",
            "-e",
            "MYSQL_USER=dvwa",
            "-e",
            "MYSQL_PASSWORD=p@ssw0rd",
            d.DB_IMAGE,
        )
        image = d.APP_IMAGE
        port = "80"
        # Lab network namespace only: www-data GID33 may open ICMP datagram sockets.
        # No CAP_NET_RAW, root application, profile relaxation or host sysctl change.
        extra = ["-e", "DB_SERVER=db", "--sysctl", "net.ipv4.ping_group_range=33 33"]
    else:
        image = q.JUICE
        port = "3000"
        extra = []
    pm(
        "run",
        "-d",
        "--name",
        d.APP,
        *common,
        "--memory=2g",
        "--memory-swap=2g",
        "-p",
        f"127.0.0.1:{PORT}:{port}",
        *extra,
        image,
    )
    info = json.loads(pm("inspect", d.APP))[0]
    net = json.loads(pm("network", "inspect", d.NET))[0]
    assert net["internal"] and info["NetworkSettings"]["Ports"][port + "/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": str(PORT)}
    ]

    if env == "dvwa":
        effective = pm(
            "exec",
            "--user",
            "33:33",
            d.APP,
            "sh",
            "-c",
            "cat /proc/sys/net/ipv4/ping_group_range; readlink /proc/self/ns/net; grep -E '^(CapEff|NoNewPrivs|Seccomp):' /proc/self/status",
        ).splitlines()
        assert effective[0].split() == ["33", "33"]
        assert (
            "CapEff:\t0000000000000000" in effective
            and "NoNewPrivs:\t1" in effective
            and "Seccomp:\t2" in effective
        )
        if DISPATCH_ROOT is not None:
            n = len(list(DISPATCH_ROOT.glob("namespace-configuration-*.json")))
            atomic_json(
                DISPATCH_ROOT / f"namespace-configuration-{n:02}.json",
                {
                    "environment": env,
                    "effective_namespace_metadata": effective,
                    "privileged": info["HostConfig"]["Privileged"],
                    "cap_add": info["HostConfig"]["CapAdd"],
                    "environment_fingerprint": load(DISPATCH_ROOT / "plan.json").get(
                        "environment_fingerprint"
                    ),
                    "host_sysctl_changed": False,
                },
            )


def cleanup(q, d):
    for name in [d.APP, d.DB]:
        result = subprocess.run(["podman", "inspect", name], capture_output=True)
        if result.returncode == 0:
            info = json.loads(result.stdout)[0]
            assert info["Config"]["Labels"].get("idps.research-run") == RUN
            removed = subprocess.run(["podman", "rm", "-f", "-v", name], capture_output=True)
            absent = (
                subprocess.run(
                    ["podman", "container", "exists", name], capture_output=True
                ).returncode
                == 1
            )
            CLEANUP_EVENTS.append(
                {
                    "operation": "remove_owned_container",
                    "returncode": removed.returncode,
                    "verified_absent": absent,
                }
            )
            if not absent:
                raise RuntimeError("Owned container cleanup not verified")
    result = subprocess.run(["podman", "network", "inspect", d.NET], capture_output=True)
    if result.returncode == 0:
        info = json.loads(result.stdout)[0]
        assert info.get("labels", {}).get("idps.research-run") == RUN
        removed = subprocess.run(["podman", "network", "rm", d.NET], capture_output=True)
        absent = (
            subprocess.run(["podman", "network", "exists", d.NET], capture_output=True).returncode
            == 1
        )
        CLEANUP_EVENTS.append(
            {
                "operation": "remove_owned_network",
                "returncode": removed.returncode,
                "verified_absent": absent,
            }
        )
        if not absent:
            raise RuntimeError("Owned network cleanup not verified")


def capture(root):
    global DISPATCH_ROOT
    DISPATCH_ROOT = root
    plan = load(root / "plan.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert plan["source_sha256"] == file_sha256(__file__) and not any(plan["preaudit"].values())
    assert plan["run_id"] == RUN
    for name, sha in plan["helper_sha256"].items():
        assert file_sha256(Path(__file__).with_name(name + ".py")) == sha
    assert not (root / "capture-status.json").exists()
    q, d = configured_helpers()
    assert not q.owned()
    (root / "heartbeat").touch()
    done = threading.Event()

    def beat():
        while not done.wait(0.2):
            (root / "heartbeat").touch()

    t = threading.Thread(target=beat, daemon=True)
    t.start()
    unit = "idps-" + RUN + "-watchdog.service"
    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--quiet",
            "--unit",
            unit,
            "--service-type=exec",
            "-p",
            "CPUQuota=10%",
            "-p",
            "MemoryMax=256M",
            "--setenv=OPENBLAS_NUM_THREADS=1",
            "--setenv=OMP_NUM_THREADS=1",
            "-p",
            "RuntimeMaxSec=900",
            sys.executable,
            str(Path(__file__).resolve()),
            "watchdog",
            "--execution-id",
            RUN,
            "--output",
            str(root),
        ],
        check=True,
        capture_output=True,
    )
    deadline = time.monotonic() + 10
    while not (root / "watchdog-ready").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (root / "watchdog-ready").exists()
    rows = []
    runtime = []
    joint = []
    full = []
    syntax = []
    setup = [0]
    count = 0
    phase_results = {}
    completed = False
    try:
        for phase in ["preflight", "main"]:
            selected = (
                cases()
                if phase == "main"
                else [c for c in cases() if c["case_id"] in plan["preflight_case_ids"]]
            )
            groups = []
            for c in selected:
                key = (c["environment"], c["role"] if phase == "main" else "PREFLIGHT_ONLY")
                if key not in groups:
                    groups.append(key)
            receipts = []
            for env, role in groups:
                launch(q, d, env)
                try:
                    if env == "dvwa":
                        ss = RAMSession()
                        d.initialize(ss)
                        setup[0] += ss.setup_requests
                    else:
                        for _ in range(60):
                            setup[0] += 1
                            try:
                                status, _, page, _ = http(
                                    PORT, "GET", "/api/Products/", None, {"User-Agent": UA}
                                )
                                if status == 200 and json.loads(page).get("data"):
                                    break
                            except (OSError, ValueError):
                                pass
                            time.sleep(0.5)
                        else:
                            raise RuntimeError("Juice readiness failed")
                    sessions = {}
                    for c in [
                        c
                        for c in selected
                        if c["environment"] == env
                        and (role == "PREFLIGHT_ONLY" or c["role"] == role)
                    ]:
                        assert (
                            count < 24
                            and setup[0] < 120
                            and not (root / "lab-watchdog-result.json").exists()
                        )
                        if c["role"] not in sessions:
                            sessions[c["role"]] = open_fixture_session(env, q, d, c["role"], setup)
                        row, f, x, v, b = run_case(c, sessions[c["role"]], q, d, setup, phase)
                        row.update(
                            execution_id=RUN,
                            environment_fingerprint=plan.get("environment_fingerprint"),
                            oracle_contract_version="locked-final-controls-v1",
                            observation_status="ORACLE_VERIFIED"
                            if row["oracle_verified"]
                            else "ORACLE_UNVERIFIED",
                        )
                        count += 1
                        if c["operation"] == "basket-read":
                            assert row["oracle_verified"]
                            for prev in receipts:
                                if prev["case_id"] == "control-03":
                                    prev["oracle_checks"][
                                        "authenticated_basket_readback_confirmed"
                                    ] = True
                            if phase == "main":
                                for prev in rows:
                                    if prev["case_id"] == "control-03":
                                        prev["oracle_checks"][
                                            "authenticated_basket_readback_confirmed"
                                        ] = True
                        if phase == "main":
                            rows.append(row)
                            runtime.append(f)
                            joint.append(x)
                            full.append(v)
                            syntax.append(b)
                        receipts.append(
                            {k: v for k, v in row.items() if k != "transient_checksums"}
                        )
                        atomic_json(root / (phase + "-oracle-receipts.json"), receipts)
                        assert row["oracle_verified"], (
                            "Essential application Oracle did not confirm"
                        )
                finally:
                    cleanup(q, d)
            phase_results[phase] = {
                "receipts": len(receipts),
                "Oracle_verified": sum(r["oracle_verified"] for r in receipts),
                "status": "PASS",
            }
            atomic_json(root / (phase + "-oracle-receipts.json"), receipts)
        # Compare equality and near relations in RAM; emit only ordinal keys and safe edges.
        old, original, old_full, base = parent_inputs()
        m = module("materialize-request-v3")
        combined = []
        xx = []
        ff = []
        vv = []
        bb = []
        for r in old:
            a = dict(
                r,
                split=r["original_role"],
                checksums={
                    k: original[r["sample_id"]]["checksums"][k]
                    for k in ["raw", "template", "full_view"]
                },
            )
            combined.append(a)
            x, f, b = base[r["sample_id"]]
            xx.append(x)
            ff.append(f)
            vv.append(old_full[r["sample_id"]])
            bb.append(b)
        for i, r in enumerate(rows):
            combined.append(dict(r, checksums=r["transient_checksums"]))
            xx.append(joint[i])
            ff.append(runtime[i])
            vv.append(full[i])
            bb.append(syntax[i])
        xx = np.stack(xx)
        ff = np.stack(ff)
        vv = np.stack(vv)
        bb = np.array(bb, np.uint8)
        near_full = m.near_pairs(combined, vv, xx[:, 588:], use_body=False)
        edges = [
            (a, b)
            for a, b in near_full
            if combined[a]["split"] != combined[b]["split"] and b >= len(old)
        ]
        for a, b in edges:
            for i in [a, b]:
                combined[i]["inclusion_exclusion_reasons"].append("CROSS_ROLE_NEAR_FULL")
        aliases = {k: {} for k in ["raw", "template", "full_view"]}
        for r in combined:
            for kind, mapping in aliases.items():
                value = r["checksums"][kind]
                if value not in mapping:
                    mapping[value] = kind + "-equivalence-" + str(len(mapping) + 1)
                r["checksums"][kind] = mapping[value]
            r.pop("transient_checksums", None)
            # Original pointers remain in the parent, not duplicated into a new sensitive schema.
            for key in [
                "frozen_request_feature_reference",
                "body_syntax_vector",
                "dataset_fingerprint",
                "availability",
                "parent_record_index",
                "parent_exclusion_reasons",
            ]:
                r.pop(key, None)
        (root / "safe-audit-records.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in combined)
        )
        np.savez(
            root / "safe-feature-receipts.npz",
            x=xx,
            frozen_runtime=ff,
            body_syntax=bb,
            ids=np.array([r["sample_id"] for r in combined]),
        )
        atomic_json(
            root / "full-near-relation-witness.json",
            {
                "source": "Computed in transient RAM from actual transmitted bodies/headers and pinned inherited full views",
                "cross_role_new_edges": [
                    [combined[a]["sample_id"], combined[b]["sample_id"]] for a, b in edges
                ],
                "no_new_full_body_tensors_or_secret_digests_saved": True,
            },
        )
        completed = True
    finally:
        cleanup(q, d)
        (root / "watchdog-done").touch()
        done.set()
        t.join(timeout=1)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)
        atomic_json(
            root / "capture-status.json",
            {
                "status": "COMPLETED" if completed else "FAILED",
                "targeted_receipts": count,
                "durably_recorded_dispatches": len(DISPATCHES),
                "global_dispatch_upper_bound": len(DISPATCHES) + 1,
                "cleanup_events": CLEANUP_EVENTS,
                "setup_HTTP_calls": setup[0],
                "phases": phase_results,
                "source_sha256": file_sha256(__file__),
                "plan_fingerprint": plan["fingerprint"],
                "ownership_watchdog_unit": unit,
                "owned_containers_remaining": len(q.owned()),
                "raw_HTTP_evidence_saved": False,
                "model_scores_computed": 0,
                "actual_cohort_training_updates": 0,
            },
        )
    print(json.dumps(load(root / "capture-status.json"), indent=2))


def watch(root):
    q, _ = configured_helpers()
    a = module("attack-intent-capture")
    a.RUN = RUN
    a.watchdog(root, q)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["plan", "capture", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--execution-id",
        help="Fresh physical execution identity; never changes logical cases/roles",
    )
    a = p.parse_args()
    os.umask(0o077)
    if a.execution_id:
        if not re.fullmatch(r"request-v3-[a-z0-9-]{1,64}", a.execution_id):
            p.error("Invalid execution ID")
        RUN = a.execution_id
    try:
        with threadpool_limits(limits=1):
            {"plan": prepare, "capture": capture, "watchdog": watch}[a.action](a.output.resolve())
    except Exception as exc:
        print(
            json.dumps({"status": "FAILED", "type": type(exc).__name__, "details": "SUPPRESSED"}),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
