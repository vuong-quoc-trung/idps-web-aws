#!/bin/sh
# Submitted verbatim to SSM. All paths and digests describe the accepted staging artifacts.
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077

fail() {
  printf 'PBL4_BLOCKED=%s\n' "$1"
  exit 1
}

release=/opt/websentinel-r62/prevention-r61
runner=$release/r60_stage.sh
bundle=$release/bundle.tgz
backup=/var/backups/websentinel-final/security.bin
runner_sha=18594ad2499d64accdff2f50a106e1e606e10a02c38fc8dae1a2b492bd354010
bundle_sha=b0f41ac44a87081f4046d15400a30d8a66bebf5575418b99b4193fd0cf573925
backup_sha=64299518c6f18fbcc9d7ab54a304996e938e7463d0624765f892eee505a0935c

verify() {
  test -f "$2" && test ! -L "$2" && test "$(stat -c '%u' "$2")" = 0 &&
    printf '%s  %s\n' "$1" "$2" | sha256sum --check --status
}

test "$(id -u)" = 0 || fail SSM_USER
exec 9>/run/lock/websentinel-pbl4-live.lock
flock -n 9 || fail LAB_BUSY
test ! -e /run/websentinel-r56-lab || fail LAB_BUSY
verify "$runner_sha" "$runner" && verify "$bundle_sha" "$bundle" || fail LAB_ARTIFACT
verify "$backup_sha" "$backup" || fail LAB_BASELINE

# Reconstruct only the disposable lab executable from the original signed-off base.
# The serving binary and rollback file are both kept in place.
patched=$(sed "s|^baseline=/opt/websentinel-r47/current/security/pbl4-security-demo\$|baseline=$backup|" "$runner")
printf '%s\n' "$patched" | grep -Fxq "baseline=$backup" || fail LAB_ARTIFACT
printf '%s\n' "$patched" | /bin/bash -s -- "$bundle" "$bundle_sha" r61
