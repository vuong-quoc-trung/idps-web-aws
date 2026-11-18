"""Recompute committed aggregates in an isolated attempt; keep original receipts immutable."""

import os
import sys
from pathlib import Path

from auth_graph import graph_study

from idps_ai.common import atomic_json, file_sha256, load_json


def replay(run):
    src = run / "auth"
    audit = run / "graph-audit"
    dest = audit / "auth"
    dest.mkdir(mode=0o700, parents=True)
    manifest = load_json(src / "download.json")
    os.link(run / "redteam.txt.gz", audit / "redteam.txt.gz")
    for name in ["download.json"] + [f"{i:03d}.gzpart" for i in range(len(manifest["chunks"]))]:
        os.link(src / name, dest / name)
    graph_study(audit)
    original = load_json(src / "assessment.json")
    result = load_json(dest / "assessment.json")
    for key in ("elapsed_s",):
        del original[key], result[key]
    if result != original or file_sha256(src / "reference-lock.json") != file_sha256(
        dest / "reference-lock.json"
    ):
        raise ValueError("causal replay diverged")
    atomic_json(
        audit / "replay.json",
        {
            "equivalent_all_counts_cutoffs_scores": True,
            "original_assessment_sha": file_sha256(src / "assessment.json"),
            "fresh_assessment_sha": file_sha256(dest / "assessment.json"),
            "reference_lock_sha": file_sha256(dest / "reference-lock.json"),
        },
    )


if __name__ == "__main__":
    replay(Path(sys.argv[1]))
