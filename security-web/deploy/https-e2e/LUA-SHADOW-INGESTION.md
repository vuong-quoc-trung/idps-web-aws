# Lua Shadow ingestion — prepared, not deployed

Runtime observation is limited: agent process namespace exposes no pbl4-security
process; system bus/API are inaccessible. Service name, effective environment,
PostgreSQL writes and Dashboard native-alert delivery are NOT_VERIFIED. The existing
.env on disk still names vmnet3. Do not equate it with process environment.
Previously observed 17 EVE HTTP and 17 Lua transactions are transport evidence,
not native alert ingestion acceptance.

## Implementation

Optional SURICATA_LUA_PATH=/var/log/suricata/chain.tsv uses the existing watcher:
transactional cursor + inode/anchor/truncation handling + incomplete-line buffering.
A new journal keeps generation/flow/tx/request ID, record hash, presence flags and
conflict/duplicate counts. No raw proof, receipt, key, cookie or client profile is
persisted or returned. A retry at identical physical cursor does not count twice;
identical copied records increment duplicate_count but never create more alerts.
Conflict latches and is reflected on subsequent detail API reads. No IP attribution
or firewall action is performed. This is metadata correlation, NOT HMAC validation.

Migration 0015 is additive (tables/view). Required even when Lua watcher is disabled
because detail SQL references the view. IMPORTANT: current backend automatically
runs migrations at startup. Do not launch the new binary against production before
DB backup/migration approval. No migration has been run by the agent.

## Generation blocker

Native EVE lacks generation. A current proof-generation file must NOT be used to
label old/rotated EVE. Alert links without a transaction-scoped sensor generation
return PENDING_GENERATION. Only the existing explicit suricata-shadow-1 event
contract yields source_instance=suricata-<generation>. Matching also requires exact
flow_id/tx_id, and equal request ID when EVE provides one. Missing evidence is
PENDING_EVIDENCE; incomplete proof/receipt MISSING_PROOF_OR_RECEIPT; conflicts
MISMATCHED; valid metadata MATCHED_SHADOW or DUPLICATE_SHADOW. No state is Verified.

Before full correlation acceptance, a reviewed per-sensor generation binding for
EVE AND Lua at capture time is required (including rotation/delayed events). No
adapter assigning a current epoch retrospectively was introduced. Current native
alerts remain visible even when no Lua link can be established. Journal retention
and capacity limits still need acceptance before sustained collection; no automatic
pruning of conflict history was added.

## Proposed configuration — do not edit production yet

```
SURICATA_EVE_PATH=/var/log/suricata/eve.json
SURICATA_LUA_PATH=/var/log/suricata/chain.tsv
SURICATA_CAPTURE_MODE=post-proxy
SURICATA_PROXY_IP=127.77.0.1
SURICATA_WEB_IP=127.77.0.2
SURICATA_WEB_PORT=18080
SURICATA_POST_PROXY_INTERFACE=lo
SURICATA_TRUSTED_EDGE_CONFIRMED=false
AUTO_BLOCK=false
ENFORCEMENT_MODE=OFF
```

Do not change SECURITY_SENSOR_ID to the current Lua generation. Keep AI deferred.
Changing topology may enable supplemental Rust HTTP rules previously filtered out
by vmnet3 parameters; check alert counts and native SID/supplemental distinction.

## Operator read-only acceptance

Use System Status /api/ready through your authenticated Dashboard session. Inspect
SURICATA and, after deployment, SURICATA_LUA: last_success_at, last_data_at,
pending_bytes, error. Do not paste API tokens or full environment.
Identify backend using `pgrep -f target/debug/pbl4-security-demo`, `systemctl list-units --type=service`
(the process comm may be truncated; inspect locally). Inspect only named nonsecret
variables above. DB reads must use an existing authorized read-only session:

```sql
BEGIN READ ONLY;
SELECT id, occurred_at, source, rule_name, severity, event_key,
       network_src_ip, client_ip, client_ip_verified
FROM security_alerts WHERE source='SURICATA' ORDER BY occurred_at DESC LIMIT 10;
SELECT file_key, path, byte_offset, generation, updated_at
FROM log_cursors WHERE file_key LIKE 'SURICATA:%' ORDER BY updated_at DESC LIMIT 10;
ROLLBACK;
```

No new native alert: NOT_VERIFIED. Optional operator-approved canary (not executed)
is ONE lab GET with the already accepted SQLi/XSS marker, through HTTPS Edge using
Edge CA; compare its new EVE native SID/timestamp/flow/tx to alert event_key and
Dashboard detail. Do not interpret an ordinary FE200/API401 as SID acceptance.

## Tests / rollout

Parser unit tests and frontend build can run without database. DB test
`checkpoint_restart_rotation_partial_and_conflict` is compiled but NOT_RUN: requires
an explicitly disposable PostgreSQL database and SQLx permission to create test DBs.
Never point its DATABASE_URL at production. It covers partial line, recreated watcher,
rotation duplicate, truncation and late conflict. SQL view semantics also require
PostgreSQL integration acceptance (not claimed validated by Rust compilation).

After blockers resolved: backup DB + existing binary/frontend/config, approve
migration 0015, deploy backend/frontend together during maintenance, then enable
Lua path with topology above. Check existing native alerts remain, canary correlation,
ready/backlog and restart/rotation in test first. No NGINX/Suricata cutover needed.
Rollback: stop new backend by operator, restore old binary/frontend/config; leave
additive tables in place, do not drop evidence or edit migration history. Restore DB
snapshot only through a separately approved recovery if needed. No production
restart/migration/rollback performed here.
