# Stage B — Rust Lua Shadow, separate approval from completed Sensor Generation

Sensor Generation is operator-accepted: notify/running, canary PASS and matching
new EVE host/Lua generation. Do not redeploy Suricata or NGINX. Correlation is NOT
cryptographic Client IP Verified. Keep AI DEFERRED, AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF.

## Current gates

Agent cannot see Rust process, localhost3000 ready returns HTTP000, Docker socket
permission denied. Actual VS Code launch, DB identity, applied migration list and
native-alert delivery are NOT_VERIFIED. No native alerts in inspected tail does not
prove absence from entire EVE. No production migration or binary startup authorized.

## 1. Identify runtime (operator, read-only)

Run `python3 security-web/scripts/inspect-shadow-runtime.py` on Host. It prints exe,
cwd, parent PID, cgroup and allowlisted initial environment, never DATABASE_URL.
Use VS Code terminal/task/debug session to establish which launch owns that PID.
Do not dump environ/cmdline/launch.json wholesale: they may contain secrets.
/proc initial env may omit dotenv changes. main.rs loads dotenv from working directory
and connects DATABASE_URL, then automatically runs ALL pending embedded migrations.
Existing shell env overrides dotenv. Confirm actual DB with read-only SQL, not filename:

```sql
BEGIN READ ONLY;
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
SELECT json_agg(x ORDER BY version) FROM
 (SELECT version, success, encode(checksum,'hex') AS checksum FROM _sqlx_migrations) x;
ROLLBACK;
```

Export second SELECT as raw JSON to /tmp/ws-applied-migrations.json (psql -X -At),
using the confirmed production connection without putting credentials in commands.
If _sqlx_migrations is absent, STOP; don't treat unknown schema as an empty new DB.

```bash
python3 security-web/scripts/check-shadow-migrations.py /tmp/ws-applied-migrations.json
```

Checker reviews all 0001–0015, rejects unknown/failed/modified versions and lists every
pending migration. Current pending list is UNKNOWN until inventory supplied.
Read /api/ready in authenticated Dashboard's network panel and source-health screen;
record SURICATA path, last successful read/new data, errors and backlog. HTTP200 alone
is not source freshness. Use SQL/native-alert queries in GENERATION-POSTGRES-ACCEPTANCE.md
and correlate SID/time/source/event key/flow/tx to the SAME Dashboard alert. If no new
native alert, mark NOT_VERIFIED; optional single lab marker requires operator choice.

## 2. Backup DB and restore rehearsal BEFORE approving new binary

Confirm container/user/db first. The following example is ONLY for confirmed
pbl4-postgres / pbl4 / pbl4_security. Never assume 5433/5434 is correct.

```bash
umask 077
WS_DB_DUMP="$HOME/ws-before-lua-shadow-$(date +%Y%m%d-%H%M%S).dump"
docker exec pbl4-postgres pg_dump -U pbl4 -d pbl4_security -Fc > "$WS_DB_DUMP"
test -s "$WS_DB_DUMP"
sha256sum "$WS_DB_DUMP"
```

Check each exit code; an empty/partial dump is not backup. Save migration JSON with
backup. pg_dump is transactionally consistent while ingest continues, but later data
is not in this snapshot. Restore rehearsal must use a separate disposable PostgreSQL
container, no mounts of production data, no production DATABASE_URL, private dump.
Example operator-only commands (unique name, local image; do not pull):

```bash
WS_RESTORE=ws-shadow-restore-$(date +%Y%m%d%H%M%S)
docker run --pull=never -d --rm --name "$WS_RESTORE" --network none \
  --memory 1g --cpus 2 --tmpfs /var/lib/postgresql/data:rw,nosuid,size=768m \
  -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine
# Wait for exit 0; do not restore until ready:
docker exec "$WS_RESTORE" pg_isready -U postgres
docker exec "$WS_RESTORE" createdb -U postgres shadow_restore
docker exec -i "$WS_RESTORE" pg_restore --exit-on-error --no-owner --no-acl \
  -U postgres -d shadow_restore < "$WS_DB_DUMP"
docker exec "$WS_RESTORE" psql -X -v ON_ERROR_STOP=1 -U postgres -d shadow_restore \
  -c 'SELECT version,success FROM _sqlx_migrations ORDER BY version;' \
  -c 'SELECT count(*) FROM security_alerts;'
```

No published ports; trust auth is confined to disposable container. If dump exceeds
capacity STOP and size the isolated store appropriately. Compare critical table counts
against a consistent backup reference (live counts can grow), constraints and history;
archive listing is insufficient. Rehearse every pending SQL in order on restored DB,
with ON_ERROR_STOP and transaction handling, then schema0015 queries/tests. Applying
SQL manually here does not update SQLx history: do not reuse this database as production
or later startup-migration test. Existing test-lua-shadow-postgres.py validates SQLx
integration separately. Remove ONLY this container after retaining sanitized results:
`docker rm -f "$WS_RESTORE"`. This stage has NOT been executed by the agent.

## 3. Candidate build and private launch directory

Build only, never cargo run before backup/approval. Frontend is served from relative
frontend/dist by Rust: preserve existing frontend BEFORE any production checkout build.
Use a separate candidate directory for artifacts. Agent candidate is in
/tmp/ws-rust-shadow-candidate (temporary, not an approved deploy location).
Record git revision + SHA256. Migrations are embedded in Rust binary; separately
copying SQL does not avoid startup migration. Preserve old executable (copy /proc/PID/exe
before stopping if needed), old frontend/dist, private env and launch cwd/arguments.
Do not copy secrets into Git, reports or world-readable staging.

Proposed config only, do NOT edit production now:

```dotenv
SURICATA_EVE_PATH=/var/log/suricata/eve.json
SURICATA_LUA_PATH=/var/log/suricata/chain.tsv
SURICATA_CAPTURE_MODE=post-proxy
SURICATA_PROXY_IP=127.77.0.1
SURICATA_WEB_IP=127.77.0.2
SURICATA_WEB_PORT=18080
SURICATA_POST_PROXY_INTERFACE=lo
SURICATA_TRUSTED_EDGE_CONFIRMED=false
SURICATA_EVE_GENERATION_HOST=true
AUTO_BLOCK=false
ENFORCEMENT_MODE=OFF
```

Use exact current paths if effective log location differs. Verify backend UID can read
EVE/chain.tsv including after rotation, without reading HMAC keys. Keep existing AI
settings deferred; do not start AI. Preserve actual DB/auth settings privately. Review
inherited VS Code env as well as .env. Runtime config cannot be proved by disk .env alone.

## 4. Approved maintenance window ONLY

Prerequisites: runtime/DB identified, full pending list reviewed, restorable dump,
known-good binary/frontend/env retained, candidate validated, permissions confirmed.
Stop only the identified VS Code Rust process (Ctrl+C in its owning terminal). Do not
kill all cargo/Rust processes. Confirm port released and process exited; no concurrent
watchers. Start candidate binary from its staged directory with reviewed private env,
frontend/dist present. This startup applies pending migrations: explicit DB approval
required. Never use new cargo run as a harmless preflight. Expect API/UI downtime;
Student HTTPS and Suricata continue independently. Do not restart them.

## 5. Health

Require /api/ready, SURICATA and SURICATA_LUA fresh reads/new data and draining backlog,
no parsing/permission errors. New native alert in DB/Dashboard must retain SID/time/
severity and separate network_src_ip. Exact generation/flow/tx and optional request ID
match -> MATCHED_SHADOW, NOT Verified; missing generation stays PENDING_GENERATION;
missing/late evidence -> PENDING_EVIDENCE; conflict -> MISMATCHED. Dashboard displays
Lua Shadow field separately. No loopback inferred as client IP, no auto block.
Read legacy rows without relabelling. Approved backend restart should preserve cursor
and counts (account for genuine new traffic); do not rotate/truncate production logs
or insert fake rows to test. Destructive rotation/conflict tests stay isolated.

## 6. Rollback distinctions

Binary/frontend/env: stop candidate, restore known-good executable, frontend and private
env/working directory, start one old process. Keep additive0015 schema, migration
history, log cursors and new evidence. Verify old binary compatibility on restored
schema before approval. Never delete0015 or mark it unapplied to force startup.

DB restore: a separate last-resort operation requiring explicit approval, coordinated
writer shutdown and downtime. Restoring older dump loses newer alerts/audits/checkpoints;
archive current DB first. Do not automate production pg_restore or drop tables as
rollback. A migration checksum mismatch is a STOP, not permission to edit history.

No production deploy until runtime identity, pending inventory and restore rehearsal
are confirmed. Sensor Generation acceptance does not remove these B-stage gates.
