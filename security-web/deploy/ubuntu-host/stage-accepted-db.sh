#!/bin/bash
# Stage only the pinned release. Edge and the enforcement worker stay stopped.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
state="${HOME}/.local/state/ws-native-database"
expected=5094ef38f5882492b56b98d5ec310ff11c9fa38b5ec0d6e99a3a4d75716b85f4
live=/opt/ws-native/current
sudo -v
exec 9<"$0"
flock -n 9 || { echo 'Staging already running'; exit 1; }
stage=$(sudo mktemp -d /var/tmp/ws-native-stage.XXXXXXXX)
for f in install-first.sh preflight.py docker_pg.py; do
    sudo install -o root -g root -m 0644 "$here/$f" "$stage/$f"
done
if sudo test -e "$live" || sudo test -L "$live"; then
    bundle=$live
    sudo test "$(sudo realpath "$live")" = "$live"
else
    bundle="$stage/release"
    sudo cp -rP --no-preserve=ownership /tmp/ws-native-db-accepted-01 "$bundle"
    sudo chmod -R go-w "$bundle"
fi
marker=/etc/ws-native/staging-db-accepted
if sudo test -e "$marker"; then
    # A previous invocation reached DB acceptance and only service startup remains.
    sudo bash -eu -o pipefail -c '
        cd "$1"
        test "$(realpath "$1")" = "$1"
        test -z "$(find . \( ! -user root -o -perm /022 -o -type l \) -print -quit)"
        test "$(stat -c %u:%a "$2")" = 0:600 && test ! -L "$2"
        test "$(cat "$2")" = "$3"
        printf "%s  SHA256SUMS\n" "$3" | sha256sum --status -c -
        diff <(find . -type f ! -path ./SHA256SUMS -printf "%P\n" | LC_ALL=C sort) <(cut -c67- SHA256SUMS | LC_ALL=C sort)
        sha256sum --quiet -c SHA256SUMS
        for u in units/*; do
            cmp "$u" "/etc/systemd/system/${u##*/}"
            test -z "$(systemctl show -p DropInPaths --value "${u##*/}")"
        done
        test ! -e /etc/ws-native/approval.json
        grep -Fxq ENFORCEMENT_MODE=OFF /etc/ws-native/security.env
        grep -Fxq AUTO_BLOCK=false /etc/ws-native/security.env
    ' _ "$live" "$marker" "$expected"
else
    sudo bash "$stage/install-first.sh" "$bundle" "$expected"
    sudo python3 -B "$live/stage-db-config.py" "$state"
    printf '%s\n' "$expected" | sudo install -m 0600 /dev/stdin "$marker"
fi

started=()
rollback_started() {
    local rc=$?
    trap - EXIT
    if ((rc && ${#started[@]})); then sudo systemctl stop "${started[@]}"; fi
    exit "$rc"
}
trap rollback_started EXIT
for unit in ws-native-security ws-native-sensor ws-native-scorer ws-native-gate; do
    if ! systemctl is-active --quiet "$unit"; then
        started+=("$unit")
        sudo systemctl start "$unit"
    fi
done
ready() {
    curl --noproxy '*' --max-time 3 -fsS http://127.0.0.1:23000/health >/dev/null &&
    sudo test -S /run/ws-native-gate/gate.sock &&
    sudo runuser -u ws-native-edge -- curl --max-time 3 -fsSi --unix-socket /run/ws-native-shadow/receiver.sock http://localhost/healthz |
        tr -d '\r' | grep -Fxi "x-model-sha256: $(sudo sha256sum "$live/scorer/ai-training/contracts/quality-freeze-r37/release/finalist.onnx" | cut -d' ' -f1)" >/dev/null
}
for ((i=0;i<60;i++)); do
    if ready 2>/dev/null; then
        for u in "${started[@]}"; do systemctl is-active --quiet "$u"; done
        sudo "$live/control.sh" status
        echo 'Staging health PASS. Edge and enforcement not started.'
        exit 0
    fi
    sleep 2
done
echo 'Staging health BLOCKED. Inspect ws-native unit journals.' >&2
exit 1
