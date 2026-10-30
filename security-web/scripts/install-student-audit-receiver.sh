#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/install-student-audit.py" receiver "$@"
