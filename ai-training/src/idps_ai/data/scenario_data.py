"""Fictional HTTP probes; no external targets, labels are runner intent only."""

import hashlib
from urllib.parse import unquote, urlencode

BENIGN_VIEWS = [
    [
        "O'Connor course",
        "student union meeting",
        "100% progress & safety",
        "select course and subject",
        "javascript textbook",
        "C++ && mathematics",
        "how to write <script> tags in a textbook",
        "UNION SELECT is a database lecture topic",
        "path ../docs is used in a tutorial",
        "shell operator ;id explained in class",
        "Nguyễn học phần",
        "campus-nmaple",
    ],
    [
        "D'Arcy syllabus",
        "union membership form",
        "50% completion & review",
        "select subject from catalogue",
        "javascript programming notes",
        "logic && boolean algebra",
        "escape <script> in HTML documentation",
        "UNION SELECT lecture exercises",
        "relative ../manual paths in notes",
        "shell $(id) in a safety lecture",
        "Trần học kỳ",
        "nikto-style glossary example",
    ],
    [
        "L'Angelo timetable",
        "union committee minutes",
        "75% attendance & grades",
        "select training programme",
        "javascript language reference",
        "binary || and && truth tables",
        "HTML <svg onload> teaching example",
        "SQL UNION SELECT tutorial",
        "relative ../../guide tutorial",
        "command `whoami` classroom discussion",
        "Lê chương trình",
        "nmaple campus glossary",
    ],
]


def payload_identity(family, payload):
    return family + "-" + hashlib.sha256(unquote(unquote(payload)).lower().encode()).hexdigest()


def expanded_payload(family, band, view, base_views):
    if family == "path_traversal":
        base_views = [
            ["../../etc/passwd", "../../usr/local/etc/hosts", "/.git/HEAD", "/.env"],
            ["../../../etc/hosts", "../../var/log/auth.log", "/.git/config", "../config/.env"],
            [
                "../../../../etc/shadow",
                "../../proc/self/environ",
                "/private/.env",
                "/repo/.git/index",
            ],
        ]
    payload = base_views[band][view % 4]
    wrappers = {
        "sqli": ["", "/*lab*/ ", "( ", "1 AND ( "],
        "xss": ["", "<!--example-->", "<div>", "<p>"],
        "path_traversal": ["", "./", "././", "./././"],
        "cmd_injection": ["", "fixture ", "input ", "value "],
    }
    return wrappers[family][view // 4] + payload


def query_target(payload, rng):
    route = rng.choice(("faculties", "majors", "classes", "training-programs"))
    fields = [(rng.choice(("q", "search", "filter", "query")), payload)]
    if rng.random() < 0.65:
        fields.extend([(rng.choice(("page", "offset")), str(rng.randrange(4))), ("size", "20")])
    rng.shuffle(fields)
    return "/api/" + route + "?" + urlencode(fields)
