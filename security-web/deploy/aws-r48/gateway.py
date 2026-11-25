"""Render the cloud beta gateway from the verified R47 configuration."""


ROUTES = {
    ("GET", "/api/auth/csrf"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}
SOURCE = "127.77.0.1"
EGRESS = "127.77.0.2"
PORT = 18080


def render(base, kit, key, key_gid, edge_log, scorer_socket):
    original = """    location /api/ {
        proxy_pass http://127.0.0.1:8080;"""
    if base.count(original) != 1:
        raise ValueError("Expected one original Student API upstream")
    mirror = (kit / "https-shadow-mirror.conf").read_text().replace(
        "__SOCKET__", str(scorer_socket)
    )
    routes = "".join(f'    "{method}:{path}" 1;\n' for method, path in sorted(ROUTES))
    http = f"""# WebSentinel R48 passive HTTPS evidence
js_import r48proof from {kit}/proof-probe.js;
js_shared_dict_zone zone=nonces:1m timeout=65s;
js_var $probe_key_gid {key_gid};
js_var $probe_receipt;
js_set $probe_signed r48proof.sign;
js_set $probe_verified r48proof.verify;

map "$request_method:$request_uri" $r48_observed {{
    default 0;
{routes}}}
log_format r48_access escape=json '{{"timestamp":"$time_iso8601","request_id":"$request_id",'
    '"client_ip":"$remote_addr","http_method":"$request_method","uri_path":"$uri",'
    '"status":$status,"dispatch":"$r35_dispatch","http_host":"$http_host"}}';

server {{
    listen {EGRESS}:{PORT};
    server_name _;
    allow {SOURCE};
    deny all;
    access_log off;
    error_log /dev/null crit;
    set $probe_key_file {key};
    client_max_body_size 1m;
    client_body_timeout 10s;
    proxy_connect_timeout 2s;
    proxy_read_timeout 15s;

    location / {{
        if ($r48_observed = 0) {{ return 404; }}
        if ($probe_verified != ok) {{ return 403; }}
        add_header X-WS-Receipt $probe_receipt always;
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Request-Id $http_x_request_id;
        proxy_set_header X-Forwarded-For $http_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        proxy_set_header X-WS-Proof "";
        proxy_set_header X-WS-Receipt "";
        proxy_set_header Forwarded "";
        proxy_hide_header X-WS-Receipt;
    }}
}}

"""
    student = f"""{mirror}
    location @r48_observed {{
        set $probe_key_file {key};
        set $r35_id $request_id;
        set $r35_method $request_method;
        set $r35_target $request_uri;
        set $r35_dispatch $msec;
        set $r35_api 1;
        access_log {edge_log} r48_access;
        error_log /dev/null crit;
        mirror /_idps_https_projection;
        mirror_request_body off;
        client_max_body_size 1m;
        proxy_bind {SOURCE};
        proxy_pass http://{EGRESS}:{PORT};
        proxy_http_version 1.1;
        proxy_set_header Connection close;
        proxy_set_header Host $http_host;
        proxy_set_header User-Agent "WebSentinel-Cloud-Beta";
        proxy_set_header Referer "";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-Id $request_id;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-WS-Proof $probe_signed;
        proxy_set_header X-WS-Receipt "";
        proxy_set_header Forwarded "";
        proxy_hide_header X-Request-Id;
        proxy_hide_header X-WS-Receipt;
        proxy_hide_header X-WS-Proof;
        proxy_connect_timeout 2s;
        proxy_read_timeout 15s;
        proxy_next_upstream off;
    }}

    location /api/ {{
        error_page 418 = @r48_observed;
        if ($r48_observed = 1) {{ return 418; }}
        proxy_pass http://127.0.0.1:8080;"""
    return http + base.replace(original, student)


def sensor_config(kit, state):
    return f"""%YAML 1.1
---
vars:
  address-groups:
    HOME_NET: "[{EGRESS}/32]"
    EXTERNAL_NET: "!$HOME_NET"
    HTTP_SERVERS: "[{EGRESS}/32]"
  port-groups:
    HTTP_PORTS: "{PORT}"
    SHELLCODE_PORTS: "!80"
af-packet:
  - interface: lo
    threads: 1
    cluster-id: 198
    cluster-type: cluster_flow
    defrag: yes
    use-mmap: yes
    bpf-filter: "tcp and ((src host {SOURCE} and dst host {EGRESS} and dst port {PORT}) or (src host {EGRESS} and src port {PORT} and dst host {SOURCE}))"
stream:
  inline: no
  checksum-validation: yes
stats:
  enabled: no
default-log-dir: {state}
default-rule-path: {kit}
classification-file: /etc/suricata/classification.config
reference-config-file: /etc/suricata/reference.config
rule-files:
  - pbl4.rules
outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: eve.json
      filemode: 640
      types:
        - http:
            extended: yes
            dump-all-headers: none
        - alert:
            metadata: no
            tagged-packets: no
            payload: no
            payload-printable: no
            packet: no
            http-body: no
            http-body-printable: no
  - lua:
      enabled: yes
      scripts-dir: {kit}
      scripts:
        - transaction-evidence.lua
app-layer:
  protocols:
    http:
      enabled: yes
unix-command:
  enabled: no
"""
