#!/usr/bin/env python3
"""Audit the pinned public SOC-MLD release; never execute its extraction code."""

import argparse
import json

from idps_ai.common import PipelineError, atomic_json, load_json
from idps_ai.data.telemetry_audit import audit_telemetry_bundle
from idps_ai.training.resources import resource_envelope

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--download-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        source = load_json(args.download_manifest)
        sha = "66aafa96a69ab54ee061abbb69284444476919295f1b16985122283dae2b3054"
        if (
            source.get("doi"),
            source.get("license"),
            source.get("sha256"),
            source.get("md5"),
            source.get("bytes"),
        ) != (
            "10.5281/zenodo.23116148",
            "cc-by-4.0",
            sha,
            "764ca570a35753a90f6ac3046750c716",
            10430367,
        ):
            raise PipelineError("Pinned official source identity/license mismatch")
        with resource_envelope(4, 16) as (guard, resources):
            result = audit_telemetry_bundle(args.archive, args.output, sha, guard)
        from pathlib import Path

        atomic_json(Path(args.output) / "resources.json", resources)
        print(json.dumps(result, sort_keys=True))
    except PipelineError as error:
        parser.exit(2, str(error) + "\n")
