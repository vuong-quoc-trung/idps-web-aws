from __future__ import annotations

import json
import math
from collections import OrderedDict, deque
from pathlib import Path

from idps_ai.common import PipelineError, digest, file_sha256
from idps_ai.data.privacy import METHODS, PRODUCTS, ROLES, request_numbers, safe_agent
from idps_ai.data.structure import STRUCTURE_KEYS

WINDOWS = (10, 60, 300)
NUMERIC_COLUMNS = tuple(sorted(request_numbers("/", None)))


def implementation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    return digest(
        {
            str(path.relative_to(root)): file_sha256(path)
            for path in (
                root / "features/pipeline.py",
                root / "features/behavior.py",
                root / "data/privacy.py",
                root / "data/readers.py",
                root / "data/query_numeric.py",
                root / "data/structure.py",
            )
        }
    )


class FeatureExtractor:
    """Post-response, event-time features, inclusive current event, no lookahead.

    A fresh instance is required at each split boundary. Bounded state is
    intentionally observable through context_incomplete, never hidden as zero.
    """

    def __init__(
        self,
        max_entities=100_000,
        max_events_per_entity=2048,
        query_structure=False,
        behavior_dynamics=False,
    ):
        if max_entities < 1 or max_events_per_entity < 1:
            raise PipelineError("Feature state limits must be positive")
        self.max_entities, self.cap = max_entities, max_events_per_entity
        self.state = OrderedDict()
        self.last_timestamp = -math.inf
        self.query_structure = query_structure
        self.behavior_dynamics = behavior_dynamics

    def observe(self, event):
        timestamp = float(event["timestamp"])
        if not math.isfinite(timestamp) or timestamp < self.last_timestamp:
            raise PipelineError("Late or invalid event: replay must be ordered by event time")
        self.last_timestamp = timestamp
        status = event.get("status_code")
        route = event.get("uri_path") or "/"
        method = event.get("http_method")
        role = event.get("role")
        numbers = json.loads(event.get("numeric_json") or "{}")
        result = {name: float(numbers.get(name, 0.0)) for name in NUMERIC_COLUMNS}
        if self.query_structure:
            result.update({name: float(numbers.get(name, 0.0)) for name in sorted(STRUCTURE_KEYS)})
        result.update({"method_" + name: float(method == name) for name in METHODS})
        result.update({"role_" + name: float(role == name) for name in ROLES})
        agent = safe_agent(event.get("user_agent"))
        products = set((agent or "").split())
        result.update({"ua_" + name: float(name in products) for name in PRODUCTS})
        result["user_agent_missing"] = float(event.get("user_agent") in (None, ""))
        result["user_agent_unknown"] = float(
            agent == "[REDACTED]" and not result["user_agent_missing"]
        )
        for family in (2, 3, 4, 5):
            result[f"status_{family}xx"] = float(status is not None and status // 100 == family)
        result["status_missing"] = float(status is None)
        result["authenticated"] = float(
            event.get("user_key") is not None and role in ("ADMIN", "STAFF", "STUDENT")
        )
        for name in ("latency_ms", "request_bytes", "response_bytes"):
            value = event.get(name)
            result[name + "_missing"] = float(value is None)
            result[name + "_log1p"] = math.log1p(min(max(float(value or 0), 0), 1e12))
        flow = json.loads(event.get("flow_json") or "{}")
        for name in (
            "duration_seconds",
            "bytes_to_server",
            "bytes_to_client",
            "packets_to_server",
            "packets_to_client",
        ):
            value = flow.get(name)
            result["flow_" + name + "_missing"] = float(value is None)
            result["flow_" + name + "_log1p"] = math.log1p(min(max(float(value or 0), 0), 1e12))
        for i, seconds in enumerate(WINDOWS):
            result[f"context_suricata_alerts_{seconds}s"] = float(
                (event.get("suricata_alert_counts") or [0, 0, 0])[i]
            )
        for scope, identity in (("ip", event.get("client_key")), ("user", event.get("user_key"))):
            key = (scope, identity)
            if identity is None:
                history, clipped_at, first_seen = [], -math.inf, timestamp
            else:
                history, clipped_at, first_seen = self.state.pop(
                    key, (deque(), -math.inf, timestamp)
                )
                while history and history[0][0] < timestamp - 300:
                    history.popleft()
                if len(history) >= self.cap:
                    clipped_at = history.popleft()[0]
                history.append((timestamp, status, route, method))
                self.state[key] = (history, clipped_at, first_seen)
                while len(self.state) > self.max_entities:
                    self.state.popitem(last=False)
            if self.behavior_dynamics:
                from idps_ai.features.behavior import dynamics

                result.update({scope + "_" + k: v for k, v in dynamics(history).items()})
            for seconds in WINDOWS:
                entries = [item for item in history if item[0] >= timestamp - seconds]
                prefix = f"{scope}_{seconds}s_"
                n = len(entries)
                result[prefix + "count"] = float(n)
                result[prefix + "rate"] = n / seconds
                result[prefix + "error4_ratio"] = sum(
                    s is not None and 400 <= s < 500 for _, s, _, _ in entries
                ) / max(n, 1)
                result[prefix + "error5_ratio"] = sum(
                    s is not None and 500 <= s < 600 for _, s, _, _ in entries
                ) / max(n, 1)
                unique = len({p for _, _, p, _ in entries})
                result[prefix + "uri_cardinality"] = float(unique)
                result[prefix + "unique_uri_ratio"] = unique / max(n, 1)
                result[prefix + "api_ratio"] = sum(
                    p.startswith("/api/") for _, _, p, _ in entries
                ) / max(n, 1)
                result[prefix + "read_ratio"] = sum(
                    m in ("GET", "HEAD", "OPTIONS") for _, _, _, m in entries
                ) / max(n, 1)
                streak = 0
                for _, s, p, _ in reversed(entries):
                    if not (p.startswith("/api/auth/") or p == "/login"):
                        continue
                    if s in (401, 403):
                        streak += 1
                    else:
                        break
                result[prefix + "auth_failure_streak"] = float(streak)
                result[prefix + "context_incomplete"] = float(
                    identity is None
                    or timestamp - first_seen < seconds
                    or clipped_at >= timestamp - seconds
                )
        if not all(math.isfinite(value) for value in result.values()):
            raise PipelineError("Non-finite feature value")
        return result


def feature_columns(include_rule_context=False, *, input_profile="native", behavior_dynamics=False):
    template = {"timestamp": 0, "client_key": None, "user_key": None}
    return sorted(
        name
        for name in FeatureExtractor(
            query_structure=input_profile == "safe_query_numeric_v2",
            behavior_dynamics=behavior_dynamics,
        ).observe(template)
        if include_rule_context or not name.startswith("context_suricata_")
    )


def fit_spec(rows, columns):
    count = 0
    mean = [0.0] * len(columns)
    m2 = [0.0] * len(columns)
    for row in rows:
        count += 1
        for i, name in enumerate(columns):
            value = float(row.get(name, 0.0))
            if not math.isfinite(value):
                raise PipelineError("Non-finite training feature")
            value = min(max(value, -1e6), 1e6)
            delta = value - mean[i]
            mean[i] += delta / count
            m2[i] += delta * (value - mean[i])
    if not count:
        raise PipelineError("No reviewed training examples after temporal/group purge")
    return {
        "feature_version": "ai-features-3",
        "normalizer_version": "ai-normalizer-3",
        "columns": list(columns),
        "imputation": 0.0,
        "raw_clip": [-1e6, 1e6],
        "clip": [-20.0, 20.0],
        "mean": mean,
        "std": [math.sqrt(value / count) if value > 1e-24 else 1.0 for value in m2],
        "fit_rows": count,
        "fit_partition": "train",
        "dtype": "float32",
        "windows_seconds": list(WINDOWS),
        "window_semantics": "[event_time-window,event_time], current observation included exactly once; reset at split boundaries",
        "late_policy": "reject",
        "state_limits": {"max_entities": 100000, "max_events_per_entity": 2048},
        "timestamp_unit": "Unix seconds float64; RFC3339 fractional seconds truncated to microseconds before conversion",
        "flow_semantics": "latest same-flow-id aggregate observed by decision time; context, never per-request packet counters",
        "inference_stage": "post_response",
        "rule_context_default": "excluded",
        "identity_columns": "never model inputs",
        "input_contract": "chronological fused requests.parquet row; ai-normalizer-3 correlation/enrichment; not an individual raw producer line",
        "user_agent_semantics": {
            "vocabulary": list(PRODUCTS),
            "encoding": "multi-hot fixed product families plus missing/unknown; no free text or rule decision",
        },
        "lexical_semantics": "privacy-filtered numeric structure; upstream-masked values remain unavailable",
        "object_access_limitation": "template cardinality/bulk API proxy only; target identity unavailable, no proof of IDOR",
    }


def transform(spec, values):
    import numpy as np

    array = np.asarray(
        [
            values.get(name) if values.get(name) is not None else spec["imputation"]
            for name in spec["columns"]
        ],
        dtype=np.float64,
    )
    if not np.isfinite(array).all():
        raise PipelineError("Non-finite inference feature")
    array = np.clip(array, *spec["raw_clip"])
    return np.clip((array - spec["mean"]) / spec["std"], *spec["clip"]).astype(np.float32)
