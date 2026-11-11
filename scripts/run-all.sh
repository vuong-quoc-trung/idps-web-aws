#!/usr/bin/env bash
# Start the existing complete demo; reuse a live session, detect current LAN IP.
set -euo pipefail
IDPS_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if (( $# )); then
  exec "$IDPS_REPO_ROOT/scripts/idps-demo.sh" start "$@"
fi
exec "$IDPS_REPO_ROOT/scripts/idps-demo.sh" start --listen 0.0.0.0 --allow-cidr 0.0.0.0/0
