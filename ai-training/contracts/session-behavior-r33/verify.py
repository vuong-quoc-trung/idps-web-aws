"""Publish aggregate R33 evidence only after checking frozen inputs, runtime and cleanup."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256, load_json

HERE = Path(__file__).resolve().parent


def need(condition, message):
    if not condition:
        raise ValueError(message)


def cmd(*args):
    return subprocess.check_output(args, text=True).strip()


def verify(run):
    snapshots = load_json(run / "before.json")
    need(cmd("git", "branch", "--show-current") == snapshots["branch"], "branch changed")
    dirty = {p: file_sha256(REPO_ROOT / p) for p in snapshots["dirty"]}
    need(dirty == snapshots["dirty"], "existing worktree changed")
    svcs = [
        cmd(
            "systemctl",
            "--user",
            "show",
            f"idps-r22-local-{r}.service",
            "-p",
            "Id",
            "-p",
            "ActiveState",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
        )
        for r in ("ri", "scorer", "collector", "receiver")
    ]
    need(svcs == snapshots["services"], "Local service changed")
    frozen = load_json(run / "reconciled/frozen.json")
    for f, digest in frozen["code"].items():
        need(file_sha256(HERE / f) == digest, "frozen implementation changed")
    need(file_sha256(HERE / "protocol.json") == frozen["protocol_sha"], "protocol changed")
    fit = load_json(run / "reconciled/fit-result.json")
    holds = load_json(run / "reconciled/transfer.json")
    need(
        holds["frozen_sha"] == file_sha256(run / "reconciled/frozen.json"),
        "unbound transfer result",
    )
    need(
        file_sha256(run / "reconciled/fit-result.json") == frozen["fit_report_sha"],
        "tuning result changed",
    )
    prior = load_json(run / "frozen.json")
    need(
        all(prior[k] == frozen[k] for k in load_json(run / "relock-check.json")["unchanged"]),
        "training result drift",
    )
    local = load_json(run / "live.json")
    rows = local["evidence"]
    ready = [r for r in rows if r["score"] is not None]
    parity = load_json(run / "rust-parity.json")
    need(
        parity["model_sha"] == local["onnx_sha"] == file_sha256(run / "session-head.onnx"),
        "scorer digest",
    )
    baseline = load_json(HERE.parent / "information-r32/r32-evidence.json")["B16"]
    need(frozen["b16_sha"] == baseline["model_sha256"], "other B16 comparator")
    graph = load_json(run / "auth/assessment.json")
    need(
        graph["download_manifest_sha"] == file_sha256(run / "auth/download.json")
        and graph["reference_lock_sha"] == file_sha256(run / "auth/reference-lock.json"),
        "auth cohort or threshold changed",
    )
    need(
        local["owned_resources_clean"] and all(r["within_cutoff"] for r in rows),
        "probe cleanup or cutoff",
    )
    previous = load_json(run / "first-local-forensics.json")
    tests = ElementTree.parse(run / "final-tests.xml").getroot().find("testsuite").attrib
    need(int(tests["errors"]) + int(tests["failures"]) == 0, "regressions failed")
    safety = {}
    for path in sorted(run.glob("adapter-*")):
        res = load_json(path / "result.json")
        unit = load_json(path / "worker-launch.json")["unit"]
        state = load_json(path / "status.json")
        live = subprocess.run(
            ["systemctl", "--user", "is-active", unit], text=True, capture_output=True
        ).stdout.strip()
        group = Path("/sys/fs/cgroup") / state["limits"]["path"].lstrip("/")
        need(
            res["cleanup_verified"]
            and not group.exists()
            and live in ("inactive", "unknown", "failed"),
            "live resource remains",
        )
        journal = subprocess.check_output(
            ["journalctl", "--user", "-u", unit, "--no-pager", "-o", "cat"]
        )
        (path / "journal.log").write_bytes(journal)
        safety[path.name] = {
            "reason": res["reason"],
            "exit_code": res.get("exit_proof", {}).get("exit_status"),
            "cleanup": True,
            "detail": res.get("detail"),
            "unit": unit,
            "worker_pid": load_json(path / "preflight.json")["worker_pid"],
            "cold_start_C": load_json(path / "cold-start-admission.json")["reading"][
                "temperature_C"
            ],
            "last_observed_C": state["temperature_c"],
            "last_kernel_cpu_max": state["limits"]["cpu.max"],
            "memory_max_bytes": int(state["limits"]["memory.max"]),
            "last_sample_memory_bytes": state["memory_bytes"],
        }
    need(
        all(
            safety[key]["reason"] == "COMPLETED"
            for key in (
                "adapter-fit",
                "adapter-relock",
                "adapter-transfer-reconciled",
                "adapter-local-drain",
                "adapter-auth-download",
                "adapter-graph-audit",
                "adapter-parity-serial",
            )
        ),
        "required phase incomplete",
    )
    replay = load_json(run / "graph-audit/replay.json")
    need(
        replay["equivalent_all_counts_cutoffs_scores"]
        and replay["original_assessment_sha"] == file_sha256(run / "auth/assessment.json")
        and replay["fresh_assessment_sha"] == file_sha256(run / "graph-audit/auth/assessment.json"),
        "auth replay mismatch",
    )
    scored = []
    with sqlite3.connect(
        (Path.home() / ".local/state/idps-r22-local/evidence.sqlite").as_uri() + "?mode=ro",
        uri=True,
    ) as db:
        for row in rows:
            raw, sha = db.execute(
                "SELECT payload,sha256 FROM evidence WHERE rid=?", (row["request_id"],)
            ).fetchone()
            need(
                sha == row["evidence_sha"] == hashlib.sha256(raw).hexdigest(),
                "Local receipt digest",
            )
            payload = json.loads(raw)
            need(
                payload["request_id"] == row["request_id"]
                and payload["r20"]["model_sha256"]
                == file_sha256(Path.home() / ".local/state/idps-r22-local/bundle/swiglu.onnx"),
                "Local model binding",
            )
            scored.append(
                {
                    "request_id": row["request_id"],
                    "ri_score": payload["ri_v2"]["score"],
                    "r20_score": payload["r20"]["score"],
                    "ri_manifest": payload["ri_v2"]["manifest_sha256"],
                    "rule_available": payload["rule"] is not None,
                    "hybrid_available": payload["hybrid"] is not None,
                }
            )
    atomic_json(run / "common-local.json", scored)
    files = {}
    for f in sorted(run.rglob("*")):
        rel = f.relative_to(run)
        if (
            not f.is_file()
            or rel.parts[0] == "cargo"
            or f.name in ("artifact-index.json", "git-push.json")
        ):
            continue
        files[str(rel)] = file_sha256(f)
    atomic_json(run / "artifact-index.json", files)

    def q(values):
        return np.quantile(values, [0.5, 0.95]).tolist()

    case = frozen["selected"]
    all_docs = holds["arms"][case]["all"]["n"] + holds["availability"]["unresolved_document_rows"]
    published = {
        "version": "r33-research-evidence-v1",
        "decision": "RESEARCH_COMPLETE_RELEASE_BLOCKED",
        "run": run.name,
        "start_head": snapshots["head"],
        "previous_dirty_verified": len(dirty),
        "services": svcs,
        "deployment": {
            "default": "RI v2",
            "shadow": "R20",
            "R20_onnx": file_sha256(Path.home() / ".local/state/idps-r22-local/bundle/swiglu.onnx"),
            "B16_research": frozen["b16_sha"],
            "new_enforcement": False,
        },
        "publisher": {
            "task": "author-annotated automation versus human navigation, noncommercial research",
            "archive_sha": load_json(HERE / "protocol.json")["archive_sha256"],
            "protocol_sha": frozen["protocol_sha"],
            "family_counts_fit_tune": fit["annotated_classes"],
            "fit_requests": fit["fit_scored"],
            "fit_sessions_scored": fit["fit_sessions_scored"],
            "tuning_sessions": fit["tuning_sessions"],
            "selected": case,
            "cutoff_strict": frozen["arms"][case]["cutoff_strict"],
            "fit_census": fit["census_fit"],
            "tuning": {k: v["common"] for k, v in fit["arms"].items()},
            "cross_phase": holds,
            "n_including_unresolved": all_docs,
            "score_coverage_including_unresolved": holds["availability"]["AVAILABLE"] / all_docs,
            "model_checkpoint_sha": holds["frozen_sha"],
        },
        "local": {
            "actual_HTTP_attempts": len(previous["records"]) + len(rows),
            "first_RI_joined": sum(v["ri"] == "SCORED" for v in previous["records"]),
            "final_HTTP": len(rows),
            "same_request_rule_and_hybrid_available": sum(
                r["rule_available"] and r["hybrid_available"] for r in scored
            ),
            "all_request_ids_distinct": len({r["request_id"] for r in rows + previous["records"]})
            == len(rows) + len(previous["records"]),
            "final_RI_and_R20_SCORED": sum(r["ri"] == r["r20"] == "SCORED" for r in rows),
            "history_status": dict(Counter(r["reason"] for r in rows)),
            "same_URI_anchor_scores": [r["score"] for r in ready[:2]],
            "availability_ms_p50_p95": q([(r["available_ns"] - r["sent_ns"]) / 1e6 for r in ready]),
            "HTTP_ms_p50_p95": q([r["http_ms"] for r in rows]),
            "inference_ms_p50_p95": q(
                [(r["available_ns"] - r["projected_ns"]) / 1e6 for r in ready]
            ),
            "native_NSA_proofs": 0,
            "source_profile": "owned NGINX+session backend, R22 request mirror; native mask unavailable",
            "ONNX_SHA": local["onnx_sha"],
            "onnx_python_max_abs": max(r["onnx_python_error"] for r in ready),
            "rust": parity,
        },
        "LANL": graph,
        "LANL_replay": replay,
        "native": {
            "ATTACK_VERIFIED_added": 0,
            "formal_TRAIN_DEV_CAL_FIT_CAL_OP_TEST": [0, 0, 0, 0, 0],
            "T07_quality_gate": "BLOCKED",
        },
        "safety": safety,
        "tests": {k: tests[k] for k in ("tests", "errors", "failures", "skipped")},
        "private_artifact_index": {
            "path": str((run / "artifact-index.json").relative_to(REPO_ROOT)),
            "sha256": file_sha256(run / "artifact-index.json"),
            "entries": len(files),
        },
    }
    need(
        published["local"]["all_request_ids_distinct"] and len(ready) == 6,
        "local duplicate or coverage discrepancy",
    )
    atomic_json(HERE / "r33-evidence.json", published)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    verify(parser.parse_args().run.resolve())
