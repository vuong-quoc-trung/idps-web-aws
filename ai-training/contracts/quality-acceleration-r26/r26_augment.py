"""Check whether already-authorized SR-BH FIT supports a second recovery round.

The earlier transfer diagnostic never changed its global FIT permission. This
new derivative preserves every historical CAL/DEV/TEST role. No model scores
or research TEST labels are used to select these components or role assignments.
"""

# isort: skip_file

import argparse
import csv
import hashlib
import hmac
import os
import time
from pathlib import Path

import numpy as np

from r26_common import ARTIFACTS, SEED, atomic_json, check, file_sha256, read
from idps_ai.features.safe_content import symbolic_request
from r14_audit import R6, R13
from r18_data import component_index
from r16_waf import origin_view, write_array

ROLES = ("FIT", "TUNING", "CAL_FIT", "CAL_OP", "RESEARCH_TEST")


def run(out):
    started = time.monotonic()
    root = out / "source2-recovery"
    root.mkdir(exist_ok=True)
    check(not (root / "manifest.json").exists(), "Source2 role manifest already locked")
    prior = read(out / "transfer.json")["SR_BH_transfer"]["metadata"]
    check(
        prior["source_role"] == "EXISTING_FIT_TRANSFER_DIAGNOSTIC_ONLY_NO_TRAINING_ADDITION",
        "Source permission must remain existing FIT",
    )
    atomic_json(
        root / "protocol.json",
        {
            "purpose": "Feasibility of adding allowed publisher FIT after the prespecified source-transfer FPR exceeded 1%",
            "trigger_metric": {
                "source": "SRBH allowed FIT transfer",
                "r26_fpr": 0.02770943933704519,
            },
            "not_triggered_by_notes_research_test": True,
            "old_R26A_model_and_test": "Immutable, no model configuration or operating point changed",
            "split": "URI76 coarse and symbolic URI template closure; fixed seed2602 SHA bucket 60/10/10/10/10; no seed search",
            "required_support": "At least 32 examples of each class in each research role before any augmentation training",
            "source_label": "SR-BH publisher annotation, not native ATTACK_VERIFIED",
            "feature_directions": "No new features; use selected URI100 only",
        },
    )
    with np.load(out / "srbh-transfer-numeric.npz", allow_pickle=False) as z:
        x, y = z["x"], z["y"]
    check(
        len(np.unique(x[:, :76], axis=0)) == len(x),
        "Retained source2 URI76 representatives must be unique",
    )
    lookup = {row[:76].tobytes(): i for i, row in enumerate(x)}
    with np.load(R6 / "development.npz", allow_pickle=False) as z:
        original_vectors = z["fit"]
    with np.load(R13 / "partition.npz", allow_pickle=False) as z:
        allowed = z["fit"]
    identities = read(R6 / "fit-identities.json")
    event_to_position = {
        row["event"]: lookup[original_vectors[i].tobytes()]
        for i, row in enumerate(identities)
        if allowed[i] and original_vectors[i].tobytes() in lookup
    }
    check(len(event_to_position) == len(x), "Approved source2 original coordinate mapping")
    source = ARTIFACTS / "generalization_20261031/srbh-public/data_capec_multilabel.csv"
    check(file_sha256(source) == prior["source_sha256"], "Source2 publisher pin")
    key = (ARTIFACTS / "generalization_20261031/srbh-identity.key").read_bytes()
    template = [None] * len(x)
    coordinate = np.full(len(x), -1, np.int64)
    csv.field_size_limit(1048576)
    with source.open(newline="", encoding="utf-8-sig") as stream:
        for ordinal, row in enumerate(csv.DictReader(stream, strict=True)):
            event = hmac.new(
                key, f"{prior['source_sha256']}:record:{ordinal}".encode(), hashlib.sha256
            ).hexdigest()
            if event not in event_to_position:
                continue
            i = event_to_position[event]
            target = origin_view(row["request_http_request"])[0]
            symbolic, _ = symbolic_request(row["request_http_method"], target, None, None)
            template[i] = hashlib.sha256(symbolic.encode()).digest()
            coordinate[i] = ordinal
    check(
        all(t is not None for t in template) and np.all(coordinate >= 0),
        "Source2 lineage metadata complete",
    )
    groups = component_index(x[:, :76], enumerate(template))
    role = np.zeros(len(x), np.int8)
    for component in np.unique(groups):
        subset = np.flatnonzero(groups == component)
        canonical = min(hashlib.sha256(v.tobytes()).hexdigest() for v in x[subset, :76])
        value = int(hashlib.sha256(f"{SEED + 1}:{canonical}".encode()).hexdigest()[:8], 16) % 100
        role[subset] = (
            0 if value < 60 else 1 if value < 70 else 2 if value < 80 else 3 if value < 90 else 4
        )
    rows = {}
    for i, name in enumerate(ROLES):
        selected = role == i
        path = root / f"{name.lower()}.npz"
        write_array(
            path,
            x=x[selected],
            y=y[selected],
            group=groups[selected],
            coordinate=coordinate[selected],
        )
        rows[name] = {
            "originals": int(selected.sum()),
            "normal_anomalous": np.bincount(y[selected], minlength=2).tolist(),
            "groups": len(np.unique(groups[selected])),
            "sha256": file_sha256(path),
        }
    support = all(min(row["normal_anomalous"]) >= 32 for row in rows.values())
    atomic_json(
        root / "manifest.json",
        {
            "source_global_role": "EXISTING_R13_FIT_ONLY",
            "source_sha256": prior["source_sha256"],
            "protocol_sha256": file_sha256(root / "protocol.json"),
            "label_source": "PUBLISHER_CAPEC_NORMAL",
            "native_verified_added": 0,
            "retained_originals": len(x),
            "roles": rows,
            "closure_groups": len(np.unique(groups)),
            "largest_group": int(np.bincount(groups).max()),
            "augmentation_training_ready": support,
            "decision": "PROCEED_TO_BOUNDED_SOURCE_AUGMENTATION_PILOT"
            if support
            else "BLOCKED_LINEAGE_CLASS_SUPPORT",
            "role_assignment_uses_scores": False,
            "historical_CAL_DEV_TEST_payloads_opened": False,
            "seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
