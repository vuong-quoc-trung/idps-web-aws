"""Strict lab transaction correlation. Never infer a match from IP/time alone."""

import hashlib
import hmac
import json
import re
from collections import defaultdict
from datetime import datetime

RID = re.compile(r"[a-f0-9]{32}\Z")
SOURCES = {"NGINX", "STUDENT_AUDIT", "SURICATA"}


class UncertainHistoryTime(RuntimeError):
    """A coarse Nginx-only response may complete after the target response."""


def replay_prefix(extractor, rows, request_key, event_time):
    """Leave target for frozen predict(); do not replay any future response."""
    for count, row in enumerate(rows):
        if row["request_key"] == request_key:
            return row, count
        if row["timestamp"] > event_time:
            break
        if (
            set(row.get("sources", [])) == {"NGINX"}
            and row["timestamp"] + 1 > event_time
        ):
            raise UncertainHistoryTime("NGINX_ONLY_HISTORY_COMPLETION_NOT_PROVEN")
        extractor.observe(row)
    raise RuntimeError("Target absent from chronological snapshot prefix")


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def response_id(value):
    headers = (value.get("http") or {}).get("response_headers") or []
    values = [
        h.get("value")
        for h in headers
        if str(h.get("name", "")).lower() == "x-request-id"
    ]
    return (
        values[0]
        if len(values) == 1 and isinstance(values[0], str) and RID.fullmatch(values[0])
        else None
    )


def identity(value):
    value = {
        k: v
        for k, v in value.items()
        if k not in {"received_at", "sensor_event_id", "adapter_version"}
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Correlator:
    def __init__(self, sensor_id, route_key=None):
        self.sensor_id = sensor_id
        self.route_key = route_key
        self.rows = defaultdict(lambda: defaultdict(dict))
        self.transactions = defaultdict(set)
        self.flow_alerts = defaultdict(set)
        self.duplicates = defaultdict(int)
        self.arrivals = defaultdict(list)
        self.missing_id = 0

    def add(self, source, value, received_at):
        if source == "SURICATA":
            flow = str(value.get("flow_id", ""))
            if value.get("event_type") == "alert" and value.get("tx_id") is None:
                self.flow_alerts[
                    (value.get("sensor_instance", self.sensor_id), flow)
                ].add(identity(value))
                return
            if value.get("event_type") != "http":
                return
            rid = response_id(value)
            tx = value.get("tx_id")
            if not flow or not isinstance(tx, int) or isinstance(tx, bool) or tx < 0:
                self.missing_id += 1
                return
        else:
            rid = value.get("request_id")
        if not isinstance(rid, str) or not RID.fullmatch(rid):
            self.missing_id += 1
            return
        digest = identity(value)
        bucket = self.rows[rid][source]
        if digest in bucket:
            self.duplicates[rid] += 1
            return
        bucket[digest] = value
        self.arrivals[rid].append(received_at)
        if source == "SURICATA":
            self.transactions[
                (
                    value.get("sensor_instance", self.sensor_id),
                    str(value["flow_id"]),
                    value["tx_id"],
                )
            ].add(rid)

    def result(self, rid):
        groups = self.rows[rid]
        present = set(groups)
        result = {
            "schema_version": "three-source-1",
            "request_id": rid,
            "sensor_instance": self.sensor_id,
            "status": "MISSING_SOURCE",
            "sources": sorted(present),
            "flow_id": None,
            "tx_id": None,
            "duplicate_events": self.duplicates[rid],
            "flow_context_alerts": 0,
            "late_event": False,
            "basis": "NO_IP_TIME_MATCH",
            "glu": None,
            "proof_sha256": hashlib.sha256(
                "".join(sorted(d for g in groups.values() for d in g)).encode()
            ).hexdigest(),
            "enforcement_actions": 0,
        }
        if any(len(v) != 1 for v in groups.values()):
            result["status"] = "AMBIGUOUS"
            return result
        values = {k: next(iter(v.values())) for k, v in groups.items()}
        eve = values.get("SURICATA")
        if eve:
            flow, tx = str(eve["flow_id"]), eve["tx_id"]
            instance = eve.get("sensor_instance", self.sensor_id)
            result.update(
                sensor_instance=instance,
                flow_id=flow,
                tx_id=tx,
                flow_context_alerts=len(self.flow_alerts[(instance, flow)]),
            )
            if len(self.transactions[(instance, flow, tx)]) != 1:
                result["status"] = "AMBIGUOUS"
                return result
        if present != SOURCES:
            return result
        n, s, e = values["NGINX"], values["STUDENT_AUDIT"], eve["http"]
        # Compare only actual observed fields, never use these as a join key.
        method = [n.get("http_method"), s.get("http_method"), e.get("http_method")]
        route = [n.get("uri_path"), s.get("uri_path"), e.get("url")]
        if self.route_key is not None:
            route = [
                hmac.new(self.route_key, str(v).encode(), hashlib.sha256).hexdigest()
                if v is not None
                else None
                for v in route[:2]
            ] + [e.get("path_fingerprint")]
        status = [
            n.get("status", n.get("status_code")),
            s.get("status_code"),
            e.get("status"),
        ]
        if (
            None in method
            or None in route
            or None in status
            or len(set(method)) != 1
            or len(set(route)) != 1
            or len(set(status)) != 1
        ):
            result["status"] = "AMBIGUOUS"
            result["basis"] = "RESPONSE_ID_CONFLICTING_HTTP_FIELDS"
            return result
        result.update(status="MATCHED", basis="EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY")
        times = [timestamp(v["timestamp"]) for v in values.values()]
        result["late_event"] = max(self.arrivals[rid]) - max(times) > 2
        return result
