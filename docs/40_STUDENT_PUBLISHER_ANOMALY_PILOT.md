# Final100K release and controlled publisher-anomaly pilot — 2026-11-10

**DATA_PIPELINE=PASS; TRAINING_READINESS=PASS for one bounded internal
publisher-anomaly experiment.** This does not establish independent attack-intent
quality or production readiness. No production model, system policy or source role
is changed.

[Machine evidence](../ai-training/reports/STUDENT_PUBLISHER_PILOT_20261110.json),
[fixed experiment configuration](../ai-training/configs/research/student-publisher-pilot-20261110.json),
[focused verifier](../ai-training/scripts/verify-student-publisher-data.py),
[training runner](../ai-training/scripts/student-publisher-pilot.py).
Baseline `803aabc`, branch `feature/ai-idps-shadow-integration`, initially clean;
remote matched. The completed data attempt was `recovery-a2`, worker/supervisor exit
success, thermal report COMPLETED,685.42s supervisor time, peak84°C. The earlier
failed attempts remain preserved.

## Actual data obtained

| Counter | Final result |
|---|---:|
|Source positions / parsed observations|100,000|
|Publisher HTTP observations / native technical receipts|99,927 /73|
|Feature-compatible offline588 rows|99,927|
|Quarantined|96,217|
|Deduplicated supervised-eligible records|3,783|
|Accepted GOLD /SILVER /BRONZE /UNLABELED|0 /3,783 /0 /0|
|Accepted publisher normal /anomalous|1,404 /2,379|
|Unique accepted588 views|3,751|
|Verified physical identities in source frame|73|
|Verified physical identities among training-eligible records|0|

The source-primary tiers are99,927 SILVER and73 UNLABELED. Those73 receipts are all
quarantined for this588 profile because complete source features and semantic
Oracle are unavailable. They remain UNKNOWN intent/outcome; human review PENDING.
WAF rows lack physical request/campaign/time identities. They are usable training
observations, not independently verified wire transactions.

The source publisher labels are77,141 normal /22,786 anomalous; admission changes
that balance substantially. The heavy quarantine is mainly the locked protected-role
and connected-component policy, not a GOLD-only requirement. Reasons overlap;
96,217 is the actual unique quarantine count. The fixed two-window slice is not
representative of deployment prevalence.

The3,783 accepted feature-compatible observations could also support an appropriate
self-supervised objective if labels were ignored. This is the **same pool**, not
3,783 additional observations. There are0 newly admitted unlabeled588 examples.
The selected pilot is supervised SILVER publisher anomaly, not SSL.

The full WAF frame supports offline588 only. No634 body-syntax dataset or causal207
telemetry was manufactured. Existing first-party46 events alone are not634 inputs.
Publisher body missing/empty/present availability is preserved, not asserted as
complete wire-body capture. Production live-runtime representation differs from
this publisher-input mode; no online parity/generalization claim is made.

## Focused final verification

Source/materialized and derivative-rebuild summaries are identical, fingerprint:
`977dbdff18dfb5c9aa1ced18e42abfd0080b8f994b465d3eeef0c69325548e9c`.
Both SQLite quick_checks pass with exactly100,000 distinct source coordinates.
All391 original/rebuild shards match prior hashes, are finite float32/588, and the
training index contains exactly3,783 correctly referenced rows with original labels.
Known protected code/artifact pins remain unchanged. Frozen Requestv2 and GLU207
checkpoint manifests and payload hashes were verified directly;187 small existing
pins also match. Raw sensitive metadata/arrays stay local.

Both exact weighted audits finish32,735/32,735 unique content anchors, with counts
summing99,927 and identical427,968,495 qualifying unordered original-row pairs.
Checkpoints/caches, checksums and source bindings agree. Identical-content grouping
retains pair multiplicities and does not establish physical identity. The40 prior
reliability/thermal/privacy tests and the actual4K equivalence benchmark are reused;
no full quadratic audit is repeated in this milestone.

Rebuild means exact normalized-metadata/graph/ledger reconstruction, byte-copied
features and independently computed near results. Raw feature extraction is not
repeated. Global unknown raw/campaign lineage and incompatible legacy-encoder near
coverage remain **PARTIAL**. This is not a newly certified independent test corpus.

The first private verification export failed only on NumPy integer JSON encoding,
after dataset assertions passed; it was corrected and rerun with the same criteria
and seed. That private log remains preserved. No dataset or model was selected by
changing outcomes.

## Labels and leakage scope

Publisher anomaly is the only supervised target. Intent/exploit outcomes remain
separate UNKNOWN fields. Frozen teacher manifest
`acdc0a2c9bff24fa0e4720dfcdd97e4a315e39fc625cf603e06eecc5c07a92fc`, unchanged
threshold0.8826237916946411, generated2,277 eligible auxiliary positive BRONZE
proposals; they do not replace primary SILVER and receive **zero gradient weight**
in this pilot. Across all positions:4,979 scored,2,365 proposals before quarantine,
97,635 abstentions including unscored/protected cases,23 conflicts. Rule evidence is
NOT_OBSERVED. No teacher-agreement accuracy claim.

A separate candidate split preserves the source release's staging roles. Before
any optimizer update, it joins original exact-lineage components and every eligible
content-near edge at the unchanged metric.263 near edges reduce3,652 original
eligible components to3,504 combined groups. A fixed SHA256 group+seed17 rule assigns
70/15/15 buckets; no reseeding or label/model-score-based role adjustment.
Identical588 views are canonicalized once, equivalent to inverse-view multiplicity
in the future objective; all retained source records remain in the original ledger.

| Internal role | Canonical views | Normal | Anomalous | Groups |
|---|---:|---:|---:|---:|
|TRAIN|2,667|994|1,673|2,497|
|CALIBRATION|564|206|358|523|
|EVALUATION|520|184|336|484|

Known exact/metric-near/component relations cannot cross these roles. Unknown
campaign lineage remains unverified. Features/labels were exposed for curation;
this is an internal grouped holdout, not a fresh blind or cross-domain evaluation.
2,912 eligible source records share known teacher-pretraining templates, so the
new candidate starts from **fresh random weights**, not Frozenv2. Frozenv2 may be
reported later only as an exposed-source diagnostic reference. It is not the sole
fair comparison baseline.

Split fingerprint:
`75188987ac4aa2cd4fd4c1ab6a1b9ee7d51a74a572d607c31ac5de8958bc874c`.
No sealed samples, historical DEV labels or body8 outcomes are used for gradients,
threshold selection or checkpoint selection. Source tensor/label provenance is
checked against the actual immutable shards before the experiment is frozen.

## One actual neural-network pilot

Run `student-publisher-anomaly-20261110-r1`, private root
`ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1/`.

- Existing NumPy Request Intelligence deep MLP588→64→64→64→64→8,50,696 parameters.
  Head0 means publisher normal; logits1–7 are marginalized anomaly latent bins.
  No attack-family labels are invented or supervised.
- Fresh seed17, binary partial objective, family weight0, smoothing0.005. AdamW-v1,
  lr0.001 constant, global norm clip1, W-only decay0.0001, TRAIN-only inverse class
  weights. No fitted feature statistics or frozen-encoder modification.
- Each canonical TRAIN view once per epoch, seeded group round-robin; batch64,
  10 epochs, **420 optimizer updates**.2,667 distinct gradient examples,26,670 planned
  presentations; repeated epochs are not extra HTTP observations.
- Final-budget checkpoint only, no early stopping, architecture or hyperparameter
  search. Atomic existing checkpoint library stores weights, Adam m/v and step,
  epoch/cursor, sampler permutation, RNG, scheduler and fingerprints. Library
  `best.json` is bookkeeping, not model selection.
- CAL/EVAL arrays are not loaded for training; their byte hashes may be checked for
  integrity. No CAL/EVAL gradients or normalization/calibration statistics.

**Actual preflight PASS:**2 real committed optimizer updates on TRAIN, nonzero
weight changes, step1 save/reload and next-update equality for parameters, Adam,
RNG/order and cursor.42 targeted/relevant tests PASS. Preparation was17.75s, peak50°C,
with independent watchdog and real kernel quota/freeze/thaw checks. The same run
resumes from step2 in background; this is not a second model experiment.

CPU ceiling stays20% of one core,<=8GiB RAM with4GiB system reserve; adaptive bands
85/90/93°C and effective96°C emergency/lower applicable hardware limit. No unrelated
application or hardware protection is changed. New root has its own supervised
worker/watchdog, heartbeat and global duplicate-run locks. Training completion is
verified by checkpoint step420 and successful resource supervision, not loss alone.

## Frozen future evaluation protocol

No automatic evaluation after training. On explicit user return only:

- Same-task TRAIN majority/prior baseline and TRAIN-only window/body-state priors
  as shortcut controls. Optional Frozenv2 diagnostic with pretraining caveat.
- Fixed0.5 threshold and a CAL-only balanced-accuracy threshold, highest threshold
  on ties. No EVALUATION threshold tuning or checkpoint selection.
- TP/FP/TN/FN, precision/recall/F1/AP/FPR, Wilson uncertainty; canonical/record and
  group sensitivity, per-window/method/body diagnostics, source shortcuts and noise.
- No family metrics without genuine family labels, no calibrated-confidence claim,
  no FPR<=1% guarantee from this small set. Publisher anomaly improvement does not
  establish better attack-intent or exploit detection.

The source release's construction-time `ACTUAL_TRAINING_CONSUMED=0` remains frozen;
actual model consumption is tracked separately in this run's plan/checkpoints.
The source/admitted yield is3,783/100K for this fixed frame, not a2M capacity forecast.
No500K batch is started. Future scaling follows user review of real training results.

Live evidence: `status.json`, `loss-history.json`, `model/latest.json`, `plan.json`,
`actual-preflight.json`, `attempts/train/services.json`, `thermal-status.json` and
`launch-verification.json`. Final `training-completion.json`/attempt result must be
verified when the user returns. New model artifacts remain private and unpromoted.
