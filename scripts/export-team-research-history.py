#!/usr/bin/env python3
"""Public derivative views of research metadata; original private files retained."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ai-training/.artifacts"
SECRET_KEY = re.compile(
    r"password|passwd|authorization|cookie|credentials|private_key|api_key|hmac_key|redaction_key|session_secret|(^|_)token($|_)",
    re.IGNORECASE,
)
RAW_KEYS = {
    "headers",
    "request_headers",
    "response_headers",
    "body",
    "request_body",
    "response_body",
    "raw_request",
    "raw_response",
    "http_request",
    "fused_request",
    "env",
}
TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{15,})\b"
)
EMAIL = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SELECT = re.compile(
    r"report|manifest|freeze|plan|evaluation|metrics|history|epoch|session|threshold|handoff|selection|quality|collision|comparison|readiness|capacity|provenance|preservation|diagnostic|scope",
    re.IGNORECASE,
)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def redact(value, key="", counts=None):
    if counts is None:
        counts = Counter()
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if (
                (
                    (
                        SECRET_KEY.search(k)
                        and not re.search(
                            r"sha256|fingerprint|hash|count|present|missing|redacted",
                            k,
                            re.IGNORECASE,
                        )
                    )
                    or k.lower() in RAW_KEYS
                )
                and isinstance(v, (str, list, dict))
                and v
            ):
                out[k] = "[WITHHELD_PRIVATE_CONTENT]"
                counts["fields_withheld"] += 1
            else:
                out[k] = redact(v, k, counts)
        return out
    if isinstance(value, list):
        return [redact(v, key, counts) for v in value]
    if isinstance(value, str):
        revised = TOKEN.sub("[WITHHELD_AUTH_TOKEN]", value)
        revised = EMAIL.sub("[REDACTED_EMAIL]", revised)
        revised = re.sub(
            r"(?i)(postgres(?:ql)?|mysql|mariadb)://[^\s/@]+:[^\s/@]+@",
            r"\1://[WITHHELD_CREDENTIALS]@",
            revised,
        )
        revised = re.sub(
            r"/home/[^/\s]+/projects/idps-web-aws", "<PROJECT_ROOT>", revised
        )
        if revised != value:
            counts["strings_changed"] += 1
        return revised
    return value


def export():
    destination = ROOT / "release/research-history"
    destination.mkdir(parents=True, exist_ok=False)
    entries = []
    skipped = Counter()
    for p in sorted(ART.rglob("*.json")):
        rel = p.relative_to(ART)
        if len(rel.parts) > 4 or not SELECT.search(p.name):
            continue
        if re.search(
            r"sealed|holdout|reserved|receipts|accounts-private|credentials|node_modules|/tools/|/runtime/|/lab/|inspect|private-inventory",
            str(rel),
            re.IGNORECASE,
        ):
            skipped["private_sealed_runtime_or_raw"] += 1
            continue
        if rel.parts[0].startswith("team_release_"):
            continue
        if p.stat().st_size > 2 * 1024**2:
            skipped["large_metadata_requires_private_review"] += 1
            continue
        try:
            data = json.loads(p.read_text())
        except (ValueError, UnicodeError):
            skipped["invalid_json"] += 1
            continue
        counts = Counter()
        safe = redact(data, counts=counts)
        out = destination / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "view_kind": "PUBLIC_REDACTED_DERIVATIVE_NOT_ORIGINAL_EVIDENCE",
                    "original_relative_path": "ai-training/.artifacts/" + str(rel),
                    "original_sha256": sha(p),
                    "redactions": dict(counts),
                    "content": safe,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        entries.append(
            {
                "path": str(out.relative_to(ROOT)),
                "sha256": sha(out),
                "original_sha256": sha(p),
                "redactions": dict(counts),
            }
        )
    summary = {
        "status": "PUBLIC_DERIVATIVES_EXPORTED",
        "entries": entries,
        "skipped": dict(skipped),
        "originals_deleted_or_changed": False,
        "independent_review": "NOT_IMPLIED",
        "limitations": "Original raw requests/responses, auth/session material, PCAP and sealed data remain local; redacted views do not replace original Ground Truth.",
    }
    (ROOT / "release/research-history-index.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "metadata_views": len(entries),
                "public_bytes": sum((ROOT / e["path"]).stat().st_size for e in entries),
                "skipped": dict(skipped),
            }
        )
    )


if __name__ == "__main__":
    export()
