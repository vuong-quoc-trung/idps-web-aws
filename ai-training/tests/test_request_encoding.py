import copy

import numpy as np
import pytest


def test_security_encoding_preserves_syntax_without_route_method_or_scale_shortcuts():
    from idps_ai.features.request_encoding import encode_request, security_spec
    from idps_ai.features.request_view import project_request

    spec = security_spec()
    a = project_request("/api/faculties?hint=1%27%20OR%201=1--&pwd=canary", "GET")["numbers"]
    b = dict(a, method_GET=0.0, method_POST=1.0, decoded_uri_length=7000.0)
    x, y = encode_request(spec, a), encode_request(spec, b)
    np.testing.assert_array_equal(x, y)
    assert np.isfinite(x).all() and np.max(abs(x)) <= 1
    assert x[spec["columns"].index("quote_boolean")] > 0
    assert x[spec["columns"].index("sql_line_comment_count")] > 0
    assert not any("method" in k or "length" in k for k in spec["columns"])
    changed = copy.deepcopy(spec)
    changed["encoding"]["implementation_sha256"] = "tampered"
    with pytest.raises(ValueError, match="encoding"):
        encode_request(changed, a)


@pytest.mark.parametrize(
    "encoding,width", [("bounded-security-v1", 45), ("bounded-request-v1", 76)]
)
def test_encoded_corpus_resume_export_and_inference_share_the_same_preprocessing(
    tmp_path, encoding, width
):
    import json

    from idps_ai.data.request_corpus import assemble_requests
    from idps_ai.features.request_view import project_request
    from idps_ai.request_inference import RequestInferencePipeline
    from idps_ai.training.checkpoint import load_checkpoint
    from idps_ai.training.request_training import export_request, train_request

    records = []
    for i in range(240):
        label = int(i % 3 == 0)
        role = "train" if i < 200 else "calibration" if i < 220 else "val"
        numbers = project_request("/shop?term=" + ("x" * i) + ("' OR 1=1--" if label else "hello"))[
            "numbers"
        ]
        records.append(
            dict(
                event_key=str(i),
                source_id="student-lab" if i % 2 == 0 or label else "public-normal",
                group_key=str(i),
                split=role,
                label=label,
                attack_family="sqli" if label else "benign",
                numbers=numbers,
            )
        )
    data = tmp_path / "data"
    manifest = assemble_requests(
        records, data, {"data_kind": "synthetic_fixture"}, encoding=encoding
    )
    assert manifest["feature_count"] == width
    spec = json.loads((data / "feature_spec.json").read_text())
    assert spec["fit_rows"] == 0  # Fixed transform; no fitted public/test moments.
    config = dict(
        kind="deep_mlp",
        width=8,
        learning_rate=0.0003,
        total_steps=8,
        training_pool="multisource_benign",
        sampling="source_family_balanced",
        family_weight=0.0,
    )
    train_request(data, tmp_path / "resumed", config, max_steps=1, cpus=1)
    train_request(data, tmp_path / "resumed", config, resume=True, cpus=1)
    train_request(data, tmp_path / "continuous", config, cpus=1)
    a, b = load_checkpoint(tmp_path / "resumed"), load_checkpoint(tmp_path / "continuous")
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    card = export_request(data, tmp_path / "resumed", tmp_path / "bundle", cpus=1)
    assert card["parity"]["all_rows_match"]
    pipeline = RequestInferencePipeline(tmp_path / "bundle", max_threads=1)
    assert np.isfinite(pipeline.observe_uri("/different?hint=hello")["score"])
    assert pipeline.observe_uri("/?token=canary")["enforcement_actions"] == 0
    # Public cohort evaluator must retain the full sample and keep dedup a
    # separate sensitivity analysis. All fixtures here are explicitly synthetic.
    import importlib.util
    from pathlib import Path

    from idps_ai.common import atomic_json, file_sha256
    from idps_ai.data.dataset import write_rows
    from idps_ai.data.real_http import SCHEMA
    from idps_ai.features.request_view import fingerprint

    module_spec = importlib.util.spec_from_file_location(
        "cohort_eval",
        Path(__file__).resolve().parents[1] / "scripts/evaluate-request-generalization.py",
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    lab, real = tmp_path / "lab", tmp_path / "real"
    lab.mkdir()
    real.mkdir()
    observations = []
    events = []
    targets = ["/public?hint=hello", "/public?hint=1%27OR%201=1--"]
    for i, target in enumerate(targets):
        rid = str(i)
        observations.append(
            dict(
                request_id=rid,
                label=i,
                attack_family="sqli" if i else "benign",
                review_status="approved",
            )
        )
        events.append(
            dict(
                event_type="http", http={"request_id": rid}, ai_request_view=project_request(target)
            )
        )
    (lab / "observer.jsonl").write_text("".join(json.dumps(r) + "\n" for r in observations))
    for name in ("student-audit.log", "access.log"):
        (lab / name).write_text(
            "".join(json.dumps({"request_id": str(i)}) + "\n" for i in range(2))
        )
    eve = tmp_path / "eve.json"
    eve.write_text("".join(json.dumps(r) + "\n" for r in events))
    source_rows = [
        dict(
            event_key=str(i),
            natural_key="normal" if i < 2 else "attack",
            client_key="privatehash",
            timestamp=1594985014.0,
            label=int(i == 2),
            attack_family=None if i == 2 else "benign",
            published_capec=["66"] if i == 2 else [],
            label_state="consistent_publisher_annotation",
            timestamp_state="observed",
            body_present=False,
            numbers_json=json.dumps(project_request(targets[int(i == 2)])["numbers"]),
            projection_state="available",
        )
        for i in range(3)
    ]
    write_rows(real / "sample.parquet", source_rows, SCHEMA)
    atomic_json(
        real / "manifest.json",
        dict(
            projection_sha256=fingerprint(),
            files={"sample.parquet": file_sha256(real / "sample.parquet")},
            sample_records=3,
        ),
    )
    selection = tmp_path / "selection.json"
    atomic_json(selection, {"test_quality_opened": False})
    registry = tmp_path / "registry.json"
    atomic_json(
        registry,
        dict(
            selection=str(selection),
            selection_sha256=file_sha256(selection),
            selected_research_candidate=None,
            models={
                "fixture": dict(
                    bundle=str(tmp_path / "bundle"),
                    dataset=str(data),
                    manifest_sha256=file_sha256(tmp_path / "bundle/model_manifest.json"),
                    config=config,
                )
            },
        ),
    )
    report = module.run(registry, real, lab, eve, tmp_path / "evaluation")
    metrics = json.loads((tmp_path / "evaluation/public-results.json").read_text())["models"][
        "fixture"
    ]
    assert metrics["full_publisher_sample"]["rows"] == 3
    assert metrics["unambiguous_unique_observation_sensitivity"]["rows"] == 2
    assert report["champion_selected"] is False and report["enforcement_actions"] == 0
    with pytest.raises(ValueError, match="already exists"):
        module.benchmark_latency(registry, tmp_path / "evaluation/public-results.json")


def test_source_family_sampler_balances_groups_without_fabricating_training_rows():
    from idps_ai.training.request_training import training_permutation

    binary = np.array([0] * 100 + [0] * 1000 + [1] * 50 + [1] * 500)
    sources = np.array(["lab"] * 100 + ["public"] * 1000 + ["lab"] * 550)
    families = np.array([0] * 1100 + [1] * 50 + [2] * 500)
    a = training_permutation(
        np.random.default_rng(17), binary, families, sources, "source_family_balanced"
    )
    b = training_permutation(
        np.random.default_rng(17), binary, families, sources, "source_family_balanced"
    )
    np.testing.assert_array_equal(a, b)
    assert len(a) == len(binary) and 0 <= min(a) <= max(a) < len(binary)
    assert 0.45 < np.mean(binary[a] == 1) < 0.55
    assert 0.20 < np.mean((binary[a] == 0) & (sources[a] == "lab")) < 0.30
    assert 0.20 < np.mean(families[a] == 1) < 0.30


def test_calibration_audit_measures_probability_quality_without_selecting_a_cutoff():
    from idps_ai.training.generalization import calibration_audit

    report = calibration_audit([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], bins=2)
    assert report["brier"] == pytest.approx(0.025)
    assert report["ece_equal_width"] == pytest.approx(0.15)
    assert report["negative_log_likelihood"] == pytest.approx(-np.log(0.9 * 0.8) / 2)
    assert report["threshold_selected"] is False
    with pytest.raises(ValueError):
        calibration_audit([0], [1.5])  # AE reconstruction scores are not probabilities.


def test_full_bounded_encoding_keeps_information_discarded_by_security_ablation():
    from idps_ai.features.request_preprocessing import bounded_spec, encode_request
    from idps_ai.features.request_view import project_request

    spec = bounded_spec()
    a = project_request("/shop?term=hello", "GET")["numbers"]
    b = dict(a, method_GET=0.0, method_POST=1.0, decoded_uri_length=7000.0)
    x, y = encode_request(spec, a), encode_request(spec, b)
    assert x.shape == (76,) and np.isfinite(x).all() and np.max(x) <= 1
    assert not np.array_equal(x, y)
    assert x[spec["columns"].index("method_GET")] == 1
    with pytest.raises(ValueError, match="encoding"):
        encode_request(dict(spec, encoding={"name": "forged"}), a)
