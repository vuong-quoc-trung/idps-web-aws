#!/usr/bin/env python3
"""Precommit a finite lab campaign; exclude exposed templates before any HTTP.

Reuses the existing bounded collector, not the production detection pipeline.
Artifacts with request/session material are always private and append-only.
"""

import argparse
import ast
import codecs
import hashlib
import importlib.util
import json
import operator
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request

ROOT = Path(__file__).resolve().parents[2]
RUN = "training-unblock-20261107-v1"
LABEL = "idps.research-run=" + RUN
ART = ROOT / "ai-training/.artifacts/training_unblock_20261107"
PORT, PROXY = 16280, 16281
JUICE = "docker.io/bkimminich/juice-shop@sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f"
HEADERS = "User-Agent: Mozilla/5.0 LabResearch\r\nAccept: text/html\r\nContent-Type: application/x-www-form-urlencoded\r\nCookie: withheld\r\nX-Request-Id: withheld"


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cases():
    out = []

    def add(env, role, workflow, family, method, route, fields, oracle, expected, intent="BENIGN"):
        idx = len(out)
        body = (
            (json.dumps(fields) if env == "juice" else urlencode(fields))
            if method == "POST"
            else ""
        )
        path = route + ("?" + urlencode(fields) if method == "GET" and fields else "")
        out.append(
            dict(
                case_id=f"case-{idx:03}",
                request_id=digest([RUN, idx])[:32],
                environment=env,
                role=role,
                workflow=workflow,
                campaign=env + ":" + workflow,
                session_plan=env + ":" + workflow,
                family=family,
                intent=intent,
                method=method,
                path=path,
                body=body,
                oracle=oracle,
                expected=expected,
            )
        )

    # Independent syntax campaigns, not nonce/padding variants. Both labels at relevant surfaces.
    for value in [
        "127.0.0.1 -c 1; { printf 'UNBLOCK_CMD_A'; }",
        "127.0.0.1 -c 1; if true; then printf 'UNBLOCK_CMD_B'; fi",
    ]:
        marker = "UNBLOCK_CMD_A" if "CMD_A" in value else "UNBLOCK_CMD_B"
        add(
            "dvwa",
            "TRAIN",
            "shell-compound-command",
            "cmd_injection",
            "POST",
            "/vulnerabilities/exec/",
            {"ip": value, "Submit": "Submit"},
            "command_stdout_canary",
            marker,
            "ATTACK_ATTEMPT",
        )
    for value in [
        "<video><source onerror=alert(31)></video>",
        "<audio src=x onerror=alert(32)></audio>",
    ]:
        add(
            "dvwa",
            "TRAIN",
            "stored-media-event",
            "xss",
            "POST",
            "/vulnerabilities/xss_s/",
            {"txtName": "LabReader", "mtxMessage": value, "btnSign": "Sign Guestbook"},
            "unsafe_stored_reflection",
            value,
            "ATTACK_ATTEMPT",
        )
    for value in [
        "Legitimate quote: 'a' and 'b'; budget (2+3).",
        "Notes {one: [2,3]} and a/b; please read.",
        "Example code: if (a > b) { return a; }",
        "A normal comparison: x != y && x > 2.",
    ]:
        add(
            "dvwa",
            "TRAIN",
            "stored-technical-notes",
            "benign",
            "POST",
            "/vulnerabilities/xss_s/",
            {"txtName": "LabReader", "mtxMessage": value, "btnSign": "Sign Guestbook"},
            "stored_literal",
            value,
        )
    for value, marker in [
        ("0' UNION SELECT CONCAT('UB','SQLA'),'fixture' #", "UBSQLA"),
        ("0' UNION SELECT UPPER('ubsqlb'),'fixture' #", "UBSQLB"),
    ]:
        add(
            "dvwa",
            "TRAIN",
            "sql-expression-union",
            "sqli",
            "GET",
            "/vulnerabilities/sqli/",
            {"id": value, "Submit": "Submit"},
            "injected_sql_rows",
            marker,
            "ATTACK_ATTEMPT",
        )
    for value in [
        "php://filter/read=string.rot13/resource=/tmp/unblock-canary.txt",
        "php://filter/read=string.toupper/resource=/tmp/unblock-canary.txt",
    ]:
        add(
            "dvwa",
            "TRAIN",
            "file-transform-filter",
            "path_traversal",
            "GET",
            "/vulnerabilities/fi/",
            {"page": value},
            "transformed_canary",
            "rot13" if "rot13" in value else "upper",
            "ATTACK_ATTEMPT",
        )
    for value in ["Hello (reader); use a < b && b > c", "Test array [1,2,3] and map {a:4}"]:
        add(
            "dvwa",
            "TRAIN",
            "reflected-technical-name",
            "benign",
            "GET",
            "/vulnerabilities/xss_r/",
            {"name": value},
            "literal_name_reflection",
            value,
        )
    for value in ["/rest/products/search", "/api/Products/"]:
        add(
            "juice",
            "TRAIN",
            "public-product-collection" if "api/" in value else "product-filter",
            "benign",
            "GET",
            value,
            {} if "api/" in value else {"q": "juice (apple)"},
            "catalog_list" if "api/" in value else "catalog_search",
            "juice (apple)",
        )
    for value in ["')) UNION SELECT * FROM Products WHERE 1=1--", "')) OR (1=1 AND 2>1)--"]:
        add(
            "juice",
            "TRAIN",
            "search-sql-compound",
            "sqli",
            "GET",
            "/rest/products/search",
            {"q": value},
            "search_injection",
            None,
            "ATTACK_ATTEMPT",
        )

    # New benign form and JSON endpoints, not TRAIN rows reassigned after scores.
    for value in ["::1 -c 1", "127.0.0.1 -c 1 -s 16", "127.0.0.1 -c 1 -W 1"]:
        add(
            "dvwa",
            "CALIBRATION",
            "bounded-loopback-diagnostics",
            "benign",
            "POST",
            "/vulnerabilities/exec/",
            {"ip": value, "Submit": "Submit"},
            "loopback_ping_result",
            value.split()[0],
        )
    for value in ["./file1.php", "./file2.php", "./file3.php"]:
        add(
            "dvwa",
            "CALIBRATION",
            "relative-public-file",
            "benign",
            "GET",
            "/vulnerabilities/fi/",
            {"page": value},
            "included_public_page",
            value[2:],
        )
    for value in [
        "C++ example; 2+2=4",
        "Search/filter worked (a > b).",
        "O'Connor & partners: [review]",
        "Normal JSON braces {a:2}; thanks",
    ]:
        add(
            "juice",
            "CALIBRATION",
            "captcha-feedback-create",
            "benign",
            "POST",
            "/api/Feedbacks/",
            {
                "comment": value,
                "rating": 4,
                "captchaId": "__CAPTCHA_ID__",
                "captcha": "__CAPTCHA_ANSWER__",
            },
            "feedback_create",
            value,
        )
    add(
        "juice",
        "CALIBRATION",
        "captcha-arithmetic",
        "benign",
        "GET",
        "/rest/captcha/",
        {},
        "captcha_arithmetic",
        None,
    )
    # Known attempts in calibration are diagnostics only; thresholds use benign only.
    for value in ["<object data=javascript:alert(41)>", "<embed src=javascript:alert(42)>"]:
        add(
            "dvwa",
            "CALIBRATION",
            "reflected-embedded-content",
            "xss",
            "GET",
            "/vulnerabilities/xss_r/",
            {"name": value},
            "unsafe_reflection_only_no_browser_execution",
            value,
            "ATTACK_ATTEMPT",
        )

    # Prospective syntax is fixed now; no labels/scores may select a design later.
    for value in [
        "<math><mtext><img src=x onerror=alert(51)></mtext></math>",
        "<svg><a onmouseover=alert(52)>link</a></svg>",
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "reflected-nested-foreign-content",
            "xss",
            "GET",
            "/vulnerabilities/xss_r/",
            {"name": value},
            "unsafe_reflection_only_no_browser_execution",
            value,
            "ATTACK_ATTEMPT",
        )
    for value in [
        "127.0.0.1 -c 1; printf '%b' '\\125\\116\\102\\114\\117\\103\\113\\137\\105\\126\\101\\114\\137\\101'",
        "127.0.0.1 -c 1; for x in UNBLOCK_EVAL_B; do printf '%s' $x; done",
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "shell-octal-and-loop",
            "cmd_injection",
            "POST",
            "/vulnerabilities/exec/",
            {"ip": value, "Submit": "Submit"},
            "command_stdout_canary",
            "UNBLOCK_EVAL_A" if "%b" in value else "UNBLOCK_EVAL_B",
            "ATTACK_ATTEMPT",
        )
    for value in [
        "php://filter/convert.iconv.UTF-8.UTF-8/resource=/tmp/unblock-canary.txt",
        "php://filter/read=convert.base64-encode|convert.base64-decode/resource=/tmp/unblock-canary.txt",
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "file-chained-conversion",
            "path_traversal",
            "GET",
            "/vulnerabilities/fi/",
            {"page": value},
            "included_private_canary",
            "UNBLOCK_FILE_CANARY",
            "ATTACK_ATTEMPT",
        )
    for value, marker in [
        ("0' UNION SELECT CASE WHEN 1=1 THEN 'UBEA' ELSE 'no' END,'fixture' #", "UBEA"),
        ("0' UNION SELECT CHAR(85,66,69,66),'fixture' #", "UBEB"),
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "sql-case-char-expression",
            "sqli",
            "GET",
            "/vulnerabilities/sqli/",
            {"id": value, "Submit": "Submit"},
            "injected_sql_rows",
            marker,
            "ATTACK_ATTEMPT",
        )
    for value in ["Example: alpha(beta[3]) = {x:4}", "Equation: a*b + c/d != e"]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "reflected-math-name",
            "benign",
            "GET",
            "/vulnerabilities/xss_r/",
            {"name": value},
            "literal_name_reflection",
            value,
        )
    for value in [
        "Planning: (Monday OR Tuesday) && [review]",
        "A path a/b/c?x=2; ordinary documentation",
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "stored-docs-hard-negative",
            "benign",
            "POST",
            "/vulnerabilities/xss_s/",
            {"txtName": "LabReader", "mtxMessage": value, "btnSign": "Sign Guestbook"},
            "stored_literal",
            value,
        )
    return out


def request(case):
    # Match http.client automatic headers as well as the explicit collector profile.
    env = case["environment"]
    headers = {
        "Host": f"127.0.0.1:{PROXY}",
        "Accept-Encoding": "identity",
        "Content-Length": str(len(case["body"].encode())),
        "X-Request-Id": case["request_id"],
        "User-Agent": "Mozilla/5.0 LabResearch",
        "Accept": "application/json" if env == "juice" else "text/html",
        "Content-Type": "application/json"
        if env == "juice"
        else "application/x-www-form-urlencoded",
    }
    if env == "dvwa":
        headers["Cookie"] = "PHPSESSID=withheld; security=low"
    return dict(
        method=case["method"],
        url=case["path"],
        body=case["body"],
        headers="\r\n".join(f"{k}: {v}" for k, v in headers.items()),
    )


def keys(req, predictor, pv):
    vec, content, _, _ = pv.vector(predictor, req)
    safe = symbolic_request(req["method"], req["url"], req["headers"], req["body"])[0]
    # Header profile is constant across roles; no request ID, host or cookie values retained.
    return dict(
        raw=digest([req["method"], req["url"], req["body"]]),
        template=digest(
            [req["method"], re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(req["url"]).path), safe]
        ),
        rich=digest(rich_request_v2(req["method"], req["url"], req["headers"], req["body"])[0]),
        view=hashlib.sha256(vec.tobytes()).hexdigest(),
    ), content


def prepare(root):
    import numpy as np

    from idps_ai.mvp_inference import ResearchMVP

    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    plan = dict(
        schema_version="training-unblock-plan-1",
        run_id=RUN,
        baseline="4b0c8e2",
        environments=["pinned DVWA low-security", "pinned Juice Shop"],
        images={
            "DVWA": module("p0-dvwa-capture").APP_IMAGE,
            "DB": module("p0-dvwa-capture").DB_IMAGE,
            "Juice": JUICE,
        },
        helper_sha256={
            n: file_sha256(Path(__file__).with_name(n + ".py"))
            for n in [
                "p0-dvwa-capture",
                "quality-lab-cohort",
                "p0-request-evaluate",
                "integration-guard",
                "rolling-resource-policy",
            ]
        },
        source_sha256=file_sha256(__file__),
        roles_immutable=True,
        candidate_design_sha256=file_sha256(
            ROOT / "ai-training/configs/research/request-channel-robustness-v3.json"
        ),
        cases=cases(),
        coverage_gates={
            "TRAIN": {
                "workflow_groups": 6,
                "benign_GET_groups": 1,
                "benign_POST_groups": 1,
                "attack_families": ["sqli", "xss", "cmd_injection", "path_traversal"],
                "unique_views": 12,
            },
            "CALIBRATION": {
                "benign_workflow_groups": 4,
                "benign_GET_groups": 2,
                "benign_POST_groups": 2,
                "benign_JSON_groups": 1,
                "unique_benign_views": 8,
                "form_and_JSON": True,
            },
            "PROSPECTIVE_EVALUATION": {
                "attack_families": ["sqli", "xss", "cmd_injection", "path_traversal"],
                "templates_each_family": 2,
                "benign_GET_groups": 1,
                "benign_POST_groups": 1,
                "unique_views": 10,
            },
        },
        exclusions=[
            "Exact raw/rich/coarse-template/frozen-view exposed overlap: prospective excluded before capture",
            "Cross-role exact raw/rich/template/view or same-route content cosine>=0.995: quarantine connected component, never reassign",
            "Unknown/missing semantic Oracle excluded from supervised/calibration/evaluation labels",
            "No nonce/ID/padding counts as new workflow/campaign; benign variants in one endpoint remain one workflow",
            "No new study traffic unless preflight coverage remains attainable; no replacement capture after scores",
        ],
        lineage={
            "environment_independence": False,
            "existing_application_source_lineage": "EXPOSED",
            "campaign_id_not_independence_proof": True,
            "session_per_workflow": True,
            "global_upstream_novelty": "UNVERIFIED",
        },
        oracle_policy="Intent separate from success; unsafe reflection never browser execution; human review PENDING",
        bindings={
            "feedback": "captcha ID/answer from individually persisted ancillary receipt; before/after feedback state, no score-derived binding"
        },
        evaluation={
            "manifest_sealed_after_capture": True,
            "prospective_scores_before_training_review": 0,
            "threshold_rule": "benign CALIBRATION only, strict > maximum score for finite pilot; no <=1% population FPR claim",
            "calibration_attacks": "diagnostic only; not threshold selection",
            "Recall_targets": dict.fromkeys(
                ["sqli", "xss", "cmd_injection", "path_traversal"], 0.8
            ),
            "FPR_target": 0.01,
            "small_group_population_claim": "INCONCLUSIVE",
            "no_promote": True,
        },
        resources={
            "container_CPU_cores": 0.5,
            "host_RAM_budget_GB": 30,
            "reserve_GiB": 4,
            "instant_C": 90,
            "active_rolling_300s_C": 80,
            "stop_sensor_or_watchdog_loss": True,
        },
        capture_budget={
            "study_cases": len(cases()),
            "max_seconds": 600,
            "no_retry_of_study_requests": True,
        },
        next_if_infeasible="Use a separately source-pinned application with distinct command/file/HTML workflows and state Oracles; do not pad or relabel existing DVWA/Juice cases.",
    )
    plan["plan_sha256"] = digest(plan)
    atomic_json(root / "precommitted-plan.json", plan)
    # This is intentionally offline: feature extraction, not model scoring.
    predictor = ResearchMVP("request-v2", cpus=1)
    pv = module("p0-request-evaluate")
    old = []
    for line in (
        (ROOT / "ai-training/.artifacts/quality_lab_20261107/assessment-v2/role-audit.jsonl")
        .read_text()
        .splitlines()
    ):
        r = json.loads(line)
        receipt = Path(r["receipt_file"])
        h = json.loads((receipt.parent / "request-headers.json").read_text())
        old.append(
            dict(
                method=r["method"],
                url=r["path"],
                body=r["body"],
                headers="\r\n".join(f"{k}: {v}" for k, v in h.items()),
            )
        )
    _, _, p0 = pv.corpus(ROOT / "ai-training/.artifacts/p0_dvwa_20261105_1520/capture-final")
    old.extend(r["http_request"] for r in p0)
    historical = defaultdict(set)
    old_content = []
    with threadpool_limits(limits=1):
        for req in old:
            k, c = keys(req, predictor, pv)
            for name, value in k.items():
                historical[name].add(value)
            old_content.append((req["method"], urlsplit(req["url"]).path, c))
        candidate = []
        for case in plan["cases"]:
            k, c = keys(request(case), predictor, pv)
            candidate.append((case, k, c))
    tensor = (
        ROOT
        / "ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz"
    )
    with np.load(tensor, allow_pickle=False) as data:
        historical["view"].update(data["view"].astype(str).tolist())
    excluded = defaultdict(set)
    for i, (case, k, c) in enumerate(candidate):
        if case["role"] == "PROSPECTIVE_EVALUATION":
            for name, value in k.items():
                if value in historical[name]:
                    excluded[i].add("EXPOSED_" + name.upper())
            if any(
                method == case["method"]
                and path == urlsplit(case["path"]).path
                and float(c @ v) >= 0.995
                for method, path, v in old_content
            ):
                excluded[i].add("EXPOSED_NEAR_CONTENT")
        for j, (other, q, d) in enumerate(candidate[:i]):
            if case["role"] != other["role"]:
                same = any(k[name] == q[name] for name in ["raw", "template", "rich", "view"])
                near = (
                    case["method"] == other["method"]
                    and urlsplit(case["path"]).path == urlsplit(other["path"]).path
                    and float(c @ d) >= 0.995
                )
                if same or near:
                    excluded[i].add("CROSS_ROLE_OVERLAP")
                    excluded[j].add("CROSS_ROLE_OVERLAP")
    rows = [
        dict(
            request_id=c["request_id"],
            role=c["role"],
            workflow=c["workflow"],
            family=c["family"],
            intent=c["intent"],
            method=c["method"],
            environment=c["environment"],
            keys=k,
            exclusions=sorted(excluded[i]),
        )
        for i, (c, k, _) in enumerate(candidate)
    ]
    checks = {}
    for role, gate in plan["coverage_gates"].items():
        selected = [r for r in rows if r["role"] == role and not r["exclusions"]]
        benign = [r for r in selected if r["intent"] == "BENIGN"]
        fam = defaultdict(set)
        for r in selected:
            if r["intent"] == "ATTACK_ATTEMPT":
                fam[r["family"]].add(r["keys"]["template"])
        stats = {
            "eligible_cases": len(selected),
            "workflow_groups": len({r["workflow"] for r in selected}),
            "benign_workflow_groups": len({r["workflow"] for r in benign}),
            "benign_GET_groups": len({r["workflow"] for r in benign if r["method"] == "GET"}),
            "benign_POST_groups": len({r["workflow"] for r in benign if r["method"] == "POST"}),
            "benign_JSON_groups": len(
                {
                    r["workflow"]
                    for r in benign
                    if r["method"] == "POST" and r["environment"] == "juice"
                }
            ),
            "unique_views": len({r["keys"]["view"] for r in selected}),
            "unique_benign_views": len({r["keys"]["view"] for r in benign}),
            "attack_templates_per_family": {k: len(v) for k, v in fam.items()},
        }
        failures = []
        for name, value in gate.items():
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and name != "templates_each_family"
                and stats[name] < value
            ):
                failures.append(name)
        for family in gate.get("attack_families", []):
            if stats["attack_templates_per_family"].get(family, 0) < gate.get(
                "templates_each_family", 1
            ):
                failures.append("family_" + family)
        checks[role] = {
            "status": "FAIL" if failures else "PASS",
            "actual_preflight": stats,
            "failed_requirements": failures,
        }
    report = {
        "schema_version": "training-unblock-preflight-1",
        "plan_file_sha256": file_sha256(root / "precommitted-plan.json"),
        "status": "PASS"
        if all(r["status"] == "PASS" for r in checks.values())
        else "INFEASIBLE_AS_PRECOMMITTED",
        "coverage": checks,
        "excluded_cases": sum(bool(r["exclusions"]) for r in rows),
        "historical_requests_checked": len(old),
        "model_scores_computed": 0,
        "new_HTTP_requests_sent": 0,
        "rows": rows,
        "sealed_holdout_opened": False,
    }
    atomic_json(root / "preflight.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


def arithmetic_answer(text):
    if not isinstance(text, str) or len(text) > 100:
        return None
    try:
        node = ast.parse(text, mode="eval").body

        def evaluate(value):
            if (
                isinstance(value, ast.Constant)
                and type(value.value) is int
                and abs(value.value) < 10000
            ):
                return value.value
            if isinstance(value, ast.BinOp) and type(value.op) in (ast.Add, ast.Sub, ast.Mult):
                return {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}[
                    type(value.op)
                ](evaluate(value.left), evaluate(value.right))
            raise ValueError("Unsupported captcha arithmetic")

        return str(evaluate(node))
    except (SyntaxError, ValueError, RecursionError):
        return None


def configure_helpers():
    base = module("quality-lab-cohort")
    base.RUN = RUN
    base.LABEL = "idps.research-run=" + RUN
    return base


def pm(*args, **kwargs):
    return configure_helpers().pm(*args, **kwargs)


def owned():
    return configure_helpers().owned()


def remove_finished_container(*args):
    return configure_helpers().remove_finished_container(*args)


def prepare_capture(root):
    preflight = json.loads((root / "preflight.json").read_text())
    assert preflight["status"] == "PASS"
    source_plan = json.loads((root / "precommitted-plan.json").read_text())
    assert file_sha256(root / "precommitted-plan.json") == preflight["plan_file_sha256"]
    assert source_plan["source_sha256"] == file_sha256(__file__)
    assert not (root / "plan.json").exists()
    plan = {
        "source_sha256": file_sha256(__file__),
        "helper_sha256": {
            name: file_sha256(Path(__file__).with_name(name + ".py"))
            for name in [
                "p0-dvwa-capture",
                "juice-gt-factory",
                "p0-thermal-run",
                "quality-lab-cohort",
            ]
        },
        "precommitted_plan_file_sha256": file_sha256(root / "precommitted-plan.json"),
        "cases": [
            c
            for c in source_plan["cases"]
            if c["request_id"]
            not in {r["request_id"] for r in preflight["rows"] if r["exclusions"]}
        ],
    }
    plan["plan_sha256"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    (root / "collector-source.py").write_bytes(Path(__file__).read_bytes())


def run(root):
    os.umask(0o077)
    plan = json.loads((root / "plan.json").read_text())
    assert json.loads((root / "preflight.json").read_text())["status"] == "PASS"
    assert plan["plan_sha256"] == digest(
        {k: v for k, v in plan.items() if k != "plan_sha256"}
    ) and plan["source_sha256"] == file_sha256(__file__)
    assert all(
        file_sha256(Path(__file__).with_name(n + ".py")) == h
        for n, h in plan["helper_sha256"].items()
    )
    assert not (root / "capture.json").exists()
    if owned():
        raise RuntimeError(
            "A labeled lab already exists; verify ownership/cleanup before a new run"
        )
    d = module("p0-dvwa-capture")
    d.CANARY = "UNBLOCK_FILE_CANARY"
    d.CANARY_PATH = "/tmp/unblock-canary.txt"
    d.PORT = PORT
    d.PROXY_PORT = PROXY
    d.RUN_ID = RUN
    d.APP = RUN + "-dvwa"
    d.DB = RUN + "-db"
    d.NET = RUN + "-net"
    original_session = d.Session

    class PortBoundSession(original_session):
        def call(self, method, path, body="", extra=None, port=PORT):
            return super().call(method, path, body, extra, port)

    d.Session = PortBoundSession
    j = module("juice-gt-factory")
    j.APP_PORT = PORT
    (root / "heartbeat").touch()
    stop = threading.Event()

    def beat():
        while not stop.wait(0.2):
            (root / "heartbeat").touch()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    unit = "idps-" + RUN + "-" + root.name + "-watchdog.service"
    cmd = [
        "systemd-run",
        "--user",
        "--quiet",
        "--unit",
        unit,
        "--service-type=exec",
        "-p",
        "RuntimeMaxSec=900",
        "-p",
        "CPUQuota=10%",
        "-p",
        "MemoryMax=128M",
        "-p",
        "MemorySwapMax=0",
        "--setenv",
        "PATH=" + os.environ["PATH"],
        sys.executable,
        str(Path(__file__).resolve()),
        "watchdog",
        "--output",
        str(root),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    end = time.monotonic() + 10
    while not (root / "watchdog-ready").exists() and time.monotonic() < end:
        time.sleep(0.1)
    if not (root / "watchdog-ready").exists() or (root / "lab-watchdog-result.json").exists():
        stop.set()
        raise RuntimeError("Independent lab watchdog did not become ready")
    observations = []
    setup_count = 0
    network_created = False
    images = {}
    owned_names = []
    try:
        for image in [d.APP_IMAGE, d.DB_IMAGE, JUICE]:
            info = json.loads(pm("image", "inspect", image))[0]
            images[image] = {"id": info["Id"], "digests": info["RepoDigests"]}
        pm("network", "create", "--internal", "--label", LABEL, d.NET)
        network_created = True
        for env in [
            e for e in ["dvwa", "juice"] if any(c["environment"] == e for c in plan["cases"])
        ]:
            if env == "dvwa":
                pm(
                    "run",
                    "-d",
                    "--name",
                    d.DB,
                    "--label",
                    LABEL,
                    "--network",
                    d.NET,
                    "--network-alias",
                    "db",
                    "--cpus=.5",
                    "--memory=1g",
                    "--memory-swap=1g",
                    "--pids-limit=128",
                    "--security-opt=no-new-privileges",
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
                owned_names.append(d.DB)
                name = d.APP
                image = d.APP_IMAGE
                port = "80"
                extra = ["-e", "DB_SERVER=db"]
            else:
                name = RUN + "-juice"
                image = JUICE
                port = "3000"
                extra = []
            pm(
                "run",
                "-d",
                "--name",
                name,
                "--label",
                LABEL,
                "--network",
                d.NET,
                "--cpus=.5",
                "--memory=2g" if env == "juice" else "--memory=1g",
                "--memory-swap=2g" if env == "juice" else "--memory-swap=1g",
                "--pids-limit=256",
                "--security-opt=no-new-privileges",
                "-p",
                f"127.0.0.1:{PORT}:{port}",
                *extra,
                image,
            )
            owned_names.append(name)
            info = json.loads(pm("inspect", name))[0]
            net = json.loads(pm("network", "inspect", d.NET))[0]
            assert net["internal"] and info["NetworkSettings"]["Ports"][port + "/tcp"] == [
                {"HostIp": "127.0.0.1", "HostPort": str(PORT)}
            ]
            atomic_json(
                root / (env + "-identity.json"),
                {
                    "container_id": info["Id"],
                    "image_id": info["Image"],
                    "network_internal": True,
                    "port": PORT,
                    "labels": info["Config"]["Labels"],
                    "cgroup_parent_containment": "NOT_CLAIMED; per-container CPU/RAM limits and independent named-label watchdog",
                },
            )
            if env == "dvwa":
                session = d.Session(root / "dvwa-setup")
                d.initialize(session)
                setup_count += session.setup_requests
                pm("exec", name, "sh", "-c", "printf %s '" + d.CANARY + "' > " + d.CANARY_PATH)
                rows = pm(
                    "exec",
                    d.DB,
                    "mariadb",
                    "-udvwa",
                    "-pp@ssw0rd",
                    "-N",
                    "dvwa",
                    "-e",
                    "SELECT user_id,first_name,last_name FROM users ORDER BY user_id",
                )
                users = {f[0]: f[1:] for f in [line.split("\t") for line in rows.splitlines()]}
                atomic_json(root / "dvwa-users-oracle.json", users)
                for source in d.SOURCES + [
                    "vulnerabilities/xss_s/source/low.php",
                    "vulnerabilities/sqli_blind/source/low.php",
                ]:
                    target = root / "application-source" / env / source.replace("/", "__")
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    target.write_text(pm("exec", name, "cat", "/var/www/html/" + source))
            else:
                for _ in range(100):
                    try:
                        status, _, body = d.low_http(PORT, "GET", "/api/Products/")
                        catalog = json.loads(body)["data"]
                        if status == 200:
                            break
                    except (OSError, ValueError, KeyError):
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Juice startup failed")
                initial = j._challenge_snapshot()
                atomic_json(root / "juice-challenge-before.json", initial)
                atomic_json(root / "juice-catalog.json", catalog)
                session = None
            group = root / env
            group.mkdir(mode=0o700)
            d.Gateway.output = group / "receipts"
            d.Gateway.output.mkdir(mode=0o700)
            d.Gateway.receipts = {}
            d.Gateway.allowed_ids = {
                c["request_id"] for c in plan["cases"] if c["environment"] == env
            }
            server = d.ThreadingHTTPServer(("127.0.0.1", PROXY), d.Gateway)
            relay = threading.Thread(target=server.serve_forever, daemon=True)
            relay.start()
            try:
                role_sessions = {}
                for case in [c for c in plan["cases"] if c["environment"] == env]:
                    headers = {
                        "X-Request-Id": case["request_id"],
                        "User-Agent": "Mozilla/5.0 LabResearch",
                        "Accept": "application/json" if env == "juice" else "text/html",
                        "Content-Type": "application/json"
                        if env == "juice"
                        else "application/x-www-form-urlencoded",
                    }
                    if env == "dvwa":
                        if case["session_plan"] not in role_sessions:
                            # Separate PHP session per role; share only predeclared clean fixture DB.
                            ss = d.Session(root / ("session-" + digest(case["session_plan"])[:12]))
                            _, _, page, _ = ss.call("GET", "/login.php")
                            token = re.search(
                                rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page
                            )
                            assert token
                            status, _, _, _ = ss.call(
                                "POST",
                                "/login.php",
                                urlencode(
                                    {
                                        "username": "admin",
                                        "password": "password",
                                        "Login": "Login",
                                        "user_token": token[1].decode(),
                                    }
                                ),
                            )
                            assert status == 302
                            ss.cookies["security"] = "low"
                            role_sessions[case["session_plan"]] = ss
                            setup_count += ss.setup_requests
                        headers["Cookie"] = "; ".join(
                            f"{k}={v}"
                            for k, v in role_sessions[case["session_plan"]].cookies.items()
                        )
                    if (root / "lab-watchdog-result.json").exists():
                        raise RuntimeError("Independent lab watchdog stopped; no more traffic")
                    actual_body = case["body"]
                    if case["oracle"] == "feedback_create":
                        ancillary = root / "ancillary" / case["request_id"]
                        ancillary.mkdir(parents=True, mode=0o700)
                        cs, ch, cb = d.low_http(PORT, "GET", "/rest/captcha/")
                        (ancillary / "captcha-response.bin").write_bytes(cb)
                        atomic_json(
                            ancillary / "captcha-receipt.json",
                            {
                                "method": "GET",
                                "path": "/rest/captcha/",
                                "status": cs,
                                "headers": ch,
                                "body_sha256": hashlib.sha256(cb).hexdigest(),
                            },
                        )
                        captcha = json.loads(cb)
                        fields = json.loads(actual_body)
                        fields["captchaId"] = captcha["captchaId"]
                        fields["captcha"] = captcha["answer"]
                        actual_body = json.dumps(fields)
                        atomic_json(
                            ancillary / "binding.json",
                            {
                                "planned_body_sha256": hashlib.sha256(
                                    case["body"].encode()
                                ).hexdigest(),
                                "actual_body_sha256": hashlib.sha256(
                                    actual_body.encode()
                                ).hexdigest(),
                                "captcha_snapshot_sha256": hashlib.sha256(cb).hexdigest(),
                            },
                        )
                    start = time.time()
                    status, returned, response = d.low_http(
                        PROXY, case["method"], case["path"], actual_body.encode(), headers
                    )
                    receipt = d.Gateway.receipts[case["request_id"]]
                    assert (
                        receipt["response_sha256"] == hashlib.sha256(response).hexdigest()
                        and receipt["request_body_sha256"]
                        == hashlib.sha256(actual_body.encode()).hexdigest()
                    )
                    rule = case["oracle"]
                    semantic = False
                    outcome = "UNKNOWN"
                    detail = {}
                    if env == "dvwa":
                        if rule == "transformed_canary":
                            expected = (
                                codecs.encode(d.CANARY, "rot_13")
                                if case["expected"] == "rot13"
                                else d.CANARY.upper()
                            )
                            semantic = expected in response.decode(errors="replace")
                            detail = {
                                "fixture_transform_matches": semantic,
                                "transform": case["expected"],
                            }
                            if semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                        elif rule in ["stored_literal", "unsafe_stored_reflection"]:
                            semantic = case["expected"] in response.decode(errors="replace")
                            detail = {
                                "stored_text_reflected": semantic,
                                "browser_execution_tested": False,
                            }
                            # Verify guestbook persistence independently from reflected textarea/input.
                            marker = case["expected"].replace("'", "''")
                            found = pm(
                                "exec",
                                d.DB,
                                "mariadb",
                                "-udvwa",
                                "-pp@ssw0rd",
                                "-N",
                                "dvwa",
                                "-e",
                                "SELECT COUNT(*) FROM guestbook WHERE comment='" + marker + "'",
                            )
                            detail["guestbook_exact_row_count"] = int(found)
                            semantic = semantic and int(found) >= 1
                            if rule == "unsafe_stored_reflection":
                                outcome = "UNSAFE_REFLECTION" if semantic else "UNKNOWN"
                        elif rule in ["blind_identity", "blind_injection"]:
                            text = response.decode(errors="replace")
                            exists = "User ID exists in the database." in text
                            missing = "User ID is MISSING from the database." in text
                            semantic = exists if case["expected"] else missing
                            detail = {
                                "exists_message": exists,
                                "missing_message": missing,
                                "fixture_user_count": len(users),
                            }
                            if rule == "blind_injection" and semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                        else:
                            semantic, detail = d.oracle(case, response, users)
                            if case["intent"] == "ATTACK_ATTEMPT" and semantic:
                                outcome = (
                                    "UNSAFE_REFLECTION"
                                    if case["family"] == "xss"
                                    else "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                                )
                    else:
                        try:
                            parsed = json.loads(response)
                        except ValueError:
                            parsed = None
                        data = parsed.get("data") if isinstance(parsed, dict) else None
                        if rule == "catalog_list":
                            semantic = isinstance(data, list) and {x["id"] for x in catalog} == {
                                x["id"] for x in data
                            }
                            detail = {"catalog_ids_equal": semantic}
                        elif rule == "feedback_create":
                            parsed_body = json.loads(actual_body)
                            semantic = (
                                status == 201
                                and isinstance(data, dict)
                                and isinstance(data.get("id"), int)
                                and data.get("comment") == case["expected"]
                                and data.get("rating") == parsed_body["rating"]
                            )
                            state_status, state_headers, state_body = d.low_http(
                                PORT, "GET", "/api/Feedbacks/"
                            )
                            state = json.loads(state_body).get("data", [])
                            persisted = semantic and any(
                                x.get("id") == data["id"]
                                and x.get("comment") == case["expected"]
                                and x.get("rating") == parsed_body["rating"]
                                for x in state
                            )
                            semantic = bool(persisted)
                            ancillary = root / "ancillary" / case["request_id"]
                            (ancillary / "feedback-state.bin").write_bytes(state_body)
                            atomic_json(
                                ancillary / "feedback-state-receipt.json",
                                {
                                    "method": "GET",
                                    "path": "/api/Feedbacks/",
                                    "status": state_status,
                                    "headers": state_headers,
                                    "body_sha256": hashlib.sha256(state_body).hexdigest(),
                                },
                            )
                            detail = {
                                "created_id": data.get("id") if isinstance(data, dict) else None,
                                "returned_and_persisted_exact_comment_rating": semantic,
                            }
                        elif rule == "captcha_arithmetic":
                            semantic = (
                                status == 200
                                and isinstance(parsed, dict)
                                and arithmetic_answer(parsed.get("captcha"))
                                == str(parsed.get("answer"))
                            )
                            detail = {"arithmetic_check": semantic}
                        elif rule == "language_catalog":
                            semantic = (
                                status == 200
                                and isinstance(parsed, list)
                                and any(x.get("key") == "en" for x in parsed)
                                and all(
                                    isinstance(x.get("key"), str) and isinstance(x.get("lang"), str)
                                    for x in parsed
                                )
                            )
                            detail = {
                                "schema_and_English_language_present": semantic,
                                "oracle_strength": "schema only; source binding required before research label eligible",
                            }
                            semantic = False  # No expected source-bound language state retained by this adapter.
                        elif rule == "catalog_identity":
                            semantic = (
                                isinstance(data, dict)
                                and data.get("id") == case["expected"]
                                and any(
                                    x["id"] == data["id"] and x["name"] == data["name"]
                                    for x in catalog
                                )
                            )
                        elif rule == "catalog_search":
                            expected = [
                                x["id"]
                                for x in catalog
                                if case["expected"].lower()
                                in (str(x["name"]) + " " + str(x.get("description", ""))).lower()
                            ]
                            semantic = (
                                isinstance(data, list)
                                and all(
                                    isinstance(x, dict)
                                    and x.get("id") in {y["id"] for y in catalog}
                                    for x in data
                                )
                                and {x["id"] for x in data} == set(expected)
                            )
                        elif rule == "invalid_login_denied":
                            semantic = status == 401 and response == b"Invalid email or password."
                        elif rule == "created_user":
                            semantic = (
                                isinstance(data, dict)
                                and isinstance(data.get("id"), int)
                                and data.get("email") == case["expected"]
                            )
                            detail = {
                                "created_fixture_user_id": data.get("id")
                                if isinstance(data, dict)
                                else None
                            }
                        elif rule == "admin_auth_bypass":
                            auth = (
                                parsed.get("authentication") if isinstance(parsed, dict) else None
                            )
                            after = j._challenge_snapshot()
                            atomic_json(root / "juice-challenge-after.json", after)
                            semantic = bool(
                                isinstance(auth, dict)
                                and auth.get("umail") == "admin@juice-sh.op"
                                and auth.get("token")
                                and not initial["solved"]
                                and after["solved"]
                                and after["id"] == initial["id"]
                            )
                            if semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                            detail = {
                                "initial_challenge_solved": initial["solved"],
                                "after_challenge_solved": after["solved"],
                            }
                        elif rule == "search_injection":
                            semantic = (
                                isinstance(data, list)
                                and all(isinstance(x, dict) for x in data)
                                and {x["id"] for x in catalog} <= {x.get("id") for x in data}
                                and len(catalog) > 10
                            )
                            if semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                            detail = {
                                "returned_distinct_ids": len({x.get("id") for x in data})
                                if isinstance(data, list)
                                else None,
                                "fixture_catalog_size": len(catalog),
                            }
                    intent = (
                        case["intent"]
                        if case["intent"] == "ATTACK_ATTEMPT" or semantic
                        else "UNKNOWN"
                    )
                    observations.append(
                        {
                            **case,
                            "actual_body_sha256": hashlib.sha256(actual_body.encode()).hexdigest(),
                            "intent": intent,
                            "semantic_oracle_matched": semantic,
                            "outcome": outcome,
                            "oracle_detail": detail,
                            "response_status": status,
                            "receipt_matches": True,
                            "receipt_path": str(
                                (
                                    group / "receipts" / case["request_id"] / "receipt.json"
                                ).relative_to(root)
                            ),
                            "response_sha256": hashlib.sha256(response).hexdigest(),
                            "session_group": hashlib.sha256(
                                (
                                    headers.get("Cookie", "")
                                    or "stateless-" + env + "-" + case["session_plan"]
                                ).encode()
                            ).hexdigest(),
                            "session_group_basis": "COOKIE_DIGEST"
                            if headers.get("Cookie")
                            else "STATELESS_ROLE_COHORT_CONSERVATIVE",
                            "review_status": "REVIEW_PENDING",
                            "independent_human_verified": False,
                            "started_at": start,
                            "ended_at": time.time(),
                            "transaction_provenance": "OWNED_PROXY_RECEIPT_NOT_APPLICATION_REQUEST_ID_LOG",
                        }
                    )
                    atomic_json(root / "observations-progress.json", {"observations": observations})
                    atomic_json(
                        root / "progress.json",
                        {"completed": len(observations), "planned": len(plan["cases"])},
                    )
            finally:
                server.shutdown()
                server.server_close()
                relay.join(timeout=3)
            pm("logs", name, check=False)  # Never print container/session logs.
            remove_finished_container(name, root / (env + "-cleanup-diagnostic.json"))
            owned_names.remove(name)
            if env == "dvwa":
                remove_finished_container(d.DB, root / "db-cleanup-diagnostic.json")
                owned_names.remove(d.DB)
        report = {
            "schema_version": "research-capture-1",
            "plan_sha256": plan["plan_sha256"],
            "script_sha256": file_sha256(__file__),
            "requests_sent": len(observations),
            "setup_requests_excluded": setup_count,
            "images": images,
            "observations": observations,
            "intent_counts": dict(Counter(o["intent"] for o in observations)),
            "outcome_counts": dict(Counter(o["outcome"] for o in observations)),
            "independent_review": "PENDING",
            "independently_verified_labels": 0,
            "models_loaded_during_capture": False,
            "GLU207_eligible": 0,
            "formal_admitted": 0,
            "raw_evidence_distribution": "LOCAL_ONLY fixtures/session material; never public",
        }
        atomic_json(root / "capture.json", report)
    finally:
        for name in reversed(owned_names):
            pm("rm", "-f", name, check=False)
        if network_created:
            pm("network", "rm", d.NET, check=False)
        stop.set()
        thread.join(timeout=2)
        (root / "watchdog-done").touch()
        for _ in range(10):
            if (root / "lab-watchdog-result.json").exists():
                break
            time.sleep(0.1)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
        atomic_json(
            root / "cleanup.json",
            {"owned_containers_remaining": len(owned()), "watchdog_unit": unit, "stopped": True},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "capture", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.command == "prepare":
        prepare(a.output.resolve())
    elif a.command == "capture":
        prepare_capture(a.output.resolve())
        run(a.output.resolve())
    else:
        configure_helpers().watchdog(a.output.resolve())
