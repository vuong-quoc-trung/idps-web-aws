# C1 Controlled Prevention — eligibility only

Endpoint (after separately approved future deployment):
`GET /api/alerts/{id}/block-eligibility` using existing authenticated session.
Admin and Viewer may read. Existing auth middleware rejects unauthenticated callers;
no approval endpoint is added. JSON contains ALLOW/DENY/REVIEW, reason codes, policy
version, alert ID, evaluation time, candidate client IP, proposed300-second TTL.
`execution_allowed=false`, `approval_enabled=false` ALWAYS, including ALLOW.
No SQL write, firewall invocation, enqueue, approval persistence or runtime deployment.

Policy C1-v1:
- Missing/unverified client identity -> DENY regardless of MATCHED_SHADOW.
- Use client_ip only, never src_ip/network_src_ip fallback.
- All private, IPv6, loopback, non-unicast IPs -> DENY. This intentionally excludes
  current private lab attackers as well as internal hosts. No lab exception in C1.
- Reuse firewall::validate: discovery must succeed, IP must be in allowed scope,
  not a discovered host/gateway, protected address, trusted proxy or IP_WHITELIST.
  Operator must include remote admin addresses in IP_WHITELIST before later enforcement.
- Only verified, safe native-SID-labelled SURICATA severity1/2 gets eligibility ALLOW.
  Rule label is persisted detector metadata, not new proof of cryptographic identity.
- Other sources, weaker severity or missing native label -> REVIEW after mandatory
  identity/protection checks. AI score never authorizes blocking.
- Mode not OFF or auto-block enabled -> DENY for this C1 endpoint.

Default enforcement subnet scope is private networks; C1 additionally denies private
IPs. Therefore default runtime has NO ALLOW candidates. Do not widen runtime scope
merely to produce ALLOW. Unit tests inject explicitly safe targets to test ALLOW.
Production local-egress is Unverified and remains DENY, which is expected acceptance.

Reused existing components: auth::guard, firewall::validate/network::Safety, source
alert table. Existing manual block route remains unchanged and independent of C1;
C1 is NOT a security retrofit for that route. Existing actuator returns without
processing when mode OFF. No claim that C1 approves or audits an actual block.

C2 preparation (not enabled):
1. Admin approval must bind alert ID, exact client IP, policy/version, evidence snapshot,
   actor, reason, decision timestamp and absolute expires_at. Re-evaluate source/IP,
   discovery, evidence freshness and trust at approval AND execution; reject stale or
   revoked proposals. GET output must never become a bearer authorization token.
2. Persist approval/rejection in existing audit architecture; review migration need
   separately. Dry-run GET currently writes NO audit row. Do not store proof/secrets.
3. Reuse firewall_actions with actor/event_id/reason/deadline and existing blocked_ips
   TTL handling; do not create a second actuator. Review existing manual routes to
   prevent bypass before C2. Unverified local-egress stays ineligible.
4. Rollback uses existing audited UNBLOCK of exactly approved target, never flush rules.
   Review OFF-mode behavior and expiry/restart restoration before enabling manual mode.
5. C2 gates: trustworthy client identity independent of Shadow, explicit lab scope
   policy (private targets currently denied), admin/gateway inventory, durable approval
   audit and replay/freshness checks, isolated integration/RBAC tests, then separately
   approved live reversible block/unblock. No automatic transition to C2.

C1 limitations: API JSON only (no Dashboard control added), no persistent proposals,
no admin approval writes, no C2 freshness/revocation workflow. Pure-policy unit tests
cover decision boundaries; PostgreSQL/API authenticated runtime tests not executed.
Production Phase B and its candidate binary are unchanged.
