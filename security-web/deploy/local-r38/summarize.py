"""Join the bounded HTTPS acceptance evidence by trusted ID and export a redacted ledger."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re


def percentiles(values):
    # Nearest rank. Preserve the observed tail in this small sample.
    ordered = sorted(values)
    return {
        f"p{p}": round(ordered[math.ceil(len(ordered) * p / 100) - 1], 6)
        for p in (50, 95, 99)
    }


def keyed(rows):
    result = {r["request_id"]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate physical request")
    return result


def summarize(run):
    def read(path):
        return json.loads((run / path).read_text())

    live = read("live/live.json")
    requests = live["requests"]
    projections = keyed(
        [
            json.loads(line)
            for line in (run / "live/observations.jsonl").read_text().splitlines()
        ]
    )
    parity = keyed(read("parity.json")["requests"])
    hybrid = keyed(read("hybrid.json")["decisions"])
    if not set(requests) == set(projections) == set(parity) == set(hybrid):
        raise ValueError("Incomplete request binding")
    rows = []
    for rid, http in requests.items():
        proj = projections[rid]
        decision = hybrid[rid]
        check = parity[rid]
        receipts = proj["source_receipts_ns"]
        dispatch, cutoff, guard = (
            proj[k] for k in ("dispatch_ns", "cutoff_ns", "guard_ns")
        )

        def timely(tag):
            t = receipts.get(tag)
            return t is not None and dispatch <= t <= cutoff - guard

        mask = (
            "".join(
                k for k, t in (("N", "N"), ("S", "S_verified"), ("A", "A")) if timely(t)
            )
            or "NONE"
        )
        if not (
            re.fullmatch("[0-9a-f]{32}", rid)
            and cutoff - dispatch == 1_000_000_000
            and guard == 1_000_000
            and mask == http["mask_at_cutoff"] == proj["source_mask_at_cutoff"]
            and decision["model_sha256"] == proj["model_sha256"] == http["model_sha256"]
            and decision["model"] == check["model"]
            and decision["score"] == proj["score"]
            and check["feature_parity"]
            and http["audit_id"] == proj["audit_event_id"]
            and http["tx"] == proj["tx"]
        ):
            raise ValueError("Acceptance binding failed")
        rows.append(
            dict(
                request_id=rid,
                method=http["method"],
                http_status=http["status"],
                http_ms=http["http_ms"],
                oracle=http["oracle"],
                audit_event_id=proj["audit_event_id"],
                sensor_tx=proj["tx"],
                sensor_absence=http.get("sensor_absence"),
                dispatch_ns=dispatch,
                guard_ns=guard,
                cutoff_ns=cutoff,
                source_receipts_ns=receipts,
                raw_eve_in_window=timely("E"),
                mask_at_cutoff=mask,
                structural_mask=proj["structural_mask"],
                model=decision["model"],
                sha256=decision["model_sha256"],
                score=proj["score"],
                scorer_status=proj["status"],
                projection_available_ns=proj["available_ns"],
                rust_timing_ns=proj["scorer_timing"],
                vector_sha256=proj["vector_sha256"],
                hybrid_policy=decision["policy"],
                observation=decision["observation"],
                python_rust_error=check["python_rust_error"],
            )
        )
    counts = lambda field: dict(Counter(r[field] for r in rows))
    ds = lambda r: (r["projection_available_ns"] - r["dispatch_ns"]) / 1e6
    delta = lambda r, key: (r["source_receipts_ns"][key] - r["dispatch_ns"]) / 1e6
    evidence = dict(
        physical=len(rows),
        unique_vectors=len({r["vector_sha256"] for r in rows}),
        methods=counts("method"),
        http=counts("http_status"),
        model_versions=counts("model"),
        policy=counts("hybrid_policy"),
        observation=counts("observation"),
        structural=counts("structural_mask"),
        at_cutoff=counts("mask_at_cutoff"),
        oracles=counts("oracle"),
        scorer=counts("scorer_status"),
        distinct_audits=len({r["audit_event_id"] for r in rows}),
        distinct_sensor_transactions=len(
            {tuple(sorted(r["sensor_tx"].items())) for r in rows if r["sensor_tx"]}
        ),
        raw_eve_at_cutoff=sum(r["raw_eve_in_window"] for r in rows),
        projection_at_cutoff=sum(
            r["dispatch_ns"]
            <= r["projection_available_ns"]
            <= r["cutoff_ns"] - r["guard_ns"]
            for r in rows
        ),
        quantile_method="nearest rank",
        https_ms=percentiles([r["http_ms"] for r in rows]),
        projection_ms=percentiles([ds(r) for r in rows]),
        rust_inference_ms=percentiles(
            [r["rust_timing_ns"]["inference_ns"] / 1e6 for r in rows]
        ),
        preprocessing_ms=percentiles(
            [r["rust_timing_ns"]["preprocessing_ns"] / 1e6 for r in rows]
        ),
        receipt_ms={
            key: percentiles(
                [
                    delta(r, key)
                    for r in rows
                    if r["source_receipts_ns"].get(key) is not None
                ]
            )
            for key in ["N", "A", "E", "S_verified"]
            if any(r["source_receipts_ns"].get(key) is not None for r in rows)
        },
        extended=live["extended"],
        python_rust_max_error=max(r["python_rust_error"] for r in rows),
        native_train=live["native_train"],
        post_proxy_client_verified=live["protected_ip_verified"],
        input_sha256={
            p: hashlib.sha256((run / p).read_bytes()).hexdigest()
            for p in (
                "live/live.json",
                "live/observations.jsonl",
                "parity.json",
                "hybrid.json",
            )
        },
    )
    return rows, evidence


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    rows, metrics = summarize(args.run)
    for name, value in (("requests", rows), ("metrics", metrics)):
        with (args.out / (name + ".json")).open("x") as f:
            f.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
