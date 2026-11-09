#!/usr/bin/env python3
"""Single matched31-row body adapter arm, isolated optimizer and original v2 weights."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.frozen_body_adapter import FrozenBodyAdapter, load_adapter, selection

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "ai-training/configs/research/request-v3-frozen-backbone-20261109.json"
REFERENCE = ROOT / "ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1"
BODY = ROOT / "ai-training/.artifacts/request_v3_body_eval_20261108/cohort-r2"


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def backbone():
    return load_checkpoint(module("train-request-v3-pilot").FROZEN)


def parity_inputs(cfg):
    # Feature-only integrity probes. No CAL/DEV labels or performance read.
    arrays = []
    counts = {}
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        with np.load(
            ROOT / cfg["dataset_release"] / (role.lower() + ".npz"), allow_pickle=False
        ) as z:
            x = z["x"].copy()
            syntax = z["body_syntax"]
            assert all(
                np.array_equal(a, request_v3.assemble(f, b.tolist()))
                for a, f, b in zip(x, z["frozen_runtime"], syntax, strict=True)
            )
            non_ok = syntax[:, body.STATES.index("OK")] == 0
            assert not np.any(x[non_ok, 603:]), "Body contract non-OK tail must zero"
            arrays.append(x[non_ok])
            counts[role] = int(non_ok.sum())
    return np.concatenate(arrays), counts


def prepare(run):
    old = module("train-request-v3-pilot")
    cfg, x, y, rows, groups = old.inputs()
    assert not run.exists() and not CONFIG.exists()
    frozen = backbone()
    adapter = FrozenBodyAdapter(frozen.model)
    probe, counts = parity_inputs(cfg)
    reference = frozen.model.predict(x[:, :588])[0]
    assert adapter.predict(x)[0].tobytes() == reference.tobytes()
    assert adapter.predict(probe)[0].tobytes() == frozen.model.predict(probe[:, :588])[0].tobytes()
    loss, gradient = adapter.loss_and_gradient(x[:16], y[:16])
    assert gradient.shape == (31, 64) and np.isfinite(gradient).all() and np.isfinite(loss)
    assert (
        adapter.A.size == 1984
        and not np.any(adapter.A)
        and not np.any(adapter.m)
        and not np.any(adapter.v)
    )
    oldplan = load(REFERENCE / "plan.json")
    assert oldplan["dataset_fingerprint"] == cfg["dataset_fingerprint"]
    assert oldplan["sampler_fingerprint"] == digest(
        {"ids": [r["sample_id"] for r in rows], "groups": groups}
    )
    # Same initial seed/order as the actual completed full-finetuning arm.
    rng = np.random.default_rng(17)
    order = old.order_for_epoch(rng, groups)
    first = load(REFERENCE / "model/best.json")
    oldck = load_checkpoint(REFERENCE / "model" / first["path"])
    assert oldck.model.steps == 1 and np.array_equal(order, oldck.permutation)
    sources = [
        Path(__file__),
        Path(__file__).with_name("evaluate-frozen-backbone-v3.py"),
        ROOT / "ai-training/src/idps_ai/training/frozen_body_adapter.py",
        Path(old.__file__),
        Path(__file__).with_name("integration-guard.py"),
    ]
    design = {
        "schema_version": "frozen-body-adapter-experiment-1",
        "run_id": run.name,
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "hypothesis": "Add useful body syntax while original v2 function survives on zero-selected-tail inputs",
        "research_scope": "EXPLORATORY; hypothesis motivated by exposed outcomes;31featuremembership solely fixed schema, not label/score-selected. No independent confirmation.",
        "selection": selection(),
        "selection_fingerprint": digest(selection()),
        "logical_architecture": [634, 64, 64, 64, 64, 8],
        "trainable_shape": [31, 64],
        "trainable_parameters": 1984,
        "initialization": "A zeros, no adapterbias, fresh Adam moments zeros; original v2 parameters frozen read-only",
        "frozen_generation": str(frozen.path.relative_to(ROOT)),
        "frozen_manifest_sha256": file_sha256(frozen.path / "manifest.json"),
        "frozen_arrays_sha256": file_sha256(frozen.path / "arrays.npz"),
        "backbone_parameter_hashes": adapter.backbone_hashes,
        "dataset_release": cfg["dataset_release"],
        "dataset_fingerprint": cfg["dataset_fingerprint"],
        "dataset_manifest_sha256": cfg["dataset_release_manifest_sha256"],
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "sampler_fingerprint": oldplan["sampler_fingerprint"],
        "sampler": "Same lineage roundrobin without replacement asfullpilot; canonical42views onceperepoch",
        "seed": 17,
        "batch_size": 16,
        "epochs": 20,
        "updates": 60,
        "objective": adapter.objective,
        "optimizer": {
            "kind": "AdamW",
            "learning_rate": 0.0001,
            "weight_decay": 0.0001,
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "global_L2_clip": 1.0,
            "state_shapes": {"A": [31, 64]},
            "fresh": True,
        },
        "compatibility_notes": [
            "Clip/Adam/decay apply only to trainable31x64subspace; full-finetune clipped its whole trainable network. Necessary optimizer isolation, not a tuned hyperparameter.",
            "Original588affine rounded then separate31affine rounded+FP32sum; matches v2 byte-exact on zero contribution, differs from full634reduction on body-active rows.",
        ],
        "arithmetic": adapter.metadata()["arithmetic"],
        "checkpoint_every": 3,
        "threshold_rule": "strict>max eligible canonical CALbenign only; original frozen threshold also predeclared secondary point, never selected after DEV/body scores",
        "reference_thresholds": load(REFERENCE / "evaluation/thresholds.json")["thresholds"],
        "reference_thresholds_sha256": file_sha256(REFERENCE / "evaluation/thresholds.json"),
        "full_v3_checkpoint": load(REFERENCE / "completion.json"),
        "body_cohort_manifest_sha256": file_sha256(BODY / "eligible-manifest.json"),
        "body_cohort_role": "Already exposed exploratory evaluation only; never gradients or calibration",
        "preflight": {
            "ZERO_ADAPTER_PARITY": "PASS_BYTE_EXACT_TRAIN42_AND_FEATURE_ONLY_NON_OK_PROBES",
            "non_OK_probe_counts": counts,
            "full46notzero": "State/media indicators remain nonzero; only selected31tail iszero perblank+validator",
            "gradient_shape": [31, 64],
            "forward_backward_finite": True,
            "backbone_readonly_and_hashes": "PASS",
        },
        "decision_screen": "CASEA only if backbone/zero-body parity verified, >=2of4bodyXSS TP and0of4FP at CALpoint, no additional benignFP on90DEV vsfrozen. Fixed-v2threshold secondary only. Otherwise CASEB; integrity/parity failure CASEC. No promotion.",
        "ablations": ["Adapter contribution disabled", "Counts6only", "Punctuation/pattern25only"],
        "checkpoint_selection": "Final60steps only",
        "resources": {
            "initial_one_core_quota_percent": 25,
            "memory_GiB": 2,
            "reserve_system_GiB": 4,
            "rolling_active_limit_C": 80,
            "instant_limit_C": 85,
            "independent_watchdog": True,
        },
        "sources_sha256": {str(p.relative_to(ROOT)): file_sha256(p) for p in sources},
        "sealed": "NOT_OPENED",
        "no_new_requests": True,
    }
    design["fingerprint"] = digest(design)
    run.mkdir(parents=True, mode=0o700)
    atomic_json(CONFIG, design)
    atomic_json(run / "plan.json", design)
    atomic_json(
        run / "status.json",
        {
            "status": "PREPARED",
            "run_id": run.name,
            "step": 0,
            "planned_steps": 60,
            "last_heartbeat": time.time(),
        },
    )
    print(
        json.dumps(
            {
                "run_id": run.name,
                "trainable_parameters": 1984,
                "ZERO_ADAPTER_PARITY": "PASS",
                "design_fingerprint": design["fingerprint"],
            }
        )
    )


def validate(run):
    p = load(run / "plan.json")
    assert p["fingerprint"] == digest({k: v for k, v in p.items() if k != "fingerprint"})
    assert p == load(CONFIG) and p["selection"] == selection()
    for name, sha in p["sources_sha256"].items():
        assert file_sha256(ROOT / name) == sha
    f = backbone()
    assert (
        file_sha256(f.path / "manifest.json") == p["frozen_manifest_sha256"]
        and file_sha256(f.path / "arrays.npz") == p["frozen_arrays_sha256"]
    )
    old = module("train-request-v3-pilot")
    cfg, x, y, rows, groups = old.inputs()
    assert p["dataset_fingerprint"] == cfg["dataset_fingerprint"] and p[
        "sampler_fingerprint"
    ] == digest({"ids": [r["sample_id"] for r in rows], "groups": groups})
    return p, f, old, cfg, x, y, groups


def train(run, resource, resume):
    p, f, old, cfg, x, y, groups = validate(run)
    rng = np.random.default_rng(17)
    if resume:
        assert load(run.parent / "arm-started.json")["run_id"] == run.name
        ck = load_adapter(run / "model", f.model, p["fingerprint"])
        assert not ck.used_previous
        a = ck.model
        s = ck.state
        order = ck.permutation
        assert (
            0 < a.steps < 60
            and s["dataset_fingerprint"] == p["dataset_fingerprint"]
            and s["selection_fingerprint"] == p["selection_fingerprint"]
        )
        assert s["scheduler"] == {"kind": "constant", "learning_rate": 0.0001, "step": a.steps}
        assert s["feature_contract_fingerprint"] == request_v3.fingerprint() and sorted(
            order.tolist()
        ) == list(range(42))
        assert len((run / "loss.jsonl").read_text().splitlines()) == a.steps
        rng.bit_generator.state = s["RNG"]
        epoch = s["epoch"]
        cursor = s["cursor"]
        checkpoint = ck.path
    else:
        assert not (run / "model/latest.json").exists()
        a = FrozenBodyAdapter(f.model)
        epoch = cursor = 0
        order = old.order_for_epoch(rng, groups)
        checkpoint = None
    zero = np.all(x[:, 603:] == 0, axis=1)
    reference = a.backbone.predict(x[zero, :588])[0]
    done = threading.Event()
    (run / "heartbeat").touch()

    def heartbeat():
        while not done.wait(0.2):
            (run / "heartbeat").touch()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

    def status(value, loss=None, error=None):
        monitor = (
            load(resource / "resource-status.json")
            if (resource / "resource-status.json").exists()
            else {}
        )
        atomic_json(
            run / "status.json",
            {
                "status": value,
                "run_id": run.name,
                "step": a.steps,
                "planned_steps": 60,
                "epoch": epoch,
                "cursor": cursor,
                "loss": loss,
                "checkpoint": str(checkpoint) if checkpoint else None,
                "PID": os.getpid(),
                "resource_service": monitor.get("unit"),
                "supervisor": os.environ.get("ADAPTER_SUPERVISOR"),
                "last_heartbeat": time.time(),
                "dataset_fingerprint": p["dataset_fingerprint"],
                "log": str(run / "loss.jsonl"),
                "resource_status": str(resource / "resource-status.json"),
                "error": error,
            },
        )

    def save():
        return save_checkpoint(
            run / "model",
            a,
            {
                "plan_fingerprint": p["fingerprint"],
                "dataset_fingerprint": p["dataset_fingerprint"],
                "selection_fingerprint": p["selection_fingerprint"],
                "feature_contract_fingerprint": request_v3.fingerprint(),
                "epoch": epoch,
                "cursor": cursor,
                "RNG": rng.bit_generator.state,
                "scheduler": {"kind": "constant", "learning_rate": 0.0001, "step": a.steps},
                "planned_steps": 60,
            },
            order,
        )

    try:
        with RunLock(run.parent), RunLock(run):
            deadline = time.monotonic() + 5
            watchdog = []
            while time.monotonic() < deadline:
                monitor = (
                    load(resource / "resource-status.json")
                    if (resource / "resource-status.json").exists()
                    else {}
                )
                unit = monitor.get("unit")
                watchdog = [
                    proc.pid
                    for proc in psutil.process_iter(["cmdline"])
                    if unit
                    and all(v in (proc.info["cmdline"] or []) for v in ["watchdog", "--unit", unit])
                ]
                if watchdog and monitor.get("status") == "RUNNING":
                    break
                time.sleep(0.05)
            assert watchdog and monitor["status"] == "RUNNING"
            atomic_json(
                run / ("resume-watchdog.json" if resume else "launch-watchdog.json"),
                {"PID": os.getpid(), "watchdog_PID": watchdog[0], "unit": unit, "ready": True},
            )
            if not resume:
                assert not (run.parent / "arm-started.json").exists()
                atomic_json(
                    run.parent / "arm-started.json",
                    {"run_id": run.name, "plan_fingerprint": p["fingerprint"]},
                )
            status("RUNNING")
            with (run / "loss.jsonl").open("a" if resume else "x") as log:
                while a.steps < 60 and epoch < 20:
                    ix = order[cursor : cursor + 16]
                    assert len(ix) > 0
                    loss = a.train_batch(x[ix], y[ix])
                    cursor += len(ix)
                    assert a.predict(x[zero])[0].tobytes() == reference.tobytes(), (
                        "Zero-selected TRAIN score regression"
                    )
                    log.write(
                        json.dumps(
                            {
                                "step": a.steps,
                                "epoch": epoch,
                                "cursor": cursor,
                                "batch_rows": len(ix),
                                "loss": loss,
                                "timestamp": time.time(),
                            }
                        )
                        + "\n"
                    )
                    log.flush()
                    os.fsync(log.fileno())
                    if cursor == 42:
                        epoch += 1
                        if epoch < 20:
                            cursor = 0
                            order = old.order_for_epoch(rng, groups)
                    if a.steps == 1 or a.steps % 3 == 0:
                        checkpoint = save()
                    if a.steps == 1 and not resume:
                        ck = load_adapter(run / "model", f.model, p["fingerprint"])
                        assert (
                            ck.model.steps == 1
                            and ck.state["cursor"] == 16
                            and not ck.used_previous
                        )
                        assert all(
                            np.array_equal(v, ck.model.arrays()[k]) for k, v in a.arrays().items()
                        )
                        a.assert_frozen()
                        assert ck.model.backbone_hashes == p["backbone_parameter_hashes"]
                        atomic_json(
                            run / "actual-preflight.json",
                            {
                                "status": "PASS",
                                "update1_committed": True,
                                "checkpoint_reload": "PASS",
                                "gradient_optimizer_isolation": "OnlyA1984,originalparamsreadOnly",
                                "backbone_hash_unchanged": True,
                                "zero_selected_TRAIN_parity": True,
                            },
                        )
                        status("RUNNING", loss)
                        break
                    status("RUNNING", loss)
            if resume:
                final = load_adapter(run / "model", f.model, p["fingerprint"])
                assert final.model.steps == 60 and epoch == 20 and not final.used_previous
                assert all(
                    np.array_equal(v, final.model.arrays()[k]) for k, v in a.arrays().items()
                )
                a.assert_frozen()
                atomic_json(
                    run / "completion.json",
                    {
                        "status": "COMPLETED",
                        "steps": 60,
                        "epochs": 20,
                        "checkpoint": str(final.path.relative_to(ROOT)),
                        "manifest_sha256": file_sha256(final.path / "manifest.json"),
                        "backbone_hash_unchanged": a.backbone_hashes
                        == p["backbone_parameter_hashes"],
                        "actual_cross_process_resume": True,
                        "final_checkpoint_verified": True,
                        "CAL_DEV_body_cohort_gradients": 0,
                    },
                )
                status("COMPLETED", loss)
    except BaseException as exc:
        status("FAILED", error=type(exc).__name__)
        raise
    finally:
        done.set()
        thread.join(timeout=1)
    if not resume:
        subprocess.run(
            [
                sys.executable,
                __file__,
                "train",
                "--run",
                str(run),
                "--resource",
                str(resource),
                "--resume",
            ],
            check=True,
        )


def supervise(run, resource):
    plan = load(run / "plan.json")
    guard = module("integration-guard")
    assert (
        file_sha256(guard.__file__)
        == plan["sources_sha256"]["ai-training/scripts/integration-guard.py"]
    )
    try:
        guard.run(
            [sys.executable, __file__, "train", "--run", str(run), "--resource", str(resource)],
            resource,
            quota=25,
            max_seconds=300,
            memory_gib=2,
            cutoff=85,
        )
        assert load(run / "completion.json")["final_checkpoint_verified"]
        atomic_json(
            run / "supervisor-result.json",
            {
                "status": "COMPLETED",
                "service": os.environ.get("ADAPTER_SUPERVISOR"),
                "finished_at": time.time(),
            },
        )
    except BaseException as exc:
        monitor = (
            load(resource / "resource-status.json")
            if (resource / "resource-status.json").exists()
            else {}
        )
        state = load(run / "status.json")
        state.update(
            status=monitor.get("status", "FAILED")
            if monitor.get("status") in ["FAILED", "THERMAL_STOPPED", "INTERRUPTED"]
            else "FAILED",
            error=type(exc).__name__,
            last_heartbeat=time.time(),
        )
        atomic_json(run / "status.json", state)
        atomic_json(run / "supervisor-result.json", state)
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "train", "supervise"])
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--resource", type=Path)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        if args.action == "prepare":
            prepare(args.run.resolve())
        elif args.action == "train":
            train(args.run.resolve(), args.resource.resolve(), args.resume)
        else:
            supervise(args.run.resolve(), args.resource.resolve())
