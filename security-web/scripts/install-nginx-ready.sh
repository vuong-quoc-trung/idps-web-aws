#!/bin/bash
# Run from the repository using sudo bash scripts/install-nginx-ready.sh.
set -euo pipefail
if (( EUID != 0 )); then
    echo 'Run this installer with sudo bash.' >&2
    exit 1
fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
script_source="$repo_dir/scripts/pbl4-wait-nginx"
unit_source="$repo_dir/deploy/systemd/pbl4-nginx-ready.service"
bash -n "$script_source"
for tool in /usr/sbin/ip /usr/sbin/nginx /usr/bin/systemctl /usr/bin/timeout /usr/bin/awk; do
    test -x "$tool" || { echo "Missing required executable: $tool" >&2; exit 1; }
done
backup_dir=$(mktemp -d /var/backups/pbl4-nginx-ready.XXXXXXXX)
for dest in /usr/local/libexec/pbl4-wait-nginx /etc/systemd/system/pbl4-nginx-ready.service; do
    if [[ -e "$dest" || -L "$dest" ]]; then
        cp -a --parents -- "$dest" "$backup_dir/"
    fi
done
systemctl is-enabled pbl4-nginx-ready.service > "$backup_dir/previous-enabled-state.txt" 2>&1 || true
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$script_source" /usr/local/libexec/pbl4-wait-nginx
install -o root -g root -m 0644 "$unit_source" /etc/systemd/system/pbl4-nginx-ready.service
systemd-analyze verify /etc/systemd/system/pbl4-nginx-ready.service
systemctl daemon-reload
systemctl enable pbl4-nginx-ready.service
# Restart only this oneshot to validate a reinstallation; active Nginx is untouched.
systemctl restart pbl4-nginx-ready.service
printf 'Installed. Backup directory: %s\n' "$backup_dir"
systemctl status pbl4-nginx-ready.service --no-pager -l
