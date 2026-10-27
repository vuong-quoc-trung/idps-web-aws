from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper, numpy_helper

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256, fsync_dir, load_json
from idps_ai.data.dataset import verify_dataset
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.evaluation import evaluate, latency_ms, threshold_at_fpr
from idps_ai.training.runner import environment_identity, load_arrays, predict_batches


def graph_for(model):
    initializers = [
        numpy_helper.from_array(array, name) for name, array in model.parameters.items()
    ]
    nodes = [
        helper.make_node("Gemm", ["input", "W1", "b1"], ["hidden_linear"]),
        helper.make_node("Relu", ["hidden_linear"], ["hidden"]),
        helper.make_node("Gemm", ["hidden", "W2", "b2"], ["output_linear"]),
    ]
    if model.kind == "mlp":
        initializers += [
            numpy_helper.from_array(np.array(0, np.int64), "benign_index"),
            numpy_helper.from_array(np.array(1, np.float32), "one"),
        ]
        nodes += [
            helper.make_node("Softmax", ["output_linear"], ["probabilities"], axis=1),
            helper.make_node(
                "Gather", ["probabilities", "benign_index"], ["benign_probability"], axis=1
            ),
            helper.make_node("Sub", ["one", "benign_probability"], ["score"]),
        ]
        output = helper.make_tensor_value_info(
            "probabilities", TensorProto.FLOAT, [None, len(CLASSES)]
        )
    else:
        initializers += [numpy_helper.from_array(np.array([1], np.int64), "reduce_axes")]
        nodes += [
            helper.make_node("Identity", ["output_linear"], ["reconstruction"]),
            helper.make_node("Sub", ["reconstruction", "input"], ["error"]),
            helper.make_node("Mul", ["error", "error"], ["squared_error"]),
            helper.make_node("ReduceMean", ["squared_error", "reduce_axes"], ["score"], keepdims=0),
        ]
        output = helper.make_tensor_value_info(
            "reconstruction", TensorProto.FLOAT, [None, model.input_dim]
        )
    graph = helper.make_graph(
        nodes,
        "idps-" + model.kind,
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [None, model.input_dim])],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, [None]), output],
        initializers,
    )
    result = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 18)],
        ir_version=9,
        producer_name="idps-ai-training",
        producer_version="0.1.0",
    )
    onnx.checker.check_model(result, full_check=True)
    return result


def cpu_session(path, max_threads=1):
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, int(max_threads))
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def infer_bundle(directory, x, max_threads=1):
    directory = Path(directory)
    manifest = load_json(directory / "model_manifest.json")
    for name in ("model.onnx", "feature_spec.json"):
        if file_sha256(directory / name) != manifest["files"][name]:
            raise PipelineError("Model bundle checksum mismatch")
    values = np.asarray(x, dtype=np.float32)
    if (
        values.ndim != 2
        or values.shape[1] != manifest["input_shape"][1]
        or not np.isfinite(values).all()
    ):
        raise PipelineError("Invalid inference tensor")
    return cpu_session(directory / "model.onnx", max_threads).run(None, {"input": values})


def export_bundle(dataset, checkpoint, output, max_threads=1):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    data_manifest = verify_dataset(dataset, "prepared")
    loaded = load_checkpoint(checkpoint)
    model, state = loaded.model, loaded.state
    if (
        state.get("dataset_sha256") != data_manifest["dataset_sha256"]
        or state.get("environment") != environment_identity()
    ):
        raise PipelineError("Export dataset/environment differs from the checkpoint")
    if output.exists() or dataset.is_relative_to(output) or output.is_relative_to(dataset):
        raise PipelineError("Model bundle requires a new path outside the dataset")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".export-", dir=output.parent) as temporary:
        work = Path(temporary)
        shutil.copyfile(dataset / "feature_spec.json", work / "feature_spec.json")
        spec = load_json(work / "feature_spec.json")
        # Parity covers every prepared row, including attacks excluded from AE
        # fitting. This is inference-only; anomaly weights still learn benign only.
        arrays = load_arrays(dataset, work, "mlp", model.input_dim, 12 * 1024**3)
        val_scores, _ = predict_batches(model, arrays["val"][0])
        calibration = threshold_at_fpr((arrays["val"][1] != 0).astype(np.int64), val_scores)
        test_scores, test_probabilities = predict_batches(model, arrays["test"][0])
        metrics = evaluate(
            arrays["test"][1], test_scores, calibration["threshold"], test_probabilities
        )
        onnx.save_model(graph_for(model), work / "model.onnx")
        session = cpu_session(work / "model.onnx", max_threads)
        parity_rows, maximum = 0, 0.0
        golden = []
        for part in ("train", "val", "test"):
            x = arrays[part][0]
            for start in range(0, len(x), 512):
                batch = np.asarray(x[start : start + 512], dtype=np.float32)
                native = model.predict(batch)
                exported = session.run(None, {"input": batch})
                for a, b in zip(native, exported):
                    if not np.allclose(a, b, rtol=1e-5, atol=1e-6) or not np.isfinite(b).all():
                        raise PipelineError("ONNX numerical parity failed")
                    maximum = max(maximum, float(np.max(np.abs(a - b))))
                parity_rows += len(batch)
                if len(golden) < 3:
                    golden.append(
                        {
                            "input": batch[0].tolist(),
                            "score": float(exported[0][0]),
                            "output": exported[1][0].tolist(),
                        }
                    )
        metrics["latency_ms"] = {
            "scope": "warm batch1 model inference; preprocessing excluded",
            "native": latency_ms(model.predict, arrays["test"][0][:1]),
            "onnxruntime": latency_ms(
                lambda x: session.run(None, {"input": x}), arrays["test"][0][:1]
            ),
        }
        atomic_json(work / "evaluation.json", metrics)
        atomic_json(work / "golden_vectors.json", golden)
        result = {
            "format_version": 1,
            "model_kind": model.kind,
            "files": {
                name: file_sha256(work / name)
                for name in (
                    "model.onnx",
                    "feature_spec.json",
                    "evaluation.json",
                    "golden_vectors.json",
                )
            },
            "dataset_sha256": data_manifest["dataset_sha256"],
            "config_sha256": state["config_sha256"],
            "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
            "features": spec["columns"],
            "feature_version": spec["feature_version"],
            "schema_sha256": data_manifest["schema_sha256"],
            "threshold": calibration["threshold"],
            "calibration": calibration,
            "classes": list(CLASSES),
            "input_shape": [None, model.input_dim],
            "input_dtype": "float32",
            "opset": 18,
            "ir_version": 9,
            "score_semantics": "1 - P(benign)"
            if model.kind == "mlp"
            else "mean squared reconstruction error; not probability of attack",
            "environment": environment_identity(),
            "runtime": "ONNX Runtime CPUExecutionProvider",
            "max_threads": max_threads,
            "parity": {
                "rows": parity_rows,
                "all_rows_match": True,
                "max_absolute_error": maximum,
                "rtol": 1e-5,
                "atol": 1e-6,
            },
            "deployment_status": "offline candidate only; no Rust integration, promotion or enforcement",
            "threshold_warning": "Validation-fitted empirical budget; no production FPR or zero-day guarantee",
        }
        atomic_json(work / "model_manifest.json", result)
        (work / "MODEL_CARD.md").write_text(
            "# Offline IDPS candidate\n\nThis artifact is an offline candidate. Synthetic S0 results validate the pipeline and resume only.\nNo production FPR, real-traffic quality, Rust preprocessing parity or deployment has been accepted.\nRead feature_spec.json availability limits, validation calibration and evaluation.json before reuse.\n"
        )
        shutil.rmtree(work / "cache")
        for file in work.iterdir():
            os.chmod(file, 0o600)
            with file.open("rb") as stream:
                os.fsync(stream.fileno())
        os.replace(work, output)
        fsync_dir(output.parent)
    return result
