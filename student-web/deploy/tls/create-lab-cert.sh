#!/usr/bin/env bash
# Creates NEW private output directory, never installs into /etc. No sudo needed.
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: bash create-lab-cert.sh NEW_PRIVATE_DIRECTORY' >&2; exit 2; }
WS_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
WS_DEST=$(realpath -m -- "$1")
case "$WS_DEST/" in "$WS_REPO/"*) echo 'Secrets must be generated outside the repository' >&2; exit 2;; esac
umask 077
mkdir -m 700 -- "$1"
WS_TLS=$(cd -- "$1" && pwd)
openssl req -x509 -newkey rsa:3072 -noenc -sha256 -days 365 \
  -subj '/CN=WebSentinel Student Lab CA' \
  -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -keyout "$WS_TLS/ca.key" -out "$WS_TLS/ca.crt"
openssl req -new -newkey rsa:3072 -noenc -sha256 \
  -subj '/CN=student.lab' -keyout "$WS_TLS/student.key" -out "$WS_TLS/student.csr"
cat > "$WS_TLS/extensions.cnf" <<'EXT'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:192.168.20.10,DNS:student.lab
EXT
openssl x509 -req -in "$WS_TLS/student.csr" -CA "$WS_TLS/ca.crt" \
  -CAkey "$WS_TLS/ca.key" -CAcreateserial -days 90 -sha256 \
  -extfile "$WS_TLS/extensions.cnf" -out "$WS_TLS/student.crt"
openssl verify -CAfile "$WS_TLS/ca.crt" -verify_ip 192.168.20.10 "$WS_TLS/student.crt"
openssl verify -CAfile "$WS_TLS/ca.crt" -verify_hostname student.lab "$WS_TLS/student.crt"
echo 'Created lab CA and leaf. Keep ca.key offline; transfer only ca.crt to Defender.'
