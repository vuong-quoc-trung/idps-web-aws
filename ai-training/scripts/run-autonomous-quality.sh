#!/usr/bin/env bash
set -euo pipefail

training_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
quality_root="$training_root/.artifacts/automated_quality_$(date +%Y%m%d)"
mkdir -p -m 700 "$quality_root"
report_path="${1:-$quality_root/report-$(date +%H%M%S).json}"

exec systemd-run --user --scope \
  -p CPUQuota=400% -p AllowedCPUs=0-7 \
  -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 \
  env PYTHONPATH="$training_root/src" PYTHONDONTWRITEBYTECODE=1 \
  OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  "$training_root/.venv/bin/python" "$training_root/scripts/assess-autonomous-quality.py" \
  --policy "$training_root/configs/autonomous_research_policy_v2.yaml" \
  --catalog "$training_root/configs/public_http_sources.yaml" \
  --audit "$training_root/.artifacts/autonomous_research_20261103/wamm/audit-v4.json" \
  --overlap "$training_root/.artifacts/autonomous_research_20261103/wamm/overlap-v2.json" \
  --staging "$training_root/.artifacts/autonomous_research_20261103/wamm/research-nonoverlap-v2.parquet" \
  --reference "$training_root/.artifacts/partition_recovery_20261031/forward-development-v2/features.parquet" \
  --oracle "$training_root/.artifacts/devgt1/run/oracle-verification/report.json" \
  --bundle "$training_root/.artifacts/scale_upgrade_20261030/pilot/residual_glu-bundle" \
  --bundle-sha 1748b7e0f356ff5a085e7bb59a9030d3173c2617b74784479bc2069adf6fe858 \
  --research-report "$training_root/.artifacts/research_glu207_stability_20261103/report.json" \
  --research-sha e8d811cc4450b909771335f247e9cf1bb3fe84c098f328afea9330d13ab22639 \
  --live "$training_root/.artifacts/live_shadow_20261103_resource/live-report.json" \
  --live-sha 12db7446e1a892569718b8b5b5c3a7d1dd6fc72b68ce742e283ca02cf79f713b \
  --handoff "$training_root/FINAL_TRAINING_HANDOFF.json" \
  --output "$report_path"
