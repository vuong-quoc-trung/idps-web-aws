# R26.2: trusted context information proof

This research adapter supplements the **unchanged URI100 lane** with a separate
20-field current-request context lane. It does not replace authorization or any
serving model. RI v2 remains the default; R20 remains the existing shadow.

`context.py` is the Python ABI reference. `context_rust` is a bounded, offline
Rust projector over the same private collector envelope. The JSON protocol is
**not** an authentication mechanism: the binding argument must come from the
project-owned correlation registry and verified receipt custody, never a client.
There is no newly exposed HTTP endpoint or inference service.

## Trust and time

The existing Student `SecurityRequestFilter` derives principal/role from
`SecurityContextHolder`, and its `AuditJsonlExporter` pseudonymizes actor/session
with a private HMAC key. The collector reads the project-owned Audit file and
validates producer scope, native event ID, method/route, trusted edge request ID,
correlation proof and clock bounds using the existing T04/T08 pipeline.

`collector.py` sanitizes context, encodes the vector **while HTTP collection is
running**, and timestamps completion after encoding. New source arrivals create
immutable versions. Finalization selects a version matching the final cutoff
view; data arriving later cannot make a missing feature observed at the cutoff.
The 1,000 ms cutoff and 1 ms guard remain fixed. Oracle runs after the drain and
is ground truth only. Early draft captures are retained separately and are not
counted as proof of final vector materialization.

Only protected GET `STUDENT_DIRECTORY` / `SELF_PRINCIPAL` context is supported.
This is advisory inference **by the cutoff after request processing**, not an
inline pre-authorization guarantee. Login/logout/CSRF and unsupported routes
are WITHHELD. Owner relationship remains GROUND_TRUTH_ONLY. Session age and
history are WITHHELD. There is no principal cache or inferred revocation state.
Missing, late, untrusted or unavailable context abstains; zeroes carry a state
mask and never mean observed benign.

No raw IDs, HMACs, cookies, credentials, request status, authorization decision,
current outcome, Oracle label or response latency enter the vector. Actor/session
HMACs are checked in memory and discarded. Their full source-envelope hash and
request-bound proof references are retained privately for custody.

## Execution and recovery

`capture.py` reuses R261/R8 KVM, NGINX, Suricata, H2, BCrypt warm-up, parallel
collector, trusted request identity and JDBC Oracle. Each invocation requires a
fresh owned directory; it never redispatches an attempted checkpoint. The
session-switch mode uses six setup/principal requests in one cookie jar.

`session_transport.py` fixes the *lab Oracle*: a valid existing HttpOnly session
does not need a fresh Set-Cookie on each CSRF GET. Existing-session continuity is
recorded separately, without changing the original Set-Cookie observation. CSRF
format validation, subsequent real login, JDBC mutation and session rotation
remain mandatory. No application authentication or authorization was changed.

The Resource Adapter permits only one managed allocation per user. Run capture,
build and verification **serially**. A simultaneous attempt was refused before
worker/HTTP creation and is preserved. Another capture stopped at the old CSRF
Oracle. Recovery uses a fresh campaign identity and a finite amended budget;
there are no endless retries, no restart of a safety-stopped attempt.

`final_checks.py` serializes offline build, Rust unit tests, raw-envelope parity
and `reconcile.py`. It sends no HTTP and performs no training. Reconciliation
verifies old receipts and new semantic witnesses, raw URI100, receipt digests,
context availability, Rust vectors, frozen-model scores and historical hashes.
Run files and exact execution sources are private in the artifact namespace.

## Scope of acceptance

Final real panel: 3 authorized / 3 unauthorized same-method/URI record accesses,
plus two principal controls. Known policy control separates the panel; that is
**deterministic control, not independent ML detection**. URI-only, role-only and
availability-only information censuses expose the corresponding ambiguities.
No learned decision rule is selected using these labels.

The captures share policy/templates/actors and form one conservative lineage
component. Canonical TRAIN/DEV/CAL/TEST remains zero. No random-row split, model
fit, calibration, production deployment or promotion is performed. The 90%/1%
quality target, seven-mask production coverage and T07 confidence gates remain
BLOCKED. Current result: `CONTEXT_PROOF_PASS_DATA_INSUFFICIENT`.

Tests distinguish synthetic trust/fault schedules from real HTTP. Logout,
revocation and concurrency are fixture-only controls; no claim of live
revocation or concurrent HTTP acceptance is made. Rust context parity on native
frames is offline replay, not an always-on Rust context service. Unchanged B16
ONNX/URI100 parity and RI/R20 restart/fallback acceptance are inherited from R261
and R22.1; healthy serving workers are not restarted for this research task.
