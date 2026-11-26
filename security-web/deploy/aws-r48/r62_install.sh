#!/usr/bin/env bash
# Install the accepted, on-demand EC2 Prevention package with its existing C2 scope.
set -euo pipefail
umask 077

[[ $EUID -eq 0 && $# -eq 2 && -f $1 && -f $2 ]]
archive=$1
runner=$2
base=/opt/websentinel-r62
release=$base/prevention-r61
serving=/opt/websentinel-r47/current/security/pbl4-security-demo
bundle_sha=b0f41ac44a87081f4046d15400a30d8a66bebf5575418b99b4193fd0cf573925
runner_sha=18594ad2499d64accdff2f50a106e1e606e10a02c38fc8dae1a2b492bd354010
serving_sha=64299518c6f18fbcc9d7ab54a304996e938e7463d0624765f892eee505a0935c
lab_sha=d68a81c3a3cd8a22550e9c8fed0a5dcde9fd161a5312e07c84908f705497968b

verify_sha() {
  printf '%s  %s\n' "$1" "$2" | sha256sum --check --quiet
}

(
  cd /opt/websentinel-r48/runtime
  python3 -B -c 'import refresh; refresh.verify_host(); refresh.verify_database()'
)
verify_sha "$serving_sha" "$serving"
test ! -e /run/websentinel-r56-lab
if [[ ! -e $base && ! -L $base ]]; then
  mkdir -m 0700 "$base"
fi
[[ ! -L $base && $(stat -c '%u:%g:%a:%F' "$base") == '0:0:700:directory' ]]
exec 9>"$base/.install.lock"
flock -n 9
if [[ ! -e $release && ! -L $release ]]; then
  stage=$(mktemp -d "$base/.prevention-r61.XXXXXXXX")
  trap 'rm -rf -- "$stage"' EXIT
  install -o root -g root -m 0600 -- "$archive" "$stage/bundle.tgz"
  install -o root -g root -m 0700 -- "$runner" "$stage/r60_stage.sh"
  verify_sha "$bundle_sha" "$stage/bundle.tgz"
  verify_sha "$runner_sha" "$stage/r60_stage.sh"
  bash -n "$stage/r60_stage.sh"
  # Reconstruct for verification without starting the backend or firewall.
  tar -xOf "$stage/bundle.tgz" lab.zst > "$stage/lab.zst"
  zstd -qd --patch-from="$serving" "$stage/lab.zst" -o "$stage/lab-verify"
  verify_sha "$lab_sha" "$stage/lab-verify"
  rm -- "$stage/lab.zst" "$stage/lab-verify"
  mv -T -- "$stage" "$release"
fi
[[ ! -L $release && $(stat -c '%u:%g:%a:%F' "$release") == '0:0:700:directory' ]]
[[ ! -L $release/bundle.tgz && $(stat -c '%u:%g:%a:%F' "$release/bundle.tgz") == '0:0:600:regular file' ]]
[[ ! -L $release/r60_stage.sh && $(stat -c '%u:%g:%a:%F' "$release/r60_stage.sh") == '0:0:700:regular file' ]]
verify_sha "$bundle_sha" "$release/bundle.tgz"
verify_sha "$runner_sha" "$release/r60_stage.sh"
printf 'R62_RELEASE=%s\nR62_BUNDLE_SHA256=%s\nR62_LAB_SHA256=%s\n' "$release" "$bundle_sha" "$lab_sha"
