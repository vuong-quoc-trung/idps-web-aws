#!/usr/bin/env python3
"""Bounded Juice Shop lab factory: precommitted cases, proxy receipts, state oracle."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from idps_ai.common import (
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.training.resources import resource_envelope

CONTAINER = "ai-idps-juice-factory-20261104"
NETWORK = "ai-idps-gt-factory-20261104"
IMAGE = "sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f"
APP_PORT = 13081
PROXY_PORT = 13082
CHALLENGE = "Login Admin"
HARD_NEGATIVES = ("O'Connor", "C++", "rock & roll", "2+2")
SEARCH_ATTACKS = (
    ("xss", "<script>alert(1)</script>"),
    ("traversal", "../../etc/passwd"),
    ("command", ";id"),
)
LOGIN_PROFILES = {
    "invalid_login_v1": ("nobody+pilot@example.invalid", "wrong-for-lab"),
    "login_admin_sqli_v1": ("' or 1=1--", "wrong-for-lab"),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _podman(*args):
    return subprocess.check_output(["podman", *args], text=True, timeout=15).strip()


def _identity():
    info = json.loads(_podman("inspect", CONTAINER))[0]
    network = json.loads(_podman("network", "inspect", NETWORK))[0]
    if (
        info["State"]["Status"] != "running"
        or NETWORK not in info["NetworkSettings"]["Networks"]
        or not network["internal"]
        or info["NetworkSettings"]["Ports"]["3000/tcp"]
        != [{"HostIp": "127.0.0.1", "HostPort": str(APP_PORT)}]
        or IMAGE
        not in _podman("image", "inspect", info["Image"], "--format", "{{json .RepoDigests}}")
    ):
        raise PipelineError("Lab target is not the pinned internal loopback Juice Shop")
    return {
        "container_id": info["Id"],
        "image_id": info["Image"],
        "internal_network": NETWORK,
        "host": "127.0.0.1",
        "app_port": APP_PORT,
    }


def _call(port, method, path, body=b"", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise PipelineError("Oversized lab response")
        return response.status, dict(response.getheaders()), data
    finally:
        connection.close()


def _json(data):
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None


def _challenge_snapshot():
    status, _, body = _call(APP_PORT, "GET", "/api/Challenges/")
    parsed = _json(body)
    if status != 200 or not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list):
        raise PipelineError("Juice Shop challenge Oracle unavailable")
    match = [item for item in parsed["data"] if item.get("name") == CHALLENGE]
    if len(match) != 1 or not isinstance(match[0].get("solved"), bool):
        raise PipelineError("Pinned challenge state missing")
    return {
        "challenge": CHALLENGE,
        "id": match[0]["id"],
        "solved": match[0]["solved"],
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "observed_at": _now(),
    }


def _body(profile):
    return json.dumps(
        dict(zip(("email", "password"), LOGIN_PROFILES[profile], strict=True)),
        separators=(",", ":"),
    ).encode()


def _case(case_id, campaign, family, intent, method, path, oracle, expected=None, profile=None):
    body = _body(profile) if profile else b""
    return {
        "case_id": case_id,
        "campaign_id": campaign,
        "scenario_family": family,
        "intended_class": intent,
        "request_id": hashlib.sha256(("juice-factory-v1:" + case_id).encode()).hexdigest()[:32],
        "method": method,
        "path": path,
        "body_profile": profile,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "oracle": oracle,
        "expected": expected,
    }


def _cases(products):
    cases = []
    for product in products[:12]:
        pid, name = int(product["id"]), str(product["name"])
        cases.append(
            _case(
                f"browse-{pid}",
                "browse-products",
                "product_browse",
                "benign",
                "GET",
                f"/api/Products/{pid}",
                "product_identity",
                {"id": pid, "name": name},
            )
        )
    terms = []
    for product in products:
        word = str(product["name"]).split()[0]
        if word.isalpha() and word.lower() not in {x.lower() for x in terms}:
            terms.append(word)
        if len(terms) == 12:
            break
    if len(terms) < 12:
        raise PipelineError("Not enough distinct catalog terms")
    for index, term in enumerate(terms):
        cases.append(
            _case(
                f"search-{index}",
                "search-products",
                "product_search",
                "benign",
                "GET",
                "/rest/products/search?q=" + quote(term, safe=""),
                "search_product_name",
                term.lower(),
            )
        )
    for index, term in enumerate(HARD_NEGATIVES):
        cases.append(
            _case(
                f"hardneg-{index}",
                "hardneg-search",
                "benign_special_query",
                "benign",
                "GET",
                "/rest/products/search?q=" + quote(term, safe=""),
                "valid_search_schema",
                None,
            )
        )
    cases.append(
        _case(
            "invalid-login",
            "auth-denial",
            "benign_auth_failure",
            "benign",
            "POST",
            "/rest/user/login",
            "invalid_login_denied",
            None,
            "invalid_login_v1",
        )
    )
    for family, payload in SEARCH_ATTACKS:
        cases.append(
            _case(
                f"attack-{family}",
                "attack-" + family,
                family,
                "attack",
                "GET",
                "/rest/products/search?q=" + quote(payload, safe=""),
                "request_receipt_only",
            )
        )
    cases.append(
        _case(
            "attack-login-sqli",
            "attack-login-sqli",
            "sqli_auth_bypass",
            "attack",
            "POST",
            "/rest/user/login",
            "login_admin_challenge_transition",
            None,
            "login_admin_sqli_v1",
        )
    )
    return cases


def prepare(output):
    output = Path(output)
    if output.exists():
        raise PipelineError("Factory plan exists")
    identity = _identity()
    initial = _challenge_snapshot()
    if initial["solved"]:
        raise PipelineError("Login Admin challenge already solved before plan")
    status, _, body = _call(APP_PORT, "GET", "/api/Products/")
    catalog = _json(body)
    if status != 200 or not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise PipelineError("Product catalog Oracle unavailable")
    cases = _cases(catalog["data"])
    if len(cases) > 40 or len({c["request_id"] for c in cases}) != len(cases):
        raise PipelineError("Unbounded or duplicate factory cases")
    plan = {
        "format_version": 1,
        "scope": "single_juice_shop_development_lab_only",
        "created_at": _now(),
        "target": identity,
        "image_digest": IMAGE,
        "script_sha256": file_sha256(__file__),
        "catalog_response_sha256": hashlib.sha256(body).hexdigest(),
        "initial_challenge": initial,
        "cases": cases,
        "max_requests": 40,
        "partition": "development_only_no_model_evaluation",
        "label_rules": {
            "benign": "proxy receipt plus expected product identity/name, valid JSON search schema, or explicit invalid-login denial",
            "attack_attempt": "precommitted scenario plus matching proxy receipt and target HTTP response; never equate to exploit success",
            "exploit_success": "Login Admin challenge false before and true after login SQLi case, with returned admin identity; other cases unknown",
            "unknown": "missing/mismatched proxy, response or application Oracle",
        },
    }
    plan["plan_sha256"] = digest(plan)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, plan)
    output.chmod(0o600)
    return plan


class _Proxy(BaseHTTPRequestHandler):
    receipts = []
    lock = threading.Lock()

    def _relay(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096 or not self.path.startswith("/") or "X-Request-Id" not in self.headers:
            self.send_error(400)
            return
        body = self.rfile.read(length)
        started = _now()
        status, headers, result = _call(
            APP_PORT,
            self.command,
            self.path,
            body,
            {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "X-Request-Id": self.headers["X-Request-Id"],
            },
        )
        self.send_response(status)
        self.send_header("Content-Type", headers.get("Content-Type", "application/octet-stream"))
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)
        with self.lock:
            self.receipts.append(
                {
                    "request_id": self.headers["X-Request-Id"],
                    "method": self.command,
                    "path_sha256": hashlib.sha256(self.path.encode()).hexdigest(),
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "response_sha256": hashlib.sha256(result).hexdigest(),
                    "status": status,
                    "started_at": started,
                    "ended_at": _now(),
                }
            )

    do_GET = _relay
    do_POST = _relay

    def log_message(self, *_args):
        pass


def run(plan_path, output):
    plan_path, output = Path(plan_path), Path(output)
    if output.exists():
        raise PipelineError("Factory run output exists")
    plan = load_json(plan_path)
    if (
        plan.get("plan_sha256") != digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        or plan["script_sha256"] != file_sha256(__file__)
        or plan["target"] != _identity()
    ):
        raise PipelineError("Factory frozen plan/code/target mismatch")
    if (
        len(plan["cases"]) > plan["max_requests"]
        or plan["cases"][-1]["case_id"] != "attack-login-sqli"
    ):
        raise PipelineError("Factory case order or budget changed")
    initial = _challenge_snapshot()
    if initial["id"] != plan["initial_challenge"]["id"] or initial["solved"]:
        raise PipelineError("Factory initial application state changed")
    output.mkdir(parents=True, mode=0o700)
    _Proxy.receipts = []
    server = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), _Proxy)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    observations = []
    try:
        for case in plan["cases"]:
            body = _body(case["body_profile"]) if case["body_profile"] else b""
            if hashlib.sha256(body).hexdigest() != case["body_sha256"]:
                raise PipelineError("Factory body changed after plan")
            status, _, response = _call(
                PROXY_PORT,
                case["method"],
                case["path"],
                body,
                {
                    "X-Request-Id": case["request_id"],
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            parsed = _json(response)
            product_ok = False
            if case["oracle"] == "product_identity":
                item = parsed.get("data") if isinstance(parsed, dict) else None
                product_ok = (
                    status == 200
                    and isinstance(item, dict)
                    and item.get("id") == case["expected"]["id"]
                    and item.get("name") == case["expected"]["name"]
                )
            elif case["oracle"] == "search_product_name":
                items = parsed.get("data") if isinstance(parsed, dict) else None
                product_ok = (
                    status == 200
                    and isinstance(items, list)
                    and any(case["expected"] in str(x.get("name", "")).lower() for x in items)
                )
            elif case["oracle"] == "valid_search_schema":
                product_ok = (
                    status == 200
                    and isinstance(parsed, dict)
                    and parsed.get("status") == "success"
                    and isinstance(parsed.get("data"), list)
                )
            elif case["oracle"] == "invalid_login_denied":
                product_ok = status == 401 and response == b"Invalid email or password."
            auth = parsed.get("authentication") if isinstance(parsed, dict) else None
            admin_identity = bool(
                isinstance(auth, dict)
                and auth.get("umail") == "admin@juice-sh.op"
                and auth.get("token")
            )
            observations.append(
                {
                    "case_id": case["case_id"],
                    "campaign_id": case["campaign_id"],
                    "request_id": case["request_id"],
                    "method": case["method"],
                    "path": case["path"],
                    "body_sha256": case["body_sha256"],
                    "status": status,
                    "response_sha256": hashlib.sha256(response).hexdigest(),
                    "response_bytes": len(response),
                    "oracle_rule": case["oracle"],
                    "application_semantic_ok": bool(product_ok),
                    "admin_identity_returned": admin_identity,
                    "intended_class": case["intended_class"],
                    "family": case["scenario_family"],
                }
            )
        final = _challenge_snapshot()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    receipts = list(_Proxy.receipts)
    by_id = {x["request_id"]: x for x in receipts}
    if len(receipts) != len(observations) or len(by_id) != len(receipts):
        raise PipelineError("Factory proxy receipt count mismatch")
    for case, observation in zip(plan["cases"], observations, strict=True):
        receipt = by_id.get(case["request_id"])
        if not receipt or any(
            (
                receipt["method"] != case["method"],
                receipt["path_sha256"] != hashlib.sha256(case["path"].encode()).hexdigest(),
                receipt["body_sha256"] != case["body_sha256"],
                receipt["response_sha256"] != observation["response_sha256"],
                receipt["status"] != observation["status"],
            )
        ):
            observation["ground_truth_tier"] = "UNKNOWN"
            continue
        if case["intended_class"] == "benign":
            observation["ground_truth_tier"] = (
                "BENIGN_WORKFLOW_VERIFIED" if observation["application_semantic_ok"] else "UNKNOWN"
            )
        else:
            observation["ground_truth_tier"] = "ATTACK_ATTEMPT_VERIFIED"
        observation["exploit_success_verified"] = bool(
            case["oracle"] == "login_admin_challenge_transition"
            and not initial["solved"]
            and final["solved"]
            and final["id"] == initial["id"]
            and observation["admin_identity_returned"]
            and observation["ground_truth_tier"] == "ATTACK_ATTEMPT_VERIFIED"
        )
    report = {
        "format_version": 1,
        "scope": "one isolated Juice Shop application, collector-controlled development only",
        "plan_file_sha256": file_sha256(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "script_sha256": file_sha256(__file__),
        "target": plan["target"],
        "requests_sent": len(observations),
        "unique_http_representations": len(
            {
                hashlib.sha256(canonical_bytes([o["method"], o["path"], o["body_sha256"]])).digest()
                for o in observations
            }
        ),
        "before_challenge": initial,
        "after_challenge": final,
        "benign_verified": sum(
            x["ground_truth_tier"] == "BENIGN_WORKFLOW_VERIFIED" for x in observations
        ),
        "attack_attempt_verified": sum(
            x["ground_truth_tier"] == "ATTACK_ATTEMPT_VERIFIED" for x in observations
        ),
        "exploit_success_verified": sum(
            x.get("exploit_success_verified", False) for x in observations
        ),
        "unknown": sum(x["ground_truth_tier"] == "UNKNOWN" for x in observations),
        "proxy_correlated": len(receipts),
        "student_nginx_suricata_correlated": 0,
        "formal_admitted": 0,
        "model_evaluation": "NOT_RUN_until_corpus_quality_and_partition_gate",
        "observations": observations,
        "proxy_receipts": receipts,
        "limits": "Proxy is AI-owned gateway receipt, not Juice Shop application request-ID log; challenge state is app-side. Single app/instance and collector-controlled intent do not establish independent generalization or formal admission. No raw auth token/password persisted.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    with resource_envelope(4, 8):
        result = prepare(args.plan) if args.action == "prepare" else run(args.plan, args.output)
    print(
        {
            k: result[k]
            for k in (
                "plan_sha256",
                "requests_sent",
                "benign_verified",
                "attack_attempt_verified",
                "exploit_success_verified",
                "unknown",
            )
            if k in result
        }
    )
