"""Evidence-bound label attestations; integrity is not proof of semantic truth.

Reviewers must supply real evidence. This module never produces labels from
detectors, model scores, response codes, temporal proximity, or missing matches.
An attack attempt may fail; exploit outcome is a separate, optional assertion.
"""

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from idps_ai.common import CLASSES, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.http_curation import require_development_source
from idps_ai.data.snapshot import new_destination

HEX = re.compile(r"[0-9a-f]{64}")
SLUG = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
KINDS = {
    "request_capture",
    "intent_provenance",
    "independent_semantic_review",
    "application_oracle",
}


def _local_file(base, relative):
    if not isinstance(relative, str):
        raise PipelineError("Evidence path must be relative")
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts):
        raise PipelineError("Evidence path must stay inside the review directory")
    candidate = base / path
    if any(p.is_symlink() for p in (candidate, *candidate.parents)):
        raise PipelineError("Evidence symlinks are forbidden")
    require_development_source(candidate)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(base.resolve()):
        raise PipelineError("Missing or escaped review evidence")
    return candidate


def iter_evidence_decisions(review_path, dataset_sha256, provenance_sha256, environment_id):
    """Validate typed evidence and yield decisions, including unresolved rows.

    A reviewer attests that each referenced artifact supports the *particular*
    request. Hashes protect that attestation, not the reviewer's honesty or skill.
    Callers must additionally bind event keys and labels to actual dataset rows.
    """
    review_path = Path(review_path).resolve()
    require_development_source(review_path)
    if not HEX.fullmatch(str(dataset_sha256)) or not HEX.fullmatch(str(provenance_sha256)):
        raise PipelineError("Review requires dataset and provenance SHA256")
    review = load_json(review_path)
    checksum = review.pop("review_sha256", None)
    if (
        digest(review) != checksum
        or review.get("format_version") != 2
        or review.get("scope") != "label_protocol_and_environment_realism"
        or review.get("dataset_sha256") != dataset_sha256
        or review.get("provenance_sha256") != provenance_sha256
        or review.get("environment_id") != environment_id
        or review.get("approved") is not True
        or review.get("independent_review") is not True
        or review.get("review_kind") != "independent_human"
        or not SLUG.fullmatch(str(review.get("reviewer_id", "")))
        or not SLUG.fullmatch(str(review.get("collector_id", "")))
        or review["reviewer_id"] == review["collector_id"]
    ):
        raise PipelineError("Invalid independent evidence review binding or attestation")
    ledger = _local_file(review_path.parent, review.get("decisions_file"))
    if file_sha256(ledger) != review.get("decisions_sha256"):
        raise PipelineError("Label decision ledger checksum mismatch")
    cache = {}
    with ledger.open("rb") as stream:
        for index in range(2_000_001):
            line = stream.readline(65537)
            if not line:
                break
            if index == 2_000_000 or len(line) > 65536:
                raise PipelineError("Label review row or line budget exceeded")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid label decision JSON; raw content omitted") from None
            if not isinstance(row, dict) or not HEX.fullmatch(str(row.get("event_key", ""))):
                raise PipelineError("Label decision requires an immutable event key")
            intent = row.get("intent", "unknown")
            status = row.get("review_status", "pending")
            outcome = row.get("exploit_outcome", "unknown")
            if (
                intent not in ("benign", "attack", "unknown")
                or status not in ("approved", "pending", "rejected")
                or outcome not in ("unknown", "succeeded", "failed", "not_applicable")
            ):
                raise PipelineError("Invalid label intent, review status or exploit outcome")
            eligible = status == "approved" and intent != "unknown"
            label = (1 if intent == "attack" else 0) if eligible else None
            family = row.get("attack_family")
            if (
                (row.get("label") is not None and type(row["label"]) is not int)
                or row.get("label") != label
                or family not in (*CLASSES, None)
                or (label == 0 and family != "benign")
                or (label == 1 and family == "benign")
                or (label is None and family is not None)
                or (intent != "attack" and outcome not in ("unknown", "not_applicable"))
            ):
                raise PipelineError("Unknown stays unknown; family, intent and outcome must agree")
            evidence = row.get("evidence", [])
            if not isinstance(evidence, list) or len(evidence) > 8:
                raise PipelineError("Invalid evidence list")
            kinds = set()
            artifacts = {}
            for item in evidence:
                if (
                    not isinstance(item, dict)
                    or item.get("kind") not in KINDS
                    or item.get("event_key") != row["event_key"]
                    or item.get("dataset_sha256") != dataset_sha256
                    or not HEX.fullmatch(str(item.get("sha256", "")))
                ):
                    raise PipelineError(
                        "Evidence must bind the request; detector hits are not truth"
                    )
                path = _local_file(review_path.parent, item.get("file"))
                identity = str(path)
                if identity not in cache:
                    if len(cache) >= 100000:
                        raise PipelineError("Too many evidence artifacts; shard the review")
                    cache[identity] = file_sha256(path)
                if cache[identity] != item["sha256"]:
                    raise PipelineError("Label evidence artifact checksum mismatch")
                kinds.add(item["kind"])
                artifacts.setdefault(item["kind"], set()).add(item["sha256"])
            if (
                eligible
                and not {"request_capture", "intent_provenance", "independent_semantic_review"}
                <= kinds
            ):
                raise PipelineError(
                    "Approved intent needs capture, provenance and semantic review evidence"
                )
            if eligible and not (
                artifacts["independent_semantic_review"] - artifacts["request_capture"]
            ):
                raise PipelineError(
                    "Independent semantic review needs evidence distinct from capture"
                )
            if outcome in ("succeeded", "failed") and "application_oracle" not in kinds:
                raise PipelineError("Exploit outcome requires application oracle evidence")
            yield {
                "event_key": row["event_key"],
                "label": label,
                "attack_family": family,
                "intent": intent,
                "exploit_outcome": outcome,
                "eligible": eligible,
            }


def audit_label_evidence(review_path, dataset, provenance_sha256, environment_id, output):
    """Read back actual rows; a reviewed representation is not a new request."""
    require_development_source(dataset)
    manifest = verify_dataset(dataset)
    output = new_destination(output)
    output.mkdir(mode=0o700)
    counts = Counter()
    db = sqlite3.connect(output / "decisions.sqlite")
    db.execute("PRAGMA cache_size=-8192")
    db.execute(
        "CREATE TABLE decisions(event TEXT PRIMARY KEY,y INTEGER,f TEXT,outcome TEXT,seen INT DEFAULT 0)"
    )
    try:
        for row in iter_evidence_decisions(
            review_path, manifest["dataset_sha256"], provenance_sha256, environment_id
        ):
            try:
                db.execute(
                    "INSERT INTO decisions(event,y,f,outcome) VALUES(?,?,?,?)",
                    (row["event_key"], row["label"], row["attack_family"], row["exploit_outcome"]),
                )
            except sqlite3.IntegrityError:
                raise PipelineError(
                    "Duplicate review event; observations cannot inflate requests"
                ) from None
            counts["decisions"] += 1
            counts["unresolved"] += row["label"] is None
            counts["intent_" + row["intent"]] += 1
            counts["outcome_" + row["exploit_outcome"]] += 1
        for row in iter_rows(Path(dataset) / "requests.parquet"):
            found = db.execute(
                "SELECT y,f,seen FROM decisions WHERE event=?", (row["event_key"],)
            ).fetchone()
            if found is None:
                counts["unreviewed_dataset_rows"] += 1
                continue
            if found[2]:
                raise PipelineError("Dataset repeats a reviewed event identity")
            if found[0] is not None and (found[0], found[1]) != (
                row["label"],
                row["attack_family"],
            ):
                raise PipelineError(
                    "Evidence decision conflicts with dataset label; no silent relabeling"
                )
            db.execute("UPDATE decisions SET seen=1 WHERE event=?", (row["event_key"],))
            counts["matched_review_rows"] += 1
            counts["reviewed_labeled_dataset_rows"] += found[0] is not None
        if db.execute("SELECT count(*) FROM decisions WHERE seen=0").fetchone()[0]:
            raise PipelineError("Evidence review contains requests outside the bound dataset")
        db.commit()
    finally:
        db.close()
    result = {
        "format_version": 2,
        "status": "EVIDENCE_INTEGRITY_VERIFIED_NOT_TRUTH_CERTIFIED",
        "dataset_sha256": manifest["dataset_sha256"],
        "provenance_sha256": provenance_sha256,
        "review_file_sha256": file_sha256(review_path),
        "counts": dict(counts),
        "index_sha256": file_sha256(output / "decisions.sqlite"),
        "formal_training_permitted": False,
        "limits": "Hash-bound human assertions require genuine independent reviewers and semantic audit. IDs alone do not authenticate people. This checks integrity and row binding, not truth, physical capture uniqueness, feature observability, independence or production readiness.",
    }
    atomic_json(output / "report.json", result)
    return result
