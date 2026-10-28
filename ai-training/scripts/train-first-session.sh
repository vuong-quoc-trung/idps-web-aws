#!/usr/bin/env bash
# Explicitly invoked by the operator. This script does not run during preparation.
set -euo pipefail
training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
artifact_root="$training_root/.artifacts/upgrade_20261028"
run_directory="$artifact_root/formal/residual-seed17"
arguments=(
  --dataset "$artifact_root/dataset-ready/prepared"
  --readiness-report "$artifact_root/dataset-ready/readiness-resource8/readiness.json"
  --config "$training_root/configs/formal_residual_config.yaml"
  --run-dir "$run_directory"
  --epochs 100
  --max-duration-minutes 150
  --cpus 8
  --memory-limit-gib 16
  --checkpoint-every-seconds 300
)
if [[ -f "$run_directory/latest.json" ]]; then
  arguments+=(--resume-from "$run_directory")
fi
exec "$training_root/.venv/bin/python" -m idps_ai.training.session "${arguments[@]}"
