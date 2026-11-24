#!/bin/bash
# Run on the Security Host as the SSH operator. Only public PKI material crosses SSH.
set -Eeuo pipefail
umask 077
mode=${1:-apply}
case $mode in apply|resume|status|rollback) ;; *) exit 2;; esac
[[ $EUID != 0 ]] || { echo 'Run as the normal VM SSH operator'; exit 1; }
src=$(realpath "$(dirname "$0")/../deploy/rsyslog")
vm=khang1901@192.168.20.10
t=$(mktemp -d)
ctl=$t/ssh
remote=(ssh -oStrictHostKeyChecking=yes -S "$ctl" "$vm")
copy=(scp -q -oStrictHostKeyChecking=yes -oControlPath="$ctl")
tools=/var/lib/pbl4-audit-mtls-tools
tls=/etc/pbl4/audit/mtls
remote_dir=
sender_probe=no receiver_probe=no cutover=no
phase=initialize
trap 'rc=$?; printf "BLOCKED: audit-mtls %s, phase %s, line %s, exit %s\n" "$mode" "$phase" "$LINENO" "$rc" >&2; exit "$rc"' ERR
host() { echo "[Security Host] $1" >&2; sudo bash "$tools/node.sh" receiver "$@"; }
guest() { echo "[Student VM] $1" >&2; ssh -tt -oStrictHostKeyChecking=yes -S "$ctl" "$vm" sudo bash "$tools/node.sh" sender "$@"; }
cleanup() {
    local result=$?
    trap - ERR
    set +e
    if [[ $cutover == yes && $result != 0 ]]; then
        echo 'Cutover incomplete: retaining TLS and queues. Attempting to resume sender with the checked TLS configuration.' >&2
        guest apply || echo 'Sender needs attention; preserve its source generations and spool.' >&2
    fi
    if [[ $result != 0 && $phase == canary-* ]]; then
        host probe-diagnostics
        guest probe-diagnostics
    fi
    if [[ $sender_probe == yes ]]; then guest probe-stop || result=1; fi
    if [[ $receiver_probe == yes ]]; then host probe-stop || result=1; fi
    if [[ $remote_dir =~ ^/tmp/ws-audit\.[a-zA-Z0-9]+$ ]]; then "${remote[@]}" rm -r -- "$remote_dir"; fi
    ssh -O exit -S "$ctl" "$vm" >/dev/null 2>&1
    rm -r -- "$t"
    exit "$result"
}
trap cleanup EXIT
ssh -M -N -f -oStrictHostKeyChecking=yes -oControlPersist=300 -S "$ctl" "$vm"
if [[ $mode == status ]]; then
    host status; guest status
    ss -Hltn 'sport = :2514'
    exit
fi
sudo -v
exec 9>"$HOME/.ws-audit-mtls.lock"
flock -n 9
if [[ $mode == rollback ]]; then
    read -rp 'Restore BOTH original plaintext configs, retaining queues? Type APPROVE-PLAINTEXT: ' ans
    [[ $ans == APPROVE-PLAINTEXT ]]
    guest stop; host stop; host restore; guest restore
    host status; guest status
    exit
fi
mkdir "$t/files"
cp "$src"/mtls/{config.py,digest.py,node.sh,probe.py} "$t/files/"
for role in sender receiver; do cp "$src/student-audit-$role.conf" "$t/files/$role.conf"; done
(cd "$t/files" && sha256sum config.py digest.py node.sh probe.py receiver.conf sender.conf > SHA256SUMS)
manifest=$(sha256sum "$t/files/SHA256SUMS" | cut -d' ' -f1)
remote_dir=$("${remote[@]}" mktemp -d /tmp/ws-audit.XXXXXXXX)
[[ $remote_dir =~ ^/tmp/ws-audit\.[a-zA-Z0-9]+$ ]]
"${copy[@]}" "$t/files/"* "$vm:$remote_dir/"
sudo install -d -m0755 "$tools"
sudo install -m0644 "$t/files/"* "$tools/"
# Copy fixed filenames first, verify from the root-owned directory before elevation of code.
ssh -tt -S "$ctl" "$vm" "sudo bash -ec 'install -d -m0755 $tools; q=\$(mktemp -d $tools/.verify.XXXXXXXX); cd $remote_dir; install -m0600 SHA256SUMS config.py digest.py node.sh probe.py receiver.conf sender.conf \$q/; cd \$q; echo \"$manifest  SHA256SUMS\" | sha256sum -c -; sha256sum -c SHA256SUMS; install -m0644 config.py digest.py node.sh probe.py receiver.conf sender.conf $tools/; rm -r -- \$q'"
host snapshot; guest snapshot
if [[ $mode == resume ]]; then
    host resume-check; guest resume-check
else
    guest csr; host csr
    "${copy[@]}" "$vm:$tls/sender.csr" "$t/sender.csr"
    sudo install -m0644 "$t/sender.csr" "$tools/"
    host sign
    "${copy[@]}" "$tls"/{ca,sender,wrong-name}.crt "$vm:$remote_dir/"
    # Verify public certs against their local digests after installing on the VM.
    for f in ca.crt sender.crt wrong-name.crt; do
        digest=$(sha256sum "$tls/$f" | cut -d' ' -f1)
        ssh -tt -S "$ctl" "$vm" "sudo bash -ec 'q=\$(mktemp $tools/.cert.XXXXXXXX); install -m0600 $remote_dir/$f \$q; echo \"$digest  \$q\" | sha256sum -c -; install -m0644 \$q $tools/$f; rm -- \$q'"
    done
    host prepare; guest prepare
fi
# Both canary listeners bind loopback. The SSH tunnel traverses the VM link.
# IPv4 bind exclusivity prevents accidentally sending to an existing service.
phase=canary-receiver
host probe-stop; guest probe-stop
host probe-free
receiver_probe=yes; host probe-start
host probe-listening
if [[ $mode == resume ]]; then
    phase=canary-stop-check
    host probe-stop; receiver_probe=no
    echo 'PASS receiver startup, listening, graceful exit and port release'
    receiver_probe=yes; host probe-start
    host probe-listening
fi
# Model a disconnected sender with NO accepting TCP socket on the VM.
# Opening the reverse forward here produces a misleading TLS EOF during queue testing.
phase=canary-disconnected-queue
guest probe-free
id=$(openssl rand -hex 16)
sender_probe=yes; guest probe-start
guest probe-send "$id"; guest probe-consumed "$id"
guest probe-stop; sender_probe=no
guest probe-queued "$id"
phase=canary-forward
ssh -oExitOnForwardFailure=yes -O forward -S "$ctl" -R 127.0.0.1:32514:127.0.0.1:32514 "$vm"
phase=canary-handshake
ack_id=$(openssl rand -hex 16)
guest probe-tls 32514 "$ack_id"
host probe-check "$ack_id"
phase=canary-queue-replay
sender_probe=yes; guest probe-start
host probe-check "$id"
guest probe-stop; sender_probe=no
host probe-stop; receiver_probe=no
phase=cutover-confirmation
read -rp 'Canary PASS. Switch the two dedicated audit services on TCP/2514? Type CUTOVER-MTLS: ' ans
[[ $ans == CUTOVER-MTLS ]]
# Graceful shutdown lets RELP persist unacknowledged items. imfile resumes at its saved offset.
cutover=yes
guest stop; host stop
host apply; guest probe-tls 2514; guest apply
headers=$t/headers
code=$(curl --noproxy '*' --cacert /etc/ws-native/edge.crt --max-time 10 -sS -D "$headers" -o /dev/null -w '%{http_code}' https://127.0.0.1:24443/api/auth/me)
[[ $code == 401 ]]
rid=$(awk 'tolower($1)=="x-request-id:" {gsub(/\r/,"",$2);print $2}' "$headers")
[[ $rid =~ ^[a-f0-9]{32}$ ]]
remote_hash=$("${remote[@]}" python3 "$tools/digest.py" /home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log "$rid")
[[ $remote_hash =~ ^[a-f0-9]{64}$ && $(host digest "$rid") == "$remote_hash" ]]
for ((i=0;i<30;i++)); do
    seen=$(sudo docker exec -e PGOPTIONS=-cdefault_transaction_read_only=on pbl4-postgres psql -XAt -v ON_ERROR_STOP=1 -U pbl4 -d ws_native_security -c "select exists(select from normalized_events where source='STUDENT_AUDIT' and request_id='$rid')")
    [[ $seen != t ]] || break
    sleep 1
done
[[ $seen == t ]]
host assert-live; guest assert-live
echo "PASS TLS 1.3 mTLS, byte-identical new audit, Rust/PostgreSQL request_id=$rid"
