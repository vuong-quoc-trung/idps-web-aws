#!/bin/bash
# Run on Student VM with the host actuator public key and Student backend OS user.
set -euo pipefail
[[ $# == 2 && $EUID == 0 ]]
ip -o -4 addr show | grep -q ' 192\.168\.20\.10/'
reader=$2
id "$reader" >/dev/null
key=$(awk 'NF>=2 && $1=="ssh-ed25519" {print $1 " " $2}' "$1")
[[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+$ ]]
src=$(dirname "$(realpath "$0")")
base=/var/lib/ws-student-leases
if ! id ws-lease >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$base" --shell /bin/sh ws-lease
fi
[[ $(getent passwd ws-lease | cut -d: -f6) == "$base" ]]
install -d -o root -g root -m755 "$base" "$base/.ssh" /usr/local/lib/ws-vm-leases
install -d -o ws-lease -g ws-lease -m700 "$base/consumed"
install -d -o ws-lease -g ws-lease -m755 "$base/leases"
# Files are 0640. Grant the backend user read access without sharing SSH credentials.
setfacl -m "d:u:$reader:r--" "$base/leases"
install -m644 "$src/vm-leases.py" /usr/local/lib/ws-vm-leases/
install -m644 "$src/../dev-i5/adaptive/approve_session.py" /usr/local/lib/ws-vm-leases/
line="restrict,from=\"192.168.20.1\",command=\"/usr/bin/python3 -EB /usr/local/lib/ws-vm-leases/vm-leases.py\" $key"
auth=$base/.ssh/authorized_keys
if [[ -e $auth ]]; then printf '%s\n' "$line" | cmp -s - "$auth" || { echo "Unexpected existing SSH authorization" >&2; exit 1; }; else printf '%s\n' "$line" > "$auth"; fi
chmod 644 "$auth"
