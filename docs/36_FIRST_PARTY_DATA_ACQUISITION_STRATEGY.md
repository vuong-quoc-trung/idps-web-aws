# First-party data acquisition strategy — 2026-11-10

**CASE B — SOURCE EXISTS, GROUND TRUTH INSUFFICIENT.** Select the existing owned
**Student live-ingress acceptance capture20261108**, rather than retry a blocked
external source. It offers native request identity, application audit and observed
body features, but no complete request-bound intent/Oracle label package. Therefore
**no admission pilot, new strict requests or training** in this milestone.

[Machine evidence](../ai-training/reports/FIRST_PARTY_SOURCE_QUALIFICATION_20261110.json).
[Exact collector intake specification](FIRST_PARTY_RAW_LABEL_INTAKE.md).
Starting branch `feature/ai-idps-shadow-integration`, HEAD `9e323c9`, clean.

## A. Source availability and authority

This was a bounded, read-only investigation of existing first-party manifests and
one retained capture, not another23-source inventory. No Biblio/network retry,
container startup, database query, HTTP request or collection campaign was performed.
The selected source is a deliberately generated, isolated owned Student fixture
stack, not unclassified real-student/browser or production traffic.

Authority is the current source-qualification instruction within the previously
authorized controlled-lab scope, corroborated by its precommitted fixture plan,
producer source pins and retained capture reports. Read-only private qualification
and existing private retention are permitted; this is not permission to redistribute
sensitive logs or process arbitrary production data merely visible on disk. Any
future production export requires that owner's actual data-use authorization.

| Existing evidence considered | Verified use/limit |
|---|---|
| Selected Student body-live acceptance | Fresh metadata reconciliation:73gateway IDs,73matching application audits,32body events; no semantic label decisions |
| Earlier real three-source acceptance | Prior report12receipts with native generation/flow/tx correlation; technical evidence, not independent attack GT; not joined to the selected later capture |
| Native GLU train derivative | Previously documented41,607train rows/scenario attribution, already reused; not new physical/qualified data; no full reread |
| Existing Oracle236 + exposedbody8 | Preserved; request IDs used only as known-reference metadata, not reassigned/recounted as new data |
| Earlier Juice factory/pilot | Metadata retains33factory requests (28benign/4attempt/1unknown) and8earlier requests; old research claims/purpose preserved, no new novelty or admission asserted here |

Smallness or a prior fit/evaluation gate alone does not invalidate an individual
Oracle label. Historical Oracle cohorts remain useful evidence. The Student source
was prioritized for its existing native application/body path and potential to
support a repeatable first-party workflow, not because other cohorts were silently
relabelled invalid. No global verdict on all historical request admissibility is made.

## Identity, coverage and the actual Ground Truth gap

The selected source's retained gateway file has **73 distinct source-issued request
IDs**. All match Student audit by ID/method/route/status. Student has75audit events;
two non-gateway events are excluded from the gateway count. Its67helper records
cover32OFF +32ON +3failure-phase requests, with6additional direct failure requests
in the73gateway total. Never add these numbers or multiple streams together.

All67helper records lack semantic `intent`, `outcome`, `oracle_verified`,
`label_source`, and `review_status`. Their `label` field is a **technical test name**.
More importantly, every one of the75Student audit outcomes matches the rule
`failure if status>=400 else success`. The implementation is explicit in
[AuditJsonlExporter](../student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/service/AuditJsonlExporter.java)
(line112). This is not attack intent, exploit outcome or verified benign behavior.

The pinned [acceptance code](../ai-training/scripts/validate-real-body-ingress.py)
does assert the fixture identity after login and authentication denial after logout
(lines761–780). That is partial application-state support, stronger than a generic
status check. But the retained per-request helper metadata stores status/parity,
not the corresponding redacted expected/actual Oracle facts or supervised intent
provenance. Do not infer that every request is benign from a whole-run PASS.

The32existing body events passed the current immutable46-field contract. They
contain only **11distinct feature views**: MISSING17, OK8, EMPTY1, MALFORMED2 and
one each unsupported-type/encoding/transfer and oversize. The41other requests have
no corresponding body event; OFF or deliberately dropped observations do not mean
the actual wire body was MISSING/EMPTY. Native timestamps exist on73gateway and75
application records. Session/actor metadata stays private; grouping aliases do not
establish independent campaigns. OFF/ON intentionally repeat the same workflows.

No selected request ID overlaps the enumerated236+8reference IDs. This is useful
identity evidence, **not** raw/template/near-duplicate clearance or proof of new
independent evaluation data. The capture is already exposed engineering evidence.

## B. Bounded admission

`PILOT=NOT_RUN_SOURCE_GT_INSUFFICIENT` — authorized metadata exists, so this is not
`NOT_RUN_NO_AUTHORIZED_SOURCE`. No qualifying RAW+LABEL package was available for
this selected source. Source discovery examined73gateway metadata identities and32
existing numeric events; it did **not** execute an admission/model pipeline.

| Admission result | Value |
|---|---|
| Candidate records processed by admission | 0 |
| Source identities verified in discovery | 73 |
| New strict eligible / new quarantine release | 0 / none created |
| Main blockers | Missing request-bound semantic intent/Oracle package; source event availability and role/lineage mapping still require qualification |
| Exact content/near/campaign overlap | NOT_RUN; no index-saturation or independence claim |
| Frozen588 /634 materialization | NOT_REVALIDATED; historical inference parity is not a source-wide new dataset contract |
| Body46 | 32existing events valid, not32new supervised examples |
| GLU207 | Not supported by this capture: retained correlation stream empty, no real matched sensor proof; earlier Suricata evidence cannot be borrowed |
| Rebuild/throughput/yield | NOT_RUN / not measured / unknown |

A private **73-row collector queue** was produced from existing IDs and references,
with UNKNOWN semantic intent/outcome, no assigned dataset role, no model scores or
admission decisions. It is a finite evidence handoff, **not** a staging dataset or
independent-review approval. Original records/labels/roles remain unchanged.

## C. Two-million feasibility

Separate capacities: current new strict0; publisher-labeled capacity in this owned
fixture source0; auxiliary engineering observations73 with32numeric events. These
are not additive pools. The earlier verified strict pilot pool remains74, so its
arithmetic gap to2M is1,999,926; global qualified capacity/shortfall remains unknown.
Even complete labels for this single capture would not establish10K availability,
representative request novelty, independent campaigns or balanced attack coverage.
No verified attack-family distribution exists for these technical test cases.

| Stage | Source-dependent condition; no capacity promise |
|---|---|
| ≤73existing requests | Obtain actual request-bound semantic ledger and retained Oracle/review references, then qualify separate exposed staging; unknowns remain unknown |
| 10K | Requires separately authorized new data, varied genuine sessions/workflows and grounded benign/attack evidence; repeats of OFF/ON/canaries do not fill the count |
| 100K | Not supported by existing volume; requires measured yield across additional authorized campaigns/time periods, stable Oracle semantics and grouped roles |
| 500K | Requires new source/application capacity and bounded qualification evidence, privacy/lineage and independent validation coverage |
| 2M | NOT_ESTABLISHED; requires verified source supply and label/Oracle capacity, not row-processing throughput |

Simple application predicates can eventually automate known-fixture state checks,
but only when the expected/actual facts are recorded with native request IDs.
Blindly mapping exporter outcomes, detector flags or response codes would scale
weak labels, not Ground Truth. Owner/operator truth and difficult semantic review
remain real dependencies. No large acquisition/training is initiated here.

## D. One next action

**Complete one collector-provided semantic evidence ledger for the existing73IDs.**
Use the [exact intake specification](FIRST_PARTY_RAW_LABEL_INTAKE.md) and private
queue `.local-dev/first-party-source-20261110/collector-intake-pending.jsonl`.
Bind original intent plus retained redacted expected/actual Oracle proof or genuine
review decisions. Leave unrecoverable cases UNKNOWN; no fabricated historical
responses and no recapture to repair the old evidence. Then run at most73through
the unchanged admission profile in a later request. No independent human review
is demanded as a substitute for valid research-tierA Oracle evidence.

This is the smallest improvement for the selected accessible source. No external
owner contact or approval message was sent. We do not request a new hypothetical
production archive while this finite existing-evidence gap remains explicit.

Private evidence hashes and authority/feature limits are recorded in the machine
report. All examined source pins remained unchanged; no source, web/system,
correlation/admission policy, model, threshold, old dataset/role or release edits.
No training, AWS, enforcement, sealed access or sensitive publication. Only docs
and aggregate metadata are committed; no new framework/tests are needed.
