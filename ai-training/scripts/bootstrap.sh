#!/usr/bin/env bash
set -euo pipefail
training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$training_root/.venv/bin/python" ]]; then
  "${AI_PYTHON:-python3}" -m venv "$training_root/.venv"
fi
export PIP_REQUIRE_VIRTUALENV=true
"$training_root/.venv/bin/python" -m pip install -r "$training_root/requirements.txt"
"$training_root/.venv/bin/python" -m pip install --no-deps -e "$training_root"
"$training_root/.venv/bin/idps-ai" check-contract
