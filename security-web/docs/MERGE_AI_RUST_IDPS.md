# Merge review: AI shadow integration + Rust IDPS

No deployment, real database, .env or host service changes were performed.

## Conflict resolutions

- main.rs: keep ai_shadow, three_source and all Rust detector, operations and
  triage modules. Keep both API sets and all configured watchers.
- ingest.rs: keep AI_SHADOW and THREE_SOURCE/GLU207_SHADOW early routing,
  sensor transaction links and all rule-based observations. Student Audit auth
  alerts use application detection rather than the legacy duplicate auth alert.
  Keep both AI retention and application observation pruning.
- frontend main.tsx: keep both AI_SHADOW and STUDENT_AUDIT filter options,
  AI shadow page and all incoming dashboard/triage/polling features.

AI records remain isolated from rule-policy/firewall evaluation. Model worker,
feature extraction, model manifests and inference settings are unchanged.

## Migration collision resolution

The operator confirmed the database has applied Rust IDPS migrations only.
Preserve incoming Rust 0001–0010 byte-for-byte, including checksums.
Rename AI migrations without changing SQL:
- 0005_ai_shadow.sql -> 0011_ai_shadow.sql
- 0006_three_source.sql -> 0012_three_source.sql
- 0007_detector_links.sql -> 0013_detector_links.sql

Do not run this migration sequence unchanged against a database that already
applied the old AI 0005–0007. Such a database needs a separate history reconciliation.
Historical integration reports retain their original migration filenames.

The AI training contract's ingest source checksum was updated after reviewing
the merged ingestion boundary. Canonical schema remains the incoming Rust schema
(including its optional Student security signals); no new schema extension was
introduced by conflict resolution. AI feature schema and model files are unchanged.

## Validation

Run cargo fmt --check, cargo check --locked --offline and full Rust tests against
an isolated PostgreSQL database. The added upgrade test installs Rust 1–10,
preserves a triaged alert, upgrades to all 13 migrations twice, checks original
SQLx checksums and confirms all AI tables exist.
The suite also covers AI idempotency/zero firewall actions and late transaction
correlation, alongside rule-based detection, cursor recovery, RBAC and triage.

Frontend tests/build and scripts/test-ai-shadow.py cover the merged interface and
worker contract/privacy. Frozen canonical snapshot/checksums are checked directly.
No live model inference, live sensor replay or production end-to-end acceptance
was claimed; the current Python environment lacks ONNX Runtime/NumPy/pytest.
