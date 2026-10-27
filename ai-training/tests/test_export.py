import numpy as np
import pytest
import yaml

from idps_ai.common import AI_ROOT, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.export.onnx import export_bundle, infer_bundle
from idps_ai.inference import InferencePipeline
from idps_ai.training.runner import train


@pytest.mark.parametrize("kind", ["mlp", "autoencoder"])
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
