#!/usr/bin/env bash
# Explicit operator action; installs only the dedicated PBL4 boot mechanism.
set -euo pipefail

if [[ $EUID -ne 0 || $# -ne 0 ]]; then
    echo 'Usage: sudo bash scripts/install-firewall-service.sh' >&2
    exit 2
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "$script_dir/.." && pwd)"
ruleset="$script_dir/pbl4.nft"
loader="$script_dir/pbl4-load-firewall"
unit="$project_dir/deploy/systemd/pbl4-firewall.service"

for required in /usr/sbin/nft /usr/bin/python3 /usr/bin/systemctl /usr/bin/systemd-analyze; do
    [[ -x $required ]] || { echo "Required executable missing: $required" >&2; exit 1; }
done
for source_file in "$ruleset" "$loader" "$unit"; do
    [[ -f $source_file && ! -L $source_file ]] || { echo "Invalid source: $source_file" >&2; exit 1; }
done

# Complete read-only preflight before creating backups or replacing system files.
/usr/bin/python3 - "$loader" "$ruleset" <<'PY'
import os
from pathlib import Path
import runpy
import stat
import sys

module = runpy.run_path(sys.argv[1], run_name="pbl4_install_preflight")
module["validate_scope"](Path(sys.argv[2]).read_text())
targets = [Path("/etc/pbl4/pbl4.nft"), Path("/usr/local/libexec/pbl4-load-firewall"),
           Path("/etc/systemd/system/pbl4-firewall.service")]
for target in targets:
    for path in [target, *target.parents]:
        if not os.path.lexists(path):
            continue
        info = path.lstat()
        expected = stat.S_ISREG(info.st_mode) if path == target else stat.S_ISDIR(info.st_mode)
        if not expected or info.st_uid != 0 or info.st_mode & 0o022:
            raise SystemExit(f"Unsafe existing destination/parent; left unchanged: {path}")
for base in ("/etc", "/run", "/usr/lib"):
    dropins = Path(base) / "systemd/system/pbl4-firewall.service.d"
    if dropins.exists() and any(dropins.glob("*.conf")):
        raise SystemExit(f"Existing systemd overrides require manual review: {dropins}")
if module["table_exists"]():
    module["check_existing_table"]()
    print("Preflight: existing PBL4 table is compatible and will be preserved.")
else:
    print("Preflight: PBL4 table is absent; service start will create it.")
PY
/usr/sbin/nft -c -f "$ruleset"
echo 'Preflight: nft syntax check passed.'

if [[ ! -d /etc/pbl4 ]]; then
    install -d -o root -g root -m 0755 /etc/pbl4
fi
if [[ ! -d /usr/local/libexec ]]; then
    install -d -o root -g root -m 0755 /usr/local/libexec
fi
if [[ -e /etc/pbl4/backups || -L /etc/pbl4/backups ]]; then
    /usr/bin/python3 - <<'PY'
from pathlib import Path
import stat
p = Path('/etc/pbl4/backups')
s = p.lstat()
if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o077:
    raise SystemExit('Unsafe backup directory; no destination files replaced')
PY
else
    install -d -o root -g root -m 0700 /etc/pbl4/backups
fi
backup_dir="$(mktemp -d "/etc/pbl4/backups/firewall-$(date +%Y%m%d-%H%M%S).XXXXXX")"
for target in /etc/pbl4/pbl4.nft /usr/local/libexec/pbl4-load-firewall /etc/systemd/system/pbl4-firewall.service; do
    if [[ -e $target ]]; then
        cp -a -- "$target" "$backup_dir/$(basename -- "$target")"
    else
        printf '%s\n' "$target" >> "$backup_dir/previously-absent.txt"
    fi
done
systemctl is-enabled pbl4-firewall.service > "$backup_dir/previous-enable-state.txt" 2>&1 || true
echo "Backup: $backup_dir"

install -o root -g root -m 0644 "$ruleset" /etc/pbl4/pbl4.nft
install -o root -g root -m 0755 "$loader" /usr/local/libexec/pbl4-load-firewall
install -o root -g root -m 0644 "$unit" /etc/systemd/system/pbl4-firewall.service

# Check installed copies, then reload only systemd's unit metadata.
/usr/sbin/nft -c -f /etc/pbl4/pbl4.nft
systemd-analyze verify /etc/systemd/system/pbl4-firewall.service
systemctl daemon-reload
systemctl enable pbl4-firewall.service
systemctl start pbl4-firewall.service
systemctl status pbl4-firewall.service --no-pager
/usr/sbin/nft list table inet pbl4_demo
/usr/sbin/nft list set inet pbl4_demo blocked_ips

echo 'Installed. AUTO_BLOCK/ENFORCEMENT_MODE and the actuator helper were not changed.'
echo 'As the backend user, run: sudo -n /usr/local/bin/pbl4-firewall list-json'
echo 'No reboot performed. See docs/FIREWALL_BOOT.md for the reboot checklist.'
