"""Collect notices and split Student application classes from publisher JARs."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import zipfile

NOTICE = re.compile(
    r"(?i)^(licen[cs]e[s]?|notice|copying|copyright|unlicense|third.?party|authors)(?:[._-]|$)"
)


def copy_notices(source, target):
    texts = []
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if (
            item.is_file()
            and not item.is_symlink()
            and (NOTICE.match(item.name) or relative.parts[0] == "LICENSES")
        ):
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, output)
            texts.append(str(relative))
    if not texts:
        raise ValueError(f"No upstream notice found for {source.name}")
    return texts


def rust_notices(manifests, cargo_home, target):
    index = []
    for binary, manifest in manifests.items():
        registry = list((cargo_home / "registry/src").glob("index.crates.io-*"))
        tree = subprocess.check_output(
            [
                "cargo",
                "tree",
                "--locked",
                "--offline",
                "--target",
                "x86_64-unknown-linux-gnu",
                "--edges",
                "normal,build",
                "--prefix",
                "none",
                "--format",
                "{p}",
                "--manifest-path",
                manifest,
            ],
            text=True,
        )
        crates = {
            (n, v.removeprefix("v"))
            for n, v, *_ in map(str.split, tree.splitlines()[1:])
        }
        for name, version in sorted(crates):
            sources = [
                path / f"{name}-{version}"
                for path in registry
                if (path / f"{name}-{version}").is_dir()
            ]
            if len(sources) != 1:
                raise ValueError(f"Expected one crates.io source for {name} {version}")
            entry = tomllib.loads((sources[0] / "Cargo.toml").read_text())["package"]
            location = Path("rust") / binary / f"{name}-{version}"
            texts = copy_notices(sources[0], target / location)
            index.append(
                dict(
                    binary=binary,
                    name=name,
                    version=version,
                    declaration=entry.get("license"),
                    source=f"https://crates.io/crates/{name}/{version}",
                    notices=[str(location / item) for item in texts],
                )
            )
    return index


def frontend_notices(frontends, target):
    index = []
    for app, root in frontends.items():
        lock = json.loads((root / "package-lock.json").read_text())["packages"]
        for path, row in sorted(lock.items()):
            if not path or (row.get("dev") and path != "node_modules/vite"):
                continue
            package = json.loads((root / path / "package.json").read_text())
            name = package["name"]
            version = package["version"]
            if version != row["version"] or package.get("license") != "MIT":
                raise ValueError(
                    f"Review unexpected runtime declaration for {name} {version}"
                )
            location = Path("npm") / app / path.removeprefix("node_modules/")
            texts = copy_notices(root / path, target / location)
            index.append(
                dict(
                    app=app,
                    name=name,
                    version=version,
                    declaration="MIT",
                    integrity=row["integrity"],
                    notices=[str(location / item) for item in texts],
                )
            )
    return index


def split_student(source, repository, output):
    with zipfile.ZipFile(source) as original:
        jars = [
            row
            for row in original.namelist()
            if row.startswith("BOOT-INF/lib/") and row.endswith(".jar")
        ]
        ordering = re.findall(
            r'^- "(BOOT-INF/lib/[^"]+\.jar)"$',
            original.read("BOOT-INF/classpath.idx").decode(),
            re.M,
        )
        if sorted(jars) != sorted(ordering) or len(set(jars)) != len(jars):
            raise ValueError("Unexpected Student runtime classpath")
        # Spring Boot adds its jarmode extractor for executable archives. The
        # standalone classpath invokes the application directly.
        ordering = [
            p
            for p in ordering
            if not Path(p).name.startswith("spring-boot-jarmode-tools-")
        ]
        wanted = {Path(path).name for path in ordering}
        candidates = {name: [] for name in wanted}
        for local in repository.rglob("*.jar"):
            if local.name in wanted and not local.is_symlink():
                candidates[local.name].append(local)
        entries = []
        for path in ordering:
            data = original.read(path)
            name = Path(path).name
            expected = hashlib.sha256(data).hexdigest()
            matches = []
            for candidate in candidates[name]:
                with candidate.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                        matches.append(candidate)
            if len(matches) != 1:
                raise ValueError(
                    f"Could not uniquely resolve publisher artifact for {name}"
                )
            entries.append(
                dict(
                    name=name,
                    repository_path=str(matches[0].relative_to(repository)),
                    size=len(data),
                    sha256=expected,
                )
            )
        package = output / "student.jar"
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as classes:
            for item in original.infolist():
                if (
                    item.filename.startswith("BOOT-INF/classes/")
                    and item.filename != "BOOT-INF/classes/"
                ):
                    classes.writestr(
                        item.filename.removeprefix("BOOT-INF/classes/"),
                        original.read(item),
                    )
        if not entries:
            raise ValueError("Student archive has no resolved runtime dependencies")
        (output / "dependencies.json").write_text(json.dumps(entries, indent=2) + "\n")
    return len(entries)
