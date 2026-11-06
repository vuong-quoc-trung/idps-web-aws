#!/usr/bin/env python3
"""Verify train-only native response-ID lineage; no PCAP/holdout/model execution."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from idps_ai.data.privacy import pseudonym

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "ai-training/.artifacts/upgrade_20261030_deep/dataset-ready"
PREP = ROOT / "ai-training/.artifacts/scale_upgrade_20261030/prepared-v5"
OUT = ROOT / ".local-dev/three-source/native-id-audit.json"


def main():
    if OUT.exists():
        raise RuntimeError("Preserve earlier audit")
    key = (BASE / "training-redaction.key").read_bytes()
    meta = json.loads((PREP / "dataset_manifest.json").read_text())
    assert pseudonym(key, "fingerprint", "v1") == meta["redaction_key_fingerprint"]
    keys = set()
    for i in range(82):
        rows = (
            pq.ParquetFile(PREP / "requests.parquet")
            .read_row_group(i, columns=["request_key", "split"], use_threads=False)
            .to_pylist()
        )
        keys.update(r["request_key"] for r in rows if r["split"] == "train")
    assert len(keys) == 41607
    report = {}
    manifest = json.loads((BASE / "snapshot/snapshot_manifest.json").read_text())
    for item in manifest["inputs"]:
        counts = Counter()
        seen = set()
        sha = hashlib.sha256()
        with (BASE / "snapshot" / item["file"]).open("rb") as f:
            for line in f:
                sha.update(line)
                e = json.loads(line)
                if item["source"] == "suricata":
                    if e.get("event_type") != "http":
                        continue
                    headers = (e.get("http") or {}).get("response_headers") or []
                    ids = [
                        h.get("value")
                        for h in headers
                        if str(h.get("name", "")).lower() == "x-request-id"
                    ]
                    rid = ids[0] if len(ids) == 1 else None
                    if rid is None:
                        counts[
                            "untrusted_or_missing_response_header_all_source_rows"
                        ] += 1
                        continue
                else:
                    rid = e.get("request_id")
                request_key = pseudonym(key, "request", rid)
                if request_key not in keys:
                    continue
                counts["train_rows_with_native_request_id"] += 1
                if request_key in seen:
                    counts["duplicate_train_request_ids"] += 1
                seen.add(request_key)
                if item["source"] == "suricata":
                    counts["train_rows_with_flow_id"] += int(
                        isinstance(e.get("flow_id"), int)
                    )
                    counts["train_rows_with_retained_tx_id"] += int(
                        isinstance(e.get("tx_id"), int)
                    )
        assert sha.hexdigest() == item["sha256"]
        report[item["source"]] = {
            "unique_training_request_keys": len(seen),
            "counts": dict(counts),
            "snapshot_file_sha256": sha.hexdigest(),
        }
    OUT.write_text(
        json.dumps(
            {
                "train_rows": len(keys),
                "key_fingerprint_matches": True,
                "native_sources": report,
                "scope": "Stored native producer snapshots; exact train key matching. Original PCAP not redecoded. Native EVE response headers only, no explicit request_id fallback accepted. No labels or sealed holdout read.",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({k: v["unique_training_request_keys"] for k, v in report.items()}))


if __name__ == "__main__":
    main()
