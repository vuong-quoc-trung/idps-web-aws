#!/bin/bash
# New transient processes only; no changes to active Edge/Student/Security units.
set -euo pipefail
test "$(hostname)" = ws-i5-dev
test "$(cat /run/systemd/container)" = systemd-nspawn
test "$(id -un)" = websentinel-security
case "${1:-}" in
    --fixture)
        exec env -i PATH=/usr/sbin:/usr/bin:/bin python3 -B ./test_edge.py ./pbl4-security-demo
        ;;
    *)
        [[ ${1:-} =~ ^[0-9a-f]{32}$ ]] || { echo 'Expected a fresh eligible incident Request ID'; exit 2; }
        plan=$(./pbl4-security-demo --dev-action-plan "$1" BLOCK_REQUEST)
        exec env -i PATH=/usr/sbin:/usr/bin:/bin WS_TEST_CANARY_PLAN="$plan" python3 -B ./test_edge.py ./pbl4-security-demo
        ;;
esac
