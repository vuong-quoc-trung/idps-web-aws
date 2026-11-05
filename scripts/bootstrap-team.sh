#!/usr/bin/env bash
set -euo pipefail
team_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${TEAM_SETUP_PYTHON:-python3}" "$team_root/scripts/bootstrap-team.py" "$@"
