"""Offline same-request information proof and conservative native admission census."""

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
from context import encode
from idps_ai.common import atomic_json, digest, file_sha256
from lab_auth import uri100

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PREVIOUS = REPO / "ai-training/.artifacts/t09-r261-recovery-drliluc_"


def require(value, message):
    if not value:
        raise ValueError(message)


def ambiguity(rows, key):
    groups = defaultdict(Counter)
    for r in rows:
        groups[key(r)][r["label"]] += 1
    positives = sum(r["label"] == "ATTACK_VERIFIED" for r in rows)
    return {
        "groups": len(groups),
        "mixed_groups": sum(len(v) > 1 for v in groups.values()),
        "unavoidable_errors_if_one_decision_per_group": sum(
            min(v.values()) for v in groups.values() if len(v) > 1
        ),
        "empirical_recall_ceiling_at_zero_FP": sum(
            v.get("ATTACK_VERIFIED", 0) for v in groups.values() if not v.get("BENIGN_VERIFIED")
        )
        / positives
        if positives
        else None,
        "scope": "RETROSPECTIVE_INFORMATION_CENSUS_NOT_FITTED_MODEL_OR_GENERALIZATION",
    }


def campaign(directory, strict):
    plan = json.loads((directory / "plan.json").read_text())
    capture.base.roster = lambda _: plan["rows"]
    adapter = directory / "campaign-1-a1/adapter"
    ledger = adapter / "guest/receipt-ledger.jsonl"
    if not ledger.exists():
        return {
            "state": "BLOCKED_NO_WORKER_OR_HTTP",
            "physical_requests": 0,
            "oracle": 0,
            "adapter": json.loads((adapter / "result.json").read_text()),
            "strict": False,
        }, []
    entries = list(map(json.loads, ledger.read_text().splitlines()))
    rows = [r for r in entries if r["kind"] == "ATTEMPT"]
    baseline = capture.base.unified.ResearchModel(capture.base.unified.MODELS)
    verified = capture.base.verify(adapter, 0, baseline)
    verified.pop("labels", None)
    for r in verified["requests"]:
        r.pop("label", None)
    bykey = {r["request_key"]: r for r in rows}
    require(len(bykey) == len(rows), "Duplicate physical request key")
    examples = []
    labels = Counter()
    completions = []
    for row in rows:
        planned = plan["rows"][row["attempt"] - 1]
        projected = row["uri100"]
        actual = np.asarray(projected["vector"], np.float32)
        require(
            actual.tobytes() == uri100(planned["target"], planned["method"]).tobytes(),
            "Raw URI100 parity",
        )
        require(
            projected["vector_sha256"] == hashlib.sha256(actual.tobytes()).hexdigest(),
            "URI100 digest",
        )
        reference_receipt = {
            k: v for k, v in row.items() if k not in ("kind", "attempt", "uri76", "uri100")
        }
        require(
            projected["base_receipt_sha256"] == digest(reference_receipt),
            "URI100 original receipt binding",
        )
        context = row["trusted_context"]
        o, b = context["observation"], context["binding"]
        require(context["encoded"] == encode(o, b), "Offline context reconstruction")
        require(
            b["request_key"] == row["request_key"] and b["source_mask"] == row["native_mask"],
            "Context request/mask mismatch",
        )
        if context["encoded"]["status"] == "CONTEXT_AVAILABLE":
            facts = [
                f
                for f in row["events"]
                if f["source"] == "A" and f["proof_sha256"] == o["proof_sha256"]
            ]
            require(
                len(facts) == 1 and facts[0]["native_event_id"] == o["event_id"],
                "Audit proof mismatch",
            )
            require(
                facts[0]["receipt_offset_ns"]
                <= facts[0]["available_offset_ns"]
                <= o["available_offset_ns"]
                <= 999_000_000,
                "Audit/context causal ordering",
            )
            if strict:
                require(
                    context["availability_timestamp_scope"] == "AFTER_ACTUAL_20_FIELD_ENCODING"
                    and context["encoding_completed_offset_ns"] == o["available_offset_ns"]
                    and projected["available_at_cutoff"],
                    "Missing true encoder completion evidence",
                )
                completions.append(o["available_offset_ns"])
        proof = row.get("authorization_oracle")
        label = None
        if proof:
            principal = bykey.get(proof["principal_request_key"], {})
            require(
                proof["sha256"] == digest({k: v for k, v in proof.items() if k != "sha256"}),
                "Oracle digest",
            )
            require(
                proof["scope"] == "GROUND_TRUTH_ONLY"
                and proof["request_key"] == row["request_key"]
                and row["oracle_verified"]
                and proof["actor_session_matches_principal"]
                and proof["owner_stable_before_after"]
                and proof["resource_owner_differs_from_actor"]
                and principal.get("oracle_basis") == "PRINCIPAL_AND_JDBC_ROLE"
                and any(
                    f["source"] == "A"
                    and f["proof_sha256"] == proof["principal_audit_proof_sha256"]
                    for f in principal.get("events", [])
                )
                and any(
                    f["source"] == "A" and f["proof_sha256"] == proof["target_audit_proof_sha256"]
                    for f in row["events"]
                ),
                "Semantic witness did not close",
            )
            require(
                o and proof["actor_role"] == o["role"],
                "Observed context did not match independent semantic evidence",
            )
            label = proof["label"]
            labels[label] += 1
        elif planned["oracle"].startswith("principal-") and row["oracle_verified"]:
            require(row["oracle_basis"] == "PRINCIPAL_AND_JDBC_ROLE", "Principal Oracle unresolved")
            label = (
                "BENIGN_VERIFIED"  # independent session/principal/JDBC control, not runner intent
            )
        if strict and label and context["encoded"]["status"] == "CONTEXT_AVAILABLE":
            examples.append(
                {
                    "campaign": directory.name,
                    "request_key": row["request_key"],
                    "attempt": row["attempt"],
                    "method": planned["method"],
                    "template": "STUDENT_DIRECTORY_RECORD" if proof else "SELF_PRINCIPAL",
                    "target": planned["target"],
                    "label": label,
                    "role": o["role"],
                    "context": context,
                    "uri100": projected,
                    "uri76": row["uri76"],
                    "is_record_witness": bool(proof),
                    "label_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
                    "role_assignment": "RESEARCH_EXPOSED_PENDING_LINEAGE_AND_ADMISSION",
                }
            )
    if strict:
        require(verified["state"] == "PASS", "Final live capture did not pass")
    available = sum(r["trusted_context"]["encoded"]["status"] == "CONTEXT_AVAILABLE" for r in rows)
    return {
        "state": verified["state"],
        "physical_requests": len(rows),
        "oracle": sum(r["oracle_verified"] for r in rows),
        "semantic_record_labels": dict(labels),
        "strict_context_timing": strict,
        "context_available": available,
        "strict_context_available": available if strict else 0,
        "encoding_completion_ms": [x / 1e6 for x in completions],
        "context_states": dict(Counter(r["trusted_context"]["encoded"]["state"] for r in rows)),
        "native_masks": verified["masks"],
        "URI100_at_cutoff": verified["proof"],
        "URI76_Rust_parity": verified["rust_parity"],
        "ledger_sha256": file_sha256(ledger),
        "capture_verification": verified,
    }, examples


def confusion(labels, predictions):
    y = np.asarray([label == "ATTACK_VERIFIED" for label in labels])
    p = np.asarray(predictions, bool)
    tn, fp, fn, tp = [int(x.sum()) for x in (~y & ~p, ~y & p, y & ~p, y & p)]
    return {
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "TP": tp,
        "recall": tp / (tp + fn) if tp + fn else None,
        "FPR": fp / (fp + tn) if fp + tn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
    }


def model_scores(model, x):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model), sess_options=options, providers=["CPUExecutionProvider"]
    )
    return session.run(["score"], {session.get_inputs()[0].name: np.asarray(x, np.float32)})[
        0
    ].reshape(-1)


def run(out):
    summaries = {}
    examples = []
    for name in ("capture-a", "capture-b", "capture-b2", "capture-b3", "capture-c"):
        summaries[name], new = campaign(out / name, name in ("capture-b3", "capture-c"))
        examples.extend(new)
    all_receipts = [
        row
        for path in out.glob("capture-*/campaign-1-a1/adapter/guest/receipt-ledger.jsonl")
        for row in map(json.loads, path.read_text().splitlines())
        if row["kind"] == "ATTEMPT"
    ]
    require(
        len({r["request_key"] for r in all_receipts}) == len(all_receipts),
        "Cross-campaign physical identity collision",
    )
    all_planned = [
        row
        for path in out.glob("capture-*/plan.json")
        for row in json.loads(path.read_text())["rows"]
    ]
    final = [r for r in examples if r["campaign"] == "capture-c"]
    require(len(final) == 8, "Final same-request contrast panel incomplete")
    records = [r for r in final if r["is_record_witness"]]
    require(
        Counter(r["label"] for r in records) == {"BENIGN_VERIFIED": 3, "ATTACK_VERIFIED": 3},
        "Two-class semantic contrast",
    )
    pairs = []
    for target in sorted({r["target"] for r in records}):
        pair = [r for r in records if r["target"] == target]
        require(
            len(pair) == 2
            and pair[0]["uri100"]["vector_sha256"] == pair[1]["uri100"]["vector_sha256"]
            and pair[0]["context"]["encoded"]["vector"] != pair[1]["context"]["encoded"]["vector"],
            "Information contrast failed",
        )
        pairs.append(
            {
                "target": target,
                "request_keys": [r["request_key"] for r in pair],
                "same_URI100": True,
                "different_context20": True,
                "both_causal": True,
            }
        )
    binary = REPO / "security-web/target/debug/idps-r262-context"
    text = "".join(
        json.dumps({"observation": r["context"]["observation"], "binding": r["context"]["binding"]})
        + "\n"
        for r in examples
    )
    result = subprocess.run(
        [str(binary)], input=text, text=True, capture_output=True, check=True, timeout=10
    )
    require(
        list(map(json.loads, result.stdout.splitlines()))
        == [r["context"]["encoded"] for r in examples],
        "Rust real-context parity failed",
    )
    frames = out / "native-context-frames.jsonl"
    frames.write_text(text)
    controls = {
        name: ambiguity(final, key)
        for name, key in {
            "URI100_only": lambda r: r["uri100"]["vector_sha256"],
            "context20_only": lambda r: tuple(r["context"]["encoded"]["vector"]),
            "role_only": lambda r: r["role"],
            "resource_category_only": lambda r: r["context"]["binding"]["category"],
            "availability_only": lambda r: tuple(r["context"]["encoded"]["vector"][11:]),
            "full_URI100_context20": lambda r: (
                r["uri100"]["vector_sha256"],
                tuple(r["context"]["encoded"]["vector"]),
            ),
        }.items()
    }
    labels = [r["label"] for r in final]
    deterministic = confusion(
        labels, [r["context"]["encoded"]["policy_control"] == "DENY" for r in final]
    )
    model_b = PREVIOUS / "research-bundle/model.onnx"
    active = Path.home() / ".local/state/idps-r22-local/bundle"
    scope = json.loads((active / "model-scope.json").read_text())
    predictions = {}
    for name, model, x, threshold, expected_sha in [
        (
            "B16_URI100",
            model_b,
            [r["uri100"]["vector"] for r in final],
            0.9420260190963745,
            "fdff05ee91f181268121ee7c72e573a4b2d771c3a8ee60cfa28e9d11860f2271",
        ),
        (
            "R20_URI76",
            active / "swiglu.onnx",
            [r["uri76"]["vector"] for r in final],
            0.9633333086967468,
            scope["models"]["swiglu"],
        ),
    ]:
        require(file_sha256(model) == expected_sha, "Frozen model digest changed")
        scores = model_scores(model, x)
        predictions[name] = {
            "scope": "OFFLINE_SAME_REAL_REQUEST_FEATURES_NEW_AUTHORIZATION_TASK_NOT_PUBLISHER_TEST",
            "scores": scores.tolist(),
            "threshold": threshold,
            "model_sha256": expected_sha,
            "strict_gt_confusion": confusion(labels, scores > threshold),
            "live_serving_model_unchanged": True,
        }
    predictions["RI_v2"] = {
        "state": "NOT_SCORED",
        "reason": "No observed RI-v2 full selected_headers feature tensor at common cutoff; never synthesize compatible input",
    }
    predictions["deterministic_policy_control"] = {
        "confusion": deterministic,
        "is_ML": False,
        "probabilistic_AP_Brier_ECE": None,
        "reason": "Known application authorization, not independent ML success; advisory replay only",
    }
    old = json.loads((PREVIOUS / "native-evidence.json").read_text())
    index = json.loads((PREVIOUS / "artifact-index.json").read_text())
    changed = [
        name for name, sha in index["artifacts"].items() if file_sha256(PREVIOUS / name) != sha
    ]
    require(not changed, "Historical R261 artifacts modified")
    summary = {
        "decision": "CONTEXT_PROOF_PASS_DATA_INSUFFICIENT",
        "campaigns": summaries,
        "HTTP_dispatched": sum(c["physical_requests"] for c in summaries.values()),
        "unique_physical_request_keys": len({r["request_key"] for r in all_receipts}),
        "identity_verified_physical_requests": sum(r["identity_verified"] for r in all_receipts),
        "raw_source_observations": dict(
            Counter(e["source"] for r in all_receipts for e in r["events"])
        ),
        "observed_method_target_signatures": len({(r["method"], r["target"]) for r in all_planned}),
        "unique_URI100_across_all_receipts": len(
            {r["uri100"]["vector_sha256"] for r in all_receipts}
        ),
        "original_full_HTTP_content_identity": "NOT_CLAIMED_CREDENTIALS_AND_RAW_BODIES_NOT_PERSISTED",
        "Oracle_verified": sum(c["oracle"] for c in summaries.values()),
        "strict_native_context_views": len(examples),
        "strict_record_BENIGN_VERIFIED": 3,
        "strict_record_ATTACK_VERIFIED": 3,
        "all_new_record_witness_counts": dict(
            sum(
                (Counter(c.get("semantic_record_labels", {})) for c in summaries.values()),
                Counter(),
            )
        ),
        "strict_context_unique_vectors": len(
            {tuple(r["context"]["encoded"]["vector"]) for r in examples}
        ),
        "strict_URI100_context_unique_vectors": len(
            {
                (r["uri100"]["vector_sha256"], tuple(r["context"]["encoded"]["vector"]))
                for r in examples
            }
        ),
        "contrast_pairs": pairs,
        "negative_controls": controls,
        "same_request_baselines": predictions,
        "raw_Rust_context_parity": {
            "state": "PASS",
            "frames": len(examples),
            "max_error": 0,
            "frame_sha256": file_sha256(frames),
        },
        "old_101_campaign": old["campaign_101_reconciliation"],
        "old_pending_candidates": old["original_admission_candidates"],
        "R261_preserved_artifacts": len(index["artifacts"]),
        "R261_changed_artifacts": changed,
        "native_TRAIN_DEV_CAL_FIT_CAL_OP_TEST": [0, 0, 0, 0, 0],
        "canonical_TRAIN": 0,
        "independent_two_class_components": 1,
        "new_pristine_TEST": 0,
        "review_attestation_fabricated": False,
        "admission_status": "PENDING_LINEAGE_ROLE_REVIEW_NOT_CANONICAL",
        "admission_reasons": [
            "Same application/policy/route templates and shared state join all new native captures into one conservative lineage component",
            "No independent DEV/CAL/TEST; existing exposed capture cannot become pristine TEST",
            "Context ABI has not been admitted by native dataset contract/role custodian; human attestation not fabricated",
            "3+3 final record contrasts are not 100 attacks/20 independent clusters or CAL 200 benign/50 attacks/10 clusters per class",
            "No production performance windows, source-mask cohort coverage or adjusted benign-anchor bound",
        ],
        "training": {
            "performed": False,
            "reason": "Information proof passes; simple deterministic policy solves this role/resource case. No independent data to establish added ML value.",
        },
        "publisher_task": {
            "model": "B16_URI100",
            "unchanged": True,
            "Notes_CAL_OP_recall": 0.28125,
            "PKDD_benign_FPR": 0.10689655,
            "not_solved_by_authorization_context": True,
        },
        "release_ready": False,
    }
    atomic_json(out / "native-reconciliation.json", summary)
    atomic_json(
        out / "candidate-ledger.json",
        {
            "records": examples,
            "canonical_TRAIN": 0,
            "task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "all_records_exposed_research": True,
            "protected_roles_reassigned": False,
            "source_dropout_counted_as_original": False,
        },
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "decision",
                    "HTTP_dispatched",
                    "Oracle_verified",
                    "strict_native_context_views",
                    "canonical_TRAIN",
                )
            }
        )
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(Path(sys.argv[1]))
