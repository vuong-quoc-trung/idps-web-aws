#!/usr/bin/env bash
# Read-only bounded requests. Explicit operator run; never disables TLS verification.
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: bash verify-from-defender.sh TRUSTED_CA_CERT' >&2; exit 2; }
WS_CA=$1
for WS_URL in https://192.168.20.10/ https://192.168.20.10/api/auth/me; do
  curl --noproxy '*' --connect-timeout 5 --max-time 15 --cacert "$WS_CA" \
    -o /dev/null -w 'TLS verified; HTTP=%{http_code}\n' "$WS_URL"
done
curl --noproxy '*' --connect-timeout 5 --max-time 15 --cacert "$WS_CA" \
  --resolve student.lab:443:192.168.20.10 -o /dev/null \
  -w 'DNS SAN verified; HTTP=%{http_code}\n' https://student.lab/api/auth/me
set +e
curl --noproxy '*' --connect-timeout 5 --max-time 15 --cacert "$WS_CA" \
  --resolve wrong-student.invalid:443:192.168.20.10 -o /dev/null -sS https://wrong-student.invalid/
WS_RESULT=$?
set -e
[[ "$WS_RESULT" -eq 60 ]] || { echo "FAIL: expected certificate rejection (60), got $WS_RESULT" >&2; exit 1; }
echo 'PASS: mismatched hostname rejected. Review HTTP statuses and Application Audit separately.'
WS_TMP=$(mktemp -d)
trap 'rm -rf -- "$WS_TMP"' EXIT
chmod 700 "$WS_TMP"
(umask 077; openssl req -x509 -newkey rsa:2048 -noenc -days 1 \
  -subj '/CN=Unrelated Test CA' -keyout "$WS_TMP/key" -out "$WS_TMP/ca.crt" >/dev/null 2>&1)
set +e
curl --noproxy '*' --connect-timeout 5 --max-time 15 --cacert "$WS_TMP/ca.crt" \
  -o /dev/null -sS https://192.168.20.10/
WS_RESULT=$?
set -e
[[ "$WS_RESULT" -eq 60 ]] || { echo "FAIL: wrong CA expected rejection (60), got $WS_RESULT" >&2; exit 1; }
echo 'PASS: unrelated CA rejected.'
