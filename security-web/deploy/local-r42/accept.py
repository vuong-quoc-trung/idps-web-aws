#!/usr/bin/env python3
"""Bounded acceptance. Run only in the disposable R42 systemd staging namespace."""

import base64
from contextlib import closing
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.parse import urlencode
from uuid import UUID

STATE = Path("/var/lib/websentinel-beta")
JOURNAL = Path("/var/lib/websentinel-https/observations.jsonl")
KEY = Path("/etc/websentinel-beta/key/key.json")
R37 = "91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff"
R36 = "d4797584ab7eb243725329f08acf160122bf1da27a9fb128850f333fd0ce4bd0"
SENSOR = "websentinel-beta-sensor.service"
SCORER = "websentinel-https-scorer.service"
CLIENT = "192.0.2.10"


def run(*args):
    return subprocess.check_output(args, text=True, timeout=40).strip()


def manage(*args):
    return run(sys.executable, "manage.py", *args)


def sql(query, db="websentinel_security"):
    return run("runuser", "-u", "postgres", "--", "psql", "-XAt", "-v", "ON_ERROR_STOP=1", db, "-c", query)


def wait(check, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError(f"Timed out: {check.__name__}")


def rows(path):
    if not path.is_file():
        return []
    return [line[:-1] for line in path.read_text().splitlines(keepends=True) if line.endswith("\n")]


def source(path, rid, key="request_id"):
    matches = [row for line in rows(path) if (row := json.loads(line)).get(key) == rid]
    if len(matches) > 1:
        raise RuntimeError("Duplicate per-request record")
    return matches[0] if matches else None


def verified_transaction(rid, method, target, status):
    captures = [line.split("\t") for line in rows(STATE / "sensor/chain.tsv")]
    captures = [row for row in captures if len(row) == 9 and row[5] == rid]
    if not captures:
        return None
    assert len(captures) == 1, "Ambiguous sensor record"
    flow, tx, proof, receipt, client, _, scheme, host, generation = captures[0]
    if not receipt:
        return None
    assert client == CLIENT and scheme == "https" and host == "127.0.0.1"
    assert re.fullmatch(r"[a-f0-9]{32}", generation) and 0 <= int(tx) < 2**53
    assert 0 <= int(flow) < 2**64
    current = json.loads(KEY.read_text())

    def verify(wire, domain):
        body, mac = wire.split(".")
        expected = hmac.digest(bytes.fromhex(current["key"]), (domain + body).encode(), "sha256")
        assert hmac.compare_digest(expected, bytes.fromhex(mac)), "Invalid edge HMAC"
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))

    p, v = verify(proof, "ws-request-v1:"), verify(receipt, "ws-receipt-v1:")
    assert p[:3] == [1, current["kid"], current["epoch"]]
    assert re.fullmatch(r"[a-f0-9]{32}", p[3])
    assert p[4:10] == [client, rid, method, scheme, host, hashlib.sha256(target.encode()).hexdigest()]
    assert v[:6] == p[:4] + [hashlib.sha256(proof.encode()).hexdigest(), "accepted"]
    assert p[11] - p[10] == 60_000 and p[10] - 1000 <= v[6] <= p[11]
    assert sum(candidate[2] == proof for candidate in captures) == 1
    # Bind the signed request and response to one observed HTTP transaction.
    # The IP and ports below delimit capture scope. They do not join requests.
    transactions = [
        row for line in rows(STATE / "sensor/eve.json")
        if (row := json.loads(line)).get("event_type") == "http"
        and (row.get("host"), str(row.get("flow_id")), row.get("tx_id")) ==
        ("ws-generation-" + generation, flow, int(tx))
    ]
    if not transactions:
        return None
    assert len(transactions) == 1
    e = transactions[0]
    assert (e["src_ip"], e["dest_ip"], e["dest_port"], e["in_iface"]) == ("127.77.0.1", "127.77.0.2", 18080, "lo")
    assert (e["http"]["http_method"], e["http"]["url"], e["http"]["status"]) == (method, target, status)
    return {"generation": generation, "flow_id": flow, "tx_id": int(tx)}


def run_acceptance(cert, password_file):
    tls = ssl.create_default_context(cafile=str(cert))
    events = []

    def connect():
        return http.client.HTTPSConnection("127.0.0.1", context=tls, source_address=(CLIENT, 0), timeout=10)

    def request(conn, method, target, status, label, headers=None, body=None, *,
                sensor=True, model=R37):
        started = time.monotonic_ns()
        conn.request(method, target, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read(65536)
        response_ms = (time.monotonic_ns() - started) / 1e6
        rid = response.getheader("X-Request-Id") or ""
        assert re.fullmatch(r"[a-f0-9]{32}", rid) and rid not in {e["request_id"] for e in events}
        assert response.status == status, f"{label}: HTTP {response.status}, expected {status}"
        assert response.getheader("X-WS-Receipt") is None
        found, observed = {}, {}
        end = time.monotonic() + 4
        while time.monotonic() < end:
            for name, path in (("N", STATE / "edge/access.jsonl"), ("A", STATE / "student/audit.jsonl"),
                               ("AI", JOURNAL)):
                if name not in found and (row := source(path, rid)):
                    found[name], observed[name] = row, time.time_ns()
            if sensor and "S" not in found and (transaction := verified_transaction(rid, method, target, status)):
                found["S"], observed["S"] = transaction, time.time_ns()
            if {"N", "A", *("S" if sensor else ())} <= found.keys() and (not model or "AI" in found):
                break
            time.sleep(0.025)
        assert found["N"]["status"] == status and found["A"]["status_code"] == status
        assert UUID(found["A"]["event_id"])
        assert not sensor or "S" in found, f"{label}: missing complete sensor transaction"
        assert sensor or verified_transaction(rid, method, target, status) is None

        def database_readback():
            result = json.loads(manage("request", rid))
            normalized = set(sql(f"select source from normalized_events where request_id='{rid}'").splitlines())
            if not {"NGINX", "STUDENT_AUDIT"} <= normalized or "policy" not in result:
                return None
            if model and not result.get("research"):
                return None
            if sensor and sql(f"select count(*) from suricata_lua_shadow where request_id='{rid}' and proof_present and receipt_present and not mismatched") != "1":
                return None
            return result

        decision = wait(database_readback)
        assert decision["request_id"] == rid and decision["automatic_block"] is False
        assert decision["policy"] in {"LOG_ONLY", "ALERT", "REVIEW"}
        cutoff, mask = None, None
        if model:
            scored = found["AI"]
            assert scored["status"] == "SCORED" and decision["research"]["status"] == "SCORED"
            assert scored["model_sha256"] == decision["research"]["model_sha256"] == model
            assert abs(scored["score"] - decision["research"]["score"]) < 1e-9
            assert scored["guard_ns"] == 1_000_000
            assert scored["cutoff_ns"] - scored["dispatch_ns"] == 1_000_000_000
            cutoff = scored["cutoff_ns"]
            assert scored["available_ns"] <= cutoff - scored["guard_ns"]
            mask = "".join(name for name in "NSA" if scored["dispatch_ns"] <= observed.get(name, 0)
                           <= cutoff - scored["guard_ns"]) or "NONE"
        else:
            assert "AI" not in found and decision["research"] is None
        event = dict(request_id=rid, oracle=label, method=method, status=status, http_ms=round(response_ms, 3),
                     model_sha256=model, score=found.get("AI", {}).get("score"),
                     policy=decision["policy"], automatic_block=False, audit_id=found["A"]["event_id"],
                     sensor_transaction=found.get("S"), source_observed_ns=observed, cutoff_ns=cutoff,
                     collector_mask_at_cutoff=mask, policy_scope="POST_OBSERVATION",
                     scorer_status="SCORED" if model else "UNAVAILABLE_NO_SCORE",
                     adjudicated_ns=time.time_ns())
        events.append(event)
        print("R42_REQUEST=" + json.dumps(event, separators=(",", ":")), flush=True)
        return payload, response.getheader("Set-Cookie", "").split(";", 1)[0]

    def brief(label, **kwargs):
        with closing(connect()) as conn:
            return request(conn, "GET", "/api/auth/me", 401, label, **kwargs)

    with closing(connect()) as conn:
        body, cookie = request(conn, "GET", "/api/auth/csrf", 200, "CSRF_ISSUED")
        token = json.loads(body)["token"]
        assert token and cookie.startswith("JSESSIONID=")
        initial_port = conn.sock.getsockname()[1]
        login = urlencode({"username": "admin", "password": Path(password_file).read_text().strip()})
        _, rotated = request(conn, "POST", "/api/auth/login", 204, "LOGIN_SESSION_ROTATED",
                             {"Cookie": cookie, "X-CSRF-TOKEN": token, "Content-Type": "application/x-www-form-urlencoded"}, login)
        assert rotated.startswith("JSESSIONID=") and rotated != cookie
        assert conn.sock.getsockname()[1] == initial_port
        current = {"Cookie": rotated}
        principal, _ = request(conn, "GET", "/api/auth/me", 200, "PRINCIPAL_ADMIN", current)
        assert json.loads(principal)["role"] == "ADMIN" and json.loads(principal)["username"] == "admin"
        body, _ = request(conn, "GET", "/api/auth/csrf", 200, "AUTHENTICATED_CSRF", current)
        request(conn, "POST", "/api/auth/logout", 204, "LOGOUT",
                current | {"X-CSRF-TOKEN": json.loads(body)["token"]})
        request(conn, "GET", "/api/auth/me", 401, "SESSION_REVOKED", current)

    audit = STATE / "student/audit.jsonl"
    audit.rename(audit.with_suffix(".jsonl.1"))
    brief("AUDIT_ROTATION")
    assert audit.stat().st_mode & 0o777 == 0o640
    assert audit.stat().st_gid == audit.parent.stat().st_gid
    run("systemctl", "stop", SENSOR)
    brief("SENSOR_UNAVAILABLE", sensor=False)
    run("systemctl", "start", SENSOR)
    wait(lambda: "Engine started." in run("journalctl", "-b", "-u", SENSOR, "-n", "8", "-o", "cat"))
    time.sleep(2.1)
    brief("SENSOR_RECOVERED")
    assert events[-1]["sensor_transaction"]["generation"] != events[0]["sensor_transaction"]["generation"]
    run("systemctl", "stop", SCORER)
    brief("SCORER_UNAVAILABLE", model=None)
    run("systemctl", "start", SCORER)
    wait(healthy)
    brief("SCORER_RECOVERED")
    manage("restart")
    wait(healthy)
    brief("SYSTEM_RESTART")
    run("systemctl", "restart", "postgresql@18-main.service")
    wait(healthy)
    brief("POSTGRES_RESTART")

    # Protect the existing scorer rate limit. Starts so far occupy the first window.
    active = int(run("systemctl", "show", SCORER, "-p", "ExecMainStartTimestampMonotonic", "--value")) / 1_000_000
    time.sleep(max(0, active + 122 - time.monotonic()))
    manage("model", "rollback")
    brief("ROLLBACK_R36", model=R36)
    manage("model", "candidate")
    brief("RESTORE_R37")
    assert sql("select count(*) from hybrid_proposals") == "0"
    assert sql("select count(*) from https_research_observations where conflicted") == "0"
    print("R42_HTTP_AND_RECOVERY=PASS", flush=True)


def healthy():
    try:
        return manage("health")
    except subprocess.CalledProcessError:
        return False


if __name__ == "__main__":
    os.umask(0o077)
    assert os.readlink("/proc/1/ns/net") != sys.argv[3]
    assert {iface.name for iface in Path("/sys/class/net").iterdir()} == {"lo"}
    run_acceptance(*sys.argv[1:3])
