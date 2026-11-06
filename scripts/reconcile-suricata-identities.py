#!/usr/bin/env python3
"""One-time exact receipt aliases at the legacy->versioned EVE parser cutover.

No timestamp/route matching, no labels, deletions, cursor reset or alert rewriting.
"""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "launcher", ROOT / "scripts/dev-up-and-verify.py"
)
launcher = importlib.util.module_from_spec(s)
s.loader.exec_module(launcher)


def sha(value):
    return hashlib.sha256(
        value.encode() if isinstance(value, str) else value
    ).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--legacy-source-instance", default="local")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise RuntimeError("Preserve previous reconciliation evidence")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", a.legacy_source_instance):
        raise RuntimeError("Invalid old source instance")
    path = launcher.RUNTIME / "suricata/eve.json"
    stat = path.stat()
    filekey = f"SURICATA:{stat.st_dev}:{stat.st_ino}"
    value = launcher.sql(
        launcher.container_name("security"),
        "security_db",
        f"SELECT byte_offset||'|'||generation FROM log_cursors WHERE file_key='{filekey}'",
    )
    offset, generation = map(int, value.split("|"))
    if generation > 32:
        raise RuntimeError("Review large historical cursor generation range manually")
    aliases = []
    writes = 0
    position = 0
    with path.open("rb") as f:
        while position < offset:
            line = f.readline()
            begin = position
            position += len(line)
            if not line.endswith(b"\n") or position > offset:
                break
            e = json.loads(line)
            if e.get("adapter_version") != "suricata-shadow-1":
                continue
            instance = e.get("sensor_instance", "")
            identity = e.get("sensor_event_id", "")
            if not re.fullmatch("[a-f0-9]{32}", instance) or not re.fullmatch(
                "[a-f0-9]{64}", identity
            ):
                raise RuntimeError("Invalid producer identity")
            newkey = sha(f"SURICATA:suricata-{instance}:{identity}")
            for g in range(generation + 1):
                physical = sha(f"{filekey}:{g}:{begin}:{sha(line)}")
                oldkey = sha(f"SURICATA:{a.legacy_source_instance}:{physical}")
                query = f"WITH added AS (INSERT INTO source_event_receipts(event_key) SELECT '{newkey}' WHERE EXISTS(SELECT 1 FROM source_event_receipts WHERE event_key='{oldkey}') ON CONFLICT DO NOTHING RETURNING event_key) SELECT (SELECT count(*) FROM added)||'|'||(SELECT count(*) FROM source_event_receipts WHERE event_key='{oldkey}')"
                inserted, known = map(
                    int,
                    launcher.sql(
                        launcher.container_name("security"), "security_db", query
                    ).split("|"),
                )
                if known:
                    aliases.append(
                        {
                            "byte_start": begin,
                            "generation": g,
                            "raw_line_sha256": sha(line),
                            "legacy_receipt": oldkey,
                            "versioned_receipt": newkey,
                            "inserted": bool(inserted),
                        }
                    )
                    writes += inserted
                    break
    end = path.stat()
    assert (
        end.st_dev == stat.st_dev
        and end.st_ino == stat.st_ino
        and end.st_size >= position
    )
    report = {
        "status": "PASS",
        "matched_legacy_physical_records": len(aliases),
        "new_receipt_aliases": writes,
        "file_key": filekey,
        "through_byte_offset": offset,
        "aliases": aliases,
        "limits": [
            "Only existing exact physical receipts with retained native versioned identity can be aliased",
            "Unversioned historical EVE has no such reversible mapping; do not invent it",
            "Already created migration-test alert is retained; no history was deleted",
            "Not source admission, labels, Ground Truth or a new packet",
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "aliases"}, indent=2))


if __name__ == "__main__":
    main()
