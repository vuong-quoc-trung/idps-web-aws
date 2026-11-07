#!/usr/bin/env python3
"""Paired offline replay of one already exposed live snapshot, never quality evaluation."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from glu207_snapshot import SnapshotBridge
from idps_ai.data.dataset import collect, iter_rows
from idps_ai.data.privacy import pseudonym
from idps_ai.data.readers import Input
from idps_ai.features.pipeline import FeatureExtractor, transform
from idps_ai.mvp_inference import ResearchMVP
from three_source_core import replay_prefix


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--journal", type=Path, required=True)
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reverse", action="store_true")
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    key = a.key.read_bytes()
    model = ResearchMVP("glu207", cpus=1)
    spec = model.glu_spec
    records = [json.loads(l) for l in a.journal.read_text().splitlines()]
    student = (a.snapshot / "student.jsonl").read_bytes()
    nginx = (a.snapshot / "nginx.jsonl").read_bytes()
    lines = (a.snapshot / "eve.jsonl").read_bytes().splitlines()
    events = [(l, json.loads(l)) for l in lines]
    results = {}
    vectors = {}
    stages = []

    def timed(stage, fn):
        w, c = time.perf_counter(), time.process_time()
        r = fn()
        stages.append(
            {
                "stage": stage,
                "wall_seconds": time.perf_counter() - w,
                "cpu_seconds": time.process_time() - c,
            }
        )
        return r

    def score(rows, rid, t):
        ext = FeatureExtractor(**spec["state_limits"])
        row, _ = timed(
            mode + ":history_prefix",
            lambda: replay_prefix(ext, rows, pseudonym(key, "request", rid), t),
        )
        raw = timed(mode + ":feature_extract", lambda: ext.observe(row))
        v = timed(mode + ":feature_transform", lambda: transform(spec, raw))
        out = timed(
            mode + ":onnx_inference",
            lambda: model.glu_session.run(None, {"input": v[None]})[0],
        )
        return v, float(out[0])

    order = ["cached", "reference"] if a.reverse else ["reference", "cached"]
    for mode in order:
        w, c = time.perf_counter(), time.process_time()
        items = []
        bridge = (
            timed(
                mode + ":prepare",
                lambda: SnapshotBridge(a.output / "batch", student, nginx, lines, key),
            )
            if mode == "cached"
            else None
        )
        for i, record in enumerate(records):
            rid = record["request_id"]
            if bridge:
                rk, t, rows = timed(
                    mode + ":collect",
                    lambda bridge=bridge, rid=rid: bridge.for_request(rid),
                )
            else:
                d = a.output / f"reference-{i:03d}"
                d.mkdir(mode=0o700)
                (d / "student.jsonl").write_bytes(student)
                (d / "nginx.jsonl").write_bytes(nginx)
                (d / "http.jsonl").write_bytes(
                    b"\n".join(l for l, e in events if e.get("event_type") != "flow")
                    + b"\n"
                )
                inputs = [
                    Input("student", d / "student.jsonl"),
                    Input("nginx", d / "nginx.jsonl"),
                ]
                timed(
                    mode + ":http_collect",
                    lambda inputs=inputs, d=d: collect(
                        [*inputs, Input("suricata", d / "http.jsonl")],
                        d / "http",
                        key,
                        input_profile="safe_query_numeric_v2",
                    ),
                )
                rk = pseudonym(key, "request", rid)
                t = next(
                    r["timestamp"]
                    for r in iter_rows(d / "http/requests.parquet")
                    if r["request_key"] == rk
                )
                (d / "eve.jsonl").write_bytes(
                    b"\n".join(
                        l
                        for l, e in events
                        if e.get("event_type") != "flow"
                        or isinstance(e.get("received_at"), (int, float))
                        and e["received_at"] <= t
                    )
                    + b"\n"
                )
                timed(
                    mode + ":fused_collect",
                    lambda inputs=inputs, d=d: collect(
                        [*inputs, Input("suricata", d / "eve.jsonl")],
                        d / "fused",
                        key,
                        input_profile="safe_query_numeric_v2",
                    ),
                )
                rows = list(iter_rows(d / "fused/requests.parquet"))
            v, out = timed(
                mode + ":prefix_transform_onnx",
                lambda rows=rows, rid=rid, t=t: score(rows, rid, t),
            )
            digest = hashlib.sha256(v.tobytes()).hexdigest()
            if mode == order[0]:
                vectors[rid] = (v, out)
            else:
                assert np.array_equal(v, vectors[rid][0]) and out == vectors[rid][1]
            items.append({"request_id": rid, "feature_sha256": digest, "score": out})
        results[mode] = {
            "wall_seconds": time.perf_counter() - w,
            "cpu_seconds": time.process_time() - c,
            "requests": len(items),
            "items": items,
            "throughput_requests_per_second": len(items) / (time.perf_counter() - w),
        }
        if bridge:
            results[mode]["frozen_collect_calls"] = len(bridge.metrics)
    report = {
        "status": "PASS",
        "scope": f"Paired offline fixed snapshot replay, same process/cgroup/CPU quota; order {order}, warm-cache effects not isolated. Not live event-to-dashboard latency; not quality evaluation.",
        "exact_feature_and_score_parity": len(vectors),
        "results": results,
        "stages": stages,
        "speedup_wall": results["reference"]["wall_seconds"]
        / results["cached"]["wall_seconds"],
    }
    (a.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ["stages", "results"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
