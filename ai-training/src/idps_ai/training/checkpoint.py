"""Atomic immutable checkpoint generations with latest/previous/best pointers."""

import fcntl
import os
import shutil
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, file_sha256, fsync_dir, load_json
from idps_ai.training.models import Model


@contextmanager
def RunLock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / ".run.lock").open("a+b") as lock:
        os.chmod(directory / ".run.lock", 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PipelineError("Run is locked by another trainer") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@dataclass
class LoadedCheckpoint:
    model: Model
    state: dict
    permutation: np.ndarray
    path: Path
    used_previous: bool = False


def validate_generation(path, expected_sha=None):
    path = Path(path)
    if path.is_symlink() or expected_sha and file_sha256(path / "manifest.json") != expected_sha:
        raise PipelineError("Checkpoint manifest integrity failure")
    manifest = load_json(path / "manifest.json")
    if manifest.get("format_version") != 1 or set(manifest.get("files", {})) != {
        "arrays.npz",
        "state.json",
    }:
        raise PipelineError("Unsupported checkpoint format")
    for name, sha in manifest["files"].items():
        file = path / name
        if name == "state.json" and file.stat().st_size > 16 * 1024**2:
            raise PipelineError("Checkpoint metadata exceeds the safe size limit")
        if file.is_symlink() or file_sha256(file) != sha:
            raise PipelineError("Checkpoint payload integrity failure")
    with zipfile.ZipFile(path / "arrays.npz") as archive:
        if sum(info.file_size for info in archive.infolist()) > 256 * 1024**2:
            raise PipelineError("Checkpoint exceeds safe tensor size")
    return manifest


def load_checkpoint(directory):
    directory = Path(directory).resolve()
    candidates = [(directory, None, False)] if (directory / "manifest.json").exists() else []
    if not candidates:
        for name in ("latest", "previous"):
            try:
                pointer = load_json(directory / (name + ".json"))
                path = (directory / pointer["path"]).resolve()
                if not path.is_relative_to(directory / "checkpoints"):
                    raise PipelineError("Checkpoint reference escaped its run directory")
                candidates.append((path, pointer["manifest_sha256"], name == "previous"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    for path, expected_sha, previous in candidates:
        try:
            validate_generation(path, expected_sha)
            state = load_json(path / "state.json")
            with np.load(path / "arrays.npz", allow_pickle=False) as archive:
                permutation = archive["permutation"].copy()
                if permutation.dtype != np.int64 or permutation.ndim != 1:
                    raise PipelineError("Invalid checkpoint sampler")
                arrays = {name: archive[name] for name in archive.files if name != "permutation"}
                model = Model.from_arrays(state["model"], arrays)
            return LoadedCheckpoint(model, state, permutation, path, previous)
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            continue
    raise PipelineError("No complete valid checkpoint; latest/previous integrity checks failed")


def save_checkpoint(directory, model, state, permutation, is_best=False):
    directory = Path(directory)
    checkpoints = directory / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = dict(state, checkpoint_format=1, model=model.metadata())
    with tempfile.TemporaryDirectory(prefix=".writing-", dir=checkpoints) as temporary:
        work = Path(temporary)
        with (work / "arrays.npz").open("wb") as stream:
            np.savez(stream, permutation=np.asarray(permutation, dtype=np.int64), **model.arrays())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(work / "arrays.npz", 0o600)
        atomic_json(work / "state.json", state)
        atomic_json(
            work / "manifest.json",
            {
                "format_version": 1,
                "files": {name: file_sha256(work / name) for name in ("arrays.npz", "state.json")},
            },
        )
        validate_generation(work)
        name = f"step-{model.steps:012d}-{uuid.uuid4().hex[:12]}"
        destination = checkpoints / name
        os.replace(work, destination)
        fsync_dir(checkpoints)
    try:
        old = load_json(directory / "latest.json")
        old_path = (directory / old["path"]).resolve()
        if not old_path.is_relative_to(checkpoints.resolve()):
            raise PipelineError("Invalid old checkpoint pointer")
        validate_generation(old_path, old["manifest_sha256"])
        atomic_json(directory / "previous.json", old)
    except (OSError, ValueError, KeyError):
        pass
    pointer = {
        "path": str(destination.relative_to(directory)),
        "manifest_sha256": file_sha256(destination / "manifest.json"),
        "global_step": model.steps,
    }
    atomic_json(directory / "latest.json", pointer)
    if is_best or not (directory / "best.json").exists():
        atomic_json(directory / "best.json", pointer)
    keep = set()
    for label in ("latest", "previous", "best"):
        try:
            keep.add(load_json(directory / (label + ".json"))["path"])
        except (OSError, ValueError, KeyError):
            pass
    for generation in checkpoints.glob("step-*"):
        if (
            str(generation.relative_to(directory)) not in keep
            and generation.is_dir()
            and not generation.is_symlink()
        ):
            shutil.rmtree(generation)
    return destination
