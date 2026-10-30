#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/verify-student-audit-forwarding.py" "$@"
