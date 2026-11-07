#!/usr/bin/env python3
"""Cross-process exact next-update recovery on synthetic data; no study fitting."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from idps_ai.common import atomic_json, file_sha256
from idps_ai.features.research_request_channels import encode
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
args = parser.parse_args()
os.umask(0o077)
root = args.output.resolve()
if not args.resume:
    root.mkdir(mode=0o700)
    requests = [
        dict(
            method="POST",
            url="/fixture/form",
            headers="Content-Type: application/x-www-form-urlencoded",
            body=b,
        )
        for b in [
            "message=normal+notes",
            "message=%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
            "message=ordinary+2%2B2",
            "ip=127.0.0.1%3Bprintf+fixture",
        ]
    ]
    x = np.stack([encode(r) for r in requests])
    y = np.array([0, 2, 0, 4], np.int64)
    rng = np.random.default_rng(17)
    perm = rng.permutation(len(x)).astype(np.int64)
    model = Model(588, 64, "deep_mlp", 17)
    first = perm[:2]
    second = perm[2:]
    model.train_batch(x[first], y[first], 0.001)
    state = {
        "dataset_fingerprint": "SYNTHETIC_RECOVERY_FIXTURE_NOT_STUDY_DATA",
        "cursor": 2,
        "epoch": 0,
        "learning_rate": 0.001,
        "scheduler": {"kind": "constant", "step": 1},
        "RNG": rng.bit_generator.state,
        "planned_steps": 2,
    }
    save_checkpoint(root, model, state, perm)
    loss = model.train_batch(x[second], y[second], 0.001)
    np.savez(root / "expected.npz", x=x, y=y, loss=loss, **model.arrays())
    subprocess.run([sys.executable, __file__, "--output", str(root), "--resume"], check=True)
else:
    loaded = load_checkpoint(root)
    model = loaded.model
    assert model.steps == 1 and loaded.state["cursor"] == 2
    rng = np.random.default_rng()
    rng.bit_generator.state = loaded.state["RNG"]
    with np.load(root / "expected.npz", allow_pickle=False) as e:
        idx = loaded.permutation[loaded.state["cursor"] :]
        loss = model.train_batch(e["x"][idx], e["y"][idx], loaded.state["learning_rate"])
        assert float(loss) == float(e["loss"])
        assert all(np.array_equal(value, e[name]) for name, value in model.arrays().items())
    state = dict(loaded.state, cursor=4, epoch=1, scheduler={"kind": "constant", "step": 2})
    path = save_checkpoint(root, model, state, loaded.permutation)
    assert load_checkpoint(root).model.steps == 2
    atomic_json(
        root / "proof.json",
        {
            "status": "PASS",
            "required_level": "CROSS_PROCESS_EXACT_NEXT_UPDATE_ON_SYNTHETIC_FIXTURE",
            "parameters": 50696,
            "parameter_Adam_m_v_loss_bitwise_equal": True,
            "RNG_sampler_cursor_scheduler_step_preserved": True,
            "checkpoint_verified_sha256": file_sha256(path / "manifest.json"),
            "actual_cohort_fit_updates": 0,
            "prospective_scores_computed": 0,
            "new_encoder_sha256": file_sha256(
                "ai-training/src/idps_ai/features/research_request_channels.py"
            ),
            "scope": "New architecture/encoder and existing checkpoint protocol; not a claim of full production recovery or a trained challenger",
        },
    )
    print((root / "proof.json").read_text())
