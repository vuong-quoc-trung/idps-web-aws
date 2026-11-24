#!/bin/bash
# Operator entry point. No Student VM changes, nft mutations or Edge startup.
set -Eeuo pipefail
src=$(dirname "$(realpath "$0")")
repo=$(realpath "$src/../../..")
ca=${WS_STUDENT_CA:-"$HOME/ws-student-trust/ca.crt"}
if (( EUID != 0 )); then
    (cd "$repo/security-web" && cargo build --offline --release --features dev-hybrid-review)
    (cd "$repo/security-web/frontend" && npm run build)
    test -x "$repo/security-web/target/release/pbl4-security-demo"
    test -s "$repo/security-web/frontend/dist/index.html"
    exec sudo bash "$src/apply-runtime-fix.sh" "$ca"
fi
ca=${1:-$ca}
live=/opt/ws-native/current
fix=/opt/ws-native/runtime-fix
etc=/etc/ws-native
units=/etc/systemd/system
exec 9>/run/lock/ws-native-dashboard-repair
flock -n 9
for u in ws-native-edge.service ws-native-worker.service ws-native-worker.timer; do
    case $(systemctl show -p ActiveState --value "$u") in inactive|failed) ;; *) echo "BLOCKED: $u"; exit 1;; esac
done
grep -Fxq AUTO_BLOCK=false "$etc/security.env"
grep -Fxq ENFORCEMENT_MODE=OFF "$etc/security.env"
test ! -e "$etc/approval.json"
# Edge stays stopped; upstream availability is a cutover checkpoint.
openssl x509 -in "$ca" -noout -checkend 0
backup=$(mktemp -d /var/backups/ws-native-dashboard.XXXXXXXX)
echo "Backup: $backup"
paths=("$etc/nginx.conf" "$etc/suricata.yaml" "$etc/student-ca.crt" "$units/ws-native-edge.service" "$units/ws-native-security.service.d/70-native-runtime.conf" "$units/ws-native-fw-status.socket" "$units/ws-native-fw-status@.service" "/etc/logrotate.d/ws-native-observation" "$fix")
for p in "${paths[@]}"; do
    if [[ -e $p ]]; then cp -a --parents "$p" "$backup"; fi
done
active=()
for u in ws-native-security ws-native-fw-status.socket; do
    if systemctl is-active --quiet "$u"; then active+=("$u"); fi
done
rollback() {
    trap - ERR
    set +e
    systemctl stop ws-native-security ws-native-fw-status.socket
    for p in "${paths[@]}"; do
        if [[ -e "$backup$p" ]]; then cp -aT "$backup$p" "$p"; elif [[ $p != "$fix" ]]; then rm -f -- "$p"; fi
    done
    setfacl --restore="$backup/log.acl"
    systemctl daemon-reload
    for u in "${active[@]}"; do systemctl start "$u"; done
    echo "Runtime rolled back; backup: $backup" >&2
    exit 1
}
getfacl -p /var/lib/ws-native/{edge,sensor} /var/log/pbl4 > "$backup/log.acl"
find /var/lib/ws-native/edge /var/lib/ws-native/sensor /var/log/pbl4 -maxdepth 1 -type f \( -name 'access.jsonl' -o -name 'error.log' -o -name 'eve.json' -o -name 'chain.tsv' -o -name 'student-audit.log*' \) -exec getfacl -p {} + >> "$backup/log.acl"
trap 'rc=$?; echo "FAILED line $LINENO: $BASH_COMMAND (exit $rc)" >&2; rollback' ERR
install -d -m0755 "$fix/frontend" "$units/ws-native-security.service.d"
install -m0755 "$repo/security-web/target/release/pbl4-security-demo" "$fix/security.new"
mv "$fix/security.new" "$fix/security"
cp -rT "$repo/security-web/frontend/dist" "$fix/frontend/dist"
chmod -R a+rX,go-w "$fix/frontend"
install -m0644 "$src/fw-status.py" "$fix/fw-status.py"
install -m0644 "$src"/ws-native-fw-status{.socket,@.service} "$units/"
install -m0644 "$ca" "$etc/student-ca.crt"
# Preserve existing settings and credentials. Refuse unfamiliar configuration.
python3 -B - "$src" "$etc" "$units" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from native_vm import nginx
etc,units=map(Path,sys.argv[2:])
cfg=etc/"nginx.conf"
cfg.write_text(nginx(cfg.read_text()))
edge=units/"ws-native-edge.service"
edge.write_text(edge.read_text().replace(" ws-native-student.service",""))
PY
cat >"$units/ws-native-security.service.d/70-native-runtime.conf" <<'EOF'
[Unit]
Wants=ws-native-fw-status.socket
After=ws-native-fw-status.socket
[Service]
ExecStart=
ExecStart=/opt/ws-native/runtime-fix/security
WorkingDirectory=/opt/ws-native/runtime-fix
Environment=WS_NATIVE_FIREWALL_SOCKET=1
Environment=WS_NATIVE_SCHEMA_CHECK_ONLY=1
EnvironmentFile=/opt/ws-native/runtime-fix/vm-audit.env
NoNewPrivileges=yes
EOF
test -f /var/log/pbl4/student-audit.log
printf 'STUDENT_AUDIT_LOG_PATH=/var/log/pbl4/student-audit.log\n' > "$fix/vm-audit.env"
# The existing receiver owns rotation; leave its output and service unchanged.
setfacl -m u:ws-native-security:r-x,d:u:ws-native-security:r-X /var/log/pbl4
find /var/log/pbl4 -maxdepth 1 -type f -name 'student-audit.log*' ! -name '*.gz' -exec setfacl -m u:ws-native-security:r {} +
# Producer creates each file; set-group-ID and ACL provide read access on recreation.
for spec in edge sensor; do
    d=/var/lib/ws-native/$spec
    test -d "$d" && test ! -L "$d"
    setfacl -m u:ws-native-security:r-x,d:u:ws-native-security:r-X "$d"
done
for f in /var/lib/ws-native/edge/{access.jsonl,error.log} /var/lib/ws-native/sensor/{eve.json,chain.tsv}; do
    if [[ -f $f ]]; then setfacl -m u:ws-native-security:r "$f"; fi
done
install -m0644 "$src/native-logrotate" /etc/logrotate.d/ws-native-observation
systemctl daemon-reload
systemctl restart ws-native-fw-status.socket
systemctl restart ws-native-security
for ((i=0;i<30;i++)); do
    if curl --noproxy '*' --max-time 2 -fsS http://127.0.0.1:23000/health >/dev/null 2>&1; then break; fi
    sleep 1
done
pid=$(systemctl show ws-native-security -p MainPID --value)
test "$pid" -gt 1
test "$(readlink "/proc/$pid/exe")" = "$fix/security"
test "$(readlink "/proc/$pid/cwd")" = "$fix"
cmp "$repo/security-web/target/release/pbl4-security-demo" "/proc/$pid/exe"
test "$(systemctl show ws-native-security -p NoNewPrivileges --value)" = yes
python3 -B "$src/check-runtime-fix.py"
echo "Dashboard runtime PASS; PID=$pid SHA256=$(sha256sum "/proc/$pid/exe" | cut -d' ' -f1). Edge and enforcement remain stopped."
