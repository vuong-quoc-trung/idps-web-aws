# Request v3 body-carried evaluation — partial XSS value observed (2026-11-08)

**BODY_CARRIED_EVALUATION=PARTIAL; V3_RESEARCH_VALUE=OBSERVED on the qualified
XSS subset only. Command INCONCLUSIVE. V3_PROMOTION=REJECTED. No new training.**

Baseline `5cae445`, branch `feature/ai-idps-shadow-integration`.
[Exact precommit protocol](../ai-training/configs/research/request-v3-body-evaluation-20261108.json),
[machine report](../ai-training/reports/REQUEST_V3_BODY_CARRIED_EVALUATION_20261108.json).
The earlier [90-view DEV regression](31_REQUEST_V3_CONTROLLED_PILOT.md) remains a
valid CASE B result; this small body-specific result does not reverse it.

## Cohort design and exclusion before traffic

Execution/cohort `request-v3-body-eval-20261108-r2`.
Precommit fingerprint:
`fe06ea7dd14d78169b18cf4f0d2d4dc308ae6e8881bb9bbdc5cbc7e0ba7bc534`.
Eligible dataset fingerprint, locked before the first model score:
`0d775248323eb183f91382cbd47e718fbfa6972b6689dfd39e050a8b9fcd9c56`.

Fixed24-template catalog:6body XSS attempts,6command attempts,6matched controls
for each. No score-selected payloads, header padding, nonce-based novelty or
replacement after exclusion. Existing same-route raw/template/full/candidate
exact/near rules checked against236exposed historical records; the unchanged
body-v3contract treats588-only collisions as diagnostics, not an independence gate.
Full-near checks are method/endpoint scoped; matching additive control reconstructed
from its pinned static template. No sealed samples, labels or features read.

Only **4complete XSS pairs** passed:8requests. Two XSS pairs overlapped historical
candidate geometry. All6command-control candidates overlapped historical views or
near views; none formed a complete novel command pair. Two command attempts could
individually pass novelty but were excluded with their nonqualifying counterparts.
This is a real matched-control/representation bottleneck, not evidence that6new
request IDs would create6independent examples. No command traffic was generated.

The8retained main receipts were captured unchanged, not expanded to fill24. There
was1separate benign stored-literal preflight and24setup/readiness HTTP attempts.
Thus **9targeted HTTP dispatches**, all with responses;8main/1diagnostic. Four
benign controls, four XSS attempts; no UNKNOWN. Fresh apps/sessions per3predeclared
campaign groups; actual session uniqueness asserted in RAM. Only **one real
business workflow/surface**, DVWA stored guestbook, reused as a known application.
Novelty here is request/template/recorded-lineage/feature-view novelty under the
locked checks, not cross-domain or statistical independence.

Decision was locked before HTTP:≥2additional attack IDs versus both references,
benefit in≥2fresh lineage groups, no new matched benign FP. Missing families remain
INCONCLUSIVE; no independent quality certification or promotion.

## Oracle and privacy evidence

All8main requests have authenticated-session assertion, unique collector ID,
source/environment binding, predeclared intent, observed outcome and feature state.
Each own entry had **DB count0→1**, exact value in the actual guestbook display
region, HTTP200 and class-specific markup/literal validation. HTTP status alone
never creates a label. All bodies FORM/OK; labels are attack intent versus benign
intent, not Rule/model decisions.

Outcomes: **4UNSAFE_REFLECTION**, **4BENIGN_SUCCESS**. No browser was opened;
no verified browser execution, successful XSS exploitation or command execution
claim. Independent human review **PENDING**. Original responses were not retained;
source-bound numeric witnesses are available, but a later reviewer cannot reparse
the original response independently. This is internal research Oracle evidence.
The receipt key `declared_active_markup` is a class-dependent predicate: active
attribute/protocol/srcdoc for attack, no parsed HTML tags for benign; source and
original receipts are preserved for interpretation.

Before scoring: actual transmitted overlap checks PASS; 8unique634views; bitwise
588prefix/634assembly/body-template parity8/8; eligible records/features/manifest
made read-only, fingerprint recomputed in a separate verification step. Zero
model predictions before that lock. Evaluation-only role is explicit. Any future
fit/calibration reuse must explicitly retire its evaluation independence.

Privacy finite scan: **21actual private values** held only in RAM,12emitted capture
files checked for literal/URL/base64/hex/SHA1/SHA256/JSONescaped forms. No raw HTTP
body/response/session/cookie dumps or session digests persisted. Derived numeric
scores/witnesses remain local ignored; known local-secret output scan PASS.
Approved privacy projections unchanged, including JSON-login exclusions.
Production privacy NOT_VERIFIED.

## Fixed-checkpoint comparison

Original step60 checkpoint unchanged; manifest:
`8130e25acb570ba694fdc27cbb48a0950928203d85a7f60fafeacd40e82859d3`.
Exact thresholds copied from existing frozen/pilot manifests; strict `>`:

| Arm | Threshold | TP / FN | FP / TN | Precision | Recall | AP |
|---|---:|---:|---:|---:|---:|---:|
| Frozen v2 | 0.8826237916946411 | 0/4 | 0/4 | undefined | 0/4 | 0.5 |
| Calibration-only | 0.8275630474090576 | 0/4 | 0/4 | undefined | 0/4 | 0.5 |
| Existing v3 step60 | 0.7795706987380981 | 2/2 | 0/4 | 2/2 | 2/4 | 1.0 |

Per-family: XSS2/4 versus0/4; command **NOT_MEASURED/INCONCLUSIVE**, not0/6.
Paired versus either reference: v3-only attacks2,reference-only0,both0,neither2;
benign falsely flagged only by v3=0,only by reference=0.

| Fresh campaign group | Attacks / controls | Frozen/control TP | V3 TP | V3 FP |
|---|---:|---:|---:|---:|
| group0 | 2/2 | 0 | 1 | 0 |
| group1 | 1/1 | 0 | 0 | 0 |
| group2 | 1/1 | 0 | 1 | 0 |

Benefit occurs in2of3fresh session/campaign groups. It is not demonstrated across
multiple business workflows or applications.

All8requests have the **same588prefix**. Frozen/control scores are identically
0.17579001188278198, hence cannot distinguish these particular inputs. V3attack
scores range0.72458–0.82282; benign0.12965–0.42876. AP1.0 describes ranking on just
8selected views, not perfect detection or population performance. Thresholds were
not moved to exploit the observed score gap; only2attacks actually exceed the
persisted0.77957threshold.

IID exact-binomial95% sensitivity bounds: v3Recall **6.76–93.24%**, zero observed
FPR upper bound **60.24%** (4controls), Precision **15.81–100%**. Three dependent
campaigns/one surface cannot establish independent cluster intervals, significance,
FPR≤1% or generalization. Counts are primary.

RULE_AI_COMPLEMENTARITY=**NOT_MEASURED**: no bound Rule/Suricata receipts exist
for these requests. No inferred alert overlap or enforcement change.

## Interpretation and next decision

The current checkpoint shows **limited body-carried XSS research value**, meeting
the precommitted subset screen. POST,FORM,body-OK and588prefix are constant across
both classes, so those variables alone cannot explain the separation within this
cohort. Predeclared inference-only tail ablation makes all8inputs identical:
AP0.5,0detections at the same threshold,2flag changes. This confirms conditional
body-feature use by this fixed checkpoint; the intervention may be off manifold
and is not another trained arm or a general causal quality estimate.

Across frozen v2 versus v3, representation and learned weight changes still differ.
No matched trained control was added. Other syntax shortcuts, unseen workflows,
small sample selection and known-app bias remain. The POSTbody result is compatible
with the prior TRAIN-POST/DEV-GET XSS mismatch explaining part of the XSS failure,
but cohorts/templates differ. It does not explain away previous SQLi/file losses
or restore the failed90-view retention decision. **V3 stays rejected for promotion.**

**One follow-up, separately authorized:** a controlled weight-preservation arm
with the same634architecture, frozen236release/42canonical TRAIN views, seed/order/
60step budget and objective. Freeze all original v2 parameters and15new state/media
rows atzero; train only31body count/syntax rows (**1,984parameters**). Compare with
existing full-finetune v3 and frozen v2. This isolates adding learned body inputs
without adapting legacy parameters; on EMPTY/MISSING body tail iszero, protecting
the legacy function within numerical tolerance. Use old90DEV+these8 as explicitly
**exposed research diagnostics**, not independent quality certification or a new
admission policy. No such arm was implemented or trained in this milestone.

## Resource safety, startup amendment and handoff

The first execution r1 stopped before lab launch/HTTP: a heavy new entrypoint at
10%CPU delayed watchdog readiness beyond10seconds. No Oracle/data failure and
zero traffic; after parent exit the watchdog observed stale heartbeat. Its source,
plan and stop evidence remain local. r2 reuses the existing lighter final-controls
watchdog CLI, allows20seconds readiness under the same conservative quota; catalog,
qualified8IDs,Oracle meanings,thresholds and decision rule unchanged. This was one
bounded startup correction, not an additional collection/research campaign.

r2capture PASS,~143.7seconds; guard peak **48°C**. Evaluation PASS; no emergency,
watchdog failure, OOM or automatic restart. Existing outer85°C/ownership80°C,
25%one-core job quota, separately capped containers and4GiB reserve retained.
All owned containers/networks/listeners cleaned,24volume inventory unchanged,
old PGs stopped with their mounts preserved; host sysctl unchanged.

158protected hashes,3historical UNKNOWN receipt files, qualified236release and
original pilot checkpoint/evaluation files unchanged. No new training/checkpoints,
recalibration, sealed access, default body-mode change, web/sensor/Rules/Policy/
correlation modifications, published model release, AWS or enforcement.

Private cohort:
`ai-training/.artifacts/request_v3_body_eval_20261108/cohort-r2/`.
Private technical proofs/source snapshots:
`.local-dev/request-v3-body-eval-20261108/`.
Safe source/tests/precommit metadata/aggregate report are public; restricted numeric
features,Oracle receipts and per-record scores stay local ignored. Three new tests,
seven combined targeted tests and Ruff PASS. Stop here.
