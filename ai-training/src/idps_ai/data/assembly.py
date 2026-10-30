"""Shared train-benign scaler over immutable, compatible raw numeric shards.

Research assembly is not scale admission. Original test stays test; validation
is separated by whole campaigns before fitting. No per-source standardized
vectors are concatenated. SQLite bounds memory independently of row count.
"""

import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

import pyarrow as pa
import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import (
    OBSERVATION_SCHEMA,
    REQUEST_SCHEMA,
    iter_rows,
    manifest,
    verify_dataset,
    write_rows,
)
from idps_ai.data.provenance import verify_provenance
from idps_ai.data.snapshot import new_destination
from idps_ai.features.pipeline import (
    FeatureExtractor,
    fit_spec,
    implementation_fingerprint,
    transform,
)

PARTS = ("train", "calibration", "val", "test")


def assemble(registry, output):
    if isinstance(registry, (str, Path)):
        registry = yaml.safe_load(Path(registry).read_text())
    if registry.get("format_version") != 1 or not registry.get("sources"):
        raise PipelineError("Nonempty immutable source registry required")
    output = new_destination(output)
    sources, seen, captures, fingerprints = [], set(), set(), {}
    template = None
    for entry in registry["sources"]:
        path = Path(entry["dataset"])
        path = path if path.is_absolute() else AI_ROOT / path
        value = verify_dataset(path, "prepared")
        source_spec = load_json(path / "feature_spec.json")
        identity = value["dataset_sha256"]
        if identity in seen or value["files"]["requests.parquet"]["sha256"] in seen:
            raise PipelineError("Duplicate immutable capture/shard")
        seen.update((identity, value["files"]["requests.parquet"]["sha256"]))
        if entry.get("provenance"):
            proof_path = Path(entry["provenance"])
            proof = verify_provenance(
                proof_path if proof_path.is_absolute() else AI_ROOT / proof_path
            )
            if proof["dataset_sha256"] != identity:
                raise PipelineError("Source provenance/dataset binding mismatch")
            capture = proof.get("sensor_evidence", {}).get("pcap_sha256")
            if capture and capture in captures:
                raise PipelineError("Duplicate packet capture under a different projection/key")
            if capture:
                captures.add(capture)
        signature = {
            k: source_spec.get(k)
            for k in (
                "columns",
                "input_profile",
                "feature_version",
                "normalizer_version",
                "state_limits",
                "implementation_sha256",
            )
        }
        if source_spec.get("implementation_sha256") != implementation_fingerprint():
            raise PipelineError("Feature implementation changed; reproject raw inputs explicitly")
        if template is not None and signature != template:
            raise PipelineError(
                "Incompatible source profile/schema; missing flow/time cannot be fabricated"
            )
        template = signature
        mapping = entry.get("partition_map", {})
        if mapping != {"train": "train", "val": "grouped_validation", "test": "test"}:
            raise PipelineError(
                "Assembly must preserve original held-out roles and grouped validation"
            )
        fingerprint = value["redaction_key_fingerprint"]
        if fingerprint in fingerprints and fingerprints[fingerprint] != entry["environment_id"]:
            raise PipelineError(
                "Same identity key claimed across environments; resolve identity scope"
            )
        fingerprints[fingerprint] = entry["environment_id"]
        # Only group/time metadata, not labels, decides calibration assignment.
        groups = {}
        for row in iter_rows(
            path / "requests.parquet", columns=["split", "group_key", "campaign_key", "timestamp"]
        ):
            if row["split"] == "val":
                group = row.get("group_key") or row.get("campaign_key")
                if not group:
                    raise PipelineError("Missing validation campaign/group")
                groups[group] = min(groups.get(group, float("inf")), row["timestamp"])
        order = sorted(groups, key=lambda g: (groups[g], g))
        if len(order) < 2:
            raise PipelineError("At least two whole validation groups needed")
        sources.append((path, value, set(order[: max(1, len(order) // 3)]), entry))
    with tempfile.TemporaryDirectory(prefix=".assemble-", dir=output.parent) as temporary:
        work = Path(temporary)
        db = sqlite3.connect(work / "scratch.sqlite")
        db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE r(id TEXT PRIMARY KEY,p TEXT,t REAL,scope TEXT,payload TEXT);
            CREATE INDEX rp ON r(p,t,id);
            CREATE TABLE identities(scope TEXT,kind TEXT,id TEXT,p TEXT,PRIMARY KEY(scope,kind,id));
            CREATE TABLE f(id TEXT PRIMARY KEY,p TEXT,t REAL,y INTEGER,family TEXT,g TEXT,n TEXT);
        """)
        for path, value, calibration, entry in sources:
            for row in iter_rows(path / "requests.parquet"):
                part = row["split"]
                if part == "excluded":
                    continue
                if part not in ("train", "val", "test"):
                    raise PipelineError("Unexpected original partition")
                group = row.get("group_key") or row.get("campaign_key")
                if part == "val" and group in calibration:
                    part = "calibration"
                row["split"] = part
                scope = value["redaction_key_fingerprint"]
                try:
                    db.execute(
                        "INSERT INTO r VALUES(?,?,?,?,?)",
                        (row["event_key"], part, row["timestamp"], scope, json.dumps(row)),
                    )
                except sqlite3.IntegrityError:
                    raise PipelineError("Duplicate request identity across shards") from None
                for kind in ("campaign_key", "client_key", "user_key", "session_key"):
                    if row.get(kind) is None:
                        continue
                    before = db.execute(
                        "SELECT p FROM identities WHERE scope=? AND kind=? AND id=?",
                        (scope, kind, row[kind]),
                    ).fetchone()
                    if before and before[0] != part:
                        raise PipelineError("Connected identity crosses assembled partitions")
                    db.execute(
                        "INSERT OR IGNORE INTO identities VALUES(?,?,?,?)",
                        (scope, kind, row[kind], part),
                    )
            db.commit()
        options = template["state_limits"]
        for part in PARTS:
            extractors = {}
            for event, scope in db.execute(
                "SELECT payload,scope FROM r WHERE p=? ORDER BY t,id", (part,)
            ):
                row = json.loads(event)
                if scope not in extractors:
                    extractors[scope] = FeatureExtractor(**options)
                numbers = extractors[scope].observe(row)
                if row["label"] is not None:
                    db.execute(
                        "INSERT INTO f VALUES(?,?,?,?,?,?,?)",
                        (
                            row["event_key"],
                            part,
                            row["timestamp"],
                            row["label"],
                            row["attack_family"],
                            row["group_key"],
                            json.dumps(numbers),
                        ),
                    )
            db.commit()
        spec = dict(source_spec)
        fitted = fit_spec(
            (
                json.loads(r[0])
                for r in db.execute("SELECT n FROM f WHERE p='train' AND y=0 ORDER BY t,id")
            ),
            template["columns"],
        )
        spec.update(
            {k: fitted[k] for k in ("mean", "std", "fit_rows", "fit_partition", "raw_clip", "clip")}
        )
        spec["fit_labels"] = "benign_only"
        spec["assembly"] = "recomputed numeric features; shared scaler fit on train benign only"
        atomic_json(work / "feature_spec.json", spec)
        write_rows(
            work / "requests.parquet",
            (json.loads(r[0]) for r in db.execute("SELECT payload FROM r ORDER BY t,id")),
            REQUEST_SCHEMA,
        )
        write_rows(
            work / "observations.parquet",
            (r for path, _, _, _ in sources for r in iter_rows(path / "observations.parquet")),
            OBSERVATION_SCHEMA,
        )
        schema = pa.schema(
            [
                ("event_key", pa.string()),
                ("timestamp", pa.float64()),
                ("split", pa.string()),
                ("group_key", pa.string()),
                ("label", pa.int8()),
                ("attack_family", pa.string()),
                ("x", pa.list_(pa.float32(), len(spec["columns"]))),
            ]
        )
        counts, distribution = Counter(), {}

        def vectors():
            for identity, part, timestamp, label, family, group, numbers in db.execute(
                "SELECT * FROM f ORDER BY p,t,id"
            ):
                counts[part] += 1
                distribution.setdefault(part, Counter())[family] += 1
                yield {
                    "event_key": identity,
                    "timestamp": timestamp,
                    "split": part,
                    "group_key": group,
                    "label": label,
                    "attack_family": family,
                    "x": transform(spec, json.loads(numbers)).tolist(),
                }

        total = write_rows(work / "features.parquet", vectors(), schema)
        if set(counts) != set(PARTS):
            raise PipelineError("Empty assembled role")
        bounds = {
            p: [lo, hi] for p, lo, hi in db.execute("SELECT p,min(t),max(t) FROM f GROUP BY p")
        }
        chronology = {
            a + "_before_" + b: bounds[a][1] + 600 < bounds[b][0] for a, b in zip(PARTS, PARTS[1:])
        }
        db.close()
        (work / "scratch.sqlite").unlink()
        source_bindings = [
            {
                "dataset_sha256": v["dataset_sha256"],
                "manifest_sha256": file_sha256(p / "dataset_manifest.json"),
                "environment_id": e["environment_id"],
                "calibration_groups": sorted(c),
            }
            for p, v, c, e in sources
        ]
        for path, value, _, _ in sources:
            if verify_dataset(path)["dataset_sha256"] != value["dataset_sha256"]:
                raise PipelineError("Source mutated during assembly")
        result = manifest(
            work,
            "prepared",
            ["requests.parquet", "observations.parquet", "features.parquet", "feature_spec.json"],
            input_profile=spec["input_profile"],
            normalizer_version=spec["normalizer_version"],
            redaction_key_fingerprint=digest(sorted(fingerprints)),
            rows=dict(counts),
            feature_rows=total,
            feature_count=len(spec["columns"]),
            label_distribution={p: dict(v) for p, v in distribution.items()},
            source_bindings=source_bindings,
            calibration_disjoint_groups=True,
            calibration_temporally_independent=chronology["calibration_before_val"],
            partition_time_bounds=bounds,
            temporal_embargo_checks=chronology,
            formal_training_permitted=False,
            assembly_scope="compatible-shard research; separate reviewed scale admission required",
            identity_scope="stable redaction-key namespace; no semantic cross-key dedup guarantee",
            limitations=[
                "No independent source/label review is created by assembly",
                "No source can be promoted from test to train",
                "Different input profiles are rejected, not filled with invented flow/time",
                "Formal scale readiness and endurance not accepted by this assembly",
            ],
        )
        os.replace(work, output)
    return result
