#!/bin/bash
# Native observation + optional, explicitly authorized 10-minute request lease window.
set -Eeuo pipefail
umask 077
mode=${1:-stage}
case $mode in continuous-enable|continuous-disable|continuous-status|continuous-check|stage|full|lan|lan-full|renew-full|ip-window|lan-rollback|status|rollback) ;; *) exit 2;; esac
src=$(dirname "$(realpath "$0")")
repo=$(realpath "$src/../../..")
if [[ $mode == lan || $mode == lan-full ]]; then
    window=ip-window
    if [[ $mode == lan-full ]]; then window=full; fi
    shift
    [[ $EUID != 0 ]] || { echo "Run as the normal Host operator."; exit 1; }
    (cd "$repo/security-web" && cargo build --offline --release --features dev-hybrid-review)
    python3 -IB "$src/lan-tls.py" install-host
    sudo flock -n /run/lock/ws-native-auto python3 -EB "$src/lan-cutover.py" prepare "$@"
    if ! sudo bash "$src/native-auto.sh" "$window"; then
        sudo flock -n /run/lock/ws-native-auto python3 -EB "$src/lan-cutover.py" rollback
        exit 1
    fi
    exit
fi
if [[ $mode == renew-full ]]; then
    sudo test -f /etc/ws-native/direct-peer.json || { echo "Missing installed LAN scope"; exit 1; }
    (cd "$repo/security-web" && cargo build --offline --release --features dev-hybrid-review)
    exec sudo bash "$src/native-auto.sh" full
fi
if ((EUID!=0)); then
    if [[ $mode == full ]] && ! bash "$src/prepare-vm-leases.sh" --digest | sudo cmp -s - /etc/ws-native/vm-lease-transport-prepared; then
        echo "Prepare SSH lease transport and VM sources (no backend restart)? Type PREPARE-VM:"
        read -r prepare </dev/tty
        [[ $prepare == PREPARE-VM ]] || exit 1
        bash "$src/prepare-vm-leases.sh"
        echo "Restart Student backend in its existing VM terminal with the printed environment. Type VM-READY to continue:"
        read -r prepared </dev/tty
        [[ $prepared == VM-READY ]] || exit 1
    fi
    if [[ $mode == stage || $mode == full ]]; then (cd "$repo/security-web" && cargo build --offline --release --features dev-hybrid-review); fi
    exec sudo bash "$src/native-auto.sh" "$mode"
fi
live=/opt/ws-native/current
fix=/opt/ws-native/runtime-fix
etc=/etc/ws-native
units=/etc/systemd/system
ip_readiness() {
    for unit in ws-native-edge.service ws-native-plan.socket ws-native-peer.socket ws-native-peer-plan.socket; do
        systemctl is-active --quiet "$unit" || { echo "BLOCKED readiness: $unit inactive" >&2; return 1; }
    done
    if [[ ${1:-} != before-worker ]]; then
        systemctl is-active --quiet ws-native-worker.timer || { echo "BLOCKED readiness: worker timer inactive" >&2; return 1; }
        [[ $(systemctl show ws-native-worker.service -p Result --value) == success ]] || { echo "BLOCKED readiness: ws-native-worker.service failed" >&2; return 1; }
    fi
    runuser -u ws-native-actuator -- python3 -IB - <<'PY_READY'
import json, socket, sys
from pathlib import Path
sys.path.insert(0, "/opt/ws-native/runtime-fix")
from direct_peer import CONFIG, check_listener_name
try:
    # Resolve via Host NSS outside the network-restricted nftables actuator.
    check_listener_name(json.loads(CONFIG.read_bytes()))
except (KeyError, ValueError, OSError) as exc:
    raise SystemExit(f"BLOCKED readiness: listener DNS: {exc}") from None
try:
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(15)
        s.connect("/run/ws-native-peer.sock")
        s.sendall(b'{"op":"readiness"}')
        s.shutdown(socket.SHUT_WR)
        reply = s.makefile("rb").read(513)
except OSError as exc:
    raise SystemExit(f"BLOCKED readiness: /run/ws-native-peer.sock: {exc}") from None
if reply == b"READY\n":
    raise SystemExit(0)
if not reply:
    raise SystemExit("BLOCKED readiness: actuator closed without a response; see ws-native-peer@ instance journal")
elif len(reply) <= 512 and reply.startswith(b"ERROR ") and reply.endswith(b"\n") and reply[6:-1].isascii() and all(32 <= c < 127 for c in reply[6:-1]):
    raise SystemExit("BLOCKED readiness: " + reply[6:-1].decode("ascii"))
else:
    raise SystemExit("BLOCKED readiness: malformed actuator response; see instance journal")
PY_READY
}
if [[ $mode == continuous-check ]]; then
    python3 -B "$fix/continuous.py" check
    for unit in ws-native-security ws-native-edge ws-native-sensor ws-native-scorer ws-native-gate; do
        systemctl is-active --quiet "$unit" || { echo "BLOCKED: $unit inactive"; exit 1; }
    done
    runuser -u ws-native-actuator -- python3 -IB -c "exec(__import__('sys').stdin.read());deliver('ready')" < "$fix/vm_transport.py"
    test "$(curl --noproxy '*' --resolve student.lab:443:192.168.20.10 --cacert "$etc/student-ca.crt" --max-time 5 -sS -o /dev/null -w '%{http_code}' https://student.lab/api/auth/me)" = 401
    ip_readiness before-worker
    exit
fi
if [[ $mode == status || $mode == continuous-status ]]; then
    if [[ $mode == continuous-status ]]; then
        systemctl show ws-native-continuous.service ws-native-worker.timer -p Id -p ActiveState -p Result
        if runuser -u ws-native-actuator -- python3 -IB -c "exec(__import__('sys').stdin.read());deliver('ready')" < "$fix/vm_transport.py"; then
            echo "Student VM receiver: READY (SSH)"
        else
            echo "Student VM receiver: UNAVAILABLE"
        fi
        if [[ ! -f $etc/approval.json ]] || ! python3 -c 'import sys,json; sys.exit(json.load(open(sys.argv[1])).get("mode")!="CONTINUOUS")' "$etc/approval.json"; then
            echo "CONTINUOUS OFF: BLOCK_REQUEST, BLOCK_SESSION, BLOCK_ACCOUNT, BLOCK_IP"
            exit 0
        fi
        python3 -B "$fix/continuous.py" outcomes
    fi
    for unit in ws-native-edge.service ws-native-plan.socket ws-native-worker.timer; do
        systemctl show "$unit" -p Id -p LoadState -p ActiveState -p SubState
    done
    ip_ready=no
    if [[ -f $etc/direct-peer.json ]] && ip_readiness; then ip_ready=yes; fi
    python3 - "$etc/approval.json" "$ip_ready" <<'PY_STATUS'
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
actions = {}
if path.exists():
    policy = json.loads(path.read_bytes())
    if policy.get("mode") == "CONTINUOUS":
        sys.path.insert(0, "/opt/ws-native/runtime-fix")
        from native_policy import current, require_ready
        import sqlite3
        try:
            require_ready(current())
            with sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro",uri=True) as db:
                if db.execute("select stopped from control").fetchall() != [(0,)]:
                    raise ValueError("emergency stop latched")
        except (OSError,ValueError,sqlite3.Error) as exc:
            print(f"CONTINUOUS BLOCKED: {exc}")
            for action in policy["actions"]:
                print(action, "BLOCKED")
            sys.exit(1)
        print("CONTINUOUS authorized; no authorization deadline")
        actions = policy["actions"]
    elif policy["start"] <= time.time() < policy["end"] <= policy["start"] + 600:
        actions = policy["actions"]
print("BLOCK_REQUEST:", "authorized window; execution unverified" if "BLOCK_REQUEST" in actions else "no current authorization")
for action in ("BLOCK_SESSION","BLOCK_ACCOUNT"):
    print(action, "authorized window; VM enforcement unverified" if action in actions else "no current authorization")
print("BLOCK_IP:", ("ACTIVE; awaiting qualifying evidence" if sys.argv[2]=="yes" else "BLOCKED; readiness failed") if "BLOCK_IP" in actions else "LOCKED; no direct-peer authorization")
scope_path=Path("/etc/ws-native/direct-peer.json")
if scope_path.exists():
    import ipaddress,subprocess
    target=str(ipaddress.IPv4Address(json.loads(scope_path.read_bytes())["exclusive_lab_peer"]))
    result=subprocess.run(["/usr/sbin/nft","get","element","inet","ws_native_lab_peer","edge_peers","{",target,"}"],capture_output=True,timeout=3)
    print("Kernel element",target, "PRESENT" if result.returncode==0 else "ABSENT" if b"No such file or directory" in result.stderr else "UNKNOWN")
if path.exists():
    import sqlite3
    with sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro",uri=True) as journal:
        for action in policy["actions"]:
            receipts=journal.execute("SELECT outcome,count(distinct rid) FROM audit WHERE at>=? AND action=? GROUP BY outcome",(policy["start"],action)).fetchall()
            print(action,"journal outcomes:",dict(receipts))
PY_STATUS
    exit 0
fi
exec 9>/run/lock/ws-native-auto
flock -n 9
stop_if_running() {
    local unit
    for unit in "$@"; do
        if [[ $(systemctl show "$unit" -p LoadState --value) == loaded ]] &&
           [[ $(systemctl show "$unit" -p ActiveState --value) != inactive ]]; then
            systemctl stop "$unit"
        fi
    done
}
stop_worker() {
    stop_if_running ws-native-worker.timer ws-native-worker.service
    if [[ -f $etc/approval.json ]]; then mv -T "$etc/approval.json" "$etc/approval.revoked.$(date +%s%N).json"; fi
    local worker="$fix/worker.py"
    [[ -f $worker ]] || worker="$live/worker.py"
    runuser -u ws-native-actuator -g ws-native-evidence -- python3 -B "$worker" stop
}
case "$mode" in
continuous-enable|continuous-disable)
    exec bash "$src/continuous.sh" "$mode" ;;
esac
if [[ -f $etc/approval.json ]] && python3 -c 'import json,sys;sys.exit(json.load(open(sys.argv[1])).get("mode")!="CONTINUOUS")' "$etc/approval.json"; then
    echo "Use continuous-disable before changing the approved scope." >&2
    exit 1
fi
if [[ $mode == lan-rollback ]]; then
    if [[ -e $etc/approval.json ]]; then
        # Pause publication until the IP capability is removed. Preserve all other grants and deadlines.
        timer_was=$(systemctl is-active ws-native-worker.timer || :)
        stop_if_running ws-native-worker.timer ws-native-worker.service
        python3 - "$etc/approval.json" <<'PY_REMOVE'
import json,os,sys,tempfile
from pathlib import Path
p=Path(sys.argv[1])
policy=json.loads(p.read_bytes())
policy["actions"].pop("BLOCK_IP",None)
with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as out:
    out.write(json.dumps(policy).encode()); out.flush(); os.fsync(out.fileno()); os.fchmod(out.fileno(),0o644)
os.replace(out.name,p)
PY_REMOVE
        if [[ $timer_was == active ]]; then systemctl start ws-native-worker.timer; fi
    fi
    stop_if_running ws-native-peer.socket ws-native-peer-plan.socket
    python3 -EB "$src/lan-cutover.py" rollback
    exit
fi
ip_only=false
if [[ $mode == ip-window ]]; then
    [[ -f $etc/direct-peer.json && -d $etc/lan-cutover ]] || exit 1
    ip_only=true
    mode=full
fi
if [[ $mode == rollback ]]; then
    stop_worker
    stop_if_running ws-native-peer.socket ws-native-peer-plan.socket
    python3 -EB "$src/lan-cutover.py" rollback
    systemctl stop ws-native-edge
    exit
fi
if [[ -e "$etc/approval.json" && $mode == full ]]; then
    python3 - "$etc/approval.json" <<'PY_WINDOW'
import json,sys,time
from pathlib import Path
existing=json.loads(Path(sys.argv[1]).read_text())
if existing["actions"] and existing["end"] > time.time():
    sys.exit("BLOCKED: authorization still active; wait for expiry or explicitly rollback")
PY_WINDOW
elif [[ -e "$etc/approval.json" ]]; then
    echo "Existing authorization: observing only; expiry will not be extended."
    exec python3 -B "$src/observe-request-block.py"
fi
direct=locked
if [[ $mode == full ]]; then
    if [[ -e $etc/direct-peer.json ]]; then
        # Only consider an explicitly provisioned direct listener and dedicated nft table.
        python3 -B -c 'import sys; sys.path.insert(0,sys.argv[1]); from direct_peer import scope,LEDGER,check_table; import subprocess; c=scope(require_neighbor=False); check_table(c,subprocess.check_output(["/usr/sbin/nft","-st","list","table","inet","ws_native_lab_peer"])); print("Dedicated test peer:",c["exclusive_lab_peer"],"interface:",c["interface"],"listener:",c["listener_ip"],"TCP/24443"); sys.exit(0 if LEDGER.is_file() else "BLOCKED: missing direct Edge ledger")' "$src"
        direct=enabled
        echo "IP scope: approved direct peer on the lab listener TCP/24443, 10 independent operations, TTL 15s. Type APPROVE-DIRECT-LAB-PEER:"
        read -r ip_approval </dev/tty
        [[ $ip_approval == APPROVE-DIRECT-LAB-PEER ]] || exit 1
    fi
    if ! "$ip_only"; then
    echo "Checking pinned Student VM SSH receiver. Missing setup: run prepare-vm-leases.sh on Host." >&2
    runuser -u ws-native-actuator -- python3 -IB -c "exec(__import__('sys').stdin.read());print(deliver('ready'))" < "$src/vm_transport.py"
    echo "600s lab authorization: request /api/users 3 operations/15s TTL; session APP-1016 5/30s; account APP-1014 8/60s. Request APP-1012/1013, 60s window/cooldown. VM lab identities only. BLOCK_IP: $direct. Type APPROVE-NATIVE-LAB:"
    read -r answer </dev/tty
    [[ $answer == APPROVE-NATIVE-LAB ]] || exit 1
    fi
else
printf '%s\n' 'Cutover lab: start native Edge, manage only inet ws_native_egress on loopback, forward HTTPS to student.lab, and authorize BLOCK_REQUEST only on /api/users after real session verification. Rules APP-1012/1013: 3 independent operations / 60s; TTL 15s; cooldown 60s; authorization 600s. No session/account/IP ban. Type APPROVE-BLOCK-REQUEST:' >/dev/tty
read -r answer </dev/tty
[[ $answer == APPROVE-BLOCK-REQUEST ]] || { echo "No cutover"; exit 1; }
fi
if [[ $mode == full ]]; then
    if [[ -e $etc/approval.json ]]; then stop_worker; fi
    runuser -u ws-native-actuator -g ws-native-evidence -- python3 -B - <<'PY_REARM'
import sqlite3,time
from pathlib import Path
db=sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=rw",uri=True)
with db:
    db.execute("BEGIN IMMEDIATE")
    if db.execute("select count(*) from decisions where revoked=0 and json_extract(plan,'$.expires')>?",(int(time.time()),)).fetchone()[0]:
        raise SystemExit("BLOCKED: outstanding active lease")
    # Re-arm only a new, explicitly approved window; keep every consumed decision.
    if db.execute("select stopped from control").fetchall()==[(1,)]:
        db.execute("update control set stopped=0")
        db.execute("insert into audit(at,operator,action,rid,outcome) values(?,'operator','ALL','-','NEW_WINDOW_ARMED')",(int(time.time()),))
    for f in Path("/run/ws-native-leases").iterdir():
        if not f.is_file() or f.is_symlink(): raise SystemExit("Unexpected lease entry")
        row=db.execute("select plan from decisions where json_extract(plan,'$.selector')=? and json_extract(plan,'$.expires')<=? order by json_extract(plan,'$.expires') desc limit 1",(f.name,int(time.time()))).fetchone()
        import json
        if not row: raise SystemExit("Lease not attributable to expired decision")
        plan=json.loads(row[0])
        if f.read_text()!=f"{plan['request_id']} {plan['issued']} {plan['expires']}\n": raise SystemExit("Lease content mismatch")
        f.unlink()
PY_REARM
fi
grep -Fxq ENFORCEMENT_MODE=OFF "$etc/security.env"
grep -Fxq AUTO_BLOCK=false "$etc/security.env"
for u in ws-native-worker.timer ws-native-worker.service ws-native-student; do
    if systemctl is-active --quiet "$u"; then echo "BLOCKED: $u active"; exit 1; fi
done
# imrelp may leave rsyslog active after failing to bind during boot.
audit_listening() {
    ss -Hltnp 'sport = :2514' | awk -v pid="$(systemctl show pbl4-audit-receiver -p MainPID --value)" '$4=="192.168.20.1:2514" && index($0,"pid="pid","){found=1} END{exit !found}'
}
if ! audit_listening; then
    ip -o -4 addr show dev vmnet3 | grep -Eq ' inet 192[.]168[.]20[.]1/' || { echo 'BLOCKED: VMnet3 receiver address unavailable'; exit 1; }
    # Restart revalidates the existing guard; refuse to create a missing table.
    nft list table inet pbl4_audit_transport >/dev/null
    /usr/local/libexec/pbl4-audit-guard >/dev/null
    systemctl restart pbl4-audit-receiver
    for ((i=0;i<10;i++)); do if audit_listening; then break; fi; sleep 1; done
    audit_listening || { journalctl -u pbl4-audit-receiver -n 12 --no-pager >&2; exit 1; }
fi
for u in ws-native-scorer ws-native-gate; do systemctl is-active --quiet "$u"; done
test "$(systemctl show ws-native-security -p WorkingDirectory --value)" = "$fix"
grep -Fq 'proxy_pass https://192.168.20.10:443;' "$etc/nginx.conf"
grep -Fq 'proxy_ssl_verify on;' "$etc/nginx.conf"
grep -Fq 'proxy_ssl_name student.lab;' "$etc/nginx.conf"
if systemctl cat ws-native-edge | grep -Eq '^(Requires|Wants)=.*ws-native-student'; then exit 1; fi
test "$(curl --noproxy '*' --resolve student.lab:443:192.168.20.10 --cacert "$etc/student-ca.crt" --max-time 5 -sS -o /dev/null -w '%{http_code}' https://student.lab/api/auth/me)" = 401
# Refuse any unknown scope or leases, even for an already expired approval.
render=$(mktemp)
trap 'rm -f "$render"' EXIT
sed 's|__APPROVED_PATH__|/api/users|g' "$live/native-gated-location.template" >"$render"
if [[ -s $etc/approved-location.inc ]]; then cmp "$render" "$etc/approved-location.inc"; fi
test -z "$(find /run/ws-native-leases -type f -print -quit)"
runuser -u ws-native-actuator -- python3 -B - <<'PY'
import sqlite3
db=sqlite3.connect("file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro",uri=True)
assert db.execute("select stopped from control").fetchall()==[(0,)], "Emergency stop latched"
PY
backup=$(mktemp -d /var/backups/ws-native-auto.XXXXXXXX)
echo "Backup: $backup"
targets=("$etc/suricata.yaml" "$etc/approved-location.inc" "$fix/security" "$fix/worker.py" "$fix/vm_transport.py" "$fix/direct_peer.py" "$fix/ip-actuator.py" "$units/ws-native-peer.socket" "$units/ws-native-peer-plan.socket" "$units/ws-native-peer-plan@.service" "$units/ws-native-peer@.service" "$fix/approve_session.py" "$fix/native-plan.py" "$fix/native_policy.py" "$fix/request-policy.env" "$units/ws-native-security.service.d/80-request-policy.conf" "$units/ws-native-worker.service" "$units/ws-native-plan.socket" "$units/ws-native-plan@.service")
for p in "${targets[@]}"; do if [[ -f $p ]]; then cp -a --parents "$p" "$backup"; fi; done
edge_was=$(systemctl is-active ws-native-edge || :)
sensor_was=$(systemctl is-active ws-native-sensor || :)
plan_was=$(systemctl is-active ws-native-plan.socket || :)
security_accepted=false
armed=false
recover() {
    trap - ERR
    set +e
    if "$armed"; then stop_worker; fi
    stop_if_running ws-native-edge ws-native-plan.socket ws-native-peer.socket ws-native-peer-plan.socket
    for p in "${targets[@]}"; do
        case "$p" in "$fix/security"|"$fix/request-policy.env"|"$units/ws-native-security.service.d/80-request-policy.conf")
            if "$security_accepted"; then continue; fi ;;
        esac
        if [[ -f "$backup$p" ]] && cmp -s "$backup$p" "$p"; then continue; fi
        if [[ -f "$backup$p" ]]; then cp -a --remove-destination "$backup$p" "$p"; else rm -f -- "$p"; fi
    done
    systemctl daemon-reload
    # Never issue a second Rust start in the error path.
    if [[ $sensor_was == active ]]; then systemctl restart ws-native-sensor; else systemctl stop ws-native-sensor; fi
    if [[ $edge_was == active ]]; then systemctl start ws-native-edge; fi
    if [[ $plan_was == active ]]; then systemctl start ws-native-plan.socket; fi
    echo "Staging failed; inspect logs. Backup: $backup" >&2
    exit 1
}
trap 'if (( BASH_SUBSHELL == 0 )); then recover; fi' ERR
if ! head -1 "$etc/suricata.yaml" | grep -Fxq '%YAML 1.1'; then
    { printf '%%YAML 1.1\n---\n'; cat "$etc/suricata.yaml"; } > "$backup/candidate.yaml"
    install -m0644 "$backup/candidate.yaml" "$etc/suricata.yaml"
fi
candidate="$repo/security-web/target/release/pbl4-security-demo"
if ! cmp -s "$candidate" "$fix/security"; then
    install -m0755 "$candidate" "$fix/security.next"
    mv -T "$fix/security.next" "$fix/security"
fi
for f in native_policy.py native-plan.py worker.py vm_transport.py direct_peer.py ip-actuator.py; do install -m0644 "$src/$f" "$fix/$f"; done
install -m0644 "$src/../dev-i5/adaptive/approve_session.py" "$fix/approve_session.py"
install -m0644 "$src"/ws-native-plan{.socket,@.service} "$src/ws-native-worker.service" "$units/"
printf '%s\n' 'WS_DEV_HYBRID_MODE=REVIEW' 'WS_DEV_HYBRID_POLICY={"rules":[{"source":"STUDENT_AUDIT","rule":"APP-1012","weight":80,"standalone":false,"max_severity":2},{"source":"STUDENT_AUDIT","rule":"APP-1013","weight":80,"standalone":false,"max_severity":2}],"combined":200,"standalone":100,"fresh_seconds":60,"r37_weight":0}' > "$fix/request-policy.env"
if [[ $mode == full ]]; then
    python3 - "$fix/request-policy.env" <<'PY_RULES'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
head,raw=p.read_text().split("WS_DEV_HYBRID_POLICY=")
policy=json.loads(raw)
for rule,weight,standalone in [("APP-1016",80,False),("APP-1014",100,True)]:
    policy["rules"].append(dict(source="STUDENT_AUDIT",rule=rule,weight=weight,standalone=standalone,max_severity=1 if standalone else 2))
p.write_text(head+"WS_DEV_HYBRID_POLICY="+json.dumps(policy,separators=(",",":"))+"\n")
PY_RULES
fi
printf '[Service]\nEnvironmentFile=%s/request-policy.env\n' "$fix" >"$units/ws-native-security.service.d/80-request-policy.conf"
systemctl daemon-reload
security_matches() {
    local pid
    pid=$(systemctl show ws-native-security -p MainPID --value)
    [[ $pid -gt 1 ]] && systemctl is-active --quiet ws-native-security &&
    cmp -s "$candidate" "/proc/$pid/exe" &&
    python3 - "$pid" "$fix/request-policy.env" <<'PY_ENV'
from pathlib import Path
import sys
env=Path("/proc",sys.argv[1],"environ").read_bytes().split(b"\0")
sys.exit(not all(line in env for line in Path(sys.argv[2]).read_bytes().splitlines() if line))
PY_ENV
}
if ! security_matches; then
    since=$(date --iso-8601=seconds)
    if [[ $(systemctl show ws-native-security -p Result --value) == start-limit-hit ]]; then
        journalctl -u ws-native-security -n 25 --no-pager >&2
        echo 'Previous start limit hit; systemd will admit at most one staging attempt.' >&2
        # The interval may already have elapsed. A single start lets systemd decide.
    fi
    if ! systemctl restart ws-native-security || ! security_matches ||
       ! curl --retry 5 --retry-connrefused --retry-delay 1 --max-time 2 --noproxy '*' -fsS http://127.0.0.1:23000/health >/dev/null; then
        journalctl -u ws-native-security --since "$since" --no-pager >&2
        # Cancel any Restart=on-failure job for the rejected candidate.
        systemctl stop ws-native-security
        false
    fi
else
    echo 'Rust Security already running the requested binary and policy; preserving PID.'
fi
security_accepted=true
pid=$(systemctl show ws-native-security -p MainPID --value)
test "$pid" -gt 1
cmp "/proc/$pid/exe" "$repo/security-web/target/release/pbl4-security-demo"
if [[ $direct == enabled ]]; then
    install -m0644 "$src/ws-native-plan@.service" "$units/ws-native-peer-plan@.service"
    install -m0644 "$src"/ws-native-peer{.socket,-plan.socket,@.service} "$units/"
    systemctl daemon-reload
    systemctl start ws-native-peer-plan.socket ws-native-peer.socket
fi
systemctl start ws-native-sensor ws-native-plan.socket
systemctl start ws-native-edge
for ((i=0;i<20;i++)); do if [[ -s /var/lib/ws-native/guard/status.json ]] && curl --noproxy '*' --max-time 2 --cacert "$etc/edge.crt" -fsS https://127.0.0.1:29443/health >/dev/null 2>&1; then break; fi; sleep 1; done
test -s /var/lib/ws-native/guard/status.json
systemctl is-active --quiet ws-native-edge
checkpoint=$mode
if "$ip_only"; then checkpoint=stage; fi
instance=$(python3 -B "$src/request-checkpoint.py" "$checkpoint")
install -m0644 "$render" "$etc/approved-location.inc"
systemctl restart ws-native-edge
# Prove the gated location still forwards an anonymous request, and the gate fails closed on errors.
for ((i=0;i<20;i++)); do
    code=$(curl --noproxy '*' --cacert "$etc/edge.crt" --max-time 3 -s -o /dev/null -w '%{http_code}' https://127.0.0.1:24443/api/users || :)
    if [[ $code == 401 ]]; then break; fi
    sleep 1
done
test "$code" = 401
python3 - "$instance" "$mode" "$direct" "$ip_only" <<'PY'
from pathlib import Path
import json,os,sys,time
start=int(time.time())
policy=dict(start=start,end=start+600,actions={"BLOCK_REQUEST":dict(rules=["APP-1012","APP-1013"],immediate=[],events=3,window_seconds=60,ttl=15,cooldown=60,source_instance=sys.argv[1])})
if sys.argv[2]=="full" and sys.argv[4]!="true":
    binding=json.loads(sys.argv[1])
    policy["actions"]["BLOCK_REQUEST"]["source_instance"]=binding["instance"]
    for action,events,ttl in [("BLOCK_SESSION",5,30),("BLOCK_ACCOUNT",8,60)]:
        policy["actions"][action]=dict(policy["actions"]["BLOCK_REQUEST"], rules=["APP-1016" if action=="BLOCK_SESSION" else "APP-1014"],events=events,ttl=ttl,lab_actor=binding["actor"])
if sys.argv[3]=="enabled":
    policy["actions"]["BLOCK_IP"]=dict(policy["actions"]["BLOCK_REQUEST"],rules=["APP-1013","APP-1014"],events=10)
if sys.argv[4]=="true": policy["actions"]={"BLOCK_IP":policy["actions"]["BLOCK_IP"]}
p=Path("/etc/ws-native/approval.json")
with p.open("x") as f:
    json.dump(policy,f)
    f.flush();os.fsync(f.fileno())
os.chmod(p,0o644)
PY
armed=true
# Exercise the exact credential boundary before scheduling any publication.
runuser -u ws-native-actuator -- python3 -B - "$ip_only" <<'PY_CHECK'
import json,socket,sys
action="BLOCK_IP" if sys.argv[1]=="true" else "BLOCK_REQUEST"
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
    sock.settimeout(8)
    sock.connect("/run/ws-native-plan.sock")
    sock.sendall(action.encode())
    sock.shutdown(socket.SHUT_WR)
    with sock.makefile("rb") as stream:
        plan=json.load(stream)
    if plan is not None and plan.get("action")!=action:
        raise SystemExit("Planner returned an unauthorized action")
PY_CHECK
if [[ $direct == enabled ]]; then ip_readiness before-worker; fi
systemctl start ws-native-worker.service
systemctl start ws-native-worker.timer
systemctl is-active --quiet ws-native-worker.timer
if [[ $direct == enabled ]]; then ip_readiness; fi
if [[ $mode == full ]]; then
    echo "Authorization installed for 600s. IP scope: $direct. No runtime action is certified by installing this window."
    exec bash "$src/native-auto.sh" status 9>&-
fi
echo 'Authorized 600 seconds of BLOCK_REQUEST evaluation. A block is proven only by a journal entry plus matching Gate 403.'

# Observation failures must never report a successful acceptance.
python3 -B "$src/observe-request-block.py"
