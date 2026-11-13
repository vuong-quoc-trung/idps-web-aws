# Host edge admission control

Lab starting values, not capacity guarantees:
- Per peer IP: 20 requests/s, burst 40, nodelay (excess returns 429).
- Sensitive auth POST: 10 requests/minute per IP + endpoint, burst 5.
  These are leaky-bucket rates, not fixed-window request counts.
- 20 concurrent active requests/connections per IP (429); NGINX limit_conn
  counts only after complete headers, not every idle TCP connection.
- Body 1 MiB (413), header/body inactivity timeout 10s, response send inactivity
  timeout 15s, keepalive 15s. These are not total transaction deadlines.
- Request buffering remains enabled. Test legitimate uploads before changing 1 MiB.
- Shared NAT clients share IP budgets. This cannot protect a saturated uplink.

Both render and AI installer use the same zone definitions. Existing request IDs,
JSON rule_signals, privacy filtering and Unix socket AI telemetry remain intact.
429 is an edge enforcement response, not proof Rust created an alert. Early
rejection can prevent app audit or alter detector threshold demonstrations.
The local-demo template is intentionally unchanged; this protects Host -> VM.

## Review and install
From repository root:

    python3 security-web/scripts/sync-nginx-edge.py --lan-ip YOUR_CURRENT_LAN_IP
    sudo python3 security-web/scripts/sync-nginx-edge.py --lan-ip YOUR_CURRENT_LAN_IP --apply

Omit --lan-ip for VMware-only access. IPs must exist on this host. The installer
replaces the managed pbl4 site and shared format file with the repository template;
review custom runtime directives before applying. It tests the candidate against
other installed includes, backs up both files under /var/backups/pbl4-nginx-edge,
tests again and reloads (not restarts) NGINX. No AI restart, firewall, DB or VM edits.
Identical files cause no reload. A failed apply restores the backup.

    sudo nginx -t
    systemctl is-active nginx
    curl --noproxy '*' -I http://192.168.10.1/

Use the exact rollback command printed by the installer:

    sudo python3 security-web/scripts/sync-nginx-edge.py --rollback /var/backups/pbl4-nginx-edge/TIMESTAMP/rollback.json

## Tests
    python3 security-web/scripts/test-nginx-host.py

Tests use disposable loopback NGINX and mock upstream, including 429/413 rejection
before forwarding, identity, privacy and detector signals. They do not load-test
production. Connection saturation and slow-client behavior still require separate
controlled acceptance; no distributed-DDoS protection is claimed.
