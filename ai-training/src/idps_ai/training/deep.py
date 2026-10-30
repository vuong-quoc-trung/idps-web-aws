"""Explicit NumPy deep tabular blocks, deterministic denoising and FP64 reductions."""

import numpy as np

DEEP_KINDS = ("deep_mlp", "denoising_autoencoder", "gated_residual", "residual_glu")
AUTOENCODERS = ("autoencoder", "denoising_autoencoder")


def cross_entropy(logits, targets, smoothing=0.0):
    shifted = logits.astype(np.float64) - logits.max(axis=1, keepdims=True).astype(np.float64)
    return (
        np.log(np.exp(shifted).sum(axis=1))
        - (1 - smoothing) * shifted[np.arange(len(targets)), targets]
        - smoothing * shifted.mean(axis=1)
    )


def initialize(input_dim, width, kind, rng):
    if kind == "residual_glu":
        from idps_ai.training.tabular import initialize as tabular_initialize

        return tabular_initialize(input_dim, width, rng)
    output_dim = input_dim if kind in AUTOENCODERS else 8
    dims = (
        [input_dim, width, width, max(2, width // 2), width, width, output_dim]
        if kind == "denoising_autoencoder"
        else [input_dim, width, width, width, width, output_dim]
    )
    parameters = {}

    def layer(name, source, target, scale=2.0):
        parameters["W" + name] = (
            rng.standard_normal((source, target)) * np.sqrt(scale / source)
        ).astype(np.float32)
        parameters["b" + name] = np.zeros(target, np.float32)

    if kind == "gated_residual":
        layer("in", input_dim, width)
        for i in range(3):
            layer("block" + str(i), width, width)
            layer("gate" + str(i), width, width, 0.1)
            parameters["bgate" + str(i)].fill(-1)
        layer("out", width, output_dim, 1.0)
    else:
        for i, (source, target) in enumerate(zip(dims, dims[1:])):
            layer(str(i), source, target, 1.0 if i == len(dims) - 2 else 2.0)
    return parameters, dims


def forward(model, x):
    if model.kind == "residual_glu":
        from idps_ai.training.tabular import forward as tabular_forward

        return tabular_forward(model, x)
    from idps_ai.training.models import affine

    p = model.parameters
    cache = []
    h = x
    if model.kind == "gated_residual":
        h = np.maximum(affine(x, p["Win"], p["bin"]), 0)
        cache.append((x, h))
        for i in range(3):
            suffix = str(i)
            a = np.maximum(affine(h, p["Wblock" + suffix], p["bblock" + suffix]), 0)
            logits = affine(h, p["Wgate" + suffix], p["bgate" + suffix])
            gate = (1 / (1 + np.exp(-np.clip(logits.astype(np.float64), -80, 80)))).astype(
                np.float32
            )
            cache.append((h, a, gate))
            h = h + np.float32(0.5) * a * gate
        hidden = h
        out = affine(h, p["Wout"], p["bout"])
        cache.append((h, out))
    else:
        for i in range(len(model.layer_dims) - 1):
            out = affine(h, p["W" + str(i)], p["b" + str(i)])
            cache.append((h, out))
            if i < len(model.layer_dims) - 2:
                h = np.maximum(out, 0)
        hidden = h
    if model.kind not in AUTOENCODERS:
        exp = np.exp(out - out.max(axis=1, keepdims=True))
        out = exp / exp.sum(axis=1, keepdims=True)
    return hidden, out, cache


def backward(model, delta, cache):
    if model.kind == "residual_glu":
        from idps_ai.training.tabular import backward as tabular_backward

        return tabular_backward(model, delta, cache)
    p = model.parameters
    grads = {}
    if model.kind == "gated_residual":
        h, _ = cache[-1]
        grads.update(Wout=h.T @ delta, bout=delta.sum(axis=0))
        delta = delta @ p["Wout"].T
        for i in reversed(range(3)):
            h, a, gate = cache[i + 1]
            suffix = str(i)
            da = delta * np.float32(0.5) * gate * (a > 0)
            dg = delta * np.float32(0.5) * a * gate * (1 - gate)
            grads["Wblock" + suffix] = h.T @ da
            grads["bblock" + suffix] = da.sum(axis=0)
            grads["Wgate" + suffix] = h.T @ dg
            grads["bgate" + suffix] = dg.sum(axis=0)
            delta = delta + da @ p["Wblock" + suffix].T + dg @ p["Wgate" + suffix].T
        x, h = cache[0]
        delta = delta * (h > 0)
        grads.update(Win=x.T @ delta, bin=delta.sum(axis=0))
    else:
        for i in reversed(range(len(cache))):
            x, out = cache[i]
            if i < len(cache) - 1:
                delta = delta * (out > 0)
            grads["W" + str(i)] = x.T @ delta
            grads["b" + str(i)] = delta.sum(axis=0)
            delta = delta @ p["W" + str(i)].T
    return grads


def corrupt(model, x):
    # Stateless counter-based sampling: restoring seed + committed optimizer
    # step restores the exact next corruption, including mid-epoch resumes.
    rng = np.random.default_rng(np.random.SeedSequence([model.noise_seed, model.steps]))
    noise = rng.normal(0, 0.1, size=x.shape).astype(np.float32)
    mask = (rng.random(x.shape) >= 0.1).astype(np.float32)
    return ((x + noise) * mask).astype(np.float32)
