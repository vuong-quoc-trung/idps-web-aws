"""Observe the already authorized window. Never generate detector traffic."""
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path

policy=json.loads(Path("/etc/ws-native/approval.json").read_text())
cfg=policy["actions"]["BLOCK_REQUEST"]
if set(policy["actions"])!={"BLOCK_REQUEST"} or cfg != dict(rules=["APP-1012","APP-1013"],immediate=[],events=3,window_seconds=60,ttl=15,cooldown=60,source_instance=cfg["source_instance"]) or policy["end"]-policy["start"]!=600:
    raise SystemExit("BLOCKED: unexpected authorization")
db=sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro",uri=True)
while time.time()<policy["end"]:
    subprocess.run(["systemctl","is-active","--quiet","ws-native-worker.timer"],check=True)
    if db.execute("select stopped from control").fetchall()!=[(0,)]:
        raise SystemExit("Emergency stop latched")
    rows=db.execute("""select d.rid,d.plan from decisions d join audit a on a.rid=d.rid and a.action=d.action
        where d.action='BLOCK_REQUEST' and d.revoked=0 and a.outcome='APPROVED' and a.at>=?""",(policy["start"],)).fetchall()
    if rows:
        logs=subprocess.check_output(["journalctl","-u","ws-native-gate","--since","@"+str(policy["start"]),"-o","cat","--no-pager"],text=True)
        for trigger,encoded in rows:
            plan=json.loads(encoded)
            if not re.fullmatch("[a-f0-9]{32}",trigger) or len(set(plan["evidence"]))<3 or plan["expires"]-plan["issued"]>15:
                continue
            for rid in re.findall(rf"^BLOCK_REQUEST trigger={trigger} request=([a-f0-9]{{32}}) expires={plan['expires']}$",logs,re.M):
                q=f"""select exists(select from normalized_events where source='NGINX' and request_id='{rid}' and uri_path='/api/users' and status_code=403)
                and exists(select from normalized_events n join normalized_events a using(request_id) where n.source='NGINX' and a.source='STUDENT_AUDIT' and n.occurred_at>=to_timestamp({policy['start']}) and n.status_code between 200 and 299 and a.status_code=n.status_code and n.uri_path<>'/api/users')"""
                ok=subprocess.check_output(["docker","exec","-e","PGOPTIONS=-cdefault_transaction_read_only=on","pbl4-postgres","psql","-XAt","-v","ON_ERROR_STOP=1","-U","pbl4","-d","ws_native_security","-c",q],text=True)
                if ok.strip()=="t" and time.time()<policy["end"]:
                    print("AUTO BLOCK_REQUEST ACTIVE; trigger="+trigger+" gate_403_request="+rid)
                    raise SystemExit(0)
    time.sleep(2)
print("WINDOW EXPIRED: insufficient live acceptance evidence; no further grants")
