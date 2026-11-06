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
from idps_ai.data.dataset import collect, iter_rows
from idps_ai.data.privacy import pseudonym
from idps_ai.data.readers import Input
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
    sequence = 0
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
        ]
        pending.sort(key=lambda r: r["observed_at"])
        for record in pending:
            if len(done) >= a.max_requests:
                return
            rid = record["request_id"]
            done.add(rid)
            sequence += 1
            snap = a.output / f"snapshot-{sequence:04d}"
            snap.mkdir(mode=0o700)
            for source, path in [
                ("nginx", a.runtime / "nginx/access.log"),
                ("student", a.runtime / "student-audit/student-audit.log"),
            ]:
                (snap / (source + ".jsonl")).write_bytes(full_lines(path))
            # Receipt time is independently preserved by the adapter. First collect HTTP
            # rows to find the exact post-response event timestamp, then filter flows.
            eve = a.sensor / "eve.json"
            lines = []
            for name in [eve.with_name(eve.name + f".{i}") for i in [3, 2, 1]] + [eve]:
                lines += full_lines(name).splitlines()
            http_lines = [l for l in lines if json.loads(l).get("event_type") != "flow"]
            (snap / "eve-http.jsonl").write_bytes(b"\n".join(http_lines) + b"\n")
            inputs = [
                Input("student", snap / "student.jsonl"),
                Input("nginx", snap / "nginx.jsonl"),
                Input("suricata", snap / "eve-http.jsonl"),
            ]
            collect(inputs, snap / "http", key, input_profile="safe_query_numeric_v2")
            target_key = pseudonym(key, "request", rid)
            rows = list(iter_rows(snap / "http/requests.parquet"))
            targets = [r for r in rows if r["request_key"] == target_key]
            if (
                len(targets) != 1
                or targets[0]["correlation"] != "request_id"
                or set(targets[0]["sources"]) != {"NGINX", "STUDENT_AUDIT", "SURICATA"}
            ):
                rejected.append(
                    {
                        "request_id": rid,
                        "reason": "FROZEN_COLLECTOR_DID_NOT_CONFIRM_THREE_SOURCES",
                    }
                )
                continue
            event_t = targets[0]["timestamp"]
            if event_t < last:
                rejected.append({"request_id": rid, "reason": "LATE_EVENT_NOT_SCORED"})
                continue
            filtered = []
            for line in lines:
                e = json.loads(line)
                if e.get("event_type") == "flow" and (
                    not isinstance(e.get("received_at"), (int, float))
                    or e["received_at"] > event_t
                ):
                    continue
                filtered.append(line)
            (snap / "eve.jsonl").write_bytes(b"\n".join(filtered) + b"\n")
            collect(
                [inputs[0], inputs[1], Input("suricata", snap / "eve.jsonl")],
                snap / "fused",
                key,
                input_profile="safe_query_numeric_v2",
            )
            # Replay the prefix: include all observed canonical requests in history,
            # including requests without EVE. Never observe a later response for target.
            model.extractor = FeatureExtractor(**model.glu_spec["state_limits"])
            try:
                target, prefix_count = replay_prefix(
                    model.extractor,
                    iter_rows(snap / "fused/requests.parquet"),
                    target_key,
                    event_t,
                )
            except UncertainHistoryTime as exc:
                rejected.append({"request_id": rid, "reason": str(exc)})
                continue
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
            replayed_target, _ = replay_prefix(
                ext, iter_rows(snap / "fused/requests.parquet"), target_key, event_t
            )
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
            journal.append(output)
            (snap / "feature-proof.json").write_text(
                json.dumps(
                    {
                        "request_id": rid,
                        "event_timestamp": event_t,
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
    run(p.parse_args())
