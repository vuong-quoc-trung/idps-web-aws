"""Read-only access to the existing security-web PostgreSQL container."""
import json
import subprocess

CONTAINER = "pbl4-postgres"
EXEC = ["docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on", CONTAINER]


def endpoint():
    # Inspect only non-secret fields. Never read Config.Env.
    fmt = '{{json (index .NetworkSettings.Ports "5432/tcp")}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}}'
    bindings, project, service = subprocess.check_output(
        ["docker", "inspect", "--format", fmt, CONTAINER], text=True
    ).strip().rsplit(" ", 2)
    ports = json.loads(bindings)
    if (project, service) != ("security-web", "postgres") or not ports or len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
        raise ValueError("Expected security-web/postgres published exclusively on IPv4 loopback")
    version = subprocess.check_output(EXEC + ["psql", "-XAt", "-U", "pbl4", "-d", "postgres",
                                      "-c", "SHOW server_version_num"], text=True)
    if int(version) // 10000 != 17:
        raise ValueError("Expected PostgreSQL 17")
    for tool in ("pg_dump", "pg_restore"):
        subprocess.run(EXEC + [tool, "--version"], check=True, stdout=subprocess.DEVNULL)
    return int(ports[0]["HostPort"])


def read_archive(archive, entry=None):
    # Archive arrives on stdin. fd 3 carries exactly one pg_restore TOC selection.
    cmd = ["pg_restore", "--list"] if entry is None else [
        "sh", "-ec", 'exec pg_restore -L /dev/fd/3 -f - 3<<EOF\n$1\nEOF',
        "restore", entry.decode("utf-8")]
    with open(archive, "rb") as stream:
        return subprocess.check_output(["docker", "exec", "-i", CONTAINER, *cmd], stdin=stream)


if __name__ == "__main__":
    print(endpoint())
