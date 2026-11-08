#!/usr/bin/env bash
# Controlled detection probes for the repository's three-VM lab. Run on Kali.
set -euo pipefail
base='http://192.168.10.1'
selected='all'
dry_run=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
        all|normal|xss|sqli|traversal|sensitive|scanner|time-sqli|time-sqli-body|upload|ssrf|ssrf-body) selected="$arg" ;;
        -h|--help)
            echo 'Usage: bash lab-probes.sh [all|normal|xss|sqli|traversal|sensitive|scanner|time-sqli|time-sqli-body|upload|ssrf|ssrf-body] [--dry-run]'
            echo 'Fixed lab target: http://192.168.10.1 (Security Host proxy). Run on Kali; start with AUTO_BLOCK=false.'
            exit 0 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 1; }
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
failures=0
probe() {
    local name="$1" sid="$2" target="$3" agent="$4"
    local body="${5:-}" content_type="${6:-application/x-www-form-urlencoded}"
    printf '\n[%s] case=%s expected_sid=%s run=%s\n' "$(date -u +%FT%TZ)" "$name" "$sid" "$run_id"
    local args=(--noproxy '*' --globoff --path-as-is --silent --show-error
        --connect-timeout 3 --max-time 8 --output /dev/null
        --write-out 'HTTP %{http_code}; remote=%{remote_ip}; seconds=%{time_total}\n'
        --user-agent "$agent" "$base$target&pbl4_run=$run_id")
    if [[ -n $body ]]; then
        args+=(--header "Content-Type: $content_type" --data-binary "$body")
    fi
    if $dry_run; then
        printf 'curl '; printf '%q ' "${args[@]}"; printf '\n'
    elif ! curl "${args[@]}"; then
        echo 'Request failed: inspect routing, proxy and block status. This is not an IDS result.' >&2
        failures=$((failures + 1))
    fi
}
echo 'Lab detection check: Kali -> Security proxy 192.168.10.1:80 -> Student Web'
echo 'Keep AUTO_BLOCK=false and unblock the Kali IP first. HTTP status is NOT proof of detection.'
echo 'Keep ENFORCEMENT_MODE=OFF. No live flood is generated; use test-extended-rules.py for rate tests.'
for name in normal xss sqli traversal sensitive scanner time-sqli time-sqli-body upload ssrf ssrf-body; do
    [[ $selected == all || $selected == "$name" ]] || continue
    case "$name" in
        normal) probe "$name" none '/?pbl4_case=normal' 'pbl4-lab-probe/1.0' ;;
        xss) probe "$name" 1000003 '/__pbl4_probe__?pbl4_case=xss&q=%3Cscript%3Ealert(1)%3C%2Fscript%3E' 'pbl4-lab-probe/1.0' ;;
        sqli) probe "$name" 1000002 '/__pbl4_probe__?pbl4_case=sqli&q=%27%20OR%201%3D1--' 'pbl4-lab-probe/1.0' ;;
        traversal) probe "$name" 1000004 '/__pbl4_probe__?pbl4_case=traversal&file=../../pbl4-probe.txt' 'pbl4-lab-probe/1.0' ;;
        sensitive) probe "$name" 1000006 '/__pbl4_probe__?pbl4_case=sensitive&file=/.env' 'pbl4-lab-probe/1.0' ;;
        scanner) probe "$name" 1000007 '/__pbl4_probe__?pbl4_case=scanner' 'sqlmap/pbl4-lab-probe' ;;
        time-sqli) probe "$name" 1000008 '/__pbl4_probe__?pbl4_case=time-sqli&q=pg_sleep%281%29' 'pbl4-lab-probe/1.0' ;;
        time-sqli-body) probe "$name" 1000013 '/__pbl4_probe__?pbl4_case=time-sqli-body' 'pbl4-lab-probe/1.0' 'q=pg_sleep%281%29' ;;
        upload)
            body=$'--pbl4-boundary\r\nContent-Disposition: form-data; name="file"; filename="pbl4-probe.php"\r\nContent-Type: application/octet-stream\r\n\r\n<?php /* PBL4 inert fixture: system("echo PBL4"); */ ?>\r\n--pbl4-boundary--\r\n'
            probe "$name" 1000011 '/__pbl4_probe__?pbl4_case=upload' 'pbl4-lab-probe/1.0' "$body" 'multipart/form-data; boundary=pbl4-boundary'
            ;;
        ssrf) probe "$name" 1000012 '/__pbl4_probe__?pbl4_case=ssrf&url=http%3A%2F%2F169.254.169.254%2Fpbl4-fixture' 'pbl4-lab-probe/1.0' ;;
        ssrf-body) probe "$name" 1000014 '/__pbl4_probe__?pbl4_case=ssrf-body' 'pbl4-lab-probe/1.0' 'url=http%3A%2F%2Flocalhost%2Fpbl4-fixture' ;;
    esac
    if ! $dry_run && [[ $selected == all ]]; then sleep 2; fi
done
printf '\nFinished. HTTP failures=%s. Match UTC time + source IP + SID in eve.json, then DB/dashboard.\n' "$failures"
(( failures == 0 ))
