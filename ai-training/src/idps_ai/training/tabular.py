"""Pre-LayerNorm residual SwiGLU challenger. No dormant capacity or external DL stack."""

import numpy as np

from idps_ai.common import PipelineError

BLOCKS = 3
DROPOUT = 0.1
SMOOTHING = 0.02
DECAY = 1e-4
NORM_EPS = 1e-5


def regularization_options(value=None):
    defaults = {"dropout": DROPOUT, "label_smoothing": SMOOTHING, "weight_decay": DECAY}
    if value is not None:
        if not isinstance(value, dict) or set(value) - set(defaults):
            raise PipelineError("Unknown regularization option")
        defaults.update(value)
    for name, maximum in (("dropout", 0.5), ("label_smoothing", 0.2), ("weight_decay", 0.1)):
        v = defaults[name]
        if (
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not np.isfinite(v)
            or not 0 <= v <= maximum
        ):
            raise PipelineError("Invalid regularization value")
    return defaults


def initialize(input_dim, width, rng):
    p = {}

    def linear(name, source, target, gain=1.0):
        p["W" + name] = (rng.standard_normal((source, target)) * np.sqrt(gain / source)).astype(
            np.float32
        )
        p["b" + name] = np.zeros(target, np.float32)

    def norm(name):
        p["gamma" + name] = np.ones(width, np.float32)
        p["beta" + name] = np.zeros(width, np.float32)

    linear("in", input_dim, width, 2.0)
    for i in range(BLOCKS):
        suffix = str(i)
        norm(suffix)
        for name in ("value", "gate", "down"):
            linear(name + suffix, width, width)
    norm("out")
    linear("out", width, 8)
    return p, [input_dim] + [width] * (BLOCKS + 1) + [8]


def normalization(x, gamma, beta):
    wide = x.astype(np.float64)
    centered = wide - wide.mean(axis=1, keepdims=True)
    inverse = 1 / np.sqrt((centered * centered).mean(axis=1, keepdims=True) + NORM_EPS)
    standardized = (centered * inverse).astype(np.float32)
    return standardized * gamma + beta, (standardized, inverse, gamma)


def norm_backward(delta, cache):
    standardized, inverse, gamma = cache
    wide = delta.astype(np.float64) * gamma.astype(np.float64)
    normalized = standardized.astype(np.float64)
    dx = (
        (
            wide
            - wide.mean(axis=1, keepdims=True)
            - normalized * (wide * normalized).mean(axis=1, keepdims=True)
        )
        * inverse
    ).astype(np.float32)
    return dx, (delta * standardized).sum(axis=0), delta.sum(axis=0)


def forward(model, x, training=False):
    from idps_ai.training.models import affine

    p = model.parameters
    dropout = model.regularization["dropout"]
    h = np.maximum(affine(x, p["Win"], p["bin"]), 0)
    cache = [(x, h)]
    rng = np.random.default_rng(np.random.SeedSequence([model.noise_seed, model.steps, 23]))
    for i in range(BLOCKS):
        s = str(i)
        n, ncache = normalization(h, p["gamma" + s], p["beta" + s])
        value = affine(n, p["Wvalue" + s], p["bvalue" + s])
        gate = affine(n, p["Wgate" + s], p["bgate" + s])
        sigmoid = (1 / (1 + np.exp(-np.clip(gate.astype(np.float64), -80, 80)))).astype(np.float32)
        mask = (
            ((rng.random(value.shape) >= dropout).astype(np.float32) / np.float32(1 - dropout))
            if training
            else np.float32(1)
        )
        activation = value * (gate * sigmoid) * mask
        cache.append((n, ncache, value, gate, sigmoid, mask, activation))
        h = h + np.float32(0.5) * affine(activation, p["Wdown" + s], p["bdown" + s])
    hidden, ncache = normalization(h, p["gammaout"], p["betaout"])
    logits = affine(hidden, p["Wout"], p["bout"])
    cache.extend([ncache, (hidden, logits)])
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    return hidden, exp / exp.sum(axis=1, keepdims=True), cache


def backward(model, delta, cache):
    p = model.parameters
    hidden, _ = cache[-1]
    grads = {"Wout": hidden.T @ delta, "bout": delta.sum(axis=0)}
    delta, grads["gammaout"], grads["betaout"] = norm_backward(delta @ p["Wout"].T, cache[-2])
    for i in reversed(range(BLOCKS)):
        s = str(i)
        n, ncache, value, gate, sigmoid, mask, activation = cache[i + 1]
        branch = delta * np.float32(0.5)
        grads["Wdown" + s] = activation.T @ branch
        grads["bdown" + s] = branch.sum(axis=0)
        da = (branch @ p["Wdown" + s].T) * mask
        dv = da * (gate * sigmoid)
        dg = da * value * (sigmoid + gate * sigmoid * (1 - sigmoid))
        grads["Wvalue" + s] = n.T @ dv
        grads["bvalue" + s] = dv.sum(axis=0)
        grads["Wgate" + s] = n.T @ dg
        grads["bgate" + s] = dg.sum(axis=0)
        normalized = dv @ p["Wvalue" + s].T + dg @ p["Wgate" + s].T
        dx, grads["gamma" + s], grads["beta" + s] = norm_backward(normalized, ncache)
        delta = delta + dx
    x, h = cache[0]
    delta = delta * (h > 0)
    grads.update(Win=x.T @ delta, bin=delta.sum(axis=0))
    return grads


def metadata(seed, options=None):
    options = regularization_options(options)
    return {
        "version": 1,
        "blocks": BLOCKS,
        "normalization": "LayerNorm_FP64_stats_round_FP32",
        "norm_epsilon": NORM_EPS,
        "activation": "SwiGLU_sigmoid_FP64_round_FP32",
        "dropout": options["dropout"],
        "dropout_seed": seed,
        "dropout_rng": "PCG64_SeedSequence(seed,committed_step,23)",
        "label_smoothing": options["label_smoothing"],
        "optimizer": "AdamW",
        "weight_decay": options["weight_decay"],
        "decay_parameters": "W_only",
        "gradient_clip_global_l2": 1.0,
        "inference_dropout": False,
    }
