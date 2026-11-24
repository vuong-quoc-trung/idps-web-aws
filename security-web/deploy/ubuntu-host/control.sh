#!/bin/bash
set -euo pipefail
cd /opt/ws-native/current
units=(ws-native-security ws-native-scorer ws-native-sensor ws-native-gate ws-native-edge)
case "${1:-}" in
  verify-db) exec /usr/bin/python3 -B ./db_check.py ;;
  status) systemctl --no-pager show -p Id -p ActiveState -p SubState -p MainPID "${units[@]}" ws-native-worker.timer ;;
  health)
    for u in "${units[@]}"; do systemctl is-active --quiet "$u"; done
    curl --max-time 4 --cacert /etc/ws-native/edge.crt -fsS https://127.0.0.1:29443/health
    test "$(curl --max-time 4 --cacert /etc/ws-native/edge.crt -s -o /dev/null -w '%{http_code}' https://127.0.0.1:24443/api/auth/me)" = 401
    runuser -u ws-native-edge -- curl --max-time 3 -fsSi --unix-socket /run/ws-native-shadow/receiver.sock http://localhost/healthz | tr -d '\r' | grep -Fxi "x-model-sha256: $(sha256sum scorer/ai-training/contracts/quality-freeze-r37/release/finalist.onnx | cut -d' ' -f1)"
    ;;
  start)
    test ! -e /etc/ws-native/approval.json
    sha256sum --quiet -c SHA256SUMS
    # First start is permitted only after an independent native restore and schema review.
    /usr/bin/python3 -B ./db_check.py
    started=()
    for u in "${units[@]}"; do
      if ! systemctl is-active --quiet "$u"; then
        if ! systemctl start "$u"; then
          for ((i=${#started[@]}-1;i>=0;i--)); do systemctl stop "${started[i]}"; done
          exit 1
        fi
        started+=("$u")
      fi
    done
    ;;
  stop|rollback)
    result=0
    systemctl stop ws-native-worker.timer ws-native-worker.service || result=1
    runuser -u ws-native-actuator -g ws-native-evidence -- python3 -B ./worker.py stop || result=1
    systemctl stop ws-native-edge ws-native-gate ws-native-sensor ws-native-scorer ws-native-security || result=1
    exit "$result"
    ;;
  *) echo 'Expected start, status, health, stop or rollback' >&2; exit 2 ;;
esac
