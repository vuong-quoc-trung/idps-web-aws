#!/usr/bin/env python3
"""Exclude exact float32 views already exposed in development roles.

Only numeric vectors and aggregate counts are written. This does not establish
publisher-label truth or independence from related templates/campaigns.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.training.resources import resource_envelope

ALLOWED_ROLES = frozenset({"train", "calibration", "val"})


def filter_views(candidate, reference, candidate_sha, reference_sha, output, report_path):
    candidate, reference, output, report_path = map(
        Path, (candidate, reference, output, report_path)
    )
    if output.exists() or report_path.exists():
        raise PipelineError("Overlap output already exists")
    if file_sha256(candidate) != candidate_sha or file_sha256(reference) != reference_sha:
        raise PipelineError("Pinned numeric input SHA256 changed")
    ref = pq.ParquetFile(reference)
    if ref.metadata.num_rows > 1_000_000:
        raise PipelineError("Development reference exceeds bounded row count")
    reference_views = {}
    for batch in ref.iter_batches(batch_size=8192, columns=["source_id", "split", "label", "x"]):
        source = batch.column("source_id").to_pylist()
        split = batch.column("split").to_pylist()
        labels = batch.column("label").to_pylist()
        vectors = (
            batch.column("x").values.to_numpy(zero_copy_only=False).reshape(batch.num_rows, 76)
        )
        for i, value in enumerate(vectors):
            if split[i] not in ALLOWED_ROLES or labels[i] not in (0, 1):
                raise PipelineError("Reference includes sealed/unknown role or invalid label")
            key = hashlib.sha256(value.tobytes()).hexdigest()
            reference_views.setdefault(key, []).append((source[i], split[i], labels[i]))
    table = pq.read_table(candidate)
    if table.column_names != ["view_sha256", "label", "occurrence_rows", "features"]:
        raise PipelineError("Candidate numeric staging schema changed")
    keys = table.column("view_sha256").to_pylist()
    labels = table.column("label").to_pylist()
    vectors = (
        table.column("features")
        .combine_chunks()
        .values.to_numpy(zero_copy_only=False)
        .reshape(len(keys), 76)
    )
    if len(keys) != len(set(keys)) or len(keys) > 1_000_000:
        raise PipelineError("Candidate has duplicate or excessive views")
    for key, vector in zip(keys, vectors):
        if key != hashlib.sha256(vector.tobytes()).hexdigest():
            raise PipelineError("Candidate feature/view hash mismatch")
    keep = []
    overlap_rows = Counter()
    overlap_views_by_source_role = Counter()
    for i, key in enumerate(keys):
        previous = reference_views.get(key)
        if previous is None:
            keep.append(i)
            continue
        overlap_rows["candidate_views"] += 1
        for source, role, previous_label in previous:
            overlap_rows["reference_rows"] += 1
            overlap_rows["label_disagreements"] += previous_label != labels[i]
            overlap_views_by_source_role[(source, role)] += 1
    result = table.take(pa.array(keep, type=pa.int64()))
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pq.write_table(result, output, compression="zstd", row_group_size=4096)
    output.chmod(0o600)
    report = {
        "format_version": 1,
        "research_policy_sha256": file_sha256(
            Path(__file__).resolve().parents[1] / "configs/autonomous_research_policy_v1.yaml"
        ),
        "candidate_sha256": candidate_sha,
        "reference_sha256": reference_sha,
        "filter_script_sha256": file_sha256(__file__),
        "reference_roles_allowed": sorted(ALLOWED_ROLES),
        "reference_rows": ref.metadata.num_rows,
        "reference_unique_views": len(reference_views),
        "candidate_views": len(keys),
        "overlap": dict(overlap_rows),
        "overlap_reference_rows_by_source_role": {
            f"{source}:{role}": count
            for (source, role), count in sorted(overlap_views_by_source_role.items())
        },
        "filtered_views": result.num_rows,
        "filtered_publisher_benign_views": sum(labels[i] == 0 for i in keep),
        "filtered_publisher_attack_views": sum(labels[i] == 1 for i in keep),
        "filtered_file_sha256": file_sha256(output),
        "research_fit_staging_ready": True,
        "autonomous_research_ready": False,
        "autonomous_research_blockers": [
            "Only one dual-class publisher; SR-BH-derived WAMM is not independent of exposed development data.",
            "No per-row campaign, actor or timestamp provenance for a defensible partition.",
            "Publisher labels and related-template independence have not been verified at request level.",
        ],
        "physical_requests_verified": 0,
        "independent_evaluation_ready": False,
        "formal_ready": False,
        "formal_admitted_requests": 0,
        "limits": "Exact view exclusion is not near-duplicate, lineage or publisher-label verification. WAMM remains SR-BH-derived research staging without independent acceptance.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(report_path, report)
    report_path.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--reference-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        summary = filter_views(
            args.candidate,
            args.reference,
            args.candidate_sha256,
            args.reference_sha256,
            args.output,
            args.report,
        )
    print({"filtered_views": summary["filtered_views"], "report": args.report})
