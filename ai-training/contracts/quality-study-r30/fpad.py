"""Verify the published FPAD TRAIN shard and test its request-target compatibility."""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "development-bulk-v1"))
from r16_waf import origin_view  # noqa: E402

BLOB = "0419804566d46c4ed0a79d348d7a4f4d202baef4"
SHA = "e450fd0a0de45e5ce29053b82573e703be5e30cf8e29f02a770fa27f60fef908"
SIZE = 11_435_138


def require(ok, reason):
    if not ok:
        raise PipelineError(reason)


def audit(run):
    directory = run / "fpad-directory.json"
    item = next(row for row in load_json(directory) if row["name"] == "train.jsonl")
    metadata = run / "fpad-record.json"
    rights = load_json(metadata)["metadata"]["license"]["id"]
    source = run / "fpad-train.jsonl"
    require(
        item["sha"] == BLOB
        and item["size"] == source.stat().st_size == SIZE
        and file_sha256(source) == SHA
        and rights == "mit-license",
        "FPAD_RELEASE_IDENTITY_MISMATCH",
    )
    blob = hashlib.sha1(f"blob {SIZE}\0".encode(), usedforsecurity=False)
    labels, normalized, body = Counter(), Counter(), Counter()
    representations = defaultdict(set)
    with source.open("rb") as stream:
        for raw in stream:
            blob.update(raw)
            row = json.loads(raw)
            require(
                set(row) == {"method", "url", "body", "label", "location"}
                and type(row["label"]) is int
                and row["label"] in range(5)
                and all(isinstance(row[k], str) for k in ("method", "url", "body")),
                "FPAD_TRAIN_RECORD_SCHEMA_MISMATCH",
            )
            group = "publisher_normal" if row["label"] == 0 else "publisher_attack"
            labels[row["label"]] += 1
            body[group] += bool(row["body"])
            url = origin_view(row["url"])
            if url is not None:
                normalized[group] += 1
            # Scope is exact publisher representations, never physical request identity.
            key = hashlib.sha256(
                json.dumps([row["method"], row["url"], row["body"]], separators=(",", ":")).encode()
            ).digest()
            representations[group].add(key)
    require(blob.hexdigest() == BLOB, "FPAD_GIT_BLOB_CHANGED")
    totals = {"publisher_normal": labels[0], "publisher_attack": sum(labels.values()) - labels[0]}
    require(
        all(totals.values())
        and normalized["publisher_normal"] == totals["publisher_normal"]
        and normalized["publisher_attack"] == 0,
        "FPAD_FORMAT_SHORTCUT_REVIEW_REQUIRED",
    )
    return {
        "version": "idps-r30-fpad-train-preflight-v1",
        "publisher": "https://github.com/Sec-AI-research/WebSpotter",
        "artifact_DOI": "10.5281/zenodo.16978408",
        "scope": "PUBLISHER_TRAIN_ONLY_METADATA_AND_TARGET_COMPATIBILITY",
        "observed_artifact_license": rights,
        "git_blob": BLOB,
        "data_sha256": SHA,
        "directory_metadata_sha256": file_sha256(directory),
        "artifact_metadata_sha256": file_sha256(metadata),
        "publisher_labels": {str(label): n for label, n in sorted(labels.items())},
        "class_totals": totals,
        "normalizable_request_target_by_class": {k: normalized[k] for k in totals},
        "nonempty_body_strings_by_class": dict(body),
        "body_type_and_capture_receipts_available": False,
        "exact_representations_by_class": {
            name: len(values) for name, values in representations.items()
        },
        "opposite_label_exact_representation_conflicts": len(
            representations["publisher_normal"] & representations["publisher_attack"]
        ),
        "decision": "EXCLUDE_TARGET_FORMAT_PERFECTLY_CONFOUNDED_WITH_PUBLISHER_CLASS",
        "protected_split_downloaded": False,
        "canonically_admitted": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    atomic_json(args.run / "fpad-census.json", audit(args.run))
