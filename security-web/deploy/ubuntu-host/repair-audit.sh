#!/bin/bash
set -euo pipefail
if (( EUID )); then exec sudo bash "$(realpath "$0")"; fi
unit=pbl4-audit-receiver.service
ready() {
    ss -Hltnp 'sport = :2514' | awk -v pid="$(systemctl show "$unit" -p MainPID --value)" '$4=="192.168.20.1:2514" && index($0,"pid="pid","){ok=1} END{exit !ok}'
}
ip -o -4 addr show dev vmnet3 | grep -Eq ' inet 192[.]168[.]20[.]1/'
nft list table inet pbl4_audit_transport >/dev/null
/usr/local/libexec/pbl4-audit-guard >/dev/null
# vmnet3 may acquire its address after network-online.target at boot.
dir=/etc/systemd/system/$unit.d
install -d -m0755 "$dir"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
cat >"$tmp" <<'UNIT'
[Service]
ExecStartPre=/bin/sh -ec 'until /usr/sbin/ip -o -4 addr show dev vmnet3 2>/dev/null | /usr/bin/grep -Eq " inet 192[.]168[.]20[.]1/"; do sleep 2; done'
ExecStartPost=/bin/sh -ec 'for i in 1 2 3 4 5; do /usr/bin/ss -Hltnp "sport = :2514" | /usr/bin/grep -F "192.168.20.1:2514" | /usr/bin/grep -Fq "pid=$MAINPID," && exit 0; sleep 1; done; exit 1'
UNIT
if ! cmp -s "$tmp" "$dir/71-require-relp-listener.conf"; then
    install -m0644 "$tmp" "$dir/71-require-relp-listener.conf"
    systemctl daemon-reload
fi
if ! ready; then systemctl restart "$unit"; fi
ready
echo 'PASS: receiver owns 192.168.20.1:2514. Checking one real VM request.'
rid=$(openssl rand -hex 16)
ca=${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)}
code=$(curl --noproxy '*' --resolve student.lab:443:192.168.20.10 --cacert "${WS_STUDENT_CA:-$ca/ws-student-trust/ca.crt}" --max-time 8 -H "X-Request-Id: $rid" -sS -o /dev/null -w '%{http_code}' https://student.lab/api/auth/me)
test "$code" = 401
for ((i=0;i<30;i++)); do
    found=$(docker exec -e PGOPTIONS=-cdefault_transaction_read_only=on pbl4-postgres psql -XAt -v ON_ERROR_STOP=1 -U pbl4 -d ws_native_security -c "select exists(select from normalized_events where source='STUDENT_AUDIT' and request_id='$rid' and status_code=401)")
    if [[ $found == t ]]; then echo "PASS VM → RELP → Rust → PostgreSQL request_id=$rid"; exit 0; fi
    sleep 1
done
if grep -Fq "$rid" /var/log/pbl4/student-audit.log; then echo "BLOCKED: receiver received $rid; inspect Rust ingestion"; else echo "BLOCKED: $rid absent at receiver; check VM exporter, request ID propagation and RELP sender queue"; fi
exit 1
