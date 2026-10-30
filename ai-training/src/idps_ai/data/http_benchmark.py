"""Raw public HTTP -> private numeric-only request-view benchmark.

This is deliberately NOT a canonical three-source capture. No timestamps,
actors, response status, flow, attack family or successful exploit are invented.
Publisher anomalous labels remain binary, including body/header-only attacks.
"""

import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, write_rows
from idps_ai.data.privacy import METHODS, PRODUCTS, safe_agent
from idps_ai.data.query_numeric import project_query
from idps_ai.data.snapshot import new_destination

PROFILE = "http-request-numeric-v1"
MAX_LINE = 65536
MAX_BODY = 1048576
SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("template_key", pa.string()),
        ("feature_key", pa.string()),
        ("source_id", pa.string()),
        ("split", pa.string()),
        ("label", pa.int8()),
        ("attack_family", pa.string()),
        ("label_source", pa.string()),
        ("body_present", pa.bool_()),
        ("numbers_json", pa.string()),
    ]
)


def fetch_public_http(output):
    """Bounded, pinned, restartable download. Never downloads aggregate TF-IDF."""
    import yaml

    from idps_ai.common import AI_ROOT

    registry_path = AI_ROOT / "configs/public_http_sources.yaml"
    registry = yaml.safe_load(registry_path.read_text())
    output = Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    expected_files = {f["filename"] for f in registry["files"]}
    if any(
        p.name not in expected_files | {"metadata.json", "registry.yaml", "fetch-manifest.json"}
        for p in output.iterdir()
    ):
        raise PipelineError("Download destination contains unrelated files")
    with urllib.request.urlopen(registry["metadata_api"], timeout=30) as response:
        payload = response.read(4 * 1024**2 + 1)
    if len(payload) > 4 * 1024**2:
        raise PipelineError("Public metadata exceeds size bound")
    value = json.loads(payload)["data"]["latestVersion"]
    if (
        value.get("versionNumber") != registry["version"]
        or value.get("license", {}).get("name") != registry["repository_license"]
    ):
        raise PipelineError("Public version/license changed; review required")
    entries = []
    remote = {r["dataFile"]["id"]: r["dataFile"] for r in value["files"]}
    for f in registry["files"]:
        declared = remote.get(f["id"], {})
        if (
            declared.get("filename") != f["filename"]
            or declared.get("filesize") != f["bytes"]
            or not 0 < f["bytes"] <= 32 * 1024**2
        ):
            raise PipelineError("Public file metadata no longer matches pinned source")
        target = output / f["filename"]
        if target.is_symlink():
            raise PipelineError("Download target cannot be a symlink")
        if not target.exists() or file_sha256(target) != f["sha256"]:
            with tempfile.NamedTemporaryFile(dir=output.parent) as temporary:
                with urllib.request.urlopen(
                    registry["repository"] + "/api/access/datafile/" + str(f["id"]), timeout=60
                ) as response:
                    count = 0
                    while block := response.read(1024**2):
                        count += len(block)
                        if count > f["bytes"]:
                            raise PipelineError("Public download exceeds pinned size")
                        temporary.write(block)
                temporary.flush()
                os.fsync(temporary.fileno())
                if count != f["bytes"] or file_sha256(temporary.name) != f["sha256"]:
                    raise PipelineError("Public download checksum mismatch")
                # An interrupted copy is rejected by the checksum on restart/import.
                import shutil

                shutil.copyfile(temporary.name, target)
                target.chmod(0o600)
        target.chmod(0o600)
        entries.append(
            {
                "file": str(target),
                "sha256": f["sha256"],
                "source_id": f["filename"].removesuffix(".txt"),
                "partition": f["partition"],
                "label": f["label"],
            }
        )
    atomic_json(output / "metadata.json", json.loads(payload))
    local = {
        "provenance": {
            "doi": registry["doi"],
            "license": registry["repository_license"],
            "attribution": registry["attribution"],
            "limitations": registry["limitations"],
        },
        "sources": entries,
    }
    (output / "registry.yaml").write_text(yaml.safe_dump(local))
    (output / "registry.yaml").chmod(0o600)
    report = {
        "registry_sha256": file_sha256(registry_path),
        "metadata_sha256": file_sha256(output / "metadata.json"),
        "license": registry["repository_license"],
        "doi": registry["doi"],
        "files": entries,
    }
    atomic_json(output / "fetch-manifest.json", report)
    return report


def request_view(numbers, method, agent):
    """Same privacy projection as EVE v2; only actually observed static fields."""
    result = dict(numbers)
    result.update({"method_" + m: float(method == m) for m in METHODS})
    products = set((safe_agent(agent) or "").split())
    result.update({"ua_" + p: float(p in products) for p in PRODUCTS})
    result["user_agent_missing"] = float(not agent)
    result["user_agent_unknown"] = float(bool(agent) and not products - {"[REDACTED]"})
    return result


def read_http(stream, identity_key=None, projector=None):
    """Bounded HTTP transcript reader. Bodies are consumed, never returned.

    Header secrets are never retained. HMACs permit duplicate auditing without
    persisting raw targets or body values. Caller supplies one private key for
    all source shards. Chunked transcripts must use a separate reviewed adapter.
    """
    identity_key = identity_key or os.urandom(32)
    while True:
        line = stream.readline(MAX_LINE + 1)
        if not line:
            return
        if len(line) > MAX_LINE:
            raise PipelineError("HTTP request line exceeds bounded input")
        if not line.strip():
            continue
        match = re.fullmatch(
            rb"([!#$%&'*+.^_`|~0-9A-Za-z-]{1,24}) (.{1,8192}) HTTP/\d\.\d\r?\n", line
        )
        if not match:
            raise PipelineError("Malformed HTTP request line; raw record omitted")
        method, target = match.group(1).decode("ascii"), match.group(2).decode("latin-1")
        agent, length = None, None
        for _ in range(128):
            header = stream.readline(MAX_LINE + 1)
            if not header or len(header) > MAX_LINE:
                raise PipelineError("Truncated or oversized HTTP headers")
            if not header.strip():
                break
            name, colon, value = header.partition(b":")
            if not colon:
                raise PipelineError("Malformed HTTP header; raw record omitted")
            name = name.lower()
            if name == b"user-agent":
                agent = value.strip().decode("latin-1")[:4096]
            if name == b"transfer-encoding":
                raise PipelineError("Transfer-encoded HTTP transcript needs reviewed decoding")
            if name == b"content-length":
                try:
                    size = int(value.strip())
                except ValueError:
                    raise PipelineError("Invalid HTTP body length") from None
                if length is not None and size != length or not 0 <= size <= MAX_BODY:
                    raise PipelineError("Conflicting or unbounded HTTP body length")
                length = size
        else:
            raise PipelineError("HTTP header count exceeds bounded input")
        body = stream.read(length or 0)
        if len(body) != (length or 0):
            raise PipelineError("Truncated HTTP body")
        try:
            numbers = (
                projector(target, method, agent)["numbers"]
                if projector
                else request_view(
                    project_query(target, version=2)["numbers"],
                    method if method in METHODS else "OTHER",
                    agent,
                )
            )
        except (ValueError, UnicodeError):
            raise PipelineError("Invalid HTTP numeric projection; raw record omitted") from None
        # Identity excludes cookies/host/authorization, which are unavailable to the model.
        decoded = unquote(unquote(target.replace("+", " ")))
        identity = method.encode() + b" " + decoded.encode("utf-8") + b"\x00" + body
        template = re.sub(r"\b\d+\b", "#", decoded.lower())
        yield {
            "event_key": hmac.new(identity_key, identity, hashlib.sha256).hexdigest(),
            "template_key": hmac.new(
                identity_key, (method + " " + template).encode(), hashlib.sha256
            ).hexdigest(),
            "feature_key": digest(numbers),
            "numbers": numbers,
            "body_present": bool(body),
        }


def import_http(entries, output, provenance):
    """Immutable, disk-backed import with cross-role duplicate quarantine.

    Whole raw payload and numeric-vector collisions across roles/labels are
    removed from every role, so a benchmark cannot reward exact view memorization.
    Near-template overlaps are reported separately; not proof of independence.
    """
    if (
        not provenance.get("doi")
        or provenance.get("license") != "CC BY 4.0"
        or not provenance.get("attribution")
    ):
        raise PipelineError("Explicit reviewed source provenance, license and attribution required")
    output = new_destination(output)
    files, hashes = [], set()
    for entry in entries:
        path = Path(entry["file"])
        actual = file_sha256(path)
        if actual != entry.get("sha256"):
            raise PipelineError("Public source checksum mismatch")
        if (
            actual in hashes
            or entry.get("partition") not in ("train", "test")
            or entry.get("label") not in (0, 1)
        ):
            raise PipelineError("Duplicate source or invalid original partition/binary annotation")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", entry.get("source_id", "")):
            raise PipelineError("Invalid public source identifier")
        hashes.add(actual)
        files.append({k: entry[k] for k in ("source_id", "sha256", "partition", "label")})
    with tempfile.TemporaryDirectory(prefix=".http-import-", dir=output.parent) as temporary:
        work = Path(temporary)
        key = os.urandom(32)
        (work / "identity.key").write_bytes(key)
        (work / "identity.key").chmod(0o600)
        db = sqlite3.connect(work / "scratch.sqlite")
        db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE r(id TEXT,t TEXT,f TEXT,p TEXT,y INTEGER,s TEXT,b INTEGER,n TEXT);
            CREATE INDEX rid ON r(id); CREATE INDEX fid ON r(f); CREATE INDEX tid ON r(t);
        """)
        total = 0
        for entry in entries:
            with Path(entry["file"]).open("rb") as stream:
                for r in read_http(stream, key):
                    db.execute(
                        "INSERT INTO r VALUES(?,?,?,?,?,?,?,?)",
                        (
                            r["event_key"],
                            r["template_key"],
                            r["feature_key"],
                            entry["partition"],
                            entry["label"],
                            entry["source_id"],
                            int(r["body_present"]),
                            json.dumps(r["numbers"], sort_keys=True),
                        ),
                    )
                    total += 1
                    if total % 4096 == 0:
                        db.commit()
        db.commit()

        def original_rows():
            for identity, template, feature, split, label, source, body, numbers in db.execute(
                "SELECT * FROM r ORDER BY rowid"
            ):
                yield {
                    "event_key": identity,
                    "template_key": template,
                    "feature_key": feature,
                    "source_id": source,
                    "split": split,
                    "label": label,
                    "attack_family": "benign" if label == 0 else None,
                    "label_source": "publisher_binary_annotation",
                    "body_present": bool(body),
                    "numbers_json": numbers,
                }

        write_rows(work / "original-requests.parquet", original_rows(), SCHEMA)
        db.executescript("""CREATE TABLE bad_id AS SELECT id FROM r GROUP BY id
            HAVING count(DISTINCT p)>1 OR count(DISTINCT y)>1;
            CREATE UNIQUE INDEX bad_i ON bad_id(id);
            CREATE TABLE bad_f AS SELECT f FROM r GROUP BY f
            HAVING count(DISTINCT p)>1 OR count(DISTINCT y)>1;
            CREATE UNIQUE INDEX bad_v ON bad_f(f);
        """)
        exact = db.execute("SELECT count(*) FROM r JOIN bad_id USING(id)").fetchone()[0]
        vector = db.execute("SELECT count(*) FROM r JOIN bad_f USING(f)").fetchone()[0]
        near = db.execute(
            "SELECT count(*) FROM (SELECT t FROM r GROUP BY t HAVING count(DISTINCT p)>1)"
        ).fetchone()[0]
        counts = Counter()

        def rows():
            sql = """SELECT id,t,f,p,y,s,max(b),n FROM r
                WHERE id NOT IN (SELECT id FROM bad_id) AND f NOT IN (SELECT f FROM bad_f)
                GROUP BY id ORDER BY p,id"""
            for identity, template, feature, split, label, source, body, numbers in db.execute(sql):
                counts[split] += 1
                yield {
                    "event_key": identity,
                    "template_key": template,
                    "feature_key": feature,
                    "source_id": source,
                    "split": split,
                    "label": label,
                    "attack_family": "benign" if label == 0 else None,
                    "label_source": "publisher_binary_annotation",
                    "body_present": bool(body),
                    "numbers_json": numbers,
                }

        retained = write_rows(work / "requests.parquet", rows(), SCHEMA)
        db.close()
        (work / "scratch.sqlite").unlink()
        report = {
            "format_version": 1,
            "profile": PROFILE,
            "provenance": provenance,
            "source_files": files,
            "raw_requests": total,
            "retained_unique_requests": retained,
            "partitions": dict(counts),
            "cross_partition_duplicate_rows": exact,
            "cross_partition_or_label_vector_collision_rows": vector,
            "near_template_cross_partition_groups": near,
            "missing_fields": [
                "timestamp",
                "client",
                "session",
                "role",
                "status",
                "latency",
                "flow",
            ],
            "full_three_source_eligible": False,
            "independent_human_review": False,
            "attack_visibility": "Binary anomalous requests can have body/header-only attacks invisible to this URI view; never infer families with rules",
            "raw_source_sha256_verified": True,
            "requests_sha256": file_sha256(work / "requests.parquet"),
            "original_requests_sha256": file_sha256(work / "original-requests.parquet"),
            "evaluation_policy": "Full original test is the primary challenge. Curated deduplicated subset is a sensitivity diagnostic, never a substitute for ambiguous/body-only attacks.",
            "identity_key_sha256": file_sha256(work / "identity.key"),
            "formal_training_permitted": False,
        }
        atomic_json(work / "manifest.json", report)
        os.replace(work, output)
    return report


def iter_benchmark(directory, original=False):
    directory = Path(directory)
    value = load_json(directory / "manifest.json")
    name = "original-requests.parquet" if original else "requests.parquet"
    expected = value["original_requests_sha256"] if original else value["requests_sha256"]
    if value.get("profile") != PROFILE or file_sha256(directory / name) != expected:
        raise PipelineError("Public benchmark integrity/profile mismatch")
    yield from iter_rows(directory / name)
