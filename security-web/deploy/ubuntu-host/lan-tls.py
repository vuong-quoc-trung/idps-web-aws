"""Provision the dedicated LAN identity without rotating existing lab trust."""
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile

DNS = "security.lab"
IP = "192.168.1.13"
LOCAL = Path.home() / ".local/share/websentinel/edge-lan-pki"
LIVE = Path("/etc/ws-native/lan-tls")
FILES = ("ca.crt", "edge.crt", "edge.key")


def openssl(directory, *args):
    subprocess.run(["openssl", *args], cwd=directory, check=True, stdout=subprocess.DEVNULL)


def verify(directory):
    for option, identity in (("-verify_hostname", DNS), ("-verify_ip", IP)):
        openssl(directory, "verify", "-purpose", "sslserver", option, identity, "-CAfile", "ca.crt", "edge.crt")
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(directory/"edge.crt", directory/"edge.key")


def provision(dest, payload=None):
    dest.parent.mkdir(exist_ok=True, parents=True)
    if dest.is_symlink():
        raise ValueError("Unexpected PKI symlink")
    if not dest.exists():
        stage = Path(tempfile.mkdtemp(dir=dest.parent))
        try:
            if payload is None:
                openssl(stage, "req","-new","-x509","-newkey","ec","-pkeyopt","ec_paramgen_curve:P-256","-nodes",
                        "-sha256","-days","730","-subj","/CN=WebSentinel Native LAN Lab CA",
                        "-addext","basicConstraints=critical,CA:TRUE,pathlen:0","-addext","keyUsage=critical,keyCertSign,cRLSign",
                        "-keyout","ca.key","-out","ca.crt")
                openssl(stage,"req","-new","-newkey","ec","-pkeyopt","ec_paramgen_curve:P-256","-nodes",
                        "-subj","/CN="+DNS,"-keyout","edge.key","-out","edge.csr")
                ext = stage/"extensions"
                ext.write_text(f"subjectAltName=DNS:{DNS},IP:{IP}\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n")
                openssl(stage,"x509","-req","-in","edge.csr","-CA","ca.crt","-CAkey","ca.key","-CAcreateserial",
                        "-sha256","-days","365","-extfile",str(ext),"-out","edge.crt")
                for file in ("edge.csr","extensions","ca.srl"):
                    (stage/file).unlink()
            else:
                for file in FILES:
                    (stage/file).write_text(payload[file])
            for file in stage.iterdir():
                file.chmod(0o600 if file.suffix==".key" else 0o644)
            verify(stage)
            stage.rename(dest)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    verify(dest)
    if payload and any((dest/f).read_text()!=payload[f] for f in FILES):
        raise ValueError("Installed LAN identity differs; dedicated PKI was preserved")


if __name__ == "__main__":
    os.umask(0o077)
    if sys.argv[1:] == ["install"] and os.geteuid()==0:
        provision(LIVE,json.loads(sys.stdin.buffer.read(32768)))
    elif sys.argv[1:] in (["prepare"],["install-host"]) and os.geteuid()!=0:
        provision(LOCAL)
        if sys.argv[1]=="install-host":
            subprocess.run(["sudo","python3","-IB",__file__,"install"],check=True,
                           input=json.dumps({f:(LOCAL/f).read_text() for f in FILES}),text=True)
    else:
        sys.exit("Run as the Host operator: prepare or install-host")
