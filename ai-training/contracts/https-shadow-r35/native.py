"""Consume a custodian-pinned T07 canonical TRAIN export. Never assign semantic labels here."""

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from receiver import CUTOFF, GUARD, PROFILE, SCHEMA, vector_sha

PROTOCOL = Path(__file__).resolve().parents[1] / "evaluation-v1/protocol.json"
LABELS = {"BENIGN_VERIFIED": 0, "ATTACK_VERIFIED": 1}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def hexsha(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def load_native(path, expected_sha):
    raw = path.read_bytes()
    require(
        hexsha(expected_sha) and hashlib.sha256(raw).hexdigest() == expected_sha,
        "Untrusted admission manifest",
    )
    m = json.loads(raw)
    require(
        m["version"] == "https-native-admitted-v1"
        and m["abi"] == SCHEMA
        and m["profile"] == PROFILE
        and m["task"] == "VERIFIED_HTTP_ATTACK_DETECTION"
        and m["source_role"] == "TRAIN"
        and m["protocol_sha256"] == hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "Wrong profile, protocol or role",
    )
    for k in (
        "admission_report_sha256",
        "protected_lineage_registry_sha256",
        "precollection_split_plan_sha256",
        "usage_grant_sha256",
    ):
        require(hexsha(m[k]), "Missing admission authority reference")
    require(
        m["observation_file"] == "observations.jsonl" and hexsha(m["observation_sha256"]),
        "Invalid observation reference",
    )
    obs_file = path.parent / "observations.jsonl"
    require(
        not obs_file.is_symlink() and obs_file.stat().st_size <= 512 * 1024**2,
        "Invalid observation file",
    )
    digest = hashlib.sha256()
    with obs_file.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    require(digest.hexdigest() == m["observation_sha256"], "Observation SHA mismatch")
    rows = {}
    with obs_file.open("rb") as f:
        for line in f:
            require(len(line) <= 32768, "Observation exceeds record bound")
            record = json.loads(line)
            require(
                record.get("role") == "TRAIN"
                and record["schema"] == SCHEMA
                and record["profile"] == PROFILE,
                "Protected or engineering observation",
            )
            k = (record["lineage"], record["request_id"])
            require(
                k not in rows and re.fullmatch("[0-9a-f]{32}", k[1]),
                "Duplicate or invalid request identity",
            )
            rows[k] = (record, hashlib.sha256(line).hexdigest())
    parts = {"FIT": [], "TUNING": []}
    assigned = set()
    groups = {}
    for item in m["examples"]:
        key = (item["campaign"], item["request_id"])
        require(key not in assigned and key in rows, "Invalid or repeated approved request")
        assigned.add(key)
        r, line_sha = rows[key]
        require(
            item["receipt_sha256"] == line_sha
            and item["role"] == "TRAIN"
            and item["label"] in LABELS
            and all(
                hexsha(item[k])
                for k in (
                    "semantic_review_sha256",
                    "correlation_proof_sha256",
                    "lineage_component_sha256",
                )
            ),
            "Unbound label, provenance or role",
        )
        require(r["status"] == "SCORED" or r["status"] == "PROJECTED", "Missing projection")
        require(
            r["availability"] == "AVAILABLE"
            and r.get("clock") == "EDGE_RECEIVER_SAME_KERNEL"
            and r["guard_ns"] == GUARD
            and r["cutoff_ns"] == r["dispatch_ns"] + CUTOFF
            and r["dispatch_ns"] <= r["receipt_ns"] <= r["available_ns"]
            and r["available_ns"] + GUARD <= r["cutoff_ns"]
            and r["source_mask_at_cutoff"] in ("N", "S", "A", "NS", "NA", "SA", "NSA"),
            "Missing causal evidence",
        )
        receipts = r["source_receipts_ns"]
        source_fields = (("N", "N"), ("S", "S_verified"), ("A", "A"))
        mask = "".join(
            source
            for source, field in source_fields
            if type(receipts.get(field)) is int
            and r["dispatch_ns"] <= receipts[field] <= r["cutoff_ns"] - GUARD
        )
        require(mask == r["source_mask_at_cutoff"], "Unsubstantiated source mask")
        v = r["features"]
        require(
            len(v) == 100
            and all(math.isfinite(z) for z in v)
            and r["vector_sha256"] == vector_sha(v),
            "Feature digest mismatch",
        )
        part = item["partition"]
        require(part in parts, "Unexpected partition")
        for g in (
            ("campaign", key[0]),
            ("closure", item["lineage_component_sha256"]),
            ("view", r["vector_sha256"]),
        ):
            require(groups.setdefault(g, part) == part, "Partition overlap")
        parts[part].append((v, LABELS[item["label"]], item["lineage_component_sha256"]))
    require(assigned == rows.keys(), "Incomplete canonical export")
    for entries in parts.values():
        require({label for _, label, _ in entries} == {0, 1}, "Two-class support missing")
    ordered = parts["FIT"] + parts["TUNING"]
    x, y, g = zip(*ordered, strict=True)
    n = len(parts["FIT"])
    return np.array(x, np.float32), np.array(y), np.array(g), np.ones(n), n
