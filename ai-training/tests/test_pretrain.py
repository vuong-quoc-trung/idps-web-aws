import json

import pytest

from idps_ai.data.readers import Input
from idps_ai.data.snapshot import snapshot, verify_snapshot


def test_snapshot_keeps_only_complete_lines_and_never_changes_the_source(tmp_path):
    source = tmp_path / "live.log"
    original = b'{"one":1}\n{"partial":'
    source.write_bytes(original)
    output = tmp_path / "capture"
    report = snapshot([Input("nginx", source)], output, data_kind="lab_capture")
    entry = report["inputs"][0]
    assert (output / entry["file"]).read_bytes() == b'{"one":1}\n'
    assert entry["discarded_tail_bytes"] == 11
    assert source.read_bytes() == original
    assert verify_snapshot(output)["snapshot_sha256"] == report["snapshot_sha256"]
    (output / entry["file"]).write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="checksum"):
        verify_snapshot(output)


def test_review_import_requires_evidence_and_preserves_unlabeled_rows(tmp_path):
    import csv

    from idps_ai.data.dataset import collect, load_labels
    from idps_ai.data.review import export_review, import_review
    from idps_ai.data.synthetic import synthetic_s0

    raw = tmp_path / "raw"
    synthetic_s0(raw, campaigns=10, requests_per_campaign=16)
    key = (raw / "redaction.key").read_bytes()
    collect([Input("student", raw / "student-audit.log")], tmp_path / "data", key)
    report = export_review(tmp_path / "data", tmp_path / "review", limit=2)
    path = tmp_path / "review/labels.csv"
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0].update(
        attack_family="benign",
        campaign_id="human-campaign",
        label_confidence="0.9",
        review_status="approved",
        evidence_ref="case-001",
    )

    def save():
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    save()
    result = import_review(
        tmp_path / "review", tmp_path / "data", tmp_path / "approved", key, reviewer="reviewer-a"
    )
    labels = load_labels(tmp_path / "approved/labels.jsonl", key)
    assert len(labels) == 1
    assert result["unknown_rows"] == 1
    assert report["dataset_sha256"] == result["dataset_sha256"]
    rows[0]["uri_path"] = "/tampered"
    save()
    with pytest.raises(ValueError, match="context"):
        import_review(
            tmp_path / "review", tmp_path / "data", tmp_path / "bad", key, reviewer="reviewer-a"
        )


def test_synthetic_fixture_cannot_pass_the_real_data_readiness_gate(prepared, tmp_path):
    from idps_ai.data.readiness import audit_readiness

    report = audit_readiness(prepared, tmp_path / "readiness", data_kind="synthetic")
    assert report["status"] == "NOT_READY"
    assert report["offline_pilot_training_permitted"] is False
    assert any(c["id"] == "provenance" and not c["pass"] for c in report["checks"])
    assert report["training_executed"] is False


def test_observer_labels_are_bound_to_capture_and_unexpected_outcomes_stay_unknown(tmp_path):
    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.provenance import observer_labels

    observer = tmp_path / "observer.jsonl"
    rows = [
        {
            "request_id": "request-1",
            "campaign_id": "campaign-1",
            "label": 1,
            "attack_family": "sqli",
            "label_source": "scenario_manifest",
            "label_confidence": 1,
            "review_status": "approved",
            "scenario": "bounded_uri_probe",
            "http_method": "GET",
            "status_code": 200,
            "expected_status_codes": [200],
            "variant_group": "sqli-view-1",
        },
        {
            "request_id": "request-2",
            "campaign_id": "campaign-1",
            "label": 0,
            "attack_family": "benign",
            "label_source": "scenario_manifest",
            "label_confidence": 1,
            "review_status": "pending",
            "scenario": "benign_catalog",
            "http_method": "GET",
            "status_code": 500,
            "expected_status_codes": [200],
            "variant_group": "catalog",
        },
    ]
    observer.write_text("".join(json.dumps(r) + "\n" for r in rows))
    capture = tmp_path / "capture.json"
    atomic_json(
        capture,
        {"data_kind": "lab_capture", "observer_sha256": file_sha256(observer), "requests": 2},
    )
    report = observer_labels(observer, capture, tmp_path / "labels", b"X" * 32)
    assert report["approved_rows"] == 1 and report["unknown_rows"] == 1
    assert len((tmp_path / "labels/labels.jsonl").read_text().splitlines()) == 1
    observer.write_text(observer.read_text() + "{}\n")
    with pytest.raises(ValueError, match="checksum"):
        observer_labels(observer, capture, tmp_path / "bad", b"X" * 32)


def test_lab_client_rejects_external_targets_before_opening_a_connection():
    from idps_ai.data.lab_capture import LabClient

    for port, address in [(443, "127.0.0.1"), (18881, "8.8.8.8"), (18881, "192.168.1.1")]:
        with pytest.raises(ValueError, match="restricted"):
            LabClient(port, address)


def test_readiness_cli_writes_a_blocked_report_and_returns_nonzero(prepared, tmp_path):
    from idps_ai.cli import main

    result = main(
        [
            "readiness",
            "--dataset",
            str(prepared),
            "--data-kind",
            "synthetic",
            "--output",
            str(tmp_path / "report"),
        ]
    )
    assert result == 3
    report = json.loads((tmp_path / "report/readiness.json").read_text())
    assert report["training_executed"] is False
    assert not list(tmp_path.rglob("model.onnx"))
    assert not list(tmp_path.rglob("tensors.npz"))


def test_snapshot_output_is_never_allowed_inside_protected_service_directories():
    from idps_ai.common import REPO_ROOT
    from idps_ai.data.snapshot import new_destination

    for directory in ["student-web", "security-web", "contracts"]:
        with pytest.raises(ValueError, match="protected"):
            new_destination(REPO_ROOT / directory / "ai-snapshot-forbidden")


def test_readiness_pass_is_bound_to_dataset_source_and_cannot_be_reused_on_tampering(
    prepared, tmp_path
):
    import yaml

    from idps_ai.common import AI_ROOT, atomic_json, digest
    from idps_ai.data.capacity import validate_training_report
    from idps_ai.data.dataset import verify_dataset
    from idps_ai.data.readiness import audit_readiness

    # Tiny fixture policy is explicitly test-only; real defaults remain unchanged.
    policy = yaml.safe_load((AI_ROOT / "configs/pretrain_policy.yaml").read_text())
    policy.update(
        require_variant_provenance=False,
        minimum_requests=100,
        minimum_groups_per_partition=1,
        minimum_benign_per_partition=1,
        minimum_family_per_partition=1,
    )
    p = tmp_path / "tiny-policy.yaml"
    p.write_text(yaml.safe_dump(policy))
    proof = {
        "format_version": 1,
        "data_kind": "lab_capture",
        "dataset_sha256": verify_dataset(prepared)["dataset_sha256"],
        "limits": ["Test fixture provenance declaration only"],
    }
    proof["provenance_sha256"] = digest(proof)
    provenance = tmp_path / "provenance.json"
    atomic_json(provenance, proof)
    report = audit_readiness(prepared, tmp_path / "gate", "lab_capture", p, provenance)
    assert report["status"] == "READY_FOR_OFFLINE_PILOT", [
        c for c in report["checks"] if not c["pass"]
    ]
    validate_training_report(tmp_path / "gate/readiness.json", prepared)
    report["source_files_sha256"]["src/idps_ai/cli.py"] = "0" * 64
    report.pop("report_sha256")
    report["report_sha256"] = digest(report)
    changed = tmp_path / "changed.json"
    atomic_json(changed, report)
    with pytest.raises(ValueError, match="Source changed"):
        validate_training_report(changed, prepared)


def test_capacity_check_reads_vectors_without_starting_a_training_run(prepared, tmp_path):
    from idps_ai.data.capacity import capacity_check

    report = capacity_check(prepared, tmp_path / "capacity.json", 1)
    assert report["training_executed"] is False
    assert report["feature_rows"] == 160
    assert not (tmp_path / "checkpoints").exists()


def test_stopping_an_unowned_lab_is_rejected_before_signalling_any_process(tmp_path):
    from idps_ai.data.lab_runtime import stop_lab

    (tmp_path / "owned-lab.json").write_text('{"purpose":"existing-service"}')
    with pytest.raises(ValueError, match="unowned"):
        stop_lab(tmp_path)


def test_rule_baseline_uses_only_validation_and_never_turns_rule_hits_into_labels(
    prepared, tmp_path
):
    from idps_ai.data.baseline import nginx_rule_baseline

    key = (prepared.parent / "raw/redaction.key").read_bytes()
    log = tmp_path / "access.jsonl"
    # Fixture request keys cannot be inverted. Replay the original native log;
    # the baseline must join through purpose-separated request HMAC.
    log.write_bytes((prepared.parent / "raw/access.log").read_bytes())
    report = nginx_rule_baseline(prepared, log, key, tmp_path / "baseline.json")
    assert report["partition"] == "val"
    assert report["matched_rows"] == 32
    assert report["training_executed"] is False
    assert report["confusion_matrix"] == [[4, 0], [12, 16]]


def test_agent_families_are_observable_features_without_free_text_or_rule_hit_inputs():
    from idps_ai.features.pipeline import FeatureExtractor, feature_columns, fit_spec

    row = {
        "timestamp": 0,
        "client_key": "ip",
        "user_key": None,
        "user_agent": "Mozilla Firefox sqlmap CANARY_SECRET",
    }
    values = FeatureExtractor().observe(row)
    assert values["ua_Firefox"] == 1
    assert values["ua_sqlmap"] == 1
    assert values["user_agent_missing"] == 0
    assert not any("CANARY" in name for name in feature_columns())
    missing = FeatureExtractor().observe({"timestamp": 0})
    assert missing["user_agent_missing"] == 1
    assert fit_spec(iter([values]), feature_columns())["feature_version"] == "ai-features-3"


def test_scanner_product_features_do_not_match_a_benign_substring_name():
    from idps_ai.features.pipeline import FeatureExtractor

    values = FeatureExtractor().observe({"timestamp": 0, "user_agent": "campus-nmaple-browser"})
    assert values["ua_nmap"] == 0
    assert values["user_agent_unknown"] == 1


def test_observer_contract_correction_is_narrow_and_audited(tmp_path):
    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.provenance import observer_labels

    base = {
        "campaign_id": "campaign-a",
        "label": 0,
        "attack_family": "benign",
        "label_source": "scenario_manifest",
        "label_confidence": 1,
        "review_status": "pending",
        "scenario": "benign_catalog",
        "status_code": 403,
        "expected_status_codes": [200],
    }
    observer = tmp_path / "observer.jsonl"
    observer.write_text(
        json.dumps(base | {"request_id": "head-one", "http_method": "HEAD"})
        + "\n"
        + json.dumps(base | {"request_id": "get-one", "http_method": "GET"})
        + "\n"
    )
    capture = tmp_path / "capture.json"
    atomic_json(
        capture,
        {"data_kind": "lab_capture", "observer_sha256": file_sha256(observer), "requests": 2},
    )
    report = observer_labels(observer, capture, tmp_path / "labels", b"K" * 32)
    assert report["approved_rows"] == 1
    assert report["unknown_rows"] == 1
    assert report["outcome_contract_corrections"] == {"benign_HEAD_OPTIONS_catalog_403": 1}


def test_capture_scope_excludes_only_undeclared_warmup_and_keeps_pending_requests(tmp_path):
    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.provenance import scope_capture_inputs

    observer = tmp_path / "observer.jsonl"
    observer.write_text('{"request_id":"observed","review_status":"pending"}\n')
    capture = tmp_path / "capture.json"
    atomic_json(capture, {"observer_sha256": file_sha256(observer), "requests": 1})
    raw = tmp_path / "source.jsonl"
    raw.write_text('{"request_id":"warmup"}\n{"request_id":"observed"}\n')
    result = scope_capture_inputs([Input("nginx", raw)], observer, capture, tmp_path / "scoped")
    assert result["inputs"][0]["excluded_outside_declared_capture"] == 1
    assert result["inputs"][0]["kept"] == 1
    assert (tmp_path / "scoped/00-nginx.jsonl").read_text() == '{"request_id":"observed"}\n'


def test_capacity_uses_inventory_before_the_launcher_cap_without_halving_twice(prepared, tmp_path):
    import os

    from idps_ai.data.capacity import capacity_check
    from idps_ai.training.resources import resource_envelope

    original = sorted(os.sched_getaffinity(0))
    requested = min(2, max(1, len(original) // 2))
    with resource_envelope(requested, 12) as (_, resources):
        report = capacity_check(
            prepared,
            tmp_path / "capacity-capped.json",
            requested,
            effective_cpus_before_cap=resources["effective_cpus_before_cap"],
        )
        assert report["available_cpus_before_cap"] == original
        assert len(report["current_affinity"]) == requested


def test_observer_excludes_decoded_payload_overlap_from_later_holdouts_without_rewriting_logs(
    tmp_path,
):
    import json

    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.provenance import observer_labels

    observer = tmp_path / "observer.jsonl"
    records = []
    for i, (campaign, variant) in enumerate([(0, "a"), (1, "a"), (1, "b"), (2, "c")]):
        records.append(
            {
                "request_id": f"request-{i}",
                "campaign_id": f"fixture-{campaign:02d}",
                "attack_family": "path_traversal",
                "label": 1,
                "label_source": "scenario_manifest",
                "label_confidence": 1.0,
                "review_status": "approved",
                "status_code": 200,
                "expected_status_codes": [200],
                "variant_group": "path_traversal-" + variant * 64,
            }
        )
    observer.write_text("".join(json.dumps(r) + "\n" for r in records))
    before = observer.read_bytes()
    capture = tmp_path / "capture.json"
    atomic_json(
        capture,
        {
            "data_kind": "lab_capture",
            "requests": 4,
            "observer_sha256": file_sha256(observer),
            "query_profile": "safe_query_numeric_v1",
            "campaign_durations": [{"campaign": i, "band": i} for i in range(3)],
        },
    )
    proof = observer_labels(observer, capture, tmp_path / "labels", b"k" * 32)
    assert proof["heldout_overlap_excluded_rows"] == 1
    assert (
        proof["heldout_overlap_exclusions"][0]["reason"] == "decoded_payload_seen_in_earlier_band"
    )
    assert proof["heldout_overlap_exclusions"][0]["earliest_band"] == 0
    assert proof["heldout_overlap_exclusions"][0]["excluded_band"] == 1
    assert proof["approved_rows"] == 3 and proof["unknown_rows"] == 1
    approved = [
        json.loads(line) for line in (tmp_path / "labels/labels.jsonl").read_text().splitlines()
    ]
    assert {r["request_id"] for r in approved} == {"request-0", "request-2", "request-3"}
    assert observer.read_bytes() == before


def test_structural_corpus_excludes_repeated_benign_challenge_labels_in_later_bands(tmp_path):
    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.provenance import observer_labels

    observer = tmp_path / "observer.jsonl"
    values = []
    for i, view in enumerate(("a", "a", "b")):
        values.append(
            {
                "request_id": f"r-{i}",
                "campaign_id": f"campaign-{i:02d}",
                "label": 0,
                "attack_family": "benign",
                "label_source": "scenario_manifest",
                "label_confidence": 1.0,
                "review_status": "approved",
                "status_code": 200,
                "expected_status_codes": [200],
                "scenario": "hard_negative_search",
                "variant_group": "hard_negative-" + view * 64,
            }
        )
    observer.write_text("".join(json.dumps(v) + "\n" for v in values))
    capture = tmp_path / "capture.json"
    atomic_json(
        capture,
        {
            "query_profile": "safe_query_numeric_v2",
            "data_kind": "lab_capture",
            "requests": 3,
            "observer_sha256": file_sha256(observer),
            "campaign_durations": [{"campaign": i, "band": i} for i in range(3)],
        },
    )
    evidence = observer_labels(observer, capture, tmp_path / "labels", b"k" * 32)
    assert evidence["approved_rows"] == 2 and evidence["unknown_rows"] == 1
    assert evidence["heldout_overlap_excluded_rows"] == 1
    assert len(evidence["campaign_hard_negative_groups"]) == 2
