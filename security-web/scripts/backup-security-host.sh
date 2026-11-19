#!/usr/bin/env bash
# Operator-only snapshot. No service/firewall changes. Contains private TLS keys.
set -euo pipefail
umask 077
[[ $EUID -eq 0 && $# -eq 1 ]] || {
  echo 'Usage: sudo bash backup-security-host.sh /var/backups/NEW-directory' >&2; exit 2;
}
WS_BACKUP=$1
[[ "$WS_BACKUP" == /var/backups/* && ! -e "$WS_BACKUP" && ! -L "$WS_BACKUP" ]] || exit 2
# Fixed protected parent; do not accept nested caller-controlled path components.
[[ "$(dirname -- "$WS_BACKUP")" == /var/backups ]] || exit 2
[[ ! -L /var/backups && "$(stat -c %u /var/backups)" == 0 ]] || exit 2
[[ -z "$(find /var/backups -maxdepth 0 -perm /022 -print)" ]] || exit 2
mkdir -m 700 -- "$WS_BACKUP"
trap 'echo "Snapshot incomplete; inspect $WS_BACKUP. Do not deploy." >&2' ERR
WS_PATHS=()
for WS_PATH in /etc/nginx /etc/suricata /etc/systemd/system /etc/logrotate.d/nginx \
  /usr/lib/nginx/modules /usr/lib/systemd/system/nginx.service \
  /usr/lib/systemd/system/suricata.service /usr/local/lib/websentinel \
  /etc/passwd /etc/group; do
  if [[ -e "$WS_PATH" || -L "$WS_PATH" ]]; then WS_PATHS+=("${WS_PATH#/}"); fi
done
tar --acls --xattrs --numeric-owner -C / -cpf "$WS_BACKUP/configuration.tar" "${WS_PATHS[@]}"
systemctl cat nginx suricata pbl4-ai-shadow.service > "$WS_BACKUP/units.txt"
systemctl show nginx suricata pbl4-ai-shadow.service \
  -p ActiveState -p SubState -p UnitFileState -p ExecStart -p ExecReload \
  -p User -p Group -p ControlGroup > "$WS_BACKUP/services.txt"
nginx -T > "$WS_BACKUP/nginx-T.txt" 2>&1
nft list ruleset > "$WS_BACKUP/nft.rules"
nft -j list ruleset > "$WS_BACKUP/nft.json"
for WS_TOOL in iptables-save ip6tables-save; do
  if command -v "$WS_TOOL" >/dev/null; then "$WS_TOOL" > "$WS_BACKUP/$WS_TOOL.txt"; fi
done
ip -j addr > "$WS_BACKUP/addresses.json"
ip -j route > "$WS_BACKUP/routes.json"
dpkg-query -W > "$WS_BACKUP/packages.txt"
command -v getfacl >/dev/null || { echo 'getfacl required for permission rollback' >&2; exit 1; }
: > "$WS_BACKUP/permissions.txt"
: > "$WS_BACKUP/permissions-errors.txt"
: > "$WS_BACKUP/permissions-status.txt"
# Ubuntu Host uses /var/lib/nginx for body/proxy/fastcgi/scgi/uwsgi temp paths.
# Missing or unreadable required trees must fail the entire snapshot.
for WS_PATH in /etc/nginx /var/log/nginx /var/lib/nginx; do
  [[ -d "$WS_PATH" ]] || { echo "Required ACL path missing: $WS_PATH" >&2; exit 1; }
  getfacl -R -p "$WS_PATH" >> "$WS_BACKUP/permissions.txt" 2>> "$WS_BACKUP/permissions-errors.txt"
  printf 'PASS required %s\n' "$WS_PATH" >> "$WS_BACKUP/permissions-status.txt"
done
# This Host does not use /var/cache/nginx by default; do not silently skip it
# if the effective configuration references it.
if [[ -e /var/cache/nginx ]]; then
  getfacl -R -p /var/cache/nginx >> "$WS_BACKUP/permissions.txt" 2>> "$WS_BACKUP/permissions-errors.txt"
  printf 'PASS cache /var/cache/nginx\n' >> "$WS_BACKUP/permissions-status.txt"
elif grep -q '/var/cache/nginx' "$WS_BACKUP/nginx-T.txt"; then
  echo 'Configured /var/cache/nginx missing; backup incomplete' >&2; exit 1
else
  printf 'SKIPPED /var/cache/nginx: absent and not referenced; Host uses /var/lib/nginx\n' >> "$WS_BACKUP/permissions-status.txt"
fi
for WS_PATH in /run/pbl4-ai-shadow /run/pbl4-ai-shadow/nginx.sock; do
  if [[ -e "$WS_PATH" || -L "$WS_PATH" ]]; then
    getfacl -p "$WS_PATH" >> "$WS_BACKUP/permissions.txt" 2>> "$WS_BACKUP/permissions-errors.txt"
    printf 'PASS AI-DEFERRED existing %s\n' "$WS_PATH" >> "$WS_BACKUP/permissions-status.txt"
  else
    printf 'SKIPPED AI-DEFERRED absent %s\n' "$WS_PATH" >> "$WS_BACKUP/permissions-status.txt"
  fi
done
# Hash every produced artifact, including ACLs, inventories and optional outputs.
(cd "$WS_BACKUP"; find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name COMPLETE -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
(cd "$WS_BACKUP"; sha256sum -c SHA256SUMS)
tar -tf "$WS_BACKUP/configuration.tar" >/dev/null
printf '%s\n' 'COMPLETE snapshot; NOT deployment approval. Contains secrets: keep root-only, never Git/chat.' > "$WS_BACKUP/COMPLETE"
printf 'Snapshot complete: %s\n' "$WS_BACKUP"
