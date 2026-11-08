# Request v3 dataset acquisition completed — 2026-11-08

**CASE A — RESEARCH PILOT READY. Training NOT_STARTED.**
Baseline `648a495`, branch `feature/ai-idps-shadow-integration`.
[Machine report](../ai-training/reports/REQUEST_V3_DATASET_ACQUISITION_COMPLETE_20261108.json)
and [frozen pilot configuration](../ai-training/configs/research/request-v3-grounded-pilot-20261108.json).

## Verified campaign

Fresh execution `request-v3-acquisition-final-20261108-r1` preserved all 12 logical
main templates, original TRAIN/DEVELOPMENT roles, Oracle meanings, coverage and
duplicate rules. No scores, threshold selection, role reassignment or sealed access.

Precommit plan fingerprint:
`ce24120b50e0bff0b042cfe7b5eaadecc1bb0e2d74166905ad91b385189f27de`.
Environment/fixture fingerprint:
`a0a7390aba70689f9d029148137849e7fc7fd8bab5adacca6568fc818f37c9dc`.

Five old DVWA representatives were reused after checking unchanged AST for
cases/run_case/preaudit/PHP Oracle, pinned images/helpers and app namespace
`ping_group_range=33 33`. Juice account/cookie changes do not affect those DVWA
bindings. Reused evidence is not new independent evidence.

Four remaining Juice representatives ran successfully:

| Representative | Result | Oracle |
|---|---|---|
| control-03 | HTTP 200 | New owned BasketItem, read-only DB 0→1 pair, quantity 1 |
| control-04 | HTTP 200 | Authenticated own-basket read confirms added product/quantity |
| control-05 | HTTP 201 | Declared product fields match response and persisted DB row |
| control-09 | HTTP 200 | Actual authenticated identity matches transient session |

**CAMPAIGN_PREFLIGHT=PASS, 9/9**. Basket fixture v2.1 uses a fresh ordinary
registered account with an empty owned basket, valid product/stock/quantity,
ProductId 1 and quantity 1. Seeded admin basket unchanged. Positive CREATE is
verified independently of negative diagnostics. Duplicate CREATE returns **500**
with the existing pair/quantity and read-only state unchanged: negative gate
**PASS**. Sanitized exception taxonomy remains **UNKNOWN**; no fabricated exact
exception claim. Historical UNKNOWN receipts, including the previous overwritten
positive receipt, remain byte-identical UNKNOWN.

Main ran in fresh app instances/sessions per environment and role: **12/24**
receipts, all 12 Oracle verified: **11 BENIGN_SUCCESS, 1 VERIFIED_EXPLOIT_SUCCESS**
(the fixed SQLi canary), **0 UNKNOWN**. The source's command/file controls only
use declared loopback/public-file lab behavior. No replacement/filler requests.

Accounting: 4 new preflight + 1 negative diagnostic + 12 main = **17 actual
new targeted dispatches**, all with responses. The legacy collector's upper-bound
field says 18 because it reserves one historical uncertain dispatch; it is not
an extra current request. Setup/readiness HTTP attempt counter 108/120 is separate.
No preflight, setup or negative request enters the supervised release.

## Versioned derivative

Release `request-v3-grounded-20261108-v1`, local ignored path:
`ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2/`.

Fingerprint:
`f6aa5b60b0c7d0291dfa123fe82a8e0870bb9fbacd36ac6eb27f3d6e9dfae22f`.

236 records = immutable parent 224 + qualified main 12. All old roles/intents/
outcomes are preserved. 219 application-Oracle-verified records overall;
236 human reviews PENDING, zero independent human verifications.

634 float32 contract unchanged: frozen 588 request prefix + 46 body-syntax
features, fixed normalization/order/missingness, no fitted statistics. Dataset is
request-only; no GLU207 features or synthetic sensor availability are introduced.

| Strict coverage | TRAIN before→after | CAL before→after | DEV before→after |
|---|---:|---:|---:|
| Eligible records | 43→48 | 13→13 | 86→93 |
| Unique feature views | 37→42 | 13→13 | 83→90 |
| Benign / attack | 23/20→27/21 | 11/2→11/2 | 40/46→47/46 |
| Benign JSON POST | 0→1 | 4→4 | 0→4 |
| Benign form POST | 19→20 | 1→1 | 0→2 |
| Benign command counterpart | 0→1 | 0→0 | 0→0 |
| Benign file counterpart | 0→1 | 2→2 | 1→1 |
| Workflow categories | 14→19 | 7→7 | 9→13 |
| Recorded lineage components | 11→13 | 7→7 | 2→4 |
| UNKNOWN / excluded | 0/20→0/20 | 9/24→9/24 | 4/38→4/38 |

UNKNOWN is a subset of excluded, not an extra disjoint count. All 12 new main
rows are strict eligible; no previously eligible parent row becomes excluded.
Total strict 154 records / 145 distinct candidate views. Canonical TRAIN has
42 views; multiplicity is not training-weight inflation.

| Eligible attack-family views | TRAIN before→after | CAL | DEV |
|---|---:|---:|---:|
| SQLi | 4→5 | 0 | 12 |
| XSS | 8→8 | 2 | 13 |
| Command injection | 4→4 | 0 | 3 |
| File family | 2→2 | 0 | 15 |

After strict missingness: TRAIN EMPTY10/MISSING3/OK35, CAL EMPTY8/OK5,
DEV EMPTY81/MISSING1/OK11. Natural TRAIN MISSING includes both benign and attack.
Full before/after method/media/environment/lineage and missingness aggregates are
in the machine report.

## Integrity, privacy and reproducibility

Locked exact, candidate-near, inherited full-near and recorded session/campaign
component rules retained; cross-role conflicts quarantine both sides. Eligible
cross-role identity/view/recorded-lineage/near overlaps **0**. New full-near
cross-role edges **0**. Sealed candidate overlap remains UNVERIFIED; no sealed
samples, labels or vectors were opened.

New dataset-wide candidate views 170, versus 130 frozen runtime views. Candidate
mixed-label group remains 1 (6 affected rows), excluded from strict masks. These
are representation diagnostics, **not detection-performance improvement**.

Independent process rebuild: **7/7 files byte-identical**, fingerprint recomputed.
All 236 rows have fixed-contract assembly parity; all 224 parent feature rows
unchanged; body syntax for all 12 new rows independently regenerated from fixed
source templates, including credential/ID exclusion semantics.

An initial materializer attempt failed serializing NumPy int64 aggregate counts.
It was fixed with native-int conversion and a serialization regression test.
Incomplete `release-v1/` is preserved and not a release; `release-v2/` plus
`rebuild-v2/` passed. No recapture or acceptance-rule change was needed.

Actual-value privacy scan before runtime secrets left RAM: **41 private values**
against 21 emitted capture files, including literal/URL/base64/hex/SHA1/SHA256/
JSON-escaped forms. No values or direct secret digests written. Derivative uses
only those privacy-qualified tensors and schema-selected metadata; known local
secret and metadata-invariant scans PASS. New metadata has ordinal group and
raw/template/full equality aliases, not session/cookie hashes. No new raw
HTTP bodies, responses, sessions, PCAPs or arbitrary sensitive field values.
Finite research privacy PASS; production privacy NOT_VERIFIED.

## Readiness and remaining limitations

| Gate | Result |
|---|---|
| DATASET_INTEGRITY / FEATURE_CONTRACT | PASS |
| ORACLE_PROVENANCE | PASS_FOR_RESEARCH, internal application Oracles |
| STRICT_SPLITS | PASS, permitted exposed roles only |
| TRAIN_COVERAGE / DEV_COVERAGE | PASS all original minimums and additive controls |
| CALIBRATION_VALIDITY | PASS unchanged research minimums |
| PRIVACY_FOR_RESEARCH | PASS finite scope above |
| WARM_START / CHECKPOINT_RELOAD / EXACT_RESUME | VERIFIED existing synthetic 634 proof |
| EVALUATION_PROTOCOL | LOCKED exposed-research comparison |
| FROZEN_BASELINE_PROTECTION | PASS, 158 protected hashes |
| RESEARCH_PILOT_READY | **TRUE** |
| INDEPENDENT_QUALITY_CERTIFIED | **FALSE** |

DEV now has 6 benign POST views across 3 workflows, FORM+JSON; POST no longer
implies attack (6 benign POST and 6 attack POST). This mitigates an obvious
shortcut, but does not prove shortcut learning eliminated. TRAIN benign JSON is
still one view/workflow; source and media correlations remain. CAL has only
11 benign and 2 XSS attempts; TRAIN file family only 2 views and DEV command only
3. These small dependent lab cohorts cannot certify population FPR or generalization.
DVWA/Juice were already known environments; no blind or cross-domain claim.

Frozen experiment configuration preserves 53,640 parameters, architecture
634→64→64→64→64→8, one seed17, batch16, max128 updates or20epochs (first cap).
With 42 canonical views and no dropped tail, current budget allows at most60 updates.
Arms: deployed frozen v2, calibration-only control, one body-syntax challenger.
Thresholds use eligible CAL benign only; original retention criteria unchanged;
no DEV-based threshold/checkpoint selection. All arms use identical pre-score
canonical IDs: old parent-strict intersection plus eligible new controls.
No run directory, actual-data checkpoint, gradient update or training process.

## Safety and handoff

All lab resources cleaned; volume inventory unchanged (24), old PGs remain stopped
with preserved mounts; host sysctl unchanged. Guard peak **52°C**, per-process
quota25% one core, separately capped containers, outer85°C/ownership80°C cutoff,
about4GiB MemAvailable reserve, zero thermal trips/watchdog failures. Serialization
attempt failed by software exception; final materialization/rebuild/verification
PASS. No host protection or user application changed.

158 protected hashes and 3 historical UNKNOWN receipt files unchanged. Frozen
models/encoders/thresholds/checkpoints, Rules/Policy/correlation, web/Nginx/Suricata
and published Releases unchanged. No AWS, AI enforcement or sealed access.
Existing clone/bootstrap/model-restore/local-system workflow remains unchanged.
Restricted numeric research data/evidence stay local and ignored; no new model
bundle needs publishing because no training occurred.

Private proofs: `.local-dev/request-v3-acquisition-final-20261108/` and
`ai-training/.artifacts/request_v3_acquisition_final_20261108/campaign-r1/`.
Release manifest pins all files; completed derivative is read-only, prior releases
untouched. 33 targeted tests and Ruff PASS.

**Decision:** no further capture required by the locked pilot minimums. Stop here.
After a separate training authorization, run the single frozen bounded pilot;
judge it against both references under the unchanged exposed-research screen.
