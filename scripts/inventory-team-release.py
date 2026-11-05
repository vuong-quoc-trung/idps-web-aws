#!/usr/bin/env python3
"""Private release inventory; never emits secret values or reads sealed content."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(root, output):
    root = Path(root).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    tracked = set(
        subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    )
    ignored = set(
        subprocess.check_output(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    artifacts = root / "ai-training/.artifacts"
    sealed_dirs = [p.parent for p in artifacts.rglob("AI_HOLDOUT.json")]
    sealed_terms = re.compile(r"(?:sealed|holdout|/reserved/)", re.IGNORECASE)
    secret_name = re.compile(
        r"(?:^|/)(?:\.env(?:\.|$)|credentials[^/]*\.json$|accounts-private|redaction\.key|hmac\.key)|\.(?:pem|key|p12|pfx)$",
        re.IGNORECASE,
    )
    cached = {}
    groups = defaultdict(lambda: Counter())
    rows = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for filename in files:
            p = Path(base) / filename
            name = str(p.relative_to(root))
            if p.is_symlink():
                continue
            st = p.stat()
            if not stat.S_ISREG(st.st_mode):
                continue
            entry = {
                "path": name,
                "bytes": st.st_size,
                "git": "tracked"
                if name in tracked
                else "ignored"
                if name in ignored
                else "untracked",
            }
            section = name.split("/")[0]
            groups[section]["files"] += 1
            groups[section]["logical_bytes"] += st.st_size
            is_artifact = p.is_relative_to(artifacts)
            sealed = bool(sealed_terms.search(name)) or any(
                p.is_relative_to(d) for d in sealed_dirs
            )
            if secret_name.search(name):
                category = "PRIVATE_AUTH_MATERIAL"
            elif sealed:
                category = "SEALED_CONTENT_NOT_READ"
            elif any(
                part
                in {
                    ".venv",
                    "venv",
                    "node_modules",
                    "target",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                }
                for part in p.parts
            ):
                category = "REBUILDABLE_ENV_OR_CACHE"
            elif (
                is_artifact
                and filename == "arrays.npz"
                and p.parent.name.startswith("step-")
            ):
                category = "MODEL_CHECKPOINT_CANDIDATE"
            elif is_artifact and p.suffix == ".onnx":
                category = "MODEL_ONNX_CANDIDATE"
            elif is_artifact and p.suffix in {
                ".log",
                ".pcap",
                ".pcapng",
                ".db",
                ".sqlite",
                ".csv",
                ".xlsx",
                ".jar",
                ".class",
            }:
                category = "RAW_EVIDENCE_OR_THIRDPARTY_RESTRICTED_UNTIL_REVIEW"
            elif is_artifact:
                category = "ARTIFACT_REQUIRES_CONTENT_REVIEW"
            elif name in tracked:
                category = "SOURCE_OR_CONFIG"
            else:
                category = "LOCAL_UNTRACKED_REVIEW"
            entry["classification"] = category
            # Hash research-state files for exact accounting. Original sealed
            # partitions and auth material are inventoried by metadata only.
            if (
                is_artifact
                and not sealed
                and category
                not in {"PRIVATE_AUTH_MATERIAL", "REBUILDABLE_ENV_OR_CACHE"}
            ):
                key = (st.st_dev, st.st_ino)
                if key not in cached:
                    cached[key] = sha(p)
                entry["sha256"] = cached[key]
            rows.append(entry)
    with (output / "private-inventory.jsonl").open("x") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    candidates = [
        r
        for r in rows
        if r["classification"] in {"MODEL_CHECKPOINT_CANDIDATE", "MODEL_ONNX_CANDIDATE"}
    ]
    dedup = {r["sha256"]: r["bytes"] for r in candidates}
    summary = {
        "status": "INVENTORY_COMPLETE_NOT_DISTRIBUTION_APPROVAL",
        "top_level": dict(groups),
        "classification_counts": dict(Counter(r["classification"] for r in rows)),
        "model_candidates": len(candidates),
        "model_candidate_logical_bytes": sum(r["bytes"] for r in candidates),
        "model_unique_content_bytes": sum(dedup.values()),
        "model_unique_objects": len(dedup),
        "sealed_content_read": False,
        "secret_values_in_report": False,
        "private_inventory_sha256": sha(output / "private-inventory.jsonl"),
    }
    (output / "inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--output", required=True)
    a = p.parse_args()
    main(a.root, a.output)
