#!/bin/bash
# Publish content-addressed assets first; open tabs may still use older assets.
set -euo pipefail
src=$(realpath "$(dirname "$0")/../../frontend")
if (( EUID )); then
    (cd "$src" && npm run build)
    exec sudo bash "$0"
fi
live=/opt/ws-native/runtime-fix/frontend/dist
exec 9>/run/lock/ws-native-dashboard-repair
flock -n 9
test -f "$live/index.html"
backup=$(mktemp -d /var/backups/ws-dashboard-ui.XXXXXXXX)
cp -p "$live/index.html" "$backup/"
echo "Previous index: $backup/index.html"
for asset in "$src"/dist/assets/*; do
    dest="$live/assets/${asset##*/}"
    if [[ -e $dest ]]; then cmp "$asset" "$dest"; continue; fi
    install -m0644 "$asset" "$dest.new"
    mv -T "$dest.new" "$dest"
done
install -m0644 "$src/dist/index.html" "$live/index.html.new"
mv -T "$live/index.html.new" "$live/index.html"
if ! curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:23000/ | cmp - "$live/index.html"; then
    install -m0644 "$backup/index.html" "$live/index.html.new"
    mv -T "$live/index.html.new" "$live/index.html"
    echo 'Served index mismatch: previous Dashboard restored' >&2
    exit 1
fi
echo 'PASS: native HTTP serves new Dashboard index'
