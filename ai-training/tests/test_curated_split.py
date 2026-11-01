import pytest

from idps_ai.features.request_view import project_request


def record(i, split, view, label=0, source="fixture", group=None, ts=None):
    return dict(
        event_key=str(i),
        source_id=source,
        proposed_split=split,
        group_key=group or f"g{i}",
        client_key=f"c{i}",
        timestamp=ts or {"train": 1000, "calibration": 2000, "val": 3000}[split],
        label=label,
        attack_family="sqli" if label else "benign",
        numbers=project_request("/shop?term=" + view)["numbers"],
    )


def test_grouped_admission_never_moves_a_future_or_related_request_into_training(tmp_path):
    from idps_ai.data.curated_split import assemble_curated
    from idps_ai.data.dataset import iter_rows

    rows = [
        record(0, "train", "hello"),
        record(1, "calibration", "hello"),
        record(2, "calibration", "independent benign calibration"),
        record(3, "val", "independent benign validation"),
        record(4, "train", "' OR 1=1--", 1),
        record(5, "calibration", "' UNION SELECT 42--", 1),
        record(6, "val", "7 HAVING COUNT(*)>0#", 1),
        record(7, "val", "grouplink", group="g0"),
    ]
    manifest = assemble_curated(
        rows, tmp_path / "data", provenance={"data_kind": "synthetic_fixture"}, min_sources=1
    )
    assert manifest["admission"]["cross_partition_model_vectors"] == 0
    assert manifest["admission"]["cross_partition_groups"] == 0
    requests = list(iter_rows(tmp_path / "data/requests.parquet"))
    assert next(r for r in requests if r["event_key"] == "0")["split"] == "train"
    assert not {"1", "7"} & {r["event_key"] for r in requests}
    decisions = list(iter_rows(tmp_path / "data/split-decisions.parquet"))
    assert next(r for r in decisions if r["event_key"] == "1")["reasons"] == [
        "model_view_cross_partition"
    ]
    assert (
        "related_group_cross_partition"
        in next(r for r in decisions if r["event_key"] == "7")["reasons"]
    )
    assert manifest["admission"]["research_training_permitted"] is True
    assert manifest["admission"]["formal_training_permitted"] is False


def test_temporal_gap_failure_cannot_become_research_ready(tmp_path):
    from idps_ai.data.curated_split import assemble_curated

    rows = [
        record(0, "train", "benign", ts=1000),
        record(1, "train", "' OR 1=1--", 1, ts=1001),
        record(2, "calibration", "another", ts=1050),
        record(3, "calibration", "' UNION SELECT 7--", 1, ts=1051),
        record(4, "val", "validation different", ts=1100),
        record(5, "val", "7 HAVING COUNT(*)>0#", 1, ts=1101),
    ]
    result = assemble_curated(
        rows, tmp_path / "data", provenance={"data_kind": "synthetic_fixture"}, min_sources=1
    )
    assert result["admission"]["research_training_permitted"] is False
    assert "temporal_embargo" in result["admission"]["failed_gates"]


def test_curated_multisource_positive_training_requires_bound_admission(tmp_path):
    import numpy as np

    from idps_ai.data.curated_split import assemble_curated
    from idps_ai.data.request_corpus import verify_requests
    from idps_ai.training.request_training import selected_training, training_permutation

    rows = []
    for s, source in enumerate(["student-lab", "real-reviewed"]):
        for p, role in enumerate(["train", "calibration", "val"]):
            rows.append(
                record(
                    f"{s}-{p}-0",
                    role,
                    "readable words " + ("abc " * (s * 3 + p + 1)),
                    source=source,
                    ts=1000 + p * 1000,
                )
            )
            rows.append(
                record(
                    f"{s}-{p}-1",
                    role,
                    "' OR " + str(10 + s * 9 + p) + "=" + str(10 + s * 9 + p) + "--" + (" " * p),
                    1,
                    source=source,
                    ts=1001 + p * 1000,
                )
            )
    data = tmp_path / "corpus"
    result = assemble_curated(
        rows, data, provenance={"data_kind": "synthetic_fixture"}, min_sources=2
    )
    verify_requests(data)
    config = dict(
        training_pool="curated_multisource", training_sources=["student-lab", "real-reviewed"]
    )
    x, y, f, s = selected_training(data, "deep_mlp", config, True)
    assert set(s[y == 1]) == {"student-lab", "real-reviewed"}
    sampled = training_permutation(np.random.default_rng(17), y, f, s, "domain_family_balanced")
    assert len(sampled) == len(x) and max(sampled) < len(x)
    assert result["admission"]["research_training_permitted"]


def test_source_without_temporally_held_out_positives_is_not_admitted(tmp_path):
    from idps_ai.data.curated_split import assemble_curated

    rows = []
    for s, source in enumerate(["student-lab", "second-source"]):
        for i, role in enumerate(["train", "calibration", "val"]):
            rows.append(
                record(
                    f"{s}-{i}-0",
                    role,
                    "harmless " + ("abcde " * (s * 4 + i + 1)),
                    source=source,
                    ts=1000 + i * 1000,
                )
            )
            if s == 0 or role == "train":
                rows.append(
                    record(
                        f"{s}-{i}-1",
                        role,
                        "' OR "
                        + str(123 + s * 80 + i)
                        + "="
                        + str(123 + s * 80 + i)
                        + "--"
                        + (" " * i),
                        1,
                        source=source,
                        ts=1001 + i * 1000,
                    )
                )
    result = assemble_curated(
        rows, tmp_path / "incomplete", provenance={"data_kind": "synthetic_fixture"}, min_sources=2
    )
    assert result["admission"]["research_training_permitted"] is False
    assert "source_role_class_coverage" in result["admission"]["failed_gates"]
    from idps_ai.training.request_training import train_request

    with pytest.raises(ValueError, match="admission"):
        train_request(
            tmp_path / "incomplete",
            tmp_path / "blocked-run",
            dict(
                kind="deep_mlp",
                width=8,
                learning_rate=0.0003,
                total_steps=2,
                training_pool="curated_multisource",
                training_sources=["student-lab", "second-source"],
                sampling="domain_family_balanced",
            ),
            cpus=1,
        )
    assert not (tmp_path / "blocked-run/latest.json").exists()


@pytest.mark.parametrize("kind", ["deep_mlp", "residual_glu"])
def test_admitted_fixture_domain_sampler_resumes_and_exports_exactly(tmp_path, kind):
    import numpy as np

    from idps_ai.data.curated_split import assemble_curated
    from idps_ai.training.checkpoint import load_checkpoint
    from idps_ai.training.request_training import export_request, train_request

    rows = []
    for s, source in enumerate(["student-lab", "real-source"]):
        for i, role in enumerate(["train", "calibration", "val"]):
            rows.append(
                record(
                    f"{s}-{i}-0",
                    role,
                    "normal words " + ("abc " * (s * 4 + i + 1)),
                    source=source,
                    ts=1000 + i * 1000,
                )
            )
            rows.append(
                record(
                    f"{s}-{i}-1",
                    role,
                    "' OR " + str(77 + s * 13 + i) + "=" + str(77 + s * 13 + i) + "--" + (" " * i),
                    1,
                    source=source,
                    ts=1001 + i * 1000,
                )
            )
    data = tmp_path / "data"
    assemble_curated(rows, data, provenance={"data_kind": "synthetic_fixture"}, min_sources=2)
    config = dict(
        kind=kind,
        width=8,
        learning_rate=0.0003,
        total_steps=2,
        warmup_steps=1,
        training_pool="curated_multisource",
        training_sources=["student-lab", "real-source"],
        sampling="domain_family_balanced",
    )
    train_request(data, tmp_path / "resumed", config, max_steps=1, cpus=1)
    train_request(data, tmp_path / "resumed", config, resume=True, cpus=1)
    train_request(data, tmp_path / "continuous", config, cpus=1)
    a, b = load_checkpoint(tmp_path / "resumed"), load_checkpoint(tmp_path / "continuous")
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    assert a.state["history"] == b.state["history"]
    card = export_request(data, tmp_path / "resumed", tmp_path / "bundle", cpus=1)
    assert card["parity"]["all_rows_match"] and card["parity"]["rows"] == 12


def test_partition_audit_reports_source_family_group_time_and_novelty(tmp_path):
    from idps_ai.data.curated_split import assemble_curated, audit_curated_partitions

    rows = []
    for i, role in enumerate(["train", "calibration", "val"]):
        rows.extend(
            [
                record(str(i) + "b", role, "words " * (i + 1)),
                record(
                    str(i) + "a", role, "' UNION SELECT " + str(123456 + i * 10) + "--" + " " * i, 1
                ),
            ]
        )
    dataset = tmp_path / "data"
    assemble_curated(rows, dataset, {"data_kind": "synthetic_fixture"}, min_sources=1)
    audit = audit_curated_partitions(dataset)
    assert audit["status"] == "PASS"
    assert audit["records"] == 6
    assert audit["cross_partition_model_views"] == audit["cross_partition_groups"] == 0
    assert len(audit["by_source_partition_family"]) == 6
    assert len(audit["by_group"]) == 6
    assert audit["source_role_class_coverage"]
    assert audit["per_source_time_gaps_seconds"]["fixture"]["train->calibration"] == 1000
    assert audit["per_source_time_gaps_seconds"]["fixture"]["calibration->val"] == 1000
    assert audit["fresh_final_test_quality_opened"] is False


def test_repeated_vectors_cannot_satisfy_minimum_independent_view_support(tmp_path):
    from idps_ai.data.curated_split import assemble_curated

    rows = []
    for i, role in enumerate(["train", "calibration", "val"]):
        for repeat in range(2):
            rows.extend(
                [
                    record(f"{i}-{repeat}b", role, "words " * (i + 1)),
                    record(
                        f"{i}-{repeat}a",
                        role,
                        "' UNION SELECT " + str(123456 + i * 10) + "--" + " " * i,
                        1,
                    ),
                ]
            )
    result = assemble_curated(
        rows,
        tmp_path / "data",
        {"data_kind": "synthetic_fixture"},
        min_sources=1,
        minimum_class_rows=2,
    )
    assert result["admission"]["research_training_permitted"] is False
    assert "source_role_unique_view_support" in result["admission"]["failed_gates"]


def test_curated_study_orchestrates_fixed_resume_calibration_and_baseline_without_test(tmp_path):
    import importlib.util
    from pathlib import Path

    from idps_ai.data.curated_split import assemble_curated

    rows = []
    for s, source in enumerate(["student-lab", "real-source"]):
        for i, role in enumerate(["train", "calibration", "val"]):
            rows.extend(
                [
                    record(f"{s}-{i}b", role, "words " * (s * 4 + i + 1), source=source),
                    record(
                        f"{s}-{i}a",
                        role,
                        "' UNION SELECT 1--" + " " * (s * 4 + i),
                        1,
                        source=source,
                    ),
                ]
            )
    data = tmp_path / "data"
    assemble_curated(rows, data, {"data_kind": "synthetic_fixture"}, min_sources=2)
    path = Path(__file__).resolve().parents[1] / "scripts/study-curated-http.py"
    spec = importlib.util.spec_from_file_location("curated_study_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run(data, tmp_path / "study", cpus=1, candidates=[("tiny", "residual_glu", 8)])
    assert result["status"] == "PASS_TECHNICAL_DEVELOPMENT_ONLY"
    assert not result["fresh_test_quality_opened"] and not result["champion_selected"]
    model = result["models"]["tiny"]
    assert model["exact_resume"] and model["parity"]["rows"] == 12
    assert model["training"]["steps"] == 300
    assert set(model["validation"]["by_source"]) == {"student-lab", "real-source"}
    assert not model["validation"]["threshold_changed_from_calibration"]
    assert "logistic" in result["models"]


def test_pilot_caps_cannot_silently_remove_class_coverage(tmp_path):
    from idps_ai.data.curated_split import assemble_curated

    rows = []
    for i, role in enumerate(["train", "calibration", "val"]):
        rows.extend(
            [
                record(f"{i}b", role, "words " * (i + 1)),
                record(f"{i}a", role, "' UNION SELECT 1--" + " " * i, 1),
            ]
        )
    result = assemble_curated(
        rows,
        tmp_path / "data",
        {"data_kind": "synthetic_fixture"},
        min_sources=1,
        cap_per_source_role={r: 1 for r in ["train", "calibration", "val"]},
    )
    assert result["admission"]["research_training_permitted"] is False
    assert "pilot_source_role_support" in result["admission"]["failed_gates"]


def test_binary_public_annotations_do_not_need_invented_attack_families(tmp_path):
    from idps_ai.data.curated_split import assemble_curated, audit_curated_partitions

    rows = []
    for i, role in enumerate(["train", "calibration", "val"]):
        positive = record(f"{i}a", role, "' UNION SELECT 1--" + " " * i, 1)
        positive["attack_family"] = None
        rows.extend([record(f"{i}b", role, "words " * (i + 1)), positive])
    dataset = tmp_path / "data"
    assemble_curated(rows, dataset, {"data_kind": "synthetic_fixture"}, min_sources=1)
    audit = audit_curated_partitions(dataset)
    assert audit["records"] == 6
    assert sum(r["rows"] for r in audit["by_source_partition_family"] if r["family"] is None) == 3
