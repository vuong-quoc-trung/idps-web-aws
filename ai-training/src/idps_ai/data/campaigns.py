"""Long real-time campaigns against AI-owned fixtures; labels describe intent only."""

import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.lab_capture import ROLES, LabClient

# Views are assigned before collection, never selected from detector output.
VIEWS = {
    "sqli": [
        ["1' OR 2=2--", "UNION ALL SELECT 7,8", "1 AND sleep(0)--", "1/**/OR/**/3=3"],
        ["2' OR 'a'='a", "uNiOn SELECT NULL", "pg_sleep(0)", "extractvalue(1,1)"],
        ["1 OR 7>2#", "UNION DISTINCT SELECT 9", "benchmark(0,md5(1))", "' AND 4=4--"],
    ],
    "xss": [
        [
            "<script>labA</script>",
            "<img src=a onerror=alert(7)>",
            "javascript:alert(7)",
            "<svg onload=alert(7)>",
        ],
        [
            "<ScRiPt>labB</ScRiPt>",
            "<body onload=alert(8)>",
            "javascript:confirm(8)",
            "<img src=b onerror=confirm(8)>",
        ],
        [
            "<script>labC</script>",
            "<svg onload=confirm(9)>",
            "javascript:prompt(9)",
            "<img src=c onerror=prompt(9)>",
        ],
    ],
    "path_traversal": [
        ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "/.git/HEAD", "/.env"],
        ["../../../etc/hosts", "%2e%2e/%2e%2e/etc/passwd", "/.git/config", "../config/.env"],
        [
            "../../../../etc/shadow",
            "%252e%252e%252fetc/passwd",
            "/private/.env",
            "/repo/.git/index",
        ],
    ],
    "cmd_injection": [
        ["a;whoami", "a&&id", "$(uname)", "`id`"],
        ["b;id", "b||whoami", "$(whoami)", "`uname`"],
        ["c;uname", "c&&whoami", "$(id)", "c|id"],
    ],
}
AGENTS = [
    ["sqlmap/1", "nikto/2", "nmap/7", "gobuster/3"],
    ["nuclei/3", "ffuf/2", "dirbuster/1", "masscan/1"],
    ["acunetix/1", "zgrab/2", "sqlmap/2", "nikto/3"],
]


def campaign_plan(band, count=1280, duration=420):
    if band not in (0, 1, 2) or not 640 <= count <= 2048 or not 360 <= duration <= 900:
        raise PipelineError("Campaigns require 640–2048 requests and 360–900 real seconds")
    families = ["benign"] * (count - 7 * 32) + [f for f in CLASSES[1:] for _ in range(32)]
    rng = random.Random(281000 + band)
    rng.shuffle(families)
    plan = []
    for i, family in enumerate(families):
        scenario = (
            "benign_login_typo"
            if i % 47 == 0
            else "hard_negative_search"
            if i % 5 == 0
            else "benign_workflow"
        )
        plan.append(
            {
                "family": family,
                "scenario": scenario if family == "benign" else family,
                "variant_group": f"{family}-band-{band}-view-{i % 4}",
                "view": i % 4,
                "at_seconds": i * duration / (count - 1),
            }
        )
    # Explicit consecutive auth/bulk bursts, with legitimate singleton failures elsewhere.
    for family, endpoint in [("brute_force", duration - 20), ("behavioral_anomaly", duration - 10)]:
        burst = [x for x in plan if x["family"] == family]
        for j, case in enumerate(burst):
            case["at_seconds"] = endpoint + j * 0.08
    return sorted(plan, key=lambda c: c["at_seconds"])


def run_extended_campaigns(directory, count=1280, duration=420, gap=620):
    lab = Path(directory).resolve()
    marker = load_json(lab / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable" or gap < 610:
        raise PipelineError("Owned lab and real embargo >=610 seconds required")
    observer = lab / "observer.jsonl"
    if observer.exists():
        raise PipelineError("Observer already exists; capture versions are immutable")
    password = load_json(lab / "accounts-private.json")["password"]
    lock = threading.Lock()
    counts, campaigns = {}, []
    started = time.time()
    with observer.open("x") as stream:
        observer.chmod(0o600)

        def campaign(index, band):
            cid = f"extended-{marker['capture_id']}-{index:02d}"
            source_ip = f"127.0.0.{index + 10}"
            client = LabClient(18881, source_ip)
            auth = LabClient(18881, source_ip)

            def send(
                target,
                method,
                path,
                family="benign",
                scenario="benign_workflow",
                expected=(200,),
                body=None,
                agent="Mozilla Firefox",
                variant="benign",
            ):
                record, data = target.request(method, path, body, agent)
                record.update(
                    campaign_id=cid,
                    attack_family=family,
                    label=int(family != "benign"),
                    label_source="scenario_manifest",
                    label_confidence=1.0,
                    review_status="approved" if record["status_code"] in expected else "pending",
                    scenario=scenario,
                    variant_group=variant,
                    expected_status_codes=list(expected),
                    intent="benign_workflow" if family == "benign" else "attack_attempt",
                    exploit_success="not_asserted",
                )
                with lock:
                    stream.write(json.dumps(record, sort_keys=True) + "\n")
                    stream.flush()
                    counts[family] = counts.get(family, 0) + 1
                return data

            for target in (client, auth):
                target.csrf = json.loads(
                    send(target, "GET", "/api/auth/csrf", scenario="csrf_setup")
                )
            send(
                client,
                "POST",
                "/api/auth/login",
                scenario="fixture_login",
                expected=(204,),
                body=urlencode({"username": f"ai_lab_{index:02d}", "password": password}),
            )
            client.csrf = json.loads(send(client, "GET", "/api/auth/csrf", scenario="csrf_refresh"))
            start = time.monotonic()
            for i, case in enumerate(campaign_plan(band, count, duration)):
                while (remaining := start + case["at_seconds"] - time.monotonic()) > 0:
                    if (lab / "STOP").exists():
                        raise PipelineError("Capture stopped by operator; no completed dataset")
                    time.sleep(min(0.5, remaining))
                if (lab / "STOP").exists():
                    raise PipelineError("Capture stopped by operator")
                family, view = case["family"], case["view"]
                kw = dict(family=family, scenario=case["scenario"], variant=case["variant_group"])
                if family in VIEWS:
                    send(
                        client,
                        "GET",
                        "/api/faculties?" + urlencode({"q": VIEWS[family][band][view]}),
                        expected=(200, 400, 403),
                        **kw,
                    )
                elif family == "scanner_recon":
                    send(client, "GET", "/api/faculties?q=fixture", agent=AGENTS[band][view], **kw)
                elif family == "brute_force" or case["scenario"] == "benign_login_typo":
                    send(
                        auth,
                        "POST",
                        "/api/auth/login",
                        expected=(401, 429),
                        body=urlencode(
                            {
                                "username": f"no_such_fixture_{index}",
                                "password": "invalid-fixture-only",
                            }
                        ),
                        **kw,
                    )
                elif family == "behavioral_anomaly":
                    send(
                        client,
                        "GET",
                        "/api/students?" + urlencode({"page": i % 9, "size": 20}),
                        expected=(403,) if ROLES[index] == "STUDENT" else (200,),
                        **kw,
                    )
                elif case["scenario"] == "hard_negative_search":
                    queries = [
                        "O'Connor",
                        "Nguyễn thử nghiệm",
                        "student union meeting",
                        "100% progress & safety",
                        "select course and subject",
                        "campus-nmaple",
                        "javascript textbook",
                        "C++ && mathematics",
                    ]
                    send(
                        client,
                        "GET",
                        "/api/faculties?" + urlencode({"q": queries[i % len(queries)]}),
                        **kw,
                    )
                elif i % 17 == 0:
                    send(
                        client,
                        "POST",
                        "/api/faculties",
                        body={
                            "shortCode": f"EX{index:02d}{i:04d}",
                            "name": f"Fixture {index}-{i}",
                            "description": "AI disposable fixture",
                            "active": True,
                        },
                        expected=(403,) if ROLES[index] == "STUDENT" else (201,),
                        **kw,
                    )
                elif i % 13 == 0:
                    send(client, "GET", "/api/faculties/99999999", expected=(404,), **kw)
                elif i % 11 == 0:
                    send(
                        client,
                        "GET",
                        "/api/me/profile",
                        expected=(200, 404) if ROLES[index] == "STUDENT" else (403,),
                        **kw,
                    )
                else:
                    method = ["GET", "HEAD", "OPTIONS"][i % 3]
                    send(
                        client,
                        method,
                        ["/api/faculties", "/api/majors", "/api/classes", "/api/training-programs"][
                            i % 4
                        ],
                        expected=(200,) if method == "GET" else (200, 204, 403),
                        **kw,
                    )
            send(client, "POST", "/api/auth/logout", scenario="fixture_logout", expected=(204,))
            with lock:
                campaigns.append(
                    {"campaign": index, "band": band, "duration_seconds": time.monotonic() - start}
                )
                atomic_json(
                    lab / "capture-progress.json",
                    {
                        "stage": "collecting",
                        "completed_campaigns": len(campaigns),
                        "captured": sum(counts.values()),
                        "label_intent_counts": counts,
                    },
                )

        for band, indices in enumerate((range(9), range(9, 12), range(12, 15))):
            if band:
                deadline = time.monotonic() + gap
                atomic_json(
                    lab / "capture-progress.json",
                    {
                        "stage": "temporal_embargo_wait",
                        "next_band": band,
                        "captured": sum(counts.values()),
                        "wait_seconds": gap,
                    },
                )
                while time.monotonic() < deadline:
                    if (lab / "STOP").exists():
                        raise PipelineError("Capture stopped during embargo")
                    time.sleep(min(1, max(0, deadline - time.monotonic())))
            atomic_json(
                lab / "capture-progress.json",
                {
                    "stage": "collecting",
                    "band": band,
                    "completed_campaigns": len(campaigns),
                    "captured": sum(counts.values()),
                },
            )
            with ThreadPoolExecutor(max_workers=len(indices)) as pool:
                for future in [pool.submit(campaign, i, band) for i in indices]:
                    future.result()
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
        "campaign_durations": sorted(campaigns, key=lambda c: c["campaign"]),
        "query_profile": "edge_masked_v1",
        "real_training_hours": 0,
        "label_semantics": "Scripted intent + expected HTTP outcome; no exploit success assertion",
        "limits": [
            "Isolated real HTTP with fictional records; not production traffic",
            "No independent human realism/label review",
            "Payloads masked consistently; no claim to see hidden query payloads",
        ],
    }
    atomic_json(lab / "capture-result.json", result)
    return result
