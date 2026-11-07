"""Batch immutable snapshot cache; frozen collector still owns all feature semantics."""

import hashlib
import json
import time
from pathlib import Path

from idps_ai.data.dataset import collect, iter_rows
from idps_ai.data.privacy import pseudonym
from idps_ai.data.readers import Input


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SnapshotBridge:
    def __init__(self, directory, student, nginx, eve_lines, key):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.key = key
        self.metrics = []
        self.cache = {}
        self.eve = [(line, json.loads(line)) for line in eve_lines]
        (self.directory / "student.jsonl").write_bytes(student)
        (self.directory / "nginx.jsonl").write_bytes(nginx)
        http = (
            b"\n".join(l for l, e in self.eve if e.get("event_type") != "flow") + b"\n"
        )
        (self.directory / "eve-http.jsonl").write_bytes(http)
        self.inputs = [
            Input("student", self.directory / "student.jsonl"),
            Input("nginx", self.directory / "nginx.jsonl"),
        ]
        self.http_rows = self._collect(
            self.directory / "eve-http.jsonl", self.directory / "http"
        )
        self.targets = {r["request_key"]: r for r in self.http_rows}

    def _collect(self, eve, out):
        wall, cpu = time.perf_counter(), time.process_time()
        collect(
            [*self.inputs, Input("suricata", eve)],
            out,
            self.key,
            input_profile="safe_query_numeric_v2",
        )
        rows = list(iter_rows(out / "requests.parquet"))
        self.metrics.append(
            {
                "stage": "frozen_collect_and_read",
                "wall_seconds": time.perf_counter() - wall,
                "cpu_seconds": time.process_time() - cpu,
                "rows": len(rows),
            }
        )
        return rows

    def for_request(self, rid):
        target_key = pseudonym(self.key, "request", rid)
        target = self.targets.get(target_key)
        if (
            target is None
            or target["correlation"] != "request_id"
            or set(target["sources"]) != {"NGINX", "STUDENT_AUDIT", "SURICATA"}
        ):
            raise ValueError("FROZEN_COLLECTOR_DID_NOT_CONFIRM_THREE_SOURCES")
        t = target["timestamp"]
        eligible = [
            l
            for l, e in self.eve
            if e.get("event_type") == "flow"
            and isinstance(e.get("received_at"), (int, float))
            and e["received_at"] <= t
        ]
        if not eligible:
            return target_key, t, self.http_rows
        # Identical flow receipt eligibility => identical frozen collector output.
        signature = digest(b"\n".join(eligible))
        if signature not in self.cache:
            if len(self.cache) >= 32:
                raise RuntimeError(
                    "Bounded flow-availability cache full; reduce batch size"
                )
            eve = self.directory / f"eve-{signature}.jsonl"
            eve.write_bytes(
                b"\n".join(
                    l
                    for l, e in self.eve
                    if e.get("event_type") != "flow" or l in eligible
                )
                + b"\n"
            )
            self.cache[signature] = self._collect(
                eve, self.directory / ("fused-" + signature)
            )
        return target_key, t, self.cache[signature]
