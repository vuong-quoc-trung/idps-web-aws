#!/usr/bin/env python3
"""Bounded local derivative of a pinned, exposed release. No network or model fit."""

import argparse
import importlib.metadata
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import (
    dataset_fingerprint,
    read_receipt,
    validate_record,
    vector_hash,
)
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3 as candidate

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai-training/.artifacts/attack_intent_20261107/release-v3"
PARENT_FP = "fa9a2d87852afea879ed146d4bd8077e8a070d42337d6b36ffe836686a4fef5f"
VERSION = "request-v3-body-syntax-20261108-v1"
ROLES = ("TRAIN", "CALIBRATION", "DEVELOPMENT")
FAMILIES = ("sqli", "xss", "cmd_injection", "path_traversal")
REPLACED = {
    "OPPOSITE_INTENT_IDENTICAL_RUNTIME_VIEW",
    "CROSS_ROLE_RUNTIME_VIEW",
    "CROSS_ROLE_NEAR_RUNTIME",
    "WITHIN_ROLE_DUPLICATE_VIEW",
}
CODE = [
    "ai-training/scripts/materialize-request-v3.py",
    "ai-training/scripts/verify-request-v3.py",
    "ai-training/src/idps_ai/features/request_v3.py",
    "ai-training/src/idps_ai/features/body_syntax_v1.py",
    "ai-training/src/idps_ai/data/attack_intent.py",
    "ai-training/configs/research/request-v3-body-syntax-v1.json",
]


def load(p):
    return json.loads(p.read_text())


def lock(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Plan already exists")
    parent = load(SOURCE / "dataset-release.json")
    assert parent["dataset_fingerprint"] == PARENT_FP
    plan = {
        "schema_version": "request-v3-data-plan-1",
        "dataset_version": VERSION,
        "parent_fingerprint": PARENT_FP,
        "parent_manifest_sha256": file_sha256(SOURCE / "dataset-release.json"),
        "source_sha256": {p: file_sha256(ROOT / p) for p in CODE},
        "contract": candidate.contract(),
        "contract_fingerprint": candidate.fingerprint(),
        "roles": "Inherit original roles exactly; no requests, scores, fits, sealed payloads or role reassignment",
        "replaced_exclusions": sorted(REPLACED),
        "retained_exclusions": "All other inherited exclusions, including raw/template/full-view/full-near, session/campaign and transitive connected components (including excluded bridge rows), prior admissions and Oracle/UNKNOWN/reserved keys",
        "exact_rule": "Quarantine opposite known-intent exact views and both sides of cross-role exact views. Canonical sample-ID dedup within role on (full-view,candidate-view); no label-based representative choice",
        "near_rule": {
            "scope": "All pairs, same HTTP method and endpoint template; across roles quarantine BOTH sides, irrespective of label. Inherit historical full-view-near exclusions",
            "runtime_content_cosine_min": 0.995,
            "tolerance": 1e-7,
            "candidate_body_normalized_linf_max": 1 / 3,
            "reason": "One clipped punctuation-count unit; binary state/media/syntax flag differences of1 are never near. Content and body must both be near, avoiding scale domination by either block",
        },
        "coverage_minimums": {
            "TRAIN": {
                "benign_unique_views": 12,
                "views_per_attack_family": 2,
                "workflow_categories": 4,
                "benign_GET_workflows": 1,
                "benign_POST_workflows": 2,
                "benign_POST_media": ["FORM", "JSON"],
                "lineage_components_per_known_intent": 2,
                "same_surface_benign_counterpart_each_family": True,
            },
            "CALIBRATION": {
                "benign_unique_views": 8,
                "benign_GET_workflows": 2,
                "benign_POST_workflows": 2,
                "benign_POST_media": ["FORM", "JSON"],
                "benign_lineage_components": 2,
                "attack_unique_views": 2,
            },
        },
        "interpretation": "Minimum research-pilot screens, not population FPR or independent model-quality certification. No learned normalization statistics",
        "sealed": "Do not open sealed content, labels, vectors or mixed ledgers; keep inherited opaque exclusions. Candidate overlap with sealed representations remains UNVERIFIED; no prospective evaluation authorized by this plan",
        "lineage_output": "Sequential surrogate IDs preserve session/campaign equivalence only. Never copy inherited group values or cookie digests; original parent-record reference remains local",
        "GLU207": "Not a dependency of request-only offline research; no207 features synthesized",
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scikit-learn": importlib.metadata.version("scikit-learn"),
        },
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(path, plan)
    print(json.dumps({"plan_fingerprint": plan["fingerprint"], "scores": 0, "fits": 0}))


def groups(keys):
    result = defaultdict(list)
    for i, key in enumerate(keys):
        result[key].append(i)
    return list(result.values())


def collision(rows, matrix, indices=None):
    ix = list(range(len(rows))) if indices is None else list(indices)
    g = groups([vector_hash(matrix[i]) for i in ix])
    mixed = [
        v for v in g if {rows[ix[i]]["intent"] for i in v} >= {"BENIGN_INTENT", "ATTACK_INTENT"}
    ]
    return {
        "records": len(ix),
        "unique_views": len(g),
        "duplicate_groups": sum(len(v) > 1 for v in g),
        "duplicate_extra_records": sum(len(v) - 1 for v in g),
        "mixed_groups": len(mixed),
        "mixed_affected_records": sum(map(len, mixed)),
        "mixed_known_records": sum(
            rows[ix[i]]["intent"] != "UNKNOWN_INTENT" for v in mixed for i in v
        ),
    }


def near_pairs(rows, runtime, syntax, *, use_body):
    sim = runtime[:, 76:].astype(np.float64) @ runtime[:, 76:].astype(np.float64).T
    out = []
    for i in range(len(rows)):
        for j in range(i):
            if (
                rows[i]["method"] != rows[j]["method"]
                or rows[i]["endpoint_template"] != rows[j]["endpoint_template"]
            ):
                continue
            if sim[i, j] < 0.995 - 1e-7:
                continue
            if use_body and np.max(np.abs(syntax[i] - syntax[j])) > 1 / 3 + 1e-7:
                continue
            out.append((j, i))
    return out


def audit(rows, runtime, joint):
    """Replace representation exclusions only; preserve all preexisting lineage gates."""
    reasons = [set(r["inclusion_exclusion_reasons"]) - REPLACED for r in rows]
    overlaps = Counter()
    for kind in ["raw", "template", "full_view", "session_group", "campaign_group", "request_id"]:
        keys = [r["checksums"][kind] if kind in r["checksums"] else r[kind] for r in rows]
        for ix in groups(keys):
            if len({rows[i]["split"] for i in ix}) > 1:
                overlaps[kind] += 1
                for i in ix:
                    reasons[i].add("CROSS_ROLE_" + kind.upper())
    roots = lineage_roots(rows)
    for ix in groups([roots[i] for i in range(len(rows))]):
        if len({rows[i]["split"] for i in ix}) > 1:
            overlaps["lineage_component"] += 1
            for i in ix:
                reasons[i].add("CROSS_ROLE_LINEAGE_COMPONENT")
    for ix in groups([vector_hash(v) for v in joint]):
        mixed = {rows[i]["intent"] for i in ix} >= {"BENIGN_INTENT", "ATTACK_INTENT"}
        cross = len({rows[i]["split"] for i in ix}) > 1
        overlaps["candidate_view"] += cross
        for i in ix:
            if mixed:
                reasons[i].add("OPPOSITE_INTENT_IDENTICAL_CANDIDATE_VIEW")
            if cross:
                reasons[i].add("CROSS_ROLE_CANDIDATE_VIEW")
    near = near_pairs(rows, runtime, joint[:, 588:], use_body=True)
    for a, b in near:
        if rows[a]["split"] != rows[b]["split"]:
            for i in [a, b]:
                reasons[i].add("CROSS_ROLE_NEAR_CANDIDATE")
    seen = set()
    for i in sorted(range(len(rows)), key=lambda i: rows[i]["sample_id"]):
        key = (rows[i]["split"], rows[i]["checksums"]["full_view"], vector_hash(joint[i]))
        if key in seen:
            reasons[i].add("WITHIN_ROLE_DUPLICATE_CANDIDATE_VIEW")
        seen.add(key)
    return reasons, overlaps, near


def lineage_roots(rows):
    # Conservative connected components from recorded session/campaign lineage.
    parent = {i: i for i in range(len(rows))}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for kind in ["session_group", "campaign_group"]:
        seen = {}
        for i in range(len(rows)):
            value = rows[i][kind]
            if value in seen:
                parent[root(i)] = root(seen[value])
            seen[value] = i
    return {i: root(i) for i in range(len(rows))}


def surrogate_groups(rows):
    """Opaque ordinal aliases, not hashes of input identifiers or secrets."""
    maps = {k: {} for k in ["session_group", "campaign_group"]}
    out = []
    for row in rows:
        item = {}
        for kind, lookup in maps.items():
            value = row[kind]
            if value not in lookup:
                lookup[value] = f"{kind}-{len(lookup) + 1:04d}"
            item[kind] = lookup[value]
        out.append(item)
    return out


def components(rows, ix):
    roots = lineage_roots(rows)
    return len({roots[i] for i in ix})


def coverage(rows, matrix, syntax, ix):
    benign = [i for i in ix if rows[i]["intent"] == "BENIGN_INTENT"]
    attacks = [i for i in ix if rows[i]["intent"] == "ATTACK_INTENT"]

    def unique(selected):
        return len({vector_hash(matrix[i]) for i in selected})

    def surface(i):
        return tuple(rows[i][k] for k in ["environment", "method", "endpoint_template"])

    benign_surfaces = {surface(i) for i in benign}
    return {
        **collision(rows, matrix, ix),
        "intents": dict(Counter(rows[i]["intent"] for i in ix)),
        "unique_benign_views": unique(benign),
        "unique_attack_views": unique(attacks),
        "workflow_categories": len({rows[i]["workflow_group"] for i in ix}),
        "lineage_components": components(rows, ix),
        "lineage_components_by_intent": {
            name: components(rows, sub)
            for name, sub in [("BENIGN_INTENT", benign), ("ATTACK_INTENT", attacks)]
        },
        "family_views": {
            f: unique([i for i in attacks if rows[i]["family"] == f]) for f in FAMILIES
        },
        "family_workflows": {
            f: len({rows[i]["workflow_group"] for i in attacks if rows[i]["family"] == f})
            for f in FAMILIES
        },
        "families_with_same_surface_benign": {
            f: any(surface(i) in benign_surfaces for i in attacks if rows[i]["family"] == f)
            for f in FAMILIES
        },
        "benign_GET_workflows": len(
            {rows[i]["workflow_group"] for i in benign if rows[i]["method"] == "GET"}
        ),
        "benign_POST_workflows": len(
            {rows[i]["workflow_group"] for i in benign if rows[i]["method"] == "POST"}
        ),
        "benign_POST_media": sorted(
            {
                body.MEDIA[int(np.argmax(syntax[i, 11:15]))]
                for i in benign
                if rows[i]["method"] == "POST"
            }
        ),
        "methods_by_intent": {
            n: dict(Counter(rows[i]["method"] for i in sub))
            for n, sub in [("BENIGN_INTENT", benign), ("ATTACK_INTENT", attacks)]
        },
        "environments_by_intent": {
            n: dict(Counter(rows[i]["environment"] for i in sub))
            for n, sub in [("BENIGN_INTENT", benign), ("ATTACK_INTENT", attacks)]
        },
        "body_states": dict(Counter(body.state_of(syntax[i].tolist()) for i in ix)),
        "media_types": dict(Counter(body.MEDIA[int(np.argmax(syntax[i, 11:15]))] for i in ix)),
        "Oracle_verified": sum(rows[i]["oracle_verified"] for i in ix),
        "review_pending": sum(rows[i]["review_status"] == "PENDING" for i in ix),
        "workflow_inventory": [
            {
                "workflow": w,
                "intent": n,
                "rows": len(v),
                "unique_views": unique(v),
                "lineage_components": components(rows, v),
            }
            for (w, n), v in sorted(_workflow_groups(rows, ix).items())
        ],
        "hard_negative_policy": "Report eligible BENIGN_INTENT workflow inventory; no new hard-negative label inferred from scores or punctuation",
    }


def _workflow_groups(rows, ix):
    g = defaultdict(list)
    for i in ix:
        g[(rows[i]["workflow_group"], rows[i]["intent"])].append(i)
    return g


def coverage_pass(report, role, minimum):
    gates = {
        "benign_unique_views": report["unique_benign_views"] >= minimum["benign_unique_views"],
        "benign_GET_workflows": report["benign_GET_workflows"] >= minimum["benign_GET_workflows"],
        "benign_POST_workflows": report["benign_POST_workflows"]
        >= minimum["benign_POST_workflows"],
        "benign_POST_media": set(minimum["benign_POST_media"]) <= set(report["benign_POST_media"]),
    }
    if role == "TRAIN":
        gates.update(
            attack_families=all(
                v >= minimum["views_per_attack_family"] for v in report["family_views"].values()
            ),
            workflow_categories=report["workflow_categories"] >= minimum["workflow_categories"],
            lineage_components=all(
                v >= minimum["lineage_components_per_known_intent"]
                for v in report["lineage_components_by_intent"].values()
            ),
            benign_counterpart=all(report["families_with_same_surface_benign"].values()),
        )
    else:
        gates.update(
            attack_unique_views=report["unique_attack_views"] >= minimum["attack_unique_views"],
            benign_lineage=report["lineage_components_by_intent"]["BENIGN_INTENT"]
            >= minimum["benign_lineage_components"],
        )
    return {"status": "PASS" if all(gates.values()) else "FAIL", "checks": gates}


def validate_split(rows, reasons, matrix, near):
    eligible = {i for i, r in enumerate(reasons) if not r}
    for kind in [
        "raw",
        "template",
        "full_view",
        "session_group",
        "campaign_group",
        "request_id",
        "candidate_view",
    ]:
        seen = {}
        for i in sorted(eligible):
            r = rows[i]
            key = (
                vector_hash(matrix[i])
                if kind == "candidate_view"
                else r["checksums"][kind]
                if kind in r["checksums"]
                else r[kind]
            )
            if key in seen and seen[key] != r["split"]:
                raise ValueError("Eligible cross-role identity/lineage overlap")
            seen[key] = r["split"]
    assert not any(
        a in eligible and b in eligible and rows[a]["split"] != rows[b]["split"] for a, b in near
    )
    roots = lineage_roots(rows)
    component_roles = defaultdict(set)
    for i, r in enumerate(rows):
        component_roles[roots[i]].add(r["split"])
    seen_roots = {}
    for i in sorted(eligible):
        assert len(component_roles[roots[i]]) == 1
        key = roots[i]
        assert key not in seen_roots or seen_roots[key] == rows[i]["split"]
        seen_roots[key] = rows[i]["split"]
    return {
        "status": "PASS",
        "scope": "Permitted exposed roles only; sealed candidate/runtime overlap UNVERIFIED",
        "eligible_cross_role_exact_lineage_near_overlaps": 0,
    }


def materialize(plan_path, output):
    assert output.is_relative_to(ROOT / "ai-training/.artifacts")
    plan = load(plan_path)
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert plan["contract_fingerprint"] == candidate.fingerprint()
    for name, sha in plan["source_sha256"].items():
        assert file_sha256(ROOT / name) == sha
    assert file_sha256(SOURCE / "dataset-release.json") == plan["parent_manifest_sha256"]
    parent = load(SOURCE / "dataset-release.json")
    for name, sha in parent["files_sha256"].items():
        assert file_sha256(SOURCE / name) == sha
    rows = [json.loads(line) for line in (SOURCE / "records.jsonl").read_text().splitlines()]
    assert (
        dataset_fingerprint(rows, parent["files_sha256"], parent["plan_fingerprint"]) == PARENT_FP
    )
    assert len(rows) == 224 and len({r["sample_id"] for r in rows}) == 224
    runtime_by_id = {}
    for role in ROLES:
        with np.load(SOURCE / (role.lower() + ".npz"), allow_pickle=False) as z:
            assert z["runtime"].shape[1] == 588
            runtime_by_id.update(
                {
                    str(s): (v.copy(), bool(e), j)
                    for j, (s, v, e) in enumerate(
                        zip(z["ids"], z["runtime"], z["eligible"], strict=True)
                    )
                }
            )
    runtime = np.stack([runtime_by_id[r["sample_id"]][0] for r in rows])
    vectors = []
    provenance = []
    for r in rows:
        validate_record(r)
        assert r["split"] in ROLES and r["split"] == r["declared_role"]
        assert bool(not r["inclusion_exclusion_reasons"]) == runtime_by_id[r["sample_id"]][1]
        assert vector_hash(runtime_by_id[r["sample_id"]][0]) == r["checksums"]["runtime_view"]
        folder = Path(r["request_provenance"]["receipt_file"]).parent.resolve()
        assert ROOT / "ai-training/.artifacts" in folder.parents
        req, receipt = read_receipt(folder, request_id=r["request_id"])
        assert file_sha256(folder / "receipt.json") == r["checksums"]["receipt"]
        assert req["method"] == r["method"]
        headers = {k.lower(): v for k, v in load(folder / "request-headers.json").items()}
        raw = (folder / "request-body.bin").read_bytes()
        observed = raw if raw or "content-length" in headers else None
        vec = body.extract(
            observed,
            headers.get("content-type"),
            content_encoding=headers.get("content-encoding"),
            transfer_encoding=headers.get("transfer-encoding"),
        )
        body.validate_event(body.event(r["request_id"], vec))
        vectors.append(vec)
        provenance.append(
            {
                "source_receipt_verified": True,
                "source_record_index": len(provenance),
                "body_available": observed is not None,
                "body_nonempty": bool(raw),
            }
        )
        # Neither raw request nor headers/response/values are copied to derivative artifacts.
        del raw, observed, headers, req, receipt
    syntax = np.array(vectors, np.uint8)
    joint = np.stack(
        [candidate.assemble(v, b.tolist()) for v, b in zip(runtime, syntax, strict=True)]
    )
    # Independent existing materialization witness, selected only by exposed sample IDs.
    prior = ROOT / "ai-training/.artifacts/body_syntax_20261107/diagnostics-v1/body-features.npz"
    with np.load(prior, allow_pickle=False) as z:
        prior_by_id = {str(i): v for i, v in zip(z["ids"], z["features"], strict=True)}
        assert all(
            np.array_equal(v, prior_by_id[r["sample_id"]])
            for r, v in zip(rows, syntax, strict=True)
        )
    reasons, overlap, near = audit(rows, runtime, joint)
    split = validate_split(rows, reasons, joint, near)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic_json(output / "feature-contract.json", plan["contract"])
    atomic_json(output / "plan.json", plan)
    reports = {}
    for role in ROLES:
        ix = [i for i, r in enumerate(rows) if r["split"] == role]
        eligible = [i for i in ix if not reasons[i]]
        old = [i for i in ix if not rows[i]["inclusion_exclusion_reasons"]]
        common = sorted(set(old) & set(eligible))
        reports[role] = {
            "all": {
                "frozen": collision(rows, runtime, ix),
                "candidate": collision(rows, joint, ix),
            },
            "parent_strict": coverage(rows, runtime, syntax, old),
            "candidate_strict": coverage(rows, joint, syntax, eligible),
            "paired_common_strict": {
                "frozen": collision(rows, runtime, common),
                "candidate": collision(rows, joint, common),
            },
            "eligibility_changes": {
                "newly_eligible": len(set(eligible) - set(old)),
                "newly_excluded": len(set(old) - set(eligible)),
            },
            "families_all": {
                f: {
                    "frozen": collision(
                        rows,
                        runtime,
                        [
                            i
                            for i in ix
                            if rows[i]["intent"] == "ATTACK_INTENT" and rows[i]["family"] == f
                        ],
                    ),
                    "candidate": collision(
                        rows,
                        joint,
                        [
                            i
                            for i in ix
                            if rows[i]["intent"] == "ATTACK_INTENT" and rows[i]["family"] == f
                        ],
                    ),
                }
                for f in FAMILIES
            },
        }
        np.savez(
            output / (role.lower() + ".npz"),
            x=joint[ix],
            frozen_runtime=runtime[ix],
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
            paired_common_eligible=np.array([i in common for i in ix]),
        )
    derivative = []
    aliases = surrogate_groups(rows)
    for i, r in enumerate(rows):
        derivative.append(
            {
                **{
                    k: r[k]
                    for k in [
                        "sample_id",
                        "request_id",
                        "environment",
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
                },
                **aliases[i],
                "dataset_version": VERSION,
                "source": r["request_provenance"]["source"],
                "original_role": r["split"],
                "parent_dataset_fingerprint": PARENT_FP,
                "parent_record_index": i,
                "parent_exclusion_reasons": r["inclusion_exclusion_reasons"],
                "frozen_request_feature_reference": {
                    "file": r["split"].lower() + ".npz",
                    "parent_key": "runtime",
                    "parent_row": runtime_by_id[r["sample_id"]][2],
                    "derivative_key": "frozen_runtime",
                    "derivative_row": sum(rows[j]["split"] == r["split"] for j in range(i)),
                },
                "body_syntax_vector": vectors[i],
                "feature_schema_version": candidate.VERSION,
                "feature_contract_fingerprint": candidate.fingerprint(),
                "body_contract_sha256": body.CONTRACT_SHA256,
                "state": body.state_of(vectors[i]),
                "truncated": bool(vectors[i][body.STATES.index("TRUNCATED")]),
                "availability": provenance[i],
                "inclusion_exclusion_reasons": sorted(reasons[i]),
                "eligible_for_research": not reasons[i],
                "eligible_for_fit": r["split"] == "TRAIN" and not reasons[i],
            }
        )
    core_fp = digest(
        {
            "records": derivative,
            "plan_fingerprint": plan["fingerprint"],
            "parent_fingerprint": PARENT_FP,
        }
    )
    for r in derivative:
        r["dataset_fingerprint"] = core_fp
    (output / "records.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in derivative)
    )
    workflow_roles = defaultdict(set)
    for r in rows:
        workflow_roles[re.sub(r"(?:TRAIN|CALIBRATION|DEVELOPMENT):", "", r["workflow_group"])].add(
            r["split"]
        )
    baseline_near = near_pairs(rows, runtime, joint[:, 588:], use_body=False)
    gates = {
        "DATASET_INTEGRITY": "PASS",
        "LABEL_PROVENANCE": "PASS_FOR_RESEARCH",
        "STRICT_SPLIT_INTEGRITY": split["status"],
        "TRAIN_COVERAGE": coverage_pass(
            reports["TRAIN"]["candidate_strict"], "TRAIN", plan["coverage_minimums"]["TRAIN"]
        ),
        "CALIBRATION_COVERAGE": coverage_pass(
            reports["CALIBRATION"]["candidate_strict"],
            "CALIBRATION",
            plan["coverage_minimums"]["CALIBRATION"],
        ),
        "FEATURE_CONTRACT": "LOCKED",
        "PRIVACY_GATE": "PENDING_DERIVATIVE_CANARY_SCAN",
        "EVALUATION_PROTOCOL": "PENDING_PROTOCOL_BINDING",
        "CHECKPOINT_RECOVERY_PLAN": "PENDING_DESIGN_BINDING",
        "FROZEN_BASELINE": "PENDING_FINAL_HASH_CHECK",
    }
    report = {
        "dataset_version": VERSION,
        "dataset_fingerprint": core_fp,
        "fingerprint_recipe": "digest(records before adding per-record dataset_fingerprint, plan_fingerprint, parent_fingerprint); file SHA bindings separate to avoid circularity",
        "parent_fingerprint": PARENT_FP,
        "plan_fingerprint": plan["fingerprint"],
        "contract_fingerprint": candidate.fingerprint(),
        "rows": len(rows),
        "roles_preserved": True,
        "intent_counts": dict(Counter(r["intent"] for r in rows)),
        "Oracle_verified": sum(r["oracle_verified"] for r in rows),
        "review_pending": sum(r["review_status"] == "PENDING" for r in rows),
        "independent_human_verified": 0,
        "all_collisions": {"frozen": collision(rows, runtime), "candidate": collision(rows, joint)},
        "role_reports": reports,
        "body_states": dict(Counter(body.state_of(v) for v in vectors)),
        "parity_with_prior_224": 224,
        "excluded_reasons": dict(Counter(reason for group in reasons for reason in group)),
        "cross_role_groups_before_quarantine": dict(overlap),
        "near_pairs": {
            "frozen_all": len(baseline_near),
            "candidate_all": len(near),
            "frozen_cross_role": sum(
                rows[a]["split"] != rows[b]["split"] for a, b in baseline_near
            ),
            "candidate_cross_role": sum(rows[a]["split"] != rows[b]["split"] for a, b in near),
        },
        "split_audit": split,
        "shared_workflow_categories_across_roles": sum(len(v) > 1 for v in workflow_roles.values()),
        "environment_overlap": "TRAIN/CAL share DVWA/Juice; DEVELOPMENT DVWA only, all exposed. Category/environment reuse is reported, not independent-domain evidence",
        "sealed_candidate_overlap": "UNVERIFIED_NOT_OPENED_NOT_USED",
        "gates": gates,
        "training_started": False,
        "scores_computed": 0,
        "new_requests": 0,
        "checkpoints_created": 0,
        "files_sha256": {p.name: file_sha256(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    atomic_json(output / "materialization-report.json", report)
    print(
        json.dumps(
            {
                "dataset_fingerprint": core_fp,
                "all_collisions": report["all_collisions"],
                "roles": {
                    role: {
                        "strict_records": reports[role]["candidate_strict"]["records"],
                        "unique_views": reports[role]["candidate_strict"]["unique_views"],
                        "family_views": reports[role]["candidate_strict"]["family_views"],
                        "unique_benign_views": reports[role]["candidate_strict"][
                            "unique_benign_views"
                        ],
                        "eligibility_changes": reports[role]["eligibility_changes"],
                    }
                    for role in ROLES
                },
                "coverage": {k: v for k, v in gates.items() if "COVERAGE" in k},
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--lock-plan", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.lock_plan:
        lock(args.plan.resolve())
    else:
        if args.output is None:
            parser.error("--output required")
        with threadpool_limits(limits=1):
            materialize(args.plan.resolve(), args.output.resolve())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print exception messages or traceback locals from raw evidence processing.
        print(
            json.dumps(
                {"status": "FAILED", "error_type": type(exc).__name__, "details": "SUPPRESSED"}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
