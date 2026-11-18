"""Serial build -> parity -> same-request reconciliation, no HTTP or model fit."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(root):
    out = root / "final-checks"
    out.mkdir(mode=0o700)
    original = root / "native-reconciliation.json"
    if original.exists():
        shutil.copyfile(original, root / "native-reconciliation-first.json")
    source = Path(__file__).parent
    steps = []
    for name, destination in (("build", out), ("verify", out), ("reconcile", root)):
        result = subprocess.run(
            [sys.executable, "-B", str(source / f"{name}.py"), str(destination)],
            capture_output=True,
            text=True,
            timeout=150,
        )
        (out / f"{name}.log").write_text(result.stdout + result.stderr)
        steps.append({"phase": name, "exit_code": result.returncode})
        (out / "status.json").write_text(
            json.dumps({"steps": steps, "state": "BLOCKED" if result.returncode else "RUNNING"})
            + "\n"
        )
        if result.returncode:
            return result.returncode
    (out / "status.json").write_text(json.dumps({"steps": steps, "state": "PASS"}) + "\n")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(run(Path(sys.argv[1])))
