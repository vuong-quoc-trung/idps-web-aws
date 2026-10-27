"""Bind scripted intent, read-only captures and dataset hashes without detector labels."""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from idps_ai.common import (
    CLASSES,
    REPO_ROOT,
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    fsync_dir,
    load_json,
)
from idps_ai.data.dataset import load_labels, verify_dataset
from idps_ai.data.privacy import pseudonym
from idps_ai.data.review import SLUG
from idps_ai.data.snapshot import new_destination, verify_snapshot


def observer_labels(observer, capture_result, output, key):
    capture = load_json(capture_result)
    observer_sha = file_sha256(observer)
    if capture.get("data_kind") != "lab_capture" or observer_sha != capture["observer_sha256"]:
        raise PipelineError("Observer/capture checksum mismatch")
    output = new_destination(output)
    counts = Counter()
    pending = corrections = 0
    seen = set()
    variants = {}
    with tempfile.TemporaryDirectory(prefix=".observer-labels-", dir=output.parent) as temporary:
        work = Path(temporary)
        with Path(observer).open("rb") as stream, (work / "labels.jsonl").open("w") as dest:
            while line := stream.readline(65537):
                if len(line) > 65536:
                    raise PipelineError("Oversized observer record")
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    raise PipelineError("Invalid observer record") from None
                rid = value.get("request_id")
                family = value.get("attack_family")
                campaign = value.get("campaign_id")
                if (
                    not isinstance(rid, str)
                    or not SLUG.fullmatch(rid)
                    or rid in seen
                    or family not in CLASSES
                    or not SLUG.fullmatch(campaign or "")
                    or value.get("label") != int(family != "benign")
                    or value.get("label_source") != "scenario_manifest"
                ):
                    raise PipelineError("Invalid or duplicated scripted intent")
                seen.add(rid)
                approved = value.get("review_status") == "approved" and value.get(
                    "status_code"
                ) in value.get("expected_status_codes", [])
                # An audited source-contract correction, not a status-to-attack heuristic.
                # Spring's explicit GET matcher does not grant HEAD/OPTIONS; these
                # intentionally benign method checks may validly return 403.
                correction = (
                    family == "benign"
                    and value.get("scenario") == "benign_catalog"
                    and value.get("http_method") in ("HEAD", "OPTIONS")
                    and value.get("status_code") == 403
                )
                if not approved and correction:
                    approved = True
                    corrections += 1
                if not approved:
                    pending += 1
                    continue
                item = {
                    k: value[k]
                    for k in (
                        "request_id",
                        "campaign_id",
                        "label",
                        "attack_family",
                        "label_source",
                        "label_confidence",
                    )
                }
                item.update(
                    review_status="approved",
                    evidence_ref="observer-sha256:" + observer_sha,
                    intent="benign_workflow" if family == "benign" else "attack_attempt",
                    exploit_success="not_asserted",
                )
                dest.write(json.dumps(item, sort_keys=True) + "\n")
                counts[family] += 1
                if family != "benign":
                    variants.setdefault(pseudonym(key, "campaign", campaign), set()).add(
                        value.get("variant_group", "unknown")
                    )
        if len(seen) != capture["requests"]:
            raise PipelineError("Observer count does not match capture manifest")
        os.chmod(work / "labels.jsonl", 0o600)
        load_labels(work / "labels.jsonl", key)
        result = {
            "format_version": 1,
            "capture_result_sha256": file_sha256(capture_result),
            "observer_sha256": file_sha256(observer),
            "labels_sha256": file_sha256(work / "labels.jsonl"),
            "approved_rows": sum(counts.values()),
            "unknown_rows": pending,
            "label_counts": dict(counts),
            "campaign_variant_groups": {k: sorted(v) for k, v in variants.items()},
            "outcome_contract_corrections": {"benign_HEAD_OPTIONS_catalog_403": corrections},
            "outcome_contract_source_sha256": file_sha256(
                REPO_ROOT
                / "student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityConfiguration.java"
            ),
            "ground_truth": "Runner intent and observed HTTP contract; no rule hit/status-only benign inference; no exploit success assertion",
            "reviewer": "automated_scenario_contract_only; human realism/coverage review still required",
        }
        atomic_json(work / "label_evidence.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result


def register_provenance(dataset, snapshot_dir, capture_result, label_evidence, output, limits=()):
    dataset = verify_dataset(dataset)
    capture = load_json(capture_result)
    snapshot = verify_snapshot(snapshot_dir)
    evidence = load_json(label_evidence)
    if (
        capture.get("data_kind") != snapshot["data_kind"]
        or evidence["capture_result_sha256"] != file_sha256(capture_result)
        or evidence["observer_sha256"] != capture["observer_sha256"]
    ):
        raise PipelineError("Capture/snapshot/label provenance mismatch")
    input_hashes = {(i["source"], i["sha256"], i["bytes"]) for i in dataset.get("inputs", [])}
    if input_hashes != {(i["source"], i["sha256"], i["bytes"]) for i in snapshot["inputs"]}:
        raise PipelineError("Snapshot inputs do not match collected dataset")
    if dataset["label_manifest_sha256"] != evidence["labels_sha256"]:
        raise PipelineError("Labels are not bound to this collected dataset")
    value = {
        "format_version": 1,
        "data_kind": snapshot["data_kind"],
        "dataset_sha256": dataset["dataset_sha256"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "capture_result_sha256": file_sha256(capture_result),
        "observer_sha256": capture["observer_sha256"],
        "label_evidence_sha256": file_sha256(label_evidence),
        "capture_metadata": capture,
        "collection_quality": dataset.get("quality", {}),
        "collection_sources": dataset.get("sources", {}),
        "label_evidence": evidence,
        "limits": list(limits),
    }
    value["provenance_sha256"] = digest(value)
    output = new_destination(output)
    atomic_json(output, value)
    return value


def derive_provenance(prepared, collected_provenance, output):
    prepared = verify_dataset(prepared, "prepared")
    parent = verify_provenance(collected_provenance)
    if prepared["parent_dataset_sha256"] != parent["dataset_sha256"]:
        raise PipelineError("Prepared dataset parent does not match provenance")
    result = {
        **parent,
        "dataset_sha256": prepared["dataset_sha256"],
        "parent_provenance_sha256": parent["provenance_sha256"],
    }
    result.pop("provenance_sha256")
    result["provenance_sha256"] = digest(result)
    output = new_destination(output)
    atomic_json(output, result)
    return result


def verify_provenance(path):
    value = load_json(path)
    expected = value.pop("provenance_sha256", None)
    if digest(value) != expected:
        raise PipelineError("Provenance checksum mismatch")
    value["provenance_sha256"] = expected
    return value


def scope_capture_inputs(inputs, observer, capture_result, output):
    """Select declared runner request IDs, including every pending/unlabeled case.

    Startup/health probes are not part of the scenario corpus. This selection is
    based on an independently recorded capture identity, never status/label/rule.
    Original source hashes and excluded counts remain in the scope manifest.
    """
    capture = load_json(capture_result)
    if file_sha256(observer) != capture["observer_sha256"]:
        raise PipelineError("Observer checksum mismatch")
    identities = set()
    with Path(observer).open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536:
                raise PipelineError("Oversized observer record")
            value = json.loads(line)
            rid = value.get("request_id")
            if not isinstance(rid, str) or not SLUG.fullmatch(rid) or rid in identities:
                raise PipelineError("Ambiguous capture identity")
            identities.add(rid)
    if len(identities) != capture["requests"]:
        raise PipelineError("Capture request count mismatch")
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix=".capture-scope-", dir=output.parent) as temporary:
        work = Path(temporary)
        entries = []
        for index, item in enumerate(inputs):
            before = file_sha256(item.path)
            kept = excluded = 0
            name = f"{index:02d}-{item.source}.jsonl"
            with Path(item.path).open("rb") as stream, (work / name).open("wb") as dest:
                while line := stream.readline(65537):
                    if len(line) > 65536 or not line.endswith(b"\n"):
                        raise PipelineError(
                            "Invalid capture source line; scope selection must not hide parser errors"
                        )
                    try:
                        value = json.loads(line)
                    except ValueError:
                        raise PipelineError("Invalid JSON in capture source") from None
                    if value.get("request_id") in identities:
                        dest.write(line)
                        kept += 1
                    else:
                        excluded += 1
                dest.flush()
                os.fsync(dest.fileno())
            os.chmod(work / name, 0o600)
            if file_sha256(item.path) != before:
                raise PipelineError("Capture source changed during scoping")
            entries.append(
                {
                    "source": item.source,
                    "file": name,
                    "source_sha256": before,
                    "sha256": file_sha256(work / name),
                    "kept": kept,
                    "excluded_outside_declared_capture": excluded,
                }
            )
        result = {
            "format_version": 1,
            "observer_sha256": capture["observer_sha256"],
            "requests": len(identities),
            "inputs": entries,
            "policy": "Exact observed request IDs only; keep pending/unknown/outcome mismatches; never filter by label/status/rule",
        }
        atomic_json(work / "scope_manifest.json", result)
        os.replace(work, output)
        fsync_dir(output.parent)
    return result
