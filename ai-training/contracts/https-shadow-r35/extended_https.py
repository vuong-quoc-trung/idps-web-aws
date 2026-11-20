"""Bounded benign HTTPS workflows for the Local acceptance profile."""

import http.client
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.parse import urlencode


def exercise(context, requests, username, password, stop_sensor, restart_sensor):
    def connection():
        return http.client.HTTPSConnection(
            "127.0.0.1", 18443, context=context, source_address=("192.0.2.10", 0), timeout=10
        )

    lock = threading.Lock()

    def exchange(c, method, route, status, label, headers=None, body=None):
        start = time.monotonic_ns()
        c.request(method, route, body=body, headers=headers or {})
        res = c.getresponse()
        payload = res.read(65536)
        elapsed = time.monotonic_ns() - start
        rid = res.getheader("X-Request-Id")
        if res.status != status or not rid or res.getheader("X-WS-Receipt"):
            raise ValueError(f"Unexpected HTTP outcome for {label}: {res.status}")
        with lock:
            if rid in requests:
                raise ValueError("Duplicate trusted request ID")
            requests[rid] = dict(
                method=method,
                route=route,
                status=status,
                oracle=label,
                http_ms=round(elapsed / 1e6, 3),
            )
        return rid, payload, res.getheader("Set-Cookie", "").split(";", 1)[0]

    with closing(connection()) as c:
        _, response, initial = exchange(c, "GET", "/api/auth/csrf", 200, "SESSION_CSRF")
        token = json.loads(response)["token"]
        assert initial.startswith("JSESSIONID=") and token
        _, _, current = exchange(
            c,
            "POST",
            "/api/auth/login",
            204,
            "SESSION_LOGIN_ROTATION",
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": initial,
                "X-CSRF-TOKEN": token,
            },
            urlencode(dict(username=username, password=password)),
        )
        assert current.startswith("JSESSIONID=") and current != initial
        headers = {"Cookie": current}
        _, response, _ = exchange(c, "GET", "/api/auth/me", 200, "PRINCIPAL_ADMIN", headers)
        principal = json.loads(response)
        assert (
            principal["username"] == username
            and principal["role"] == "ADMIN"
            and principal["enabled"] is True
        )
        exchange(c, "HEAD", "/api/me/profile", 403, "ROLE_DENIED", headers)
        _, response, _ = exchange(c, "GET", "/api/auth/csrf", 200, "AUTHENTICATED_CSRF", headers)
        token = json.loads(response)["token"]
        exchange(
            c,
            "POST",
            "/api/auth/logout",
            204,
            "AUTHENTICATED_LOGOUT",
            dict(headers, **{"X-CSRF-TOKEN": token}),
        )
        exchange(c, "GET", "/api/auth/me", 401, "SESSION_REVOKED", headers)
    stop_sensor()
    with closing(connection()) as c:
        missing, _, _ = exchange(
            c, "GET", "/api/auth/me?stage=recovery", 401, "ANONYMOUS_SENSOR_OFFLINE"
        )
    recovery = restart_sensor()
    clients = 4
    per_client = 4
    gate = threading.Barrier(clients, timeout=8)

    def burst(client):
        with closing(connection()) as c:
            gate.wait()
            port = None
            for i in range(per_client):
                path = f"/api/auth/me?view={client}&page={i}"
                exchange(c, "GET" if i % 2 == 0 else "HEAD", path, 401, "ANONYMOUS_CHALLENGE")
                current_port = c.sock.getsockname()[1] if c.sock else None
                if current_port is None or (port is not None and port != current_port):
                    raise ValueError("Client keep-alive socket was not retained")
                port = current_port
            return port

    begin = time.monotonic()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        sockets = set(pool.map(burst, range(clients)))
    duration = time.monotonic() - begin
    assert len(sockets) == clients
    return dict(
        concurrent_clients=clients,
        burst_requests=clients * per_client,
        reused_client_connections=len(sockets),
        burst_seconds=duration,
        burst_requests_per_second=clients * per_client / duration,
        sensor_unavailable_request=missing,
        **recovery,
    )
