"""Run a fresh Firefox against the disposable R56 backend on EC2."""

import base64
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import r56_prevention_lab as lab


def until(predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if value := predicate():
                return value
        except (URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Browser action or readback did not arrive before the lab deadline")


def acceptance(root, runtime):
    def check(call, synced, connects, audit):
        profile = root / "profile"
        profile.mkdir()
        account = pwd.getpwnam("ws-r47-security")
        os.chown(profile, account.pw_uid, account.pw_gid)
        fonts = root / "fonts.conf"
        fonts.write_text(
            f"<fontconfig><dir>{runtime / 'libs/usr/share/fonts/truetype/dejavu'}</dir>"
            f"<cachedir>{profile / 'font-cache'}</cachedir></fontconfig>"
        )
        fonts.chmod(0o644)
        env = os.environ | {
            "LD_LIBRARY_PATH": f"{runtime}/libs/usr/lib/x86_64-linux-gnu:{runtime}/firefox",
            "HOME": str(profile), "TMPDIR": str(profile),
            "R58_FIREFOX": str(runtime / "firefox/firefox"), "R58_PROFILE": str(profile),
        }
        with (root / "browser-driver.log").open("w") as log:
            driver = subprocess.Popen([
                "runuser", "-u", account.pw_name, "--", "env",
                f"HOME={profile}", f"TMPDIR={profile}",
                f"XDG_RUNTIME_DIR={profile}", f"FONTCONFIG_FILE={fonts}",
                "MOZ_CRASHREPORTER_DISABLE=1",
                f"LD_LIBRARY_PATH={env['LD_LIBRARY_PATH']}", str(runtime / "gecko-new/geckodriver"),
                "--port", "20758", "--log", "debug",
            ], env=env, stdout=log, stderr=log)
        observer = None
        try:
            until(lambda: urlopen("http://127.0.0.1:20758/status", timeout=1).status == 200, 6)
            observer = subprocess.Popen([sys.executable, "-B", root / "r58_browser_test.py", root],
                                        env=env)

            def action(kind, reason=None, exclude=None):
                if observer.poll() not in (None, 0):
                    raise RuntimeError("Browser acceptance failed")
                _, records = call("/api/audit")
                return next((row for row in records if row["ip"] == lab.PEER
                             and row["action"] == kind and row["id"] != exclude
                             and (reason is None or row["reason"] == reason)
                             and row["status"] == "SUCCESS"), None)

            first = until(lambda: action("BLOCK", "R58 browser block"), 40)
            assert synced(True) and not connects()
            second = until(lambda: action("UNBLOCK"), 20)
            assert synced(False) and connects()
            third = until(lambda: action("BLOCK", "R58 browser TTL", first["id"]), 43)
            assert synced(True) and not connects()
            until(lambda: synced(False), 22)
            assert connects() and audit(third["id"])["status"] == "SUCCESS"
            ids = {first["id"], second["id"], third["id"]}
            _, records = call("/api/audit")
            assert ids == {row["id"] for row in records}
            if observer.wait(12):
                raise RuntimeError("Firefox UI did not confirm operation history")
            print("R58_BROWSER_KERNEL=" + json.dumps({
                "actions": [first["id"], second["id"], third["id"]],
                "audit_success": len(ids), "db_kernel": "SYNCED_EMPTY",
                "peer_restored_after_ttl": True,
            }), flush=True)
            for name in ("firewall-active.png", "firewall-history.png"):
                encoded = base64.b64encode((root / name).read_bytes()).decode()
                print(f"R58_SCREENSHOT {name} {encoded}", flush=True)
        finally:
            if observer and observer.poll() is None:
                observer.terminate()
                observer.wait(6)
            if driver.poll() is None:
                driver.terminate()
                driver.wait(8)
            # Keep the diagnostic bounded and independent of credentials.
            lines = (root / "browser-driver.log").read_text(errors="replace").splitlines()
            if not (root / "firewall-history.png").is_file():
                password = (root / "browser.password").read_text().strip()
                print("\n".join(line.replace(password, "[REDACTED]")[:500] for line in lines[-18:]), flush=True)
    return check


if __name__ == "__main__":
    root, pg, host, runtime = sys.argv[1:]
    lab.main(Path(root), Path(pg), int(host), browser_check=acceptance(Path(root), Path(runtime)))
