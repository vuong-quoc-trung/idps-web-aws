"""Small safe serialization and integrity primitives; no pickle or service writes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AI_ROOT.parent
CLASSES = (
    "benign",
    "sqli",
    "xss",
    "path_traversal",
    "cmd_injection",
    "scanner_recon",
    "brute_force",
    "behavioral_anomaly",
)


class PipelineError(ValueError):
    """An actionable message which must never include raw log content/secrets."""


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_json(path):
    with Path(path).open() as stream:
        return json.load(stream)
