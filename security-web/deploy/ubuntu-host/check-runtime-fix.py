"""One authenticated status read; do not print tokens, credentials, or evidence."""
import json
import re
import sys
import time
from pathlib import Path
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = "http://127.0.0.1:23000/api/"
def call(path, data=None, headers=None):
    req = urllib.request.Request(base+path, data=data, headers=headers or {})
    with opener.open(req, timeout=5) as response:
        return response.read()

token=json.loads(call("auth/login", json.dumps({"username":"admin","password":Path("/etc/ws-native/dashboard.password").read_text().strip()}).encode(), {"Content-Type":"application/json"}))["token"]
headers={"Authorization":"Bearer "+token}
monitoring = sys.argv[1:] == ["--monitoring"]
try:
    for attempt in range(10):
        report=json.loads(call("status",headers=headers))
        nginx=report["watchers"].get("NGINX", {})
        if monitoring:
            if report.get("operations", {}).get("native_authorization") and report["watchers"].get("SURICATA_LUA"):
                break
            time.sleep(1)
            continue
        if nginx.get("state") == "NOT_STARTED" and nginx.get("error") is None:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Missing required runtime sample; got "+str(nginx.get("state"))+": "+str(nginx.get("error")))
    fw=report.get("firewall_status")
    blocked=json.loads(call("blocked-ips",headers=headers))
    if fw not in ("READY","FIREWALL_UNINITIALIZED","ACTUATOR_OFFLINE") or blocked.get("error") != (None if fw=="READY" else fw):
        raise RuntimeError(f"Inconsistent firewall status: {fw}, blocked-ips: {blocked.get('error')}")
    if monitoring:
        lua = report["collection"]["SURICATA_LUA"]
        watcher = report["watchers"]["SURICATA_LUA"]
        if (fw != "READY" or report.get("firewall_initialized") is not True
                or not all(x.get("sync", {}).get("status") in ("SYNCED","OUT_OF_SYNC","UNVERIFIED") for x in (report,blocked))
                or watcher["state"] != "watching"):
            raise RuntimeError("Native monitoring checkpoint failed: "+str((fw, watcher["state"])))
        for endpoint, payload, legacy in (("status",report,"firewall_in_sync"),("blocked-ips",blocked,"in_sync")):
            sync = payload["sync"]
            expected = {"SYNCED": True, "OUT_OF_SYNC": False, "UNVERIFIED": None}[sync["status"]]
            if (legacy not in payload or payload[legacy] is not expected
                    or sync.get("scope") != "inet ws_native_lab_peer/edge_peers"
                    or bool(sync.get("differences")) != (expected is False)):
                raise RuntimeError("Invalid reconciliation contract on "+endpoint)
        print("Native firewall", fw, "IP count", report["kernel_blocked_count"],
              "DB/journal/kernel", report["sync"]["status"], report["sync"]["reason"], "authorization", report["operations"]["native_authorization"])
        print("Lua last read", watcher["last_success_at"], "last data", watcher["last_data_at"],
              "pending bytes", watcher["pending_bytes"], "last DB write", lua["last_ingested_at"],
              "parser errors", lua["error_count"])
    dist=Path("/opt/ws-native/runtime-fix/frontend/dist")
    with opener.open("http://127.0.0.1:23000/",timeout=3) as response:
        index=response.read()
    if index != (dist/"index.html").read_bytes():
        raise RuntimeError("Served HTML differs from release")
    asset=re.search(rb'src="(/assets/[^"/]+\.js)"',index)[1].decode()
    with opener.open("http://127.0.0.1:23000"+asset,timeout=3) as response:
        if response.read() != (dist/asset.lstrip("/")).read_bytes():
            raise RuntimeError("Served Dashboard JavaScript differs from release")
    print("Dashboard assets match; firewall:",fw)
finally:
    call("auth/logout",b"",headers)
