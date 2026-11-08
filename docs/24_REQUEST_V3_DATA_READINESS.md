# Request Intelligence v3 — derivative data readiness, 2026-11-08

**CASE B — DATASET IMPROVED, TRAINING BLOCKED.** Materialization, research privacy,
reproducibility và strict candidate splits đã kiểm chứng. TRAIN coverage chưa đạt;
DEVELOPMENT chưa có benign POST để kiểm tra false positives của body signal.
Không phát request, tính model scores, training hoặc tạo checkpoint trong milestone.

Baseline `8e069f0`, branch `feature/ai-idps-shadow-integration`, working tree sạch khi
bắt đầu. Dùng lại attack-intent release và body/live acceptance; không sửa hạ tầng,
models, thresholds, Rules/Policy, Web, Nginx, Suricata hoặc correlation. Candidate OFF.
GLU207 live regression vẫn PARTIAL nhưng **không là dependency** của offline Request v3.

Machine evidence: [readiness report](../ai-training/reports/REQUEST_V3_DATA_READINESS_20261108.json).
Contract: [634-input candidate](../ai-training/configs/research/request-v3-body-syntax-v1.json).
Single design/evaluation/recovery plan:
[locked design](../ai-training/configs/research/request-v3-body-syntax-design-20261108.json).

## Derivative đã tạo và cách tái lập

Dataset version `request-v3-body-syntax-20261108-v1`, final build directory
`ai-training/.artifacts/request_v3_body_syntax_20261108/release-v2/`.
Dataset fingerprint:
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`.
Parent `attack-intent-v1-20261107` fingerprint giữ nguyên:
`fa9a2d87852afea879ed146d4bd8077e8a070d42337d6b36ffe836686a4fef5f`.

**224/224** receipt checks, frozen-prefix references và body-vector parity với
materialization Nov7 PASS. Fresh-output rebuild có **7/7 files byte-identical**,
không chỉ giống aggregate counts. Final `dataset-release.json` bổ sung fingerprints,
file checksums, gates và design binding; không đổi các files materialization.

Mỗi row private có sample/request IDs, source/environment, workflow và ordinal
session/campaign groups, original role, intent/outcome riêng, inherited Oracle/review
tier, parent record/frozen tensor reference, 46 raw numeric features, feature/schema
fingerprints, availability/state/truncation và inclusion/exclusion reasons. Mỗi row
mang dataset fingerprint; fingerprint được tính trước khi thêm chính field đó để
tránh vòng lặp. File SHA bindings của tensors/records được lưu riêng trong manifest.

Ba NPZ theo role chứa float32 `x[N,634]`, frozen prefix `[N,588]`, uint8 body syntax
`[N,46]`, opaque sample IDs, binary labels, strict mask và paired-common mask.
Không lưu raw URI/body/headers/response, arbitrary field values, cookies hoặc secret
digests vào release cuối. Per-request metadata/tensors vẫn **LOCAL ONLY**.

Builder và verifier không có HTTP client, model fitting hoặc holdout loader:

```sh
# Yêu cầu permitted local evidence gốc, không cần cho inference/bootstrap của team.
# Luôn chọn output mới; không overwrite release đã có.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ai-training/.venv/bin/python \
  ai-training/scripts/materialize-request-v3.py --lock-plan --plan NEW_PLAN.json
# Chạy materialization/verifier trong integration-guard.py với quota25%, cutoff85C,
# memory budget2GiB và reserve4GiB như evidence milestone, rồi truyền:
# materialize-request-v3.py --plan NEW_PLAN.json --output ai-training/.artifacts/NEW_RELEASE
# verify-request-v3.py --release ai-training/.artifacts/NEW_RELEASE --output NEW_PROOF.json
```

Plan khóa source hashes, fixed normalization, near rules, inherited exclusions và
coverage minimums trước materialization. Plan đầu và plan sửa metadata đều giữ ở
`.local-dev/request-v3-20261108/`; không đổi feature/label/role/gate để cải thiện số liệu.
Tái lập cần đúng local receipts được parent release cho phép; không đọc mixed-role
ledgers, prospective samples hoặc 12 sealed records. Clone/bootstrap/model restore
không thay đổi và không yêu cầu tải private derivative.

## Tensor và normalization đã khóa

| Offset | Width | Semantics |
|---|---:|---|
| 0 | 76 | Frozen runtime numeric, bounded-request-v1, exact inherited column ordering |
| 76 | 512 | Frozen rich_content_v2 của URI + User-Agent/Accept/Content-Type, body=None; unsigned char3–5 hashing, shared L2 |
| 588 | 46 | http-body-syntax-v1 ordering, float32 integer/fixed maximum |

634-input contract fingerprint:
`d186dd653d9e2d4e7af77469766465144a3778a4f4a5202229a47d4ebc5feaa5`.
Body contract SHA vẫn
`0e163b7392a9bb68131e4c66486fa5827ce6259295f0d703b403a8efad96982c`.
Numeric prefix dùng frozen `log1p(v)/(1+log1p(v))` cho counts, flags/ratios giữ nguyên;
content vectorizer theo frozen runtime contract (lowercase, unsigned char3–5/512/L2).
Body one-hot/flags chia1, field buckets chia6, punctuation counts chia3. Mỗi feature
trong [0,1]; không fit means/std/vocabulary hoặc dùng CAL/DEV để scale. Điều này tránh
raw count scale lấn át từng feature khác, không chứng minh mọi block có ảnh hưởng bằng nhau.
Missing/empty/unsupported/truncated states không bị impute thành nhau; non-OK tail0.
Đây là contract riêng; không nối634 vào frozen588/207 hoặc đổi deployment threshold.

## Collision re-audit và strict eligibility

| Representation, toàn224 | Unique views | Mixed groups | Affected records |
|---|---:|---:|---:|
| Frozen runtime | 122 | 2 | 35 |
| Runtime + body syntax | 158 | 1 | 6 |

Stored-XSS group29 (19benign/10attempts) từ1view thành23views, không còn exact
opposite-intent collision. JSON login vẫn1view/6records:3benign,2SQLi,1UNKNOWN.
Email/password values bị loại có chủ đích; giữ collisions và exclusions. Không đưa
identities/secret hashes vào model để tách nhóm này. 6affected gồm1UNKNOWN, không có
nghĩa6known label errors. Không suy Recall/FPR từ giảm collisions.

| Role | Receipts | Parent strict | Candidate strict | Candidate unique strict | Benign / Attack |
|---|---:|---:|---:|---:|---|
| TRAIN | 63 | 10 | **43** | **37** | 23 / 20 |
| CALIBRATION | 37 | 13 | **13** | **13** | 11 / 2 |
| DEVELOPMENT | 124 | 86 | **86** | **83** | 40 / 46 |

TRAIN thêm33eligible records:19benign và14attacks (10XSS,4command). Chỉ runtime
collision/exact/near và within-role view reasons được tính lại. Giữ nguyên mọi
raw/template/full-view/full-near, prior admission, Oracle/UNKNOWN và opaque reserved
exclusion; kiểm session/campaign và cả lineage components qua excluded bridge rows.
Không đổi vai trò hoặc nhãn, không dùng scores. Strict view không đồng nghĩa mỗi
receipt có tensor khác: TRAIN43 chỉ37views, DEV86 chỉ83views.

Near rule đã khóa: cùng method/endpoint, frozen content cosine≥0.995 (tol1e-7),
và body normalized L-infinity distance≤1/3. Mức1/3 là một punctuation-count unit;
state/media/binary flag đổi1 không được coi near. Hai block phải cùng near để tránh
concat cosine bị scale chi phối. Inherit full-view near exclusions lịch sử.
Across-role candidate near pairs31, frozen-runtime-only62; cả hai phía quarantine.
Raw6/template4/full-view2/candidate-view3 cross-role exact groups trước quarantine;
strict admitted candidate subsets có **0 cross-role exact/lineage/near overlaps**.
Frozen-prefix similarity có thể còn khi body phân biệt được; không gọi prefix độc lập.
Workflow categories/environment vẫn trùng nguồn; đó không phải independent campaigns
hoặc cross-domain evidence. Candidate/runtime overlap với sealed **UNVERIFIED**,
không mở seal để debug; protocol hiện tại không sử dụng sealed evaluation.

## Coverage và shortcut risks

| Strict coverage | TRAIN | CALIBRATION | DEVELOPMENT |
|---|---:|---:|---:|
| Unique benign views | 19 | 11 | 40 |
| SQLi / XSS / command / file views | 4 / 8 / 4 / 2 | 0 / 2 / 0 / 0 | 12 / 13 / 3 / 15 |
| Benign GET / POST receipts | 4 / 19 | 6 / 5 | 40 / **0** |
| Benign GET / POST workflow categories | 3 / 3 | 4 / 2 | 3 / **0** |
| Recorded lineage components | 11 | 7 | 2 |
| Benign POST media | FORM | FORM + JSON | Không có |

TRAIN có14workflow categories nhưng11recorded lineage components; không gọi14là14
independent samples. Benign technical stored notes/literals và reflected technical
names là controls có provenance, không gán hard-negative labels mới từ model scores.
TRAIN giữ cảbenign/attack ởDVWA vàJuice, nhưngJuice chỉ4eligible records. Command và
file TRAIN **không có benign counterpart cùng environment/method/endpoint**; endpoint
shortcut vẫn là rủi ro. SQLi/XSS có counterparts; JSON-login information vẫn bị withheld.

TRAIN đã giải quyết thiếu XSS/command views và benign form POST. Hai locked checks
còn FAIL: **benign JSON POST** và **same-surface benign command/file controls**.
CAL đạt minimum cho pilot nhỏ, không đủ population FPR hoặc mọi attack family.
DEVELOPMENT có6attack POST và0benign POST: một POST/body-presence shortcut có thể
trông tốt mà không trả giá false positive. Đây là thiếu controls cần giải quyết trước
khi giữ một candidate có apparent improvement; protocol đánh giá đã khóa nhưng
adequacy của dữ liệu hiện tại chưa đạt.

Một availability shift khác:224receipts có149EMPTY+75OK,0MISSING/unsupported. Live ON
trước có17MISSING/32requests. Body states phản ánh framing thực tế trong receipts;
không đổi chúng thành MISSING hoặc thêm fake samples. Cần controls có absent body
thật ở acquisition sau và giữ giới hạn cho unsupported cases.

## Privacy finding, correction và evidence tier

Scan đầu **FAIL thực sự**: inherited `session_group` của một số nguồn là digest của
session cookie. Copy field đó vào derivative mới vi phạm privacy intent dù không
có raw body. Không waive scan hoặc chỉ tăng độ dài canary để bỏ qua.

Sửa metadata thành ordinal aliases (`session_group-0001`, campaign tương tự), không
hash/reencode cookie. Verifier kiểm bijection của grouping trên224records, giữ đầy
đủ lineage để quarantine. Không đổi feature vectors, nhãn, roles hoặc coverage rule.
Bản sao `records.jsonl` không an toàn do milestone này vừa tạo được loại khỏi rejected
build; rejection metadata/counts/checksums/diagnostics giữ local. **Source receipts,
parent frozen dataset và evidence gốc không xóa hoặc sửa.** Final build v2 tách riêng.

Final privacy PASS_FOR_RESEARCH: scan137source values trong RAM cùng literal,
URL/base64/hex/SHA1/SHA256/JSON-escaped trên7core artifacts;6fake-secret families
kiểm protected-value invariance và numeric JSON/NPZ serialization. Không persist các
values/digests dùng cho scan. Reuse real-ingress privacy qualification của milestone
trước; lượt này không chạy HTTP hay claim live delivery mới cho224receipts.
Numeric/structural side channels và linkability metadata vẫn có, artifacts per-row
local-only. **PRODUCTION_PRIVACY=NOT_VERIFIED**, không có DP/absolute guarantee.

Parent labels giữ130benign/81attack/13unknown;207internal application Oracles.
Toàn bộ142eligible rows có Oracle. Human review224PENDING,0independent verification.
Unsafe reflection vẫn không phải confirmed browser execution; UNKNOWN/unverified
không fit. Không dùng formal human admission để giả tạo blocker cho research pilot.

## Một challenger và evaluation/recovery plan

Chọn **một634→64→64→64→64→8 deep MLP**,53,640parameters; tăng đúng2,944parameters
(46×64), không tăng width hoặc thử nhiều architectures. Versioned warm start mở rộng
**W0**, copy588rows cũ và thêm46zero rows; các layers sau giữ nguyên. Synthetic
forward parity atol1e-7 PASS,0updates/0checkpoints. Đây là WARM_START với optimizer
reset, không phải direct588tensor compatibility hoặc EXACT_RESUME. Binary intent
objective dùng existing `partial_binary_v1`, family_weight0, không gộp publisher anomaly.

Frozen Request v2 và calibration-only giữ làm hai references. Same-data evaluation
trên canonical joint views thuộc intersection parent/candidate strict CAL/DEV;
hiện13CALreceipts/86DEVreceipts,83jointDEVviews. Frozen threshold giữ nguyên;
control/candidate strict>maxeligibleCALbenign, không optimize trên attacks/DEV/P0.
Một final checkpoint, không best-DEV selection/sweep. Pilot sau tối đa128updates
hoặc20epochs, điều kiện nào tới trước, batch16; **không có job hoặc checkpoint hiện tại**.

Retention screen: thêm ít nhất2XSS và2command flags so với reference tốt hơn, không
flag thêm benign IDs so với cả hai references, không giảm SQLi/file TP trên cùngIDs;
không đạt thì REJECT/INCONCLUSIVE. Phải bổ sung DEVbody negatives trước khi giữ gain.
Data đã lộ chỉ hỗ trợ descriptive research, không independent quality, temporal
future test hoặc cross-domain claim. CAL11benign/DEV40benign và dependence không đủ
certify FPR≤1%. Không thay shadow model từ experiment này.

Recovery plan READY dưới dạng thiết kế: persist weights/moments/step, objective,
RNG/permutation/cursor/epoch/scheduler và source/data/feature fingerprints; atomic
manifest/checksums; storage riêng. Actual634 cross-process exact next-update proof
còn bắt buộc trước fit ở milestone sau, **chưa chạy** vì lượt này không training
hoặc tạo synthetic checkpoint. Resource monitor cũng phải revalidate trước fit.

## Gate decision và một nhiệm vụ tiếp theo

| Gate | Kết quả |
|---|---|
| DATASET_INTEGRITY | PASS |
| LABEL_PROVENANCE | PASS_FOR_RESEARCH cho eligible Oracle rows |
| STRICT_SPLIT_INTEGRITY | PASS cho permitted exposed candidate roles; sealed overlap chưa xác minh |
| TRAIN_COVERAGE | **FAIL**: JSON benign POST và command/file counterparts |
| CALIBRATION_COVERAGE | PASS cho bounded pilot, sample/group limits giữ nguyên |
| FEATURE_CONTRACT | LOCKED |
| PRIVACY_GATE | PASS_FOR_RESEARCH sau metadata correction |
| EVALUATION_PROTOCOL | LOCKED; current DEV body-negative coverage FAIL |
| CHECKPOINT_RECOVERY_PLAN | READY; actual634 recovery proof chưa thực hiện |
| FROZEN_BASELINE | PROTECTED |

**TRAINING_READY=false.** Một nhiệm vụ tiếp theo duy nhất: **one bounded Oracle
control supplementation, tối đa24receipts**, giữ CAL và prospective nguyên trạng.
Precommit TRAIN/DEVELOPMENT workflow/session/campaign/templates trước HTTP/scores.
TRAIN bổ sung đúng3cells: benign JSON POST mới, legitimate command-form POST có
execution Oracle, public-file/include GET có public-content Oracle. Mỗi gap phải có
ít nhất1new unique eligible view. DEV bổ sung ≥6unique benign POST views qua≥3real
workflows, FORM+JSON, gồm legitimate technical hard negatives. Hai roles cần có
absent-body GET controls thật khi feasible; không force framing để làm đẹp state.

Preflight exact/template/full-near/candidate-near trên permitted exposed release và
planned cross-role cells trước capture; không copy TRAIN templates sangDEV hoặc dùng
IDs/headers/padding đổi tên để gọi novelty. Nếu Oracle benign command không chạy được
hoặc không tìm được structurally disjoint workflow, dừng và ghi đúng gap; không gán
benign từ200, hạ gate hoặc phát filler. Cap24là giới hạn, không là tiêu chí PASS.
Không thực hiện campaign đó trong milestone này.

40final Python tests PASS; ban đầu fixture thiếu request_id và validator chưa bắt
excluded cross-role lineage bridge được sửa trước materialization. Ruff/format PASS.
Tất cả workloads dùng25%one-core/cutoff85°C/reserve4GiB; materialization v2 peak71°C,
active average66.09°C, mỗi processing guard chỉ vài giây. Không sustained300s claim,
không sửa OS/firmware hoặc đóng user apps.158protected files và parent release giữ
nguyên; không mở sealed samples, tạo checkpoint, enforcement/AWS hoặc published release.
