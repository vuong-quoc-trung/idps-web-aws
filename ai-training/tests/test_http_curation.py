from idps_ai.features.request_view import project_request


def observation(
    i,
    *,
    label=0,
    natural=None,
    view="hello",
    timestamp=1594985014.0,
    client="client",
    family="benign",
    body=False,
):
    return dict(
        event_key=f"e{i}",
        natural_key=natural or f"n{i}",
        client_key=client,
        timestamp=timestamp,
        label=label,
        attack_family=family,
        published_capec=[] if label == 0 else ["66"],
        label_state="consistent_publisher_annotation",
        body_present=body,
        numbers=project_request("/shop?term=" + view)["numbers"],
        projection_state="available",
    )


def test_curation_preserves_original_labels_and_accounts_for_every_rejected_record(tmp_path):
    from idps_ai.data.http_curation import curate_records

    rows = [
        observation(0),
        observation(1, natural="n0"),
        observation(2, label=0, natural="conflict", view="same"),
        observation(3, label=1, natural="conflict", view="' OR 1=1--", family="sqli"),
        observation(4, timestamp=None),
        observation(5, timestamp=1604267991.0),
        observation(6, view="a different longer term"),
        observation(7, label=1, view="' UNION SELECT 42--", family="sqli"),
        observation(8, body=True, view="body only"),
    ]
    manifest = curate_records(
        rows,
        tmp_path / "curated",
        source_id="test-source",
        provenance={"data_kind": "synthetic_fixture"},
    )
    assert manifest["input_records"] == 9
    assert manifest["decisions"]["accepted_research"] == 3
    assert sum(manifest["decisions"].values()) == 9
    from idps_ai.data.dataset import iter_rows

    decisions = list(iter_rows(tmp_path / "curated/decisions.parquet"))
    assert {r["event_key"] for r in decisions if r["decision"] == "accepted_research"} == {
        "e0",
        "e6",
        "e7",
    }
    reasons = {r["event_key"]: r["reasons"] for r in decisions}
    assert "duplicate_observation" in reasons["e1"]
    assert (
        "contradictory_observation_labels" in reasons["e2"]
        and "contradictory_observation_labels" in reasons["e3"]
    )
    assert "missing_timestamp" in reasons["e4"] and "outside_documented_time_range" in reasons["e5"]
    assert "body_view_unavailable" in reasons["e8"]
    assert next(r for r in decisions if r["event_key"] == "e3")["original_label"] == 1
    assert not manifest["production_admitted"] and not manifest["independent_human_review"]


def test_curation_quarantines_conflicting_model_views_without_relabeling(tmp_path):
    from idps_ai.data.dataset import iter_rows
    from idps_ai.data.http_curation import curate_records

    a = observation(0, view="hello")
    b = dict(observation(1, label=1, family="sqli"), numbers=a["numbers"])
    manifest = curate_records(
        [a, b],
        tmp_path / "curated",
        source_id="fixture",
        provenance={"data_kind": "synthetic_fixture"},
    )
    assert manifest["decisions"]["quarantine"] == 2
    assert all(
        "contradictory_model_view_labels" in r["reasons"]
        for r in iter_rows(tmp_path / "curated/decisions.parquet")
    )


def test_curated_outputs_are_immutable_and_detect_tampered_decisions(tmp_path):
    import pytest

    from idps_ai.data.http_curation import curate_records, verify_curation

    output = tmp_path / "curated"
    curate_records([observation(0)], output, "fixture", {"data_kind": "synthetic_fixture"})
    assert verify_curation(output)["input_records"] == 1
    with pytest.raises(ValueError, match="exists"):
        curate_records([observation(1)], output, "fixture", {"data_kind": "synthetic_fixture"})
    with (output / "decisions.parquet").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        verify_curation(output)


def test_sealed_holdout_marker_blocks_development_import_before_any_rows_are_read(tmp_path):
    import json

    import pytest

    from idps_ai.data.http_curation import require_development_source

    source = tmp_path / "reserved"
    source.mkdir()
    (source / "AI_HOLDOUT.json").write_text(
        json.dumps({"role": "sealed_final", "model_scores_opened": False})
    )
    file = source / "observer.jsonl"
    file.write_text("not a training source\n")
    with pytest.raises(ValueError, match="holdout"):
        require_development_source(file)
    with pytest.raises(ValueError, match="holdout"):
        require_development_source(source)
    ordinary = tmp_path / "development.csv"
    ordinary.write_text("fixture")
    require_development_source(ordinary)


def test_unknown_annotation_is_not_misreported_as_a_contradictory_label(tmp_path):
    from idps_ai.data.dataset import iter_rows
    from idps_ai.data.http_curation import curate_records

    row = observation(0, label=None, family=None)
    row["label_state"] = "missing_publisher_labels"
    curate_records([row], tmp_path / "unknown", "fixture", {"data_kind": "synthetic_fixture"})
    decision = next(iter_rows(tmp_path / "unknown/decisions.parquet"))
    assert decision["decision"] == "quarantine"
    assert "unknown_or_conflicting_record_label" in decision["reasons"]
    assert "contradictory_observation_labels" not in decision["reasons"]


def test_research_evaluator_refuses_a_sealed_cohort_before_opening_registry(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    import pytest

    path = Path(__file__).resolve().parents[1] / "scripts/evaluate-request-generalization.py"
    spec = importlib.util.spec_from_file_location("sealed_evaluator_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lab = tmp_path / "sealed"
    lab.mkdir()
    (lab / "AI_HOLDOUT.json").write_text(json.dumps({"role": "sealed_final"}))
    with pytest.raises(ValueError, match="holdout"):
        module.run(
            tmp_path / "not-opened-registry.json",
            tmp_path / "public",
            lab,
            tmp_path / "eve",
            tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
