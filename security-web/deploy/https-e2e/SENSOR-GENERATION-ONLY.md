# Sensor Generation only — manual rollout

Operator verified Type=notify, active Suricata, only 90/99 drop-ins, ExecStart:
`/usr/bin/suricata -D --af-packet -c /etc/suricata/pbl4/local-egress.yaml --pidfile /var/run/suricata/suricata.pid`.
This supersedes the earlier suggestion to check for Type=forking: KEEP Type=notify.
No Rust/DB/NGINX changes. AI DEFERRED, AUTO_BLOCK=false, Unverified stay unchanged.

`zz-websentinel-generation.conf` sorts after 90 and 99, resets ExecStart then installs
Python launcher ExecStart. It does not override Type, NotifyAccess, PIDFile, UMask or
ProtectHome. Python execve preserves PID/environment (including NOTIFY_SOCKET), then
runs the same Suricata executable/arguments plus sensor-name. Existing -D semantics
remain unchanged. Installed launcher is outside /home; stdlib only; no writable cache
or repository imports needed. UMask0077 is inherited. ProtectSystem=full permits reads
of launcher/Lua and existing writes under /var/log. No claim of systemd READY acceptance
until the operator restarts and observes it. A privileged administrator remains trusted.

## 1. Preflight (no changes)

Run from repo root. Keep this shell for the remaining steps; stop on any failed check.
Do not run the apply section until reviewing the backup and validation results.

```bash
set -euo pipefail
WS_GEN_BUNDLE=/tmp/ws-generation-only-review
python3 security-web/scripts/stage-sensor-generation.py check "$WS_GEN_BUNDLE"
systemctl cat suricata --no-pager
systemctl show suricata -p Type -p NotifyAccess -p ProtectHome -p UMask -p ExecStart -p DropInPaths
systemctl is-active suricata
test -x /usr/bin/python3
test ! -e /usr/local/libexec/websentinel/run-suricata-generation.py
test ! -e /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
```

Require the verified original ExecStart, Type=notify, ProtectHome=yes/true, UMask0077.
Stop on additional effective overrides (including /run drop-ins), unexpected sandbox
restrictions, different command, existing target paths, or checksum/drift failure.
Do not change NotifyAccess or service Type to force startup. The shell checker cannot
prove effective systemd state; the displayed output is a mandatory operator gate.

## 2. Root-owned backup and dry-run validation (operator sudo only)

```bash
WS_GEN_BACKUP=/var/backups/ws-generation-$(date +%Y%m%d-%H%M%S)
sudo install -d -m 0700 "$WS_GEN_BACKUP"
sudo cp -a "$WS_GEN_BUNDLE" "$WS_GEN_BACKUP/bundle"
sudo chown -R root:root "$WS_GEN_BACKUP/bundle"
sudo python3 security-web/scripts/stage-sensor-generation.py check "$WS_GEN_BACKUP/bundle"
sudo cp -a /etc/suricata/pbl4/transaction-evidence.lua "$WS_GEN_BACKUP/old.lua"
sudo cp -a /etc/suricata/pbl4/local-egress.yaml "$WS_GEN_BACKUP/original.yaml"
sudo cp -a /var/log/suricata/proof-generation "$WS_GEN_BACKUP/previous-generation"
sudo sh -c 'systemctl cat suricata --no-pager > "$1/effective-unit.txt"' sh "$WS_GEN_BACKUP"
sudo tar --acls --xattrs --numeric-owner -cpf "$WS_GEN_BACKUP/sensor.tar" /etc/suricata/pbl4 /etc/systemd/system/suricata.service.d
sudo sh -c 'cd "$1" && sha256sum old.lua original.yaml previous-generation effective-unit.txt sensor.tar > SHA256SUMS && sha256sum -c SHA256SUMS' sh "$WS_GEN_BACKUP"
```

Record WS_GEN_BACKUP outside this shell. Backup contains configuration; retain mode0700.
Prepare validation YAML from CURRENT production YAML, changing ONLY Lua scripts-dir
for the test. It is never copied to /etc. Python PyYAML is needed for this validation;
stop if unavailable (do not install packages automatically).

```bash
sudo install -d -m 0700 "$WS_GEN_BACKUP/validation-logs"
sudo /usr/bin/python3 - "$WS_GEN_BACKUP" <<'PY'
import sys, yaml
from pathlib import Path
b=Path(sys.argv[1])
c=yaml.safe_load((b/'original.yaml').read_text())
for o in c['outputs']:
    if 'lua' in o:
        assert o['lua']['enabled'] is True
        o['lua']['scripts-dir']=str(b/'bundle')
(b/'validation.yaml').write_text('%YAML 1.1\n---\n'+yaml.safe_dump(c))
PY
sudo /usr/bin/python3 "$WS_GEN_BACKUP/bundle/run-suricata-generation.py" \
  -T -c "$WS_GEN_BACKUP/validation.yaml" -l "$WS_GEN_BACKUP/validation-logs"
```

Require successful Suricata8.0.3 -T. This does not capture traffic or restart services.
It validates config/candidate Lua but not systemd readiness; the reported live E2E and
offline tests separately cover EVE/Lua equality. Keep validation output for audit.

## 3. Apply after explicit operator decision

Recheck drift immediately before installation. Do not alter existing90/99, YAML,
AF_PACKET, NGINX, firewall, Rust, log cursors or logs.

```bash
sudo python3 security-web/scripts/stage-sensor-generation.py check "$WS_GEN_BACKUP/bundle"
sudo install -d -m 0755 /usr/local/libexec/websentinel
sudo install -o root -g root -m 0755 "$WS_GEN_BACKUP/bundle/run-suricata-generation.py" /usr/local/libexec/websentinel/run-suricata-generation.py
sudo install -o root -g root -m 0644 "$WS_GEN_BACKUP/bundle/transaction-evidence.lua" /etc/suricata/pbl4/transaction-evidence.lua
sudo install -o root -g root -m 0644 "$WS_GEN_BACKUP/bundle/zz-websentinel-generation.conf" /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
sudo systemctl daemon-reload
systemctl show suricata -p Type -p ProtectHome -p UMask -p ExecStart -p DropInPaths
```

STOP and inspect: Type remains notify; ExecStart now `/usr/bin/python3
/usr/local/libexec/websentinel/run-suricata-generation.py -D --af-packet -c
/etc/suricata/pbl4/local-egress.yaml --pidfile /var/run/suricata/suricata.pid`.
Only zz override is new. If unexpected, rollback before restart. Then:

```bash
sudo systemctl restart suricata
systemctl is-active suricata
systemctl show suricata -p Type -p MainPID -p SubState -p Result
sudo cmp "$WS_GEN_BACKUP/original.yaml" /etc/suricata/pbl4/local-egress.yaml
sudo python3 security-web/scripts/check-generation-canary.py \
  --edge-ca "$HOME/websentinel-lab.crt" \
  --previous-generation "$(sudo cat "$WS_GEN_BACKUP/previous-generation")"
curl --noproxy '*' --cacert "$HOME/websentinel-lab.crt" --max-time 10 -sS -o /dev/null -w 'FE=%{http_code}\n' https://192.168.10.1/
```

Require systemd active/running, Result=success, fresh checkpoint PASS, FE200. Canary
expects API401 and a request ID, snapshots offsets BEFORE its unique GET, matches
EVE lo source/destination + flow/tx + EVE host with Lua nine-field generation and rid.
Generation must differ from backup and stay stable through checkpoint. Old EVE is
never relabelled. Rotation/truncation during checkpoint fails rather than guessing.
No raw proof/receipt/key is printed. This is Shadow metadata, not Verified.
On restart/checkpoint failure STOP and run rollback; do not proceed to Rust migration.
Suricata restart has a monitoring gap; NGINX traffic remains independent/passive.

## 4. Exact rollback (operator; also works after partial apply)

Use the recorded backup path. Validate backup before stopping service. Newly installed
paths must not have been repurposed by another change. This removes only this rollout's
zz override/launcher, restores old Lua and leaves 90/99 and YAML intact.

```bash
sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh "$WS_GEN_BACKUP"
sudo systemctl stop suricata
sudo rm -f /etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf
sudo cp -a "$WS_GEN_BACKUP/old.lua" /etc/suricata/pbl4/transaction-evidence.lua
sudo rm -f /usr/local/libexec/websentinel/run-suricata-generation.py
sudo systemctl daemon-reload
sudo sh -c 'systemctl cat suricata --no-pager > "$1/restored-unit.txt"; cmp "$1/effective-unit.txt" "$1/restored-unit.txt"' sh "$WS_GEN_BACKUP"
sudo cmp "$WS_GEN_BACKUP/original.yaml" /etc/suricata/pbl4/local-egress.yaml
systemctl show suricata -p Type -p ExecStart
sudo systemctl start suricata
systemctl is-active suricata
curl --noproxy '*' --cacert "$HOME/websentinel-lab.crt" --max-time 10 -sS -o /dev/null -w 'FE=%{http_code}\n' https://192.168.10.1/
curl --noproxy '*' --cacert "$HOME/websentinel-lab.crt" --max-time 10 -sS -o /dev/null -w 'API=%{http_code}\n' https://192.168.10.1/api/auth/me
```

Require old ExecStart exactly and FE200/API401. If effective-unit comparison fails,
inspect intervening changes rather than unpacking all backup over them. Confirm new
HTTP/Lua records after rollback; generation-specific health is no longer expected to
PASS on old launcher-free configuration. Never restore old log files/checkpoints or
the generation marker; startup owns the marker. No database rollback is involved.

## Acceptance status

Code/environment propagation, staging and offline generation tests PASS. Operator
reported privileged live generation PASS. Type=notify production launcher startup and
fresh-production generation checkpoint remain NOT_RUN until approved manual steps.
No known design blocker from Type=notify/ProtectHome/UMask; preflight failures are hard
stops, not waived. This is permission to review a procedure, not an automatic cutover.
