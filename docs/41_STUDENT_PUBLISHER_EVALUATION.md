# First publisher-anomaly pilot: completion and evaluation — 2026-11-10

**TRAINING=COMPLETED; EVALUATION=COMPLETED.** One fresh neural network learned
SILVER publisher-defined anomaly labels and substantially outperformed the locked
same-task controls on the internal grouped holdout. This is useful research
evidence, not proof of better attack-intent detection or production readiness.
No additional training, promotion, 500K processing or system change was performed.

[Aggregate evidence](../ai-training/reports/STUDENT_PUBLISHER_EVALUATION_20261110.json),
[locked configuration](../ai-training/configs/research/student-publisher-pilot-20261110.json),
[evaluator](../ai-training/scripts/evaluate-student-publisher.py),
[metric definitions](../ai-training/src/idps_ai/training/publisher_evaluation.py),
[dataset and launch report](40_STUDENT_PUBLISHER_ANOMALY_PILOT.md).
Starting HEAD was `c9dde0e416527c6478770815069c4f2322428855`, clean, on
`feature/ai-idps-shadow-integration`.

## Completed training and checkpoint verification

Run: `student-publisher-anomaly-20261110-r1`.
Private root:
`ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1/`.

The existing supervisor exited successfully; worker, watchdog and completion
evidence agree. Inactive services and a final, non-advancing heartbeat are expected
after successful completion. This conclusion also requires the checkpoint checks
below, not merely a process exit.

- Fresh seed17 MLP `588→64→64→64→64→8`, **50,696 parameters**. Head0 means publisher
  normal; the other logits are marginalized anomaly bins, not attack families.
- **420/420 updates, 10 epochs, 2,667 canonical TRAIN views, 26,670 gradient
  presentations**. Each view occurs once per epoch through the seeded group sampler.
  The actual preflight committed2 updates; background continuation committed418.
- AdamW lr0.001, batch64, constant scheduler, TRAIN-only inverse-frequency class
  weights, smoothing0.005, family weight0, global clip1, W-only decay0.0001.
  No hyperparameter search, teacher warm-start or CAL/EVAL gradients.
- Final checkpoint: `model/checkpoints/step-000000000420-4cff462d0af0`.
  Manifest SHA256:
  `def83fbbabe7bc69464a9454d3c8a3c5daf56b3e08cbb2d74b2cd9b405d69c6d`.
  Payload hashes, finite weights/Adam m/v, scheduler step420, epoch10/cursor2667,
  architecture and parameter count pass. Replaying all10 sampler permutations
  reproduces saved permutation and RNG. Actual step1 reload/next-update exact
  continuation proof from preflight is preserved. Evaluation performs no updates.
- Dataset fingerprint:
  `977dbdff18dfb5c9aa1ced18e42abfd0080b8f994b465d3eeef0c69325548e9c`.
  Plan fingerprint:
  `3353ad863a09d7a1f508916b228a77751d0cdcdb6665d65ab54b63b0c847b28a`.
  Split fingerprint:
  `75188987ac4aa2cd4fd4c1ab6a1b9ee7d51a74a572d607c31ac5de8958bc874c`.
  Plan-bound source code and all four data/split file hashes pass.

First batch loss1.164556; last batch loss0.225523 is **not** full-TRAIN loss.
Batch-size-weighted logged epoch means are0.727964,0.464672,0.334868,0.324167,
0.272790,0.241471,0.232848,0.207443,0.220453,0.215592. Final full-partition objective
losses using the same TRAIN class weights are TRAIN0.168335, CAL0.216847,
EVAL0.197836. The checkpoint was the final fixed-budget checkpoint; evaluation
did not select a different epoch.

Background continuation took11.46s supervisor time, including startup/guard
coordination; worker CPU counter ended at1.973 CPU seconds. Peak training temperature
50°C, CPU ceiling20% of one core, sampled worker cgroup memory maximum31.13MiB,
minimum system MemAvailable18.96GiB, no OOM counters, swap use or thermal pauses.
These are sampled measurements, not a worst-case memory guarantee. Evaluation
used the same independent adaptive guardian and quota;35.68s guarded wall time,
peak56°C, completed normally. Neither run exercised the high-temperature bands.
The existing85/90/93/96°C policy and lower hardware limits remain unchanged.

## Exact reconciliation of the32 records

| Role | Retained SILVER records | Canonical588 views | Same-view aliases | Normal / anomalous canonical views |
|---|---:|---:|---:|---:|
|TRAIN|2,689|2,667|22|994 /1,673|
|CALIBRATION|573|564|9|206 /358|
|EVALUATION|521|520|1|184 /336|
|Total|3,783|3,751|32|1,384 /2,367|

All32 records remain in the original accepted ledger:20 normal and12 anomalous.
Each has exactly the same588 view and publisher label as its canonical
representative. They were neither lost, quarantined nor reserved. Canonicalization
prevents duplicate gradient weighting. The private alias map records each source
row, representative and unchanged role. No split was changed for this evaluation.

## Locked evaluation results

The anomaly score is `1-P(publisher_normal)`. Predictions use strict `score > t`.
Both precommitted operating points are reported: fixed0.5 and maximum balanced
accuracy on CAL only, highest threshold on ties. Candidate CAL threshold:
**0.3641684055328369**. `evaluation-v1/thresholds.json` was persisted before
EVAL tensors/scores were loaded and remained unchanged. No EVAL threshold fitting,
new optimizer updates, fitted feature statistics or checkpoint selection occurred.
Source labels were previously exposed for curation; this ordering does not make
the holdout blind.

| Partition / operating point | Precision | Recall | F1 | AP | FPR | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---:|---|
|TRAIN / CAL threshold|97.44%|93.31%|95.33%|0.99191|4.12%|953 /41 /112 /1561|
|CAL / CAL threshold|97.59%|90.50%|93.91%|0.98496|3.88%|198 /8 /34 /324|
|EVAL / CAL threshold|**96.34%**|**94.05%**|**95.18%**|**0.98881**|**6.52%**|**172 /12 /20 /316**|
|EVAL / fixed0.5|97.76%|90.77%|94.14%|0.98881|3.80%|177 /7 /31 /305|

Confusion matrices have rows true normal/anomalous and columns predicted
normal/anomalous. EVAL CAL-threshold matrix is `[[172,12],[20,316]]`.
Nominal Wilson95% intervals: precision93.72–97.89%, recall90.99–96.11%,
FPR3.77–11.05%. These assume independent trials and do not certify source selection,
group dependence or label accuracy. No FPR≤1% claim is supported. CAL metrics
describe the fitting partition and are optimistic for its selected threshold.

| Same-task control, EVAL | Precision | Recall | F1 | AP | FPR |
|---|---:|---:|---:|---:|---:|
|TRAIN majority/prior, fixed0.5|64.62%|100%|78.50%|0.64615|100%|
|TRAIN body-state prior, CAL threshold|64.69%|91.07%|75.65%|0.65263|90.76%|
|TRAIN source-window prior, CAL threshold|64.69%|91.07%|75.65%|0.64686|90.76%|

For completeness the constant-prior control at its CAL-balanced threshold predicts
all normal: recall0/F10/FPR0, precision undefined, AP0.64615. Highest-threshold
tie-breaking produces this degenerate point; it does not make the control useful.
The body/window controls make the same binary decisions here but rank scores
differently. Candidate discrimination is substantially better than these controls.
Frozen Requestv2 was not used for a numerical same-task improvement claim:
different label semantics and known source pretraining overlap make that comparison
unsuitable as independent detection evidence. No teacher-label accuracy is reported.

### Group, source and method sensitivity

All evaluated examples come from WAF; there is no second qualified source for a
cross-source comparison. The two original source windows are not environments.
At the candidate CAL threshold:

| Stratum | Rows | Normal / anomalous | FP / FN | Precision | Recall | AP |
|---|---:|---:|---:|---:|---:|---:|
|Source window0|473|167 /306|12 /16|96.03%|94.77%|0.99046|
|Source window1|47|17 /30|0 /4|100%|86.67%|0.97644|
|GET|500|178 /322|9 /19|97.12%|94.10%|0.98947|
|POST|12|2 /10|**2 /1**|81.82%|90%|0.96515|
|Body MISSING|464|166 /298|11 /16|96.25%|94.63%|0.99024|
|Body EMPTY|47|17 /30|0 /4|100%|86.67%|0.97644|
|Publisher body present, wire completeness unverified|9|1 /8|1 /0|88.89%|100%|1.00000|

The other8 rows comprise OPTIONS5, PATCH1, PUT1, TRACE1; aggregate JSON preserves
their counts. Both publisher-normal POSTs are false positives. The count is too
small for a stable POST FPR estimate and the labels are not proven benign intent.
Window1's0/17 normal false positives still has Wilson upper bound18.43%.
The sole normal body-present record is also a false positive. Present-body and
POST results cannot establish robust body-based discrimination.

Giving each of484 recorded EVAL lineage/near components equal total weight yields
precision96.06%, recall93.75%, F10.94893, AP0.98785, FPR6.98%: the main result is
not driven only by a few large groups. Reintroducing the one EVAL alias gives521
records, matrix `[[173,12],[20,316]]`, AP0.98879, FPR6.49%. Canonical results remain
primary. Group weights are a sensitivity analysis, not a new independent test.

TRAIN AP0.99191 versus EVAL0.98881 and the objective gap do not show a large aggregate
collapse. They also cannot rule out memorization or source-specific shortcuts:
same-source publisher artifacts, method imbalance and missing bodies remain.
Beating window/body priors rules out those priors as a complete explanation; it
does not identify which content/header features cause the predictions.

Labels are SILVER publisher anomaly, not verified attack intent or exploit outcome.
There is no family Ground Truth, so SQLi/XSS/command-injection recall is unavailable.
Known exact and metric-near relations respect the frozen split. Global campaign,
time/raw lineage and incompatible legacy-encoder near coverage remain PARTIAL.
Human review remains PENDING. No independent cross-domain claim or Rule/AI overlap
is inferred. The original optional teacher has2,912 accepted-record template overlaps;
the candidate was initialized fresh and used zero teacher gradients.

## Why100K positions yielded3,783 records

The following waterfall is exclusive; it sums to100,000:

| Disposition | Positions |
|---|---:|
|First-party reference-only: no complete588 inputs/semantic target|73|
|Protected or label-conflicting connected component|96,115|
|Exact representation duplicate outside the blocked components|29|
|Accepted SILVER publisher records|3,783|

The99,927 publisher rows parse and support the offline588 contract; no publisher
label-invalid category explains the rejection. Across the full frame, reason flags
overlap: exact duplicates16,292; protected existing role94,948; protected template/
view/route75,719; protected current-contract near61,734; protected/conflict component
96,115. **Do not add these counts.** Mixed-label keys:4 request-representation keys
and206 full feature-view keys. These are conflicts, not evidence that a model can
recover a missing identity signal. Privacy exclusions were not relaxed.

Weighted near audit covers32,735 distinct content vectors representing99,927 rows,
with427,968,495 qualifying unordered row pairs. A content match does not mean an
independent physical request match. Eligible-only near closure has263 edges and
reduces3,652 exact components to3,504 groups; it controls splitting rather than
simply deleting all near-related eligible examples.

Accepted source tiers: GOLD0/SILVER3,783/BRONZE0/UNLABELED0. Source-primary tiers
before quarantine: SILVER99,927/UNLABELED73. Accepted classes are normal1,404 /
anomalous2,379, whereas source classes are77,141 /22,786. This selection bias matters.
Teacher proposals remain auxiliary, never counted again as additional accepted
labels. The same3,783 pool could be used without labels for SSL, not added twice.
The source has73 verified first-party physical identities; accepted WAF training
records have **zero verified physical identities**, which means unverified, not
that the publisher observations are fabricated.

Eligible-record yield is3.783%; canonical-view yield3.751%; actual TRAIN-gradient
view yield2.667% of source positions. Two fixed source prefixes and conservative
legacy exclusions make this a poor population forecast. It is not a reason to
promise that a500K batch will yield18,915 or to weaken quality gates.

### Specific evidence of possible over-filtering

`student-data-pipeline.py::protected` uses `all_protected=True` for both legacy
numeric-only/content-v1 corpora. That protects even historical TRAIN templates,
as a conservative response to incompatible older encoders; modern common-contract
protection separately retains held-out roles. This is broader than merely keeping
historical evaluation out of training, but is not proof that every exclusion is wrong.

A read-only role/template diagnostic found71,415 legacy TRAIN-only template keys
after removing all known CAL/DEV template keys.66,153 current quarantined positions
match them;30,557 lack a direct current-contract protected-near flag. Screening
their whole current components for known held-out template keys and current-near
flags leaves **27,235 candidate positions for requalification**. This is an upper
candidate count, **not newly admissible records**, unique views or recovered yield.
Protected views/routes, legacy near comparability, conflicts and raw lineage still
need resolution. No admission rule or source decision changed in this milestone.

## 2M capacity and cost reassessment

Reuse the [hash-bound source inventory](34_AI_IDPS_2M_DATA_SCALING_READINESS.md)
and [student policy](37_AI_IDPS_STUDENT_2M_DATA_PIPELINE.md); no new all-source census
or download was performed. WAF publisher TRAIN has1,924,461 rows and historically
1,612,017 exact representations before current exclusions, including192 conflicting
representations and312,443 duplicate extras. It falls short of2M by75,539 positions
or **at least387,983 exact representations**, before label/role/near/privacy losses.
The historical representation-plus-duplicate counts differ from the row total by
one; that old discrepancy was not resolved by a new full-source census here.
Treat these capacity numbers as hash-bound historical evidence, not a newly exact
arithmetic partition or an admitted capacity guarantee.

Open-appsec has811,129 nonreserved rows /756,548 historically retained signatures,
with its existing supervised-fit restriction unchanged. It cannot simply be added
as publisher-anomaly supervised capacity. SR-BH/WAMM derivatives and telemetry copies
also cannot be added as independent requests. Cross-source additive qualified
capacity and2M verified physical requests remain unestablished. The current verified
accepted release is3,783 SILVER records; it is not a global repository census.
This release supports offline588, not live body634 or causal GLU207/207.

Processing is the bottleneck observed here, not the50K-parameter pilot. Historical
ingestion was approximately41 positions/s at20% of one core: conditional linear
ingestion alone is about41min/100K,3.4h/500K,13.6h/2M, excluding preparation,
audits, rebuilds, failures and IO changes. Recovery-a2 took685.42s for near/finalization
and derivative rebuild after ingestion was already complete. Its two exact near
passes were about188s and171s. Unique-vector exact pair work can grow quadratically;
20× as many unique vectors means roughly400× pair work, not20×. The current sample
does not justify a full2M completion-time guarantee or a dense pair-matrix allocation.

Float32/588 features alone require4.704GB decimal at2M rows, before shards, indices,
copies and model buffers. Keep8GiB worker cap/4GiB system reserve; a larger job
would need bounded/chunked loading, not assume all arrays and copies fit. At2M
canonical examples and a conditional70% TRAIN share,10epochs/batch64 imply218,750
updates and14M presentations. Scaling the measured background workload by
presentations alone gives roughly1.7h at the same quota, **not a validated budget**:
cache/IO/sampling/checkpoint costs and thermal duty cycle differ. No GPU or larger
model is required by the evidence from this small pilot. No2M training is authorized
or launched here.

## Engineering decision: exactly one next milestone

**Choose A — improve yield without weakening quality.** Perform one bounded,
role-aware requalification of the existing100K legacy-TRAIN-only exclusion
candidates into a **new versioned derivative**. Preserve every original artifact,
all known CAL/DEV/evaluation/sealed protections, conflicts, privacy rules and exact/
near deduplication. Resolve the reason for each candidate's exclusion rather than
removing `all_protected` globally. Do not use this EVAL's predictions to select
recovered rows or change the finished experiment.

Completion criterion: one provenance-bound decision ledger with recovered SILVER
records/canonical views and exact remaining exclusion reasons, plus split/near
integrity checks under an explicit new contract. If legacy near compatibility or
lineage cannot be resolved, retain quarantine and quantify that blocker; stop after
this finite frame.27,235 is only a diagnostic ceiling, never a target to force.
No automatic retraining or500K batch is part of this recommendation.

The measured publisher signal is already stronger than simple controls, while
rejection policy dominates yield and source capacity is finite. Multiplying the
same processing policy to500K before resolving this ambiguity risks spending most
of the budget on avoidable exclusions. Thus500K expansion is **DEFERRED**, and2M
usable-example capacity is **NOT_ESTABLISHED**. POST and label-quality weaknesses
remain documented; they do not justify an unplanned second model experiment now.

## Evidence, tests and preservation

Private checkpoint, Adam/RNG state, loss history, source ledger, alias map, per-record
scores and watchdog logs stay local. Public JSON contains aggregate metrics and
fingerprints only. Original training `status.json` still says evaluation NOT_RUN
because it is a preserved training-time snapshot; this report and the new private
`evaluation-v1/metrics.json` record the separately authorized completed evaluation.
37 relevant tests passed this turn across student data, split/sampler/checkpoint,
adaptive thermal, pipeline reliability, scaling admission and new evaluation metrics.
Ruff passes for the evaluator, metric module and its tests. The three new metric
tests cover CAL-only tie/comparator behavior, AP under ties, Wilson bounds, group
weight sensitivity and invalid inputs; no optimizer is exercised by evaluation.

Both frozen model manifest/payload hashes and187 nonsealed small preservation pins
were checked unchanged; one sealed-named pin was deliberately skipped. Frozenv2,
GLU207, Requestv3 checkpoints, thresholds, Web/Nginx/Suricata/Rules/Policy/correlation,
strict datasets and published Releases remain unchanged. No sealed access, AWS,
enforcement, production inference change or model promotion. Team clone/bootstrap/
model restore/local inference does not require this private research corpus.
