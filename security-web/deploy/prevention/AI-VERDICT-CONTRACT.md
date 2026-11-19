> Superseded for integration by [C3-HANDOFF.md](C3-HANDOFF.md). The text below documents the earlier test-only prototype.

# AI verdict interface proposal — test-only, NOT runtime-ready

Prototype lives in ai_verdict_contract.rs under cfg(test); no Worker implementation,
HTTP endpoint, production key or execution authorization. Existing AI Shadow remains
independent and deferred. A recommendation is never a client identity proof.

Transport contract: UTF-8 JSON bytes <=4096, reject unknown/duplicate fields, HMAC-SHA256
on ASCII `WebSentinel-AI-verdict-v1` + NUL + EXACT received bytes. Authenticate before
parsing; no independent JSON reserialization/canonicalization across languages.
Required fields: version=1, issuer, key_id, epoch, nonce, alert_id, generation, flow_id
(string to preserve64-bit value), tx_id, request_id, client_ip, issued_at/expires_at
(integer UTC seconds), recommend_block. TTL<=60s; reject future/expired proofs.
Bind every field to independently loaded alert/transaction and verified client identity.
Missing Worker/verdict, bad MAC, wrong binding or Unverified client cannot authorize.

Prototype key id lab-key-v1 is test-only. Runtime must resolve key_id from an authorized
issuer/key registry, not caller supplied material. Separate signing key from NGINX
proof key. Restrict key to Worker/verifier identities, rotate atomically and revoke old
keys with defined bounded in-flight validity. Do not log MAC/key or expose secrets.

Current prototype nonce HashSet tests duplicate rejection only within process. NOT
acceptable for runtime: persist unique issuer/key/epoch/nonce plus verdict digest and
bound decision transactionally, enforce expiry/capacity, retain replay tombstones for
validity window, test concurrent/reordered delivery, crash/restart, rollback and key
revocation. Root/DB rollback remains a trust-boundary question. Epoch is fixed trusted
configuration per acceptance window, never accepted just because sender requested it.

Only after durable replay, issuer authentication, key lifecycle and persisted binding
are integrated and tested may runtime use verdict. Auto approval/execution still needs
fresh shared eligibility and independent deployment authorization. No static true flag
or cfg(test) exception may enable production firewall gate.
