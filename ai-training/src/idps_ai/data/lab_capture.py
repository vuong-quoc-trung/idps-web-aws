"""Bounded Student lab observer. Uses only an explicitly owned loopback fixture.

No production credentials, scanning, mail/reset workflows or external targets.
Ground truth describes runner intent/expected HTTP outcome, never exploit success.
"""

import http.client
import json
import random
import re
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256

ROLES = [
    "STAFF",
    "STUDENT",
    "ADMIN",
    "STAFF",
    "STUDENT",
    "STAFF",
    "STUDENT",
    "STAFF",
    "STUDENT",
    "STAFF",
    "ADMIN",
    "STUDENT",
    "STAFF",
    "STUDENT",
    "ADMIN",
]
PAYLOADS = {
    "sqli": ["1' OR 1=1--", "UNION SELECT 1,2", "pg_sleep(1)"],
    "xss": ["<script>lab</script>", "<img src=x onerror=alert(1)>", "javascript:alert(1)"],
    "path_traversal": ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "/.git/HEAD"],
    "cmd_injection": ["ok;whoami", "$(uname)", "ok&&id"],
}


class LabClient:
    def __init__(self, port, source_ip):
        if port not in (18881, 18882) or not re.fullmatch(
            r"127\.0\.0\.(?:[1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-4])", source_ip
        ):
            raise PipelineError("Lab client is restricted to owned loopback fixtures")
        self.port, self.source_ip = port, source_ip
        self.cookies = {}
        self.csrf = None

    def request(self, method, path, body=None, agent="Mozilla Firefox", csrf=True):
        if not path.startswith("/") or any(c in path for c in "\r\n") or len(path) > 2048:
            raise PipelineError("Invalid bounded lab request")
        headers = {"User-Agent": agent, "Connection": "close"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if body is not None:
            headers["Content-Type"] = (
                "application/x-www-form-urlencoded" if isinstance(body, str) else "application/json"
            )
            body = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        if csrf and self.csrf:
            headers[self.csrf["headerName"]] = self.csrf["token"]
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=5, source_address=(self.source_ip, 0)
        )
        start = time.time()
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            data = response.read(512 * 1024 + 1)
            if len(data) > 512 * 1024:
                raise PipelineError("Lab response body cap exceeded")
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    cookie = SimpleCookie()
                    cookie.load(value)
                    for k, v in cookie.items():
                        self.cookies[k] = v.value
            request_id = response.getheader("X-Request-Id")
            if not request_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
                raise PipelineError("Lab edge did not return a bounded request ID")
            record = {
                "request_id": request_id,
                "timestamp": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                "status_code": response.status,
                "http_method": method,
                "latency_ms": (time.time() - start) * 1000,
            }
            return record, data
        finally:
            connection.close()


def run_campaigns(lab_dir, requests_per_campaign=320, gap_seconds=620):
    lab = Path(lab_dir).resolve()
    marker = json.loads((lab / "owned-lab.json").read_text())
    if (
        marker.get("purpose") != "ai-pretrain-disposable"
        or marker.get("edge_port") != 18881
        or not marker.get("source_commit")
    ):
        raise PipelineError("An explicitly owned disposable lab is required")
    if requests_per_campaign < 160 or requests_per_campaign > 640 or gap_seconds < 610:
        raise PipelineError("Use 160–640 requests per campaign and >=610s temporal gaps")
    observer = lab / "observer.jsonl"
    if observer.exists():
        raise PipelineError(
            "Observer exists; choose a fresh capture, never append a new experiment"
        )
    password = json.loads((lab / "accounts-private.json").read_text())["password"]
    rng = random.Random(27102026)
    started = time.time()
    counts = {}
    with observer.open("x") as stream:
        observer.chmod(0o600)

        def observe(
            client,
            method,
            path,
            family="benign",
            scenario="benign_read",
            expected=(200,),
            body=None,
            agent="Mozilla Firefox",
            csrf=True,
            campaign=None,
            variant=None,
        ):
            record, data = client.request(method, path, body, agent, csrf)
            record.update(
                campaign_id=campaign,
                attack_family=family,
                label=int(family != "benign"),
                label_source="scenario_manifest",
                label_confidence=1.0,
                review_status="approved" if record["status_code"] in expected else "pending",
                scenario=scenario,
                variant_group=variant or scenario,
                expected_status_codes=list(expected),
                intent="benign_workflow" if family == "benign" else "attack_attempt",
                exploit_success="not_asserted",
            )
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            counts[family] = counts.get(family, 0) + 1
            return record, data

        for campaign in range(15):
            phase = 0 if campaign < 9 else 1 if campaign < 12 else 2
            if campaign in (9, 12):
                deadline = time.time() + gap_seconds
                atomic_json(
                    lab / "capture-progress.json",
                    {
                        "stage": "temporal_embargo_wait",
                        "next_campaign": campaign,
                        "resume_after_unix": deadline,
                        "captured": sum(counts.values()),
                        "real_training_hours": 0,
                    },
                )
                while time.time() < deadline:
                    if (lab / "STOP").exists():
                        raise PipelineError("Lab collection stopped by operator")
                    time.sleep(min(1, max(0, deadline - time.time())))
            cid = f"lab-{marker['capture_id']}-{campaign:02d}"
            client = LabClient(18881, f"127.0.0.{campaign + 10}")

            def send(*a, **kw):
                return observe(client, *a, **kw, campaign=cid)

            # Benign setup outcomes are observable; response bodies/cookies/password never persisted.
            _, data = send("GET", "/api/auth/csrf", scenario="csrf_setup", expected=(200,))
            client.csrf = json.loads(data)
            send(
                "POST",
                "/api/auth/login",
                scenario="fixture_login",
                expected=(204,),
                body=urlencode({"username": f"ai_lab_{campaign:02d}", "password": password}),
            )
            _, data = send("GET", "/api/auth/csrf", scenario="csrf_refresh", expected=(200,))
            client.csrf = json.loads(data)
            auth_client = LabClient(18881, f"127.0.0.{campaign + 10}")
            _, auth_data = observe(
                auth_client,
                "GET",
                "/api/auth/csrf",
                scenario="auth_probe_csrf_setup",
                expected=(200,),
                campaign=cid,
            )
            auth_client.csrf = json.loads(auth_data)
            cases = ["benign"] * (requests_per_campaign - 7 * 16) + [
                family for family in CLASSES[1:] for _ in range(16)
            ]
            rng.shuffle(cases)
            for index, family in enumerate(cases):
                if (lab / "STOP").exists():
                    raise PipelineError("Lab collection stopped by operator")
                if family == "benign":
                    choice = index % 8
                    if choice == 0:
                        send(
                            "POST",
                            "/api/faculties",
                            scenario="fake_faculty_create",
                            expected=(201,) if ROLES[campaign] != "STUDENT" else (403,),
                            body={
                                "shortCode": f"AI{campaign:02d}{index:03d}",
                                "name": f"AI lab fixture {campaign}-{index}",
                                "description": "Synthetic disposable fixture only",
                                "active": True,
                            },
                        )
                    elif choice == 1:
                        send(
                            "GET",
                            "/api/faculties?"
                            + urlencode(
                                {
                                    "q": rng.choice(
                                        [
                                            "student union meeting",
                                            "O'Connor",
                                            "Nguyễn thử nghiệm",
                                            "100% progress",
                                        ]
                                    )
                                }
                            ),
                            scenario="hard_negative_search",
                            expected=(200,),
                        )
                    elif choice == 2:
                        send(
                            "GET",
                            "/api/me/profile",
                            scenario="role_specific_read",
                            expected=(200, 404) if ROLES[campaign] == "STUDENT" else (403,),
                        )
                    elif choice == 3:
                        send(
                            "GET",
                            "/api/faculties/99999999",
                            scenario="benign_missing_record",
                            expected=(404,),
                        )
                    else:
                        send(
                            rng.choice(["GET", "HEAD", "OPTIONS"]),
                            rng.choice(
                                [
                                    "/api/faculties",
                                    "/api/majors",
                                    "/api/classes",
                                    "/api/training-programs",
                                ]
                            ),
                            scenario="benign_catalog",
                            expected=(200, 204),
                        )
                elif family in PAYLOADS:
                    payload = PAYLOADS[family][phase]
                    send(
                        "GET",
                        "/api/faculties?" + urlencode({"q": payload}),
                        family=family,
                        scenario="bounded_uri_probe",
                        expected=(200, 400, 403),
                        variant=f"{family}-heldout-view-{phase}",
                    )
                elif family == "scanner_recon":
                    send(
                        "GET",
                        "/api/faculties?q=lab",
                        family=family,
                        scenario="scanner_agent_probe",
                        expected=(200,),
                        agent=["sqlmap/1.0", "nikto/2.0", "nuclei/3.0"][phase],
                        variant=f"scanner-heldout-view-{phase}",
                    )
                elif family == "brute_force":
                    observe(
                        auth_client,
                        "POST",
                        "/api/auth/login",
                        campaign=cid,
                        family=family,
                        scenario="invalid_lab_login_attempt",
                        expected=(401, 429),
                        body=urlencode(
                            {
                                "username": f"no_such_lab_{campaign}",
                                "password": "lab-invalid-password-only",
                            }
                        ),
                        variant=f"auth-heldout-view-{phase}",
                    )
                else:
                    # A predeclared scripted bulk-read attempt, not proof of an actual exploit.
                    send(
                        "GET",
                        "/api/students?" + urlencode({"page": index % 4, "size": 20}),
                        family=family,
                        scenario="scripted_bulk_read_attempt",
                        expected=(200,) if ROLES[campaign] != "STUDENT" else (403,),
                        variant=f"bulk-heldout-view-{phase}",
                    )
                time.sleep(rng.uniform(0.04, 0.07))
            send("POST", "/api/auth/logout", scenario="fixture_logout", expected=(204,))
            atomic_json(
                lab / "capture-progress.json",
                {
                    "stage": "collecting",
                    "completed_campaigns": campaign + 1,
                    "captured": sum(counts.values()),
                    "label_intent_counts": counts,
                    "real_training_hours": 0,
                },
            )
    result = {
        "format_version": 1,
        "capture_id": marker["capture_id"],
        "data_kind": "lab_capture",
        "started_at_unix": started,
        "ended_at_unix": time.time(),
        "campaigns": 15,
        "requests": sum(counts.values()),
        "intent_counts": counts,
        "observer_sha256": file_sha256(observer),
        "source_commit": marker["source_commit"],
        "authenticity": "Actual HTTP against isolated Student build and disposable PostgreSQL with synthetic accounts/objects; not production traffic",
        "label_semantics": "Scripted intent + observed HTTP expectation; pending on unexpected status; no exploit success claim",
        "limits": [
            "Loopback identities are distinct actual bound source addresses, not forged headers",
            "3 ADMIN/6 STAFF/6 STUDENT fixtures; no real profiles or personal records",
            "Behavioral label denotes scripted attempt, not verified real-world abuse",
            "Payload variants differ across temporal bands; only three views per family, not representative coverage",
        ],
        "real_training_hours": 0,
    }
    atomic_json(lab / "capture-result.json", result)
    return result
