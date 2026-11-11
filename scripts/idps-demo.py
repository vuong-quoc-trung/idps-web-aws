#!/usr/bin/env python3
"""Small terminal client for the real local HTTP/AI/policy API. No fake scores."""

import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from idps_ai.common import atomic_json
from idps_ai.training.heartbeat import process_identity

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / ".local-dev/demo-v1"
POINTER = REPO / ".local-dev/demo-session.json"


def load(path):
    return json.loads(path.read_text())


def request(path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(
        "http://127.0.0.1:3001" + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(r, timeout=15) as response:
        return json.load(response)


def token():
    secret = load(RUNTIME / "credentials.json")
    return request(
        "/api/auth/login",
        {"username": "admin", "password": secret["security_admin_password"]},
    )["token"]


def lan_urls():
    interfaces = json.loads(subprocess.check_output(['ip','-j','-4','address'], text=True))
    routes = json.loads(subprocess.check_output(['ip','-j','-4','route','show','default'],text=True))
    primary = next((r['dev'] for r in sorted(routes,key=lambda r:r.get('metric',0)) if 'dev' in r),None)
    urls = []
    for iface in sorted(interfaces,key=lambda i:i['ifname'] != primary):
        if 'UP' not in iface.get('flags',[]):
            continue
        for a in iface.get('addr_info',[]):
            if a.get('scope') == 'global':
                urls.append('http://' + a['local'] + ':18782')
    return urls


def health_snapshot():
    report = {"status":"UNHEALTHY", "errors":[], "external_client":"PENDING_EXTERNAL_CLIENT"}
    try:
        session = load(POINTER)
        root = Path(session['root'])
        report['session'] = str(root)
        alive = process_identity(session['pid']) == session.get('start_ticks')
        if not alive:
            raise RuntimeError(f"Supervisor stopped. Inspect {root / 'demo-failure.json'} and {root / 'guard/stderr.log'}; run start after resolving the cause")
        if not (root/'demo-ready.json').exists():
            raise RuntimeError(f"STARTING: LAN readiness not yet verified. Inspect {root/'sensor.log'} and guard/stderr.log; do not launch a duplicate")
        ready = load(root/'demo-ready.json')
        urls = lan_urls() if ready.get('listen') == '0.0.0.0' else [ready['gateway']]
        report['LAN_URL'] = urls[0] if urls else ready['gateway']
        report['LAN_URLS'] = urls
        report['LISTEN'] = ready.get('listen',ready['gateway'])
        guard = load(root/'guard/resource-status.json')
        report['resource'] = guard
        if time.time()-guard['heartbeat']>5 or guard['status']!='RUNNING':
            raise RuntimeError(f"Resource guard {guard['status']}; inspect thermal/heartbeat before serving")
        sensor = Path(ready['sensor'])
        sensor_status = load(sensor/'status.json')
        report['sensor'] = sensor_status
        # A successful backend /health alone cannot establish LAN readiness.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(ready['gateway']+'/api/auth/csrf',timeout=5) as response:
            response.read()
            rid = response.headers.get('X-Request-Id')
            if response.status!=200 or not rid:
                raise RuntimeError('LAN endpoint did not return NGINX HTTP200 + X-Request-Id')
        report['HTTP'] = {'status':200,'request_id':rid,'vantage':'HOST_TO_LAN_LISTENER'}
        report['Rust'] = request('/health')
        auth = token()
        end = time.monotonic()+10
        while time.monotonic()<end:
            page = request('/api/ai-shadow?request_id='+rid,token=auth)
            incident = request('/api/hybrid-incidents?request_id='+rid,token=auth)
            rows = page.get('detectors',[])
            ai = page.get('worker') or {}
            valid = [v for v in rows if v.get('request_id')==rid and (v.get('correlation') or {}).get('status')=='MATCHED' and (v.get('request_ai') or {}).get('status')=='SCORED']
            if valid and incident['incidents'] and ai.get('status')=='READY' and not ai.get('stale'):
                report.update(status='HEALTHY',AI_worker=ai,correlation=valid[0]['correlation'],policy=incident['incidents'][0],mode=page['mode'],enforcement=page['enforcement'])
                return report
            time.sleep(.25)
        raise RuntimeError(f"LAN HTTP worked but request {rid} lacks fresh SCORED + MATCHED + policy evidence. Inspect {sensor/'status.json'}, ai/results.jsonl, sensor.log")
    except Exception as exc:  # noqa: BLE001 -- health must report component failures without a traceback
        report['errors'].append(f"{type(exc).__name__}: {str(exc) or 'No diagnostic message'}")
        return report


def start(listen=None, allow_cidr=None):
    spec = importlib.util.spec_from_file_location(
        "demo_sensor", REPO / "scripts/three-source-shadow.py"
    )
    sensor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sensor)
    network_path = REPO / '.local-dev/demo-network.json'
    saved = load(network_path) if network_path.exists() else {}
    listen = listen or saved.get('listen','127.0.0.1')
    allow_cidr = allow_cidr or saved.get('allow_cidr','127.0.0.0/8')
    sensor.gateway_network(listen, allow_cidr)
    if POINTER.exists():
        existing = load(POINTER)
        if process_identity(existing['pid']) == existing.get('start_ticks'):
            health = health_snapshot()
            print(json.dumps({'state':'EXISTING_SESSION_NO_DUPLICATE_STARTED','health':health},indent=2))
            if health['status'] != 'HEALTHY':
                raise SystemExit(1)
            return
    sensor.namespace_command()  # Fail before starting services if capture permission is unavailable.
    with (REPO / ".local-dev/hybrid-acceptance.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another owned demo/acceptance holds startup lock; use status. Lock file presence alone is harmless; do not delete it or start duplicates') from exc
    atomic_json(network_path, {'listen':listen,'allow_cidr':allow_cidr})
    if POINTER.exists():
        current = load(POINTER)
        if process_identity(current["pid"]) == current.get("start_ticks"):
            raise RuntimeError("Existing demo supervisor alive; use health/status/stop")
    root = REPO / ".local-dev" / ("demo-session-" + str(time.time_ns())[-12:])
    with (REPO / ".local-dev/demo-session-launch.log").open("ab") as log:
        p = subprocess.Popen(
            [
                sys.executable,
                str(REPO / "scripts/hybrid-system-acceptance.py"),
                "--action",
                "demo",
                "--root",
                str(root),
            ],
            cwd=REPO,
            env=os.environ
            | {
                "IDPS_DEMO_RUNTIME": str(RUNTIME),
                "IDPS_DEMO_CONTAINER_PREFIX": "idps-demo-v1",
                "IDPS_DEMO_LISTEN": listen,
                "IDPS_DEMO_ALLOW_CIDR": allow_cidr,
            },
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    atomic_json(
        POINTER,
        {"root": str(root), "pid": p.pid, "start_ticks": process_identity(p.pid)},
    )
    deadline = time.monotonic()+240
    last_progress = 0
    while time.monotonic()<deadline:
        if (root/'demo-ready.json').exists():
            health=health_snapshot()
            print(json.dumps(health,indent=2))
            if health['status']!='HEALTHY':
                raise SystemExit(1)
            return
        if process_identity(p.pid) is None:
            print(json.dumps({'status':'FAILED','reason':load(root/'demo-failure.json') if (root/'demo-failure.json').exists() else 'Supervisor exited; inspect logs','diagnostic':str(root/'demo-failure.json'),'workload_log':str(root/'guard/stderr.log'),'sensor_log':str(root/'sensor.log')},indent=2))
            raise SystemExit(1)
        if time.monotonic()-last_progress >= 10:
            phase = load(root/'wrapper-status.json').get('phase','PREPARING_DATABASES') if (root/'wrapper-status.json').exists() else 'PREPARING_DATABASES'
            print(f"[AI-IDPS] {phase}; chờ kiểm tra HTTP/AI/Suricata — {root}", file=sys.stderr, flush=True)
            last_progress = time.monotonic()
        time.sleep(.5)
    print(json.dumps({'status':'STARTUP_TIMEOUT','supervisor_pid':p.pid,'status_file':str(root/'wrapper-status.json'),'action':'Inspect status and logs; do not start a duplicate'},indent=2))
    raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=[
            "start",
            "credentials",
            "health",
            "normal",
            "test",
            "ai",
            "rules",
            "policy",
            "incident",
            "history",
            "response",
            "status",
            "stop",
            "manual-proof",
        ],
    )
    p.add_argument("--request-id")
    p.add_argument(
        "--listen", default=None, help="Specific host LAN IPv4; default loopback"
    )
    p.add_argument(
        "--allow-cidr", default=None, help="Authorized private lab subnet only"
    )
    p.add_argument("--operator-approved-isolated-client", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    if a.action == "credentials":
        secret = load(RUNTIME / 'credentials.json')
        print(json.dumps({
            'Student Web': {'url':(lan_urls() or ['http://127.0.0.1:18782'])[0]+'/login','username':'foundation-admin','password':secret['student_admin_password']},
            'Security Web': {'url':'http://127.0.0.1:3001/','username':'admin','password':secret['security_admin_password']},
            'AI/Suricata/NGINX': 'No separate login; use Security Web and demo CLI',
        },indent=2,ensure_ascii=False))
        return
    if a.action == "start":
        start(a.listen, a.allow_cidr)
        return
    if a.action in ["status", "stop", "manual-proof"]:
        pointer = (
            POINTER if POINTER.exists() else REPO / ".local-dev/demo-acceptance.json"
        )
        session = load(pointer)
        root = Path(session["root"])
        if a.action == "status":

            def read(name):
                return load(root / name) if (root / name).exists() else {}

            final = read("final-status.json")
            wrapper = read("wrapper-status.json")
            current = read("worker-status.json")
            guard = read("guard/resource-status.json")
            alive = process_identity(session["pid"]) == session.get("start_ticks")
            print(
                json.dumps(
                    {
                        "run_id": root.name,
                        "supervisor_alive": alive,
                        "supervisor": read("supervisor.json"),
                        "phase": current.get("phase")
                        if current.get("state") == "RUNNING"
                        else wrapper.get("phase"),
                        "heartbeat_age_seconds": round(
                            time.time()
                            - read("supervisor-heartbeat.json").get(
                                "heartbeat", time.time()
                            ),
                            1,
                        ),
                        "guard": guard,
                        "demo": read("demo-ready.json"),
                        "LAN_URLS": lan_urls() if read("demo-ready.json").get("listen") == "0.0.0.0" else [read("demo-ready.json").get("gateway")],
                        "local_release": final.get(
                            "local_release", "RUNNING" if alive else "STOPPED"
                        ),
                        "gates": final.get("gates"),
                        "failures": final.get("failures"),
                        "operator_proof": read("operator-proof-status.json"),
                        "evidence_directory": str(root),
                    },
                    indent=2,
                )
            )
            return
        if process_identity(session["pid"]) != session.get("start_ticks"):
            raise RuntimeError("Demo is already stopped; no process signaled")
        if a.action == "stop":
            (root / "STOP").touch(mode=0o600)
            print("GRACEFUL_STOP_REQUESTED; kiểm tra status, không xóa logs/DB")
            return
        if not a.operator_approved_isolated_client:
            raise RuntimeError(
                "Explicit --operator-approved-isolated-client required for actual firewall test"
            )
        if not (root / "demo-ready.json").exists():
            raise RuntimeError("Demo not ready")
        atomic_json(
            root / "OPERATOR_PROOF_REQUEST.json",
            {
                "operator_uid": os.getuid(),
                "approved_at": time.time(),
                "target": "DISPOSABLE_NAMESPACE_CLIENT_10.203.17.2_ONLY",
                "ttl_seconds": [15, 4],
                "actions": ["BLOCK", "UNBLOCK", "TTL_EXPIRY"],
                "host_firewall": False,
            },
        )
        print(
            "OPERATOR_APPROVAL_QUEUED; kết quả sẽ lưu trong status. Không tác động host firewall."
        )
        return
    if a.action == "health":
        value = health_snapshot()
        print(json.dumps(value,indent=2))
        if value['status']!='HEALTHY':
            raise SystemExit(1)
        return
    if a.action in ["normal", "test"]:
        session = load(POINTER)
        root = Path(session["root"])
        assert (root / "demo-ready.json").exists(), "Demo gateway not ready"
        query = (
            ""
            if a.action == "normal"
            else "?" + urllib.parse.urlencode({"search": "1' OR 1=1--"})
        )
        gateway = load(root / "demo-ready.json")["gateway"]
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            gateway + "/api/auth/csrf" + query, timeout=20
        ) as response:
            response.read()
            value = {
                "case": a.action,
                "http_status": response.status,
                "request_id": response.headers["X-Request-Id"],
                "gateway": "NGINX via isolated passive Suricata gateway",
                "time": time.time(),
                "scope": "harmless query to existing CSRF endpoint; no exploit-success claim",
            }
        atomic_json(RUNTIME / "last-demo-receipt.json", value)
        print(json.dumps(value, indent=2))
        return
    if a.action == "history":
        print(json.dumps(request("/api/hybrid-incidents", token=token()), indent=2))
        return
    rid = a.request_id or load(RUNTIME / "last-demo-receipt.json")["request_id"]
    if len(rid) != 32 or any(c not in "0123456789abcdef" for c in rid):
        raise RuntimeError("Invalid request_id")
    auth = token()
    if a.action in ["ai", "rules"]:
        page = request("/api/ai-shadow?request_id=" + rid, token=auth)
        value = page["items"] if a.action == "ai" else page["detectors"]
        presentation = None
        if a.action == "ai":
            incidents = request("/api/hybrid-incidents?request_id=" + rid, token=auth)[
                "incidents"
            ]
            incident = incidents[0] if incidents else None
            presentation = [
                {
                    "REQUEST_ID": v["request_id"],
                    "INCIDENT_ID": incident["request_id"] if incident else None,
                    "INCIDENT_ID_SEMANTICS": "actual hybrid_incidents primary key request_id",
                    "MODEL_ID": v["model_version"],
                    "MODEL_VERSION": v["model_version"],
                    "FEATURE_SCHEMA_VERSION": v["feature_profile"],
                    "EVENT_SCHEMA_VERSION": v["schema_version"],
                    "AI_SCORE": v["score"],
                    "AI_THRESHOLD": v["threshold"],
                    "AI_SIGNAL": "AI_UNAVAILABLE"
                    if v["score"] is None
                    else "ABOVE_THRESHOLD_UNCALIBRATED"
                    if v["above_threshold"]
                    else "BELOW_THRESHOLD_UNCALIBRATED",
                    "INFERENCE_STATUS": v["status"],
                    "INFERENCE_LATENCY_MS": v["latency_ms"],
                    "SOURCE_EVIDENCE_IDS": incident["evidence_ids"]
                    if incident
                    else ["ai:" + v["event_id"]],
                }
                for v in value
            ]
        print(
            json.dumps(
                {
                    "request_id": rid,
                    "incident_key": "request_id is the actual hybrid_incidents primary key",
                    "kind": "REAL_PERSISTED_INFERENCE"
                    if a.action == "ai"
                    else "REAL_DETECTOR_EVIDENCE",
                    "items": value,
                    "presentation_of_persisted_evidence": presentation,
                    "score_semantics": "uncalibrated research score, not attack probability",
                },
                indent=2,
            )
        )
        return
    if a.action in ["policy", "incident"]:
        print(
            json.dumps(
                request("/api/hybrid-incidents?request_id=" + rid, token=auth), indent=2
            )
        )
        return
    if a.action == "response":
        print(
            json.dumps(
                {
                    "queue_audit": request("/api/audit", token=auth),
                    "firewall": request("/api/blocked-ips", token=auth),
                    "default_mode": "OFF; manual tests require explicit operator command",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
