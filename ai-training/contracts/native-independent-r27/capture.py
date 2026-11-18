"""Policy-family-disjoint KVM captures, serial Resource Adapter allocation."""

# isort: skip_file
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R262 = HERE.parent / "quality-context-r262"
sys.path.insert(0, str(R262))
spec = importlib.util.spec_from_file_location("r27_capture_parent", R262 / "capture.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
base = previous.base
sys.path.insert(0, str(HERE))
from plan import configuration, roster as family_roster  # noqa: E402
from idps_ai.common import atomic_json, digest, file_sha256  # noqa: E402
from idps_ai.training.checkpoint import RunLock  # noqa: E402

FAMILY = None


def roster(index):
    if index != 0:
        raise ValueError("Single material-family campaign per invocation")
    return family_roster(FAMILY)


def extend(root, pins):
    previous.extend(root, pins)
    from lab_auth import stage_guest_python

    cfg = configuration(FAMILY)
    plan_path = root / "lab/r27-plan.json"
    plan_path.write_text(json.dumps(cfg, sort_keys=True) + "\n")
    pins["/lab/r27-plan.json"] = file_sha256(plan_path)
    for name, destination in (
        ("context22.py", "context.py"),
        ("semantic.py", "authorization_oracle.py"),
        ("guest_plan.py", "guest_plan.py"),
    ):
        target = stage_guest_python(HERE / name, root, "/lab/" + destination)
        pins["/lab/" + destination] = file_sha256(target)
    collector = root / "lab/collector.py"
    text = (
        collector.read_text()
        .replace("20-field", "22-field")
        .replace("AFTER_ACTUAL_20_FIELD_ENCODING", "AFTER_ACTUAL_22_FIELD_ENCODING")
        .replace(
            "AUDIT_COMPLETION_FOR_CURRENT_PROTECTED_GET_ONLY",
            "CURRENT_PROTECTED_GET_OR_CATALOG_POST",
        )
    )
    collector.write_text(text)
    pins["/lab/collector.py"] = file_sha256(collector)
    # Explicitly extend the private endpoint allowlist, not the host NGINX.
    for file in (root / "lab/t083/nginx.conf", root / "lab/nginx.conf"):
        if not file.exists():
            continue
        text = file.read_text()
        if "auth/(csrf|login|me)|students/" in text:
            text = base.replace_once(
                text,
                "auth/(csrf|login|me)|students/(10[1-9]|11[0-9]|12[0-9]|13[0-2])",
                "auth/(csrf|login|me)|users/2|me/profile|training-programs",
            )
            file.write_text(text)
            pins["/" + str(file.relative_to(root))] = file_sha256(file)
    pilot = root / "bundle/ai-training/contracts/capture-pilot-v1/guest.py"
    text = base.replace_once(
        pilot.read_text(),
        '!= ["ADMIN", "STUDENT"]:',
        '!= json.loads(Path("/lab/r27-plan.json").read_text())["actors"]:',
    )
    pilot.write_text(text)
    pins["/bundle/ai-training/contracts/capture-pilot-v1/guest.py"] = file_sha256(pilot)
    timing = root / "bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"
    text = base.replace_once(
        timing.read_text(),
        "from lab_auth import login_username",
        "from guest_plan import login_username",
    )
    text = base.replace_once(
        text,
        '                body = urllib.parse.urlencode({"username": login_username(self.row["oracle"]), "password": self.password})',
        '                if self.row["oracle"].startswith("login-"):\n'
        '                    body = urllib.parse.urlencode({"username": login_username(self.row["oracle"]), "password": self.password})\n'
        '                elif self.row["oracle"] == "r27-academic-write":\n'
        "                    from guest_plan import program_body\n"
        "                    body = program_body()\n"
        '                    headers["Content-Type"] = "application/json"\n'
        '                else:\n                    raise ValueError("Unsupported POST")',
    )
    timing.write_text(text)
    pins["/bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"] = file_sha256(timing)
    campaign = root / "bundle/ai-training/contracts/capture-campaign-r2/campaign_guest.py"
    text = base.replace_once(
        campaign.read_text(),
        '    rule = row["oracle"]\n',
        '    rule = row["oracle"]\n    if rule.startswith("r27-"):\n'
        '        return None, None, 1 if row["account"] == "admin" else 2\n',
    )
    text = base.replace_once(
        text,
        '        if row["method"] == "POST":\n',
        '        if row["oracle"].startswith("login-"):\n',
    )
    campaign.write_text(text)
    pins["/bundle/ai-training/contracts/capture-campaign-r2/campaign_guest.py"] = file_sha256(
        campaign
    )
    integrity = root / "lab/source_integrity.py"
    text = base.replace_once(
        integrity.read_text(),
        '    expected = scenario["path"]\n',
        '    expected = scenario["path"]\n'
        '    if scenario.get("oracle") == "r27-user-read" and expected == "/api/users/2":\n'
        '        if row.get("redacted") is not True or row.get("truncated") is not False:\n'
        '            return None, "AUDIT_ROUTE_REDACTION_UNVERIFIED"\n'
        '        expected = "/api/users/[id]"\n',
    )
    integrity.write_text(text)
    pins["/lab/source_integrity.py"] = file_sha256(integrity)
    java = root / "lab/t083/T083Oracle.java"
    text = java.read_text()
    username_sql = "".join(
        f"            st.executeUpdate(\"UPDATE USERS SET ROLE='{role}', USERNAME='{cfg['usernames'][account]}' WHERE ID={i}\");\n"
        for i, (account, role) in enumerate(
            zip(("admin", "student"), cfg["actors"], strict=True), 1
        )
    )
    if FAMILY == "self-profile":
        username_sql += (
            '            st.executeUpdate("UPDATE STUDENTS SET USER_ID=1 WHERE ID=101");\n'
        )
        username_sql += (
            '            st.executeUpdate("UPDATE STUDENTS SET USER_ID=2 WHERE ID=102");\n'
        )
    if FAMILY == "academic-write":
        username_sql += '            st.executeUpdate("ALTER TABLE TRAINING_PROGRAMS ALTER COLUMN ID RESTART WITH 1000");\n'
        username_sql += (
            "            st.executeUpdate(\"UPDATE MAJORS SET SHORT_CODE='R27' WHERE ID=1\");\n"
        )
    text = base.replace_once(
        text, "            db.commit();\n", username_sql + "            db.commit();\n"
    )
    cases = """            case "USERNAME" -> query(db, "SELECT USERNAME FROM USERS WHERE ID = ?", Integer.parseInt(fields[1]));
            case "ENABLED" -> query(db, "SELECT ENABLED FROM USERS WHERE ID = ?", Integer.parseInt(fields[1]));
            case "SELF" -> query(db, "SELECT ID FROM STUDENTS WHERE USER_ID = ?", Integer.parseInt(fields[1]));
            case "PCOUNT" -> query(db, "SELECT COUNT(*) FROM TRAINING_PROGRAMS WHERE MAJOR_ID = ? AND PROGRAM_NAME = 'R27 Research Curriculum'", Integer.parseInt(fields[1]));
            case "PID" -> query(db, "SELECT ID FROM TRAINING_PROGRAMS WHERE MAJOR_ID = ? AND PROGRAM_NAME = 'R27 Research Curriculum'", Integer.parseInt(fields[1]));
"""
    text = base.replace_once(text, '            case "MARK"', cases + '            case "MARK"')
    java.write_text(text)
    subprocess.run(
        [
            "/usr/bin/javac",
            "-J-XX:ActiveProcessorCount=1",
            "-cp",
            f"{root / 'lab/h2.jar'}:{root / 'lab/t083/crypto.jar'}",
            "-d",
            str(java.parent),
            str(java),
        ],
        check=True,
        timeout=20,
    )
    pins["/lab/t083/T083Oracle.java"] = file_sha256(java)
    pins["/lab/t083/T083Oracle.class"] = file_sha256(java.with_suffix(".class"))


def supervise(args):
    with RunLock(args.output):
        if (args.output / "checkpoint.json").exists():
            raise ValueError("No redispatch of attempted namespace")
        cfg = configuration(FAMILY)
        rows = roster(0)
        plan = {
            "run_id": args.output.name,
            "family": FAMILY,
            "configuration": cfg,
            "rows": rows,
            "max_HTTP": len(rows),
            "role": cfg["role"],
            "policy_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "code_sha256": {f.name: file_sha256(f) for f in HERE.glob("*.py")},
            "cutoff_ns": 1000000000,
            "guard_ns": 1000000,
            "no_training": True,
        }
        atomic_json(args.output / "plan.json", plan)
        atomic_json(
            args.output / "checkpoint.json",
            {"state": "RUNNING", "committed": 0, "binding": digest(plan), "resend": False},
        )
        atomic_json(
            args.output / "status.json",
            {"state": "RUNNING", "family": FAMILY, "planned": len(rows)},
        )
        attempt, command = base.start(args, 0, 1)
        attempt.parent.mkdir(mode=0o700)
        command[command.index(str(Path(base.__file__).resolve()))] = str(HERE / "capture.py")
        command += ["--family", FAMILY]
        start = time.monotonic()
        process = subprocess.run(command, check=False, timeout=260)
        result = json.loads((attempt / "result.json").read_text())
        ledger = attempt / "guest/receipt-ledger.jsonl"
        entries = list(map(json.loads, ledger.read_text().splitlines())) if ledger.exists() else []
        completed = sum(r["kind"] == "ATTEMPT" for r in entries)
        state = (
            "CAPTURED" if process.returncode == 0 and result["reason"] == "COMPLETED" else "BLOCKED"
        )
        atomic_json(
            args.output / "checkpoint.json",
            {
                "state": state,
                "binding": digest(plan),
                "committed": completed,
                "ledger_sha256": file_sha256(ledger) if ledger.exists() else None,
                "resend": False,
            },
        )
        atomic_json(
            args.output / "status.json",
            {
                "state": state,
                "completed": completed,
                "planned": len(rows),
                "adapter": result,
                "seconds": time.monotonic() - start,
            },
        )
        return process.returncode


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("supervise", "worker"))
    for name in ("output", "iso", "h2", "numpy"):
        parser.add_argument(name, type=lambda s: Path(s).resolve(strict=True))
    parser.add_argument(
        "--family", required=True, choices=("user-read", "self-profile", "academic-write")
    )
    parser.add_argument("--index", type=int, choices=(0,))
    parser.add_argument("--campaign")
    args = parser.parse_args()
    FAMILY = args.family
    base.roster, base.extend = roster, extend
    raise SystemExit(base.worker(args) if args.action == "worker" else supervise(args))
