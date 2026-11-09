#!/usr/bin/env python3
"""One fixed <=10K source-coordinate pilot; no HTTP, model scores, fit or sealed reads."""

import argparse
import hashlib
import hmac
import itertools
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import psutil
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from idps_ai.common import PipelineError, atomic_json, canonical_bytes, file_sha256
from idps_ai.data.http_curation import require_development_source
from idps_ai.data.scaling_admission import AdmissionIndex, simhash
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import HEADERS
from idps_ai.training.checkpoint import RunLock

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "ai-training/configs/research/http-scaling-admission-20261109.json"
TASK = ROOT / ".local-dev/data-scaling-20261109"
WAF = ROOT / "ai-training/.artifacts/autonomous_research_20261104/waf_v2/train.parquet"
ORACLE = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2"


def load(p):
    return json.loads(p.read_text())


def opaque(key, purpose, value):
    return hmac.new(key, canonical_bytes([purpose, value]), hashlib.sha256).hexdigest()


def binding():
    return load(TASK / "pilot-lock.json")


def verify():
    lock = binding()
    assert file_sha256(POLICY) == lock["policy_sha256"]
    for name, sha in lock["code_sha256"].items():
        assert file_sha256(ROOT / name) == sha
    # Full WAF hash verified by guarded source audit; on every execution verify
    # full candidate source bytes again, not only size/mtime.
    assert file_sha256(WAF) == lock["source_sha256"]["waf_train"]
    manifest = load(ORACLE / "materialization-report.json")
    for name, sha in manifest["files_sha256"].items():
        assert file_sha256(ORACLE / name) == sha
    assert (
        file_sha256(ORACLE / "materialization-report.json")
        == lock["source_sha256"]["oracle_manifest"]
    )
    assert file_sha256(TASK / "identity.key") == lock["key_fingerprint"]
    assert manifest["gates"]["STRICT_SPLITS"] == "PASS"
    assert manifest["gates"]["FEATURE_CONTRACT"] == "PASS"
    assert manifest["gates"]["ORACLE_PROVENANCE"] == "PASS_FOR_RESEARCH"
    return lock


def oracle_rows(key, start):
    rows = [json.loads(line) for line in (ORACLE / "records.jsonl").open()]
    assert len(rows) == 236
    arrays = {}
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        with np.load(ORACLE / (role.lower() + ".npz"), allow_pickle=False) as z:
            for sid, x, f, b in zip(
                z["ids"], z["x"], z["frozen_runtime"], z["body_syntax"], strict=True
            ):
                assert np.array_equal(x, request_v3.assemble(f, b.tolist()))
                arrays[str(sid)] = x.copy()
    for i, r in enumerate(rows):
        if i < start:
            continue
        x = arrays[r["sample_id"]]
        assert r["feature_contract_fingerprint"] == request_v3.fingerprint()
        y = {"BENIGN_INTENT": 0, "ATTACK_INTENT": 1}.get(r["intent"])
        yield {
            "source": "grounded-v3",
            "source_row": i,
            "request_key": opaque(key, "physical-lab-request", [r["environment"], r["request_id"]]),
            "representation_key": opaque(
                key, "inherited-raw-equivalence", [r["dataset_fingerprint"], r["checksums"]["raw"]]
            ),
            "view_key": opaque(
                key,
                "versioned-feature",
                [request_v3.fingerprint(), hashlib.sha256(x.tobytes()).hexdigest()],
            ),
            "groups": [
                opaque(key, "inherited-lineage", [r["dataset_fingerprint"], k, r[k]])
                for k in ["session_group", "campaign_group"]
            ]
            + [
                opaque(
                    key,
                    "inherited-template",
                    [r["dataset_fingerprint"], r["checksums"]["template"]],
                )
            ],
            "workflow_key": opaque(
                key, "workflow-category", [r["environment"], r["workflow_group"]]
            ),
            "role": r["original_role"],
            "tier": "A" if r["oracle_verified"] and y is not None else "E",
            "label": y,
            "label_task": "attack_intent",
            "identity_verified": True,
            "label_verified": bool(r["oracle_verified"] and y is not None),
            "feature_valid": bool(np.isfinite(x).all() and x.shape == (634,)),
            "body_state": r["state"],
            "headers_available": True,
            "lineage_verified": True,
            "privacy_valid": True,
            "inherited_eligible": bool(r["eligible_for_research"]),
            "reasons": list(r["inclusion_exclusion_reasons"]),
            "near_hash": None,
            "timestamp": None,
            "family": r["family"],
            "method": r["method"],
        }


def allowed_headers(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 1000000:
        raise PipelineError("Invalid source header field")
    matches = list(HEADERS.finditer(value[:8192]))
    selected = {}
    for i, match in enumerate(matches):
        name = match.group(1).lower()
        if name in {"user-agent", "accept", "content-type"}:
            end = matches[i + 1].start() if i + 1 < len(matches) else min(len(value), 8192)
            selected.setdefault(name, value[match.end() : end].strip())
    return "\n".join(
        f"{n}: {selected[n]}" for n in ["user-agent", "accept", "content-type"] if n in selected
    )


def waf_rows(key, start):
    parquet = pq.ParquetFile(WAF)
    assert parquet.num_row_groups == 2 and parquet.metadata.num_rows == 1924461
    vectorizer = HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=512,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    spec = bounded_spec()
    base = 0
    for group in range(2):
        low = max(0, start - 4882 * group)
        if low >= 4882:
            base += parquet.metadata.row_group(group).num_rows
            continue
        seen = 0
        for batch in parquet.iter_batches(batch_size=128, row_groups=[group], use_threads=False):
            # Decode only the two precommitted windows, never scan all rows for selection.
            records = batch.slice(0, min(batch.num_rows, 4882 - seen)).to_pylist()
            for r in records:
                local = seen
                seen += 1
                if local < low:
                    continue
                if local >= 4882:
                    break
                method, url = r["method"], r["url"]
                if any(v is not None and not isinstance(v, str) for v in r.values()):
                    raise PipelineError("Pinned source type changed")
                valid = True
                symbolic = ""
                view = None
                headers = None
                try:
                    if not method or not re.fullmatch("[A-Za-z]{1,24}", method):
                        raise PipelineError("Invalid publisher method")
                    headers = allowed_headers(r["headers"])
                    n = encode_request(spec, project_request(url, method)["numbers"])
                    symbolic, _ = rich_request_v2(method, url, headers, None)
                    content = vectorizer.transform([symbolic]).toarray().astype(np.float32)[0]
                    x = request_v3.assemble(np.concatenate([n, content]), body.extract(None))
                    view = opaque(
                        key,
                        "versioned-feature",
                        [request_v3.fingerprint(), hashlib.sha256(x.tobytes()).hexdigest()],
                    )
                except (PipelineError, ValueError, OverflowError, TypeError):
                    valid = False
                label = {"normal": 0, "anomalous": 1}.get(r["label"])
                yield {
                    "source": "waf-v2",
                    "source_row": base + local,
                    "request_key": None,
                    "representation_key": opaque(
                        key,
                        "complete-publisher-request",
                        [r[k] for k in ["method", "url", "protocol", "headers", "body"]],
                    ),
                    "view_key": view,
                    "groups": [opaque(key, "unknown-lineage", "waf-v2")]
                    + ([opaque(key, "safe-template", symbolic)] if valid else []),
                    "workflow_key": opaque(key, "safe-template", symbolic) if valid else None,
                    "role": "EXTERNAL_STAGING_EXPOSED",
                    "tier": "C" if label is not None else "E",
                    "label": label,
                    "label_task": "publisher_anomaly",
                    "identity_verified": False,
                    "label_verified": False,
                    "feature_valid": valid,
                    "body_state": "MISSING",
                    "headers_available": r["headers"] is not None,
                    "lineage_verified": False,
                    "privacy_valid": True,
                    "inherited_eligible": False,
                    "reasons": [
                        "PUBLISHER_TASK_NOT_VERIFIED_INTENT",
                        "PHYSICAL_CAPTURE_LINEAGE_UNDOCUMENTED",
                    ],
                    "near_hash": simhash(symbolic) if valid else None,
                    "timestamp": None,
                    "family": "publisher_unspecified",
                    "method": method
                    if method and re.fullmatch("[A-Za-z]{1,24}", method)
                    else "OTHER",
                }
            if seen >= 4882:
                break
        assert seen >= 4882
        base += parquet.metadata.row_group(group).num_rows


def candidates(key, start):
    if start < 236:
        yield from oracle_rows(key, start)
    yield from waf_rows(key, max(0, start - 236))


def run(output, stop):
    output = Path(output).resolve()
    require_development_source(output)
    lock = verify()
    key = (TASK / "identity.key").read_bytes()
    with RunLock(output / "runner.lock"):
        index = AdmissionIndex(output, lock)
        start = index.cursor
        if not 0 <= start <= stop <= 10000:
            raise PipelineError("Pilot source-coordinate budget exceeded")
        process = psutil.Process()
        began = time.monotonic()
        before = process.cpu_times()

        def bounded():
            yield from itertools.islice(candidates(key, start), stop - start)

        index.append(bounded())
        assert index.cursor == stop
        if stop == 10000:
            summary = index.finalize()
            state = "COMPLETED"
        else:
            summary = None
            state = "INTERRUPTED_AT_PRECOMMITTED_RESUME_BOUNDARY"
        after = process.cpu_times()
        elapsed = time.monotonic() - began
        atomic_json(
            output / f"metrics-{start:05}-{stop:05}.json",
            {
                "state": state,
                "rows_this_process": stop - start,
                "start_cursor": start,
                "end_cursor": index.cursor,
                "elapsed_seconds": elapsed,
                "process_cpu_seconds": after.user + after.system - before.user - before.system,
                "peak_RSS_bytes": process.memory_info().rss,
                "RSS_note": "end RSS; authoritative peak is independent cgroup telemetry",
                "candidate_throughput_per_second": (stop - start) / elapsed if elapsed else None,
                "no_scores": True,
                "no_training": True,
            },
        )
        index.close()
    print(
        json.dumps(
            {
                "state": state,
                "cursor": stop,
                "dataset_fingerprint": summary["dataset_fingerprint"] if summary else None,
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--stop", type=int, default=10000)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ["OMP_NUM_THREADS"] = "1"
    with threadpool_limits(limits=1):
        run(a.output, a.stop)
