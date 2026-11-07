#!/usr/bin/env python3
"""Finite DVWA security-setting preflight and calibration, isolated from evaluation."""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

from idps_ai.common import atomic_json, digest, file_sha256

ROOT = Path(__file__).resolve().parents[2]
RUN = "final-calibration-20261107-v1"
PORT, PROXY = 17280, 17281
LABEL = "idps.research-run=" + RUN


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def helper():
    q = module("quality-lab-cohort")
    q.RUN = RUN
    q.LABEL = LABEL
    return q


def token(page):
    m = re.search(rb'name=[\'"]user_token[\'"]\s+value=[\'"]([^\'"]+)', page)
    return m[1].decode() if m else None


def selected(page):
    # Match the selected option, not a status code or reflected submitted string.
    m = re.search(rb'<option\s+value=[\'"]([^\'"]+)[\'"][^>]*selected[^>]*>', page, re.I)
    if not m:
        m = re.search(rb'<option\s+selected[^>]*value=[\'"]([^\'"]+)[\'"]', page, re.I)
    return m[1].decode() if m else None


def run(command, root, preflight):
    os.umask(0o077)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    q = helper()
    d = module("p0-dvwa-capture")
    d.PORT = PORT
    d.PROXY_PORT = PROXY
    d.APP = RUN + "-app"
    d.DB = RUN + "-db"
    d.NET = RUN + "-net"
    original = d.Session

    class Session(original):
        def call(self, method, path, body="", extra=None, port=PORT):
            return super().call(method, path, body, extra, port)

    d.Session = Session
    if command == "capture":
        proof = json.loads((preflight / "preflight.json").read_text())
        plan = json.loads((preflight / "cohort-plan.json").read_text())
        assert proof["status"] == "PASS" and plan["source_sha256"] == file_sha256(__file__)
        assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
        (root / "cohort-plan.json").write_bytes((preflight / "cohort-plan.json").read_bytes())
    else:
        plan = {"targets": ["medium", "low"], "role": "PREFLIGHT_ONLY"}
    assert not q.owned(), "Owned lab already exists"
    (root / "heartbeat").touch()
    stop = threading.Event()

    def beat():
        while not stop.wait(0.2):
            (root / "heartbeat").touch()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    unit = "idps-" + RUN + "-" + root.name + "-watchdog"
    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--quiet",
            "--unit",
            unit,
            "--service-type=exec",
            "-p",
            "CPUQuota=10%",
            "-p",
            "MemoryMax=128M",
            "-p",
            "RuntimeMaxSec=600",
            "--setenv",
            "PATH=" + os.environ["PATH"],
            sys.executable,
            str(Path(__file__).resolve()),
            "watchdog",
            "--output",
            str(root),
        ],
        check=True,
        capture_output=True,
    )
    server = None
    owned = []
    network = False
    try:
        until = time.monotonic() + 8
        while not (root / "watchdog-ready").exists() and time.monotonic() < until:
            time.sleep(0.1)
        assert (root / "watchdog-ready").exists() and not (
            root / "lab-watchdog-result.json"
        ).exists()
        q.pm("network", "create", "--internal", "--label", LABEL, d.NET)
        network = True
        for name, image, port, extra in [
            (
                d.DB,
                d.DB_IMAGE,
                None,
                [
                    "--network-alias",
                    "db",
                    "-e",
                    "MYSQL_ROOT_PASSWORD=dvwa",
                    "-e",
                    "MYSQL_DATABASE=dvwa",
                    "-e",
                    "MYSQL_USER=dvwa",
                    "-e",
                    "MYSQL_PASSWORD=p@ssw0rd",
                ],
            ),
            (d.APP, d.APP_IMAGE, "80", ["-p", f"127.0.0.1:{PORT}:80", "-e", "DB_SERVER=db"]),
        ]:
            q.pm("image", "inspect", image)
            q.pm(
                "run",
                "-d",
                "--name",
                name,
                "--label",
                LABEL,
                "--network",
                d.NET,
                "--cpus=.5",
                "--memory=1g",
                "--memory-swap=1g",
                "--pids-limit=128",
                "--security-opt=no-new-privileges",
                *extra,
                image,
            )
            owned.append(name)
        info = json.loads(q.pm("inspect", d.APP))[0]
        net = json.loads(q.pm("network", "inspect", d.NET))[0]
        assert net["internal"] and info["NetworkSettings"]["Ports"]["80/tcp"] == [
            {"HostIp": "127.0.0.1", "HostPort": str(PORT)}
        ]
        atomic_json(
            root / "identity.json",
            {
                "image_id": info["Image"],
                "pinned_image": d.APP_IMAGE,
                "pinned_DB": d.DB_IMAGE,
                "internal_network": True,
                "loopback_port": PORT,
                "container_id": info["Id"],
                "no_extra_capabilities": True,
            },
        )
        src = q.pm("exec", d.APP, "cat", "/var/www/html/security.php")
        (root / "security-source.php").write_text(src)
        if command == "preflight":
            # Source-driven form contract; no fallback to GET for a POST workflow.
            assert "$_POST" in src and "seclev_submit" in src and "user_token" in src
        else:
            assert file_sha256(root / "security-source.php") == plan["application_source_sha256"]
        ss = d.Session(root / "setup")
        d.initialize(ss)
        d.Gateway.output = root / "receipts"
        d.Gateway.output.mkdir(mode=0o700)
        d.Gateway.receipts = {}
        d.Gateway.allowed_ids = set()
        server = d.ThreadingHTTPServer(("127.0.0.1", PROXY), d.Gateway)
        relay = threading.Thread(target=server.serve_forever, daemon=True)
        relay.start()
        sequence = 0
        all_transactions = []

        def call(method, path, body="", study=False):
            nonlocal sequence
            assert not (root / "lab-watchdog-result.json").exists()
            sequence += 1
            rid = digest([RUN, command, sequence])[:32]
            d.Gateway.allowed_ids.add(rid)
            h = {
                "X-Request-Id": rid,
                "User-Agent": "Mozilla/5.0 LabResearch",
                "Accept": "text/html",
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "; ".join(f"{k}={v}" for k, v in ss.cookies.items()),
            }
            status, returned, page = d.low_http(PROXY, method, path, body.encode(), h)
            assert rid in d.Gateway.receipts
            from http.cookies import SimpleCookie

            for name, value in returned:
                if name.lower() == "set-cookie":
                    cookie = SimpleCookie()
                    cookie.load(value)
                    ss.cookies.update({k: v.value for k, v in cookie.items()})
            all_transactions.append(
                {
                    "request_id": rid,
                    "method": method,
                    "path": path,
                    "study": study,
                    "receipt_sha256": file_sha256(root / "receipts" / rid / "receipt.json"),
                }
            )
            return rid, status, returned, page

        records = []
        for target in plan["targets"]:
            before_id, bs, _, before = call("GET", "/security.php")
            csrf = token(before)
            before_level = selected(before)
            assert bs == 200 and csrf and before_level is not None
            fields = {"security": target, "seclev_submit": "Submit", "user_token": csrf}
            body = urlencode(fields)
            rid, status, returned, _ = call("POST", "/security.php", body, command == "capture")
            after_id, after_status, _, after = call("GET", "/security.php")
            # Both a response cookie and a read-after-write page are required.
            security_cookie = any(
                k.lower() == "set-cookie"
                and re.search(r"(?:^|;)\s*security=" + re.escape(target) + r"(?:;|$)", v)
                for k, v in returned
            )
            matched = (
                security_cookie
                and ss.cookies.get("security") == target
                and after_status == 200
                and selected(after) == target
                and before_level != target
            )
            records.append(
                {
                    "request_id": rid,
                    "role": "CALIBRATION" if command == "capture" else "PREFLIGHT_ONLY",
                    "workflow": "dvwa-security-setting",
                    "campaign": RUN + ":security-setting",
                    "intent": "BENIGN" if matched else "UNKNOWN",
                    "oracle": "CSRF-bound POST changes security cookie AND next authenticated page selected state",
                    "semantic_oracle_matched": bool(matched),
                    "target": target,
                    "before_level": before_level,
                    "post_status": status,
                    "before_request_id": before_id,
                    "after_request_id": after_id,
                    "csrf_sha256": digest(csrf),
                    "body_sha256": digest(body),
                    "session_digest": digest(ss.cookies.get("PHPSESSID", "")),
                    "review": "PENDING",
                    "independent_human_verified": False,
                }
            )
            atomic_json(
                root / "progress.json", {"records": records, "transactions": all_transactions}
            )
        import numpy as np

        from idps_ai.features.research_request_channels import encode
        from idps_ai.mvp_inference import ResearchMVP

        pv = module("p0-request-evaluate")
        uc = module("training-unblock-cohort")
        frozen = ResearchMVP("request-v2", cpus=1)
        vectors = []
        base_vectors = []
        keys = []
        for r in records:
            b = root / "receipts" / r["request_id"]
            h = json.loads((b / "request-headers.json").read_text())
            req = {
                "method": "POST",
                "url": "/security.php",
                "body": (b / "request-body.bin").read_text(),
                "headers": "\r\n".join(f"{k}: {v}" for k, v in h.items()),
            }
            k, _ = uc.keys(req, frozen, pv)
            keys.append(k)
            vectors.append(encode(req))
            base_vectors.append(pv.vector(frozen, req)[0])
        candidate_unique = len({v.tobytes() for v in vectors})
        frozen_unique = len({v.tobytes() for v in base_vectors})
        exclusion = json.loads(
            (
                ROOT
                / "ai-training/.artifacts/training_unblock_20261107/campaign-capture-v2/preflight.json"
            ).read_text()
        )
        # Read only the precommitted exclusion keys, not sealed evaluation records/features/labels.
        prior = {
            name: {r["keys"][name] for r in exclusion["rows"]}
            for name in ["raw", "template", "rich", "view"]
        }
        overlap = [any(k[name] in prior[name] for name in prior) for k in keys]
        passed = (
            all(r["semantic_oracle_matched"] for r in records)
            and candidate_unique >= 2
            and not any(overlap)
        )
        report = {
            "status": "PASS" if passed else "FAIL",
            "command": command,
            "records": records,
            "transactions": all_transactions,
            "candidate_unique_views": candidate_unique,
            "frozen_unique_views": frozen_unique,
            "prior_identifier_template_view_overlap": any(overlap),
            "prospective_content_opened": False,
            "prospective_scores_computed": 0,
            "source_sha256": file_sha256(__file__),
            "application_source_sha256": file_sha256(root / "security-source.php"),
        }
        if command == "capture":
            np.savez(
                root / "calibration-addendum.npz",
                x=np.array(vectors),
                baseline=np.array(base_vectors),
                y=np.zeros(len(records), np.int64),
                ids=np.array([r["request_id"] for r in records]),
                groups=np.repeat(10000, len(records)),
            )
            report["feature_file_sha256"] = file_sha256(root / "calibration-addendum.npz")
        atomic_json(root / ("preflight.json" if command == "preflight" else "capture.json"), report)
        if command == "preflight" and passed:
            plan = {
                "schema_version": "calibration-addendum-plan-1",
                "run_id": RUN,
                "role": "CALIBRATION",
                "targets": ["medium", "low"],
                "method": "POST",
                "path": "/security.php",
                "workflow": "dvwa-security-setting",
                "cases": 2,
                "source_sha256": file_sha256(__file__),
                "application_source_sha256": report["application_source_sha256"],
                "preflight_report_sha256": file_sha256(root / "preflight.json"),
                "csrf_binding": "token from separately receipted immediately preceding authenticated GET",
                "Oracle": records[0]["oracle"],
                "minimum_candidate_views": 2,
                "old_UNKNOWN_unchanged": True,
                "no_role_reassignment": True,
                "no_prospective_peek": True,
                "quality_claim": "Internal Oracle calibration only; not evaluation or independent review",
            }
            plan["fingerprint"] = digest(plan)
            atomic_json(root / "cohort-plan.json", plan)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in [
                        "status",
                        "command",
                        "candidate_unique_views",
                        "frozen_unique_views",
                        "prior_identifier_template_view_overlap",
                        "prospective_content_opened",
                        "prospective_scores_computed",
                    ]
                }
            )
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()
        for name in reversed(owned):
            q.remove_finished_container(name, root / (name + "-cleanup.json"))
        if network:
            q.pm("network", "rm", d.NET)
        stop.set()
        thread.join(timeout=2)
        (root / "watchdog-done").touch()
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
        atomic_json(
            root / "cleanup.json",
            {"owned_containers_remaining": len(q.owned()), "watchdog_stopped": True},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["preflight", "capture", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--preflight", type=Path)
    a = p.parse_args()
    if a.command == "watchdog":
        helper().watchdog(a.output.resolve())
    else:
        run(a.command, a.output.resolve(), a.preflight.resolve() if a.preflight else None)
