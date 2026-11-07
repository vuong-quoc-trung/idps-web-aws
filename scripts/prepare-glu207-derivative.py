#!/usr/bin/env python3
"""Train-partition-only immutable derivative, preserving original features and label uncertainty."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from idps_ai.common import file_sha256

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "ai-training/.artifacts/scale_upgrade_20261030/prepared-v5"
PARENT = ROOT / "ai-training/.artifacts/upgrade_20261030_deep/dataset-ready/collected"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    for base in [PREP, PARENT]:
        declared = json.loads((base / "dataset_manifest.json").read_text())["files"]
        for name in [
            "requests.parquet",
            "features.parquet",
            "observations.parquet",
            "feature_spec.json",
        ]:
            if name in declared:
                assert file_sha256(base / name) == declared[name]["sha256"], name
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    requests = pq.ParquetFile(PREP / "requests.parquet")
    features = pq.ParquetFile(PREP / "features.parquet")
    rows = []
    fx = []
    for i in range(82):
        rg = requests.read_row_group(i, use_threads=False).to_pylist()
        fg = features.read_row_group(i, use_threads=False).to_pylist()
        for r, f in zip(rg, fg, strict=True):
            if r["split"] == "train":
                assert f["event_key"] == r["event_key"] and f["split"] == "train"
                rows.append(r)
                fx.append(f)
    assert len(rows) == 41607
    keys = {r["request_key"] for r in rows}
    assert len(keys) == len(rows)
    obs = defaultdict(lambda: defaultdict(list))
    for b in pq.ParquetFile(PARENT / "observations.parquet").iter_batches(
        columns=[
            "request_key",
            "event_key",
            "source",
            "http_method",
            "uri_path",
            "status_code",
            "timestamp",
            "available_at",
        ],
        use_threads=False,
    ):
        for e in b.to_pylist():
            if e["request_key"] in keys:
                obs[e["request_key"]][e["source"]].append(e)
    meta = []
    quarantine = []
    summary = Counter()
    impact = Counter()
    for r in rows:
        g = obs[r["request_key"]]
        unique = set(g) == {"NGINX", "STUDENT_AUDIT", "SURICATA"} and all(
            len(es) == 1 for es in g.values()
        )
        status = {k: es[0]["status_code"] for k, es in g.items() if len(es) == 1}
        ident = unique and all(
            len({es[0][field] for es in g.values()}) == 1
            for field in ["http_method", "uri_path"]
        )
        app = status.get("STUDENT_AUDIT")
        wire = (
            status.get("NGINX")
            if status.get("NGINX") == status.get("SURICATA")
            else None
        )
        reason = (
            "CONSISTENT"
            if ident and len(set(status.values())) == 1
            else (
                "APPLICATION_WIRE_STATUS_CONFLICT"
                if ident and wire is not None
                else "UNVERIFIED_IDENTITY_OR_WIRE"
            )
        )
        q = reason != "CONSISTENT"
        summary[reason] += 1
        impact[
            f"{'quarantine' if q else 'retained'}|{r['http_method']}|{r['attack_family']}|label={r['label']}"
        ] += 1
        item = {
            "event_key": r["event_key"],
            "request_key": r["request_key"],
            "application_status": app,
            "wire_status": wire,
            "source_statuses": json.dumps(status, sort_keys=True),
            "source_event_keys": json.dumps(
                {k: es[0]["event_key"] for k, es in g.items() if len(es) == 1},
                sort_keys=True,
            ),
            "quarantined": q,
            "reason": reason,
            "native_transaction_identity": "NOT_RETAINED_IN_HISTORICAL_SNAPSHOT",
            "label_review": "INHERITED_RESEARCH_LABEL_NOT_NEWLY_APPROVED",
            "supervised_candidate": not q and r["label"] in (0, 1),
            "history_row_retained": True,
            "original_feature_row_preserved": True,
        }
        meta.append(item)
        if q:
            quarantine.append(item)
    assert summary["APPLICATION_WIRE_STATUS_CONFLICT"] == 174
    pq.write_table(
        pa.Table.from_pylist(rows, schema=requests.schema_arrow),
        a.output / "requests_train.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(fx, schema=features.schema_arrow),
        a.output / "features_train.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(meta),
        a.output / "source_semantics.parquet",
        compression="zstd",
    )
    (a.output / "quarantine.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in quarantine)
    )
    (a.output / "feature_spec.json").write_bytes(
        (PREP / "feature_spec.json").read_bytes()
    )
    sources = {
        str(p.relative_to(ROOT)): file_sha256(p)
        for p in [
            PREP / "dataset_manifest.json",
            PREP / "feature_spec.json",
            PREP / "requests.parquet",
            PREP / "features.parquet",
            PARENT / "observations.parquet",
        ]
    }
    report = {
        "schema_version": "glu207-derivative-1",
        "status": "PREPARED_NOT_TRAINING_ADMITTED",
        "partition": "train only; no sealed holdout/evaluation opened",
        "rows": len(rows),
        "classification": dict(summary),
        "supervised_candidates": sum(r["supervised_candidate"] for r in meta),
        "unknown_or_unlabeled_excluded_from_supervision": sum(
            r["label"] not in (0, 1) for r in rows
        ),
        "impact_by_method_family_label": dict(impact),
        "source_hashes": sources,
        "files": {f.name: file_sha256(f) for f in a.output.iterdir() if f.is_file()},
        "frozen_unchanged": all(file_sha256(ROOT / p) == h for p, h in sources.items()),
        "limits": [
            "174 conflicts quarantined from supervised candidate selection, retained for history/provenance/impact analysis",
            "Existing features copied exactly, not refitted. Other rows can retain historical contribution of quarantined requests; this is documented, not claimed full removal",
            "Application405/wire403 lifecycle cause not reproduced; no outcome/attack/label correction inferred",
            "Historical native tx_id unavailable, not invented",
            "Labels inherited from scenario/runner research evidence; no independent review or formal admission claimed",
            "No new calibration/evaluation datasets supplied; this derivative alone is insufficient to launch the proposed challenger",
        ],
    }
    (a.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ["source_hashes", "files", "impact_by_method_family_label"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
