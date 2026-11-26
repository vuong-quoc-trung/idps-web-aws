"""Update only Student Web's Gmail settings on the verified staging instance."""

import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys

import refresh
import update

ENV = update.R47 / "student.env"
BACKUP = Path("/var/backups/websentinel-r50-mail")
HOST = "smtp.gmail.com"
PORT = 587


def mail_settings(user, password):
    if not re.fullmatch(r"[A-Za-z0-9._+%-]+@gmail\.com", user, re.ASCII):
        raise ValueError("Expected a Gmail sender address")
    if not re.fullmatch(r"[A-Za-z0-9]{16}", password, re.ASCII):
        raise ValueError("Expected an unspaced Gmail app password")
    return {
        "MAIL_HOST": HOST, "MAIL_PORT": str(PORT), "MAIL_USERNAME": user,
        "MAIL_FROM": user, "MAIL_PASSWORD": password, "PASSWORD_RESET_MAIL_ENABLED": "true",
    }


def merge(original, settings):
    lines = original.splitlines(keepends=True)
    existing = set()
    for index, line in enumerate(lines):
        key = line.partition("=")[0].strip()
        if key in settings:
            if key in existing:
                raise ValueError("Duplicate SMTP setting")
            existing.add(key)
            lines[index] = f"{key}={settings[key]}\n"
    result = "".join(lines)
    if result and not result.endswith("\n"):
        result += "\n"
    return result + "".join(f"{key}={value}\n" for key, value in settings.items() if key not in existing)


def verify_smtp(user, password):
    with smtplib.SMTP(HOST, PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(user, password)


def install(user, password):
    refresh.verify_host()
    refresh.verify_database()
    settings = mail_settings(user, password)
    original = ENV.read_bytes()
    program = original.decode()
    for expected in ("PUBLIC_APP_URL=https://student-dut.duckdns.org", "SESSION_COOKIE_SECURE=true"):
        if program.splitlines().count(expected) != 1:
            raise ValueError("Expected HTTPS application URL and secure cookie")
    rendered = merge(program, settings)
    verify_smtp(user, password)
    if rendered == program:
        return
    if BACKUP.exists():
        raise ValueError("R50 mail backup already exists. Review it before another update")
    update.backup(BACKUP)
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    if (BACKUP / "student.env").read_bytes() != original or ENV.read_bytes() != original:
        raise ValueError("Student environment changed during preflight")
    update.replace(ENV, rendered, 0o600)
    try:
        update.run("systemctl", "restart", update.STUDENT, timeout=160)
        refresh.health()
        pid = update.run("systemctl", "show", update.STUDENT, "-p", "MainPID", "--value")
        actual = dict(line.decode().split("=", 1) for line in Path(f"/proc/{int(pid)}/environ").read_bytes().split(b"\0") if b"=" in line)
        if any(actual.get(key) != value for key, value in settings.items()):
            raise ValueError("Student process did not load SMTP settings")
    except Exception:
        restore()
        raise


def restore():
    refresh.verify_host()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    update.replace(ENV, (BACKUP / "student.env").read_bytes(), 0o600)
    update.run("systemctl", "restart", update.STUDENT, timeout=160)
    refresh.health()


def main():
    if sys.argv[1:] == ["rollback"]:
        restore()
        print("MAIL_ROLLBACK=PASS")
        return 0
    try:
        if os.isatty(0):
            raise ValueError("Read credentials through a protected pipe")
        form = json.loads(sys.stdin.buffer.read(512))
        install(form["username"], form["password"])
    except smtplib.SMTPAuthenticationError as exc:
        print(f"SMTP_AUTH=REFUSED status={exc.smtp_code}")
        return 1
    except Exception as exc:
        print(f"MAIL_CONFIGURATION=FAILED type={type(exc).__name__}")
        return 1
    print("SMTP_AUTH=PASS MAIL_CONFIGURATION=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
