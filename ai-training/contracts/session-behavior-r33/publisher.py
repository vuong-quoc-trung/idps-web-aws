"""Offline prefix projection from author-annotated sessions. Never reads mouse biometrics."""

import hashlib
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from history import Prefix
from idps_ai.common import file_sha256, load_json

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "information-r32"))
from external import uri  # noqa: E402 - frozen R32 implementation

LINE = re.compile(rb'^.*?\[([^\]]+)\] "GET ([^ ]+) HTTP/[^"]+" \S+ \S+ "[^"]*" (\S+) ')
ACCESS = re.compile(rb'^.*?\[([^\]]+)\] "(\S+) (\S+) HTTP/[^"]+" \S+ \S+ "[^"]*" (\S+) ')
DOCUMENT = re.compile(rb"/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.php\Z")


@lru_cache(maxsize=4096)
def second(stamp):
    return int(datetime.strptime(stamp.decode(), "%d/%b/%Y:%H:%M:%S %z").timestamp())


def fingerprint(session):
    return hashlib.sha256(b"R33-study-v1/" + session).hexdigest()


def episodes(observed_seconds):
    starts = []
    last = None
    for t in sorted(observed_seconds):
        if last is None or t - last > 1800:
            starts.append(t)
        last = t
    return starts


def reconcile(archive, labels, sessions, counters, run):
    """Use raw PHP binding and the publisher's 30-minute session definition."""
    from bisect import bisect_right

    indexed = defaultdict(dict)
    for sid in labels:
        base, sep, index = sid.rpartition(b"_")
        if not sep or not index.isdigit() or not base or int(index) in indexed[base]:
            raise ValueError("ambiguous annotated session")
        indexed[base][int(index)] = sid
    if {fingerprint(base) for base in indexed} & set(load_json(run / "frozen.json")["phase1_ids"]):
        raise ValueError("raw session shared across phases")
    timestamps, docs, locations = defaultdict(set), defaultdict(list), {}
    for name in sorted(
        n
        for n in archive.namelist()
        if n.startswith("phase2/data/web_logs/") and n.endswith(".log")
    ):
        with archive.open(name) as stream:
            for line in stream:
                match = ACCESS.match(line)
                if not match:
                    continue
                stamp, method, target, base = match.groups()
                if base not in indexed:
                    continue
                t = second(stamp)
                timestamps[base].add(t)
                if method != b"GET" or not (target == b"/" or DOCUMENT.fullmatch(target)):
                    continue
                if locations.setdefault((base, t, target), name) != name:
                    counters["duplicate_cross_file"] += 1
                    continue
                docs[base].append((t, target))
    for base, annotations in indexed.items():
        starts = episodes(timestamps[base])
        # Ambiguous family or missing episode: no labels propagated across a gap.
        if (
            set(annotations) != set(range(len(starts)))
            or len({labels[s] for s in annotations.values()}) != 1
        ):
            counters["unresolved_annotated_sessions"] += len(annotations)
            counters["unresolved_document_rows"] += len(docs[base])
            continue
        for t, route in docs[base]:
            sessions[annotations[bisect_right(starts, t) - 1]].append((t, route))
    counters["raw_session_overlap_with_phase1"] = 0


def read(run, phase):
    plan = load_json(HERE / "protocol.json")
    path = run / "source.zip"
    if file_sha256(path) != plan["archive_sha256"]:
        raise ValueError("source SHA mismatch")
    if phase == "phase1":
        lists = [
            f"phase1/annotations/humans_and_{kind}_bots/train" for kind in ("moderate", "advanced")
        ]
    elif phase == "phase2":
        lists = [
            "phase2/annotations/humans_and_moderate_and_advanced_bots/humans_and_moderate_and_advanced_bots"
        ]
    else:
        raise ValueError("unknown source role")
    labels, sessions, counters = {}, defaultdict(list), Counter()
    with ZipFile(path) as archive:
        for name in lists:
            for line in archive.read(name).splitlines():
                sid, label = line.strip().split()
                kind = label.decode()
                if (
                    kind not in ("human", "moderate_bot", "advanced_bot")
                    or labels.setdefault(sid, kind) != kind
                ):
                    raise ValueError("annotation conflict or unexpected label")
        locations = {}
        if phase == "phase2":
            reconcile(archive, labels, sessions, counters, run)
        for name in sorted(archive.namelist()) if phase == "phase1" else ():
            if not (name.startswith(phase + "/data/web_logs/") and name.endswith(".log")):
                continue
            with archive.open(name) as f:
                for line in f:
                    match = LINE.match(line)
                    if not match:
                        continue
                    stamp, target, sid = match.groups()
                    if sid not in labels or not (target == b"/" or DOCUMENT.fullmatch(target)):
                        continue
                    t = second(stamp)
                    key = sid, t, target
                    if locations.setdefault(key, name) != name:
                        counters["duplicate_cross_file"] += 1
                        continue
                    sessions[sid].append((t, target))
    rows = []
    for sid, items in sessions.items():
        state = Prefix()
        # Archive event time has whole-second resolution. Reject windows with ties;
        # tie-breaking within a second never supplies a distinguishable input.
        for t, target in sorted(items):
            history, reason = state.observe(t, target)
            counters[reason] += 1
            rows.append(
                (fingerprint(sid), labels[sid], uri(target.decode("ascii"), "GET"), history)
            )
    counts = Counter(labels.values())
    counters["annotated_sessions"] = len(labels)
    counters["sessions_without_navigation"] = len(set(labels) - set(sessions))
    return rows, {fingerprint(k): v for k, v in labels.items()}, dict(counters), dict(counts)


def arrays(rows):
    return {
        "id": np.array([r[0] for r in rows]),
        "kind": np.array([r[1] for r in rows]),
        "y": np.array([int(r[1] != "human") for r in rows]),
        "uri": np.stack([r[2] for r in rows]),
        "hist": np.array([r[3] if r[3] is not None else (np.nan,) * 8 for r in rows]),
    }
