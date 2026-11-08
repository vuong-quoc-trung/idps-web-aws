#!/usr/bin/env python3
"""Local-only fingerprint, row-reference and finite privacy checks. Never prints values."""

import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3 as candidate

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai-training/.artifacts/attack_intent_20261107/release-v3"


def load(p):
    return json.loads(p.read_text())


def forms(value):
    raw = value.encode()
    return {
        raw,
        quote(value, safe="").encode(),
        base64.b64encode(raw),
        raw.hex().encode(),
        hashlib.sha1(raw).hexdigest().encode(),
        hashlib.sha256(raw).hexdigest().encode(),
        json.dumps(value)[1:-1].encode(),
    }


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def verify(release, output):
    report = load(release / "materialization-report.json")
    for name, sha in report["files_sha256"].items():
        assert file_sha256(release / name) == sha
    rows = [json.loads(line) for line in (release / "records.jsonl").read_text().splitlines()]
    core = [{k: v for k, v in r.items() if k != "dataset_fingerprint"} for r in rows]
    assert (
        digest(
            {
                "records": core,
                "plan_fingerprint": report["plan_fingerprint"],
                "parent_fingerprint": report["parent_fingerprint"],
            }
        )
        == report["dataset_fingerprint"]
    )
    assert all(r["dataset_fingerprint"] == report["dataset_fingerprint"] for r in rows)
    original = [json.loads(line) for line in (SOURCE / "records.jsonl").read_text().splitlines()]
    # Verify the equivalence relation, never emit the original group values or digests.
    for kind in ["session_group", "campaign_group"]:
        forward, backward = {}, {}
        for row in rows:
            old = original[row["parent_record_index"]][kind]
            new = row[kind]
            assert new.startswith(kind + "-") and new[len(kind) + 1 :].isdigit()
            assert old not in forward or forward[old] == new
            assert new not in backward or backward[new] == old
            forward[old], backward[new] = new, old
    secrets_in_memory = set()
    verified = 0
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        subset = [r for r in rows if r["original_role"] == role]
        with (
            np.load(release / (role.lower() + ".npz"), allow_pickle=False) as z,
            np.load(SOURCE / (role.lower() + ".npz"), allow_pickle=False) as parent,
        ):
            assert z["x"].shape == (len(subset), 634) and z["x"].dtype == np.float32
            assert (
                z["body_syntax"].shape == (len(subset), 46) and z["body_syntax"].dtype == np.uint8
            )
            assert set(z.files) == {
                "x",
                "frozen_runtime",
                "body_syntax",
                "ids",
                "binary_y",
                "eligible",
                "paired_common_eligible",
            }
            for i, r in enumerate(subset):
                assert str(z["ids"][i]) == r["sample_id"]
                ref = r["frozen_request_feature_reference"]
                assert ref["derivative_row"] == i
                assert str(parent["ids"][ref["parent_row"]]) == r["sample_id"]
                assert np.array_equal(parent["runtime"][ref["parent_row"]], z["frozen_runtime"][i])
                assert np.array_equal(z["body_syntax"][i], r["body_syntax_vector"])
                assert np.array_equal(
                    z["x"][i], candidate.assemble(z["frozen_runtime"][i], r["body_syntax_vector"])
                )
                assert bool(z["eligible"][i]) == r["eligible_for_research"]
                old = original[r["parent_record_index"]]
                assert old["request_id"] == r["request_id"] and old["sample_id"] == r["sample_id"]
                assert old["split"] == r["original_role"]
                assert all(
                    old[k] == r[k]
                    for k in [
                        "intent",
                        "outcome",
                        "review_status",
                        "oracle_verified",
                        "workflow_group",
                    ]
                )
                folder = Path(old["request_provenance"]["receipt_file"]).parent
                raw = (folder / "request-body.bin").read_text()
                if len(raw) >= 8:
                    secrets_in_memory.add(raw)
                try:
                    value = json.loads(raw)
                except ValueError:
                    value = dict(parse_qsl(raw, keep_blank_values=True))
                if isinstance(value, dict):
                    for key, v in value.items():
                        if key.lower() not in body.ALLOW:
                            secrets_in_memory.update(s for s in strings(v) if len(s) >= 8)
                headers = load(folder / "request-headers.json")
                for key, v in headers.items():
                    if key.lower() in {"authorization", "cookie"}:
                        secrets_in_memory.update(s for s in strings(v) if len(s) >= 8)
                        for cookie in str(v).split(";"):
                            val = cookie.partition("=")[2].strip()
                            if len(val) >= 8:
                                secrets_in_memory.add(val)
                verified += 1
    files = [p for p in release.iterdir() if p.is_file()]
    needles = {n for value in secrets_in_memory for n in forms(value)}
    assert not any(n in p.read_bytes() for p in files for n in needles), (
        "Private value/representation found in derivative"
    )
    # Canary boundary is offline; no HTTP requests, sockets or additional evidence copies.
    canaries = [
        "FakePassword-" + secrets.token_hex(20),
        "FakeApiKey-" + secrets.token_hex(20),
        "FakeSession-" + secrets.token_hex(20),
        secrets.token_hex(32),
        "person-" + secrets.token_hex(8) + "@example.invalid",
        "+849" + str(secrets.randbelow(10**8)).zfill(8),
    ]
    observed = []
    for secret in canaries:
        value = {
            "message": "Ordinary mathematical notes: a < b",
            "password": secret,
            "email": secret,
            "token": secret,
            "unknown-private-field": secret,
        }
        vec = body.extract(json.dumps(value).encode(), "application/json")
        observed.append(vec)
    assert all(v == observed[0] for v in observed)
    synthetic = candidate.assemble(np.zeros(588, np.float32), observed[0])
    stream = io.BytesIO()
    np.savez(stream, x=synthetic, body_syntax=np.array(observed, np.uint8))
    serialized = stream.getvalue() + json.dumps({"features": observed}).encode()
    assert not any(n in serialized for value in canaries for n in forms(value))
    result = {
        "status": "PASS_FOR_RESEARCH",
        "dataset_fingerprint": report["dataset_fingerprint"],
        "rows_verified": verified,
        "tensor_parent_and_derivative_references_verified": verified,
        "fingerprint_verified": True,
        "artifact_files_scanned": len(files),
        "source_values_scanned_in_RAM": len(secrets_in_memory),
        "canary_families": len(canaries),
        "protected_value_invariance": True,
        "transformations": ["literal", "URL", "base64", "hex", "SHA1", "SHA256", "JSONescaped"],
        "source_values_or_secret_hashes_written": False,
        "scope": "Finite offline derivative serialization and actual source-value scans. Reuses real-ingress lab qualification; no production privacy, DP, independent-human or new live-delivery claim",
    }
    assert not output.exists()
    atomic_json(output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    try:
        with threadpool_limits(limits=1):
            verify(a.release.resolve(), a.output.resolve())
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_type": type(exc).__name__, "details": "SUPPRESSED"}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
