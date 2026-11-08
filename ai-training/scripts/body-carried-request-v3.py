#!/usr/bin/env python3
"""Bounded evaluation only: precommit complete matched pairs before HTTP/scores."""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import vector_hash
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.training.checkpoint import load_checkpoint

ROOT = Path(__file__).resolve().parents[2]
RUN = "request-v3-body-eval-20261108-r2"
RELEASE = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2"
PILOT = ROOT / "ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1"


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def cases():
    # Independent grammar choices, not nonce/count padding or score-selected variants.
    xss = [
        '<a href="java&#x73;cript:alert(1)">open</a>',
        '<svg onload="alert(&#49;)"></svg>',
        "<img src=x onerror=\"window['alert'](1)\">",
        '<button onclick="alert(String.fromCharCode(49))">show</button>',
        '<iframe srcdoc="&#60;svg onload=alert(1)&#62;"></iframe>',
        '<form><button formaction="javascript:alert(1)">send</button></form>',
    ]
    notes = [
        "Reference: java&#x73;cript is a word, not a link.",
        "Literal markup: &lt;svg onload=&quot;demo&quot;&gt;",
        "Array notes: values['left'] + values['right']",
        "Math notes: f(g(h(2))) + (3 * 4) = 14",
        "Document example: &lt;iframe srcdoc=&quot;text&quot;&gt;",
        "Form notes: action = submit; result = (2 + 3)",
    ]
    commands = [
        ("127.0.0.1; printf '%s\\n' BODY_SEQUENCE", "BODY_SEQUENCE"),
        ("127.0.0.1 && printf '%s' BODY_AND", "BODY_AND"),
        ("127.0.0.1 | printf '%s' BODY_PIPE", "BODY_PIPE"),
        ("127.0.0.1; printf '%s' \"$(printf BODY_SUB)\"", "BODY_SUB"),
        ("127.0.0.1; printf '%s' \"`printf BODY_BACKTICK`\"", "BODY_BACKTICK"),
        ("127.0.0.1; (printf '%s' BODY_GROUP)", "BODY_GROUP"),
    ]
    targets = ["127.0.0.1", "localhost", "127.0.0.2", "'localhost'", '"localhost"', "::1"]
    out = []
    for family, attacks, benign in [
        ("xss", [(v, v) for v in xss], notes),
        ("cmd_injection", commands, targets),
    ]:
        for i, ((attack, expected), control) in enumerate(zip(attacks, benign, strict=True)):
            for label, value, expect in [
                ("BENIGN_INTENT", control, control),
                ("ATTACK_INTENT", attack, expected),
            ]:
                guest = family == "xss"
                out.append(
                    {
                        "case_id": f"{family}-{i}-"
                        + ("benign" if label == "BENIGN_INTENT" else "attack"),
                        "pair_id": f"{family}-{i}",
                        "group": f"{family}-campaign-{i // 2}",
                        "family": family,
                        "intent": label,
                        "environment": "dvwa",
                        "role": "EVALUATION_ONLY",
                        "operation": "body-evaluation",
                        "workflow": "guestbook-body" if guest else "loopback-command-body",
                        "method": "POST",
                        "path": "/vulnerabilities/xss_s/" if guest else "/vulnerabilities/exec/",
                        "fields": {
                            "txtName": "LabReader",
                            "mtxMessage": value,
                            "btnSign": "Sign Guestbook",
                        }
                        if guest
                        else {"ip": value, "Submit": "Submit"},
                        "expected": expect,
                    }
                )
    return out


def collector(root):
    driver = module("complete-request-v3-campaign")
    driver.RUN = RUN
    return driver.configure(root)


def references(c):
    manifest = load(RELEASE / "dataset-release.json")
    for p, sha in manifest["files_sha256"].items():
        assert file_sha256(RELEASE / p) == sha
    rows = [json.loads(s) for s in (RELEASE / "records.jsonl").read_text().splitlines()]
    matrices = {}
    for role in ["train", "calibration", "development"]:
        with np.load(RELEASE / (role + ".npz"), allow_pickle=False) as z:
            matrices.update(
                {
                    str(s): (x.copy(), f.copy())
                    for s, x, f in zip(z["ids"], z["x"], z["frozen_runtime"], strict=True)
                }
            )
    old, original, fulls, base = c.parent_inputs()
    raw_template = {
        r["sample_id"]: {k: original[r["sample_id"]]["checksums"][k] for k in ["raw", "template"]}
        for r in old
    }
    # Only one additive main template shares either tested surface. Its request
    # body is static; the other11have different method/endpoint identities.
    cap = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/campaign-r1"
    main = load(cap / "main-oracle-receipts.json")
    catalog = {r["case_id"]: r for r in c.cases()}
    for r in main:
        if r["endpoint_template"] in {"/vulnerabilities/xss_s/", "/vulnerabilities/exec/"}:
            assert r["case_id"] == "control-00"
            _, _, full, keys, _ = c.representation(catalog[r["case_id"]])
            raw_template[r["sample_id"]] = {k: keys[k] for k in ["raw", "template"]}
            fulls[r["sample_id"]] = full
    return rows, matrices, raw_template, fulls


def preaudit(c, selected, actual=None):
    old, mat, keys, fulls = references(c)
    results = {}
    features = {}
    for case in selected:
        base = dict(case, fields=case["fields"])
        f, x, v, k, b = actual[case["case_id"]] if actual is not None else c.representation(base)
        features[case["case_id"]] = (f, x, v, k, b)
        why = set()
        endpoint = case["path"]
        for r in old:
            same = r["method"] == case["method"] and r["endpoint_template"] == endpoint
            oldx, oldf = mat[r["sample_id"]]
            if np.array_equal(x, oldx):
                why.add("HISTORICAL_EXACT_CANDIDATE")
            if same:
                assert r["sample_id"] in keys and r["sample_id"] in fulls, (
                    "Matching full/raw/template reference unavailable"
                )
                if any(k[name] == keys[r["sample_id"]][name] for name in ["raw", "template"]):
                    why.add("HISTORICAL_RAW_OR_TEMPLATE")
                if vector_hash(v) == vector_hash(fulls[r["sample_id"]]):
                    why.add("HISTORICAL_FULL_EXACT")
                if (
                    float(v[76:].astype(np.float64) @ fulls[r["sample_id"]][76:].astype(np.float64))
                    >= 0.995 - 1e-7
                ):
                    why.add("HISTORICAL_FULL_NEAR")
                if (
                    float(f[76:].astype(np.float64) @ oldf[76:].astype(np.float64)) >= 0.995 - 1e-7
                    and np.max(np.abs(x[588:] - oldx[588:])) <= 1 / 3 + 1e-7
                ):
                    why.add("HISTORICAL_CANDIDATE_NEAR")
        results[case["case_id"]] = why
    # Canonical first declared template per identical candidate view, score-free.
    seen = {}
    for case in selected:
        key = vector_hash(features[case["case_id"]][1])
        if key in seen:
            prior = seen[key]
            results[case["case_id"]].add("WITHIN_COHORT_DUPLICATE_CANDIDATE")
            if prior["intent"] != case["intent"]:
                results[prior["case_id"]].add("MIXED_INTENT_CANDIDATE")
                results[case["case_id"]].add("MIXED_INTENT_CANDIDATE")
        else:
            seen[key] = case
    qualified = []
    for pair in sorted({r["pair_id"] for r in selected}):
        members = [r for r in selected if r["pair_id"] == pair]
        assert len(members) == 2
        if all(not results[r["case_id"]] for r in members):
            qualified.extend(r["case_id"] for r in members)
        else:
            for r in members:
                results[r["case_id"]].add("PAIR_NOT_BOTH_QUALIFIED")
    return {k: sorted(v) for k, v in results.items()}, qualified


def lock(root):
    assert not root.exists()
    root.mkdir(mode=0o700, parents=True)
    c = collector(root)
    selected = cases()
    exclusions, qualified = preaudit(c, selected)
    thresholds = load(PILOT / "evaluation/thresholds.json")["thresholds"]
    frozen = ResearchMVP("request-v2", cpus=1)
    assert thresholds["frozen"] == frozen.v2_threshold
    candidate = load_checkpoint(PILOT / "model")
    assert candidate.model.steps == 60 and not candidate.used_previous
    q, d = c.configured_helpers()
    plan = {
        "schema_version": "body-carried-evaluation-precommit-1",
        "run_id": RUN,
        "cohort_id": RUN,
        "source_sha256": file_sha256(__file__),
        "helpers_sha256": {
            n: file_sha256(Path(__file__).with_name(n + ".py"))
            for n in [
                "request-v3-final-controls",
                "complete-request-v3-campaign",
                "materialize-request-v3",
                "p0-dvwa-capture",
                "quality-lab-cohort",
                "attack-intent-capture",
                "evaluate-request-v3-pilot",
            ]
        },
        "parent_dataset_fingerprint": load(RELEASE / "dataset-release.json")["dataset_fingerprint"],
        "parent_manifest_sha256": file_sha256(RELEASE / "dataset-release.json"),
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "body_contract_sha256": body.CONTRACT_SHA256,
        "checkpoint": {
            "candidate_path": str(candidate.path.relative_to(ROOT)),
            "candidate_manifest_sha256": file_sha256(candidate.path / "manifest.json"),
            "candidate_arrays_sha256": file_sha256(candidate.path / "arrays.npz"),
            "frozen_manifest_sha256": frozen.v2_manifest_sha,
        },
        "thresholds": thresholds,
        "threshold_source_sha256": file_sha256(PILOT / "evaluation/thresholds.json"),
        "images": {"app": d.APP_IMAGE, "db": d.DB_IMAGE},
        "profile": "Unchanged LabResearch UA/FORM headers and actual complete bodies; no header/payload padding for novelty",
        "templates": [
            {
                "case_id": r["case_id"],
                "pair_id": r["pair_id"],
                "group": r["group"],
                "intent": r["intent"],
                "family": r["family"],
                "method": r["method"],
                "endpoint": r["path"],
            }
            for r in selected
        ],
        "template_binding": "Exact fields/expected expressions in source; no substituted cases after exclusion",
        "target": {
            "xss_attack": 6,
            "cmd_attack": 6,
            "xss_controls": 6,
            "cmd_controls": 6,
            "main_cap": 24,
            "preflight_cap": 2,
        },
        "preaudit_exclusions": exclusions,
        "qualified_case_ids": qualified,
        "deduplication": "Historical raw/template/full-exact/full-near/candidate-exact/candidate-near on matching endpoint; candidate-exact all236; retain only complete predeclared pairs. Within-cohort canonical candidate-view first, mixed-known intents excluded. Frozen588overlap diagnostic only per body-v3contract.",
        "lineage": "Fresh owned apps/sessions per predeclared group; ordinal aliases; no old groups reused. Same knownDVWAenvironment, template-level research novelty only.",
        "oracles": {
            "guestbook": "Before0/after1exactDBrow plus ownentry literal/rawHTML response; malicious markup UNSAFE_REFLECTION not verified browser execution; benign literal row persistence not HTTPstatus alone",
            "command_attack": "Only declared harmless stdout canary after shell injection; confirmed execution if exactstdoutcanary in pre block; no host/external commands",
            "command_benign": "Operator-free or quoted literal loopback target only; fourtransmitted/fourreceived/zero-loss; no option injection",
        },
        "roles": "EVALUATION_ONLY; no fit or calibration; future reusefortraining retires evaluation independence explicitly",
        "label_status": "INTERNAL_APPLICATION_ORACLE; HUMAN_REVIEW_PENDING; unknown excluded, no replacements",
        "decision_rule": "Report countsprimary. OBSERVED only >=2additional attackIDs vs bothrefs across>=2freshlineagegroups with no new benignFP vs either; incomplete family not measured. Otherwise NOT_DEMONSTRATED on qualifiedsupport, INCONCLUSIVE if<2completepairs or missingmatchedsupport. No promotion.",
        "scoring_gate": "After allcapture+Oracle+feature/lineage/privacy checks and eligible manifest fingerprint locked; no predictions before then",
        "metrics": [
            "TP/FN/FP/TN",
            "precision/recall/FPR/AP",
            "per-family matched controls",
            "paired attack and benign disagreements",
            "per-fresh-lineage group counts",
            "IID exact-binomial95% sensitivity only",
            "fixed-checkpoint syntax-tail ablation, no refit",
        ],
        "partial_scope": "First score-free audit retains four XSS pairs, zero complete command pairs. Capture only unchanged qualified subset; no replacement or new templates. Command result remains INCONCLUSIVE.",
        "resource": {
            "quota_percent_one_core": 25,
            "instant_cutoff_C": 85,
            "ownership_cutoff_C": 80,
            "reserve_GiB": 4,
        },
        "host_sysctl_before": Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip(),
        "sealed_overlap": "UNVERIFIED_NOT_OPENED; no sealed samples/labels/features accessed",
        "training": False,
        "startup_amendment": "R1abortedbeforeanyHTTP: heavy new entrypoint exceeded watchdog readiness deadline. Reuse existing lightweight final-controls watchdog CLI; same templates/eligible pairs/Oracles/thresholds, fresh execution ID; no recapture or score exposure.",
        "parent_plan_fingerprint": load(
            ROOT / "ai-training/.artifacts/request_v3_body_eval_20261108/cohort-r1/plan.json"
        )["fingerprint"],
        "model_scores_computed": 0,
        "stop": "No substitutions,retries orbudget expansion; stop essentialOracle/ownership/privacy/parity failure; qualifiedsubset only, disclose gaps",
    }
    plan["environment_fingerprint"] = digest(
        {
            "images": plan["images"],
            "source_sha256": plan["source_sha256"],
            "helpers": plan["helpers_sha256"],
            "namespace": "ping_group_range33 33,NNP,seccomp,loopback19280",
        }
    )
    plan["fingerprint"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    print(
        json.dumps(
            {
                "plan_fingerprint": plan["fingerprint"],
                "qualified": qualified,
                "exclusion_counts": dict(
                    Counter(v for values in exclusions.values() for v in values)
                ),
            },
            indent=2,
        )
    )


def db_count(d, value):
    # Bound SELECT only; raw value/hex travels transiently on stdin, not argv/log.
    literal = value.encode().hex()
    sql = (
        "SELECT COUNT(*) FROM guestbook WHERE comment=CONVERT(UNHEX('"
        + literal
        + "') USING utf8mb4);"
    )
    result = subprocess.run(
        ["podman", "exec", "-i", d.DB, "mariadb", "-udvwa", "-pp@ssw0rd", "-N", "dvwa"],
        input=sql.encode(),
        capture_output=True,
        timeout=10,
        check=True,
    )
    return int(result.stdout.strip())


def guestbook_proof(value, response, status, before, after, attack):
    from html.parser import HTMLParser

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags = []
            self.active = False

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            for key, val in attrs:
                val = val or ""
                if (
                    key.lower().startswith("on")
                    or val.strip().lower().startswith("javascript:")
                    or key.lower() == "srcdoc"
                    and "<" in val
                ):
                    self.active = True

    own = Tags()
    own.feed(value)
    text = response.decode(errors="replace")
    # Exact value must be in the actual guestbook display, not only a form field.
    regions = re.findall(r"<div id=[\"\']guestbook_comments[\"\']>(.*?)</div>", text, re.S)
    present = any(value in block for block in regions)
    facts = {
        "HTTP200": status == 200,
        "before_absent": before == 0,
        "one_new_exact_DB_row": after == before + 1,
        "own_value_in_guestbook_display": present,
        "declared_active_markup": own.active if attack else not own.tags,
        "browser_execution_tested": False,
    }
    ok = all(v for k, v in facts.items() if k != "browser_execution_tested")
    return ok, facts


def capture(root):
    plan = load(root / "plan.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert plan["source_sha256"] == file_sha256(__file__) and plan["run_id"] == RUN
    for name, sha in plan["helpers_sha256"].items():
        assert file_sha256(Path(__file__).with_name(name + ".py")) == sha
    assert not (root / "capture-status.json").exists()
    c = collector(root)
    q, d = c.configured_helpers()
    assert not q.owned()
    selected = [v for v in cases() if v["case_id"] in plan["qualified_case_ids"]]
    assert selected and len(selected) <= 24
    assert all(r["family"] == "xss" for r in selected), (
        "This fixed qualified subset supports guestbook Oracle only"
    )
    ledger = []
    receipts = []
    features = {}
    setup = 0
    seen_sessions = set()
    done = threading.Event()

    def beat():
        while not done.wait(0.2):
            (root / "heartbeat").touch()

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
            str(Path(__file__).with_name("request-v3-final-controls.py")),
            "watchdog",
            "--execution-id",
            RUN,
            "--output",
            str(root),
        ],
        check=True,
        capture_output=True,
    )
    deadline = time.monotonic() + 20
    while not (root / "watchdog-ready").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (root / "watchdog-ready").exists()
    success = False

    def send(case, phase, session, group_index):
        assert len([r for r in ledger if r["phase"] == phase]) < (24 if phase == "main" else 2)
        rid = digest([RUN, phase, case["case_id"]])[:32]
        raw = urlencode(case["fields"]).encode()
        before = db_count(d, case["fields"]["mtxMessage"])
        assert c.php_authenticated(q, d, session), "Authenticated session witness missing"
        entry = {
            "request_id": rid,
            "case_id": case["case_id"],
            "phase": phase,
            "state": "ISSUED_RESPONSE_UNCONFIRMED",
        }
        ledger.append(entry)
        atomic_json(root / "dispatch-ledger.json", ledger)
        headers = {
            "User-Agent": c.UA,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Request-Id": rid,
            "Cookie": "; ".join(f"{k}={v}" for k, v in session.cookies.items()),
        }
        status, _, response, sent = c.http(c.PORT, "POST", case["path"], raw, headers)
        entry.update(state="RESPONSE_RECEIVED", HTTP_status=status)
        atomic_json(root / "dispatch-ledger.json", ledger)
        after = db_count(d, case["fields"]["mtxMessage"])
        attack = case["intent"] == "ATTACK_INTENT"
        ok, proof = guestbook_proof(
            case["fields"]["mtxMessage"], response, status, before, after, attack
        )
        row = {
            "sample_id": digest([RUN, phase, rid]),
            "request_id": rid,
            "case_id": case["case_id"],
            "pair_id": case["pair_id"],
            "phase": phase,
            "role": "EVALUATION_ONLY" if phase == "main" else "DIAGNOSTIC_ONLY",
            "family": case["family"],
            "planned_intent": case["intent"],
            "intent": case["intent"] if ok else "UNKNOWN_INTENT",
            "outcome": ("UNSAFE_REFLECTION" if attack else "BENIGN_SUCCESS")
            if ok
            else "UNKNOWN_OUTCOME",
            "observation_status": "ORACLE_VERIFIED" if ok else "ORACLE_UNVERIFIED",
            "oracle_verified": ok,
            "oracle_checks": proof,
            "environment": "dvwa",
            "method": "POST",
            "endpoint_template": case["path"],
            "workflow_group": case["workflow"],
            "session_group": f"session_group-{3000 + group_index:04d}",
            "campaign_group": f"campaign_group-{3000 + group_index:04d}",
            "template_group": case["group"],
            "environment_fingerprint": plan["environment_fingerprint"],
            "review_status": "PENDING",
            "independent_human_verified": False,
            "browser_execution": "NOT_TESTED",
            "inclusion_exclusion_reasons": [] if ok else ["ORACLE_UNVERIFIED"],
            "transaction_identity": "Freshcollector requestID+actualclientreceipt+same authenticated RAM session; no independent packetcapture claim",
            "feature_contract_fingerprint": request_v3.fingerprint(),
        }
        receipts.append(row)
        atomic_json(root / "oracle-receipts.json", receipts)
        assert ok, "Essential guestbook Oracle failed; stop without replacement"
        if phase == "main":
            features[case["case_id"]] = c.representation(
                case, raw=raw, headers=sent, path=case["path"]
            )

    try:
        # One diagnostic on existing benign stored-literal Oracle; not a new main.
        c.launch(q, d, "dvwa")
        try:
            session = c.RAMSession()
            d.initialize(session)
            setup += session.setup_requests
            diag = dict(
                selected[0],
                case_id="preflight-literal",
                pair_id="DIAGNOSTIC_ONLY",
                intent="BENIGN_INTENT",
                fields={
                    "txtName": "LabReader",
                    "mtxMessage": "Ordinary evidence row",
                    "btnSign": "Sign Guestbook",
                },
            )
            send(diag, "preflight", session, 0)
        finally:
            c.cleanup(q, d)
        for group_index, group in enumerate(sorted({v["group"] for v in selected}), 1):
            c.launch(q, d, "dvwa")
            try:
                session = c.RAMSession()
                d.initialize(session)
                setup += session.setup_requests
                actual_session = session.cookies.get("PHPSESSID")
                assert actual_session and actual_session not in seen_sessions
                seen_sessions.add(actual_session)
                assert setup < 120 and not (root / "lab-watchdog-result.json").exists()
                group_cases = sorted(
                    [v for v in selected if v["group"] == group],
                    key=lambda v: (v["intent"] == "ATTACK_INTENT", v["case_id"]),
                )
                for case in group_cases:
                    assert not (root / "lab-watchdog-result.json").exists()
                    send(case, "main", session, group_index)
            finally:
                c.cleanup(q, d)
        # Recheck actual transmitted features/keys, then destroy raw equality keys.
        reasons, actual_qualified = preaudit(c, selected, features)
        assert set(actual_qualified) == set(plan["qualified_case_ids"]) and not any(
            reasons.values()
        ), "Actual overlap invalidates evaluation; do not score"
        main = [r for r in receipts if r["phase"] == "main"]
        by_id = {r["case_id"]: r for r in main}
        for case_id, v in features.items():
            f, x, full, keys, b = v
            assert np.array_equal(x, request_v3.assemble(f, b))
            assert b == body.extract(
                urlencode(next(r for r in selected if r["case_id"] == case_id)["fields"]).encode(),
                "application/x-www-form-urlencoded",
            )
            by_id[case_id]["body_state"] = body.state_of(b)
            by_id[case_id]["feature_availability"] = {
                "request_v3": True,
                "frozen_prefix": True,
                "GLU207": False,
            }
        ids = [r["sample_id"] for r in main]
        np.savez(
            root / "features-private.npz",
            ids=np.array(ids),
            x=np.stack([features[r["case_id"]][1] for r in main]),
            frozen=np.stack([features[r["case_id"]][0] for r in main]),
            body=np.array([features[r["case_id"]][4] for r in main], np.uint8),
        )
        atomic_json(root / "eligible-records.json", main)
        atomic_json(root / "oracle-receipts.json", receipts)
        c.privacy_check()
        fp = digest(
            {
                "records": main,
                "features_sha256": file_sha256(root / "features-private.npz"),
                "plan_fingerprint": plan["fingerprint"],
            }
        )
        atomic_json(
            root / "eligible-manifest.json",
            {
                "dataset_fingerprint": fp,
                "plan_fingerprint": plan["fingerprint"],
                "records_sha256": file_sha256(root / "eligible-records.json"),
                "features_sha256": file_sha256(root / "features-private.npz"),
                "eligible_views": len(main),
                "roles": "EVALUATION_ONLY",
                "label_Oracle_privacy_lineage_feature_gates": "PASS",
                "historical_overlap_scope": plan["deduplication"],
                "sealed": "NOT_OPENED",
                "model_scores_computed_before_lock": 0,
                "future_fit_reuse": "Requires explicit retirement of evaluation-only independence",
            },
        )
        success = True
    finally:
        c.cleanup(q, d)
        (root / "watchdog-done").touch()
        done.set()
        thread.join(timeout=1)
        time.sleep(0.3)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)
        atomic_json(
            root / "capture-status.json",
            {
                "status": "COMPLETED" if success else "FAILED",
                "main_receipts": sum(r["phase"] == "main" for r in receipts),
                "preflight_receipts": sum(r["phase"] == "preflight" for r in receipts),
                "targeted_dispatches": len(ledger),
                "setup_HTTP_attempts": setup,
                "owned_containers_remaining": len(q.owned()),
                "model_scores_computed": 0,
                "training_updates": 0,
                "cleanup_events": c.CLEANUP_EVENTS,
            },
        )
        # Covers immutable manifest/status added after the first scan as well.
        c.privacy_check()
    print(json.dumps(load(root / "capture-status.json"), indent=2))


def evaluate(root):
    plan = load(root / "plan.json")
    assert plan["source_sha256"] == file_sha256(__file__)
    assert load(root / "capture-status.json")["status"] == "COMPLETED"
    manifest = load(root / "eligible-manifest.json")
    assert (
        manifest["model_scores_computed_before_lock"] == 0
        and manifest["label_Oracle_privacy_lineage_feature_gates"] == "PASS"
    )
    assert load(root / "actual-value-privacy-check.json")["status"] == "PASS_FOR_RESEARCH"
    assert (
        file_sha256(root / "eligible-records.json") == manifest["records_sha256"]
        and file_sha256(root / "features-private.npz") == manifest["features_sha256"]
    )
    rows = load(root / "eligible-records.json")
    assert manifest["dataset_fingerprint"] == digest(
        {
            "records": rows,
            "features_sha256": manifest["features_sha256"],
            "plan_fingerprint": plan["fingerprint"],
        }
    )
    assert all(r["oracle_verified"] and r["role"] == "EVALUATION_ONLY" for r in rows)
    assert not (root / "evaluation.json").exists()
    with np.load(root / "features-private.npz", allow_pickle=False) as z:
        x, f, b = z["x"].copy(), z["frozen"].copy(), z["body"].copy()
        assert list(z["ids"]) == [r["sample_id"] for r in rows]
    assert np.isfinite(x).all() and all(
        np.array_equal(v, request_v3.assemble(base, syntax.tolist()))
        for v, base, syntax in zip(x, f, b, strict=True)
    )
    candidate = load_checkpoint(ROOT / plan["checkpoint"]["candidate_path"])
    frozen = ResearchMVP("request-v2", cpus=1)
    assert candidate.model.steps == 60 and not candidate.used_previous
    assert (
        file_sha256(candidate.path / "manifest.json")
        == plan["checkpoint"]["candidate_manifest_sha256"]
        and file_sha256(candidate.path / "arrays.npz")
        == plan["checkpoint"]["candidate_arrays_sha256"]
    )
    assert (
        frozen.v2_manifest_sha == plan["checkpoint"]["frozen_manifest_sha256"]
        and frozen.v2_threshold == plan["thresholds"]["frozen"]
    )
    assert file_sha256(PILOT / "evaluation/thresholds.json") == plan["threshold_source_sha256"]
    ev = module("evaluate-request-v3-pilot")
    assert file_sha256(ev.__file__) == plan["helpers_sha256"]["evaluate-request-v3-pilot"]
    labels = np.array([int(r["intent"] == "ATTACK_INTENT") for r in rows])
    scores = {"frozen": frozen.v2_model.predict(f)[0], "challenger": candidate.model.predict(x)[0]}
    scores["calibration_only"] = scores["frozen"]
    thresholds = plan["thresholds"]
    flags = {name: score > thresholds[name] for name, score in scores.items()}
    summary = {}
    for name, score in scores.items():
        family = {}
        for fam in ["xss", "cmd_injection"]:
            ix = np.array([i for i, r in enumerate(rows) if r["family"] == fam], np.int64)
            family[fam] = ev.metrics(labels[ix], score[ix], thresholds[name]) if len(ix) else None
        summary[name] = {
            "all": ev.metrics(labels, score, thresholds[name]),
            "family_with_matched_benign": family,
            "groups": {
                g: ev.metrics(
                    labels[[r["template_group"] == g for r in rows]],
                    score[[r["template_group"] == g for r in rows]],
                    thresholds[name],
                )
                for g in sorted({r["template_group"] for r in rows})
            },
        }
    paired = {}
    for name in ["frozen", "calibration_only"]:
        v = flags["challenger"]
        ref = flags[name]
        paired[name] = {
            "V3_only_attack": int(np.sum(v & ~ref & (labels == 1))),
            "reference_only_attack": int(np.sum(~v & ref & (labels == 1))),
            "both_attack": int(np.sum(v & ref & (labels == 1))),
            "neither_attack": int(np.sum(~v & ~ref & (labels == 1))),
            "V3_only_benign_FP": int(np.sum(v & ~ref & (labels == 0))),
            "reference_only_benign_FP": int(np.sum(~v & ref & (labels == 0))),
        }
    gain_groups = {
        r["template_group"]
        for i, r in enumerate(rows)
        if labels[i]
        and flags["challenger"][i]
        and all(not flags[k][i] for k in ["frozen", "calibration_only"])
    }
    observed = (
        all(
            paired[n]["V3_only_attack"] >= 2 and paired[n]["V3_only_benign_FP"] == 0 for n in paired
        )
        and len(gain_groups) >= 2
    )
    support = len({r["pair_id"] for r in rows}) >= 2
    decision = "OBSERVED" if observed else "NOT_DEMONSTRATED" if support else "INCONCLUSIVE"
    # Predeclared structural sensitivity; not another trained arm or a tuned threshold.
    ablated = x.copy()
    ablated[:, 603:] = 0
    abscore = candidate.model.predict(ablated)[0]
    result = {
        "cohort_id": RUN,
        "dataset_fingerprint": manifest["dataset_fingerprint"],
        "plan_fingerprint": plan["fingerprint"],
        "BODY_CARRIED_EVALUATION": "COMPLETED" if len(rows) == 24 else "PARTIAL",
        "V3_RESEARCH_VALUE": decision,
        "main_receipts": len(rows),
        "eligible_views": len(rows),
        "attack": int(labels.sum()),
        "benign": int(np.sum(labels == 0)),
        "family_counts": dict(Counter(r["family"] for r in rows)),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "thresholds": thresholds,
        "checkpoint_fingerprints": plan["checkpoint"],
        "arms": summary,
        "paired": paired,
        "benefit_fresh_groups": len(gain_groups),
        "distinct_workflow_surfaces": len({r["workflow_group"] for r in rows}),
        "distinct_lineage_groups": len({r["session_group"] for r in rows}),
        "method_body_presence": dict(Counter(r["method"] + "/" + r["body_state"] for r in rows)),
        "frozen588_unique_views": len({vector_hash(v) for v in f}),
        "syntax_tail_probe": {
            "scope": "Fixed checkpoint inference-only zeroing counts/flags; no threshold fitting or primary-arm replacement",
            "ablated_unique_inputs": len({vector_hash(v) for v in ablated}),
            "threshold_crossings": int(
                np.sum((abscore > thresholds["challenger"]) != flags["challenger"])
            ),
            "same_threshold_metrics": ev.metrics(labels, abscore, thresholds["challenger"]),
        },
        "family_scope": {
            "xss": "Qualified complete paired subset only",
            "command": "INCONCLUSIVE_NO_NOVEL_MATCHED_CONTROL_PAIRS",
        },
        "uncertainty": "Counts primary; exact binomial intervals only IID sensitivity; few dependent known-lab groups, no population FPR<=1% or independent generalization claim",
        "attribution": "Within matched inputs observe feature use, but representation and training weight changes remain confounded across checkpoints; no matched588finetune arm",
        "RULE_AI_COMPLEMENTARITY": "NOT_MEASURED",
        "rule_reason": "No bound sensor/Rule receipts for these new requests",
        "INDEPENDENT_QUALITY_CERTIFIED": False,
        "human_review": "PENDING",
        "V3_PROMOTION": "REJECTED",
        "REQUEST_V3_TRAINING": "NOT_STARTED_THIS_MILESTONE",
        "sealed_opened": False,
    }
    atomic_json(root / "evaluation.json", result)
    np.savez(
        root / "scores-private.npz",
        **scores,
        labels=labels,
        ids=np.array([r["sample_id"] for r in rows]),
    )
    print(
        json.dumps(
            {
                "status": result["BODY_CARRIED_EVALUATION"],
                "research_value": decision,
                "paired": paired,
                "arms": {n: v["all"] for n, v in summary.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["lock", "capture", "watchdog", "evaluate"])
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        {
            "lock": lock,
            "capture": capture,
            "watchdog": lambda root: collector(root).watch(root),
            "evaluate": evaluate,
        }[a.action](a.output.resolve())
