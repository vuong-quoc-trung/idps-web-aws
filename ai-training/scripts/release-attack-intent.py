#!/usr/bin/env python3
"""Versioned, receipt-bound derivative; never read sealed samples or select by scores."""

import argparse
import codecs
import importlib.util
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import CLASSES, atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import (
    VERSION,
    collision_groups,
    dataset_fingerprint,
    normalize_label,
    raw_key,
    read_receipt,
    runtime_request,
    validate_eligible_splits,
    validate_record,
    vector_hash,
    visibility_bounds,
)
from idps_ai.mvp_inference import ResearchMVP

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "ai-training/.artifacts"


def load(p):
    return json.loads(p.read_text())


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def unsealed_ledger(path, reserved):
    rows = []
    with path.open() as stream:
        for line in stream:
            role = re.search(r'"role"\s*:\s*"([A-Z_]+)"', line)
            if role and role[1] == "PROSPECTIVE_EVALUATION":
                # Only pre-existing opaque exclusion keys; never deserialize this row.
                for field in ["raw", "template", "rich", "view", "feature_view_sha256"]:
                    match = re.search(r'"' + field + r'"\s*:\s*"([a-f0-9]{64})"', line)
                    if match:
                        reserved[field].add(match[1])
                continue
            rows.append(json.loads(line))
    return rows


def evidence_sources(base):
    reserved = defaultdict(set)
    source = []
    bindings = {}
    for name in [
        "quality_lab_20261107/assessment-v2/role-audit.jsonl",
        "training_unblock_20261107/dataset-release-final-v2/private-role-ledger.jsonl",
    ]:
        p = ART / name
        bindings[str(p.relative_to(ROOT))] = file_sha256(p)
        for row in unsealed_ledger(p, reserved):
            row["_source"] = name
            row["_source_sha256"] = bindings[str(p.relative_to(ROOT))]
            source.append(row)
    # Exactly the two previously verified form-state calibration records.
    folder = ART / "final_training_unblock_20261107/security-calibration"
    p = folder / "capture.json"
    bindings[str(p.relative_to(ROOT))] = file_sha256(p)
    for x in load(p)["records"]:
        source.append(
            dict(
                x,
                environment="dvwa",
                family="benign",
                method="POST",
                path="/security.php",
                oracle="security_state_transition",
                role="CALIBRATION",
                session_group=digest(["security-calibration", file_sha256(p)]),
                workflow="security-state-form",
                receipt_file=str(folder / "receipts" / x["request_id"] / "receipt.json"),
                outcome="UNKNOWN",
                _source=str(p.relative_to(ART)),
                _source_sha256=file_sha256(p),
            )
        )
    pv = module("p0-request-evaluate")
    p0 = ART / "p0_dvwa_20261105_1520/capture-final"
    plan, cap, rows = pv.corpus(p0)
    cases = {c["request_id"]: c for c in plan["cases"]}
    observed = {o["request_id"]: o for o in cap["observations"]}
    bindings[str((p0 / "capture-report.json").relative_to(ROOT))] = file_sha256(
        p0 / "capture-report.json"
    )
    for r in rows:
        c = cases[r["request_id"]]
        o = observed[r["request_id"]]
        source.append(
            {
                **c,
                **o,
                "intent": r["lab_intent"],
                "outcome": r["outcome"],
                "role": "DEVELOPMENT",
                "environment": "dvwa",
                "session_group": digest(["P0_SINGLE_CAPTURE_SHARED_SESSION", plan["run_id"]]),
                "receipt_file": r["receipt_file"],
                "_source": "P0_EXPOSED_DEVELOPMENT",
                "_source_sha256": file_sha256(p0 / "capture-report.json"),
            }
        )
    fresh = base / "cohort/capture.json"
    bindings[str(fresh.relative_to(ROOT))] = file_sha256(fresh)
    cp = load(base / "cohort/plan.json")
    assert cp["plan_sha256"] == load(fresh)["plan_sha256"]
    assert cp["source_sha256"] == file_sha256(base / "capture-source.py")
    for x in load(fresh)["observations"]:
        source.append(
            {
                **x,
                "receipt_file": str(
                    base
                    / "cohort"
                    / x["environment"]
                    / "receipts"
                    / x["request_id"]
                    / "receipt.json"
                ),
                "_source": "NEW_FINITE_COHORT",
                "_source_sha256": file_sha256(fresh),
            }
        )
    assert len({r["request_id"] for r in source}) == len(source)
    return source, reserved, bindings


def oracle_recheck(old, req, receipt):
    """Replay compatible checks; unretained dependencies are not synthesized."""
    base = Path(old["receipt_file"]).parent
    response = (base / "response-body.bin").read_bytes()
    text = response.decode(errors="replace")
    matched = bool(old.get("oracle_matched", old.get("semantic_oracle_matched", False)))
    rule = old["oracle"]
    expected = old.get("expected")
    proof = "PRIOR_AUDIT_PLUS_BOUND_RECEIPT_RECHECK"
    if not matched:
        return False, "PRIOR_ORACLE_NOT_VERIFIED"
    if rule in {"stored_literal", "unsafe_stored_reflection"}:
        blocks = re.findall(r'<div id="guestbook_comments">(.*?)</div>', text, re.S)
        return any(
            "Name: LabReader<br />Message: " + expected + "<br />" in b for b in blocks
        ), "EXACT_GUESTBOOK_BLOCK_PLUS_PRIOR_PERSISTENCE_AUDIT"
    if rule == "security_state_transition":
        fc = module("final-calibration-capture")
        folder = base.parent
        before = folder / old["before_request_id"]
        after = folder / old["after_request_id"]
        read_receipt(before, request_id=old["before_request_id"])
        read_receipt(after, request_id=old["after_request_id"])
        return fc.selected((before / "response-body.bin").read_bytes()) == old[
            "before_level"
        ] != old["target"] and fc.selected((after / "response-body.bin").read_bytes()) == old[
            "target"
        ], "BOUND_BEFORE_AFTER_SECURITY_STATE"
    if old["environment"] == "juice":
        parsed = json.loads(response) if response.startswith(b"{") else {}
        data = parsed.get("data")
        if rule == "created_user":
            return isinstance(data, dict) and data.get("email") == expected and isinstance(
                data.get("id"), int
            ), "CREATED_ENTITY_RESPONSE_PLUS_PRIOR_ORACLE"
        if rule == "invalid_login_denied":
            return receipt[
                "status"
            ] == 401 and response == b"Invalid email or password.", "EXACT_AUTH_DENIAL_RESPONSE"
        if rule == "admin_auth_bypass":
            auth = parsed.get("authentication", {})
            return bool(
                auth.get("token") and auth.get("umail") == "admin@juice-sh.op"
            ), "AUTH_IDENTITY_RESPONSE_PLUS_PRIOR_CHALLENGE_TRANSITION"
        if rule == "feedback_create":
            return isinstance(data, dict) and data.get(
                "comment"
            ) == expected, "CREATED_FEEDBACK_RESPONSE_PLUS_PRIOR_PERSISTED_STATE_AUDIT"
        if rule == "captcha_arithmetic":
            return module("training-unblock-cohort").arithmetic_answer(parsed["captcha"]) == str(
                parsed["answer"]
            ), "ARITHMETIC_ORACLE_REPLAY"
        if rule in {"catalog_search", "catalog_identity", "catalog_list", "search_injection"}:
            return matched, proof + "_CATALOG_AND_CONTROL_CHECKED_IN_ORIGINAL_AUDIT"
    if rule == "transformed_canary":
        expected = (
            codecs.encode("UNBLOCK_FILE_CANARY", "rot_13")
            if expected == "rot13"
            else "UNBLOCK_FILE_CANARY".upper()
        )
        return expected in text, "PINNED_CANARY_TRANSFORM"
    d = module("p0-dvwa-capture")
    if "training_unblock_20261107" in str(base):
        d.CANARY = "UNBLOCK_FILE_CANARY"
    if old["_source"] == "P0_EXPOSED_DEVELOPMENT":
        users = load(ART / "p0_dvwa_20261105_1520/capture-final/plan.json")["users_oracle"]
    elif (ART / "training_unblock_20261107/campaign-capture-v2/dvwa-users-oracle.json").exists():
        users = load(ART / "training_unblock_20261107/campaign-capture-v2/dvwa-users-oracle.json")
    else:
        users = {}
    if rule in {
        "command_stdout_canary",
        "injected_sql_rows",
        "literal_name_reflection",
        "unsafe_reflection_only_no_browser_execution",
        "loopback_ping_result",
        "included_public_page",
        "included_private_canary",
        "user_identity_rows",
    }:
        return d.oracle(old, response, users)[0], "APPLICATION_RESPONSE_ORACLE_REPLAY"
    return matched, proof


def build(base, output):
    os.umask(0o077)
    output.mkdir(mode=0o700, exist_ok=False)
    plan = load(base / "release-plan.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert plan["source_sha256"]["ai-training/scripts/attack-intent-capture.py"] == file_sha256(
        base / "capture-source.py"
    )
    assert load(base / "preflight/preflight-result.json")["status"] == "PASS"
    sources, reserved, bindings = evidence_sources(base)
    pv = module("p0-request-evaluate")
    uc = module("training-unblock-cohort")
    frozen = ResearchMVP("request-v2", cpus=1)
    with np.load(
        ART / "final_training_unblock_20261107/dataset/train.npz", allow_pickle=False
    ) as d:
        admitted_train = set(d["ids"].astype(str))
    with np.load(
        ART / "final_training_unblock_20261107/dataset/calibration.npz", allow_pickle=False
    ) as d:
        admitted_cal = set(d["ids"].astype(str))
    rows = []
    full = []
    runtime = []
    requests = []
    for old in sources:
        req, receipt = read_receipt(Path(old["receipt_file"]).parent, request_id=old["request_id"])
        assert req["method"] == old["method"] and req["url"] == old["path"]
        if "body" in old:
            if old["oracle"] == "feedback_create":
                # Capture substituted a request-bound CAPTCHA; the planned body is a template.
                ancillary = Path(old["receipt_file"]).parents[3] / "ancillary" / old["request_id"]
                binding = load(ancillary / "binding.json")
                captcha = load(ancillary / "captcha-response.bin")
                assert binding["actual_body_sha256"] == file_sha256(
                    Path(old["receipt_file"]).parent / "request-body.bin"
                )
                assert binding["captcha_snapshot_sha256"] == file_sha256(
                    ancillary / "captcha-response.bin"
                )
                expected = json.loads(old["body"])
                expected["captchaId"] = captcha["captchaId"]
                expected["captcha"] = captcha["answer"]
                assert json.loads(req["body"]) == expected
            else:
                assert req["body"] == old["body"]
        verified, replay = oracle_recheck(old, req, receipt)
        original_outcome = old.get("outcome", "UNKNOWN")
        compatible_outcome = original_outcome
        if old["_source"] == "P0_EXPOSED_DEVELOPMENT" and verified:
            # P0 stores lowercase execution outcome; its XSS Oracle proves unsafe
            # reflection, with no browser execution. Keep the original value too.
            if old["family"] == "xss" and old["intent"] == "attack":
                compatible_outcome = "UNSAFE_REFLECTION"
            elif original_outcome == "succeeded":
                compatible_outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
        intent, outcome = normalize_label(old["intent"], compatible_outcome, verified)
        # A failed benign Oracle cannot establish a benign label. Attack provenance is distinct.
        if intent == "BENIGN_INTENT" and not verified:
            intent = "UNKNOWN_INTENT"
        a, _, _, av = pv.vector(frozen, req)
        projected = runtime_request(req)
        b, _, _, rv = pv.vector(frozen, projected)
        keys, _ = uc.keys(req, frozen, pv)
        reasons = []
        rid = old["request_id"]
        role = old["role"]
        fresh = old["_source"] == "NEW_FINITE_COHORT"
        if role == "TRAIN" and not fresh and rid not in admitted_train:
            reasons.append("PRIOR_TRAIN_ADMISSION_EXCLUDED")
        if role == "CALIBRATION" and not fresh and rid not in admitted_cal:
            reasons.append("PRIOR_CALIBRATION_ADMISSION_EXCLUDED")
        if intent == "UNKNOWN_INTENT":
            reasons.append("UNKNOWN_INTENT_NO_ORACLE_LABEL")
        if not verified:
            reasons.append("OUTCOME_ORACLE_UNVERIFIED")
        if (
            any(keys[k] in reserved[k] for k in ["raw", "template", "rich", "view"])
            or keys["view"] in reserved["feature_view_sha256"]
        ):
            reasons.append("OPAQUE_RESERVED_PROSPECTIVE_IDENTIFIER_OVERLAP")
        endpoint = re.sub(r"/\d+(?=/|$)", "/:id", urlsplit(req["url"]).path)
        row = dict(
            sample_id=digest([VERSION, rid]),
            dataset_version=VERSION,
            request_id=rid,
            environment=old["environment"],
            request_provenance=dict(
                receipt_file=old["receipt_file"],
                transaction_identity="OWNED_PROXY_RECEIPT",
                source=old["_source"],
                source_sha256=old["_source_sha256"],
                capture_time=receipt.get("captured_at"),
            ),
            workflow_group=old.get("workflow", old.get("campaign", old["oracle"])),
            session_group=old.get("session_group", digest([old["_source"], role])),
            campaign_group=old.get("campaign", old["_source"] + ":" + role),
            intent=intent,
            outcome=outcome,
            original_outcome=original_outcome,
            evidence_levels=(
                ["APPLICATION_ORACLE_VERIFIED"] if verified else ["AUTOMATED_CHECK_SUPPORTED"]
            )
            + ["REVIEW_PENDING"],
            label_source="Collector precommitted intent + internal application Oracle",
            review_status="PENDING",
            oracle_verified=verified,
            oracle_replay=replay,
            independent_human_verified=False,
            feature_compatibility=dict(
                frozen_request_v2_full=True,
                frozen_request_v2_runtime_emulated=True,
                live_delivery_verified=False,
                GLU207=False,
            ),
            split=role,
            declared_role=role,
            label_queue="UNKNOWN_REVIEW_PENDING"
            if intent == "UNKNOWN_INTENT"
            else "REVIEW_PENDING",
            family=old.get("family", "benign"),
            method=req["method"],
            endpoint_template=endpoint,
            checksums=dict(
                receipt=file_sha256(Path(old["receipt_file"])),
                raw=raw_key(req),
                template=keys["template"],
                full_view=vector_hash(a),
                runtime_view=vector_hash(b),
                rich=keys["rich"],
            ),
            missingness=dict(
                full=av,
                runtime=rv,
                body_lost_at_worker=bool(req["body"]),
                headers_selected_only=True,
                nginx_api_route_scope_matches=endpoint.startswith("/api/"),
            ),
            inclusion_exclusion_reasons=reasons,
            prior_exposure="NEW_PRECOMMITTED_UNSCORED_TRAIN_CAL"
            if fresh
            else "PREVIOUSLY_EXPOSED_OR_ADMITTED_ROLE",
            eligible_for_fit=False,
        )
        rows.append(row)
        full.append(a)
        runtime.append(b)
        requests.append(req)
    x = np.array(full, np.float32)
    xr = np.array(runtime, np.float32)
    # Same information loss, independent of a model or threshold: count mixed-label views.
    ambiguity = {}
    for name in ["full_view", "runtime_view"]:
        mixed = collision_groups(rows, name)
        ambiguity[name] = dict(
            groups=len(mixed),
            affected_rows=len({i for g in mixed for i in g}),
            counts=[
                dict(
                    size=len(g),
                    benign=sum(rows[i]["intent"] == "BENIGN_INTENT" for i in g),
                    attacks=sum(rows[i]["intent"] == "ATTACK_INTENT" for i in g),
                    families=dict(
                        Counter(
                            rows[i]["family"] for i in g if rows[i]["intent"] == "ATTACK_INTENT"
                        )
                    ),
                )
                for g in mixed
            ],
        )
        for g in mixed:
            for i in g:
                rows[i]["inclusion_exclusion_reasons"].append(
                    "OPPOSITE_INTENT_IDENTICAL_" + name.upper()
                )
    overlap = Counter()
    seen = defaultdict(list)
    for i, r in enumerate(rows):
        for kind in ["raw", "template", "full_view", "runtime_view"]:
            seen[(kind, r["checksums"][kind])].append(i)
        for kind in ["session_group", "campaign_group"]:
            seen[(kind, r[kind])].append(i)
    for (kind, _), indices in seen.items():
        if len({rows[i]["split"] for i in indices}) > 1:
            overlap[kind] += 1
            for i in indices:
                rows[i]["inclusion_exclusion_reasons"].append("CROSS_ROLE_" + kind.upper())
    near = 0
    # Exhaustive bounded audit on all allowed rows; no sealed input matrices.
    for matrix, name in [(x, "FULL"), (xr, "RUNTIME")]:
        sim = matrix[:, 76:].astype(np.float64) @ matrix[:, 76:].astype(np.float64).T
        for i in range(len(rows)):
            for j in range(i):
                if (
                    rows[i]["split"] != rows[j]["split"]
                    and rows[i]["method"] == rows[j]["method"]
                    and rows[i]["endpoint_template"] == rows[j]["endpoint_template"]
                    and sim[i, j] >= 0.995 - 1e-7
                ):
                    near += 1
                    for k in [i, j]:
                        rows[k]["inclusion_exclusion_reasons"].append("CROSS_ROLE_NEAR_" + name)
    duplicate_seen = set()
    for i in sorted(range(len(rows)), key=lambda i: rows[i]["sample_id"]):
        r = rows[i]
        key = (r["split"], r["checksums"]["full_view"], r["checksums"]["runtime_view"])
        if key in duplicate_seen:
            r["inclusion_exclusion_reasons"].append("WITHIN_ROLE_DUPLICATE_VIEW")
        duplicate_seen.add(key)
        r["inclusion_exclusion_reasons"] = sorted(set(r["inclusion_exclusion_reasons"]))
        r["eligible_for_fit"] = r["split"] == "TRAIN" and not r["inclusion_exclusion_reasons"]
        validate_record(r)
    validate_eligible_splits(rows)
    role_report = {}
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        ix = [i for i, r in enumerate(rows) if r["split"] == role]
        eligible = [i for i in ix if not rows[i]["inclusion_exclusion_reasons"]]
        y = np.array(
            [
                0
                if rows[i]["intent"] == "BENIGN_INTENT"
                else CLASSES.index(rows[i]["family"])
                if rows[i]["intent"] == "ATTACK_INTENT"
                else -1
                for i in ix
            ],
            np.int64,
        )
        np.savez(
            output / (role.lower() + ".npz"),
            full=x[ix],
            runtime=xr[ix],
            y=y,
            eligible=np.array([i in eligible for i in ix]),
            ids=np.array([rows[i]["sample_id"] for i in ix]),
        )
        role_report[role] = dict(
            receipted_rows=len(ix),
            intent=dict(Counter(rows[i]["intent"] for i in ix)),
            outcome=dict(Counter(rows[i]["outcome"] for i in ix)),
            Oracle_verified=sum(rows[i]["oracle_verified"] for i in ix),
            environments=dict(Counter(rows[i]["environment"] for i in ix)),
            workflow_categories=len({rows[i]["workflow_group"] for i in ix}),
            session_components=len({rows[i]["session_group"] for i in ix}),
            unique_full_views=len({rows[i]["checksums"]["full_view"] for i in ix}),
            unique_runtime_views=len({rows[i]["checksums"]["runtime_view"] for i in ix}),
            strict_eligible_rows=len(eligible),
            strict_eligible_intents=dict(Counter(rows[i]["intent"] for i in eligible)),
            families=dict(
                Counter(rows[i]["family"] for i in ix if rows[i]["intent"] == "ATTACK_INTENT")
            ),
            strict_unique_benign_views=len(
                {
                    rows[i]["checksums"]["runtime_view"]
                    for i in eligible
                    if rows[i]["intent"] == "BENIGN_INTENT"
                }
            ),
            strict_benign_GET_workflows=len(
                {
                    rows[i]["workflow_group"]
                    for i in eligible
                    if rows[i]["intent"] == "BENIGN_INTENT" and rows[i]["method"] == "GET"
                }
            ),
            strict_benign_POST_workflows=len(
                {
                    rows[i]["workflow_group"]
                    for i in eligible
                    if rows[i]["intent"] == "BENIGN_INTENT" and rows[i]["method"] == "POST"
                }
            ),
            strict_family_views={
                family: len(
                    {
                        rows[i]["checksums"]["runtime_view"]
                        for i in eligible
                        if rows[i]["intent"] == "ATTACK_INTENT" and rows[i]["family"] == family
                    }
                )
                for family in ["sqli", "xss", "cmd_injection", "path_traversal"]
            },
        )
    (output / "records.jsonl").write_text(
        "".join(
            json.dumps(r, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: r["sample_id"])
        )
    )
    (output / "human-review-queue.jsonl").write_text(
        "".join(
            json.dumps(
                dict(
                    sample_id=r["sample_id"],
                    receipt=r["request_provenance"]["receipt_file"],
                    reviewer=None,
                    decision=None,
                    reviewed_at=None,
                )
            )
            + "\n"
            for r in rows
        )
    )
    atomic_json(
        output / "protected-prospective-reference.json",
        dict(
            rows=12,
            seal_sha256=plan["protected_seal_sha256"],
            samples_labels_features_scores_opened=False,
            runtime_overlap_checked=False,
            distribution="EXTERNAL_PROTECTED_REFERENCE_NOT_COPIED",
        ),
    )
    actual_seal = ART / "training_unblock_20261107/dataset-release-final-v2/prospective-seal.json"
    assert file_sha256(actual_seal) == plan["protected_seal_sha256"]
    hashes = {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()}
    fp = dataset_fingerprint(rows, hashes, plan["fingerprint"])
    report = dict(
        schema_version="attack-intent-dataset-release-1",
        dataset_version=VERSION,
        dataset_fingerprint=fp,
        plan_fingerprint=plan["fingerprint"],
        status="RELEASED_FOR_RESEARCH_WITH_EXCLUSIONS",
        training_state="BLOCKED",
        rows=len(rows),
        sources=dict(Counter(r["request_provenance"]["source"] for r in rows)),
        roles=role_report,
        intent_counts=dict(Counter(r["intent"] for r in rows)),
        outcome_counts=dict(Counter(r["outcome"] for r in rows)),
        Oracle_verified=sum(r["oracle_verified"] for r in rows),
        independent_human_verified=0,
        review_pending=len(rows),
        feature_view_ambiguity=ambiguity,
        finite_cohort_runtime_visibility_bound=visibility_bounds(rows),
        finite_cohort_full_visibility_bound=visibility_bounds(rows, "full_view"),
        cross_role_identifier_groups=dict(overlap),
        cross_role_near_pairs_both_views=near,
        strict_exclusion_counts=dict(
            Counter(reason for r in rows for reason in r["inclusion_exclusion_reasons"])
        ),
        same_role_assignment_preserved=all(r["split"] == r["declared_role"] for r in rows),
        model_scores_used_for_selection=0,
        model_fits=0,
        publisher_anomaly_rows=0,
        prospective_contents_opened=False,
        files_sha256=hashes,
        source_bindings=bindings,
        source_sha256={
            str(Path(__file__).relative_to(ROOT)): file_sha256(__file__),
            "ai-training/src/idps_ai/data/attack_intent.py": file_sha256(
                ROOT / "ai-training/src/idps_ai/data/attack_intent.py"
            ),
        },
        limits=[
            "Known two-app laboratory sources; no independent cross-environment quality evidence",
            "Full and runtime tensors are separate contracts; body cannot be recovered by training",
            "Historical labels retain original Oracle tier; automated receipt/replay verification is not independent human review",
            "Opaque sealed full-view keys only; sealed runtime-view overlap not inspected",
            "Cross-role conflicts quarantined, never reassigned; workflow category counts are not independent sessions",
            "Collector total HTTP includes unreceipted readiness retries; cohort request count is not total HTTP",
            "Historical DEVELOPMENT predates new TRAIN/CAL; no forward-temporal evaluation claim",
            "Family path_traversal is the inherited classifier label including file inclusion; not a separately supervised file-inclusion class",
        ],
        gates=dict(
            LABEL_PROVENANCE="PASS_FOR_RESEARCH_FOR_ORACLE_ROWS_REVIEW_PENDING",
            RUNTIME_INTENT_IDENTIFIABILITY="FAIL"
            if ambiguity["runtime_view"]["groups"]
            else "NOT_YET_VERIFIED",
            SPLIT_INTEGRITY="QUARANTINED_EXPOSED_CONFLICTS_SEALED_RUNTIME_OVERLAP_UNVERIFIED",
            DATA_COVERAGE="SEE_ROLE_COVERAGE_AFTER_QUARANTINE_NOT_PASS",
            CROSS_ENVIRONMENT_EVALUATION="EXPOSED_SLICES_ONLY_NO_UNTOUCHED_ENVIRONMENT",
            TRAINING="BLOCKED_NO_JOB_STARTED",
        ),
        one_next_task="One privacy-preserving body-syntax observability feasibility experiment on the existing full-vs-runtime ambiguous Oracle pairs, with explicit allowed-field contract and leakage-safe view checks before any new adaptation training. Do not capture more count variants or change live telemetry without authorization.",
    )
    atomic_json(output / "dataset-release.json", report)
    # Public output contains counts/hashes, not record IDs, payloads, sessions, or tensors.
    public = {k: v for k, v in report.items() if k not in {"source_bindings"}}
    public["private_release_path"] = str(output.relative_to(ROOT))
    atomic_json(ROOT / "ai-training/reports/ATTACK_INTENT_DATASET_20261107.json", public)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "dataset_fingerprint",
                    "rows",
                    "intent_counts",
                    "outcome_counts",
                    "Oracle_verified",
                    "roles",
                    "feature_view_ambiguity",
                    "gates",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    with threadpool_limits(limits=1):
        build(a.base.resolve(), a.output.resolve())
