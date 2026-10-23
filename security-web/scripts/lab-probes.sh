#!/usr/bin/env bash
# Controlled detection probes for the repository's three-VM lab. Run on Kali.
set -euo pipefail
base='http://192.168.10.1'
selected='all'
dry_run=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
        all|normal|xss|sqli|traversal|sensitive|scanner) selected="$arg" ;;
        -h|--help)
            echo 'Usage: bash lab-probes.sh [all|normal|xss|sqli|traversal|sensitive|scanner] [--dry-run]'
            echo 'Fixed lab target: http://192.168.10.1 (Security VM proxy). Run on Kali; start with AUTO_BLOCK=false.'
            exit 0 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 1; }
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
failures=0
probe() {
    local name="$1" sid="$2" target="$3" agent="$4"
    printf '\n[%s] case=%s expected_sid=%s run=%s\n' "$(date -u +%FT%TZ)" "$name" "$sid" "$run_id"
    local args=(--noproxy '*' --globoff --path-as-is --silent --show-error
        --connect-timeout 3 --max-time 8 --output /dev/null
        --write-out 'HTTP %{http_code}; remote=%{remote_ip}; seconds=%{time_total}\n'
        --user-agent "$agent" "$base$target&pbl4_run=$run_id")
    if $dry_run; then
        printf 'curl '; printf '%q ' "${args[@]}"; printf '\n'
    elif ! curl "${args[@]}"; then
        echo 'Request failed: inspect routing, proxy and block status. This is not an IDS result.' >&2
        failures=$((failures + 1))
    fi
}
echo 'Lab detection check: Kali -> Security proxy 192.168.10.1:80 -> Student Web'
echo 'Keep AUTO_BLOCK=false and unblock the Kali IP first. HTTP status is NOT proof of detection.'
for name in normal xss sqli traversal sensitive scanner; do
    [[ $selected == all || $selected == "$name" ]] || continue
    case "$name" in
        normal) probe "$name" none '/?pbl4_case=normal' 'pbl4-lab-probe/1.0' ;;
        xss) probe "$name" 1000003 '/__pbl4_probe__?pbl4_case=xss&q=%3Cscript%3Ealert(1)%3C%2Fscript%3E' 'pbl4-lab-probe/1.0' ;;
        sqli) probe "$name" 1000002 '/__pbl4_probe__?pbl4_case=sqli&q=%27%20OR%201%3D1--' 'pbl4-lab-probe/1.0' ;;
        traversal) probe "$name" 1000004 '/__pbl4_probe__?pbl4_case=traversal&file=../../pbl4-probe.txt' 'pbl4-lab-probe/1.0' ;;
        sensitive) probe "$name" 1000006 '/__pbl4_probe__?pbl4_case=sensitive&file=/.env' 'pbl4-lab-probe/1.0' ;;
        scanner) probe "$name" 1000007 '/__pbl4_probe__?pbl4_case=scanner' 'sqlmap/pbl4-lab-probe' ;;
    esac
    if ! $dry_run && [[ $selected == all ]]; then sleep 2; fi
done
printf '\nFinished. HTTP failures=%s. Match UTC time + source IP + SID in eve.json, then DB/dashboard.\n' "$failures"
(( failures == 0 ))
