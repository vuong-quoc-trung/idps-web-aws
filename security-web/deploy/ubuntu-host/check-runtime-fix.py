"""One authenticated status read; do not print tokens, credentials, or evidence."""
import json
import re
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
try:
    for attempt in range(10):
        report=json.loads(call("status",headers=headers))
        nginx=report["watchers"].get("NGINX", {})
        if nginx.get("state") == "NOT_STARTED" and nginx.get("error") is None:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Expected NGINX NOT_STARTED; got "+str(nginx.get("state"))+": "+str(nginx.get("error")))
    fw=report.get("firewall_status")
    blocked=json.loads(call("blocked-ips",headers=headers))
    if fw not in ("READY","FIREWALL_UNINITIALIZED","ACTUATOR_OFFLINE") or blocked.get("error") != (None if fw=="READY" else fw):
        raise RuntimeError(f"Inconsistent firewall status: {fw}, blocked-ips: {blocked.get('error')}")
    dist=Path("/opt/ws-native/runtime-fix/frontend/dist")
    with opener.open("http://127.0.0.1:23000/",timeout=3) as response:
        index=response.read()
    if index != (dist/"index.html").read_bytes():
        raise RuntimeError("Served HTML differs from release")
    asset=re.search(rb'src="(/assets/[^"/]+\.js)"',index)[1].decode()
    with opener.open("http://127.0.0.1:23000"+asset,timeout=3) as response:
        if response.read() != (dist/asset.lstrip("/")).read_bytes():
            raise RuntimeError("Served Dashboard JavaScript differs from release")
    print("NGINX: NOT_STARTED; firewall:",fw,"; Dashboard assets match")
finally:
    call("auth/logout",b"",headers)
