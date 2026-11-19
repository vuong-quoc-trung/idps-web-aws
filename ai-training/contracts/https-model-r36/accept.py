"""Run the default Local HTTPS scorer and normal Rust ingestion/Hybrid workers on a disposable DB."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import secrets
import signal
import re
import subprocess as sp
import sys
import tempfile
import time
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def cmd(args, **kw):
    return sp.run(args, check=True, capture_output=True, timeout=60, **kw).stdout


def wait(check, proc, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise RuntimeError("Owned process exited before readiness")
        if check():
            return
        time.sleep(0.2)
    raise RuntimeError("Readiness deadline")


def stop(proc, graceful=False):
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT if graceful else signal.SIGTERM)
        try:
            proc.wait(timeout=12)
        except sp.TimeoutExpired:
            proc.kill()
            proc.wait()


def run(a):
    os.umask(0o077)
    if a.out.exists():
        raise ValueError("Use a fresh run directory")
    a.out.mkdir()
    from serve import SLOT_ROOT

    slots = json.loads((SLOT_ROOT / "slots.json").read_text())
    previous = a.asset_root / "ai-training/.artifacts/t09-r35-HXrqHh86"
    pg = a.pg / "usr/lib/postgresql/18/bin"
    with (
        tempfile.TemporaryDirectory(prefix="idps-r36-") as scratch,
        contextlib.ExitStack() as cleanup,
    ):
        w = Path(scratch)
        delivery = w / "delivery"
        delivery.mkdir(mode=0o700)
        # nginx can chown its temp dirs to a subordinate UID. Dispose the private
        # delivery tree in its owner namespace after the two host processes exit.
        cleanup.callback(
            cmd,
            [
                "podman",
                "unshare",
                sys.executable,
                "-B",
                "-c",
                "import shutil,sys; shutil.rmtree(sys.argv[1])",
                str(delivery),
            ],
        )
        cmd(
            [
                pg / "initdb",
                "-D",
                w / "db",
                "-U",
                "postgres",
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
                "-L",
                a.pg / "usr/share/postgresql/18",
            ]
        )

        def spawn(name, args, env):
            f = cleanup.enter_context((w / (name + ".log")).open("wb"))
            p = sp.Popen(args, cwd=w, stdout=f, stderr=f, env=env)
            cleanup.callback(stop, p, name == "backend")
            return p

        # Peer DB transport is a mode-0700 private Unix directory; no TCP listener.
        db = spawn(
            "db",
            [
                pg / "postgres",
                "-D",
                w / "db",
                "-k",
                w,
                "-c",
                "listen_addresses=",
                "-c",
                "shared_buffers=16MB",
                "-c",
                "max_connections=30",
                "-c",
                "jit=off",
            ],
            os.environ.copy(),
        )
        psql = [
            pg / "psql",
            "-XAt",
            "-h",
            w,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
        ]

        def sql(q):
            return cmd(psql + [q]).decode().strip()

        wait(lambda: (w / ".s.PGSQL.5432").exists(), db, 10)
        lab = a.out / "live"
        key = (
            cmd([a.server, "--hash-password"], input=secrets.token_hex(24).encode())
            .decode()
            .strip()
        )
        env = {
            k: os.environ[k] for k in ["PATH", "HOME", "LANG", "LD_LIBRARY_PATH"] if k in os.environ
        }
        env.update(
            DATABASE_URL="postgresql://postgres@localhost/postgres?host=" + quote(str(w), safe=""),
            ADMIN_PASSWORD_HASH=key,
            APP_ADDR="127.0.0.1:0",
            ENFORCEMENT_MODE="OFF",
            AUTO_BLOCK="false",
            PBL4_FIREWALL_CMD="/bin/false",
            COLLECT_ALL_EVENTS="true",
            SECURITY_SENSOR_ID="local-r36",
            NGINX_ACCESS_PATH=str(delivery / "access"),
            STUDENT_AUDIT_LOG_PATH=str(delivery / "audit.jsonl"),
            SURICATA_EVE_PATH=str(delivery / "eve.json"),
            AI_HTTPS_RESULTS_PATH=str(lab / "https-research.jsonl"),
            SURICATA_CAPTURE_MODE="post-proxy",
            SURICATA_POST_PROXY_INTERFACE="lo",
            SURICATA_PROXY_IP="127.77.0.1",
            SURICATA_WEB_IP="127.77.0.2",
            SURICATA_WEB_PORT="18080",
            SURICATA_EVE_GENERATION_HOST="true",
            TOKIO_WORKER_THREADS="1",
        )
        backend = spawn("backend", [a.server], env)
        try:
            wait(
                lambda: sql("select to_regclass('https_research_observations') is not null") == "t",
                backend,
                15,
            )
            args = [
                "podman",
                "unshare",
                "unshare",
                "-n",
                sys.executable,
                "-B",
                HERE.parent / "https-shadow-r35/live.py",
                "--output",
                lab,
                "--delivery",
                delivery,
                "--nginx",
                previous / "pkg/root/usr/sbin/nginx",
                "--module",
                previous / "pkg/root/usr/lib/nginx/modules/ngx_http_js_module.so",
                "--student",
                a.asset_root / "student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar",
                "--h2",
                Path.home() / ".m2/repository/com/h2database/h2/2.4.240/h2-2.4.240.jar",
                "--sensor-prefix",
                a.asset_root / ".local-dev/suricata-runtime",
                "--ort",
                a.ort,
                "--scorer",
                a.scorer,
                "--proof-binary",
                a.proof,
                "--owner-uid",
                str(os.getuid()),
                "--host-netns",
                os.readlink("/proc/self/ns/net"),
            ]
            sp.run(args, check=True, timeout=180)
            live = json.loads((lab / "live.json").read_text())
            roster = live["requests"]
            q = "SELECT decision FROM hybrid_incidents WHERE decision->'https_research'->>'status'='SCORED'"
            wait(lambda: int(sql("SELECT count(*) FROM (" + q + ") d")) == len(roster), backend, 20)
            decisions = [json.loads(l) for l in sql(q).splitlines()]
            journal = {
                r["request_id"]: r
                for r in map(json.loads, (lab / "https-research.jsonl").read_text().splitlines())
            }
            summary = []
            for row in decisions:
                rid = row["request_id"]
                observation = row["ai"]
                assert observation == row["https_research"] and rid == observation["request_id"]
                assert not row["automatic_block"] and row["policy_action"] in (
                    "LOG_ONLY",
                    "ALERT",
                    "REVIEW",
                )
                assert (
                    observation["model_sha256"]
                    == roster[rid]["model_sha256"]
                    == journal[rid]["model_sha256"]
                )
                assert (
                    abs(observation["score"] - roster[rid]["score"]) < 1e-6
                    and not observation["enforcement"]
                )
                summary.append(
                    dict(
                        request_id=rid,
                        model=observation["model_id"],
                        model_sha256=observation["model_sha256"],
                        observation=observation["action"],
                        policy=row["policy_action"],
                        score=observation["score"],
                    )
                )
            assert {r["request_id"] for r in summary} == set(roster) == set(journal)
            assert sum(r["model"] == slots["slots"]["candidate"]["version"] for r in summary) == 5
            assert decisions and journal[list(roster)[3]]["version"] == slots["slots"]["rollback"]["version"]
            assert sql("select count(*) from hybrid_proposals") == "0"
            assert sql("select count(*) from https_research_observations where conflicted") == "0"
            errors = sql("select count(*) from ingestion_errors where source='HTTPS_RESEARCH'")
            assert errors == "0"
            (a.out / "hybrid.json").write_text(
                json.dumps(
                    dict(
                        mode="LIVE_BACKEND_FILE_INGEST_POSTGRES_HYBRID",
                        decisions=summary,
                        proposals=0,
                        research_ingestion_errors=0,
                    ),
                    indent=2,
                )
                + "\n"
            )
            regression = {}
            for pattern in [
                "c2_",
                "c3_",
                "r36_pinned_request_time",
                "restore_does_not_override_pending_unblock",
            ]:
                checks = sp.run(
                    [a.proof, pattern, "--test-threads=1"],
                    cwd=w,
                    env=env,
                    capture_output=True,
                    timeout=90,
                )
                hits = sum(
                    int(n) for n in re.findall(rb"test result: ok[.] (\d+) passed", checks.stdout)
                )
                if checks.returncode or not hits:
                    raise RuntimeError(f"Isolated regression failed: {pattern}; executed={hits}")
                regression[pattern] = hits
            (a.out / "regression.json").write_text(json.dumps(regression, indent=2) + "\n")
        except Exception:
            # Keep diagnostics private and never export DB URL, raw telemetry, cookies or credentials.
            print(
                "backend_alive",
                backend.poll() is None,
                "migrated",
                sql("select to_regclass('https_research_observations') is not null"),
                flush=True,
            )
            if backend.poll() is not None:
                print(
                    "backend_error",
                    (w / "backend.log").read_text()[-250:].replace(str(w), "[lab]"),
                    flush=True,
                )
            raise
    (a.out / "cleanup.json").write_text(
        json.dumps(
            dict(
                db_exit=db.poll(),
                backend_exit=backend.poll(),
                scratch_removed=not w.exists(),
                http_replay_on_restart=False,
            )
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ["pg", "out", "asset-root", "server", "scorer", "proof", "ort"]:
        p.add_argument("--" + k, type=Path, required=True)
    run(p.parse_args())
