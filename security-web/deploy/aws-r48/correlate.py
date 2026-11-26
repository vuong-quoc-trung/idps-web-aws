"""Join the R48 private evidence leg for observation-only Rust intake."""

import argparse
import base64
from collections import namedtuple
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import time

from gateway import CATALOG_COLLECTIONS, EGRESS, PORT, ROUTES, SOURCE, observed_label

GUARD_NS = 1_000_000
CUTOFF_NS = 1_000_000_000
MAX_AGE_NS = 65_000_000_000
CHUNK = 128 * 1024
MAX_ROWS = 2048
Event = namedtuple("Event", "value digest received")
CATALOG_LABELS = frozenset(f"/api/{name}/[id]" for name in CATALOG_COLLECTIONS)


class ProofError(ValueError):
    pass


def hex_id(value, length=32):
    return isinstance(value, str) and re.fullmatch(f"[a-f0-9]{{{length}}}", value)


def key(epoch, flow, tx):
    if not hex_id(epoch) or type(flow) is not int or type(tx) is not int:
        raise ValueError("Invalid sensor identity")
    if not 0 <= flow < 2**64 or not 0 <= tx < 2**53:
        raise ValueError("Sensor identity out of range")
    return epoch, str(flow), tx


def sha(value):
    return hashlib.sha256(value).hexdigest()


def stamp_ns(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}\.[0-9]{3}", value):
        raise ValueError("Invalid dispatch clock")
    return int(value.replace(".", "")) * 1_000_000


def utc_ns(value):
    date = datetime.fromisoformat(value)
    if date.utcoffset() is None:
        raise ValueError("Timestamp has no timezone")
    return int(date.timestamp() * 1_000_000_000)


def decode(kind, line, now):
    if kind == "lua":
        f = line.decode("ascii").split("\t")
        if len(f) != 9 or not hex_id(f[5]) or f[6] != "https" or not f[2] or not f[3]:
            raise ValueError("Incomplete Lua evidence")
        return f[5], (key(f[8], int(f[0]), int(f[1])), f[2], f[3], f[4], f[7])

    row = json.loads(line)
    if not isinstance(row, dict):
        raise ValueError("Invalid metadata")
    if kind == "eve":
        if (row.get("event_type"), row.get("src_ip"), row.get("dest_ip"),
            row.get("dest_port"), row.get("in_iface"), row.get("proto")) != (
                "http", SOURCE, EGRESS, PORT, "lo", "TCP"
        ):
            raise ValueError("Not a scoped HTTP transaction")
        host = row["host"]
        if not isinstance(host, str) or not host.startswith("ws-generation-"):
            raise ValueError("No shared sensor generation")
        ident = key(host.removeprefix("ws-generation-"), row["flow_id"], row["tx_id"])
        http = row["http"]
        status = http["status"]
        if type(status) is not int:
            raise ValueError("No HTTP outcome")
        return ident, (http["http_method"], http["url"], status, utc_ns(row["timestamp"]))

    rid = row["request_id"]
    method, path = row["http_method"], row["uri_path"]
    status = row["status"] if kind == "edge" else row["status_code"]
    if (not hex_id(rid) or type(status) is not int
        or ((method, path) not in ROUTES and not (method == "GET" and path in CATALOG_LABELS))):
        raise ValueError("Invalid request metadata")
    client = str(ipaddress.ip_address(row["client_ip"]))
    if kind == "edge":
        dispatch = stamp_ns(row["dispatch"])
        if dispatch > now + GUARD_NS or dispatch < now - MAX_AGE_NS:
            raise ValueError("Expired edge receipt")
        return rid, (method, path, status, client, row["http_host"], dispatch)
    if row.get("source") != "STUDENT_AUDIT" or row.get("source_instance") != "aws-r47" or not row.get("event_id"):
        raise ValueError("Invalid Student Audit identity")
    return rid, (method, path, status, client, utc_ns(row["timestamp"]), row["event_id"])


def verify_wire(wire, prefix, secret):
    if len(wire) > 4096:
        raise ValueError("Proof exceeds limit")
    body, tag = wire.split(".")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", body) or not hex_id(tag, 64):
        raise ValueError("Invalid proof encoding")
    expected = hmac.digest(secret, (prefix + body).encode(), "sha256").hex()
    if not hmac.compare_digest(expected, tag):
        raise ProofError("Bad proof MAC")
    result = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if not isinstance(result, list):
        raise ValueError("Invalid signed payload")
    return result


def match(rid, edge, lua, eve, audit, material, now):
    method, path, status, client, host, dispatch = edge.value
    ident, proof, receipt, forwarded, routed_host = lua.value
    secret = bytes.fromhex(material["key"])
    p = verify_wire(proof, "ws-request-v1:", secret)
    q = verify_wire(receipt, "ws-receipt-v1:", secret)
    actual_target = eve.value[1]
    expected = [client, rid, method, "https", host, sha(actual_target.encode())]
    if (len(p) != 12 or p[:3] != [1, material["kid"], material["epoch"]]
        or not hex_id(p[3]) or p[4:10] != expected
        or type(p[10]) is not int or type(p[11]) is not int
        or p[11] - p[10] != 60_000 or not dispatch // 1_000_000 <= p[10] <= p[11]
        or max(row.received for row in (edge, lua, eve, audit)) // 1_000_000 > p[11]
        or forwarded != client or routed_host != host
        or len(q) != 7 or q[:6] != p[:4] + [sha(proof.encode()), "accepted"]
        or type(q[6]) is not int or not p[10] <= q[6] <= p[11]):
        raise ValueError("Proof and receipt do not bind the same request")
    if (eve.value[0] != method or eve.value[2] != status or observed_label(method, actual_target) != path
        or audit.value[:4] != (method, path, status, client)
        or not all(dispatch - GUARD_NS <= value <= now + GUARD_NS for value in (
            eve.value[3], audit.value[4], q[6] * 1_000_000
        ))):
        raise ValueError("Source observations conflict")
    return ident, p[3]


class Source:
    def __init__(self, path):
        self.path = path
        self.identity = None
        self.offset = 0
        self.tail = b""

    def lines(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return []
        with os.fdopen(fd, "rb") as stream:
            st = os.fstat(stream.fileno())
            identity = st.st_dev, st.st_ino
            if self.identity != identity or st.st_size < self.offset:
                self.offset = max(0, st.st_size - CHUNK) if self.identity is None else 0
                self.identity, self.tail = identity, b""
                if self.offset:
                    stream.seek(self.offset)
                    stream.readline(CHUNK)
                    self.offset = stream.tell()
            stream.seek(self.offset)
            data = self.tail + stream.read(CHUNK)
            self.offset = stream.tell()
        *lines, tail = data.split(b"\n")
        self.tail = tail if len(tail) < CHUNK else b""
        return [line for line in lines if 0 < len(line) <= 16 * 1024]


class Correlator:
    def __init__(self):
        self.events = {name: {} for name in ("edge", "lua", "eve", "audit")}
        self.emitted = {}
        self.nonces = {}

    def recover(self, output, now):
        for path in (output.with_name(output.name + ".1"), output):
            for line in Source(path).lines():
                try:
                    row = json.loads(line)
                    rid = row["request_id"]
                    status = row["status"]
                    stamp = utc_ns(row["observed_at"])
                    ident = key(row["sensor_instance"], int(row["flow_id"]), row["tx_id"])
                    if (hex_id(rid) and status in ("MATCHED", "AMBIGUOUS")
                        and now - MAX_AGE_NS <= stamp <= now + GUARD_NS):
                        self.emitted[rid] = (status, ident, stamp)
                except (AttributeError, ValueError, TypeError, KeyError):
                    continue

    def add(self, kind, line, now):
        try:
            ident, value = decode(kind, line, now)
        except (AttributeError, ValueError, TypeError, KeyError):
            return
        rows = self.events[kind]
        previous = rows.get(ident)
        if previous:
            if previous.value is not None and previous.value != value:
                rows[ident] = Event(None, sha(line), now)
            return
        if len(rows) == MAX_ROWS:
            del rows[next(iter(rows))]
        rows[ident] = Event(value, sha(line), now)

    def finalize(self, material, now):
        for rows in (*self.events.values(), self.emitted, self.nonces):
            for ident, entry in list(rows.items()):
                if now - entry[-1] > MAX_AGE_NS:
                    del rows[ident]
        edge = self.events["edge"]
        candidates = {}
        conflicts = set()
        for rid, e in edge.items():
            lua = self.events["lua"].get(rid)
            audit = self.events["audit"].get(rid)
            if any(entry is not None and entry.value is None for entry in (e, lua, audit)):
                conflicts.add(rid)
                continue
            if not lua or not audit:
                continue
            tx = self.events["eve"].get(lua.value[0])
            if not tx:
                continue
            if tx.value is None:
                conflicts.add(rid)
                continue
            previous = self.emitted.get(rid)
            if previous:
                continue
            try:
                ident, nonce = match(rid, e, lua, tx, audit, material, now)
            except ProofError:
                # Old proof epochs and unauthenticated rows cannot retract a match.
                continue
            except (ValueError, TypeError, KeyError):
                conflicts.add(rid)
                continue
            previous = self.nonces.get(nonce)
            if previous and previous[0] != rid:
                conflicts.update((rid, previous[0]))
                continue
            self.nonces[nonce] = (rid, now)
            candidates[rid] = (
                ident, sha("".join(item.digest for item in (e, lua, tx, audit)).encode())
            )
        for rid in sorted(candidates.keys() | conflicts):
            status = "AMBIGUOUS" if rid in conflicts else "MATCHED"
            previous = self.emitted.get(rid)
            if previous and (previous[0] == status or previous[0] == "AMBIGUOUS"):
                continue
            lua = self.events["lua"].get(rid)
            if status == "MATCHED":
                ident, digest = candidates[rid]
            else:
                ident = lua.value[0] if lua and lua.value else None
                if ident is None and previous:
                    ident = previous[1]
                if ident is None:
                    continue
                digest = sha(("conflict:" + rid + ":" + ident[0]).encode())
            e = edge.get(rid)
            late = not e or not e.value or now + GUARD_NS > e.value[-1] + CUTOFF_NS
            self.emitted[rid] = (status, ident, now)
            yield {
                "schema_version": "three-source-1", "request_id": rid,
                "sensor_instance": ident[0],
                "observed_at": datetime.fromtimestamp(now / 10**9, timezone.utc).isoformat(),
                "status": status, "sources": ["NGINX", "STUDENT_AUDIT", "SURICATA"] if status == "MATCHED" else [],
                "flow_id": ident[1], "tx_id": ident[2],
                "duplicate_events": 0, "flow_context_alerts": 0, "late_event": late,
                "basis": "EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY" if status == "MATCHED" else "RESPONSE_ID_CONFLICTING_HTTP_FIELDS",
                "proof_sha256": digest, "glu": None, "enforcement_actions": 0,
            }


def serve(paths, secret, output):
    model = Correlator()
    model.recover(output, time.time_ns())
    sources = {kind: Source(path) for kind, path in zip(model.events, paths, strict=True)}
    while True:
        now = time.time_ns()
        received = False
        for kind, stream in sources.items():
            for line in stream.lines():
                model.add(kind, line, now)
                received = True
        if received and secret.is_file():
            material = json.loads(secret.read_text())
            rows = list(model.finalize(material, time.time_ns()))
            if rows:
                fd = os.open(output, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
                with os.fdopen(fd, "a") as f:
                    for row in rows:
                        f.write(json.dumps(row, separators=(",", ":")) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        time.sleep(0.12)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--key", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("sources", type=Path, nargs=4, metavar="SOURCE")
    args = cli.parse_args()
    serve(args.sources, args.key, args.output)
