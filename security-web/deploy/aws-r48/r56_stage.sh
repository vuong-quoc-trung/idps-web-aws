#!/usr/bin/env bash
# Run a SHA-pinned R56 bundle on the existing AWS staging host.
set -euo pipefail
umask 077

if [[ $# -ne 3 || ! $3 =~ ^[0-9a-f]{64}$ ]]; then
  printf 'Usage: %s lab|deploy /absolute/path/bundle.tgz sha256\n' "$0" >&2
  exit 2
fi
mode=$1
bundle=$2
digest=$3
[[ "$bundle" == /* && -f "$bundle" && ! -L "$bundle" ]]
printf '%s  %s\n' "$digest" "$bundle" | sha256sum --check --quiet
kit=/opt/websentinel-r48/runtime
baseline=/opt/websentinel-r47/current/security/pbl4-security-demo
cd "$kit"
python3 -B -c 'import refresh; refresh.verify_host(); refresh.verify_database()'
stage=$(mktemp -d /var/tmp/websentinel-r56-stage.XXXXXXXX)
pg=$(mktemp -d /var/tmp/websentinel-r56-pg.XXXXXXXX)
trap 'python3 -c "from pathlib import Path; import shutil,sys; [shutil.rmtree(Path(p)) for p in sys.argv[1:]]" "$stage" "$pg"' EXIT
tar -xzf "$bundle" --no-same-owner --no-same-permissions -C "$stage"

case "$mode" in
  lab)
    chown postgres:postgres "$pg"
    chmod 755 "$stage"
    [[ $(sha256sum "$baseline" | cut -d ' ' -f1) == 96681283805c457ec7ab02278deefc419897d871659c2cceb405536373b8f960 ]]
    zstd -qd --patch-from="$baseline" "$stage/lab.zst" -o "$stage/lab-bin"
    printf '%s  %s\n' "$(cat "$stage/lab.sha256")" "$stage/lab-bin" | sha256sum --check --quiet
    chmod 755 "$stage/lab-bin"
    test ! -e /run/websentinel-r56-lab
    host=$(stat -Lc %i /proc/self/ns/net)
    systemd-run --collect --unit=websentinel-r56-prevention --wait --pipe \
      -p PrivateNetwork=yes -p RuntimeDirectory=websentinel-r56-lab -p RuntimeDirectoryMode=0755 \
      -p RuntimeMaxSec=115 -p CPUQuota=100% -p MemoryMax=512M -p MemorySwapMax=0 -p TasksMax=80 \
      --setenv=PYTHONPATH="$kit" /usr/bin/python3 -B "$stage/r56_prevention_lab.py" "$stage" "$pg" "$host"
    test ! -e /run/websentinel-r56-lab
    ;;
  deploy)
    systemd-run --collect --unit=websentinel-r56-deploy --wait --pipe \
      -p RuntimeMaxSec=165 -p CPUQuota=75% -p MemoryMax=512M -p MemorySwapMax=0 -p TasksMax=32 \
      --setenv=PYTHONPATH="$kit" /usr/bin/python3 -B "$stage/r56.py" install
    install -m 0644 "$stage/r56.py" "$kit/r56.py"
    ;;
  *)
    exit 2
    ;;
esac
