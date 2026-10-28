"""A small NumPy MLP/autoencoder with explicit Adam state (no pickle/CUDA)."""

import numpy as np

from idps_ai.common import CLASSES, PipelineError


def affine(x, weight, bias):
    # Small CPU networks: accumulate affine reductions in FP64, then round to
    # the FP32 activation contract. This avoids BLAS/MLAS cancellation drift
    # without relaxing the ONNX tolerance. Parameters/gradients/Adam stay FP32.
    return (np.asarray(x, np.float64) @ weight.astype(np.float64) + bias.astype(np.float64)).astype(
        np.float32
    )


class Model:
    def __init__(self, input_dim, hidden_dim=32, kind="mlp", seed=17):
        if (
            not 1 <= input_dim <= 4096
            or not 1 <= hidden_dim <= 256
            or kind not in ("mlp", "autoencoder", "residual")
        ):
            raise PipelineError("Unsupported model architecture")
        self.input_dim, self.hidden_dim, self.kind = input_dim, hidden_dim, kind
        self.steps = 0
        rng = np.random.default_rng(seed)
        output_dim = len(CLASSES) if kind != "autoencoder" else input_dim
        self.parameters = {
            "W1": (rng.standard_normal((input_dim, hidden_dim)) * np.sqrt(2 / input_dim)).astype(
                np.float32
            ),
            "b1": np.zeros(hidden_dim, np.float32),
            "W2": (rng.standard_normal((hidden_dim, output_dim)) * np.sqrt(1 / hidden_dim)).astype(
                np.float32
            ),
            "b2": np.zeros(output_dim, np.float32),
        }
        if kind == "residual":
            self.parameters["Wr"] = (
                rng.standard_normal((hidden_dim, hidden_dim)) * np.sqrt(1 / hidden_dim)
            ).astype(np.float32)
            self.parameters["br"] = np.zeros(hidden_dim, np.float32)
        self.m = {name: np.zeros_like(value) for name, value in self.parameters.items()}
        self.v = {name: np.zeros_like(value) for name, value in self.parameters.items()}

    def metadata(self):
        return {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "kind": self.kind,
            "optimizer_step": self.steps,
            "optimizer": "adam-v1",
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "gradient_clip": 10.0,
            "dtype": "float32",
            "affine_accumulation": "float64_then_round_float32_v1",
        }

    def forward(self, x):
        x = np.asarray(x, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != self.input_dim or not np.isfinite(x).all():
            raise PipelineError("Invalid model input tensor")
        p = self.parameters
        hidden = np.maximum(affine(x, p["W1"], p["b1"]), 0)
        if self.kind == "residual":
            hidden = np.maximum(affine(hidden, p["Wr"], p["br"]) + hidden, 0)
        output = affine(hidden, p["W2"], p["b2"])
        if self.kind != "autoencoder":
            exp = np.exp(output - output.max(axis=1, keepdims=True))
            output = exp / exp.sum(axis=1, keepdims=True)
        return hidden, output

    def predict(self, x):
        _, output = self.forward(x)
        scores = (
            1 - output[:, 0] if self.kind != "autoencoder" else np.mean((output - x) ** 2, axis=1)
        )
        return scores.astype(np.float32), output

    def loss_and_gradients(self, x, y):
        hidden, output = self.forward(x)
        if self.kind != "autoencoder":
            y = np.asarray(y, dtype=np.int64)
            if len(y) != len(x) or (y < 0).any() or (y >= len(CLASSES)).any():
                raise PipelineError("Invalid class targets")
            loss = float(-np.log(np.maximum(output[np.arange(len(x)), y], 1e-12)).mean())
            delta = output.copy()
            delta[np.arange(len(x)), y] -= 1
            delta /= len(x)
        else:
            error = output - x
            loss = float(np.mean(error**2))
            delta = 2 * error / error.size
        grads = {"W2": hidden.T @ delta, "b2": delta.sum(axis=0)}
        backward = (delta @ self.parameters["W2"].T) * (hidden > 0)
        if self.kind == "residual":
            first = np.maximum(affine(x, self.parameters["W1"], self.parameters["b1"]), 0)
            grads.update(Wr=first.T @ backward, br=backward.sum(axis=0))
            backward = (backward @ self.parameters["Wr"].T + backward) * (first > 0)
        grads.update(W1=x.T @ backward, b1=backward.sum(axis=0))
        return loss, grads

    def train_batch(self, x, y, learning_rate):
        loss, gradients = self.loss_and_gradients(x, y)
        if not np.isfinite(loss) or not all(
            np.isfinite(value).all() for value in gradients.values()
        ):
            raise PipelineError("Non-finite model loss/gradient")
        self.steps += 1
        for name, gradient in gradients.items():
            gradient = np.clip(gradient, -10, 10)
            self.m[name] *= 0.9
            self.m[name] += 0.1 * gradient
            self.v[name] *= 0.999
            self.v[name] += 0.001 * gradient**2
            corrected_m = self.m[name] / (1 - 0.9**self.steps)
            corrected_v = self.v[name] / (1 - 0.999**self.steps)
            self.parameters[name] -= learning_rate * corrected_m / (np.sqrt(corrected_v) + 1e-8)
        return loss

    def arrays(self):
        return {
            prefix + name: array
            for prefix, state in (("p_", self.parameters), ("m_", self.m), ("v_", self.v))
            for name, array in state.items()
        }

    @classmethod
    def from_arrays(cls, metadata, arrays):
        if metadata.get("affine_accumulation") != "float64_then_round_float32_v1":
            raise PipelineError(
                "Checkpoint arithmetic contract differs; retain its original source, do not force resume"
            )
        model = cls(metadata["input_dim"], metadata["hidden_dim"], metadata["kind"])
        expected = model.arrays()
        if set(arrays) != set(expected):
            raise PipelineError("Unsupported checkpoint tensors")
        for name, value in arrays.items():
            if (
                value.shape != expected[name].shape
                or value.dtype != np.float32
                or not np.isfinite(value).all()
            ):
                raise PipelineError("Checkpoint tensor shape/dtype mismatch")
            prefix, parameter = name[:2], name[2:]
            {"p_": model.parameters, "m_": model.m, "v_": model.v}[prefix][parameter] = value.copy()
        model.steps = int(metadata["optimizer_step"])
        return model
