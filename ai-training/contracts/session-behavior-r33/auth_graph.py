"""Passive prequential scoring of authenticated actor/device relationships on LANL records."""

import gzip
import math
import re
import sys
import time
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256, load_json

PLAN = Path(__file__).with_name("auth-plan.json")
USER = re.compile(rb"U\d+@DOM\d+\Z")
DEVICE = re.compile(rb"C\d+\Z")
ARMS = ("GLOBAL_DESTINATION", "UNSEEN_ACTOR_TARGET", "CONDITIONAL_SURPRISAL")
END = 259200


def lines(root, manifest):
    inflater = zlib.decompressobj(31)
    remaining = b""
    for i, entry in enumerate(manifest["chunks"]):
        path = root / f"{i:03d}.gzpart"
        if file_sha256(path) != entry["sha256"]:
            raise ValueError("untrusted compressed range")
        with path.open("rb") as stream:
            while block := stream.read(65536):
                plain = (remaining + inflater.decompress(block)).split(b"\n")
                remaining = plain.pop()
                yield from plain
    # Intentional compressed prefix. Only complete lines and seconds may count.


class Graph:
    def __init__(self):
        self.total = 0
        self.actor = Counter()
        self.source = Counter()
        self.dest = Counter()
        self.actor_dest = Counter()
        self.source_dest = Counter()

    def score(self, actor, source, dest):
        background = (self.dest[dest] + 1) / (self.total + len(self.dest) + 1)
        hit = self.actor_dest[actor, dest]
        pa = (hit + 8 * background) / (self.actor[actor] + 8)
        ps = (self.source_dest[source, dest] + 8 * background) / (self.source[source] + 8)
        return (
            round(-100 * math.log2(background)),
            int(hit == 0),
            round(-100 * math.log2((pa + ps) / 2)),
        )

    def update(self, keys):
        for a, s, d in keys:
            self.total += 1
            self.dest[d] += 1
            self.actor[a] += 1
            self.source[s] += 1
            self.actor_dest[a, d] += 1
            self.source_dest[s, d] += 1


def cutoff(hist):
    budget = sum(hist.values()) // 100
    remaining = 0
    for value, n in sorted(hist.items(), reverse=True):
        if remaining + n > budget:
            return value
        remaining += n
    raise ValueError("empty reference histogram")


def graph_study(run):
    root = run / "auth"
    manifest = load_json(root / "download.json")
    plan = load_json(PLAN)
    if (
        manifest["plan_sha"] != file_sha256(PLAN)
        or file_sha256(run / "redteam.txt.gz") != plan["positive_sha256"]
    ):
        raise ValueError("source manifest changed")
    if (root / "assessment.json").exists():
        raise ValueError("immutable evaluation output")
    labels = defaultdict(set)
    for line in gzip.decompress((run / "redteam.txt.gz").read_bytes()).splitlines():
        stamp, a, s, d = line.split(b",")
        labels[int(stamp)].add((a, s, d))
    graph = Graph()
    bins = {part: [Counter() for _ in ARMS] for part in ("reference", "volume", "positive")}
    cuts = None
    observed = Counter()
    by_day = defaultdict(Counter)
    last, bucket, started = None, Counter(), time.monotonic()
    raw = 0

    def finish(stamp, group):
        nonlocal cuts
        if stamp >= 86400 and cuts is None:
            cuts = [cutoff(b) for b in bins["reference"]]
            atomic_json(
                root / "reference-lock.json",
                {
                    "strict_cutoffs": dict(zip(ARMS, cuts, strict=True)),
                    "first_scoring_second": stamp,
                    "reference_groups": sum(bins["reference"][0].values()),
                    "plan_sha": file_sha256(PLAN),
                },
            )
        if stamp >= 43200:
            reference = stamp < 86400
            for key, multiplicity in group.items():
                values = graph.score(*key)
                chosen = bins["reference" if reference else "volume"]
                for b, v in zip(chosen, values, strict=True):
                    b[v] += 1
                if reference:
                    continue
                day = by_day[stamp // 86400]
                day["groups"] += 1
                match = key in labels.get(stamp, ())
                if match:
                    observed["exact_matched_tuple_groups"] += 1
                    observed["one_raw_event" if multiplicity == 1 else "multiple_raw_events"] += 1
                    day["matched"] += 1
                    for b, v in zip(bins["positive"], values, strict=True):
                        b[v] += 1
                for i, value in enumerate(values):
                    if value > cuts[i]:
                        day[ARMS[i] + "_alerts"] += 1
                        if match:
                            day[ARMS[i] + "_hits"] += 1
        graph.update(group)

    for line in lines(root, manifest):
        cols = line.split(b",", 8)
        if len(cols) != 9:
            raise ValueError("authentication schema")
        stamp = int(cols[0])
        if last is not None and stamp != last:
            if stamp < last:
                raise ValueError("timestamp regression")
            finish(last, bucket)
            bucket.clear()
        if stamp >= END:
            break
        last = stamp
        raw += 1
        if raw % 2000000 == 0:
            atomic_json(
                root / "scan-progress.json",
                {
                    "raw": raw,
                    "second": last,
                    "groups": graph.total,
                    "elapsed_s": time.monotonic() - started,
                },
            )
        a, s, d = cols[1], cols[3], cols[4]
        if USER.fullmatch(a) and DEVICE.fullmatch(s) and DEVICE.fullmatch(d):
            bucket[a, s, d] += 1
    else:
        # No subsequent event to seal this last second.
        if last is None:
            raise ValueError("no full seconds")
        stamp = last
    if cuts is None:
        raise ValueError("insufficient chronological exposure")
    total_labels = sum(len(group) for ts, group in labels.items() if 86400 <= ts < stamp)
    volume = sum(bins["volume"][0].values())
    metrics = {}
    for i, k in enumerate(ARMS):
        h = bins["positive"][i]
        ref = bins["reference"][i]
        n = bins["volume"][i]
        hit = sum(v for x, v in h.items() if x > cuts[i])
        alert = sum(v for x, v in n.items() if x > cuts[i])
        metrics[k] = {
            "cutoff_strict": cuts[i],
            "matched_hits": hit,
            "all_published_recall": hit / total_labels if total_labels else None,
            "volume_alerts": alert,
            "alert_fraction": alert / volume if volume else None,
            "reference_alert_fraction": sum(v for x, v in ref.items() if x > cuts[i])
            / sum(ref.values()),
            "unknown_true_fpr": None,
        }
    atomic_json(
        root / "assessment.json",
        {
            "task": "LANL annotation retrieval on exact time/principal/source/target tuples",
            "first_unscored_second": stamp,
            "raw_source_rows_through_incomplete_second": raw,
            "committed_groups": graph.total,
            "reference_groups": sum(bins["reference"][0].values()),
            "evaluation_groups": volume,
            "published_positives_in_window": total_labels,
            "matches": dict(observed),
            "metrics": metrics,
            "by_relative_day": {str(k): dict(v) for k, v in by_day.items()},
            "elapsed_s": time.monotonic() - started,
            "human_verified_benign": 0,
            "http_cutoff_proofs": 0,
            "native_admitted": 0,
            "reference_lock_sha": file_sha256(root / "reference-lock.json"),
            "download_manifest_sha": file_sha256(root / "download.json"),
        },
    )


if __name__ == "__main__":
    graph_study(Path(sys.argv[1]))
