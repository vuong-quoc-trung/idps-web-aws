#!/usr/bin/env python3
"""Public-view ambiguity audit; never fits/tunes a deployed threshold."""

import argparse
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256
from idps_ai.data.http_benchmark import iter_benchmark


def run(directory, output):
    counts, coverage, bodies = Counter(), Counter(), Counter()
    with tempfile.TemporaryDirectory(prefix=".public-quality-") as temporary:
        db = sqlite3.connect(Path(temporary) / "index.sqlite")
        db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE r(id TEXT,f TEXT,p TEXT,y INTEGER);
            CREATE INDEX ri ON r(id); CREATE INDEX rf ON r(f);""")
        for row in iter_benchmark(directory, original=True):
            db.execute(
                "INSERT INTO r VALUES(?,?,?,?)",
                (row["event_key"], row["feature_key"], row["split"], row["label"]),
            )
            key = row["split"] + ("_normal" if row["label"] == 0 else "_anomalous")
            counts[key] += 1
            bodies[key] += int(row["body_present"])
            coverage[key] += int(json.loads(row["numbers_json"])["query_length"] > 0)
        db.commit()
        unique = db.execute("SELECT count(DISTINCT id) FROM r").fetchone()[0]
        overlap = db.execute(
            "SELECT count(*) FROM (SELECT id FROM r GROUP BY id HAVING count(DISTINCT p)>1)"
        ).fetchone()[0]
        conflicts = db.execute(
            "SELECT count(*) FROM (SELECT id FROM r GROUP BY id HAVING count(DISTINCT y)>1)"
        ).fetchone()[0]
        ambiguity = db.execute(
            "SELECT sum(min(n0,n1)),count(*) FROM (SELECT f,sum(y=0) AS n0,sum(y=1) AS n1 FROM r WHERE p='test' GROUP BY f) WHERE n0>0 AND n1>0"
        ).fetchone()
        all_test = sum(v for k, v in counts.items() if k.startswith("test_"))
        db.close()
    result = {
        "source_manifest_sha256": file_sha256(Path(directory) / "manifest.json"),
        "source_records": dict(counts),
        "unique_observable_request_identities": unique,
        "request_identities_crossing_original_train_test": overlap,
        "conflicting_binary_label_request_identities": conflicts,
        "nonempty_query_after_existing_v2_privacy_projection": dict(coverage),
        "body_present_requests": dict(bodies),
        "test_mixed_label_feature_vectors": ambiguity[1],
        "test_minimum_errors_any_deterministic_classifier_using_this_view": ambiguity[0] or 0,
        "test_empirical_view_error_lower_bound": (ambiguity[0] or 0) / max(all_test, 1),
        "interpretation": "An optimistic empirical information-loss bound from exact static vector collisions, not model accuracy, label-error proof or a tuned decision rule. Different bodies/headers and URI masking can legitimately share one vector.",
        "formal_training_permitted": False,
        "original_lab_test_opened": False,
    }
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.benchmark, args.output), sort_keys=True))
