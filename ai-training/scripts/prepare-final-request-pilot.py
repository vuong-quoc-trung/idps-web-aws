#!/usr/bin/env python3
"""Append Oracle-backed calibration; audit only legacy TRAIN inputs, no evaluation peek."""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np

from idps_ai.common import CLASSES, atomic_json, digest, file_sha256
from idps_ai.features.research_request_channels import encode
from idps_ai.mvp_inference import ResearchMVP

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "ai-training/.artifacts/training_unblock_20261107"


def load(p):
    return json.loads(p.read_text())


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def verified_request(base, case):
    receipt = load(base / "receipt.json")
    h = load(base / "request-headers.json")
    rh = load(base / "response-headers.json")
    body = (base / "request-body.bin").read_bytes()
    response = (base / "response-body.bin").read_bytes()
    assert (
        receipt["request_id"] == case["request_id"]
        and receipt["method"] == case["method"]
        and receipt["path"] == case["path"]
    )
    assert file_sha256(base / "request-body.bin") == receipt["request_body_sha256"]
    assert (
        digest(h) == receipt["request_headers_sha256"]
        and digest(rh) == receipt["response_headers_sha256"]
    )
    assert file_sha256(base / "response-body.bin") == receipt["response_sha256"]
    return (
        dict(
            method=case["method"],
            url=case["path"],
            body=body.decode(),
            headers="\r\n".join(f"{k}: {v}" for k, v in h.items()),
        ),
        response,
        receipt,
    )


def prepare(addendum, output):
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    release = OLD / "dataset-release-final-v2"
    old = load(release / "dataset-release.json")
    for name in ["train.npz", "calibration.npz", "prospective-seal.json"]:
        assert file_sha256(release / name) == old["files_sha256"][name]
    # Only the seal record is read; prospective examples, labels and tensors stay closed.
    seal = load(release / "prospective-seal.json")
    assert seal["no_scores"]
    cap = load(addendum / "capture.json")
    plan = load(addendum / "cohort-plan.json")
    assert cap["status"] == "PASS" and plan["fingerprint"] == digest(
        {k: v for k, v in plan.items() if k != "fingerprint"}
    )
    assert (
        cap["application_source_sha256"]
        == file_sha256(addendum / "security-source.php")
        == plan["application_source_sha256"]
    )
    fc = module("final-calibration-capture")
    pv = module("p0-request-evaluate")
    uc = module("training-unblock-cohort")
    model = ResearchMVP("request-v2", cpus=1)
    added_keys = []
    for record in cap["records"]:
        assert (
            record["role"] == "CALIBRATION"
            and record["intent"] == "BENIGN"
            and record["semantic_oracle_matched"]
        )
        case = {"request_id": record["request_id"], "method": "POST", "path": "/security.php"}
        req, _, _ = verified_request(addendum / "receipts" / record["request_id"], case)
        before_id = record["before_request_id"]
        after_id = record["after_request_id"]
        _, before, _ = verified_request(
            addendum / "receipts" / before_id,
            {"request_id": before_id, "method": "GET", "path": "/security.php"},
        )
        _, after, _ = verified_request(
            addendum / "receipts" / after_id,
            {"request_id": after_id, "method": "GET", "path": "/security.php"},
        )
        assert (
            fc.selected(before) == record["before_level"] != record["target"]
            and fc.selected(after) == record["target"]
        )
        from urllib.parse import parse_qs

        fields = parse_qs(req["body"])
        assert fields["security"] == [record["target"]] and fields["user_token"] == [
            fc.token(before)
        ]
        returned = load(addendum / "receipts" / record["request_id"] / "response-headers.json")
        assert any(
            k.lower() == "set-cookie" and ("security=" + record["target"] + ";") in v
            for k, v in returned
        )
        k, _ = uc.keys(req, model, pv)
        added_keys.append(k)
    assert file_sha256(addendum / "calibration-addendum.npz") == cap["feature_file_sha256"]
    with np.load(release / "train.npz", allow_pickle=False) as d:
        train = {k: d[k].copy() for k in d.files}
    with np.load(release / "calibration.npz", allow_pickle=False) as d:
        cal = {k: d[k].copy() for k in d.files}
    with np.load(addendum / "calibration-addendum.npz", allow_pickle=False) as d:
        for k in cal:
            cal[k] = np.concatenate([cal[k], d[k]])
    # Opaque exclusion identifiers were committed before scores; no payload/label inspection.
    index = load(OLD / "campaign-capture-v2/preflight.json")["rows"]
    reserved = {
        name: {r["keys"][name] for r in index if r["role"] != "TRAIN"}
        for name in ["raw", "template", "rich", "view"]
    }
    for k in added_keys:
        for name in reserved:
            reserved[name].add(k[name])
    # Extract only candidate-view hash and role from the ledger; never parse prospective contents.
    reserved_candidate = set()
    with (release / "private-role-ledger.jsonl").open() as stream:
        for line in stream:
            role = re.search(r'"role"\s*:\s*"([A-Z_]+)"', line)[1]
            if role != "TRAIN":
                reserved_candidate.add(
                    re.search(r'"candidate_view"\s*:\s*"([a-f0-9]{64})"', line)[1]
                )
    reserved_candidate.update(hashlib.sha256(v.tobytes()).hexdigest() for v in cal["x"])
    legacy = module("quality-lab-cohort")
    assessor = module("assess-quality-cohort")
    selected = [c for c in legacy.cases() if c["role"] == "TRAIN"]
    assert len(selected) == 35
    accepted = []
    excluded = []
    seen = {hashlib.sha256(v.tobytes()).hexdigest() for v in train["x"]}
    for case in selected:
        root = (
            ROOT
            / "ai-training/.artifacts/quality_lab_20261107"
            / ("cohort-v3" if case["environment"] == "dvwa" else "cohort-v4-juice")
        )
        base = root / case["environment"] / "receipts" / case["request_id"]
        req, response, receipt = verified_request(base, case)
        assert req["body"] == case["body"]
        if case["environment"] == "juice":
            recovered = assessor.recover_juice(root, case, response, receipt["status"])
            matched = recovered["semantic_oracle_matched"]
        else:
            blocks = re.findall(
                r'<div id="guestbook_comments">(.*?)</div>', response.decode(errors="replace"), re.S
            )
            matched = any(
                "Name: LabReader<br />Message: " + case["expected"] + "<br />" in b for b in blocks
            )
        assert matched, "Legacy TRAIN Oracle recheck failed"
        k, _ = uc.keys(req, model, pv)
        x = encode(req)
        view = hashlib.sha256(x.tobytes()).hexdigest()
        reason = []
        if any(k[name] in reserved[name] for name in reserved) or view in reserved_candidate:
            reason.append("RESERVED_ROLE_EXACT_IDENTIFIER_OVERLAP")
        if view in seen:
            reason.append("TRAIN_EXACT_CANDIDATE_VIEW_DUPLICATE")
        if reason:
            excluded.append({"request_id": case["request_id"], "reasons": reason})
            continue
        seen.add(view)
        accepted.append(
            {
                "request_id": case["request_id"],
                "x": x,
                "baseline": pv.vector(model, req)[0],
                "y": CLASSES.index(case["family"]) if case["intent"] == "ATTACK_ATTEMPT" else 0,
                "group": 20000 + (case["environment"] == "juice"),
                "receipt_sha256": file_sha256(base / "receipt.json"),
            }
        )
    current_train_rows = len(train["x"])
    if accepted:
        for key, values in {
            "x": [r["x"] for r in accepted],
            "baseline": [r["baseline"] for r in accepted],
            "y": [r["y"] for r in accepted],
            "groups": [r["group"] for r in accepted],
            "ids": [r["request_id"] for r in accepted],
        }.items():
            train[key] = np.concatenate([train[key], np.asarray(values, dtype=train[key].dtype)])
    np.savez(output / "train.npz", **train)
    np.savez(output / "calibration.npz", **cal)
    assert not set(map(bytes, train["x"])).intersection(map(bytes, cal["x"]))
    benign = cal["y"] == 0
    frozen_unique = len({v.tobytes() for v in cal["baseline"][benign]})
    candidate_unique = len({v.tobytes() for v in cal["x"][benign]})
    assert frozen_unique >= 8 and candidate_unique >= 8 and len(set(cal["groups"][benign])) >= 4
    assert (
        old["coverage"]["TRAIN"]["status"] == "PASS"
        and old["coverage"]["PROSPECTIVE_EVALUATION"]["status"] == "PASS"
    )
    report = {
        "schema_version": "final-request-dataset-1",
        "parent_dataset_fingerprint": old["dataset_fingerprint"],
        "original_train_file_sha256": old["files_sha256"]["train.npz"],
        "original_train_rows_unchanged": current_train_rows,
        "calibration_addendum": {
            "physical_study_POSTs": 2,
            "semantic_Oracle_matches": 2,
            "views_candidate": 2,
            "views_frozen": 1,
            "review": "PENDING",
        },
        "calibration": {
            "known_rows": len(cal["x"]),
            "benign": int(benign.sum()),
            "attempts": int((~benign).sum()),
            "benign_unique_frozen_views": frozen_unique,
            "benign_unique_candidate_views": candidate_unique,
            "benign_workflow_components": len(set(cal["groups"][benign])),
            "GET_groups": 2,
            "POST_groups": 2,
            "JSON_POST_groups": 1,
            "form_POST_groups": 1,
            "old_UNKNOWN_retained": 3,
            "role_changed": False,
        },
        "fit": {
            "current_train_rows": current_train_rows,
            "legacy_TRAIN_considered": 35,
            "legacy_TRAIN_added": len(accepted),
            "legacy_TRAIN_excluded": len(excluded),
            "fit_rows": len(train["x"]),
            "candidate_unique_views": len(seen),
            "classes": {
                CLASSES[int(k)]: int(v) for k, v in zip(*np.unique(train["y"], return_counts=True))
            },
            "groups": len(set(train["groups"])),
            "legacy_provenance": "Previously audited Oracle TRAIN only, per-receipt reverified; stored guestbook persistence/reflection via source+response, no browser-execution or independent human claim",
        },
        "training_value": {
            "classification": "ENGINEERING_AND_SMALL_SAMPLE_FEASIBILITY_PILOT",
            "quality_improvement_evidence": "INSUFFICIENT; same two applications, few lineages, overparameterized vs sample count",
            "fine_tune": False,
            "initialization": "NEW_INITIALIZATION",
            "old_WAF": "Shared 512-dimensional content tensor cannot be decomposed into URI/body/header channels; publisher anomaly semantics differ from attack intent/family labels, not silently mixed",
            "GLU207": "Wrong feature contract; not mixed",
            "candidate_and_budget_changed": False,
        },
        "gates": {
            "DATA_COVERAGE": "PASS_FOR_PRECOMMITTED_RESEARCH_PILOT",
            "LABEL_PROVENANCE": "PASS_FOR_RESEARCH_REVIEW_PENDING",
            "SPLIT_INTEGRITY": "PASS_WITHIN_LOCKED_IDENTIFIER_TEMPLATE_CHECKS",
            "FEATURE_CONTRACT": "PASS_REQUEST588",
            "EVALUATION_PROTOCOL": "LOCKED_PROSPECTIVE_UNOPENED",
            "CHECKPOINT_RECOVERY": "SYNTHETIC_EXACT_NEXT_UPDATE_VERIFIED; real full resume not yet claimed",
            "RESOURCE_MONITORING": "EXISTING_GUARD_PLUS_INDEPENDENT_WATCHDOG",
            "FROZEN_BASELINE": "PROTECTED",
        },
        "prospective": {
            "rows": 12,
            "seal_record_sha256": file_sha256(release / "prospective-seal.json"),
            "scores_computed": 0,
            "contents_labels_tensors_opened": False,
            "access": "Only opaque role/view/template exclusion identifiers, no samples or labels",
        },
        "limits": [
            "No global publisher raw or exhaustive near-duplicate proof",
            "Legacy TRAIN source/schema/checks compatible, but two application sources do not establish independence",
            "New calibration is exposed internal Oracle research, not an independent FPR estimate",
        ],
        "files_sha256": {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()},
    }
    report["dataset_fingerprint"] = digest(report)
    atomic_json(output / "dataset-release.json", report)
    atomic_json(
        output / "legacy-admission.json",
        {
            "accepted": [
                {k: v for k, v in r.items() if k not in ["x", "baseline"]} for r in accepted
            ],
            "excluded": excluded,
        },
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--addendum", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    prepare(a.addendum.resolve(), a.output.resolve())
