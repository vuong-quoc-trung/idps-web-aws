"""Lifecycle for an AI-owned disposable fixture, never the user's existing services.

Uses an isolated Git export/build, a new bounded PostgreSQL container, loopback
ports and private Nginx config. No production DB/credential/config is read.
"""

import io
import os
import secrets
import signal
import socket
import subprocess
import tarfile
import time
import uuid
from pathlib import Path

import psutil

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.lab_capture import ROLES, LabClient
from idps_ai.data.snapshot import new_destination


def start_lab(output, nginx_bin):
    output = new_destination(output)
    nginx_bin = Path(nginx_bin).resolve()
    if not nginx_bin.is_file():
        raise PipelineError("Provide an existing trusted Nginx binary")
    for port in (18880, 18881, 55435):
        with socket.socket() as connection:
            try:
                connection.bind(("127.0.0.1", port))
            except OSError:
                raise PipelineError(
                    "A lab-only port is occupied; do not reuse an existing service"
                ) from None
    if subprocess.check_output(
        ["git", "diff", "HEAD", "--name-only", "--", "student-web", "security-web"], cwd=REPO_ROOT
    ):
        raise PipelineError("Protected source is modified; review before exporting the lab fixture")
    output.mkdir(mode=0o700)
    capture_id = uuid.uuid4().hex
    marker = {
        "purpose": "ai-pretrain-disposable",
        "capture_id": capture_id,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "edge_port": 18881,
        "backend_port": 18880,
        "database_port": 55435,
        "database_container": "idps-ai-pretrain-" + capture_id[:10],
        "nginx_binary": str(nginx_bin),
        "query_view": "Lab-only Nginx native JSON with scripted non-sensitive query values; production masks query; deployment availability requires review",
        "sensor_capture": "NOT_RUN: this lab does not capture packet sockets; EVE is not fabricated",
        "processes": {},
    }
    atomic_json(output / "owned-lab.json", marker)
    try:
        archive = subprocess.check_output(
            ["git", "archive", "HEAD", "student-web/backend"], cwd=REPO_ROOT
        )
        source = output / "build-source"
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(source, filter="data")
        with (output / "build.log").open("wb") as log:
            subprocess.run(
                ["./mvnw", "-q", "-DskipTests", "package"],
                cwd=source / "student-web/backend",
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=True,
            )
        jar = source / "student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar"
        marker["jar_sha256"] = file_sha256(jar)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                marker["database_container"],
                "--label",
                "idps.owner=ai-pretrain",
                "--cpus",
                "1",
                "--memory",
                "512m",
                "-e",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e",
                "POSTGRES_DB=ai_student_lab",
                "-p",
                "127.0.0.1:55435:5432",
                "postgres:17-alpine",
            ],
            check=True,
            capture_output=True,
        )
        producer_key = secrets.token_hex(32)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                (
                    "DB_",
                    "SPRING_",
                    "SERVER_",
                    "MAIL_",
                    "BOOTSTRAP_",
                    "STUDENT_",
                    "TRUSTED_",
                    "SESSION_",
                    "PASSWORD_",
                    "PUBLIC_APP_",
                    "AUDIT_",
                )
            )
        }
        env.update(
            DB_URL="jdbc:postgresql://127.0.0.1:55435/ai_student_lab",
            DB_USERNAME="postgres",
            DB_PASSWORD="",
            SERVER_PORT="18880",
            STUDENT_BIND_ADDRESS="127.0.0.1",
            STUDENT_AUDIT_LOG_PATH=str(output / "student-audit.log"),
            STUDENT_AUDIT_HMAC_KEY=producer_key,
            STUDENT_SOURCE_INSTANCE="ai-isolated-" + capture_id,
            TRUSTED_PROXIES="127.0.0.0/8",
            AUDIT_INCLUDE_SUCCESSFUL_READS="true",
            AUDIT_RETENTION_ENABLED="false",
            BOOTSTRAP_ADMIN_ENABLED="false",
            PASSWORD_RESET_MAIL_ENABLED="false",
            JAVA_TOOL_OPTIONS="-Xms128m -Xmx512m -XX:ActiveProcessorCount=2",
        )
        time.sleep(2)
        with (output / "student.log").open("wb") as log:
            process = subprocess.Popen(
                ["java", "-jar", str(jar)],
                cwd=output,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        marker["processes"]["student"] = {
            "pid": process.pid,
            "create_time": psutil.Process(process.pid).create_time(),
        }
        atomic_json(output / "owned-lab.json", marker)
        for _ in range(90):
            if process.poll() is not None:
                raise PipelineError("Isolated Student startup failed; inspect private log")
            try:
                with socket.create_connection(("127.0.0.1", 18880), timeout=0.3):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise PipelineError("Isolated Student startup timeout")
        password = secrets.token_urlsafe(24)
        atomic_json(output / "accounts-private.json", {"password": password})
        sql = "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n" + "\n".join(
            f"INSERT INTO users(username,role,password_hash,password_setup_required,enabled,created_at,updated_at) VALUES('ai_lab_{i:02d}','{role}',crypt('{password}',gen_salt('bf',10)),false,true,now(),now());"
            for i, role in enumerate(ROLES)
        )
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                marker["database_container"],
                "psql",
                "-U",
                "postgres",
                "-d",
                "ai_student_lab",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=sql,
            text=True,
            capture_output=True,
            check=True,
        )
        fragment = (REPO_ROOT / "security-web/nginx/pbl4-proxy.conf").read_text()
        marker["nginx_template_sha256"] = file_sha256(
            REPO_ROOT / "security-web/nginx/pbl4-proxy.conf"
        )
        fragment = (
            fragment.replace("127.0.0.1:8080", "127.0.0.1:18880")
            .replace("127.0.0.1:5173", "127.0.0.1:18880")
            .replace("    server 192.168.20.10:80 backup;", "")
            .replace("listen 0.0.0.0:80;", "listen 127.0.0.1:18881;")
            .replace("/var/log/nginx/access.log", str(output / "access.log"))
        )
        start = fragment.index("log_format idps_json")
        end = fragment.index("\n\n", start)
        raw = (
            fragment[start:end]
            .replace("log_format idps_json", "log_format idps_lab")
            .replace('"query_string":null', '"query_string":"$args"')
        )
        fragment = fragment[:end] + "\n\n" + raw + fragment[end:]
        fragment = fragment.replace(
            "access_log " + str(output / "access.log") + " idps_json;",
            "access_log "
            + str(output / "access.log")
            + " idps_json;\naccess_log "
            + str(output / "access-lab.log")
            + " idps_lab;",
        )
        config = (
            "worker_processes 1;\npid "
            + str(output / "nginx.pid")
            + ";\nerror_log "
            + str(output / "nginx-error.log")
            + " warn;\nevents {worker_connections 128;}\nhttp {\n"
            + "".join(
                name + "_temp_path " + str(output / (name + "-temp")) + ";\n"
                for name in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
            )
            + fragment
            + "\n}\n"
        )
        (output / "nginx.conf").write_text(config)
        subprocess.run(
            [str(nginx_bin), "-p", str(output) + "/", "-c", str(output / "nginx.conf")],
            check=True,
            capture_output=True,
        )
        pid = int((output / "nginx.pid").read_text())
        marker["processes"]["nginx"] = {
            "pid": pid,
            "create_time": psutil.Process(pid).create_time(),
        }
        atomic_json(output / "owned-lab.json", marker)
        response, _ = LabClient(18881, "127.0.0.250").request("GET", "/api/auth/csrf")
        if response["status_code"] != 200:
            raise PipelineError("Lab readiness request failed")
        return {k: v for k, v in marker.items() if k != "processes"}
    except (Exception, KeyboardInterrupt):
        atomic_json(output / "owned-lab.json", marker)
        stop_lab(output)
        raise PipelineError(
            "AI-owned lab setup failed; only its private logs/artifacts were retained"
        ) from None


def stop_lab(directory):
    directory = Path(directory).resolve()
    marker = load_json(directory / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable":
        raise PipelineError("Refusing to stop an unowned lab")
    results = {}
    for name, identity in sorted(
        marker.get("processes", {}).items(), key=lambda item: item[0] != "sensor_namespace"
    ):
        try:
            process = psutil.Process(identity["pid"])
            if process.create_time() != identity["create_time"] or str(directory) not in " ".join(
                process.cmdline()
            ):
                raise PipelineError("Lab process identity changed; refusing to signal it")
            process.send_signal(signal.SIGQUIT if name == "nginx" else signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except psutil.TimeoutExpired:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    raise PipelineError("Lab process did not stop gracefully") from None
            results[name] = "stopped"
        except psutil.NoSuchProcess:
            results[name] = "already_stopped"
    container = marker.get("database_container", "")
    if not container.startswith("idps-ai-pretrain-"):
        raise PipelineError("Refusing to stop an unowned DB container")
    inspect = subprocess.run(
        ["docker", "inspect", "--format", '{{ index .Config.Labels "idps.owner" }}', container],
        capture_output=True,
        text=True,
    )
    if inspect.returncode == 0:
        if inspect.stdout.strip() not in ("ai-pretrain", "ai-pretrain-20261027"):
            raise PipelineError("Container ownership label mismatch")
        subprocess.run(["docker", "stop", container], check=True, capture_output=True, timeout=30)
        results["database"] = "stopped"
    else:
        results["database"] = "already_stopped"
    atomic_json(directory / "cleanup.json", results)
    return results
