#!/usr/bin/env bash
# Reuse the current staging host and an isolated C2 binary for the ingress test.
set -euo pipefail
umask 077
export SYSTEMD_PAGER=cat

if [[ $# -lt 2 || $# -gt 3 || $1 != /* || ! -f $1 || -L $1 || ! $2 =~ ^[a-f0-9]{64}$ || ${3:-r60} != r60 && ${3:-r60} != r61 ]]; then
  printf 'Usage: %s /absolute/path/bundle.tgz sha256 [r60|r61]\n' "$0" >&2
  exit 2
fi
printf '%s  %s\n' "$2" "$1" | sha256sum --check --quiet
kit=/opt/websentinel-r48/runtime
baseline=/opt/websentinel-r47/current/security/pbl4-security-demo
cd "$kit"
python3 -B -c 'import refresh; refresh.verify_host(); refresh.verify_database()'
stage=$(mktemp -d /var/tmp/websentinel-r60-stage.XXXXXXXX)
pg=$(mktemp -d /var/tmp/websentinel-r60-pg.XXXXXXXX)
trap 'rm -rf -- "$stage" "$pg"' EXIT
chown postgres:postgres "$pg"
chmod 755 "$stage"
files=(baseline.sha256 lab.sha256 lab.zst r53_runtime_lab.py r56_prevention_lab.py r60_ingress.py)
runner=r60_ingress.py
if [[ ${3:-r60} == r61 ]]; then
  runner=r61_canary.py
  files+=("$runner")
fi
tar -xzf "$1" --no-same-owner --no-same-permissions -C "$stage" "${files[@]}"
printf '%s  %s\n' "$(cat "$stage/baseline.sha256")" "$baseline" | sha256sum --check --quiet
zstd -qd --patch-from="$baseline" "$stage/lab.zst" -o "$stage/lab-bin"
printf '%s  %s\n' "$(cat "$stage/lab.sha256")" "$stage/lab-bin" | sha256sum --check --quiet
chmod 755 "$stage/lab-bin"
test ! -e /run/websentinel-r56-lab
host=$(stat -Lc %i /proc/self/ns/net)
printf 'R60_LAB_SHA=%s\n' "$(cat "$stage/lab.sha256")"
systemd-run --collect --unit=websentinel-r56-prevention --wait --pipe \
  -p PrivateNetwork=yes -p RuntimeDirectory=websentinel-r56-lab -p RuntimeDirectoryMode=0755 \
  -p RuntimeMaxSec=110 -p CPUQuota=100% -p MemoryMax=512M -p MemorySwapMax=0 -p TasksMax=80 \
  --setenv=PYTHONPATH="$kit" /usr/bin/python3 -B "$stage/$runner" "$stage" "$pg" "$host"
test ! -e /run/websentinel-r56-lab
test ! -e /sys/fs/cgroup/system.slice/websentinel-r56-prevention.service
python3 -B -c 'import refresh; refresh.verify_host(); refresh.verify_database()'
printf 'R60_HOST_READBACK_AND_CLEANUP=PASS\n'
