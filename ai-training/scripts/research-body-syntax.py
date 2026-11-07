#!/usr/bin/env python3
"""One locked representation diagnostic and isolated HTTP proof; never fits a model."""

import argparse
import base64
import gzip
import http.client
import importlib.util
import json
import secrets
import socket
import time
import tracemalloc
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import read_receipt
from idps_ai.features import body_syntax_v1 as syntax
from idps_ai.features.body_syntax_transport import Ingress, SyntaxWorker

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def fixture():
    p = ROOT / "ai-training/tests/test_body_syntax_v1.py"
    spec = importlib.util.spec_from_file_location("body_transport_fixture", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def wait_event(worker, rid):
    until = time.monotonic() + 3
    while rid not in worker.events and time.monotonic() < until:
        time.sleep(0.002)
    if rid not in worker.events:
        raise RuntimeError("Isolated syntax delivery timeout")
    return worker.events[rid]


def http_probe(port, method, path, body, headers):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    start = time.perf_counter_ns()
    try:
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        assert r.status == 200 and r.getheader("X-Witness") == "unchanged" and r.read() == b"OK"
    finally:
        c.close()
    return (time.perf_counter_ns() - start) / 1e6


def mixed(rows, vectors):
    groups = defaultdict(list)
    for i, v in enumerate(vectors):
        groups[v.tobytes()].append(i)
    chosen = [
        ix
        for ix in groups.values()
        if {rows[i]["intent"] for i in ix} >= {"BENIGN_INTENT", "ATTACK_INTENT"}
    ]
    return {
        "unique_views": len(groups),
        "mixed_groups": len(chosen),
        "affected_records": sum(map(len, chosen)),
        "counts": [
            {"records": len(ix), "intents": dict(Counter(rows[i]["intent"] for i in ix))}
            for ix in chosen
        ],
    }, chosen


def study(base):
    plan = load(base / "plan.json")
    lock = load(base / "candidate-lock.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert lock["contract_sha256"] == syntax.CONTRACT_SHA256
    for path, sha in {**plan["protected_sha256"], **lock["source_sha256"]}.items():
        assert file_sha256(ROOT / path) == sha
    output = base / "diagnostics-v1"
    output.mkdir(mode=0o700, exist_ok=False)
    release = ROOT / "ai-training/.artifacts/attack_intent_20261107/release-v3"
    data = load(release / "dataset-release.json")
    assert data["dataset_fingerprint"] == plan["dataset_fingerprint"]
    for name, sha in data["files_sha256"].items():
        assert file_sha256(release / name) == sha
    rows = [json.loads(line) for line in (release / "records.jsonl").read_text().splitlines()]
    runtime_by_id = {}
    for role in ["train", "calibration", "development"]:
        with np.load(release / (role + ".npz"), allow_pickle=False) as z:
            runtime_by_id.update(zip(z["ids"].astype(str), z["runtime"]))
    runtime = np.stack([runtime_by_id[r["sample_id"]] for r in rows])
    raw = []
    body_vectors = []
    cpu_times = []
    peak_allocations = []
    for r in rows:
        folder = Path(r["request_provenance"]["receipt_file"]).parent
        req, _ = read_receipt(folder, request_id=r["request_id"])
        headers = load(folder / "request-headers.json")
        lowered = {k.lower(): v for k, v in headers.items()}
        body = (folder / "request-body.bin").read_bytes()
        observed = body if body or "content-length" in lowered else None
        tracemalloc.start()
        t = time.process_time_ns()
        vector = syntax.extract(
            observed,
            lowered.get("content-type"),
            content_encoding=lowered.get("content-encoding"),
            transfer_encoding=lowered.get("transfer-encoding"),
        )
        cpu_times.append((time.process_time_ns() - t) / 1e6)
        peak_allocations.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        body_vectors.append(vector)
        raw.append((req, headers, observed))
    body_vectors = np.array(body_vectors, np.uint8)
    joint = np.concatenate([runtime, body_vectors.astype(np.float32)], axis=1)
    before, original_mixed = mixed(rows, runtime)
    after, _ = mixed(rows, joint)
    root_causes = []
    for indices in original_mixed:
        subset = [raw[i] for i in indices]
        full_input_intents = defaultdict(set)
        for i in indices:
            req, headers, body = raw[i]
            # Equality in RAM only; never emit or hash raw body/secret values.
            key = (req["method"], req["url"], tuple(sorted(headers.items())), body)
            full_input_intents[key].add(rows[i]["intent"])
        partial_after, _ = mixed([rows[i] for i in indices], joint[indices])
        root_causes.append(
            {
                "records": len(indices),
                "unique_request_ids": len({rows[i]["request_id"] for i in indices}),
                "intents": dict(Counter(rows[i]["intent"] for i in indices)),
                "methods": sorted({req["method"] for req, _, _ in subset}),
                "routes": sorted({rows[i]["endpoint_template"] for i in indices}),
                "content_types": sorted({h.get("Content-Type", "") for _, h, _ in subset}),
                "body_available": sum(bool(b) for _, _, b in subset),
                "unique_bodies_in_RAM": len({b for _, _, b in subset}),
                "selected_header_profiles": len(
                    {
                        tuple(
                            (k, v)
                            for k, v in sorted(h.items())
                            if k.lower() in {"user-agent", "accept", "content-type"}
                        )
                        for _, h, _ in subset
                    }
                ),
                "all_header_profiles_in_RAM": len({tuple(sorted(h.items())) for _, h, _ in subset}),
                "conservative_session_lineages": len({rows[i]["session_group"] for i in indices}),
                "outcomes": dict(Counter(rows[i]["outcome"] for i in indices)),
                "same_complete_HTTP_input_opposite_intent_groups": sum(
                    v >= {"BENIGN_INTENT", "ATTACK_INTENT"} for v in full_input_intents.values()
                ),
                "cause": "CASE_A_BODY_LOST_AT_WORKER_MODEL_RECORD; CASE_B_NOT_DEMONSTRATED",
                "candidate_after": partial_after,
                "policy_limit": "Identity field values, including email/password, deliberately excluded; body availability is not permission to profile them.",
            }
        )
    np.savez(
        output / "body-features.npz",
        features=body_vectors,
        ids=np.array([r["sample_id"] for r in rows]),
        contract_sha256=np.array(syntax.CONTRACT_SHA256),
    )
    atomic_json(output / "contract.json", syntax.contract())
    # The worker and origin witness are isolated, real sockets; no HTTP receipts are written.
    witness = fixture().Witness()
    worker = SyntaxWorker(output / "worker")
    rid_set = [r["request_id"] for r in rows]
    ingress = Ingress(witness.port, worker.socket_path, rid_set)
    latencies = []
    canaries = [
        "FakePassword-" + secrets.token_hex(24),
        "FakeApiKey-" + secrets.token_hex(24),
        "FakeSession-" + secrets.token_hex(24),
        secrets.token_hex(32),
        "person-" + secrets.token_hex(8) + "@example.invalid",
        "+849" + str(secrets.randbelow(10**8)).zfill(8),
    ]
    canary_vectors = []
    unsupported_results = []
    try:
        for i, r in enumerate(rows):
            req, headers, body = raw[i]
            assert (
                next((v for k, v in headers.items() if k.lower() == "x-request-id"), None)
                == r["request_id"]
            )
            latencies.append(http_probe(ingress.port, req["method"], req["url"], body, headers))
            path, received_headers, received_body = witness.seen.pop()
            assert path == req["url"] and received_body == (body or b"")
            assert all(received_headers.get(k) == v for k, v in headers.items())
            assert wait_event(worker, r["request_id"])["features"] == body_vectors[i].tolist()
        for i, canary in enumerate(canaries):
            rid = uuid.uuid4().hex
            ingress.trusted_ids.add(rid)
            body = json.dumps(
                {
                    "message": "<svg onload=alert(1)>",
                    "password": canary,
                    "api_key": canary,
                    "session": canary,
                    "email": canary,
                    "arbitrary-user-field": canary,
                }
            ).encode()
            headers = {
                "Content-Type": "application/json",
                "X-Request-Id": rid,
                "Authorization": "Bearer " + canary,
                "Cookie": "session=" + canary,
            }
            http_probe(ingress.port, "POST", "/witness", body, headers)
            assert witness.seen.pop()[2] == body
            e = wait_event(worker, rid)
            assert e["features"] == syntax.extract(body, "application/json")
            canary_vectors.append(e["features"])
            # Rejected telemetry attempts exercise actual worker error serialization.
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                s.sendto(
                    json.dumps({"raw_body": canary, "secret": canary}).encode(), worker.socket_path
                )
        formats = [
            (b'{"message":', {"Content-Type": "application/json"}, "MALFORMED"),
            (
                b"message=" + b"x" * 9000,
                {"Content-Type": "application/x-www-form-urlencoded"},
                "OVERSIZE",
            ),
            (
                b"--boundary\r\nprivate fixture\r\n--boundary--",
                {"Content-Type": "multipart/form-data; boundary=boundary"},
                "UNSUPPORTED_TYPE",
            ),
            (
                gzip.compress(b"message=hello"),
                {"Content-Type": "application/x-www-form-urlencoded", "Content-Encoding": "gzip"},
                "UNSUPPORTED_ENCODING",
            ),
            (
                b"9\r\nmessage=x\r\n0\r\n\r\n",
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Transfer-Encoding": "chunked",
                },
                "UNSUPPORTED_TRANSFER",
            ),
        ]
        for body, headers, expected in formats:
            rid = uuid.uuid4().hex
            ingress.trusted_ids.add(rid)
            headers["X-Request-Id"] = rid
            http_probe(ingress.port, "POST", "/witness", body, headers)
            assert witness.seen.pop()[2] == body
            vector = wait_event(worker, rid)["features"]
            assert syntax.state_of(vector) == expected
            assert vector == syntax.extract(
                body,
                headers.get("Content-Type"),
                content_encoding=headers.get("Content-Encoding"),
                transfer_encoding=headers.get("Transfer-Encoding"),
            )
            unsupported_results.append(
                {
                    "expected_state": expected,
                    "HTTP_forward_unchanged": True,
                    "offline_live_parity": True,
                }
            )
        nominal_sent = ingress.sent
        assert ingress.dropped == 0 and worker.rejected == len(canaries)
        old_extractor = ingress.extractor

        def broken(*_, **__):
            raise RuntimeError("Extractor intentionally unavailable")

        ingress.extractor = broken
        http_probe(
            ingress.port,
            "POST",
            "/witness",
            b"message=hello",
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        witness.seen.clear()
        ingress.extractor = old_extractor
        ingress.worker_path = str(output / "absent.sock")
        http_probe(
            ingress.port,
            "POST",
            "/witness",
            b"message=hello",
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        witness.seen.clear()
        ingress.enabled = False
        http_probe(
            ingress.port,
            "POST",
            "/witness",
            b"message=hello",
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        witness.seen.clear()
        direct = []
        via = []
        ingress.worker_path = worker.socket_path
        # Compare HTTP proxy overhead with extraction off/on; all outside dataset roles.
        for _ in range(12):
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            direct.append(
                http_probe(ingress.port, "POST", "/witness", b"message=plain+notes", headers)
            )
            witness.seen.clear()
            ingress.enabled = True
            via.append(
                http_probe(ingress.port, "POST", "/witness", b"message=plain+notes", headers)
            )
            witness.seen.clear()
            ingress.enabled = False
        assert ingress.max_prefix <= syntax.MAX_BYTES
    finally:
        ingress.close()
        worker.close()
        witness.close()
    np.savez(output / "canary-feature-artifact.npz", features=np.array(canary_vectors, np.uint8))
    needle_forms = {
        x.encode()
        for c in canaries
        for x in [c, quote(c), base64.b64encode(c.encode()).decode(), json.dumps(c)[1:-1]]
    }
    scanned = 0
    for path in output.rglob("*"):
        if path.is_file():
            assert not any(n in path.read_bytes() for n in needle_forms)
            scanned += 1
    # Existing production journals have no new connection to this prototype.
    existing_scanned = 0
    for pattern in ["*.log", "normalized-events.jsonl", "ai/*.jsonl", "correlation/*.jsonl"]:
        for path in (ROOT / ".local-dev/foundation").glob(pattern):
            with path.open("rb") as stream:
                carry = b""
                while block := stream.read(1024 * 1024):
                    assert not any(n in carry + block for n in needle_forms)
                    carry = block[-max(map(len, needle_forms)) :]
            existing_scanned += 1
    for path, sha in plan["protected_sha256"].items():
        assert file_sha256(ROOT / path) == sha
    result = {
        "milestone_state": "CASE_B_CANDIDATE_PARTIAL",
        "candidate_version": syntax.VERSION,
        "contract_sha256": syntax.CONTRACT_SHA256,
        "body_dimensions": len(syntax.COLUMNS),
        "diagnostic_joint_dimensions_not_a_frozen_model_input": joint.shape[1],
        "records": len(rows),
        "dataset_fingerprint": data["dataset_fingerprint"],
        "before": before,
        "after": after,
        "root_causes": root_causes,
        "extraction_states": dict(Counter(syntax.state_of(v.tolist()) for v in body_vectors)),
        "privacy": {
            "isolated_serialization_datagram_worker_journal_feature_artifacts": "PASS",
            "canary_families": len(canaries),
            "raw_base64_urlencoded_escaped_canary_leaks": 0,
            "output_files_scanned": scanned,
            "existing_foundation_logs_journals_scanned_no_canaries": existing_scanned,
            "rejected_canary_events": worker.rejected,
            "Rust_database_dashboard_live_candidate_paths": "NOT_EXERCISED_NO_CONNECTION",
            "production_privacy_gate": "NOT_VERIFIED",
            "residual_risk": "Coarse count/flag disclosure, known-payload fingerprinting, field-count/parse-state side channels; not anonymity, DP, or absolute privacy",
        },
        "live_observability": {
            "isolated_actual_HTTP_to_datagram_to_candidate_worker": "VERIFIED",
            "old_receipts_replayed_not_new_GT": len(rows),
            "tensor_parity": len(rows),
            "unchanged_body_path_headers": len(rows),
            "unsupported_transport_cases": unsupported_results,
            "deliberate_extractor_worker_failures_fail_open": ingress.dropped,
            "extractor_disabled_application_OK": True,
            "nominal_telemetry_drops": 0,
            "nominal_events_sent": nominal_sent,
            "max_prefix_bytes": ingress.max_prefix,
            "production": "NOT_READY",
            "origin": "No-log HTTP byte/header witness, not DVWA/Student application-state execution",
            "scope": "Loopback HTTP/1.1, <=1MiB transport budget, no TLS/Expect100/pipelining qualification; no existing correlation or route changed",
        },
        "performance": {
            "extract_CPU_ms_with_tracemalloc_p50_p95_max": np.quantile(
                cpu_times, [0.5, 0.95, 1]
            ).tolist(),
            "peak_traced_extract_allocations_bytes": max(peak_allocations),
            "live_replay_end_to_end_ms_p50_p95_max": np.quantile(
                latencies, [0.5, 0.95, 1]
            ).tolist(),
            "extraction_disabled_proxy_ms_p50_p95": np.quantile(direct, [0.5, 0.95]).tolist(),
            "extraction_enabled_proxy_ms_p50_p95": np.quantile(via, [0.5, 0.95]).tolist(),
            "scope": "Single host,25%oneCPU guarded run, tracing and scheduling overhead; not production throughput or hard real-time bound",
        },
        "claim": "Representation collision reduction only, no model Recall/FPR improvement claim",
        "training_started": False,
        "checkpoints_created": 0,
        "model_promotion": False,
        "prospective_opened": False,
        "formal_independent_review": "PENDING",
        "next_task": "One opt-in real ingress integration verification for the numeric body contract, including body-buffer/non-persistence canaries and actual candidate worker delivery; keep identity fields excluded and frozen path unchanged. No training before split/coverage re-audit.",
        "source_sha256": {
            str(Path(__file__).relative_to(ROOT)): file_sha256(__file__),
            **lock["source_sha256"],
        },
        "private_artifact_sha256": {
            str(p.relative_to(ROOT)): file_sha256(p) for p in output.rglob("*") if p.is_file()
        },
    }
    atomic_json(output / "report.json", result)
    atomic_json(ROOT / "ai-training/reports/BODY_SYNTAX_20261107.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "milestone_state",
                    "before",
                    "after",
                    "extraction_states",
                    "privacy",
                    "live_observability",
                    "performance",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--base", type=Path, required=True)
    args = a.parse_args()
    with threadpool_limits(limits=1):
        study(args.base.resolve())
