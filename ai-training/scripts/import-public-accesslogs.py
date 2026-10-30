#!/usr/bin/env python3
"""Bounded public real-accesslog sample. Unknown is NEVER silently benign.

Streams a prefix from the CC0 OpenCitations archive without saving/extracting
raw CSV, tokens, referers or query strings. This sample is for observability and
label/shift review, not supervised fitting or benign-only anomaly training.
"""

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, file_sha256
from idps_ai.data.dataset import write_rows
from idps_ai.data.privacy import METHODS, safe_agent, safe_route
from idps_ai.data.query_numeric import project_query
from idps_ai.data.snapshot import new_destination
from idps_ai.training.resources import resource_envelope

RECORD = "https://zenodo.org/api/records/20289873"
ARCHIVE = "oc-botwatch-logs-2026-jan-apr.tar.gz"
SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("timestamp", pa.float64()),
        ("client_key", pa.string()),
        ("http_method", pa.string()),
        ("uri_path", pa.string()),
        ("status_code", pa.int16()),
        ("user_agent", pa.string()),
        ("numeric_json", pa.string()),
        ("label", pa.int8()),
        ("label_source", pa.string()),
    ]
)


class BudgetReader:
    def __init__(self, stream):
        self.stream, self.count, self.hash, self.start = (
            stream,
            0,
            hashlib.sha256(),
            time.monotonic(),
        )

    def read(self, size=-1):
        if size < 0 or size > 1024**2 or time.monotonic() - self.start > 180:
            raise PipelineError("Accesslog stream read/time budget exceeded")
        if self.count + size > 64 * 1024**2:
            raise PipelineError("Accesslog compressed-prefix budget exceeded")
        value = self.stream.read(size)
        self.count += len(value)
        self.hash.update(value)
        return value


class ForwardOnly(io.RawIOBase):
    """Python3.12 tar adapter: never seeks in a streamed archive member."""

    def __init__(self, stream):
        self.stream = stream

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.stream.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def run(output, max_requests, fixture=None):
    if not 1 <= max_requests <= 100_000:
        raise PipelineError("Public observability sample limited to1–100000 rows")
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix=".public-accesslogs-", dir=output.parent) as temporary:
        work = Path(temporary)
        key = os.urandom(32)
        (work / "identity.key").write_bytes(key)
        (work / "identity.key").chmod(0o600)
        if fixture:
            metadata = {"id": "synthetic-test-fixture"}
            source = Path(fixture).open("rb")
        else:
            with urllib.request.urlopen(RECORD, timeout=30) as response:
                payload = response.read(1024**2 + 1)
            if len(payload) > 1024**2:
                raise PipelineError("Public accesslog metadata exceeds bound")
            metadata = json.loads(payload)
            if (
                metadata["metadata"].get("license", {}).get("id") != "cc-zero"
                or metadata["metadata"].get("access_right") != "open"
            ):
                raise PipelineError("Public accesslog license/access requires review")
            files = [f for f in metadata["files"] if f["key"] == ARCHIVE]
            if len(files) != 1 or files[0]["checksum"] != "md5:7ee5c87798cbb14f93f39e54b01ef0e6":
                raise PipelineError("Public archive version changed")
            source = urllib.request.urlopen(files[0]["links"]["self"], timeout=30)
        atomic_json(work / "source-metadata.json", metadata)
        db = sqlite3.connect(work / "identities.sqlite")
        db.execute("CREATE TABLE ids(id TEXT PRIMARY KEY)")
        stats, methods, statuses, clients = Counter(), Counter(), Counter(), set()
        bounds, members = [], []
        budget = BudgetReader(source)
        old_limit = csv.field_size_limit(65536)

        def opaque(purpose, value):
            return hmac.new(key, (purpose + ":" + value).encode(), hashlib.sha256).hexdigest()

        def rows():
            with source, tarfile.open(fileobj=budget, mode="r|gz") as archive:
                for member in archive:
                    if not member.isfile() or not member.name.endswith(".csv"):
                        continue
                    # No extract()/extractall(): names can never write outside the snapshot.
                    members.append({"name": Path(member.name).name, "declared_bytes": member.size})
                    with io.TextIOWrapper(
                        io.BufferedReader(ForwardOnly(archive.extractfile(member))),
                        encoding="utf-8",
                        errors="strict",
                        newline="",
                    ) as stream:
                        reader = csv.DictReader(stream)
                        required = {
                            "hashed_ip",
                            "request_method",
                            "request_path",
                            "http_response_code",
                            "user_agent",
                            "date",
                        }
                        if not required <= set(reader.fieldnames or []):
                            raise PipelineError("Unknown public accesslog CSV schema")
                        for row in reader:
                            if stats["source_rows"] >= max_requests:
                                return
                            stats["source_rows"] += 1
                            try:
                                if None in row or any(row[k] is None for k in required):
                                    raise ValueError
                                instant = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
                                if instant.tzinfo is None:
                                    raise ValueError
                                timestamp = instant.timestamp()
                                url = row["request_path"]
                                numbers = project_query(url, version=2)["numbers"]
                                status = int(row["http_response_code"])
                                if not 100 <= status <= 599:
                                    raise ValueError
                            except (ValueError, OverflowError):
                                stats["invalid_rows"] += 1
                                continue
                            identity = opaque(
                                "request",
                                json.dumps(
                                    [
                                        row[k]
                                        for k in (
                                            "date",
                                            "hashed_ip",
                                            "request_method",
                                            "request_path",
                                            "http_response_code",
                                            "user_agent",
                                        )
                                    ],
                                    separators=(",", ":"),
                                ),
                            )
                            try:
                                db.execute("INSERT INTO ids VALUES(?)", (identity,))
                            except sqlite3.IntegrityError:
                                stats["duplicate_rows"] += 1
                                continue
                            client = (
                                opaque("client", row["hashed_ip"]) if row["hashed_ip"] else None
                            )
                            clients.add(client)
                            method = (
                                row["request_method"]
                                if row["request_method"] in METHODS
                                else "OTHER"
                            )
                            methods[method] += 1
                            statuses[str(status // 100) + "xx"] += 1
                            bounds.append(timestamp)
                            yield {
                                "event_key": identity,
                                "timestamp": timestamp,
                                "client_key": client,
                                "http_method": method,
                                "uri_path": safe_route(urlsplit(url).path),
                                "status_code": status,
                                "user_agent": safe_agent(row["user_agent"]),
                                "numeric_json": json.dumps(numbers, sort_keys=True),
                                "label": None,
                                "label_source": "unreviewed_public_accesslog",
                            }

        try:
            count = write_rows(work / "requests.parquet", rows(), SCHEMA)
        finally:
            csv.field_size_limit(old_limit)
            db.close()
        (work / "identities.sqlite").unlink()
        result = {
            "format_version": 1,
            "profile": "public-accesslog-partial-v1",
            "data_kind": "synthetic_fixture" if fixture else "public_unlabeled_real_accesslog",
            "doi": "10.5281/zenodo.20289873" if not fixture else None,
            "license": "CC0-1.0" if not fixture else "test fixture",
            "source_rows": stats["source_rows"],
            "unique_observations": count,
            "duplicate_rows": stats["duplicate_rows"],
            "invalid_rows": stats["invalid_rows"],
            "unique_clients": len(clients - {None}),
            "methods": dict(methods),
            "statuses": dict(statuses),
            "timestamp_min": min(bounds, default=None),
            "timestamp_max": max(bounds, default=None),
            "members": members,
            "compressed_prefix_bytes": budget.count,
            "compressed_prefix_sha256": budget.hash.hexdigest(),
            "full_archive_checksum_verified": False,
            "requests_sha256": file_sha256(work / "requests.parquet"),
            "metadata_sha256": file_sha256(work / "source-metadata.json"),
            "supervised_eligible_requests": 0,
            "benign_only_training_eligible_requests": 0,
            "formal_training_permitted": False,
            "limits": [
                "No normal/attack labels; do not infer benign from status200 or missing alerts",
                "A chronological prefix of one service/month is not representative of four months",
                "Archive prefix was streamed over HTTPS; full3.6GB publisher checksum NOT verified",
                "No body, role, latency or flow is available; never synthesize them",
                "Tokens/referers/raw URI/query/IP hashes are discarded before writing",
                "Actual recorded timestamps are retained; source client hashes are HMAC pseudonymized again",
            ],
        }
        atomic_json(work / "manifest.json", result)
        os.replace(work, output)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-requests", type=int, default=100_000)
    parser.add_argument(
        "--fixture", help="Local test archive; always marked synthetic, never admitted"
    )
    args = parser.parse_args()
    with resource_envelope(2, 12):
        print(json.dumps(run(args.output, args.max_requests, args.fixture), sort_keys=True))
