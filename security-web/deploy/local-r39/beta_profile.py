"""Render the Local beta profile using the checked R38 HTTPS and sensor templates."""

import importlib.util
from pathlib import Path

import yaml

import student_deps

ROOT = Path(__file__).resolve().parent
LIVE = "/opt/websentinel-beta/current"
CONFIG = "/etc/websentinel-beta"
STATE = "/var/lib/websentinel-beta"
SCORER_STATE = "/var/lib/websentinel-https"
SUPPORT = LIVE + "/support/security-web"
UNITS = [
    "websentinel-https-scorer.service",
    "websentinel-beta-student.service",
    "websentinel-beta-security.service",
    "websentinel-beta-sensor.service",
    "websentinel-beta-edge.service",
]


def load(name):
    path = ROOT / "support/security-web/scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nginx(gid):
    script = load("prepare-proof-egress.py")
    site, http = script.render(
        CONFIG + "/edge.crt",
        CONFIG + "/edge.key",
        CONFIG + "/origin.crt",
        "student.internal",
        SUPPORT + "/tests/njs/proof-probe.js",
        CONFIG + "/key/key.json",
        gid,
        shadow_socket="/run/websentinel-edge-shadow/receiver.sock",
        edge_ip="127.0.0.1",
        student_ip="127.0.0.3",
    )
    site = site.replace("listen 127.0.0.1:80;", "")
    site = "\n".join(line for line in site.splitlines() if "tag=ai_shadow" not in line)
    site = site.replace("/var/log/nginx/access.log", STATE + "/edge/access.jsonl")
    return f"""load_module /usr/lib/nginx/modules/ngx_http_js_module.so;
user websentinel-edge websentinel-edge;
worker_processes 1;
pid /run/websentinel-beta-nginx/nginx.pid;
error_log stderr crit;
events {{ worker_connections 256; }}
http {{
    include /etc/nginx/mime.types;
    access_log off;
    client_body_temp_path /run/websentinel-beta-nginx/client_body;
    proxy_temp_path /run/websentinel-beta-nginx/proxy;
    fastcgi_temp_path /run/websentinel-beta-nginx/fastcgi;
    uwsgi_temp_path /run/websentinel-beta-nginx/uwsgi;
    scgi_temp_path /run/websentinel-beta-nginx/scgi;
    {http}
    {site}
    server {{
        listen 127.0.0.3:443 ssl;
        server_name student.internal;
        ssl_certificate {CONFIG}/origin.crt;
        ssl_certificate_key {CONFIG}/origin.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        error_log /dev/null crit;
        root {LIVE}/student/frontend/dist;
        location /api/ {{
            proxy_pass http://127.0.0.1:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Request-ID $http_x_request_id;
            proxy_set_header X-Forwarded-For $http_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        }}
        location / {{ try_files $uri $uri/ /index.html; }}
    }}
    server {{
        listen 127.0.0.1:9443 ssl;
        ssl_certificate {CONFIG}/edge.crt;
        ssl_certificate_key {CONFIG}/edge.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        error_log /dev/null crit;
        client_max_body_size 16k;
        location / {{
            proxy_pass http://127.0.0.1:3000;
            proxy_set_header X-Forwarded-For "";
        }}
    }}
}}
"""


def sensor():
    template = Path("/etc/suricata/suricata.yaml")
    config = load("prepare-suricata-post-proxy.py").render(
        yaml.safe_load(template.read_text()), "local-egress"
    )
    config.pop("run-as", None)
    config["default-log-dir"] = STATE + "/sensor"
    config["default-rule-path"] = SUPPORT + "/suricata"
    config["rule-files"] = ["pbl4.rules"]
    config["unix-command"] = {"enabled": False}
    config["outputs"] = [
        entry for entry in config["outputs"] if entry.get("eve-log", {}).get("enabled")
    ]
    config["outputs"].append(
        {
            "lua": {
                "enabled": True,
                "scripts-dir": SUPPORT + "/config/suricata",
                "scripts": ["transaction-evidence.lua"],
            }
        }
    )
    return "%YAML 1.1\n---\n" + yaml.safe_dump(config, sort_keys=False)


def units():
    common = """Restart=on-failure
RestartSec=3
TimeoutStopSec=15
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
UMask=0027
"""
    db = "Requires=postgresql.service\nAfter=postgresql.service\n"
    jars = student_deps.rows(ROOT / "student/dependencies.json")
    classpath = ":".join(
        [
            LIVE + "/student/student.jar",
            *(STATE + "/java/lib/" + row["name"] for row in jars),
        ]
    )
    student = f"""User=websentinel-student
Group=websentinel-evidence
EnvironmentFile={CONFIG}/student.env
WorkingDirectory={STATE}/student
ReadWritePaths={STATE}/student
ExecStart=/usr/bin/java -XX:ActiveProcessorCount=2 -Xmx512m -cp {classpath} com.pbl4.studentweb.StudentWebApplication
MemoryMax=1G
CPUQuota=200%
"""
    security = f"""User=websentinel-security
Group=websentinel-evidence
SupplementaryGroups=websentinel-https-readers
EnvironmentFile={CONFIG}/security.env
WorkingDirectory={LIVE}/security
ExecStart={LIVE}/security/pbl4-security-demo
MemoryMax=512M
CPUQuota=100%
"""
    sensor = f"""User=websentinel-sensor
Group=websentinel-evidence
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
ReadWritePaths={STATE}/sensor
ExecStart=/usr/bin/python3 -IB {SUPPORT}/scripts/run-suricata-generation.py -c {CONFIG}/suricata.yaml --af-packet --runmode single
MemoryMax=768M
CPUQuota=100%
"""
    edge = f"""RuntimeDirectory=websentinel-beta-nginx
RuntimeDirectoryMode=0755
UMask=0027
KillMode=control-group
Restart=no
ExecStart=/usr/bin/python3 -B {SUPPORT}/scripts/proof-nginx-lifecycle.py --unit websentinel-beta-edge.service --config {CONFIG}/nginx.conf --key {CONFIG}/key/key.json --state {STATE}/guard
TimeoutStopSec=30
"""
    return {
        UNITS[0]: (ROOT / "support/websentinel-https-scorer.service")
        .read_text()
        .replace("/etc/websentinel/https-scorer.env", CONFIG + "/scorer.env")
        .replace("/opt/websentinel/https/current", LIVE + "/scorer")
        .replace("\nGroup=websentinel-scorer\n", "\nGroup=websentinel-https-readers\n")
        .replace("StateDirectoryMode=0711", "StateDirectoryMode=0750"),
        UNITS[1]: service("Student Web", db, student + common),
        UNITS[2]: service("Security Web", db, security + common),
        UNITS[3]: service("Suricata observation", "", sensor + common),
        UNITS[4]: service(
            "HTTPS proof edge",
            f"Wants={' '.join(UNITS[:-1])}\nAfter={' '.join(UNITS[:-1])}\n",
            edge,
        ),
    }


def service(title, dependencies, body):
    return f"""[Unit]
Description=WebSentinel Beta {title}
StartLimitIntervalSec=120
StartLimitBurst=3
{dependencies}
[Service]
Type=exec
{body}
[Install]
WantedBy=multi-user.target
"""
