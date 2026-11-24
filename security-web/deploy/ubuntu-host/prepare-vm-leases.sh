#!/bin/bash
# Host-side interactive provisioning; no service restart and no policy activation.
set -euo pipefail
src=$(dirname "$(realpath "$0")")
repo=$(realpath "$src/../../..")
files=(student-web/backend/src/main/java/com/pbl4/studentweb/configuration/{SecurityConfiguration,ActiveAccountFilter,DevSessionLease}.java)
if [[ ${1:-} == --digest ]]; then
    cd "$repo"
    sha256sum "${files[@]}" "$src"/{install-vm-leases.sh,start-vm-lease-backend.sh,vm-leases.py} "$src/../dev-i5/adaptive/approve_session.py" | sha256sum | cut -d' ' -f1
    exit 0
fi
vm=khang1901@192.168.20.10
# Require a previously authenticated host key, never bootstrap from ssh-keyscan.
ssh -o StrictHostKeyChecking=yes "$vm" true
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
ssh-keygen -F 192.168.20.10 -f "$HOME/.ssh/known_hosts" | sed '/^#/d' > "$tmp/known"
test -s "$tmp/known"
put_new() {
    if sudo test -e "$2"; then sudo cmp "$1" "$2"; else sudo install -o root -g "$3" -m "$4" "$1" "$2"; fi
}
put_new "$tmp/known" /etc/ws-native/student-known-hosts root 644
if ! sudo test -e /etc/ws-native/lease-ssh; then
    ssh-keygen -q -t ed25519 -N '' -f "$tmp/lease-key"
    sudo install -o ws-native-actuator -m400 "$tmp/lease-key" /etc/ws-native/lease-ssh
fi
sudo -u ws-native-actuator ssh-keygen -y -f /etc/ws-native/lease-ssh > "$tmp/key.pub"
dest=$(ssh "$vm" 'mktemp -d')
[[ $dest =~ ^/tmp/tmp\.[a-zA-Z0-9]+$ ]]
ssh "$vm" "mkdir -p '$dest/ubuntu-host' '$dest/dev-i5/adaptive'"
scp "$src/install-vm-leases.sh" "$src/start-vm-lease-backend.sh" "$src/vm-leases.py" "$tmp/key.pub" "$vm:$dest/ubuntu-host/"
scp "$src/../dev-i5/adaptive/approve_session.py" "$vm:$dest/dev-i5/adaptive/"
files=(student-web/backend/src/main/java/com/pbl4/studentweb/configuration/{SecurityConfiguration,ActiveAccountFilter,DevSessionLease}.java)
for f in "${files[@]}"; do
    name=${f##*/}
    scp "$repo/$f" "$vm:$dest/$name"
    if git -C "$repo" cat-file -e "HEAD:$f" 2>/dev/null; then
        git -C "$repo" show "HEAD:$f" > "$tmp/$name.base"
        scp "$tmp/$name.base" "$vm:$dest/"
    fi
done
ssh "$vm" bash -s -- "$dest" "${files[@]}" <<'VM_COPY'
set -eu
cd ~/idps-web-aws
stage=$1
shift
for f; do
    name=${f##*/}
    if [[ -e $f ]]; then
        cp -p "$f" "$stage/$name.before"
        if [[ -f $stage/$name.base ]] && ! cmp -s "$f" "$stage/$name"; then
            git merge-file -p "$f" "$stage/$name.base" "$stage/$name" > "$stage/$name.merged"
            mv "$stage/$name.merged" "$stage/$name"
        fi
    fi
done
for f; do install -m644 "$stage/${f##*/}" "$f"; done
VM_COPY
ssh -t "$vm" "sudo bash '$dest/ubuntu-host/install-vm-leases.sh' '$dest/ubuntu-host/key.pub' khang1901"
sudo -u ws-native-actuator python3 -IB -c "exec(__import__('sys').stdin.read());print(deliver('ready'))" < "$src/vm_transport.py"
bash "$src/prepare-vm-leases.sh" --digest > "$tmp/prepared"
sudo install -o root -g root -m644 "$tmp/prepared" /etc/ws-native/vm-lease-transport-prepared
echo "VM source backups: $dest. In the previous VM backend terminal stop Spring Boot, then run: bash '$dest/ubuntu-host/start-vm-lease-backend.sh'"
