#!/usr/bin/env bash
# Starts one explicit experiment only. Preparation/pilot never invokes this script.
set -euo pipefail
training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
artifact_root="$training_root/.artifacts/upgrade_20261030_deep"
candidate="${1:-gated_residual}"
case "$candidate" in
  gated_residual) configuration="gated_residual_config.yaml" ;;
  deep_mlp) configuration="deep_mlp_config.yaml" ;;
  denoising_autoencoder) configuration="denoising_config.yaml" ;;
  residual) configuration="formal_residual_config.yaml" ;;
  *) echo 'Choose gated_residual, deep_mlp, denoising_autoencoder, or residual.' >&2; exit 2 ;;
esac
run_directory="$artifact_root/formal/$candidate-seed17"
arguments=(
  --dataset "$artifact_root/dataset-ready/prepared"
  --readiness-report "$artifact_root/dataset-ready/readiness/readiness.json"
  --config "$training_root/configs/$configuration"
  --run-dir "$run_directory"
  --epochs 150
  --max-duration-minutes 150
  --cpus 8
  --memory-limit-gib 16
  --checkpoint-every-seconds 300
)
if [[ -f "$run_directory/latest.json" ]]; then
  arguments+=(--resume-from "$run_directory")
fi
exec systemd-inhibit --no-ask-password --what=sleep:idle --mode=block \
  --who=IDPS-AI-Training --why='Bounded expanded AI experiment with checkpoints' \
  "$training_root/.venv/bin/python" -m idps_ai.training.session "${arguments[@]}"
