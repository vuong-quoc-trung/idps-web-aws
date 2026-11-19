# Sensor generation + PostgreSQL acceptance (NOT deployment approval)

## Actual results in agent environment

- No visible Rust process; Host system bus denied; /api/ready HTTP000. Runtime
  service/config/DB native alert delivery: NOT_VERIFIED. Initial /proc environment
  is only partial evidence; dotenv changes after exec may not appear there.
- EVE last 8MiB has no native alerts. This is not a claim about the entire log.
- Docker socket inaccessible; no postgres/initdb/psql installed. PostgreSQL migration,
  journal integration and dump/restore: BLOCKED / NOT_RUN, not PASS.
- Real Suricata 8.0.3 offline PCAP: shared generation across EVE/Lua, process restart,
  rotated old logs and legacy capture PASS. No AF_PACKET or production restart.
- Rust parser 8 PASS, origin 9 PASS, live input regression 15 PASS.

## Runtime read-only commands (operator, no sudo)

```
python3 security-web/scripts/inspect-shadow-runtime.py
systemctl list-units --type=service --all --no-pager | rg -i 'pbl4|security|websentinel'
```

Script exposes only PID/cgroup/allowlisted variables and EVE SID/time/flow/tx;
never dump /proc environ, systemctl Environment or full .env. A cgroup under
system.slice/<name>.service identifies the service. User/session scopes may mean
cargo or terminal launch. Missing /proc variable is UNKNOWN, not a default value.
Use authenticated Dashboard System Status (or browser network response /api/ready)
to inspect watcher timestamps/backlog/error. Do not export tokens/cookies.

In an authorized read-only PostgreSQL session:

```sql
BEGIN READ ONLY;
SELECT id, occurred_at, source, rule_name, severity, event_key,
       network_src_ip, client_ip, client_ip_verified
FROM security_alerts WHERE source='SURICATA'
ORDER BY occurred_at DESC LIMIT 20;
SELECT a.id,l.source_instance,l.flow_id,l.tx_id,l.link_basis
FROM security_alerts a JOIN detector_alert_links l ON l.alert_id=a.id
WHERE a.source='SURICATA' ORDER BY a.occurred_at DESC LIMIT 20;
SELECT path, byte_offset, generation, updated_at FROM log_cursors
WHERE file_key LIKE 'SURICATA:%' ORDER BY updated_at DESC LIMIT 10;
ROLLBACK;
```

No new native alert: NOT_VERIFIED. An optional ONE-request lab XSS canary, only
if operator chooses to send it (not executed by agent):

```
curl --noproxy '*' --cacert "$HOME/websentinel-lab.crt" --max-time 10 \
  --get --data-urlencode 'q=<script>alert(1)</script>' \
  --output /dev/null --write-out '%{http_code}\n' https://192.168.10.1/
```

This sends a marker in a GET, not JS execution. Record UTC time, inspect new EVE
SID1000003 and correlate with DB; do not assert detection solely from HTTP status.

## Disposable PostgreSQL test (operator, no sudo)

```
python3 security-web/scripts/test-lua-shadow-postgres.py
```

Requires accessible Docker and existing postgres:17-alpine image (does not pull).
Creates only a uniquely named labelled ws-lua-pg-test-* container, random loopback
port, tmpfs DB, 512MiB memory/2CPU limits. Ignores any inherited DATABASE_URL; every
cargo integration test uses this generated isolated URL. No mounts/production DB.
Finally removes its exact container even on test failure. If forcibly killed,
inspect Docker label and remove only that test container; never pbl4-postgres.

Cases: checkpoint partial/restart/rotation/dedup/late conflict; transactional rollback
including seen-key table; view statuses across missing/wrong generations and request
IDs; upgrade from existing schema with historical data unchanged; pg_dump/pg_restore
of schema0015 and conflict history. Must all PASS before deploy. Test failures must
be investigated; no migration changes based only on compiled tests.

## Generation design and trust boundary

Launcher `run-suricata-generation.py` creates random 128-bit generation at every
process start and execs Suricata with `--set sensor-name=ws-generation-<hex>` plus
WS_SENSOR_GENERATION environment. Lua snapshots that immutable startup environment
in setup; EVE includes top-level `host` from engine config. HTTP Host is a different
nested field. No reading a current generation file to label historical events.
Existing Lua without launcher falls back to its old independent generation; EVE
without matching tag remains PENDING_GENERATION. Malformed tag never upgrades.

The owner of launch/config/log paths must be trusted. Root or a process able to
rewrite EVE/Lua can forge metadata; this is NOT cryptographic attribution or proof
of response completeness. HMAC verifier remains test-only. Rotation within a sensor
process keeps generation; restarting the process creates a new one. Rule reload
within the same process need not change generation. Restoring old files never
changes their recorded generation. Never set SECURITY_SENSOR_ID to an epoch.

Rust opt-in SURICATA_EVE_GENERATION_HOST=true interprets ONLY the top-level prefix,
creates stable per-record identity and source_instance=suricata-<generation>.
Late evidence/conflicts are resolved by the DB view on each read. No Client IP
Verified, IP inference or firewall action is added. Request ID is retained for
supplementary mismatch checks rather than cleared when setting tx_id.

## Proposed deployment after acceptance (NOT executed)

1. Obtain runtime evidence and all isolated PostgreSQL/live PASS first.
2. Backup database with pg_dump custom format and test restore; retain existing
   binary/frontend, env (private), Suricata unit/YAML/Lua. Save migration versions.
3. Review replacement Suricata ExecStart that runs root-owned launcher with the same
   -D/AF_PACKET/config/pidfile options as current unit. Keep existing service Type;
   do not blindly install a second service. Shared Lua and launcher installed together.
4. Operator-approved sensor restart once; confirm native EVE host tag equals Lua row
   generation for exact flow/tx; keep old logs. New launcher needs live acceptance.
5. Approve additive migration0015 and backend update. Current backend auto-runs ALL
   pending migrations at startup: merely running new binary is a DB mutation.
6. Proposed env only (do not edit production here):
   SURICATA_EVE_PATH=/var/log/suricata/eve.json
   SURICATA_LUA_PATH=/var/log/suricata/chain.tsv
   SURICATA_CAPTURE_MODE=post-proxy
   SURICATA_PROXY_IP=127.77.0.1
   SURICATA_WEB_IP=127.77.0.2
   SURICATA_WEB_PORT=18080
   SURICATA_POST_PROXY_INTERFACE=lo
   SURICATA_TRUSTED_EDGE_CONFIRMED=false
   SURICATA_EVE_GENERATION_HOST=true
   AUTO_BLOCK=false / ENFORCEMENT_MODE=OFF; AI stays DEFERRED.
7. Health: FE200/API401, both watchers fresh/no errors/backlog draining, native alert
   visible, MATCHED_SHADOW only on exact metadata, old log Pending, IP Unverified.

Rollback is operator-controlled: stop new backend, restore old binary/frontend/env,
restore old Suricata unit/Lua if needed. Leave additive tables/data and migration
history intact; never drop tables as automatic rollback. DB snapshot restore requires
separate approval because it discards newer data. No deploy while PostgreSQL or live
generation remains BLOCKED. Journal capacity/retention also needs review for sustained
operation; no conflict-history deletion was introduced.

Lua changed: old bundle /tmp/ws-host-bundle-lua-final-972 is not the new generation
bundle. Do NOT reinstall it for this stage, edit its checksum or claim old Live E2E
PASS covers the new launcher. Generation launcher is not integrated into installer
until the database/live gates pass; no new production bundle is claimed ready.

Isolated live acceptance after offline/DB gates:

```
python3 security-web/scripts/test-sensor-generation.py
bash security-web/scripts/run-live-transaction-proof.sh /usr/lib/nginx/modules/ngx_http_js_module.so --extended
```

The live wrapper requests sudo ONLY for the existing isolated namespace/cgroup test;
agent did not execute it. New assertions compare native EVE host and Lua generation.
