#!/usr/bin/env python3
"""Build reviewed, content-addressed Release assets without touching originals.

Raw HTTP, sessions, PCAP, credentials and sealed data are never selected. Safe
research tensor and model state are optional assets; inference needs core only.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ai-training/.artifacts"
TAG = "ai-research-team-20261105"


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def json_bytes(d):
    return (
        json.dumps(d, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def metadata_safe(data):
    patterns = [
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
        rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{15,}\b",
    ]
    if any(re.search(p, data) for p in patterns):
        raise RuntimeError("Secret-like material in selected metadata")


def array_safe(p):
    with np.load(p, allow_pickle=False) as arrays:
        for k in arrays.files:
            a = arrays[k]
            if a.dtype.kind in "biuf":
                if not np.isfinite(a).all():
                    raise RuntimeError("Nonfinite tensor")
            elif a.dtype.kind in "SU" and k in {"view", "group"}:
                if not all(re.fullmatch("[0-9a-f]{64}", str(v)) for v in a.astype(str)):
                    raise RuntimeError("Nonhash text in research tensor")
            else:
                raise RuntimeError("Unapproved nonnumeric tensor field: " + k)


class Asset:
    def __init__(self, name, group):
        self.name = name
        self.group = group
        self.entries = []
        self.objects = {}

    def add(self, path, destination=None):
        p = Path(path)
        rel = str(p.relative_to(ROOT))
        if re.search(
            r"(sealed|holdout|/reserved/|\.env|credentials|accounts-private|/receipts/|\.pcap$)",
            rel,
            re.IGNORECASE,
        ):
            raise RuntimeError("Forbidden artifact selection: " + rel)
        value = sha(p)
        if p.suffix in {".json", ".py", ".txt", ".md", ".yaml"}:
            metadata_safe(p.read_bytes())
        self.entries.append(
            {
                "destination": destination or rel,
                "sha256": value,
                "bytes": p.stat().st_size,
                "original": rel,
                "transformation": "NONE_EXACT_BYTES",
            }
        )
        self.objects.setdefault(value, p)

    def tree(self, path):
        for p in sorted(Path(path).rglob("*")):
            if p.is_file() and not p.is_symlink() and "__pycache__" not in str(p):
                self.add(p)

    def checkpoint(self, run, all_generations=True):
        run = Path(run)
        if not all_generations:
            pointer = json.loads((run / "latest.json").read_text())
            self.add(run / "latest.json")
            for name in ["arrays.npz", "state.json", "manifest.json"]:
                self.add(run / pointer["path"] / name)
            return
        for name in ["latest.json", "previous.json", "best.json"]:
            if (run / name).exists():
                self.add(run / name)
        for p in sorted((run / "checkpoints").glob("step-*")):
            for name in ["arrays.npz", "state.json", "manifest.json"]:
                self.add(p / name)

    def write(self, output):
        manifest = {
            "format_version": 1,
            "group": self.group,
            "entries": self.entries,
            "unique_objects": len(self.objects),
            "objects_bytes": sum(p.stat().st_size for p in self.objects.values()),
        }
        path = output / self.name
        with (
            path.open("xb") as raw,
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=0) as gz,
            tarfile.open(fileobj=gz, mode="w|") as tar,
        ):
            body = json_bytes(manifest)
            info = tarfile.TarInfo("asset-manifest.json")
            info.size = len(body)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(body))
            for value, p in sorted(self.objects.items()):
                info = tarfile.TarInfo("objects/" + value)
                info.size = p.stat().st_size
                info.mode = 0o600
                with p.open("rb") as stream:
                    tar.addfile(info, stream)
        return {
            "name": self.name,
            "group": self.group,
            "bytes": path.stat().st_size,
            "sha256": sha(path),
            "url": f"https://github.com/vuong-quoc-trung/idps-web-aws/releases/download/{TAG}/{self.name}",
            "restore_files": len(self.entries),
            "unique_objects": len(self.objects),
            "objects_bytes": manifest["objects_bytes"],
        }


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    core = Asset("models-core.tar.gz", "inference")
    for rel in [
        "research_glu207_bounded_final_20261104/run",
        "request_intelligence_v2_20261104/run/model",
    ]:
        core.checkpoint(ART / rel, all_generations=False)
    for rel in [
        "research_glu207_bounded_final_20261104/report.json",
        "research_glu207_bounded_final_20261104/research-final.onnx",
        "scale_upgrade_20261030/prepared-v5/feature_spec.json",
        "bc27_1104/threshold-manifest.json",
        "request_intelligence_v2_20261104/frozen-plan.json",
        "request_intelligence_v2_20261104/run/fit-report.json",
        "request_intelligence_v2_20261104/run/threshold-manifest.json",
        "request_intelligence_v2_20261104/run/evaluation-report.json",
        "request_intelligence_v2_20261104/waf-rich-v2/report.json",
    ]:
        core.add(ART / rel)
    core.tree(ART / "integration_candidate_20261105/demo-request-bundle")
    research = Asset("request-training-recovery.tar.gz", "request_training")
    for rel in [
        "request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz",
        "autonomous_content_intelligence_20261104/waf-rich-v1/rich-content.npz",
    ]:
        array_safe(ART / rel)
        research.add(ART / rel)
    new = ART / "integration_candidate_20261105"
    for name in ["train.npy", "labels.npy", "views.npy", "plan.json"]:
        research.add(new / "study" / name)
    research.checkpoint(new / "candidate-run")
    research.checkpoint(new / "resume-reference")
    research.checkpoint(new / "resume-split")
    for path in [
        "evaluation/evaluation-report.json",
        "evaluation/threshold.json",
        "evaluation/dvwa-predictions.json",
        "resume-exact-report.json",
        "resume-restored-final-report.json",
        "resource-summary.json",
        "verification.json",
        "portable-inference-verification.json",
    ]:
        research.add(new / path)
    for p in sorted((new / "candidate-run").glob("session-*.json")):
        research.add(p)
    research.tree(new / "research-candidate-bundle")
    for rel in [
        "autonomous_content_intelligence_20261104/study-v1/numeric_mlp",
        "autonomous_content_intelligence_20261104/study-v1/content_mlp",
    ]:
        research.checkpoint(ART / rel)
    historical = Asset("historical-baselines.tar.gz", "historical_models")
    for rel in [
        "generalization_20261031/study-phase2/bounded76-glu17-resumed",
        "generalization_20261031/study-phase2/bounded76-mlp17-resumed",
        "scale_upgrade_20261030/pilot/gated_residual-resumed",
        "scale_upgrade_20261030/pilot/deep_mlp-resumed",
        "scale_upgrade_20261030/pilot/residual-resumed",
    ]:
        historical.checkpoint(ART / rel)
    for rel in [
        "generalization_20261031/study-phase2/bounded76-glu17-bundle",
        "generalization_20261031/study-phase2/bounded76-mlp17-bundle",
    ]:
        if (ART / rel).exists():
            historical.tree(ART / rel)
    assets = [a.write(output) for a in [core, research, historical]]
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    manifest = {
        "format_version": 1,
        "release_tag": TAG,
        "storage": "GitHub Releases; no LFS, no paid storage",
        "default_groups": ["inference"],
        "assets": assets,
        "restriction": "PCAP, HTTP session/credential material, original private evidence and sealed datasets remain local. No private store configured.",
        "dataset_notice": "Optional numeric WAF derivatives only; publisher card declares MIT; no raw HTTP is redistributed.",
        "training_continuity": {
            "integration_candidate": "RESUME_EXACT verified in pinned environment; terminal3072 target",
            "request_v2_frozen": "INFERENCE_ONLY verified; no interruption resume claim",
            "GLU207": "inference restored; historical resume requires source revision3a67d15 and restricted full prepared-v5 dataset; current release does not waive hashes",
        },
        "all_originals_preserved": True,
    }
    (release / "assets.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "SHA256SUMS").write_text(
        "".join(f"{a['sha256']}  {a['name']}\n" for a in assets)
    )
    print(
        json.dumps({"assets": assets, "total_bytes": sum(a["bytes"] for a in assets)})
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    build(p.parse_args().output)
