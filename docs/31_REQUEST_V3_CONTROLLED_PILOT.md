# Request v3 controlled pilot — completed, rejected (2026-11-08)

**CASE B — NO DEMONSTRATED IMPROVEMENT.** One valid actual-data pilot completed;
retain its negative evidence and checkpoint, keep deployed/shadow frozen v2.
No automatic retraining, threshold change, model promotion or further capture.

[Machine report](../ai-training/reports/REQUEST_V3_CONTROLLED_PILOT_20261108.json).
Baseline `3168f11`; execution source committed/pushed as `9dbf084` before launch.
Frozen [pilot design](../ai-training/configs/research/request-v3-grounded-pilot-20261108.json)
remains unchanged.

## Run and checkpoint evidence

Run `request-v3-pilot-20261108-r1`, supervisor
`idps-request-v3-pilot-20261108-r1.service`, **COMPLETED** in ~6.1 seconds under the
resource guard. This was short enough to evaluate during the same chat.

Dataset fingerprint:
`f6aa5b60b0c7d0291dfa123fe82a8e0870bb9fbacd36ac6eb27f3d6e9dfae22f`.
Feature fingerprint:
`d186dd653d9e2d4e7af77469766465144a3778a4f4a5202229a47d4ebc5feaa5`.
Design fingerprint:
`5656548503f15afae512bcf47e2976afefd7148a1cea696e44bd2aa88555e32c`.

Architecture 634→64→64→64→64→8, **53,640 parameters**. W0[588,64] copied into
W0[634,64], 46 new rows zero, remaining arrays copied. Fresh AdamW moments,
lr0.0001, W-only decay0.0001, global gradient clip1, binary-marginal objective
smoothing0.005/family_weight0. Eight-logit output is binary-supervised; no family
classification quality claim.

Seed17, batch16, 20epochs/128step first cap; 42 canonical eligible TRAIN views
from48receipts yield **60 updates**, 840 canonical exposures. Recorded-lineage
round-robin order without replacement, each canonical view once/epoch. Near
variants remain correlated distinct views under the locked contract; they are
not artificially resampled. TRAIN has13 recorded lineage and21 near components.
No CAL/DEV gradients, fitted statistics, early stopping or checkpoint selection.

Execution preflight used the actual first training update, not a discarded extra
fit. Step1 checkpoint reloaded with identical arrays and nonzero fresh Adam moments;
a new process continued from step1/cursor16. Final step60/epoch20/cursor42 verified.
Seeded replay of all20sampler orders reproduces first/final permutations and final
RNG state. Periodic recovery every3updates; best.json is library bookkeeping and
was not used for selection. Final checkpoint alone evaluated; no failed-run restart.

Final private checkpoint:
`ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1/model/checkpoints/step-000000000060-52599c3250fb/`.
Manifest SHA256:
`8130e25acb570ba694fdc27cbb48a0950928203d85a7f60fafeacd40e82859d3`.
Step1 and57 recovery generations also retained by existing checkpoint tooling.

Same full42-view TRAIN partial loss: **0.89565→0.29559**. Canonical TRAIN AP:
**0.61032→0.97214**. All60batch losses/20epoch aggregates are in machine report;
these are fit diagnostics, not generalization evidence.

## Frozen three-arm comparison

Primary: same90canonical DEV views, **47benign/43attack**, selected before scores
by eligible common mask and canonical sample ID per candidate view. Receipt
sensitivity separately covers93receipts. CAL13views:11benign/2XSS attempts.
Strict `>` thresholds: deployed v2 unchanged; control/challenger each maximum of
eligible canonical CAL benign only. No DEV label used to choose a threshold.

| DEV metric | Frozen v2 | Calibration-only | v3 challenger |
|---|---:|---:|---:|
| Threshold | 0.88262379 | 0.82756305 | 0.77957070 |
| Average precision | 0.85689 | 0.85689 | 0.83382 |
| Precision | 1.000 | 1.000 | 1.000 |
| Recall | 20/43 =46.51% | 20/43 =46.51% | 12/43 =27.91% |
| FP / benign | 0/47 | 0/47 | 0/47 |
| Confusion [[TN,FP],[FN,TP]] | [[47,0],[23,20]] | same | [[47,0],[31,12]] |

| DEV family detected / total | Frozen v2 | Calibration-only | v3 |
|---|---:|---:|---:|
| XSS | 1/13 | 1/13 | 0/13 |
| Command injection | 0/3 | 0/3 | 0/3 |
| SQLi | 12/12 | 12/12 | 11/12 |
| File family | 7/15 | 7/15 | 1/15 |

Paired v3 versus either reference: **1 corrected attack, 9 lost attacks**, zero
new/removed benign FP. The corrected attack is file-related; losses:7file,1SQLi,
1XSS. No XSS/command gain. Four of five retention checks fail; only no-new-benign
FP passes. This is a valid failed challenger, not an invalid execution.

DEV GET: frozen20TP/20FN, v3 12TP/28FN, both0FP/41benign. DEV POST: all3attacks
(command) missed by all arms; **0FP/6benign** in each, comprising4JSON and2FORM
POSTs (including empty logout). Four catalog-description hard negatives and
login/logout workflows have no additional FP. Full workflow/media/source strata
are in machine report; none used for retuning.

## Uncertainty, calibration and dependence

47benign views with zero FP give an IID exact-binomial two-sided95% interval
**[0,7.55%]**, not FPR≤1% certification. For6benign POSTs it is **[0,45.93%]**.
Recall IID sensitivity intervals: frozen **31.18–62.35%**, v3 **15.33–43.67%**.
DEV has only4recorded lineage components, so no independent-cluster CI claimed.
No statistical-significance or cross-domain conclusion from these intervals.

The regression persists under fixed-threshold sensitivity analyses:

| Recall weighting | Frozen/control | v3 |
|---|---:|---:|
| 93receipt-weighted | 43.48% | 26.09% |
| Equal recorded-lineage component | 43.54% | 15.17% |
| Equal near-feature component | 45.37% | 31.48% |

CAL control maximum0.827563 is tied: leave-one-benign-out maximum unchanged.
Candidate maximum0.779571, next0.753211; leave-one-out maxima range0.753211–0.779571.
These refits are diagnostic only; actual threshold stayed0.779571. Both CAL XSS
attempts are missed. Probability calibration diagnostics also retained.

RULE_AI_COMPLEMENTARITY=**NOT_MEASURED**: this derivative has no bound per-record
Rule/Suricata alert evidence. Do not infer alert overlap or use alerts as GT.

## What the negative result establishes

Verified family/payload-location matrix:

| Family | Canonical TRAIN | Canonical DEV |
|---|---|---|
| XSS | 8POST/OK,8nonzero syntax tails | 13GET/EMPTY,0syntax tails |
| Command | 4POST/OK,4syntax tails | 3POST/OK,3syntax tails |
| SQLi | 4GET/EMPTY+1GET/MISSING | 12GET/EMPTY |
| File | 2GET/EMPTY | 15GET/EMPTY |

The body representation has **no direct XSS payload content on DEV**. TRAIN
learned body-carried XSS (3/8flags versus0/8), while DEV tests URI-carried XSS.
This demonstrated transport shift limits attribution; it does not excuse failing
the precommitted overall retention screen or prove body-XSS representation useless.

Command scores increased: TRAIN median~0.212→0.400, DEV~0.157→0.310. They remain
far below candidate threshold0.780; even TRAIN command0/4flagged. No meaningful
command discrimination established against legitimate hard negatives. Lowering
threshold after observing this cohort is not an accepted remedy.

Candidate threshold is already lower than both references, while AP also drops:
regression is not solely a high cutoff. Strong TRAIN fit plus DEV loss is
consistent with small-cohort overfit and legacy-function drift. Original W0 rows
move L2~0.343; learned46body rows norm~0.095. These observations do not causally
separate finetuning from the46newfeatures: no matched588-input finetune was
precommitted, and none was added after results.

Posthoc inference-only zeroing of syntax-count/flag tail, retaining state/media:
mean absolute DEV score delta0.00526 (command0.09217), **0threshold crossings**.
This is a possibly off-manifold sensitivity probe, not a fourth trained arm or
independent evaluation. XSS/SQLi/file tail effects are zero because DEV body
payload syntax is absent. Missingness/media/method shortcuts remain possible.

Identity-sensitive JSON-login collisions remain excluded; no password/identity
features or weakened privacy exclusions were introduced. Human review PENDING;
known DVWA/Juice lab data and internal Oracle labels do not establish independent
model quality. The pilot minimum gates permitted a defensible experiment; they
did not guarantee an aligned test of every body-feature hypothesis.

## Safety, artifacts and decision

Training guard: peak47°C, active-window average~46.39°C over~5.77active seconds,
no pause/cooldown, emergency, OOM, watchdog failure or restart. Initial25%one-core,
MemoryMax2GiB, no swap,4GiB MemAvailable reserve, rolling80°C/instant85°C.
Independent watchdog PID differed from both training processes. No user app,
OS/firmware thermal protection or application service changed.

158protected hashes,3historical UNKNOWN files and8qualified-release files verified
unchanged. Frozen v2/GLU207,encoders,thresholds,checkpoints,web/Nginx/sensors,
Rules/Policy/correlation and published Releases preserved. No sealed content,
AWS, AI enforcement or promotion. New weights/optimizer/per-record scores remain
local ignored. Finite artifact/log scan against known local secrets PASS; no raw
HTTP/session/body data added. Production privacy remains NOT_VERIFIED.

Private run root:
`ai-training/.artifacts/request_v3_pilots_20261108/request-v3-pilot-20261108-r1/`:
`plan.json`, `status.json`, `loss.jsonl`, `model/`, `resource/`, `evaluation/`,
`completion.json`, `supervisor-result.json`. Private verification:
`.local-dev/request-v3-pilot-20261108/`. Four new targeted tests/Ruff PASS; actual
resume/sampler replay/metric recomputation provide execution evidence.

**Engineering decision:** reject this checkpoint as a replacement; preserve it
as a negative research result. Keep frozen v2 in shadow inference.

**One next task:** a finite precommitted body-carried XSS+command evaluation cohort
with matched benign POST/form+JSON controls and disjoint template/session/campaign
lineage. Score the existing fixed step60 checkpoint and frozen v2, without
retraining or threshold adjustment. It fills the observed DEV body-XSS gap before
choosing another training design. Known-lab Oracle evidence only; no independent
cross-domain claim. Do not start that campaign in this milestone.
