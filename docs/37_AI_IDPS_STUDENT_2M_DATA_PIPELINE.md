# AI_IDPS_STUDENT_2M_DATA_PIPELINE — 2026-11-10

The new `student-training-v1` profile permits imperfect labels for student research.
It is separate from the unchanged strict attack-intent admission profile. **No model
training, promotion, inference change or new capture is part of this milestone.**

[Machine-readable prelaunch evidence](../ai-training/reports/AI_IDPS_STUDENT_2M_DATA_PIPELINE_20261110.json).

## Policy and task semantics

[Versioned policy](../ai-training/configs/research/student-training-v1.json).
GOLD requires request-bound Oracle or genuine review provenance. Independent human
review is not required for an otherwise valid research Oracle label, but remains
PENDING where no reviewer exists. SILVER retains the publisher's documented task.
BRONZE is a versioned weak-label proposal, never verified Ground Truth. UNLABELED
has no supervised target; a future self-supervised objective must be separate.
Intent, exploit outcome and observation availability are separate facts.

This pilot uses publisher normal/anomalous labels as **SILVER publisher_anomaly**.
It does not translate anomalies into attack intent or manufacture benign intent.
Teacher agreement cannot upgrade SILVER to GOLD. The primary tier and an auxiliary
BRONZE proposal are counted separately, never as two training examples.

The lecturer's updated requirements supersede the earlier requirement for new
strict labels as the only scaling route. Earlier strict-profile results remain
valid for that profile; their zero new WAF yield is not a student-profile verdict.

## Frozen source frame

Baseline `29563213513ff4de1714192945dbb6a1f193c978`, branch
`feature/ai-idps-shadow-integration`; remote matched at execution start.
No score-based sampling. The maximum frame contains **100,000 positions**:

- Existing first-party intake: 73 native gateway identities. One reconciliation
  pass found no retained request-bound semantic Oracle reference. They stay
  UNKNOWN intent/outcome and UNLABELED; the original receipts are unchanged.
  A later preparation retry reuses this reconciliation, without recapture/review.
- Pinned WAF publisher train: first 49,964 positions of row group 0 and first
  49,963 of row group 1, namely global rows `0..49963` and
  `1048576..1098538`. These 99,927 observations are not a representative random
  population sample. Seed 17 is recorded; selection itself is deterministic.

WAF revision `b035dc17f875f1f732c10654709abed66a4e9742`, Parquet SHA256
`3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6`.
The pinned publisher card declares MIT; research processing is authorized, raw
redistribution is not performed. No Biblio retry, new download or publisher test
access. Source/config/code/key/teacher bindings are persisted in private `plan.json`.

SOURCE_ROWS, PARSED_HTTP_OBSERVATIONS, VERIFIED_PHYSICAL_REQUESTS, compatible
features, deduplicated examples and unique feature views are separate counters.
The WAF source has no verified physical IDs/campaign clock. Import coordinates
are provenance, not wire identities. Rebuilding the same frame does not add new
observations. The 73 known identities are source accounting, not 73 newly eligible
supervised examples or independent campaigns.

## Representation and privacy

WAF supports version `student-http588-rich-v2-publisher-v1`: frozen bounded numeric76
plus frozen `rich_request_v2` unsigned char3–5 content512/shared L2, float32.
This is the existing **offline publisher-input** mode, including publisher-supplied
body and headers. It differs from the live runtime's selected-header/body-absent
prefix. No fitted statistics or encoder modification. Missing/empty/present header
and body metadata remain distinct, even where the frozen vector conflates states.
Publisher body availability is not proof of complete wire capture or parse success.
No 634 body-syntax or causal207 features are fabricated. The first-party technical
receipts lack complete retained588 input and are reference-only for this release.
Their existing46 events are not padded into588/634 rows.

Feature projection reuses existing value exclusions. Private request/raw/view/group
identifiers use a run-keyed HMAC; raw HTTP and native IDs do not enter the staging
ledger. Metadata has a strict allowlist and bounded feature paths. Identity key,
reconciliation receipts, teacher scores, arrays and per-example manifests remain
local/ignored. Only code, tests, policy and aggregate documentation enter Git.

## Leakage, duplicates and scope

The existing disk-backed AdmissionIndex supplies transactional cursors and the
request/representation/view/template graph. A separate StudentIndex policy retains
excluded bridge nodes and propagates protected flags across exact components.
All known legacy-v1 sampled template/view groups are excluded conservatively, as
are current-v2 CAL/DEV groups/views and the known grounded/first-party route scope.
Runtime-compatible content is compared against the236/body8 references. No sealed
prospective data is opened; reference checks do not use labels to tune a policy.
Known v2 TRAIN template reuse is recorded as teacher-pretraining overlap.

Full publisher-representation duplicates retain the earliest source coordinate.
Mixed-label exact representations or588 views quarantine every connected member;
there is no majority vote. Distinct representations with the same compatible view
may remain, with inverse accepted-view multiplicity for a future loss. Feature
equality does not prove identical physical events.

The old capped LSH is not used. Common-contract protected near comparison uses
blocked float64 content cosine >=0.995, tolerance1e-7, before teacher scoring.
The intra-frame audit also uses bounded blocks, without a full pair matrix or
candidate-bucket cap. Near similarity is not semantic identity; variants in a
single TRAIN role are counted, not falsely called distinct physical requests.
**Global raw/campaign lineage and incompatible legacy-encoder near coverage remain
PARTIAL.** This release is exposed TRAIN staging, not independent evaluation.
The older DEV and body8 cohorts remain historical diagnostics; they cannot establish
fresh quality. Existing original roles and strict admission artifacts remain intact.

## Frozen teacher and abstention

Frozen Request v2, step3072, 50,696 parameters, checkpoint manifest bound at prepare
and process restart. Parameters are read-only, zero optimizer updates. Its unchanged
operating point is `score > 0.8826237916946411`.

Only positives above that operating point may create an exploratory BRONZE proposal.
A publisher-normal/teacher-positive disagreement is conflict + abstention, without
changing SILVER. All teacher-negative cases abstain: no independently justified
negative-confidence cutoff exists. Missing publisher labels could receive a BRONZE
`teacher_high_risk_proxy` primary target; this is not attack intent. With fully
publisher-labeled WAF, eligible primary labels remain SILVER and BRONZE is auxiliary.
Scores are not calibrated PPV/confidence. Same-source pretraining is disclosed.
Rule evidence is NOT_OBSERVED. Agreement with publisher anomaly is not trusted-label
accuracy, and evaluating the teacher against its own labels is prohibited.

## Execution, recovery and acceptance

Code: [pipeline](../ai-training/scripts/student-data-pipeline.py),
[student extension](../ai-training/src/idps_ai/data/student_training.py),
[supervisor wrapper](../ai-training/scripts/student-data-supervisor.py).
Reuses the existing resource guard, active-work thermal monitor, independent
systemd watchdog and RunLock. A global pipeline lock rejects simultaneous workers.
SQLite commits <=256 observations and extension metadata atomically; cursor recovery
uses committed SQLite, not stale JSON. Numeric shards are atomic and immutable;
an orphan with different bytes fails closed. Resume rejects changed bindings.

The planned actual boundaries are512,4096,100000. A fresh process resumes after each
boundary. A separate rebuild processes the **same100000** coordinates. Completion
requires identical semantic summaries, byte-identical ledgers, training indexes
and all numeric shards, plus unchanged source/teacher bindings. Never infer PASS
from row count alone. `completion.json` and a PASS resource report, followed by
`supervisor-result.json: COMPLETED`, are required for verified final completion.
Status RUNNING alone is not completion or usable yield. The worker writes a1s
heartbeat, phase, incremental progress, logs and failure state. No automatic retries
or further data expansion. A timeout/thermal stop preserves committed data.

Preparation at100% of one core was emergency-stopped: peak95°C,1.10s,0WAF candidates,
about186MiB cgroup peak. The one reduced-load retry uses **20% of one core**, up to
8 affinity CPUs, one math thread, <=8GiB job cap, >=4GiB system reserve, no swap.
The instantaneous cutoff remains85°C, active300s average must stay<80°C, proactive
throttling starts near77–78°C. Idle cannot dilute active averages. Sensors/watchdog
must remain healthy. No unrelated application or hardware protection is changed.
The initial95°C event remains part of the report, never hidden in successful averages.
The background job deadline is10800s; further thermal failure stops the milestone.

Versioned private root:
`ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2/`.
The earlier failed preparation root `...-r1` is retained. Final values are in
`completion.json`, `materialized/summary.json`, `resource/resource-report.json` and
`supervisor-result.json`. No eventual100K counts or final PASS are asserted here.

## Future learning and 500K/2M scaling

Start with separately normalized GOLD intent and SILVER publisher-anomaly objectives
(coefficient1 each where available), not one silently merged attack target. Optional
BRONZE distillation starts at coefficient0.1 as an explicitly unvalidated heuristic;
UNLABELED has zero supervised weight. Apply inverse-view multiplicity and monitor
source/method/body shortcuts. A later controlled pilot must compare publisher-only
supervision with the same data plus weak supervision, under an independently locked
evaluation protocol. No such training is authorized in this milestone.

[Prior source inventory](34_AI_IDPS_2M_DATA_SCALING_READINESS.md) is reused, not repeated.
WAF capacity is1,924,461 source rows and a hash-bound historical1,612,017 exact
representations, before current conflict/protected exclusions. This is VERIFIED
source-frame/historical-audit capacity, **not verified student-admitted yield**.
Open-appsec has811,129 nonreserved rows/756,548 historically retained signatures,
with its existing supervised-fit restriction; consider UNLABELED/SSL subject to its
contract, not unrestricted supervised benign. Cross-source additive capacity remains
UNVERIFIED. SR-BH/WAMM share lineage and cannot simply be added as independent data.

| Stage | Capacity and expected composition | Cost and completion condition |
|---|---|---|
|100K positions|73 UNLABELED reference receipts +99,927 WAF SILVER observations; actual eligible/aux BRONZE yield comes from the pilot|Measured completion/guard metrics, deterministic resume/rebuild and disclosed partial lineage|
|500K positions|Within WAF source frame; estimated SILVER-led pool, exact yield not yet known|Next fixed disjoint source windows; cumulative protected/raw/view graph and full protected-near checks; no LSH cap; use measured pilot throughput/storage with headroom|
|1M positions|Within WAF source frame; historical duplicates suggest row count overstates yield|Streaming shards/SQLite remain suitable; replace quadratic intra-frame audit with verified blocked/exact-vector or scalable search, explicitly PARTIAL if incomplete; no random row holdout|
|2M positions|WAF alone is75,539 source rows short; at least387,983 short of2M distinct representations even before exclusions|Qualify additional authorized source capacity and cross-source lineage; no promise of2M admitted examples or physical events|

For500K/1M/2M, projected feature bytes start at `eligible_count*588*4`, plus measured
ledger/index overhead and rebuild copies; compression ratio must be measured.
At1M, rawfloat32 features alone are2.352GB; at2M4.704GB (decimal), not peakRAM.
Future duration estimates must use measured100K phase throughput and protected-index
size, not linear extrapolation of an O(N²) audit. GOLD is the preserved separate
research pool, not synthetic volume added to WAF. Physical2M capacity is NOT_ESTABLISHED.

**One next action after pilot verification:** lock and process a disjoint cumulative
500K WAF frame using the measured student-profile yield/cost, retaining task semantics,
existing evaluation protection and explicit global-lineage limits. No automatic
500K execution, training, model promotion or change to team bootstrap.
