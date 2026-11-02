"""Evidence-first collection on the AI-owned loopback Student fixture.

The runner records its planned intent. It never approves a semantic label or
infers exploit success from a response, WAF rule, or model prediction.
"""

import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.lab_capture import LabClient
from idps_ai.data.snapshot import new_destination

FAMILIES = ("sqli", "xss", "path_traversal", "cmd_injection")
SEARCHES = (
    (
        "registrar calendar",
        "O'Connor course catalogue",
        "notes about SELECT in SQL",
        "HTML onload tutorial",
    ),
    (
        "exam timetable",
        "a guide to ../ relative paths",
        "boolean OR lecture",
        "shell pipe documentation",
    ),
    (
        "course prerequisites",
        "javascript: URL explained",
        "accounting union report",
        "literal $(name) example",
    ),
)
PROBES = (
    {
        "sqli": ("7' OR 'x'='x' --", "7 UNION SELECT NULL"),
        "xss": ("<svg onload=confirm(71)>", "<a href=javascript:confirm(71)>go</a>"),
        "path_traversal": ("../../etc/hosts",),
        "cmd_injection": ("text;printf LAB71",),
    },
    {
        "sqli": ("11' AND 2=2--", "11 UNION ALL SELECT 3"),
        "xss": ("<img src=x onerror=confirm(83)>", "<details open ontoggle=confirm(83)>"),
        "path_traversal": ("..%2f..%2fetc%2fhostname",),
        "cmd_injection": ("word$(printf LAB83)",),
    },
    {
        "sqli": ("13' OR 4>3--", "13/**/UNION/**/SELECT 5"),
        "xss": ("<body onload=confirm(97)>", "<math href=javascript:confirm(97)>"),
        "path_traversal": ("%2e%2e/%2e%2e/etc/hosts",),
        "cmd_injection": ("value&&printf LAB97",),
    },
)
NOVEL_SEARCHES = (
    (
        "course notes discussing UNION as a set operator",
        "HTML tutorial showing <table> markup",
        "syllabus explains ../../ as a relative path",
        "shell lesson discusses && as prose",
    ),
    (
        "database lecture about boolean AND expressions",
        "web class explains javascript: URLs safely",
        "filesystem guide uses ../ in examples",
        "manual quotes command substitution $(date)",
    ),
    (
        "SQL lecture compares SELECT and JOIN",
        "front-end notes show onerror handler syntax",
        "documentation lists /etc/hosts as an example",
        "terminal guide explains pipes | in text",
    ),
)
NOVEL_PROBES = (
    {
        "sqli": ("42' OR 8=8 /*lab*/", "42 UNION SELECT 8,9"),
        "xss": ("<video oncanplay=confirm(112)>", "javascript:confirm(112)"),
        "path_traversal": ("....//etc/hosts",),
        "cmd_injection": ("agenda;id",),
    },
    {
        "sqli": ("53' AND 9>2#", "53 UNION ALL SELECT 9,10"),
        "xss": ("<iframe srcdoc=confirm(124)>", "<svg onfocus=confirm(124)>"),
        "path_traversal": ("..%252f..%252fetc%252fhostname",),
        "cmd_injection": ("catalog|whoami",),
    },
    {
        "sqli": ("61' OR 1 LIKE 1--", "61/**/UNION/**/SELECT/**/11"),
        "xss": (
            "<input autofocus onfocus=confirm(139)>",
            "data:text/html,<script>confirm(139)</script>",
        ),
        "path_traversal": ("%252e%252e%252fetc%252fhosts",),
        "cmd_injection": ("term`id`",),
    },
)


def _body_sha(case):
    if case.get("body_kind") == "private_fixture_password":
        return None
    body = case.get("body", "")
    encoded = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
    return hashlib.sha256(encoded).hexdigest()


def _cases(campaign_index, seed, profile="legacy"):
    if campaign_index not in ((0,) if profile == "gt-pilot-v1" else (0, 1, 2)):
        raise PipelineError("Only three bounded development campaigns are defined")
    if profile not in ("legacy", "novel-v2", "gt-pilot-v1"):
        raise PipelineError("Unsupported bounded evidence campaign profile")
    if profile == "gt-pilot-v1":
        # This small prospective protocol has a real application-state oracle.
        # Intent remains unapproved until an independent reviewer signs its
        # exact plan before any request is sent.
        return [
            {
                "case_id": "csrf",
                "scenario": "csrf_setup",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": "/api/auth/csrf",
            },
            {
                "case_id": "fixture_login",
                "scenario": "authorized_fixture_login",
                "family": "benign",
                "intent": "benign",
                "method": "POST",
                "target": "/api/auth/login",
                "body_kind": "private_fixture_password",
            },
            {
                "case_id": "csrf_refresh",
                "scenario": "csrf_after_login",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": "/api/auth/csrf",
            },
            {
                "case_id": "catalog_read",
                "scenario": "benign_catalog",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": "/api/faculties",
            },
            {
                "case_id": "hard_negative",
                "scenario": "hard_negative_search",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": "/api/faculties?" + urlencode({"q": "course notes about UNION SELECT"}),
            },
            {
                "case_id": "sqli_probe",
                "scenario": "bounded_attack_intent_probe",
                "family": "sqli",
                "intent": "attack",
                "method": "GET",
                "target": "/api/faculties?" + urlencode({"q": "7' OR 'x'='x' --"}),
            },
            {
                "case_id": "xss_probe",
                "scenario": "bounded_attack_intent_probe",
                "family": "xss",
                "intent": "attack",
                "method": "GET",
                "target": "/api/faculties?" + urlencode({"q": "<svg onload=confirm(71)>"}),
            },
            {
                "case_id": "faculty_create",
                "scenario": "benign_mutation_with_db_oracle",
                "family": "benign",
                "intent": "benign",
                "method": "POST",
                "target": "/api/faculties",
                "body": {
                    "shortCode": "GTPILOT01",
                    "name": "Ground Truth Pilot",
                    "description": "AI-owned lab oracle marker",
                    "active": True,
                },
            },
        ]
    rows = [
        {
            "case_id": "csrf",
            "scenario": "csrf_setup",
            "family": "benign",
            "intent": "benign",
            "method": "GET",
            "target": "/api/auth/csrf",
        },
        {
            "case_id": "fixture_login",
            "scenario": "authorized_fixture_login",
            "family": "benign",
            "intent": "benign",
            "method": "POST",
            "target": "/api/auth/login",
            "body_kind": "private_fixture_password",
        },
        {
            "case_id": "csrf_refresh",
            "scenario": "csrf_after_login",
            "family": "benign",
            "intent": "benign",
            "method": "GET",
            "target": "/api/auth/csrf",
        },
    ]
    typo = [
        {
            "case_id": "login_typo",
            "scenario": "single_invalid_login",
            "family": "benign",
            "intent": "benign",
            "method": "POST",
            "target": "/api/auth/login",
            "body": urlencode(
                {
                    "username": f"no_such_ai_lab_{campaign_index}",
                    "password": "lab-only-invalid-password",
                }
            ),
        },
    ]
    for j, endpoint in enumerate(("faculties", "majors", "classes", "training-programs")):
        rows.append(
            {
                "case_id": f"catalog_{j}",
                "scenario": "benign_catalog",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": (
                    f"/api/{endpoint}?page={campaign_index + 2}&sort=asc"
                    if profile == "novel-v2"
                    else f"/api/{endpoint}"
                ),
            }
        )
    searches = NOVEL_SEARCHES if profile == "novel-v2" else SEARCHES
    probes = NOVEL_PROBES if profile == "novel-v2" else PROBES
    attack_endpoint = ("majors", "classes", "training-programs")[campaign_index]
    for j, phrase in enumerate(searches[campaign_index]):
        rows.append(
            {
                "case_id": f"hard_negative_{j}",
                "scenario": "hard_negative_search",
                "family": "benign",
                "intent": "benign",
                "method": "GET",
                "target": (
                    f"/api/{attack_endpoint}?" if profile == "novel-v2" else "/api/faculties?"
                )
                + urlencode({"q": phrase}),
            }
        )
    for family in FAMILIES:
        for j, probe in enumerate(probes[campaign_index][family]):
            rows.append(
                {
                    "case_id": f"{family}_{j}",
                    "scenario": "bounded_attack_intent_probe",
                    "family": family,
                    "intent": "attack",
                    "method": "GET",
                    "target": (
                        f"/api/{attack_endpoint}?" if profile == "novel-v2" else "/api/faculties?"
                    )
                    + urlencode({"q": probe}),
                }
            )
    first, rest = rows[:3], rows[3:]
    random.Random(seed).shuffle(rest)
    return [*first, *rest, *typo]


def create_plan(output, collector_source, seeds, profile="legacy", exclude_plans=()):
    required = 1 if profile == "gt-pilot-v1" else 3
    if (
        len(seeds) != required
        or len(set(seeds)) != required
        or not all(type(x) is int for x in seeds)
    ):
        raise PipelineError("The profile requires distinct fixed seeds for each campaign")
    if profile not in ("legacy", "novel-v2", "gt-pilot-v1"):
        raise PipelineError("Unsupported bounded evidence campaign profile")
    excluded = set()
    excluded_plan_sha = []
    for path in exclude_plans:
        prior = load_json(Path(path) / "plan.json")
        checksum = prior.pop("plan_sha256", None)
        if checksum != digest(prior):
            raise PipelineError("Excluded campaign plan integrity failed")
        excluded_plan_sha.append(file_sha256(Path(path) / "plan.json"))
        excluded.update(
            case["target_sha256"]
            for campaign in prior["campaigns"]
            for case in campaign["cases"]
            if case["scenario"] in ("hard_negative_search", "bounded_attack_intent_probe")
        )
    output = new_destination(output)
    output.mkdir(mode=0o700)
    campaigns = []
    targets = set()
    for index, seed in enumerate(seeds):
        cases = []
        for case in _cases(index, seed, profile):
            target_sha = hashlib.sha256(case["target"].encode()).hexdigest()
            if case["scenario"] in ("hard_negative_search", "bounded_attack_intent_probe"):
                if target_sha in targets or target_sha in excluded:
                    raise PipelineError(
                        "Attack or hard-negative view repeats across campaigns or prior plans"
                    )
                targets.add(target_sha)
            cases.append(
                {
                    "case_id": case["case_id"],
                    "scenario": case["scenario"],
                    "planned_intent": case["intent"],
                    "attack_family": case["family"],
                    "http_method": case["method"],
                    "target_sha256": target_sha,
                    "body_sha256": _body_sha(case),
                    "body_kind": case.get("body_kind"),
                    **(
                        {
                            "review_target": case["target"],
                            "review_body": case.get("body"),
                            "review_note": "Private lab-only request; independently inspect semantics before signing. Fixture login password is withheld.",
                        }
                        if profile == "gt-pilot-v1"
                        else {}
                    ),
                }
            )
        campaigns.append(
            {
                "campaign_id": f"evidence-lab-{index:02d}-{seed:08x}",
                "seed": seed,
                "source_ip": f"127.0.0.{40 + index}",
                "partition": "development_review_only",
                "cases": cases,
            }
        )
    result = {
        "format_version": 1,
        "purpose": "authorized_ai_owned_loopback_http_evidence",
        "target": "127.0.0.1:18881",
        "collector_source_sha256": file_sha256(collector_source),
        "case_profile": profile,
        "excluded_plan_file_sha256": excluded_plan_sha,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaigns": campaigns,
        "future_holdout": {
            "status": "RESERVED_NOT_GENERATED_OR_CAPTURED",
            "environment": "new_independent_authorized_environment_required",
            "allow_for_tuning": False,
        },
        "label_policy": "Prospective pilot needs an independently signed exact protocol before capture; a matching request is staging only until the evidence-v2 gate. Application DB state verifies outcome separately from intent."
        if profile == "gt-pilot-v1"
        else "Planned intent is evidence, not approval; independent semantic review required. Exploit outcome remains unknown without application oracle.",
    }
    result["plan_sha256"] = digest(result)
    atomic_json(output / "plan.json", result)
    return result


def _source_lines(path, ids):
    found = defaultdict(list)
    with Path(path).open("rb") as stream:
        for line in stream:
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Oversized or partial lab log line")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid lab JSONL; raw line omitted") from None
            rid = row.get("request_id")
            if rid in ids:
                found[rid].append((row, hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()))
    return found


def _verify_sources(lab, observed):
    ids = set(observed)
    nginx_path, student_path = lab / "access-lab.log", lab / "student-audit.log"
    deadline = time.monotonic() + 15
    while True:
        nginx = _source_lines(nginx_path, ids)
        student = _source_lines(student_path, ids)
        if all(len(nginx[rid]) == len(student[rid]) == 1 for rid in ids):
            break
        if time.monotonic() >= deadline:
            raise PipelineError("Missing or ambiguous request ID in Student/Nginx captures")
        time.sleep(0.2)
    evidence = []
    for rid, source in observed.items():
        n, n_sha = nginx[rid][0]
        s, s_sha = student[rid][0]
        for row, method_key, status_key in (
            (n, "http_method", "status"),
            (s, "http_method", "status_code"),
        ):
            if (
                row.get(method_key) != source["http_method"]
                or int(row.get(status_key, -1)) != source["status_code"]
            ):
                raise PipelineError("Correlated source disagrees on HTTP method/status")
        target = source.pop("_target")
        parsed = urlsplit(target)
        if n.get("uri_path") != parsed.path or (n.get("query_string") or "") != parsed.query:
            raise PipelineError("Nginx capture does not match precommitted request target")
        evidence.append(
            source
            | {
                "source_evidence": {
                    "nginx_access_line_sha256": n_sha,
                    "student_audit_line_sha256": s_sha,
                    "nginx_timestamp": n.get("timestamp"),
                    "student_timestamp": s.get("timestamp"),
                    "nginx_file_sha256": file_sha256(nginx_path),
                    "student_file_sha256": file_sha256(student_path),
                },
                "source_count": 2,
                "capture_verified": True,
                "review_status": "pending_independent_semantic_review",
                "training_eligible": False,
            }
        )
    return evidence


def collect(
    plan_dir, lab_dir, output, collector_source, approval_path=None, trusted_public_key=None
):
    plan = load_json(Path(plan_dir) / "plan.json")
    checksum = plan.pop("plan_sha256", None)
    if (
        checksum != digest(plan)
        or plan.get("purpose") != "authorized_ai_owned_loopback_http_evidence"
        or plan.get("target") != "127.0.0.1:18881"
        or plan.get("collector_source_sha256") != file_sha256(collector_source)
    ):
        raise PipelineError("Pre-registered campaign plan changed")
    approval = None
    if plan.get("case_profile") == "gt-pilot-v1":
        if not approval_path or not trusted_public_key:
            raise PipelineError(
                "Prospective GT pilot needs a signed independent pre-capture protocol"
            )
        from idps_ai.data.protocol_ground_truth import verify_signed_protocol

        approval = verify_signed_protocol(
            Path(plan_dir) / "plan.json",
            approval_path,
            trusted_public_key,
            require_current_collector=True,
        )
    lab = Path(lab_dir).resolve()
    marker = load_json(lab / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable" or marker.get("edge_port") != 18881:
        raise PipelineError("Only the AI-owned loopback lab can receive these campaigns")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    if approval:
        atomic_json(
            output / "preflight-approval.json",
            {
                "format_version": 1,
                "plan_sha256": checksum,
                "approval_file_sha256": approval["approval_file_sha256"],
                "reviewer_public_key_sha256": approval["reviewer_public_key_sha256"],
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "SIGNED_PROTOCOL_VERIFIED_BEFORE_REQUEST_DISPATCH",
            },
        )
    fixture_password = load_json(lab / "accounts-private.json")["password"]
    observed, actual = {}, Counter()
    for index, campaign in enumerate(plan["campaigns"]):
        if campaign.get("partition") != "development_review_only":
            raise PipelineError("Future holdout must not be captured by this runner")
        client = LabClient(18881, campaign["source_ip"])
        cases = _cases(index, campaign["seed"], plan.get("case_profile", "legacy"))
        if len(cases) != len(campaign["cases"]):
            raise PipelineError("Plan case count changed")
        for case, committed in zip(cases, campaign["cases"]):
            if (
                case["case_id"] != committed["case_id"]
                or hashlib.sha256(case["target"].encode()).hexdigest() != committed["target_sha256"]
                or _body_sha(case) != committed["body_sha256"]
                or case.get("body_kind") != committed.get("body_kind")
                or case["intent"] != committed["planned_intent"]
                or case["family"] != committed["attack_family"]
                or case["method"] != committed["http_method"]
            ):
                raise PipelineError("Dispatched case differs from sealed plan")
            request_body = case.get("body")
            if case.get("body_kind") == "private_fixture_password":
                request_body = urlencode(
                    {"username": f"ai_lab_{index:02d}", "password": fixture_password}
                )
            record, body = client.request(case["method"], case["target"], request_body)
            if case["case_id"] == "fixture_login" and record["status_code"] != 204:
                raise PipelineError(
                    "Owned fixture login did not establish an authenticated session"
                )
            if case["case_id"] in ("csrf", "csrf_refresh"):
                try:
                    csrf = json.loads(body)
                    if not isinstance(csrf.get("token"), str) or not isinstance(
                        csrf.get("headerName"), str
                    ):
                        raise ValueError
                    client.csrf = csrf
                except (ValueError, AttributeError):
                    raise PipelineError("Owned lab CSRF fixture failed") from None
            if (
                case["scenario"]
                in ("benign_catalog", "hard_negative_search", "bounded_attack_intent_probe")
                and record["status_code"] == 401
            ):
                raise PipelineError("Application workload was intercepted by the auth boundary")
            rid = record["request_id"]
            if rid in observed:
                raise PipelineError("Edge returned a duplicate request ID")
            observed[rid] = {
                "request_id": rid,
                "timestamp_utc": record["timestamp"],
                "campaign_id": campaign["campaign_id"],
                "case_id": case["case_id"],
                "planned_intent": case["intent"],
                "planned_family": case["family"],
                "intent_label_from_plan": int(case["intent"] == "attack"),
                "http_method": case["method"],
                "status_code": record["status_code"],
                "target_sha256": committed["target_sha256"],
                "plan_sha256": checksum,
                "exploit_outcome": "unknown",
                "_target": case["target"],
            }
            actual[case["intent"]] += 1
            time.sleep(0.04 + random.Random(campaign["seed"] + len(observed)).random() * 0.08)
    evidence = _verify_sources(lab, observed)
    with (output / "pending-evidence.jsonl").open("x") as stream:
        for row in evidence:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    (output / "pending-evidence.jsonl").chmod(0o600)
    result = {
        "format_version": 1,
        "status": "CAPTURE_VERIFIED_SEMANTIC_REVIEW_PENDING",
        "plan_sha256": checksum,
        "plan_file_sha256": file_sha256(Path(plan_dir) / "plan.json"),
        "owned_lab_marker_sha256": file_sha256(lab / "owned-lab.json"),
        "pending_evidence_sha256": file_sha256(output / "pending-evidence.jsonl"),
        "observed_distinct_request_ids": len(evidence),
        "captured_nginx_and_student": len(evidence),
        "planned_intent_counts": dict(actual),
        "application_workload_401": sum(
            row["status_code"] == 401
            for row in evidence
            if row["case_id"].startswith(
                ("catalog_", "hard_negative_", "sqli_", "xss_", "path_traversal_", "cmd_injection_")
            )
        ),
        "executed_development_campaigns": len(plan["campaigns"]),
        "independent_environments": 1,
        "new_independently_reviewed_benign": 0,
        "new_independently_reviewed_attack": 0,
        "new_training_admission": 0,
        "future_holdout": plan["future_holdout"],
        "pre_capture_approval": approval,
        "pre_capture_approval_preflight_sha256": (
            file_sha256(output / "preflight-approval.json") if approval else None
        ),
        "missing_evidence": [
            "Independent semantic review of the sealed protocol and actual request-bound captures",
            "Application oracle for any claim of exploit success; responses alone are insufficient",
            "Cross-source/role/template deduplication and a valid future independent evaluation environment",
            "Suricata flow parity if the deployed feature profile requires that source",
        ],
        "formal_training_permitted": False,
    }
    atomic_json(output / "report.json", result)
    return result


def verify_capture(plan_dir, lab_dir, capture_dir, collector_source):
    """Read back immutable plan, observer evidence and both local source logs."""
    plan = load_json(Path(plan_dir) / "plan.json")
    plan_sha = plan.pop("plan_sha256", None)
    # This verifier was appended after the first capture. Its frozen dispatch
    # prefix must still match the hash sealed before any request was sent.
    source_bytes = Path(collector_source).read_bytes()
    dispatch_prefix = source_bytes.split(b"\n\ndef verify_capture(", 1)[0]
    source_hashes = {
        hashlib.sha256(source_bytes).hexdigest(),
        hashlib.sha256(dispatch_prefix).hexdigest(),
    }
    if (
        plan_sha != digest(plan)
        or plan.get("collector_source_sha256") not in source_hashes
        or plan.get("future_holdout", {}).get("status") != "RESERVED_NOT_GENERATED_OR_CAPTURED"
    ):
        raise PipelineError("Campaign plan integrity or future holdout state changed")
    capture_dir = Path(capture_dir)
    report = load_json(capture_dir / "report.json")
    ledger = capture_dir / "pending-evidence.jsonl"
    if (
        report.get("plan_sha256") != plan_sha
        or report.get("plan_file_sha256") != file_sha256(Path(plan_dir) / "plan.json")
        or report.get("pending_evidence_sha256") != file_sha256(ledger)
        or report.get("new_training_admission") != 0
        or report.get("formal_training_permitted") is not False
    ):
        raise PipelineError("Capture report integrity or pending admission state changed")
    if plan.get("case_profile") == "gt-pilot-v1":
        preflight_path = capture_dir / "preflight-approval.json"
        preflight = load_json(preflight_path)
        approval = report.get("pre_capture_approval") or {}
        if (
            report.get("pre_capture_approval_preflight_sha256") != file_sha256(preflight_path)
            or preflight.get("status") != "SIGNED_PROTOCOL_VERIFIED_BEFORE_REQUEST_DISPATCH"
            or preflight.get("plan_sha256") != plan_sha
            or preflight.get("approval_file_sha256") != approval.get("approval_file_sha256")
            or preflight.get("reviewer_public_key_sha256")
            != approval.get("reviewer_public_key_sha256")
        ):
            raise PipelineError("GT pilot preflight approval provenance changed")
    expected = {
        (campaign["campaign_id"], case["case_id"]): case
        for campaign in plan["campaigns"]
        for case in campaign["cases"]
    }
    observed = {}
    with ledger.open("rb") as stream:
        for line in stream:
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Invalid pending evidence line")
            row = json.loads(line)
            key = (row.get("campaign_id"), row.get("case_id"))
            spec = expected.get(key)
            rid = row.get("request_id")
            if (
                spec is None
                or key in observed
                or not isinstance(rid, str)
                or row.get("plan_sha256") != plan_sha
                or row.get("target_sha256") != spec["target_sha256"]
                or row.get("http_method") != spec["http_method"]
                or row.get("planned_intent") != spec["planned_intent"]
                or row.get("planned_family") != spec["attack_family"]
                or row.get("intent_label_from_plan") != int(spec["planned_intent"] == "attack")
                or row.get("capture_verified") is not True
                or row.get("review_status") != "pending_independent_semantic_review"
                or row.get("training_eligible") is not False
                or row.get("exploit_outcome") != "unknown"
            ):
                raise PipelineError("Evidence row does not match the precommitted pending plan")
            observed[key] = row
    if set(observed) != set(expected) or len({r["request_id"] for r in observed.values()}) != len(
        expected
    ):
        raise PipelineError("Missing or duplicate request-bound evidence")
    ids = {r["request_id"] for r in observed.values()}
    lab = Path(lab_dir)
    nginx_path, student_path = lab / "access-lab.log", lab / "student-audit.log"
    nginx = _source_lines(nginx_path, ids)
    student = _source_lines(student_path, ids)
    nginx_sha, student_sha = file_sha256(nginx_path), file_sha256(student_path)
    if report.get("observed_distinct_request_ids") != len(ids) or report.get(
        "captured_nginx_and_student"
    ) != len(ids):
        raise PipelineError("Capture report count disagrees with request evidence")
    for row in observed.values():
        rid = row["request_id"]
        if len(nginx[rid]) != 1 or len(student[rid]) != 1:
            raise PipelineError("Capture source request ID is missing or duplicated")
        source = row["source_evidence"]
        n, s = nginx[rid][0][0], student[rid][0][0]
        if (
            source["nginx_file_sha256"] != nginx_sha
            or source["student_file_sha256"] != student_sha
            or source["nginx_access_line_sha256"] != nginx[rid][0][1]
            or source["student_audit_line_sha256"] != student[rid][0][1]
            or source["nginx_timestamp"] != n.get("timestamp")
            or source["student_timestamp"] != s.get("timestamp")
            or row.get("source_count") != 2
        ):
            raise PipelineError("Source log changed after request-bound capture")
        target = str(n.get("uri_path") or "")
        if n.get("query_string"):
            target += "?" + n["query_string"]
        if (
            n.get("http_method") != row["http_method"]
            or s.get("http_method") != row["http_method"]
            or n.get("status") != row["status_code"]
            or s.get("status_code") != row["status_code"]
            or s.get("uri_path") != n.get("uri_path")
            or hashlib.sha256(target.encode()).hexdigest() != row["target_sha256"]
        ):
            raise PipelineError("Correlated HTTP evidence disagrees with captured request")
        try:
            clocks = [
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                for value in (row["timestamp_utc"], n["timestamp"], s["timestamp"])
            ]
            if any(clock.tzinfo is None for clock in clocks):
                raise ValueError
            delta = (max(clocks) - min(clocks)).total_seconds()
        except (KeyError, TypeError, ValueError):
            raise PipelineError("Correlated request timestamps lack a common timezone") from None
        if delta > 5:
            raise PipelineError("Correlated request clocks differ by more than 5 seconds")
    return {
        "status": "CAPTURE_INTEGRITY_REVERIFIED_ADMISSION_PENDING",
        "request_ids": len(ids),
        "campaigns": len(plan["campaigns"]),
        "source_logs_per_request": 2,
        "new_training_admission": 0,
    }


def audit_capture_set(specs, output, historical_student_logs=()):
    """Count physical request IDs across development captures without approving labels."""
    from idps_ai.data.http_curation import require_development_source

    if not 2 <= len(specs) <= 32:
        raise PipelineError("Capture lineage audit needs 2–32 development captures")
    ids, targets, campaigns = set(), Counter(), set()
    captures = []
    for plan_dir, lab_dir, capture_dir, collector_source in specs:
        for path in (plan_dir, lab_dir, capture_dir, collector_source):
            require_development_source(path)
        verified = verify_capture(plan_dir, lab_dir, capture_dir, collector_source)
        current_ids = set()
        current_campaigns = set()
        with (Path(capture_dir) / "pending-evidence.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                rid = row["request_id"]
                if rid in ids:
                    raise PipelineError("Request ID repeats across capture runs")
                ids.add(rid)
                current_ids.add(rid)
                targets[row["target_sha256"]] += 1
                current_campaigns.add(row["campaign_id"])
        if len(current_ids) != verified["request_ids"]:
            raise PipelineError("Capture lineage count changed during readback")
        campaigns.update(current_campaigns)
        captures.append(
            {
                "capture_report_sha256": file_sha256(Path(capture_dir) / "report.json"),
                "pending_evidence_sha256": file_sha256(
                    Path(capture_dir) / "pending-evidence.jsonl"
                ),
                "request_ids": len(current_ids),
                "campaign_ids": len(current_campaigns),
            }
        )
    historical = []
    historical_ids = set()
    historical_collisions = 0
    for path in historical_student_logs:
        require_development_source(path)
        path = Path(path)
        current = set()
        with path.open("rb") as stream:
            while line := stream.readline(65537):
                if len(line) > 65536 or not line.endswith(b"\n"):
                    raise PipelineError("Invalid historical Student audit line")
                try:
                    rid = json.loads(line).get("request_id")
                except (ValueError, UnicodeError, AttributeError):
                    raise PipelineError("Invalid historical Student JSONL") from None
                if rid is None:
                    continue
                if not isinstance(rid, str) or not rid:
                    raise PipelineError("Invalid historical Student request ID")
                if rid in current:
                    raise PipelineError("Repeated request ID inside historical Student log")
                current.add(rid)
        historical_collisions += len(current & (historical_ids | ids))
        historical_ids.update(current)
        historical.append(
            {"file_sha256": file_sha256(path), "student_log_request_ids": len(current)}
        )
    result = {
        "format_version": 1,
        "status": (
            "CROSS_RUN_ID_COLLISION_REVIEW_REQUIRED"
            if historical_collisions
            else "DEVELOPMENT_CAPTURE_IDS_DISTINCT_NO_TRAINING_ADMISSION"
        ),
        "captures": captures,
        "physical_request_ids_observed": len(ids),
        "distinct_campaign_ids": len(campaigns),
        "distinct_target_hashes": len(targets),
        "repeated_target_observations": sum(n - 1 for n in targets.values()),
        "unsealed_historical_student_logs": historical,
        "historical_student_ids_scanned": len(historical_ids),
        "cross_run_id_collisions": historical_collisions,
        "independently_reviewed_benign": 0,
        "independently_reviewed_attack": 0,
        "training_admission": 0,
        "limits": "Only supplied development captures and explicitly supplied unsealed Student logs are compared by request ID. Historical log IDs may include setup events and are not added to training-request counts. Repeated targets are real separate HTTP requests, not new behavior templates. The sealed historical cohort is untouched, so the full 75,150-request corpus is not globally deduplicated by this audit; semantic labels and physical request provenance still need independent review.",
    }
    output = new_destination(output)
    output.mkdir(mode=0o700)
    atomic_json(output / "report.json", result)
    return result


def load_three_source_review_evidence(three_source_dir, capture_dir, request_count):
    """Read a pinned three-source ledger without treating sensor alerts as labels."""
    three_source_dir = Path(three_source_dir)
    report = load_json(three_source_dir / "report.json")
    ledger = three_source_dir / "three-source-evidence.jsonl"
    if (
        report.get("status") != "THREE_SOURCE_CORRELATED_DEVELOPMENT_ONLY"
        or report.get("request_count") != request_count
        or report.get("source_count_per_request") != 3
        or report.get("training_admission") != 0
        or report.get("capture_report_sha256") != file_sha256(Path(capture_dir) / "report.json")
        or report.get("three_source_evidence_sha256") != file_sha256(ledger)
        or report.get("pcap_sha256") != file_sha256(three_source_dir.parent / "lab/traffic.pcap")
        or report.get("eve_sha256") != file_sha256(three_source_dir.parent / "eve/eve.json")
    ):
        raise PipelineError("Three-source review evidence is stale or incomplete")
    rows = {}
    with ledger.open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Invalid three-source review evidence line")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid three-source review evidence JSONL") from None
            rid = row.get("request_id")
            if (
                not isinstance(rid, str)
                or rid in rows
                or row.get("source_count") != 3
                or row.get("lab_nginx_eve_numeric_projection_equal") is not True
                or row.get("training_eligible") is not False
                or row.get("intent") != "unknown"
                or row.get("label") is not None
                or not isinstance(row.get("flow_record_sha256"), list)
                or not row["flow_record_sha256"]
            ):
                raise PipelineError("Three-source review evidence is ambiguous")
            rows[rid] = row
    if len(rows) != request_count:
        raise PipelineError("Three-source review evidence misses requests")
    return rows


def verify_blind_queue(
    plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir=None
):
    """Recheck every unresolved reviewer item against immutable capture evidence."""
    verified = verify_capture(plan_dir, lab_dir, capture_dir, collector_source)
    capture_dir, review_dir = Path(capture_dir), Path(review_dir)
    capture_report = load_json(capture_dir / "report.json")
    review_report = load_json(review_dir / "report.json")
    queue = review_dir / "blind-review.jsonl"
    if bool(three_source_dir) != bool(review_report.get("three_source_report_sha256")):
        raise PipelineError("Blind review three-source binding is missing")
    three_source = None
    if three_source_dir:
        three_source_dir = Path(three_source_dir)
        if review_report["three_source_report_sha256"] != file_sha256(
            three_source_dir / "report.json"
        ):
            raise PipelineError("Blind review three-source report changed")
        three_source = load_three_source_review_evidence(
            three_source_dir, capture_dir, verified["request_ids"]
        )
    if (
        review_report.get("plan_sha256") != capture_report["plan_sha256"]
        or review_report.get("capture_report_sha256") != file_sha256(capture_dir / "report.json")
        or review_report.get("queue_sha256") != file_sha256(queue)
        or review_report.get("approved_benign") != 0
        or review_report.get("approved_attack") != 0
        or review_report.get("new_training_admission") != 0
    ):
        raise PipelineError("Blind review report is stale or no longer pending")
    with (capture_dir / "pending-evidence.jsonl").open() as stream:
        pending = {row["request_id"]: row for row in (json.loads(line) for line in stream)}
    seen = set()
    with queue.open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Invalid blind review queue line")
            row = json.loads(line)
            rid = row.get("request_id")
            source = pending.get(rid)
            expected_key = hashlib.sha256(
                (capture_report["plan_sha256"] + ":" + str(rid)).encode()
            ).hexdigest()
            eve = three_source.get(rid) if three_source is not None else None
            expected_hashes = (
                {
                    "nginx": source["source_evidence"]["nginx_access_line_sha256"],
                    "student": source["source_evidence"]["student_audit_line_sha256"],
                }
                if source is not None
                else None
            )
            if eve is not None:
                expected_hashes["eve_http"] = eve["eve_http_line_sha256"]
            if (
                source is None
                or (three_source is not None and eve is None)
                or rid in seen
                or row.get("event_key") != expected_key
                or row.get("campaign_id") != source["campaign_id"]
                or row.get("timestamp_utc") != source["timestamp_utc"]
                or row.get("http_method") != source["http_method"]
                or row.get("source_line_sha256") != expected_hashes
                or row.get("flow_record_sha256")
                != (eve["flow_record_sha256"] if eve is not None else None)
                or (eve is not None and eve.get("campaign_id") != source["campaign_id"])
                or (eve is not None and eve.get("nginx_line_sha256") != expected_hashes["nginx"])
                or (
                    eve is not None and eve.get("student_line_sha256") != expected_hashes["student"]
                )
                or row.get("intent") != "unknown"
                or row.get("label") is not None
                or row.get("attack_family") is not None
                or row.get("exploit_outcome") != "unknown"
                or row.get("review_status") != "pending"
                or row.get("training_eligible") is not False
                or row.get("reviewer_id") is not None
                or row.get("semantic_evidence_sha256") is not None
                or row.get("application_oracle_sha256") is not None
            ):
                raise PipelineError("Blind reviewer item does not match pending capture")
            seen.add(rid)
    if len(seen) != verified["request_ids"] or review_report.get("requests") != len(seen):
        raise PipelineError("Blind review queue does not cover every captured request")
    return {
        "status": "BLIND_QUEUE_REVERIFIED_NO_LABELS_APPROVED",
        "requests": len(seen),
        "approved_benign": 0,
        "approved_attack": 0,
        "training_admission": 0,
    }


def verify_three_source_capture(plan_dir, lab_dir, capture_dir, eve_dir, collector_source, output):
    """Bind real EVE HTTP/flow to pending lab requests; never infer labels."""
    from idps_ai.data.http_curation import require_development_source
    from idps_ai.data.privacy import safe_route
    from idps_ai.data.query_numeric import project_query
    from idps_ai.data.readers import eve_request_id

    for path in (plan_dir, lab_dir, capture_dir, eve_dir, collector_source):
        require_development_source(path)
    verified = verify_capture(plan_dir, lab_dir, capture_dir, collector_source)
    lab_dir, capture_dir, eve_dir = map(Path, (lab_dir, capture_dir, eve_dir))
    pcap = lab_dir / "traffic.pcap"
    pcap_manifest = load_json(lab_dir / "pcap-manifest.json")
    decode = load_json(eve_dir / "decode-manifest.json")
    eve_path = eve_dir / "eve.json"
    marker = load_json(lab_dir / "owned-lab.json")
    if (
        pcap_manifest.get("pcap_sha256") != file_sha256(pcap)
        or pcap_manifest.get("evidence_capture_report_sha256")
        != file_sha256(capture_dir / "report.json")
        or decode.get("status") != "PASS"
        or decode.get("input_profile") != "safe_query_numeric_v2"
        or decode.get("pcap_sha256") != pcap_manifest["pcap_sha256"]
        or decode.get("eve_sha256") != file_sha256(eve_path)
        or marker.get("ai_input_profile") != pcap_manifest.get("query_profile")
    ):
        raise PipelineError("PCAP/EVE/capture provenance mismatch")
    plan = load_json(Path(plan_dir) / "plan.json")
    sources = {c["campaign_id"]: c["source_ip"] for c in plan["campaigns"]}
    with (capture_dir / "pending-evidence.jsonl").open() as stream:
        pending = {r["request_id"]: r for r in (json.loads(line) for line in stream)}
    if len(pending) != verified["request_ids"]:
        raise PipelineError("Pending request IDs changed during EVE correlation")
    nginx = _source_lines(lab_dir / "access-lab.log", set(pending))
    masked_nginx = _source_lines(lab_dir / "access.log", set(pending))
    http, flows = defaultdict(list), defaultdict(list)
    with eve_path.open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Oversized or partial redacted EVE line")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid redacted EVE JSONL") from None
            sha = hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()
            if row.get("event_type") == "http":
                headers = (row.get("http") or {}).get("response_headers") or []
                rid = eve_request_id(row.get("http") or {})
                if rid in pending and any(
                    isinstance(h, dict)
                    and str(h.get("name", "")).lower() == "x-request-id"
                    and h.get("value") == rid
                    for h in headers
                ):
                    http[rid].append((row, sha))
            elif row.get("event_type") == "flow":
                flows[row.get("flow_id")].append((row, sha))
    evidence = []
    numeric_projection_mismatches = 0
    max_http_clock_delta = 0.0
    max_flow_emission_lag = 0.0
    for rid, expected in pending.items():
        if len(http[rid]) != 1:
            raise PipelineError("EVE HTTP request ID missing or ambiguous")
        row, eve_sha = http[rid][0]
        h = row.get("http") or {}
        n = nginx[rid][0][0]
        if len(masked_nginx[rid]) != 1:
            raise PipelineError("Masked edge Nginx request ID missing or ambiguous")
        m = masked_nginx[rid][0][0]
        if (
            m.get("query_string") is not None
            or m.get("http_method") != expected["http_method"]
            or int(m.get("status", -1)) != expected["status_code"]
            or m.get("uri_path") != n.get("uri_path")
        ):
            raise PipelineError("Masked edge Nginx view disagrees with private request")
        target = n["uri_path"] + ("?" + n["query_string"] if n.get("query_string") else "")
        projection_match = row.get("ai_query_numeric") == project_query(target, version=2)
        numeric_projection_mismatches += not projection_match
        flow_id = row.get("flow_id")
        try:
            status = int(h.get("status"))
            clocks = [
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                for value in (expected["timestamp_utc"], row["timestamp"])
            ]
            if any(clock.tzinfo is None for clock in clocks):
                raise ValueError
            delta = abs((clocks[1] - clocks[0]).total_seconds())
        except (ValueError, TypeError, KeyError):
            raise PipelineError("EVE HTTP status or timestamp is invalid") from None
        if (
            h.get("http_method") != expected["http_method"]
            or status != expected["status_code"]
            or row.get("src_ip") != sources[expected["campaign_id"]]
            or row.get("dest_port") != 18881
            or h.get("url") != safe_route(n["uri_path"])
            or delta > 5
            or flow_id is None
            or not flows[flow_id]
        ):
            raise PipelineError("EVE HTTP/flow disagrees with the request-bound capture")
        try:
            flow_lags = [
                (
                    datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
                    - clocks[1]
                ).total_seconds()
                for item, _ in flows[flow_id]
            ]
        except (KeyError, TypeError, ValueError):
            raise PipelineError("EVE flow emission timestamp is invalid") from None
        if any(lag < 0 for lag in flow_lags):
            raise PipelineError("EVE flow arrived before its HTTP event")
        max_http_clock_delta = max(max_http_clock_delta, delta)
        max_flow_emission_lag = max(max_flow_emission_lag, *flow_lags)
        evidence.append(
            {
                "request_id": rid,
                "campaign_id": expected["campaign_id"],
                "nginx_line_sha256": expected["source_evidence"]["nginx_access_line_sha256"],
                "student_line_sha256": expected["source_evidence"]["student_audit_line_sha256"],
                "eve_http_line_sha256": eve_sha,
                "flow_record_sha256": [sha for _, sha in flows[flow_id]],
                "client_timestamp": expected["timestamp_utc"],
                "eve_timestamp": row["timestamp"],
                "eve_flow_available_at": [item["timestamp"] for item, _ in flows[flow_id]],
                "source_count": 3,
                "lab_nginx_eve_numeric_projection_equal": projection_match,
                "intent": "unknown",
                "label": None,
                "exploit_outcome": "unknown",
                "training_eligible": False,
            }
        )
    output = new_destination(output)
    output.mkdir(mode=0o700)
    ledger = output / "three-source-evidence.jsonl"
    with ledger.open("x") as stream:
        for row in evidence:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    ledger.chmod(0o600)
    result = {
        "format_version": 1,
        "status": (
            "THREE_SOURCE_CORRELATED_DEVELOPMENT_ONLY"
            if numeric_projection_mismatches == 0
            else "THREE_SOURCE_CORRELATED_NUMERIC_PARITY_GAP"
        ),
        "request_count": len(evidence),
        "source_count_per_request": 3,
        "masked_nginx_query_null_requests": len(evidence),
        "lab_input_profile": marker["ai_input_profile"],
        "offline_eve_input_profile": decode["input_profile"],
        "offline_visibility_status": (
            "LAB_MASKED_EDGE_AND_EVE_V2_BOUND"
            if marker["ai_input_profile"] == decode["input_profile"]
            else "LAB_PROFILE_MARKER_GAP"
        ),
        "lab_nginx_eve_numeric_projection_mismatches": numeric_projection_mismatches,
        "max_client_to_eve_http_delta_seconds": max_http_clock_delta,
        "max_eve_http_to_flow_emission_seconds": max_flow_emission_lag,
        "pcap_sha256": pcap_manifest["pcap_sha256"],
        "eve_sha256": decode["eve_sha256"],
        "capture_report_sha256": file_sha256(capture_dir / "report.json"),
        "three_source_evidence_sha256": file_sha256(ledger),
        "independently_reviewed_benign": 0,
        "independently_reviewed_attack": 0,
        "training_admission": 0,
        "flow_causality": "Flow records are evidence only; their values are unavailable to per-request inference until the sensor actually emits them.",
        "feature_visibility": (
            "Masked lab Nginx and offline EVE v2 are request-bound; live production sensor and end-to-end 207-feature parity remain untested."
            if marker["ai_input_profile"] == decode["input_profile"]
            else "Private lab Nginx and EVE profiles differ; not certified as a formal 207-feature training profile."
        ),
    }
    atomic_json(output / "report.json", result)
    return result
