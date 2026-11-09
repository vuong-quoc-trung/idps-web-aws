"""Separate 31x64 AdamW tensor; original v2 arrays are read-only and hash checked.

First layer = original588 affine + selected31 body affine, no adapter bias.
EMPTY/MISSING/non-OK tail is validated zero, so its original path is byte exact.
"""

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from idps_ai.common import digest
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.training.checkpoint import validate_generation
from idps_ai.training.models import affine
from idps_ai.training.partial import partial_loss


def selection():
    start = len(body.STATES) + len(body.MEDIA)
    assert start == 15 and len(body.COLUMNS) - start == 31
    assert tuple(body.COLUMNS[start:]) == tuple(body.COUNTS) + tuple(
        "punct_" + n for n, _ in body.PUNCT
    ) + tuple(body.PATTERNS)
    return {
        "rule": "Exclude schema state/media blocks; retain complete existing count/punctuation/pattern blocks, without labels/scores.",
        "selected": [
            {
                "body_index": i,
                "input_index": 588 + i,
                "name": body.COLUMNS[i],
                "divisor": body.MAXIMA[i],
            }
            for i in range(start, len(body.COLUMNS))
        ],
        "excluded": [
            {"body_index": i, "input_index": 588 + i, "name": body.COLUMNS[i]} for i in range(start)
        ],
        "schema_fingerprint": request_v3.fingerprint(),
        "privacy_contract": body.CONTRACT_SHA256,
        "selection_label_score_inputs": 0,
        "confirmatory_claim": False,
    }


def tensor_hashes(parameters):
    return {
        k: digest(
            {
                "shape": list(v.shape),
                "dtype": str(v.dtype),
                "bytes_sha256": hashlib.sha256(v.tobytes()).hexdigest(),
            }
        )
        for k, v in sorted(parameters.items())
    }


class FrozenBodyAdapter:
    def __init__(self, backbone):
        assert backbone.kind == "deep_mlp" and backbone.layer_dims == [588, 64, 64, 64, 64, 8]
        self.backbone = backbone
        for a in backbone.parameters.values():
            a.setflags(write=False)
        self.backbone_hashes = tensor_hashes(backbone.parameters)
        self.A = np.zeros((31, 64), np.float32)
        self.m = np.zeros_like(self.A)
        self.v = np.zeros_like(self.A)
        self.steps = 0
        self.objective = {"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0}

    def assert_frozen(self):
        assert tensor_hashes(self.backbone.parameters) == self.backbone_hashes, (
            "Frozen backbone changed"
        )
        assert all(not a.flags.writeable for a in self.backbone.parameters.values())

    def metadata(self):
        return {
            "kind": "frozen_body_adapter_v1",
            "input_dim": 634,
            "logical_dims": [634, 64, 64, 64, 64, 8],
            "adapter_shape": [31, 64],
            "trainable_parameters": 1984,
            "adapter_bias": False,
            "optimizer_step": self.steps,
            "optimizer": "adamw-v1",
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "learning_rate": 0.0001,
            "weight_decay": 0.0001,
            "gradient_clip_global_L2": 1.0,
            "objective": self.objective,
            "selection_fingerprint": digest(selection()),
            "backbone_parameter_hashes": self.backbone_hashes,
            "arithmetic": "original588FP64affine_thenFP32 + selected31FP64affine_thenFP32; FP32sum; original remaining layers unchanged",
            "non_OK_contract": "selectedtail mustzero; no intent/method gate; 15state/media features have no parameter tensor",
        }

    def arrays(self):
        return {"p_A": self.A, "m_A": self.m, "v_A": self.v}

    def _forward(self, x, disable=False, feature_mode="all"):
        x = np.asarray(x, np.float32)
        assert x.ndim == 2 and x.shape[1] == 634 and np.isfinite(x).all()
        states = x[:, 588:599]
        media = x[:, 599:603]
        assert np.isin(states, [0, 1]).all() and np.all(states.sum(axis=1) == 1)
        assert np.isin(media, [0, 1]).all() and np.all(media.sum(axis=1) == 1)
        selected = x[:, 603:634]
        assert np.all((selected >= 0) & (selected <= 1))
        non_ok = states[:, body.STATES.index("OK")] == 0
        assert not np.any(selected[non_ok]), "Inconsistent non-OK body tail"
        assert feature_mode in {"all", "counts_only", "syntax_only"}
        if feature_mode != "all":
            selected = selected.copy()
            if feature_mode == "counts_only":
                selected[:, 6:] = 0
            else:
                selected[:, :6] = 0
        p = self.backbone.parameters
        z = affine(x[:, :588], p["W0"], p["b0"])
        active = np.any(selected != 0, axis=1)
        if not disable and np.any(active):
            contribution = (selected[active].astype(np.float64) @ self.A.astype(np.float64)).astype(
                np.float32
            )
            z[active] = z[active] + contribution
        cache = [z]
        h = np.maximum(z, 0)
        for layer in range(1, 5):
            z = affine(h, p["W" + str(layer)], p["b" + str(layer)])
            cache.append(z)
            if layer < 4:
                h = np.maximum(z, 0)
        ex = np.exp(z - z.max(axis=1, keepdims=True))
        probs = ex / ex.sum(axis=1, keepdims=True)
        return probs, cache, selected

    def predict(self, x, disable=False, feature_mode="all"):
        probs, _, _ = self._forward(x, disable, feature_mode)
        return (1 - probs[:, 0]).astype(np.float32), probs

    def loss_and_gradient(self, x, binary):
        probs, cache, selected = self._forward(x)
        y = np.asarray(binary, np.int64)
        loss, delta = partial_loss(cache[-1], y, np.where(y == 0, 0, -1), 0.005, 0.0)
        # Propagate activations only: no gradient tensor is created for any
        # original weight/bias. Only A has a gradient and optimizer state.
        for layer in range(4, -1, -1):
            if layer < 4:
                delta = delta * (cache[layer] > 0)
            if layer == 0:
                return loss, (selected.T @ delta).astype(np.float32)
            delta = delta @ self.backbone.parameters["W" + str(layer)].T
        raise AssertionError("Unreachable")

    def train_batch(self, x, binary):
        self.assert_frozen()
        loss, g = self.loss_and_gradient(x, binary)
        assert np.isfinite(loss) and np.isfinite(g).all()
        norm = float(np.sqrt(np.sum(g.astype(np.float64) ** 2)))
        g = g * np.float32(min(1.0, 1 / max(norm, 1e-12)))
        self.steps += 1
        self.A -= np.float32(0.0001 * 0.0001) * self.A
        self.m *= 0.9
        self.m += 0.1 * g
        self.v *= 0.999
        self.v += 0.001 * g * g
        self.A -= (
            0.0001
            * (self.m / (1 - 0.9**self.steps))
            / (np.sqrt(self.v / (1 - 0.999**self.steps)) + 1e-8)
        )
        assert self.A.shape == self.m.shape == self.v.shape == (31, 64)
        self.assert_frozen()
        return float(loss)


@dataclass
class LoadedAdapter:
    model: FrozenBodyAdapter
    state: dict
    permutation: np.ndarray
    path: Path
    used_previous: bool = False


def load_adapter(directory, backbone, expected_plan=None):
    root = Path(directory).resolve()
    candidates = []
    if (root / "manifest.json").exists():
        candidates = [(root, None, False)]
    else:
        for label in ["latest", "previous"]:
            try:
                pointer = json.loads((root / (label + ".json")).read_text())
                p = (root / pointer["path"]).resolve()
                assert p.is_relative_to(root / "checkpoints")
                candidates.append((p, pointer["manifest_sha256"], label == "previous"))
            except (OSError, ValueError, KeyError, AssertionError):
                continue
    for path, sha, previous in candidates:
        try:
            validate_generation(path, sha)
            state = json.loads((path / "state.json").read_text())
            if expected_plan is not None:
                assert state["plan_fingerprint"] == expected_plan
            model = FrozenBodyAdapter(backbone)
            assert type(state["model"]["optimizer_step"]) is int
            model.steps = state["model"]["optimizer_step"]
            assert state["model"] == model.metadata() and model.steps >= 0
            with np.load(path / "arrays.npz", allow_pickle=False) as z:
                assert set(z.files) == {"p_A", "m_A", "v_A", "permutation"}
                for key, attr in [("p_A", "A"), ("m_A", "m"), ("v_A", "v")]:
                    a = z[key]
                    assert a.dtype == np.float32 and a.shape == (31, 64) and np.isfinite(a).all()
                    setattr(model, attr, a.copy())
                perm = z["permutation"].copy()
                assert perm.dtype == np.int64 and perm.ndim == 1
            model.assert_frozen()
            return LoadedAdapter(model, state, perm, path, previous)
        except (OSError, ValueError, KeyError, TypeError, AssertionError, zipfile.BadZipFile):
            continue
    raise ValueError(
        "No valid compatible adapter checkpoint; inspect latest/previous, do not reset optimizer"
    )
