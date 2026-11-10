# First-party RAW+LABEL intake — research handoff, not a new admission policy

This specifies an owner/collector export. It does not authorize collection,
retroactive relabeling, model training, redistribution or a production change.
Use the existing [attack-intent schema](../ai-training/src/idps_ai/data/attack_intent.py),
[evidence validator](../ai-training/src/idps_ai/data/label_evidence.py) and
[strict research profile](../ai-training/configs/research/http-scaling-admission-20261109.json).
No second framework or replacement formal-review gate is introduced.

## Required package

| Content | Minimum evidence |
|---|---|
| Source and authority | Source/controller alias, operational owner, explicit permitted data use/retention, access/recipient scope, expiry/deletion conditions if applicable; production exports need their actual owner's authorization |
| Environment | Application/build/config fingerprint, capture instance, fixture versus production declaration, source-native ID issuance/uniqueness semantics |
| Capture frame | Actual start/end/timezone, ordering and clock resolution, fixed source version and ≤10K selection frame; no score-based selection |
| Original identity | Capture-scoped original gateway/app request ID; retain its source reference. Import row/sample ID is separate. If native ID is absent, provide original event/order/transport evidence sufficient to establish distinct requests; row number alone is insufficient |
| HTTP metadata | Method/target or approved projection, selected-header availability, actual observed body state, response/observation time when available; no invented fields |
| Telemetry correlation | Exact source references and request-ID linkage. Sensor generation/flow/tx required only when claiming that sensor's correlation. Multiple streams/copies do not add request counts |
| Grouping | Original session/workflow/campaign relationships with approved opaque surrogates; unknown stays unknown. A case name/phase is not independent campaign evidence |
| Intent | BENIGN_INTENT / ATTACK_INTENT / UNKNOWN_INTENT, collector provenance and original planned action; payload shape, response status or absence of alerts cannot assign intent |
| Outcome | Existing attack-intent outcome enum, separate from intent: BENIGN_SUCCESS, VERIFIED_EXPLOIT_SUCCESS, VERIFIED_FAILED_ATTEMPT, UNSAFE_REFLECTION, UNKNOWN_OUTCOME, NOT_APPLICABLE |
| Application Oracle | Request-bound expected and actual redacted facts, predicate version/source hash, execution receipt, artifact checksum/reference. Example: known fixture identity before/after login, invalidated session after logout, expected object state after CRUD. Generic200/401 or exporter success/failure is insufficient |
| Label confidence | Existing research evidence levels/tier and why they apply. A needs real intent+Oracle support; B needs genuine reviewer provenance. C/D/E do not silently become verified intent |
| Reviewer, if used | Actual reviewer/collector identities or controlled aliases, independence and decision provenance; no AI agent or automated check represented as human review. Formal human review retains its existing validator requirements |
| Unknown handling | Explicit missing/conflicting evidence, no eligible-for-fit default, no guessed benign label; preserve rejected/excluded rows as graph bridges |
| Feature contract | Exact version/fingerprint and per-record availability. Keep source/actor/session/status labels out of request features. No padding207 or inference from missing event to missing wire body |
| Privacy | Keep credentials/tokens/cookies/email/sensitive values local and restricted. Prefer existing numeric body-syntax events and redacted Oracle facts; raw sensitive bodies need not enter training artifacts. Do not export per-secret hashes as a substitute |
| Integrity | Immutable manifest with per-file hashes, original source references, script/contract hashes, ordered selection fingerprint, permitted-use evidence and stable private lineage key/ordinal namespace |
| Exposure/roles | Preserve original engineering/DEVELOPMENT/prospective purpose and prior exposure. Do not make an exposed capture a new blind holdout. New eligible records first go to separate versioned staging under a precommitted role plan |

`OBSERVATION` must retain technical facts separately from `INTENT`, `OUTCOME` and
`LABEL_CONFIDENCE`. In this project's Student exporter the lowercase observation
`outcome` is a status-class convenience; it is **not** the uppercase semantic
outcome in the research schema.

For missing body events distinguish at least: observation disabled, deliberate
transport/consumer drop, source unavailable, and an actual extractor MISSING or
EMPTY event. Only the real event may carry its recorded body-syntax state. Do not
fill all OFF requests with an all-zero/MISSING vector. Raw response persistence
is not necessary if an immutable redacted expected/actual Oracle receipt is saved.

## Current finite handoff

Selected source: `student-live-ingress-20261108-acceptance-v1`, existing owned
Student fixture capture. Current intake queue:
`.local-dev/first-party-source-20261110/collector-intake-pending.jsonl`.

It contains **73 original gateway request IDs**, source references, technical
observations, engineering phases and privacy-safe grouping aliases. Every semantic
intent/outcome remains UNKNOWN; no dataset role or eligibility has been assigned.
There are no scores, raw bodies, cookies, usernames, IPs or session digests in the
new queue. The actual original source remains private and unchanged.

**The single requested collector deliverable** is a request-bound semantic ledger
for these same73IDs, with original intent provenance and existing redacted Oracle
proof or genuine review evidence. Recover only facts supported by retained evidence;
leave unrecoverable rows UNKNOWN. Do not reconstruct supposed responses from the
expected code, sign fictitious review decisions or issue new requests to repair the
past. Generic whole-run PASS is not a substitute for the missing per-request proof.
A human review is not mandatory for properly supported research tierA Oracle labels.

Once that package is actually complete, use the existing strict graph/dedup/privacy
rules for a bounded **≤73** staging qualification. The new package must not change
old labels, dataset roles or the frozen74-record pool. Current OFF/ON repetitions,
one fixture environment and eleven body views do not justify10K or100K capacity.
No new capture, label decision, admission or training is started by this document.
