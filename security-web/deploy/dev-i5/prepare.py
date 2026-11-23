"""Build an isolated, development-only distribution from the pinned Beta.2 archive."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

ARCHIVE_SHA = "7cd56aab50f744f7ce94e460aa4d86fbae6af1b02a66a95b59fba11fcf7cb061"
THERMAL_SHA = "cc881f868ef4d61eb2e859e5fbdb0473bcc56ccab17dfd9086b00bf7c4f6da7d"
MODEL = "12th Gen Intel(R) Core(TM) i5-12450HX"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected upstream layout: {old}")
    return text.replace(old, new)


def dev_reader(source):
    # Generate a sibling module from the reviewed/pinned collector. Keep the
    # packaged official collector byte-for-byte intact. Avoid duplicating its
    # platform-zone, alarm and continuous SensorReader logic in the repository.
    if digest(source) != THERMAL_SHA:
        raise ValueError("Unexpected thermal collector")
    text = source.read_text().split("\nclass SensorReader:")[0]
    text = replace_once(text, 'model != "Intel(R) Core(TM) Ultra 9 285H"', f'model != "{MODEL}"')
    text = replace_once(text, '    limit = min(', '''    if not any(s["label"].startswith("Core ") for s in sensors):
        raise PipelineError("Missing core sensors")
    if any(not 40 <= s["critical_C"] <= 100 for s in sensors):
        raise PipelineError("Unexpected i5 sensor limits")
    limit = min(''')
    text = replace_once(text, "min([limit - HARDWARE_MARGIN_C]", "min([85.0, limit - HARDWARE_MARGIN_C]")
    # 85 C is a deliberately conservative development cutoff, not a vendor rating.
    start = text.index('        "official_max_operating_C"')
    end = text.index('\n    }', start)
    return text[:start] + '        "profile": "dev-i5-12450hx",' + text[end:]


def prepare(archive, output):
    if digest(archive) != ARCHIVE_SHA or output.exists() or output.is_symlink():
        raise ValueError("Expected pinned Beta.2 archive and a new output directory")
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        with tarfile.open(archive) as package:
            package.extractall(tmp, filter="data")
        root, = Path(tmp).iterdir()
        scorer = root / "scorer"
        training = scorer / "ai-training/src/idps_ai/training"
        reader = training / "dev_i5_thermal.py"
        reader.write_text(dev_reader(training / "adaptive_thermal.py"))
        for path in (root / "manage.py", training / "delegated_guard.py"):
            text = path.read_text()
            old = "from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot"
            indent = "    " if path.name == "manage.py" else ""
            text = replace_once(text, old, old.split(",")[0] + "\n" + indent +
                                "from idps_ai.training.dev_i5_thermal import hardware_snapshot")
            if path.name == "manage.py":
                text = replace_once(text, "def require_root():", '''def require_root():
    if (run("systemd-detect-virt", "--container") != "systemd-nspawn"
        or socket.gethostname() != "ws-i5-dev"
        or set(name for _, name in socket.if_nameindex()) != {"lo"}):
        raise RuntimeError("Requires the private-loopback ws-i5-dev nspawn machine")
''')
            path.write_text(text)
        manifest = scorer / "files.json"
        files = json.loads(manifest.read_text())
        for path in (reader, training / "delegated_guard.py"):
            files[str(path.relative_to(scorer))] = digest(path)
        manifest.chmod(0o644)
        manifest.write_text(json.dumps(files, sort_keys=True, indent=2) + "\n")
        meta = root / "release.json"
        info = json.loads(meta.read_text())
        info["development_profile"] = "dev-i5-12450hx"
        meta.write_text(json.dumps(info, indent=2) + "\n")
        sums = root / "SHA256SUMS"
        sums.write_text("".join(f"{digest(p)}  {p.relative_to(root)}\n" for p in
                                sorted(root.rglob("*")) if p.is_file() and p != sums))
        root.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.archive, args.output)
