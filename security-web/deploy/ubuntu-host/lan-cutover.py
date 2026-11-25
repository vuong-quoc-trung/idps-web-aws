"""Prepare the direct lab ingress. Called by native-auto.sh; holds no application credentials."""
import ssl
import argparse
import hashlib
import grp
import pwd
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from direct_peer import CONFIG, LEDGER, check_listener_name, check_table, listening, validate

BASE = Path("/etc/ws-native")
NGINX = BASE / "nginx.conf"
STATE = BASE / "lan-cutover"
SRC = Path(__file__).resolve().parent
TABLE = ("table", "inet", "ws_native_lab_peer")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=30, **kwargs)


def nft_table():
    return run("nft","-st","list",*TABLE,stdout=subprocess.PIPE).stdout


def wait_for_edge(address, timeout=30):
    # Type=exec acknowledges the Python supervisor before it grants the guard
    # and starts NGINX. The status file identifies its guarded master process.
    deadline = time.monotonic() + timeout
    status = Path("/var/lib/ws-native/guard/status.json")
    while True:
        state = run("systemctl", "show", "ws-native-edge", "-p", "ActiveState",
                    "--value", text=True, stdout=subprocess.PIPE).stdout.strip()
        if state not in ("active", "activating"):
            raise RuntimeError(f"ws-native-edge {state} before binding {address}:24443")
        try:
            snapshot = json.loads(status.read_bytes())
        except FileNotFoundError:
            snapshot = {}
        pid = snapshot.get("pid")
        if (snapshot.get("guard_snapshot") is True and type(pid) is int and pid > 1
                and listening(address, pid)):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Guarded NGINX did not bind {address}:24443 within {timeout}s")
        time.sleep(0.25)


def render(text, cfg):
    listen = "listen 127.0.0.1:24443 ssl;"
    access = "access_log /var/lib/ws-native/edge/access.jsonl pbl4_ai_access;"
    local, peer = cfg["listener_ip"], cfg["exclusive_lab_peer"]
    for marker in ("http {",listen,access):
        if text.count(marker)!=1:
            raise ValueError("Unexpected native configuration: "+marker)
    fmt=(SRC/"direct-peer-log.inc.example").read_text().splitlines()[1]
    # The rendered site uses matching indentation for each server and its closing brace.
    blocks=list(re.finditer(r"(?ms)^(?P<indent>[ \t]*)server \{[^\n]*\n.*?^(?P=indent)\}",text))
    edge, = [b for b in blocks if listen in b.group()]
    site=edge.group()
    if site.count("listen ")!=1 or site.count(access)!=1 or "proxy_protocol" in site:
        raise ValueError("Unexpected Edge listener/log scope")
    clone=site.replace(listen,f"listen {local}:24443 ssl;\n    allow {peer};\n    deny all;")
    clone=clone.replace(access,access+"\n    access_log /var/lib/ws-native/edge/direct-peer.jsonl ws_direct;")
    for directive,key in (("ssl_certificate","cert"),("ssl_certificate_key","key")):
        clone,n=re.subn(r"(?m)^(\s*)"+directive+r"\s+[^;]+;",lambda m:m[1]+directive+" "+cfg[key]+";",clone)
        if n!=1: raise ValueError("Unexpected TLS directive "+directive)
    return (text[:edge.end()]+"\n"+clone+text[edge.end():]).replace("http {","http {\n    "+fmt)


def atomic_config(path, text, reference=None):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        f.write(text.encode())
        f.flush()
        os.fsync(f.fileno())
        if reference:
            st=reference.stat()
            os.fchown(f.fileno(),st.st_uid,st.st_gid)
            os.fchmod(f.fileno(),st.st_mode & 0o777)
        else:
            os.fchmod(f.fileno(),0o644)
    os.replace(f.name,path)


def rollback():
    if not STATE.exists(): return
    old=STATE/"before.conf"
    if (STATE/"candidate.conf").exists() and NGINX.read_bytes()!=(STATE/"candidate.conf").read_bytes() and NGINX.read_bytes()!=old.read_bytes():
        raise RuntimeError("NGINX drift; preserve backup at "+str(old))
    if old.exists() and NGINX.read_bytes()!=old.read_bytes():
        atomic_config(NGINX,old.read_text(),old)
        run("nginx","-t","-c",str(NGINX))
        run("systemctl","restart","ws-native-edge")
    if (STATE/"owns-table").exists():
        cfg=json.loads((STATE/"scope.json").read_text())
        actual=nft_table()
        if hashlib.sha256(actual).hexdigest()!=cfg["table_sha256"]:
            raise RuntimeError("Dedicated firewall table drift; retained for review")
        run("nft","delete",*TABLE)
    if (STATE/"rotation").exists():
        rot=Path("/etc/logrotate.d/ws-native-direct-peer")
        if rot.exists() and rot.read_bytes()!=(STATE/"rotation").read_bytes():
            raise RuntimeError("Direct ledger logrotate drift; preserve for review")
        rot.unlink(missing_ok=True)
    CONFIG.unlink(missing_ok=True)
    STATE.rename(BASE/f"lan-retired-{time.time_ns()}")


def prepare(a):
    a.name=a.name or "security.lab"
    a.ca=a.ca or str(BASE/"lan-tls/ca.crt")
    a.cert=a.cert or str(BASE/"lan-tls/edge.crt")
    a.key=a.key or str(BASE/"lan-tls/edge.key")
    if not all((a.cidr,a.interface,a.listener,a.peer,a.mac,a.protect,a.name,a.ca)):
        run("ip","-br","-4","addr")
        for key,label in (("interface","Physical lab interface"),("listener","Host LAN IPv4"),
                          ("cidr","Authorized private lab CIDR"),("peer","Reserved exclusive laptop IPv4"),
                          ("mac","Approved laptop MAC for this Wi-Fi"),("name","DNS SAN on LAN TLS certificate"),
                          ("ca","Absolute path to trusted LAN CA"),("cert","Absolute path to LAN certificate"),
                          ("key","Absolute path to LAN private key")):
            if not getattr(a,key): setattr(a,key,input(label+": ").strip())
        if not a.protect: a.protect=input("Management and shared/infrastructure IPs or CIDRs (space-separated): ").split()
    cfg=dict(listener_name=a.name,lab_cidr=a.cidr,interface=a.interface,listener_ip=a.listener,
             exclusive_lab_peer=a.peer,peer_mac=a.mac,protected_networks=a.protect,
             exclusive_no_relay_confirmed=True)
    if subprocess.run(["systemctl","is-active","--quiet","ws-native-edge"]).returncode:
        raise RuntimeError("Require running native Edge before LAN cutover")
    if CONFIG.exists() or STATE.exists():
        raise RuntimeError("Direct scope already present. Use status or rollback.")
    window=BASE/"approval.json"
    existing=json.loads(window.read_bytes()) if window.exists() else {}
    if existing.get("actions") and existing["end"] > time.time():
        raise RuntimeError("Active window; wait for expiry before changing the listener")
    check_listener_name(cfg)
    validate(cfg, require_listener=False)
    # Check the actual Edge leaf and the operator-supplied trust anchor. Use this DNS name on laptop.
    for path in (a.cert,a.key):
        if not re.fullmatch(r"/[A-Za-z0-9/_.-]+",path) or not Path(path).is_file():
            raise ValueError("Require absolute certificate and key paths")
    cfg.update(cert=a.cert,key=a.key)
    sans=run("openssl","x509","-in",a.cert,"-noout","-ext","subjectAltName",stdout=subprocess.PIPE,text=True).stdout
    if not re.fullmatch(r"[A-Za-z0-9.-]+",a.name) or ("DNS:"+a.name.lower()) not in [
            x.strip().lower().replace("dns:","DNS:",1) for x in sans.replace("\n",",").split(",")]:
        raise ValueError("Explicit matching DNS SAN required for the lab listener")
    run("openssl","verify","-purpose","sslserver","-verify_hostname",a.name,"-CAfile",a.ca,a.cert)
    run("openssl","verify","-purpose","sslserver","-verify_ip",a.listener,"-CAfile",a.ca,a.cert)
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(a.cert,a.key)
    candidate=render(NGINX.read_text(),cfg)
    rules=(SRC/"direct-peer.nft.example").read_text().replace("table inet ws_native_lab_peer {","create table inet ws_native_lab_peer\ntable inet ws_native_lab_peer {").replace("LAB_INTERFACE",a.interface).replace("LISTENER_IPV4",a.listener).replace("EXCLUSIVE_TEST_IPV4",a.peer)
    run("nft","-c","-f","-",input=rules,text=True)
    print(f"Direct peer {a.peer} ({a.mac}) via {a.interface}, CIDR {a.cidr}; HTTPS {a.name} at {a.listener}:24443. Protected: {a.protect}. No relay/NAT/shared host. Restart native Edge; install dedicated input chain.")
    if input("Type APPROVE-DIRECT-LAN: ")!="APPROVE-DIRECT-LAN": raise SystemExit(1)
    STATE.mkdir(mode=0o700)
    try:
        shutil.copy2(NGINX,STATE/"before.conf")
        os.chown(STATE/"before.conf",NGINX.stat().st_uid,NGINX.stat().st_gid)
        owner=pwd.getpwnam("ws-native-edge").pw_uid
        group=grp.getgrnam("ws-native-evidence").gr_gid
        try:
            fd=os.open(LEDGER,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
        except FileExistsError:
            if LEDGER.resolve()!=LEDGER or not LEDGER.is_file() or LEDGER.stat().st_uid!=owner or LEDGER.stat().st_gid!=group or LEDGER.stat().st_mode & 0o777 != 0o640:
                raise RuntimeError("Unexpected existing direct ledger permissions")
        else:
            with os.fdopen(fd,"wb") as file:
                os.fchown(file.fileno(),owner,group)
                os.fchmod(file.fileno(),0o640)
        (STATE/"candidate.conf").write_text(candidate)
        run("nginx","-t","-c",str(STATE/"candidate.conf"))
        rotation=Path("/etc/logrotate.d/ws-native-direct-peer")
        if rotation.exists(): raise RuntimeError("Existing unmanaged rotation policy")
        spec=(SRC/"native-logrotate").read_text().split("/var/lib/ws-native/sensor/")[0]
        spec=spec.replace("/var/lib/ws-native/edge/access.jsonl /var/lib/ws-native/edge/error.log",str(LEDGER))
        (STATE/"rotation").write_text(spec)
        atomic_config(rotation,spec)
        run("nft","-f","-",input=rules,text=True)
        actual=nft_table()
        cfg["table_sha256"]=hashlib.sha256(actual).hexdigest()
        (STATE/"scope.json").write_text(json.dumps(cfg))
        (STATE/"owns-table").touch()
        check_table(cfg,actual)
        atomic_config(NGINX,candidate,STATE/"before.conf")
        run("nginx","-t","-c",str(NGINX))
        run("systemctl","restart","ws-native-edge")
        wait_for_edge(a.listener)
        validate(cfg, require_neighbor=False)
        check_table(cfg,nft_table())
        atomic_config(CONFIG,json.dumps(cfg))
    except BaseException:
        rollback()
        raise


if __name__=="__main__":
    if os.geteuid()!=0: raise SystemExit("Run via native-auto.sh lan")
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    prep=sub.add_parser("prepare")
    for arg in ("cidr","interface","listener","peer","mac","name","ca"):
        prep.add_argument("--"+arg)
    prep.add_argument("--protect",action="append",help="Management/shared/infrastructure CIDR; repeat as needed")
    prep.add_argument("--cert",default=None)
    prep.add_argument("--key",default=None)
    sub.add_parser("rollback")
    args=parser.parse_args()
    if args.cmd=="rollback": rollback()
    else: prepare(args)
