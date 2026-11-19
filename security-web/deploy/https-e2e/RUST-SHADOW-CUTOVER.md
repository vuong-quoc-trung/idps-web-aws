# Rust Shadow cutover: manual, no Sensor/NGINX changes

Operator has accepted production DB pbl4_security, pbl4-postgres port5433, migrations
1–15 checksums/pending=[], backup and isolated PG17 restore, Sensor generation.
Backup: /var/backups/ws-rust-shadow-20261118-222906/pbl4_security.dump.
Agent verified candidate revision d33bd28 and five artifact SHA256 hashes, rebuilt
release successfully and compared executable bytes. Candidate binary SHA256:
e3d412554f1e8aa5c9f4dcdd051ae8da9418c6d5fad0e244591fd05e6f5190c9.
No running backend observed in agent environment; actual process environment remains
operator-gated. Migration approval is not permission to edit SQLx history.

## 1. Preflight in the SAME VS Code terminal environment used to launch debug

```bash
cd /home/dinh-huynh-nguyen-khang/Projects_PBL4/idps-web-aws
python3 security-web/scripts/inspect-shadow-runtime.py
ss -ltnp 'sport = :3000'
```

Set WS_OLD_PID manually to that verified Rust PID (not cargo PID). Do not guess or
use broad pkill. Inspector reports binary/cwd and initial allowlisted env, sanitized
DB host/port/name only. If DATABASE_URL absent there, dotenv may have loaded it after
exec; absence is NOT an error/default. Confirm the actual connection with the prior
TCP evidence, inspect .env privately and the VS Code launch/task overrides. Do not
print full env. Require DB127.0.0.1:5433/pbl4_security and APP_ADDR127.0.0.1:3000.
Keep the existing auth secrets, source paths and other settings. If active config is
not reconstructable from private env plus launch overrides, BLOCKED: do not stop yet.

Refresh ALL migration checks immediately before cutover:

```bash
umask 077
docker exec pbl4-postgres psql -X -At -v ON_ERROR_STOP=1 -U pbl4 -d pbl4_security \
  -c "SELECT coalesce(json_agg(x ORDER BY version),'[]'::json) FROM (SELECT version,success,encode(checksum,'hex') AS checksum FROM _sqlx_migrations) x" \
  > /tmp/ws-applied-migrations.json
python3 security-web/scripts/check-shadow-migrations.py /tmp/ws-applied-migrations.json
```

STOP unless all15 valid and pending=[]. No new binary execution yet. Check read access
as ordinary Rust user: `test -r /var/log/suricata/eve.json` and
`test -r /var/log/suricata/chain.tsv`. Also confirm rotated logs retain access; no HMAC
key access required. Use existing approved DB backup; no migration/down migration needed.

## 2. Preserve running executable and frontend; stage privately

```bash
# Set exact PID from step1; example syntax only: WS_OLD_PID=12345
: "${WS_OLD_PID:?Set verified Rust PID}"
WS_OLD_CWD=$(readlink -f "/proc/$WS_OLD_PID/cwd")
WS_RELEASE="$HOME/ws-rust-shadow-$(date +%Y%m%d-%H%M%S)"
mkdir -m 0700 "$WS_RELEASE"
mkdir -m 0700 "$WS_RELEASE/backup" "$WS_RELEASE/candidate"
cp "/proc/$WS_OLD_PID/exe" "$WS_RELEASE/backup/pbl4-security-demo"
chmod 0700 "$WS_RELEASE/backup/pbl4-security-demo"
mkdir "$WS_RELEASE/backup/frontend"
cp -a "$WS_OLD_CWD/frontend/dist" "$WS_RELEASE/backup/frontend/dist"
cp -a /tmp/ws-rust-shadow-candidate/. "$WS_RELEASE/candidate/"
printf '%s\n' "$WS_OLD_CWD" > "$WS_RELEASE/backup/original-cwd.txt"
```

Privately copy the effective dotenv file to backup/.env and candidate/.env; if dotenv
was found in a parent directory, use that ACTUAL file. Save needed launch env overrides
privately, never into Git. Do not assume cwd/.env existed or captured every export.
Do not source .env as shell code. Retain the terminal's original exports for rollback.
Check manifest in candidate:

```bash
python3 - "$WS_RELEASE/candidate" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);m=json.loads((p/'manifest.json').read_text())
for name,h in m['sha256'].items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h,name
print('PASS artifact checksums')
PY
```

Record WS_RELEASE and WS_OLD_PID. Ensure backup files and old env reconstruct the
known-good service before continuing. Preserve other relative paths/resources used by
original configuration; convert them to reviewed absolute paths in candidate env.
Frontend is served relative to cwd, hence candidate/frontend/dist is mandatory.

## 3. Review candidate env ONLY (never production .env)

Keep confirmed DATABASE_URL and auth settings in candidate/.env (mode0600). Set these
values in candidate/.env too so a future launch does not silently use old topology:

```dotenv
APP_ADDR=127.0.0.1:3000
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
AI_SHADOW_RESULTS_PATH=
```

AI worker is still deferred. Blank results path prevents new AI file watcher; historical
AI DB data remains. Do not start worker or modify NGINX telemetry. Keep other inherited
env deliberate: dotenv does not overwrite exports. The explicit launch below pins
security flags and unsets DATABASE_URL so reviewed candidate dotenv selects DB.

## 4. Stop old Rust, then start ONE candidate (operator approval point)

Ctrl+C in the terminal that owns old cargo run; for VS Code debug use Stop Debugging.
Do not launch while a task auto-restarts it. Confirm old PID gone and no3000 listener:

```bash
if kill -0 "$WS_OLD_PID" 2>/dev/null; then echo 'BLOCKED: old process still alive'; else echo 'Old process stopped'; fi
ss -ltnp 'sport = :3000'
```

STOP if PID still alive or any listener remains. Then in a new terminal, set recorded
WS_RELEASE and run foreground (not sudo, no nohup/no second cargo run):

```bash
cd "$WS_RELEASE/candidate"
env -u DATABASE_URL APP_ADDR=127.0.0.1:3000 \
 SURICATA_EVE_PATH=/var/log/suricata/eve.json SURICATA_LUA_PATH=/var/log/suricata/chain.tsv \
 SURICATA_CAPTURE_MODE=post-proxy SURICATA_PROXY_IP=127.77.0.1 SURICATA_WEB_IP=127.77.0.2 \
 SURICATA_WEB_PORT=18080 SURICATA_POST_PROXY_INTERFACE=lo \
 SURICATA_TRUSTED_EDGE_CONFIRMED=false SURICATA_EVE_GENERATION_HOST=true \
 AUTO_BLOCK=false ENFORCEMENT_MODE=OFF AI_SHADOW_RESULTS_PATH= \
 ./pbl4-security-demo
```

Startup still invokes SQLx migrate: pending=[] is mandatory, don't disable validation.
If an unexpected migration/checksum error occurs STOP; don't alter migration history.
Brief Dashboard API downtime expected. Student/Suricata/NGINX stay running untouched.

## 5. Health and Dashboard

From another terminal:

```bash
curl --noproxy '*' --max-time 5 -sS http://127.0.0.1:3000/api/ready
python3 /home/dinh-huynh-nguyen-khang/Projects_PBL4/idps-web-aws/security-web/scripts/inspect-shadow-runtime.py
```

If ready requires auth use authenticated Dashboard network panel, never paste tokens.
Verify exactly one backend, intended binary/cwd and loopback flags; both SURICATA and
SURICATA_LUA watcher successful reads, new-data timestamps and draining backlog. Confirm
current native alert SID/time/flow/tx in DB and same Dashboard record. If none newly
exists, mark NOT_VERIFIED and request/approve a separate safe marker; don't infer from
HTTP401. Lua evidence must match generation/flow/tx plus rid checks: MATCHED_SHADOW is
not Verified. Old missing generation remains PENDING_GENERATION; pending/mismatch must
remain visible. Never infer loopback client identity. All enforcement flags OFF.
Do not inject fake EVE, truncate logs or clear cursors. Restart/dedup acceptance needs
another deliberate maintenance action; previous isolated tests do not prove runtime.

## 6. Rollback without schema rollback

Ctrl+C candidate terminal. Confirm no3000 listener/no candidate process. Use the saved
original env exports in original terminal and original cwd (production .env unchanged),
then run `$WS_RELEASE/backup/pbl4-security-demo` directly, not cargo run (which may
rebuild NEW code). If old frontend was changed separately restore backup/frontend/dist
only while backend is stopped. Original cwd paths must be intact. Check ready/native
alerts and old configuration. If recreating env is uncertain, STOP rather than guess.

Migration0015 is already production-applied BEFORE this rollout; keep all migration
history, new evidence, cursors and schema. Never delete0015 or restore the DB dump as
routine binary rollback. DB restore loses post-backup records and requires separate
approval, writer shutdown and an additional current backup. No DB rollback command is
authorized here. Sensor Generation is unaffected by Rust rollback.
