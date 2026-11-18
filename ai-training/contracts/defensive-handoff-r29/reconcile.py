"""Reconcile existing defensive evidence without opening payload or feature archives."""

import argparse
import gzip
import json
import sqlite3
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json

ARTIFACTS = REPO_ROOT / "ai-training/.artifacts"
CONTRACTS = REPO_ROOT / "ai-training/contracts"


def require(condition, reason):
    if not condition:
        raise PipelineError(reason)


def verify(path, expected, pins):
    actual = file_sha256(path)
    require(actual == expected, "HISTORICAL_INPUT_SHA_MISMATCH")
    pins[str(path.relative_to(REPO_ROOT))] = actual
    return path


def checked_report(path, pins):
    report = load_json(path)
    content = {key: value for key, value in report.items() if key != "report_sha256"}
    require(report["report_sha256"] == digest(content), "HISTORICAL_REPORT_CONTENT_SHA_MISMATCH")
    pins[str(path.relative_to(REPO_ROOT))] = file_sha256(path)
    return report


@contextmanager
def readonly_db(path):
    def snapshot():
        st = path.stat()
        require(
            not path.is_symlink()
            and not any(Path(str(path) + ext).exists() for ext in ("-wal", "-shm", "-journal")),
            "HISTORICAL_SQLITE_NOT_QUIESCENT",
        )
        return st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns

    initial = snapshot()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        yield db
    require(snapshot() == initial, "HISTORICAL_SQLITE_CHANGED_DURING_READ")


def queue(pins):
    """Bind the archived blind and after-unblind ledgers without promoting triage labels."""
    root = ARTIFACTS / "evidence_campaign_20261102"
    blind_report_path = root / "auto-review-v3/report.json"
    blind_report = checked_report(blind_report_path, pins)
    comparison = checked_report(root / "auto-review-v3-unblind/report.json", pins)
    require(
        comparison["blind_report_file_sha256"]
        == pins[str(blind_report_path.relative_to(REPO_ROOT))]
        and comparison["blind_sqlite_sha256"] == blind_report["sqlite_sha256"],
        "BLIND_COMPARISON_PROVENANCE_MISMATCH",
    )
    db_path = verify(
        root / "auto-review-v3/auto-review.sqlite", blind_report["sqlite_sha256"], pins
    )
    rows_path = verify(
        root / "auto-review-v3-unblind/unblind-comparison.jsonl",
        comparison["comparison_sha256"],
        pins,
    )
    distinct, sources, disagreements = set(), Counter(), Counter()
    reviewed = oracle = 0
    with readonly_db(db_path) as db, rows_path.open() as stream:
        for line in stream:
            item = json.loads(line)
            key = item["event_key"]
            found = db.execute(
                "SELECT request_id,source_id,record_json FROM decisions WHERE event_key=?", (key,)
            ).fetchone()
            require(
                found is not None
                and found[:2] == (item["request_id"], item["source_id"])
                and key not in distinct
                and item["verified_label"] is None
                and item["training_eligible"] is False,
                "REVIEW_QUEUE_ROW_BINDING_MISMATCH",
            )
            row = json.loads(found[2])
            require(
                digest(row) == item["blind_record_sha256"] and row["event_key"] == key,
                "BLIND_RECORD_DIGEST_MISMATCH",
            )
            distinct.add(key)
            sources[item["source_id"]] += 1
            disagreements.update(item["triage_disagreements"])
            reviewed += row["independent_human_label"] is not None
            oracle += row["oracle_verified_label"] is not None
        require(
            len(distinct) == db.execute("SELECT count(*) FROM decisions").fetchone()[0],
            "QUEUE_INCOMPLETE",
        )
    require(
        len(distinct)
        == comparison["counts"]["requests_compared"]
        == blind_report["expected_requests"]
        and dict(sources) == blind_report["by_source"]
        and reviewed == blind_report["independently_reviewed_labels"]
        and oracle == blind_report["objective_oracle_verified_labels"],
        "QUEUE_CENSUS_MISMATCH",
    )
    return {
        "record_pairs_verified": len(distinct),
        "source_counts": dict(sources),
        "triage_disagreement_counts": dict(disagreements),
        "independent_labels": reviewed,
        "semantic_oracle_labels": oracle,
        "state": "PENDING_REQUEST_BOUND_SEMANTIC_EVIDENCE",
    }


def indexed_records(path, coordinates):
    # These pinned files are safe metadata ledgers, not feature/payload archives.
    # Decode only the positions referenced by the authorized TRAIN index.
    with path.open() as stream:
        rows = {
            number: json.loads(line) for number, line in enumerate(stream) if number in coordinates
        }
    require(set(rows) == set(coordinates), "TRAIN_METADATA_LOCATOR_MISSING")
    return rows


def grounded(pins):
    t06 = CONTRACTS / "admission-pilot-v1"
    acceptance = load_json(t06 / "acceptance.json")
    ledger = t06 / "decision-ledger.json.gz"
    verify(ledger, acceptance["artifacts_sha256"][str(ledger.relative_to(REPO_ROOT))], pins)
    with gzip.open(ledger, "rt") as stream:
        selected = [
            row
            for row in json.load(stream)
            if row["cohort"] == "grounded" and row["admission_status"] == "RESEARCH_ONLY"
        ]
    require(len(selected) == 48, "T06_RESEARCH_FRAME_MISMATCH")
    database = ARTIFACTS / "data_scaling_20261109/pilot-r2/index.sqlite"
    locators = {}
    with readonly_db(database) as db:
        for row in selected:
            position = row["coordinate"]
            found = db.execute(
                "SELECT j FROM r WHERE i=? AND s='grounded-v3' AND role='TRAIN'", (position,)
            ).fetchone()
            require(found is not None and row["original_role"] == "TRAIN", "T06_ROLE_MISMATCH")
            meta = json.loads(found[0])
            require(
                digest([position, meta]) == row["row_evidence_sha256"]
                and meta["role"] == "TRAIN"
                and meta["label"] == row["target"]
                and meta["source_row"] not in locators,
                "T06_SCOPED_INDEX_DIGEST_MISMATCH",
            )
            locators[meta["source_row"]] = row

    capture = ARTIFACTS / "request_v3_acquisition_final_20261108"
    release = capture / "release-v2"
    assets = load_json(CONTRACTS / "multisource-v1/reusable-assets-ledger.json")["assets"]
    historical = next(row for row in assets if row["asset_id"] == "data-24")["provenance_evidence"]
    for item in historical:
        verify(REPO_ROOT / item["path"], item["sha256"], pins)
    manifest = load_json(release / "dataset-release.json")
    plan = load_json(verify(release / "plan.json", manifest["files_sha256"]["plan.json"], pins))
    rows = indexed_records(
        verify(release / "records.jsonl", manifest["files_sha256"]["records.jsonl"], pins), locators
    )
    receipts = load_json(
        verify(
            capture / "campaign-r1/main-oracle-receipts.json",
            plan["capture_files_sha256"]["main-oracle-receipts.json"],
            pins,
        )
    )
    by_sample = {receipt["sample_id"]: receipt for receipt in receipts}
    require(len(by_sample) == len(receipts), "DUPLICATE_ARCHIVED_ORACLE_SAMPLE")
    parent = ARTIFACTS / "request_v3_body_syntax_20261108/release-v2"
    parent_manifest = load_json(parent / "dataset-release.json")
    require(
        parent_manifest["dataset_fingerprint"] == plan["parent_fingerprint"],
        "PARENT_RELEASE_CHANGED",
    )
    parent_records = indexed_records(
        verify(parent / "records.jsonl", parent_manifest["files_sha256"]["records.jsonl"], pins),
        {
            record["parent_record_index"]
            for record in rows.values()
            if record["parent_record_index"] is not None
        },
    )
    outcomes, direct_outcomes, parents = Counter(), Counter(), 0
    equivalents = set()
    fields = (
        "request_id",
        "sample_id",
        "original_role",
        "intent",
        "outcome",
        "oracle_verified",
        "independent_human_verified",
        "review_status",
    )
    for coordinate, record in rows.items():
        historical_row = locators[coordinate]
        index = record["parent_record_index"]
        require(
            record["dataset_fingerprint"] == manifest["dataset_fingerprint"]
            and record["original_role"] == "TRAIN"
            and record["oracle_verified"] is True
            and record["independent_human_verified"] is False
            and record["review_status"] == "PENDING"
            and {"BENIGN_INTENT": 0, "ATTACK_INTENT": 1}.get(record["intent"])
            == historical_row["target"],
            "GROUNDED_ARCHIVED_LABEL_OR_ROLE_MISMATCH",
        )
        other = by_sample[record["sample_id"]] if index is None else parent_records[index]
        require(
            all(other[field] == record[field] for field in fields),
            "ARCHIVED_ORACLE_BINDING_MISMATCH",
        )
        outcomes[record["outcome"]] += 1
        equivalents.add(historical_row["lineage"]["view"])
        if index is None:
            require(
                other["observation_status"] == "ORACLE_VERIFIED"
                and bool(other["HTTP_transaction_identity"])
                and other["oracle_checks"] == record["oracle_checks"]
                and other["oracle_checks"]
                and all(value is True for value in other["oracle_checks"].values()),
                "DIRECT_ARCHIVED_ORACLE_PROOF_MISMATCH",
            )
            direct_outcomes[other["outcome"]] += 1
        else:
            parents += 1
    return {
        "TRAIN_metadata_rows_bound": len(rows),
        "legacy_distinct_views": len(equivalents),
        "legacy_outcomes": dict(outcomes),
        "direct_archived_oracle_receipts_bound": sum(direct_outcomes.values()),
        "direct_archived_outcomes": dict(direct_outcomes),
        "parent_metadata_records_bound": parents,
        "independent_review_pending": len(rows),
        "state": "RESEARCH_ONLY_NATIVE_MASK_AND_CAUSAL_TIMING_UNPROVEN",
    }


def soc(pins):
    root = ARTIFACTS / "attack_evidence_20261101/soc-pending-review-final-v2"
    historical = load_json(CONTRACTS / "native-defensive-r28/r28-evidence.json")
    audit_root = REPO_ROOT / historical["artifact_root"]
    old_pins = load_json(
        verify(audit_root / "inventory.json", historical["evidence_sha256"]["inventory.json"], pins)
    )["metadata_sha256"]
    path = root / "report.json"
    report = load_json(verify(path, old_pins[str(path.relative_to(REPO_ROOT))], pins))
    ledger = verify(root / "pending-dossiers.jsonl", report["dossiers_sha256"], pins)
    keys, coordinates = set(), set()
    with ledger.open() as stream:
        for line in stream:
            row = json.loads(line)
            require(
                row["decision"]["training_eligible"] is False
                and row["publisher_campaign"]["attack_instance_id"] is None
                and row["source_sha256"] == report["source_sha256"],
                "SOC_DOSSIER_SCOPE_CHANGED",
            )
            keys.add(row["event_key"])
            coordinates.add((row["source_member"], row["source_line_index_0"]))
    require(
        len(keys) == len(coordinates) == report["pending_records"], "SOC_DOSSIER_COUNT_MISMATCH"
    )
    return {
        "dossiers_sha_and_unique_locator_verified": len(keys),
        "approved_labels": report["labels_approved"],
        "campaign_overlap_ids_in_publisher_split": report["original_split_leakage"][
            "shared_attack_instance_ids"
        ],
        "state": "PENDING_REQUEST_LEVEL_OUTCOME_AND_CAMPAIGN_JOIN",
    }


def native_archives(pins):
    r27 = load_json(CONTRACTS / "native-independent-r27/r27-evidence.json")
    r262 = load_json(CONTRACTS / "quality-context-r262/r262-evidence.json")
    for release in (r27, r262):
        verify(
            REPO_ROOT / release["artifact_root"] / "acceptance.json",
            release["evidence_sha256"]["acceptance.json"],
            pins,
        )
    engineering = CONTRACTS / "capture-campaign-r72/capture-acceptance.json"
    t08 = load_json(engineering)
    pins[str(engineering.relative_to(REPO_ROOT))] = file_sha256(engineering)
    legacy = []
    for version in ("upgrade_20261029_query", "upgrade_20261030_deep"):
        path = ARTIFACTS / version / "dataset-ready/handoff.json"
        old = load_json(path)
        pins[str(path.relative_to(REPO_ROOT))] = file_sha256(path)
        require(
            any("Scenario labels" in limit for limit in old["limits"])
            and any("65s" in limit for limit in old["limits"]),
            "LEGACY_HANDOFF_CLASSIFICATION_REVIEW_REQUIRED",
        )
        legacy.append(
            {
                "profile": old["input_profile"],
                "scenario_labels_in_legacy_scope": old["approved_label_rows"],
                "state": "SCENARIO_LABELS_AND_COMPLETED_FLOW_CONTEXT",
            }
        )
    return {
        "R27": {
            "task": r27["native_counts"]["security_task"],
            "research_counts": r27["native_counts"]["research_canonical_TRAIN_DEV_CAL_TEST"],
        },
        "R26_2": {
            "state": r262["decision"],
            "exposed_authorization_cohort": r262["native"]["all_new_examples_exposed_research"],
            "candidate_views_pending": r262["native"]["candidate_views_pending"],
        },
        "T08_R72": {
            "pending_candidates": t08["admission"]["candidate_count"],
            "native_views_ready": t08["admission"]["native_views_ready"],
            "canonical_train": t08["admission"]["canonical_train"],
        },
        "legacy_handoffs": legacy,
    }


def audit():
    pins = {}
    sources = {"review_queue": queue(pins), "T06_grounded": grounded(pins), "SOC_MLD": soc(pins)}
    inbox = ARTIFACTS / "defensive-intake"
    inbox_present = any((inbox / name).is_file() for name in ("index.json", "handoff.json"))
    return {
        "version": "idps-r29-reconciliation-v1",
        "state": "TRUSTED_HANDOFF_PIN_REQUIRED" if inbox_present else "BLOCKED_NO_VERIFIED_DATA",
        "sources": sources | {"native_archives": native_archives(pins)},
        "metadata_sha256": pins,
        "pending_resolved_to_formal_labels": 0,
        "new_native_eligible": {"benign": 0, "attack": 0, "independent_lineage": 0},
        "canonical_counts": dict.fromkeys(("TRAIN", "DEV", "CAL_FIT", "CAL_OP", "TEST_SHADOW"), 0),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and not args.output.is_symlink(), "NEW_OUTPUT_REQUIRED")
    atomic_json(args.output, audit())
