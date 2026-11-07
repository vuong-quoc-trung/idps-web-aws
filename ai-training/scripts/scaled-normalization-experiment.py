#!/usr/bin/env python3
"""Two matched, sequential WAF anomaly fits. No evaluation arrays opened by training."""

import argparse
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.training.checkpoint import (
    RunLock,
    load_checkpoint,
    save_checkpoint,
    validate_generation,
)
from idps_ai.training.models import Model

ROOT = Path(__file__).resolve().parents[2]


def load(p):
    return json.loads(p.read_text())


def identity():
    files = list((ROOT / "ai-training/src/idps_ai/training").glob("*.py")) + [
        ROOT / "ai-training/src/idps_ai/features/normalization_ablation.py",
        Path(__file__),
        Path(__file__).with_name("evaluate-scaled-normalization.py"),
    ]
    return {
        "source_sha256": {str(p.relative_to(ROOT)): file_sha256(p) for p in files},
        "python": sys.version,
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ["numpy", "scipy", "scikit-learn", "threadpoolctl"]
        },
    }


def model():
    return Model(
        588,
        64,
        "deep_mlp",
        seed=31,
        objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
    )


def plan(root):
    p = load(root / "plan.json")
    assert p["plan_sha256"] == digest({k: v for k, v in p.items() if k != "plan_sha256"})
    assert p["identity"] == identity(), (
        "Source/environment changed; retain source snapshot, never force resume"
    )
    assert file_sha256(Path(p["corpus"]) / "train.npz") == p["train_file_sha256"]
    return p


def prepare(corpus, root):
    os.umask(0o077)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    r = load(corpus / "corpus-report.json")
    assert r["status"] == "PASS"
    assert r["dataset_fingerprint"] == digest(
        {k: v for k, v in r.items() if k != "dataset_fingerprint"}
    )
    for name, sha in r["files_sha256"].items():
        assert file_sha256(corpus / name) == sha
    net = model()
    assert sum(v.size for v in net.parameters.values()) == 50696
    p = {
        "schema_version": "scaled-normalization-experiment-1",
        "experiment_id": root.name,
        "corpus": str(corpus),
        "dataset_fingerprint": r["dataset_fingerprint"],
        "train_file_sha256": file_sha256(corpus / "train.npz"),
        "models": ["matched-control-shared-L2", "normalization-challenger-channel-L2"],
        "architecture": net.metadata(),
        "parameters_each": 50696,
        "arms": ["control", "challenger"],
        "seed": 31,
        "batch_size": 256,
        "updates_per_arm": 3072,
        "learning_rate": 0.001,
        "checkpoint_every": 128,
        "schedule": "constant; identical PCG64 permutations; incomplete tail dropped at epoch wrap to match original v2 trainer",
        "initialization": "NEW_INITIALIZATION; exact same initial arrays in both arms",
        "objective": "Publisher NORMAL/ANOMALOUS marginalized binary only; family labels all-1, smoothing0.005, family_weight0; no invented attack-family labels",
        "Oracle_fit_exposures": 0,
        "Oracle_reason": "Attack attempt/family supervision differs from publisher anomaly; do not silently pool labels. Oracle49 TRAIN stays exposed diagnostics; Oracle12 CAL used for separate fixed-threshold analysis only",
        "representation": "Original numeric76 + exact original rich-v2 char3-5 hash512; same privacy/tokens/hash coordinates. Challenger unit-normalizes URI/header/body counts separately before final L2; only normalization changes",
        "hypothesis": "Separate channel normalization improves XSS/command evidence without unacceptable benign flag regression; may fail because frozen privacy projection already withholds some fields",
        "checkpoint_selection": "Final3072 only; no best-loss/DEV-selected checkpoint, extra epochs, seeds or sweeps",
        "evaluation_protocol": {
            "publisher": "Original internal CAL/DEV roles, near-quarantined before fit; no publisher eval/test/heldout. Threshold score>q99(higher) of retained CAL NORMAL, same rule per model; DEV anomaly/normal counts, PR-AUC, group-aware uncertainty; these are publisher labels not independently verified attacks",
            "Oracle": "Separate stratum: immutable Oracle CAL12(10benign,2attempt) threshold strictly>max benign; exposed P0 and explicit DEVELOPMENT cohorts evaluated separately/dedup IDs, per-family Recall, benign workflow flags and hard negatives; no threshold search",
            "Oracle_TRAIN49": "Exposed diagnostic only; never independent evaluation",
            "selection": "Research retention only if DEV publisher anomaly TPR>=matched+0.02 with NORMAL flag rate<=matched+0.002 AND exposed P0>=4 extra attempt flags with no extra benign flags; INCONCLUSIVE if intervals/groups inadequate. No automatic promotion even on PASS",
            "family_targets": {
                "sqli": 0.8,
                "xss": 0.8,
                "cmd_injection": 0.8,
                "path_traversal": 0.8,
            },
            "FPR_target": 0.01,
            "prospective": "12sealed rows NOT accessed by training or automatic completion. Only upon explicit results-review request after final model/threshold fingerprints locked: one opening, no subsequent tuning; no <=1%FPR/cross-domain claim from12samples",
            "Rules": "Use existing request-bound P0 Suricata evidence where recoverable, distinguish dependent sources; no WAF PCAP/EVE so no invented rule-only/added-detection metric",
            "runtime": "Same CPU/thread cap, measure encoder/inference latency and RSS on fixed permitted inputs after completion",
        },
        "resource_policy": {
            "CPU_initial_percent_one_core": 25,
            "CPU_host_soft_fraction": 0.5,
            "MemAvailable_reserve_GiB": 4,
            "shared_host_budget_GB": 30,
            "rolling_active_seconds": 300,
            "proactive_reduce_C": 77,
            "active_rolling_stop_C": 80,
            "instant_stop_C": 90,
            "watchdog": "Independent systemd service; loss of monitor heartbeat/sensors kills exact workload; no autorestart",
        },
        "identity": identity(),
        "formal_admissions": 0,
        "frozen_changed": False,
        "promotion": False,
    }
    p["plan_sha256"] = digest(p)
    atomic_json(root / "plan.json", p)
    (root / "training-source.py").write_bytes(Path(__file__).read_bytes())
    atomic_json(
        root / "status.json",
        {
            "state": "PREPARING",
            "experiment_id": root.name,
            "dataset_fingerprint": p["dataset_fingerprint"],
            "planned_updates_per_arm": 3072,
            "last_heartbeat": time.time(),
        },
    )
    print(
        json.dumps(
            {
                "experiment": root.name,
                "train_rows": r["coverage"]["TRAIN"]["rows"],
                "steps_each": 3072,
                "plan_sha256": p["plan_sha256"],
            }
        )
    )


def resource_root(root):
    pointer = root / "active-resource.json"
    resource = Path(load(pointer)["path"]) if pointer.exists() else root / "resource"
    assert resource.resolve().is_relative_to(root.resolve()), (
        "Resource directory escaped experiment"
    )
    return resource


def write_status(root, p, state, arm, step, loss=None, error=None):
    resource = resource_root(root)
    monitor = (
        load(resource / "resource-status.json")
        if (resource / "resource-status.json").exists()
        else {}
    )
    old = load(root / "status.json") if (root / "status.json").exists() else {}
    atomic_json(
        root / "status.json",
        {
            "state": state,
            "experiment_id": root.name,
            "run_id": root.name + "/" + arm,
            "model": arm,
            "current_step": step,
            "planned_steps_per_arm": p["updates_per_arm"],
            "dataset_fingerprint": p["dataset_fingerprint"],
            "loss": loss,
            "checkpoint": str(root / arm / "latest.json"),
            "committed_checkpoint_step": load(root / arm / "latest.json")["global_step"]
            if (root / arm / "latest.json").exists()
            else 0,
            "logs": str(root / arm / "metrics.jsonl"),
            "last_heartbeat": time.time(),
            "started_at": old.get("started_at", time.time()),
            "finished_at": time.time() if state in ["COMPLETED", "FAILED", "INTERRUPTED"] else None,
            "service": monitor.get("unit"),
            "resource_status": str(resource / "resource-status.json"),
            "thermal": monitor.get("thermal"),
            "error": error,
            "promotion": False,
        },
    )


def segment(root, arm, run, through, recovery=False):
    p = plan(root)
    with np.load(Path(p["corpus"]) / "train.npz", allow_pickle=False) as d:
        x = d[arm].copy()
        y = d["y"].copy()
    if recovery:
        x = x[:600]
        y = y[:600]
    assert x.shape[1] == 588 and np.isin(y, [0, 1]).all()
    rng = np.random.default_rng(p["seed"])
    losses = []
    cursor = 0
    stop = [False]
    old_handlers = {
        s: signal.signal(s, lambda *_: stop.__setitem__(0, True))
        for s in [signal.SIGTERM, signal.SIGINT]
    }
    with RunLock(run), threadpool_limits(limits=1):
        if (run / "latest.json").exists():
            loaded = load_checkpoint(run)
            assert not loaded.used_previous
            net = loaded.model
            state = loaded.state
            assert state["plan_sha256"] == p["plan_sha256"] and state["arm"] == arm
            order = loaded.permutation
            rng.bit_generator.state = state["RNG"]
            cursor = state["sampler_cursor"]
            losses = state["losses"]
        else:
            net = model()
            order = rng.permutation(len(x)).astype(np.int64)
        assert net.steps < through <= p["updates_per_arm"]
        with (run / "metrics.jsonl").open("a") as log:
            while net.steps < through:
                if not recovery:
                    resource = resource_root(root)
                    heartbeat = resource / "heartbeat"
                    assert heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 3, (
                        "Resource supervisor heartbeat lost"
                    )
                    assert (resource / "external-watchdog.json").exists(), (
                        "Independent watchdog not ready"
                    )
                if cursor + p["batch_size"] > len(order):
                    order = rng.permutation(len(x)).astype(np.int64)
                    cursor = 0
                idx = order[cursor : cursor + p["batch_size"]]
                cursor += len(idx)
                loss = float(
                    net.train_batch(
                        x[idx],
                        np.full(len(idx), -1, np.int64),
                        p["learning_rate"],
                        binary_targets=y[idx],
                    )
                )
                losses.append(loss)
                log.write(
                    json.dumps({"step": net.steps, "loss": loss, "timestamp": time.time()}) + "\n"
                )
                log.flush()
                if (
                    net.steps == 1
                    or net.steps % p["checkpoint_every"] == 0
                    or net.steps == through
                    or stop[0]
                ):
                    state = {
                        "plan_sha256": p["plan_sha256"],
                        "dataset_fingerprint": p["dataset_fingerprint"],
                        "arm": arm,
                        "sampler_cursor": cursor,
                        "RNG": rng.bit_generator.state,
                        "scheduler": {
                            "kind": "constant",
                            "step": net.steps,
                            "learning_rate": p["learning_rate"],
                        },
                        "losses": losses,
                        "training_configuration": p,
                        "recovery_fixture": recovery,
                        "TRAIN_only": True,
                    }
                    saved = save_checkpoint(run, net, state, order)
                    validate_generation(saved)
                if not recovery:
                    write_status(root, p, "RUNNING", arm, net.steps, loss)
                if stop[0]:
                    break
        check = load_checkpoint(run)
        assert check.model.steps == net.steps and all(
            np.array_equal(v, check.model.arrays()[k]) for k, v in net.arrays().items()
        )
        atomic_json(
            run / "summary.json",
            {
                "state": "COMPLETED" if net.steps == through else "INTERRUPTED",
                "arm": arm,
                "step": net.steps,
                "checkpoint_manifest_sha256": file_sha256(check.path / "manifest.json"),
                "dataset_fingerprint": p["dataset_fingerprint"],
                "sample_exposures": net.steps * p["batch_size"],
                "train_rows": len(x),
                "final_loss": losses[-1],
                "quality_claim": False,
                "prospective_scored": 0,
            },
        )
    for s, h in old_handlers.items():
        signal.signal(s, h)
    return net.steps == through


def recovery(root):
    plan(root)
    for arm in ["control", "challenger"]:
        for label, through in [("direct", 4), ("split", 2), ("split", 4)]:
            subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "segment",
                    "--root",
                    str(root),
                    "--arm",
                    arm,
                    "--run",
                    str(root / "recovery" / arm / label),
                    "--through",
                    str(through),
                    "--recovery-fixture",
                ],
                check=True,
            )
        a = load_checkpoint(root / "recovery" / arm / "direct")
        b = load_checkpoint(root / "recovery" / arm / "split")
        assert a.state == b.state and np.array_equal(a.permutation, b.permutation)
        assert all(np.array_equal(v, b.model.arrays()[k]) for k, v in a.model.arrays().items())
    atomic_json(
        root / "recovery-proof.json",
        {
            "status": "RESUME_EXACT_TRAIN_SUBSET_4_UPDATES_WITH_WRAP",
            "arms": ["control", "challenger"],
            "fresh_processes": True,
            "scope": "First600 TRAIN rows,4updates and epoch-tail wrap; exact loss/weights/Adam/RNG/sampler/scheduler/config; full3072-step continuation not yet tested",
            "no_CAL_DEV_Oracle_or_prospective_used": True,
        },
    )
    print("PASS: both representations, fresh-process exact next update on real TRAIN subset")


def train(root, resource=None):
    p = plan(root)
    assert (
        load(root / "recovery-proof.json")["status"]
        == "RESUME_EXACT_TRAIN_SUBSET_4_UPDATES_WITH_WRAP"
    )
    with RunLock(root / "experiment-lock"):
        if resource is not None:
            assert resource.resolve().is_relative_to(root.resolve())
            pointer = {"path": str(resource.resolve()), "created_at": time.time()}
            archive = root / "resource-attempts"
            archive.mkdir(exist_ok=True, mode=0o700)
            atomic_json(archive / (str(time.time_ns()) + ".json"), pointer)
            atomic_json(root / "active-resource.json", pointer)
        try:
            for arm in p["arms"]:
                if (root / arm / "summary.json").exists():
                    done = load(root / arm / "summary.json")
                    if done["state"] == "COMPLETED" and done["step"] == p["updates_per_arm"]:
                        continue
                if not segment(root, arm, root / arm, p["updates_per_arm"]):
                    write_status(
                        root,
                        p,
                        "INTERRUPTED",
                        arm,
                        load_checkpoint(root / arm).model.steps,
                        error="Signal checkpointed; explicit resume required",
                    )
                    return
            for arm in p["arms"]:
                assert load_checkpoint(root / arm).model.steps == p["updates_per_arm"]
            atomic_json(
                root / "training-completion.json",
                {
                    "state": "COMPLETED",
                    "arms": p["arms"],
                    "steps_each": p["updates_per_arm"],
                    "dataset_fingerprint": p["dataset_fingerprint"],
                    "plan_sha256": p["plan_sha256"],
                    "prospective_opened": False,
                    "evaluated": False,
                    "promotion": False,
                },
            )
            write_status(root, p, "COMPLETED", "challenger", p["updates_per_arm"])
        except BaseException as exc:
            previous = load(root / "status.json")
            write_status(
                root,
                p,
                "FAILED",
                previous.get("model", "control"),
                previous.get("current_step", 0),
                error=type(exc).__name__ + ": " + str(exc),
            )
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "recovery", "segment", "train", "status"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--corpus", type=Path)
    p.add_argument("--arm", choices=["control", "challenger"])
    p.add_argument("--run", type=Path)
    p.add_argument("--through", type=int)
    p.add_argument("--resource", type=Path)
    p.add_argument("--recovery-fixture", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    if a.command == "prepare":
        prepare(a.corpus.resolve(), a.root.resolve())
    elif a.command == "recovery":
        recovery(a.root.resolve())
    elif a.command == "segment":
        segment(a.root.resolve(), a.arm, a.run.resolve(), a.through, a.recovery_fixture)
    elif a.command == "train":
        train(a.root.resolve(), a.resource.resolve() if a.resource else None)
    else:
        print(json.dumps(load(a.root.resolve() / "status.json"), indent=2))
