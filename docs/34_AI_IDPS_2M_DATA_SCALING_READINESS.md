# AI_IDPS_2M_DATA_SCALING_READINESS — 2026-11-09

**CASE B — DATA SOURCES INSUFFICIENT.** The bounded admission pilot and rebuild
worked, but no large local source demonstrated qualified attack-intent capacity.
Of 10,000 source positions, **74 existing requests** pass the new conservative
research profile. **No new training data, requests or model experiment were created.**
This milestone supersedes the proposed margin-aware experiment; that experiment
was not started.

[Machine-readable inventory, measurements and evidence](../ai-training/reports/AI_IDPS_2M_DATA_SCALING_READINESS_20261109.json).
[Locked research admission policy](../ai-training/configs/research/http-scaling-admission-20261109.json).
Baseline was `87b80bc`, clean, on `feature/ai-idps-shadow-integration`.

## Available source capacity

The inventory covers **23 source groups**, including related cohorts, unavailable
candidates and excluded flow/URL-only categories. It is not a sum of independent
sources. Five permitted raw source files were rehashed; current WAF Parquet row
metadata was checked. Other large counts are explicitly **hash-bound historical
audits**, with current file existence/size checked, rather than a new all-row census.
No reserved ZIP members or sealed payloads were opened. No large data was downloaded.

| Source | Available rows / previously audited uniqueness | Label and admission limits |
|---|---|---|
| WAF v2, pinned publisher train | 1,924,461 rows; 1,612,017 exact HTTP representations | C: publisher normal/anomalous, no request IDs/time/campaign or verified attack intent; 312,443 duplicate extras, 192 conflicting representations |
| SR-BH2020 | 907,815 records; 905,043 natural observations | C: signature-assisted/manual/semi-auto annotations; 26 natural-label conflicts; publisher count differs by one; exposed development |
| WAMM | 704,665 database rows; 312,241 text representations | C: SR-BH derivative, not a new independent source; 23,576 numeric views overlap exposed development |
| Open-appsec legitimate | 811,129 nonreserved records; 756,548 retained signatures | C: publisher legitimate browsing; 54,391 duplicates, 190 quarantines; 148 reserved case files remain unopened and uncounted; existing supervised-fit restriction retained |
| SOC-MLD | 198,122 access lines; 193,220 complete distinct observations | D/unverified intent: operator/rule/time matching lacks request-bound basis; 38 shared attack-instance IDs across original train/test, affecting 3,066 rows |
| ModSec-WP | 108,883 rows; 27,686 transaction IDs; 18,474 text representations | C/mixed basis: 81,197 repeated rule rows, 20 conflicting transaction IDs; not 108,883 physical requests |
| Kyoushi scenario1 slice | 408,477 access lines; 406,692 method/URI request lines | C: 406,402 attacker labels, 2,075 UNKNOWN; positive-only slice, not benign FPR evidence; full archive checksum unverified |
| CSIC transcript benchmark | 97,065 transcripts; 34,561 observable identities | C: anomaly includes invalid nonmalicious requests; 626 identities cross original train/test; test never moved into fit |
| PKDD flattened mirror | 24,504 train / 25,612 test records | C: mirror/context and time limitations; normal train only historically considered for research |
| OrganizationX | 211,178 distinct log observations | E: unlabeled; non-alert/HTTP200/nonmatch is not benign |
| OpenCitations prefix | 100,000 rows; 90,334 unique observations | E: unlabeled, partial request observability; no new full archive download |
| Native GLU207 frozen TRAIN | 41,607 rows; 41,585 feature views | D/scenario research attribution; subset of the same 69,345 fused capture, not an extra physical corpus |
| Existing Student/Nginx/Suricata runtime captures | Global distinct request count UNKNOWN | Multiple telemetry streams/snapshots must be correlated; technical acceptance is not a benign label |
| Grounded v3 union | 236 receipts; 219 Oracle-supported target labels | A/E, human review PENDING; includes P0 111 and later cohorts; do not add parents again |
| Exposed body8 | 4 XSS attempts + 4 benign controls | A, EVALUATION_ONLY; unsafe reflection does not establish browser execution; not processed/reassigned in this pilot |
| Earlier Juice pilot/factory | Factory33 requests/21 feature views; earlier pilot8 planned cases | Development only; cross-cohort uniqueness unverified; factory fit/evaluation gates failed |
| AIT/MWAD/WAF-benchmark/IoT-CVE material | Local slices/examples exist | Related, flow/URI-only, generated, reconstructed or exposed test material; no new scalable strict admission |
| Biblio-US17 | Authorized RAW+LABEL copy **absent** | Publisher large counts are claims, not local capacity; request-copy/usage and reviewed-subset verification pending |

Licenses and version/file references are recorded **per source** in the JSON.
Examples: WAF MIT card claim, SR-BH CC0, WAMM repository CC BY4, SOC/ModSec CC BY4,
Kyoushi/AIT CC BY-NC-SA4, ANII mirrors CC BY4 with original lineage limitations,
Open-appsec legitimate-data Apache-2.0 grant. None grants public distribution of
our sensitive sessions. All raw HTTP/PCAP, keys and private evidence stay local.
The current [WAF card](https://huggingface.co/datasets/puyang2025/waf_data_v2) and
[Open-appsec repository](https://github.com/openappsec/waf-comparison-project)
were checked as small metadata references; they do not provide our independent GT.

**There is no verified additive total of unique physical requests across the
repository.** WAF, WAMM, logs, feature vectors, copied captures and derivatives
cannot be summed toward 2M. Existing 76-feature WAF/WAMM overlap evidence finds
4,156 shared numeric views; this is not proof of identical HTTP transactions.

## Qualified counting and labels

The counting unit is a **distinct receipt-backed transaction in a trusted capture
namespace**. Nginx, Student and Suricata records join only through trusted transaction
identity and existing causal/availability contracts. Timestamp/IP/flow proximity
alone is insufficient. Source SHA plus row index provides traceability, but does
not establish a physical transaction or a valid target label.

Three units remain separate: physical event identity, complete request
representation, and versioned feature view. Private HMAC keys protect opaque
identifiers; no raw header/body or per-secret value is exported. Identical recorded
representations are conservatively excluded from additional qualified novelty,
while physical accounting retains independently identified events. Repeated views
must not receive excess future gradient weight.

| Tier | Evidence | Use in this milestone |
|---|---|---|
| A | Collector intent + request-bound application Oracle | Research admission allowed; independent human review not required |
| B | Genuine independent human decision with request-bound provenance | Eligible after actual verification; none invented here |
| C | Publisher-provided annotation, retained in its declared task | Separate exploratory publisher-task pool; no automatic upgrade to attack intent |
| D | Heuristic/detector/model/scenario-only attribution without semantic support | Quarantine from strict target labels |
| E | Unknown/unverified | No supervised label |

This profile targets **attack intent**, not publisher anomaly classification.
It does not declare every C source intrinsically unusable: a separately justified
publisher-task experiment can retain C provenance and uncertainty. Existing source
restrictions still apply. No formal admission policy was changed.

## Fixed ≤10K pilot

Selection was frozen before ingestion: all 236 exposed v3 TRAIN/CAL/DEV records,
plus 4,882 rows from the beginning of each of WAF's two row groups. Zero-based WAF
windows are `0..4881` and `1048576..1053457`. Selection used metadata, no model scores
or desired labels. This is a pipeline validation sample, not a prevalence estimate.

| Counter | Result |
|---|---:|
| TOTAL_SOURCE_ROWS | 10,000 |
| UNIQUE_HTTP_REQUESTS with trusted receipt identity | 236 |
| FEATURE_COMPATIBLE, explicit runtime634 profile | 10,000 |
| LABEL_SUPPORTED for attack-intent task | 219 |
| STRICT_ELIGIBLE | **74** |
| TRAIN_ADMITTED | **48** records / **42** views |
| CALIBRATION_ADMITTED | **10** records / **10** views |
| DEVELOPMENT_ADMITTED | **16** records / **16** views |
| QUARANTINED | **9,926** |
| UNKNOWN target intent | 9,777 |

UNKNOWN includes 9,764 publisher-anomaly rows and 13 unknown-intent lab rows.
Four additional declared lab intents lack verified Oracle support, so total
`TARGET_LABEL_UNSUPPORTED=9,781`. All are quarantined, never relabeled benign.

Strict composition: TRAIN benign27/attack21; CAL benign8/attack2; DEV benign11/
attack5. TRAIN retains SQLi5/XSS10/command4/file2 attack records. Strict DEV now has
XSS2/file3 and **no SQLi or command cases**. This is not a complete scaled evaluation
set. Every admitted record was already present; **incremental strict yield from
9,764 WAF rows is zero**. The pooled yield 0.74% is not a forecast for new sources.

The WAF windows contain publisher normal7,537/anomalous2,227, retained as C with
that task. Their wire-body completeness/encoding is unattested, so body state is
**MISSING**, never fabricated EMPTY. Across all pilot inputs: EMPTY150, MISSING9,768,
OK82. Computable 634 shape does not establish complete body observability.
No 207 features were synthesized: **GLU207 pilot compatibility=0**.

There are 9,175 request-representation keys within their own namespaces, 4,379
feature views, and 825 repeated representation extras (8.25%). These are not
certified global physical dedup counts. The 4,219 syntax/workflow proxies are not
4,219 independently verified business workflows. Strict TRAIN has 19 workflow
categories and 12 unified lineage components, across two already-known labs.

## Split and leakage findings

The prior protocol admitted 154 records. The new profile quarantines **80 additional
existing records**: CAL3 and DEV77. It forms transitive closure across request/raw/
template/view relations **together with** session/campaign lineage, keeping excluded
rows as bridges. The old protocol checked direct representation overlaps and
session/campaign closure separately.

Two mixed-role components contain 122 and 31 rows. The first links P0's 111 DEV
records to 11 CAL records; the second links 20 TRAIN to 11 CAL records. Existing
TRAIN48 remain admitted. This conservative graph exposes an independence risk;
it is not proof that all component members are the same physical request, nor a
retroactive declaration that the earlier locked experiment was invalid. Original
roles, eligibility artifacts and results remain unchanged. No exact candidate-view
match between WAF and Oracle was found in this pilot; exhaustive cross-corpus raw/
near overlap remains **UNVERIFIED** because the available key namespaces differ.

Approximate near checking uses four 16-bit bands of fixed syntax SimHash, verifies
Hamming≤3 and caps each candidate bucket at256. Saturation quarantines all members;
**8,709 rows** saturated buckets. This measures a coarse-index limitation, not a
near-duplicate rate or proof of semantic equivalence. It must not certify 2M-scale
independence. No unbounded all-pairs computation was used.

An aggregate-only probe of the existing SR-BH index applied a ±600-second embargo
at its documented July18/July19 boundaries: **23,054 and 522 records**, respectively,
lie inside the windows. Two records lack time. The interval is a conservative
minimum above the old60-second feature window, not proof against longer campaigns
or unknown clock skew. No new temporal roles were assigned. Random row splits,
source/class separation and exposed DEV reuse cannot establish independent quality.

## Pipeline, reproducibility and resources

The extension reuses existing privacy/features, SQLite patterns, atomic JSON,
RunLock and independent resource guard. It adds a bounded admission index and two
fixed source adapters; it is not a replacement formal-review framework.

- SQLite16MiB cache, disk indexes and ≤256-row commits; cursor and rows commit in
  the same transaction. Progress JSON is an atomic projection; SQLite recovers it
  after a stale projection. Source/config/code/key fingerprints bind resume.
- Actual process1 stopped at cursor2,500; process2 resumed and committed the remaining
  7,500. A separate rebuild of the **same**10,000 coordinates produced byte-identical
  decision ledger and semantic summary. Four focused adversarial tests and Ruff PASS.
- Attempt r1 omitted explicit template graph edges in the source adapter. Its output
  is preserved as diagnostic, excluded from the final valid-pipeline claim. R2 fixed
  the implementation under the same policy/windows; counts stayed74. There were
  30,000 ingestions across r1/r2/rebuild of the same10,000 positions, **not30,000 new
  requests**. No new source positions or model experiments were added.
- Valid pilot wall time, including both guards: **170.24s**, **58.74 candidates/s**.
  Rebuild167.19s. CPU quota25% of **one core**, observed own CPU≈24.6–24.7% of one
  core; host mean6.6–7.5%. Pilot cgroup peak≈223MiB; all-phase peak≈647MiB including
  source/metadata index reads and file cache. Minimum MemAvailable stayed above20GiB.
- Peak pilot temperature **72°C**, active averages50.3–50.7°C; rebuild peak61°C.
  Independent sensors/watchdog stayed healthy, no pauses/emergencies/restarts.
  Rolling80°C/instant85°C protections and4GiB reserve retained. Actual windows were
  shorter than300s; no sustained300s or 2M-load safety claim. No user apps terminated.

Pilot dataset fingerprint:
`232d39885150b5712492dc628d2703a5f29702d90463a9f8f8ecaaf136812005`.
Private runs: `ai-training/.artifacts/data_scaling_20261109/pilot-r2/` and
`rebuild-r2/`; invalid r1 diagnostics remain separate. Keys, row ledgers, SQLite and
vectors stay local ignored. Aggregate metadata alone is published. A fresh,
authorized host can create private controls with
`ai-training/scripts/prepare-http-scaling-pilot.py` under the same resource guard,
then invoke `scale-http-admission.py` on a fresh output directory. The helper refuses
existing controls; it was added after the actual run and checked for safe refusal,
not exercised as a new capture/run. The historical lock is published as nonsecret
metadata in the JSON; exact historical rebuild additionally requires the retained
private HMAC key and authorized datasets. No key is distributed with Git.

## Scale estimates and decision

The following are **linear candidate-processing estimates**, not time or capacity
to obtain N qualified requests. Metadata includes the current index/decision ledger;
634-feature storage is exact float32 payload size. Raw/evidence storage is unknown.

| Qualified target | Gap from pilot-verified74* | Time for N candidate rows | Metadata estimate | 634 features |
|---|---:|---:|---:|---:|
| 10K | 9,926 | 2.84min | 32.2MB | 25.4MB |
| 100K | 99,926 | 28.4min | 322MB | 254MB |
| 500K | 499,926 | 2.36h | 1.61GB | 1.27GB |
| 1M | 999,926 | 4.73h | 3.22GB | 2.54GB |
| 2M | 1,999,926 | 9.46h | 6.44GB | 5.07GB |

*This is the gap from the **verified pilot pool**, not an exact global shortage
census. Qualified capacity elsewhere remains unverified. Future rejection/yield,
raw storage, disk-index growth and source semantics cannot be extrapolated from
this mixed pilot. No locally verified large source currently supplies the missing
strong-intent volume. The 2M goal is **not yet evidenced as achievable**.

Stage1 requires an actual10K qualified release with request-level label provenance,
whole-group roles, benign GET/form/JSON/hard negatives and meaningful attack-family
coverage. Before100K, validate that release and incremental replay/recovery; before
500K/1M/2M, grow independent sources/campaigns and time periods, verify per-source
label/feature/privacy yields and bounded processing at each stage. All later stages
are conditional, not commitments. No100K campaign or scaled training is authorized
by this report. Keep v2, GLU207, full-v3 and adapter unchanged; the ~10M parameter
objective is separate from request admission and does not justify model growth.

**One next task:** obtain and verify one authorized ≤10K request-level reviewed
RAW+LABEL+README subset. Biblio-US17 is an access-limited candidate, not admitted
capacity: [official item](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e).
The metadata probe returned403; no archive was downloaded and no author message
was sent. Require explicit permitted-use evidence, stable RID/raw joins and actual
review provenance, matched benign/attack labels and precommitted group roles.
Publisher manual-review claims alone do not become tierB; CLEAN is not uniformly
reviewed benign. Retain missing headers/body/time honestly. Finish at10K actual
qualified requests or report the exact source/rights/review gap; do not fill the
count with weak labels. This targets the missing evidence rather than processing
more copies of the same weak corpus.

213 protected files remained hash-identical, including frozen models, previous
v3/adapter evidence, existing datasets and experiment sources. No Student/Security/
Nginx/Suricata/Rust/Policy/inference/threshold/release changes, no sealed access,
training, enforcement, AWS, force-push or main merge.
