"""One isolated 12-request authorization pair, using the existing KVM pipeline."""

# isort: skip_file

import argparse
import importlib.util
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

from common import HERE, PARENT, atomic_json, check, file_sha256, read
from idps_ai.common import REPO_ROOT, digest

spec = importlib.util.spec_from_file_location(
    "r261_authorized_base", HERE.parent / "native-authorized-control-v1/run.py"
)
r8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r8)
base = r8.base


def roster(index):
    check(index == 0, "Only one bounded native campaign")
    rows = []
    for account in ("admin", "student"):
        session = "r261-" + account
        for method, path, oracle, status, record in [
            ("GET", "/api/auth/csrf", "csrf", 200, None),
            ("POST", "/api/auth/login", "login-" + account, 204, None),
            ("GET", "/api/auth/me", "principal-" + account, 200, None),
            *[
                ("GET", f"/api/students/{i}", "record", 200 if account == "admin" else 403, i)
                for i in (113, 121, 128)
            ],
        ]:
            rows.append(
                {
                    "attempt": len(rows) + 1,
                    "method": method,
                    "path": path,
                    "target": path,
                    "expected_status": status,
                    "oracle": oracle,
                    "record": record,
                    "session": session,
                    "intent": "ATTACK_INTENT"
                    if oracle == "record" and account == "student"
                    else "BENIGN",
                }
            )
    return rows


def extend(root, pins):
    r8.extend(root, pins)
    target = root / "lab/authorization_oracle.py"
    from lab_auth import stage_guest_python

    stage_guest_python(HERE / "native_authorization.py", root, "/lab/authorization_oracle.py")
    check(
        file_sha256(target) == file_sha256(HERE / "native_authorization.py"),
        "Wrong guest authorization Oracle staged",
    )
    pins["/lab/authorization_oracle.py"] = file_sha256(target)
    base.unified.vm.copy_file(HERE / "lab_auth.py", root, "/lab/lab_auth.py")
    timing = root / "bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"
    text = base.replace_once(
        timing.read_text(),
        '                body = urllib.parse.urlencode({"username": "labu1", "password": self.password})',
        "                from lab_auth import login_username\n"
        '                body = urllib.parse.urlencode({"username": login_username(self.row["oracle"]), "password": self.password})',
    )
    timing.write_text(text)
    pins["/lab/lab_auth.py"] = file_sha256(root / "lab/lab_auth.py")
    pins["/bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"] = file_sha256(timing)
    shape = HERE.parent / "development-bulk-v1/r23_features.py"
    base.unified.vm.copy_file(shape, root, "/lab/r23_features.py")
    receiver = root / "lab/receiver.py"
    text = receiver.read_text()
    addition = """
    import numpy as np
    from r23_features import sketch, describe_lane
    def uri100_shape(target):
        path, query = sketch(target)
        values = np.minimum(31, describe_lane(path, b"/") + describe_lane(query, b"&")).astype(np.float32) / 31
        return {"version": "idps-r23-uri-shape24-v1", "values": values.tolist()}
"""
    text = base.replace_once(
        text, "    args = parser.parse_args()\n", "    args = parser.parse_args()\n" + addition
    )
    text = base.replace_once(
        text,
        "        args.socket, args.journal, model, args.rust_shadow_socket, args.representation_history\n",
        "        args.socket, args.journal, model, args.rust_shadow_socket, args.representation_history,\n        experimental_projector=uri100_shape\n",
    )
    receiver.write_text(text)
    acquire = root / "lab/acquire.py"
    insert = """                            projection = projections[0]
                            extension = projection["experimental_projection"]
                            vector100 = projection["vectors"] + extension["values"]
                            observed = projection["received_monotonic_ns"] - result["send_monotonic_ns"]
                            available = projection["available_monotonic_ns"] - result["send_monotonic_ns"]
                            result["uri100"] = {
                                "request_key": result["request_key"], "schema": "idps-uri100-raw-ascii-r26-v1",
                                "base_receipt_sha256": digest(result), "vector": vector100,
                                "vector_sha256": hashlib.sha256(struct.pack("<100f", *vector100)).hexdigest(),
                                "projection_available_offset_ns": available, "collector_receipt_offset_ns": observed,
                                "available_at_cutoff": 0 <= observed <= available <= result["cutoff_ns"] - result["clock_guard_ns"],
                                "feature_code_sha256": hashlib.sha256(Path("/lab/r23_features.py").read_bytes()).hexdigest(),
                                "scope": "TRUSTED_NGINX_MIRROR_REQUEST_TIME_ONLY"
                            }
"""
    text = base.replace_once(
        acquire.read_text(),
        '                            result["uri76"] = attach(result, projections[0], rid, boot)\n',
        insert
        + '                            result["uri76"] = attach(result, projections[0], rid, boot)\n',
    )
    acquire.write_text(text)
    for file in (receiver, acquire, root / "lab/r23_features.py"):
        pins["/" + str(file.relative_to(root))] = file_sha256(file)


def supervise(args):
    from idps_ai.training.checkpoint import RunLock

    out = args.output
    with RunLock(out):
        check(
            not (out / "checkpoint.json").exists(),
            "Native capture already attempted; never resend receipts",
        )
        rows = roster(0)
        policy = REPO_ROOT / "student-web/backend/src/main/java" / (r8.POLICY + ".java")
        jar = REPO_ROOT / "student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar"
        old = read(PARENT.parent / "t09-r8-authorized-20261117/plan.json")
        with zipfile.ZipFile(jar) as z:
            packaged = (
                __import__("hashlib")
                .sha256(z.read("BOOT-INF/classes/" + r8.POLICY + ".class"))
                .hexdigest()
            )
        check(
            file_sha256(policy) == old["policy_source_sha256"]
            and packaged == old["packaged_policy_sha256"],
            "Existing verified application policy changed",
        )
        plan = {
            "run_id": out.name,
            "rows": rows,
            "max_HTTP_attempts": 12,
            "scope": "ISOLATED_LOCAL_KVM_AUTHORIZATION_PAIR",
            "policy_source_sha256": file_sha256(policy),
            "packaged_policy_sha256": packaged,
            "oracle_sha256": file_sha256(HERE / "native_authorization.py"),
            "label_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "label_rule": "Independent Audit actor/session + principal/JDBC role + owner/policy + app Oracle; never runner intent or HTTP status alone",
            "role": "TRAIN_RESEARCH_CANDIDATE_QUARANTINED",
            "source_masks": "Actual cutoff 1000ms guard1ms, no fabricated source",
            "canonical_TRAIN": 0,
            "native_split": "One guest/session pair; no independent split claim",
        }
        atomic_json(out / "plan.json", plan)
        atomic_json(
            out / "checkpoint.json",
            {
                "state": "IN_PROGRESS",
                "binding": digest(plan),
                "committed": 0,
                "resend_committed": False,
            },
        )
        atomic_json(out / "status.json", {"state": "RUNNING", "phase": "CAPTURE", "planned": 12})
        began = time.monotonic()
        attempt, command = base.start(args, 0, 1)
        attempt.parent.mkdir(mode=0o700)
        command[command.index(str(Path(base.__file__).resolve()))] = str(Path(__file__).resolve())
        result = subprocess.run(command, check=False)
        return reconcile(args, result.returncode, time.monotonic() - began)


def reconcile(args, exit_code, elapsed):
    out = args.output
    attempt = out / "campaign-1-a1/adapter"
    plan = read(out / "plan.json")
    rows = plan["rows"]
    model = base.unified.ResearchModel(base.unified.MODELS)
    capture = base.verify(attempt, 0, model)
    # Base verifier's legacy 'benign' labels are not semantic labels for this run.
    capture.pop("labels", None)
    for row in capture.get("requests", []):
        row.pop("label", None)
    ledger = attempt / "guest/receipt-ledger.jsonl"
    records = (
        [
            r
            for line in ledger.read_text().splitlines()
            if (r := json.loads(line)).get("kind") == "ATTEMPT"
        ]
        if ledger.exists()
        else []
    )
    witnesses = [r["authorization_oracle"] for r in records if r.get("authorization_oracle")]
    from lab_auth import uri100 as python_uri100
    import numpy as np

    uri100_valid = 0
    for row in records:
        projected = row.get("uri100")
        if projected is None:
            continue
        vector = np.asarray(projected["vector"], np.float32)
        expected = python_uri100(
            rows[row["attempt"] - 1]["target"], rows[row["attempt"] - 1]["method"]
        )
        check(
            vector.tobytes() == expected.tobytes()
            and projected["request_key"] == row["request_key"]
            and projected["vector_sha256"]
            == __import__("hashlib").sha256(vector.tobytes()).hexdigest(),
            "Native URI100 dispatch parity or request binding failed",
        )
        uri100_valid += bool(projected["available_at_cutoff"])
    bykey = {r["request_key"]: r for r in records if r.get("request_key")}
    for proof in witnesses:
        row = bykey[proof["request_key"]]
        principal = bykey.get(proof["principal_request_key"], {})
        check(
            proof["sha256"] == digest({k: v for k, v in proof.items() if k != "sha256"})
            and row["oracle_verified"]
            and proof["actor_session_matches_principal"]
            and proof["owner_stable_before_after"]
            and (
                proof.get("resource_owner_differs_from_actor") is True
                or (
                    proof.get("label") == "BENIGN_VERIFIED"
                    and proof.get("policy") == "STUDENT_RECORD_READ_ADMIN"
                )
            )
            and principal.get("oracle_basis") == "PRINCIPAL_AND_JDBC_ROLE"
            and any(
                e["source"] == "A" and e["proof_sha256"] == proof["target_audit_proof_sha256"]
                for e in row["events"]
            )
            and any(
                e["source"] == "A" and e["proof_sha256"] == proof["principal_audit_proof_sha256"]
                for e in principal.get("events", [])
            ),
            "Host semantic witness reconciliation failed",
        )
    labels = {
        label: sum(w["label"] == label for w in witnesses)
        for label in ("BENIGN_VERIFIED", "ATTACK_VERIFIED")
    }
    passed = (
        exit_code == 0
        and capture["state"] == "PASS"
        and uri100_valid == 12
        and labels == {"BENIGN_VERIFIED": 3, "ATTACK_VERIFIED": 3}
    )
    summary = {
        "state": "PASS" if passed else "BLOCKED",
        "campaign": out.name,
        "adapter_exit": exit_code,
        "capture": capture,
        "semantic_label_counts": labels,
        "witnesses": witnesses,
        "semantic_task": plan["label_task"],
        "human_review_attestation": False,
        "canonical_TRAIN": 0,
        "URI100_views_at_cutoff": uri100_valid,
        "URI100_unique": len({r["uri100"]["vector_sha256"] for r in records if r.get("uri100")}),
        "URI100_mixed_task_vectors": len(
            {
                row["uri100"]["vector_sha256"]
                for row in records
                if row.get("authorization_oracle", {}).get("label") == "BENIGN_VERIFIED"
            }
            & {
                row["uri100"]["vector_sha256"]
                for row in records
                if row.get("authorization_oracle", {}).get("label") == "ATTACK_VERIFIED"
            }
        ),
        "native_TRAIN_DEV_CAL_TEST": [0, 0, 0, 0],
        "elapsed_seconds": elapsed,
        "no_training_or_threshold_change_from_native_results": True,
    }
    atomic_json(out / "summary.json", summary)
    atomic_json(
        out / "checkpoint.json",
        {
            "state": summary["state"],
            "binding": digest(plan),
            "committed": len(records),
            "ledger_sha256": file_sha256(ledger) if ledger.exists() else None,
            "resend_committed": False,
        },
    )
    atomic_json(
        out / "status.json",
        {
            "state": summary["state"],
            "completed": len(records),
            "planned": 12,
            "phase": "FINALIZED",
        },
    )
    return int(not passed)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("supervise", "worker", "reconcile"))
    for name in ("output", "iso", "h2", "numpy"):
        parser.add_argument(name, type=lambda p: Path(p).resolve(strict=True))
    parser.add_argument("--index", type=int, choices=(0,))
    parser.add_argument("--campaign")
    args = parser.parse_args()
    base.roster = roster
    base.extend = extend
    if args.action == "worker":
        code = base.worker(args)
    elif args.action == "reconcile":
        result = read(args.output / "campaign-1-a1/adapter/result.json")
        code = reconcile(args, 0 if result["reason"] == "COMPLETED" else 1, 0)
    else:
        code = supervise(args)
    raise SystemExit(code)
