"""Pure global-step schedules: resume never restarts warmup or decay."""

import math

from idps_ai.common import PipelineError


def learning_rate(training, step):
    base = training["learning_rate"]
    if not 0 < base <= 1 or step < 0:
        raise PipelineError("Invalid learning rate or optimizer step")
    schedule = training.get("scheduler", "exponential")
    if schedule == "exponential":
        gamma = training["scheduler_gamma"]
        decay = training["scheduler_decay_steps"]
        if not 0 < gamma <= 1 or decay < 1:
            raise PipelineError("Invalid exponential schedule")
        return base * gamma ** (step // decay)
    if schedule != "warmup_cosine":
        raise PipelineError("Unsupported scheduler")
    warmup = training.get("warmup_steps", 0)
    total = training.get("total_steps", 0)
    floor = training.get("min_lr_ratio", 0.05)
    if (
        type(warmup) is not int
        or type(total) is not int
        or not 0 <= warmup < total
        or not 0 <= floor <= 1
    ):
        raise PipelineError("Invalid warmup/cosine configuration")
    if step < warmup:
        return base * (step + 1) / warmup
    progress = min(1.0, (step - warmup) / (total - warmup))
    return base * (floor + (1 - floor) * 0.5 * (1 + math.cos(math.pi * progress)))
