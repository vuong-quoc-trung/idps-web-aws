"""Resume exact byte ranges from the public Imperial College LANL mirror."""

import concurrent.futures
import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from idps_ai.common import atomic_json, file_sha256, load_json

PLAN = Path(__file__).with_name("auth-plan.json")
CHUNK = 8 * 1024**2


def acquire(run):
    plan = load_json(PLAN)
    root = run / "auth"
    root.mkdir(mode=0o700, exist_ok=True)
    jobs = range(plan["compressed_budget_bytes"] // CHUNK)

    def fetch(i):
        path = root / f"{i:03d}.gzpart"
        meta = path.with_suffix(".json")
        if path.is_file() and meta.exists() and file_sha256(path) == load_json(meta)["sha256"]:
            return
        start = i * CHUNK
        for attempt in range(3):
            try:
                req = Request(
                    plan["source"],
                    headers={
                        "Range": f"bytes={start}-{start + CHUNK - 1}",
                        "If-Match": plan["auth_etag"],
                        "Accept-Encoding": "identity",
                    },
                )
                with urlopen(req, timeout=35) as response:
                    if (
                        response.status != 206
                        or response.headers.get("ETag") != plan["auth_etag"]
                        or response.headers.get("Content-Range")
                        != f"bytes {start}-{start + CHUNK - 1}/{plan['auth_total_bytes']}"
                    ):
                        raise ValueError("remote range identity changed")
                    data = response.read(CHUNK + 1)
                if len(data) != CHUNK:
                    raise OSError("short range")
                with path.with_suffix(".part").open("wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                path.with_suffix(".part").replace(path)
                atomic_json(
                    meta,
                    {
                        "start": start,
                        "length": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    },
                )
                return
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)

    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        for count, _ in enumerate(pool.map(fetch, jobs), 1):
            atomic_json(
                root / "progress.json",
                {
                    "committed_prefix_bytes": count * CHUNK,
                    "total_bytes": plan["compressed_budget_bytes"],
                },
            )
    atomic_json(
        root / "download.json",
        {
            "plan_sha": file_sha256(PLAN),
            "chunks": [load_json(root / f"{i:03d}.json") for i in jobs],
            "seconds": time.monotonic() - start,
        },
    )


if __name__ == "__main__":
    acquire(Path(sys.argv[1]))
