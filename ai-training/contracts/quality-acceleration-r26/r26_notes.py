"""Pinned synthetic source intake with old-role fences and label-free closure."""

# isort: skip_file

import argparse
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from r26_common import NOTES_SHA, SEED, atomic_json, check, file_sha256
from r26_features import project, schema
from idps_ai.common import canonical_bytes
from idps_ai.features.safe_content import symbolic_request
from idps_ai.training.checkpoint import RunLock
from r16_waf import coarse, origin_view, project as old_projection, write_array
from r18_data import component_index, prior_roles
from r19_data import PINS as R18_PINS, R18
from r20_quality import PINS, R19

ROLES = ("FIT", "TUNING", "CAL_FIT", "CAL_OP", "RESEARCH_TEST")


def parse_request(text):
    if not isinstance(text, str) or len(text) > 1048576:
        raise ValueError("Serialized request exceeds source bound")
    normalized = text.replace("\r\n", "\n")
    head, sep, body = normalized.partition("\n\n")
    lines = head.split("\n")
    matched = re.fullmatch(r"([A-Z]+) (.{1,8192}) HTTP/([0-9]\.[0-9])", lines[0])
    if not matched or len(lines) > 129:
        raise ValueError("Unsupported synthetic request line or header count")
    for line in lines[1:]:
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+:.*", line):
            raise ValueError("Malformed serialized request headers")
    # The publisher serializes a complete request, not a sensor capture. An
    # absent separator is an observed empty body only for bodyless methods.
    method, target, protocol = matched.groups()
    body_value = body if sep else "" if method in {"GET", "HEAD", "OPTIONS", "DELETE"} else None
    return method, target, "\n".join(lines[1:]), body_value, protocol


def source_fences():
    check(file_sha256(R19 / "waf-r19.npz") == PINS["waf-r19.npz"], "R19 fence pin")
    check(
        file_sha256(R18 / "requests.sqlite") == R18_PINS["requests.sqlite"], "R18 lineage index pin"
    )
    old_rows, old_templates, old_coarse, r16_rows, r16_templates, r16_coarse = prior_roles()
    del old_rows, r16_rows
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as z:
        x, roles, vector_ids = z["x"], z["role"], z["vector_id"]
    buckets = defaultdict(int)
    for vector, role in zip(coarse(x), roles, strict=True):
        buckets[vector.tobytes()] |= 1 << int(role)
    lookup = {bytes(k): 1 << int(role) for k, role in zip(vector_ids, roles, strict=True)}
    templates = defaultdict(int)
    with sqlite3.connect(
        (R18 / "requests.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as db:
        for vector, template in db.execute("SELECT vector_id,template FROM original"):
            templates[template] |= lookup.get(vector, 0)
    return buckets, templates, old_coarse | r16_coarse, set(r16_templates), old_templates


def run(out):
    started = time.monotonic()
    source = out / "notes-train.parquet"
    check(file_sha256(source) == NOTES_SHA, "New source SHA differs")
    root = out / "notes"
    root.mkdir(exist_ok=True)
    with RunLock(root):
        check(not (root / "manifest.json").exists(), "Intake already committed")
        key_path = root / "identity.key"
        if not key_path.exists():
            with key_path.open("xb") as f:
                f.write(secrets.token_bytes(32))
            key_path.chmod(0o600)
        key = key_path.read_bytes()
        check(len(key) == 32, "Identity domain")
        vectors, labels, templates, bits, coordinates, identities = [], [], [], [], [], []
        rejected = Counter()
        availability = Counter()
        fences = source_fences()
        old_buckets, old_templates, protected_buckets, protected_templates, protected_full = fences
        labels_map = {"benign": 0, "malicious": 1}
        offset = 0
        for batch in pq.ParquetFile(source).iter_batches(
            batch_size=1024, columns=["text", "label"], use_threads=False
        ):
            for ordinal, row in enumerate(batch.to_pylist(), offset):
                check(row["label"] in labels_map, "Unexpected publisher label")
                try:
                    method, target, headers, body, protocol = parse_request(row["text"])
                    normalized = origin_view(target)
                    if normalized is None:
                        raise ValueError("Unobserved method/target")
                    projected, observation = project(normalized[0], method, headers, body)
                    old = old_projection(method, normalized[0])
                    check(old is not None, "Base projector mismatch")
                    _, bucket, template = old
                    full_template, _ = symbolic_request(method, target, headers, body)
                except ValueError:
                    rejected["MALFORMED_OR_UNSUPPORTED_REQUEST_ENVELOPE"] += 1
                    continue
                bit = old_buckets[bucket] | old_templates[template]
                if (
                    bucket in protected_buckets
                    or template in protected_templates
                    or hashlib.sha256(full_template.encode()).hexdigest().encode() in protected_full
                ):
                    bit |= 4
                identity = hmac.digest(
                    key, canonical_bytes([method, target, protocol, headers, body]), "sha256"
                )
                vectors.append(projected)
                labels.append(labels_map[row["label"]])
                templates.append(template)
                bits.append(bit)
                identities.append(identity)
                coordinates.append(ordinal)
                availability[observation["body_state"]] += 1
            offset += batch.num_rows
        x, y = np.asarray(vectors, np.float32), np.asarray(labels, np.int8)
        check(len(x) > 0 and offset == 11949, "New source cardinality")
        groups = component_index(x[:, :76], enumerate(templates))
        original_labels = defaultdict(set)
        for identity, label in zip(identities, y, strict=True):
            original_labels[identity].add(int(label))
        conflicts = {identity for identity, ys in original_labels.items() if len(ys) > 1}
        original_seen = set()
        role = np.full(len(y), -1, np.int8)
        group_decisions = {}
        for component in np.unique(groups):
            subset = np.flatnonzero(groups == component)
            mask = 0
            for i in subset:
                mask |= bits[i]
            if mask & 4:
                decision, reason = -1, "PROTECTED_LINEAGE_CLOSURE"
            elif mask & 3 == 3:
                decision, reason = -1, "CROSS_ROLE_LINEAGE_CLOSURE"
            elif mask & 1:
                decision, reason = 0, "EXISTING_FIT_COMPONENT"
            elif mask & 2:
                decision, reason = 1, "EXISTING_TUNING_COMPONENT"
            else:
                canonical = min(hashlib.sha256(v.tobytes()).hexdigest() for v in x[subset, :76])
                value = (
                    int(hashlib.sha256(f"{SEED}:{canonical}".encode()).hexdigest()[:8], 16) % 100
                )
                decision = (
                    0
                    if value < 60
                    else 1
                    if value < 70
                    else 2
                    if value < 80
                    else 3
                    if value < 90
                    else 4
                )
                reason = "NEW_COMPONENT_HASH_SPLIT"
            group_decisions[str(int(component))] = {
                "role": decision,
                "reason": reason,
                "records": len(subset),
            }
            for i in subset:
                if identities[i] in conflicts:
                    rejected["EXACT_ORIGINAL_LABEL_CONFLICT"] += 1
                elif identities[i] in original_seen:
                    rejected["EXACT_ORIGINAL_DUPLICATE"] += 1
                elif decision < 0:
                    rejected[reason] += 1
                else:
                    role[i] = decision
                original_seen.add(identities[i])
        manifest = {
            "source_sha256": NOTES_SHA,
            "identity_key_fingerprint": file_sha256(key_path),
            "schema": schema(),
            "feature_code_sha256": file_sha256(Path(__file__).with_name("r26_features.py")),
            "raw_records": offset,
            "parseable_projectable": len(y),
            "rejected": dict(rejected),
            "availability": dict(availability),
            "label_semantics": "SYNTHETIC_PUBLISHER_BENIGN_MALICIOUS",
            "native_attack_verified": 0,
            "physical_capture_proven": False,
            "campaign_independence_proven": False,
            "protected_payloads_opened": False,
            "grouping": "Existing R19 coarse URI76 and symbolic URI template closure; excluded rows retain bridge edges",
            "component_decisions": group_decisions,
            "roles": {},
            "seconds": time.monotonic() - started,
        }
        for i, name in enumerate(ROLES):
            selected = role == i
            path = root / f"{name.lower()}.npz"
            write_array(
                path,
                x=x[selected],
                y=y[selected],
                group=groups[selected],
                coordinate=np.asarray(coordinates)[selected],
            )
            manifest["roles"][name] = {
                "originals": int(selected.sum()),
                "normal_anomalous": np.bincount(y[selected], minlength=2).tolist(),
                "groups": len(np.unique(groups[selected])),
                "sha256": file_sha256(path),
            }
        for a in range(len(ROLES)):
            for b in range(a):
                check(
                    not set(groups[role == a]) & set(groups[role == b]),
                    "New source cross-role group leakage",
                )
        atomic_json(root / "manifest.json", manifest)


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)
