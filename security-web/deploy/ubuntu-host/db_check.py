"""Require exact schema and logical backup/restore on the dedicated native PG cluster."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from docker_pg import EXEC, endpoint, read_archive
from restore_compare import compare_objects
from restore_fingerprint import fingerprint


def main():
    root=Path(__file__).resolve().parent
    conf=Path("/etc/ws-native/db-acceptance.json")
    if conf.resolve()!=conf or conf.stat().st_uid or conf.stat().st_mode & 0o022:
        raise ValueError("Untrusted native DB acceptance config")
    # Validate the actual service targets before allowing their startup migrations.
    port = endpoint()
    for name,key,db in (("student","DB_URL","ws_native_student"),("security","DATABASE_URL","ws_native_security")):
        envfile=Path("/etc/ws-native")/(name+".env")
        if envfile.resolve()!=envfile or envfile.stat().st_uid or envfile.stat().st_mode & 0o077:
            raise ValueError("Unsafe service environment file: "+name)
        values=[line.split("=",1)[1] for line in envfile.read_text().splitlines() if line.startswith(key+"=")]
        if len(values)!=1:
            raise ValueError("Missing or repeated DB target for "+name)
        url=urlsplit(values[0].removeprefix("jdbc:"))
        if (name=="security" and url.username!=db) or (name=="student" and (url.username is not None or [line for line in envfile.read_text().splitlines() if line.startswith("DB_USERNAME=")] != ["DB_USERNAME="+db])):
            raise ValueError("Unexpected application role: "+name)
        if (url.scheme not in ("postgresql","postgres") or url.hostname!="127.0.0.1"
                or url.port!=port or url.path!="/"+db or url.query or url.fragment):
            raise ValueError("Refusing unexpected database target for "+name)
    verify_backup(root, json.loads(conf.read_text()))


def verify_backup(root, spec):
    backup=Path(spec["backup"])
    if not backup.is_absolute() or backup.resolve()!=backup or not re.fullmatch("[a-z][a-z0-9_]{2,18}",spec["suffix"]):
        raise ValueError("Invalid backup path or restore suffix")
    pg = EXEC
    for db,expected,query in [
        ("ws_native_security","migrations.expected","SELECT version,encode(checksum,'hex'),success FROM _sqlx_migrations"),
        ("ws_native_student","flyway.expected","SELECT version,checksum,success FROM flyway_schema_history")]:
        role_check = """SELECT d.datname FROM pg_database d JOIN pg_roles r ON d.datdba=r.oid
            WHERE d.datname=current_database() AND r.rolname=current_database()
            AND r.rolcanlogin AND NOT (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
            OR r.rolreplication OR r.rolbypassrls)
            AND NOT EXISTS (SELECT FROM pg_auth_members m WHERE m.member=r.oid)"""
        owner=subprocess.check_output(pg+["psql","-U","pbl4","-XAt","-v","ON_ERROR_STOP=1",
                                          "-d",db,"-c",role_check],text=True).strip()
        if owner != db:
            raise ValueError("Native database requires a dedicated unprivileged owner: "+db)
        wanted=sorted((root/expected).read_text().splitlines())
        targets=[db,db+"_"+spec["suffix"]]
        for target in targets:
            got=subprocess.check_output(pg+["psql","-U","pbl4","-XAt","-v","ON_ERROR_STOP=1","-d",target,"-c",query],text=True)
            if sorted(got.splitlines())!=wanted or not wanted:
                raise ValueError(f"Pending or mismatched migrations: {target}")
        archive=backup/(db+".dump")
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest()!=spec["sha256"][db]:
                raise ValueError("Backup checksum mismatch: "+db)
        with tempfile.TemporaryDirectory() as tmp:
            copy=Path(tmp)/"restore.dump"
            with copy.open("xb") as out:
                subprocess.run(pg+["pg_dump","-U","pbl4","-Fc","--lock-wait-timeout=5s","-d",targets[1]],stdout=out,check=True)
            errors=compare_objects(fingerprint(archive, read_archive),fingerprint(copy, read_archive))
            if errors:
                raise ValueError(f"{db}: "+", ".join(errors))
        print(db,"PASS schema and logical restore")


if __name__=="__main__":
    main()
