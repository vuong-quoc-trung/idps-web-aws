#!/usr/bin/env bash
set -euo pipefail
training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$training_root"
.venv/bin/ruff check src tests scripts/*.py
.venv/bin/ruff format --check src tests scripts/*.py
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q src
.venv/bin/idps-ai check-contract
# Check this session's edits. The historical foundation ref predates accepted
# frontend commits and incorrectly rejects them on the current training branch.
git -C "$training_root/.." diff --exit-code HEAD -- student-web security-web contracts docker
