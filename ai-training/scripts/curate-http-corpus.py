#!/usr/bin/env python3
"""Full pinned SR-BH curation; never relabel, overwrite raw data, or admit production."""

import argparse
import hashlib
import json
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.http_curation import POLICY, curate_records, require_development_source
from idps_ai.data.real_http import iter_srbh
from idps_ai.training.resources import resource_envelope


def run(source, download_manifest, identity_key, output):
    source = Path(source)
    require_development_source(source)
    proof = load_json(download_manifest)
    key = Path(identity_key).read_bytes()
    expected = "9c73c90ce6564ae48b14f7179cd864d037a6a130ef69c68c1626ec5d7ce4a910"
    if (
        proof.get("doi") != "10.7910/DVN/OGOIXX"
        or proof.get("license") != "CC0 1.0"
        or source.is_symlink()
        or file_sha256(source) != expected
        or source.stat().st_size != 436437661
    ):
        raise PipelineError("Pinned source identity/license/size/SHA mismatch")
    md5 = hashlib.md5()
    with source.open("rb") as stream:
        while block := stream.read(1024**2):
            md5.update(block)
    if md5.hexdigest() != "173ec515308bdce5aec19cfd5b792596":
        raise PipelineError("Publisher whole-file MD5 mismatch")
    with (
        source.open(newline="", encoding="utf-8-sig") as stream,
        resource_envelope(4, 16) as (guard, resources),
    ):

        def records():
            for i, r in enumerate(iter_srbh(stream, key, expected, project_fraction=1.0)):
                if i % 4096 == 0 and (guard.check() or guard.thermal_limit_reached):
                    raise PipelineError(
                        "Full curation resource guard stopped; incomplete output not certified"
                    )
                yield r

        result = curate_records(
            records(),
            output,
            "srbh2020",
            {
                "source_sha256": expected,
                "download_manifest_sha256": file_sha256(download_manifest),
                "source_doi": "10.7910/DVN/OGOIXX",
                "license": "CC0 1.0",
                "physical_source_rows": 907815,
                "source_role": "development_exposed",
                "labels": "publisher signature-assisted manual/semi-automatic annotations, not our independent adjudication",
                "policy": POLICY,
            },
        )
    if result["input_records"] != 907815:
        raise PipelineError("Unexpected original record count; review source version")
    atomic_json(Path(output) / "resources.json", resources)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--download-manifest", required=True)
    p.add_argument("--identity-key", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    print(
        json.dumps(
            run(args.source, args.download_manifest, args.identity_key, args.output), sort_keys=True
        )
    )
