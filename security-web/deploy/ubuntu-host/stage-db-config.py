"""First install only, after install-first. Run as root; never print secrets."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

from docker_pg import endpoint

def main(state):
    os.umask(0o077)
    if os.getuid() != 0 or endpoint() != 5433:
        raise ValueError("Expected approved native host and database endpoint")
    etc = Path("/etc/ws-native")
    names = ("security", "student")
    roles = ["ws_native_"+name for name in names]
    spec = json.loads((state/"db-acceptance.json").read_text())
    if spec["suffix"] != "accept01" or Path(spec["backup"]) != state/"backup":
        raise ValueError("Unexpected restore manifest")
    dest = Path("/var/backups/ws-native-db-accept01")
    envs = [(etc/(name+".env")).read_text() for name in names]
    passwords = [(state/(role+".password")).read_text().strip() for role in roles]
    if not all(re.fullmatch("[0-9a-f]{64}", pw) for pw in passwords):
        raise ValueError("Unexpected credential format")
    url = "postgresql://ws_native_security@127.0.0.1:5433/ws_native_security"
    if envs[0].count("DATABASE_URL="+url+"\n") != 1 or "DB_PASSWORD=" in envs[1]:
        raise ValueError("Expected unused first-install configuration")
    if (etc/"db-acceptance.json").exists() or (etc/"dashboard.password").exists():
        raise ValueError("Existing acceptance or dashboard credentials")
    dest.mkdir(mode=0o700)
    for role in roles:
        target = dest/(role+".dump")
        shutil.copyfile(state/"backup"/target.name,target)
        with target.open("rb") as f:
            if hashlib.file_digest(f,"sha256").hexdigest()!=spec["sha256"][role]:
                raise ValueError("Backup digest mismatch")
    spec["backup"] = str(dest)
    password=secrets.token_urlsafe(32)
    hashed=subprocess.check_output(["/opt/ws-native/current/security/pbl4-security-demo","--hash-password"],input=password,text=True).strip()
    (etc/"dashboard.password").write_text(password+"\n")
    envs[0]=envs[0].replace(url,url.replace("@",":"+passwords[0]+"@"))+"ADMIN_PASSWORD_HASH='"+hashed+"'\n"
    envs[1]+="DB_PASSWORD="+passwords[1]+"\n"
    for name,content in zip(names,envs):
        (etc/(name+".env")).write_text(content)
    (etc/"db-acceptance.json").write_text(json.dumps(spec)+"\n")
    subprocess.run(["bash","/opt/ws-native/current/control.sh","verify-db"],check=True)
    print("Runtime DB configuration accepted; no services started")

if __name__=="__main__":
    main(Path(sys.argv[1]).resolve(strict=True))
