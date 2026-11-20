"""Check one crash and recovery of the owned R38 single-user staging unit."""

import argparse
import hashlib
import http.client
import json
import os
import pathlib
import signal
import socket
import sqlite3
import subprocess
import time
from contextlib import closing

unit = "idps-r38-https-scorer.service"
sock = pathlib.Path(os.environ["XDG_RUNTIME_DIR"]) / "idps-r38-https/receiver.sock"


def props():
    cmd = ["systemctl", "--user", "show", unit]
    keys = "ActiveState SubState MainPID InvocationID NRestarts ControlGroup UnitFileState MemoryCurrent".split()
    data = subprocess.check_output(cmd + ["--property=" + ",".join(keys)], text=True)
    return dict(line.split("=", 1) for line in data.splitlines())


def health():
    t = time.monotonic()
    with closing(socket.socket(socket.AF_UNIX)) as s:
        s.settimeout(1.5)
        s.connect(str(sock))
        s.sendall(b"GET /healthz HTTP/1.0\r\n\r\n")
        res = http.client.HTTPResponse(s)
        res.begin()
        res.read()
        assert (
            res.status == 200
            and res.getheader("X-Model-SHA256")
            == "91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff"
        )
        return round((time.monotonic() - t) * 1000, 3)


def count():
    db = pathlib.Path.home() / ".local/state/idps-r38-https/private/receipts.db"
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as c:
        assert c.execute("pragma quick_check").fetchone() == ("ok",)
        return c.execute("select count(*) from receipts").fetchone()[0]


def run():
    a = props()
    assert a["SubState"] == "running" and a["UnitFileState"] == "enabled"
    warm = [health() for _ in range(8)]
    before = count()
    cg = pathlib.Path("/sys/fs/cgroup" + a["ControlGroup"]) / "ai-worker"
    pids = [int(x) for x in (cg / "cgroup.procs").read_text().split()]

    def receiver(pid):
        args = pathlib.Path("/proc") / str(pid) / "cmdline"
        return any(
            v.endswith(b"/ai-training/contracts/https-model-r36/serve.py")
            for v in args.read_bytes().split(b"\0")
        )

    (p,) = [p for p in pids if receiver(p)]
    args = pathlib.Path("/proc", str(p), "cmdline").read_bytes().split(b"\0")
    (serve,) = [
        pathlib.Path(os.fsdecode(val))
        for val in args
        if val.endswith(b"/ai-training/contracts/https-model-r36/serve.py")
    ]
    root = serve.parents[3]
    base = pathlib.Path.home() / ".local/share/websentinel/releases"
    if root.parent != base or root.resolve() != root:
        raise ValueError("Receiver outside owned R38 release")
    release_pin = hashlib.sha256((root / "files.json").read_bytes()).hexdigest()
    settings = subprocess.check_output(
        ["systemctl", "--user", "show", unit, "-p", "Environment", "--value"], text=True
    ).split()
    if not {"SINGLE_USER_STAGING=1", "RELEASE_SHA256=" + release_pin} <= set(settings):
        raise ValueError("The unit is not the pinned single-user stage")
    start = time.monotonic()
    with closing(os.fdopen(os.pidfd_open(p), "rb", buffering=0)) as handle:
        assert (
            str(p) in (cg / "cgroup.procs").read_text().split()
            and receiver(p)
            and props()["InvocationID"] == a["InvocationID"]
        )
        signal.pidfd_send_signal(handle.fileno(), signal.SIGKILL)
    end = start + 13
    while time.monotonic() < end:
        b = props()
        if b["SubState"] == "running" and b["InvocationID"] != a["InvocationID"]:
            try:
                cold = health()
                break
            except (OSError, AssertionError, http.client.HTTPException):
                pass
        time.sleep(0.1)
    else:
        raise RuntimeError("no healthy restarted worker")
    after = count()
    assert before == after and int(b["NRestarts"]) == int(a["NRestarts"]) + 1
    assert all(not pathlib.Path("/proc", str(pid)).exists() for pid in pids)
    e = dict(
        unit=unit,
        before=a,
        after=b,
        before_health_ms=warm,
        first_healthy_probe_after_crash_ms=cold,
        elapsed_to_recovery_ms=round((time.monotonic() - start) * 1000, 2),
        previous_worker_pids=pids,
        killed_receiver_pid=p,
        old_worker_pids_gone=True,
        receipts_before=before,
        receipts_after=after,
        quota={
            k: (cg / k).read_text().strip()
            for k in [
                "cpu.max",
                "memory.max",
                "memory.high",
                "memory.swap.max",
                "pids.max",
            ]
        },
        model_sha256="91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff",
        release_sha256=release_pin,
        linger=subprocess.check_output(
            ["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"],
            text=True,
        ).strip(),
        socket_mode=oct(sock.stat().st_mode & 0o777),
    )
    return e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    if args.output.exists() or not __debug__:
        parser.error("Require a new output path and enabled checks")
    evidence = run()
    with args.output.open("x") as f:
        f.write(json.dumps(evidence, indent=2) + "\n")
