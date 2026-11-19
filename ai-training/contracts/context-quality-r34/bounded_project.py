"""Project oversized chronological account buckets with the same six-event boundary state."""

import os
import sys
from pathlib import Path

import numpy as np
from login_data import RAW, features, mix, peer_features, peer_snapshot, project

from idps_ai.common import atomic_json, file_sha256, load_json


def project_blocks(mapped, *, size=65536):
    last_time = None
    tail = np.empty(0, dtype=RAW)
    start = 0
    while start < len(mapped):
        end = min(start + size, len(mapped))
        # Close concurrent anchors together. A future anchor may depend on whether
        # the fifth prior event shared its timestamp with the sixth.
        while end < len(mapped) and mapped["ts"][end] == mapped["ts"][end - 1]:
            end += 1
            if end - start > 2 * size:
                raise ValueError("oversized timestamp tie")
        batch = np.asarray(mapped[start:end])
        if np.any(batch["ts"][1:] < batch["ts"][:-1]) or (
            last_time is not None and batch["ts"][0] <= last_time
        ):
            raise ValueError("publisher timeline needs external sort")
        last_time = batch["ts"][-1]
        ids = np.unique(batch["user"])
        active = np.isin(tail["user"], ids)
        prefix = tail[active]
        merged = np.concatenate((prefix, batch))
        order = np.lexsort((merged["index"], merged["ts"], merged["user"]))
        merged = merged[order]
        fresh = order >= len(prefix)
        history, valid = features(merged)
        yield merged[fresh], history[fresh], valid[fresh]
        user = merged["user"]
        keep = np.ones(len(user), dtype=bool)
        keep[:-6] = user[:-6] != user[6:]
        tail = np.concatenate((tail[~active], merged[keep]))
        start = end


def assemble(run):
    import login_data

    raw = load_json(run / "raw-index.json")
    root = run / "login-inputs"
    root.mkdir(mode=0o700, exist_ok=True)
    boundary = raw["first_ms"] + (raw["last_ms"] - raw["first_ms"]) // 4
    peer = peer_snapshot(run, raw, boundary)
    manifest_sha = file_sha256(run / "raw-index.json")
    for name, pin in sorted(raw["bucket_shas"].items()):
        src = run / "account-buckets" / name
        j = int(src.stem)
        if src.stat().st_size <= 64 * 1024**2:
            continue
        dest = root / f"{j:02d}.npz"
        meta = dest.with_suffix(".json")
        if meta.exists():
            saved = load_json(meta)
            if (
                saved.get("block_projector_sha") != file_sha256(__file__)
                or file_sha256(dest) != saved["sha256"]
            ):
                raise ValueError("large bucket checkpoint changed")
            continue
        if file_sha256(src) != pin:
            raise ValueError("source shard changed")
        parts = root / f"parts-{j:02d}"
        parts.mkdir(exist_ok=True)
        mapped = np.memmap(src, dtype=RAW, mode="r")
        entries, users = [], set()
        nrows = nrole = nsel = 0
        for n, (batch, h, good) in enumerate(project_blocks(mapped)):
            if not np.all(batch["user"] % 100 == j):
                raise ValueError("role mismatch")
            users.update(np.unique(batch["user"]).tolist())
            in_role = batch["ts"] < raw["boundary_ms"]
            if j >= 80:
                in_role = ~in_role
            keep = in_role.copy()
            if j < 65:
                keep &= (mix(batch["index"]) % 32 == 0) | (batch["y"] == 1)
            nrows += len(batch)
            nrole += int(in_role.sum())
            nsel += int(keep.sum())
            if not keep.any():
                continue
            x = np.column_stack((h[keep], peer_features(batch[keep], peer, boundary)))
            f = parts / f"{n:05d}.npz"
            temp = f.with_suffix(".partial")
            with temp.open("wb") as stream:
                np.savez_compressed(
                    stream, x=x, u=batch["user"][keep], valid=good[keep], y=batch["y"][keep]
                )
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(f)
            entries.append(
                {
                    "file": str(f.relative_to(root)),
                    "sha256": file_sha256(f),
                    "rows": int(keep.sum()),
                }
            )
        if nrows != len(mapped) or nsel != sum(e["rows"] for e in entries):
            raise ValueError("large shard row conservation")
        np.savez(
            dest,
            part_names=np.asarray([e["file"] for e in entries]),
            part_shas=np.asarray([e["sha256"] for e in entries]),
        )
        atomic_json(
            meta,
            {
                "bucket": j,
                "binding": [manifest_sha, file_sha256(login_data.__file__), j],
                "block_projector_sha": file_sha256(__file__),
                "rows": nrows,
                "in_role": nrole,
                "sampled": nsel,
                "actors": len(users),
                "parts": entries,
                "sha256": file_sha256(dest),
            },
        )
    project(run)


if __name__ == "__main__":
    assemble(Path(sys.argv[1]))
