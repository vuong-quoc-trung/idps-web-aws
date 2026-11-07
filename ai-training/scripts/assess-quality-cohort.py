#!/usr/bin/env python3
"""Receipt re-verification, conservative role audit and calibration-only diagnostics.

Prospective scores are never evaluated here. Human review is not synthesized.
"""

import argparse
import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from scipy.stats import beta
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.safe_content import symbolic_request
from idps_ai.mvp_inference import ResearchMVP

ROOT = Path(__file__).resolve().parents[2]


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def interval(k, n):
    if not n:
        return None
    return [
        0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1)),
        1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k)),
    ]


def recover_juice(root, case, response, status):
    try:
        parsed = json.loads(response)
    except ValueError:
        parsed = None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    catalog = json.loads((root / "juice-catalog.json").read_text())
    rule = case["oracle"]
    ok = False
    outcome = "UNKNOWN"
    detail = {}
    if rule == "catalog_identity":
        ok = (
            isinstance(data, dict)
            and data.get("id") == case["expected"]
            and any(x["id"] == data["id"] and x["name"] == data["name"] for x in catalog)
        )
    elif rule == "catalog_search":
        expected = [
            x["id"]
            for x in catalog
            if case["expected"].lower()
            in (str(x["name"]) + " " + str(x.get("description", ""))).lower()
        ]
        ok = (
            isinstance(data, list)
            and all(isinstance(x, dict) and x.get("id") in {y["id"] for y in catalog} for x in data)
            and (bool(data) if expected else not data)
        )
    elif rule == "invalid_login_denied":
        ok = status == 401 and response == b"Invalid email or password."
    elif rule == "created_user":
        ok = (
            isinstance(data, dict)
            and isinstance(data.get("id"), int)
            and data.get("email") == case["expected"]
        )
    elif rule == "admin_auth_bypass":
        before = json.loads((root / "juice-challenge-before.json").read_text())
        after = json.loads((root / "juice-challenge-after.json").read_text())
        auth = parsed.get("authentication") if isinstance(parsed, dict) else None
        ok = bool(
            isinstance(auth, dict)
            and auth.get("umail") == "admin@juice-sh.op"
            and auth.get("token")
            and not before["solved"]
            and after["solved"]
            and before["id"] == after["id"]
        )
        detail = {
            "before_challenge_solved": before["solved"],
            "after_challenge_solved": after["solved"],
            "matching_challenge_id": before["id"] == after["id"],
        }
        if ok:
            outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
    elif rule == "search_injection":
        controls = [
            c
            for c in json.loads((root / "plan.json").read_text())["cases"]
            if c["oracle"] == "catalog_search" and c["expected"] == "zzn7missingitem"
        ]
        control = (
            json.loads(
                (
                    root / "juice/receipts" / controls[0]["request_id"] / "response-body.bin"
                ).read_bytes()
            )
            if len(controls) == 1
            else None
        )
        ok = (
            isinstance(data, list)
            and all(isinstance(x, dict) for x in data)
            and {x["id"] for x in catalog} <= {x.get("id") for x in data}
            and len(catalog) > 10
            and isinstance(control, dict)
            and control.get("data") == []
        )
        detail = {
            "returned_distinct_ids": len({x.get("id") for x in data})
            if isinstance(data, list)
            else None,
            "catalog_size": len(catalog),
            "negative_control_empty": isinstance(control, dict) and control.get("data") == [],
        }
        if ok:
            outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
    return {
        **case,
        "intent": case["intent"] if case["intent"] == "ATTACK_ATTEMPT" or ok else "UNKNOWN",
        "outcome": outcome,
        "semantic_oracle_matched": ok,
        "oracle_detail": detail,
        "response_status": status,
        "review_status": "REVIEW_PENDING",
        "independent_human_verified": False,
        "session_group": sha("stateless-juice-" + case["role"]),
        "oracle_recovery": "SAVED_RECEIPTS_CATALOG_AND_CHALLENGE_SNAPSHOTS_RECOMPUTED",
    }


def recover(root):
    plan = json.loads((root / "plan.json").read_text())
    assert digest({k: v for k, v in plan.items() if k != "plan_sha256"}) == plan["plan_sha256"]
    for name, expected in plan["helper_sha256"].items():
        assert file_sha256(Path(__file__).with_name(name + ".py")) == expected
    if (root / "collector-source.py").exists():
        assert file_sha256(root / "collector-source.py") == plan["source_sha256"]
    complete = (
        json.loads((root / "capture.json").read_text())
        if (root / "capture.json").is_file()
        else None
    )
    saved = {o["request_id"]: o for o in complete["observations"]} if complete else {}
    spec = importlib.util.spec_from_file_location(
        "p0", ROOT / "ai-training/scripts/p0-dvwa-capture.py"
    )
    p0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p0)
    rows = []
    for case in plan["cases"]:
        base = root / case["environment"] / "receipts" / case["request_id"]
        if not (base / "receipt.json").exists():
            continue
        receipt = json.loads((base / "receipt.json").read_text())
        headers = json.loads((base / "request-headers.json").read_text())
        returned = json.loads((base / "response-headers.json").read_text())
        body = (base / "request-body.bin").read_bytes()
        response = (base / "response-body.bin").read_bytes()
        assert (
            receipt["request_id"] == case["request_id"]
            and receipt["path"] == case["path"]
            and receipt["method"] == case["method"]
        )
        assert (
            body.decode() == case["body"]
            and sha(body) == receipt["request_body_sha256"]
            and digest(headers) == receipt["request_headers_sha256"]
            and sha(response) == receipt["response_sha256"]
            and digest(returned) == receipt["response_headers_sha256"]
        )
        if case["request_id"] in saved:
            label = dict(saved[case["request_id"]])
            assert label["response_sha256"] == sha(response)
            label["oracle_recovery"] = "COMPLETE_CAPTURE_REPORT_REVERIFIED"
        elif case["environment"] == "juice":
            label = recover_juice(root, case, response, receipt["status"])
        else:
            assert case["environment"] == "dvwa"
            text = response.decode(errors="replace")
            rule = case["oracle"]
            ok = False
            outcome = "UNKNOWN"
            detail = {}
            if rule in ["stored_literal", "unsafe_stored_reflection"]:
                blocks = re.findall(r'<div id="guestbook_comments">(.*?)</div>', text, re.S)
                ok = any(
                    "Name: LabReader<br />Message: " + case["expected"] + "<br />" in b
                    for b in blocks
                )
                detail = {
                    "persisted_guestbook_render_block": ok,
                    "direct_DB_count_originally_not_persisted": True,
                    "browser_execution_tested": False,
                }
                if rule == "unsafe_stored_reflection" and ok:
                    outcome = "UNSAFE_REFLECTION"
            elif rule == "user_identity_rows":
                # Exact expected DB snapshot was not retained in the interrupted capture.
                # Do not reconstruct an Oracle from its own answer and call it verified.
                detail = {"missing_expected_users_DB_snapshot": True}
                ok = False
            elif rule in ["blind_identity", "blind_injection"]:
                exists = "User ID exists in the database." in text
                missing = "User ID is MISSING from the database." in text
                ok = exists if case["expected"] else missing
                detail = {
                    "exists_message": exists,
                    "missing_message": missing,
                    "negative_control_in_same_role": "id99999 missing receipt required",
                }
                if rule == "blind_injection" and ok:
                    outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
            else:
                ok, detail = p0.oracle(case, response, {})
                if case["intent"] == "ATTACK_ATTEMPT" and ok:
                    outcome = (
                        "UNSAFE_REFLECTION"
                        if case["family"] == "xss"
                        else "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                    )
            label = {
                **case,
                "intent": case["intent"] if case["intent"] == "ATTACK_ATTEMPT" or ok else "UNKNOWN",
                "outcome": outcome,
                "semantic_oracle_matched": ok,
                "oracle_detail": detail,
                "response_status": receipt["status"],
                "review_status": "REVIEW_PENDING",
                "independent_human_verified": False,
                "session_group": sha(
                    headers.get("Cookie", "")
                    or "stateless-" + case["environment"] + "-" + case["role"]
                ),
                "oracle_recovery": "RECEIPT_RESPONSE_SOURCE_RECHECK; direct DB facts not fabricated",
            }
        label["raw_http_sha256"] = sha(
            canonical_bytes([case["method"], case["path"], case["body"]])
        )
        label["receipt_sha256"] = file_sha256(base / "receipt.json")
        label["receipt_file"] = str(base / "receipt.json")
        label["captured_at"] = receipt["captured_at"]
        label["receipt_matches"] = True
        label["_request"] = {
            "method": case["method"],
            "url": case["path"],
            "headers": "\r\n".join(f"{k}: {v}" for k, v in headers.items()),
            "body": case["body"],
        }
        rows.append(label)
    # Blind injection success is only valid with a request-bound false control.
    controls = [
        r
        for r in rows
        if r["oracle"] == "blind_identity"
        and r["expected"] is False
        and r["semantic_oracle_matched"]
    ]
    for r in rows:
        if r["oracle"] == "blind_injection" and not controls:
            r["outcome"] = "UNKNOWN"
            r["semantic_oracle_matched"] = False
    return plan, rows


def audit(roots, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    predictor = ResearchMVP("request-v2", cpus=1)
    spec = importlib.util.spec_from_file_location(
        "p0_eval", ROOT / "ai-training/scripts/p0-request-evaluate.py"
    )
    pv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pv)
    plans = []
    rows = []
    vectors = []
    contents = []
    for root in roots:
        plan, part = recover(root)
        plans.append(
            {
                "path": str(root / "plan.json"),
                "sha256": file_sha256(root / "plan.json"),
                "cases_planned": len(plan["cases"]),
                "receipts_recovered": len(part),
            }
        )
        for r in part:
            v, c, group, _ = pv.vector(predictor, r["_request"])
            vectors.append(v)
            contents.append(c)
            r["feature_view_sha256"] = sha(v.tobytes())
            r["safe_template_sha256"] = group
            r["endpoint_template"] = case_endpoint = re.sub(
                r"/\d+(?=/|$)", "/:id", urlsplit(r["path"]).path
            )
            r["workflow_template_sha256"] = sha(
                canonical_bytes([r["method"], case_endpoint, group])
            )
            rich, _ = pv.rich_request_v2(
                r["_request"]["method"],
                r["_request"]["url"],
                r["_request"]["headers"],
                r["_request"]["body"],
            )
            r["rich_template_sha256"] = sha(rich)
            rows.append(r)
    assert len({r["request_id"] for r in rows}) == len(rows)
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    groups = {}
    mixed = set()
    hashlabels = defaultdict(set)
    for i, r in enumerate(rows):
        for field in [
            "raw_http_sha256",
            "feature_view_sha256",
            "workflow_template_sha256",
            "rich_template_sha256",
            "session_group",
        ]:
            key = (field, r[field])
            if key in groups:
                union(i, groups[key])
            else:
                groups[key] = i
        if r["intent"] != "UNKNOWN":
            hashlabels[r["feature_view_sha256"]].add(r["intent"])
    mixed = {h for h, values in hashlabels.items() if len(values) > 1}
    # Exhaustive n<=100 pairwise near-content check, conservative cosine>=.995.
    near = []
    mat = np.asarray(contents, np.float32)
    sim = mat @ mat.T
    for i in range(len(rows)):
        for j in range(i):
            if (
                sim[i, j] >= 0.995
                and rows[i]["endpoint_template"] == rows[j]["endpoint_template"]
                and rows[i]["method"] == rows[j]["method"]
            ):
                union(i, j)
                if rows[i]["role"] != rows[j]["role"]:
                    near.append(
                        {
                            "left": rows[j]["request_id"],
                            "right": rows[i]["request_id"],
                            "cosine": float(sim[i, j]),
                        }
                    )
    component_roles = defaultdict(set)
    for i, r in enumerate(rows):
        component_roles[find(i)].add(r["role"])
    # Compare to exposed P0 + all frozen WAF selected model roles without opening holdouts.
    p0 = ROOT / "ai-training/.artifacts/p0_dvwa_20261105_1520/capture-final"
    _, _, old = pv.corpus(p0)
    old_raw = {
        sha(
            canonical_bytes(
                [
                    r["http_request"]["method"],
                    r["http_request"]["url"],
                    r["http_request"]["body"] or "",
                ]
            )
        )
        for r in old
    }
    old_workflow_groups = {
        sha(
            canonical_bytes(
                [
                    r["http_request"]["method"],
                    re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(r["http_request"]["url"]).path),
                    sha(
                        symbolic_request(
                            r["http_request"]["method"],
                            r["http_request"]["url"],
                            r["http_request"]["headers"],
                            r["http_request"]["body"],
                        )[0]
                    ),
                ]
            )
        )
        for r in old
    }
    old_groups = {
        sha(
            symbolic_request(
                r["http_request"]["method"],
                r["http_request"]["url"],
                r["http_request"]["headers"],
                r["http_request"]["body"],
            )[0]
        )
        for r in old
    }
    tensor = (
        ROOT
        / "ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz"
    )
    assert file_sha256(tensor) == "279dca7d03b38bb2092bf775762bfe68904eea131e0d1145a564de0f98441049"
    with np.load(tensor, allow_pickle=False) as data:
        roles = data["role"]
        assert set(roles.tolist()) <= {0, 1, 2}
        wafviews = {v.decode() for v in data["view"][roles == 0]}
        wafgroups = {v.decode() for v in data["group"][roles == 0]}
    for i, r in enumerate(rows):
        reasons = []
        if len(component_roles[find(i)]) > 1:
            reasons.append("CROSS_ROLE_CONNECTED_TEMPLATE_VIEW_NEAR_OR_SESSION")
        if r["feature_view_sha256"] in mixed:
            reasons.append("MIXED_INTENT_IDENTICAL_FROZEN_VIEW")
        if r["intent"] == "UNKNOWN":
            reasons.append("UNKNOWN_INTENT_OR_BENIGN_ORACLE")
        if r["feature_view_sha256"] in wafviews or r["rich_template_sha256"] in wafgroups:
            reasons.append("FROZEN_TRAIN_VIEW_OR_RICH_TEMPLATE_OVERLAP")
        r["exposed_P0_workflow_template_overlap"] = (
            r["workflow_template_sha256"] in old_workflow_groups
        )
        r["exposed_P0_raw_overlap"] = r["raw_http_sha256"] in old_raw
        r["exposed_P0_safe_template_overlap"] = r["safe_template_sha256"] in old_groups
        if r["role"] == "PROSPECTIVE_EVALUATION" and (
            r["exposed_P0_raw_overlap"] or r["exposed_P0_workflow_template_overlap"]
        ):
            reasons.append("EXPOSED_P0_OVERLAP_NOT_NEW_EVALUATION")
        r["eligibility_reasons"] = reasons
        r["eligible_in_declared_role"] = not reasons
        r["component"] = sha(str(find(i)))
        r.pop("_request", None)
    # Freeze role eligibility and vector fingerprints BEFORE reading model scores.
    payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    (output / "role-audit.jsonl").write_text(payload)
    np.savez_compressed(
        output / "feature-views.npz",
        x=np.asarray(vectors, np.float32),
        request_id=np.asarray([r["request_id"] for r in rows], dtype="S32"),
    )
    cal = [
        i
        for i, r in enumerate(rows)
        if r["role"] == "CALIBRATION" and r["intent"] == "BENIGN" and r["eligible_in_declared_role"]
    ]
    # Deduplicate calibration by exact frozen view, without choosing examples from scores.
    physical_calibration_rows = len(cal)
    unique = {rows[i]["feature_view_sha256"]: i for i in cal}
    cal = list(unique.values())
    protocol = {
        "schema_version": "cohort-analysis-protocol-1",
        "capture_plans": plans,
        "role_ledger_sha256": file_sha256(output / "role-audit.jsonl"),
        "feature_file_sha256": file_sha256(output / "feature-views.npz"),
        "code_sha256": file_sha256(__file__),
        "calibration_indices": cal,
        "calibration_method": "maximum finite score for n<100; strict> comparator; predeclared empirical1%budget; calibration only",
        "prospective_scores": "NOT_COMPUTED; no prospective data used for model selection or fitting",
        "primary_FPR_target": 0.01,
        "family_recall_targets": {
            k: 0.8 for k in ["sqli", "xss", "cmd_injection", "path_traversal"]
        },
        "training_budget": {"max_candidates": 1, "max_updates": 250, "max_epochs": 1},
        "review": "PENDING_INTERNAL_ORACLE_ONLY",
    }
    protocol["protocol_sha256"] = digest(protocol)
    atomic_json(output / "analysis-protocol.json", protocol)
    diagnostics = {}
    calibration = {"status": "BLOCKED_NO_ELIGIBLE_CALIBRATION", "threshold": None}
    allowed = [i for i, r in enumerate(rows) if r["role"] != "PROSPECTIVE_EVALUATION"]
    with threadpool_limits(limits=1):
        scores = {i: float(predictor.v2_model.predict(vectors[i][None])[0][0]) for i in allowed}
    if cal:
        threshold = max(scores[i] for i in cal)
        calibration = {
            "status": "RESEARCH_ONLY_LOW_SUPPORT",
            "threshold": threshold,
            "n_unique_views": len(cal),
            "physical_rows_before_view_dedup": physical_calibration_rows,
            "empirical_flags": 0,
            "descriptive_two_sided95_upper_FPR_if0": interval(0, len(cal))[1],
            "frozen_threshold_unchanged": predictor.v2_threshold,
            "independent_population_FPR": None,
        }
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        selected = [
            i for i in allowed if rows[i]["role"] == role and rows[i]["intent"] != "UNKNOWN"
        ]
        c = Counter()
        for i in selected:
            flag = scores[i] > predictor.v2_threshold
            attack = rows[i]["intent"] == "ATTACK_ATTEMPT"
            c[("T" if flag == attack else "F") + ("P" if flag else "N")] += 1
        diagnostics[role] = {
            "confusion_on_all_observed_known_internal_intents": dict(c),
            "rows": len(selected),
            "scope": "Exposed diagnostic, not independent evaluation and not restricted to leakage-safe eligible rows",
        }
    counts = Counter(r["intent"] for r in rows)
    eligible = Counter(r["role"] for r in rows if r["eligible_in_declared_role"])
    components = Counter(
        find(i)
        for i, r in enumerate(rows)
        if r["eligible_in_declared_role"] and r["role"] == "TRAIN"
    )
    report = {
        "schema_version": "quality-cohort-assessment-1",
        "physical_receipts": len(rows),
        "unique_request_ids": len(rows),
        "unique_method_URL_body": len({r["raw_http_sha256"] for r in rows}),
        "unique_frozen_feature_views": len({r["feature_view_sha256"] for r in rows}),
        "unique_safe_templates": len({r["safe_template_sha256"] for r in rows}),
        "intent_counts": dict(counts),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "per_environment": {
            env: dict(Counter(r["intent"] for r in rows if r["environment"] == env))
            for env in ["dvwa", "juice"]
        },
        "independent_human_verified": 0,
        "review_pending": len(rows),
        "formal_admitted": 0,
        "GLU207_eligible": 0,
        "Request_v2_recorded_input_compatible": len(rows),
        "eligible_declared_role_counts": dict(eligible),
        "training_independent_connected_groups": len(components),
        "mixed_intent_feature_views": len(mixed),
        "cross_role_near_pairs": len(near),
        "cross_role_component_rows": sum(
            len(component_roles[find(i)]) > 1 for i in range(len(rows))
        ),
        "exposed_P0_raw_overlaps": sum(r["exposed_P0_raw_overlap"] for r in rows),
        "exposed_P0_template_overlaps": sum(r["exposed_P0_safe_template_overlap"] for r in rows),
        "eligibility_reasons": dict(Counter(k for r in rows for k in r["eligibility_reasons"])),
        "calibration_only": calibration,
        "frozen_diagnostics": diagnostics,
        "prospective_scores_computed": 0,
        "training_started": False,
        "training_gate": "BLOCKED",
        "blockers": [
            "Few role-independent benign/positive groups after explicit leakage checks; no justified finite challenger fit yet",
            "Prospective target-family outcome support and per-environmentFPR precision incomplete; no independent review claim",
            "A historical exact-resume claim does not qualify a new representation run; no training supervisor launched",
        ],
        "next_task": "Collect one leakage-targeted, role-isolated cohort filling missing benignPOST/calibration and prospective family groups, using this role audit to exclude templates before sending requests",
        "limits": [
            "New requests are not equally many independent examples; session/template/near groups retained",
            "Interrupted DVWA direct DB counts not retained; five expected-user snapshot-dependent benign labels remainUNKNOWN",
            "Stored guestbook response blocks + frozen application source support persistence/reflection, not independent human or XSS execution",
            "Old WAF raw complete-request hashes not retained; no claim full raw or exhaustive cross-corpus near dedup",
            "No evaluation/heldout labels scored or used to choose thresholds; no Recall/FPR acceptance claim",
            "Recorded offline body/header inputs do not imply live worker body observability",
        ],
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    atomic_json(
        output / "review-package.json",
        {
            "status": "REVIEW_PENDING",
            "reviewer": None,
            "priority_ids": [
                r["request_id"]
                for r in rows
                if r["intent"] == "UNKNOWN"
                or r["outcome"] == "UNSAFE_REFLECTION"
                or r["feature_view_sha256"] in mixed
            ],
            "intent_outcome_review_are_separate": True,
            "private_receipt_ledger": "role-audit.jsonl",
            "automated_checks_not_independent_human_review": True,
        },
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "physical_receipts",
                    "unique_frozen_feature_views",
                    "intent_counts",
                    "eligible_declared_role_counts",
                    "mixed_intent_feature_views",
                    "calibration_only",
                    "training_gate",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    audit(a.capture, a.output)
