"""Separate 10M request candidate; publisher and intent heads never share labels."""

import numpy as np

from idps_ai.common import PipelineError
from idps_ai.training.models import Model
from idps_ai.training.tabular import backward, forward

VERSION = "request-swiglu-10m-multitask-v1"


def parameter_count(width=1024):
    # Input projection, three active SwiGLU residual blocks, norms, eight outputs.
    return 9 * width**2 + 614 * width + 8


class LargeRequest(Model):
    """8 logits: intent[0:2], publisher[2:4], masked structure regression[4:8].

    The input is the frozen request-time 588 projection, never full HTTP bodies.
    Reconstruction targets are TRAIN-only features, not invented benign labels.
    This objective deliberately does not call publisher anomaly attack intent.
    """

    def __init__(self, width=1024, seed=17):
        super().__init__(588, width, "residual_glu", seed=seed)
        if sum(a.size for a in self.parameters.values()) != parameter_count(width):
            raise PipelineError("Large request parameter layout mismatch")

    def metadata(self):
        result = super().metadata()
        result.update(
            multitask_version=VERSION,
            classifier_loss="separate_masked_heads_plus_numeric_reconstruction",
            head_semantics={
                "0:2": "intent",
                "2:4": "publisher_anomaly",
                "4:8": "masked_numeric_regression",
            },
        )
        return result

    @classmethod
    def from_arrays(cls, metadata, arrays):
        if metadata.get("multitask_version") != VERSION:
            raise PipelineError("Wrong multitask checkpoint contract")
        checked = Model.from_arrays(metadata, arrays)
        checked.__class__ = cls
        return checked

    def loss_and_gradients(self, x, y, binary_targets=None):
        x = np.asarray(x, np.float32)
        # y columns: intent {-1,0,1}, publisher {-1,0,1}. Unknown=-1.
        y = np.asarray(y, np.int64)
        if binary_targets is not None or y.shape != (len(x), 2) or not np.isin(y, [-1, 0, 1]).all():
            raise PipelineError("Explicit separate task targets required")
        if x.shape != (len(y), 588) or not np.isfinite(x).all():
            raise PipelineError("Invalid large request feature contract")
        masked = x.copy()
        rng = np.random.default_rng(np.random.SeedSequence([self.noise_seed, self.steps, 71]))
        mask = rng.random((len(x), 4)) < 0.5
        masked[:, :4] *= ~mask
        _, _, cache = forward(self, masked, training=True)
        logits = cache[-1][1]
        delta = np.zeros_like(logits)
        loss = 0.0
        for task, offset in [(0, 0), (1, 2)]:
            valid = y[:, task] >= 0
            if not valid.any():
                continue
            z = logits[valid, offset : offset + 2].astype(np.float64)
            z -= z.max(axis=1, keepdims=True)
            probability = np.exp(z)
            probability /= probability.sum(axis=1, keepdims=True)
            target = y[valid, task]
            loss -= float(np.log(np.maximum(probability[np.arange(len(z)), target], 1e-30)).mean())
            probability[np.arange(len(z)), target] -= 1
            delta[valid, offset : offset + 2] = probability / len(z)
        prediction = 1 / (1 + np.exp(-np.clip(logits[:, 4:8].astype(np.float64), -60, 60)))
        error = (prediction - x[:, :4]) * mask
        denominator = max(1, int(mask.sum()))
        loss += 0.1 * float(np.sum(error**2) / denominator)
        delta[:, 4:8] = (0.2 / denominator) * error * prediction * (1 - prediction)
        gradients = backward(self, delta, cache)
        if not np.isfinite(loss) or set(gradients) != set(self.parameters):
            raise PipelineError("Invalid active gradient paths")
        return loss, gradients

    def score_heads(self, x):
        # Masking is training-only augmentation, like dropout. All input weights
        # retain active paths; no reconstructed or fabricated live input.
        x = np.asarray(x, np.float32).copy()
        if x.ndim != 2 or x.shape[1] != 588 or not np.isfinite(x).all():
            raise PipelineError("Invalid inference tensor")
        logits = forward(self, x)[2][-1][1].astype(np.float64)
        result = {}
        for name, offset in [("synthetic_or_grounded_intent", 0), ("publisher_anomaly", 2)]:
            z = logits[:, offset : offset + 2]
            e = np.exp(z - z.max(axis=1, keepdims=True))
            result[name] = (e[:, 1] / e.sum(axis=1)).astype(np.float32)
        return result

    def predict(self, x):
        raise PipelineError(
            "Multitask model requires explicit score_heads; not an eight-class attack model"
        )
