"""Build a native release directory. No service, firewall, UID or DB mutations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import yaml
from native_vm import nginx as vm_nginx

HERE = Path(__file__).resolve().parent
SEC = HERE.parents[1]
LIVE = "/opt/ws-native/current"
ETC = "/etc/ws-native"
STATE = "/var/lib/ws-native"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def prepare(archive, out):
    if out.exists():
        raise ValueError("Expected a new release directory")
    # Pinned Beta archive and the existing i5-specific thermal admission, unchanged.
    dev = module("dev", SEC/"deploy/dev-i5/prepare.py")
    dev.prepare(archive,out)
    sys.path.insert(0,str(SEC/"deploy/local-r39"))
    import student_deps
    import beta_profile as b
    b.ROOT, b.LIVE, b.CONFIG, b.STATE = out, LIVE, ETC, STATE
    b.SUPPORT = LIVE+"/support/security-web"
    b.SCORER_STATE = STATE+"/scorer"
    support = out/"support/security-web"
    for name in ("local-egress-guard.py","proof-nginx-lifecycle.py"):
        shutil.copy2(SEC/"scripts"/name,support/"scripts"/name)
    # Only the native launcher's POSIX account names change. Model, delegated
    # guardian, sensors, thresholds and scorer manifest remain pinned.
    launch = out/"scorer/launch.py"
    text = launch.read_text()
    for old,new in (("websentinel-edge","ws-native-edge"),("websentinel-evidence","ws-native-evidence")):
        if old not in text:
            raise ValueError("Unexpected scorer launcher")
        text = text.replace(old,new)
    (out/"scorer/native-launch.py").write_text(text)
    shutil.copy2(SEC/"target/release/pbl4-security-demo",out/"security")
    subprocess.run(["jar","--create","--file",out/"student/student.jar","-C",
                    SEC.parent/"student-web/backend/target/classes","."],check=True)
    lib = out/"student/lib"
    lib.mkdir()
    for row in student_deps.rows(out/"student/dependencies.json"):
        src = Path.home()/".m2/repository"/row["repository_path"]
        if not student_deps.matches(src,row):
            raise ValueError("Missing pinned JAR: "+row["name"])
        shutil.copy2(src,lib/row["name"])
    shutil.copy2(SEC/"deploy/dev-i5/adaptive/restore_fingerprint.py",out)
    shutil.copy2(SEC/"deploy/dev-i5/adaptive/preflight_guest.py",out/"restore_compare.py")
    for name in ("stage-db-config.py","docker_pg.py","native_policy.py","vm_transport.py","direct_peer.py","worker.py","control.sh","db_check.py","preflight.py","install-first.sh"):
        shutil.copy2(HERE/name,out/name)
    shutil.copy2(SEC/"deploy/dev-i5/adaptive/approve_session.py",out)
    migrations = sorted((SEC/"migrations").glob("*.sql"))
    (out/"migrations.expected").write_text("".join(
        f"{int(p.name.split('_')[0])}|{hashlib.sha384(p.read_bytes()).hexdigest()}|t\n" for p in migrations))
    import zlib
    flyway=[]
    for migration in sorted((SEC.parent/"student-web/backend/src/main/resources/db/migration").glob("V*__*.sql")):
        crc=zlib.crc32("".join(migration.read_text(encoding="utf-8-sig").splitlines()).encode())
        flyway.append(f"{migration.name.split('__')[0][1:]}|{crc if crc<2**31 else crc-2**32}|t\n")
    (out/"flyway.expected").write_text("".join(flyway))
    # GID placeholder must be rendered against the provisioned account before start.
    config = b.nginx(2147483646)
    if config.count("2147483646") != 1:
        raise ValueError("Unexpected proof GID marker")
    for old,new in (
        ("2147483646","__NATIVE_EDGE_GID__"),("websentinel-edge websentinel-edge","ws-native-edge ws-native-edge"),
        ("/run/websentinel-beta-nginx","/run/ws-native-edge"),("/run/websentinel-edge-shadow","/run/ws-native-shadow"),
        ("127.77.0.1","127.78.0.1"),("127.77.0.2:18080","127.78.0.2:28080"),
        ("127.0.0.3:443","127.78.0.3:28443"),("127.0.0.1:443","127.0.0.1:24443"),
        ("127.0.0.1:9443","127.0.0.1:29443"),("127.0.0.1:8080","127.0.0.1:28081"),
        ("127.0.0.1:3000","127.0.0.1:23000")):
        if old not in config:
            raise ValueError("Missing expected nginx directive: "+old)
        config=config.replace(old,new)
    # Only gate a literal operator-approved location; preserve proxy headers, TLS,
    # edge protection and AI mirror by copying the rendered forwarding location.
    marker="    location / {\n        set $r35_id"
    if config.count(marker)!=1:
        raise ValueError("Cannot locate edge forwarding location")
    a=config.index(marker)
    z=config.index("\n    }",a)+len("\n    }")
    gated=config[a:z].replace("location / {","location = __APPROVED_PATH__ {\n        set $ws_main_id $request_id;\n        auth_request /__ws_native_check;")
    auth="""    location = /__ws_native_check {
        internal;
        proxy_pass_request_headers off;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-WS-Request-Id $ws_main_id;
        proxy_set_header X-WS-Selector native-session;
        proxy_set_header X-WS-Session-Cookie $http_cookie;
        proxy_pass http://unix:/run/ws-native-gate/gate.sock:/check;
    }
"""
    (out/"native-gated-location.template").write_text(gated+"\n"+auth)
    (out/"native-nginx.template").write_text(vm_nginx(config[:a]+"    include /etc/ws-native/approved-location.inc;\n"+config[a:]))
    sensor=yaml.safe_load(b.sensor())
    cap=sensor["af-packet"][0]
    cap["cluster-id"]=197
    cap["bpf-filter"]=cap["bpf-filter"].replace("127.77.","127.78.").replace("18080","28080")
    for k in ("HOME_NET","HTTP_SERVERS"):
        sensor["vars"]["address-groups"][k]="[127.78.0.2/32]"
    sensor["vars"]["port-groups"]["HTTP_PORTS"]="28080"
    sensor["pid-file"]="/run/ws-native-sensor/sensor.pid"
    (out/"native-suricata.yaml").write_text("%YAML 1.1\n---\n"+yaml.safe_dump(sensor,sort_keys=False))
    unitdir=out/"units";unitdir.mkdir()
    for unit, text in b.units().items():
        name=unit.replace("websentinel-https-scorer","ws-native-scorer").replace("websentinel-beta-","ws-native-")
        for old,new in (("postgresql.service","docker.service"),("websentinel-https-scorer.service","ws-native-scorer.service"),
                        ("websentinel-beta-","ws-native-"),("websentinel-evidence","ws-native-evidence"),
                        ("websentinel-edge","ws-native-edge"),("websentinel-scorer","ws-native-scorer"),
                        ("websentinel-student","ws-native-student"),("websentinel-security","ws-native-security"),
                        ("websentinel-sensor","ws-native-sensor"),("websentinel-https-readers","ws-native-evidence"),
                        ("/run/ws-native-edge-shadow","/run/ws-native-shadow"),
                        ("RuntimeDirectory=ws-native-edge-shadow","RuntimeDirectory=ws-native-shadow"),
                        ("RuntimeDirectory=ws-native-nginx","RuntimeDirectory=ws-native-edge"),
                        ("StateDirectory=websentinel-https","StateDirectory=ws-native/scorer"),
                        ("/scorer/launch.py","/scorer/native-launch.py"),
                        (STATE+"/java/lib/",LIVE+"/student/lib/"),
                        ("--unit ws-native-edge.service","--unit ws-native-edge.service --user ws-native-edge"),
                        ("ReadWritePaths="+STATE+"/sensor","RuntimeDirectory=ws-native-sensor\nReadWritePaths="+STATE+"/sensor")):
            text=text.replace(old,new)
        if name=="ws-native-student.service":
            continue
        if name=="ws-native-edge.service":
            text=text.replace(" ws-native-student.service","")
        (unitdir/name).write_text(text)
    shutil.copy2(HERE/"fw-status.py",out)
    for path in HERE.glob("ws-native-*.*"):
        shutil.copy2(path,unitdir)
    for p in (out/"manage.py",out/"SHA256SUMS"):
        p.unlink()  # discard the guest-only installer, generate a native manifest
    (out/"SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(out)}\n" for p in sorted(out.rglob("*")) if p.is_file() and "__pycache__" not in p.parts))


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("beta_archive",type=Path)
    cli.add_argument("output",type=Path)
    args=cli.parse_args()
    prepare(args.beta_archive,args.output.resolve())
