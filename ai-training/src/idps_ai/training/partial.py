"""Stable marginalized binary objective with optional conditional family labels."""

import numpy as np

from idps_ai.common import PipelineError


def partial_loss(
    logits, binary, families, smoothing=0.005, family_weight=0.2, binary_class_weights=None
):
    z = np.asarray(logits, np.float64)
    binary, families = np.asarray(binary), np.asarray(families)
    if (
        z.ndim != 2
        or z.shape[1] != 8
        or not len(z)
        or not np.isfinite(z).all()
        or binary.shape != (len(z),)
        or families.shape != (len(z),)
        or not np.isin(binary, [0, 1]).all()
        or not np.isin(families, range(-1, 8)).all()
        or np.any((binary == 0) & (families > 0))
        or np.any((binary == 1) & (families == 0))
        or not 0 <= smoothing <= 0.2
        or not 0 <= family_weight <= 1
    ):
        raise PipelineError("Invalid partial binary/family supervision")
    z = z - z.max(axis=1, keepdims=True)
    log_total = np.log(np.exp(z).sum(axis=1))
    a = z[:, 1:]
    shift = a.max(axis=1, keepdims=True)
    log_attack = shift[:, 0] + np.log(np.exp(a - shift).sum(axis=1))
    probabilities = np.exp(z - log_total[:, None])
    conditional = np.exp(a - log_attack[:, None])
    target = binary * (1 - smoothing) + smoothing / 2
    errors = log_total - (1 - target) * z[:, 0] - target * log_attack
    delta = probabilities.copy()
    delta[:, 0] -= 1 - target
    delta[:, 1:] -= target[:, None] * conditional
    known = np.flatnonzero(families > 0)
    if len(known):
        indices = families[known].astype(np.int64) - 1
        errors[known] += family_weight * (log_attack[known] - a[known, indices])
        delta[known, 1:] += family_weight * conditional[known]
        delta[known, indices + 1] -= family_weight
    if binary_class_weights is None:
        return float(errors.mean()), (delta / len(z)).astype(np.float32)
    weights = np.asarray(binary_class_weights, np.float64)
    if weights.shape != (2,) or not np.isfinite(weights).all() or (weights <= 0).any():
        raise PipelineError("Invalid binary class weights")
    sample = weights[binary.astype(np.int64)]
    return float(np.sum(errors * sample) / sample.sum()), (
        delta * (sample / sample.sum())[:, None]
    ).astype(np.float32)
