import io
import json
import zipfile

import pytest


def test_request_array_streaming_keeps_chunk_boundaries_and_rejects_bad_json():
    from idps_ai.data.wcp import request_array

    data = json.dumps([{"url": "/?q=tiếng Việt", "method": "GET"}, {"url": "/"}]).encode()
    assert len(list(request_array(io.BytesIO(data), chunk_bytes=7))) == 2
    for invalid in [b"{}", b"[{},]", b"[{}]extra", b"[{", b"[true]"]:
        with pytest.raises(ValueError):
            list(request_array(io.BytesIO(invalid), chunk_bytes=7))


def test_oversized_capture_object_is_quarantined_and_next_request_is_still_read():
    from idps_ai.data.wcp import request_array

    source = json.dumps(
        [{"url": "/first"}, {"data": 'nested { \\" } ' * 300}, {"url": "/last"}]
    ).encode()
    rows = list(request_array(io.BytesIO(source), chunk_bytes=31, max_record_chars=200))
    assert rows == [{"url": "/first"}, None, {"url": "/last"}]


def test_public_capture_import_keeps_reserved_sites_unread_and_secrets_out(tmp_path):
    from idps_ai.common import file_sha256
    from idps_ai.data.dataset import iter_rows
    from idps_ai.data.wcp import import_legitimate, site_role

    key = b"z" * 32
    names = {}
    for i in range(100):
        name = f"Legitimate/website{i}.json"
        names.setdefault(site_role(key, name), name)
    archive = tmp_path / "original.zip"
    request = {
        "method": "GET",
        "url": "/catalog?q=hello&token=canary-secret",
        "headers": {"Cookie": "canary-cookie"},
        "data": "canary-body",
    }
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(names["reserved_holdout"], "unread-invalid-json")
        z.writestr(names["validation"], json.dumps([request, request]))
    output = tmp_path / "corpus"
    report = import_legitimate(archive, output, key, file_sha256(archive), project_modulus=1)
    assert report["source_records_audited"] == 2
    assert report["distinct_request_signatures"] == 1
    assert report["duplicate_records"] == 1
    assert report["reserved_members_unopened"] == 1
    assert report["reserved_request_count"] is None
    assert report["formal_training_permitted"] is False
    rows = list(iter_rows(output / "observations.parquet"))
    assert (
        len(rows) == 1
        and rows[0]["label"] == 0
        and rows[0]["label_source"] == "publisher_legitimate_capture"
    )
    assert rows[0]["timestamp"] is None and rows[0]["split"] == "validation"
    assert "canary" not in json.dumps(rows) + json.dumps(report)
    decisions = list(iter_rows(output / "decisions.parquet"))
    assert len(decisions) == 2
    duplicate = next(r for r in decisions if r["decision"] == "duplicate")
    assert duplicate["duplicate_of"] == rows[0]["event_key"]
    assert not (tmp_path / "Legitimate").exists()


def test_capture_import_refuses_path_traversal_and_wrong_source_hash(tmp_path):
    from idps_ai.common import file_sha256
    from idps_ai.data.wcp import import_legitimate

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../site.json", "[]")
    with pytest.raises(ValueError, match="Unsafe"):
        import_legitimate(archive, tmp_path / "out", b"z" * 32, file_sha256(archive))
    with pytest.raises(ValueError, match="SHA"):
        import_legitimate(archive, tmp_path / "out2", b"z" * 32, "wrong")


def test_frozen_benign_evaluation_preserves_weights_thresholds_and_reserved_members(tmp_path):
    import importlib.util
    from pathlib import Path

    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.curated_split import assemble_curated
    from idps_ai.data.wcp import import_legitimate, site_role
    from idps_ai.features.request_view import project_request
    from idps_ai.training.request_training import export_request, train_request

    rows = []
    for i, split in enumerate(["train", "calibration", "val"]):
        for label in (0, 1):
            target = "/?q=" + ("hello " * (i + 1) if not label else "' UNION SELECT 1--" + " " * i)
            rows.append(
                dict(
                    event_key=f"{i}-{label}",
                    source_id="student-lab",
                    group_key=f"g{i}-{label}",
                    proposed_split=split,
                    label=label,
                    attack_family="sqli" if label else "benign",
                    timestamp=1000 + i * 1000,
                    numbers=project_request(target)["numbers"],
                )
            )
    data = tmp_path / "data"
    assemble_curated(rows, data, {"data_kind": "synthetic_fixture"}, min_sources=1)
    train_request(
        data,
        tmp_path / "run",
        dict(kind="deep_mlp", width=8, learning_rate=0.001, total_steps=2, warmup_steps=1),
        cpus=1,
    )
    bundle = tmp_path / "bundle"
    card = export_request(data, tmp_path / "run", bundle, cpus=1)
    key = b"z" * 32
    names = {}
    for i in range(100):
        n = f"Legitimate/site{i}.json"
        names.setdefault(site_role(key, n), n)
    archive = tmp_path / "public.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(names["reserved_holdout"], "unread malformed JSON")
        z.writestr(
            names["validation"],
            json.dumps([dict(url="/?q=book", method="GET", headers={}, data="")]),
        )
    import_legitimate(archive, tmp_path / "public", key, file_sha256(archive), project_modulus=1)
    before = file_sha256(bundle / "model.onnx")
    registry = tmp_path / "registry.json"
    atomic_json(
        registry,
        {
            "evaluate_role": "validation",
            "reserved_websites_unopened": True,
            "no_HPO_or_new_training": True,
            "models": {
                "tiny": {
                    "bundle": str(bundle),
                    "onnx_sha256": before,
                    "manifest_sha256": file_sha256(bundle / "model_manifest.json"),
                    "threshold": card["threshold"],
                }
            },
        },
    )
    spec = importlib.util.spec_from_file_location(
        "wcp_eval", Path(__file__).resolve().parents[1] / "scripts/evaluate-wcp-http.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.run(tmp_path / "public", registry, tmp_path / "eval", cpus=1)
    assert report["rows"] == 1 and report["reserved_members_opened"] is False
    assert report["models"]["tiny"]["primary_all_sampled_validation"]["metrics"]["recall"] is None
    assert report["models"]["tiny"]["threshold_changed"] is False
    assert file_sha256(bundle / "model.onnx") == before
