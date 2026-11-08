#!/usr/bin/env python3
"""Additive634 derivative from privacy-qualified numeric receipts; no HTTP or fit."""

import argparse
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "ai-training/.artifacts/request_v3_body_syntax_20261108/release-v2"
VERSION = "request-v3-grounded-20261108-v1"
ROLES = ("TRAIN", "CALIBRATION", "DEVELOPMENT")


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def lock(capture, output):
    assert not output.exists()
    plan = load(capture / "plan.json")
    status = load(capture / "capture-status.json")
    assert status["status"] == "COMPLETED"
    assert status["phases"]["preflight"]["Oracle_verified"] == 9
    assert status["phases"]["main"]["Oracle_verified"] == 12
    assert load(capture / "actual-value-privacy-check.json")["status"] == "PASS_FOR_RESEARCH"
    m = module("materialize-request-v3")
    parent_plan = load(PARENT / "plan.json")
    p = {
        "schema_version": "grounded634-materialization-plan-1",
        "dataset_version": VERSION,
        "capture_root": str(capture.relative_to(ROOT)),
        "capture_plan_fingerprint": plan["fingerprint"],
        "parent_fingerprint": load(PARENT / "dataset-release.json")["dataset_fingerprint"],
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "capture_files_sha256": {
            n: file_sha256(capture / n)
            for n in [
                "plan.json",
                "fixture-amendment.json",
                "capture-status.json",
                "preflight-oracle-receipts.json",
                "main-oracle-receipts.json",
                "safe-audit-records.jsonl",
                "safe-feature-receipts.npz",
                "full-near-relation-witness.json",
                "actual-value-privacy-check.json",
            ]
        },
        "source_sha256": {
            str(p.relative_to(ROOT)): file_sha256(p)
            for p in [
                Path(__file__),
                Path(m.__file__),
                ROOT / "ai-training/src/idps_ai/features/request_v3.py",
                ROOT / "ai-training/src/idps_ai/features/body_syntax_v1.py",
            ]
        },
        "coverage_minimums": parent_plan["coverage_minimums"],
        "additional_coverage": plan["coverage"],
        "deduplication": "Reuse locked audit; retain all inherited exclusions and transient full-near witness; both sides quarantine; no role reassignment",
        "paired_evaluation": "Old rows: parent-strict intersection with new-strict. New main controls: new-strict, same IDs for every arm. Canonical sample ID per candidate exact view, pre-score selection only.",
        "privacy": "Only previously privacy-qualified numeric tensors and schema-selected safe metadata; no raw requests or secret-derived equality keys",
        "sealed": "NOT_OPENED_NOT_USED",
        "fit_statistics": 0,
        "training": False,
    }
    p["fingerprint"] = digest(p)
    atomic_json(output, p)
    print(json.dumps({"materialization_plan_fingerprint": p["fingerprint"]}))


def augment_coverage(m, rows, x, syntax, ix):
    r = m.coverage(rows, x, syntax, ix)
    benign = [i for i in ix if rows[i]["intent"] == "BENIGN_INTENT"]

    def unique(indices):
        return len({m.vector_hash(x[i]) for i in indices})

    post = [i for i in benign if rows[i]["method"] == "POST"]
    r.update(
        benign_POST_unique_views=unique(post),
        benign_JSON_POST=int(sum(syntax[i, 12] == 1 for i in post)),
        benign_FORM_POST=int(sum(syntax[i, 11] == 1 for i in post)),
        benign_command_like=sum(
            rows[i]["endpoint_template"] == "/vulnerabilities/exec/" for i in benign
        ),
        benign_file_like=sum(
            rows[i]["endpoint_template"] == "/vulnerabilities/fi/" for i in benign
        ),
        body_states_by_intent={
            n: dict(
                Counter(body.state_of(syntax[i].tolist()) for i in ix if rows[i]["intent"] == n)
            )
            for n in ["BENIGN_INTENT", "ATTACK_INTENT"]
        },
    )
    return r


def materialize(plan_path, output):
    plan = load(plan_path)
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert plan["feature_contract_fingerprint"] == request_v3.fingerprint()
    for p, sha in plan["source_sha256"].items():
        assert file_sha256(ROOT / p) == sha
    capture = ROOT / plan["capture_root"]
    for p, sha in plan["capture_files_sha256"].items():
        assert file_sha256(capture / p) == sha
    parent = load(PARENT / "dataset-release.json")
    assert parent["dataset_fingerprint"] == plan["parent_fingerprint"]
    for p, sha in parent["files_sha256"].items():
        assert file_sha256(PARENT / p) == sha
    rows = [json.loads(s) for s in (capture / "safe-audit-records.jsonl").read_text().splitlines()]
    old = [json.loads(s) for s in (PARENT / "records.jsonl").read_text().splitlines()]
    receipts = load(capture / "main-oracle-receipts.json")
    assert len(old) == 224 and len(rows) == 236 and len(receipts) == 12
    assert (
        len({r["sample_id"] for r in rows}) == 236 and len({r["request_id"] for r in rows}) == 236
    )
    assert [r["sample_id"] for r in rows[:224]] == [r["sample_id"] for r in old]
    assert [r["sample_id"] for r in rows[224:]] == [r["sample_id"] for r in receipts]
    m = module("materialize-request-v3")
    with np.load(capture / "safe-feature-receipts.npz", allow_pickle=False) as z:
        x, frozen, syntax = z["x"].copy(), z["frozen_runtime"].copy(), z["body_syntax"].copy()
        assert list(z["ids"]) == [r["sample_id"] for r in rows]
    assert x.shape == (236, 634) and x.dtype == np.float32 and np.isfinite(x).all()
    assert frozen.shape == (236, 588) and frozen.dtype == np.float32 and np.isfinite(frozen).all()
    assert syntax.shape == (236, 46) and syntax.dtype == np.uint8
    for i, r in enumerate(rows):
        assert r["split"] == r["original_role"] and r["split"] in ROLES
        assert all(
            str(r["checksums"][k]).startswith(k + "-equivalence-")
            for k in ["raw", "template", "full_view"]
        )
        body.validate_event(body.event(r["request_id"], syntax[i].tolist()))
        assert np.array_equal(x[i], request_v3.assemble(frozen[i], syntax[i].tolist()))
        if i < 224:
            assert all(
                r[k] == old[i][k]
                for k in [
                    "intent",
                    "outcome",
                    "oracle_verified",
                    "request_id",
                    "original_role",
                    "workflow_group",
                ]
            )
        else:
            assert r["oracle_verified"] and r["observation_status"] == "ORACLE_VERIFIED"
            assert (
                r["intent"] == r["planned_intent"]
                and r["environment_fingerprint"]
                == load(capture / "plan.json")["environment_fingerprint"]
            )
            assert r["review_status"] == "PENDING" and not r["independent_human_verified"]
    parent_by_id = {}
    for role in ROLES:
        with np.load(PARENT / (role.lower() + ".npz"), allow_pickle=False) as z:
            parent_by_id.update(
                {
                    str(s): (v, f, b)
                    for s, v, f, b in zip(
                        z["ids"], z["x"], z["frozen_runtime"], z["body_syntax"], strict=True
                    )
                }
            )
    assert all(
        all(
            np.array_equal(a, b)
            for a, b in zip((x[i], frozen[i], syntax[i]), parent_by_id[r["sample_id"]], strict=True)
        )
        for i, r in enumerate(rows[:224])
    )
    reasons, overlaps, near = m.audit(rows, frozen, x)
    split = m.validate_split(rows, reasons, x, near)
    assert all(
        rows[i]["oracle_verified"] and rows[i]["intent"] in {"BENIGN_INTENT", "ATTACK_INTENT"}
        for i in range(len(rows))
        if not reasons[i]
    )
    reports = {}
    before_report = load(PARENT / "materialization-report.json")
    for role in ROLES:
        ix = [i for i, r in enumerate(rows) if r["split"] == role]
        eligible = [i for i in ix if not reasons[i]]
        before = before_report["role_reports"][role]["candidate_strict"]
        reports[role] = {
            "before": before,
            "after": augment_coverage(m, rows, x, syntax, eligible),
            "total_records": len(ix),
            "excluded": len(ix) - len(eligible),
            "UNKNOWN": sum(rows[i]["intent"] == "UNKNOWN_INTENT" for i in ix),
            "new_main_records": sum(i >= 224 for i in ix),
            "new_strict_records": sum(i >= 224 for i in eligible),
            "newly_excluded_parent_strict": sum(
                i < 224 and old[i]["eligible_for_research"] and bool(reasons[i]) for i in ix
            ),
        }
    train = m.coverage_pass(reports["TRAIN"]["after"], "TRAIN", plan["coverage_minimums"]["TRAIN"])
    cal = m.coverage_pass(
        reports["CALIBRATION"]["after"], "CALIBRATION", plan["coverage_minimums"]["CALIBRATION"]
    )
    dev = reports["DEVELOPMENT"]["after"]
    dev_checks = {
        "benign_POST_unique_views": dev["benign_POST_unique_views"]
        >= plan["additional_coverage"]["DEV_benign_POST_unique_views"],
        "benign_POST_workflows": dev["benign_POST_workflows"]
        >= plan["additional_coverage"]["DEV_benign_POST_workflows"],
        "benign_POST_media": set(plan["additional_coverage"]["DEV_benign_POST_media"])
        <= set(dev["benign_POST_media"]),
    }
    train_new = [
        i
        for i in range(224, 236)
        if not reasons[i] and rows[i]["split"] == "TRAIN" and rows[i]["intent"] == "BENIGN_INTENT"
    ]
    train_checks = {
        "new_JSON_POST_views": len(
            {
                m.vector_hash(x[i])
                for i in train_new
                if rows[i]["method"] == "POST" and syntax[i, 12] == 1
            }
        )
        >= plan["additional_coverage"]["TRAIN_new_JSON_POST_views"],
        "new_command_counterpart": sum(
            rows[i]["endpoint_template"] == "/vulnerabilities/exec/" for i in train_new
        )
        >= plan["additional_coverage"]["TRAIN_command_counterpart_views"],
        "new_file_counterpart": sum(
            rows[i]["endpoint_template"] == "/vulnerabilities/fi/" for i in train_new
        )
        >= plan["additional_coverage"]["TRAIN_file_counterpart_views"],
    }
    missing = {
        r["intent"]
        for i, r in enumerate(rows)
        if not reasons[i] and body.state_of(syntax[i].tolist()) == "MISSING"
    }
    gates = {
        "DATASET_INTEGRITY": "PASS",
        "FEATURE_CONTRACT": "PASS",
        "ORACLE_PROVENANCE": "PASS_FOR_RESEARCH",
        "STRICT_SPLITS": split["status"],
        "TRAIN_COVERAGE": train,
        "TRAIN_ADDITIONAL_COVERAGE": {
            "status": "PASS" if all(train_checks.values()) else "FAIL",
            "checks": train_checks,
        },
        "DEV_COVERAGE": {
            "status": "PASS" if all(dev_checks.values()) else "FAIL",
            "checks": dev_checks,
        },
        "CALIBRATION_VALIDITY": cal,
        "NATURAL_MISSING_NOT_BENIGN_ONLY": missing >= {"BENIGN_INTENT", "ATTACK_INTENT"},
    }
    aliases = m.surrogate_groups(rows)
    derivative = []
    keep = [
        "sample_id",
        "request_id",
        "environment",
        "source",
        "workflow_group",
        "intent",
        "outcome",
        "review_status",
        "evidence_levels",
        "oracle_verified",
        "oracle_replay",
        "independent_human_verified",
        "method",
        "endpoint_template",
        "family",
        "prior_exposure",
    ]
    for i, r in enumerate(rows):
        item = {k: r[k] for k in keep}
        item.update(
            aliases[i],
            dataset_version=VERSION,
            original_role=r["split"],
            parent_dataset_fingerprint=plan["parent_fingerprint"],
            parent_record_index=i if i < 224 else None,
            observation_status=r.get("observation_status", "INHERITED_PARENT_ORACLE_FLAG"),
            execution_id=r.get("execution_id", "INHERITED_PARENT"),
            environment_fingerprint=r.get("environment_fingerprint", "INHERITED_PARENT"),
            checksums=r["checksums"],
            oracle_checks=r.get("oracle_checks", {}),
            feature_contract_fingerprint=request_v3.fingerprint(),
            body_contract_sha256=body.CONTRACT_SHA256,
            body_syntax_vector=syntax[i].tolist(),
            state=body.state_of(syntax[i].tolist()),
            inclusion_exclusion_reasons=sorted(reasons[i]),
            eligible_for_research=not reasons[i],
            eligible_for_fit=r["split"] == "TRAIN" and not reasons[i],
            feature_compatibility={
                "request_v3": True,
                "frozen_runtime_prefix": True,
                "GLU207": False,
            },
            source_reference={"capture_file": "safe-feature-receipts.npz", "row": i},
        )
        derivative.append(item)
    fp = digest(
        {
            "records": derivative,
            "plan_fingerprint": plan["fingerprint"],
            "parent_fingerprint": plan["parent_fingerprint"],
        }
    )
    for r in derivative:
        r["dataset_fingerprint"] = fp
    assert output.is_relative_to(ROOT / "ai-training/.artifacts")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "feature-contract.json", request_v3.contract())
    (output / "records.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in derivative)
    )
    for role in ROLES:
        ix = [i for i, r in enumerate(rows) if r["split"] == role]
        np.savez(
            output / (role.lower() + ".npz"),
            x=x[ix],
            frozen_runtime=frozen[ix],
            body_syntax=syntax[ix],
            ids=np.array([rows[i]["sample_id"] for i in ix]),
            binary_y=np.array(
                [
                    0
                    if rows[i]["intent"] == "BENIGN_INTENT"
                    else 1
                    if rows[i]["intent"] == "ATTACK_INTENT"
                    else -1
                    for i in ix
                ],
                np.int64,
            ),
            eligible=np.array([not reasons[i] for i in ix]),
            paired_common_eligible=np.array(
                [not reasons[i] and (i >= 224 or old[i]["eligible_for_research"]) for i in ix]
            ),
        )
    report = {
        "dataset_version": VERSION,
        "dataset_fingerprint": fp,
        "parent_fingerprint": plan["parent_fingerprint"],
        "plan_fingerprint": plan["fingerprint"],
        "rows": 236,
        "parent_parity_rows": 224,
        "feature_parity_rows": 236,
        "role_reports": reports,
        "gates": gates,
        "split_audit": split,
        "all_collisions": {"frozen": m.collision(rows, frozen), "candidate": m.collision(rows, x)},
        "excluded_reasons": dict(Counter(v for group in reasons for v in group)),
        "cross_role_groups_before_quarantine": dict(overlaps),
        "near_pairs": {
            "candidate_all": len(near),
            "candidate_cross_role": sum(rows[a]["split"] != rows[b]["split"] for a, b in near),
        },
        "full_near_witness_sha256": file_sha256(capture / "full-near-relation-witness.json"),
        "Oracle_verified": sum(r["oracle_verified"] for r in rows),
        "review_pending": sum(r["review_status"] == "PENDING" for r in rows),
        "independent_human_verified": 0,
        "sealed_overlap": "UNVERIFIED_NOT_OPENED",
        "GLU207": "NOT_AVAILABLE_REQUEST_ONLY",
        "scores_computed": 0,
        "fit_statistics": 0,
        "training_updates": 0,
        "new_checkpoints": 0,
        "files_sha256": {p.name: file_sha256(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    atomic_json(output / "materialization-report.json", report)
    print(
        json.dumps(
            {
                "dataset_fingerprint": fp,
                "gates": gates,
                "roles": {
                    r: {
                        k: reports[r]["after"][k]
                        for k in [
                            "records",
                            "unique_views",
                            "intents",
                            "benign_POST_unique_views",
                            "benign_POST_media",
                        ]
                    }
                    for r in ROLES
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["lock", "materialize"])
    p.add_argument("--capture", type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        if a.action == "lock":
            lock(a.capture.resolve(), a.plan.resolve())
        else:
            materialize(a.plan.resolve(), a.output.resolve())
