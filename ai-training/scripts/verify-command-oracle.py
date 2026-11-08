#!/usr/bin/env python3
"""Bounded localhost-only Oracle recovery, separate from every cohort and model.

Uses existing lab limits/watchdog/session helpers. No raw HTTP or session values
are written. CLI exit status is a separate same-identity witness, not the unexposed
exit status of DVWA shell_exec's HTTP child.
"""

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
RUN = "command-oracle-recovery-20261108"


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def helpers():
    c = module("request-v3-final-controls")
    c.RUN = RUN
    q, d = c.configured_helpers()
    return c, q, d


def ping_summary(blob, expected=4):
    """One coherent summary; packet observation/identity are verified separately."""
    if not isinstance(blob, bytes) or len(blob) > 1_000_000:
        return {"valid": False, "reason": "INVALID_OUTPUT"}
    header = bool(re.search(rb"(?m)^PING\s+localhost\b", blob))
    matches = list(
        re.finditer(
            rb"(?m)^([0-9]+) packets transmitted,\s*([0-9]+)(?: packets)? received,\s*([0-9]+(?:\.[0-9]+)?)% packet loss(?:,[^\r\n]*)?\r?$",
            blob,
        )
    )
    if len(matches) != 1:
        return {"valid": False, "reason": "INVALID_OUTPUT", "summary_count": len(matches)}
    m = matches[0]
    tx, rx, loss = int(m[1]), int(m[2]), float(m[3])
    valid = header and tx == rx == expected and loss == 0
    return {
        "valid": valid,
        "localhost_header": header,
        "transmitted": tx,
        "received": rx,
        "loss_percent": loss,
        "summary_count": 1,
        "reason": "VERIFIED_SUMMARY" if valid else "INVALID_OUTPUT",
    }


def decision(
    summary,
    *,
    returncode=None,
    timed_out=False,
    session=True,
    app_ok=True,
    packets=True,
    error_class=None,
):
    """Execution outcome only; never a benign/attack label or formal admission."""
    if not session:
        return "UNKNOWN_SESSION_MISMATCH"
    if not app_ok:
        return "UNKNOWN_APPLICATION_ERROR"
    if timed_out:
        return "UNKNOWN_COMMAND_TIMEOUT"
    if error_class == "PERMISSION_DENIED":
        return "UNKNOWN_PERMISSION_DENIED"
    if returncode is None:
        return "UNKNOWN_EXIT_STATUS_NOT_OBSERVED"
    if returncode == 127:
        return "UNKNOWN_COMMAND_NOT_FOUND"
    if returncode:
        return "UNKNOWN_COMMAND_FAILED"
    if not summary.get("valid"):
        return "UNKNOWN_INVALID_OUTPUT"
    if not packets:
        return "UNKNOWN_PACKET_OBSERVATION_FAILURE"
    return "VERIFIED_EXECUTION"


def exec_json(name, code, value=None):
    p = subprocess.run(
        ["podman", "exec", "-i", "--user", "33:33", name, "php", "-r", code],
        input=json.dumps(value).encode() if value is not None else b"",
        capture_output=True,
        timeout=15,
        check=True,
    )
    return json.loads(p.stdout)


def session_code(c):
    return next(
        v
        for v in c.php_authenticated.__code__.co_consts
        if isinstance(v, str) and "$v=json_decode" in v
    )


def authenticated(c, d, ss):
    if not ss.cookies.get("PHPSESSID"):
        return False
    return exec_json(d.APP, session_code(c), {"id": ss.cookies["PHPSESSID"]})["authenticated"]


def counters(name):
    code = """$r=[];foreach(['/proc/net/snmp','/proc/net/snmp6'] as $p){$ls=@file($p,FILE_IGNORE_NEW_LINES);if($ls===false)continue;for($i=0;$i<count($ls);$i++){if($p==='/proc/net/snmp6'){$x=preg_split('/\\s+/',trim($ls[$i]));if(count($x)==2&&str_starts_with($x[0],'Icmp6'))$r[$x[0]]=(int)$x[1];}elseif(str_starts_with($ls[$i],'Icmp:')&&isset($ls[$i+1])){$k=preg_split('/\\s+/',trim($ls[$i]));$v=preg_split('/\\s+/',trim($ls[++$i]));foreach($k as $j=>$key){if($j)$r['Icmp'.$key]=(int)$v[$j];}}}}echo json_encode(['netns'=>readlink('/proc/self/ns/net'),'counters'=>$r]);"""
    return exec_json(name, code)


def echo_delta(before, after):
    if before["netns"] != after["netns"]:
        return {"valid": False, "reason": "NAMESPACE_MISMATCH"}
    tx = ["IcmpOutEchos", "Icmp6OutEchos"]
    rx = ["IcmpInEchoReps", "Icmp6InEchoReplies"]
    common = set(before["counters"]) & set(after["counters"])
    if not any(k in common for k in tx) or not any(k in common for k in rx):
        return {"valid": False, "reason": "MISSING_COUNTERS"}
    sent = sum(after["counters"][k] - before["counters"][k] for k in tx if k in common)
    received = sum(after["counters"][k] - before["counters"][k] for k in rx if k in common)
    return {
        "valid": sent >= 0 and received >= 0,
        "echo_requests_sent": sent,
        "echo_replies_received": received,
        "netns_same": True,
        "scope": "Kernel ICMP MIB counters inside owned lab namespace, not PCAP",
    }


def initialize(c, q, d):
    setup = c.RAMSession()
    for _ in range(40):
        try:
            s, _, page, _ = setup.call("GET", "/setup.php")
            if s == 200:
                break
        except OSError:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("Setup readiness failed")
    for _ in range(40):
        p = subprocess.run(
            [
                "podman",
                "exec",
                d.DB,
                "mariadb",
                "-h127.0.0.1",
                "-udvwa",
                "-pp@ssw0rd",
                "-N",
                "dvwa",
                "-e",
                "SELECT 1",
            ],
            capture_output=True,
        )
        if p.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Database readiness failed")
    _, _, page, _ = setup.call("GET", "/setup.php")
    token = re.search(rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page)
    assert token
    setup.call(
        "POST",
        "/setup.php",
        urlencode({"create_db": "Create / Reset Database", "user_token": token[1].decode()}),
    )
    ss = c.RAMSession()
    _, _, page, _ = ss.call("GET", "/login.php")
    token = re.search(rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page)
    assert token
    s, _, _, _ = ss.call(
        "POST",
        "/login.php",
        urlencode(
            {
                "username": "admin",
                "password": "password",
                "Login": "Login",
                "user_token": token[1].decode(),
            }
        ),
    )
    assert s == 302 and authenticated(c, d, ss)
    ss.cookies["security"] = "low"
    return ss, setup.setup_requests + ss.setup_requests


def observer(name):
    # Only ping process metadata/ancestors, no argv or credentials.
    code = """$r=[];$end=microtime(true)+6;while(microtime(true)<$end){foreach(glob('/proc/[0-9]*/comm') as $f){if(trim(@file_get_contents($f))!=='ping')continue;$p=(int)basename(dirname($f));$chain=[];$n=$p;for($j=0;$j<4&&$n>0;$j++){$s=@file('/proc/'.$n.'/status',FILE_IGNORE_NEW_LINES);if($s===false)break;$v=['pid'=>$n];foreach($s as $l){foreach(['Name','PPid','Uid','Gid','CapEff','NoNewPrivs','Seccomp'] as $k){if(str_starts_with($l,$k.':'))$v[$k]=trim(substr($l,strlen($k)+1));}}$chain[]=$v;$n=(int)($v['PPid']??0);}$r[$p]=$chain;}usleep(25000);}echo json_encode(array_values($r));"""
    return exec_json(name, code)


def verify(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    c, q, d = helpers()
    assert not q.owned()
    host_range = Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip()
    host_ns = os.readlink("/proc/self/ns/net")
    protected = json.loads(
        (ROOT / ".local-dev/request-v3-final-20261108/protected-before.json").read_text()
    )
    assert all(file_sha256(ROOT / k) == v for k, v in protected.items())
    old = (
        ROOT
        / "ai-training/.artifacts/request_v3_final_20261108/campaign-v3/preflight-oracle-receipts.json"
    )
    old_sha = file_sha256(old)
    source = ROOT / "ai-training/scripts/helpers/icmp-socket-probe.c"
    subprocess.run(
        ["cc", "-static", "-O2", str(source), "-o", str(root / "socket-probe")],
        capture_output=True,
        check=True,
    )
    os.chmod(root / "socket-probe", 0o755)
    (root / "heartbeat").touch()
    stop = threading.Event()

    def beat():
        while not stop.wait(0.2):
            (root / "heartbeat").touch()

    t = threading.Thread(target=beat, daemon=True)
    t.start()
    unit = "idps-" + RUN + "-watchdog.service"
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
            "MemoryMax=256M",
            "-p",
            "RuntimeMaxSec=600",
            "--setenv=OPENBLAS_NUM_THREADS=1",
            "--setenv=OMP_NUM_THREADS=1",
            sys.executable,
            str(Path(__file__).resolve()),
            "watchdog",
            "--output",
            str(root),
        ],
        check=True,
        capture_output=True,
    )
    deadline = time.monotonic() + 10
    while not (root / "watchdog-ready").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (root / "watchdog-ready").exists()
    try:
        c.launch(q, d, "dvwa")
        for _ in range(40):
            ready = subprocess.run(
                ["podman", "exec", d.APP, "test", "-s", "/var/run/apache2/apache2.pid"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Apache readiness failed")
        # Ephemeral metadata-only observer. Original PHP workflow is not modified.
        conf = "sed -i '/<\\/VirtualHost>/i\\ CustomLog /tmp/oracle-http-metadata.log \"%{X-Request-Id}i %P %>s\"' /etc/apache2/sites-available/000-default.conf && apache2ctl -k graceful"
        q.pm("exec", d.APP, "sh", "-c", conf)
        subprocess.run(
            ["podman", "cp", str(root / "socket-probe"), d.APP + ":/tmp/socket-probe"],
            check=True,
            capture_output=True,
        )
        socket_probe = json.loads(q.pm("exec", "--user", "33:33", d.APP, "/tmp/socket-probe"))
        assert (
            socket_probe["uid"] == 33
            and socket_probe["gid"] == 33
            and socket_probe["icmp_dgram_fd_ok"]
            and not socket_probe["icmp_raw_fd_ok"]
        )
        ss, setup_calls = initialize(c, q, d)
        before = counters(d.APP)
        seen = []
        th = threading.Thread(target=lambda: seen.extend(observer(d.APP)), daemon=True)
        th.start()
        rid = digest([RUN, "HTTP_POSITIVE"])[:32]
        raw = urlencode({"ip": '"localhost"', "Submit": "Submit"}).encode()
        headers = {
            "User-Agent": c.UA,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Request-Id": rid,
            "Cookie": "; ".join(f"{k}={v}" for k, v in ss.cookies.items()),
        }
        status, _, page, _ = c.http(c.PORT, "POST", "/vulnerabilities/exec/", raw, headers)
        after = counters(d.APP)
        th.join(timeout=10)
        assert not th.is_alive()
        pre = re.findall(rb"<pre>(.*?)</pre>", page, re.S)
        valid = [ping_summary(p) for p in pre if b"PING" in p]
        assert len(valid) == 1
        summary = valid[0]
        delta = echo_delta(before, after)
        assert (
            status == 200
            and summary["valid"]
            and delta["valid"]
            and delta["echo_requests_sent"] == 4
            and delta["echo_replies_received"] == 4
        )
        log = q.pm("exec", d.APP, "cat", "/tmp/oracle-http-metadata.log").splitlines()
        identity = [line.split() for line in log if line.startswith(rid + " ")]
        assert len(identity) == 1
        server_pid = int(identity[0][1])
        assert identity[0][2] == "200"
        matches = [chain for chain in seen if server_pid in [p["pid"] for p in chain]]
        assert matches
        relevant = matches[0][
            : next(i for i, p in enumerate(matches[0]) if p["pid"] == server_pid) + 1
        ]
        assert all(
            p["Uid"].split()[1] == "33"
            and p["Gid"].split()[1] == "33"
            and int(p["CapEff"], 16) == 0
            and p["NoNewPrivs"] == "1"
            for p in relevant
        )
        positive = {
            "HTTP_status": status,
            "request_id": rid,
            "session_group": "session_group-0001",
            "role": "DIAGNOSTIC_ONLY",
            "summary": summary,
            "packets": delta,
            "request_server_pid_correlated": True,
            "app_worker_and_ping_UID_GID": 33,
            "observed_ping_process": True,
            "session_authenticated_after": authenticated(c, d, ss),
            "outcome": "VERIFIED_HTTP_PACKET_EXECUTION",
            "intent": "AUTHORIZED_LOCALHOST_DIAGNOSTIC_NO_DATASET_ADMISSION",
        }
        assert positive["session_authenticated_after"]
        # A real negative control: same endpoint, no valid authenticated session.
        neg_id = digest([RUN, "HTTP_SESSION_NEGATIVE"])[:32]
        negative_headers = {k: v for k, v in headers.items() if k != "Cookie"}
        negative_headers["X-Request-Id"] = neg_id
        before = counters(d.APP)
        ns, _, np, _ = c.http(c.PORT, "POST", "/vulnerabilities/exec/", raw, negative_headers)
        nd = echo_delta(before, counters(d.APP))
        assert (
            ns == 302
            and nd["valid"]
            and nd["echo_requests_sent"] == nd["echo_replies_received"] == 0
        )
        negative_log = q.pm("exec", d.APP, "cat", "/tmp/oracle-http-metadata.log").splitlines()
        negative_identity = [line.split() for line in negative_log if line.startswith(neg_id + " ")]
        assert (
            len(negative_identity) == 1
            and negative_identity[0][2] == "302"
            and authenticated(c, d, ss)
        )
        negative = {
            "HTTP_status": ns,
            "request_id": neg_id,
            "session_group": "session_group-0002",
            "role": "DIAGNOSTIC_ONLY",
            "outcome": decision(ping_summary(np), session=False),
            "packets": nd,
            "no_successful_summary": not ping_summary(np)["valid"],
            "auth_gate_preserved": True,
            "benign_label_assigned": False,
        }
        # Independent same-argv/status witness; DVWA does not expose shell_exec exit.
        cli_code = """$p=proc_open(['/usr/bin/ping','-c','4','localhost'],[1=>['pipe','w'],2=>['pipe','w']],$pipes);$s=stream_get_contents($pipes[1]);$e=stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$r=proc_close($p);echo json_encode(['exit'=>$r,'stdout'=>$s,'stderr_empty'=>$e==='']);"""
        cli = exec_json(d.APP, cli_code)
        cli_summary = ping_summary(cli["stdout"].encode())
        assert cli["exit"] == 0 and cli_summary["valid"]
        assert decision(cli_summary, returncode=cli["exit"], packets=True) == "VERIFIED_EXECUTION"
        metadata = q.pm(
            "exec",
            "--user",
            "33:33",
            d.APP,
            "sh",
            "-c",
            'id; readlink /proc/self/ns/net; cat /proc/sys/net/ipv4/ping_group_range; grep -E "^(Cap|NoNewPrivs|Seccomp)" /proc/self/status; cat /proc/self/attr/current',
        ).splitlines()
        assert (
            host_ns != before["netns"]
            and Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip() == host_range
        )
        atomic_json(
            root / "diagnostic-receipts.json",
            {
                "positive": positive,
                "negative": negative,
                "observed_process_metadata": relevant,
                "separate_CLI_status": {
                    "exit": cli["exit"],
                    "summary": cli_summary,
                    "HTTP_child_exit_directly_observed": False,
                },
            },
        )
        result = {
            "case": "CASE_A_ORACLE_VERIFIED",
            "COMMAND_ORACLE_ROOT_CAUSE": "VERIFIED",
            "LOCALHOST_PING": "PASS",
            "PACKET_SUMMARY_ORACLE": "PASS",
            "ORACLE_NEGATIVE_CONTROL": "PASS",
            "SANDBOX_ISOLATION": "PASS",
            "MAIN_CAPTURE": "NOT_STARTED",
            "REQUEST_V3_TRAINING": "NOT_STARTED",
            "DATASET_COVERAGE": "UNCHANGED",
            "HTTP_diagnostic_requests": 2,
            "setup_HTTP_calls": setup_calls,
            "supervised_rows_added": 0,
            "CLI_status": 0,
            "HTTP_child_exit_status": "NOT_EXPOSED_BY_DVWA_SEPARATE_SAME_IDENTITY_CLI_WITNESS",
            "packet_evidence": "Actual lab-namespace ICMP counters4echo/4reply, PID ancestry and coherent4/4zero-loss response",
            "socket_probe": socket_probe,
            "security_metadata_lines": metadata,
            "host_ping_group_range_before_after": host_range,
            "host_netns": host_ns,
            "lab_netns": before["netns"],
            "host_protections_changed": False,
            "raw_HTTP_or_session_values_saved": False,
            "old_UNKNOWN_sha256": old_sha,
            "source_sha256": file_sha256(__file__),
            "collector_source_sha256": file_sha256(
                ROOT / "ai-training/scripts/request-v3-final-controls.py"
            ),
            "C_probe_source_sha256": file_sha256(source),
            "NEXT_ACTION": "Resume locked bounded campaign only on later request; no acquisition now",
        }
        atomic_json(root / "result.json", result)
    finally:
        c.cleanup(q, d)
        (root / "watchdog-done").touch()
        stop.set()
        t.join(timeout=1)
        # Give ownership monitor a chance to record normal completion before stop.
        deadline = time.monotonic() + 2
        while not (root / "lab-watchdog-result.json").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)
    assert (
        not q.owned()
        and file_sha256(old) == old_sha
        and all(file_sha256(ROOT / k) == v for k, v in protected.items())
    )
    assert Path("/proc/sys/net/ipv4/ping_group_range").read_text().strip() == host_range
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "case",
                    "LOCALHOST_PING",
                    "PACKET_SUMMARY_ORACLE",
                    "ORACLE_NEGATIVE_CONTROL",
                    "MAIN_CAPTURE",
                    "REQUEST_V3_TRAINING",
                    "DATASET_COVERAGE",
                ]
            }
        )
    )


def watch(root):
    _, q, _ = helpers()
    a = module("attack-intent-capture")
    a.RUN = RUN
    a.watchdog(root, q)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["verify", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    try:
        {"verify": verify, "watchdog": watch}[a.action](a.output.resolve())
    except Exception as e:
        print(
            json.dumps({"status": "FAILED", "type": type(e).__name__, "details": "SUPPRESSED"}),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
