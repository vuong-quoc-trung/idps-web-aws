"""Immutable application-neutral request corpus with explicit partial labels.

No source name, actor, status, timestamp, rule or family is a feature. Publisher
request-level positives with unknown attack location retain that limitation.
Existing held-out roles cannot silently become train. Unknown is never benign.
"""

import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, write_rows
from idps_ai.data.http_benchmark import read_http
from idps_ai.data.snapshot import new_destination
from idps_ai.features.pipeline import fit_spec, transform
from idps_ai.features.request_view import (
    PROFILE,
    columns,
    fingerprint,
    project_request,
    validate_numbers,
    validate_view,
)

PARTS = ("train", "calibration", "val", "test", "reference")
PAYLOAD_FAMILIES = {"sqli", "xss", "path_traversal", "cmd_injection"}
SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("source_id", pa.string()),
        ("group_key", pa.string()),
        ("split", pa.string()),
        ("label", pa.int8()),
        ("evaluation_label", pa.int8()),
        ("attack_family", pa.string()),
        ("visibility", pa.string()),
        ("feature_key", pa.string()),
        ("timestamp", pa.float64()),
        ("numeric_json", pa.string()),
    ]
)


def read_pkdd(path, identity_key):
    """Parse the repository's bounded *flattened* mirror, not invented XML fields.

    This mirror has no Context/inContext/attackIntervall. Never reconstruct them
    from rule matches. Metadata/headers/body are transient and discarded.
    """
    part, size = [], 0
    with Path(path).open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536:
                raise PipelineError("Oversized public flattened HTTP line")
            if line.startswith(b"Start - Id:"):
                if part:
                    raise PipelineError("Nested public HTTP record boundary")
                part, size = [line], len(line)
                continue
            if not part:
                if line.strip():
                    raise PipelineError("Unframed public HTTP record")
                continue
            part.append(line)
            size += len(line)
            if size > 2 * 1024**2:
                raise PipelineError("Oversized public HTTP record")
            if not line.startswith(b"End - Id:"):
                continue
            if part[0].split(b":", 1)[1].strip() != line.split(b":", 1)[1].strip():
                raise PipelineError("Mismatched public HTTP record identity")
            labels = [
                item.split(b":", 1)[1].strip().decode("ascii")
                for item in part
                if item.startswith(b"class:")
            ]
            if len(labels) != 1 or labels[0] not in (
                "Valid",
                "XSS",
                "SqlInjection",
                "LdapInjection",
                "XPathInjection",
                "PathTransversal",
                "OsCommanding",
                "SSI",
            ):
                raise PipelineError("Unknown publisher class annotation; no automatic mapping")
            request = re.fullmatch(rb"([A-Za-z]{1,24}) (.{1,8192}) HTTP/\d\.\d\r?\n", part[2])
            if not request:
                raise PipelineError("Malformed flattened HTTP request line")
            method, target = request.group(1).decode(), request.group(2).decode("latin-1")
            view = project_request(target, method)
            identity = hmac.new(
                identity_key, b"pkdd:" + part[0].strip(), hashlib.sha256
            ).hexdigest()
            # Group identical model views together, regardless of publisher class.
            group = digest(view["numbers"])
            label = int(labels[0] != "Valid")
            yield {
                "event_key": identity,
                "group_key": group,
                "label": label,
                "evaluation_label": label,
                "attack_family": "benign" if not label else None,
                "numbers": view["numbers"],
                "visibility": "request_location_unavailable",
            }
            part, size = [], 0
    if part:
        raise PipelineError("Partial public flattened HTTP record")


def public_role(group):
    # Declared before viewing scores/labels. No fake wall clock or session.
    n = int(group[:8], 16) % 100
    return "train" if n < 70 else "calibration" if n < 85 else "val"


def lab_rows(eve, request_dataset, identity_key, source_id="student-lab"):
    """Reproject same real PCAP, joining only existing train/val request identities."""
    from idps_ai.data.dataset import verify_dataset
    from idps_ai.data.privacy import pseudonym
    from idps_ai.data.readers import eve_request_id
    from idps_ai.training.protocol import validation_groups

    manifest = verify_dataset(request_dataset, "prepared")
    if pseudonym(identity_key, "fingerprint", "v1") != manifest["redaction_key_fingerprint"]:
        raise PipelineError("Lab join uses a different redaction-key namespace")
    known = {
        r["request_key"]: r
        for r in iter_rows(Path(request_dataset) / "requests.parquet")
        if r["split"] in ("train", "val")
    }
    protocol = validation_groups(request_dataset)
    calibration = set(protocol["calibration_groups"])
    with Path(eve).open() as stream:
        for line in stream:
            event = json.loads(line)
            if event.get("event_type") != "http":
                continue
            rid = pseudonym(identity_key, "request", eve_request_id(event.get("http") or {}))
            if rid not in known:
                continue
            row = known[rid]
            view = event.get("ai_request_view")
            validate_view(view or {})
            label = row["label"] if row["attack_family"] in PAYLOAD_FAMILIES | {"benign"} else None
            group = row["group_key"]
            role = "calibration" if row["split"] == "val" and group in calibration else row["split"]
            yield {
                "event_key": row["event_key"],
                "source_id": source_id,
                "group_key": group,
                "split": role,
                "label": label,
                "evaluation_label": row["label"],
                "attack_family": row["attack_family"],
                "timestamp": row["timestamp"],
                "numbers": view["numbers"],
                "visibility": "request_payload_only; behavior/agent families unobservable",
            }


def public_training_rows(csic, pkdd, identity_key):
    """Only published training files. Original test data never enters fitting."""
    with Path(csic).open("rb") as stream:
        file_hash = file_sha256(csic)
        for index, row in enumerate(read_http(stream, identity_key, projector=project_request)):
            group = digest(row["numbers"])
            yield {
                **row,
                "event_key": hmac.new(
                    identity_key, f"csic-record:{file_hash}:{index}".encode(), hashlib.sha256
                ).hexdigest(),
                "source_id": "csic-published-normal-training",
                "split": public_role(group),
                "group_key": group,
                "label": 0,
                "evaluation_label": 0,
                "attack_family": "benign",
                "visibility": "publisher_normal; body excluded",
            }
    for row in read_pkdd(pkdd, identity_key):
        yield {**row, "source_id": "pkdd-mirror-training", "split": public_role(row["group_key"])}


def assemble_requests(records, output, provenance):
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix=".request-corpus-", dir=output.parent) as temporary:
        work = Path(temporary)
        db = sqlite3.connect(work / "index.sqlite")
        db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE r(id TEXT PRIMARY KEY,p TEXT,s TEXT,g TEXT,y INTEGER,e INTEGER,f TEXT,n TEXT,t REAL,v TEXT,k TEXT);
            CREATE INDEX rp ON r(p); CREATE INDEX rg ON r(g); CREATE INDEX rk ON r(k);""")
        counts, distributions = Counter(), Counter()
        for r in records:
            role = r.get("split")
            if role not in PARTS or r.get("label") not in (None, 0, 1):
                raise PipelineError("Unknown request-corpus partition/label")
            validate_numbers(r["numbers"])
            feature_key = digest(r["numbers"])
            try:
                db.execute(
                    "INSERT INTO r VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        r["event_key"],
                        role,
                        r["source_id"],
                        r["group_key"],
                        r.get("label"),
                        r.get("evaluation_label", r.get("label")),
                        r.get("attack_family"),
                        json.dumps(r["numbers"], sort_keys=True),
                        r.get("timestamp"),
                        r.get("visibility", "unknown"),
                        feature_key,
                    ),
                )
            except sqlite3.IntegrityError:
                raise PipelineError("Duplicate physical request/record identity") from None
            counts[role] += 1
            distributions[(r["source_id"], role, str(r.get("label")))] += 1
            if sum(counts.values()) % 4096 == 0:
                db.commit()
        db.commit()
        if any(not counts[p] for p in PARTS[:3]):
            raise PipelineError("Need nonempty train/calibration/validation partitions")
        collisions = db.execute(
            "SELECT count(*) FROM (SELECT k FROM r WHERE p!='reference' GROUP BY k HAVING count(DISTINCT p)>1)"
        ).fetchone()[0]
        # Stable train-only fit, never access test/reference labels for fitting.
        fitted = fit_spec(
            (
                json.loads(r[0])
                for r in db.execute("SELECT n FROM r WHERE p='train' AND y=0 ORDER BY id")
            ),
            columns(),
        )
        spec = {
            k: fitted[k]
            for k in (
                "columns",
                "mean",
                "std",
                "imputation",
                "raw_clip",
                "clip",
                "dtype",
                "fit_rows",
                "fit_partition",
            )
        }
        spec.update(
            profile=PROFILE,
            feature_version=PROFILE,
            fit_labels="benign_only",
            implementation_sha256=fingerprint(),
            input_contract="bounded ephemeral URI + actual HTTP method; not a fused v5 event",
            excluded="all actor/status/flow/time/UA/source/rule fields",
            temporal_features=False,
        )
        atomic_json(work / "feature_spec.json", spec)

        def rows():
            for (
                identity,
                part,
                source,
                group,
                label,
                evaluation,
                family,
                numbers,
                timestamp,
                visibility,
                key,
            ) in db.execute("SELECT * FROM r ORDER BY p,id"):
                yield {
                    "event_key": identity,
                    "source_id": source,
                    "group_key": group,
                    "split": part,
                    "label": label,
                    "evaluation_label": evaluation,
                    "attack_family": family,
                    "timestamp": timestamp,
                    "visibility": visibility,
                    "numeric_json": numbers,
                    "feature_key": key,
                }

        write_rows(work / "requests.parquet", rows(), SCHEMA)
        fschema = pa.schema(list(SCHEMA) + [("x", pa.list_(pa.float32(), len(spec["columns"])))])
        write_rows(
            work / "features.parquet",
            ({**r, "x": transform(spec, json.loads(r["numeric_json"])).tolist()} for r in rows()),
            fschema,
        )
        unique = db.execute(
            "SELECT count(DISTINCT k) FROM r WHERE p='train' AND y IS NOT NULL"
        ).fetchone()[0]
        db.close()
        (work / "index.sqlite").unlink()
        result = {
            "format_version": 1,
            "profile": PROFILE,
            "rows": dict(counts),
            "feature_count": len(spec["columns"]),
            "source_partition_labels": [
                {"source": s, "split": p, "label": y, "rows": n}
                for (s, p, y), n in sorted(distributions.items())
            ],
            "unique_training_views": unique,
            "cross_partition_vector_collision_groups": collisions,
            "fit_train_benign_only": True,
            "formal_training_permitted": False,
            "champion_selected": False,
            "provenance": provenance,
            "files": {
                f: file_sha256(work / f)
                for f in ("requests.parquet", "features.parquet", "feature_spec.json")
            },
            "limitations": [
                "Group splits on public data have no invented timestamps or temporal independence",
                "Full-profile v5 actors/flows/roles remain a different task",
                "Mirror labels are publisher annotations, not independent human realism/visibility review",
                "Exact view collisions are reported; no held-out hard cases removed",
                "Scale admission and production acceptance are separate and not granted",
            ],
        }
        result["dataset_sha256"] = digest(result)
        atomic_json(work / "manifest.json", result)
        os.replace(work, output)
    return result


def verify_requests(directory):
    directory = Path(directory)
    r = load_json(directory / "manifest.json")
    expected = r.pop("dataset_sha256", None)
    if digest(r) != expected or r.get("profile") != PROFILE:
        raise PipelineError("Request dataset manifest/profile integrity mismatch")
    for f, sha in r["files"].items():
        if (
            f not in ("requests.parquet", "features.parquet", "feature_spec.json")
            or (directory / f).is_symlink()
            or file_sha256(directory / f) != sha
        ):
            raise PipelineError("Request dataset shard integrity mismatch")
    if load_json(directory / "feature_spec.json")["implementation_sha256"] != fingerprint():
        raise PipelineError("Request feature implementation differs from dataset")
    return dict(r, dataset_sha256=expected)


def prepare_request_registry(registry, output):
    import yaml

    config = yaml.safe_load(Path(registry).read_text())
    if config.get("format_version") != 1:
        raise PipelineError("Versioned request source registry required")
    hashes = {
        "csic_training": "d3344377d4721b03b906ca232ab44bfd81b9c1356f967ec9d348532ec420f000",
        "pkdd_training": "b4e85e85a315eb522f5175e11ed0d35d0e0aab5cd41c4618102b624772692a86",
    }
    for name, expected in hashes.items():
        if file_sha256(config[name]) != expected:
            raise PipelineError("Public training shard differs from verified publisher split")
    key = Path(config["public_identity_key"]).read_bytes()
    lab = config["lab"]
    labkey = Path(lab["redaction_key"]).read_bytes()
    if len(key) < 32:
        raise PipelineError("Independent public-data identity key is required")
    decoder = load_json(Path(lab["eve"]).parent / "decode-manifest.json")
    if (
        decoder.get("input_profile") != PROFILE
        or decoder.get("request_structure_implementation_sha256") != fingerprint()
        or decoder["eve_sha256"] != file_sha256(lab["eve"])
    ):
        raise PipelineError("Request EVE decoder/projection binding mismatch")

    def records():
        yield from lab_rows(lab["eve"], lab["prepared"], labkey)
        yield from public_training_rows(config["csic_training"], config["pkdd_training"], key)

    return assemble_requests(
        records(),
        output,
        {
            "registry_sha256": file_sha256(registry),
            "verified_public_training_shards": hashes,
            "lab_pcap_sha256": decoder["pcap_sha256"],
            "decoder_manifest_sha256": file_sha256(
                Path(lab["eve"]).parent / "decode-manifest.json"
            ),
            "public_positive_training_sources": 0,
            "supervised_sources": ["student-lab"],
            "public_use": "benign-only AE and train-benign common scaler; no source-ID positive shortcut",
            "scale_admission": False,
        },
    )
