"""Fresh time-held-out fixture cohort with new grammars and hard negatives.

Never targets an unowned service. Labels mean runner intent, not exploit success.
Only a single new held-out temporal cohort; concurrent clients are not independent
deployment environments. Raw targets are not written to the observer.
"""

import json
import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.lab_capture import LabClient

PAYLOADS = {
    "sqli": [
        "0/**/oR/**/17 BETWEEN 9 AND 23--",
        "1 AND ASCII(SUBSTR((SELECT CURRENT_USER),1,1))>32",
        "1' UNION SELECT CAST(NULL AS CHAR)--",
        "9' OR 'note' LIKE 'n%'--",
    ],
    "xss": [
        "<details open ontoggle=confirm(23)>",
        "<svg><animate onbegin=alert(23)>",
        '" autofocus onfocus=confirm(23) x="',
        "<iframe srcdoc='<script>confirm(23)</script>'>",
    ],
    "path_traversal": [
        "..\\..\\Windows\\win.ini",
        ".%2e/%2e./opt/config/application.yml",
        "../../srv/app/config/settings.ini",
        "..%252f..%252fproc/self/cmdline",
    ],
    "cmd_injection": [
        "x;printf${IFS}LAB_CHECK",
        "x$(printf LAB_CHECK)",
        "value|/usr/bin/printf LAB_CHECK",
        "note&&printf${IFS}LAB_CHECK",
    ],
}
HARD_NEGATIVES = [
    "a lecture discussing OR and BETWEEN in SQL",
    "book title: SELECT learning objectives",
    "please display the literal string <details> in documentation",
    "client-side onfocus handler explained safely",
    "C shell tutorial uses $(printf example)",
    "Windows path notation ..\\..\\manual in textbook",
    "union membership and project selection",
    "50% completion; report && review requested",
    "SPARQL SELECT ?article WHERE { ?article a ?kind } LIMIT 10",
    'JSON sample {"operator":"OR","value":17}',
    "Giáo trình truy vấn và lập trình giao diện",
    "O'Reilly's database and scripting catalogue",
]

SECOND_PAYLOADS = {
    "sqli": [
        "7 HAVING MIN(7)>0#",
        "7' AND COALESCE(NULL,19)=19#",
        "7 ORDER BY CASE WHEN 3=3 THEN 1 ELSE 2 END",
        "7' UNION ALL SELECT CONCAT(CHAR(65),CHAR(66))#",
    ],
    "xss": [
        "<marquee onstart=print()>",
        "<video><source onerror=confirm(37)>",
        "<math href='javascript:confirm(37)'>text</math>",
        "<select autofocus onfocus=print()><option>one",
    ],
    "path_traversal": [
        "..%5c..%5cboot.ini",
        "%252e%252e%252f%252e%252e%252fvar/log/auth.log",
        "..././..././etc/hosts",
        "../../../../usr/local/etc/service.conf",
    ],
    "cmd_injection": [
        "text;echo${IFS}VERIFY_ONLY",
        "text`echo VERIFY_ONLY`",
        "text||echo VERIFY_ONLY",
        "text%0aecho${IFS}VERIFY_ONLY",
    ],
}
SECOND_NEGATIVES = [
    "Shopping list: bread; milk; fruit. Please print a receipt.",
    "A textbook explains HAVING and GROUP BY in natural language.",
    "HTML manual: <video controls> requires a <source> child element.",
    "Windows tutorial names boot.ini and folder \\manual\\chapter.",
    "Search notes about CONCAT and COALESCE, neither is a submitted SQL command.",
    "Documentation displays `echo example` as quoted shell syntax.",
    "A boolean logic lecture covers OR, AND, NOT and cases 1=1.",
    "Meeting notes: status=ready && reviewed; priority high.",
    "Dictionary entry about ../ as a relative path in a programming guide.",
    "Phần hướng dẫn truy vấn, dấu ngoặc và ký hiệu trong tài liệu.",
    "Literature query: O'Connor & Sons, edition 2026.",
    "The browser example spells javascript: without executing a link.",
]


THIRD_PAYLOADS = {
    "sqli": [
        "5' AND NULLIF(23,24)=23--",
        "5 UNION DISTINCT SELECT HEX(25)#",
        "5' OR LENGTH('sample')>2#",
        "5 AND EXISTS(SELECT 23)",
    ],
    "xss": [
        "<object data='javascript:confirm(59)'>",
        "<input onpointerenter=confirm(59)>",
        "<style onload=print()></style>",
        "<a href='&#106;avascript:print()'>go</a>",
    ],
    "path_traversal": [
        "../../../etc/resolv.conf",
        "..%2f..%2fusr/share/config.txt",
        "..\\..\\ProgramData\\settings.ini",
        "%2e%2e/%2e%2e/var/lib/app/config.yml",
    ],
    "cmd_injection": [
        "value;printf${IFS}ONLY_TEST",
        "value$(echo ONLY_TEST)",
        "value|echo${IFS}ONLY_TEST",
        "value&&echo${IFS}ONLY_TEST",
    ],
}
THIRD_NEGATIVES = [
    "The lecture compares NULLIF and EXISTS as database language concepts.",
    "HTML reference describes object and input elements in a textbook.",
    "A shell guide explains pipes | and echo without submitting commands.",
    "The path ../../../manual is printed as an example in programming notes.",
    "A chapter about escaping ampersands & and quotes in ordinary text.",
    "Please find documents about pointer events and onpointerenter examples.",
    "Example CSV: number, name, course; no executable instructions.",
    "A book entitled Hex and the Art of Database Queries.",
    "Tìm giáo trình về dữ liệu, mạng máy tính và lập trình giao diện.",
    "Administrative notes: completed && reviewed | pending; literal punctuation.",
    "A catalog title about Unix configuration files and resolv.conf.",
    "Explanation of javascript: links in a security awareness handbook.",
]


def challenge_plan(seed, count=640, duration=360, generation=1):
    if not 320 <= count <= 1280 or not 360 <= duration <= 900:
        raise PipelineError("Held-out cohort requires320–1280requests and360–900real seconds")
    rng = random.Random(seed)
    if generation not in (1, 2, 3):
        raise PipelineError("Unknown challenge generation")
    payloads = {1: PAYLOADS, 2: SECOND_PAYLOADS, 3: THIRD_PAYLOADS}[generation]
    negatives = {1: HARD_NEGATIVES, 2: SECOND_NEGATIVES, 3: THIRD_NEGATIVES}[generation]
    families = [
        f
        for f in (*PAYLOADS, "scanner_recon", "brute_force", "behavioral_anomaly")
        for _ in range(24)
    ]
    families += ["benign"] * (count - len(families))
    rng.shuffle(families)
    increments = [rng.lognormvariate(0, 0.8) for _ in range(count - 1)]
    total, clock, plan = sum(increments), 0, []
    for i, family in enumerate(families):
        if i:
            clock += duration * increments[i - 1] / total
        payload = rng.choice(payloads[family]) if family in payloads else rng.choice(negatives)
        # Meaningful numeric variation, no suffix that acts as a class flag.
        fields = [
            (rng.choice(("term", "hint", "criteria", "descriptionText")), payload),
            ("page", str(rng.randrange(5))),
            ("limit", str(rng.choice((10, 15, 25)))),
        ]
        rng.shuffle(fields)
        plan.append(
            {
                "at_seconds": clock,
                "family": family,
                "target": "/api/"
                + rng.choice(("faculties", "majors", "classes"))
                + "?"
                + urlencode(fields),
                "variant": digest({"family": family, "payload": payload}),
                "hard_negative": family == "benign" and rng.random() < 0.55,
                "workflow": rng.randrange(8),
            }
        )
    return plan


def run_challenge(directory, count=640, duration=360):
    lab = Path(directory)
    marker = load_json(lab / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable" or marker.get("scenario_version") not in (
        "request-challenge-1",
        "request-challenge-2",
        "request-challenge-3",
    ):
        raise PipelineError("An explicitly owned challenge lab is required")
    observer = lab / "observer.jsonl"
    if observer.exists():
        raise PipelineError("Held-out captures cannot append or replay an existing observer")
    password = load_json(lab / "accounts-private.json")["password"]
    seed = marker["scenario_seed"]
    lock, counts, campaigns = threading.Lock(), Counter(), []
    started = time.time()
    with observer.open("x") as stream:
        observer.chmod(0o600)

        def campaign(index):
            client, auth = (
                LabClient(18881, f"127.0.0.{210 + index}"),
                LabClient(18881, f"127.0.0.{210 + index}"),
            )
            role = marker["roles"][index]
            cid = f"request-challenge-{marker['capture_id']}-{index}"
            local_seed = seed + index * 100003
            generation = int(marker["scenario_version"].rsplit("-", 1)[1])
            plan = challenge_plan(local_seed, count, duration, generation)
            rng = random.Random(local_seed + 17)

            def send(
                target,
                method,
                path,
                family="benign",
                expected=(200,),
                body=None,
                agent="Mozilla Firefox",
                scenario="legitimate_workflow",
                variant=None,
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
                    variant_group=variant
                    or digest({"method": method, "path": path.split("?")[0], "scenario": scenario}),
                    expected_status_codes=list(expected),
                    intent="attack_attempt" if family != "benign" else "benign_workflow",
                    exploit_success="not_asserted",
                )
                with lock:
                    stream.write(json.dumps(record, sort_keys=True) + "\n")
                    stream.flush()
                    counts[family] += 1
                return data

            for target in (client, auth):
                target.csrf = json.loads(
                    send(target, "GET", "/api/auth/csrf", scenario="csrf_setup")
                )
            send(
                client,
                "POST",
                "/api/auth/login",
                expected=(204,),
                body=urlencode({"username": f"ai_lab_{index:02d}", "password": password}),
                scenario="fixture_login",
            )
            client.csrf = json.loads(send(client, "GET", "/api/auth/csrf", scenario="csrf_refresh"))
            origin = time.monotonic()
            objects = []
            for i, case in enumerate(plan):
                while (remaining := origin + case["at_seconds"] - time.monotonic()) > 0:
                    if (lab / "STOP").exists():
                        raise PipelineError("Challenge capture stopped")
                    time.sleep(min(0.5, remaining))
                family = case["family"]
                kw = {"family": family, "variant": case["variant"]}
                if family in PAYLOADS:
                    send(
                        client,
                        "GET",
                        case["target"],
                        expected=(200, 400, 403),
                        scenario="unseen_query_grammar",
                        **kw,
                    )
                elif family == "scanner_recon":
                    send(
                        client,
                        "GET",
                        case["target"],
                        agent=rng.choice(("nuclei/3.5", "ffuf/2.2", "gobuster/3.7")),
                        scenario="scanner_agent",
                        **kw,
                    )
                elif family == "brute_force":
                    send(
                        auth,
                        "POST",
                        "/api/auth/login",
                        expected=(401, 429),
                        body=urlencode(
                            {
                                "username": f"challenge_unknown_{index}",
                                "password": "incorrect-fixture-only",
                            }
                        ),
                        scenario="auth_failures",
                        **kw,
                    )
                elif family == "behavioral_anomaly":
                    send(
                        client,
                        "GET",
                        f"/api/students?page={i % 13}&size=20",
                        expected=(403,) if role == "STUDENT" else (200,),
                        scenario="enumeration_attempt",
                        **kw,
                    )
                elif case["hard_negative"]:
                    send(client, "GET", case["target"], scenario="new_hard_negative", **kw)
                elif case["workflow"] == 0:
                    body = {
                        "shortCode": f"CH{index:02d}{i:04d}",
                        "name": f"Challenge faculty {i}",
                        "description": "AI-owned fictional data",
                        "active": True,
                    }
                    data = send(
                        client,
                        "POST",
                        "/api/faculties",
                        body=body,
                        expected=(403,) if role == "STUDENT" else (201,),
                        scenario="legitimate_create",
                    )
                    if role != "STUDENT":
                        objects.append(json.loads(data)["id"])
                elif case["workflow"] == 1 and objects:
                    send(
                        client,
                        "DELETE",
                        f"/api/faculties/{objects.pop()}",
                        expected=(204,),
                        scenario="legitimate_delete",
                    )
                elif case["workflow"] == 2:
                    send(
                        client,
                        "GET",
                        "/api/faculties/99999999",
                        expected=(404,),
                        scenario="legitimate_missing_record",
                    )
                elif case["workflow"] == 3:
                    send(client, "HEAD", "/api/faculties", scenario="legitimate_head")
                elif case["workflow"] == 4:
                    send(client, "OPTIONS", "/api/faculties", scenario="legitimate_options")
                else:
                    send(client, "GET", case["target"], scenario="legitimate_search")
            send(client, "POST", "/api/auth/logout", expected=(204,), scenario="fixture_logout")
            with lock:
                campaigns.append(
                    {
                        "campaign": index,
                        "seed": local_seed,
                        "duration_seconds": time.monotonic() - origin,
                        "plan_sha256": digest(plan),
                    }
                )

        with ThreadPoolExecutor(max_workers=3) as pool:
            for f in [pool.submit(campaign, i) for i in range(3)]:
                f.result()
    result = {
        "format_version": 1,
        "capture_id": marker["capture_id"],
        "data_kind": "lab_capture",
        "scenario_version": marker["scenario_version"],
        "started_at_unix": started,
        "ended_at_unix": time.time(),
        "requests": sum(counts.values()),
        "intent_counts": dict(counts),
        "campaigns": 3,
        "campaign_durations": campaigns,
        "observer_sha256": file_sha256(observer),
        "source_commit": marker["source_commit"],
        "query_profile": "safe_query_numeric_v2",
        "role": "fresh_test_cohort",
        "limits": [
            "New real HTTP cohort and new grammars at a later time, same owned fixture/environment",
            "Runner intent plus expected outcome, not exploit success or independent human labels",
            "Three clients run concurrently within this held-out cohort; not three independent times/environments",
        ],
    }
    atomic_json(lab / "capture-result.json", result)
    return result
