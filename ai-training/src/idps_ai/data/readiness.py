"""Auditable pre-training checks. No optimizer/model fitting or network operations."""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, fsync_dir
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.snapshot import new_destination
from idps_ai.data.split import temporal_groups
from idps_ai.features.pipeline import (
    FeatureExtractor,
    feature_columns,
    implementation_fingerprint,
    transform,
)


def audit_readiness(dataset, output, data_kind, policy_path=None, provenance=None):
    policy_path = Path(policy_path or AI_ROOT / "configs/pretrain_policy.yaml")
    policy = yaml.safe_load(policy_path.read_text())
    source = verify_dataset(dataset)
    output = new_destination(output)
    rows = list(iter_rows(Path(dataset) / "requests.parquet"))
    if len(rows) > 2_000_000:
        raise PipelineError("Readiness metadata cap exceeded; use smaller snapshots")
    checks = []

    def check(name, passed, detail):
        checks.append({"id": name, "pass": bool(passed), "detail": detail})

    # Provenance is an auditable declaration, not a cryptographic attestation of the lab.
    check(
        "provenance",
        data_kind in policy["allowed_data_kinds"] and provenance is not None,
        "Real lab pilot requires a bound capture/observer provenance file; synthetic/demo cannot certify readiness",
    )
    if provenance:
        from idps_ai.data.provenance import verify_provenance

        proof = verify_provenance(provenance)
        check(
            "provenance_binding",
            proof["dataset_sha256"] == source["dataset_sha256"] and proof["data_kind"] == data_kind,
            "Provenance references this immutable dataset",
        )
    else:
        proof = {}
    check(
        "volume",
        len(rows) >= policy["minimum_requests"],
        {"actual": len(rows), "minimum": policy["minimum_requests"]},
    )
    known = [r for r in rows if r["label"] is not None]
    check(
        "reviewed_labels",
        len(known) / max(len(rows), 1) >= policy["minimum_label_coverage"]
        and all(
            r["label_source"] in ("human_review", "scenario_manifest")
            and (r["label_confidence"] or 0) >= policy["minimum_label_confidence"]
            for r in known
        ),
        {
            "known": len(known),
            "unknown": len(rows) - len(known),
            "coverage": len(known) / max(len(rows), 1),
        },
    )
    check(
        "approved_identity",
        all(
            r["correlation"] != "ambiguous_request_id"
            and r["request_key"] is not None
            and r["campaign_key"] is not None
            for r in known
        ),
        "No ambiguous or ungrouped observation can be approved",
    )
    check(
        "identity",
        sum(
            r["client_key"] is None
            or r["request_key"] is None
            or r["correlation"] == "ambiguous_request_id"
            for r in rows
        )
        / max(len(rows), 1)
        <= policy["maximum_unknown_identity_fraction"],
        "Trusted source/request identity coverage; this does not prove topology attribution acceptance",
    )
    role_counts = Counter(r["role"] for r in rows)
    check("roles", all(role_counts[r] > 0 for r in policy["required_roles"]), dict(role_counts))
    observed = Counter(
        r["source"] for r in iter_rows(Path(dataset) / "observations.parquet", columns=["source"])
    )
    check("sources", all(observed[s] > 0 for s in policy["required_sources"]), dict(observed))
    check(
        "http_coverage",
        all(
            any(
                (r["status_code"] or 0) < 400 and r["http_method"] in methods
                for r in known
                if r["label"] == 0
            )
            for methods in [("GET", "HEAD", "OPTIONS"), ("POST", "PUT", "PATCH", "DELETE")]
        )
        and any((r["status_code"] or 0) >= 400 and r["label"] == 0 for r in known),
        "Reviewed benign reads, mutations and hard-negative HTTP errors must all exist",
    )
    quality = source.get("quality", proof.get("collection_quality", {}))
    invalid = sum(quality.get(n, 0) for n in ("invalid", "oversized", "partial"))
    check(
        "parser_quality",
        invalid / max(quality.get("accepted", len(rows)) + invalid, 1)
        <= policy["maximum_invalid_fraction"],
        quality,
    )
    assignment = {}
    split_error = None
    try:
        assignment, split = temporal_groups(rows, embargo_seconds=policy["embargo_seconds"])
    except PipelineError as error:
        split = {}
        split_error = str(error)
    check("temporal_split", bool(assignment), split_error or split)
    distributions = {}
    groups = {}
    times = {}
    for partition in ("train", "val", "test"):
        part = [r for r in known if assignment.get(r["event_key"], ("",))[0] == partition]
        distributions[partition] = dict(Counter(r["attack_family"] for r in part))
        groups[partition] = len({assignment[r["event_key"]][1] for r in part})
        times[partition] = [
            min((r["timestamp"] for r in part), default=None),
            max((r["timestamp"] for r in part), default=None),
        ]
        check(
            partition + "_classes",
            all(
                distributions[partition].get(f, 0) >= policy["minimum_family_per_partition"]
                for f in policy["required_families"]
            )
            and distributions[partition].get("benign", 0) >= policy["minimum_benign_per_partition"],
            distributions[partition],
        )
        check(
            partition + "_groups",
            groups[partition] >= policy["minimum_groups_per_partition"],
            groups[partition],
        )
    # Independently audit identities across the proposed partition assignment.
    owners = {}
    overlaps = 0
    for row in rows:
        partition = assignment.get(row["event_key"], ("excluded",))[0]
        if partition == "excluded":
            continue
        for col in ("client_key", "user_key", "session_key", "campaign_key"):
            if row.get(col) is None:
                continue
            identity = (col, row[col])
            previous = owners.setdefault(identity, partition)
            overlaps += previous != partition
    check(
        "identity_disjoint",
        bool(assignment) and overlaps == 0,
        {"cross_partition_identities": overlaps},
    )
    variants = proof.get("label_evidence", {}).get("campaign_variant_groups", {})
    variant_partitions = {}
    variant_overlap = 0
    missing_variant = 0
    for row in known:
        partition = assignment.get(row["event_key"], ("excluded",))[0]
        if row["label"] == 0 or partition == "excluded":
            continue
        identifiers = variants.get(row["campaign_key"], [])
        if not identifiers:
            missing_variant += 1
        for identifier in identifiers:
            previous = variant_partitions.setdefault(identifier, partition)
            variant_overlap += previous != partition
    if policy.get("require_variant_provenance", True):
        check(
            "heldout_variants",
            bool(variants) and missing_variant == 0 and variant_overlap == 0,
            {
                "missing_variant_rows": missing_variant,
                "cross_partition_variant_rows": variant_overlap,
                "distinct_scripted_views": len(variant_partitions),
            },
        )
    spec_file = Path(dataset) / "feature_spec.json"
    vector_count = nonfinite = mismatch = 0
    quality_counts = Counter()
    feature_ranges = {}
    if source["stage"] == "prepared":
        spec = json.loads(spec_file.read_text())
        check(
            "rule_free_features",
            not any(
                n.startswith("context_suricata_")
                or n
                in (
                    "label",
                    "rule_signals",
                    "request_key",
                    "campaign_key",
                    "client_key",
                    "user_key",
                )
                for n in spec["columns"]
            ),
            "Rule facts and identities are not model inputs",
        )
        check(
            "feature_contract",
            spec["columns"] == feature_columns()
            and spec.get("implementation_sha256") == implementation_fingerprint(),
            "Feature order and implementation fingerprint match the current source",
        )
        for row in iter_rows(Path(dataset) / "features.parquet"):
            x = np.asarray(row["x"], np.float32)
            vector_count += 1
            nonfinite += int(not np.isfinite(x).all())

        # Replay each causal state independently; compare every persisted feature.
        def replay():
            for partition in ("train", "val", "test"):
                extractor = FeatureExtractor()
                for row in rows:
                    if row.get("split") != partition:
                        continue
                    values = extractor.observe(row)
                    for name, value in values.items():
                        if name.endswith("_missing") or name.endswith("_incomplete"):
                            quality_counts[name] += int(value != 0)
                        bounds = feature_ranges.setdefault(name, [value, value])
                        bounds[0] = min(bounds[0], value)
                        bounds[1] = max(bounds[1], value)
                    if row["label"] is not None:
                        yield row["event_key"], transform(spec, values)

        vectors = iter(iter_rows(Path(dataset) / "features.parquet"))
        for event_key, expected in replay():
            actual = next(vectors, None)
            if (
                actual is None
                or actual["event_key"] != event_key
                or not np.array_equal(np.asarray(actual["x"], np.float32), expected)
            ):
                mismatch += 1
        if next(vectors, None) is not None:
            mismatch += 1
        check(
            "finite_vectors",
            vector_count == source["feature_rows"] and nonfinite == 0,
            {"vectors": vector_count, "nonfinite": nonfinite},
        )
        check("offline_replay_parity", mismatch == 0, {"mismatched_vectors": mismatch})
    else:
        check("prepared_features", False, "Collected observations must be prepared before training")
    passed = all(c["pass"] for c in checks)
    result = {
        "format_version": 1,
        "status": "READY_FOR_OFFLINE_PILOT" if passed else "NOT_READY",
        "offline_pilot_training_permitted": passed,
        "training_executed": False,
        "dataset_sha256": source["dataset_sha256"],
        "policy_sha256": file_sha256(policy_path),
        "purpose": policy["purpose"],
        "data_kind": data_kind,
        "provenance_sha256": file_sha256(provenance) if provenance else None,
        "implementation_sha256": implementation_fingerprint(),
        "source_files_sha256": {
            str(p.relative_to(AI_ROOT)): file_sha256(p)
            for p in sorted((AI_ROOT / "src").rglob("*.py"))
        },
        "checks": checks,
        "rows": len(rows),
        "label_distributions": distributions,
        "groups_per_partition": groups,
        "partition_time_ranges": times,
        "feature_count": source.get("feature_count"),
        "quality_feature_counts": dict(quality_counts),
        "constant_feature_columns": [n for n, b in feature_ranges.items() if b[0] == b[1]],
        "limits": [
            "This gate checks offline pilot data readiness, not detection quality or production acceptance",
            "No training is executed; rule comparison, quality metrics and held-out performance follow training",
            "Rust preprocessing/inference parity and target-machine endurance remain separate acceptance tasks",
        ]
        + proof.get("limits", []),
    }
    result["report_sha256"] = digest(result)
    with tempfile.TemporaryDirectory(prefix=".readiness-", dir=output.parent) as temporary:
        work = Path(temporary)
        atomic_json(work / "readiness.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result
