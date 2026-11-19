# Live transaction proof acceptance — pending operator execution

`test-live-transaction-proof.py` reuses the njs Stack, TLS Student mock,
Suricata local-egress profile, selective Lua logger and Rust offline verifier.
It creates no synthetic PCAP and never issues a proof in Python.

The harness checks 68 real Edge requests (4 sequential including the three
custom signatures, then 64 requests in bounded concurrent batches), actual
upstream keepalive, real EVE timestamps and a fresh generation per sensor
invocation. It replays an actual captured Edge proof and attempts XFF, request
ID and MAC tampering. It checks no proof/receipt reaches the mock or client,
checks each SID once, and runs the existing Rust batch tests on captured data.
Rust negative batch tests mutate captured evidence; they are NOT live network
failure injection. No production Verified path is enabled.

## Run after authorization

From repository root, the operator can run the wrapper as an ordinary user:

```bash
bash security-web/scripts/run-live-transaction-proof.sh
```

It builds Rust without root, then prompts for sudo only for the isolated capture.
An optional first argument specifies an already extracted njs module. No package
is installed. Alternatively, build as the ordinary user (no database connection):

```bash
cargo test --offline --manifest-path security-web/Cargo.toml --no-run --message-format=json > /tmp/websentinel-test-artifacts.jsonl
WS_TEST_BIN=$(python3 - <<'PY'
import json
from pathlib import Path
rows = [json.loads(s) for s in Path('/tmp/websentinel-test-artifacts.jsonl').read_text().splitlines()]
paths = [r['executable'] for r in rows if r.get('reason') == 'compiler-artifact' and r.get('profile', {}).get('test') and r.get('executable') and r.get('target', {}).get('name') == 'pbl4-security-demo']
assert len(paths) == 1, paths
print(paths[0])
PY
)
sudo unshare --net -- python3 security-web/scripts/test-live-transaction-proof.py \
  --isolated-root \
  --module /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so \
  --rust-test-binary "$WS_TEST_BIN"
```

The extracted module must already exist; this does not install/load a module in
production. Root is used only by this disposable test process tree. The harness
refuses the host network namespace and any namespace with interfaces other than
`lo`. It adds 192.0.2.10 only inside the namespace and listens on temporary Edge/
mock ports plus isolated 18080. Configuration, keys (0600), certificates and logs
live in a temporary directory and are removed on exit. Only aggregate evidence
is printed. Rust uses the prebuilt binary, avoiding a root-owned Cargo build.
No host firewall, cgroup, service, database or `/etc` changes are made.

Where unprivileged user namespaces are supported, the alternative is:

```bash
unshare --user --map-root-user --net -- python3 security-web/scripts/test-live-transaction-proof.py \
  --module /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so
```

## Acceptance status and gaps

Prepared, not live-executed in this change. A final PASS line only covers the
assertions above, not the entire user acceptance plan. Do not report complete
E2E acceptance based on syntax checks or prior synthetic-PCAP tests.

Still required: combined kernel guard deletion under load, live restart/epoch
rotation in this capture, aborted requests and incomplete responses, explicit
live missing/invalid receipt injection, and long-delayed conflict handling.
Current Rust verification resolves a complete batch; it does not provide durable
streaming replay state or retract a previously published Verified result.
Generation is associated with this isolated sensor process by the harness; a
production authenticated sensor-generation lifecycle is not implemented.
Same-UID key access remains possible. Double-HMAC comparison in njs has functional
tests, not a proven constant-time implementation. Root/NGINX compromise is outside
the unprivileged spoofing guarantee. Runtime Client IP Verified remains disabled
for local egress.

## Nonprivileged regression checks in this revision

- Observed EVE indexing: 3/3 PASS (duplicates rejected, keepalive transactions
  distinct, alert/fileinfo excluded as HTTP observations).
- Rust suricata_origin: 8/8 PASS.
- Rust events::tests: 7/7 PASS.
- Python compilation, shell syntax and git diff whitespace checks: PASS.
- Live capture: NOT RUN; operator chose to run privileged steps themselves.

## Follow-up: failure-mode results (2026-11-17)

The operator reports the original 68-transaction live capture PASS. This is
operator-provided acceptance, separate from the reruns below.

Executed non-root isolated njs harness with real temporary TLS sockets:
- Replay, altered XFF/Request-ID/MAC, missing/expired proof: PASS.
- Reload retains nonce state: PASS.
- Restart without rotation: negative control reproduces replay vulnerability.
- Restart and whole-master/workers crash with new epoch/key: PASS.
- Missing key, unsafe permissions, full nonce dictionary: fail-closed PASS.
- Same-UID child process reads the 0600 key: reproduced; KEY ISOLATION FAIL.
  A dedicated worker UID excludes other users, not malicious same-UID processes.
  No claim that file permissions alone close this threat model.
- Timing: NOT VERIFIED. Randomized double-HMAC string comparison is not an
  audited constant-time primitive; functional results are not timing evidence.

Rust test-only journal uses append + sync_all before acknowledgement. A full
recovery/recompute with actual njs receipts (synthetic-PCAP bridge, 64 transactions)
passes, including a late conflicting receipt revoking an earlier candidate.
Truncated/corrupt journal recovery fails closed. This is a SINGLE-WRITER test
prototype, not a production durable replay service: no directory fsync on initial
creation, locking, bounded retention, authenticated journal, rollback protection,
key archival policy, or downstream revocation API is implemented. Do not wire this
into runtime Verified. No key is stored in journal records; proof metadata is
sensitive and the temporary journal is 0600 and removed after testing.

SID 1000001 is `TCP SYN Burst Threshold`, `flags:S; flow:stateless;
threshold:type both, track by_src, count 10, seconds 5; priority:2; rev:4`.
Concurrent Edge connections may legitimately trigger it. It counts network SYNs
per proxy source, not individual attacker HTTP requests. Its presence alone is
neither a duplicate capture finding nor proof of a legitimate threshold crossing.
The 68-transaction uniqueness and single occurrence of each SQLi/XSS/Traversal
SID are separate checks. Definitive threshold acceptance still needs observed
SYN tuple/sequence counts over the corresponding 5-second window; no raw packet
trace was retained from the operator's run in this session.

Still NOT accepted: delete the real UID+cgroup guard during live load, interrupted
request/incomplete response tests, live missing/invalid receipt injection,
combined capture plus restart/rotation. Do not substitute deletion of an empty nft
table or a UID-only policy for that test. Previous authorization is for preparing
privileged commands for the operator, not executing them automatically.

## Dedicated identity and journal follow-up

Added optional identity renderer and `DEDICATED-IDENTITY.md`. njs now has an opt-in
managed key layout (root-owned 0640 key, exact nonzero GID, root-owned 0750 parent,
no key symlink); default private 0600 fixture mode is preserved. The normal njs
suite and 64-transaction offline bridge PASS after this change. Managed layout
with real privilege separation is NOT yet accepted; same-UID compromise remains
inside the boundary and timing remains unverified.

Journal prototype now serializes writers with an atomic create-new sidecar lock,
syncs the journal and parent directory, rejects unsafe existing permissions and
partial/corrupt state, and caps size at 16 MiB. A crash leaving a stale lock blocks
further writes pending operator recovery. No automatic retention/reset exists.
This supersedes the earlier missing-directory-fsync/locking notes. It still lacks
rollback-resistant anchoring, authenticated storage and production revocation.

Live harness now keeps the sensor running through graceful NGINX restart and
key/epoch rotation, attempts the captured old proof again and requires 403 with
no receipt or mock request. Rust verifies the earlier capture using its archived
old test key; processing delay must not be confused with replay acceptance by the
new Egress epoch. This new live branch has only passed syntax checks and awaits
operator execution; no new live PASS is claimed.

Runtime admission gates: privileged managed-key/UID isolation accepted; real guard
deletion under load accepted; aborted/incomplete response semantics and live
missing receipt accepted; live restart AND crash/rotation accepted; durable
conflict revocation and rollback policy specified/tested; timing review accepted
or explicitly excluded by documented threat-model decision. Until then local
Verified stays disabled. An acceptance receipt proves Egress accepted a request,
not that the entire response body completed; these states must not be conflated.

## Extended operator acceptance

Run as the normal user (the wrapper asks for sudo only for isolated execution):

```bash
bash security-web/scripts/run-live-transaction-proof.sh \
  /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so --extended
```

Reuses the existing outer kernel harness. It creates ONLY its unique temporary
`ws-egress-test-*` cgroup subtree on the host and a disposable network namespace;
all nft changes, NGINX, Suricata and TLS mock traffic stay in that namespace.
The subtree and test processes are cleaned up. No account, production service,
database or host firewall configuration is changed. The test uses numeric
65534/nogroup as a temporary worker identity, NOT as a proposed production account.
Key DAC is tested with real UID/GID changes and empty supplementary groups.

New assertions awaiting operator execution:
- UID+cgroup guard initially denies a foreign socket; the actual guard table is
  deleted during four concurrent valid Edge requests. Subsequent invalid proofs
  and replays must be rejected by njs without mock delivery/receipt. After policy
  deletion rejected HTTP CAN be captured; it must not be accepted/Verified.
- Root-owned group-readable key works for the fixture worker, denies another UID.
  Same-UID read remains explicitly allowed by the threat boundary.
- Partial client headers are aborted without delivery to the mock.
- Truncated response and deliberately suppressed receipt are passed as negative
  observations to Rust, which must produce no Verified candidates.
- Graceful restart followed by whole-master/worker crash, each with fresh key and
  epoch while the sensor stays live, must reject the old captured proof.

`response_complete` is now required for a candidate (missing defaults false).
In these tests the harness supplies it from controlled fault cases. This is NOT
an implemented trusted runtime completion signal. Egress acceptance receipt alone
does not attest full body completion. Mid-body client aborts and arbitrary network
truncation still need broader acceptance beyond the partial-header case.

Journal: repeated identical adjacent observations are idempotent; contradictory
observations remain fail-closed. Existing append/sync/lock checks and negative
receipt tests remain. Durable storage is still not rollback-resistant: restoration
of an old valid journal cannot be detected without an independent trusted anchor.
No production Verified path or downstream revocation mechanism has been enabled.
Timing of njs HMAC comparison remains UNVERIFIED, not PASS.

## Case-level reporting correction

The former `pending: operator execution of new fault cases` was a literal string,
not execution state. A 72-transaction extended PASS ran the fault code, but did not
provide independent case statuses. This is corrected with required-case tracking:
each case starts NOT_RUN, becomes PASS only after assertions, and failures emit
FAIL with error type (no proof/key content). Overall PASS requires ALL required
cases PASS. Non-extended runs cannot claim extended acceptance. Python `-O` is
refused because it would disable assertions. Scope limitations are separate from
pending execution; empty pending does not mean production-ready.

Additional corrections:
- Before deletion the mock holds four valid requests until the harness observes
  all four and deletes the real guard table. Previous futures alone did not prove
  temporal overlap.
- Missing receipt is tied to its own request ID and status 204, not just ANY one
  of the two negative transactions. Its response_complete is true, so Rust must
  reject for absent receipt rather than the incomplete-response gate.
- Incomplete response remains a distinct controlled negative observation; partial
  body is observed as IncompleteRead or upstream failure 502.
- Restart/crash and rotation each report separate results. Crash requires observed
  worker PIDs. Replay after crash still uses the original pre-restart proof; a
  proof freshly accepted immediately before crash is not tested.
- Aborted request scope is partial headers and no mock delivery; mid-body abort
  is not tested. Same-UID isolation, timing proof, journal rollback and runtime
  completion-signal provenance are not claimed PASS.

Nonprivileged reporting/index regression tests: 7/7 PASS. Extended live rerun is
operator-required; use the existing --extended command above. Expected final JSON
has `cases`, dynamically computed `pending`, and `runtime_readiness: NOT_ACCEPTED`.
