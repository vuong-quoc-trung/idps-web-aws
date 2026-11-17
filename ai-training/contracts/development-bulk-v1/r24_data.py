"""Materialize only permitted publisher FIT/TUNING features and count contracts."""

import argparse
import os
import secrets
import time
from functools import lru_cache
from hashlib import blake2s
from pathlib import Path

import numpy as np
import r16_waf as waf
from r18_data import check, read, status
from r19_train import training_cells
from r20_quality import PINS, R19
from r23_features import VERSION, describe_lane, numeric, sketch
from r23_pilot import select_fit

from idps_ai.common import atomic_json, file_sha256
from idps_ai.features.request_time import from_request, schema


def census(x, labels):
    unique, inverse = np.unique(x, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    counts = np.zeros((len(unique), 2), dtype=np.int64)
    np.add.at(counts, (inverse, labels), 1)
    support = counts.sum(axis=1)
    mixed = np.all(counts > 0, axis=1)
    summary = {
        "originals": int(support.sum()),
        "classes_normal_anomalous": counts.sum(axis=0).tolist(),
        "distinct": len(unique),
        "mixed": int(mixed.sum()),
        "originals_in_mixed": int(support[mixed].sum()),
        "anomalous_in_mixed": int(counts[mixed, 1].sum()),
        "max_originals_per_vector": int(support.max()),
        "originals_in_colliding_vectors": int(support[support > 1].sum()),
        "minority_mass": int(counts.min(axis=1).sum()),
    }
    return unique, counts, inverse, summary


def frame(out):
    status(out, "R24_ETL_JOIN")
    start = time.monotonic()
    for name in ("waf-r19.npz", "dataset-manifest.json"):
        check(file_sha256(R19 / name) == PINS[name], "R19 ETL source digest changed")
    check(file_sha256(waf.WAF) == waf.WAF_SHA, "Publisher TRAIN digest changed")
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as archive:
        x, groups, counts = (archive[name] for name in ("x", "component", "counts"))
        index, coord, labels = [
            np.concatenate((archive[f"fit_{k}"], archive[f"tuning_{k}"]))
            for k in ("index", "row", "label")
        ]
        nfit = len(archive["fit_index"])
    check(
        nfit == 400_000 and len(np.unique(coord)) == len(coord),
        "R19 unique physical coordinates differ",
    )
    check(
        not np.intersect1d(groups[index[:nfit]], groups[index[nfit:]]).size, "R19 component overlap"
    )
    picked = np.r_[select_fit(index[:nfit], labels[:nfit]), np.ones(len(index) - nfit, dtype=bool)]
    match = np.full(len(index), -1, dtype=np.int64)
    match[picked] = np.arange(picked.sum())
    order = np.argsort(coord)
    sorted_coord = coord[order]
    extension = np.zeros((len(coord), 24), np.uint8)
    lexical = np.zeros((picked.sum(), 128), np.uint8)
    context = np.zeros((len(coord), 2), np.uint8)
    secret = secrets.token_bytes(32)
    target_keys = [set(), set()]
    parity = set()

    @lru_cache(maxsize=4096)
    def structure(target):
        lane = sketch(target)
        result = np.minimum(31, describe_lane(lane[0], b"/") + describe_lane(lane[1], b"&")).astype(
            np.uint8
        )
        return lane, result

    seen, offset = 0, 0
    for batch in waf.source().iter_batches(
        batch_size=waf.BATCH, columns=["method", "url", "label"], use_threads=False
    ):
        end = offset + batch.num_rows
        lo, hi = np.searchsorted(sorted_coord, [offset, end])
        rows = batch.take(sorted_coord[lo:hi] - offset).to_pylist() if hi > lo else ()
        for i, row in zip(order[lo:hi], rows, strict=True):
            origin = waf.origin_view(row["url"])
            check(origin and waf.LABEL[row["label"]] == labels[i], "Publisher coordinate binding")
            target, form, _ = origin
            method = row["method"]
            target_keys[int(i >= nfit)].add(
                blake2s(
                    method.encode() + b"\0" + target.encode(), key=secret, digest_size=16
                ).digest()
            )
            lane, extension[i] = structure(target)
            context[i] = (
                0 if method == "GET" else 1 if method == "POST" else 2,
                int(form == "absolute"),
            )
            if picked[i]:
                check(
                    from_request(target, method).tobytes() == x[index[i]].tobytes(),
                    "URI76 projection binding",
                )
                exact_structure, lexical[match[i]] = numeric(*lane)
                check(
                    np.array_equal(exact_structure, extension[i]), "Structure implementation drift"
                )
                if len(parity) < 256:
                    parity.add(lane)
            seen += 1
        offset = end
    check(
        seen == len(index) and not target_keys[0].intersection(target_keys[1]),
        "Origin-form coordinate or target overlap",
    )
    fit, fit_counts, fit_inv, fit_summary = census(
        np.column_stack((x[index[:nfit]], extension[:nfit].astype(np.float32) / 31)), labels[:nfit]
    )
    check(np.array_equal(fit[fit_inv, :76], x[index[:nfit]]), "URI76 prefix drift")
    tune = np.column_stack((x[index[nfit:]], extension[nfit:].astype(np.float32) / 31))
    check(
        not {row.tobytes() for row in np.floor(fit * 16)}.intersection(
            row.tobytes() for row in np.floor(tune * 16)
        ),
        "Bucket embargo failed",
    )
    first = np.unique(fit_inv, return_index=True)[1]
    parent = index[:nfit][first]
    _, base_counts, _, base_summary = census(x[index[:nfit]], labels[:nfit])
    fit_idx = np.unique(index[:nfit])
    _, _, _, balance, weight_report = training_cells(counts[fit_idx])
    original_weight = np.minimum(8, np.sqrt(counts.sum(axis=1))) / counts.sum(axis=1)
    aligned = index[picked[:nfit].nonzero()[0]]
    sample_y = labels[:nfit][picked[:nfit]]
    sample_counts = np.zeros_like(counts)
    np.add.at(sample_counts, (aligned, sample_y), 1)
    sample_mass = (
        original_weight[aligned] * counts[aligned, sample_y] / sample_counts[aligned, sample_y]
    )
    # Preserve parent URI76 loss mass when extended views split a large parent.
    final_cell_mass = fit_counts * original_weight[parent, None]
    check(
        np.allclose(
            final_cell_mass.sum(axis=0),
            (counts[fit_idx] * original_weight[fit_idx, None]).sum(axis=0),
        ),
        "Weight conservation",
    )
    path = out / "publisher-r24-uri100.npz"
    waf.write_array(
        path,
        fit_x=fit,
        fit_counts=fit_counts,
        fit_parent=parent,
        fit_cell_mass=final_cell_mass,
        pilot_fit_x=np.column_stack(
            (x[aligned], extension[:nfit][picked[:nfit]].astype(np.float32) / 31)
        ),
        pilot_fit_y=sample_y,
        pilot_fit_mass=sample_mass,
        binary_class_weights=balance,
        pilot_lexical=lexical,
        tune_x=tune,
        tune_y=labels[nfit:],
        tune_groups=groups[index[nfit:]],
        tune_context=context[nfit:],
    )
    with (out / "parity-sketch.tsv").open("w", encoding="ascii") as f:
        for p, q in sorted(parity):
            f.write(p.decode() + "\t" + q.decode() + "\n")
    seconds = time.monotonic() - start
    atomic_json(
        out / "dataset-manifest.json",
        {
            "role": "PUBLISHER_DEVELOPMENT_ONLY",
            "label_task": "WAF_NORMAL_ANOMALOUS",
            "data_sha256": file_sha256(path),
            "fit_uri100": fit_summary,
            "fit_uri76": base_summary,
            "tuning_uri100": census(tune, labels[nfit:])[3],
            "fit_tuning_normalized_exact_overlap": 0,
            "fit_tuning_extended_bucket_overlap": 0,
            "distinct_normalized_method_target": [len(p) for p in target_keys],
            "inherited_component_split": True,
            "fit_tuning_group_counts": [
                len(np.unique(groups[index[:nfit]])),
                len(np.unique(groups[index[nfit:]])),
            ],
            "fit_weighting": weight_report,
            "base_count_reconciled": int(base_counts.sum()),
            "preprocessing": {
                "uri76": schema(),
                "extension": VERSION,
                "width": 100,
                "extension_scale": 31,
                "feature_code_sha256": file_sha256(Path(__file__).with_name("r23_features.py")),
            },
            "sources": {
                "waf_train_sha256": waf.WAF_SHA,
                "r19_npz_sha256": PINS["waf-r19.npz"],
                "r19_manifest_sha256": PINS["dataset-manifest.json"],
            },
            "roles": {
                "fit_count": nfit,
                "tuning_count": len(index) - nfit,
                "new_cal": None,
                "new_test": None,
                "protected_roles_read": False,
            },
            "etl_seconds": seconds,
            "projected_originals_per_second": len(index) / seconds,
            "label_conflict_at_original_quarantined_r19": read(R19 / "dataset-manifest.json")[
                "type_a_original_conflicts_quarantined"
            ],
            "raw_inputs_persisted": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    frame(parser.parse_args().out)
