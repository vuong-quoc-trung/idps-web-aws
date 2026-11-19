# Optional TLS Egress — stage 1

Topology: Edge TLS → HTTP `127.77.0.1 → 127.77.0.2:18080` on `lo` → TLS Student.
Two server blocks, same NGINX. Existing HTTP/HTTPS listeners and Edge Protection
remain; only the upstream changes when explicitly enabled. No HSTS or redirect.
Defaults remain the previously accepted direct HTTP upstream and vmnet3 sensor.

## Stage candidate only

From repository root (paths below are examples, no keys are stored in Git):

```bash
python3 security-web/scripts/prepare-nginx-host.py \
  --tls-cert /etc/nginx/pbl4-tls/lab.crt \
  --tls-key /etc/nginx/pbl4-tls/lab.key \
  --egress-ca /etc/nginx/pbl4-tls/student-ca.pem \
  --egress-name student.internal.websentinel.test \
  --egress-port 443 --output /tmp/pbl4-egress-stage
python3 security-web/scripts/prepare-suricata-post-proxy.py \
  --base /path/to/reviewed-suricata.yaml \
  --profile local-egress --output /tmp/pbl4-egress-sensor
```

The Suricata output directory must be new. Original YAML snapshot, absolute rule
paths/checksums and drop-in are generated for review; nothing is installed.
`--profile post-proxy` remains the default. Local profile changes only capture
interface/filter, cluster ID, HOME_NET and HTTP_SERVERS; SID content, EVE privacy
and XFF extra-data remain unchanged. It is passive, not inline.
Do not start a second sensor against the production EVE file. Temporary tests
must override PID/log/output paths and use a private directory.

For a reviewed future deployment `sync-nginx-edge.py` accepts the same egress
options and retains them from managed metadata on later syncs. `--disable-egress`
returns to the direct HTTP upstream, retaining Edge TLS. Existing backup/rollback
mechanism covers both blocks because they are rendered into the same site file.
`--disable-https` while egress is enabled is rejected: explicitly disable egress
as well if deliberately returning to HTTP-only. Do not apply during stage 1.
AI installer may reject the changed upstream for manual review; it must not be
used to regenerate this topology blindly. Existing telemetry stays at Edge only.

## Trust gate — mandatory before runtime adoption

`allow 127.77.0.1` is an ACL, NOT proof of process identity. Another local process
may bind that source IP and forge headers. Even HTTP403 does not prove the sensor
has not already observed a forged request. Header shape checks are not authentication.
Keep `SURICATA_TRUSTED_EDGE_CONFIRMED=false`, `AUTO_BLOCK=false`, and
`ENFORCEMENT_MODE=OFF`. Stage 1 does not change Rust or claim Client IP Verified.
Do not apply the local capture profile with the old trust-confirmed environment.

Before stage 2 prove process/cgroup isolation and capture behavior, or use veth
plus separate namespaces. The latter will generally require a separate egress
process. Capture both directions at one point only. AF_PACKET loopback packet
handling, actual in_iface, flow_id/tx_id, retransmissions and duplicate alerts
remain to be verified with the installed kernel/Suricata. Retain the events.rs
fileinfo/response guard. Changing topology changes observed destination to egress;
do not label it as the final Student host or rewrite network IP fields.

## Student TLS prerequisites

Student must already provide a reviewed TLS endpoint before adoption. No fallback
to HTTP on certificate failure. Egress verifies CA and DNS SAN using explicit
proxy_ssl_name (independent of upstream IP), TLS1.2/1.3. Certificate rotation and
CA distribution are operator tasks. No automatic Student prod-profile activation:
that profile also changes bootstrap/DDL behavior. Use a separate TLS-only config
or the VM reverse proxy after reviewing its real deployment.

Egress preserves Edge's XFF, X-Real-IP, X-Request-Id, Host and forwarded scheme.
It does not generate a second AI event or run per-client limits on a shared proxy
IP. Student's trusted peer must match its actual connection chain. Test session,
CSRF, Audit identity and scheme separately using lab data. Loopback plaintext is
visible to privileged local processes; do not collect packet/body/header dumps
containing credentials during acceptance.

## Tests and next gate

```bash
python3 security-web/scripts/test-sync-nginx-edge.py
python3 security-web/scripts/test-nginx-host.py
python3 security-web/scripts/test-nginx-https.py
python3 security-web/scripts/test-nginx-egress.py
```

Tests use temporary NGINX configs, certificates, log files and a TLS mock backend;
nginx -t runs before starting the temporary process. No production requests or
services. Requires nginx, openssl, PyYAML and loopback sockets. Test-only ports
are ephemeral. The mock upstream verifies transport/header plumbing, not real
Student Audit, Suricata capture or AI inference.

Next, with explicit authorization only: isolated AF_PACKET capture and SID tests,
negative local-forgery tests, Rust attribution tests without relaxing policy,
Student TLS/Audit acceptance, resource measurements and sensor-stop independence.
No stage 2, migration, service changes or deployment are performed automatically.
Rollback must restore the old NGINX topology, vmnet3 profile and matching trust
configuration together; never just switch one interface while keeping old trust.

## Stage 2 partial acceptance — 2026-11-16

Executed with non-root disposable NGINX/TLS upstream, ephemeral loopback ports;
not the production Student or AI Worker. Suricata binary reports 8.0.3 RELEASE.

Observed security reproduction:

```json
{"boundary":"FAIL","source":"127.77.0.1","egress_status":204,"upstream_xff":"192.168.10.99","upstream_request_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","scope":"temporary TLS mock; no Suricata capture"}
```

A normal Python client bound the allowlisted loopback source and supplied forged
headers. Egress accepted them and the mock received them unchanged. The regression
test intentionally asserts this reproduction: a green test means the vulnerability
was reproduced, NOT that the trust boundary passes acceptance. Source-IP ACL alone
must not authorize enabling trusted attribution. No trusted flag was changed.

17 Python checks passed (including reproduction and syntax-only Suricata -T);
5 attribution tests and 9 events/contracts tests passed. New Rust test uses
synthetic EVE with the local tuple and trusted_edge=false, verifying that both
plausible and forged XFF stay unverified, native alerts remain and fileinfo does
not generate URI detections. It is not live capture evidence.

Live AF_PACKET on lo, exact fixed port18080, SID detections from live traffic,
packet duplication, actual EVE flow_id/tx_id/in_iface, and stopping a running
sensor while proxying are NOT TESTED. They require capture privileges; awaiting
operator decision before privileged/namespace operations. Running NGINX with no
sensor in these tests does not prove a sensor-stop transition.

Current result: NOT ACCEPTED for trusted local attribution. Prefer a controlled
veth/network-namespace boundary if local untrusted processes are in scope; this
requires process isolation, routes and access policy, not merely creation of a
veth pair. No alternative topology was deployed. Production runtime, DB, flags,
services and firewall were not changed by this acceptance run.

### Authorized isolated AF_PACKET follow-up — 2026-11-16

Operator authorized namespace capture. Host sudo required interactive authentication;
used `unshare --user --map-root-user --net` instead: uid0 maps to the invoking
unprivileged host user, only `lo` exists, no production network connection.
The harness refuses a user namespace without the single-ID mapping or with extra
interfaces. It starts one temporary NGINX (two blocks), mock TLS server and Suricata
8.0.3, and cleans them up. Only namespace-local lo is configured. No host interface,
service, /etc, DB, AI socket, flags or production traffic is changed.

Reproduce only with authorization for namespace capture:

```bash
unshare --user --map-root-user --net \
  python3 security-web/scripts/test-local-egress-capture.py
```

Optional `--evidence NEW_DIRECTORY` retains only allowlisted EVE attribution fields,
not certificates, keys or packet dumps. Captured fixture committed to the working
files (not Git committed): `tests/fixtures/local-egress-capture/eve.jsonl`.

Observed twice with real AF_PACKET (supersedes the earlier NOT TESTED capture rows):
- Exact local hop: 127.77.0.1 → 127.77.0.2:18080, interface lo.
- Synthetic real client socket source192.0.2.10 exists only inside namespace;
  Edge generated XFF from that connection, not a supplied client header.
- Four legitimate HTTPS probes: baseline, SQLi, XSS, traversal. Each returned204.
- SID1000002/1000003/1000004 occurred once each for legitimate client.
- One direct source-bound forged XSS returned204 and produced SID1000003 with
  forged XFF192.0.2.99. Trust boundary FAIL is now supported by live EVE too.
- Exactly five HTTP events, each with methodGET and response status204;
  alert app_proto=http, flow_id and tx_id present, in_iface=lo.
- Native HTTP EVE lacks top-level app_proto. Current Rust requires that field
  for HTTP attribution/supplemental URI detection; do not claim those paths work
  from this evidence or invent that field. Native alert handling stays intact.
- No duplicate SID/HTTP events observed in this small sequence. All observed
  hop transactions have tx_id0 on distinct flows; multi-request upstream keepalive,
  concurrency, retransmission and longer-duration duplicate behavior remain open.
- After actual SIGINT shutdown and wait of the sensor, HTTPS still returned204.

Rust regression reads the sanitized real capture with trusted_edge=false; preserves
network tuple, flow/transaction and all native alerts, keeps both legitimate and
forged XFF unverified. No production logic or environment flag changed. This is
safe failure, NOT successful verified legitimate-client acceptance.

Conclusion remains NOT ACCEPTED for trusted attribution. Loopback capture is
functional, but tuple/ACL cannot distinguish the bound-source impersonator.
Prefer controlled veth+namespace/process isolation before real Student deployment;
no alternative has been deployed. Student Audit, production TLS, AI, performance
and complete application/correlation acceptance remain untested.

## UID + cgroup kernel prerequisite harness (not production readiness)

New harness `scripts/test-egress-kernel-guard.py` uses only the Python standard
library plus `ip`, `unshare`, and `nft`. Run from a trusted checkout. It requires
sudo, cgroup v2 and AF_PACKET privileges. It creates exactly one unique
`/sys/fs/cgroup/ws-egress-test-<uuid>` subtree with `allowed` and `denied` children;
only newly created probe processes enter them. This is the sole host-visible
configuration change. A fresh network namespace has only loopback, no veth or
production routes. nftables is loaded **inside that namespace only**. It never
flushes the host ruleset, writes /etc, or controls any production service.

```bash
python3 security-web/scripts/test-egress-kernel-guard-unit.py
sudo python3 security-web/scripts/test-egress-kernel-guard.py --run-isolated
```

The six JSON case results must all say PASS:

- Correct UID 65534 and allowed cgroup: HTTP 204 and captured outbound frames.
- Same UID, denied cgroup, explicitly bound source 127.77.0.1: no connection,
  zero HTTP requests and zero matching outbound AF_PACKET frames.
- UID 65533 in allowed cgroup with the same bound source: likewise denied.
- UID 65533 in denied cgroup with the same bound source: likewise denied.
- Atomic replacement with a deny-only policy: formerly allowed process denied.
- Atomic restoration of the grant: new allowed process succeeds.

Each probe has a short timeout; the outer harness bounds execution to 90 seconds.
Normal exit/errors/Ctrl+C terminate the namespace process group and remove only
its unique cgroup subtree. SIGKILL/power failure cannot guarantee cleanup; inspect
any leftover uniquely named subtree before manual removal. No packet contents,
credentials, or production requests are stored. Unsupported cgroup socket matching
or failed nft loading aborts; there is no weaker UID/IP fallback.

**Scope:** this prerequisite deliberately uses a tiny HTTP receiver and real
unprivileged sockets to isolate kernel behavior. It is not a replacement NGINX,
Student application, or production guard. PASS does not yet prove NGINX
reload/restart, Suricata EVE/SID behavior under the guard, or Rust readiness.
The existing NGINX/Suricata capture harness remains unchanged. AF_PACKET counters
are not Suricata alert counts. A successful allowed case is essential to validate
the capture observation; a timeout alone never counts as proof of blocking.

Deny-only replacement proves grant revocation, **not** safety after deletion of
the entire table. No claim is made that periodic polling can close that gap or
validate delayed EVE events. A reviewed production lifecycle and event-time trust
gate remain mandatory. Keep local-egress attribution untrusted. Root, CAP_NET_ADMIN,
a compromised trusted process and handed-off socket descriptors are outside the
unprivileged-process boundary tested here.

Status: policy unit tests can run without root. Actual kernel results must be
collected from the sudo command above; do not label them PASS before reviewing
its output. No production policy/readiness integration is installed by this step.

## Lifecycle candidate and attribution safety gate

The operator reports the original six kernel prerequisite cases PASS on Ubuntu.
This is operator-supplied acceptance, not an additional run by this implementation.

`local-egress-guard.py` now owns the shared policy renderer and lifecycle primitives.
The original kernel harness imports this renderer. No host-facing installer,
background service, timer, or systemd drop-in is installed. `Guard` and `Lifecycle`
are exercised by the temporary NGINX harness; production lifecycle wiring remains
unreleased pending the following acceptance.

State transitions:

1. `arm`: refuse an existing reserved table, install deny-only boundary first.
2. `grant`: resolve the dedicated non-root worker UID/cgroup, atomically replace
   only the owned table, retain cgroup inode and actual nft JSON snapshot.
3. `ready`: compare live table expressions/order and cgroup identity. Counter and
   handle changes do not invalidate the snapshot. Missing/changed table or cgroup
   latches FAULTED; later restoration does not automatically clear that fault.
4. Reload checks before/after the owned NGINX callback. Intentional restart first
   revokes the grant and stops the owned NGINX, then resolves the cgroup again.
5. A failed lifecycle check revokes the grant and stops the owned process. If the
   table disappeared, restore deny-only. If restoration fails, stop still runs
   and the error propagates. Never flush other firewall tables or adopt one after
   a failed initial arm. No automatic restart after a fault.

**Critical distinction:** readiness is a snapshot, not a continuous proof. A
whole-table deletion can admit traffic until detection. Delete-and-restore between
checks can be missed entirely. Root/nft privilege can also defeat this policy.
Thus this manager does NOT establish transport fail-closed behavior against table
removal. A systemd watchdog or polling interval alone would not fix that claim.

Rust now categorically refuses Verified for loopback boundaries even when the
static trust flag is true. Native SIDs, tuple, XFF evidence, flow_id and tx_id are
preserved. This prevents false verification of delayed EVE from an unprotected
interval; it intentionally also withholds Verified for legitimate local traffic.
There is no fake readiness JSON that enables trust. Existing accepted vmnet3
attribution remains available with its original boundary checks.

EVE `http` may omit `app_proto` only with structured HTTP method, TCP, flow_id,
tx_id and acceptable direction. An explicit non-HTTP/null protocol is rejected.
`alert` still requires explicit `app_proto=http`. Supplemental URI detection stays
limited to HTTP request transaction records; fileinfo/native alerts are not rerun
through URI detection. Missing protocol is never synthesized in stored evidence.

### Isolated combined acceptance command

From repository root, with the same approved temporary cgroup/network scope:

```bash
python3 security-web/scripts/test-local-egress-guard.py
python3 security-web/scripts/test-egress-kernel-guard-unit.py
sudo python3 security-web/scripts/test-egress-kernel-guard.py \
  --run-isolated --with-nginx-suricata
```

Dependencies: system Python with PyYAML, nginx, openssl, Suricata, nft, ip, unshare;
Linux `nobody:nogroup` must resolve to UID 65534. The NGINX temporary master runs as
root with unprivileged workers, inside the allowed test cgroup. It retains the
existing two-server-block config, temporary TLS upstream and test ports. No
production Student, AI, PostgreSQL, or 80/443 listener is used.

Expected output, **not yet measured for the new combined harness**:

- `NGINX_LIFECYCLE`: reload and intentional restart complete with guard snapshot.
- Four real HTTP transactions captured; SQLi/XSS/Traversal SID each once.
- Forged source-bound XFF request blocked, with no corresponding EVE HTTP/alert.
- Sensor stop leaves HTTPS proxy response 204.
- Whole table deletion detected: owned NGINX stopped, deny-only restored, readiness
  remains false. This does not assert a zero-duration deletion gap.

The existing six-case kernel harness still separately covers wrong UID and same
UID/different cgroup. Combined capture currently tests a root process in another
cgroup; do not claim it independently covers every identity case.

### Current test record and remaining blockers

- Python policy/lifecycle: 7 PASS; kernel-renderer unit tests: 3 PASS.
- NGINX/TLS regression: 17 PASS (includes deliberate reproduction of insecure
  IP-only ACL in its unguarded fixture; that green test is not boundary acceptance).
- Rust attribution: 8 PASS; EVE parsing/contracts: 9 PASS; clippy/format checked.
- Full Rust suite: 49 PASS / 40 database-dependent failures at sandbox-denied
  connection setup. No database acceptance is claimed, and no database/migration
  permission was opened to make these tests pass.
- New privileged combined harness: NOT RUN; sudo requires interactive password.

Before real Student HTTPS: collect combined harness output; implement and validate
an event-time provenance mechanism or a separately enforced boundary that survives
nft deletion before enabling local Verified; then finish reviewed production
lifecycle integration. Validate Student TLS CA/SAN, Audit/request ID/session/CSRF,
and AI telemetry separately with lab fixtures. Remain on the accepted production
vmnet3/direct-HTTP topology meanwhile. Do not switch to veth or deploy automatically.

Rollback in the isolated harness is destruction of its namespace and unique
cgroup subtree. For a future production rollout, stop Egress use, restore the
reviewed direct upstream/vmnet3 profile and matching trust configuration first;
only then remove the dedicated guard. No production rollback commands are run here.
