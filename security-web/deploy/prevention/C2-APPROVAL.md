# C2 — approval records, no execution

Not deployed. Migration0016 is SOURCE ONLY (tested in disposable PostgreSQL17).
Starting a new backend against production would automatically apply it: NOT authorized.

New routes (existing authentication plus explicit Admin check):
- POST /api/prevention/proposals: alert_id, reason(1–500), idempotency_key(alphanumeric/hyphen <=64), ttl_seconds(1–300).
- GET /api/prevention/proposals: latest100 with audit history and expired boolean.
- POST /api/prevention/proposals/{id}/review: approve boolean, reason.

Proposal creation loads actual alert client_ip, never caller IP or network_src_ip.
Shared C1 policy denies unverified, private/loopback/protected targets; Shadow status
cannot grant verification. C2 still requires OFF/auto false. ALLOW is PROPOSED;
other decisions persist DENIED/REVIEW. Proposal expires after5minutes; ttl_seconds is
future block TTL, NOT an active firewall timeout. All responses execution_allowed=false.

Admin reviewer must differ from creator for approval. Review locks proposal FOR UPDATE,
locks current alert FOR SHARE, reevaluates shared policy and rejects changed client IP.
Expiry checked again after waiting for locks. Only one concurrent reviewer succeeds.
APPROVED_DRY_RUN is a terminal historical decision, not executable authorization;
GET separately reports expiry even for terminal decisions. Future execution must never
trust this state without fresh evidence and policy evaluation. C2 has NO execution
transition, so policy changes after approval cannot cause an actuator call.

proposals + decisions are inserted/updated atomically. Persistent audit includes actor,
reason, evaluated reasons/client and timestamps. No token/proof/key accepted as fields;
operators must not paste secrets in free-text reasons. Invalid inputs, RBAC rejections,
self-approval and repeated terminal review return errors (not durable approval decisions).
No separate HTTP rejection audit introduced. Idempotency replay returns original row;
changed payload under same key rejected; advisory lock and UNIQUE serialize retries.

Execution barriers:
- Legacy POST blocked-ips / DELETE blocked-ips/{ip}: reject before enqueue.
- firewall::enqueue: closed for direct callers.
- process_one: returns before DB dequeue or executor callback even if mode changed.
- firewall::run: mutation actions blocked; read-only list-json preserved.
Existing automatic SQL producers may still write jobs if policy is misconfigured;
worker cannot execute them in C2. Keep AUTO_BLOCK=false. Never replay accumulated jobs
in C3 without audit/revalidation/expiry. Existing restore/TTL machinery is retained,
not an authorized execution route. No nftables add/delete was performed.

Compatibility: historical enforcement tests expecting successful enqueue/execution
under MANUAL/ENFORCE now conflict with the deliberate C2 execution lock. This work
ran targeted C2 tests, not the entire legacy PostgreSQL suite; do not claim full CI
acceptance. Those tests must be separated into pure actuator contract tests and C2
closed-gate expectations before shipping this branch. Do not re-enable execution
under cfg(test) or runtime flags merely to make old tests pass.

Tests actually run:5 pure policy/input tests; isolated PG17 runner --c2 runs2 DB tests
and1 pure lock test (3PASS). DB cases cover migration0016, Admin-only handlers, durable
create/decision audit, retry idempotency, independent reviewer, trust revoked before
approval, concurrent review serialization, expiry and zero firewall jobs. No production
DB used, disposable container removed. Auth middleware reused; complete HTTP route
integration/RBAC matrix and DB audit failure injection remain required before C3.

C3 gates: finish legacy test compatibility and API coverage; durable security audit for
rejected approval attempts if required; trustworthy Client IP independent of Lua Shadow;
review native evidence/freshness (C1 native label is not cryptographic proof); refreshed
host/admin/gateway inventory; explicit scope policy (private still denied); transactionally
re-evaluate approval/evidence/IP/policy at execution; TTL starts at authorized execution,
absolute deadline survives restart; idempotent audited unblock only approved target.
C2 prepares TTL and existing rollback mechanisms but intentionally disables real unblock
too. Separately authorize any live deployment. AI stays deferred; no Verified change.
