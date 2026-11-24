#!/bin/bash
# Run as root on the named endpoint. The coordinator exchanges only public files.
set -Eeuo pipefail
umask 077
role=$1 op=$2
step=$op
trap 'rc=$?; printf "BLOCKED: %s/%s: %s (node.sh line %s, exit %s)\n" "$role" "$op" "$step" "$LINENO" "$rc" >&2; exit "$rc"' ERR
case $role in
  receiver) ip=192.168.20.1; eku=serverAuth; purpose=sslserver;;
  sender) ip=192.168.20.10; eku=clientAuth; purpose=sslclient;;
  *) exit 2;;
esac
base=/etc/pbl4/audit
state=/var/backups/pbl4-audit-mtls-$role
tls=$base/mtls
unit=pbl4-audit-$role
user=$(systemctl show "$unit" -p User --value)
[[ -n $user && $user != root ]]
conf=$base/$role.conf
stage=$base/$role.mtls-next.conf
testconf=$base/$role.mtls-test.conf
testdir=/var/lib/$unit/mtls-canary
bundle=$(dirname "$(realpath "$0")")
os() { openssl "$@"; }
asuser() { runuser -u "$user" -- "$@"; }
checkconf() { asuser /usr/sbin/rsyslogd -N1 -f "$1"; }
replace() { install -m0644 "$1" "$conf.next"; mv -T "$conf.next" "$conf"; }
case $op in
snapshot)
    systemctl is-active --quiet "$unit"
    systemctl show "$unit" -p ExecStart --value | grep -Fq -- "-f $conf"
    install -d -m0700 "$state"
    [[ ! -L $conf && -f $conf ]]
    if [[ ! -e $state/before.conf ]]; then
        [[ ! -e $tls ]] || { echo "Refusing to adopt an existing identity directory"; exit 1; }
        grep -qi 'tls="on"' "$conf" && { echo 'Existing TLS installation requires review'; exit 1; }
        cp -p "$conf" "$state/before.conf"
        systemctl cat "$unit" > "$state/unit.before"
    fi
    cmp -s "$state/before.conf" "$conf" || cmp -s "$stage" "$conf"
    dpkg-query -W rsyslog rsyslog-relp 'librelp0*'
    if [[ $role == receiver ]]; then
        nft list table inet pbl4_audit_transport >/dev/null
        /usr/local/libexec/pbl4-audit-guard
    fi
    ;;
csr)
    install -d -m0711 "$tls"
    if [[ ! -e $tls/$role.key ]]; then
        [[ ! -e $tls/$role.crt && ! -e $tls/$role.csr ]] || {
            echo "BLOCKED: $role identity exists but its private key is missing" >&2; exit 1;
        }
        os genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$tls/$role.key.tmp"
        mv -T "$tls/$role.key.tmp" "$tls/$role.key"
    fi
    # chmod 0600 would also clear the effective ACL mask on every retry.
    setfacl --set="u::rw-,u:$user:r--,g::---,m::r--,o::---" "$tls/$role.key"
    os req -new -key "$tls/$role.key" -subj "/CN=audit-$role.lab" -out "$tls/$role.csr"
    chmod 0644 "$tls/$role.csr"
    ;;
sign)
    [[ $role == receiver ]]
    ca=$state/issuer
    install -d -m0700 "$ca"
    if [[ ! -e $ca/ca.key && ! -e $ca/ca.crt ]]; then
        os req -new -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 1825 \
            -subj '/CN=WebSentinel Audit RELP CA' -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
            -addext 'keyUsage=critical,keyCertSign,cRLSign' -keyout "$ca/ca.key" -out "$ca/ca.crt"
    fi
    install -m0644 "$ca/ca.crt" "$tls/ca.crt"
    for end in receiver sender; do
        req=$tls/receiver.csr addr=192.168.20.1 use=serverAuth
        if [[ $end == sender ]]; then req=$bundle/sender.csr; addr=192.168.20.10; use=clientAuth; fi
        os req -in "$req" -noout -verify
        if [[ -e $tls/$end.crt ]]; then
            cmp <(os req -in "$req" -pubkey -noout) <(os x509 -in "$tls/$end.crt" -pubkey -noout)
            os verify -CAfile "$ca/ca.crt" -verify_hostname "audit-$end.lab" "$tls/$end.crt"
            continue
        fi
        printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'keyUsage=critical,digitalSignature' \
            "extendedKeyUsage=$use" "subjectAltName=DNS:audit-$end.lab,IP:$addr" > "$ca/leaf.ext"
        os x509 -req -in "$req" -CA "$ca/ca.crt" -CAkey "$ca/ca.key" -CAcreateserial -days 365 \
            -extfile "$ca/leaf.ext" -out "$tls/$end.crt.new"
        chmod 0644 "$tls/$end.crt.new"; mv -T "$tls/$end.crt.new" "$tls/$end.crt"
    done
    if [[ -s $tls/wrong-name.crt ]] && os x509 -in "$tls/wrong-name.crt" -noout -checkend 300 &&
       os verify -purpose sslclient -CAfile "$ca/ca.crt" -verify_hostname unapproved.audit.lab "$tls/wrong-name.crt" &&
       cmp <(os x509 -in "$tls/sender.crt" -pubkey -noout) <(os x509 -in "$tls/wrong-name.crt" -pubkey -noout); then
        exit 0
    fi
    # Valid CA and client EKU, deliberately unapproved DNS identity for the negative test.
    printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'keyUsage=critical,digitalSignature' 'extendedKeyUsage=clientAuth' 'subjectAltName=DNS:unapproved.audit.lab' > "$ca/probe.ext"
    os x509 -req -in "$bundle/sender.csr" -subj '/CN=unapproved.audit.lab' -CA "$ca/ca.crt" -CAkey "$ca/ca.key" -CAcreateserial -days 1 -extfile "$ca/probe.ext" -out "$tls/wrong-name.crt"
    chmod 0644 "$tls/wrong-name.crt"
    ;;
prepare)
    if [[ $role == sender ]]; then
        install -m0644 "$bundle/ca.crt" "$bundle/sender.crt" "$bundle/wrong-name.crt" "$tls/"
    fi
    step="verify certificate chain, SAN and EKU"
    os verify -purpose "$purpose" -verify_hostname "audit-$role.lab" -CAfile "$tls/ca.crt" "$tls/$role.crt"
    os verify -verify_ip "$ip" -CAfile "$tls/ca.crt" "$tls/$role.crt"
    step="check remaining certificate lifetime"
    os x509 -in "$tls/$role.crt" -noout -checkend 86400
    step="open and parse private key as $user"
    # pipefail propagates OpenSSL/runuser errors. Only public-key digests leave these pipes.
    key_digest=$(asuser openssl pkey -in "$tls/$role.key" -passin pass: -pubout -outform DER | sha256sum)
    step="extract public key from verified certificate"
    cert_digest=$(os x509 -in "$tls/$role.crt" -noout -pubkey | os pkey -pubin -outform DER | sha256sum)
    step="match service-readable private key to $role certificate"
    [[ $key_digest == "$cert_digest" ]]
    echo "PASS: $role certificate matches key read by $user"
    step="render TLS configs from the saved transport config"
    python3 "$bundle/config.py" "$role" "$state/before.conf" "$bundle/$role.conf" "$stage" "$testconf" "$testdir"
    chmod 0644 "$stage" "$testconf"
    step="install AppArmor rules for $role TLS files"
    profile=/etc/apparmor.d/usr.sbin.rsyslogd
    if [[ -e $profile ]]; then
        grep -Fq 'include if exists <rsyslog.d>' "$profile"
        printf '%s r,\n' "$stage" "$testconf" "$base/$role.rollback.conf" "$tls/ca.crt" "$tls/$role.crt" "$tls/$role.key" > /etc/apparmor.d/rsyslog.d/pbl4-audit-mtls-$role
        apparmor_parser -r "$profile"
    fi
    install -d -m0700 -o "$user" "$testdir"
    if [[ $role == sender ]]; then asuser touch "$testdir/input.log"; fi
    step="validate production candidate as $user"; checkconf "$stage"
    step="validate isolated canary as $user"; checkconf "$testconf"
    ;;
resume-check)
    cmp "$conf" "$state/before.conf"
    scratch=$(mktemp -d)
    trap 'rm -r -- "$scratch"' EXIT
    python3 "$bundle/config.py" "$role" "$state/before.conf" "$bundle/$role.conf" \
        "$scratch/site" "$scratch/canary" "$testdir"
    cmp "$scratch/site" "$stage"
    cmp "$scratch/canary" "$testconf"
    checkconf "$stage"; checkconf "$testconf"
    ;;
probe-free)
    sockets=$(ss -H -ltn 'sport = :32514')
    [[ -z $sockets ]] || { echo "$role: port 32514 already in use" >&2; exit 1; };;
probe-listening)
    [[ $role == receiver ]]
    pid=$(cat "$testdir/pid")
    [[ $pid =~ ^[0-9]+$ ]]
    for ((i=0;i<50;i++)); do
        sockets=$(ss -4 -Hltnp 'sport = :32514')
        if [[ $sockets == *"127.0.0.1:32514 "* && $sockets == *"pid=$pid,"* ]]; then exit 0; fi
        sleep .1
    done
    echo "Canary receiver pid=$pid did not bind 127.0.0.1:32514" >&2; exit 1;;
probe-diagnostics)
    if [[ -s $testdir/pid ]]; then
        pid=$(cat "$testdir/pid")
        if [[ $pid =~ ^[0-9]+$ ]]; then
            journalctl -b "_PID=$pid" --no-pager -n 40 | grep -Ei 'imrelp|omrelp|gnutls|handshake|permission denied|binding' | tail -12 || :
        fi
    fi
    ss -Hltn 'sport = :32514';;
probe-start)
    # An isolated queue, pid, input and output. Start under the same service user.
    [[ ! -e $testdir/pid ]]
    asuser /usr/sbin/rsyslogd -i "$testdir/pid" -f "$testconf"
    ;;
probe-stop)
    if [[ -e $testdir/pid ]]; then
        # Validate /proc as root, then signal as the service UID from a PID-1
        # launched helper. sudo alone inherits the terminal AppArmor profile.
        systemd-run --quiet --wait --pipe --collect --property=NoNewPrivileges=yes \
            /usr/bin/python3 -c '
import os, pwd, select, signal, stat, sys
from pathlib import Path

pidfile, config = map(Path, sys.argv[1:3])
account = pwd.getpwnam(sys.argv[3])
with os.fdopen(os.open(pidfile, os.O_RDONLY | os.O_NOFOLLOW)) as owned:
    info = os.fstat(owned.fileno())
    if not stat.S_ISREG(info.st_mode) or info.st_uid != account.pw_uid:
        sys.exit("Canary pidfile owner/type mismatch")
    pid = int(owned.read().strip())
if pid <= 1:
    sys.exit("Invalid canary PID")
fd = os.pidfd_open(pid)
proc = Path(f"/proc/{pid}")
exe = "/usr/sbin/rsyslogd"
expected = [exe, "-i", str(pidfile), "-f", str(config)]
if (proc.stat().st_uid != account.pw_uid or os.readlink(proc / "exe") != exe or
        (proc / "cmdline").read_bytes().split(b"\0") != [os.fsencode(x) for x in expected] + [b""]):
    sys.exit("Canary process identity mismatch; refusing SIGTERM")
watch = select.poll()
watch.register(fd, select.POLLIN)
os.setgroups([])
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
signal.pidfd_send_signal(fd, signal.SIGTERM)
if not watch.poll(120000):
    sys.exit("Canary process did not exit")
print(f"Canary exited PID={pid} signal_uid={os.geteuid()}")
' "$testdir/pid" "$testconf" "$user"
        [[ ! -e $testdir/pid ]] || { echo "Canary retained its pidfile" >&2; exit 1; }
    fi
    if [[ $role == receiver ]]; then
        sockets=$(ss -Hltn 'sport = :32514')
        [[ -z $sockets ]] || { echo "Canary port 32514 still occupied" >&2; exit 1; }
    fi
    ;;
probe-send) [[ $role == sender && $3 =~ ^[a-f0-9]{32}$ ]]; printf '{"schema_version":"1.0","source":"STUDENT_AUDIT","event_id":"%s"}\n' "$3" | asuser tee -a "$testdir/input.log" >/dev/null;;
probe-consumed)
    [[ $role == sender && $3 =~ ^[a-f0-9]{32}$ ]]
    # Disk queue writes may be buffered until graceful shutdown. Wait for imfile
    # to consume this specific append before asking the isolated sender to stop.
    python3 - "$testdir" "$3" <<'PYTHON'
import json
import sys
import time
from pathlib import Path
directory = Path(sys.argv[1])
source = directory / "input.log"
with source.open("rb") as stream:
    for line in stream:
        if json.loads(line).get("event_id") == sys.argv[2]:
            end = stream.tell()
            break
    else:
        sys.exit("Canary input record missing")
for _ in range(60):
    for path in directory.glob("imfile-state:*"):
        try:
            state = json.loads(path.read_bytes())
        except (FileNotFoundError, ValueError):
            continue
        if state.get("filename") == str(source) and state.get("curr_offs", -1) >= end:
            sys.exit(0)
    time.sleep(.5)
sys.exit("Canary imfile checkpoint did not reach appended JSON")
PYTHON
    ;;
probe-queued)
    [[ $role == sender && $3 =~ ^[a-f0-9]{32}$ && ! -e $testdir/pid ]]
    grep -aFql -- "$3" "$testdir"/student-forward.[0-9]* || {
        echo "Gracefully stopped sender did not persist canary JSON in disk queue" >&2; exit 1; };;
probe-check) [[ $role == receiver && $3 =~ ^[a-f0-9]{32}$ ]]
    for ((i=0;i<40;i++)); do
        if grep -Fxq "{\"schema_version\":\"1.0\",\"source\":\"STUDENT_AUDIT\",\"event_id\":\"$3\"}" "$testdir/output.log" 2>/dev/null; then exit 0; fi
        sleep .5
    done; echo "Exact canary JSON missing at receiver" >&2; exit 1;;
probe-tls) [[ $role == sender ]]; asuser python3 "$bundle/probe.py" "$tls" "${3:-32514}" "${4:-}";;
stop) systemctl stop "$unit"; test "$(systemctl show "$unit" -p Result --value)" = success;;
apply) cmp -s "$state/before.conf" "$conf" || cmp -s "$stage" "$conf"; checkconf "$stage"; replace "$stage"; systemctl start "$unit"; systemctl is-active --quiet "$unit";;
restore) cmp -s "$stage" "$conf" || cmp -s "$state/before.conf" "$conf"; install -m0644 "$state/before.conf" "$base/$role.rollback.conf"; checkconf "$base/$role.rollback.conf"; cp -p "$state/before.conf" "$conf.next"; mv -T "$conf.next" "$conf"; systemctl start "$unit"; systemctl is-active --quiet "$unit";;
assert-live)
    step="confirm active dedicated unit uses the accepted TLS config"
    systemctl is-active --quiet "$unit"
    cmp "$stage" "$conf"
    pid=$(systemctl show "$unit" -p MainPID --value)
    [[ $pid =~ ^[1-9][0-9]*$ ]]
    grep -zFxq -- "$conf" "/proc/$pid/cmdline"
    echo "PASS: $unit active, PID=$pid, configured=mTLS"
    ;;
status) systemctl show "$unit" -p ActiveState -p SubState -p MainPID; if grep -q 'tls="on"' "$conf"; then echo 'configured=mTLS'; else echo 'configured=plaintext'; fi;;
digest)
    [[ $3 =~ ^[a-f0-9]{32}$ ]]
    file=/var/log/pbl4/student-audit.log
    if [[ $role == sender ]]; then file=/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log; fi
    python3 "$bundle/digest.py" "$file" "$3";;
*) exit 2;;
esac
