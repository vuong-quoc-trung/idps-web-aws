"""Verify the packaged scorer with three mapped UIDs in a fresh rootless namespace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def run(release, owner, host_netns):
    if (
        owner <= 0
        or os.geteuid() != 0
        or Path("/proc/self/uid_map").read_text().split()[:2] != ["0", str(owner)]
        or os.readlink("/proc/self/ns/net") == host_netns
        or socket.if_nameindex() != [(1, "lo")]
    ):
        raise ValueError("An isolated rootless namespace is required")
    scorer, edge, observer = 201, 202, 203
    readers = 204
    with tempfile.TemporaryDirectory(prefix="r38-identities-") as directory:
        w = Path(directory)
        w.chmod(0o711)
        package = w / "release"
        shutil.copytree(release, package)
        for rel, expected in json.loads((package / "files.json").read_text()).items():
            if hashlib.sha256((package / rel).read_bytes()).hexdigest() != expected:
                raise ValueError("Release hash mismatch")
        runtime, state, private = w / "run", w / "state", w / "state/private"
        for path, mode in ((runtime, 0o711), (state, 0o711), (private, 0o700)):
            path.mkdir()
            os.chown(path, scorer, scorer)
            path.chmod(mode)
        sock, db, journal = (
            runtime / "receiver.sock",
            private / "receipts.db",
            state / "observations.jsonl",
        )
        key = w / "edge-key-permission-sentinel"
        key.touch(mode=0o640)
        os.chown(key, 0, edge)
        proc = subprocess.Popen(
            [
                sys.executable,
                "-IB",
                package / "ai-training/contracts/https-model-r36/serve.py",
                "--binary",
                package / "bin/scorer",
                "--ort",
                package / "lib/onnxruntime.so",
                "--socket",
                sock,
                "--database",
                db,
                "--journal",
                journal,
                "--lineage",
                "uid-acceptance",
                "--peer-uid",
                str(edge),
                "--journal-gid",
                str(readers),
            ],
            user=scorer,
            group=scorer,
            extra_groups=[readers],
            cwd=w,
        )
        try:
            deadline = time.monotonic() + 6
            while not sock.is_socket():
                if proc.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Scorer failed to bind")
                time.sleep(0.025)
            probe = """import http.client,json,os,pathlib,socket,sys
sock,db,journal,key=sys.argv[1:]
result={'journal_read':os.access(journal,os.R_OK),'journal_write':os.access(journal,os.W_OK),
        'edge_key_read':os.access(key,os.R_OK),'database_read':os.access(db,os.R_OK)}
try:
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(2)
        s.connect(sock)
        s.sendall(b'GET /healthz HTTP/1.0\\r\\n\\r\\n')
        res=http.client.HTTPResponse(s)
        res.begin()
        result.update(http=res.status,sha=res.getheader('X-Model-SHA256'))
except (OSError,http.client.HTTPException):
    result['http']=None
print(json.dumps(result))"""

            def check(uid, groups):
                return json.loads(
                    subprocess.check_output(
                        [sys.executable, "-I", "-c", probe, sock, db, journal, key],
                        user=uid,
                        group=uid,
                        extra_groups=groups,
                        cwd=w,
                        timeout=5,
                    )
                )

            a, b, c = check(edge, []), check(observer, [readers]), check(observer, [])
            pin = json.loads(
                (
                    package / "ai-training/contracts/quality-freeze-r37/slots.json"
                ).read_text()
            )["slots"]["candidate"]["sha256"]
            scorer_view = check(scorer, [readers])
            assert (
                not scorer_view["edge_key_read"]
                and not b["edge_key_read"]
                and a["edge_key_read"]
            )
            assert a["http"] == 200 and a["sha"] == pin and not a["journal_read"]
            assert (
                b["http"] is None
                and b["journal_read"]
                and not c["journal_read"]
                and c["http"] is None
            )
            assert all(
                not i["database_read"] and not i["journal_write"] for i in (a, b, c)
            )
            assert (
                sock.stat().st_mode & 0o777
            ) == 0o660 and sock.stat().st_gid == scorer
            assert (
                journal.stat().st_mode & 0o777
            ) == 0o640 and journal.stat().st_gid == readers
            result = dict(
                scope="rootless user/network namespaces, three mapped UIDs",
                edge=a,
                scorer_has_edge_key=scorer_view["edge_key_read"],
                journal_reader=b,
                unrelated_uid=c,
                release_sha256=hashlib.sha256(
                    (package / "files.json").read_bytes()
                ).hexdigest(),
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        assert proc.returncode == 0 and not sock.exists()
    return dict(
        result,
        scorer_exit=proc.returncode,
        socket_removed=True,
        scratch_removed=not w.exists(),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("release", type=Path)
    p.add_argument("owner", type=int)
    p.add_argument("host_netns")
    p.add_argument("evidence", type=Path)
    a = p.parse_args()
    result = run(a.release, a.owner, a.host_netns)
    with a.evidence.open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")
