"""Cross-publisher original-byte overlap audit before combined fitting."""

# isort: skip_file

import argparse
import hmac
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from r26_common import atomic_json, check, file_sha256
from r26_notes import ROLES, parse_request
from idps_ai.common import canonical_bytes
from r16_waf import BATCH, LABEL, WAF, WAF_SHA, origin_view, source


def signature(key, method, target, protocol, headers, body):
    origin = origin_view(target)
    if origin is None:
        raise ValueError("Unobserved original target")
    return hmac.digest(
        key,
        canonical_bytes(
            [
                method,
                origin[0],
                str(protocol).removeprefix("HTTP/"),
                headers.replace("\r\n", "\n").strip() if headers else "",
                body if body is not None else None,
            ]
        ),
        "sha256",
    )


def run(out):
    check(file_sha256(WAF) == WAF_SHA, "Publisher source pin")
    key = (out / "notes/identity.key").read_bytes()
    coordinates, role_lookup = set(), {}
    for role in ROLES:
        with np.load(out / "notes" / f"{role.lower()}.npz", allow_pickle=False) as z:
            for coord in z["coordinate"]:
                coordinates.add(int(coord))
                role_lookup[int(coord)] = role
    selected = (
        pq.read_table(out / "notes-train.parquet", columns=["text", "label"])
        .take(sorted(coordinates))
        .to_pylist()
    )
    notes = defaultdict(list)
    for coordinate, row in zip(sorted(coordinates), selected, strict=True):
        method, target, headers, body, protocol = parse_request(row["text"])
        key_value = signature(key, method, target, protocol, headers, body)
        notes[key_value].append(
            (coordinate, role_lookup[coordinate], int(row["label"] == "malicious"))
        )
    with np.load(out / "data-v2/waf-r26.npz", allow_pickle=False) as z:
        coord = z["coordinates"]
        nfit = int(z["nfit"])
        labels = z["y"]
    order = np.argsort(coord)
    ordered = coord[order]
    matches = Counter()
    offset = 0
    for batch in source().iter_batches(
        batch_size=BATCH,
        columns=["method", "url", "protocol", "headers", "body", "label"],
        use_threads=False,
    ):
        end = offset + batch.num_rows
        lo, hi = np.searchsorted(ordered, [offset, end])
        rows = batch.take(ordered[lo:hi] - offset).to_pylist() if hi > lo else ()
        for i, row in zip(order[lo:hi], rows, strict=True):
            check(LABEL[row["label"]] == labels[i], "Overlap coordinate-label binding")
            request = signature(
                key, row["method"], row["url"], row["protocol"], row["headers"], row["body"]
            )
            for _, role, label in notes.get(request, ()):
                status = "SAME_LABEL" if label == labels[i] else "LABEL_CONFLICT"
                matches[f"WAF_{'FIT' if i < nfit else 'TUNING'}__NOTES_{role}__{status}"] += 1
        offset = end
    atomic_json(
        out / "cross-source-overlap.json",
        {
            "status": "PASS_NO_EXACT_OVERLAP" if not matches else "BLOCKED_RECONCILIATION_REQUIRED",
            "matched_originals": dict(matches),
            "eligible_notes_originals": len(coordinates),
            "waf_originals": len(coord),
            "identity": "HMAC of observed method, origin target, protocol, serialized headers and body",
            "identity_key_fingerprint": file_sha256(out / "notes/identity.key"),
            "near_role_embargo": "Coarse URI76 plus symbolic URI template closure, recorded by intake",
            "proves_physical_request_identity": False,
            "payload_or_digests_persisted": False,
        },
    )
    check(not matches, "New original overlap requires explicit quarantine before fitting")


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
