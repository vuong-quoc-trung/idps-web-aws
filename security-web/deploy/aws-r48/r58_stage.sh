#!/usr/bin/env bash
# Stage one checked R58 release on the existing EC2 instance.
set -euo pipefail
umask 077

if [[ $# -ne 2 || ! $2 =~ ^[0-9a-f]{64}$ || $1 != /* || ! -f $1 || -L $1 ]]; then
    printf 'Usage: %s /absolute/path/bundle.tgz sha256\n' "$0" >&2
    exit 2
fi
bundle=$1
digest=$2
printf '%s  %s\n' "$digest" "$bundle" | sha256sum --check --quiet
kit=/opt/websentinel-r48/runtime
cd "$kit"
python3 -B -c 'import refresh; refresh.verify_host(); refresh.verify_database()'
stage=$(mktemp -d /var/tmp/websentinel-r58-stage.XXXXXXXX)
trap 'python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1])" "$stage"' EXIT
tar -xzf "$bundle" --no-same-owner --no-same-permissions -C "$stage"
systemd-run --collect --unit=websentinel-r58-deploy --wait --pipe \
    -p RuntimeMaxSec=270 -p CPUQuota=100% -p MemoryMax=768M -p MemorySwapMax=0 -p TasksMax=48 \
    --setenv=PYTHONPATH="$kit" /usr/bin/python3 -B "$stage/r58.py" install
install -m 0644 "$stage/r58.py" "$kit/r58.py"
