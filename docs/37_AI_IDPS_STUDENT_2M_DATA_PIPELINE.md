# 37 — Kế hoạch tự động 1M TRAIN examples cho AI-IDPS 10M

**PLANNED / POSTPONED — 11/11/2026. Không capture hoặc train trong milestone demo.**
Mục tiêu hiện hành là ≥1.000.000 HTTP requests phân biệt có evidence hợp lệ và
≥1.000.000 unique eligible TRAIN examples;2M là mục tiêu lịch sử. Hai bộ đếm
khác nhau: một request có nhiều logs vẫn chỉ một transaction; epoch không tạo mẫu.

### Lựa chọn kỹ thuật

Tái dùng admission SQLite, receipts fsync, feature hashing, checkpoint và supervisor
hiện có. Không xây framework mới. Dùng **một model10M đa nhiệm** đã có: intent,
publisher anomaly và self-supervision có mask nhãn riêng. Requestv2 chỉ làm baseline/
teacher weak-label có provenance; không tạo model thứ ba. Teacher không nâng nhãn
thành GOLD. Không buộc mọi row có independent human review.

**Nguồn ưu tiên và giới hạn** (metadata nguồn kiểm tra11/11/2026):

| Nguồn | Chọn dùng | Cách tính và giới hạn |
|---|---|---|
| WAFv2 TRAIN local pinSHA3e1f8bc6…a7a3fd6 | nguồn public đầu tiên cho SILVER publisher_anomaly |1.924.461 source rows, census1.612.017 HTTP representations; chưa phải runtime588 TRAIN eligible/physical receipts. Không mở eval/test/heldout |
| SR-BH2020 local | pool phụ, giữ task publisher và provenance | historical905.043 natural observations; source/campaign overlap và roles cũ phải giữ; không cộng WAMM derivative thành nguồn độc lập |
| Open-appsec legitimate | nguồn benign-workflow tham khảo hoặc unlabeled theo quyền/role hiện có | giữ supervised-fit restriction cũ và148case reserved; không lấy benchmark đã exposed làm fresh test |
| Grounded236 và first-party73 | regression/provenance; dùng đúng roles cũ | không phải nguồn triệu mẫu; benign technical success không tự thành GT |
| HTTP lab của mình | nguồn tạo physical receipts và bù TRAIN views thực | đa workflow/ngữ pháp, server receipt thật; simulated intent BRONZE, không khai man exploit success |
| Public logs chưa có nhãn | self-supervision của cùng model | UNKNOWN intent; không gán benign vì HTTP200 hoặc rule không báo |

[WAF card](https://huggingface.co/datasets/puyang2025/waf_data_v2) công bố MIT;
[Open-appsec](https://github.com/openappsec/waf-comparison-project) công bố Apache2
cho legitimate data/tooling, còn malicious collection có nhiều license. Giữ
source revision/license metadata và không public raw sessions. [Kyoushi](https://github.com/ait-aecid/kyoushi-simulation)
cho thấy workflow state-machine có thể tự động hóa; tái dùng nguyên tắc trong
runner có sẵn, không cài cả cyber range mới. [Kiểm kê23nguồn](34_AI_IDPS_2M_DATA_SCALING_READINESS.md)
và [source qualification](35_AI_IDPS_RAW_LABEL_SOURCE_QUALIFICATION.md) giữ các
hạn chế pháp lý/lineage cụ thể. Không tải Biblio chưa được cấp bản raw+labels.

### Kế hoạch thực thi hữu hạn sau khi được cho phép lại

1. **Khóa release revision và roles trước chạy.** Giữ nguồn/reserved hiện có;
   group mới phân TRAIN/CAL/EVAL80/10/10 theo hash campaign+workflow-template,
   không theo scores/record IDs. Nguồn cùng ứng dụng không phải cross-domain mới.
2. **Một pilot10K candidates**, không train: public slice có provenance và lab
   workflow mới, đo eligible-yield, template/view novelty, RAM, thermal và throughput.
   Nếu TRAIN yield thấp, dừng ở pilot để sửa nguyên nhân cụ thể; không tự chạy triệu
   request trùng rồi đổi roles. Config hiện tại tối đa1.048.576 synthetic candidates
   không thể cung cấp1M TRAIN với split80% ngay cả yield100%; cần revision mới.
3. **Một campaign tối đa2M candidates/48h**, target tối thiểu1,6M receipt-backed
   requests đa dạng khi cần bảo đảm physical target. Với TRAIN fraction0,8 và
   retention0,8 dự kiến1,024M TRAIN; đây là tính dung lượng, không phải yield đã
   chứng minh. Dừng sớm khi hai bộ đếm đạt; nếu hết budget thì báo thiếu chính xác.
   Public row không có transaction ID chỉ tăng observations/examples, không tăng
   verified physical receipts. Replay vào app lab tạo receipt mới nhưng source-label
   vẫn publisher; không được gọi replay là vụ tấn công tự nhiên thành công.
4. **Một materialization release**: incremental SQLite unique constraints/source
   cursor; immutable shards1–4K rows; transactional commit + fingerprints; exact
   request/view dedup, near-grouping bằng index/blocked candidates. Không O(N²)
   toàn nguồn. Overflow phải cách ly hoặc kiểm tra exact có giới hạn, không PASS giả.
   Nhóm xuyên role cách ly khỏi fit; không bỏ node cầu nối. Không mở sealed để check;
   chỉ dùng fingerprint reference được phép. Giữ label conflict theo task riêng.
5. **Một training run sau authorization riêng**: khóa config/code/data/split, seed,
   task masks/weights, sampling theo campaign/view trước khi nhìn EVAL. Optimizer
   và resume đã có; không dùng EVAL chọn threshold/epoch. CAL chọn operating point,
   EVAL chỉ mở một lần. Không tự promote dù metric đẹp.

### Nhãn và chống shortcuts

GOLD=Oracle/reviewer thật có lineage; SILVER=publisher task; BRONZE=weak/synthetic/
pseudo-label có phiên bản rule/model và confidence; UNLABELED chỉ self-supervision.
Intent/outcome/review là ba cột riêng. UNKNOWN không vào supervised loss tương ứng.
Mỗi canonical view chỉ được tính một example; nhiều objectives trên cùng view
không tăng số đếm. Dataset feature-contract588 phải trùng runtime; body46/GLU207
không được padding vào hợp đồng này. Missingness ghi rõ. Không đổi privacy để đạt1M.

Generator cần catalog/search/filter/auth/form/JSON/CRUD và hard negatives với cả
benign/attack intent trong từng method/source; random nonce, timestamp, UA không
được coi là semantic diversity. LLM chỉ soạn scenario specs hữu hạn rồi freeze;
HTTP runner mới tạo request/receipt. Không dùng LLM để chứng nhận independent GT.
Dành template/campaign/app mới cho tương lai; giới hạn tỷ trọng một template/source,
đo per-source/method/body states, group-weighted metrics, source-only prior baseline,
OOD mới, và lỗi FP benign POST/XSS/command. Giảm collision chưa chứng minh tăng recall.

### Ngân sách thực tế và tiêu chí thành công

Máy16CPU/32GiB-class; giữ4GiB MemAvailable. Feature1M×588×float32≈2,19GiB,
1,6M≈3,50GiB;2copies+index/SQLite+raw receipts có thể cần20–40GiB disk.
Model10,07M float32≈38,4MiB, weights+grad+Adam≈154MiB chưa kể temporaryFP64/activations.
Dùng mmap/shards, một ingestion writer và tối đa2encoder workers sau benchmark.
Không tải cảraw corpus/feature matrix nhiều bản lênRAM; raw chỉ local.

Lượt cũ đo62,3receipts/s trong một cửa sổ quota50%ONE core nhưng sau đó thermal
stop: **không phải sustained-safe throughput**. Tính toán1,6M/20–60requests/s là
7,4–22,2giờ chỉ capture; admission/dedup/rebuild thêm thời gian chưa đo.
Tại yieldTRAIN≈7,9% của200K trước, mở rộng y hệt sẽ không đạt mục tiêu trong2M;
phải kiểm chứng source/contract/campaign diversity ở10K trước. Không tăng quota
hoặc lặp template để che yield thấp. Thời gian training10M chưa có benchmark thật;
không lấy2preflightupdates làm ETA. Sau này chỉ đo cửa sổ đã khóa trong run chính.

Nhanh nhất thực tế: tận dụng public TRAIN đã có, cache projection theo content,
materialize+dedup streaming đồng thời capture thật; ưu tiên data diversity thay
thêmepochs. Gate cuối yêu cầu unique TRAIN≥1M, physical receipt counter≥1M nếu
đang tuyên bố mục tiêu physical, coverage/label masks/leakage/privacy PASS. Nếu
chỉ đạt observations thì báo đúng observations. Promotion cần evaluation so sánh
và chủ dự án duyệt, không theo parameter count hoặc training loss.

---

## Hồ sơ lịch sử (không phải trạng thái live hiện hành)

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