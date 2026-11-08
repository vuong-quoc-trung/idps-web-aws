#!/usr/bin/env python3
"""One duplicate-create diagnostic and one owned-basket GET in a disposable lab.

No application/seed repair, no cohort capture, no raw HTTP/session values or direct
secret digests persisted. SQL witnesses open the lab SQLite database read-only.
"""

import argparse
import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from idps_ai.common import atomic_json, digest, file_sha256

ROOT = Path(__file__).resolve().parents[2]
RUN = "request-v3-basket-diagnostic-20261108-r1"


def collector():
    p = Path(__file__).with_name("request-v3-final-controls.py")
    s = importlib.util.spec_from_file_location("basket_collector", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    m.RUN = RUN
    return m


def safe_error(blob):
    """Allowlist categories/locations only; never emit SQL, message, stack or values."""
    result = {"exception_class": "UNKNOWN", "database_category": "UNKNOWN", "stack_locations": []}
    try:
        data = json.loads(blob)
        error = data.get("error", data)
        if not isinstance(error, dict):
            return result
        allowed = {
            "SequelizeUniqueConstraintError",
            "SequelizeForeignKeyConstraintError",
            "SequelizeValidationError",
            "SequelizeDatabaseError",
            "TypeError",
            "Error",
            "UnauthorizedError",
        }
        name = error.get("name")
        stack = error.get("stack", "")
        if name in allowed:
            result["exception_class"] = name
        elif isinstance(stack, str) and stack.split(":", 1)[0] in allowed:
            result["exception_class"] = stack.split(":", 1)[0]
        for parent in [error, error.get("parent", {}), error.get("original", {})]:
            if isinstance(parent, dict) and parent.get("code") in {
                "SQLITE_CONSTRAINT",
                "SQLITE_CONSTRAINT_UNIQUE",
                "SQLITE_CONSTRAINT_FOREIGNKEY",
                "SQLITE_BUSY",
                "SQLITE_ERROR",
            }:
                result["database_category"] = parent["code"]
        if (
            result["exception_class"] == "SequelizeUniqueConstraintError"
            and result["database_category"] == "UNKNOWN"
        ):
            result["database_category"] = "UNIQUE_CONSTRAINT_MAPPED_BY_SEQUELIZE"
        if isinstance(stack, str):
            for filename, line, column in re.findall(
                r"(basketItems\.js|query\.js|model\.js|query-interface\.js):(\d+):(\d+)", stack
            ):
                value = {"file": filename, "line": int(line), "column": int(column)}
                if value not in result["stack_locations"]:
                    result["stack_locations"].append(value)
        result["unique_basket_product_fields"] = sorted(
            {
                f
                for item in error.get("errors", [])
                if isinstance(item, dict)
                for f in [item.get("path")]
                if f in {"BasketId", "ProductId"}
            }
        )
    except (ValueError, TypeError, AttributeError):
        pass
    return result


def db_state(name, bid, uid):
    code = r"""let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',async()=>{const v=JSON.parse(s),sql=require('sqlite3');const db=new sql.Database('data/juiceshop.sqlite',sql.OPEN_READONLY);const all=(q,p=[])=>new Promise((resolve,reject)=>db.all(q,p,(e,r)=>e?reject(e):resolve(r)));try{let u=await all('SELECT id FROM Users WHERE id=? AND deletedAt IS NULL',[v.uid]);let b=await all('SELECT UserId FROM Baskets WHERE id=?',[v.bid]);let product=await all('SELECT id FROM Products WHERE id=1 AND deletedAt IS NULL');let q=await all('SELECT quantity,limitPerUser FROM Quantities WHERE ProductId=1');let items=await all('SELECT quantity FROM BasketItems WHERE BasketId=? AND ProductId=1',[v.bid]);let total=await all('SELECT count(*) AS n FROM BasketItems WHERE BasketId=?',[v.bid]);let indexes=await all('PRAGMA index_list(BasketItems)');let safe=[];for(let i of indexes){if(!/^[A-Za-z0-9_]+$/.test(i.name))throw Error('index identifier');let cols=await all('PRAGMA index_info('+i.name+')');safe.push({unique:!!i.unique,columns:cols.map(x=>x.name).filter(x=>['BasketId','ProductId','id'].includes(x))});}let fk=await all('PRAGMA foreign_key_list(BasketItems)');let configured=await all('PRAGMA foreign_keys');const fs=require('fs');const listener=['/proc/net/tcp','/proc/net/tcp6'].some(p=>fs.readFileSync(p,'utf8').split('\n').slice(1).some(l=>{const x=l.trim().split(/\s+/);return x[1]?.endsWith(':0BB8')&&x[3]==='0A';}));console.log(JSON.stringify({readonly:true,app_listener3000_in_namespace:listener,user_exists:u.length===1,basket_exists:b.length===1,basket_owned_by_authenticated_user:b.length===1&&b[0].UserId===v.uid,product_exists:product.length===1,quantity_record_exists:q.length===1,stock_at_least_requested:q.length===1&&q[0].quantity>=1,limit_allows_requested:q.length===1&&(!q[0].limitPerUser||q[0].limitPerUser>=1),existing_pair_rows:items.length,existing_pair_quantities:items.map(x=>x.quantity),owned_basket_total_items:total[0].n,indexes:safe,foreign_keys:fk.map(x=>({table:x.table,from:x.from,to:x.to})),foreign_keys_enabled_on_readonly_connection:configured[0].foreign_keys===1}));}catch(e){console.log(JSON.stringify({readonly:true,error_class:'READ_ONLY_STATE_QUERY_FAILED'}));process.exitCode=1;}finally{db.close();}});"""
    p = subprocess.run(
        ["podman", "exec", "-i", name, "/nodejs/bin/node", "-e", code],
        input=json.dumps({"bid": bid, "uid": uid}).encode(),
        capture_output=True,
        timeout=15,
        check=True,
    )
    return json.loads(p.stdout)


def classify(status, error, before, after):
    prereq = all(
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
    unique = any(
        i["unique"] and set(i["columns"]) == {"BasketId", "ProductId"}
        for i in before.get("indexes", [])
    )
    unchanged = before.get("existing_pair_quantities") == after.get(
        "existing_pair_quantities"
    ) and before.get("owned_basket_total_items") == after.get("owned_basket_total_items")
    verified = (
        status == 500
        and error.get("exception_class") == "SequelizeUniqueConstraintError"
        and prereq
        and unique
        and before.get("existing_pair_rows") == 1
        and unchanged
    )
    return {
        "root_cause": "TEST_FIXTURE_ERROR" if verified else "UNKNOWN",
        "verified": verified,
        "prerequisites_valid": prereq,
        "unique_pair_constraint": unique,
        "state_unchanged": unchanged,
        "application_response_category": "APPLICATION_ERROR_500" if status == 500 else "OTHER",
        "causal_chain": "Fixture requests CREATE of seededexisting BasketId/ProductId pair -> ORM save -> UNIQUE constraint -> unhandled-to-500 response -> Oracle refuses success"
        if verified
        else "NOT_ESTABLISHED",
    }


def run(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    c = collector()
    q, d = c.configured_helpers()
    assert not q.owned()
    source = root / "application-source"
    source.mkdir(mode=0o700)
    records = []
    setup_calls = 0
    complete = False
    (root / "heartbeat").touch()
    stop = threading.Event()

    def beat():
        while not stop.wait(0.2):
            (root / "heartbeat").touch()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
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
            "-p",
            "RuntimeMaxSec=600",
            "--setenv=OPENBLAS_NUM_THREADS=1",
            "--setenv=OMP_NUM_THREADS=1",
            sys.executable,
            str(Path(__file__).resolve()),
            "watchdog",
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
    try:
        c.launch(q, d, "juice")
        # Bind the actual container source, not just an earlier source snapshot.
        for path in [
            "build/server.js",
            "build/routes/basketItems.js",
            "build/routes/login.js",
            "build/routes/basket.js",
            "build/models/relations.js",
            "build/models/basketitem.js",
            "build/models/basket.js",
            "build/models/quantity.js",
            "build/data/datacreator.js",
        ]:
            subprocess.run(
                [
                    "podman",
                    "cp",
                    d.APP + ":/juice-shop/" + path,
                    str(source / path.replace("/", "__")),
                ],
                check=True,
                capture_output=True,
            )
        for _ in range(50):
            try:
                probe = db_state(d.APP, 1, 1)
                if (
                    probe["user_exists"]
                    and probe["product_exists"]
                    and probe["app_listener3000_in_namespace"]
                ):
                    break
            except (subprocess.SubprocessError, ValueError, KeyError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Readonly initialization readiness not verified")
        setup = [0]
        session = c.open_fixture_session("juice", q, d, "TRAIN", setup)
        setup_calls = setup[0]
        token_payload = json.loads(base64.urlsafe_b64decode(session.token.split(".")[1] + "==="))
        uid = token_payload["data"]["id"]
        bid = session.bid
        assert isinstance(uid, int) and isinstance(bid, int)
        before = db_state(d.APP, bid, uid)
        atomic_json(root / "readonly-before.json", before)
        case = next(v for v in c.cases() if v["operation"] == "basket-add")
        body = json.dumps(dict(case["fields"], BasketId=bid)).encode()
        rid = digest([RUN, "locked-duplicate-post"])[:32]
        headers = {
            "User-Agent": c.UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + session.token,
            "X-Request-Id": rid,
        }
        atomic_json(
            root / "diagnostic-dispatches.json",
            [
                {
                    "request_id": rid,
                    "method": "POST",
                    "route": "/api/BasketItems/",
                    "state": "ISSUED_RESPONSE_UNCONFIRMED",
                }
            ],
        )
        status, _, response, _ = c.http(c.PORT, "POST", case["path"], body, headers)
        error = safe_error(response)
        after = db_state(d.APP, bid, uid)
        atomic_json(root / "readonly-after-post.json", after)
        result = classify(status, error, before, after)
        records.append(
            {
                "request_id": rid,
                "execution_id": RUN,
                "session_group": "session_group-0001",
                "method": "POST",
                "route": "/api/BasketItems/",
                "HTTP_status": status,
                "exception": error,
                "state_classification": result,
                "planned_intent": "LEGITIMATE_OWNED_BASKET_CREATE_DIAGNOSTIC",
                "intent": "UNKNOWN_INTENT",
                "outcome": "UNKNOWN_OUTCOME",
                "Oracle_success": False,
                "admission": "DIAGNOSTIC_ONLY_EXCLUDED",
                "review_status": "PENDING",
                "independent_human_verified": False,
            }
        )
        atomic_json(root / "diagnostic-receipts.json", records)
        # Second and final diagnostic: observe owned basket via authenticated GET, no repair.
        getid = digest([RUN, "owned-basket-get"])[:32]
        headers["X-Request-Id"] = getid
        atomic_json(
            root / "diagnostic-dispatches.json",
            [
                {
                    "request_id": rid,
                    "method": "POST",
                    "route": "/api/BasketItems/",
                    "state": "RESPONSE_RECEIVED",
                    "status": status,
                },
                {
                    "request_id": getid,
                    "method": "GET",
                    "route": "/rest/basket/:id",
                    "state": "ISSUED_RESPONSE_UNCONFIRMED",
                },
            ],
        )
        gs, _, response, _ = c.http(c.PORT, "GET", f"/rest/basket/{bid}", None, headers)
        data = json.loads(response).get("data", {})
        products = data.get("Products", [])
        quantities = [p.get("BasketItem", {}).get("quantity") for p in products if p.get("id") == 1]
        match = (
            gs == 200 and data.get("id") == bid and quantities == after["existing_pair_quantities"]
        )
        records.append(
            {
                "request_id": getid,
                "execution_id": RUN,
                "session_group": "session_group-0001",
                "method": "GET",
                "route": "/rest/basket/:id",
                "HTTP_status": gs,
                "authenticated_owned_basket_read_matches_DB": match,
                "preexisting_product_pair_present": len(quantities) == 1,
                "observed_product_quantity": quantities,
                "Oracle_expected_added_quantity1": quantities == [1],
                "outcome": "VERIFIED_READBACK_OF_UNCHANGED_EXISTING_STATE"
                if match
                else "UNKNOWN_OUTCOME",
                "admission": "DIAGNOSTIC_ONLY_EXCLUDED",
                "review_status": "PENDING",
                "independent_human_verified": False,
            }
        )
        atomic_json(root / "diagnostic-receipts.json", records)
        afterget = db_state(d.APP, bid, uid)
        atomic_json(root / "readonly-after-get.json", afterget)
        assert afterget == after and match
        assert len(records) == 2
        complete = True
        atomic_json(
            root / "result.json",
            {
                "case": "CASE_A_ROOT_CAUSE_VERIFIED"
                if result["verified"]
                else "CASE_B_ROOT_CAUSE_PARTIAL",
                "BASKET_ROOT_CAUSE": "VERIFIED" if result["verified"] else "PARTIAL",
                "BASKET_APPLICATION_CONTRACT": "VERIFIED",
                "BASKET_ORACLE": "BLOCKED_FIXTURE_PRECONDITION",
                "BASKET_PREFLIGHT": "NOT_RERUN",
                "MAIN_CAPTURE": "NOT_STARTED",
                "REQUEST_V3_TRAINING": "NOT_STARTED",
                "DATASET_COVERAGE": "UNCHANGED",
                "execution_id": RUN,
                "classification": result,
                "exception": error,
                "status": status,
                "HTTP_diagnostic_transactions": 2,
                "setup_login_HTTP_transactions": setup_calls,
                "read_only_state_before": before,
                "read_only_state_after": after,
                "owned_readback_HTTP_status": gs,
                "root_cause_source_bindings": {p.name: file_sha256(p) for p in source.iterdir()},
                "raw_HTTP_or_session_values_saved": False,
                "new_admissions": 0,
                "new_checkpoints": 0,
                "source_sha256": file_sha256(__file__),
                "Oracle_contract_changed": False,
                "NEXT_ACTION": "Correct only fixture precondition: dedicated authenticated unseeded-owned basket before CREATE; preserve product1 quantity1 and endpoint, bind setup change explicitly before campaign replay. No repair/seed deletion or template change now.",
            },
        )
    finally:
        c.cleanup(q, d)
        (root / "watchdog-done").touch()
        stop.set()
        thread.join(timeout=1)
        deadline = time.monotonic() + 2
        while not (root / "lab-watchdog-result.json").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)
        atomic_json(
            root / "cleanup.json",
            {
                "owned_containers_remaining": len(q.owned()),
                "cleanup_events": c.CLEANUP_EVENTS,
                "completed": complete,
                "HTTP_diagnostics_completed": len(records),
                "setup_HTTP_calls": setup_calls,
            },
        )
    print(
        json.dumps(
            {
                k: load(root / "result.json")[k]
                for k in [
                    "case",
                    "BASKET_ROOT_CAUSE",
                    "BASKET_ORACLE",
                    "BASKET_PREFLIGHT",
                    "MAIN_CAPTURE",
                    "DATASET_COVERAGE",
                ]
            }
        )
    )


def load(p):
    return json.loads(p.read_text())


def watch(root):
    c = collector()
    q, _ = c.configured_helpers()
    a = c.module("attack-intent-capture")
    a.RUN = RUN
    a.watchdog(root, q)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["run", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    try:
        {"run": run, "watchdog": watch}[a.action](a.output.resolve())
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_type": type(exc).__name__, "details": "SUPPRESSED"}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
