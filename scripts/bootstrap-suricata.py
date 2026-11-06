#!/usr/bin/env python3
"""Extract Ubuntu Suricata/dependencies locally. No sudo, service or host changes."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(runtime):
    env = os.environ | {"LD_LIBRARY_PATH": str(runtime / "usr/lib/x86_64-linux-gnu")}
    binary = runtime / "usr/bin/suricata"
    linked = subprocess.run(
        ["ldd", str(binary)], env=env, text=True, capture_output=True, check=True
    )
    if "not found" in linked.stdout:
        raise RuntimeError(
            "Incomplete extracted dependencies; choose a fresh runtime and --prepare"
        )
    version = subprocess.check_output([str(binary), "-V"], env=env, text=True).strip()
    if "8.0." not in version:
        raise RuntimeError(
            "Only Suricata8.0 profile tested; validate new producer before use"
        )
    return {
        "version": version,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "rules_sha256": hashlib.sha256(
            (ROOT / "security-web/suricata/pbl4.rules").read_bytes()
        ).hexdigest(),
        "dependency_check": "PASS",
        "runtime": str(runtime),
        "mode": "local extraction only, no host install or capture",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", type=Path, default=ROOT / ".local-dev/suricata-runtime")
    p.add_argument("--prepare", action="store_true")
    a = p.parse_args()
    runtime = a.runtime.resolve()
    if a.prepare:
        if runtime.exists():
            raise RuntimeError(
                "Preserve existing runtime; omit --prepare to check it, or use a new path"
            )
        os.umask(0o077)
        packages = runtime.parent / (runtime.name + "-packages")
        packages.mkdir(parents=True, exist_ok=False, mode=0o700)
        tree = subprocess.check_output(
            [
                "apt-cache",
                "depends",
                "--recurse",
                "--no-recommends",
                "--no-suggests",
                "--no-conflicts",
                "--no-breaks",
                "--no-replaces",
                "--no-enhances",
                "suricata",
            ],
            text=True,
        )
        names = sorted(
            {
                line.strip().split(":")[0]
                for line in tree.splitlines()
                if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9+.-]*(?::[a-z0-9]+)?", line)
            }
        )
        missing = []
        for n in names:
            state = subprocess.run(
                ["dpkg-query", "-W", "-f=${db:Status-Status}", n],
                capture_output=True,
                text=True,
                check=False,
            )
            if state.returncode or state.stdout != "installed" or n == "suricata":
                missing.append(n)
        if not missing or len(missing) > 180:
            raise RuntimeError(
                "Unexpected dependency resolution; no installation performed"
            )
        subprocess.run(["apt-get", "download", *missing], cwd=packages, check=True)
        archives = sorted(packages.glob("*.deb"))
        if sum(f.stat().st_size for f in archives) > 500_000_000:
            raise RuntimeError(
                "Downloaded packages exceed bounded500MB; no extraction performed"
            )
        runtime.mkdir(mode=0o700)
        for f in archives:
            subprocess.run(["dpkg-deb", "-x", str(f), str(runtime)], check=True)
        proof = check(runtime)
        proof["packages"] = {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in archives
        }
        (packages / "runtime-manifest.json").write_text(
            json.dumps(proof, indent=2) + "\n"
        )
    else:
        proof = check(runtime)
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
