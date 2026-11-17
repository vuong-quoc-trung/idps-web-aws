"""Incremental numeric-only join of the frozen WAF FIT/TUNING coordinates."""

# isort: skip_file

import argparse
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
from r26_common import R24, R24_DATA_SHA, atomic_json, check, file_sha256, read, status
from r16_waf import BATCH, LABEL, WAF, WAF_SHA, origin_view, source, write_array
from r20_quality import PINS, R19
from r23_pilot import select_fit
from r24_data import census
from r26_features import FULL_WIDTH, URI_WIDTH, project, schema

from idps_ai.common import digest
from idps_ai.features.request_time import from_request
from idps_ai.training.checkpoint import RunLock


def census_report(x, y):
    return census(x, y)[3]


def run(out):
    started = time.monotonic()
    check(file_sha256(WAF) == WAF_SHA, "Pinned WAF publisher TRAIN differs")
    check(file_sha256(R19 / "waf-r19.npz") == PINS["waf-r19.npz"], "R19 roster pin")
    check(file_sha256(R24 / "publisher-r24-uri100.npz") == R24_DATA_SHA, "R24 data pin")
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as z:
        coordinates = np.r_[z["fit_row"], z["tuning_row"]]
        labels = np.r_[z["fit_label"], z["tuning_label"]]
        indices = np.r_[z["fit_index"], z["tuning_index"]]
        parents = z["x"]
        counts = z["counts"]
        components = z["component"][indices]
        nfit = len(z["fit_row"])
    check(
        nfit == 400000 and len(np.unique(coordinates)) == len(coordinates),
        "Original roster identity",
    )
    order = np.argsort(coordinates)
    sorted_coordinates = coordinates[order]
    binding = digest(
        {
            "source": WAF_SHA,
            "roster": PINS["waf-r19.npz"],
            "schema": schema(),
            "feature_code": file_sha256(Path(__file__).with_name("r26_features.py")),
            "etl_code": file_sha256(__file__),
        }
    )
    chunk_dir = out / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    with RunLock(out / "etl"):
        state_path = out / "etl-state.json"
        state = (
            read(state_path)
            if state_path.exists()
            else {
                "binding": binding,
                "next_batch": 0,
                "selected": 0,
                "chunks": [],
                "availability": {},
            }
        )
        check(state["binding"] == binding, "ETL checkpoint binding differs")
        availability = Counter(state["availability"])
        offset = 0
        for batch_number, batch in enumerate(
            source().iter_batches(
                batch_size=BATCH,
                columns=["method", "url", "label", "headers", "body"],
                use_threads=False,
            )
        ):
            end = offset + batch.num_rows
            lo, hi = np.searchsorted(sorted_coordinates, [offset, end])
            if batch_number < state["next_batch"]:
                offset = end
                continue
            positions = order[lo:hi]
            projected = np.zeros((len(positions), FULL_WIDTH), np.float32)
            context = np.zeros((len(positions), 4), np.uint8)
            raw = batch.take(sorted_coordinates[lo:hi] - offset).to_pylist() if hi > lo else ()
            batch_availability = Counter()
            for j, (i, record) in enumerate(zip(positions, raw, strict=True)):
                normalized = origin_view(record["url"])
                check(
                    normalized and LABEL[record["label"]] == labels[i],
                    "WAF coordinate/label binding",
                )
                target, form, _ = normalized
                if j == 0:
                    np.testing.assert_array_equal(
                        from_request(target, record["method"]), parents[indices[i]]
                    )
                projected[j], observation = project(
                    target,
                    record["method"],
                    record["headers"],
                    record["body"],
                    base=parents[indices[i]],
                )
                context[j] = (
                    0 if record["method"] == "GET" else 1 if record["method"] == "POST" else 2,
                    int(form == "absolute"),
                    int(projected[j, -16]),
                    int(projected[j, -15]),
                )
                role = "fit" if i < nfit else "tuning"
                batch_availability[f"{role}:{labels[i]}:{observation['body_state']}"] += 1
            path = chunk_dir / f"batch-{batch_number:04}.npz"
            if len(positions):
                payload = {"position": positions, "x": projected, "context": context}
                if path.exists():
                    # Reconcile an immutable chunk committed immediately before
                    # a state-pointer interruption, without duplicating output.
                    with np.load(path, allow_pickle=False) as old:
                        for name, value in payload.items():
                            np.testing.assert_array_equal(old[name], value)
                else:
                    write_array(path, **payload)
                state["chunks"].append(
                    {"file": path.name, "sha256": file_sha256(path), "rows": len(positions)}
                )
            availability.update(batch_availability)
            state.update(
                next_batch=batch_number + 1,
                selected=state["selected"] + len(positions),
                availability=dict(availability),
            )
            atomic_json(state_path, state)
            elapsed = max(time.monotonic() - started, 1e-9)
            status(
                out,
                "RUNNING",
                "WAF_ETL",
                originals_committed=state["selected"],
                raw_cursor=end,
                raw_total=1924461,
                elapsed_seconds=elapsed,
            )
            offset = end
        check(state["selected"] == len(coordinates), "ETL selected-row census")
        matrix = np.zeros((len(coordinates), FULL_WIDTH), np.float32)
        context = np.zeros((len(coordinates), 4), np.uint8)
        seen = np.zeros(len(coordinates), bool)
        for chunk in state["chunks"]:
            path = chunk_dir / chunk["file"]
            check(file_sha256(path) == chunk["sha256"], "Numeric chunk digest differs")
            with np.load(path, allow_pickle=False) as z:
                position = z["position"]
                check(not seen[position].any(), "Duplicate committed original coordinate")
                matrix[position] = z["x"]
                context[position] = z["context"]
                seen[position] = True
        check(seen.all(), "Missing numeric original")
        with np.load(R24 / "publisher-r24-uri100.npz", allow_pickle=False) as z:
            np.testing.assert_array_equal(matrix[nfit:, :100], z["tune_x"])
            np.testing.assert_array_equal(np.unique(matrix[:nfit, :100], axis=0), z["fit_x"])
            balance = z["binary_class_weights"]
        picked = select_fit(indices[:nfit], labels[:nfit])
        pilot_positions = np.flatnonzero(picked)
        original_mass = np.minimum(8, np.sqrt(counts.sum(axis=1))) / counts.sum(axis=1)
        sample_counts = np.zeros_like(counts)
        np.add.at(sample_counts, (indices[pilot_positions], labels[pilot_positions]), 1)
        pilot_mass = (
            original_mass[indices[pilot_positions]]
            * counts[indices[pilot_positions], labels[pilot_positions]]
            / sample_counts[indices[pilot_positions], labels[pilot_positions]]
        )
        path = out / "waf-r26.npz"
        write_array(
            path,
            x=matrix,
            y=labels,
            parent=indices,
            component=components,
            coordinates=coordinates,
            context=context,
            nfit=np.array(nfit),
            pilot_position=pilot_positions,
            pilot_mass=pilot_mass,
            original_mass=original_mass[indices],
            binary_class_weights=balance,
        )
        metrics = {}
        for name, width in (("URI100", 100), ("URI164_A", URI_WIDTH), ("HTTP244_B", FULL_WIDTH)):
            metrics[name] = {
                "fit": census_report(matrix[:nfit, :width], labels[:nfit]),
                "tuning": census_report(matrix[nfit:, :width], labels[nfit:]),
            }
        atomic_json(
            out / "waf-manifest.json",
            {
                "binding": binding,
                "dataset_sha256": file_sha256(path),
                "source_sha256": WAF_SHA,
                "schema": schema(),
                "fit_originals": nfit,
                "tuning_originals": len(labels) - nfit,
                "pilot_originals": len(pilot_positions),
                "census": metrics,
                "availability": dict(availability),
                "original_coordinate_unique": True,
                "roles_preserved": True,
                "protected_payloads_read": False,
                "publisher_eval_test_heldout_read": False,
                "label_task": "PUBLISHER_NORMAL_ANOMALOUS",
                "native_labels_added": 0,
                "feature_timestamp": "Static publisher request fields; not a native availability proof",
                "auxiliary_views_are_new_originals": False,
                "seconds": time.monotonic() - started,
            },
        )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
