import copy

import pytest

from idps_ai.common import PipelineError


def registry(prepared):
    return {
        "format_version": 1,
        "sources": [
            {
                "id": "fixture-reference",
                "dataset": str(prepared),
                "environment_id": "fixture",
                "collection_kind": "synthetic",
                "authorization_ref": "test-only",
                "review": None,
                "partition_map": {"train": "reference", "val": "reference", "test": "reference"},
            }
        ],
    }


def test_reference_fixture_does_not_unlock_two_million_gate(prepared, tmp_path):
    from idps_ai.data.corpus import audit_catalog

    report = audit_catalog(registry(prepared), tmp_path / "catalog")
    assert report["status"] == "NOT_READY"
    assert report["reference_requests"] == 160
    assert report["eligible_requests"] == 0
    assert not report["formal_training_permitted"]
    assert {"request_volume", "independent_environments", "reviewed_sources"} <= {
        c["id"] for c in report["checks"] if not c["pass"]
    }


def test_capture_replay_and_old_test_to_train_are_rejected(prepared, tmp_path):
    from idps_ai.data.corpus import audit_catalog

    reg = registry(prepared)
    reg["sources"].append(copy.deepcopy(reg["sources"][0]))
    reg["sources"][1]["id"] = "replay-different-name"
    with pytest.raises(PipelineError, match="Duplicate"):
        audit_catalog(reg, tmp_path / "duplicate")
    reg = registry(prepared)
    reg["sources"][0]["partition_map"]["test"] = "train"
    with pytest.raises(PipelineError, match="held-out"):
        audit_catalog(reg, tmp_path / "leak")


def test_automatic_lab_labels_cannot_masquerade_as_independently_reviewed(prepared, tmp_path):
    from idps_ai.data.corpus import audit_catalog

    reg = registry(prepared)
    reg["sources"][0]["collection_kind"] = "scripted_lab"
    reg["sources"][0]["partition_map"]["train"] = "train"
    report = audit_catalog(reg, tmp_path / "lab")
    assert report["eligible_requests"] == 0
    assert report["unreviewed_requests"] > 0
    assert not report["formal_training_permitted"]


def test_shared_scaler_assembly_has_four_roles_and_preserves_sealed_test(prepared, tmp_path):
    from idps_ai.common import load_json
    from idps_ai.data.assembly import assemble
    from idps_ai.data.dataset import iter_rows, verify_dataset

    reg = registry(prepared)
    reg["sources"][0]["partition_map"] = {
        "train": "train",
        "val": "grouped_validation",
        "test": "test",
    }
    output = tmp_path / "assembled"
    result = assemble(reg, output)
    verify_dataset(output, "prepared")
    assert set(result["rows"]) == {"train", "calibration", "val", "test"}
    assert result["feature_rows"] == 160
    assert not result["formal_training_permitted"]
    spec = load_json(output / "feature_spec.json")
    expected_benign = sum(
        r["split"] == "train" and r["label"] == 0 for r in iter_rows(prepared / "requests.parquet")
    )
    assert spec["fit_rows"] == expected_benign
    assert spec["fit_partition"] == "train"
    old_test = {
        r["event_key"] for r in iter_rows(prepared / "requests.parquet") if r["split"] == "test"
    }
    new_test = {
        r["event_key"] for r in iter_rows(output / "requests.parquet") if r["split"] == "test"
    }
    assert new_test == old_test


def test_assembly_rejects_replay_even_with_new_environment_name(prepared, tmp_path):
    from idps_ai.data.assembly import assemble

    reg = registry(prepared)
    reg["sources"][0]["partition_map"] = {
        "train": "train",
        "val": "grouped_validation",
        "test": "test",
    }
    reg["sources"].append(copy.deepcopy(reg["sources"][0]))
    reg["sources"][1].update(id="other-name", environment_id="claimed-other-lab")
    with pytest.raises(PipelineError, match="Duplicate"):
        assemble(reg, tmp_path / "replay")


def test_four_role_training_export_calibrates_without_using_selection_labels(prepared, tmp_path):
    import yaml

    from idps_ai.common import AI_ROOT, load_json
    from idps_ai.data.assembly import assemble
    from idps_ai.export.onnx import export_bundle
    from idps_ai.training.runner import train

    reg = registry(prepared)
    reg["sources"][0]["partition_map"] = {
        "train": "train",
        "val": "grouped_validation",
        "test": "test",
    }
    data = tmp_path / "four"
    assemble(reg, data)
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    train(data, tmp_path / "run", config, epochs=1, max_threads=1)
    export_bundle(
        data,
        tmp_path / "run",
        tmp_path / "bundle",
        max_threads=1,
        evaluation_partition="val",
        independent_validation=True,
    )
    card = load_json(tmp_path / "bundle/model_manifest.json")
    assert card["calibration"]["fit_partition"] == "calibration"
    assert card["evaluation_partition"] == "val"
    assert card["parity"]["rows"] == 160
    import json
    import subprocess
    import sys

    bundle_map = tmp_path / "bundles.json"
    bundle_map.write_text(json.dumps({"toy": str(tmp_path / "bundle")}))
    result = subprocess.run(
        [
            sys.executable,
            str(AI_ROOT / "scripts/compare-operating-points.py"),
            "--dataset",
            str(data),
            "--bundles",
            str(bundle_map),
            "--output",
            str(tmp_path / "operating.json"),
            "--thread-counts",
            "1",
            "--repeats",
            "20",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    comparison = load_json(tmp_path / "operating.json")
    assert comparison["calibration_rows"] == 16
    assert comparison["selection_rows"] == 16
    assert not comparison["test_quality_opened"]
    assert set(comparison["models"]["toy"]["operating_points"]) == {"0.001", "0.005", "0.01"}


def test_two_sources_are_recomputed_instead_of_concatenating_scaled_vectors(prepared, tmp_path):
    import hashlib
    import json
    import shutil

    import pyarrow.parquet as pq

    from idps_ai.common import load_json
    from idps_ai.data.assembly import assemble
    from idps_ai.data.dataset import REQUEST_SCHEMA, iter_rows, manifest, write_rows

    other = tmp_path / "other"
    shutil.copytree(prepared, other)
    changed = []
    for r in iter_rows(prepared / "requests.parquet"):
        for name in (
            "event_key",
            "request_key",
            "client_key",
            "user_key",
            "session_key",
            "campaign_key",
            "group_key",
        ):
            if r[name]:
                r[name] = hashlib.sha256(("second:" + r[name]).encode()).hexdigest()
        r["timestamp"] += 86400
        numbers = json.loads(r["numeric_json"])
        numbers["query_length"] = 10.0
        r["numeric_json"] = json.dumps(numbers)
        changed.append(r)
    write_rows(other / "requests.parquet", changed, REQUEST_SCHEMA)
    table = pq.read_table(other / "features.parquet")
    false_vectors = [{**r, "x": [999.0] * len(r["x"])} for r in table.to_pylist()]
    write_rows(other / "features.parquet", false_vectors, table.schema)
    original = load_json(other / "dataset_manifest.json")
    metadata = {k: v for k, v in original.items() if k not in ("dataset_sha256", "files", "stage")}
    metadata["redaction_key_fingerprint"] = "different-test-key"
    manifest(other, "prepared", list(original["files"]), **metadata)
    reg = registry(prepared)
    reg["sources"][0]["partition_map"] = {
        "train": "train",
        "val": "grouped_validation",
        "test": "test",
    }
    reg["sources"].append(
        {**reg["sources"][0], "id": "second", "dataset": str(other), "environment_id": "other"}
    )
    result = assemble(reg, tmp_path / "both")
    assert result["feature_rows"] == 320
    spec = load_json(tmp_path / "both/feature_spec.json")
    first = [
        json.loads(r["numeric_json"])["query_length"]
        for r in iter_rows(prepared / "requests.parquet")
        if r["split"] == "train" and r["label"] == 0
    ]
    assert spec["mean"][spec["columns"].index("query_length")] == pytest.approx(
        (sum(first) + 10 * len(first)) / (2 * len(first))
    )
    assert all(max(r["x"]) < 999 for r in iter_rows(tmp_path / "both/features.parquet"))
