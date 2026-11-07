#!/usr/bin/env python3
"""Bounded post-response snapshot consumer, under its own resource guard.

Shares the frozen collector and feature implementation, never fits/trains.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from glu207_snapshot import SnapshotBridge
from idps_ai.features.pipeline import FeatureExtractor, transform
from idps_ai.mvp_inference import ResearchMVP
from three_source_core import UncertainHistoryTime, replay_prefix

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "shadow", ROOT / "scripts/ai-shadow-worker.py"
)
shadow = importlib.util.module_from_spec(s)
s.loader.exec_module(shadow)


def full_lines(path):
    data = path.read_bytes() if path.exists() else b""
    return data[: data.rfind(b"\n") + 1]


def run(a):
    os.umask(0o077)
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    key = os.urandom(32)
    (a.output / "pseudonym-key.bin").write_bytes(key)
    model = ResearchMVP("glu207", cpus=1)

    class CaptureSession:
        def __init__(self, delegate):
            self.delegate = delegate
            self.last_input = None

        def run(self, names, feeds):
            self.last_input = feeds["input"].copy()
            return self.delegate.run(names, feeds)

    model.glu_session = CaptureSession(model.glu_session)
    journal = shadow.Journal(a.runtime / "glu207/results.jsonl")
    rejected = shadow.Journal(a.output / "rejections.jsonl")
    done = set()
    last = -float("inf")
    started_at = time.time()
    sequence = 0
    batch_sequence = 0
    while True:
        if len(done) >= a.max_requests:
            return
        # Read complete records only; never treat an incomplete append as a result.
        records = {}
        path = a.runtime / "correlation/results.jsonl"
        if path.exists():
            for name in [path.with_name(path.name + f".{i}") for i in [3, 2, 1]] + [
                path
            ]:
                for line in full_lines(name).splitlines():
                    r = json.loads(line)
                    if r.get("observed_at"):
                        records[r["request_id"]] = r
        pending = [
            r
            for rid, r in records.items()
            if rid not in done
            and r.get("status") == "MATCHED"
            and not r.get("late_event")
            and (
                not a.since_now
                or datetime.fromisoformat(r["observed_at"]).timestamp() >= started_at
            )
        ]
        pending.sort(key=lambda r: r["observed_at"])
        bridge = None
        if pending:
            batch_sequence += 1
            eve = a.sensor / "eve.json"
            lines = []
            for name in [eve.with_name(eve.name + f".{i}") for i in [3, 2, 1]] + [eve]:
                lines += full_lines(name).splitlines()
            bridge = SnapshotBridge(
                a.output / f"batch-{batch_sequence:04d}",
                full_lines(a.runtime / "student-audit/student-audit.log"),
                full_lines(a.runtime / "nginx/access.log"),
                lines,
                key,
            )
        for record in pending:
            if len(done) >= a.max_requests:
                return
            rid = record["request_id"]
            done.add(rid)
            sequence += 1
            snap = a.output / f"snapshot-{sequence:04d}"
            snap.mkdir(mode=0o700)
            try:
                target_key, event_t, rows = bridge.for_request(rid)
            except ValueError as exc:
                rejected.append({"request_id": rid, "reason": str(exc)})
                continue
            if event_t < last:
                rejected.append({"request_id": rid, "reason": "LATE_EVENT_NOT_SCORED"})
                continue
            # Replay the prefix: include all observed canonical requests in history,
            # including requests without EVE. Never observe a later response for target.
            prefix_wall, prefix_cpu = time.perf_counter(), time.process_time()
            model.extractor = FeatureExtractor(**model.glu_spec["state_limits"])
            try:
                target, prefix_count = replay_prefix(
                    model.extractor,
                    rows,
                    target_key,
                    event_t,
                )
            except UncertainHistoryTime as exc:
                rejected.append({"request_id": rid, "reason": str(exc)})
                continue
            prefix_ms = (time.perf_counter() - prefix_wall) * 1000
            prefix_cpu_ms = (time.process_time() - prefix_cpu) * 1000
            replay_wall = time.perf_counter()
            started = time.perf_counter()
            result = model.predict(
                {
                    "schema_version": "research-mvp-1",
                    "record_id": rid,
                    "fused_request": target,
                }
            )
            glu = result["models"]["glu207"]
            inference_ms = (time.perf_counter() - started) * 1000
            # Separate replay of the same frozen chronological input checks the exact
            # vector fed to ONNX; saved tensor parity is audited by a separate script.
            ext = FeatureExtractor(**model.glu_spec["state_limits"])
            replayed_target, _ = replay_prefix(ext, rows, target_key, event_t)
            raw = ext.observe(replayed_target)
            vector = transform(model.glu_spec, raw)
            assert vector.shape == (207,) and np.isfinite(vector).all()
            assert np.array_equal(vector, model.glu_session.last_input[0])
            output = dict(
                record,
                observed_at=datetime.now(UTC).isoformat(),
                glu={
                    "model_version": glu["model_version"],
                    "score": glu["score"],
                    "threshold": glu["research_threshold"],
                    "above_threshold": glu["above_research_threshold"],
                    "feature_count": 207,
                    "feature_sha256": hashlib.sha256(vector.tobytes()).hexdigest(),
                    "latency_ms": inference_ms,
                    "flow_observed": glu["feature_availability"]["prior_flow_observed"],
                    "context_incomplete": glu["feature_availability"][
                        "context_incomplete"
                    ],
                },
            )
            journal_wall = time.perf_counter()
            journal.append(output)
            (bridge.directory / "profile.json").write_text(
                json.dumps(bridge.metrics, indent=2) + "\n"
            )
            (snap / "feature-proof.json").write_text(
                json.dumps(
                    {
                        "request_id": rid,
                        "event_timestamp": event_t,
                        "snapshot_batch": bridge.directory.name,
                        "prefix_wall_ms": prefix_ms,
                        "prefix_cpu_ms": prefix_cpu_ms,
                        "validation_replay_ms": (journal_wall - replay_wall) * 1000
                        - inference_ms,
                        "journal_append_ms": (time.perf_counter() - journal_wall)
                        * 1000,
                        "event_to_result_seconds": time.time() - event_t,
                        "vector_sha256": output["glu"]["feature_sha256"],
                        "flow_values": json.loads(target["flow_json"]),
                        "missing_feature_names": [
                            n for n, v in raw.items() if n.endswith("_missing") and v
                        ],
                        "feature_count": len(vector),
                        "sources": target["sources"],
                        "input_profile": "safe_query_numeric_v2",
                        "no_future_response_replayed": True,
                        "prefix_requests_replayed": prefix_count,
                    },
                    indent=2,
                )
                + "\n"
            )
            last = event_t
            if len(done) >= a.max_requests:
                return
        time.sleep(0.5)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", type=Path, default=ROOT / ".local-dev/foundation")
    p.add_argument("--sensor", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-requests", type=int, default=16)
    p.add_argument(
        "--since-now",
        action="store_true",
        help="Score only correlation observations emitted after consumer start",
    )
    run(p.parse_args())
