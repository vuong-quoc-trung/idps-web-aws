#!/usr/bin/env python3
"""Assess frozen AI evidence without fitting, unsealing, relabeling or promotion."""

from __future__ import annotations

import argparse
import hashlib
import resource
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import yaml

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.export.onnx import cpu_session, infer_bundle
from idps_ai.features.request_preprocessing import bounded_spec
from idps_ai.training.resources import resource_envelope

ROLES = frozenset({"train", "calibration", "val"})


def _report(path):
    result = load_json(path)
    expected = result.get("report_sha256")
    if (
        not isinstance(expected, str)
        or digest({k: v for k, v in result.items() if k != "report_sha256"}) != expected
    ):
        raise PipelineError("Evidence report self-hash mismatch")
    return result


def _gate(status, evidence):
    return {"status": status, "evidence": evidence}


def _overall_status(gates, names):
    statuses = [gates[name]["status"] for name in names]
    if not statuses or any(status not in ("PASS", "FAIL", "INCONCLUSIVE") for status in statuses):
        raise PipelineError("Unknown quality gate status")
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "INCONCLUSIVE" for status in statuses):
        return "INCONCLUSIVE"
    return "PASS"


def _read_numeric_views(path, expected_sha, expected_rows):
    if file_sha256(path) != expected_sha:
        raise PipelineError("Numeric staging checksum mismatch")
    table = pq.read_table(path)
    if table.column_names != ["view_sha256", "label", "occurrence_rows", "features"]:
        raise PipelineError("Numeric staging schema mismatch")
    if table.num_rows != expected_rows or table.num_rows > 1_000_000:
        raise PipelineError("Numeric staging row count changed")
    keys = table.column("view_sha256").to_pylist()
    labels = table.column("label").to_pylist()
    if len(keys) != len(set(keys)) or any(label not in (0, 1) for label in labels):
        raise PipelineError("Staging contains duplicate keys or invalid labels")
    values = (
        table.column("features")
        .combine_chunks()
        .values.to_numpy(zero_copy_only=False)
        .reshape(len(keys), 76)
    )
    for key, vector in zip(keys, values):
        if not np.isfinite(vector).all() or hashlib.sha256(vector.tobytes()).hexdigest() != key:
            raise PipelineError("Staging vector is nonfinite or mismatches its key")
    return set(keys), labels


def _reference_keys(path, expected_sha):
    if file_sha256(path) != expected_sha:
        raise PipelineError("Exposed development checksum mismatch")
    parquet = pq.ParquetFile(path)
    if parquet.metadata.num_rows > 1_000_000:
        raise PipelineError("Exposed development exceeds bounded QA")
    keys = set()
    for batch in parquet.iter_batches(batch_size=8192, columns=["split", "x"]):
        splits = batch.column("split").to_pylist()
        if any(role not in ROLES for role in splits):
            raise PipelineError("QA refuses sealed or unknown reference partition")
        vectors = (
            batch.column("x").values.to_numpy(zero_copy_only=False).reshape(batch.num_rows, 76)
        )
        keys.update(hashlib.sha256(vector.tobytes()).hexdigest() for vector in vectors)
    return keys


def _model_artifact(bundle, expected_manifest_sha, research_report, research_sha, live, live_sha):
    bundle = Path(bundle)
    manifest_path = bundle / "model_manifest.json"
    if file_sha256(manifest_path) != expected_manifest_sha:
        raise PipelineError("Frozen GLU bundle manifest changed")
    manifest = load_json(manifest_path)
    if (
        manifest.get("model_kind") != "residual_glu"
        or manifest.get("input_shape") != [None, 207]
        or len(manifest.get("features", [])) != 207
        or manifest.get("feature_version") != "ai-features-5"
    ):
        raise PipelineError("Frozen GLU207 contract changed")
    for name, expected in manifest["files"].items():
        if file_sha256(bundle / name) != expected:
            raise PipelineError("Frozen GLU bundle member changed")
    if not manifest.get("parity", {}).get("all_rows_match"):
        raise PipelineError("Frozen GLU ONNX parity evidence is absent")
    if file_sha256(research_report) != research_sha:
        raise PipelineError("Research training report changed")
    research = load_json(research_report)
    if (
        research.get("parameters") != 9_675_784
        or research.get("features") != 207
        or research.get("updates") != 100
        or research.get("checkpoint_readback") != "PASS_PARAMETERS_AND_ADAM_STATE_EXACT"
        or research.get("validation_or_test_rows_decoded") != 0
    ):
        raise PipelineError("Research GLU technical evidence mismatch")
    checkpoint = Path(research["checkpoint"])
    checkpoint_manifest = checkpoint / "manifest.json"
    if file_sha256(checkpoint_manifest) != research["checkpoint_manifest_sha256"]:
        raise PipelineError("Research checkpoint manifest changed")
    for name, expected in load_json(checkpoint_manifest)["files"].items():
        if file_sha256(checkpoint / name) != expected:
            raise PipelineError("Research checkpoint member changed")
    if file_sha256(live) != live_sha:
        raise PipelineError("Live shadow evidence changed")
    shadow = load_json(live)
    if shadow.get("bundle_manifest_sha256") != expected_manifest_sha:
        raise PipelineError("Shadow run used a different GLU bundle")
    values = np.zeros((1, 207), dtype=np.float32)
    infer_bundle(bundle, values, max_threads=2)  # integrity and warmup, technical input only
    session = cpu_session(bundle / "model.onnx", max_threads=2)
    session.run(None, {"input": values})
    times = []
    for _ in range(8):
        start = time.perf_counter()
        outputs = session.run(None, {"input": values})
        times.append((time.perf_counter() - start) * 1000)
        if not all(np.isfinite(output).all() for output in outputs):
            raise PipelineError("Frozen GLU ONNX produced nonfinite output")
    return {
        "manifest_sha256": expected_manifest_sha,
        "historical_onnx_parity_rows": manifest["parity"].get("rows"),
        "research_updates_previous_run": research.get("updates"),
        "checkpoint_integrity": "PASS",
        "onnx_cpu_smoke_p95_ms": float(np.quantile(times, 0.95)),
        "onnx_cpu_smoke_scope": "one zero vector, excludes preprocessing and session construction; not HTTP inference latency",
        "lab_shadow": {
            "requests_sent": shadow.get("requests_sent"),
            "three_source": shadow.get("three_source"),
            "inferred": shadow.get("inferred"),
            "sensor_drops": shadow.get("sensor_drops"),
            "end_to_end_p95_ms": shadow.get("end_to_end_ms", {}).get("p95"),
            "scope": shadow.get("feature_parity_scope"),
        },
    }


def assess(
    policy,
    catalog,
    audit,
    overlap,
    staging,
    reference,
    oracle,
    bundle,
    bundle_sha,
    research_report,
    research_sha,
    live,
    live_sha,
    handoff,
    output,
):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise PipelineError("Quality report already exists")
    policy_path, catalog_path = Path(policy), Path(catalog)
    policy = yaml.safe_load(policy_path.read_text())
    catalog = yaml.safe_load(catalog_path.read_text())
    if policy.get("format_version") != 2:
        raise PipelineError("Unknown research quality policy")
    source = next(
        (
            row
            for row in catalog["autonomous_source_screening_20261103"]
            if row["name"] == "WAMM_DS_Augmented_v2"
        ),
        None,
    )
    if source is None:
        raise PipelineError("WAMM source registry entry missing")
    audit_data, overlap_data, oracle_data = _report(audit), _report(overlap), _report(oracle)
    if (
        file_sha256(audit) != source["audit_report_sha256"]
        or file_sha256(overlap) != source["overlap_report_sha256"]
        or audit_data["input_sha256"]["archive"] != source["archive_sha256"]
        or audit_data["input_sha256"]["sqlite"] != source["sqlite_sha256"]
        or overlap_data["candidate_sha256"] != audit_data["numeric_research_staging"]["sha256"]
        or overlap_data["research_policy_sha256"] != policy["supersedes_research_policy_sha256"]
        or audit_data["request_feature_spec_sha256"] != digest(bounded_spec())
    ):
        raise PipelineError("Registered source, policy or feature contract mismatch")
    if source["lineage_parent"].lower().replace(" ", "") not in audit_data[
        "lineage"
    ].lower().replace(" ", ""):
        raise PipelineError("Registered lineage disagrees with publisher audit")
    if source["independent_from_exposed_development"] and "derivative" in audit_data["lineage"]:
        raise PipelineError("Derivative source cannot be declared independent")
    keys, labels = _read_numeric_views(
        staging, overlap_data["filtered_file_sha256"], overlap_data["filtered_views"]
    )
    reference_keys = _reference_keys(reference, overlap_data["reference_sha256"])
    intersect = len(keys & reference_keys)
    counts = audit_data["counts"]
    if (
        counts["raw_records"] != sum(audit_data["publisher_label_counts"].values())
        or counts["parsed_request_representations"]
        != counts["publisher_benign_parsed"] + counts["publisher_attack_parsed"]
        or counts["parsed_request_representations"]
        + counts.get("invalid_request_line_rows", 0)
        + counts.get("unknown_publisher_label_rows", 0)
        + counts.get("missing_or_oversized_request_rows", 0)
        + counts.get("unprojectable_request_rows", 0)
        != counts["raw_records"]
        or len(keys) != sum(labels.count(value) for value in (0, 1))
        or labels.count(0) != overlap_data["filtered_publisher_benign_views"]
        or labels.count(1) != overlap_data["filtered_publisher_attack_views"]
    ):
        raise PipelineError("Dataset accounting does not reconcile")
    if oracle_data.get("physical_requests_verified") != oracle_data.get(
        "three_source_correlated_requests"
    ):
        raise PipelineError("Oracle request/correlation counts disagree")
    model = _model_artifact(bundle, bundle_sha, research_report, research_sha, live, live_sha)
    handoff_data = load_json(handoff)
    scale = yaml.safe_load((policy_path.parent / policy["formal_policy"]).read_text())
    formal_count = handoff_data["scale_admitted_requests"]
    invalid_fraction = (counts["raw_records"] - counts["parsed_request_representations"]) / counts[
        "raw_records"
    ]
    majority_fraction = max(labels.count(0), labels.count(1)) / len(labels)
    gates = {
        "publisher_http_parsing": _gate(
            "PASS"
            if invalid_fraction <= policy["data"]["maximum_invalid_http_fraction"]
            else "FAIL",
            {
                "invalid_or_unusable": counts["raw_records"]
                - counts["parsed_request_representations"],
                "fraction": invalid_fraction,
            },
        ),
        "raw_vector_label_consistency": _gate(
            "FAIL" if audit_data["exact_float32_request_view"]["mixed_label_keys"] else "PASS",
            {
                "mixed_views": audit_data["exact_float32_request_view"]["mixed_label_keys"],
                "minority_label_rows": audit_data["exact_float32_request_view"][
                    "minority_label_rows_on_mixed_keys"
                ],
            },
        ),
        "curated_vector_integrity": _gate(
            "PASS",
            {
                "unique_numeric_views": len(keys),
                "publisher_benign_views": labels.count(0),
                "publisher_attack_views": labels.count(1),
            },
        ),
        "publisher_class_balance": _gate(
            "PASS"
            if majority_fraction <= policy["data"]["maximum_majority_class_fraction"]
            else "FAIL",
            {"majority_fraction_on_unique_views": majority_fraction},
        ),
        "exposed_development_overlap": _gate(
            "PASS" if intersect == 0 else "FAIL", {"remaining_exact_overlap_views": intersect}
        ),
        "independent_source_lineage": _gate(
            "PASS" if source["independent_from_exposed_development"] else "FAIL",
            {"declared_parent": source["lineage_parent"]},
        ),
        "campaign_partition": _gate(
            "INCONCLUSIVE" if not source["per_row_campaign_available"] else "PASS",
            {"campaign_metadata_available": source["per_row_campaign_available"]},
        ),
        "related_template_and_temporal_leakage": _gate(
            "INCONCLUSIVE",
            {
                "exact_view_overlap_checked": True,
                "related_template_groups_available": False,
                "per_row_timestamps_available": source["per_row_timestamp_available"],
            },
        ),
        "source_label_shortcut": _gate(
            "INCONCLUSIVE",
            {
                "audited_two_class_sources": 1,
                "reason": "A single source cannot test whether source identity predicts the label",
            },
        ),
        "GLU207_public_input_coverage": _gate(
            "FAIL",
            {
                "observed_request_only_features": audit_data["request_features"],
                "required_fused_features": 207,
                "nonempty_body_rows_not_encoded": counts.get("nonempty_body_rows", 0),
            },
        ),
        "dual_class_source_coverage": _gate(
            "INCONCLUSIVE",
            {
                "audited_two_class_sources": 1,
                "minimum": policy["data"]["minimum_independent_dual_class_sources"],
            },
        ),
        "oracle_observation": _gate(
            "PASS",
            {
                "physical_requests": oracle_data["physical_requests_verified"],
                "three_source": oracle_data["three_source_correlated_requests"],
                "application_mutations": oracle_data[
                    "protected_staff_mutation_db_transition_verified"
                ],
            },
        ),
        "oracle_intent_ground_truth": _gate(
            "INCONCLUSIVE",
            {
                "intent_unknown": oracle_data["intent_unknown"],
                "machine_verified_benign": oracle_data["machine_verified_benign_intent"],
                "machine_verified_attack": oracle_data["machine_verified_attack_intent"],
            },
        ),
        "GLU207_artifact_integrity": _gate("PASS", model),
        "GLU207_independent_quality": _gate(
            "INCONCLUSIVE",
            {
                "eligible_independent_balanced_cohorts": 0,
                "precision": None,
                "recall": None,
                "fpr": None,
                "pr_auc": None,
                "reason": "No new source/campaign with independent request-level intent labels",
            },
        ),
        "production_edge_parity": _gate(
            "INCONCLUSIVE", {"lab_shadow": model["lab_shadow"], "rust_edge_207_verified": False}
        ),
        "formal_admission": _gate(
            "PASS" if formal_count >= scale["minimum_requests"] else "FAIL",
            {"admitted": formal_count, "minimum": scale["minimum_requests"]},
        ),
    }
    fit_status = _overall_status(
        gates,
        (
            "publisher_http_parsing",
            "curated_vector_integrity",
            "publisher_class_balance",
            "exposed_development_overlap",
        ),
    )
    evaluation_status = _overall_status(
        gates,
        (
            "publisher_http_parsing",
            "curated_vector_integrity",
            "publisher_class_balance",
            "exposed_development_overlap",
            "independent_source_lineage",
            "campaign_partition",
            "related_template_and_temporal_leakage",
            "dual_class_source_coverage",
        ),
    )
    result = {
        "format_version": 2,
        "policy_sha256": file_sha256(policy_path),
        "catalog_sha256": file_sha256(catalog_path),
        "handoff_sha256": file_sha256(handoff),
        "formal_scale_policy_sha256": file_sha256(policy_path.parent / policy["formal_policy"]),
        "evidence_file_sha256": {
            "audit": file_sha256(audit),
            "overlap": file_sha256(overlap),
            "oracle": file_sha256(oracle),
            "research_training": research_sha,
            "live_shadow": live_sha,
            "bundle_manifest": bundle_sha,
        },
        "label_tiers": {
            "MACHINE_VERIFIED_intent": oracle_data["machine_verified_benign_intent"]
            + oracle_data["machine_verified_attack_intent"],
            "PUBLISHER_LABELED_raw_rows": counts["raw_records"],
            "PUBLISHER_LABELED_parseable_rows": counts["parsed_request_representations"],
            "WEAK_LABEL_promoted": 0,
            "UNKNOWN_publisher_label_rows": counts.get("unknown_publisher_label_rows", 0),
            "UNKNOWN_independent_intent_on_parseable_publisher_rows": counts[
                "parsed_request_representations"
            ],
            "UNKNOWN_lab_oracle_intent": oracle_data["intent_unknown"],
            "publisher_intent_independently_verified": 0,
        },
        "data_accounting": {
            "raw_publisher_rows": counts["raw_records"],
            "unique_http_text_representations": audit_data["exact_text_representation"]["unique"],
            "unique_numeric_views_before_quarantine": audit_data["exact_float32_request_view"][
                "unique"
            ],
            "numeric_views_after_quarantine_and_exposed_overlap": len(keys),
            "verified_new_physical_requests": 0,
            "formal_admitted_requests": formal_count,
        },
        "gates": gates,
        "gate_count": len(gates),
        "gate_status_counts": {
            status: sum(gate["status"] == status for gate in gates.values())
            for status in ("PASS", "FAIL", "INCONCLUSIVE")
        },
        "research_fit_gate_status": fit_status,
        "research_eval_gate_status": evaluation_status,
        "model_technical_status": gates["GLU207_artifact_integrity"]["status"],
        "model_quality_status": gates["GLU207_independent_quality"]["status"],
        "formal_gate_status": _overall_status(gates, ("formal_admission",)),
        "RESEARCH_FIT_READY": fit_status == "PASS",
        "RESEARCH_EVAL_READY": evaluation_status == "PASS",
        "FORMAL_READY": False,
        "model_quality_metrics": {
            "precision": None,
            "recall": None,
            "fpr": None,
            "pr_auc": None,
            "false_positives_per_10000_benign": None,
            "attack_family_recall": None,
            "reason": "No eligible independent balanced cohort for GLU207",
        },
        "automatic_improvement": {
            "hypothesis": "76 request-only features collapse distinct HTTP content into conflicting views",
            "evidence_minority_label_rows": audit_data["exact_float32_request_view"][
                "minority_label_rows_on_mixed_keys"
            ],
            "experiment_started": False,
            "reason": "A bounded train-only fit is permissible; no independent quality evaluation exists",
        },
        "new_optimizer_updates": 0,
        "new_checkpoint": False,
        "new_onnx": False,
        "enforcement_actions": 0,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "next_action": "Run a bounded train-only fitting diagnostic on quarantined WAMM views; separately acquire a distinct dual-class source with request-level provenance and campaign/time groups for evaluation.",
    }
    result["report_sha256"] = digest(result)
    atomic_json(output, result)
    output.chmod(0o600)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "policy",
        "catalog",
        "audit",
        "overlap",
        "staging",
        "reference",
        "oracle",
        "bundle",
        "bundle-sha",
        "research-report",
        "research-sha",
        "live",
        "live-sha",
        "handoff",
        "output",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = assess(
            args.policy,
            args.catalog,
            args.audit,
            args.overlap,
            args.staging,
            args.reference,
            args.oracle,
            args.bundle,
            args.bundle_sha,
            args.research_report,
            args.research_sha,
            args.live,
            args.live_sha,
            args.handoff,
            args.output,
        )
    print(
        {
            "research_fit_ready": result["RESEARCH_FIT_READY"],
            "research_eval_ready": result["RESEARCH_EVAL_READY"],
            "formal_ready": result["FORMAL_READY"],
            "report": args.output,
        }
    )
