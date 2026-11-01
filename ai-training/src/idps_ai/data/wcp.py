"""Private, bounded ingestion of publisher-labeled legitimate HTTP captures.

No requests are replayed to websites. Body/header values are transient inputs to
a private HMAC signature only. URI statistics use the existing privacy contract.
Reserved website members are never opened, decoded, projected or scored.
"""

import hashlib
import hmac
import io
import json
import sqlite3
import stat
import zipfile
from collections import Counter
from pathlib import PurePosixPath

import pyarrow as pa
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.data.dataset import write_rows
from idps_ai.data.http_curation import require_development_source
from idps_ai.data.privacy import METHODS
from idps_ai.data.snapshot import new_destination
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import fingerprint, project_request

ROLES = ("train_candidates", "calibration", "validation", "reserved_holdout")
SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("source_member_key", pa.string()),
        ("request_signature", pa.string()),
        ("record_index", pa.int64()),
        ("split", pa.string()),
        ("label", pa.int8()),
        ("label_source", pa.string()),
        ("timestamp", pa.float64()),
        ("body_present", pa.bool_()),
        ("projected", pa.bool_()),
        ("numeric_json", pa.string()),
        ("model_key", pa.string()),
        ("earliest_model_view_role", pa.string()),
    ]
)
DECISIONS = pa.schema(
    [
        ("event_key", pa.string()),
        ("member_key", pa.string()),
        ("record_index", pa.int64()),
        ("decision", pa.string()),
        ("reason", pa.string()),
        ("duplicate_of", pa.string()),
    ]
)


def request_array(binary_stream, chunk_bytes=65536, max_record_chars=16 * 1024**2):
    """Read incrementally; None quarantines an unparsed/oversized object.

    Oversized payloads are discarded using a bounded structural scanner that
    handles nested objects, strings and escapes. They are never parsed into a
    trusted request, assigned a label, projected or silently omitted from counts.
    """
    decoder = json.JSONDecoder()
    text = io.TextIOWrapper(binary_stream, encoding="utf-8-sig", errors="strict")
    buffer, eof = "", False

    class RecordBudgetExceeded(Exception):
        pass

    def fill():
        nonlocal buffer, eof
        block = text.read(chunk_bytes)
        eof = not block
        buffer += block
        if len(buffer) > max_record_chars:
            raise RecordBudgetExceeded

    def skip_object():
        nonlocal buffer, eof
        stack = []
        quoted = escaped = False
        if not buffer.lstrip().startswith("{"):
            raise PipelineError("Oversized non-object capture value")
        while True:
            for i, char in enumerate(buffer):
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in "{[":
                    stack.append(char)
                    if len(stack) > 128:
                        raise PipelineError("Oversized JSON nesting budget exceeded")
                elif char in "}]":
                    if not stack or stack.pop() != ("{" if char == "}" else "["):
                        raise PipelineError("Invalid oversized object structure")
                    if not stack:
                        buffer = buffer[i + 1 :]
                        return
            buffer = text.read(chunk_bytes)
            if not buffer:
                eof = True
                raise PipelineError("Incomplete oversized capture object")

    def trim():
        nonlocal buffer
        buffer = buffer.lstrip()
        while not buffer and not eof:
            fill()
            buffer = buffer.lstrip()

    trim()
    if not buffer.startswith("["):
        raise PipelineError("Publisher capture must be a JSON request array")
    buffer = buffer[1:]
    after_comma = False
    while True:
        trim()
        if buffer.startswith("]"):
            if after_comma:
                raise PipelineError("Trailing comma in capture array")
            buffer = buffer[1:]
            trim()
            if buffer:
                raise PipelineError("Trailing content after capture array")
            break
        while True:
            oversized = False
            try:
                value, end = decoder.raw_decode(buffer)
                break
            except json.JSONDecodeError:
                if eof:
                    raise PipelineError("Invalid or incomplete capture array") from None
                try:
                    fill()
                except RecordBudgetExceeded:
                    skip_object()
                    oversized, value, end = True, None, 0
                    break
        if not isinstance(value, dict) and not oversized:
            raise PipelineError("Capture array must contain request objects")
        buffer = buffer[end:]
        yield value
        trim()
        if buffer.startswith(","):
            buffer = buffer[1:]
            after_comma = True
        elif buffer.startswith("]"):
            after_comma = False
        else:
            raise PipelineError("Missing capture-array separator")


def site_role(key, member_name):
    if len(key) < 32:
        raise PipelineError("Private capture grouping key must be at least32bytes")
    bucket = int(hmac.new(key, member_name.encode(), hashlib.sha256).hexdigest()[:8], 16) % 10
    return (
        "reserved_holdout"
        if bucket < 2
        else "calibration"
        if bucket == 2
        else "validation"
        if bucket < 5
        else "train_candidates"
    )


def import_legitimate(
    archive, output, identity_key, expected_sha256, project_modulus=17, budget_check=None
):
    """Audit every nonreserved record; deterministic signature sampling for projection.

    Publisher label0 is explicitly annotated capture intent, not inferred from
    status/rules. It does not constitute our independent semantic review. Training
    admission stays false, particularly for a benign-only new source.
    """
    require_development_source(archive)
    if file_sha256(archive) != expected_sha256:
        raise PipelineError("Capture source SHA mismatch")
    if not 1 <= project_modulus <= 1000 or len(identity_key) < 32:
        raise PipelineError("Invalid capture projection sampling/key")
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if len(members) > 2000 or len({m.filename for m in members}) != len(members):
            raise PipelineError("Invalid capture archive member count")
        for m in members:
            path = PurePosixPath(m.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in m.filename
                or stat.S_ISLNK(m.external_attr >> 16)
                or m.flag_bits & 1
            ):
                raise PipelineError("Unsafe capture archive member")
        if sum(m.file_size for m in members) > 8 * 1024**3 or any(
            m.file_size > 1024**3 for m in members
        ):
            raise PipelineError("Capture archive expansion budget exceeded")
        output = new_destination(output)
        output.mkdir(mode=0o700)
        db = sqlite3.connect(output / "audit.sqlite")
        db.execute("PRAGMA cache_size=-32768")
        db.executescript(
            "CREATE TABLE seen(k TEXT PRIMARY KEY,id TEXT);CREATE TABLE views(k TEXT PRIMARY KEY,role TEXT);"
        )
        counts, methods, roles = Counter(), Counter(), Counter()
        encoding = bounded_spec()
        per_site, reserved, rejected = [], [], []
        ledger = pq.ParquetWriter(output / "decisions.parquet", DECISIONS, compression="zstd")
        pending_decisions = []

        def decision(event, site, index, kind, reason=None, duplicate_of=None):
            pending_decisions.append(
                dict(
                    event_key=event,
                    member_key=site,
                    record_index=index,
                    decision=kind,
                    reason=reason,
                    duplicate_of=duplicate_of,
                )
            )
            if len(pending_decisions) >= 2048:
                ledger.write_table(pa.Table.from_pylist(pending_decisions, schema=DECISIONS))
                pending_decisions.clear()

        def mac(value):
            return hmac.new(identity_key, value.encode(), hashlib.sha256).hexdigest()

        def rows():
            for m in sorted(
                members,
                key=lambda m: (ROLES.index(site_role(identity_key, m.filename)), m.filename),
            ):
                if m.is_dir() or not m.filename.endswith(".json"):
                    continue
                role = site_role(identity_key, m.filename)
                site = mac("site:" + m.filename)
                if role == "reserved_holdout":
                    reserved.append(
                        {"member_key": site, "uncompressed_bytes": m.file_size, "CRC32": m.CRC}
                    )
                    continue
                local = Counter()
                with z.open(m) as stream:
                    for i, r in enumerate(request_array(stream)):
                        counts["source_records_audited"] += 1
                        if budget_check and counts["source_records_audited"] % 4096 == 0:
                            budget_check()
                        local["source_records"] += 1
                        if counts["source_records_audited"] > 1500000:
                            raise PipelineError("Capture row budget exceeded")
                        event = mac(f"{expected_sha256}:{m.filename}:{i}")
                        if r is None:
                            reason = "unparsed_or_oversized_JSON_object"
                            counts[reason] += 1
                            rejected.append(
                                dict(
                                    event_key=event, member_key=site, record_index=i, reason=reason
                                )
                            )
                            decision(event, site, i, "quarantine", reason)
                            continue
                        target, method = r.get("url"), r.get("method")
                        reason = None
                        if not isinstance(target, str) or not target or len(target) > 8192:
                            reason = "missing_or_oversized_URI"
                        elif method not in METHODS or not isinstance(r.get("headers", {}), dict):
                            reason = "unsupported_method_or_headers"
                        if reason:
                            counts[reason] += 1
                            rejected.append(
                                {
                                    "event_key": event,
                                    "member_key": site,
                                    "record_index": i,
                                    "reason": reason,
                                }
                            )
                            decision(event, site, i, "quarantine", reason)
                            continue
                        signature = mac(
                            json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                        )
                        prior = db.execute("SELECT id FROM seen WHERE k=?", (signature,)).fetchone()
                        if prior:
                            counts["duplicate_records"] += 1
                            local["duplicate_records"] += 1
                            decision(
                                event,
                                site,
                                i,
                                "duplicate",
                                "same_recorded_HTTP_signature",
                                prior[0],
                            )
                            continue
                        db.execute("INSERT INTO seen VALUES(?,?)", (signature, event))
                        counts["distinct_request_signatures"] += 1
                        decision(event, site, i, "publisher_capture_candidate")
                        local["distinct_request_signatures"] += 1
                        roles[role] += 1
                        methods[method] += 1
                        selected = int(signature[:8], 16) % project_modulus == 0
                        numbers = None
                        if selected:
                            try:
                                numbers = project_request(target, method)["numbers"]
                            except PipelineError:
                                counts["selected_projection_unavailable"] += 1
                                selected = False
                            else:
                                counts["projected_records"] += 1
                                local["projected_records"] += 1
                        model_key = (
                            digest(encode_request(encoding, numbers).tolist())
                            if numbers is not None
                            else None
                        )
                        earliest = None
                        if model_key is not None:
                            db.execute("INSERT OR IGNORE INTO views VALUES(?,?)", (model_key, role))
                            earliest = db.execute(
                                "SELECT role FROM views WHERE k=?", (model_key,)
                            ).fetchone()[0]
                            if earliest != role:
                                counts["projected_view_seen_in_earlier_role"] += 1
                        yield dict(
                            event_key=event,
                            source_member_key=site,
                            request_signature=signature,
                            record_index=i,
                            split=role,
                            label=0,
                            label_source="publisher_legitimate_capture",
                            timestamp=None,
                            body_present=bool(r.get("data")),
                            projected=selected,
                            numeric_json=json.dumps(numbers, sort_keys=True, separators=(",", ":"))
                            if numbers is not None
                            else None,
                            model_key=model_key,
                            earliest_model_view_role=earliest,
                        )
                        if counts["source_records_audited"] % 4096 == 0:
                            db.commit()
                per_site.append({"member_key": site, "role": role, **dict(local)})

        write_rows(output / "observations.parquet", rows(), SCHEMA)
        if pending_decisions:
            ledger.write_table(pa.Table.from_pylist(pending_decisions, schema=DECISIONS))
        ledger.close()
        db.commit()
        db.close()
        (output / "audit.sqlite").chmod(0o600)
        atomic_json(output / "rejected.json", rejected)
        atomic_json(output / "site-distribution.json", per_site)
        holdout = output / "reserved"
        holdout.mkdir(mode=0o700)
        atomic_json(
            holdout / "AI_HOLDOUT.json",
            {
                "role": "sealed_final_benign_supplement",
                "members": reserved,
                "archive_sha256": expected_sha256,
                "members_opened": False,
                "model_scores_opened": False,
                "used_for_training": False,
                "used_for_calibration": False,
                "used_for_model_selection": False,
                "request_count": None,
                "limits": "Publisher recorded browsing, not independently reviewed; benign-only supplemental holdout cannot certify recall or select champion.",
            },
        )
        result = {
            "format_version": 1,
            "source": "openappsec_WCP_legitimate",
            "license": "Apache-2.0",
            "archive_sha256": expected_sha256,
            **dict(counts),
            "source_records_audited": counts["source_records_audited"],
            "distinct_request_signatures": counts["distinct_request_signatures"],
            "duplicate_records": counts["duplicate_records"],
            "nonreserved_members": len(per_site),
            "reserved_members_unopened": len(reserved),
            "reserved_request_count": None,
            "role_rows": dict(roles),
            "methods": dict(methods),
            "projection_sampling": f"PrivateHMAC request signature modulo{project_modulus}; independent of label/predictions",
            "projection_sha256": fingerprint(),
            "model_view_encoding": encoding["feature_version"],
            "model_view_encoder_sha256": encoding["encoding"]["implementation_sha256"],
            "timestamp_available": False,
            "no_temporal_independence_claim": True,
            "independent_human_review": False,
            "formal_training_permitted": False,
            "supervised_training_permitted": False,
            "publisher_recorded_HTTP_not_local_new_capture": True,
            "count_caution": "Distinct recorded HTTP representations, not verified unique physical request IDs. Reserved members not opened or counted. No benchmark replay, observation padding or counting projections as new HTTP.",
            "files": {
                f: file_sha256(output / f)
                for f in [
                    "observations.parquet",
                    "decisions.parquet",
                    "rejected.json",
                    "site-distribution.json",
                    "reserved/AI_HOLDOUT.json",
                ]
            },
        }
        atomic_json(output / "manifest.json", result)
        return result
