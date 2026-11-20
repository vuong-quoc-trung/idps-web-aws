"""Stage a relocatable HTTPS scorer release using pinned native dependencies."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def build(out, scorer, ort, pins):
    if out.exists():
        raise ValueError("Use a fresh release directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    native = json.loads(pins.read_text())
    files = {"bin/scorer": scorer, "lib/onnxruntime.so": ort}
    for key, path in files.items():
        if sha(path) != native[key]:
            raise ValueError("Unrecognized native dependency: " + key)
    files["launch.py"] = HERE / "launch.py"
    for name in [
        "__init__",
        "common",
        "training/__init__",
        "training/adaptive_thermal",
        "training/delegated_guard",
        "training/heartbeat",
        "training/resource_adapter",
        "training/resource_contract",
        "training/thermal_policy",
    ]:
        rel = "ai-training/src/idps_ai/" + name + ".py"
        files[rel] = ROOT / rel
    contracts = ROOT / "ai-training/contracts"
    slots_dir = contracts / "quality-freeze-r37"
    slots = json.loads((slots_dir / "slots.json").read_text())
    for rel in [
        "https-model-r36/serve.py",
        "https-shadow-r35/receiver.py",
        "https-shadow-r35/schema.json",
        "quality-freeze-r37/slots.json",
    ]:
        files[str((contracts / rel).relative_to(ROOT))] = contracts / rel
    for slot in slots["slots"].values():
        for key, digest in (("manifest", "manifest_sha256"), ("model", "sha256")):
            path = (slots_dir / slot[key]).resolve()
            if sha(path) != slot[digest]:
                raise ValueError("Invalid release pin")
            files[str(path.relative_to(ROOT))] = path
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage = Path(temp) / "release"
        for rel, source in files.items():
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o555 if rel == "bin/scorer" else 0o444)
        manifest = {rel: sha(stage / rel) for rel in sorted(files)}
        (stage / "files.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n"
        )
        (stage / "files.json").chmod(0o444)
        os.rename(stage, out)
    return sha(out / "files.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["output", "scorer", "ort"]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--pins", type=Path, default=HERE / "native-dependencies.json")
    a = p.parse_args()
    print(build(a.output, a.scorer, a.ort, a.pins))
