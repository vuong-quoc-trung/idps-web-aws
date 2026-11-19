"""Stream the synthesized SSO release. Only pseudonym-relative equality enters ML."""

import hashlib
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as csv
from acquire import MD5, SIZE

from idps_ai.common import atomic_json, file_sha256, load_json

HERE = Path(__file__).resolve().parent
FIELDS = ("Country", "ASN", "Device Type", "Browser Name and Version", "OS Name and Version")
NAMES = (
    "prior_count",
    "gap_log_days",
    "prior_span_log_days",
    *(
        name + "_" + item
        for name in ("country", "asn", "device", "browser", "os")
        for item in ("known", "repeat_fraction", "same_latest")
    ),
    "network_device_both_new",
    "prior_distinct_network_fraction",
    "prior_distinct_device_fraction",
)
HISTORY_WIDTH = len(NAMES)
PEERS = ((0,), (1,), (2,), (3,), (4,), (0, 1), (2, 3), (3, 4), (0, 2))
NAMES = (
    *NAMES,
    "peer_prefix_available",
    *(f"peer_{i}_{op}" for i in range(len(PEERS)) for op in ("observed", "surprisal")),
)
RAW = np.dtype(
    [("user", "<u8"), ("ts", "<i8"), ("index", "<u8"), ("ctx", "<u8", (5,)), ("y", "u1")]
)
DAY = 86400000
MASK = (1 << 64) - 1


def mix(x):
    z = np.asarray(x, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> 30)) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> 27)) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> 31)


def family(value):
    # Discard browser/OS versions without persisting names.
    return re.split(r"[/\d]", value, 1)[0].strip().lower()


def encoded(column, coarse=False):
    d = column.dictionary_encode()
    values = [
        0
        if not v or v.strip().lower() in ("-", "unknown", "n/a", "nan", "?")
        else int.from_bytes(
            hashlib.blake2b(
                (family(v) if coarse else v).encode(), digest_size=8, person=b"r34context"
            ).digest(),
            "little",
        )
        for v in d.dictionary.to_pylist()
    ]
    ids = d.indices.fill_null(len(values)).to_numpy()
    return np.array(values + [0], dtype=np.uint64)[ids]


def extract(run):
    raw = run / "rba.zip"
    source = load_json(run / "source.json")
    with raw.open("rb") as f:
        official = hashlib.file_digest(f, "md5").hexdigest()
    if (
        raw.stat().st_size != SIZE
        or official != MD5
        or source["publisher_md5"] != MD5
        or file_sha256(raw) != source["sha256"]
    ):
        raise ValueError("unexpected source")
    extract_rows(run, raw, source["sha256"])


def extract_rows(run, raw, archive_sha):
    directory = run / "account-buckets"
    directory.mkdir(mode=0o700)
    columns = {
        "index": pa.uint64(),
        "User ID": pa.int64(),
        "Login Timestamp": pa.timestamp("ms"),
        "Is Account Takeover": pa.bool_(),
        **{f: pa.string() for f in FIELDS},
    }
    start = time.monotonic()
    total = 0
    first = 2**63 - 1
    last = 0
    with zipfile.ZipFile(raw) as z, z.open("rba-dataset.csv") as stream:
        reader = csv.open_csv(
            stream,
            read_options=csv.ReadOptions(use_threads=False, block_size=2**22),
            convert_options=csv.ConvertOptions(
                column_types=columns,
                include_columns=list(columns),
                true_values=["True", "true"],
                false_values=["False", "false"],
            ),
        )
        for batch in reader:

            def col(name):
                return batch.column(batch.schema.get_field_index(name))

            n = batch.num_rows
            for key in ("User ID", "Login Timestamp", "index", "Is Account Takeover"):
                if col(key).null_count:
                    raise ValueError("missing identity, time or label")
            a = np.empty(n, dtype=RAW)
            a["index"] = col("index").to_numpy()
            if not np.array_equal(a["index"], np.arange(total, total + n)):
                raise ValueError("unreconciled publisher ordinal")
            a["user"] = mix(col("User ID").to_numpy().view(np.uint64))
            a["ts"] = col("Login Timestamp").to_numpy().astype("datetime64[ms]").astype(np.int64)
            a["y"] = col("Is Account Takeover").to_numpy(zero_copy_only=False)
            for j, f in enumerate(FIELDS):
                a["ctx"][:, j] = encoded(col(f), coarse=j >= 3)
            first = min(first, int(a["ts"].min()))
            last = max(last, int(a["ts"].max()))
            role = a["user"] % 100
            order = np.argsort(role, kind="stable")
            ends = np.cumsum(np.bincount(role.astype(int), minlength=100))
            for j, (lo, hi) in enumerate(zip(np.r_[0, ends[:-1]], ends, strict=True)):
                if hi > lo:
                    with (directory / f"{j:02d}.bin").open("ab") as out:
                        a[order[lo:hi]].tofile(out)
            total += n
            if total // 500000 != (total - n) // 500000:
                atomic_json(
                    run / "etl-progress.json",
                    {"written": total, "elapsed_s": time.monotonic() - start},
                )
    public = {
        "rows": total,
        "first_ms": first,
        "last_ms": last,
        "boundary_ms": first + 3 * (last - first) // 4,
        "source_sha": archive_sha,
        "bucket_shas": {p.name: file_sha256(p) for p in sorted(directory.glob("*.bin"))},
    }
    if sum(p.stat().st_size for p in directory.glob("*.bin")) != total * RAW.itemsize:
        raise ValueError("row conservation failed")
    atomic_json(run / "raw-index.json", public)


def features(a):
    """Sorted by account and timestamp. Ties at anchor share the prior closed prefix."""
    n = len(a)
    ix = np.arange(n)
    uid, ts, ctx = a["user"], a["ts"], a["ctx"]
    first = np.r_[True, (uid[1:] != uid[:-1]) | (ts[1:] != ts[:-1])]
    start = np.maximum.accumulate(np.where(first, ix, 0))
    tied = (~first) | np.r_[~first[1:], False]
    prev = start[:, None] - np.arange(1, 6)
    safe = np.maximum(0, prev)
    gaps = ts[:, None] - ts[safe]
    valid = (prev >= 0) & (uid[safe] == uid[:, None]) & (gaps > 0) & (gaps <= 30 * DAY)
    count = valid.sum(axis=1)
    ambiguous = np.any(tied[safe] & valid, axis=1)
    supported = (count > 0) & ~ambiguous
    denom = np.maximum(1, count)
    x = np.zeros((n, HISTORY_WIDTH), dtype="<f4")
    x[:, 0] = count / 5
    x[:, 1] = np.log1p(np.where(count > 0, gaps[:, 0], 0) / DAY)
    x[:, 2] = np.log1p(np.max(np.where(valid, gaps, 0), axis=1) / DAY)
    for k in range(5):
        current = ctx[:, k]
        previous = ctx[safe, k]
        obs = valid & (previous != 0) & (current[:, None] != 0)
        same = (previous == current[:, None]) & obs
        j = 3 + 3 * k
        x[:, j] = obs.any(axis=1)
        x[:, j + 1] = same.sum(axis=1) / np.maximum(1, obs.sum(axis=1))
        x[:, j + 2] = same[:, 0]
        if k in (1, 2):
            distinct = np.zeros(n)
            for h in range(5):
                novel = np.all((previous[:, :h] != previous[:, h, None]) | ~valid[:, :h], axis=1)
                distinct += valid[:, h] & (previous[:, h] != 0) & novel
            x[:, 19 if k == 1 else 20] = distinct / denom
    x[:, 18] = (x[:, 6] > 0) & (x[:, 9] > 0) & (x[:, 7] == 0) & (x[:, 10] == 0)
    supported &= np.any(x[:, 3:18:3] > 0, axis=1)
    x[~supported] = 0
    return x, supported


def peer_keys(ctx, cols):
    # Each key is the exact tuple of pseudonymous categories. Never hash pairs down to one ID.
    raw = np.ascontiguousarray(ctx[:, list(cols)], dtype="<u8")
    return raw.view(np.dtype((np.void, 8 * len(cols)))).ravel(), (raw != 0).all(axis=1)


def peer_snapshot(run, manifest, boundary):
    path = run / "peer-prefix.npz"
    marker = path.with_suffix(".json")
    binding = [file_sha256(run / "raw-index.json"), file_sha256(Path(__file__)), boundary]
    if marker.exists():
        saved = load_json(marker)
        if saved["binding"] != binding or file_sha256(path) != saved["sha256"]:
            raise ValueError("peer reference changed")
    else:
        accumulators = [{} for _ in PEERS]
        count = 0
        for j in range(50):
            name = f"{j:02d}.bin"
            src = run / "account-buckets" / name
            if file_sha256(src) != manifest["bucket_shas"][name]:
                raise ValueError("peer source changed")
            a = np.fromfile(src, RAW)
            if not (a["user"] % 100 == j).all():
                raise ValueError("peer cross-role actor")
            ctx = a["ctx"][a["ts"] < boundary]
            count += len(ctx)
            for cols, acc in zip(PEERS, accumulators, strict=True):
                keys, valid = peer_keys(ctx, cols)
                vals, counts = np.unique(keys[valid], return_counts=True)
                for k, n in zip(vals, counts, strict=True):
                    key = bytes(k)
                    acc[key] = acc.get(key, 0) + int(n)
        arrays = {}
        for i, (cols, acc) in enumerate(zip(PEERS, accumulators, strict=True)):
            keys = sorted(acc)
            arrays[f"k{i}"] = np.asarray(keys, dtype=f"V{8 * len(cols)}")
            arrays[f"n{i}"] = np.asarray([acc[k] for k in keys], dtype=np.int64)
        np.savez_compressed(path, **arrays)
        atomic_json(
            marker, {"binding": binding, "fit_reference_events": count, "sha256": file_sha256(path)}
        )
    with np.load(path, allow_pickle=False) as z:
        return [(z[f"k{i}"], z[f"n{i}"]) for i in range(len(PEERS))]


def peer_features(a, table, boundary):
    x = np.zeros((len(a), 1 + 2 * len(PEERS)), dtype="<f4")
    for i, (cols, (keys, counts)) in enumerate(zip(PEERS, table, strict=True)):
        v, present = peer_keys(a["ctx"], cols)
        ok = present & (a["ts"] >= boundary)
        if not len(keys) or not ok.any():
            continue
        idx = np.searchsorted(keys, v[ok])
        clipped = np.minimum(idx, len(keys) - 1)
        seen = (idx < len(keys)) & (keys[clipped] == v[ok])
        freq = np.where(seen, counts[clipped], 0)
        # Add-one relative frequency, bounded bits of surprise; unseen differs from missing.
        x[ok, 1 + 2 * i] = 1
        x[ok, 2 + 2 * i] = np.minimum(20, np.log2((counts.sum() + len(keys) + 1) / (freq + 1))) / 20
    x[:, 0] = x[:, 1::2].any(axis=1)
    return x


def project(run):
    manifest = load_json(run / "raw-index.json")
    dest = run / "login-inputs"
    dest.mkdir(mode=0o700, exist_ok=True)
    summary = []
    schema_pin = file_sha256(Path(__file__))
    manifest_pin = file_sha256(run / "raw-index.json")
    boundary = manifest["first_ms"] + (manifest["last_ms"] - manifest["first_ms"]) // 4
    peer = peer_snapshot(run, manifest, boundary)
    for j in range(100):
        name = f"{j:02d}.bin"
        src = run / "account-buckets" / name
        out = dest / f"{j:02d}.npz"
        if file_sha256(src) != manifest["bucket_shas"][name]:
            raise ValueError("bucket changed")
        marker = out.with_suffix(".json")
        binding = [manifest_pin, schema_pin, j]
        if marker.exists():
            saved = load_json(marker)
            if saved["binding"] != binding or file_sha256(out) != saved["sha256"]:
                raise ValueError("projection checkpoint changed")
            summary.append(saved)
            continue
        a = np.fromfile(src, RAW)
        a = a[np.lexsort((a["index"], a["ts"], a["user"]))]
        if not np.all(a["user"] % 100 == j):
            raise ValueError("actor partition changed")
        x, valid = features(a)
        x = np.column_stack((x, peer_features(a, peer, boundary)))
        early = a["ts"] < manifest["boundary_ms"]
        in_role = early if j < 80 else ~early
        keep = in_role.copy()
        if j < 65:
            keep &= ((mix(a["index"]) % 32) == 0) | (a["y"] == 1)
        temp = out.with_suffix(".partial")
        with temp.open("wb") as f:
            np.savez_compressed(f, x=x[keep], valid=valid[keep], u=a["user"][keep], y=a["y"][keep])
            f.flush()
            os.fsync(f.fileno())
        temp.replace(out)
        summary.append(
            {
                "bucket": j,
                "binding": binding,
                "rows": len(a),
                "actors": len(np.unique(a["user"])),
                "in_role": int(in_role.sum()),
                "sampled": int(keep.sum()),
                "sha256": file_sha256(out),
            }
        )
        atomic_json(marker, summary[-1])
    atomic_json(
        run / "projection.json",
        {
            "schema": NAMES,
            "role_bins": summary,
            "boundary_ms": manifest["boundary_ms"],
            "manifest_sha": file_sha256(run / "raw-index.json"),
            "peer_ref_sha": file_sha256(run / "peer-prefix.npz"),
            "peer_ref_boundary_ms": boundary,
        },
    )


if __name__ == "__main__":
    phase, folder = sys.argv[1:]
    (extract if phase == "extract" else project)(Path(folder))
