# Lua capture checkpoint — supersedes old bundle cutover instructions

New bundle: `/tmp/ws-host-bundle-lua-final-972`. Do not use the previous deferred-only
bundle. Manifest hashes include `transaction-evidence.lua`; installer target set now
requires it. Student CA and Edge public trust certificate are copied, no private keys.

Lua source is shared with Live E2E/offline harness through `write_lua()`. Nine TSV
fields: flow_id, tx_id, proof, receipt, client, request_id, scheme, host, generation.
Generation is read from kernel UUID randomness at Lua logger setup, recorded in
`proof-generation` and every row. No HMAC key/cookie/body/full header dump is read.
Output is `chain.tsv` in Suricata default-log-dir, separate from EVE. The staged
Suricata unit uses UMask=0077. Script is root-owned 0644 at apply; Suricata service
must be able to read it and write its existing log directory. A logger startup or
write failure must not pass health. Retain evidence securely; it includes proofs.

Preflight requires enabled Lua, exact script path, hashed bundled script, regular
HTTP EVE and performs Suricata -T with temporary output/script paths. It does not
prove service UID/runtime directory access; live checkpoint verifies actual output.

After sensor switch, checkpoint reads the new generation, records log inode/offset,
then sends HTTPS GET /api/auth/me with a random non-sensitive query canary. It
requires 401 plus Edge request ID, fresh EVE HTTP on lo with expected source/dest,
request target/timestamp and matching Lua flow_id/tx_id/request ID/generation with
both proof and receipt. Old bytes, missing receipt, mismatches, truncation/rotation
and sensor restart cannot pass. This is capture/correlation readiness, not HMAC
verification or proof of full response completion. Client IP remains Unverified.

A failed checkpoint invokes rollback. Backup restores previous Suricata YAML/unit
(vmnet3 on this Host), NGINX config and scripts. After starting restored services,
rollback checks HTTP/HTTPS FE200 and API401 using Edge CA. Failure is reported as
ROLLBACK ALSO FAILED, not successful recovery. No global nftables restoration.

## Non-root final checks from repository root

```bash
python3 security-web/scripts/test-proof-host-deploy.py
python3 security-web/scripts/test-proof-capture-health.py
python3 security-web/scripts/test-live-proof-inputs.py
python3 security-web/scripts/deploy-proof-host.py preflight --bundle /tmp/ws-host-bundle-lua-final-972 --backup /var/backups/ws-proof-cutover-lua
python3 security-web/scripts/deploy-proof-host.py dry-run --bundle /tmp/ws-host-bundle-lua-final-972 --backup /var/backups/ws-proof-cutover-lua
```

Host ownership must pass on actual Host; sandbox sees module ownership mapped to
nobody and blocks preflight. Do not bypass it. Suricata isolated -T passed here.

## Operator-only isolated live acceptance (NOT apply)

```bash
bash security-web/scripts/run-live-transaction-proof.sh /usr/lib/nginx/modules/ngx_http_js_module.so --extended
```

Run as normal user. Wrapper builds Rust, then requests sudo ONLY for temporary
network namespace/cgroup capture and test nftables. It uses the existing renderer
and shared Lua source, not production Student/DB/services. Review harness before
running. Expected required cases all PASS, no pending, with actual Lua generation.
This does not test systemd installer on Host and is not production acceptance.

Current evidence: mocked installer 15 PASS; checkpoint 5 PASS; live input regression
10 PASS; Rust journal 1 PASS, external bridge test ignored (no live fixture).
Real Suricata 8.0.3 offline synthetic-PCAP Lua test PASS: HTTP204, proof/receipt,
generation and no cookie leakage. Non-root njs runtime attempt BLOCKED by sandbox
socket permission; AF_PACKET live run NOT_RUN. Previous live PASS is not reused as
acceptance of this Lua revision. No production apply commands until operator live
and actual Host preflight complete. AI DEFERRED; AUTO_BLOCK/Verified not enabled.
