"""Disk-backed corpus admission. Reference data is never silently promoted to train."""

import os
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.provenance import verify_provenance
from idps_ai.data.snapshot import new_destination

PARTITIONS = ("train", "calibration", "validation", "test")
SLUG = re.compile(r"[A-Za-z0-9_.:-]{1,160}")


def _path(value):
    path = Path(value)
    return path if path.is_absolute() else AI_ROOT / path


def _reviewed(entry, manifest, proof):
    if (
        entry["collection_kind"] == "synthetic"
        or not proof
        or proof.get("data_kind") not in ("lab_capture", "production_snapshot", "public_benchmark")
        or not entry.get("review")
    ):
        return False
    review = load_json(_path(entry["review"]))
    return (
        review.get("approved") is True
        and review.get("independent_review") is True
        and SLUG.fullmatch(str(review.get("reviewer_id", ""))) is not None
        and review.get("dataset_sha256") == manifest["dataset_sha256"]
        and review.get("provenance_sha256") == proof["provenance_sha256"]
        and review.get("environment_id") == entry["environment_id"]
        and review.get("scope") == "label_protocol_and_environment_realism"
    )


def audit_catalog(registry, output, policy_path=None):
    """Audit actual Parquet rows; neither fabricate requests nor assemble mixed scalers."""
    policy_path = Path(policy_path or AI_ROOT / "configs/scale_policy.yaml")
    policy = yaml.safe_load(policy_path.read_text())
    if isinstance(registry, (str, Path)):
        registry = yaml.safe_load(Path(registry).read_text())
    if registry.get("format_version") != 1 or not registry.get("sources"):
        raise PipelineError("A nonempty versioned source registry is required")
    output = new_destination(output)
    source_ids, datasets, capture_hashes = set(), set(), set()
    references = eligible = unreviewed = low_confidence = correlated = leaks = 0
    counts = {p: Counter() for p in PARTITIONS}
    envs, times, days, campaigns = defaultdict(set), {}, set(), set()
    summaries, problems = [], []
    with tempfile.TemporaryDirectory(prefix=".corpus-audit-", dir=output.parent) as temporary:
        work = Path(temporary)
        db = sqlite3.connect(work / "index.sqlite")
        db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE identities(scope TEXT,kind TEXT,id TEXT,part TEXT,
              PRIMARY KEY(scope,kind,id));
            CREATE TABLE events(scope TEXT,id TEXT,PRIMARY KEY(scope,id));
            CREATE TABLE payloads(id TEXT PRIMARY KEY,part TEXT);
        """)
        try:
            for entry in registry["sources"]:
                for name in ("id", "environment_id", "authorization_ref"):
                    if not SLUG.fullmatch(str(entry.get(name, ""))):
                        raise PipelineError(
                            "Source IDs, environment and authorization reference must be bounded slugs"
                        )
                if entry["id"] in source_ids:
                    raise PipelineError("Duplicate source ID")
                source_ids.add(entry["id"])
                if entry.get("collection_kind") not in (
                    "scripted_lab",
                    "authorized_capture",
                    "public_benchmark",
                    "synthetic",
                ):
                    raise PipelineError("Unsupported collection kind")
                mapping = entry.get("partition_map", {})
                if set(mapping) != {"train", "val", "test"}:
                    raise PipelineError(
                        "Source partition map must explicitly preserve every original split"
                    )
                allowed = {
                    "train": ("train", "reference"),
                    "val": ("calibration", "validation", "reference"),
                    "test": ("test", "reference"),
                }
                if any(mapping[p] not in allowed[p] for p in allowed):
                    raise PipelineError(
                        "Original held-out data cannot be reassigned to training or other roles"
                    )
                directory = _path(entry["dataset"])
                manifest = verify_dataset(directory, "prepared")
                if manifest["dataset_sha256"] in datasets:
                    raise PipelineError("Duplicate immutable dataset/replay")
                datasets.add(manifest["dataset_sha256"])
                proof = (
                    verify_provenance(_path(entry["provenance"]))
                    if entry.get("provenance")
                    else None
                )
                if proof and proof["dataset_sha256"] != manifest["dataset_sha256"]:
                    raise PipelineError("Source provenance is bound to another dataset")
                pcap = (proof or {}).get("sensor_evidence", {}).get("pcap_sha256")
                if pcap:
                    if pcap in capture_hashes:
                        raise PipelineError("Duplicate packet capture, even if reprojected/rekeyed")
                    capture_hashes.add(pcap)
                reviewed = _reviewed(entry, manifest, proof)
                spec = load_json(directory / "feature_spec.json")
                compatible = (
                    manifest.get("input_profile") == policy["required_profile"]
                    and spec.get("feature_version") == policy["required_feature_version"]
                )
                if not compatible:
                    problems.append(entry["id"] + ": incompatible numeric profile; reference only")
                # Renaming an environment cannot make a repeated HMAC identity independent.
                scope = manifest["redaction_key_fingerprint"]
                local, local_parts = Counter(), defaultdict(set)
                for row in iter_rows(directory / "requests.parquet"):
                    role = mapping.get(row.get("split"), "reference")
                    local["actual_requests"] += 1
                    if role == "reference":
                        references += 1
                        continue
                    if not reviewed or not compatible:
                        unreviewed += 1
                        continue
                    if (
                        row["label"] is None
                        or (row["label_confidence"] or 0) < policy["minimum_label_confidence"]
                    ):
                        low_confidence += 1
                        continue
                    try:
                        db.execute("INSERT INTO events VALUES(?,?)", (scope, row["event_key"]))
                    except sqlite3.IntegrityError:
                        raise PipelineError(
                            "Duplicate request identity across source shards"
                        ) from None
                    for kind in ("client_key", "user_key", "session_key", "campaign_key"):
                        identity = row.get(kind)
                        if identity is None:
                            continue
                        before = db.execute(
                            "SELECT part FROM identities WHERE scope=? AND kind=? AND id=?",
                            (scope, kind, identity),
                        ).fetchone()
                        if before and before[0] != role:
                            leaks += 1
                        db.execute(
                            "INSERT OR IGNORE INTO identities VALUES(?,?,?,?)",
                            (scope, kind, identity, role),
                        )
                    eligible += 1
                    local["eligible_requests"] += 1
                    counts[role][row["attack_family"]] += 1
                    correlated += {"STUDENT_AUDIT", "NGINX", "SURICATA"} <= set(
                        row.get("sources") or []
                    )
                    envs[role].add(entry["environment_id"])
                    timestamp = float(row["timestamp"])
                    lo, hi = times.get(role, (timestamp, timestamp))
                    times[role] = min(lo, timestamp), max(hi, timestamp)
                    days.add(
                        datetime.fromtimestamp(row["timestamp"], timezone.utc).date().isoformat()
                    )
                    campaigns.add((scope, row.get("campaign_key")))
                    local_parts[row["campaign_key"]].add(role)
                    if eligible % 8192 == 0:
                        db.commit()
                # Payload/hard-negative identities are audit facts, never model features.
                evidence = (proof or {}).get("label_evidence", {})
                for key in ("campaign_variant_groups", "campaign_hard_negative_groups"):
                    for campaign, variants in evidence.get(key, {}).items():
                        for role in local_parts.get(campaign, ()):
                            for variant in variants:
                                before = db.execute(
                                    "SELECT part FROM payloads WHERE id=?", (variant,)
                                ).fetchone()
                                if before and before[0] != role:
                                    leaks += 1
                                db.execute(
                                    "INSERT OR IGNORE INTO payloads VALUES(?,?)", (variant, role)
                                )
                summaries.append(
                    {
                        "id": entry["id"],
                        "environment_id": entry["environment_id"],
                        "collection_kind": entry["collection_kind"],
                        "dataset_sha256": manifest["dataset_sha256"],
                        "dataset_manifest_sha256": file_sha256(directory / "dataset_manifest.json"),
                        "provenance_sha256": proof["provenance_sha256"] if proof else None,
                        "review_sha256": file_sha256(_path(entry["review"]))
                        if entry.get("review")
                        else None,
                        "independent_review_attested": reviewed,
                        "profile_compatible": compatible,
                        "counts": dict(local),
                        "partition_map": mapping,
                    }
                )
            db.commit()
        finally:
            db.close()
        checks = []

        def check(name, passed, details):
            checks.append({"id": name, "pass": bool(passed), "detail": details})

        check(
            "request_volume",
            eligible >= policy["minimum_requests"],
            {"eligible": eligible, "required": policy["minimum_requests"]},
        )
        check(
            "reviewed_sources",
            unreviewed == 0 and eligible > 0,
            {
                "unreviewed_requests": unreviewed,
                "attestation_is_not_automatic_truth_verification": True,
            },
        )
        check("label_confidence", low_confidence == 0 and eligible > 0, low_confidence)
        all_envs = set().union(*envs.values())
        check(
            "independent_environments",
            len(all_envs) >= policy["minimum_environments"],
            sorted(all_envs),
        )
        check("capture_days", len(days) >= policy["minimum_capture_days"], sorted(days))
        check("campaign_depth", len(campaigns) >= policy["minimum_campaigns"], len(campaigns))
        check(
            "three_source_coverage",
            correlated / max(eligible, 1) >= policy["minimum_three_source_fraction"],
            {"correlated": correlated, "total": eligible},
        )
        check("identity_and_payload_holdouts", eligible > 0 and leaks == 0, leaks)
        check(
            "environment_holdouts",
            bool(envs["train"] and envs["validation"] and envs["test"])
            and not (envs["train"] & (envs["calibration"] | envs["validation"] | envs["test"]))
            and not (envs["test"] & (envs["calibration"] | envs["validation"])),
            {k: sorted(v) for k, v in envs.items()},
        )
        for part in PARTITIONS:
            check(
                part + "_families",
                all(
                    counts[part][f] >= policy["minimum_family_per_partition"]
                    for f in policy["required_families"]
                )
                and counts[part]["benign"] >= policy["minimum_benign_per_partition"],
                dict(counts[part]),
            )
        for left, right in zip(PARTITIONS, PARTITIONS[1:]):
            check(
                left + "_before_" + right,
                bool(times.get(left) and times.get(right))
                and times[left][1] + 2 * policy["embargo_seconds"] < times[right][0],
                {
                    "left_max": times.get(left, (None, None))[1],
                    "right_min": times.get(right, (None, None))[0],
                    "embargo_each_side_seconds": policy["embargo_seconds"],
                },
            )
        passed = all(c["pass"] for c in checks)
        report = {
            "format_version": 1,
            "status": "READY_FOR_SCALE_RESEARCH" if passed else "NOT_READY",
            "formal_training_permitted": False,
            "eligible_requests": eligible,
            "reference_requests": references,
            "unreviewed_requests": unreviewed,
            "sources": summaries,
            "checks": checks,
            "problems": problems,
            "registry_sha256": digest(registry),
            "policy_sha256": file_sha256(policy_path),
            "index_sha256": file_sha256(work / "index.sqlite"),
            "dataset_assembly_required": True,
            "limits": [
                "This catalog audits inputs; differently normalized shards are never concatenated as feature vectors.",
                "Environment/review attestations need genuine human verification; metadata alone does not certify realism.",
                "A passing catalog still needs train-only shared scaler, immutable assembled dataset and source-bound readiness before formal training.",
                "Near-duplicate semantic grammars may survive exact payload identity checks; independent unseen-campaign review is required.",
            ],
        }
        report["report_sha256"] = digest(report)
        atomic_json(work / "report.json", report)
        os.rename(work, output)
    return report


def require_scale_dataset(dataset):
    """Formal main-model admission fails closed; technical pilots are separate."""
    manifest = verify_dataset(dataset, "prepared")
    if manifest.get("feature_rows", 0) < 2_000_000 or not manifest.get("rows", {}).get(
        "calibration"
    ):
        raise PipelineError(
            "Main model formal training requires 2M admitted requests and independent calibration; lab pilot remains available"
        )
    path = manifest.get("corpus_catalog_report")
    if not path:
        raise PipelineError("An assembled corpus must bind its audited source catalog")
    report_path = _path(path)
    report = load_json(report_path)
    expected = report.pop("report_sha256", None)
    if (
        digest(report) != expected
        or report["status"] != "READY_FOR_SCALE_RESEARCH"
        or not all(c["pass"] for c in report["checks"])
        or report["policy_sha256"] != file_sha256(AI_ROOT / "configs/scale_policy.yaml")
        or manifest.get("corpus_catalog_sha256") != file_sha256(report_path)
        or manifest["feature_rows"] != report["eligible_requests"]
        or file_sha256(report_path.parent / "index.sqlite") != report["index_sha256"]
    ):
        raise PipelineError("Scale catalog/policy/dataset binding mismatch")
    return report
