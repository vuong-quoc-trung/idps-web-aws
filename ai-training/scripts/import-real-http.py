#!/usr/bin/env python3
"""Fetch pinned, unrestricted SRBH original and audit a deterministic request sample.

Uses the publisher export API and exact HTTP byte ranges when the large-object
endpoint times out. No third-party relabeling, no synthetic request padding.
"""

import argparse
import hashlib
import json
import os
import secrets
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.real_http import import_srbh
from idps_ai.training.resources import resource_envelope


def fetch_srbh(directory):
    record = yaml.safe_load((AI_ROOT / "configs/public_http_sources.yaml").read_text())[
        "additional_real_sources"
    ][0]
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)

    def request(url, headers=None):
        return urllib.request.urlopen(
            urllib.request.Request(
                url, headers={"User-Agent": "IDPS-research-source-audit/1.0", **(headers or {})}
            ),
            timeout=45,
        )

    target = directory / record["filename"]
    if target.is_symlink():
        raise PipelineError("Source download cannot follow symlink")
    if (directory / "download.json").exists() and target.is_file():
        previous = load_json(directory / "download.json")
        if (
            target.stat().st_size == record["bytes"]
            and previous.get("md5") == record["md5"]
            and file_sha256(target) == previous.get("sha256")
        ):
            return target, directory / "download.json"
        raise PipelineError("Existing original source differs from recorded checksum")
    with request(record["metadata_api"]) as response:
        blob = response.read(4 * 1024**2 + 1)
    if len(blob) > 4 * 1024**2:
        raise PipelineError("Source metadata exceeds bound")
    metadata = json.loads(blob)
    version = metadata["datasetVersion"]
    files = version["files"]
    if (
        version["license"]["name"] != "CC0 1.0"
        or f"{version['versionNumber']}.{version['versionMinorNumber']}" != record["version"]
        or len(files) != 1
        or files[0].get("restricted")
    ):
        raise PipelineError("Source license/version/access state changed")
    declared = files[0]["dataFile"]
    if (
        declared["id"] != record["file_id"]
        or declared["filesize"] != record["bytes"]
        or declared["checksum"]["value"] != record["md5"]
    ):
        raise PipelineError("Source metadata no longer matches pinned original")
    atomic_json(directory / "metadata-export.json", metadata)
    parts = directory / "range-parts"
    parts.mkdir(mode=0o700, exist_ok=True)
    size = record["bytes"]
    chunk = 8 * 1024**2

    def fetch(index):
        lo = index * chunk
        hi = min(size - 1, lo + chunk - 1)
        part = parts / f"{index:03d}.part"
        if part.is_symlink():
            raise PipelineError("Range part cannot be symlink")
        if part.exists() and part.stat().st_size == hi - lo + 1:
            return
        url = (
            record["repository"]
            + "/api/access/datafile/"
            + str(record["file_id"])
            + "?format=original&range_start="
            + str(lo)
        )
        with request(url, {"Range": f"bytes={lo}-{hi}"}) as response:
            if (
                response.status != 206
                or response.headers.get("Content-Range") != f"bytes {lo}-{hi}/{size}"
            ):
                raise PipelineError("Publisher HTTP byte-range contract mismatch")
            value = response.read(hi - lo + 2)
        if len(value) != hi - lo + 1:
            raise PipelineError("Incomplete publisher byte range")
        part.write_bytes(value)
        part.chmod(0o600)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, range((size + chunk - 1) // chunk)))
    staging = directory / "original.partial"
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    if staging.is_symlink():
        raise PipelineError("Download staging cannot be symlink")
    with staging.open("wb") as out:
        staging.chmod(0o600)
        for part in sorted(parts.glob("*.part")):
            value = part.read_bytes()
            out.write(value)
            md5.update(value)
            sha.update(value)
    if staging.stat().st_size != size or md5.hexdigest() != record["md5"]:
        raise PipelineError("Full original source checksum mismatch; no admission")
    os.replace(staging, target)
    proof = {
        "source": "SR-BH2020",
        "doi": record["doi"],
        "version": record["version"],
        "license": record["dataset_license"],
        "bytes": size,
        "md5": md5.hexdigest(),
        "sha256": sha.hexdigest(),
        "metadata_sha256": file_sha256(directory / "metadata-export.json"),
        "training_admission": False,
        "download_method": "Publisher exact HTTP206ranges; full originalMD5verified",
    }
    atomic_json(directory / "download.json", proof)
    for part in parts.glob("*.part"):
        part.unlink()
    parts.rmdir()
    return target, directory / "download.json"


def run(raw_dir, output, key_file, sample_fraction=0.1):
    source, proof = fetch_srbh(raw_dir)
    key_file = Path(key_file)
    if key_file.is_symlink():
        raise PipelineError("Private identity key cannot be symlink")
    if not key_file.exists():
        with key_file.open("xb") as f:
            f.write(secrets.token_bytes(32))
        key_file.chmod(0o600)
    with resource_envelope(4, 16):
        return import_srbh(source, proof, output, key_file.read_bytes(), sample_fraction)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--identity-key", required=True)
    parser.add_argument("--sample-fraction", type=float, default=0.1)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.raw_dir, args.output, args.identity_key, args.sample_fraction), sort_keys=True
        )
    )
