#!/usr/bin/env bash
set -euo pipefail
training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$training_root"
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q src
.venv/bin/idps-ai check-contract
git -C "$training_root/.." diff --exit-code fbe078d -- student-web security-web
