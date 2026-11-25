#!/bin/bash
# Install only the boot guard. Leave publishers, grants and Edge untouched.
set -euo pipefail
src=$(dirname "$(realpath "$0")")
(( EUID == 0 )) || exec sudo bash "$src/install-lan-guard.sh"
fix=/opt/ws-native/runtime-fix
unit=ws-native-lan-guard.service
exec 9>/run/lock/ws-native-auto
flock -n 9
check_off() {
    if systemctl is-active --quiet ws-native-continuous.service ||
       systemctl is-enabled --quiet ws-native-continuous.service; then
        echo 'BLOCKED: continuous active or enabled' >&2
        exit 1
    fi
    python3 -I - <<'PY'
import json,time
from pathlib import Path
p=Path('/etc/ws-native/approval.json')
if p.exists():
    grant=json.loads(p.read_bytes())
    if grant.get('mode')=='CONTINUOUS' or int(grant['end'])>time.time():
        raise SystemExit('BLOCKED: existing enforcement authorization')
PY
}
check_off
test -d "$fix"
for dir in /opt /opt/ws-native "$fix" /etc/ws-native /etc/ws-native/lan-cutover; do
    [[ $(realpath "$dir") == "$dir" && $(stat -c %u "$dir") == 0 ]]
    (( (8#$(stat -c %a "$dir") & 022) == 0 ))
done
copy() {
    local temp
    if cmp -s "$1" "$2" && [[ ! -L $2 && $(stat -c %u:%g:%a "$2") == 0:0:644 ]]; then return; fi
    temp=$(mktemp --tmpdir="$(dirname "$2")")
    install -o root -g root -m 0644 "$1" "$temp"
    mv -fT "$temp" "$2"
}
for file in continuous.py direct-peer.nft.example native_policy.py direct_peer.py; do
    copy "$src/$file" "$fix/$file"
done
/usr/bin/python3 -EB "$fix/continuous.py" enroll-guard
copy "$src/$unit" "/etc/systemd/system/$unit"
install -d -m0755 "/etc/systemd/system/$unit.d"
printf '[Service]\nEnvironment=WS_REQUIRE_GUARD_BINDING=1\n' | install -m0644 /dev/stdin "/etc/systemd/system/$unit.d/90-approved-network.conf"
systemctl daemon-reload
systemctl restart "$unit"
systemctl is-active --quiet "$unit"
nft -j list set inet ws_native_lab_peer edge_peers | python3 -c '
import sys,json
s,=[i["set"] for i in json.load(sys.stdin)["nftables"] if "set" in i]
if s["name"]!="edge_peers" or s.get("elem"): sys.exit("BLOCKED: expected empty edge_peers")'
check_off
systemctl enable "$unit"
systemctl is-enabled --quiet "$unit"
echo 'READY: approved kernel fingerprint, empty edge_peers, guard active/enabled, CONTINUOUS OFF'
