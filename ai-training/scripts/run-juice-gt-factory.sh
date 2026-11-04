#!/usr/bin/env bash
# One bounded, loopback-only lab run. The output directory must be new.
set -euo pipefail

training_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
artifact_root="$(realpath -m "${1:?usage: run-juice-gt-factory.sh NEW_OUTPUT_DIRECTORY}")"
container_name='ai-idps-juice-factory-20261104'
network_name='ai-idps-gt-factory-20261104'
image_ref='docker.io/bkimminich/juice-shop@sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f'

if [[ -e "$artifact_root" || -L "$artifact_root" ]]; then
  echo 'Output exists; refusing to overwrite evidence' >&2
  exit 2
fi
if podman ps -a --format '{{.Names}}' | rg -q "^${container_name}$"; then
  echo 'Factory container name already exists' >&2
  exit 2
fi
if podman network ls --format '{{.Name}}' | rg -q "^${network_name}$"; then
  echo 'Factory network name already exists' >&2
  exit 2
fi
if [[ -n "$(ss -ltn '( sport = :13081 or sport = :13082 )' | tail -n +2)" ]]; then
  echo 'Factory loopback ports are busy' >&2
  exit 2
fi

cleanup() {
  podman rm -f "$container_name" >/dev/null 2>&1 || true
  podman network rm "$network_name" >/dev/null 2>&1 || true
  if podman ps -a --format '{{.Names}}' | rg -q "^${container_name}$" ||
     podman network ls --format '{{.Name}}' | rg -q "^${network_name}$" ||
     [[ -n "$(ss -ltn '( sport = :13081 or sport = :13082 )' | tail -n +2)" ]]; then
    echo 'Factory cleanup incomplete; inspect only the named lab resources' >&2
    return 1
  fi
}
trap cleanup EXIT

umask 077
mkdir -p "$artifact_root"
podman image exists "$image_ref" || podman pull "$image_ref" >/dev/null
podman network create --internal "$network_name" >/dev/null
podman run -d --name "$container_name" --network "$network_name" \
  -p 127.0.0.1:13081:3000 --cpus=2 --memory=3g --pids-limit=256 \
  --security-opt no-new-privileges "$image_ref" >/dev/null

ready=0
for _ in {1..40}; do
  if curl --fail --silent --show-error --max-time 2 \
    http://127.0.0.1:13081/api/Challenges/ -o /dev/null 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo 'Juice Shop did not become ready' >&2
  exit 3
fi

cd "$training_root"
python_bin="$training_root/.venv/bin/python"
scope=(systemd-run --user --scope -p CPUQuota=400% -p AllowedCPUs=0-7
  -p MemoryMax=8G -p MemoryHigh=7G -p MemorySwapMax=0)
"${scope[@]}" "$python_bin" scripts/juice-gt-factory.py prepare \
  --plan "$artifact_root/plan.json"
curl --fail --silent --show-error --max-time 5 \
  http://127.0.0.1:13081/api/Challenges/ -o "$artifact_root/challenge-before.json"
curl --fail --silent --show-error --max-time 5 \
  http://127.0.0.1:13081/api/Products/ -o "$artifact_root/catalog-before.json"
"$python_bin" - "$artifact_root" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]); plan = json.loads((root / 'plan.json').read_text())
for path, expected in [('challenge-before.json', plan['initial_challenge']['response_sha256']), ('catalog-before.json', plan['catalog_response_sha256'])]:
    if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Pre-capture Oracle snapshot changed: {path}')
PY
"${scope[@]}" "$python_bin" scripts/juice-gt-factory.py run \
  --plan "$artifact_root/plan.json" --output "$artifact_root/run"
curl --fail --silent --show-error --max-time 5 \
  http://127.0.0.1:13081/api/Challenges/ -o "$artifact_root/challenge-after.json"
"$python_bin" - "$artifact_root" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]); report = json.loads((root / 'run/report.json').read_text())
if hashlib.sha256((root / 'challenge-after.json').read_bytes()).hexdigest() != report['after_challenge']['response_sha256']:
    raise SystemExit('Post-capture Oracle snapshot changed')
PY
"${scope[@]}" "$python_bin" scripts/curate-juice-gt-factory.py \
  --plan "$artifact_root/plan.json" --run-report "$artifact_root/run/report.json" \
  --factory-script scripts/juice-gt-factory.py --encoder rich_v2 \
  --output "$artifact_root/curated-v2"
"${scope[@]}" "$python_bin" scripts/assess-juice-gt-factory.py \
  --plan "$artifact_root/plan.json" --run-report "$artifact_root/run/report.json" \
  --curation-report "$artifact_root/curated-v2/report.json" \
  --tensor "$artifact_root/curated-v2/lab-request-views.npz" \
  --output "$artifact_root/quality-gates.json"
podman logs "$container_name" >"$artifact_root/container.log" 2>&1
echo "Factory evidence: $artifact_root"
