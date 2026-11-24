#!/bin/bash
# Unprivileged, disposable guest-only Edge. No traffic to Student or real Edge.
set -euo pipefail
test "$(hostname)" = ws-i5-dev
test "$(cat /run/systemd/container)" = systemd-nspawn
test "$(id -u)" != 0
cd /run/ws-auto-edge
umask 077
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=ws-auto-canary' \
  -addext 'subjectAltName=IP:127.0.0.1' -keyout key.pem -out cert.pem >/dev/null 2>&1
sed 's|@GATE_SOCKET@|/run/ws-auto-gate/gate.sock|g' /opt/ws-auto-canary/gate.conf.template > gate.inc
cat > nginx.conf <<'NGINX'
pid /run/ws-auto-edge/nginx.pid;
error_log stderr warn;
events {}
http {
    client_body_temp_path body;
    proxy_temp_path proxy;
    fastcgi_temp_path fastcgi;
    uwsgi_temp_path uwsgi;
    scgi_temp_path scgi;
    log_format edge '$request_id $status upstream=$upstream_status';
    log_format origin 'origin request=$http_x_request_id';
    upstream ws_dev_canary_origin { server unix:/run/ws-auto-edge/origin.sock; }
    server {
        listen unix:/run/ws-auto-edge/origin.sock;
        access_log /run/ws-auto-edge/origin.log origin;
        return 204;
    }
    server {
        listen 127.0.0.1:19443 ssl;
        ssl_certificate cert.pem;
        ssl_certificate_key key.pem;
        access_log /run/ws-auto-edge/access.log edge;
        add_header X-Request-Id $request_id always;
        proxy_set_header X-Request-Id $request_id;
        include gate.inc;
        location = /normal { proxy_pass http://ws_dev_canary_origin; }
        location / { return 404; }
    }
}
NGINX
nginx -e stderr -t -p "$PWD/" -c nginx.conf
exec nginx -e stderr -p "$PWD/" -c nginx.conf -g 'daemon off;'
