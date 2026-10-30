import json

from idps_ai.features.request_view import project_request


def test_flat_pkdd_adapter_preserves_binary_annotation_without_guessing_visibility(tmp_path):
    from idps_ai.data.request_corpus import read_pkdd

    f = tmp_path / "pkdd.txt"
    f.write_text(
        "Start - Id: 7\nclass: SqlInjection\nGET /shop?item=1%27OR%201=1 HTTP/1.1\nCookie: canary\n\nEnd - Id: 7\n"
    )
    rows = list(read_pkdd(f, b"k" * 32))
    assert len(rows) == 1
    assert rows[0]["label"] == 1
    assert rows[0]["attack_family"] is None
    assert rows[0]["visibility"] == "request_location_unavailable"
    assert "canary" not in json.dumps(rows)
    assert "timestamp" not in rows[0]


def test_request_corpus_has_one_train_only_scaler_and_never_trains_test_or_unknown(tmp_path):
    from idps_ai.data.dataset import iter_rows
    from idps_ai.data.request_corpus import assemble_requests, verify_requests

    records = []
    for i in range(12):
        split = ["train", "calibration", "val", "test"][i // 3]
        records.append(
            {
                "event_key": str(i),
                "source_id": "fixture",
                "group_key": str(i),
                "split": split,
                "label": None if i == 2 else i % 2,
                "attack_family": "benign" if i % 2 == 0 else None,
                "numbers": project_request(f"/shop?term={i}")["numbers"],
                "visibility": "fixture",
            }
        )
    result = assemble_requests(records, tmp_path / "corpus", {"data_kind": "synthetic_fixture"})
    verify_requests(tmp_path / "corpus")
    assert result["rows"] == {"train": 3, "calibration": 3, "val": 3, "test": 3}
    spec = json.loads((tmp_path / "corpus/feature_spec.json").read_text())
    assert spec["fit_rows"] == 1  # train benign0 only; unknown2 is not benign.
    rows = list(iter_rows(tmp_path / "corpus/features.parquet"))
    assert next(r for r in rows if r["event_key"] == "2")["label"] is None
    assert not result["formal_training_permitted"]
