#!/bin/bash
# Native Dashboard only. Backup + transactional schema change + monitoring rollout.
set -Eeuo pipefail
src=$(dirname "$(realpath "$0")")
project=$(realpath "$src/../..")
if (( EUID )); then
    if [[ ${1:-} != rollback ]]; then
        (cd "$project" && cargo build --release --offline --features dev-hybrid-review)
        (cd "$project/frontend" && npm run build)
    fi
    exec sudo bash "$0" "$@"
fi
umask 077
exec 8>/run/lock/ws-native-dashboard-sse
flock -n 8
live=/opt/ws-native/runtime-fix
pg=(docker exec -i pbl4-postgres psql -XqAt -v ON_ERROR_STOP=1 -U pbl4 -d ws_native_security)
file="$project/migrations/0020_alert_notifications.sql"
digest=$(sha384sum "$file" | cut -d' ' -f1)
rollback() {
    local backup=$1
    [[ $backup =~ ^/var/backups/ws-native-sse\.[a-zA-Z0-9]+$ && $(stat -c %u "$backup") == 0 ]]
    [[ $(cat "$backup/schema.sha384") == "$digest" ]]
    [[ $("${pg[@]}" -c "select max(version) from _sqlx_migrations") == 20 ]]
    [[ $("${pg[@]}" -c "select encode(checksum,'hex') from _sqlx_migrations where version=20") == "$digest" ]]
    "${pg[@]}" <<SQL
BEGIN;
SET LOCAL lock_timeout='5s';
DROP TRIGGER ws_alert_created ON security_alerts;
DROP FUNCTION ws_notify_alert_created();
DELETE FROM _sqlx_migrations WHERE version=20;
COMMIT;
SQL
    install -m0755 "$backup/security" "$live/security.sse-old"
    mv -T "$live/security.sse-old" "$live/security"
    cp -aT "$backup/dist" "$live/frontend/dist"
    systemctl restart ws-native-security
}
if [[ ${1:-} == rollback ]]; then rollback "${2:?backup directory required}"; exit; fi
pid=$(systemctl show ws-native-security -p MainPID --value)
test "$(readlink "/proc/$pid/exe")" = "$live/security"
grep -zFxq WS_NATIVE_SCHEMA_CHECK_ONLY=1 "/proc/$pid/environ"
backup=$(mktemp -d /var/backups/ws-native-sse.XXXXXXXX)
echo "Backup / rollback argument: $backup"
for f in "$project"/migrations/*.sql; do
    version=${f##*/}; version=${version%%_*}; (( 10#$version < 20 )) || continue
    printf '%d|%s\n' "$((10#$version))" "$(sha384sum "$f" | cut -d' ' -f1)"
done > "$backup/expected"
"${pg[@]}" -c "select version,encode(checksum,'hex') from _sqlx_migrations where success order by version" > "$backup/applied"
cmp "$backup/expected" "$backup/applied"
cp -a "$live/security" "$live/frontend/dist" "$backup/"
docker exec pbl4-postgres pg_dump --lock-wait-timeout=5s -U pbl4 -Fc ws_native_security > "$backup/database.dump"
docker exec -i pbl4-postgres pg_restore -l < "$backup/database.dump" > "$backup/archive.list"
echo "$digest" > "$backup/schema.sha384"
{
    echo "BEGIN; SET LOCAL ROLE ws_native_security; SET LOCAL lock_timeout='5s';"
    cat "$file"
    echo "INSERT INTO _sqlx_migrations(version,description,success,checksum,execution_time) VALUES(20,'alert notifications',true,decode('$digest','hex'),0); COMMIT;"
} | "${pg[@]}"
trap 'rc=$?; trap - ERR; rollback "$backup"; exit "$rc"' ERR
bash "$src/apply-runtime-fix.sh" --monitoring
python3 - "$src" <<'PY'
import json, pathlib, urllib.request
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
base='http://127.0.0.1:23000/api/'
payload=json.dumps(dict(username='admin',password=pathlib.Path('/etc/ws-native/dashboard.password').read_text().strip())).encode()
with op.open(urllib.request.Request(base+'auth/login',payload,{'Content-Type':'application/json'}),timeout=5) as r:
    headers={'Authorization':'Bearer '+json.load(r)['token']}
try:
    with op.open(urllib.request.Request(base+'events',headers=headers),timeout=5) as r:
        assert r.headers.get_content_type()=='text/event-stream'
        frame=b''
        while len(frame)<2048:
            line=r.readline(512)
            if line in (b'',b'\n'): break
            frame+=line
        assert b'event: resync' in frame
finally:
    op.open(urllib.request.Request(base+'auth/logout',b'',headers),timeout=5).close()
print('PASS authenticated native SSE resync')
PY
