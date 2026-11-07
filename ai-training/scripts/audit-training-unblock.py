#!/usr/bin/env python3
"""Verify precommitted receipts and seal a research dataset; never score evaluation."""

import argparse
import codecs
import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import CLASSES, atomic_json, digest, file_sha256
from idps_ai.features.research_request_channels import encode
from idps_ai.mvp_inference import ResearchMVP

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def coverage(rows, plan):
    checks = {}
    for role, gate in plan["coverage_gates"].items():
        selected = [
            r
            for r in rows
            if r["role"] == role and not r["exclusions"] and r["intent"] != "UNKNOWN"
        ]
        benign = [r for r in selected if r["intent"] == "BENIGN"]
        families = defaultdict(set)
        for r in selected:
            if r["intent"] == "ATTACK_ATTEMPT":
                families[r["family"]].add(r["keys"]["template"])
        stats = dict(
            eligible_cases=len(selected),
            workflow_groups=len({r["workflow"] for r in selected}),
            benign_workflow_groups=len({r["workflow"] for r in benign}),
            benign_GET_groups=len({r["workflow"] for r in benign if r["method"] == "GET"}),
            benign_POST_groups=len({r["workflow"] for r in benign if r["method"] == "POST"}),
            benign_JSON_groups=len(
                {
                    r["workflow"]
                    for r in benign
                    if r["method"] == "POST" and r["environment"] == "juice"
                }
            ),
            unique_views=len({r["keys"]["view"] for r in selected}),
            unique_benign_views=len({r["keys"]["view"] for r in benign}),
            candidate_unique_views=len({r["candidate_view"] for r in selected}),
            attack_templates_per_family={k: len(v) for k, v in families.items()},
        )
        failures = []
        for k, v in gate.items():
            if type(v) is int and k != "templates_each_family" and stats[k] < v:
                failures.append(k)
        for family in gate.get("attack_families", []):
            if stats["attack_templates_per_family"].get(family, 0) < gate.get(
                "templates_each_family", 1
            ):
                failures.append("family_" + family)
        if gate.get("form_and_JSON") and not (
            any(r["method"] == "POST" and r["environment"] == "dvwa" for r in benign)
            and stats["benign_JSON_groups"]
        ):
            failures.append("form_and_JSON")
        checks[role] = dict(
            status="FAIL" if failures else "PASS", actual=stats, failed_requirements=failures
        )
    return checks


def audit(root, output):
    output.mkdir(mode=0o700, exist_ok=False)
    plan = load(root / "precommitted-plan.json")
    assert plan["plan_sha256"] == digest({k: v for k, v in plan.items() if k != "plan_sha256"})
    captured_plan = load(root / "plan.json")
    assert captured_plan["plan_sha256"] == digest(
        {k: v for k, v in captured_plan.items() if k != "plan_sha256"}
    )
    assert captured_plan["precommitted_plan_file_sha256"] == file_sha256(
        root / "precommitted-plan.json"
    )
    assert file_sha256(root / "collector-source.py") == plan["source_sha256"]
    lock = load(root / "experiment-lock.json")
    assert lock["fingerprint"] == digest({k: v for k, v in lock.items() if k != "fingerprint"})
    assert lock["feature_source_sha256"] == file_sha256(
        ROOT / "ai-training/src/idps_ai/features/research_request_channels.py"
    )
    observations = load(
        root
        / ("capture.json" if (root / "capture.json").exists() else "observations-progress.json")
    )["observations"]
    byid = {r["request_id"]: r for r in observations}
    assert len(byid) == len(observations)
    pv = module("p0-request-evaluate")
    c = module("training-unblock-cohort")
    frozen = ResearchMVP("request-v2", cpus=1)
    rows = []
    semantic_rechecks = 0
    p0_oracle = module("p0-dvwa-capture")
    p0_oracle.CANARY = "UNBLOCK_FILE_CANARY"
    users = load(root / "dvwa-users-oracle.json")
    catalog = load(root / "juice-catalog.json")
    content = []
    new_vectors = []
    old_vectors = []
    for case in captured_plan["cases"]:
        rid = case["request_id"]
        base = root / case["environment"] / "receipts" / rid
        if not (base / "receipt.json").exists() or rid not in byid:
            continue
        receipt = load(base / "receipt.json")
        headers = load(base / "request-headers.json")
        returned = load(base / "response-headers.json")
        body = (base / "request-body.bin").read_bytes()
        response = (base / "response-body.bin").read_bytes()
        assert (
            receipt["request_id"] == rid
            and receipt["method"] == case["method"]
            and receipt["path"] == case["path"]
        )
        assert (
            receipt["request_body_sha256"]
            == hashlib.sha256(body).hexdigest()
            == byid[rid]["actual_body_sha256"]
        )
        assert receipt["request_headers_sha256"] == digest(headers)
        assert receipt["response_headers_sha256"] == digest(returned)
        assert (
            receipt["response_sha256"]
            == hashlib.sha256(response).hexdigest()
            == byid[rid]["response_sha256"]
        )
        if case["oracle"] == "feedback_create":
            ancillary = root / "ancillary" / rid
            captcha = load(ancillary / "captcha-response.bin")
            binding = load(ancillary / "binding.json")
            assert binding["captcha_snapshot_sha256"] == file_sha256(
                ancillary / "captcha-response.bin"
            )
            assert binding["actual_body_sha256"] == file_sha256(base / "request-body.bin")
            expected = json.loads(case["body"])
            expected["captchaId"] = captcha["captchaId"]
            expected["captcha"] = captcha["answer"]
            assert json.loads(body) == expected
            assert c.arithmetic_answer(captcha["captcha"]) == str(captcha["answer"])
            state = load(ancillary / "feedback-state.bin")
            assert (
                file_sha256(ancillary / "feedback-state.bin")
                == load(ancillary / "feedback-state-receipt.json")["body_sha256"]
            )
            if byid[rid]["semantic_oracle_matched"]:
                assert any(
                    x["id"] == byid[rid]["oracle_detail"]["created_id"]
                    and x["comment"] == case["expected"]
                    for x in state["data"]
                )
        else:
            assert body.decode() == case["body"]
        rule = case["oracle"]
        matched = False
        if case["environment"] == "dvwa":
            if rule in ["stored_literal", "unsafe_stored_reflection"]:
                blocks = re.findall(
                    r'<div id="guestbook_comments">(.*?)</div>',
                    response.decode(errors="replace"),
                    re.S,
                )
                matched = any(
                    "Name: LabReader<br />Message: " + case["expected"] + "<br />" in b
                    for b in blocks
                )
                matched = (
                    matched and byid[rid]["oracle_detail"].get("guestbook_exact_row_count", 0) >= 1
                )
            elif rule == "transformed_canary":
                expected = (
                    codecs.encode(p0_oracle.CANARY, "rot_13")
                    if case["expected"] == "rot13"
                    else p0_oracle.CANARY.upper()
                )
                matched = expected in response.decode(errors="replace")
            else:
                matched, _ = p0_oracle.oracle(case, response, users)
        else:
            parsed = json.loads(response)
            data = parsed.get("data")
            if rule == "feedback_create":
                matched = (
                    receipt["status"] == 201
                    and isinstance(data, dict)
                    and data.get("comment") == case["expected"]
                    and data.get("rating") == json.loads(body)["rating"]
                    and any(
                        x.get("id") == data.get("id")
                        and x.get("comment") == case["expected"]
                        and x.get("rating") == data.get("rating")
                        for x in state["data"]
                    )
                )
            elif rule == "captcha_arithmetic":
                matched = receipt["status"] == 200 and c.arithmetic_answer(
                    parsed.get("captcha")
                ) == str(parsed.get("answer"))
            elif rule == "catalog_list":
                matched = isinstance(data, list) and {x["id"] for x in data} == {
                    x["id"] for x in catalog
                }
            elif rule == "catalog_search":
                expected = {
                    x["id"]
                    for x in catalog
                    if case["expected"].lower()
                    in (str(x["name"]) + " " + str(x.get("description", ""))).lower()
                }
                matched = isinstance(data, list) and {x["id"] for x in data} == expected
            elif rule == "search_injection":
                negative_controls = [
                    x
                    for x in captured_plan["cases"]
                    if x["oracle"] == "catalog_search" and x["role"] == "TRAIN"
                ]
                assert len(negative_controls) == 1
                negative = load(
                    root
                    / "juice/receipts"
                    / negative_controls[0]["request_id"]
                    / "response-body.bin"
                )
                matched = (
                    isinstance(data, list)
                    and {x["id"] for x in catalog} <= {x["id"] for x in data}
                    and negative["data"] == []
                )
        assert bool(matched) == byid[rid]["semantic_oracle_matched"]
        semantic_rechecks += 1
        assert (
            byid[rid]["role"] == case["role"]
            and byid[rid]["campaign"] == case["campaign"]
            and byid[rid]["session_plan"] == case["session_plan"]
        )
        req = dict(
            method=case["method"],
            url=case["path"],
            body=body.decode(),
            headers="\r\n".join(f"{k}: {v}" for k, v in headers.items()),
        )
        with threadpool_limits(limits=1):
            keys, co = c.keys(req, frozen, pv)
            nv = encode(req)
            ov = pv.vector(frozen, req)[0]
        row = {
            **case,
            "intent": byid[rid]["intent"],
            "outcome": byid[rid]["outcome"],
            "oracle_matched": byid[rid]["semantic_oracle_matched"],
            "session_group": byid[rid]["session_group"],
            "keys": keys,
            "candidate_view": hashlib.sha256(nv.tobytes()).hexdigest(),
            "receipt_file": str(base / "receipt.json"),
            "receipt_sha256": file_sha256(base / "receipt.json"),
            "exclusions": [],
            "review": "PENDING",
            "independent_human_verified": False,
        }
        if row["intent"] == "UNKNOWN":
            row["exclusions"].append("UNKNOWN_ORACLE")
        rows.append(row)
        content.append(co)
        new_vectors.append(nv)
        old_vectors.append(ov)
    # Recheck actual headers and runtime-bound bodies, not just planned placeholders.
    historic = []
    for line in (
        (ROOT / "ai-training/.artifacts/quality_lab_20261107/assessment-v2/role-audit.jsonl")
        .read_text()
        .splitlines()
    ):
        r = json.loads(line)
        b = Path(r["receipt_file"]).parent
        h = load(b / "request-headers.json")
        historic.append(
            dict(
                method=r["method"],
                url=r["path"],
                body=r["body"],
                headers="\r\n".join(f"{k}: {v}" for k, v in h.items()),
            )
        )
    _, _, p0 = pv.corpus(ROOT / "ai-training/.artifacts/p0_dvwa_20261105_1520/capture-final")
    historic.extend(r["http_request"] for r in p0)
    known = defaultdict(set)
    previous_content = []
    with threadpool_limits(limits=1):
        for req in historic:
            k, co = c.keys(req, frozen, pv)
            for name, value in k.items():
                known[name].add(value)
            previous_content.append((req["method"], urlsplit(req["url"]).path, co))
    with np.load(
        ROOT
        / "ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz",
        allow_pickle=False,
    ) as data:
        known["view"].update(data["view"].astype(str).tolist())
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        parent[find(i)] = find(j)

    for i, row in enumerate(rows):
        if row["role"] == "PROSPECTIVE_EVALUATION":
            for name, value in row["keys"].items():
                if value in known[name]:
                    row["exclusions"].append("EXPOSED_" + name.upper())
            if any(
                method == row["method"]
                and endpoint == urlsplit(row["path"]).path
                and float(content[i] @ v) >= 0.995
                for method, endpoint, v in previous_content
            ):
                row["exclusions"].append("EXPOSED_NEAR_CONTENT")
        for j, other in enumerate(rows[:i]):
            same = any(
                row["keys"][name] == other["keys"][name]
                for name in ["raw", "template", "rich", "view"]
            )
            same = (
                same
                or row["candidate_view"] == other["candidate_view"]
                or row["session_group"] == other["session_group"]
                or row["campaign"] == other["campaign"]
            )
            near = (
                row["method"] == other["method"]
                and urlsplit(row["path"]).path == urlsplit(other["path"]).path
                and float(content[i] @ content[j]) >= 0.995
            )
            if same or near:
                join(i, j)
    roles = defaultdict(set)
    for i, r in enumerate(rows):
        roles[find(i)].add(r["role"])
    for i, r in enumerate(rows):
        r["component"] = find(i)
        if len(roles[find(i)]) > 1:
            r["exclusions"].append("CROSS_ROLE_CONNECTED_OVERLAP")
        r["exclusions"] = sorted(set(r["exclusions"]))
    views = defaultdict(set)
    for row in rows:
        if row["intent"] != "UNKNOWN":
            views[row["candidate_view"]].add(row["intent"])
    mixed = {key for key, intents in views.items() if len(intents) > 1}
    for row in rows:
        if row["candidate_view"] in mixed:
            row["exclusions"].append("MIXED_INTENT_CANDIDATE_VIEW")
    stats = coverage(rows, plan)
    # Seal prospective content/outcomes automatically, without scoring any model.
    prospective = [r for r in rows if r["role"] == "PROSPECTIVE_EVALUATION"]
    atomic_json(
        output / "prospective-manifest.json",
        {
            "plan_sha256": file_sha256(root / "precommitted-plan.json"),
            "experiment_fingerprint": lock["fingerprint"],
            "records": prospective,
            "scores_computed": 0,
            "claim": "Precommitted within exposed application lineage; NOT independent cross-domain or human-verified",
        },
    )
    prospective_indices = [i for i, r in enumerate(rows) if r["role"] == "PROSPECTIVE_EVALUATION"]
    np.savez(
        output / "prospective-features.npz",
        x=np.asarray(new_vectors)[prospective_indices],
        baseline=np.asarray(old_vectors)[prospective_indices],
    )
    atomic_json(
        output / "prospective-seal.json",
        {
            "manifest_sha256": file_sha256(output / "prospective-manifest.json"),
            "features_sha256": file_sha256(output / "prospective-features.npz"),
            "scope": "Logical hash seal, local permissions; not an inaccessible old sealed holdout",
            "no_scores": True,
        },
    )
    for role in ["TRAIN", "CALIBRATION"]:
        indices = [
            i
            for i, r in enumerate(rows)
            if r["role"] == role and not r["exclusions"] and r["intent"] != "UNKNOWN"
        ]
        np.savez(
            output / (role.lower() + ".npz"),
            x=np.asarray(new_vectors)[indices],
            baseline=np.asarray(old_vectors)[indices],
            y=np.array(
                [
                    CLASSES.index(rows[i]["family"]) if rows[i]["intent"] == "ATTACK_ATTEMPT" else 0
                    for i in indices
                ],
                dtype=np.int64,
            ),
            groups=np.array([rows[i]["component"] for i in indices], dtype=np.int64),
            ids=np.array([rows[i]["request_id"] for i in indices]),
        )
    with (output / "private-role-ledger.jsonl").open("x") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    with (output / "blind-review-queue.jsonl").open("x") as f:
        for row in rows:
            f.write(
                json.dumps(
                    {k: row[k] for k in ["request_id", "receipt_file", "receipt_sha256"]}
                    | {"reviewer": None, "decision": None, "reviewed_at": None}
                )
                + "\n"
            )
    summary = {
        "schema_version": "training-unblock-dataset-1",
        "receipts_verified": len(rows),
        "planned": len(plan["cases"]),
        "intent_counts": dict(Counter(r["intent"] for r in rows)),
        "attack_outcomes": dict(
            Counter(r["outcome"] for r in rows if r["intent"] == "ATTACK_ATTEMPT")
        ),
        "automated_semantic_rechecks": semantic_rechecks,
        "mixed_intent_candidate_views": len(mixed),
        "semantic_oracle_matches": sum(r["oracle_matched"] for r in rows),
        "independent_human_verified": 0,
        "review_pending": len(rows),
        "unique_raw_representations": len({r["keys"]["raw"] for r in rows}),
        "unique_frozen_views": len({r["keys"]["view"] for r in rows}),
        "unique_candidate_views": len({r["candidate_view"] for r in rows}),
        "coverage": stats,
        "excluded_cases": sum(bool(r["exclusions"]) for r in rows),
        "exclusion_counts": dict(Counter(x for r in rows for x in r["exclusions"])),
        "actual_component_counts": dict(
            Counter(r["role"] for i, r in enumerate(rows) if i == find(i))
        ),
        "TRAIN_connected_groups": len(
            {r["component"] for r in rows if r["role"] == "TRAIN" and not r["exclusions"]}
        ),
        "roles_changed_after_scores": False,
        "model_scores_computed": 0,
        "prospective_seal_sha256": file_sha256(output / "prospective-seal.json"),
        "GLU207_compatible": 0,
        "request_model_offline_full_body_headers": True,
        "data_coverage": "PASS"
        if len(rows) == len(plan["cases"]) and all(x["status"] == "PASS" for x in stats.values())
        else "FAIL",
        "limitations": [
            "Same DVWA/Juice source and shared fixture DB; session/workflow components are not independent environments",
            "At most two prospective templates per family and four benign rows; no population Recall/FPR or <=1% FPR claim",
            "Frozen model WAF exact views checked; global publisher raw/near provenance remains unverified",
            "No PCAP/EVE for new cohort, no Rule-only added-detection measurement",
            "Independent review PENDING; unsafe reflection not browser execution; no formal admission",
        ],
    }
    (output / "auditor-source.py").write_bytes(Path(__file__).read_bytes())
    summary["files_sha256"] = {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()}
    summary["dataset_fingerprint"] = digest(summary)
    atomic_json(output / "dataset-release.json", summary)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ["files_sha256", "limitations"]}, indent=2
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    audit(a.capture.resolve(), a.output.resolve())
