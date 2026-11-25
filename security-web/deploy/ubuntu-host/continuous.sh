#!/bin/bash
# Invoked under native-auto.sh's exclusive lifecycle lock.
set -Eeuo pipefail
src=$(dirname "$(realpath "$0")")
fix=/opt/ws-native/runtime-fix
etc=/etc/ws-native
units=/etc/systemd/system
policy=$etc/approval.json
unit=ws-native-continuous.service
act() { runuser -u ws-native-actuator -g ws-native-evidence -- "$@"; }
continuous() { [[ -f $policy ]] && python3 -c 'import json,sys;sys.exit(json.load(open(sys.argv[1])).get("mode")!="CONTINUOUS")' "$policy"; }
disable() {
    local failed=0
    if continuous; then mv -T "$policy" "$etc/continuous.revoked.$(date +%s%N).json"; fi
    systemctl disable --now "$unit" || failed=1
    systemctl stop ws-native-worker.timer ws-native-worker.service || failed=1
    act python3 -B "$fix/worker.py" stop || failed=1
    return "$failed"
}
if [[ $1 == continuous-disable ]]; then
    if [[ -e $policy ]] && ! continuous; then echo 'LAB policy in use; continuous-disable does not revoke LAB'; exit 1; fi
    disable
    exit
fi
if continuous; then
    python3 -B "$fix/continuous.py" check
    systemctl enable --now "$unit"
    systemctl is-active --quiet ws-native-worker.timer
    exec bash "$src/native-auto.sh" continuous-status
fi
echo 'Approve continuous enforcement for the four existing lab scopes, including boot restoration of the dedicated LAN nftables table. Lease TTLs request/session/account/IP: 15/30/60/15s. Type ENABLE-CONTINUOUS:'
read -r answer </dev/tty
[[ $answer == ENABLE-CONTINUOUS ]]
# Refuse promotion of an unknown or partial installation.
for name in security edge scorer sensor gate; do systemctl is-active --quiet "ws-native-$name"; done
test -f "$etc/direct-peer.json"
test -x "$fix/security"
act python3 -IB -c "exec(__import__('sys').stdin.read());deliver('ready')" < "$src/vm_transport.py"
timer_was=$(systemctl is-active ws-native-worker.timer || :)
systemctl stop ws-native-worker.timer ws-native-worker.service
on_failure() {
    local rc=$?
    trap - ERR
    if continuous; then disable
    elif [[ $timer_was == active && -f $policy ]]; then systemctl start ws-native-worker.timer
    fi
    exit "$rc"
}
trap on_failure ERR
# Quiesce publishers before atomically replacing files. Never clear decisions or consumed IDs.
for f in native_policy.py worker.py direct_peer.py ip-actuator.py continuous.py native-auto.sh direct-peer.nft.example; do
    install -m0644 "$src/$f" "$fix/$f.new"
    mv -T "$fix/$f.new" "$fix/$f"
done
install -m0644 "$src/../dev-i5/adaptive/approve_session.py" "$fix/approve_session.py.new"
mv -T "$fix/approve_session.py.new" "$fix/approve_session.py"
install -m0644 "$src"/{ws-native-continuous,ws-native-lan-guard}.service "$units/"
install -d "$units/ws-native-edge.service.d"
printf '[Unit]\nRequires=ws-native-lan-guard.service\nAfter=ws-native-lan-guard.service\n' > "$units/ws-native-edge.service.d/95-ws-native-lan-guard.conf"
systemctl daemon-reload
systemctl start ws-native-lan-guard.service
python3 -B "$fix/continuous.py" promote
act python3 -IB - <<'PY'
import sqlite3,time
with sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=rw", uri=True) as db:
    db.execute("BEGIN IMMEDIATE")
    if db.execute("SELECT 1 FROM decisions WHERE revoked=0 AND json_extract(plan,'$.expires')>? LIMIT 1",(time.time(),)).fetchone():
        raise SystemExit("Outstanding lease; retry after expiry")
    db.execute("UPDATE control SET stopped=0")
    db.execute("INSERT INTO audit(at,operator,action,rid,outcome) VALUES(?, 'operator','ALL','-','CONTINUOUS_ENABLED')",(int(time.time()),))
PY
systemctl enable --now "$unit"
systemctl is-active --quiet ws-native-worker.timer
exec bash "$src/native-auto.sh" continuous-status
