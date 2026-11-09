# Request v3 frozen-backbone experiment — 2026-11-09

**COMPLETED — CASE B: no demonstrated detection benefit at the precommitted operating points.**
The preservation mechanism worked. The trained adapter retained the frozen v2
DEV detections, but detected none of the four exposed body-carried XSS attempts.
Body ranking improved; that is narrower evidence than useful thresholded detection.
No promotion, further arm, capture, threshold retuning or deployment was performed.

[Aggregate execution/evaluation evidence](../ai-training/reports/REQUEST_V3_FROZEN_BACKBONE_20261109.json)
and [precommitted design](../ai-training/configs/research/request-v3-frozen-backbone-20261109.json).
Both DEV90 and body8 were already exposed; this experiment is exploratory.
Independent human review remains **PENDING**.

## Model and fixed design

Frozen v2 remains `588 → 64 → 64 → 64 → 64 → 8`, with all **50,696** original
parameters and biases read-only. The logical expanded input is 634, with a separate
`31 × 64` tensor: exactly **1,984 trainable parameters**, no adapter bias.
The other 15 body rows have no parameter tensor and contribute zero.
Original tensors never enter the optimizer; their hashes are asserted every update.

The deterministic schema rule retains the complete six-count, 17-punctuation and
eight-pattern blocks: body indices 15–45, input indices **603–633**, zero-based.
It excludes the 11 state and four media indicators at input indices 588–602.
The design file records all 31 names, indices and normalization divisors. Membership
uses no labels or model scores. The direction of the experiment was motivated by
exposed results, so this is not a confirmatory feature-selection claim.
No identity-sensitive values or new feature families were introduced.

The first affine is the original 588-feature FP64 accumulation rounded to FP32,
plus a separate selected-31 FP64 accumulation rounded to FP32, summed in FP32.
Remaining layers/activations are original. This intentional arithmetic difference
from a joint 634-feature affine was documented before fitting. It guarantees the
original score bytes at zero adapter or zero selected tail. Existing non-OK body
validation requires a zero selected tail; the full 46-vector can still contain
state/media indicators. There is no intent-based or HTTP-method gate.

## Training and recovery

Run: `request-v3-frozen-backbone-20261109-r1`.
Source/config handoff commit: `65c2239`; starting baseline: `92f525f`.

The same frozen 236-record release supplied 48 eligible TRAIN records, reduced to
42 canonical views across 13 lineage components. Seed 17, original group-aware
round-robin sampler without replacement, batch 16, 20 epochs, **60 updates**, and
840 view exposures. No duplicate-view excess weighting. CAL, DEV and body evaluation
contributed **zero gradient rows** and no fitted normalization statistics.

Fresh AdamW state, learning rate 0.0001, decay 0.0001, betas 0.9/0.999, epsilon 1e-8,
L2 gradient clipping 1.0; original partial-binary objective, smoothing 0.005,
family weight 0. Clipping, moments and decay apply only to the adapter subspace,
unlike full fine-tuning. These compatibility differences were precommitted.
No architecture, seed, learning-rate or checkpoint search followed evaluation.

Full canonical TRAIN objective fell **0.895648 → 0.609889**. TRAIN AP rose
0.610321 → 0.773908; at the declared CAL threshold TRAIN stayed TP5/FN14/FP1/TN22.
This shows learning, not successful generalization or adequate operating margin.
The aggregate report preserves all 60 minibatch losses; they are not a monotonic
full-dataset loss curve. No additional optimizer updates were used for diagnostics.

Actual-data step 1 was checkpointed, reloaded, then resumed in a different process
at step 1/cursor 16, retaining moments, sampler and RNG. It counted within the same
60 updates. Atomic checkpoints were saved every three updates. Final-budget step
60 alone was evaluated. Loader verifies plan/schema/backbone/checksums and signals
previous-generation recovery; no silent reset or fallback occurred in the actual run.
Only adapter A/m/v and sampler state are stored; the original weights are referenced
by pinned hashes. Unit checks also cover corruption fallback and incompatible plans.

Final checkpoint, local only:

```text
ai-training/.artifacts/request_v3_frozen_backbone_20261109/
  request-v3-frozen-backbone-20261109-r1/model/checkpoints/
  step-000000000060-5ac6f69425ec/
```

Manifest SHA256: `b1b4f4d69999d60722d5e50f40d3b50d3497b244fbb8149742abfba9ec8a009f`.
Arrays SHA256: `f0a5249b7470d45cd5e62e98b60115cb9a927d682ada0a25c9910b56c904f9e8`.
The report pins optimizer-array hashes and the full run configuration.

Supervisor `idps-request-v3-frozen-backbone-20261109-r1.service` completed successfully.
The existing independent guard imposed 25% of one CPU core, 2 GiB workload memory,
no swap and a 4 GiB system reserve, active rolling 80°C limit and 85°C instantaneous
cutoff. Actual guarded wall time **5.71 seconds**, peak cgroup memory approximately
50.7 MiB, peak/active-average temperature **48°C**, no pauses, emergency stops,
watchdog failures or restarts. Sensor health was OK. This short run does **not**
validate sustained 300-second thermal behavior; the available active window was
5.43 seconds, without idle/cooldown padding. No unrelated application was closed.

## Locked operating points

All comparisons use strict `score > threshold`.

| Arm | Threshold | Source |
|---|---:|---|
| Frozen v2 | 0.8826237916946411 | Unchanged original |
| Calibration-only control | 0.8275630474090576 | Existing fixed control |
| Previous full-v3 step 60 | 0.7795706987380981 | Existing fixed CAL result |
| Adapter, primary | 0.8871806859970093 | Maximum of 11 eligible canonical CAL benign scores |
| Adapter, secondary | 0.8826237916946411 | Original v2 point, predeclared |

No DEV/body labels selected any threshold. CAL leave-one-out maxima span
0.872695–0.887181, indicating sensitivity to one benign observation. This is a
sensitivity diagnostic, not a second threshold choice. Both adapter operating
points produced identical DEV/body confusion matrices in this run.

## DEVELOPMENT: 90 canonical views

47 benign, 43 attack attempts. Matrix order below is TP/FN/FP/TN.

| Arm | TP/FN/FP/TN | AP | Precision | Recall | FPR |
|---|---|---:|---:|---:|---:|
| Frozen v2 | 20 / 23 / 0 / 47 | 0.856891 | 1.000 | 46.51% | 0/47 |
| Calibration-only | 20 / 23 / 0 / 47 | 0.856891 | 1.000 | 46.51% | 0/47 |
| Previous full-v3 | 12 / 31 / 0 / 47 | 0.833820 | 1.000 | 27.91% | 0/47 |
| Adapter, CAL point | 20 / 23 / 0 / 47 | 0.862376 | 1.000 | 46.51% | 0/47 |
| Adapter, original point | 20 / 23 / 0 / 47 | 0.862376 | 1.000 | 46.51% | 0/47 |

| Arm | XSS | Command injection | SQLi | File/traversal | Benign POST FP |
|---|---:|---:|---:|---:|---:|
| Frozen v2 / calibration-only | 1/13 | 0/3 | 12/12 | 7/15 | 0/6 |
| Previous full-v3 | 0/13 | 0/3 | 11/12 | 1/15 | 0/6 |
| Adapter, either point | 1/13 | 0/3 | 12/12 | 7/15 | 0/6 |

GET: adapter TP20/FN20/FP0/TN41; POST: TP0/FN3/FP0/TN6. The legacy XSS DEV
cases are GET/body-empty, so this body-only adapter cannot repair them. Command
injection remains undetected. JSON-products benign POST and login/logout controls
introduced no FP, but the subgroup is too small to establish safety.

Relative to frozen v2 the adapter corrected **zero** thresholded errors and
introduced zero new errors. Relative to full-v3 it recovered nine attack detections
and lost one, a net eight. The paired report retains this distinction; equal pooled
counts would not establish identical per-record behavior.

Duplicate sensitivity: using all 93 eligible DEV receipts gives adapter TP20/FN26/
FP0/TN47. Four DEV lineage components yield equal-component AP0.593184 (frozen
0.593052); near-component equal weighting gives AP0.817000 (frozen0.813149), across
64 components. Pooled AP0.8624 substantially overstates some group-weighted views.
These weighting checks are diagnostic, not independent evaluations.

## Already-exposed body cohort: eight views

Four attack attempts with unsafe-reflection outcomes, four benign-success controls;
all POST/FORM/OK with identical 588-feature prefixes. Three campaign/lineage groups,
one previously known DVWA guestbook workflow. No confirmed browser execution.

| Arm | TP/FN/FP/TN | AP |
|---|---|---:|
| Frozen v2 / calibration-only | 0 / 4 / 0 / 4 | 0.5 |
| Previous full-v3 | 2 / 2 / 0 / 4 | 1.0 |
| Adapter, CAL point | 0 / 4 / 0 / 4 | 1.0 |
| Adapter, original point | 0 / 4 / 0 / 4 | 1.0 |

Adapter attack scores span **0.733094–0.824361**; benign scores **0.177075–0.520773**.
The ranking separates these eight observations, but no attack crosses either
predeclared adapter threshold. No operating point was chosen inside that observed
gap. Compared with full-v3, two detections were lost; compared with frozen v2,
no thresholded detections were added.

## Ablation, preservation and shortcuts

At the primary adapter threshold:

| Same trained checkpoint | DEV TP/FP/AP | Body TP/FP/AP |
|---|---|---|
| Adapter normal | 20 / 0 / 0.862376 | 0 / 0 / 1.0 |
| Adapter disabled | 20 / 0 / 0.856891 | 0 / 0 / 0.5 |
| Six counts only | 20 / 0 / 0.859969 | 0 / 0 / 0.5 |
| 25 syntax features only | 20 / 0 / 0.860385 | 0 / 0 / 1.0 |

These are inference ablations of the same weights, not additional training arms
or performance-selected models. Counts-only produces one identical body-cohort
score (0.216146); syntax causes the within-cohort ordering. Since method, media,
body availability and frozen prefix are matched, they cannot alone explain this
ordering. This does not exclude environment/template shortcuts beyond that cohort,
nor prove that every syntax feature is causally useful.

The CAL maximum comes from benign `captcha-feedback-create`: frozen0.827563,
adapter0.887181, counts-only0.850707, syntax-only0.870681. Both blocks can raise a
benign score. Removing counts alone is not an evidenced solution. TRAIN includes
body-active benign17/23 and attack12/19, so it is not simply BODY=ATTACK. Source and
workflow diversity are still small. Fit improved without new detections; excessive
overfitting, inadequate budget, fixed-pathway limitations and objective/operating
margin mismatch have not been isolated as separate causes.

All original backbone arrays remained read-only and byte-identical. After fitting,
**154 zero-selected rows** retained exact frozen score bytes, including **153 GET**
rows across the full TRAIN/CAL/DEV derivative. Disabling the adapter reproduced the
baseline exactly on all **244** derivative-plus-body observations. Original fixed-
threshold flags also matched on all zero-selected rows; maximum score delta was
zero. Body8 has no zero-selected rows and provides no no-body parity evidence.
Changing a CAL threshold can change flags independently of score preservation;
that is why original-threshold parity was checked separately.

## Integrity, uncertainty and decision

- Dataset: `f6aa5b60b0c7d0291dfa123fe82a8e0870bb9fbacd36ac6eb27f3d6e9dfae22f`.
- Feature contract: `d186dd653d9e2d4e7af77469766465144a3778a4f4a5202229a47d4ebc5feaa5`.
- Plan: `e9d8054ca8c003ba327a84e640645948ddc98fb8629e00cc584a8262fa0f4532`.
- Frozen generation and per-array hashes are pinned in the design and aggregate report.
- Preservation checks: 158 protected paths, three historical UNKNOWN evidence files,
  eight qualified-release files, 17 previous-pilot files, 14 body-evaluation files,
  and five experiment source pins unchanged. Overlap among these sets is possible;
  these counts must not be added as unique files.
- No new HTTP requests, role changes, Oracle changes, sealed-payload access,
  system-policy edits, live model replacement, model releases or raw-body logging.
  Private data, per-record scores, adapter/optimizer artifacts remain local/ignored.
- Seven focused tests and Ruff passed. Safe publication includes only source/tests/
  configuration and aggregate metadata/docs. Team bootstrap and frozen releases
  retain their existing inference path; research checkpoints are not required.

For DEV, 0/47 FP has an IID two-sided exact 95% upper bound **7.55%**; recall
20/43 has interval **31.18%–62.35%**. Body0/4 FP has upper bound **60.24%**,
and adapter0/4 recall interval **0–60.24%**. Group dependence further limits these
IID sensitivity intervals. No FPR≤1%, independent generalization or independent
human verification claim is supported. `RULE_AI_COMPLEMENTARITY=NOT_MEASURED`.

The precommitted research screen required at least 2/4 body detections, 0/4 body FP,
no additional DEV FP and preservation PASS. Preservation passed; body detection
failed at both declared points. Therefore:

```text
FROZEN_BACKBONE = VERIFIED
TRAINABLE_PARAMETERS = 1984
TRAINING = COMPLETED
LEGACY_ZERO_BODY_PARITY = PASS
BODY_ADAPTER_RESEARCH_VALUE = NOT_DEMONSTRATED
INDEPENDENT_QUALITY_CERTIFIED = FALSE
PRODUCTION_PROMOTION = NOT_AUTHORIZED
```

`NOT_DEMONSTRATED` refers to additive detection benefit at the locked operating
points; exploratory syntax-ranking value was observed and preserved as evidence.
The experiment is valid, with a negative operating-point outcome.

**One recommended next research task:** a matched margin-aware objective arm for
this same frozen adapter. Change only the TRAIN objective to explicitly target a
binary score margin around the original v2 decision boundary. Keep 1,984 parameters,
backbone, seed, sampler, 60-update budget and CAL-only threshold rule fixed. Precommit
margin/weight using TRAIN and the protocol before evaluating DEV/body; do not search
those exposed sets. This tests whether the current finite arm learned ranking
without sufficient operational margin. It is a hypothesis, not an established
root cause or a promise of improvement. Do not lower the threshold on body8, enlarge
the model, extend epochs or run this next arm without a subsequent request. Any
later result on these exposed cohorts remains exploratory.

Private execution root:
`ai-training/.artifacts/request_v3_frozen_backbone_20261109/request-v3-frozen-backbone-20261109-r1/`.
Authoritative files: `plan.json`, `actual-preflight.json`, `loss.jsonl`, `status.json`,
`completion.json`, `supervisor-result.json`, `resource/resource-report.json`,
`model/`, `evaluation/`. Final preservation proof:
`.local-dev/request-v3-frozen-backbone-20261109/final-verification.json`.
