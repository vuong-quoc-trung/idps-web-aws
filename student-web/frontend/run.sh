#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$FRONTEND_DIR"

LOCAL_NODE="$FRONTEND_DIR/../../.local-node/24/bin"
if [[ -x "$LOCAL_NODE/node" ]]; then
  export PATH="$LOCAL_NODE:$PATH"
fi

if ! command -v npm >/dev/null 2>&1; then
  printf 'Không tìm thấy npm. Cài Node.js hoặc đặt Node.js local tại .local-node/24.\n' >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  npm ci
fi

exec npm run dev -- "$@"
