"""A small NumPy MLP/autoencoder with explicit Adam state (no pickle/CUDA)."""

import numpy as np

from idps_ai.common import CLASSES, PipelineError
from idps_ai.training.deep import AUTOENCODERS, DEEP_KINDS


def affine(x, weight, bias):
    # Small CPU networks: accumulate affine reductions in FP64, then round to
    # the FP32 activation contract. This avoids BLAS/MLAS cancellation drift
    # without relaxing the ONNX tolerance. Parameters/gradients/Adam stay FP32.
    return (np.asarray(x, np.float64) @ weight.astype(np.float64) + bias.astype(np.float64)).astype(
        np.float32
    )


class Model:
    def __init__(
        self,
        input_dim,
        hidden_dim=32,
        kind="mlp",
        seed=17,
        class_weights=None,
        regularization=None,
        objective=None,
    ):
        if (
            not 1 <= input_dim <= 4096
            or not 1 <= hidden_dim <= (1024 if kind == "residual_glu" else 256)
            or kind not in ("mlp", "autoencoder", "residual", *DEEP_KINDS)
        ):
            raise PipelineError("Unsupported model architecture")
        self.input_dim, self.hidden_dim, self.kind = input_dim, hidden_dim, kind
        from idps_ai.training.tabular import regularization_options

        if regularization is not None and kind != "residual_glu":
            raise PipelineError("Explicit regularization is supported only for residual_glu")
        self.regularization = regularization_options(regularization)
        self.objective = dict(objective) if objective is not None else None
        if self.objective is not None:
            if (
                kind not in ("deep_mlp", "residual_glu")
                or class_weights is not None
                or not {"kind", "smoothing", "family_weight"} <= set(self.objective)
                or set(self.objective)
                - {"kind", "smoothing", "family_weight", "binary_class_weights"}
                or self.objective["kind"] != "partial_binary_v1"
                or not 0 <= self.objective["smoothing"] <= 0.2
                or not 0 <= self.objective["family_weight"] <= 1
            ):
                raise PipelineError("Unsupported partial binary objective")
            if "binary_class_weights" in self.objective:
                weights = np.asarray(self.objective["binary_class_weights"], np.float64)
                if weights.shape != (2,) or not np.isfinite(weights).all() or (weights <= 0).any():
                    raise PipelineError("Invalid binary class weights")
            if kind == "residual_glu":
                self.regularization["label_smoothing"] = self.objective["smoothing"]
        self.class_weights = (
            None if class_weights is None else np.asarray(class_weights, np.float32)
        )
        if self.class_weights is not None and (
            kind in AUTOENCODERS
            or self.class_weights.shape != (len(CLASSES),)
            or not np.isfinite(self.class_weights).all()
            or (self.class_weights <= 0).any()
        ):
            raise PipelineError("Invalid classifier class weights")
        self.steps = 0
        rng = np.random.default_rng(seed)
        self.noise_seed = seed
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
        if kind in DEEP_KINDS:
            from idps_ai.training.deep import initialize

            self.parameters, self.layer_dims = initialize(input_dim, hidden_dim, kind, rng)
        self.m = {name: np.zeros_like(value) for name, value in self.parameters.items()}
        self.v = {name: np.zeros_like(value) for name, value in self.parameters.items()}

    def metadata(self):
        metadata = {
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
        if self.class_weights is not None:
            metadata["class_weights"] = self.class_weights.tolist()
            metadata["loss"] = "weighted_cross_entropy_v1"
        if self.kind in DEEP_KINDS:
            metadata["deep_architecture_version"] = 1
            metadata["layer_dims"] = self.layer_dims
            if self.kind not in AUTOENCODERS:
                metadata["classifier_loss"] = "stable_logsumexp_cross_entropy_v1"
        if self.kind == "residual_glu":
            from idps_ai.training.tabular import metadata as tabular_metadata

            metadata["regularization"] = tabular_metadata(self.noise_seed, self.regularization)
            metadata["optimizer"] = "adamw-v1"
            metadata["gradient_clip"] = 1.0
            metadata["gradient_clip_kind"] = "global_l2"
            metadata["classifier_loss"] = "label_smoothed_logsumexp_cross_entropy_v1"
        if self.kind == "denoising_autoencoder":
            metadata["corruption"] = {
                "version": 1,
                "seed": self.noise_seed,
                "gaussian_std": 0.1,
                "mask_probability": 0.1,
                "rng": "PCG64 SeedSequence(seed, committed optimizer step)",
            }
        if self.objective is not None:
            metadata.update(
                objective=self.objective,
                classifier_loss="binary_marginal_optional_conditional_family_v1",
                optimizer="adamw-v1",
                gradient_clip=1.0,
                gradient_clip_kind="global_l2",
                partial_optimizer={
                    "weight_decay": self.regularization["weight_decay"],
                    "decay_parameters": "W_only",
                    "gradient_clip_global_l2": 1.0,
                },
            )
        return metadata

    def forward(self, x):
        x = np.asarray(x, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != self.input_dim or not np.isfinite(x).all():
            raise PipelineError("Invalid model input tensor")
        p = self.parameters
        if self.kind in DEEP_KINDS:
            from idps_ai.training.deep import forward

            hidden, output, _ = forward(self, x)
            return hidden, output
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
            1 - output[:, 0]
            if self.kind not in AUTOENCODERS
            else np.mean((output - x) ** 2, axis=1)
        )
        return scores.astype(np.float32), output

    def loss_and_gradients(self, x, y, binary_targets=None):
        x = np.asarray(x, np.float32)
        if self.objective is not None:
            if binary_targets is None:
                raise PipelineError("Partial supervision requires explicit binary labels")
            from idps_ai.training.deep import backward, forward
            from idps_ai.training.partial import partial_loss

            if self.kind == "residual_glu":
                from idps_ai.training.tabular import forward as tabular_forward

                _, _, cache = tabular_forward(self, x, training=True)
            else:
                _, _, cache = forward(self, x)
            loss, delta = partial_loss(
                cache[-1][1],
                binary_targets,
                y,
                self.objective["smoothing"],
                self.objective["family_weight"],
                self.objective.get("binary_class_weights"),
            )
            return loss, backward(self, delta, cache)
        if binary_targets is not None:
            raise PipelineError("Binary labels require the explicit partial objective")
        if self.kind in DEEP_KINDS:
            from idps_ai.training.deep import corrupt, forward

            inputs = corrupt(self, x) if self.kind == "denoising_autoencoder" else x
            if self.kind == "residual_glu":
                from idps_ai.training.tabular import forward as tabular_forward

                hidden, output, cache = tabular_forward(self, inputs, training=True)
            else:
                hidden, output, cache = forward(self, inputs)
        else:
            hidden, output = self.forward(x)
        if self.kind not in AUTOENCODERS:
            y = np.asarray(y, dtype=np.int64)
            if len(y) != len(x) or (y < 0).any() or (y >= len(CLASSES)).any():
                raise PipelineError("Invalid class targets")
            errors = -np.log(np.maximum(output[np.arange(len(x)), y], 1e-12))
            if self.kind in DEEP_KINDS:
                from idps_ai.training.deep import cross_entropy

                errors = cross_entropy(
                    cache[-1][1],
                    y,
                    self.regularization["label_smoothing"] if self.kind == "residual_glu" else 0.0,
                )
            delta = output.copy()
            if self.kind == "residual_glu":
                smoothing = self.regularization["label_smoothing"]
                delta -= np.float32(smoothing / len(CLASSES))
                delta[np.arange(len(x)), y] -= np.float32(1 - smoothing)
            else:
                delta[np.arange(len(x)), y] -= 1
            if self.class_weights is None:
                loss = float(errors.mean())
                delta /= len(x)
            else:
                weights = self.class_weights[y]
                normalizer = weights.sum()
                loss = float((errors * weights).sum() / normalizer)
                delta *= (weights / normalizer)[:, None]
        else:
            error = output - x
            loss = float(np.mean(error**2))
            delta = 2 * error / error.size
        if self.kind in DEEP_KINDS:
            from idps_ai.training.deep import backward

            return loss, backward(self, delta, cache)
        grads = {"W2": hidden.T @ delta, "b2": delta.sum(axis=0)}
        backward = (delta @ self.parameters["W2"].T) * (hidden > 0)
        if self.kind == "residual":
            first = np.maximum(affine(x, self.parameters["W1"], self.parameters["b1"]), 0)
            grads.update(Wr=first.T @ backward, br=backward.sum(axis=0))
            backward = (backward @ self.parameters["Wr"].T + backward) * (first > 0)
        grads.update(W1=x.T @ backward, b1=backward.sum(axis=0))
        return loss, grads

    def classification_errors(self, x, y):
        x = np.asarray(x, np.float32)
        if self.kind in AUTOENCODERS:
            raise PipelineError("Reconstruction models do not use classifier loss")
        if x.ndim != 2 or x.shape[1] != self.input_dim or not np.isfinite(x).all():
            raise PipelineError("Invalid classifier loss input")
        if self.kind in DEEP_KINDS:
            from idps_ai.training.deep import cross_entropy, forward

            return cross_entropy(
                forward(self, x)[2][-1][1],
                y,
                self.regularization["label_smoothing"] if self.kind == "residual_glu" else 0.0,
            )
        output = self.forward(x)[1]
        return -np.log(np.maximum(output[np.arange(len(x)), y], 1e-12))

    def train_batch(self, x, y, learning_rate, binary_targets=None):
        loss, gradients = self.loss_and_gradients(x, y, binary_targets=binary_targets)
        if not np.isfinite(loss) or not all(
            np.isfinite(value).all() for value in gradients.values()
        ):
            raise PipelineError("Non-finite model loss/gradient")
        self.steps += 1
        global_scale = 1.0
        if self.kind == "residual_glu" or self.objective is not None:
            norm = np.sqrt(sum(np.sum(g.astype(np.float64) ** 2) for g in gradients.values()))
            global_scale = min(1.0, 1.0 / max(float(norm), 1e-12))
        for name, gradient in gradients.items():
            if self.kind == "residual_glu" or self.objective is not None:
                gradient = gradient * np.float32(global_scale)
                if name.startswith("W"):
                    self.parameters[name] -= (
                        np.float32(learning_rate * self.regularization["weight_decay"])
                        * self.parameters[name]
                    )
            else:
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
        model = cls(
            metadata["input_dim"],
            metadata["hidden_dim"],
            metadata["kind"],
            seed=metadata.get("regularization", {}).get(
                "dropout_seed", metadata.get("corruption", {}).get("seed", 17)
            ),
            class_weights=metadata.get("class_weights"),
            regularization={
                k: metadata.get("regularization", {}).get(k)
                for k in ("dropout", "label_smoothing", "weight_decay")
            }
            if metadata["kind"] == "residual_glu"
            else None,
            objective=metadata.get("objective"),
        )
        if model.objective is not None and model.metadata()["partial_optimizer"] != metadata.get(
            "partial_optimizer"
        ):
            raise PipelineError("Partial objective optimizer contract mismatch")
        if model.kind in DEEP_KINDS and (
            metadata.get("deep_architecture_version") != 1
            or metadata.get("layer_dims") != model.layer_dims
        ):
            raise PipelineError("Deep checkpoint architecture contract mismatch")
        if model.kind == "denoising_autoencoder" and model.metadata()["corruption"] != metadata.get(
            "corruption"
        ):
            raise PipelineError("Denoising checkpoint corruption contract mismatch")
        if model.kind == "residual_glu" and model.metadata()["regularization"] != metadata.get(
            "regularization"
        ):
            raise PipelineError("GLU checkpoint regularization/arithmetic contract mismatch")
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
