"""Fetch the immutable CC-BY research release as independently resumable byte ranges."""

import concurrent.futures
import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from idps_ai.common import atomic_json, file_sha256, load_json

URL = "https://zenodo.org/records/6782156/files/rba-dataset.zip"
SIZE = 1093700330
MD5 = "cc1b1078b3929650e6c08678caffcc57"
STEP = 16 * 1024**2


def fetch(run):
    chunks = run / "downloads"
    chunks.mkdir(exist_ok=True, mode=0o700)
    began = time.monotonic()

    def part(start):
        size = min(STEP, SIZE - start)
        out = chunks / str(start)
        marker = chunks / f"{start}.json"
        if (
            marker.exists()
            and out.exists()
            and out.stat().st_size == size
            and file_sha256(out) == load_json(marker)["sha256"]
        ):
            return out
        for i in range(3):
            try:
                req = Request(
                    URL,
                    headers={
                        "Range": f"bytes={start}-{start + size - 1}",
                        "Accept-Encoding": "identity",
                    },
                )
                with urlopen(req, timeout=45) as f:
                    if (
                        f.status != 206
                        or f.headers.get("Content-Range")
                        != f"bytes {start}-{start + size - 1}/{SIZE}"
                    ):
                        raise ValueError("unverified archive range")
                    data = f.read(size + 1)
                if len(data) != size:
                    raise OSError("range incomplete")
                with out.with_suffix(".tmp").open("wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                out.with_suffix(".tmp").replace(out)
                atomic_json(
                    marker,
                    {"offset": start, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()},
                )
                return out
            except OSError:
                if i == 2:
                    raise
                time.sleep(i + 1)

    starts = list(range(0, SIZE, STEP))
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        completed = 0
        for future in concurrent.futures.as_completed([pool.submit(part, s) for s in starts]):
            completed += future.result().stat().st_size
            atomic_json(
                run / "download-progress.json",
                {
                    "bytes_verified": completed,
                    "total_bytes": SIZE,
                    "elapsed_s": time.monotonic() - began,
                },
            )
    md5 = hashlib.md5(usedforsecurity=False)
    sha = hashlib.sha256()
    temp = run / "rba.zip.partial"
    with temp.open("wb") as dst:
        for s in starts:
            with (chunks / str(s)).open("rb") as f:
                while block := f.read(1024**2):
                    dst.write(block)
                    md5.update(block)
                    sha.update(block)
        dst.flush()
        os.fsync(dst.fileno())
    if md5.hexdigest() != MD5:
        raise ValueError("publisher checksum mismatch")
    temp.replace(run / "rba.zip")
    atomic_json(
        run / "source.json",
        {
            "url": URL,
            "record": "10.5281/zenodo.6782156",
            "license": "CC BY 4.0",
            "publisher_md5": MD5,
            "sha256": sha.hexdigest(),
            "size": SIZE,
            "ranges": len(starts),
            "seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    fetch(Path(sys.argv[1]))
