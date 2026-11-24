"""Real anonymous HTTPS through a private NGINX and the Rust development gate."""
import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import hmac
import os
from pathlib import Path
import re
import ssl
import socket
import subprocess
import tempfile
import threading
import time
from approve_session import initialize, publish
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def wait_for(check):
    for _ in range(100):
        if check():
            return
        time.sleep(0.03)
    raise RuntimeError("Temporary service did not become ready")


def stop(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)


def test(binary):
    observed = []

    class Origin(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append((self.path, self.headers.get("X-Request-Id")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    with tempfile.TemporaryDirectory() as work, ExitStack() as stack:
        root = Path(work)
        origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        stack.callback(origin.server_close)
        threading.Thread(target=origin.serve_forever, daemon=True).start()
        stack.callback(origin.shutdown)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-subj", "/CN=ws-dev-canary",
                        "-addext", "subjectAltName=IP:127.0.0.1",
                        "-keyout", str(root/"key"), "-out", str(root/"cert")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        tls = ssl.create_default_context(cafile=str(root/"cert"))
        sock = root / "gate.sock"
        issue = int(time.time())
        plan = json.loads(os.environ["WS_TEST_CANARY_PLAN"]) if "WS_TEST_CANARY_PLAN" in os.environ else {
            "action":"BLOCK_REQUEST","request_id":"a"*32,"selector":"dev-canary","issued":issue,"expires":issue+8}
        native = os.environ.get("WS_TEST_NATIVE") == "1"
        fixture_key, fixture_session = "a"*64, "1"*32
        if native:
            expected = hmac.new(fixture_key.encode(), ("session:"+fixture_session).encode(), hashlib.sha256).hexdigest()
            assert plan["selector"] == "request-"+expected
            (root/"session.key").write_text(fixture_key)
        trigger = plan["request_id"]
        state = root / "persistent"
        state.mkdir()
        initialize(state)
        def approve(cancel=False):
            window = None
            if not cancel and "WS_TEST_AUTO_START" in os.environ:
                start = int(os.environ["WS_TEST_AUTO_START"])
                window = (start, start+300)
            return publish(plan, trigger, "BLOCK_REQUEST", root, os.getgid(), cancel, state=state, auto_window=window,
                           native={"action":"BLOCK_REQUEST","ttl":15,"cooldown":60} if native else None)
        assert approve() == "APPROVED" and approve() == "ALREADY_ACTIVE"
        journal = stack.enter_context((root/"gate.log").open("w"))
        gate = subprocess.Popen([binary, "--dev-edge-gate"], stderr=journal, env=os.environ | {
            **({"WS_NATIVE_SESSION_KEY_FILE":str(root/"session.key")} if native else {}), "WS_DEV_GATE_DIR":work, "WS_DEV_GATE_LEASE_DIR":work})
        stack.callback(stop, gate)
        wait_for(sock.exists)
        snippet = Path(__file__).with_name("gate.conf.template").read_text().replace("@GATE_SOCKET@", str(sock))
        if native:
            snippet=snippet.replace("X-WS-Selector dev-canary;", "X-WS-Selector native-session; proxy_set_header X-WS-Session-Cookie $http_cookie;")
        config = root / "nginx.conf"
        config.write_text(f"""pid {root}/pid; error_log {root}/errors; events {{}}
http {{ log_format receipt '$request_id $status $upstream_status';
access_log {root}/access receipt; client_body_temp_path {root}/body; proxy_temp_path {root}/proxy;
fastcgi_temp_path {root}/fcgi; uwsgi_temp_path {root}/uwsgi; scgi_temp_path {root}/scgi;
upstream ws_dev_canary_origin {{server 127.0.0.1:{origin.server_port};}}
server {{listen 127.0.0.1:{port} ssl; ssl_certificate {root}/cert; ssl_certificate_key {root}/key;
add_header X-Request-Id $request_id always; proxy_set_header X-Request-Id $request_id; {snippet}
location / {{proxy_pass http://ws_dev_canary_origin;}} }} }}""")
        nginx = subprocess.Popen(["nginx","-p",work,"-c",str(config),"-g","daemon off;"])
        stack.callback(stop, nginx)
        wait_for((root/"pid").exists)

        receipts = {}
        def status(path, sid=None):
            request = Request(f"https://127.0.0.1:{port}" + path,
                              headers={"X-Request-Id":"f"*32, **({"Cookie":"JSESSIONID="+sid} if sid else {})})
            try:
                response = urlopen(request, context=tls, timeout=2)
            except HTTPError as err:
                response = err
            with response:
                rid = response.headers["X-Request-Id"]
                assert re.fullmatch("[a-f0-9]{32}", rid) and rid != "f"*32 and rid not in receipts
                receipts[rid] = response.status
                return response.status

        canary = "/__ws_dev__/canary"
        for path in ["/", "/normal", "/assets/app.js", "/api/profile-options"] * 3:
            assert status(path) == 204
        if native:
            assert status(canary,"2"*32)==204
            assert status(canary)==204
        before = len(observed)
        assert status(canary,fixture_session if native else None) == 403 and len(observed) == before
        denied = next(rid for rid,code in receipts.items() if code==403)
        assert f"trigger={trigger} request={denied} " in (root/"gate.log").read_text()
        time.sleep(max(0,plan["expires"]-time.time())+.05)
        assert status(canary,fixture_session if native else None) == 204
        assert approve(cancel=True) == "REVOKED"
        try:
            approve()
        except ValueError:
            pass
        else:
            raise AssertionError("revoked lease reactivated")
        stop(gate)
        assert status(canary) == 500
        assert status("/normal") == 204
        lines = (root/"access").read_text().splitlines()
        forwarded = {rid for _,rid in observed}
        for rid, code in receipts.items():
            upstream = "204" if code == 204 else "-"
            assert f"{rid} {code} {upstream}" in lines
            assert (rid in forwarded) == (code == 204)
        print("PASS HTTPS with trusted SAN: benign blocked 0/12, canary blocked 1/1,"
              f" expiry 204, gate outage 500 on canary only; {len(receipts)} unique response IDs matched access log/upstream")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    test(parser.parse_args().binary.resolve())
