#!/bin/bash
# Explicit native first install only. Does not start a service or apply nft rules.
set -euo pipefail
umask 077
test "$(id -u)" = 0
test "$(systemd-detect-virt || true)" = none
helper=$(dirname "$(realpath "$0")")
cd /  # all inputs below are absolute
bundle=$(realpath "${1:?absolute root-owned bundle path}")
expected=${2:?approved manifest SHA-256}
test "$(stat -c %u "$bundle")" = 0
test -z "$(find "$bundle" \( -type l -o ! -user root -o -perm /022 \) -print -quit)"
cd "$bundle"
printf '%s  SHA256SUMS\n' "$expected" | sha256sum --quiet -c -
sha256sum --quiet -c SHA256SUMS
resume=false
if [[ $bundle == /opt/ws-native/current ]]; then
  resume=true
  test "$(realpath /opt/ws-native)" = /opt/ws-native
  test -z "$(find "$bundle" ! -type f ! -type d -print -quit)"
  diff <(find . -type f ! -path ./SHA256SUMS -printf '%P\n' | LC_ALL=C sort) <(cut -c67- SHA256SUMS | LC_ALL=C sort)
  python3 -B "$helper/preflight.py" --resume-copied-bundle "$bundle"
else
  python3 -B "$helper/preflight.py" "$bundle"
fi
pgport=$(python3 -B ./docker_pg.py)
for name in ws-native-{edge,scorer,security,sensor,student,actuator,gate}; do
  if getent passwd "$name" >/dev/null || getent group "$name" >/dev/null; then exit 1; fi
done
! getent group ws-native-evidence >/dev/null || exit 1
for f in /etc/tmpfiles.d/ws-native.conf /etc/sysusers.d/ws-native.conf; do test ! -e "$f"; done
# On partial provisioning retain new files/users for inspection, never reuse/overwrite a journal.
for d in /etc/sysusers.d /etc/tmpfiles.d; do
  if [[ ! -e $d ]]; then install -d -m 0755 "$d"; fi
  test -d "$d" && test ! -L "$d" || exit 1
done
install -d -m 0755 /opt/ws-native /opt/ws-native/current /etc/ws-native /var/lib/ws-native
if ! "$resume"; then cp -a "$bundle/." /opt/ws-native/current/; fi
chmod -R a+rX,go-w /opt/ws-native/current
for name in ws-native-{edge,scorer,security,sensor,student,actuator,gate}; do
  echo "u $name - \"WebSentinel native\" /nonexistent /usr/sbin/nologin"
done > /etc/sysusers.d/ws-native.conf
echo 'g ws-native-evidence -' >> /etc/sysusers.d/ws-native.conf
systemd-sysusers /etc/sysusers.d/ws-native.conf
for name in edge student sensor scorer; do
  install -d -o ws-native-"$name" -g ws-native-evidence -m 2750 /var/lib/ws-native/"$name"
done
install -d -o ws-native-actuator -m 0700 /var/lib/ws-native/approval
echo 'd /run/ws-native-leases 0750 ws-native-actuator ws-native-evidence -' > /etc/tmpfiles.d/ws-native.conf
systemd-tmpfiles --create /etc/tmpfiles.d/ws-native.conf
runuser -u ws-native-actuator -g ws-native-evidence -- python3 -B /opt/ws-native/current/worker.py init
cd /etc/ws-native
printf 'WS_NATIVE_LEASE_OWNER_UID=%s\n' "$(id -u ws-native-actuator)" > gate.env
sed "s/__NATIVE_EDGE_GID__/$(id -g ws-native-edge)/" "$bundle/native-nginx.template" >nginx.conf
cp "$bundle/native-suricata.yaml" suricata.yaml
: > approved-location.inc
openssl rand -hex 32 > session.key
for pair in 'edge IP:127.0.0.1' 'origin DNS:student.internal'; do
  read -r name san <<< "$pair"
  openssl req -x509 -nodes -newkey rsa:3072 -days 90 -subj "/CN=ws-native-$name" \
    -addext "subjectAltName=$san" -keyout "$name.key" -out "$name.crt" 2>/dev/null
done
chmod 0644 *.crt suricata.yaml
lineage=ws-native-$(openssl rand -hex 8)
printf 'MODEL_SLOT=candidate\nEVIDENCE_LINEAGE=%s\nRELEASE_SHA256=%s\n' "$lineage" \
  "$(sha256sum "$bundle/scorer/files.json" |cut -d' ' -f1)" > scorer.env
cat >security.env <<ENV
DATABASE_URL=postgresql://ws_native_security@127.0.0.1:$pgport/ws_native_security
APP_ADDR=127.0.0.1:23000
ENFORCEMENT_MODE=OFF
AUTO_BLOCK=false
PBL4_FIREWALL_CMD=/bin/false
COLLECT_ALL_EVENTS=true
NGINX_ACCESS_PATH=/var/lib/ws-native/edge/access.jsonl
SURICATA_EVE_PATH=/var/lib/ws-native/sensor/eve.json
SURICATA_LUA_PATH=/var/lib/ws-native/sensor/chain.tsv
STUDENT_AUDIT_LOG_PATH=/var/log/pbl4/student-audit.log
AI_HTTPS_RESULTS_PATH=/var/lib/ws-native/scorer/observations.jsonl
SURICATA_CAPTURE_MODE=post-proxy
SURICATA_POST_PROXY_INTERFACE=lo
SURICATA_EVE_GENERATION_HOST=true
SURICATA_TRUSTED_EDGE_CONFIRMED=false
SURICATA_PROXY_IP=127.78.0.1
SURICATA_WEB_IP=127.78.0.2
SURICATA_WEB_PORT=28080
WS_DEV_HYBRID_MODE=REVIEW
WS_DEV_HYBRID_POLICY='{"rules":[],"combined":200,"standalone":100,"fresh_seconds":60,"r37_weight":0}'
ENV
cat >student.env <<ENV
DB_URL=jdbc:postgresql://127.0.0.1:$pgport/ws_native_student
DB_USERNAME=ws_native_student
SERVER_ADDRESS=127.0.0.1
SERVER_PORT=28081
SESSION_COOKIE_SECURE=true
PUBLIC_APP_URL=https://127.0.0.1:24443
BOOTSTRAP_ADMIN_ENABLED=false
SPRING_PROFILES_INCLUDE=ws-i5-development
APP_DEV_SESSIONLEASEDIR=/run/ws-native-leases
APP_DEV_ACCOUNTLOCKS=false
APP_NATIVE_SESSIONKEY=$(cat session.key)
STUDENT_AUDIT_LOG_PATH=/var/lib/ws-native/student/audit.jsonl
STUDENT_AUDIT_LOG_GROUP_READABLE=true
STUDENT_AUDIT_HMAC_KEY=$(openssl rand -hex 32)
STUDENT_SOURCE_INSTANCE=$lineage
ENV
# Services cannot be started inadvertently before DB credentials and schema acceptance.
for u in "$bundle"/units/*; do
  install -m 0644 "$u" "/etc/systemd/system/$(basename "$u")"
done
systemctl daemon-reload
echo "STAGED, services stopped. Provision dedicated DB credentials, sign off restore, then review start."
