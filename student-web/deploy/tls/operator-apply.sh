#!/usr/bin/env bash
# VM operator only. Explicit apply/rollback; never invoked by prepare.py.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Operator sudo required' >&2; exit 2; }
case ${1:-} in
  apply)
    [[ $# -eq 4 ]] || { echo 'apply STAGED_SITE CERT_DIRECTORY NEW_BACKUP_DIRECTORY' >&2; exit 2; }
    WS_SITE=$(readlink -f /etc/nginx/sites-enabled/student-web)
    [[ -f "$WS_SITE" && "$WS_SITE" == /etc/nginx/* ]] || exit 2
    [[ ! -e /etc/nginx/student-tls ]] || { echo 'TLS directory exists; manual review required' >&2; exit 2; }
    nginx -t
    systemctl is-active --quiet nginx
    umask 077
    mkdir -m 700 -- "$4"
    WS_BACKUP=$(cd -- "$4" && pwd)
    cp -a -- "$WS_SITE" "$WS_BACKUP/site.before"
    printf '%s\n' "$WS_SITE" > "$WS_BACKUP/site.path"
    install -d -m 700 /etc/nginx/student-tls
    install -m 600 -- "$3/student.key" /etc/nginx/student-tls/student.key
    install -m 644 -- "$3/student.crt" /etc/nginx/student-tls/student.crt
    cp -- "$2" "$WS_SITE"
    if ! nginx -t; then
      cp -a -- "$WS_BACKUP/site.before" "$WS_SITE"
      echo 'Validation failed; previous site restored. TLS files retained for review; no reload.' >&2
      exit 1
    fi
    if ! systemctl reload nginx; then
      cp -a -- "$WS_BACKUP/site.before" "$WS_SITE"
      nginx -t && systemctl reload nginx
      echo 'Reload failed; rollback attempted. Inspect service status.' >&2
      exit 1
    fi
    echo "Applied; backup: $WS_BACKUP. Run HTTP/HTTPS and application checks now."
    ;;
  rollback)
    [[ $# -eq 2 ]] || exit 2
    WS_SITE=$(cat -- "$2/site.path")
    [[ "$WS_SITE" == /etc/nginx/* && -f "$2/site.before" ]] || exit 2
    cp -a -- "$2/site.before" "$WS_SITE"
    nginx -t
    systemctl reload nginx
    echo 'Original site restored. Certificates retained; no unrelated files removed.'
    ;;
  *) echo 'Use apply or rollback; see README.' >&2; exit 2;;
esac
