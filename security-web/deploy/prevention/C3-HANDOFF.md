# Controlled Prevention source/test handoff (NOT production deployment)

Migration0017 adds key metadata (no secret), persistent verdict journal, execution
intent/state and audit. Migration0016/0017 remain SOURCE ONLY. New binary auto-runs
pending migrations: do not start it against production. Phase B binary stays untouched.

## AI intake contract

POST /api/prevention/ai-verdict under existing authenticated Admin RBAC, plus independent
HMAC. Envelope: {"payload":"<exact UTF-8 JSON string>","mac":"<64 hex chars>"}.
MAC is HMAC-SHA256 over ASCII `WebSentinel-AI-verdict-v1` + NUL + exact payload bytes.
Payload<=4096 bytes, version1, issuer,key_id,epoch,nonce(32hex),alert_id,generation(32hex),
flow_id(string),tx_id,request_id(string or null),client_ip,issued_at/expires_at UTC seconds,
recommend_block=true. Unknown/duplicate payload fields rejected. Do not reserialize
between signing and sending. Dedicated service identity provisioning is deployment work;
this revision uses the existing Admin authentication contract, no anonymous endpoint.

AI_VERDICT_KEY_DIR is unset by default: fail closed. key_id only alphanumeric/hyphen;
key file must be regular, exactly32bytes, mode0600 or stricter. Provision protected
parent directories accessible only to trusted backend/key administrators; do not place
keys in repo or a shared writable directory. Database registry key_id maps authorized
issuer/epoch, activation/expiration and revocation. Rotate using a NEW key_id/key file,
then revoke old metadata; retain nonce journal, never clear it to rotate. Runtime secret
provisioning is not performed here. Key registry metadata changes are privileged DB
operations, not exposed as general API. Parent directory/DB/root administrators are
inside trust boundary; DB rollback protection is outside this source guarantee.

TTL<=60s; future/expired invalid. HMAC constant-time verify_slice. Client must already
be independently Verified; eligibility and exact alert/sensor generation/flow/tx/rid/IP
binding required. Null request ID matches only null; no guessed IDs. Registry/alert/link
rows locked during validation. PostgreSQL UNIQUE(key_id,nonce)+advisory lock makes retry
atomic: identical valid payload returns same ID, changed payload rejected. Replays after
expiry/key revocation fail even if previously accepted. Journal survives backend restart.
No Worker, verdict or trusted identity => no accepted authorization. AI does not enqueue,
call firewall or change Client IP. Intake audit persists accepted and rejected decisions
without raw payload/MAC/key; journal stores bounded binding metadata and digest only.

## Worker/actuator seam

controlled_prevention::step is shared non-test worker logic, called with a supplied
Actuator. Only supplied production implementation ClosedActuator ALWAYS refuses; no
scheduler/HTTP execution route is started. Existing block/unblock/enqueue/legacy worker
remain hard-closed. Integration tests call the same step with isolated Fake actuator,
not a separate policy simulator. Connecting a real actuator later is explicitly a new
production enablement review, not an env switch in this revision.

Each step locks proposal; checks current approval/reviewer,5minute expiry/freshness,
policy version, current verified identity, protected scope, alert age<=300s, exact AI
binding, AI expiration/key/epoch/verdict revocation. Source policy remains C2-v2,
private addresses denied. Changing flags from OFF/auto=false DENIES rather than enables.
No network_src_ip fallback. Repeated step for ACTIVE yields no second action.
Unique proposal execution and unique verdict prevent cross-proposal verdict reuse.

Durable intent is committed before actuator call; on retry same ID/IP/deadline is used.
Deadline is approval timestamp+requested TTL (max300s), never retry time. Actuator MUST
be idempotent by proposal ID and set absolute deadline/no timeout renewal. Calls bounded
by5s; unknown outcome is ERROR, not success. DB commit failure after external success
requires same idempotent retry. Exactly-once external effects are not claimed.

Rollback/expiry/revocation routes through same step using the recorded original IP,
not a newly supplied target. Cleanup intent is latched before external call, survives
failure/restart, cannot become BLOCK on retry. Repeated terminal cleanup does nothing.
Audit stores intent/decision/outcome. C3 currently stores separate controlled execution
state; it does not report simulated operations as real blocked_ips or alter alert action.

## Tests and runner

`python3 security-web/scripts/test-lua-shadow-postgres.py --c2-regression`

Uses fresh PostgreSQL17 container, tmpfs/no production mounts, generated credentials,
no caller DATABASE_URL. All migrations and complete Rust regression run there. Container
removed on exit. No nftables invocation. Includes real HTTP/RBAC; approval/review races;
legacy bypass; signed concurrent intake/idempotency/conflicting nonce; persistent reuse
across verifier instances; key epoch/revocation; expired verdict; worker error/retry;
unchanged deadline; revoked client cleanup; obsolete policy; TTL expiry and durable
rollback latch; ClosedActuator refusal. Existing external-PCAP test remains ignored
because it requires its separate fixture (not introduced by this task).

Source ready means member can implement sender against this intake and exercise signed
lab fixtures without touching production. It does NOT mean production protection is
active or that current Unverified local-egress alerts can block. Actual OS actuator,
key provisioning, new migration deployment and service identity require separate explicit
production approval; they are intentionally not enabled by this handoff.
