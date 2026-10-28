import numpy as np
import pytest
import yaml

from idps_ai.common import AI_ROOT, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.export.onnx import export_bundle, infer_bundle
from idps_ai.inference import InferencePipeline
from idps_ai.training.runner import train


@pytest.mark.parametrize("kind", ["mlp", "autoencoder", "residual"])
def test_onnx_matches_every_prepared_row_and_detects_artifact_tampering(prepared, tmp_path, kind):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    config["model"].update(kind=kind, hidden_dim=8)
    run = tmp_path / "run"
    train(prepared, run, config, epochs=1, max_threads=1)
    result = export_bundle(prepared, run, tmp_path / "bundle")
    assert result["parity"]["all_rows_match"]
    assert result["parity"]["rows"] > 0
    assert result["parity"]["rows"] == load_json(prepared / "dataset_manifest.json")["feature_rows"]
    assert result["calibration"]["fit_partition"] == "val"
    sample = np.zeros((1, result["input_shape"][1]), dtype=np.float32)
    assert infer_bundle(tmp_path / "bundle", sample)[0].shape == (1,)
    expected = {
        row["event_key"]: row["x"]
        for row in iter_rows(prepared / "features.parquet")
        if row["split"] == "train"
    }
    online = InferencePipeline(tmp_path / "bundle")
    for row in iter_rows(prepared / "requests.parquet"):
        if row["split"] != "train":
            continue
        observed = online.observe(row, include_features=True)
        np.testing.assert_array_equal(observed["feature_vector"], expected[row["event_key"]])
    (tmp_path / "bundle/model.onnx").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        infer_bundle(tmp_path / "bundle", sample)


def test_pilot_bundle_keeps_test_metrics_sealed(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/residual_config.yaml").read_text())
    train(prepared, tmp_path / "run", config, epochs=1, max_threads=1)
    report = export_bundle(
        prepared, tmp_path / "run", tmp_path / "bundle", evaluation_partition="val"
    )
    metrics = load_json(tmp_path / "bundle/evaluation.json")
    assert metrics["partition"] == "val"
    assert metrics["final_test_metrics_computed"] is False
    assert report["calibration"]["fit_partition"] == "val"
    assert report["parity"]["all_rows_match"] is True


def test_autoencoder_parity_with_wide_magnitude_inputs_keeps_strict_tolerance(tmp_path):
    import onnx

    from idps_ai.export.onnx import cpu_session, graph_for
    from idps_ai.training.models import Model

    model = Model(148, 32, "autoencoder", 17)
    x = np.random.default_rng(37).uniform(-20, 20, size=(4096, 148)).astype(np.float32)
    path = tmp_path / "wide.onnx"
    onnx.save_model(graph_for(model), path)
    session = cpu_session(path, 1)
    for start in range(0, len(x), 512):
        batch = x[start : start + 512]
        for native, exported in zip(model.predict(batch), session.run(None, {"input": batch})):
            np.testing.assert_allclose(native, exported, rtol=1e-5, atol=1e-6)
