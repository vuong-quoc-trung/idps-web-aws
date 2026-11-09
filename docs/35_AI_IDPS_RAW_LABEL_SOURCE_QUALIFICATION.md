# AI_IDPS_RAW_LABEL_SOURCE_QUALIFICATION — 2026-11-10

**CASE C — SOURCE INACCESSIBLE.** Biblio-US17 is a verified source, but the
repository reports **embargo** and its archive HEAD returns **401**. No authorized
RAW+LABEL copy was found in the approved project artifact/catalog paths. Therefore
**0/10,000 candidate records processed; 0 new strict requests; no staging release**.
No sampling plan or admission/rebuild run was started. This is an access-gate
outcome, not evidence that the dataset is intrinsically invalid.

[Machine report and evidence fingerprints](../ai-training/reports/AI_IDPS_RAW_LABEL_SOURCE_QUALIFICATION_20261110.json).
Starting HEAD `6209e6b`, clean, branch `feature/ai-idps-shadow-integration`.

## Verified identity and access

Official item: **Labeled HTTP requests dataset: Dataset Biblio-US17**, DOI
`10.12795/11441/148254`, idUS item `53034f60-d215-44b0-a198-eb8a5229218e`.
The [official item API](https://idus.us.es/server/api/core/items/53034f60-d215-44b0-a198-eb8a5229218e)
identifies the five creators, a July2023 release and the repository rights statement.
The [author documentation](https://dtstc.ugr.es/neus-cslab/recursos/ds-biblio/)
and [publication](https://link.springer.com/article/10.1186/s42400-024-00336-3)
confirm the source. Publication date is June5,2025; the DOI's2024 component is not
its publication date. No numbered dataset version was verified.

Metadata advertises `Biblio-US17.tar.gz`, **1,223,176,305 bytes**, bitstream
`17b2ff3b-90ea-48a4-8ecd-a12edc394361`, declared MD5
`bda3bc86b8bb6d8768e88431a861b737`. This checksum is repository metadata, **not a
locally verified archive hash**. The metadata APIs return200;
[accessStatus](https://idus.us.es/server/api/core/items/53034f60-d215-44b0-a198-eb8a5229218e/accessStatus)
says embargo. One ordinary unauthenticated HEAD per archive/two repository README
bitstreams returned401. No content GET, Range retrieval, authentication, mirrors,
bypass or request-copy submission followed. The earlier web-tool frontend403 alone
would not have established this origin-level blocker.

## Rights and provenance limits

The public [README](https://dtstc.ugr.es/neus-cslab/wp-content/uploads/2023/08/README.txt)
states research use under **CC BY-NC**, while current idUS metadata specifies
**CC BY-NC-ND4.0**. Intended-use rights are therefore **UNKNOWN**, separate from the
confirmed access blocker. The public README is11,540bytes, versus14,143bytes for
the inaccessible repository README: matching document versions were not verified.
The article's CC BY4.0 does not license the dataset.
ND is not a blanket prohibition of private noncommercial adaptation: the
[legal code, section2(a)(1)](https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode.en)
distinguishes producing/reproducing adaptations from sharing them. No applicable
access/retention or derived-artifact sharing permission was inferred for this project.
Only permitted public documentation/metadata was inspected.

The source is documented as processed/anonymized **Apache log observations**, not
wire HTTP. Its RID encodes original day, HTTP/HTTPS service and log ordinal; this
is stronger provenance than inventing IDs during import. Actual uniqueness,
RAW/LABEL joins and custody remain unverified without records. A legitimate
single-source external log dataset does not need artificial three-source telemetry.

Publisher labels have a documented expert-assisted methodology: S1 detector
flags, S2 TP/FP inspection and S3 vocabulary review/propagation. This is not proof
that every request received independent human review. Missing LABEL/default values
are not reviewed benign; CLEAN is not uniformly reviewed benign. Attack intent,
anomaly/OOS and exploit success must remain distinct. No labels were upgraded to
our independent-review tier. Detailed schema and confidence distinctions are in
[the source README](https://dtstc.ugr.es/neus-cslab/wp-content/uploads/2023/08/README.txt).

## Compatibility and capacity

| Component | Current conclusion |
|---|---|
| Frozen v2 | Method/URI projection potentially useful; no full588 parity or record-level compatibility verified |
| Request v3 /46body features | Headers/body not supplied; a future permitted partial projection must retain MISSING, never infer EMPTY; no observed body-syntax signal recovered |
| GLU207 | Unsupported causal history/flow/identity availability; no padding |
| Exact/near/cross-source checks | NOT_RUN; no clearance against WAF, SRBH/WAMM or exposed cohorts |
| Chronology | Day/order does not permit certifying a600-second embargo or session independence |

No vectors, throughput, yield, duplicate-rate or index-saturation measurements were
fabricated. Quarantine counters are0 because no records were obtained; the **source
is ON_HOLD**, rather than a fictitious quarantined dataset. Publisher47M counts
remain unverified potential, not available qualified capacity. This milestone adds0
to the prior verified74-record pilot pool; its gap to2M remains1,999,926, **not an
exact global qualified-request census**. A100K expansion is not justified.

URI-only shift/anomaly diagnostics could be a legitimate auxiliary objective after
access/rights resolution, with publisher label uncertainty disclosed. They cannot
recover the missing body signal and were not performed or trained here.

**One next action:** obtain one owner-authorized **first-party capture sample
≤10K**, with capture-scoped request IDs and request-bound application Oracle or
actual reviewer evidence. This alternative category is supported by the project's
existing receipt/Oracle path, which previously supported219labels and74strict
records; it does not imply that a large production source is already available.
Require actual observed header/body states and campaign/workflow provenance before
using the existing admission pipeline. No acquisition or third-party contact was
started; do not keep probing this blocked archive.

## Recorded state

```text
SOURCE_IDENTITY = VERIFIED
USAGE_RIGHTS = UNKNOWN
PHYSICAL_REQUEST_IDENTITY = PARTIAL
LABEL_PROVENANCE = PARTIAL
BOUNDED_PILOT = NOT_RUN
CANDIDATE_RECORDS = 0/10000
NEW_STRICT_ELIGIBLE = 0
CROSS_SOURCE_LEAKAGE = PARTIAL
DEDUPLICATION_COVERAGE = PARTIAL
PRIVACY = PASS
REBUILD = NOT_RUN
TWO_MILLION_VERIFIED_CAPACITY = NOT_ESTABLISHED
TRAINING = NOT_STARTED
FROZEN_MODELS = UNCHANGED
```

PARTIAL means documentary support without record-level verification. PRIVACY PASS
covers this audit's behavior/publication, not uninspected source contents. Private
metadata snapshots/probes reside in `.local-dev/raw-label-source-20261110/`; their
hashes are in the machine report. 188 small historical pins matched;25large payloads
were deliberately not rehashed, so this is not a new213-payload audit. No system,
encoder, threshold, label, split, model/release or sealed-data changes. No new code
or tests required for this documentation-only gate result. A metadata-only snapshot
showed54°C and22.47GiB MemAvailable; no workload/sustained thermal certification.
