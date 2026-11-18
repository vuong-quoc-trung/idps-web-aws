"""Recover only the explicitly assigned publisher FIT/TUNING rows into private numeric shards."""

import argparse
import csv
import os
import sys
import time
from array import array
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy import sparse
from symbols import WIDTH, project

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256, load_json
from idps_ai.features.request_time import from_request

HERE = Path(__file__).resolve().parent
sys.path[:0] = [
    str(HERE.parent / name)
    for name in ("ranking-r31", "quality-acceleration-r26", "development-bulk-v1")
]
from r16_waf import LABEL, WAF_SHA, origin_view  # noqa: E402
from r16_waf import WAF as RAW_WAF  # noqa: E402
from r26_common import NOTES_SHA  # noqa: E402
from r26_notes import parse_request  # noqa: E402
from rank_pilot import B16_PIN, BASELINE, FOLDERS, ROOT, WAF, need, waf_fit, waf_tuning  # noqa: E402

NAMES = ("WAF", "NOTES", "SRBH")
RAW_NOTES = ROOT / "notes-train.parquet"
RAW_SRBH = ROOT.parent / "generalization_20261031/srbh-public/data_capec_multilabel.csv"
GATES = {
    "advance_min_macro_recall_gain": 0.05,
    "advance_max_original_or_vector_recall_regression_per_source": 0.02,
    "advance_held_source_fpr_cap": 0.01,
}


def lock(out):
    pins = {str(BASELINE): B16_PIN, str(RAW_WAF): WAF_SHA, str(RAW_NOTES): NOTES_SHA}
    wm = load_json(ROOT / "data-v2/waf-manifest.json")
    need(wm["roles_preserved"] and not wm["protected_payloads_read"], "WAF_ROLE")
    pins[str(WAF)] = wm["dataset_sha256"]
    for folder in FOLDERS.values():
        manifest = load_json(ROOT / folder / "manifest.json")
        for role in ("fit", "tuning"):
            pins[str(ROOT / folder / (role + ".npz"))] = manifest["roles"][role.upper()]["sha256"]
        if folder == FOLDERS["SRBH"]:
            pins[str(RAW_SRBH)] = manifest["source_sha256"]
    implementation = [HERE / name for name in ("dataset.py", "symbols.py", "experiment.py")]
    implementation += [
        HERE.parent / "ranking-r31/rank_pilot.py",
        HERE.parent / "quality-study-r30/calibration_pilot.py",
        HERE.parent / "quality-acceleration-r26/r26_notes.py",
        HERE.parent / "development-bulk-v1/r16_waf.py",
        REPO_ROOT / "ai-training/src/idps_ai/features/safe_content.py",
    ]
    pins.update({str(path): file_sha256(path) for path in implementation})
    need(not (out / "plan.json").exists(), "PLAN_ALREADY_EXISTS")
    atomic_json(
        out / "plan.json",
        {
            "schema": "idps-symbol-pairs-r32-v1",
            "pins": pins,
            **GATES,
            "budget": {
                "pilot": "four fixed estimators; three FIT-source exclusion fits each for symbol-only generalization; paired cluster uncertainty",
                "expansion": "full WAF 400000 and other FIT once, for winning arm only if the R31 development gate is met",
                "arms": ["SYMBOL_ONLY", "URI_RESIDUAL", "BODY_AND_URI_RESIDUAL", "TREE_BLEND"],
                "deadline_each_phase_seconds": 900,
                "seed": 3201,
            },
            "selection": "R31 shared strict source/request/vector cap plus leave-one-source cutoff. Same URI100 reference vector weights in all comparisons. Macro paired bootstrap by TUNING lineage conditional on measured cutoff.",
            "transfer": "Additional SYMBOL_ONLY source exclusions: neither feature model nor cutoff uses target source (exposed TUNING, no claim of pristine test).",
            "access": "Publisher FIT and TUNING only. No cutoff proofs inferred. Outcome/Oracle not features; no inflight or future response access.",
        },
    )


def verify(out, stage):
    p = load_json(out / "plan.json")
    for name, sha in p["pins"].items():
        if stage == "etl" or name.endswith((".py", ".onnx")):
            need(file_sha256(name) == sha, "PIN_CHANGED: " + Path(name).name)


def roster(name, full):
    if name == "WAF":
        x, y, m = waf_fit(full)
        t = waf_tuning(WAF)
        with np.load(WAF, allow_pickle=False) as a:
            n = int(a["nfit"])
            sel = np.arange(n) if full else np.sort(a["pilot_position"])
            ids = np.r_[sel, np.arange(n, len(a["y"]))]
            return (
                np.vstack((x, t["x"])),
                np.r_[y, t["y"]],
                a["coordinates"][ids],
                a["component"][ids],
                len(y),
                a["original_mass"][sel] if full else m,
            )
    frames = []
    for role in ("fit", "tuning"):
        with np.load(ROOT / FOLDERS[name] / (role + ".npz"), allow_pickle=False) as a:
            frames.append([a["x"][:, :100].copy(), a["y"], a["coordinate"], a["group"]])
    x, y, coord, groups = [np.concatenate(items) for items in zip(*frames, strict=True)]
    n = len(frames[0][1])
    _, inv, counts = np.unique(x[:n], axis=0, return_inverse=True, return_counts=True)
    mass = (np.minimum(8, np.sqrt(counts)) / counts)[inv.reshape(-1)]
    return x, y, coord, groups, n, mass


def rows(name, coords):
    ordered = np.sort(coords)
    if name == "SRBH":
        csv.field_size_limit(1048576)
        allowed = set(ordered.tolist())
        with RAW_SRBH.open(encoding="utf-8-sig", newline="") as f:
            for i, row in enumerate(csv.DictReader(f, strict=True)):
                if i in allowed:
                    yield i, row["request_http_method"], row["request_http_request"], None, None
        return
    src, fields = (
        (RAW_WAF, ["method", "url", "body", "label"])
        if name == "WAF"
        else (RAW_NOTES, ["text", "label"])
    )
    offset = 0
    for batch in pq.ParquetFile(src).iter_batches(
        columns=fields, batch_size=4096, use_threads=False
    ):
        end = offset + len(batch)
        lo, hi = np.searchsorted(ordered, [offset, end])
        ids = ordered[lo:hi]
        selected = batch.take(ids - offset).to_pylist() if len(ids) else []
        for i, row in zip(ids, selected, strict=True):
            if name == "WAF":
                yield int(i), row["method"], row["url"], row["body"], LABEL[row["label"]]
            else:
                method, target, _, body, _ = parse_request(row["text"])
                yield int(i), method, target, body, {"benign": 0, "malicious": 1}[row["label"]]
        offset = end


def materialize(out, name, full):
    marker = out / (name + ".json")
    if marker.exists():
        shard = load_json(marker)
        need(shard["plan_sha256"] == file_sha256(out.parent / "plan.json"), "STALE_ETL")
        for f, sha in shard["files"].items():
            need(file_sha256(out / f) == sha, "CORRUPT_ETL")
        return
    x, y, coords, groups, n, mass = roster(name, full)
    need(
        len(coords) == len(set(coords.tolist())) and not set(groups[:n]) & set(groups[n:]),
        "ROLE_OR_ID_OVERLAP",
    )
    lookup = {int(c): j for j, c in enumerate(coords)}
    positions = []
    offsets = array("i", [0])
    columns = array("i")
    for c, method, raw, body, label in rows(name, coords):
        j = lookup[c]
        target = origin_view(raw)
        need(
            target is not None and (label is None or label == y[j]),
            "ROSTER_LABEL_OR_TARGET_MISMATCH",
        )
        # Ordinal comes from the pinned original and role manifest. Independently
        # reproduce the original URI76 on every selected coordinate.
        need(np.array_equal(from_request(target[0], method), x[j, :76]), "ROW_VIEW_MISMATCH")
        columns.extend(project(target[0], body))
        offsets.append(len(columns))
        positions.append(j)
    order = np.argsort(positions)
    need(np.array_equal(np.array(positions)[order], np.arange(len(x))), "MISSING_COORDINATE")
    z = sparse.csr_matrix(
        (np.ones(len(columns), np.uint8), np.asarray(columns), np.asarray(offsets)),
        shape=(len(x), WIDTH),
    )[order]
    numeric = out / (name + ".npz")
    symbolic = out / (name + "-symbols.npz")
    np.savez_compressed(numeric, x=x, y=y, group=groups, nfit=n, mass=mass)
    sparse.save_npz(symbolic, z)
    atomic_json(
        marker,
        {
            "source": name,
            "fit": n,
            "tuning": len(x) - n,
            "request_bindings_checked": len(x),
            "plan_sha256": file_sha256(out.parent / "plan.json"),
            "files": {p.name: file_sha256(p) for p in (numeric, symbolic)},
        },
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("mode", choices=("plan", "pilot", "full"))
    a.add_argument("output", type=Path)
    args = a.parse_args()
    os.umask(0o077)
    if args.mode == "plan":
        lock(args.output)
    else:
        verify(args.output, "etl")
        if args.mode == "full":
            pilot = load_json(args.output / "pilot-result.json")
            need(
                (
                    pilot["advance"]
                    or (
                        (args.output / "neighbors-pilot.json").exists()
                        and load_json(args.output / "neighbors-pilot.json")["advance"]
                    )
                )
                and pilot["plan_sha256"] == file_sha256(args.output / "plan.json"),
                "FULL_FIT_GATE",
            )
        folder = args.output / args.mode
        folder.mkdir(exist_ok=True)
        for name in NAMES:
            since = time.monotonic()
            materialize(folder, name, args.mode == "full")
            print(name, round(time.monotonic() - since, 2), "seconds", flush=True)
