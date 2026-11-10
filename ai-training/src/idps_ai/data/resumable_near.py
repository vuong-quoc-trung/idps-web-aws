"""Exact weighted content-pair audit with atomic cursor AND accumulator commits.

Compress only bitwise-equivalent numerical rows, never approximate neighbors.
Worst case stays quadratic in unique vectors; RAM/output blocks are bounded.
"""

import json
import os
import time
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, fsync_dir

THRESHOLD = 0.995 - 1e-7
ALGORITHM = "weighted-exact-content-pairs-v1"


def save_array(path, array):
    temp = path.with_suffix(".writing.npy")
    with temp.open("wb") as f:
        np.save(f, array, allow_pickle=False)
        f.flush()
        os.fsync(f.fileno())
    if path.exists():
        if file_sha256(temp) != file_sha256(path):
            raise PipelineError("Immutable near-audit array mismatch")
        temp.unlink()
    else:
        temp.replace(path)
        fsync_dir(path.parent)


def pack_vectors(directory, content, source_binding):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = directory / "vectors-manifest.json"
    if marker.exists():
        return load_vectors(directory, source_binding)[2]
    content = np.asarray(content, dtype=np.float32)
    if content.ndim != 2 or not np.isfinite(content).all():
        raise PipelineError("Near input must be finite matrix")
    vectors, counts = np.unique(content, axis=0, return_counts=True)
    counts = counts.astype(np.int64)
    save_array(directory / "vectors.npy", vectors)
    save_array(directory / "counts.npy", counts)
    state = {
        "algorithm": ALGORITHM,
        "implementation_sha256": file_sha256(__file__),
        "source_binding": source_binding,
        "rows": len(content),
        "dimension": content.shape[1],
        "unique_vectors": len(vectors),
        "vectors_sha256": file_sha256(directory / "vectors.npy"),
        "counts_sha256": file_sha256(directory / "counts.npy"),
        "threshold": THRESHOLD,
    }
    state["fingerprint"] = digest(state)
    atomic_json(marker, state)
    return state


def load_vectors(directory, source_binding):
    directory = Path(directory)
    try:
        manifest = json.loads((directory / "vectors-manifest.json").read_text())
        check = dict(manifest)
        fp = check.pop("fingerprint")
        if (
            digest(check) != fp
            or manifest["source_binding"] != source_binding
            or manifest["algorithm"] != ALGORITHM
            or manifest["implementation_sha256"] != file_sha256(__file__)
            or manifest["threshold"] != THRESHOLD
        ):
            raise PipelineError("Near cache fingerprint/policy mismatch")
        if (
            file_sha256(directory / "vectors.npy") != manifest["vectors_sha256"]
            or file_sha256(directory / "counts.npy") != manifest["counts_sha256"]
        ):
            raise PipelineError("Near cache integrity failure")
        x = np.load(directory / "vectors.npy", mmap_mode="r", allow_pickle=False)
        counts = np.load(directory / "counts.npy", allow_pickle=False)
        if (
            x.shape != (manifest["unique_vectors"], manifest["dimension"])
            or x.dtype != np.float32
            or counts.shape != (len(x),)
            or counts.dtype != np.int64
            or np.any(counts <= 0)
            or sum(map(int, counts)) != manifest["rows"]
            or not np.isfinite(x).all()
        ):
            raise PipelineError("Invalid near cache schema")
        return x, counts, manifest
    except PipelineError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PipelineError("Invalid near cache; preserve evidence, do not reset") from exc


def within_identical(vectors, counts):
    value = 0
    for i in range(0, len(vectors), 512):
        x = np.asarray(vectors[i : i + 512], np.float64)
        norms = np.einsum("ij,ij->i", x, x)
        if np.any(norms > 1.00001) or x.shape[1] > 512:
            raise PipelineError("Near cache violates unit-L2 content contract")
        if np.any(np.abs(norms - THRESHOLD) <= 1e-12):
            raise PipelineError("Near threshold numerical ambiguity; preserve checkpoint")
        c = counts[i : i + 512]
        value += int(np.sum((norms >= THRESHOLD) * (c * (c - 1) // 2), dtype=np.int64))
    return value


def cross_chunk(vectors, counts, start, end, reference_block=2048):
    q = np.asarray(vectors[start:end], np.float64)
    left = counts[start:end, None]
    total = 0
    # Only upper-triangle unique pairs; multiplicities restore original-row pairs.
    for other in range(start, len(vectors), reference_block):
        stop = min(other + reference_block, len(vectors))
        ref = np.asarray(vectors[other:stop], np.float64)
        scores = q @ ref.T
        if np.any(np.abs(scores - THRESHOLD) <= 1e-12):
            raise PipelineError("Near threshold numerical ambiguity; preserve checkpoint")
        mask = (scores >= THRESHOLD) & (
            np.arange(start, end)[:, None] < np.arange(other, stop)[None, :]
        )
        total += int(np.sum(mask * left * counts[None, other:stop], dtype=np.int64))
    return total


def checkpoint_read(path, binding, unique, rows, block):
    try:
        envelope = json.loads(Path(path).read_text())
        p = envelope["payload"]
        if (
            digest(p) != envelope["sha256"]
            or p["binding"] != binding
            or p["algorithm"] != ALGORITHM
        ):
            raise PipelineError("Near checkpoint checksum/binding mismatch")
        cursor = p["next_unique_anchor"]
        pairs = p["pairs"]
        if (
            type(cursor) is not int
            or not 0 <= cursor <= unique
            or (cursor != unique and cursor % block)
            or type(pairs) is not int
            or not 0 <= pairs <= rows * (rows - 1) // 2
        ):
            raise PipelineError("Invalid near checkpoint accumulator/cursor")
        return p
    except PipelineError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PipelineError("Invalid near checkpoint; do not silently start over") from exc


def audit(directory, source_binding, *, block=128, stop_after_chunks=None):
    directory = Path(directory)
    if not 1 <= block <= 256:
        raise PipelineError("Near block budget exceeded")
    vectors, counts, manifest = load_vectors(directory, source_binding)
    binding = digest(
        {
            "vectors": manifest["fingerprint"],
            "block": block,
            "reference_block": 2048,
            "algorithm": ALGORITHM,
        }
    )
    checkpoint = directory / "checkpoint.json"
    if checkpoint.exists():
        state = checkpoint_read(checkpoint, binding, len(vectors), manifest["rows"], block)
    else:
        state = {
            "binding": binding,
            "algorithm": ALGORITHM,
            "next_unique_anchor": 0,
            "pairs": within_identical(vectors, counts),
        }
        atomic_json(checkpoint, {"payload": state, "sha256": digest(state)})
    # Reconcile a progress projection that lagged an atomic checkpoint commit.
    atomic_json(
        directory / "progress.json",
        {
            "state": "COMPLETED" if state["next_unique_anchor"] == len(vectors) else "RUNNING",
            "unique_anchor_rows": state["next_unique_anchor"],
            "unique_vectors": len(vectors),
            "covered_original_anchor_rows": int(np.sum(counts[: state["next_unique_anchor"]])),
            "original_rows": manifest["rows"],
            "pairs_committed": state["pairs"],
            "checkpoint_sha256": file_sha256(checkpoint),
            "checkpoint_binding": binding,
            "chunks_this_process": 0,
        },
    )
    began = time.monotonic()
    initial = state["next_unique_anchor"]
    chunks = 0
    for start in range(initial, len(vectors), block):
        end = min(start + block, len(vectors))
        delta = cross_chunk(vectors, counts, start, end)
        state = {**state, "next_unique_anchor": end, "pairs": state["pairs"] + delta}
        # Exactly-once contribution: cursor + all accumulator fields share one fsynced write.
        atomic_json(checkpoint, {"payload": state, "sha256": digest(state)})
        chunks += 1
        atomic_json(
            directory / "progress.json",
            {
                "state": "COMPLETED" if end == len(vectors) else "RUNNING",
                "unique_anchor_rows": end,
                "unique_vectors": len(vectors),
                "covered_original_anchor_rows": int(np.sum(counts[:end])),
                "original_rows": manifest["rows"],
                "checkpoint_sha256": file_sha256(checkpoint),
                "checkpoint_binding": binding,
                "pairs_committed": state["pairs"],
                "chunks_this_process": chunks,
                "unique_anchors_per_second_this_process": (end - initial)
                / max(0.001, time.monotonic() - began),
            },
        )
        if stop_after_chunks is not None and chunks >= stop_after_chunks:
            break
    complete = state["next_unique_anchor"] == len(vectors)
    result = {
        "complete": complete,
        "pairs": state["pairs"],
        "original_rows": manifest["rows"],
        "unique_vectors": len(vectors),
        "vector_fingerprint": manifest["fingerprint"],
        "algorithm": ALGORITHM,
        "next_unique_anchor": state["next_unique_anchor"],
        "checkpoint_binding": binding,
    }
    if complete:
        atomic_json(directory / "result.json", result)
    return result


def original_pairs(content):
    """Original64x2048 FP64 metric, bounded reference for equivalence/benchmark."""
    total = 0
    for start in range(0, len(content), 64):
        ids = np.arange(start, min(start + 64, len(content)))
        q = np.asarray(content[ids], np.float64)
        for other in range(start, len(content), 2048):
            js = np.arange(other, min(other + 2048, len(content)))
            scores = q @ np.asarray(content[js], np.float64).T
            total += int(np.sum((scores >= THRESHOLD) & (ids[:, None] < js[None, :])))
    return total
