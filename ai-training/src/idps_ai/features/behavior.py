"""Past/current-only dynamics from bounded event histories; no label/rule inputs."""

import math


def dynamics(history):
    entries = list(history)
    now = entries[-1][0] if entries else 0.0
    intervals = {
        s: [b[0] - a[0] for a, b in zip(entries, entries[1:]) if a[0] >= now - s] for s in (60, 300)
    }
    counts = {s: sum(e[0] >= now - s for e in entries) for s in (10, 60, 300)}
    failures = {
        s: sum(
            e[0] >= now - s
            and e[1] in (401, 403)
            and (e[2].startswith("/api/auth/") or e[2] == "/login")
            for e in entries
        )
        for s in (10, 60)
    }
    result = {
        "interarrival_missing": float(len(entries) < 2),
        "interarrival_log1p": math.log1p(entries[-1][0] - entries[-2][0])
        if len(entries) > 1
        else 0.0,
        "burst_10_to_60": 6 * counts[10] / max(counts[60], 1),
        "burst_60_to_300": 5 * counts[60] / max(counts[300], 1),
        "uri_transition": float(len(entries) > 1 and entries[-1][2] != entries[-2][2]),
        "method_transition": float(len(entries) > 1 and entries[-1][3] != entries[-2][3]),
        "auth_failure_acceleration": failures[10] / 10 - failures[60] / 60,
    }
    for seconds, gaps in intervals.items():
        mean = sum(gaps) / max(len(gaps), 1)
        result[f"interarrival_cv_{seconds}s"] = (
            math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps)) / mean
            if gaps and mean > 0
            else 0.0
        )
    return result
