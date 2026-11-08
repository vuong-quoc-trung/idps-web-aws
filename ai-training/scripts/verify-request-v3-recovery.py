#!/usr/bin/env python3
"""Two synthetic updates only: real v2 warm start and cross-process v3 recovery."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features import request_v3
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model

ROOT = Path(__file__).resolve().parents[2]


def verify(root, child=False):
    if not child:
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        frozen = load_checkpoint(
            ROOT / "ai-training/.artifacts/request_intelligence_v2_20261104/run/model"
        )
        model = Model(
            634,
            64,
            "deep_mlp",
            17,
            objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
        )
        model.parameters = request_v3.expanded_parameters(frozen.model.parameters)
        assert model.steps == 0 and all(
            not np.any(v) for d in [model.m, model.v] for v in d.values()
        )
        assert sum(v.size for v in model.parameters.values()) == 53640
        rng = np.random.default_rng(17)
        x = rng.random((4, 634), dtype=np.float32)
        assert np.allclose(
            frozen.model.forward(x[:, :588])[1], model.forward(x)[1], atol=1e-7, rtol=0
        )
        y = np.array([0, 2, 0, 4], np.int64)
        binary = np.array([0, 1, 0, 1], np.int64)
        perm = rng.permutation(4).astype(np.int64)
        fp = digest({"scope": "SYNTHETIC_ONLY", "seed": 17, "shape": [4, 634]})
        first, second = perm[:2], perm[2:]
        loss = model.train_batch(x[first], y[first], 0.0001, binary_targets=binary[first])
        state = {
            "dataset_fingerprint": fp,
            "feature_contract_fingerprint": request_v3.fingerprint(),
            "objective": model.objective,
            "cursor": 2,
            "epoch": 0,
            "RNG": rng.bit_generator.state,
            "learning_rate": 0.0001,
            "scheduler": {"kind": "constant", "step": 1},
            "planned_updates": 2,
            "scope": "SYNTHETIC_PROOF_NOT_ACTUAL_COHORT",
        }
        saved = save_checkpoint(root, model, state, perm)
        loaded = load_checkpoint(root)
        assert all(np.array_equal(v, loaded.model.arrays()[k]) for k, v in model.arrays().items())
        loss = model.train_batch(x[second], y[second], 0.0001, binary_targets=binary[second])
        np.savez(
            root / "expected.npz",
            x=x,
            y=y,
            binary=binary,
            loss=loss,
            next_rng=rng.integers(0, 100000, size=8),
            **model.arrays(),
        )
        atomic_json(
            root / "warm-start-proof.json",
            {
                "WARM_START_VERIFIED": True,
                "CHECKPOINT_RELOAD_VERIFIED": True,
                "actual_frozen_manifest_sha256": file_sha256(frozen.path / "manifest.json"),
                "initial_Adam_m_v_zero": True,
                "warm_start_step0": True,
                "initial_function_parity_atol": 1e-7,
                "first_synthetic_manifest_sha256": file_sha256(saved / "manifest.json"),
                "cohort_updates": 0,
            },
        )
        subprocess.run([sys.executable, __file__, "--output", str(root), "--child"], check=True)
    else:
        loaded = load_checkpoint(root)
        m = loaded.model
        s = loaded.state
        assert m.input_dim == 634 and m.steps == 1 and s["cursor"] == 2
        assert s["feature_contract_fingerprint"] == request_v3.fingerprint()
        assert s["dataset_fingerprint"] == digest(
            {"scope": "SYNTHETIC_ONLY", "seed": 17, "shape": [4, 634]}
        )
        assert s["objective"] == m.objective and s["scheduler"]["step"] == m.steps
        rng = np.random.default_rng()
        rng.bit_generator.state = s["RNG"]
        with np.load(root / "expected.npz", allow_pickle=False) as e:
            assert np.array_equal(rng.integers(0, 100000, size=8), e["next_rng"])
            ix = loaded.permutation[s["cursor"] :]
            loss = m.train_batch(
                e["x"][ix], e["y"][ix], s["learning_rate"], binary_targets=e["binary"][ix]
            )
            assert loss == float(e["loss"])
            assert all(np.array_equal(v, e[k]) for k, v in m.arrays().items())
        dest = save_checkpoint(
            root,
            m,
            dict(
                s,
                cursor=4,
                epoch=1,
                scheduler={"kind": "constant", "step": 2},
                RNG=rng.bit_generator.state,
            ),
            loaded.permutation,
        )
        assert load_checkpoint(root).model.steps == 2
        atomic_json(
            root / "recovery-proof.json",
            {
                "EXACT_RESUME_VERIFIED": True,
                "required_level": "CROSS_PROCESS_BITWISE_NEXT_UPDATE_ON_SYNTHETIC_634_INPUTS",
                "WARM_START_VERIFIED": True,
                "CHECKPOINT_RELOAD_VERIFIED": True,
                "model_parameters": 53640,
                "objective": m.objective,
                "parameter_m_v_loss_bitwise_equal": True,
                "RNG_permutation_cursor_epoch_scheduler_restored": True,
                "contract_fingerprint": request_v3.fingerprint(),
                "final_manifest_sha256": file_sha256(dest / "manifest.json"),
                "synthetic_updates": 2,
                "actual_cohort_updates": 0,
                "production_recovery": "NOT_VERIFIED",
            },
        )
        print((root / "recovery-proof.json").read_text())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        verify(a.output.resolve(), a.child)
