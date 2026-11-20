"""Exercise the shipped private-subnet actuator on an isolated veth with bounded TCP probes."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess as sp
import sys
import time

DEPLOY = Path(__file__).resolve().parents[2]
SCRIPTS = DEPLOY / "scripts"
SERVER = "10.198.38.1"
CLIENT = "10.198.38.2"
TABLE = ["inet", "pbl4_demo"]


def run(*argv, check=True):
    return sp.run(argv, check=check, capture_output=True, text=True, timeout=6)


def acceptance(host_ns, output):
    if (
        os.geteuid() != 0
        or os.readlink("/proc/self/ns/net") == host_ns
        or Path("/proc/self/uid_map").read_text().split()[1] == "0"
        or socket.if_nameindex() != [(1, "lo")]
        or run("nft", "list", "tables").stdout.strip()
    ):
        raise RuntimeError("A fresh rootless network namespace is required")
    ns = os.readlink("/proc/self/ns/net")
    with contextlib.ExitStack() as cleanup:
        peer = sp.Popen(["unshare", "-n", "sleep", "55"])

        def reap():
            peer.terminate()
            peer.wait(timeout=3)

        cleanup.callback(reap)
        for _ in range(100):
            peer_ns = os.readlink(f"/proc/{peer.pid}/ns/net")
            if peer_ns not in [ns, host_ns]:
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("Peer namespace not owned")
        prefix = ["nsenter", "-t", str(peer.pid), "-n"]
        run(
            "ip",
            "link",
            "add",
            "r38-edge",
            "type",
            "veth",
            "peer",
            "name",
            "r38-client",
        )
        run("ip", "link", "set", "r38-client", "netns", str(peer.pid))
        for exec_prefix, dev, addr in [
            ([], "r38-edge", SERVER),
            (prefix, "r38-client", CLIENT),
        ]:
            run(*exec_prefix, "ip", "link", "set", "lo", "up")
            run(*exec_prefix, "ip", "addr", "add", addr + "/30", "dev", dev)
            run(*exec_prefix, "ip", "link", "set", dev, "up")
        listener = cleanup.enter_context(socket.socket())
        listener.bind((SERVER, 0))
        listener.listen(12)
        port = listener.getsockname()[1]

        def connects():
            probe = "import socket,sys; s=socket.socket();s.settimeout(.35);sys.exit(s.connect_ex((sys.argv[1],int(sys.argv[2])))!=0)"
            return (
                run(
                    *prefix, sys.executable, "-c", probe, SERVER, str(port), check=False
                ).returncode
                == 0
            )

        def actuator(*args, check=True):
            return run(
                sys.executable, SCRIPTS / "pbl4-firewall-policy.py", *args, check=check
            )

        def elements():
            result = json.loads(actuator("list-json").stdout)
            entries = next(i["set"] for i in result["nftables"] if "set" in i)
            return [
                row.get("elem", {}).get("val") if isinstance(row, dict) else row
                for row in entries.get("elem", [])
            ]

        def drop_count():
            items = json.loads(
                run("nft", "-j", "list", "chain", *TABLE, "input").stdout
            )["nftables"]
            return sum(
                e["counter"]["packets"]
                for i in items
                for e in i.get("rule", {}).get("expr", [])
                if isinstance(e, dict) and "counter" in e
            )

        run("nft", "-f", SCRIPTS / "pbl4.nft")
        try:
            assert connects() and not elements()
            assert (
                actuator("block", SERVER, "10", check=False).returncode
                and not elements()
            )
            actuator("block", CLIENT, "8")
            before = drop_count()
            assert elements() == [CLIENT] and not connects() and drop_count() > before
            actuator("block", CLIENT, "8")
            assert elements() == [CLIENT]
            drops = drop_count() - before
            actuator("unblock", CLIENT)
            actuator("unblock", CLIENT)
            assert connects() and not elements()
            actuator("block", CLIENT, "1")
            assert CLIENT in elements() and not connects()
            end = time.monotonic() + 4
            while CLIENT in elements() and time.monotonic() < end:
                time.sleep(0.1)
            assert not elements() and connects()
        finally:
            run("nft", "delete", "table", *TABLE)
        assert not run("nft", "list", "tables").stdout.strip()
    output.write_text(
        json.dumps(
            dict(
                scope="two fresh rootless network namespaces, no default routes",
                policy="shipped pbl4.nft and pbl4-firewall-policy.py",
                connect_before=True,
                peer_blocked=True,
                kernel_dropped_packets=drops,
                duplicate_one_element=True,
                protected_server_denied=True,
                double_unblock_pass=True,
                connect_after_unblock=True,
                ttl_expired=True,
                connect_after_expiry=True,
                table_removed=True,
                peer_reaped=True,
                hybrid_originated=False,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("host_ns")
    p.add_argument("output", type=Path)
    a = p.parse_args()
    acceptance(a.host_ns, a.output)
