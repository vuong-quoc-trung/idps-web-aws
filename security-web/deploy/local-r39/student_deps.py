"""Resolve the exact Student runtime JAR dependencies from Maven Central."""

import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.request

MAVEN_URL = "https://repo.maven.apache.org/maven2/"


def rows(manifest):
    result = json.loads(manifest.read_text())
    if not result:
        raise ValueError("Missing Student dependency pins")
    for row in result:
        path = Path(row["repository_path"])
        if (
            not re.fullmatch(r"[A-Za-z0-9_.+/-]+", row["repository_path"])
            or str(path) != row["repository_path"]
            or path.is_absolute()
            or ".." in path.parts
            or path.name != row["name"]
            or path.suffix != ".jar"
            or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
            or type(row["size"]) is not int
            or not 0 < row["size"] <= 32 * 1024**2
        ):
            raise ValueError("Invalid Student dependency pin")
    if len({row["name"] for row in result}) != len(result):
        raise ValueError("Duplicate Student dependency")
    return result


def matches(path, row):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != row["size"]:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"]


def verify(manifest, directory):
    for row in rows(manifest):
        if not matches(directory / row["name"], row):
            raise ValueError(f"Missing or invalid cached JAR: {row['name']}")


def fetch(manifest, directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for row in rows(manifest):
        path = directory / row["name"]
        if matches(path, row):
            continue
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temp:
            stage = Path(temp.name)
        try:
            with urllib.request.urlopen(
                MAVEN_URL + row["repository_path"], timeout=30
            ) as reply:
                with stage.open("wb") as output:
                    left = row["size"] + 1
                    while left:
                        chunk = reply.read(min(128 * 1024, left))
                        if not chunk:
                            break
                        output.write(chunk)
                        left -= len(chunk)
            if not matches(stage, row):
                raise ValueError(
                    f"Maven Central bytes differ from the build pin: {row['name']}"
                )
            stage.replace(path)
        finally:
            stage.unlink(missing_ok=True)


def install(manifest, cache, destination):
    destination.mkdir(mode=0o700)
    for row in rows(manifest):
        target = destination / row["name"]
        source = cache / row["name"]
        # Validate the private copy before it becomes visible to the service.
        with source.open("rb") as original, target.open("xb") as out:
            out.write(original.read(row["size"] + 1))
        if not matches(target, row):
            raise ValueError(f"Student cache changed while copying {row['name']}")
        target.chmod(0o644)
    destination.chmod(0o755)
