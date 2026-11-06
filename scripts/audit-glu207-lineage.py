#!/usr/bin/env python3
"""Train-only lineage audit. Never reads a sealed holdout or changes datasets."""

import argparse
import bisect
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from idps_ai.common import file_sha256
from idps_ai.features.pipeline import (
    FeatureExtractor,
    implementation_fingerprint,
    transform,
)

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "ai-training/.artifacts/scale_upgrade_20261030/prepared-v5"
PARENT = ROOT / "ai-training/.artifacts/upgrade_20261030_deep/dataset-ready/collected"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise RuntimeError("Preserve previous audit; choose a new output")
    spec = json.loads((PREP / "feature_spec.json").read_text())
    manifest = json.loads((PREP / "dataset_manifest.json").read_text())
    parent = json.loads((PARENT / "dataset_manifest.json").read_text())
    assert manifest["parent_dataset_sha256"] == parent["dataset_sha256"]
    hashes = {}
    for base in [PREP, PARENT]:
        for n, v in json.loads((base / "dataset_manifest.json").read_text())[
            "files"
        ].items():
            if n in [
                "requests.parquet",
                "observations.parquet",
                "features.parquet",
                "feature_spec.json",
            ]:
                actual = file_sha256(base / n)
                assert actual == v["sha256"]
                hashes[str((base / n).relative_to(ROOT))] = actual
    req = pq.ParquetFile(PREP / "requests.parquet")
    features = pq.ParquetFile(PREP / "features.parquet")
    rows = []
    expected = []
    for i in range(82):
        group = req.read_row_group(i, use_threads=False).to_pylist()
        # Read only the prefix needed for the parity diagnostic, not val/test tensors.
        fx = (
            features.read_row_group(i, use_threads=False).to_pylist()
            if len(expected) < 512
            else []
        )
        for j, r in enumerate(group):
            if r["split"] != "train":
                continue
            rows.append(r)
            if len(expected) < 512:
                assert (
                    fx[j]["event_key"] == r["event_key"] and fx[j]["split"] == "train"
                )
                expected.append(fx[j]["x"])
    assert len(rows) == 41607
    keys = {r["request_key"] for r in rows}
    obs = defaultdict(lambda: defaultdict(list))
    flows = defaultdict(list)
    columns = [
        "event_key",
        "source",
        "event_type",
        "request_key",
        "flow_key",
        "timestamp",
        "available_at",
        "http_method",
        "uri_path",
        "status_code",
        "client_key",
        "flow_json",
    ]
    for b in pq.ParquetFile(PARENT / "observations.parquet").iter_batches(
        batch_size=512, columns=columns, use_threads=False
    ):
        for e in b.to_pylist():
            if e["request_key"] in keys and e["event_type"] == "http_request":
                obs[e["request_key"]][e["source"]].append(e)
            if e["event_type"] == "flow":
                flows[e["client_key"]].append(e)
    flow_order = {
        # Frozen SQL: ORDER BY a DESC,t DESC,eid ASC. The tie-break matters.
        k: sorted(
            v,
            key=lambda e: (e["available_at"], e["timestamp"], -int(e["event_key"], 16)),
        )
        for k, v in flows.items()
    }
    flow_index = {
        k: [(e["available_at"], e["timestamp"], -int(e["event_key"], 16)) for e in v]
        for k, v in flow_order.items()
    }
    print("Normalized observations indexed; checking41607 train rows", flush=True)
    counts = Counter()
    field_conflicts = Counter()
    conflict_patterns = Counter()
    http_examples = []
    flow_examples = []
    issues = []
    sourcecounts = Counter()
    flowpresent = 0
    flow_causes = Counter()
    for r in rows:
        g = obs[r["request_key"]]
        for s in g:
            sourcecounts[s] += 1
        if set(g) == {"NGINX", "STUDENT_AUDIT", "SURICATA"}:
            counts["three_sources_in_observations"] += 1
        if any(len(v) != 1 for v in g.values()):
            counts["duplicate_or_missing_mapping"] += 1
            continue
        vals = [v[0] for v in g.values()]
        good = (
            len(vals) == 3
            and r["correlation"] == "request_id"
            and all(
                len({v[k] for v in vals}) == 1
                for k in ["http_method", "uri_path", "status_code"]
            )
        )
        counts[
            "http_consistent_triplets" if good else "http_conflict_or_unverified"
        ] += 1
        if not good:
            conflict_patterns[
                json.dumps(
                    {
                        v["source"]: [v["http_method"], v["uri_path"], v["status_code"]]
                        for v in vals
                    },
                    sort_keys=True,
                )
            ] += 1
            for field in ["http_method", "uri_path", "status_code"]:
                if len({v[field] for v in vals}) != 1:
                    field_conflicts[field] += 1
            if len(http_examples) < 8:
                http_examples.append(
                    {
                        "request_key": r["request_key"],
                        "sources": {
                            v["source"]: {
                                k: v[k]
                                for k in [
                                    "http_method",
                                    "uri_path",
                                    "status_code",
                                    "timestamp",
                                ]
                            }
                            for v in vals
                        },
                    }
                )
        if not good and len(issues) < 20:
            issues.append(
                {
                    "request_key": r["request_key"],
                    "sources": sorted(g),
                    "correlation": r["correlation"],
                }
            )
        f = json.loads(r["flow_json"])
        if any(v is not None for v in f.values()):
            flowpresent += 1
            group = flow_order.get(r["client_key"], [])
            index = flow_index.get(r["client_key"], [])
            i = (
                bisect.bisect_right(index, (r["timestamp"], float("inf"), float("inf")))
                - 1
            )
            chosen = None
            while i >= 0 and group[i]["available_at"] >= r["timestamp"] - 300:
                if group[i]["timestamp"] >= r["timestamp"] - 300:
                    chosen = group[i]
                    break
                i -= 1
            if (
                chosen
                and json.loads(chosen["flow_json"]) != f
                and len(flow_examples) < 8
            ):
                flow_examples.append(
                    {
                        "request_key": r["request_key"],
                        "request_t": r["timestamp"],
                        "chosen_t": chosen["timestamp"],
                        "chosen_available_at": chosen["available_at"],
                        "stored": f,
                        "reconstructed": json.loads(chosen["flow_json"]),
                    }
                )
            flow_causes[
                "matches_prior_completed_client_flow"
                if chosen and json.loads(chosen["flow_json"]) == f
                else "flow_not_reconstructed"
            ] += 1
    ext = FeatureExtractor(**spec["state_limits"])
    maxerr = 0
    for r, e in zip(rows[: len(expected)], expected):
        x = transform(spec, ext.observe(r))
        assert x.shape == (207,) and x.dtype == np.float32
        maxerr = max(maxerr, float(np.max(np.abs(x - np.asarray(e, np.float32)))))
        assert np.array_equal(x, np.asarray(e, np.float32))
    r = {
        "status": "PARTIAL_RAW_SOURCE_ATTESTATION_NOT_REDECODED",
        "train_rows": len(rows),
        "train_unique_request_keys": len(keys),
        "source_rows_with_normalized_evidence": dict(sourcecounts),
        "correlation_checks": dict(counts),
        "issues": issues,
        "http_conflicts_by_field": dict(field_conflicts),
        "http_conflict_patterns": dict(conflict_patterns),
        "http_examples": http_examples,
        "flow_examples": flow_examples,
        "flow_present_rows": flowpresent,
        "flow_missing_rows": len(rows) - flowpresent,
        "flow_semantics_checks": dict(flow_causes),
        "feature_parity": {
            "status": "PASS",
            "chronological_train_prefix_rows": len(expected),
            "features": 207,
            "dtype": "float32",
            "max_absolute_error": maxerr,
            "implementation_fingerprint_matches": implementation_fingerprint()
            == spec["implementation_sha256"],
        },
        "verified_file_hashes": hashes,
        "limits": [
            "Counts from actual training rows and immutable normalized observations, not feature nonzero inference",
            "Raw PCAP not redecoded and original response headers not reattested for all training rows",
            "Scenario/runner labels remain without independent human review; no recall/FPR or exploit-success claims",
            "Only train partition and bounded prefix feature replay; no sealed holdout opened",
            "Flow features mean previous available completed client flow, not request-specific byte counters",
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(r, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: r[k]
                for k in [
                    "train_rows",
                    "source_rows_with_normalized_evidence",
                    "correlation_checks",
                    "flow_semantics_checks",
                    "feature_parity",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
