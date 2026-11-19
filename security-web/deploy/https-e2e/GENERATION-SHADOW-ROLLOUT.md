# Generation + Lua Shadow: operator review, not deployment approval

For the now-confirmed Type=notify Sensor-only rollout, use
[SENSOR-GENERATION-ONLY.md](SENSOR-GENERATION-ONLY.md); its procedure supersedes section A below.

## Evidence and gates

Operator reports latest live 15/15, pending=[], Rust72/2 and isolated PostgreSQL4/4
PASS. These supersede the earlier NOT_RUN entries in GENERATION-POSTGRES-ACCEPTANCE.md;
this session did not rerun privileged live tests or PostgreSQL. Production HTTPS is
reported healthy. AI DEFERRED, AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF, Unverified.

Disk inspection found 99-pbl4-local-egress.conf pointing to local-egress.yaml, lo,
and enabled Lua. Host system bus is inaccessible in the agent environment; no visible
Rust process. Effective systemd configuration, VS Code launch environment, actual DB,
/api/ready and native alert delivery remain NOT_VERIFIED. Do not deploy B until these
are checked. Disk .env and /proc initial environment alone do not prove dotenv values.

## A. Minimal bundle (no NGINX or YAML replacement)

Prepared /tmp/ws-generation-only-review contains launcher, shared Lua, one new drop-in
and manifest of current YAML/Lua/unit hashes. No certificate/key/config copy to Git.
Recreate with a NEW directory if production has changed; never bypass drift failures.

Read-only preparation:

```bash
python3 security-web/scripts/stage-sensor-generation.py check /tmp/ws-generation-only-review
systemctl cat suricata --no-pager
systemctl show suricata -p Type -p ExecStart -p FragmentPath -p DropInPaths -p MainPID
python3 security-web/scripts/inspect-shadow-runtime.py
```

BLOCKED until effective ExecStart matches the bundle's reviewed original command:
/usr/bin/suricata -D --af-packet -c /etc/suricata/pbl4/local-egress.yaml
--pidfile /var/run/suricata/suricata.pid. Review unit overrides including /run, service
Type=notify compatibility (keep the verified service Type), Python access and confinement. No new second sensor.
Manifest hashes detect disk drift, not hostile privileged administrators.

Following commands are proposed for separate operator approval, NOT executed. Stop
on any failure. Run from repository root. Confirm destination paths absent first;
otherwise stop and add their existing contents to backup (do not overwrite blindly).

```bash
set -euo pipefail
WS_GEN_BUNDLE=/tmp/ws-generation-only-review
WS_GEN_BACKUP=/var/backups/ws-generation-$(date +%Y%m%d-%H%M%S)
test ! -e /usr/local/libexec/websentinel/run-suricata-generation.py
test ! -e /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
python3 security-web/scripts/stage-sensor-generation.py check "$WS_GEN_BUNDLE"
sudo install -d -m 0700 "$WS_GEN_BACKUP"
sudo cp -a "$WS_GEN_BUNDLE" "$WS_GEN_BACKUP/bundle"
sudo chown -R root:root "$WS_GEN_BACKUP/bundle"
sudo tar --acls --xattrs --numeric-owner -cpf "$WS_GEN_BACKUP/sensor.tar" \
  /etc/suricata/pbl4 /etc/systemd/system/suricata.service.d
sudo sh -c 'systemctl cat suricata > "$1/effective-unit.txt"' sh "$WS_GEN_BACKUP"
sudo cp -a /var/log/suricata/proof-generation "$WS_GEN_BACKUP/previous-generation"
sudo sh -c 'cd "$1" && sha256sum sensor.tar previous-generation effective-unit.txt > SHA256SUMS && sha256sum -c SHA256SUMS' sh "$WS_GEN_BACKUP"
sudo python3 security-web/scripts/stage-sensor-generation.py check "$WS_GEN_BACKUP/bundle"
```

Check reviewed Lua checksum equals config/suricata/transaction-evidence.lua. The
launcher uses a fresh random generation per exec; native EVE sensor-name and Lua
startup environment share it. Existing logs are neither rewritten nor relabelled.
Suricata syntax check must use the candidate Lua, not just the currently installed
one: stage a temporary YAML with scripts-dir pointing at root-owned bundle and run
`suricata -T -c <temporary YAML> -l <temporary log directory>`. This needs operator
approval; no live capture or daemon should be started by this check. Remove only the
temporary validation files after reading results. If Suricata cannot validate Lua,
stop. Existing offline/live tests do not replace this Host configuration check.

After backup AND successful syntax review, proposed install:

```bash
sudo install -d -m 0755 /usr/local/libexec/websentinel
sudo install -m 0755 "$WS_GEN_BACKUP/bundle/run-suricata-generation.py" /usr/local/libexec/websentinel/run-suricata-generation.py
sudo install -m 0644 "$WS_GEN_BACKUP/bundle/transaction-evidence.lua" /etc/suricata/pbl4/transaction-evidence.lua
sudo install -m 0644 "$WS_GEN_BACKUP/bundle/zz-websentinel-generation.conf" /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
sudo systemctl daemon-reload
sudo systemctl restart suricata
systemctl is-active suricata
sudo python3 security-web/scripts/check-generation-canary.py \
  --edge-ca "$HOME/websentinel-lab.crt" \
  --previous-generation "$(sudo cat "$WS_GEN_BACKUP/previous-generation")"
```

Canary sends ONE GET /api/auth/me with unique query via HTTPS; requires401 and request
ID. It snapshots file inode/offset before request, matches exact flow/tx/rid/new gen,
requires EVE host + lo topology, and rejects rotation/restart during checkpoint.
Does not print proof/receipt. This checks metadata correlation, NOT cryptographic
Verified. Also check FE200/API401 and Suricata journal for Lua/permission errors.
NGINX not restarted; sensor restart creates a short monitoring gap. Keep old logs.

A rollback (operator only, use exact backup path; no NGINX/firewall changes):

```bash
sudo systemctl stop suricata
sudo rm /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
sudo tar -xpf "$WS_GEN_BACKUP/sensor.tar" -C / etc/suricata/pbl4/transaction-evidence.lua
sudo rm /usr/local/libexec/websentinel/run-suricata-generation.py
sudo systemctl daemon-reload
sudo systemctl start suricata
systemctl is-active suricata
```

Restore only files this rollout changed; do not unpack entire YAML/unit backup over
newer unrelated configuration. Old profile stays local-egress (not vmnet3). Old
launcher-free records may lack EVE generation; Rust must retain PENDING_GENERATION.
Verify fresh EVE/Lua and HTTP health; do not call generation-specific checkpoint PASS
on rollback. Keep generation logs and backup for investigation.

## B. Rust, DB and Dashboard (separate approval)

1. Operator runs inspect-shadow-runtime.py from VS Code terminal, checks parent PID,
   cwd and launch/task config locally. Do not paste full env, launch arguments or DB
   password. Read authenticated Dashboard /api/ready + System Status: source paths,
   last successful read/new data, errors/backlog. Confirm actual database with a
   read-only SQL session: current_database(), inet_server_addr(), inet_server_port(),
   current_user. Compare with intended DB, not just .env. Do not expose credentials.
2. Use read-only SQL in GENERATION-POSTGRES-ACCEPTANCE.md to join native SID/time/event
   key/flow/tx to DB alert. Check same alert in Dashboard. No new native alert means
   NOT_VERIFIED; the optional single XSS marker command in that doc requires operator
   choice. Agent has not sent it. HTTP401 canary itself need not generate a SID alert.
3. Review all pending migrations, not only0015. main.rs automatically runs ALL pending
   migrations before server startup. Build without running; preserve known-good binary,
   frontend assets and private env. Do not run cargo run/new binary before DB approval.
4. In the CONFIRMED production DB, use pg_dump custom-format to a restricted backup,
   record SHA256 and test pg_restore in an isolated database. Example on confirmed
   pbl4-postgres container ONLY (first verify this is the actual backend DB):

```bash
umask 077
WS_DB_DUMP="$HOME/ws-db-before-shadow-$(date +%Y%m%d-%H%M%S).dump"
docker exec pbl4-postgres pg_dump -U pbl4 -d pbl4_security -Fc > "$WS_DB_DUMP"
test -s "$WS_DB_DUMP"
sha256sum "$WS_DB_DUMP"
docker exec -i pbl4-postgres pg_restore --list < "$WS_DB_DUMP" >/dev/null
```

Archive listing is NOT restore acceptance. Restore into isolated PostgreSQL and
verify schema/history/counts before approving migration; never restore over production
as a test. Stop if container/database identity differs, dump fails or restore fails.
5. Proposed environment (reviewed file only, do not edit production now):

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

Ensure VS Code shell exports do not override proposed values; dotenv does not overwrite
existing env. Confirm Rust UID has read permissions for both logs and newly rotated
files without granting HMAC-key access. Keep AI deferred. Stop old backend before
starting approved new version to avoid concurrent watchers. Expect brief Dashboard
API downtime, no NGINX/Student downtime. Migration0015 is additive (tables/view);
no HMAC evidence content persisted, only metadata/hash/presence. DB size/retention of
seen records must be monitored; do not delete conflict/checkpoint state casually.
6. Acceptance after approved rollout: both watchers fresh and backlog drains; new
native alert visible, correct SID/severity/time/network IP; exact generation/flow/tx
and optional rid match -> MATCHED_SHADOW, never Verified. Legacy missing generation ->
PENDING_GENERATION. Delayed evidence -> pending then match, contradictory evidence ->
MISMATCHED. Check real restart/dedup only in an approved backend maintenance window;
use existing isolated tests for destructive rotation/conflict cases, never inject
fake records into production logs or clear production offsets. Dashboard must show
Lua Shadow separately from verified client attribution. Loopback is network IP only.

B rollback: stop new backend using the same VS Code/manual launch mechanism; restore
old binary/frontend/private env and start once. Leave additive0015 schema and migration
history intact; do not drop tables or rewind checkpoints. Verify old binary compatibility
with added schema in isolated restore first. A full DB restore requires separate
approval and coordinated downtime because newer alerts/audits would be lost. Roll
back A independently only if generation itself failed. No auto downgrade of database.

## Remaining BLOCKED before production approval

- Effective Host unit, Rust process/VS Code env and database identity not observable here.
- Native alert EVE -> actual DB -> Dashboard not yet verified here.
- Host candidate syntax/confinement, log permissions and production backup restore.
- Approval of pending migrations and exact backend launch/rollback artefacts.
- Post-restart production generation checkpoint is necessarily NOT_RUN until approved.
- No Client IP Verified approval: HMAC timing/revocation/completion limitations remain.
