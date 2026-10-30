import numpy as np
import pytest


@pytest.mark.parametrize("kind", ["deep_mlp", "residual_glu", "denoising_autoencoder"])
def test_request_pilot_resumes_mid_epoch_with_onnx_and_separate_benign_calibration(tmp_path, kind):
    from idps_ai.data.request_corpus import assemble_requests
    from idps_ai.features.request_view import project_request
    from idps_ai.training.checkpoint import load_checkpoint
    from idps_ai.training.request_training import export_request, train_request

    records = []
    for i in range(320):
        role = "train" if i < 280 else "calibration" if i < 300 else "val"
        label = i % 2
        records.append(
            {
                "event_key": str(i),
                "source_id": "student-lab",
                "group_key": str(i),
                "split": role,
                "label": label,
                "attack_family": "sqli" if label else "benign",
                "numbers": project_request(
                    "/api?term=" + ("w%20" * i) + ("%27OR%201=1--" if label else "")
                )["numbers"],
            }
        )
    dataset = tmp_path / "data"
    assemble_requests(records, dataset, {"data_kind": "synthetic_fixture"})
    config = {"kind": kind, "width": 8, "learning_rate": 0.0003, "total_steps": 10}
    run, reference = tmp_path / "run", tmp_path / "reference"
    train_request(dataset, run, config, epochs=2, max_steps=1, cpus=1)
    assert load_checkpoint(run).state["cursor"] > 0
    train_request(dataset, run, config, epochs=2, resume=True, cpus=1)
    train_request(dataset, reference, config, epochs=2, cpus=1)
    a, b = load_checkpoint(run), load_checkpoint(reference)
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    assert a.state["history"] == b.state["history"]
    card = export_request(dataset, run, tmp_path / "bundle", cpus=1)
    assert card["parity"]["all_rows_match"] and card["parity"]["rows"] == 320
    assert card["calibration"]["student-lab"]["benign_count"] == 10
    assert not card["champion_selected"]
    from idps_ai.request_inference import RequestInferencePipeline

    pipeline = RequestInferencePipeline(tmp_path / "bundle", max_threads=1)
    decision = pipeline.observe_uri("/shop?unexpectedKey=hello", "GET")
    assert decision["family_candidate"] is None
    assert decision["enforcement_actions"] == 0
    assert decision["profile"] == "request-structure-v1"


def test_flow_presence_requires_observed_numeric_counters_not_dictionary_shape():
    from idps_ai.request_inference import has_flow_observation

    assert not has_flow_observation({})
    assert not has_flow_observation({"duration_seconds": None, "bytes_to_server": None})
    assert not has_flow_observation({"context_missing": True, "flow_id": 123})
    assert not has_flow_observation({"duration_seconds": "unknown"})
    assert not has_flow_observation({"packets_to_server": float("nan")})
    assert has_flow_observation({"duration_seconds": 0, "bytes_to_server": 0})
    assert has_flow_observation({"packets_to_client": 3})
