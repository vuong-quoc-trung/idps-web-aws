"""Temporal partitions + connected campaign/IP/user/session groups + embargo."""

import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, fsync_dir
from idps_ai.data.dataset import (
    REQUEST_SCHEMA,
    iter_rows,
    load_labels,
    manifest,
    verify_dataset,
    write_rows,
)
from idps_ai.data.privacy import pseudonym
from idps_ai.features.pipeline import (
    FeatureExtractor,
    feature_columns,
    fit_spec,
    implementation_fingerprint,
    transform,
)


def temporal_groups(rows, train_fraction=0.6, val_fraction=0.2, embargo_seconds=300):
    if embargo_seconds < 300 or not (
        0 < train_fraction < 1 and 0 < val_fraction < 1 and train_fraction + val_fraction < 1
    ):
        raise PipelineError("Invalid split fractions or embargo below the 300s lookback")
    if len(rows) < 5:
        raise PipelineError("Insufficient reviewed temporal groups for three partitions")
    rows = sorted(rows, key=lambda row: (row["timestamp"], row["event_key"]))
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    identities = {}
    for i, row in enumerate(rows):
        for column in ("campaign_key", "client_key", "user_key", "session_key"):
            value = row.get(column)
            if value is None:
                continue
            identity = (column, value)
            if identity in identities:
                parent[find(i)] = find(identities[identity])
            else:
                identities[identity] = i
    cuts = []
    for fraction in (train_fraction, train_fraction + val_fraction):
        index = min(max(1, int(len(rows) * fraction)), len(rows) - 1)
        cuts.append((rows[index - 1]["timestamp"] + rows[index]["timestamp"]) / 2)
    members = {}
    for i, row in enumerate(rows):
        members.setdefault(find(i), []).append(row)
    assignment, reviewed = {}, Counter()
    for group in members.values():
        low, high = group[0]["timestamp"], group[-1]["timestamp"]
        if high < cuts[0] - embargo_seconds:
            split = "train"
        elif low > cuts[0] + embargo_seconds and high < cuts[1] - embargo_seconds:
            split = "val"
        elif low > cuts[1] + embargo_seconds:
            split = "test"
        else:
            split = "excluded"
        group_key = digest(sorted(row["event_key"] for row in group))
        for row in group:
            assignment[row["event_key"]] = (split, group_key)
            if row.get("label") is not None:
                reviewed[split] += 1
    if any(reviewed[name] == 0 for name in ("train", "val", "test")):
        raise PipelineError(
            "Temporal/group purge leaves an empty reviewed partition; collect more independent campaigns/IPs"
        )
    return assignment, {
        "cutoffs": cuts,
        "embargo_seconds": embargo_seconds,
        "groups": len(members),
        "reviewed_rows": dict(reviewed),
        "group_columns": ["campaign_key", "client_key", "user_key", "session_key"],
        "policy": "connected groups never cross partitions; spanning/boundary groups purged; no random fallback",
    }


def prepare(dataset, output, labels_path=None, key=None):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    source_manifest = verify_dataset(dataset, "collected")
    if output.exists() or dataset.is_relative_to(output):
        raise PipelineError("Prepared dataset needs a new destination outside the source snapshot")
    labels = {}
    if labels_path:
        if (
            key is None
            or pseudonym(key, "fingerprint", "v1") != source_manifest["redaction_key_fingerprint"]
        ):
            raise PipelineError("Label import requires the same training redaction key")
        labels = load_labels(labels_path, key)

    def labeled_rows():
        for row in iter_rows(dataset / "requests.parquet"):
            if row["request_key"] in labels:
                row.update(labels[row["request_key"]])
            yield row

    metadata = [
        {
            k: row[k]
            for k in (
                "event_key",
                "timestamp",
                "campaign_key",
                "client_key",
                "user_key",
                "session_key",
                "label",
            )
        }
        for row in labeled_rows()
    ]
    assignment, split_report = temporal_groups(metadata)
    columns = feature_columns()

    def feature_rows(partition):
        extractor = FeatureExtractor()
        for row in labeled_rows():
            split, _ = assignment[row["event_key"]]
            if split != partition:
                continue
            numbers = extractor.observe(row)
            if row["label"] is not None:
                yield row, numbers

    spec = fit_spec(
        (numbers for row, numbers in feature_rows("train") if row["label"] == 0), columns
    )
    spec["fit_labels"] = "benign_only"
    spec["implementation_sha256"] = implementation_fingerprint()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=output.parent) as temporary:
        work = Path(temporary)
        shutil.copyfile(dataset / "observations.parquet", work / "observations.parquet")
        os.chmod(work / "observations.parquet", 0o600)

        def assigned_rows():
            for row in labeled_rows():
                row["split"], row["group_key"] = assignment[row["event_key"]]
                yield row

        write_rows(work / "requests.parquet", assigned_rows(), REQUEST_SCHEMA)
        atomic_json(work / "feature_spec.json", spec)
        schema = pa.schema(
            [
                ("event_key", pa.string()),
                ("timestamp", pa.float64()),
                ("split", pa.string()),
                ("group_key", pa.string()),
                ("label", pa.int8()),
                ("attack_family", pa.string()),
                ("x", pa.list_(pa.float32(), len(columns))),
            ]
        )
        counts, distributions = Counter(), {}

        def vectors():
            for partition in ("train", "val", "test"):
                dist = Counter()
                for row, numbers in feature_rows(partition):
                    counts[partition] += 1
                    dist[row["attack_family"]] += 1
                    yield {
                        "event_key": row["event_key"],
                        "timestamp": row["timestamp"],
                        "split": partition,
                        "group_key": assignment[row["event_key"]][1],
                        "label": row["label"],
                        "attack_family": row["attack_family"],
                        "x": transform(spec, numbers).tolist(),
                    }
                distributions[partition] = dict(dist)

        total = write_rows(work / "features.parquet", vectors(), schema)
        verify_dataset(dataset, "collected")
        result = manifest(
            work,
            "prepared",
            ["observations.parquet", "requests.parquet", "features.parquet", "feature_spec.json"],
            parent_dataset_sha256=source_manifest["dataset_sha256"],
            split=split_report,
            rows=dict(counts),
            feature_rows=total,
            feature_count=len(columns),
            label_distribution=distributions,
            label_manifest_sha256=file_sha256(labels_path)
            if labels_path
            else source_manifest["label_manifest_sha256"],
            redaction_key_fingerprint=source_manifest["redaction_key_fingerprint"],
            note="Synthetic metrics verify plumbing only when the capture is synthetic; unknown/weak labels never trained",
        )
        os.replace(work, output)
        fsync_dir(output.parent)
    return result
