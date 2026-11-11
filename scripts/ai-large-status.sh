#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/ai-training/.venv/bin/python" "$ROOT/ai-training/scripts/large-request-workflow.py" status --run "${1:-$ROOT/.local-dev/large-request-2m-20261110-r1}"
