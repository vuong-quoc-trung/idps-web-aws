#!/usr/bin/env python3
"""Audit publisher legitimate captures; never replay traffic or fit a model."""

import argparse
import json
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.wcp import import_legitimate
from idps_ai.training.resources import resource_envelope


def run(archive, download_manifest, identity_key, protocol, output):
    source = load_json(download_manifest)
    declared = load_json(protocol)
    if (
        source.get("URL") != "https://downloads.openappsec.io/waf-comparison-project/legitimate.zip"
        or source.get("bytes") != Path(archive).stat().st_size
        or not source.get("license", "").startswith("Apache-2.0")
        or declared.get("original_holdouts_unchanged") is not True
        or declared.get("source") != "openappsecWCP legitimate captures"
    ):
        raise PipelineError("Explicit publisher provenance/license/protocol required")
    with resource_envelope(4, 16) as (guard, resources):

        def check():
            if guard.check() or guard.thermal_limit_reached:
                raise PipelineError(
                    "Public corpus resource/thermal guard stopped; incomplete output is not certified"
                )

        result = import_legitimate(
            archive, output, Path(identity_key).read_bytes(), source["SHA256"], budget_check=check
        )
    atomic_json(Path(output) / "resources.json", resources)
    atomic_json(
        Path(output) / "provenance.json",
        {
            "source_download_manifest_sha256": file_sha256(download_manifest),
            "protocol_sha256": file_sha256(protocol),
            "identity_key_fingerprint": file_sha256(identity_key),
            "publisher_url": "https://github.com/openappsec/waf-comparison-project",
            "license": "Apache-2.0 for legitimate dataset only; do not infer malicious collection license",
            "label_scope": "Publisher recorded legitimate browsing intent; no independent semantic review, no new labels generated",
            "original_holdouts_unchanged": True,
        },
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "download-manifest", "identity-key", "protocol", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.archive, args.download_manifest, args.identity_key, args.protocol, args.output
            ),
            sort_keys=True,
        )
    )
