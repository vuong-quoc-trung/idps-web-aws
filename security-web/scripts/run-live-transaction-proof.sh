#!/usr/bin/env bash
# Operator entry point. Builds unprivileged, then requests sudo for isolated capture.
set -euo pipefail
if [[ ${EUID} -eq 0 ]]; then
  echo 'Run as your ordinary user; only the isolated capture step requests sudo.' >&2
  exit 2
fi
WS_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
WS_MODULE=${1:-/tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so}
[[ -f "$WS_MODULE" ]] || { echo 'Extracted njs module not found; no module will be installed.' >&2; exit 2; }
WS_MODULE=$(realpath -- "$WS_MODULE")
WS_BUILD_LOG=$(mktemp)
trap 'rm -f -- "$WS_BUILD_LOG"' EXIT
cargo test --offline --manifest-path "$WS_REPO/security-web/Cargo.toml" --no-run --message-format=json > "$WS_BUILD_LOG"
WS_TEST_BIN=$(python3 - "$WS_BUILD_LOG" <<'PY'
import json, sys
from pathlib import Path
rows = [json.loads(s) for s in Path(sys.argv[1]).read_text().splitlines()]
paths = {r['executable'] for r in rows if r.get('reason') == 'compiler-artifact' and r.get('profile', {}).get('test') and r.get('executable') and r.get('target', {}).get('name') == 'pbl4-security-demo'}
assert len(paths) == 1, 'Cannot identify unique Rust test executable'
print(paths.pop())
PY
)
printf '%s\n' 'Starting isolated loopback capture; production services and firewall remain unchanged.'
if [[ ${2:-} == --extended ]]; then
  sudo python3 "$WS_REPO/security-web/scripts/test-egress-kernel-guard.py" \
    --run-isolated --live-proof-module "$WS_MODULE" --rust-test-binary "$WS_TEST_BIN"
else
  sudo unshare --net -- python3 "$WS_REPO/security-web/scripts/test-live-transaction-proof.py" \
    --isolated-root --module "$WS_MODULE" --rust-test-binary "$WS_TEST_BIN"
fi
