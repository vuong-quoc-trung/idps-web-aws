"""Stage a separate single-user persistent HTTPS slot without binding a TCP port."""

import argparse
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def render(release, digest):
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", str(release)) or not release.is_absolute():
        raise ValueError("Unsafe release path")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid release pin")
    system = (HERE / "websentinel-https-scorer.service").read_text()
    remove = (
        "User=",
        "Group=",
        "SupplementaryGroups=",
        "EnvironmentFile=",
        "PrivateTmp=",
        "ProtectHome=",
        "ProtectSystem=",
        "RestrictAddressFamilies=",
    )
    unit = (
        "\n".join(line for line in system.splitlines() if not line.startswith(remove))
        + "\n"
    )
    return (
        unit.replace("/opt/websentinel/https/current", str(release))
        .replace(
            "RuntimeDirectory=websentinel-edge-shadow",
            "RuntimeDirectory=idps-r38-https",
        )
        .replace("StateDirectory=websentinel-https", "StateDirectory=idps-r38-https")
        .replace("DirectoryMode=0711", "DirectoryMode=0700")
        .replace("WantedBy=multi-user.target", "WantedBy=default.target")
        .replace(
            "Type=exec",
            "Type=exec\nEnvironment=SINGLE_USER_STAGING=1\n"
            "Environment=EVIDENCE_LINEAGE=r38-local-single-user\nEnvironment=RELEASE_SHA256="
            + digest,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("release", type=Path)
    p.add_argument("pin")
    p.add_argument("output", type=Path)
    a = p.parse_args()
    with a.output.open("x") as output:
        output.write(render(a.release.resolve(), a.pin))
