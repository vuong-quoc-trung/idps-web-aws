# Canonical Event Schema v1.0 — frozen foundation contract

Authority: `canonical-event-v1.schema.json`. Implementations: Java `AuditJsonlExporter` and Rust `events::CanonicalEvent`. The fixture is synthetic and contains no credentials. Validate with `python3 contracts/test-schema.py` (the development test uses the small `jsonschema` package).

- `timestamp` is ISO-8601 **UTC with Z**, not the old proposed `event_time_utc`. Database `occurred_at` maps to it; `observed_at` is ingestion time.
- `event_id` identifies an observation, not a request. Student emits a UUID once per line; `(source,source_instance,event_id)` survives file-copy/replay. Native Nginx/EVE use file device/inode/generation/offset/content identity. `request_id` correlates sources and is intentionally **not unique**.
- `source` is `STUDENT_AUDIT`, `NGINX` or `SURICATA`. `source_instance` must distinguish producers/sensors. It is configured by `STUDENT_SOURCE_INSTANCE` / `SECURITY_SENSOR_ID`.
- `user_id`, `username`, `session_hmac` are nullable HMAC-SHA256 pseudonyms with a purpose-separated key, prefixed `hmac-sha256:`. The key stays outside Git. These pseudonyms still require access control.
- Query **values are never retained**; unknown keys and dynamic path segments are suppressed. Student JSONL and database audit contain bounded, sanitized metadata. Rust applies another redaction boundary before storing evidence. User-agent families are reduced in normalized events; raw body, Authorization, cookies, CSRF/OTP/activation tokens are not schema fields.
- Nginx's wire JSON has `status`, `latency_seconds`, and safe `rule_signals`; the normalizer maps these to `status_code`/`latency_ms`. Those signals are detector facts and **not serialized into canonical model inputs or used as ground-truth labels**. Query strings remain null at the edge, so flags preserve detection without copying query values to disk.
- Flow features are optional/null; HTTP audit cannot invent packet counters. Missing payload/session features are not zeros or benign labels. `outcome=success/failure` is the HTTP outcome, not an attack label.
- Consumer rejects unknown top-level fields and incompatible schema versions. Any field addition, type/meaning change or source-vocabulary change requires a new contract version and coordinated producer/consumer tests; do not silently edit v1.0 when AI/IPS branches diverge. Derived ML features have a separate future `feature_version`.

Limits: Student line max 16KiB; collector max line 64KiB by default; bounded 1MiB scans. Oversized input is explicitly quarantined by source/hash/byte range, without retaining its raw content. Dataset persistence is opt-in (`COLLECT_ALL_EVENTS=true`) and is distinct from alerting.

Exporter DB and file writes are independent sinks, not an atomic outbox. File writes are synchronous/locked/fsynced with owner-only permissions and follow rename/create rotation; disk/permission/64MiB file-limit failure is logged safely. This does not guarantee lossless production export if both sinks fail. Remote VM/cloud collection requires secure file transport/mount of the configured audit path; the reverse-proxy failover does not transport files by itself.
