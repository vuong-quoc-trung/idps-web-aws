"""Private immutable JSONL prefixes, with read-back checks and explicit provenance."""

import hashlib
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from idps_ai.common import (
    REPO_ROOT,
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    fsync_dir,
    load_json,
)

KINDS = ("lab_capture", "local_demo", "production_snapshot", "public_benchmark", "synthetic")
ADAPTERS = ("student", "nginx", "suricata", "canonical", "postgres-export")


def new_destination(output):
    output = Path(output).resolve()
    for service in ("student-web", "security-web", "contracts", ".github", "docker"):
        if output.is_relative_to(REPO_ROOT / service):
            raise PipelineError("AI output cannot be written inside a protected service/contract")
    if output.exists():
        raise PipelineError("Output exists; use a new immutable version")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output


def snapshot(inputs, output, data_kind, max_file_bytes=256 * 1024 * 1024):
    if data_kind not in KINDS or not 1 <= len(inputs) <= 64:
        raise PipelineError("Invalid snapshot kind or input count")
    output = new_destination(output)
    if any(Path(i.path).resolve().is_relative_to(output) for i in inputs):
        raise PipelineError("Snapshot inputs must be outside its destination")
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=output.parent) as temp:
        work = Path(temp)
        entries = []
        for index, item in enumerate(inputs):
            if item.source not in ADAPTERS or Path(item.path).is_symlink():
                raise PipelineError("Unsupported adapter or symlink source")
            descriptor = os.open(item.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size > max_file_bytes:
                    raise PipelineError("Snapshot requires bounded regular input files")
                target = work / f"{index:02d}-{item.source}.jsonl"
                captured = remaining = before.st_size
                prefix_hash = hashlib.sha256()
                last_newline = 0
                with target.open("wb") as dest:
                    os.chmod(target, 0o600)
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            raise PipelineError("Source truncated during snapshot")
                        prefix_hash.update(block)
                        dest.write(block)
                        newline = block.rfind(b"\n")
                        if newline >= 0:
                            last_newline = captured - remaining + newline + 1
                        remaining -= len(block)
                    dest.truncate(last_newline)
                    dest.flush()
                    os.fsync(dest.fileno())
                # Appends are allowed; any change to the frozen prefix is rejected.
                source.seek(0)
                verify_hash = hashlib.sha256()
                remaining = captured
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise PipelineError("Source changed during snapshot")
                    verify_hash.update(block)
                    remaining -= len(block)
                after = os.fstat(source.fileno())
                current = Path(item.path).stat()
                if (
                    (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                    or after.st_size < captured
                    or prefix_hash.digest() != verify_hash.digest()
                ):
                    raise PipelineError("Source rotated or changed during snapshot; retry")
                entries.append(
                    {
                        "source": item.source,
                        "file": target.name,
                        "sha256": file_sha256(target),
                        "bytes": last_newline,
                        "source_prefix_bytes": captured,
                        "discarded_tail_bytes": captured - last_newline,
                        "source_identity_sha256": digest(
                            [before.st_dev, before.st_ino, str(Path(item.path).resolve())]
                        ),
                        "append_during_capture": after.st_size > captured,
                    }
                )
        result = {
            "format_version": 1,
            "data_kind": data_kind,
            "started_at_utc": started,
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": entries,
            "semantics": "Independent complete-line prefixes, not a cross-source atomic transaction; no labels inferred",
        }
        result["snapshot_sha256"] = digest(result)
        atomic_json(work / "snapshot_manifest.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result


def verify_snapshot(directory):
    directory = Path(directory)
    result = load_json(directory / "snapshot_manifest.json")
    expected = result.pop("snapshot_sha256", None)
    if digest(result) != expected or result.get("data_kind") not in KINDS:
        raise PipelineError("Snapshot manifest checksum mismatch")
    for item in result["inputs"]:
        name = item["file"]
        if Path(name).name != name or not name.endswith(".jsonl"):
            raise PipelineError("Invalid snapshot file")
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != item["bytes"]
            or file_sha256(path) != item["sha256"]
        ):
            raise PipelineError("Snapshot file checksum mismatch")
    result["snapshot_sha256"] = expected
    return result
