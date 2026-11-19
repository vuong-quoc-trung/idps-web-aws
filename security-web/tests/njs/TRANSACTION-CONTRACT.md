# Transaction proof v1 — isolated test contract, NOT runtime authorization

Request wire: base64url-no-padding(UTF-8 compact JSON array) + '.' + lowercase
hex HMAC-SHA256(key, ASCII('ws-request-v1:') || encoded-body).
Array order is EXACTLY:

[1, key_id, epoch, nonce, client_ip, request_id, method, scheme, host,
 target_sha256, issued_ms, expires_ms]

Receipt uses the same wire encoding with domain 'ws-receipt-v1:' and array:

[1, key_id, epoch, nonce, sha256(full-request-wire), 'accepted', accepted_ms]

Keys are 32 random bytes; key_id is 1..64 ASCII alphanumeric/hyphen; epoch, nonce
and request_id are 32 lowercase hex chars. Times are integer Unix milliseconds
<= 2^53-1; expires-issued = 60000; future skew <= 1000 ms. The nonce dictionary
retains entries for 65000 ms, with no eviction. Full storage fails closed.
Limit each wire to 4096 bytes. Reject malformed/noncanonical base64url, invalid
MAC, unexpected field count/types, alternate JSON spacing/escaping and nulls.
No decode/re-encode of an untrusted URI is used as the request-target identity.
Target digest is SHA256 of original request_uri bytes (percent escapes and query
order retained). Do not put query strings in the proof output. ASCII lab request
targets only are currently exercised; arbitrary Unicode/HTTP parser ambiguities
remain outside acceptance. This is metadata attribution, NOT body authentication.

Host is the original HTTP Host value including port, without lowercasing or
removing the port. The Edge fixture explicitly preserves $http_host to avoid
$host normalization causing signature mismatch. Scheme is literal http/https.
Methods are uppercase token subset; client IP must be a canonical non-loopback,
non-unspecified/non-multicast IP for offline Rust acceptance. Runtime IPv6
normalization needs additional tests. HMAC authenticity never replaces comparing
XFF, X-Real-IP, request ID, method, scheme, Host and target digest at Egress.

The JS fixture overwrites proof from Client; Egress clears proof/receipt before
TLS mock upstream; Edge hides receipt from Client. Receipt means authenticated
admission, NOT successful Student processing or completed response delivery.
No receipt on refusal. MAC comparison uses randomized blinding in njs 0.9.4;
Rust uses hmac::Mac::verify_slice. JS timing behavior is not independently proven.

## Sensor envelope and offline join

Selected Lua output is a separate TSV stream, never appended to EVE. Columns:
flow_id, tx_id, proof, receipt, XFF, request_id, forwarded scheme, Host.
Control chars and values >4096 bytes become missing. The offline test launcher
adds a fixed test sensor generation; production needs a fresh trusted generation
per sensor lifecycle. Do not infer transaction IDs from line order or timestamps.
Match sensor generation + flow_id + tx_id, with HTTP method and target from EVE.

The Rust module is cfg(test) ONLY. It resolves COMPLETE finite batches. Every
transaction claiming a reused valid nonce is rejected, independent of ingestion
order; identical replay of the same EVE/proof row is idempotent. Conflicting rows
for the same transaction or multiple observations are rejected. No current clock
or kernel-guard snapshot grants historical trust. Known key_id/epoch selects a
verification key; historical keys must remain available according to retention.
Streaming storage, restart persistence and retracting a prior decision after a
late conflict are NOT implemented. Existing runtime local Verified remains off.

## Actual integration evidence / limitations

Run test-njs-proof.py with --proof-chain and extracted --module. It reuses the
existing Edge/Egress TLS harness. Edge signing is smoke-tested separately. For
64 offline bridge transactions Python creates request proofs, actual njs Egress
verifies and returns receipts, then those exact artifacts are placed in synthetic
PCAP. Real Suricata Lua/EVE output is passed to Rust via a private 0600 fixture.
Thus this is cross-language integration, NOT live NGINX-to-Suricata capture.
The 64 bridge requests are sequential on NGINX; separate tests run 64 concurrent
requests. The synthetic PCAP exercises 64 keep-alive transactions on one flow.

Synthetic PCAP uses historical timestamps and disabled checksum verification.
The bridge explicitly supplies issuance time as observed_ms; clock provenance,
delayed packet timestamps and sensor/EVE timestamp semantics are NOT proven.
Rust reverse-order batch checks do not simulate a durable streaming ingest outage.
No claim of 64 concurrent live transactions captured and verified end-to-end.

Unresolved acceptance: live capture with real clock provenance; trusted generation
and tuple validation; request abort/partial response; SQLi/XSS/Traversal in this
new proof chain; policy deletion transition with proof enabled; production key
isolation from same UID; arbitrary malformed/duplicate headers; clock jumps;
streaming nonce conflict persistence and response receipt replay by privileged
injectors. Root/compromised NGINX is not covered. Do not enable Verified.

Only test dependencies hmac/base64 are added. No runtime integration, migrations,
service installation, firewall changes or production module loading occurs.
