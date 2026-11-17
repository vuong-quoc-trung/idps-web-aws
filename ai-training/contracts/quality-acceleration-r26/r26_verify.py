"""New-process exact epoch replay and post-selection information diagnostics."""

# isort: skip_file

import argparse
import os
from pathlib import Path

import numpy as np

from r26_common import atomic_json, check, file_sha256, read
from r26_learning import epoch, make_training, source_data
from idps_ai.common import digest
from idps_ai.training.checkpoint import load_checkpoint
from r18_train import WeightedSwiGLU
from r20_calibration import uri76_oracle
from r24_data import census


def effective_diversity(x, y, width):
    unique, counts, _, summary = census(x[:, :width], y)
    group_mass = np.minimum(8, np.sqrt(counts.sum(axis=1)))
    mass = counts * (group_mass / counts.sum(axis=1))[:, None]
    mass /= 2 * mass.sum(axis=0)
    per_original = np.divide(mass, counts, out=np.zeros_like(mass), where=counts > 0)
    square_original = float((counts * per_original**2).sum())
    square_vector = float((mass.sum(axis=1) ** 2).sum())
    return {
        "census": summary,
        "kish_original": 1 / square_original,
        "kish_vector": 1 / square_vector,
    }, unique


def run(out):
    plan = read(out / "training-plan.json")
    check(
        plan["code_sha256"] == file_sha256(Path(__file__).with_name("r26_train.py")),
        "Executed trainer code binding",
    )
    check(
        plan["learning_code_sha256"] == file_sha256(Path(__file__).with_name("r26_learning.py")),
        "Sampler/weighted objective binding",
    )
    train, _ = source_data(out)
    width = plan["schema_width"]
    x, y, weight, data_report = make_training(train, width)
    root = out / "training/model"
    pointer = read(root / "previous.json")
    previous = load_checkpoint(root / pointer["path"])
    latest = load_checkpoint(root)
    check(previous.state["epoch"] + 1 == latest.state["epoch"], "Adjacent committed replay epochs")
    check(previous.state["binding"] == latest.state["binding"] == digest(plan), "Replay binding")
    model = WeightedSwiGLU.from_arrays(previous.model.metadata(), previous.model.arrays())
    permutation, loss = epoch(model, x, y, weight, previous.state["epoch"], plan["schedule"])
    check(
        loss == latest.state["last_loss"] and model.steps == latest.model.steps,
        "Replay loss and step equality",
    )
    np.testing.assert_array_equal(permutation, latest.permutation)
    for name, values in model.arrays().items():
        np.testing.assert_array_equal(values, latest.model.arrays()[name])
    state = read(out / "data-v2/etl-state.json")
    with np.load(out / "data-v2/waf-r26.npz", allow_pickle=False) as data:
        matrix = data["x"]
        nfit = int(data["nfit"])
        groups = data["component"]
        check(
            not np.intersect1d(groups[:nfit], groups[nfit:]).size,
            "Frozen WAF FIT/TUNING component separation",
        )
    seen = np.zeros(len(matrix), bool)
    for chunk in state["chunks"]:
        path = out / "data-v2/chunks" / chunk["file"]
        check(file_sha256(path) == chunk["sha256"], "ETL prefix digest")
        with np.load(path, allow_pickle=False) as data:
            position = data["position"]
            check(not seen[position].any(), "ETL duplicate original")
            np.testing.assert_array_equal(data["x"], matrix[position])
            seen[position] = True
    check(seen.all() and state["selected"] == len(matrix), "ETL prefix rebuild census")
    diversity, unique = [], []
    for values, labels, _ in train:
        report, vectors = effective_diversity(values, labels, width)
        diversity.append(report)
        unique.append(vectors)
    total_ess = 4 / sum(1 / record["kish_original"] for record in diversity)
    selected = read(out / "evaluation.json")["selected_before_research_test"]
    lock = read(out / "evaluation-lock.json")
    cut = lock["models"][selected]["cutoff"]
    with np.load(out / "research-test-scores.npz", allow_pickle=False) as scores:
        test_scores = scores[selected]
    diagnostics = {}
    for role in ("CAL_OP", "RESEARCH_TEST"):
        with np.load(out / "notes" / f"{role.lower()}.npz", allow_pickle=False) as data:
            values, truth = data["x"][:, :width], data["y"]
            _, counts, inverse, summary = census(values, truth)
            oracle = {str(fpr): uri76_oracle(counts, fpr=fpr) for fpr in (0.005, 0.01)}
            diagnostics[role] = {"census": summary, "label_lookup_ceiling_not_a_model": oracle}
            if role == "RESEARCH_TEST":
                missed = (truth == 1) & (test_scores <= cut)
                benign_collision = counts[inverse, 0] > 0
                content = data["x"]
                diagnostics[role]["frozen_candidate_false_negatives"] = {
                    "total": int(missed.sum()),
                    "sharing_uri100_with_normal": int((missed & benign_collision).sum()),
                    "observed_nonempty_body": int(
                        (missed & (content[:, 229] == 1) & (content[:, 243] == 0)).sum()
                    ),
                    "body_missing_or_privacy_withheld": int(
                        (missed & (content[:, 229] == 0)).sum()
                    ),
                }
    atomic_json(
        out / "verification.json",
        {
            "resume": {
                "state": "PASS",
                "new_worker_pid": os.getpid(),
                "from_epoch": previous.state["epoch"],
                "to_epoch": latest.state["epoch"],
                "optimizer_parameters_sampler_loss": "BIT_EXACT",
                "global_step": model.steps,
                "previous_manifest_sha256": pointer["manifest_sha256"],
                "binding": digest(plan),
                "mid_batch_resume": "NOT_CLAIMED",
            },
            "etl_committed_chunk_rebuild": "EXACT_NO_DUPLICATE_OR_MISSING_ORIGINAL",
            "source_diversity": diversity,
            "combined_kish_original_equal_source_weight": total_ess,
            "union_unique_final_vectors": len(np.unique(np.concatenate(unique), axis=0)),
            "original_fit_count": sum(row["originals"] for row in data_report),
            "post_selection_diagnostics": diagnostics,
            "diagnostic_caveat": "Label-lookup ceilings describe this exposed small publisher cohort; never used to alter the selected R26 model or threshold",
            "native_train_dev": [0, 0],
            "protected_historical_payloads_read": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
