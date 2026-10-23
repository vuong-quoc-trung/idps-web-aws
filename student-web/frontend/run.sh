#!/usr/bin/env bash
set -euo pipefail
FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$FRONTEND_DIR"
if [[ -x "$FRONTEND_DIR/../../.local-node/24/bin/node" ]]; then
  export PATH="$FRONTEND_DIR/../../.local-node/24/bin:$PATH"
fi
if ! command -v npm >/dev/null 2>&1; then
  printf 'Cần cài Node.js và npm trước khi chạy frontend.\n' >&2
  exit 1
fi
exec npm run dev -- "$@"
