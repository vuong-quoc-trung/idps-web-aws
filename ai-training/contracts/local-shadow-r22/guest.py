"""Guest-side shadow lifecycle and benign fault-panel witness."""

import json
import re
import time

from idps_ai.common import digest


def hold_collector(capture):
    """Hold actual reads after worker launch. Preserve real late receipts."""
    poll = capture.poll
    calls = 0
    until = None

    def gated_poll():
        nonlocal calls, until
        calls += 1
        now = time.monotonic_ns() if calls >= 2 else None
        if calls == 2:
            until = now + 1_250_000_000
        if until is None or now >= until:
            poll()

    capture.poll = gated_poll


def stop_scorer(process, socket):
    process.terminate()
    process.wait(timeout=3)
    socket.unlink(missing_ok=True)


def witness(run, attempt, receipt, request_id, emit, scorer, previous):
    if (
        not request_id
        or not receipt["identity_verified"]
        or not re.fullmatch(r"[a-f0-9]{32}", request_id)
    ):
        raise ValueError("R22_WITNESS_UNVERIFIED_ID")
    journal = run / "r22-ri.jsonl"
    if journal.stat().st_size > 16_384:
        raise ValueError("R22_TELEMETRY_BUDGET")
    rows = [
        row
        for line in journal.read_text().splitlines()
        if (row := json.loads(line))["request_id"] == request_id
    ]
    if (
        len(rows) != 1
        or rows[0]["method"] not in {"GET", "POST"}
        or rows[0]["url"] != "/api/redacted"
    ):
        raise ValueError("R22_TELEMETRY_SCOPE")
    if any(
        value not in {"", "-", "application/json", "application/x-www-form-urlencoded"}
        for value in rows[0]["headers"].values()
    ):
        raise ValueError("R22_TELEMETRY_HEADER_SCOPE")
    emit(
        "PHASE",
        component="r22_live_edge",
        attempt=attempt,
        receipt_sha256=digest(receipt | {"kind": "ATTEMPT", "attempt": attempt}),
        telemetry=rows[0],
        scorer={"pid": scorer.pid, "running": scorer.poll() is None, "previous_pid": previous},
    )
