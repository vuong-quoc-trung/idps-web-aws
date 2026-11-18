"""One reviewed code-repair retry; preserve first eight receipts and never replay them."""

# isort: skip_file

import os
import subprocess
import sys

from common import HERE, PARENT, atomic_json, check, file_sha256, output_arg, read


def run(out):
    old = out / "native-live"
    new = out / "native-live-v2"
    check(not new.exists(), "Native repair retry already used")
    command = read(PARENT.parent / "t09-r10-context-20261117/campaign-1-a1/adapter/request.json")[
        "command"
    ]
    dependencies = command[5:8]
    ledger = old / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl"
    import json

    rows = [
        r
        for line in ledger.read_text().splitlines()
        if (r := json.loads(line)).get("kind") == "ATTEMPT"
    ]
    check(
        len(rows) == 8 and rows[-1]["http_status"] == 401, "First capture repair evidence changed"
    )
    atomic_json(
        out / "native-recovery-plan.json",
        {
            "reason": "Lab HTTP transport hardcoded ADMIN username for STUDENT login",
            "old_receipt_sha256": file_sha256(ledger),
            "old_dispatched": 8,
            "new_campaign_budget": 12,
            "maximum_total_HTTP": 20,
            "new_guest_database_sessions": True,
            "no_resume_of_ephemeral_old_sessions": True,
            "old_requests_not_resent_under_old_campaign_or_ID": True,
            "code_sha256": file_sha256(HERE / "native_capture.py"),
            "account_routing_sha256": file_sha256(HERE / "lab_auth.py"),
            "retry_count": 1,
        },
    )
    reconcile = subprocess.run(
        [
            sys.executable,
            "-B",
            str(HERE / "native_capture.py"),
            "reconcile",
            str(old),
            *dependencies,
        ],
        check=False,
    )
    check((old / "summary.json").exists(), "First capture offline reconciliation did not finish")
    new.mkdir(mode=0o700)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(HERE / "native_capture.py"),
            "supervise",
            str(new),
            *dependencies,
        ],
        check=False,
    )
    atomic_json(
        out / "native-recovery-result.json",
        {
            "first_reconcile_exit": reconcile.returncode,
            "second_campaign_exit": result.returncode,
            "second_summary_sha256": file_sha256(new / "summary.json")
            if (new / "summary.json").exists()
            else None,
            "additional_automatic_retries": False,
        },
    )
    return result.returncode


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(run(output_arg()))
