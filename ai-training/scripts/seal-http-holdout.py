#!/usr/bin/env python3
"""Acquire an independent source archive and seal it without scoring or extraction.

This positive-only WAF-flagged source cannot establish benign FPR or independent
semantic ground truth. It is reserved supplementary evidence, not a champion gate.
"""

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.snapshot import new_destination


def seal(metadata, output):
    metadata = Path(metadata)
    m = load_json(metadata)
    if (
        m.get("id") != 17178461
        or m["metadata"].get("license", {}).get("id") != "cc-by-4.0"
        or len(m.get("files", [])) != 1
    ):
        raise PipelineError("Independent holdout source metadata/license mismatch")
    f = m["files"][0]
    if (
        f["key"] != "owasp.zip"
        or f["size"] != 29524147
        or f["checksum"] != "md5:95b7a8237abc163d8ca31e49f7318efd"
    ):
        raise PipelineError("Independent source version/file checksum changed")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    temp = output / "archive.partial"
    url = f["links"]["self"]
    md5 = hashlib.md5()
    size = 0
    if not url.startswith("https://zenodo.org/"):
        raise PipelineError("Unexpected publisher download origin")
    with urllib.request.urlopen(url, timeout=60) as response, temp.open("xb") as out:
        temp.chmod(0o600)
        while block := response.read(1024**2):
            size += len(block)
            if size > f["size"]:
                raise PipelineError("Holdout download size exceeded")
            md5.update(block)
            out.write(block)
    if size != f["size"] or md5.hexdigest() != f["checksum"][4:]:
        raise PipelineError("Holdout original archive checksum mismatch")
    raw = output / "sealed-original.zip"
    os.replace(temp, raw)
    result = {
        "format_version": 1,
        "role": "sealed_final_supplement",
        "source_doi": "10.5281/zenodo.17178461",
        "license": "CC BY 4.0",
        "source_metadata_sha256": file_sha256(metadata),
        "archive_sha256": file_sha256(raw),
        "archive_MD5": md5.hexdigest(),
        "archive_bytes": size,
        "files": {"sealed-original.zip": file_sha256(raw)},
        "extracted": False,
        "model_scores_opened": False,
        "used_for_training": False,
        "used_for_calibration": False,
        "used_for_model_selection": False,
        "registered_requests": None,
        "request_count_note": "Archive not extracted; bytes/records are not counted as verified HTTP requests.",
        "labels": "Positive-only CRS-flagged/blocked production traffic. Not independent human ground truth and no benignFPRmeasurement.",
        "unseal_protocol": "Freeze future candidate/config/preprocessor/threshold/source hashes before one-timeevaluation; never feed CAPEC/rule/SID into featuretensor. Do not select champion from positive-only recall.",
        "attribution": m["metadata"].get("creators", []),
        "production_admitted": False,
    }
    atomic_json(output / "seal.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    seal(args.metadata, args.output)
