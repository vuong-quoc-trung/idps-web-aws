"""Resolve native witnesses and task-scoped research admission; no TEST or fit."""

# isort: skip_file
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import capture
import numpy as np
import onnxruntime as ort
from sklearn.metrics import average_precision_score
from context22 import encode
from lineage import close
from plan import FAMILIES, TASK
from idps_ai.common import atomic_json, digest, file_sha256
from lab_auth import uri100

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def check(value, reason):
    if not value:
        raise ValueError(reason)


def database_state(cfg, row, after):
    """Resolve captured state digests against the pinned, quiescent lab seed.

    Equality is required with the digest OBSERVED by JDBC, not manufactured
    replacement evidence. This also independently checks the owner relation.
    """
    number = 1 if row["account"] == "admin" else 2
    result = {"actor_role": cfg["actors"][number - 1], "actor_number": number}
    if cfg["family"] == "user-read":
        result.update(
            resource=2, username=cfg["usernames"]["student"], role=cfg["actors"][1], enabled="TRUE"
        )
    elif cfg["family"] == "self-profile":
        result.update(resource=100 + number, owner=number, marker="Lab Record " + str(100 + number))
    else:
        count = 1 if after or number == 2 else 0
        result.update(count=count, resource=1000 if count else None)
    return result


def metrics(labels, scores, threshold):
    y = np.asarray([label == "ATTACK_VERIFIED" for label in labels])
    scores = np.asarray(scores)
    p = scores > threshold
    tn, fp, fn, tp = [int(v.sum()) for v in (~y & ~p, ~y & p, y & ~p, y & p)]
    ece = 0
    for i in range(10):
        mask = (scores >= i / 10) & (scores < (i + 1) / 10 if i < 9 else scores <= 1)
        if mask.any():
            ece += float(mask.mean() * abs(scores[mask].mean() - y[mask].mean()))
    return {
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "TP": tp,
        "recall": tp / (tp + fn) if tp + fn else None,
        "FPR": fp / (fp + tn) if fp + tn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "AP": float(average_precision_score(y, scores)) if y.any() else None,
        "Brier": float(np.mean((scores - y) ** 2)),
        "ECE_10_bin": ece,
        "count": len(y),
        "scope": "DESCRIPTIVE_TINY_ENRICHED_RESEARCH_PANEL_NO_PROBABILITY_OR_FINAL_QUALITY_CLAIM",
    }


def score(model, values):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model), sess_options=options, providers=["CPUExecutionProvider"]
    )
    return session.run(["score"], {session.get_inputs()[0].name: np.asarray(values, np.float32)})[
        0
    ].reshape(-1)


def run(out):
    prereg = json.loads((out / "preregistration.json").read_text())
    graph = []
    targets = []
    all_keys = set()
    summaries = {}
    observations = Counter()
    model = capture.base.unified.ResearchModel(capture.base.unified.MODELS)
    for family, cfg0 in FAMILIES.items():
        directory = out / family
        plan = json.loads((directory / "plan.json").read_text())
        cfg = plan["configuration"]
        check(
            plan["rows"] == prereg["rows"][family]
            and plan["role"] == prereg["families"][family]["role"],
            "Acquisition changed preregistered role/roster",
        )
        capture.base.roster = lambda _: plan["rows"]
        attempt = directory / "campaign-1-a1/adapter"
        verified = capture.base.verify(attempt, 0, model)
        verified.pop("labels", None)
        for entry in verified["requests"]:
            entry.pop("label", None)
        check(
            verified["state"] == "PASS",
            "KVM/URI76/correlation/cleanup acceptance failed: " + family,
        )
        rows = [
            r
            for line in (attempt / "guest/receipt-ledger.jsonl").read_text().splitlines()
            if (r := json.loads(line))["kind"] == "ATTEMPT"
        ]
        bykey = {r["request_key"]: r for r in rows}
        check(len(bykey) == len(rows), "Duplicate receipt request key")
        family_targets = []
        for receipt in rows:
            observations.update(e["source"] for e in receipt["events"])
            planned = plan["rows"][receipt["attempt"] - 1]
            key = receipt["request_key"]
            check(key not in all_keys, "Cross-campaign duplicate physical request")
            all_keys.add(key)
            check(
                receipt["identity_verified"]
                and receipt["clock_valid"]
                and receipt["oracle_verified"]
                and not receipt["conflicts"]
                and not receipt["duplicate_request"]
                and not receipt["invalid_source_rows"],
                "Native request integrity",
            )
            u = receipt["uri100"]
            v = np.asarray(u["vector"], np.float32)
            check(
                v.tobytes() == uri100(planned["target"], planned["method"]).tobytes()
                and u["vector_sha256"] == hashlib.sha256(v.tobytes()).hexdigest(),
                "URI100 reference mismatch",
            )
            base = {
                k: value
                for k, value in receipt.items()
                if k not in ("kind", "attempt", "uri76", "uri100")
            }
            check(u["base_receipt_sha256"] == digest(base), "URI100 receipt binding")
            account = planned["account"]
            actor_alias = cfg["usernames"][account]
            node = {
                "key": key,
                "campaign": directory.name,
                "session": directory.name + ":" + planned["session"],
                "actor_alias": None,
                "actor_resolution": "NOT_ASSERTED_FOR_SETUP; OWNED_SESSION_CUSTODY_ONLY",
                "actor_scope_resolved": True,
                "identity_verified": True,
                "material_template": family,
                "role": cfg["role"],
                "population": planned["population"],
                "task": planned["label_task"],
                "ABI": "idps-uri100-context22-r27-v1",
                "profile": "LOCAL_KVM_CURRENT_AUDIT_AND_URI_MIRROR",
                "primary_view_sha256": None,
                "eligible": False,
            }
            graph.append(node)
            if planned["population"] != "TARGET":
                continue
            p = receipt.get("authorization_oracle")
            c = receipt["trusted_context"]
            check(
                p
                and p["sha256"] == digest({k: value for k, value in p.items() if k != "sha256"})
                and p["request_key"] == key
                and p["scope"] == "GROUND_TRUTH_ONLY"
                and p["label_task"] == TASK,
                "Task/Oracle digest binding",
            )
            parent = bykey[p["principal_request_key"]]
            check(
                parent["oracle_verified"]
                and parent["oracle_basis"] == "PRINCIPAL_AND_JDBC_ROLE"
                and any(
                    e["source"] == "A" and e["proof_sha256"] == p["principal_audit_proof_sha256"]
                    for e in parent["events"]
                )
                and any(
                    e["source"] == "A" and e["proof_sha256"] == p["target_audit_proof_sha256"]
                    for e in receipt["events"]
                )
                and p["actor_session_matches_principal"],
                "Actor/session principal closure",
            )
            for stage in ("before", "after"):
                check(
                    digest(database_state(cfg, planned, stage == "after"))
                    == p["database_" + stage + "_sha256"],
                    "JDBC observed state does not resolve against pinned seed: " + family + stage,
                )
            check(
                p["actor_role"]
                == c["observation"]["role"]
                == cfg["actors"][0 if account == "admin" else 1]
                and p["application_basis"] == receipt["oracle_basis"],
                "Context/Oracle provenance mismatch",
            )
            check(
                c["encoded"] == encode(c["observation"], c["binding"])
                and c["binding"]["request_key"] == key
                and c["binding"]["source_mask"] == receipt["native_mask"],
                "Context reconstruction",
            )
            audit = next(e for e in receipt["events"] if e["source"] == "A")
            check(
                c["observation"]["proof_sha256"]
                == p["target_audit_proof_sha256"]
                == audit["proof_sha256"]
                and c["observation"]["event_id"] == audit["native_event_id"]
                and audit["receipt_offset_ns"]
                <= audit["available_offset_ns"]
                <= c["observation"]["available_offset_ns"],
                "Context does not follow its actual current-request Audit proof",
            )
            eligible = (
                u["available_at_cutoff"]
                and c["encoded"]["status"] == "CONTEXT_AVAILABLE"
                and c["availability_timestamp_scope"] == "AFTER_ACTUAL_22_FIELD_ENCODING"
                and c["encoding_completed_offset_ns"]
                == c["observation"]["available_offset_ns"]
                <= 999000000
            )
            combined = np.r_[v, np.asarray(c["encoded"]["vector"], np.float32)].astype("<f4")
            feature_sha = hashlib.sha256(combined.tobytes()).hexdigest()
            node.update(
                primary_view_sha256=feature_sha,
                eligible=bool(eligible),
                label=p["label"],
                actor_alias=actor_alias,
                actor_resolution="PRINCIPAL_AUDIT_JDBC_AND_PINNED_ACCOUNT_NAMESPACE",
            )
            record = {
                "request_key": key,
                "campaign": family,
                "role": cfg["role"],
                "task": TASK,
                "method": planned["method"],
                "path": planned["path"],
                "label": p["label"],
                "feature_sha256": feature_sha,
                "feature_ABI": "idps-uri100-context22-r27-v1",
                "eligible": bool(eligible),
                "native_mask": receipt["native_mask"],
                "context": c,
                "uri100": u,
                "uri76": receipt["uri76"],
                "oracle": p,
                "basis": "MACHINE_VERIFIED_POLICY_PRINCIPAL_OWNER_OR_COMMITTED_MUTATION",
                "independent_human_review": False,
                "relation": p["resource_relation"],
            }
            family_targets.append(record)
            targets.append(record)
        summaries[family] = {
            "capture": verified,
            "target_requests": len(family_targets),
            "eligible_targets": sum(r["eligible"] for r in family_targets),
            "role": cfg["role"],
            "labels": dict(Counter(r["label"] for r in family_targets)),
            "targets": [
                {
                    "request_key": r["request_key"],
                    "method": r["method"],
                    "label": r["label"],
                    "mask": r["native_mask"],
                    "context_ready_ms": r["context"]["encoding_completed_offset_ns"] / 1e6,
                }
                for r in family_targets
            ],
        }
    components = close(graph)
    check(len(components) == 3, "Material-family closure differs from preregistration")
    for component in components:
        check(not component["blocked"], "Lineage gate failed: " + str(component["reasons"]))
    # Exhaustive six-target comparison, not an approximate/saturated near index.
    # Distinct policy/source branches, method/action and resource resolution
    # differ across families. Shared infrastructure is not a final sampling proof.
    near = []
    for i, a in enumerate(targets):
        for b in targets[i + 1 :]:
            near.append(
                {
                    "left": a["request_key"],
                    "right": b["request_key"],
                    "same_method_path": (a["method"], a["path"]) == (b["method"], b["path"]),
                    "same_material_policy_family": a["campaign"] == b["campaign"],
                    "same_primary_view": a["feature_sha256"] == b["feature_sha256"],
                    "classification": "SAME_COMPONENT"
                    if a["campaign"] == b["campaign"]
                    else "DISTINCT_POLICY_AND_RESOURCE_RESOLUTION_NOT_A_VERIFIED_NEAR_ALIAS",
                }
            )
    canonical = {}
    admitted = Counter()
    labels_by_role = defaultdict(Counter)
    for target in targets:
        if target["eligible"]:
            canonical_key = digest(
                [TASK, target["feature_ABI"], target["feature_sha256"], target["label"]]
            )
            if canonical_key not in canonical:
                canonical[canonical_key] = target
                admitted[target["role"]] += 1
                labels_by_role[target["role"]][target["label"]] += 1
            target["canonical_key"] = canonical_key
            target["admission"] = "ELIGIBLE_FOR_DECLARED_TASK_RESEARCH"
        else:
            target["admission"] = "QUARANTINED_MISSING_CAUSAL_FEATURE"
    payload = "".join(
        json.dumps({"observation": r["context"]["observation"], "binding": r["context"]["binding"]})
        + "\n"
        for r in targets
    )
    rust = subprocess.run(
        [str(REPO / "security-web/target/debug/idps-r27-context")],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    check(
        list(map(json.loads, rust.stdout.splitlines()))
        == [r["context"]["encoded"] for r in targets],
        "Native Rust/Python context22 parity",
    )
    models = {}
    labels = [r["label"] for r in targets]
    frozen = [
        (
            "B16_URI100",
            REPO / "ai-training/.artifacts/t09-r261-recovery-drliluc_/research-bundle/model.onnx",
            100,
            0.9420260190963745,
            "fdff05ee91f181268121ee7c72e573a4b2d771c3a8ee60cfa28e9d11860f2271",
        ),
        (
            "R20_URI76",
            Path.home() / ".local/state/idps-r22-local/bundle/swiglu.onnx",
            76,
            0.9633333086967468,
            "1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525",
        ),
    ]
    for name, path, width, threshold, sha in frozen:
        check(file_sha256(path) == sha, "Frozen model changed")
        values = [r["uri100" if width == 100 else "uri76"]["vector"] for r in targets]
        scores = score(path, values)
        models[name] = {
            "threshold": threshold,
            "model_sha256": sha,
            "scores": scores.tolist(),
            "request_weighted": metrics(labels, scores, threshold),
            "per_method": {
                m: metrics(
                    [r["label"] for r in targets if r["method"] == m],
                    scores[[r["method"] == m for r in targets]],
                    threshold,
                )
                for m in ("GET", "POST")
            },
        }
    deterministic = [r["context"]["encoded"]["policy_control"] == "DENY" for r in targets]
    policy = metrics(labels, np.asarray(deterministic, float), 0.5)
    policy.update(
        is_ML=False, probability_calibration_claim=False, AP=None, Brier=None, ECE_10_bin=None
    )
    models["deterministic_policy_control"] = policy
    models["context_aware_ML"] = {
        "state": "NOT_TRAINED",
        "reason": "No added value established over exact deterministic authorization; too few independent data for generalization.",
    }
    models["RI_v2_Hybrid"] = {
        "state": "NOT_SCORED",
        "reason": "No common-request RI-v2 full selected-header tensor or frozen rule-score envelope; do not fabricate inputs or alter enforcement.",
    }
    prior = {}
    for name in ("t09-r261-recovery-drliluc_", "t09-r262-context-yaqvp710"):
        root = REPO / "ai-training/.artifacts" / name
        index = json.loads((root / "artifact-index.json").read_text())
        changed = [
            path for path, sha in index["artifacts"].items() if file_sha256(root / path) != sha
        ]
        check(not changed, "Historical artifact changed")
        prior[name] = {"artifacts": len(index["artifacts"]), "changed": changed}
    summary = {
        "decision": "NATIVE_RESEARCH_ADMISSION_IMPROVED_FINAL_QUALITY_BLOCKED",
        "families": summaries,
        "HTTP": len(graph),
        "target_requests": len(targets),
        "source_observations": dict(observations),
        "Oracle_verified": sum(s["capture"]["oracle_verified"] for s in summaries.values()),
        "labels": dict(Counter(r["label"] for r in targets)),
        "structurally_disjoint_material_components": len(components),
        "independent_final_exposure_anchors": 0,
        "canonical_research_by_role": dict(admitted),
        "canonical_labels_by_role": {role: dict(counts) for role, counts in labels_by_role.items()},
        "native_research_TRAIN_DEV_CAL_FIT_CAL_OP_TEST": [
            admitted["TRAIN"],
            admitted["DEV"],
            0,
            0,
            0,
        ],
        "canonical_research_samples": len(canonical),
        "unique_primary_vectors": len({r["feature_sha256"] for r in targets}),
        "unique_URI100_vectors": len({r["uri100"]["vector_sha256"] for r in targets}),
        "exact_feature_overlap_across_roles": False,
        "protected_native_CAL_TEST": "None admitted in R262 handoff; old task/roles untouched; publisher protected payloads not read",
        "near_pairs_exhaustively_checked": len(near),
        "near_index_saturated": False,
        "statistical_independence": "Not claimed from structural disjointness; shared lab/environment and scripted label population remain. Final T07 support and confidence BLOCKED.",
        "model_comparison": models,
        "model_selection": "Keep RI v2 default/R20 shadow/B16 publisher research. Deterministic policy for the tested authorization task.",
        "request_level_reference_bounds_if_independent": {
            "recall_3_of_3_lower95": 0.05 ** (1 / 3),
            "FPR_0_of_3_upper95": 1 - 0.05 ** (1 / 3),
            "applicable_to_T07": False,
        },
        "historical_preservation": prior,
        "new_training": False,
        "release_ready": False,
        "publisher_quality_blockers_unchanged": {
            "Notes_CAL_OP_recall": 0.28125,
            "PKDD_benign_FPR": 0.10689655,
        },
        "remaining": [
            "No representative independent native CAL/TEST or T07 support/confidence",
            "No measured authorization ML gain over deterministic policy",
            "No new payload-anomaly training information addressing publisher threshold shift",
            "Context22 not deployed to persistent Local or AWS",
        ],
    }
    atomic_json(out / "admission.json", summary)
    atomic_json(
        out / "lineage-graph.json",
        {
            "nodes": graph,
            "components": components,
            "verified_near_census": near,
            "control_task_scope": prereg["lineage"],
            "statistical_independence_proven": False,
        },
    )
    atomic_json(
        out / "canonical-research-ledger.json",
        {
            "profile": "idps-r27-native-task-admission-v1",
            "rows": targets,
            "canonical_keys": sorted(canonical),
            "permission": "Internal research only, never final native performance or model promotion",
        },
    )
    atomic_json(
        out / "native-source-role-registry.json",
        {
            "version": "idps-r27-native-source-role-registry-v1",
            "task": TASK,
            "profile_sha256": file_sha256(HERE / "admission-profile.json"),
            "preregistration_sha256": file_sha256(out / "preregistration.json"),
            "role_assignment": "LOCKED_BEFORE_CAPTURE_INTERNAL_RESEARCH",
            "canonical": {
                key: {
                    "role": r["role"],
                    "feature_sha256": r["feature_sha256"],
                    "campaign": r["campaign"],
                    "request_key": r["request_key"],
                }
                for key, r in canonical.items()
            },
            "DEV_protected_from_future_TRAIN": True,
            "CAL_TEST_not_acquired": True,
            "requires_future_native_intake_to_load_this_registry": True,
            "publisher_source_roles_unchanged": True,
            "release_permission": False,
        },
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "decision",
                    "HTTP",
                    "target_requests",
                    "canonical_research_by_role",
                    "labels",
                )
            }
        )
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(Path(sys.argv[1]))
