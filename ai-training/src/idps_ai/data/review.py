"""Bounded redacted review queues. Unknown stays unknown; detector hits are not labels."""

import csv
import json
import math
import os
import re
import tempfile
from pathlib import Path

from idps_ai.common import (
    CLASSES,
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    fsync_dir,
    load_json,
)
from idps_ai.data.dataset import iter_rows, load_labels, verify_dataset
from idps_ai.data.privacy import pseudonym
from idps_ai.data.snapshot import new_destination

CONTEXT = ("request_key", "timestamp", "http_method", "uri_path", "status_code", "role", "sources")
EDITABLE = ("attack_family", "campaign_id", "label_confidence", "review_status", "evidence_ref")
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


def export_review(dataset, output, offset=0, limit=1000):
    if offset < 0 or not 1 <= limit <= 5000:
        raise PipelineError("Review pages require nonnegative offset and limit <=5000")
    source = verify_dataset(dataset)
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix=".review-", dir=output.parent) as temporary:
        work = Path(temporary)
        contexts = {}
        skipped = eligible = 0
        with (work / "labels.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CONTEXT + EDITABLE)
            writer.writeheader()
            for row in iter_rows(Path(dataset) / "requests.parquet"):
                if not row["request_key"] or row["correlation"] == "ambiguous_request_id":
                    skipped += 1
                    continue
                eligible += 1
                if eligible <= offset:
                    continue
                if len(contexts) >= limit:
                    break
                context = {k: str(row.get(k) if row.get(k) is not None else "") for k in CONTEXT}
                context["sources"] = "|".join(row["sources"])
                if row["request_key"] in contexts:
                    raise PipelineError("Ambiguous request identity cannot be manually approved")
                contexts[row["request_key"]] = digest(context)
                writer.writerow(context | {k: "" for k in EDITABLE})
        os.chmod(work / "labels.csv", 0o600)
        result = {
            "format_version": 1,
            "dataset_sha256": source["dataset_sha256"],
            "offset": offset,
            "rows": len(contexts),
            "skipped_unidentifiable": skipped,
            "context_hashes": contexts,
            "editable_columns": list(EDITABLE),
            "semantics": "Fill only reviewed evidence; blank/pending remain unknown; no labels inferred from status/rule",
        }
        result["review_sha256"] = digest(result)
        atomic_json(work / "review_manifest.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result


def import_review(review_dir, dataset, output, key, reviewer):
    if not SLUG.fullmatch(reviewer):
        raise PipelineError("Reviewer must be a non-sensitive identifier")
    source = verify_dataset(dataset)
    if pseudonym(key, "fingerprint", "v1") != source["redaction_key_fingerprint"]:
        raise PipelineError("Review requires the same dataset HMAC key")
    review = load_json(Path(review_dir) / "review_manifest.json")
    expected = review.pop("review_sha256", None)
    if digest(review) != expected or review["dataset_sha256"] != source["dataset_sha256"]:
        raise PipelineError("Review manifest/dataset checksum mismatch")
    labels = []
    unknown = 0
    seen = set()
    with (Path(review_dir) / "labels.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CONTEXT + EDITABLE):
            raise PipelineError("Review CSV columns changed")
        for row in reader:
            rid = row["request_key"]
            if rid in seen or digest({k: row[k] for k in CONTEXT}) != review["context_hashes"].get(
                rid
            ):
                raise PipelineError("Review context changed or request duplicated")
            seen.add(rid)
            if row["review_status"] != "approved":
                unknown += 1
                continue
            if (
                row["attack_family"] not in CLASSES
                or not SLUG.fullmatch(row["campaign_id"])
                or not SLUG.fullmatch(row["evidence_ref"])
            ):
                raise PipelineError(
                    "Approved labels require family, campaign and evidence reference"
                )
            try:
                confidence = float(row["label_confidence"])
            except ValueError:
                raise PipelineError("Invalid label confidence") from None
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise PipelineError("Invalid label confidence")
            labels.append(
                {
                    "request_key": rid,
                    "campaign_id": row["campaign_id"],
                    "attack_family": row["attack_family"],
                    "label": int(row["attack_family"] != "benign"),
                    "label_source": "human_review",
                    "label_confidence": confidence,
                    "review_status": "approved",
                    "reviewer": reviewer,
                    "evidence_ref": row["evidence_ref"],
                }
            )
    if seen != set(review["context_hashes"]):
        raise PipelineError("Review rows missing")
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix=".labels-", dir=output.parent) as temporary:
        work = Path(temporary)
        with (work / "labels.jsonl").open("w") as stream:
            for label in labels:
                stream.write(json.dumps(label, sort_keys=True) + "\n")
        os.chmod(work / "labels.jsonl", 0o600)
        load_labels(work / "labels.jsonl", key)
        result = {
            "format_version": 1,
            "dataset_sha256": source["dataset_sha256"],
            "review_sha256": expected,
            "reviewer": reviewer,
            "approved_rows": len(labels),
            "unknown_rows": unknown,
            "labels_sha256": file_sha256(work / "labels.jsonl"),
        }
        atomic_json(work / "label_review.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result
