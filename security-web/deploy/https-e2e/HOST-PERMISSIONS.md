# Cutover permissions — 2026-11-17

Account observed: websentinel-edge UID 997 / GID 972. AI DEFERRED.

Apply stops NGINX before creating `/var/lib/websentinel-nginx` root:972 0750,
with client_body/proxy/fastcgi/scgi/uwsgi children 997:972 0700.
Existing `/var/lib/nginx`, `/var/log/nginx` and their ACLs remain unchanged.
Root master opens existing log files and passes descriptors to workers. No cache
zone is introduced. Other sites that read private files need separate access
review; a successful syntax check does not prove their functional availability.
Existing dedicated temp root blocks initial apply rather than silently chmod it.
Rollback restores old configuration and removes only empty new temp directories;
nonempty directories are reported RETAINED, never recursively deleted.

Module includes are expanded into the staged main config; the installed njs is
loaded exactly once. Regenerate/review the bundle after package/module changes.
AI syslog is commented, with restore marker retained. No AI runtime acceptance.

## Current evidence

Bundle: `/tmp/ws-host-bundle-deferred-972` (ephemeral; no private key).
ABI/load test PASS; installer mocked tests 15/15; renderer tests 4/4.
Edge public certificate self-signature/server purpose/IP verification PASS.
Dry-run validates bundle only, NOT host readiness.
Preflight BLOCKED: sandbox sees installed njs as nobody:nogroup. This may reflect
filesystem ownership mapping; verify on actual Host. Do not blindly chown packages.
Full effective NGINX syntax, privileged permissions and cutover NOT TESTED.
The previous Live E2E evidence does not test these new filesystem permissions.

## Next commands on actual Host (no changes)

From repository root:

```bash
stat -Lc '%U:%G %a %n' /usr/lib/nginx/modules /usr/lib/nginx/modules/ngx_http_js_module.so
namei -l /usr/lib/nginx/modules/ngx_http_js_module.so
python3 security-web/scripts/check-njs-abi.py --module /usr/lib/nginx/modules/ngx_http_js_module.so
python3 security-web/scripts/deploy-proof-host.py preflight --bundle /tmp/ws-host-bundle-deferred-972 --backup /var/backups/ws-proof-cutover
python3 security-web/scripts/deploy-proof-host.py dry-run --bundle /tmp/ws-host-bundle-deferred-972 --backup /var/backups/ws-proof-cutover
```

Stop on any failure. If ownership is genuinely non-root, inspect package provenance
and restore package permissions through a separately approved step first.

## Only after preflight passes and operator approves downtime

Existing full backup: `/var/backups/ws-security-before-egress-20261117-221032`.
Installer additionally creates its own fresh checkpoint (do not reuse full backup
as installer backup; formats differ). Verify COMPLETE/checksums of full backup.
Root staging below is a production preparation action, NOT executed by the agent:

```bash
sudo install -d -m 0700 /root/ws-proof-cutover
sudo cp -a /tmp/ws-host-bundle-deferred-972 /root/ws-proof-cutover/bundle
sudo cp security-web/scripts/deploy-proof-host.py security-web/scripts/proof-nginx-lifecycle.py security-web/scripts/local-egress-guard.py /root/ws-proof-cutover/
sudo chown -R root:root /root/ws-proof-cutover
sudo chmod -R go-w /root/ws-proof-cutover
sudo python3 /root/ws-proof-cutover/deploy-proof-host.py preflight --bundle /root/ws-proof-cutover/bundle --backup /var/backups/ws-proof-cutover
sudo python3 /root/ws-proof-cutover/deploy-proof-host.py apply --bundle /root/ws-proof-cutover/bundle --backup /var/backups/ws-proof-cutover --approve-host-change
sudo python3 /root/ws-proof-cutover/deploy-proof-host.py health --bundle /root/ws-proof-cutover/bundle --backup /var/backups/ws-proof-cutover
```

Run individually; stop on error. Apply interrupts NGINX and later switches Suricata.
HTTP/HTTPS FE/API checkpoint precedes sensor switch; failures invoke rollback.
No automatic deletion of installed account/module. Supervisor leaves its deny-only
local-egress guard on shutdown; old vmnet3 path is not matched by that guard.

Manual rollback (only after installer checkpoint exists):

```bash
sudo python3 /root/ws-proof-cutover/deploy-proof-host.py rollback --bundle /root/ws-proof-cutover/bundle --backup /var/backups/ws-proof-cutover --approve-host-change
sudo nginx -t
systemctl is-active nginx suricata
curl --noproxy '*' --cacert "$HOME/websentinel-lab.crt" -I https://192.168.10.1/
```

No Client IP Verified/AUTO_BLOCK acceptance. Review other sites, actual HTTP/HTTPS,
Suricata events and Application Audit after operator cutover; AI remains DEFERRED.
