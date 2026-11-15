# Phase 1: passive Suricata after NGINX

## Scope and observed configuration

Target: Client -> NGINX -> HTTP 192.168.20.10:80; capture vmnet3 on
Security Host (192.168.20.1). No TLS, AWS, inline mode or automatic blocking.
Keep NGINX edge limits, AI socket telemetry and audit unchanged.
Client attribution now has an additive DB/API/Dashboard extension. Use
[the single integrated acceptance checklist](ACCEPTANCE.md) for deployment.
The frontend interface vmnet2 remains the attacker-side firewall interface;
DO NOT change ATTACKER_IFACE to vmnet3 just because the sensor moved.

Inspection on this checkout/host:
- Both YAML files select vmnet2. Git HOME_NET includes private networks; runtime
  uses 192.168.10.1/32 and 192.168.20.0/24. XFF is disabled in runtime.
- Runtime rule file differs from Git. The generator preserves the runtime rule
  paths, records SHA256 hashes, and does NOT install the Git rules silently.
- systemd vendor unit uses one daemon with --af-packet and /etc/suricata/suricata.yaml.
- Runtime NGINX includes edge limits, passes HTTP to 192.168.20.10:80, overwrites
  X-Forwarded-For/X-Real-IP with remote_addr, and generates X-Request-Id.
- Before this update Rust used EVE src_ip as client_ip. The new optional post-proxy
  policy preserves network_src_ip separately and only promotes transaction-local
  XFF after explicit trusted-edge confirmation; otherwise client_ip is null.
- Raw EVE was empty at inspection. No live post-proxy success has been established.

## Profiles and privacy

The generator takes an explicit base YAML, preserves it byte-for-byte as
pre-proxy.yaml and produces post-proxy.yaml plus a systemd drop-in. It changes
AF_PACKET to vmnet3 only, uses a bidirectional BPF filter for the proxy/VM pair
on TCP80, and sets HTTP_SERVERS/HOME_NET to the VM. EXTERNAL_NET excludes only
that server so the proxy can match inbound rules. All existing rule files remain.
Suricata is passive: no copy-mode, no NFQUEUE, stream.inline=false.

The post profile retains the same EVE filename/directory; never run pre and post
processes concurrently. A controlled restart replaces capture, leaving the old
configuration available for rollback. Do not remove the pre profile after testing.
Rate-based rules still count proxy traffic, NOT individual clients. Request
normalization, buffering, upstream reuse and edge refusals change visibility.

XFF extra-data preserves src_ip/dest_ip. On tested Suricata8.0.3, alert.xff and
http.xff correspond to the transaction; use sensor run + flow_id + tx_id, never
flow_id alone. XFF is only an assertion: trust requires the actual peer to be
NGINX and the backend to be unreachable by untrusted bypass paths. Missing or
ambiguous transaction evidence means alert-only, never block.

X-Request-Id continues in NGINX and Student Audit. Suricata8.0.3's fixed custom
HTTP-header list did not emit arbitrary X-Request-Id in the offline test.
We intentionally do NOT dump all headers, cookies, Authorization or bodies to
obtain it. Exact NGINX-request-ID correlation is NOT implemented in this phase.
Optional canonical suricata_origin metadata and migration 0014 preserve attribution.
No AI feature schema change; post-proxy never queues automatic firewall actions.
Existing EVE URL logging is retained: do not use real secrets in test queries.

## Stage and validate (no deployment)

From repository root, with Python3 + PyYAML:

    STAGE=$(mktemp -d /tmp/pbl4-profile-parent.XXXXXX)/profiles
    python3 security-web/scripts/prepare-suricata-post-proxy.py --base /etc/suricata/suricata.yaml --output "$STAGE"
    mkdir -p "$STAGE/test-logs"
    suricata -T -c "$STAGE/post-proxy.yaml" -l "$STAGE/test-logs"
    cat "$STAGE/manifest.json"
    diff -u /etc/suricata/suricata.yaml security-web/config/suricata/suricata.yaml
    systemctl cat suricata
    ps -eo pid,args | grep '[s]uricata'
    ip -br addr show vmnet3
    ip route get 192.168.20.10

The diff is informational (exit1 means differences). Review any custom unit/drop-ins
and alternate processes. The provided drop-in matches the observed vendor unit;
if yours differs, do not replace it blindly. Review classification/reference paths
and all existing output settings. The manifest records external rule dependencies;
back up those files and avoid changing them during acceptance.

## Operator-only activation

1. Verify the RUNNING Rust instance uses AUTO_BLOCK=false AND ENFORCEMENT_MODE=OFF,
   and protects 192.168.20.1, 192.168.20.10, host/admin addresses. If necessary adjust
   its environment and restart using your existing deployment workflow. Merely
   editing .env does not change a running process. Do not clear firewall sets;
   inspect any pre-existing blocks separately. Do not proceed without this gate.
2. Confirm Student Web VM is reachable, NGINX is active, only one Suricata process
   owns the EVE destination, and no other capture wrapper will launch another.
3. Back up configuration, referenced rule files and any existing override:

    BACKUP=/var/backups/pbl4-suricata/$(date +%Y%m%d-%H%M%S)
    sudo install -d -m 700 "$BACKUP"
    sudo cp -a /etc/suricata "$BACKUP/etc-suricata"
    sudo cp -a /var/lib/suricata/rules "$BACKUP/rules"
    systemctl cat suricata | sudo tee "$BACKUP/unit.txt" >/dev/null
    # If this directory exists, also back it up before proceeding:
    # sudo cp -a /etc/systemd/system/suricata.service.d "$BACKUP/drop-ins"

4. First-time installation only (stop if these profile/override files already exist;
   preserve the previous snapshot instead of overwriting it):

    sudo install -d /etc/suricata/pbl4 /etc/systemd/system/suricata.service.d
    sudo test ! -e /etc/suricata/pbl4/pre-proxy.yaml
    sudo test ! -e /etc/systemd/system/suricata.service.d/90-pbl4-post-proxy.conf

   Execute the next commands ONLY if both checks succeed:

    sudo install -m 600 "$STAGE/pre-proxy.yaml" /etc/suricata/pbl4/pre-proxy.yaml
    sudo install -m 644 "$STAGE/post-proxy.yaml" /etc/suricata/pbl4/post-proxy.yaml
    sudo suricata -T -c /etc/suricata/pbl4/post-proxy.yaml
    sudo install -m 644 "$STAGE/post-proxy.conf" /etc/systemd/system/suricata.service.d/90-pbl4-post-proxy.conf
    sudo systemctl daemon-reload
    sudo systemctl restart suricata
    systemctl status suricata --no-pager -l
    sudo journalctl -u suricata -n 50 --no-pager

   Stop and rollback on failure. Do not run a second manual Suricata daemon.
   The original /etc/suricata/suricata.yaml is untouched. No firewall, NGINX, AI,
   PostgreSQL or Dashboard files are installed by these steps.

## Runtime acceptance (NOT yet executed)

On Defender, inspect packet headers only (no -A/-X, no payload PCAP retention):

    sudo timeout 30 tcpdump -ni vmnet3 -c 40 'host 192.168.20.1 and host 192.168.20.10 and tcp port 80'

From Kali, send only these four lab requests; record UTC time and X-Request-Id:

    curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null http://192.168.10.1/api/auth/me
    curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null --get --data-urlencode "q=' OR 1=1" http://192.168.10.1/api/probe
    curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null --get --data-urlencode 'q=<script>alert(1)</script>' http://192.168.10.1/api/probe
    curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null http://192.168.10.1/.env

Check new EVE HTTP/alert entries (not old history), src_ip=192.168.20.1,
dest_ip=192.168.20.10, tx_id and alert.xff/http.xff=192.168.10.10.
Confirm both directions in capture/flow counters. Check SID1000002/1000003,
NGINX access receipt, and new Rust/Dashboard alerts with verified client IP plus separate proxy network IP.
Use the NGINX request ID for NGINX/audit lookup only; do not invent an EVE ID join.
The /.env request should return403 in NGINX, with NO corresponding upstream
transaction. During a quiet isolated window verify this in capture and EVE;
absence from an unrelated or incomplete log alone is not sufficient evidence.
Also inspect NGINX, AI worker and audit service health before/after and verify an
ordinary request still works. No new firewall block/action should occur.

## Rollback (same single service)

Remove ONLY the drop-in created above; do not remove other administrator overrides:

    sudo rm /etc/systemd/system/suricata.service.d/90-pbl4-post-proxy.conf
    sudo systemctl daemon-reload
    sudo suricata -T -c /etc/suricata/suricata.yaml
    sudo systemctl restart suricata
    systemctl status suricata --no-pager -l

The vendor ExecStart selects the untouched original vmnet2 YAML again. Confirm
with systemctl cat and journal. If the original was modified independently,
restore it from the recorded backup first, after reviewing the diff. Leave the
staged profiles for analysis. Resume enforcement only after a separate review.

## Automated checks and limits

    python3 security-web/scripts/test-suricata-post-proxy.py
    SURICATA_RULES=/var/lib/suricata/rules/pbl4.rules python3 security-web/scripts/test-suricata-post-proxy.py
    python3 security-web/scripts/test-extended-rules.py
    cd security-web && cargo test --offline events::tests

Offline tests exercise Suricata8.0.3, SQLi/XSS/traversal, four HTTP transactions on
one connection with distinct XFF, unchanged proxy IP, response metadata and no
cookie logging. Synthetic PCAP is evidence for parser/rules, NOT live vmnet3
visibility or successful Dashboard ingestion. Those remain runtime acceptance.
