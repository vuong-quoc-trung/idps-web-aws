#!/usr/bin/env python3
"""Explicitly declassify exposed research cohorts; combine only admitted source rows.

The original final lab test and newly sealed holdouts are never opened here.
SRBH is retrospective exposed development data, not an independent final test.
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.curated_split import assemble_curated, audit_curated_partitions
from idps_ai.data.dataset import iter_rows
from idps_ai.data.http_curation import require_development_source, verify_curation
from idps_ai.data.readers import eve_request_id
from idps_ai.data.request_corpus import PAYLOAD_FAMILIES, lab_rows
from idps_ai.features.request_view import fingerprint, validate_view
from idps_ai.training.resources import resource_envelope


def run(registry_path, output):
    config = yaml.safe_load(Path(registry_path).read_text())
    if config.get("format_version") != 1 or config.get("role") != "development_exposed":
        raise PipelineError("Explicit exposed-development source registry required")
    protocol = config.get("protocol")
    if protocol:
        registered = load_json(protocol)
        boundaries = config["srbh_boundaries"]
        if (
            file_sha256(protocol) != config.get("preregistered_protocol_sha256")
            or registered.get("SRBH_time_boundaries")
            != [boundaries["train_to_calibration"], boundaries["calibration_to_val"]]
            or registered.get("embargo_seconds") != config["embargo_seconds"]
            or registered.get("models_or_scores_used_to_select_split") is not False
            or registered.get("holdouts_unchanged") is not True
        ):
            raise PipelineError(
                "Registered forward-development protocol differs from source registry"
            )
    source = Path(config["srbh_curated"])
    curation = verify_curation(source)
    if curation["provenance"].get("source_role") != "development_exposed":
        raise PipelineError("Source role differs from registered development scope")
    boundaries = config["srbh_boundaries"]
    b1, b2 = boundaries["train_to_calibration"], boundaries["calibration_to_val"]
    embargo = config["embargo_seconds"]
    if embargo < 300 or not b1 < b2:
        raise PipelineError("Invalid preregistered temporal boundaries")
    if not config.get("exposed_cohorts_declassified_for_development"):
        raise PipelineError(
            "Previously exposed cohorts must be explicitly declassified, never silently reused as fresh tests"
        )
    stats = Counter()
    proof = {
        "registry_sha256": file_sha256(registry_path),
        "protocol_sha256": file_sha256(protocol) if protocol else None,
        "srbh_curation_sha256": curation["curation_sha256"],
        "srbh_source_sha256": curation["provenance"]["source_sha256"],
        "role": "development_exposed",
        "srbh_boundaries": boundaries,
        "embargo_seconds": embargo,
        "old_final_lab_test_quality_used": False,
        "new_final_holdouts_used": False,
        "exposed_cohort_declassification": config["exposed_cohorts_declassified_for_development"],
        "source_files": {},
    }
    for item in [config["lab_train"], *config["lab_development_cohorts"]]:
        eve = Path(item["eve"])
        require_development_source(eve)
        decoder = load_json(eve.parent / "decode-manifest.json")
        if (
            decoder.get("request_structure_implementation_sha256") != fingerprint()
            or file_sha256(eve) != decoder["eve_sha256"]
        ):
            raise PipelineError("Immutable EVE projection/decoder mismatch")
        proof["source_files"][str(eve)] = {
            "sha256": file_sha256(eve),
            "decoder_sha256": file_sha256(eve.parent / "decode-manifest.json"),
            "pcap_sha256": decoder["pcap_sha256"],
        }
        if "lab" in item:
            lab = Path(item["lab"])
            require_development_source(lab / "observer.jsonl")
            capture = load_json(lab / "capture-result.json")
            if file_sha256(lab / "observer.jsonl") != capture["observer_sha256"]:
                raise PipelineError("Exposed observer identity changed")
            proof["source_files"][str(lab / "observer.jsonl")] = {
                "sha256": capture["observer_sha256"]
            }

    def records():
        for r in iter_rows(source / "curated.parquet"):
            t = r["timestamp"]
            if min(abs(t - b1), abs(t - b2)) < embargo:
                stats["srbh_temporal_boundary_embargo"] += 1
                continue
            split = "train" if t < b1 else "calibration" if t < b2 else "val"
            day = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
            stats["srbh_proposed_" + split] += 1
            yield dict(
                event_key=r["event_key"],
                source_id="srbh2020",
                proposed_split=split,
                group_key=digest({"source": "srbh2020", "client": r["client_key"], "UTC_day": day}),
                related_key=r["feature_key"],
                timestamp=t,
                client_key=r["client_key"],
                label=r["original_label"],
                attack_family=r["attack_family"],
                numbers=json.loads(r["numeric_json"]),
            )
        train = config["lab_train"]
        key = Path(train["redaction_key"]).read_bytes()
        for r in lab_rows(train["eve"], train["prepared"], key):
            if r["split"] != "train":
                continue
            if r["label"] is None:
                stats["lab_train_unsupported_task"] += 1
                continue
            stats["lab_proposed_train"] += 1
            yield {**r, "proposed_split": "train", "related_key": r["group_key"]}
        for item in config["lab_development_cohorts"]:
            role = item["split"]
            if role not in ["calibration", "val"]:
                raise PipelineError("Exposed challenge cannot become supervised train")
            lab = Path(item["lab"])
            capture = load_json(lab / "capture-result.json")
            observer = {
                r["request_id"]: r
                for r in map(json.loads, (lab / "observer.jsonl").read_text().splitlines())
            }
            ids = set()
            with Path(item["eve"]).open() as stream:
                for line in stream:
                    event = json.loads(line)
                    if event.get("event_type") != "http":
                        continue
                    rid = eve_request_id(event.get("http") or {})
                    r = observer.get(rid)
                    if r is None:
                        continue
                    if rid in ids:
                        raise PipelineError("Duplicate HTTP request identity in development cohort")
                    ids.add(rid)
                    if (
                        r["review_status"] != "approved"
                        or r["status_code"] not in r["expected_status_codes"]
                    ):
                        stats["lab_" + role + "_pending_HTTP_contract"] += 1
                        continue
                    if r["attack_family"] not in PAYLOAD_FAMILIES | {"benign"}:
                        stats["lab_" + role + "_unsupported_task"] += 1
                        continue
                    numbers = validate_view(event["ai_request_view"])
                    timestamp = datetime.fromisoformat(
                        event["timestamp"].replace("Z", "+00:00")
                    ).timestamp()
                    stats["lab_proposed_" + role] += 1
                    yield dict(
                        event_key=digest({"capture": capture["capture_id"], "request": rid}),
                        source_id="student-lab",
                        proposed_split=role,
                        group_key=digest(
                            {"capture": capture["capture_id"], "campaign": r["campaign_id"]}
                        ),
                        related_key=r["variant_group"],
                        timestamp=timestamp,
                        label=r["label"],
                        attack_family=r["attack_family"],
                        numbers=numbers,
                    )
            if len(ids) != len(observer):
                raise PipelineError("Incomplete source identity coverage before split filtering")

    with resource_envelope(4, 16):
        result = assemble_curated(
            records(),
            output,
            proof,
            min_sources=2,
            embargo_seconds=embargo,
            cap_per_source_role=config["pilot_cap_per_source_role"],
            minimum_class_rows=config.get("minimum_records_per_source_role_class", 32),
        )
    atomic_json(Path(output) / "source-filter-audit.json", dict(stats))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry")
    source.add_argument("--audit-dataset")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if a.audit_dataset:
        if Path(a.output).exists():
            raise PipelineError("Partition audit output must be new")
        result = audit_curated_partitions(a.audit_dataset)
        atomic_json(a.output, result)
    else:
        result = run(a.registry, a.output)
    print(json.dumps(result, sort_keys=True))
