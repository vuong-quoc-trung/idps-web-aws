"""Read-only ws-i5-dev checks from the checkout on the Host. Does not apply migrations."""
import argparse
import difflib
import hashlib
import json
from collections import Counter, defaultdict
import re
import sys
from pathlib import Path
import subprocess
import zlib


def repository_root():
    return Path(__file__).resolve().parents[4]


def guest(*args, timeout=60):
    return subprocess.check_output(["sudo", "-n", "systemd-run", "-M", "ws-i5-dev",
                                    "--quiet", "--collect", "--wait", "--pipe", "--", *args],
                                   text=True, timeout=timeout)


def check_db(db, sql, expected):
    raw = guest("runuser", "-u", "postgres", "--", "env", "PGOPTIONS=-c default_transaction_read_only=on",
                "psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-d", db, "-c", sql)
    actual = set(raw.splitlines())
    missing = expected - actual
    extra = actual - expected
    print(db, "PASS" if actual == expected else "BLOCKED",
          "expected rows absent:", sorted(missing), "unexpected rows:", sorted(extra))
    return actual == expected


DATABASES = ("websentinel_student", "websentinel_security")

def compare_objects(archive, restored):
    def group(entries):
        groups = defaultdict(list)
        for label, logical, ordered, count, meta, rows, *detail in entries:
            groups[label].append((logical, ordered, count, meta, rows, detail))
        return groups

    before, after = group(archive), group(restored)
    errors = []
    if [r[0] for r in archive] != [r[0] for r in restored]:
        print("DIAGNOSTIC: TOC order or inventory differs")
    for label in sorted(before.keys() | after.keys()):
        left, right = before[label], after[label]
        name = ascii(label)
        if len(left) == len(right) == 1 and left[0][5] and right[0][5] and left[0][1] != right[0][1]:
            print("DDL diff", name)
            for line in difflib.unified_diff(left[0][5][0], right[0][5][0], "archive", "restored", n=0, lineterm=""):
                print(line)
        if len(left) != len(right):
            errors.append(f"{name}: object inventory {len(left)} -> {len(right)}")
        elif Counter((r[0],r[2]) for r in left) != Counter((r[0],r[2]) for r in right):
            if label.startswith("TABLE DATA "):
                kind = "row values/multiplicity" if Counter(r[4] for r in left) != Counter(r[4] for r in right) else "COPY definition"
                errors.append(f"{name}: {kind} differs; counts "
                              f"{[r[2] for r in left]} -> {[r[2] for r in right]}")
            else:
                errors.append(f"{name}: SQL definition/state differs")
        elif Counter(r[1] for r in left) != Counter(r[1] for r in right):
            if label.startswith("TABLE DATA "):
                print("DIAGNOSTIC: equivalent COPY rows in different order:", name)
            else:
                print("DIAGNOSTIC: equivalent varchar enum CHECK, array vs element casts:", name)
    if {r[4] for r in archive} != {r[4] for r in restored}:
        print("DIAGNOSTIC: dump tool/server version metadata differs")
    return errors


def verify_restore(backup, suffix):
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,18}", suffix):
        raise ValueError("Cần --restore-suffix đúng hậu tố đã dùng với manage.py restore-test")
    manifest = guest("cat", str(backup/"SHA256SUMS"))
    files = {}
    for line in manifest.splitlines():
        item = re.fullmatch(r"([0-9a-f]{64})  (websentinel_(?:student|security)\.dump|receipts\.db)", line)
        if not item or item[2] in files:
            raise ValueError("SHA256SUMS có mục không hợp lệ hoặc lặp")
        files[item[2]] = item[1]
    if any(db+".dump" not in files for db in DATABASES):
        raise ValueError("SHA256SUMS thiếu dump Student hoặc Security")
    try:
        guest("env", "-C", str(backup), "sha256sum", "--check", "--status", "SHA256SUMS")
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"{backup}: file thiếu, không đọc được hoặc sai SHA256SUMS") from exc
    helper = Path(__file__).with_name("restore_fingerprint.py").read_text()
    failures = []
    for db in DATABASES:
        target = db + "_" + suffix
        print(f"Checking {backup}/{db}.dump against {target}", flush=True)
        try:
            archive = json.loads(guest("python3", "-c", helper, "archive", str(backup/(db+".dump")), timeout=900))
            restored = json.loads(guest("python3", "-c", helper, "database", target, timeout=900))
            errors = compare_objects(archive, restored)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            errors = [f"unable to fingerprint both sources ({type(exc).__name__}); see guest diagnostic"]
        if errors:
            failures.extend(f"{target}: {error}" for error in errors)
        else:
            print(f"{target} PASS logical restore; archive SHA256={files[db+'.dump']} objects={len(archive)}")
    if failures:
        raise ValueError("\n".join(failures))



def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--backup", type=Path, help="Absolute guest backup directory")
    cli.add_argument("--restore-suffix", help="Suffix passed to manage.py restore-test")
    args = cli.parse_args()
    if not args.backup or not args.backup.is_absolute():
        cli.error("BLOCKED: cần --backup là đường dẫn tuyệt đối trong guest")
    suffix = args.restore_suffix
    if suffix is None:
        stamp = re.fullmatch(r"ws-adaptive-([0-9]{12})", args.backup.name)
        if not stamp:
            cli.error("BLOCKED: cần --restore-suffix của lần restore")
        suffix = "r" + stamp[1]
    print("Restore target suffix:", suffix, flush=True)
    for unit in ("postgresql", "websentinel-beta-edge", "websentinel-beta-security",
                 "websentinel-beta-student", "websentinel-beta-sensor", "websentinel-https-scorer"):
        print(unit, guest("systemctl", "is-active", unit).strip())
    sqlx = {f"{int(p.name.split('_')[0])}|{hashlib.sha384(p.read_bytes()).hexdigest()}|t"
            for p in (repository_root()/"security-web/migrations").glob("*.sql")}
    flyway = set()
    for p in (repository_root()/"student-web/backend/src/main/resources/db/migration").glob("V*__*.sql"):
        crc = zlib.crc32("".join(p.read_text(encoding="utf-8-sig").splitlines()).encode())
        signed = crc if crc < 2**31 else crc - 2**32
        flyway.add(f"{p.name.split('__')[0][1:]}|{signed}|t")
    if not sqlx or not flyway:
        raise SystemExit("BLOCKED: missing candidate migrations")
    rust = check_db("websentinel_security", "SELECT version,encode(checksum,'hex'),success FROM _sqlx_migrations", sqlx)
    student = check_db("websentinel_student", "SELECT version,checksum,success FROM flyway_schema_history", flyway)
    verify_restore(args.backup, suffix)
    if not (rust and student):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"BLOCKED: bước {exc.cmd[exc.cmd.index('--')+1]} exit={exc.returncode}; xem lỗi guest ở trên")
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        sys.exit("BLOCKED: " + (str(exc) if not isinstance(exc, subprocess.TimeoutExpired) else "guest command timed out"))
