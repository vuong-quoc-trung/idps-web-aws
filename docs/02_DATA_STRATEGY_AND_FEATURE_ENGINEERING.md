# 02 — Chiến lược dữ liệu và Feature Engineering

## Sau training: khả năng đánh giá GLU207 — 2026-11-04

Checkpoint mới chỉ được shadow trên **54 request ba nguồn** của capture Nov-02 có 207-vector causal/post-response; request thứ55 thiếu nguồn bị bỏ qua. Capture này **không có nhãn intent** và cùng lab với train, nên chỉ là technical diagnostic. So với 41.607 train rows: overlap request ID xuyên hai khóa HMAC **chưa kiểm được**, **3 exact float32 views lặp**; prior completed flow train36.443/41.607 nhưng shadow0/54. 143/207 cột có ít nhất một giá trị khác0 và 122 cột biến thiên; toàn0 không đồng nghĩa missing. Request-only Juice/WAF/WAMM/AIT không được padding response/flow/history để đánh giá GLU207. Nguồn có nhãn hai lớp và đủ 207 features độc lập hiện **0**; final holdout không mở, formal admission0. [Plan và report](../ai-training/PRETRAINING.md) cùng ledger 06 mục65 ghi hash và giới hạn.

## Partition và nhãn dùng cho bounded research GLU207 — 2026-11-04

Run mới dùng **đúng `prepared-v5` train**: 41.607 rows, 41.585 unique float32 views, không có train view hai nhãn; 29.511 benign/12.096 attack theo lab runner. Hai epoch tạo 83.214 sample exposures, **không** tạo thêm request hay unique views. Dataset SHA `45ca178b494446451bfeec8e30b655044df02460ef5aa9273a93143d54cd9b08`, feature spec `ai-features-5`/207 SHA `3f7fe0a8c53d9aacadd5bc4e6070fb1a0f6de2b6a0f4bf208d686e83b5c1c580`, order và preprocessing được khóa trong [freeze private](../ai-training/.artifacts/research_glu207_bounded_final_20261104/freeze.json). Validation/test không dùng để fit, tune hoặc score; final holdout không mở. Nhãn development không được nâng thành intent đã review; formal admission0, independent evaluation chưa sẵn sàng. Xem ledger 06 mục64.

## Factory lab evidence, nhãn và feature views — 2026-11-04

Juice Shop factory có 33 client sends qua AI proxy, 33 response/proxy receipts cùng request ID/method/path/body/response SHA, 33 complete-request representations khác nhau; **không** đếm proxy/app observations thành request mới. Application challenge ID45 `Login Admin` đổi `false→true` sau case SQLi login precommit, response xác nhận danh tính admin. Nguồn evidence này cho 28 benign workflow, 4 attack attempts và **1 exploit success** (subset), 1 UNKNOWN. 8 scenario campaign IDs trong **một** app/instance không có tính độc lập của nhiều môi trường. Nhãn được collector định nghĩa và Oracle ứng dụng kiểm; chưa phải review intent độc lập hay formal evidence-v2.

32 labeled rows sau loại UNKNOWN: encoder rich v1 có 20 unique views, một view trái nhãn gồm benign invalid-login và SQLi login do body chứa `password` bị bỏ hoàn toàn; 2 rows cách ly. Encoder JSON body v2 giữ cú pháp identity field khi không chứa PII, che password/token/email thật, tạo **21 unique views/0 mixed views** (17 benign/4 attack). V2 là contract mới cho nghiên cứu lab, **không** đưa vào checkpoint WAF v1 hoặc GLU207. 11 same-label duplicate view rows không là thêm unique views. Có 15 near-view pairs cosine≥0,995; thiếu campaign độc lập, header observation và 207 fused features. Với chỉ 17 benign unique views, cận trên95% FPR khi 0 FP vẫn16,16%; không đánh giá hoặc chọn model. Formal admission0. Xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục63.

## Lab intent và exploit outcome là hai tầng evidence — 2026-11-04

Juice Shop pilot mới có plan khóa trước, 8 request/response và SHA/readback trong một mạng lab cô lập: 3 `BENIGN_VERIFIED_LAB` từ workflow tìm sản phẩm và JSON name Oracle, 3 `ATTACK_ATTEMPT_VERIFIED_LAB` theo case/payload precommit và response app, 2 `UNKNOWN` vì response không đạt quy tắc; **0 exploit success** vì không có application-state/challenge Oracle. Nhãn lab do cùng collector định nghĩa intent, không thay thế reviewer độc lập hoặc formal evidence-v2; 0 Student/Nginx/EVE correlation cho app này. Không biến HTTP500/200, SQL error hay test-plan thành exploit outcome. 8 unique request representations, 0 training/evaluation mới, 0 admitted. Kyoushi scenario1 slice vẫn 406.402 attacker_http publisher rows/2.075 unlabeled `UNKNOWN`/0 explicit benign; [publisher documentation](https://zenodo.org/records/5779411) chỉ xác nhận gán nhãn event liên quan attack, không cho phép `unlabeled→benign`. Xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục62.

## WAF rich-content research cohort và collision attribution — 2026-11-04

Audit theo tầng trên WAF `train` đã pin: **192** raw exact representations trái nhãn trên 1.612.017 exact representations; với mẫu cũ 101.098 exact nonconflicting, numeric76 có 269 mixed feature keys/77.978 rows; safe symbolic+numeric trước hashing 243/43.167; float32 hashed512 cuối 245/43.171. Mất thông tin chủ yếu nằm ở canonicalization/symbolic extraction, không chỉ ở hashing. Encoder AI mới thêm buckets độ dài chữ/số, cấu trúc query/header/body, entropy thô, từ bảo mật allowlist; cùng mẫu cũ sau hashing tạo 34.169 views, 241 mixed/28.174 rows. Không khẳng định view trái nhãn là publisher label error. URL khác ở 91, header khác 180 và body khác 26 trong 245 mixed views cũ; các nhóm có thể giao nhau. Secret/PII bị che, raw HTTP không lưu vào corpus; hash của template vẫn có rủi ro suy đoán và chỉ giữ trong artifact riêng tư.

Fresh curation lấy SHA raw modulo4 residue1 (old modulo16 residue0), loại mọi safe symbolic template từng có trong old cohort. Trong 402.108 raw selected, 311.821 bị loại vì template overlap; 90.287 projectable, 73 mixed views/637 rows cách ly, còn **84.193 unique float32 views**. Train/calibration/validation chia theo 69.607 coarse safe-template groups không overlap và có cả hai publisher classes. Near-template khác group và thiếu source/campaign/time metadata vẫn là leakage/domain limit. Không đưa các views này vào GLU 207; WAF không có Student/Nginx/EVE tương quan, status/latency/flow/behavior lịch sử. Nguồn nhãn vẫn `WEAK_LABEL`; 0 machine-verified attack intent, 0 formal admitted. Study một nguồn tại budget1% đạt publisher-label recall75,04%/FPR1,086% cho content, không qua budget; xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục61.

Near-template diagnostic seed113, 2.000 validation so 10.000 train views: **580** có nearest hashed-content cosine≥0,995, **42** nearest pairs trái nhãn publisher dù coarse group khác. Đây là tương tự biểu diễn, không là bằng chứng duplicate physical request; split chưa đủ để chứng nhận độc lập.

## WAF request-content corpus và giới hạn nhãn — 2026-11-04

WAF Data v2 `train` MIT publisher claim đã được curate trong phạm vi AI:
1.611.825 exact complete-request representations không trái nhãn là ứng viên
research **NORMAL/ANOMALOUS**, không là physical request count hay confirmed
attack. SHA modulo16 lấy 101.098 exact representations; 245 combined feature
views có hai nhãn khiến 43.171 rows bị cách ly. Dedup cùng nhãn để lại
**28.336 unique float32 views** (76 request numeric +512 hashed char-ngrams
từ symbolic safe content). URI/query secret fields bị bỏ, header values không
đi vào encoder, body có private-key family bị ẩn toàn phần; HTTP method lạ
được map `OTHER` theo allowlist sau khi sửa privacy ở bản v2. Bản v1 còn giữ
làm bằng chứng. Artifact active chỉ có số, hashes, role và label publisher.
Split 25.803 symbolic template groups
train/calibration/validation không có exact group overlap; các near-template
khác nhóm, label-selection bias và thiếu campaign/time vẫn là giới hạn. 4.156
unique numeric76 keys của corpus trùng WAMM staging; đó là overlap feature,
không là bằng chứng cùng request vật lý. Nhãn WAMM attack và WAF anomalous
**không gộp**.

Ở ngưỡng calibration `NORMAL` 99th percentile, content model tăng publisher
PR-AUC/`ANOMALOUS` recall trên internal validation nhưng `NORMAL` FPR đạt
**1,44%**, cao hơn ngân sách1%; 43.171 rows xung đột đã loại nên chất lượng
trên full source chưa biết. Label tier vẫn `WEAK_LABEL`, independent Ground
Truth và formal admission **0**. Xem [PRETRAINING](../ai-training/PRETRAINING.md)
và ledger 06 mục 60.

## Research fit, evaluation và formal là ba phạm vi khác nhau — 2026-11-04

Policy v2 giữ nguyên các ngưỡng chất lượng đánh giá, nhưng assessor nay xuất
riêng `RESEARCH_FIT_READY`, `RESEARCH_EVAL_READY`, `FORMAL_READY`. WAMM đạt
**fit train-only** trên 43.287 unique float32/76 views không mâu thuẫn và
không trùng exact train/cal/val development đã lộ (14.242 publisher benign,
29.045 publisher attack). Đây là biểu diễn, **0 physical requests mới được xác
minh**; nguồn SR-BH derivative và không có campaign/time nên evaluation FAIL.
Raw conflict 757 views/15.872 minority-label rows vẫn là FAIL nguồn gốc; curated
fit subset không âm thầm giải quyết nhãn raw. Formal admitted vẫn **0**.

Train split WAF Data v2 đã được đọc thật: 1.924.461 publisher rows, gồm
1.539.108 `normal` và 385.353 `anomalous`, 1.612.017 exact complete-request
representations, 312.443 duplicate rows và 192 request views trái nhãn.
Mẫu deterministic 1/32 có 9.826 unique 76-feature views/59.046 rows và
180 view trái nhãn; không suy rộng thành full count. 77.823 body không rỗng,
nhưng request-only encoder 76 không quan sát body/header. 13 methods có
5.228 anomalous/0 normal: shortcut đáng nghi. `anomalous` chỉ là nhãn
publisher yếu, không là verified attack intent; không đưa vào formal hoặc
independent quality. Kyoushi scenario1 slice xác minh 408.477 Apache lines,
406.402 publisher `attacker_http`, 2.075 unlabeled UNKNOWN, **0 benign**;
không thể dùng lát cắt này đo FPR. Không cộng các dòng/log observations vào
mục tiêu unique physical requests. Handoff và báo cáo chi tiết ở
[PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 59.

## Quality gate v2 cho research và nhãn — 2026-11-04

[Policy v2](../ai-training/configs/autonomous_research_policy_v2.yaml) khóa tiêu chí nội bộ: HTTP parse lỗi ≤0,1%, majority class ≤90% theo unique view, hai nguồn độc lập có cả hai lớp, ≥32 unique views/source/role/class, group/time/related-template split có bằng chứng, train/calibration/validation không overlap. Cổng QA kiểm SHA của source report, Parquet 76 cột, exposed development roles và bundle 207; `test` hoặc role lạ ở reference bị từ chối. `PASS` chỉ là tiêu chí cụ thể đạt, `FAIL` là bằng chứng không đạt, `INCONCLUSIVE` là thiếu bằng chứng; raw conflict vẫn FAIL dù các vector đó đã được cách ly thành công. Policy này phục vụ research và không thay scale/admission formal.

WAMM: 704.665 publisher labels trên raw rows, 704.649 dòng parseable; 0 publisher label bị bỏ trống, nhưng **0 intent được xác minh độc lập**. Oracle lab cũ có 8 physical requests/8 ba nguồn/1 DB transition hợp lệ; cả 8 intent UNKNOWN, 0 machine-verified benign/attack. 43.287 numeric views đã cách ly xung đột và trùng exact với exposed development, song chưa có campaign/time/related-template metadata hoặc nguồn hai lớp độc lập. Nguồn request-only 76 cũng không cung cấp input 207 của GLU. Vì vậy research gate FAIL, model generalization INCONCLUSIVE; Precision/Recall/FPR/PR-AUC phải null, không chấm bằng nhãn publisher như thể là Ground Truth độc lập. Báo cáo/ledger ở [PRETRAINING](../ai-training/PRETRAINING.md) và mục 58 của [sổ chạy](06_AI_HANDOFF_AND_RUN_LEDGER.md).

## Research policy v1 và WAMM intake — 2026-11-03T21:07+07:00

[Policy autonomous v1](../ai-training/configs/autonomous_research_policy_v1.yaml) cho phép nghiên cứu với machine-verified hoặc nhãn publisher khi có quyền dùng, parse/dedup, hai nguồn hai lớp, group/related-template partition, ít nhất 32 unique views/source/role/class và train/calibration/validation không overlap. Publisher label chỉ chứng minh điều publisher công bố; UNKNOWN và vector trái nhãn cách ly. Policy này **không thay** `scale_policy.yaml` và không cấp formal admission. Final holdout không được dùng tuning; request-only 76 không padding thành GLU 207.

WAMM v2 được pin SHA, audit private 704.649 HTTP representations parseable, 312.241 exact text representations, 67.620 exact float32/76 views. 757 views mang hai nhãn, với 15.872 minority-label rows là mức lỗi tối thiểu của bộ phân loại tất định chỉ thấy vector 76 trên chính dữ liệu này (2,25% các dòng parseable; chưa phải metric model). Export numeric-only 66.863 views không xung đột, sau loại 23.576 views trùng exposed development còn **43.287**; report `audit-v4.json` và `overlap-v2.json` nằm trong `.artifacts/autonomous_research_20261103/wamm/`. Dedup exact không giải quyết near-duplicate/campaign leakage. WAMM dẫn xuất SR-BH, không có row-level campaign/time hoặc nhãn intent kiểm độc lập, nên chỉ là staging, **0 request formal admitted** và chưa chạy study. Kyoushi nguồn Apache/attacker-log có thể hỗ trợ đánh giá về sau nhưng hiện metadata-only; WAF Data v2 `anomalous` chưa được xác nhận là attack intent. Xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 57.

## Intake/study chỉ sau quyền và nhãn mới — 2026-11-03

Gói Biblio trong [PRETRAINING](../ai-training/PRETRAINING.md) yêu cầu RAW+LABEL+README/terms trước khi đọc data. Khi được cấp quyền: pin SHA/provenance, ghép RID theo README, giữ riêng publisher label/S2/S3/UNKNOWN, audit duplicate/xung đột và unique float32 views, rồi khóa partition theo source/campaign/day với embargo khi có clock thật. CLEAN không mặc định benign được review; Biblio METHOD/URI chỉ cho request-only 70+6 khi parse được, không được padding thành 207. Mốc G0–G3 là tiến độ nghiên cứu, không thay `scale_policy.yaml`. Study mới FPR 1% và cohort acceptance chưa dùng tune chỉ chuẩn bị protocol, **NOT_RUN**. Review Oracle cũ hiện bị provenance SHA mismatch khi tái kiểm bằng code mới; plan-v3 có thể ký prospective nhưng chưa có reviewer. Formal admission **0/2 triệu**. Chi tiết trong ledger 06 mục 56.

## Research fitting tách formal admission — 2026-11-03

Prepared-v5 có 41.607 train rows / 41.585 exact 207-feature views từ một lab, nhãn development 29.511 benign/12.096 attack; không là số physical requests độc lập. Run train-only mới chỉ dùng 12.800 rows/12.798 views, không decode validation/test. Kết quả loss/gradient là phép kiểm optimizer, không dùng để tuyên bố model phát hiện attack tốt hoặc làm formal admission. Sàng lọc WebSpotter qua [paper](https://www.ndss-symposium.org/ndss-paper/achieving-interpretable-dl-based-web-attack-detection-through-malicious-payload-localization/) và [repo](https://github.com/Sec-AI-research/WebSpotter): FPAD benign kế thừa CSIC, attack tái tạo từ payload/Burp Bounty; CVE attack được annotate nhưng không có matched benign từ cùng capture. Giữ nghiên cứu/cách ly, 0 request mới được verify/admit. Scale gate 2M/3 môi trường/7 ngày/120 campaign/95% ba nguồn/evidence-v2 không đổi. [Chi tiết](../ai-training/PRETRAINING.md), ledger 06 mục 55.

## Canonical edge và AI numeric sidecar — 2026-11-03

`normalized_events.canonical` giữ redacted events; Python `postgres-export` đã đọc schema v1 và khớp 5/5 Student observations khi bọc export từ capture live. Nhưng Rust Suricata parser chỉ nhận `http.request_id` trực tiếp; capture EVE có **0/4** trường này, **4/4** ID ở response header và **4/4** numeric v2 sidecar. Canonical Rust chỉ lưu 5 query counters, không giữ `ai_query_numeric` 28+41 hoặc flow start/end; `observed_at` nằm ở bảng, chưa đi vào causal collector. Do đó không padding các cột thiếu hoặc tự đoán correlation. Để tạo 207 theo contract đang có: canonical Student/Nginx + EVE AI numeric v2 trước mask, rồi collect/post-response inference; flow quá khứ chỉ khi EVE đã đến và thời gian hiệu lực hợp lệ. Export SQL phải lọc Student/Nginx, vì đưa canonical Suricata cùng EVE sidecar gây duplicate source/ambiguity. Đây là thiết kế offline đã được kiểm từng thành phần, **chưa chứng nhận live DB→AI/receipt-time**. [Runbook](../ai-training/README.md), ledger 06 mục 54.

## Ranh giới 207 feature và lỗi realtime — 2026-11-03T17:51+07:00

Python inference v5 yêu cầu ba nguồn cùng request ID, numeric bridge và status/latency/request/response bytes sau response; `request_key` phát lại bị từ chối trước khi cập nhật lịch sử. Replay trên bốn request live đã lưu xác nhận exact duplicate line không đổi vector, duplicate logical cùng ID nhưng khác nội dung trở thành ambiguous, đảo thứ tự line vẫn deterministic, fused request đến ngược thời gian bị từ chối. Thiếu EVE tại deadline thì skip; EVE về sau chỉ xuất hiện trong staged snapshot, không được backfill trong replay. Chưa có durable timeout ledger để chứng minh điều đó qua restart hoặc event trễ tự nhiên.

Security Web Rust hiện tính 5 `QueryFeatures` cơ bản và lưu canonical observations; **không có vectorizer/ONNX 207 cột**. Vì thế Python train↔Python inference parity không chứng nhận Python↔Rust parity. Live lab cho 197/207 cột giá trị có nguồn trước prior flow, 202/207 sau prior flow; 5 original-query values không quan sát được dù cờ missingness hữu hạn. Không padding các giá trị vắng mặt và không lấy EVE flow tương lai. Formal admission 0; Biblio nếu được cấp quyền chỉ hỗ trợ request-only research sau kiểm RID/nhãn/quyền dùng, không lấp 207 full-view. [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 53.

## Feature availability theo thời gian nhận EVE live — 2026-11-03T16:22+07:00

Probe AI-owned ba nguồn live (16 target GET qua bốn lab tạm) chứng minh input 207 chỉ hợp lệ **sau response và sau khi Student/Nginx/EVE HTTP cùng request ID đã đến**. Cấu hình sensor mặc định rơi 100/240 packet: 2/4 request đầu mất EVE, **không** được score; ring AF_PACKET `lo` riêng giảm drop về 0/208 và hai lượt 0/80 ở ba probe tiếp, 12/12 request đủ ba nguồn. Không thấy observation trùng ở 12 request đó. EVE HTTP đến sau client send 16,7–35,0ms; không có trường hợp EVE trễ quá timeout 12s trong probe thành công. Lượt query vô hại có numeric v2 khớp target đã gửi 4/4 trước inference. Khi EVE thiếu, shadow ghi nguyên nhân bỏ qua; không suy đoán từ hai log còn lại.

Lượt chờ 67s: prior completed flow **0/2 request đầu, 2/2 request sau** theo `available_at <= request timestamp` và `flow.end+65s`. Như vậy 5 giá trị flow có thể quan sát sau khi đủ lịch sử nhưng **không** được lấy từ flow hiện tại/tương lai. Năm original-query values vẫn không có vì mask; availability/missingness flags giữ nguyên. 207/207 input hữu hạn; **197/207** value columns có nguồn ở hai request đầu và **202/207** ở hai request sau. Sáu cờ incomplete 10/60/300s của IP/user bật lúc đầu, bốn cờ còn bật sau 67s. Train v5 có prior flow ở 36.443/41.607 rows nên coverage khác mạnh khi khởi động lạnh; đây là domain shift và shortcut risk, không chứng minh label leakage. Bốn vector live khớp exact giữa hai đường dùng **cùng implementation Python**; Rust/edge, TLS, clock/receipt ở môi trường khác chưa đối chiếu. [Chi tiết](../ai-training/PRETRAINING.md), ledger 06 mục 52.

## Audit 207 cột trên capture thật, replay offline — 2026-11-03T09:31+07:00

Spec v5 gồm **28** numeric URI/query cơ sở + **41** chỉ số cấu trúc + **78** behavior IP/user + **10** flow (5 giá trị/5 missing flags) + **23** UA/missing + **10** method + **5** status + **5** role + **7** authenticated/latency/request/response bytes = **207**. `FeatureExtractor` nhận đủ các cờ `query_structure=true`, `behavior_dynamics=true` từ `state_limits`; 207/207 cột được sinh hữu hạn trên 54 request ba nguồn thật trong lab. **197 cột có đầu vào quan sát phù hợp**; năm `flow_*_log1p` thiếu vì chưa có prior completed flow, năm `query_original_*` thiếu vì query gốc được che. Hai nhóm cờ missing/availability của chúng vẫn là đầu vào hợp lệ. 122 cột biến thiên trong 54 request; zero/constant hợp lệ không được đếm thành missing.

| Nguồn/timing | Train v5 | Capture ba nguồn mới | Giới hạn |
| --- | ---: | ---: | --- |
| Correlation Student + Nginx + EVE | 41.607/41.607 train rows | 54/54 request mục tiêu; 1 setup hai nguồn bị bỏ score | EVE từ PCAP offline, chưa live receipt-time |
| Numeric query v2, structure, URI | 41.607/41.607 | 54/54 | Đường EVE offline trước mask; live edge parity chưa chứng minh |
| Prior completed flow có hiệu lực tại request | 36.443/41.607 | **0/54** | Không lấy future flow của chính request; 5 values missing |
| Status/latency/request/response bytes | 41.607/41.607 | 54/54 | Chỉ hợp lệ **sau response**; 207 feature không dùng chặn trước response |
| IP và user context đủ 10/60/300s | Có lúc đủ trong train | **0/54** ở cả sáu cờ incomplete | Capture mục tiêu chỉ 11,34s, thiếu độ sâu thời gian |
| User key | 37.750/41.607 | 51/54 | Unknown giữ null; không bịa user history |

Các cột status/latency/response trực tiếp và behavior error/auth phụ thuộc status hiện tại chỉ được tính sau response. `dataset.collect` dùng `available_at=max(EVE timestamp, flow.end+65s)` cho flow cũ, `a<=request timestamp`; không backfill totals của chính request. `FeatureExtractor` thêm request hiện tại đúng một lần vào các cửa sổ 10/60/300s, không nhìn tương lai. Runtime v5 giờ **abstain** trước model khi thiếu một nguồn/ID tương quan, response fields hoặc cờ numeric bắt buộc; flow có missingness được giữ vì train đã có 5.164/41.607 rows thiếu flow. 512 persisted train vectors ×207 khớp exact với inference; 54/54 capture vectors khớp giữa hai đường dùng **cùng mã Python**. Đây chưa là Rust/live parity. Sự lệch flow **87,59% train vs 0% capture**, UA đơn dạng và context incomplete là nguy cơ shortcut/domain shift, không phải chứng cứ label leakage. [PRETRAINING](../ai-training/PRETRAINING.md), [report](../ai-training/reports/ATTACK_EVIDENCE_20261101.json), ledger 06 mục 51.

## Phân bố exposure và giới hạn study sampler — 2026-11-03T08:44+07:00

Trong `forward-development-v2`, 96.423 train rows chứa 27.142 exact float32 views sau lựa chọn train; không có view trái nhãn trong pool. Cùng 300 updates/38.278 lượt đưa vào optimizer, sampler cân source/family có hoàn lại chỉ thấy 14.060 views, Student benign 206 views nhận 9.684 lượt (tối đa 69/view); thứ tự không hoàn lại thấy đủ 27.142 views, Student benign nhận 310 lượt (tối đa 2/view). Hai cách còn thay đổi tỷ trọng source/class/family, nên đây là phép thử **toàn bộ sampler**, không xác định nguyên nhân đơn lẻ.

Phép đo validation theo row và exact view cho thấy GLU không hoàn lại cải thiện Student lab nhưng giảm mạnh SR-BH; MLP mất toàn bộ Student attack recall ở ngưỡng calibration cũ theo policy. Vì source shift lớn và validation đã lộ, không promote thay đổi. Giữ riêng request vật lý, 118.760 development vectors, unique model views và formal admitted 0. GLU 207 cột vẫn cần dữ liệu mới kiểm tra timing/parity live edge/EVE và nhãn độc lập; không lấy study 76 cột làm bằng chứng cho full model. [Chi tiết](../ai-training/PRETRAINING.md), [report](../ai-training/reports/PARTITION_RECOVERY_20261031.json), ledger 06 mục 50.

## Intake request-only từ nguồn mới — 2026-11-03T08:01+07:00

CIKM 2026 IoT CVE là artifact [tác giả công bố](https://github.com/mm-doshisha/CIKM2026-iot-vuln-pipeline) có 281 CVE examples và 281 benign IoT được lấy từ [UNSW-IoTraffic](https://doi.org/10.5061/dryad.w0vt4b94b). [Bài báo](https://arxiv.org/html/2608.22889) nói 245/281 attack request được **tái dựng thủ công** từ exploit/advisory; không tính chúng thành traffic attack vật lý đã bắt. 281 CVE-paired benign là control do tác giả tạo, không phải 281 request thật mới. Hai lớp train tiềm năng thuộc hai quy trình nguồn khác nhau, tạo shortcut nguồn/nhãn; không có dual-class mỗi source hay campaign/time split hợp lệ.

Phép project thử chỉ đọc method/path, dùng đúng `request-structure-v1` 70+6, không dựng lại wire query từ `params` object. Kết quả 214 attack views/281 examples, 140 benign UNSW views/281 examples, **4 view giao nhãn**. Trong attack examples có 167 body, 48 `params` object và chỉ 9 path có query; request-only profile thiếu nhiều tín hiệu. Đây là kiểm khả năng quan sát, **không** là corpus đủ điều kiện study; 0 nhãn mới được xác minh độc lập và 0 admission. GLU 207 post-response/ba nguồn giữ riêng. Biblio-US17 vẫn cần quyền RAW+LABEL; ForenWebLog chưa thấy bản release/label trail, DEDALE gắn nhãn flow. [Catalog](../ai-training/configs/public_http_sources.yaml), [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 49.

## Model input view và request ID — 2026-11-03T07:45+07:00

Đếm trực tiếp tensor float32 thay vì chỉ `feature_key`: SR-BH validation có **6.839** exact encoded views/10.000 rows (so với 6.840 `feature_key`), Student lab **290**/1.024. 118.760 `event_key` khác nhau trong development snapshot chỉ chứng minh ID nội bộ không trùng, **không xác nhận** số request vật lý toàn cục. Không có view float32 hoặc group xuất hiện ở hai role train/calibration/val; không có view trái nhãn trong snapshot. Trùng view trong một role có thể là nhiều request hợp lệ với cùng biểu diễn, vì vậy không xóa raw request hay thay chuỗi hành vi.

`export_request` thêm `validation_encoded_views` và `validation_encoded_views_by_source` vào manifest để đặt metric theo row cạnh metric theo view. View chứa nhãn mâu thuẫn làm metric view-weighted `null` và giữ nguyên nhãn gốc. Đây là guard diễn giải cho request-only 76 cột, không phải thay đổi trainer hoặc phép đo GLU chính 207 cột. Nhãn publisher/runner, source shift và thiếu campaign độc lập vẫn ngăn mọi kết luận về chất lượng thực tế. [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 48.

## Độ lặp view và giới hạn đánh giá development — 2026-11-03T07:04+07:00

Study checkpoint chỉ đọc trên 118.760 vectors đã có: SR-BH validation 10.000 rows chỉ 6.840 `feature_key`, Student lab 1.024 rows chỉ 290 keys. GLU 76 cột có 1.492 attack rows SR-BH được bắt riêng mà MLP không bắt, nhưng chỉ 677 keys; MLP-only 1.052 rows gần như 1.047 keys. Khi cân đều key, recall MLP 31,89% vượt GLU 21,82% (ngược thứ tự theo rows 22,83%/31,37%). Đây là tín hiệu **frequency/representation sensitivity**, không chứng minh feature cụ thể gây shortcut. FPR Student lab của GLU 10,73% theo rows và 10,22% theo benign keys; shift không biến mất khi gỡ trọng số lặp. Các chỉ số chỉ áp dụng nhãn publisher/runner và validation development đã lộ, không được dùng chọn champion hoặc chỉnh threshold. [Report](../ai-training/reports/PARTITION_RECOVERY_20261031.json), ledger 06 mục 47.

AIT có 25 benign/3.146 attack encoded views, 4 views mang nhãn trái chiều. 13 attack publisher trên các views đó không thể đồng thời được phân biệt khỏi benign bởi bất kỳ classifier tất định nào chỉ nhìn cùng 76 số. Giữ nguyên nhãn và báo cáo cả row-/view-weighted; không chọn tập sạch bằng cách bỏ xung đột hậu nghiệm. AIT thiếu 137 cột full-only và phần lớn attack là scanner, nên no-fit stress 76 cột không phải evaluation của GLU 207. Theo dõi riêng **request vật lý xác minh được / biểu diễn duy nhất / nhãn intent review / formal admitted**; 118.760 vectors không cộng vào 2 triệu physical requests, formal hiện 0.

## Addendum AIT request-only screening — 2026-11-02T19:10+07:00

[AIT Log Data Set V2.1](https://zenodo.org/records/19483937) cung cấp Apache access log testbed và label theo số dòng; archive `russellmitchell_no-pcaps.zip` được tải private, MD5 khớp Zenodo, CC BY-NC-SA 4.0. Trên **một** intranet campaign, 7.695 dòng có attack-related publisher label và 2.831 dòng parse được trước attack làm benign candidate; 604 dòng không nhãn trong/sau attack và 54 dòng không parse request giữ ngoài corpus. Đây là **10.526 log observations ứng viên**, không là 10.526 nhãn intent review độc lập hay request vật lý có ID. Request-only 70+6 project/encode hữu hạn 10.526/10.526, nhưng chỉ có **25 benign / 3.146 attack views**, 4 view giao nhãn; 25 benign `<32` trước khi chia train/calibration/validation. Rule/timeline của publisher và scanner áp đảo làm nguồn này chưa đủ cho study hai nguồn hai lớp hoặc formal admission. Không dùng status, host hoặc label rule làm feature/ground truth tự động. [Chi tiết audit](../ai-training/PRETRAINING.md).

Đối chiếu 8 request Oracle cũ: EVE numeric v2 từ Nginx private target khớp 8/8, request-only 70+6 hợp lệ 8/8 nhưng 6/8 lệch ít nhất một trong 60 số tên chung vì mask/alias profile khác nhau; không tráo vector giữa profile. AIT không có 137 full-only features, Student audit, EVE flow hay live edge parity. Biblio-US17 vẫn cần quyền truy cập, không truy lại archive 401. Formal admitted/independent intent review vẫn 0; study mới **NOT_RUN**.

## Nguồn nhãn và ranh giới nghiên cứu — 2026-11-02

Rà soát tiếp ngày 02/11: Biblio [form xin bản sao](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361) hoạt động (HTTP 200), archive cần quyền (401); nội dung xin phép và các câu hỏi về CC BY-NC-ND trong [PRETRAINING](../ai-training/PRETRAINING.md). File [WAF-Bench](https://huggingface.co/datasets/netgoat-ai/WAF-Bench) được pin/tải private và kiểm 77 ID, 57 malicious/20 benign; 13 case chỉ có body, gồm 8 malicious mà request-only profile không nhìn thấy. Chỉ là fixture synthetic, không train/admit. Paper [multi-agent honeypot](https://arxiv.org/html/2603.02963v1) nói 140.973 cặp nhưng gán nhãn từ cấu hình generator và chưa có archive/quyền tải được xác minh; không thêm vào corpus.

Đối chiếu current projector và `feature_spec.json`: request-only có **70 số gốc + 6 tương tác = 76 cột**, full post-response **207 cột**; giao **70 tên cột**, 137 chỉ full-view. Biblio có method+URI để **có thể** tính 70 số gốc rồi 6 tương tác sau khi được phép và kiểm parse; không có clock chính xác/client/body/flow/UA/latency để khôi phục 207. MWAD URI CSV thiếu method và khóa ghép flow; WAF-Bench query object thiếu raw wire encoding/order. Không điền 137 cột thiếu bằng số 0 rồi dùng lại GLU 207. Corpus development cũ có **118.760 rows/vectors** gắn nhãn publisher/runner (55.559 nhãn 0; 63.201 nhãn 1), nhưng thiếu independent semantic review và không phải 118.760 request vật lý mới. Research fitting kỹ thuật từng được phép; study tổng quát hóa mới vẫn thiếu nguồn nhãn đủ tin. Chi tiết accounting ở [PRETRAINING](../ai-training/PRETRAINING.md).

Screening mới không thay đổi admission: **0 nhãn intent benign/attack được xác minh độc lập trong corpus hiện tại, 0 request formal admitted, 0 study mới**. [Biblio-US17](https://link.springer.com/article/10.1186/s42400-024-00336-3) là ứng viên mạnh vì tác giả mô tả 327.906 LVL1 attacks qua kiểm tra chuyên gia và RID nối RAW/LABEL; nhưng archive [idUS](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e) hiện cần quyền truy cập, license CC BY-NC-ND 4.0 và số liệu chưa kiểm row. CLEAN chứa nhiều request S2=-1/S3=-1 chưa được review thủ công, vì vậy không tự gán toàn bộ là benign. Biblio có URI/method/response/ngày-thứ tự, thiếu clock chính xác, client/body/flow và hợp đồng 207 feature.

[MWAD](https://github.com/paul12345-cyber/Multimodal-web-attack-Dataset) được audit hai CSV private 1.000 dòng mỗi bảng, nhãn 500/500, 975 URI hashes/989 flow vector hashes; thiếu ID/clock/khóa nối request với flow, nhãn do chiến dịch SQLi của tác giả, không có review ngữ nghĩa độc lập theo request. [WAF-Bench-77](https://huggingface.co/datasets/netgoat-ai/WAF-Bench) có 57/20 nhãn do người ngoài project biên soạn, nhưng là synthetic fixture, 20 benign dưới research minimum trước split và test đã công khai. [CSIC2010](https://www.impactcybertrust.org/dataset_view?idDataset=940) có `anomalous` gồm cả input sai không ác ý: kết quả binary trước đây là **anomaly research**, không chứng nhận attack-intent. OWASP CRS test là rule-match fixture; CICIDS2017 là flow/schedule label. Các nguồn này đều không vượt evidence-v2/scale gate hiện hành; lý do chi tiết và SHA của bản MWAD trong [catalog](../ai-training/configs/public_http_sources.yaml) và [PRETRAINING](../ai-training/PRETRAINING.md).

Oracle 8 request chỉ xác minh capture/response/body và DB side effect của mutation hợp lệ, không xác minh ý định SQLi/XSS hoặc exploit outcome. Một machine-verifiable trust chain cần protocol/case được reviewer thật phê duyệt, request/body/clock khớp sau capture và oracle ứng dụng độc lập với collector, cùng kiểm toán disagreement; đây là đề xuất nghiệm thu **chưa được chấp thuận**, không mở gate. Study request-only mới cần hai nguồn hai lớp, nhãn theo request, mỗi source/role/class ≥32 request và ≥32 encoded views, split tránh group/view overlap và clock embargo 300s. Formal GLU 207 cần riêng ba nguồn/causal post-response và quy mô `scale_policy.yaml`; nguồn URI-only không được nhét vào 207 cột bằng missing/imputation giả. Bước tiếp theo tập trung **quyền truy cập + audit nhãn Biblio và nguồn thứ hai độc lập**, sau đó mới study.

## Quan sát development và ranh giới nhãn — 2026-11-02T11:09+07:00

Profile `dev-oracle-observation-v1` là luồng **không chữ ký, không admission** riêng với `gt-pilot-v1` đã khóa. Plan và execution code được hash trước capture. 8 request thực được đối chiếu ID/clock/target qua Student, Nginx và Suricata EVE decode offline từ PCAP; response ledger, 2 body POST trong PCAP, DB khoa `0→1` sau POST STAFF/201 và cleanup lab được tái kiểm. Kết quả máy xác nhận các quan sát đó, **không** xác nhận intent: 8 `UNKNOWN`, 0 benign/attack được review độc lập, 0 attack exploit outcome, 0 admitted. Blind queue mới giữ `label=null`; evidence-v2 gate không đổi. Xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 43.

Audit bốn capture pending ghi 170 ID riêng/79 target hashes/91 lượt lặp target, 0 ID collision; thêm v1 cách ly thành năm capture có 218 ID/79 target hashes/139 lượt lặp, vẫn 0 collision. Sealed historical cohort chưa mở, nên tổng 75.360 theo report cũ không được tự nâng thành unique toàn cục. Dữ liệu lab mới ở cùng môi trường và 8 nhãn unknown không thể tạo partition train/val/cal/test hai lớp độc lập. Hợp đồng 207 feature vẫn **post-response**; sensor offline và query numeric trong lab chưa chứng minh live edge receipt-time/query parity. Không fit, calibration hoặc ONNX export mới từ capture này.

## Kiểm tra trust boundary của pilot — 2026-11-02

Approval Ed25519 của reviewer sẽ pin plan SHA/file SHA, public-key SHA, 10 source SHA, Student Git tree và SHA mẫu Nginx; code collector kiểm lại trước request. Đây là kiểm integrity/key possession; tính độc lập của người ký cần operator xác nhận. Student/Nginx/EVE và PCAP có thể xác minh request thật, còn DB count trước/sau chỉ là quan sát do collector tạo về benign mutation. `verify_lab_cleanup` xác nhận container tạm biến mất và ports đóng sau mutation. Không có chữ ký/capture pilot thật, nên machine-verified labels **0** và admission **0**. Chính sách evidence-v2 vẫn cần independent semantic review, dataset/provenance và gate corpus. Xem [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 42.

## Hợp đồng Ground Truth pilot — 2026-11-02

Protocol `gt-pilot-v1` khóa trước capture: exact URI/method/body không bí mật, campaign/seed, intent dự kiến và SHA collector; reviewer khác collector phải ký bằng khóa riêng sau khi đọc ngữ nghĩa. Collector từ chối plan không ký, source đổi hoặc target ngoài lab AI-owned loopback. Request thực phải khớp plan và Student/Nginx/EVE cùng ID, method, target SHA, clock; mỗi case đúng một request. `MACHINE_VERIFIED_PROTOCOL_MATCH` chỉ là **staging** cho GET khi chứng cứ ba nguồn và chữ ký thật hợp lệ; POST body chưa bind nên UNKNOWN. DB count trước/sau tạo khoa là quan sát ứng dụng do collector ghi, không xác thực độc lập exploit outcome. Gate evidence-v2 và chính sách admission giữ nguyên: **0 nhãn đủ điều kiện training, 0 admitted**, chưa có pilot thật vì thiếu reviewer key/signature độc lập. Plan 8 request là development một lab, không phải holdout hoặc dữ liệu đại diện 2 triệu. Xem [workflow](../ai-training/PRETRAINING.md) và ledger 06 mục 41.

## Blind automated review và giới hạn admission — 2026-11-02

Pipeline review mới đọc capture/queue/assist facts nhưng **không parse proposal của runner** khi tạo SQLite blind. `auto-compare` chỉ mở proposal sau khi blind pass đầy đủ và pin SHA. 162/162 request được kiểm provenance; 12 POST có PCAP body, 6 POST cũ thiếu body; 102 query chỉ có trong private Nginx lab. Scan cú pháp có 39 single-cue, 123 no-cue; 7 cue trên runner-benign và 22 runner-attack không có cue. Những số này chỉ giúp xếp ưu tiên review, không chứng minh attack intent, benign hay exploit outcome. Toàn bộ **162 nhãn intent vẫn unknown**, 0 oracle, 0 AI-model proposal, 0 review độc lập, 0 admission. Không dùng response status, Suricata alert, runner intent hoặc cue làm ground truth.

SQLite unique request ID/event key chống đếm nhiều observation thành request; resume thử nghiệm 65→162→162 không sinh bản trùng. 78 target views/162 request, 84 lượt lặp và 36 view trùng giữa campaign là nguy cơ học vẹt nếu split trong cùng lab. Đây là dedup theo registry mới; lịch sử sealed không đọc, chưa có global physical-request certification. Batch/shard là thiết kế có chạy thử 162, **chưa benchmark 2 triệu**. Muốn thay gate để nhận machine-verified labels cần oracle độc lập request-bound và chính sách audit riêng; code admission hiện tại không đổi. [Workflow](../ai-training/PRETRAINING.md), ledger 06 mục 40.

## Ranh giới evidence và 207 feature — 2026-11-02

`review-evidence.py` tái kiểm 162 hồ sơ từ ba queue private và tách quyết định người review khỏi runner/syntax proposal; chưa có quyết định người độc lập nên **0 request admitted, 0 benign/0 attack verified**. PCAP hai lượt EVE chứng minh body bytes và response request ID cho 12 POST, artifact HMAC không lưu secret; 6 POST hai nguồn cũ không có body capture, phải giữ unknown khi thiếu nguồn khác. Semantic intent cần người review độc lập và bằng chứng ứng dụng; exploit outcome vẫn unknown nếu không có oracle. `finalize` chỉ pin quyết định, không thay thế evidence-v2 + prepared dataset/provenance + catalog admission.

Hợp đồng v5/207 cột là **post-response**. Status, latency, response size và behavior tính đến request hiện tại không có tại thời điểm chặn trước response. Causal collection chỉ chọn flow EVE đã có `available_at <= timestamp` của request và từ các flow cũ; flow của request hiện tại phát muộn không được backfill. Inference đọc `feature_spec.json`, cùng `state_limits`, fingerprint code, và chronological fused request. Đã có tương thích code/replay cho contract này; **chưa có chứng cứ live Rust/edge receipt-time và query numeric trước mask**. Do đó không dùng offline 207-vector parity để khẳng định triển khai realtime hoặc tự động chặn an toàn.

## Admission và visibility profile sau capture thứ hai — 2026-11-02T08:54+07:00

Plan `novel-v2` chốt SHA collector, seeds, campaign/case/target hash và loại trừ critical target từ hai plan trước **trước khi phát request**. Lượt mới 54 request vật lý, 42 target hashes mới, 3 campaign development trong cùng lab. Bốn capture có 210 ID riêng/78 target hashes; 0 ID collision với 227.619 ID từ bảy Student log lịch sử chưa sealed, nhưng sealed holdout giữ nguyên nên chưa có global dedup certification. Không cộng EVE HTTP/flow/alert hoặc 162 hồ sơ pending thành request train mới.

Masked Nginx lab `access.log` có query null 54/54, EVE offline `safe_query_numeric_v2` trích số học từ packet *trước* redaction và bằng private Nginx projection 54/54. Student audit query mask không được dùng để tái dựng payload; `normalize_record` trong causal profile không dùng raw query từ Student/Nginx. Đây là **offline lab contract**; cần thử live Suricata→AI bridge và quan sát thực tế trước khi tuyên bố cùng 207 feature khi triển khai. Flow phát tới 11,341s sau EVE HTTP và chỉ có giá trị sau timestamp phát; không được dùng totals tương lai tại request.

Automation tách `review-assist.jsonl` chứa facts blind/hash và `review-proposals.jsonl` chứa runner claim + syntax cues; hai file đều `training_eligible=false` và không được nhập làm nhãn. Ở lượt mới, cú pháp cue xuất hiện ở 9 benign-intent theo plan và vắng ở 3/18 attack-intent theo plan; rule không đủ làm ground truth. 162 hồ sơ chưa có reviewer semantic độc lập hoặc application oracle; **0 benign/0 attack verified, 0 admitted**. Cần evidence-v2 ledger, môi trường/campaign độc lập và partition theo group/time trước formal. [Workflow](../ai-training/PRETRAINING.md), ledger 06 mục 38.

## Evidence ba nguồn và thời điểm feature có hiệu lực — 2026-11-02T08:31+07:00

Lượt capture AI-owned mới chạy Nginx và collector trong private network namespace, bắt TCP thật bằng PCAP rồi Suricata decode offline. 54/54 request có đúng một EVE HTTP với `X-Request-Id` trả về, cùng Student/Nginx ID, method, status, source IP, safe path và timestamp ≤5s; mỗi HTTP gắn flow ID có bản ghi EVE flow thật. Numeric projection v2 trên query Nginx lab private so với EVE khớp **54/54**. Bản EVE persisted đã mask query/UA và không lưu body; raw Nginx query chỉ ở artifact review private. 54 flow được phát muộn tối đa **10,811s** sau HTTP, nên mọi feature dùng giá trị kết thúc flow tại thời điểm HTTP là **future leakage**. Parser/admission phải dựa trên thời gian sensor phát record và chỉ dùng context đã xảy ra.

Queue review mới bind hash Student/Nginx/EVE HTTP/flow nhưng giữ toàn bộ `intent=unknown`, `label=null`, `training_eligible=false`; 18 alert Suricata không thành ground truth. 54 request hai nguồn hôm trước không được nâng thành ba nguồn bằng EVE của hôm nay. Audit ba capture cho 156 ID riêng, 36 target hash/120 lượt lặp, 0 collision với 73.218 ID Student từ các log chưa niêm phong; không đụng sealed cohort. Cả ba campaign mới là development cùng một lab và cùng biến thể target cũ, **không tạo một partition độc lập hợp lệ**. Formal feature contract 207 cột còn gap: lab private query và numeric EVE được thấy trước mask, còn edge production dùng `edge_masked_v1`; không coi parity lab là parity inference thực tế. Admission mới =0, reviewer độc lập và môi trường/biến thể khác vẫn cần thiết. Chi tiết tại [PRETRAINING](../ai-training/PRETRAINING.md) và ledger 06 mục 37.

## Ranh giới dedup và review thực tế — 2026-11-01T11:45+07:00

`audit-captures` xác minh lại từng request bằng plan/capture cùng Nginx + Student, rồi so ID xuyên hai lượt mới và ba log Student lịch sử *không sealed* được chỉ định. Kết quả: 102 ID khác nhau, 0 va chạm với 73.218 ID lịch sử đã quét, nhưng chỉ 36 target hash khác nhau; 66 lượt lặp target không tạo sự đa dạng cú pháp mới. 73.218 là số ID trong log có thể bao gồm setup, không phải số request training mới. Cohort sealed và phần còn lại của 75.150 request lịch sử chưa được đối chiếu toàn cục; không mở holdout để làm đẹp con số. 54 request v2 vẫn pending/null-label, 48 v1 bị cách ly. Nguồn v2 chỉ có Student/Nginx; EVE và query visibility parity còn thiếu, vì vậy không đưa vào profile fused 207 cột cho formal. [Review workflow](../ai-training/PRETRAINING.md) yêu cầu reviewer độc lập quyết định semantic intent trên capture thực trước khi tạo evidence-v2 ledger; runner plan, status/rule và hash integrity không phải ground truth.

Thiết kế vòng capture kế tiếp, **chưa phát request hoặc gán role dữ liệu thực**:

| Nhóm cần thu | Bằng chứng và biến thể cần khóa trước capture |
| --- | --- |
| Benign | Phiên đọc/tìm kiếm/mutation/auth hợp lệ, nhiều người dùng và độ dài phiên >300 giây; ghi oracle ứng dụng khi có mutation để biết kết quả thực. |
| Hard negatives | Tra cứu tài liệu có chuỗi SQL/HTML/path/shell hợp lệ, lỗi đăng nhập lẻ tẻ, query dài và encoded nhưng có mục đích hợp lệ; reviewer xác nhận ngữ cảnh. |
| Attack intent | Các họ SQLi, XSS, traversal, command và recon/auth abuse trong target được cấp phép; precommit template/seed và ghi riêng intent với exploit outcome. Không dùng HTTP status hay rule hit làm nhãn. |
| Prospective acceptance | Ứng dụng hoặc môi trường và thời điểm khác development, cả benign/attack được review, campaign/template disjoint và embargo 300 giây. Đóng băng model/threshold trước khi mở; không dùng để tuning. |

Mỗi campaign cần target allowlist/phê duyệt, campaign ID, clock đồng bộ, request ID, SHA capture Nginx + Student + EVE/PCAP, provenance người phát và người review khác nhau. Sensor EVE có thể chạy offline trên PCAP trong lab AI, nhưng phải xác minh flow/request correlation và không điền giá trị thiếu bằng số giả. Nếu chưa có môi trường/nguồn được phép và reviewer, trạng thái vẫn `DESIGNED_NOT_COLLECTED`; không triển khai chỉ để tăng số request. Kế hoạch nguồn công khai/prospective hiện có nằm trong `ai-training/configs/public_http_sources.yaml`.

## Contract thu thập evidence-native trên lab — 2026-11-01T11:21+07:00

Plan SHA được chốt trước traffic và gắn từng case với campaign, seed, source IP loopback, method, hash target, benign/attack *intent dự kiến*. Collector chỉ gửi vào fixture AI-owned, lấy `X-Request-Id` do Nginx phát và xác minh đúng một dòng Nginx + Student audit cho mỗi ID. Queue review riêng giữ `label=null`, `intent=unknown`, `exploit_outcome=unknown`, `training_eligible=false` cho tới khi có reviewer độc lập. HTTP 200/401, WAF rule và mô hình không tạo nhãn; login hợp lệ chỉ là điều kiện vận hành để workload đi qua auth boundary.

Lượt đầu 48 request (45 trả 401) cách ly. Lượt sau 54 request qua capture check: 36 planned benign, 18 planned attack, 54 correlated IDs, clock skew tối đa 0,924s, 30 attack/hard-negative target hash không lặp giữa 3 campaign. Tất cả cùng môi trường và chỉ ở role development; benign catalog target còn lặp, nên không split các campaign này thành train/validation/test hoặc xem là independent generalization. Future holdout `RESERVED_NOT_GENERATED_OR_CAPTURED`. Cần review ngữ nghĩa có bằng chứng per-request, dataset/provenance bất biến, gate admission hiện có, thêm môi trường/campaign theo thời gian độc lập và kiểm parity query mask/EVE trước train. 0 request được admission lượt này.

## Rà soát admission thực tế — 2026-11-01T10:53+07:00

64 hồ sơ SOC-MLD đã được gắn locator/SHA và đặc trưng HTTP không chứa IP/URI/query/UA, nhưng chưa có request-bound campaign hoặc intent evidence. Cả 64 `unknown`, 0 approved, 0 admission. 38 attack-instance IDs chung train/test ảnh hưởng 1.852 train và 1.214 test rows; split do publisher cấp không được dùng làm phép đo độc lập. ModSec-WP: 108.883 workbook rows, 27.686 distinct transaction IDs/event keys, 18.474 method/URL/body views, 20 ID và 25 views có nhãn mâu thuẫn. Tập này vẫn cách ly; không coi repeated rule-message rows là request mới, không dùng rule/response làm nhãn. Nhãn có thể được review với capture, provenance, independent semantic evidence và campaign binding rồi tạo dataset/provenance bất biến mới. Các holdout đã khóa giữ nguyên.

## Admission nhãn v2 và nguồn attack mới — 2026-11-01T07:36:28.147641+07:00

**Không có positive HTTP mới đủ điều kiện train ở lượt này.** Nguồn mới có cả nhãn normal/attack nhưng audit chưa xác minh được cơ sở nhãn theo request. Không đưa unknown vào supervised loss hay tính observations thành physical requests.

| Nguồn | Số đo đã xác minh | Trạng thái học/đánh giá |
| --- | --- | --- |
| Lab hiện hữu | 75.150 HTTP thật đã phát/capture, không phát mới lượt này | Scripted intent; không phải independent human review |
| SR-BH hiện hữu | 907.815 dòng đã audit trước; 310.314 structural research candidates | Retrospective development; không final holdout |
| WCP nonreserved hiện hữu | 811.129 records audit / 756.548 request signatures / 44.437 projections | Publisher benign-only; chưa admission; 148 reserved files chưa đọc |
| Organization X hiện hữu | 211.178 distinct complete-log observations | Unknown, không rule-derived benign |
| SOC-MLD v2 mới | 198.122 access lines; 198.082 parseable; 193.220 complete-log identities; 6.856 method/URI/UA views | Toàn bộ mới chờ review; verified physical requests=null, training eligible=0 |

Không cộng các cột ở bảng hoặc cộng 11.679 EVE HTTP / 119.330 flow / 28.013 alert của SOC-MLD thành request mới. Raw archive và publisher labels được giữ nguyên. 40 access lines không parse được vẫn nằm trong raw. Biểu diễn method/URI/UA không bao gồm body, không đồng nghĩa encoded76 model views hay physical identity.

SOC-MLD: 6.600 operator rows đều timezone-naive, không có request ID; code consume nearest time±30s rồi fallback `label_l7_payload`/NORMAL, L3/L4 dùng signature. Không đoán timezone/offset để biến thành ground truth. CSV thực 4.786 train/1.220 test, 38 `attack_instance_id` chung và thời gian chồng lấn. Các số README 5.058/947 không thay thế readback. Published alert windows dùng ts±60s và whole-session aggregates; không nhập những feature này cho causal inference.

### Hợp đồng review có bằng chứng

Review manifest v2 gắn `dataset_sha256`, `provenance_sha256`, `environment_id`, reviewer/collector IDs khác nhau, scope, `decisions_file`, `decisions_sha256` và digest `review_sha256`. Ledger JSONL dùng `event_key` immutable và các trường:

- `intent`: benign / attack / unknown; `label`: 0 / 1 / null theo review, không theo HTTP status hay detection.
- `review_status`: approved / pending / rejected; pending/rejected/unknown không cấp nhãn dùng để học.
- `attack_family`: family được hỗ trợ hoặc null; unknown family không tự suy diễn.
- `exploit_outcome`: unknown / succeeded / failed / not_applicable. Attack thất bại vẫn là positive intent.
- `evidence`: tối đa 8 refs, mỗi ref có kind, file tương đối, SHA256, event_key và dataset_sha256. Approved intent cần đủ request_capture, intent_provenance, independent_semantic_review; review ngữ nghĩa phải có artifact khác capture. Success/failure còn cần application_oracle.

Review có thể theo protocol/campaign và dùng chung artifact cho nhiều event nếu trace nguồn chứng minh được binding của từng request; không bắt buộc kiểm thủ công từng dòng trong hàng triệu request. Cần phân biệt review protocol/generator với manual semantic review từng mẫu, không tự tuyên bố đã review toàn bộ. Rule hits, model prediction, status-only hoặc time proximity không được dùng làm loại bằng chứng ground truth. Mỗi event chỉ review một lần; dòng dư ngoài dataset hoặc nhãn đã biết mâu thuẫn bị từ chối. Không đổi nhãn tại chỗ. Nếu review giải quyết unknown, tạo chain dataset/labels/provenance immutable mới rồi attestation đúng binding trước admission. Review v1 cũ vẫn dùng được cho research workflow cũ nhưng **không đạt cổng formal**; cached catalog không có evidence-v2 markers cũng không mở formal.

`scripts/audit-label-evidence.py --review <review.json> --dataset <immutable-dataset> --provenance <provenance.json> --environment-id <id> --output <new-directory>` kiểm tra binding và tạo report/index. Hash/ID chỉ bảo vệ integrity; nguồn-owner và người review thật vẫn phải chịu trách nhiệm ngữ nghĩa/independence. Không tạo reviewer hoặc approved labels giả. Path/evidence dưới sealed markers bị từ chối.

### Điều kiện trước study tiếp và formal

Giữ nguyên yêu cầu 2 eligible dual-class sources cho research, tối thiểu 32 samples và 32 encoded views/class/source/role, group/view purge và embargo 300s. Benign-only WCP không được lách gate. Formal scale policy và toàn bộ holdout vẫn khóa; chưa có balanced independent acceptance corpus. Phải kiểm provenance/license, request-bound label/visibility, campaign/environment independence và fit-side preprocessing trước future labels; không lọc lỗi final theo nhãn tương lai.

Protocol acceptance phải khóa trước scores: matched MLP/GLU/baseline, dữ liệu/feature visibility/ngân sách FPR, calibration hợp lệ, metrics theo source/campaign/family và cluster uncertainty; đo latency model-only riêng end-to-end. Không chọn threshold từ test, không dùng benign-only để kết luận recall. Chi tiết executable contract và nguồn được cập nhật ở `configs/public_http_sources.yaml`; [report](../ai-training/reports/ATTACK_EVIDENCE_20261101.json) và ledger 32 giữ file hashes/lệnh/trạng thái.

Kiểm chứng cuối: **211 pytest PASS, 0 skip**; Ruff/format/compile/canonical PASS; **53/53 gate kỹ thuật legacy PASS**, corpus formal **NOT_READY/0 eligible** (exit 3 đúng thiết kế). Giữ nguyên SHA của **2.941 file** cũ và source/config freeze trong final test; không sửa hai Web. Handoff format 10, ledger 32.

## Corpus công khai, nhãn và giới hạn sử dụng — 2026-11-01T06:48:58.523006+07:00

Tái sử dụng nguyên vẹn SR-BH audit 907.815 dòng, curation 310.314 candidates và corpus development hồi cứu 118.760 vectors; không làm lại projection/train đã hoàn thành. SR-BH và validation từng xem vẫn là development exposed, không test cuối độc lập.

### Nguồn benign mới đã xác minh

[Publisher open-appsec WCP](https://github.com/openappsec/waf-comparison-project) mô tả capture khi duyệt/thao tác website và cấp Apache-2.0 rõ ràng cho legitimate dataset. Pin revision `8ec8263eebba76816601f7c7052f8ffb83e31312`, README/LICENSE/config SHA. Archive 1.203.983.791 byte, SHA 256 `58faee18c54229759287a574f6f8cb1e3b951fa135e403ea9a679d2b18efd778`; nguồn không cung cấp checksum crypto riêng, local SHA được pin sau tải HTTPS/ETag/Content-Range xác minh. Raw gốc giữ private, không commit.

Archive có 692 JSON case files; tài liệu publisher ghi 692 websites/14 categories nhưng README ghi 185/12. Báo actual case files, không tự coi là 692 môi trường độc lập đã review. Last-Modified của archive không là clock của từng request. Không nhập tập malicious đi kèm: payload collection có copyright/lineage hỗn hợp và không phải các HTTP độc lập được capture chỉ vì được bọc thành request.

HMAC website roles khóa trước nội dung: bucket 0–1 reserved, 2 calibration, 3–4 validation, 5–9 train_candidates. 148 reserved files **không đọc/project/score**, không suy ra số request từ mô tả tổng. 544 file còn lại được audit hết:

| Quyết định | Record |
| --- | ---: |
| Biểu diễn HTTP có signature khác nhau |756.548|
| Trùng signature quan sát |54.391|
| Quarantine URI thiếu/quá dài |170|
| Quarantine object JSON chưa parse được/quá lớn |20|
| Tổng record được kiểm tra ngoài reserved |811.129|

Mỗi record có source SHA/member HMAC/index/decision, duplicate link hoặc lý do loại trong ledger. Signature là canonical observed request object, không chứng minh unique physical request IDs hoặc phiên người dùng độc lập. Không đếm projection/bản copy/duplicate là HTTP mới. Nhãn 0 được giữ theo **publisher legitimate-capture annotation**, không suy từ status/no-alert và chưa được nhóm này review ngữ nghĩa độc lập.

### Biểu diễn và role không đồng nghĩa admission

Staging roles:443.897 train_candidates, 87.189 calibration, 225.462 validation; chưa role nào được dùng fit trọng số/threshold. HMAC signature modulo 17 chọn 44.437 projections, không theo score hoặc nhãn khó/dễ. Có 26.318 unique bounded 76 model views; cùng population có 187.167 record chứa body nhưng body không vào request-only model, tất cả 756.548 thiếu timestamp. Trong projections:2.257 query-lexical unavailable và 1 URI-lexical unavailable; không khôi phục query đã mất hoặc giả behavior/flow.

Các case groups disjoint, nhưng numeric input có overlap giữa role: train_candidates→cal 235, train_candidates→val 510, cal→val 207 unique views. Chưa train nên đây không phải model leakage của benchmark mới; nếu ghép để fit sau này phải xử lý lineage/template/views bằng protocol phù hợp. Primary benchmark giữ mọi mẫu validation hợp lệ, không lọc khó theo score; novel-view sensitivity chỉ bổ sung. Trong 13.290 validation projections, 144 khớp input train cũ:141 benign-view, 3 positive-view. Đây là mơ hồ của partial representation/nhãn cần review, không đủ để đổi nhãn hoặc kết luận HTTP gốc bị sao chép.

### Unknown, holdout và bước tiếp

Organization X vẫn 211.178 distinct log observations theo audit cũ, raw và report giữ nguyên; **unknown**, 0 nhãn mới. Các rule UA/method/readme/nonmatch chưa là ground truth. Cần source-owner/independent evidence-bound review; không gán benign mặc định hoặc dùng dự đoán model tự làm nhãn.

Holdout cũ và public 148-case benign supplement giữ kín; không có recall/PR-AUC đáng tin từ nguồn chỉ có benign. `prospective_evaluation_plan` trong catalog hiện có thiết kế thêm browser catalog/cart, documentation/code search và API/auth campaigns có quyền, role/time/seed/template khóa trước, actual 10/60/300 s history và review evidence. Trạng thái **DESIGNED_NOT_COLLECTED**, không có target live nào được tự cấp quyền. Không biến row index thành timestamp hoặc giả source flow.

Nguồn mới được phép audit và frozen external FPR stress, **supervised/formal admission=false**. Tổng lab 75.150 HTTP giữ nguyên, 0 traffic mới thu lượt này, scale-admitted 0/2M. Positive độc lập, nhãn ngữ nghĩa, clock/behavior và balanced independent evaluation còn thiếu; ưu tiên chúng thay vì tổng row count.

[Báo cáo dữ liệu/tổng quát hóa](../ai-training/reports/GENERALIZATION_QUALITY_20261101.json), [handoff format 9](../ai-training/FINAL_TRAINING_HANDOFF.json), ledger 06 mục 31. Các snapshot phía dưới là lịch sử.

## Data admission đã triển khai; corpus 2M NOT_READY — 30/10/2026

Đầu vào hiện chỉ 69.345 request, một fixture localhost và kịch bản tự động. Không
đếm bản sao PCAP/snapshot, re-projection, checkpoint cache hoặc dòng flow thành
HTTP request mới. Bộ cũ vẫn là baseline riêng; test cũ không được đưa ngược vào train.

Nâng cấp theo registry immutable có hash và scope/label provenance, kiểm trùng
capture, thứ tự thời gian/embargo và các holdout. Một instance/container clone
không tự chứng minh một môi trường độc lập. Gate lớn phải phản ánh số request,
nguồn, môi trường, ngày, campaign và bằng chứng review thực; thiếu dữ liệu thì
NOT_READY. Không tự lấy CSV flow công khai làm request/schema ứng dụng hoặc điền
các cột thiếu bằng dữ liệu bịa. Corpus lab vẫn phục vụ technical pilot.

**Đo thực cuối phiên:**134 tests và53 gate kỹ thuật PASS trên69.345 request cũ;
fit scaler benign train29.511 rows; split41.607/13.869/13.869. v5 giữ source3/flow/
embargo300s như snapshot cũ. Registry chỉ có reference, scale-admitted=0. Không có
nguồn độc lập mới hoặc human review. Multi-environment shared-scaler assembly chưa
được triển khai/nghiệm thu; không tự ghép các feature đã normalize riêng.
[Báo cáo](../ai-training/reports/SCALE_UPGRADE_20261030.json) ghi đầy đủ giới hạn và hashes.

## Temporal dynamics v5 và admission — triển khai 30/10/2026

`ai-features-5` / `ai-normalizer-5`:207 cột=189 cột cũ+18 dynamics, vẫn dùng numeric
projection v2 và canonical 1.0. Opt-in bằng `prepare --behavior-dynamics`; default
profile cũ giữ nguyên số cột/ngữ nghĩa. Không force-resume checkpoint cũ bằng v5.

Mỗi scope IP/user thêm: interarrival log1p và cờ missing; burst10/60 và60/300;
URI/method transition; CV khoảng cách request trong60/300s; gia tốc tỷ lệ auth
failure giữa10/60s. Chỉ lịch sử đã quan sát và request hiện tại, tối đa2048events/
entity như trước; thiếu/evict/truncate vẫn có cờ context incomplete. Không thêm raw
query, bí mật, identity hoặc rule/SID vào vector. Scaler fit benign train duy nhất.

`corpus-audit` đọc Parquet và provenance immutable bằng SQLite index trên đĩa;
chống duplicate dataset/PCAP kể cả re-project, không gán lại test cũ vào train,
kiểm tra holdout identity/payload, thứ tự thời gian/embargo, coverage nguồn và nhãn.
Review phải là attestation độc lập gắn hash dataset/provenance/environment; nhãn
automatic của lab không được tự nhận là human review. Attestation không tự chứng
minh sự thật; người review phải kiểm realism/topology/nhãn.

Policy scale ban đầu đặt2M eligible requests,3 environments,7capture days,120 campaign,
4 roles train/calibration/validation/test,≥95%three-source. Các floor ngoài2M là
engineering proposal cần review, không là chuẩn chất lượng phổ quát. Registry
chỉ audit; không concatenate các vector dùng scaler khác nhau. Shared-scaler corpus
assembly và kiểm định trên nguồn mới còn phải hoàn tất trước formal.

**Nguồn hiện có:** cùng69.345HTTP thật của lab, chưa thêm request hoặc môi trường.
V5 là re-extraction, không cộng lại thành corpus mới. Tập này là reference/technical
pilot, chưa đạt scale admission vì thiếu independent labels/environments. Flow CSV
công khai không tương đương HTTP requests: [CICIDS2017 chính thức](https://www.unb.ca/cic/datasets/ids-2017.html)
phân biệt PCAP với labeled flow CSV. Không điền giả Student fields để nhập CSV đó
vào hợp đồng ba nguồn của model này.

## Corpus revision 4.1 đã nghiệm thu offline — 2026-10-30T09:08:21+07:00

| Hạng mục | Kết quả đo thực |
| --- | --- |
| Corpus | 69,345 request; 297,685 observations từ Student, Nginx và Suricata thật |
| Split và nhãn | 69,345 vectors có nhãn được duyệt; train: 41,607 / val: 13,869 / test: 13,869; groups 27/9/9 |
| Đặc trưng | ai-features-4.1 / normalizer 4.1, 189 cột, projection v2; canonical 1.0 giữ nguyên |
| Mô hình | Residual nhỏ đối chứng; MLP 248.072 / DAE 294.717 / gated residual 445.448 tham số |
| Readiness | 53/53 PASS; payload và hard negatives có identity riêng giữa các temporal bands |
| Pilot | 4 mô hình × 5 epoch; resume qua process mới khớp reference; ONNX 69,345/69,345 vectors PASS từng mô hình |
| Kiểm thử và phạm vi | 118 pytest PASS, 0 skipped; giữ nguyên hash 366 file dịch vụ/contract và 1.946 artifact cũ |
| Train dài / chất lượng trên test / deploy | NOT_RUN; chưa chọn Champion Model hoặc nghiệm thu Rust/live/enforcement |

Nhãn pending theo HTTP contract: 0; loại khỏi nhãn
do trùng identity giữa holdout: 0.
Packet counters: `{'captured': 717792, 'dropped_by_kernel': 4, 'received_by_filter': 1435588}`.
Parser quality: `{'accepted': 297685, 'duplicates': 0}`. Không hạ gate hoặc đổi timestamp/embargo
để đạt điều kiện. Dataset SHA `f143742a7dd5c130a3adcbc40b611f14938a4759a50816efada9b59308b18f50`.

[Báo cáo](../ai-training/reports/PRETRAIN_EXPANDED_20261030.json) ghi coverage, các cột hằng, bằng chứng campaign/variant và giới
hạn thực nghiệm. Chưa tính chất lượng trên test; canonical schema 1.0 giữ nguyên.

## Mở rộng cấu trúc Query/URI, revision 4.1 — 29/10/2026

`safe_query_numeric_v2` mở rộng adapter AI, giữ **canonical v1.0** và các profile
cũ nguyên nghĩa. Vector mới có **189 cột**: 148 cột cũ + 41 số cấu trúc. Vì v4/148
đã có checkpoint, revision mới ghi `ai-features-4.1`/`ai-normalizer-4.1`, projection
version 2, state option và hash riêng. Không sửa nhãn/version của artifact cũ.

| Nhóm mới | Đặc trưng điển hình | Mục đích và giới hạn |
| --- | --- | --- |
| Availability/encoding |structure_available, decoded URI/query length, encoding rounds, valid/invalid escapes, contraction ratio |Đếm trên view trong memory trước mask; tối đa hai lần decode |
| Phân bố ký tự |Unicode/uppercase/whitespace ratios |Không giữ ký tự, byte n-gram hoặc từ tự do |
| Cấu trúc tham số |max/mean/std length, duplicate/empty counts, numeric value ratio |Chỉ trên key được phép; không đo giá trị password/token |
| SQL/punctuation |block/line comment delimiters, comparisons, boolean operators, commas, parenthesis counts/depth |Các bộ đếm số, không là rule match/nhãn attack |
| HTML/URI |tag open/close, HTML entity, event assignment, URI scheme counts |Có hard negatives tài liệu/lập trình hợp lệ; cùng ký hiệu có thể mang ý nghĩa khác |
| Path/shell |parent/dot segments, slashes/backslashes/dots, &&/\|\|/substitution/backticks/newlines/null counts |Không chạy lệnh hoặc đọc file target; chỉ phân tích chuỗi request |

Allowlist 69 key số = 28 key của projection v1 + 41 key trong `structure.py`. Envelope
v2 chỉ chấp nhận `{version:2,numbers:{...}}` đúng key và số finite trong giới hạn.
Collector chọn v2 bằng profile; thiếu projection giữ unavailable. Không chấp nhận
envelope v1 như v2 hoặc tự tính đặc trưng từ query đã mask để lấp trường thiếu.

Key query được decode bounded rồi kiểm allowlist. Bỏ các key nhạy cảm/không được
phép; PII hoặc giá trị đã redaction không góp nội dung vào thống kê. URI giữ view
encoded để đo encoding, nhưng cắt đuôi credential path/PII trước tính số. Test
thay token/password/path-secret bằng chuỗi khác phải cho cùng projection; các
secret canary không xuất hiện trong output. Credential tail được loại cả khi
dấu phân cách là `/`, `%2F`, `%252F`, `%5C` hoặc `%255C`; encoded traversal
vẫn được đếm nếu không chứa credential tail. Không ghi query/body/header tự do
vào EVE dành cho AI hay Parquet. PCAP raw vẫn là evidence private của fixture giả.

Offline Suricata decoder và `project-eve --projection-version 2` gọi cùng hàm.
Decoder dùng `--query-numeric --projection-version 2`; normalizer/feature state,
scaler train-only và reference inference cùng revision. Model vẫn post-response;
Rust live, TLS vantage, receipt-time và mất nguồn chưa được nghiệm thu bởi việc
thêm numeric projection. Không phát biểu rằng các bộ đếm hiểu đầy đủ ngữ nghĩa
SQL/HTML/shell hoặc thấy nội dung đã bị loại vì privacy.

Corpus mới dùng45 campaign với seed độc lập,27/9/9 nhóm, nhịp lognormal/jitter,
parameter keys/order/paging và bốn catalog endpoint thay đổi. Mỗi họ payload có
16 views/band; hard negatives có12 views/band riêng. Identity tính từ decoded payload;
approved attack **và hard-negative identity** không giao giữa train/val/test.
Nếu phát hiện identity lặp ở band sau, giữ request context nhưng loại nhãn khỏi
fit/quality evaluation, lưu evidence. Identity của các view mới đã được test
disjoint trước capture; không gán nhãn bằng rule/status hoặc số liệu model.

Embargo của splitter giữ 300 giây; gap thật 620 giây để có khoảng trống ở cả hai phía
cutoff. Không viết lại timestamp/IP để đạt split. Gate mở rộng yêu cầu 60.000–80.000
request, ≥9 nhóm/partition, ≥12 payload views/họ/partition và ≥12 hard-negative views
độc lập mỗi partition, cùng source/flow/300s coverage và variation của cấu trúc.
Các ngưỡng này là floor cho offline pilot, không phải chứng nhận production.

## AI input contract v4 — nâng cấp ngày 29/10/2026

Canonical Event Schema **1.0 giữ nguyên**. `safe_query_numeric_v1` là extension
của adapter AI cho Suricata EVE, không thêm field vào JSON Schema hay bảng sự kiện
của Student/Security. Corpus và checkpoint `edge_masked_v1` cũ được giữ riêng;
không trộn hoặc force-resume với feature/normalizer v4.

| Thành phần | Contract mới |
| --- | --- |
| Input profile | `safe_query_numeric_v1`, opt-in khi decode PCAP bằng `--query-numeric` |
| EVE extension | `ai_query_numeric: {version: 1, numbers: {...}}`; đúng 28 key số finite, không có chuỗi payload |
| Feature/normalizer | `ai-features-4` / `ai-normalizer-4`, vẫn 148 cột; có fingerprint implementation |
| Shared transform | `project-eve` và offline decoder cùng gọi `redact_eve` → `project_query` trước khi bỏ query |
| Thiếu projection | Ghi unavailable; không phục hồi query từ bản đã mask hoặc từ rule hit |
| Flow | Chỉ flow client đã hoàn tất, `available_at=max(EVE timestamp, flow.end+65s)`; không lấy flow tương lai |

28 key gồm `uri_length`, `path_depth`, `uri_entropy`, `query_length`,
`query_entropy`, `parameter_count`, `digit_ratio`, `special_ratio`,
`uri_lexical_available`, `query_lexical_available`, `object_identity_available`,
`sqli_keywords`, `xss_tokens`, `traversal_tokens`, tám bộ đếm
`quote_single/quote_double/semicolon/percent/lt/gt/dollar/pipe`, năm bộ đếm có
prefix `query_original_` (`length/parameter_count/percent_count/quote_count/operator_count`)
và `query_original_available`. Original counters và object identity vẫn unavailable
nếu producer không cung cấp. Tên key đầy đủ được kiểm bằng allowlist trong code.
Operator counters mới đếm trên view đã decode tối đa hai lần sau redaction;
`percent` giữ trên view encoded. Profile cũ giữ nguyên ngữ nghĩa.

Tham số password/token/secret/cookie/CSRF/OTP và PII được loại trước tính số.
URL, UA và response header được allowlist trước khi ghi EVE. Không lưu body,
Cookie/Set-Cookie, hostname, referer hay alert text vào EVE dành cho AI. Snapshot,
Parquet và model input không chứa plaintext query/credential. **PCAP riêng của lab
vẫn chứa HTTP thô và session của tài khoản giả**; file 0600 dưới thư mục private,
không đưa lên Git hay phát hành cùng model.

`query_numeric_policy.yaml` đặt floor 40.000 request, ≥6 nhóm mỗi partition,
campaign ≥450 giây, đủ GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE benign, ≥95%
projection và query visibility của bốn họ payload. Mỗi partition cần ≥6 payload
identity đã decode khác nhau mỗi họ; hash identity không được giao giữa các tập.
Plan hash phải riêng cho từng campaign. Đây là gate dữ liệu cho offline pilot,
không chứng nhận chất lượng phát hiện.

Identity payload được tính từ probe đã decode/lowercase, không dùng tên campaign
để giả định hai probe khác nhau. Nếu một identity xuất hiện ở temporal band trước,
bản ở band sau giữ trong raw log và request context nhưng bị loại khỏi nhãn
train/evaluation. `label_evidence.json` lưu HMAC request key, hai band, identity
và lý do loại. Đây là dedup trước fit, không chọn mẫu theo kết quả model; không
sửa timestamp/IP, không gán bản trùng thành benign và không hạ floor của gate.

**Điều kiện dùng model ở edge:** bridge phải thấy cùng HTTP view trước redaction
(sau TLS termination nếu có), chạy đúng projection v1, rồi mới đưa số vào AI.
Python bridge dùng chung hàm với decoder; Rust live serving/receipt-time parity
chưa được nghiệm thu. Không dùng model v4 với stream v3 đã bỏ query. Response
status/latency là tín hiệu sau request, không phải quyết định chặn trước request.

| Tiến độ dữ liệu v4 ngày29 | Kết quả đã xác minh |
| --- | --- |
| Corpus ba nguồn |46.230request /198.765observations; PCAP0kernel drops, parser0invalid/oversized/partial |
| Nhãn/split |46.134approved vectors sau96overlap exclusions; train27.738/val9.150/test9.246, nhóm18/6/6 |
| Readiness |48/48PASS;38/148cột hằng, so với59/148ở corpus cũ |
| Pilot |Bốn model5epoch, exactresume và ONNX toàn bộ vectorPASS; chỉ chất lượng validation |
| Chưa nghiệm thu |Đại diện production, human realism review, Rust live/TLS/receipt-time, thiếu nguồn và champion |

Corpus mới nằm private ở `upgrade_20261029_query/dataset-ready`; checksum và kết
quả cuối ở [report nâng cấp](../ai-training/reports/PRETRAIN_UPGRADE_20261029.json)
và ledger06 mục23. Các snapshot bên dưới là lịch sử.

## Ca residual đầu tiên — 29/10/2026

Đã chạy một experiment residual offline với trần150phút: data-readiness35/35PASS,
dừng sớm tại14epoch sau11,616giây bởi patience8, best tại6epoch. Checkpoint và
ONNX19.275/19.275PASS; chỉ tính chất lượng validation (recall44,20%,FPR0,943%).
Dataset/schema/features giữ nguyên; đây vẫn là lab có fixture giả, chưa champion,
Rust/live hoặc nghiệm thu endurance150phút. Xem [báo cáo ca residual](../ai-training/reports/FORMAL_RESIDUAL_20261029.json) và ledger06 mục22.
Các trạng thái “chưa train chính thức” trong snapshot28/10 bên dưới giữ ý nghĩa lịch sử.

## Cập nhật resource sau pilot — 28/10/2026

Ca tiếp theo dùng **8logicalCPU/16GiB RAM**, CPUQuota800%, MemoryHigh15GiB,
swap0,Nice10; BLAS/OpenMP8,ONNX intra8/inter1 sequential. CPU là50% của16luồng;
16GiB là**52,96% RAM OS-visible** trên máy32GB danh nghĩa, được user chỉ định rõ.
77testsPASS,35readinesschecksPASS, guardprobe0optimizerstep; **không train chính thức
hoặc chạy lại pilot corpus thật**. [Báo cáo resource](../ai-training/reports/RESOURCE_GUARD_20261028.json).

Dataset prepared và pilot-ready giữ nguyên hash; readiness-final cũ cũng được giữ.
Readiness mới`readiness-resource8` gắn source hiện hành và được handoff/script sử dụng.
Các metric/giới hạn2CPU/12GiB ở các snapshot pilot phía dưới là lịch sử. Các attempt
fail/stale/cache/NEXT_COMMANDS cũ đã dọn; giữ raw capture evidence, runtime và venv
cần thiết. Xem ledger06 mục21 cho kiểm tra, danh sách dọn và commit.

Ngày khảo sát: **26/10/2026** (Asia/Ho_Chi_Minh). Baseline code: `37bc4d2ae1552939659a10647898e2228f1b801f`.

**Cập nhật foundation 26/10/2026:** canonical v1.0 đã có code, JSON Schema, fixture và validation; Java xuất JSONL, Rust thu cả Student/Nginx/EVE khi bật dataset. Foundation đã được commit đến `fbe078d` (xem06 mục15); branch AI hiện hành là `feat/ai-model-training`. Phần1 là bằng chứng khảo sát lịch sử tại37bc4d2; phần2 dưới đây là **contract hiện hành đã khóa**. Tại mốc foundation chưa tải public dataset hoặc tạo model; cập nhật AI dưới đây thay thế phần trạng thái đó, không đổi contract v1.0.

## 0B. Corpus ba nguồn và featurev3 — 28/10/2026

**Trạng thái28/10/2026:** corpus mới có **19.275 request thật / 80.556 observations**, đủ Student audit + Nginx + Suricata EVE từ PCAP thật trong namespace lab. Split **11.565 / 3.855 / 3.855**, nhóm 9/3/3; mỗi campaign ≥420 giây, hai khoảng nghỉ 620 giây thật. Feature v3 / normalizer3, 148 cột, `edge_masked_v1`; canonical v1.0 giữ nguyên. Readiness **35 checks PASS**, **77 tests PASS / 0 skipped**. MLP/AE/residual đều chạy 2 epoch → tiến trình mới resume đến 5 epoch, exact với reference 5 epoch; ONNX parity toàn bộ prepared rows. Chỉ đánh giá validation; test metric chưa mở. [Report có hash](../ai-training/reports/PRETRAIN_PILOT_20261028.json).

Chưa chạy ca chính thức 2–3 giờ, chọn champion, port Rust hoặc bật AI response. Corpus vẫn là loopback với fixture giả / scripted intent; chưa đại diện production. Query bị mask thống nhất nên metadata AI không thấy nội dung payload. Flow chỉ lấy flow client đã kết thúc ≥65 giây trước đó, không backfill bằng đóng flow tương lai. Live receipt-time/TLS/feature parity và human realism review còn riêng.

DatasetSHA`eb494a87534b156b3a4f6b1f5746bf798c2f8971ff266f645a603725b840b5c5`. Flow availability sau warmup/delay: train: 9757/11565, val: 3233/3855, test: 3236/3855. Các mẫu đầu vẫn thiếu có cờ; không sửa dữ liệu để đạt100%. Duration lấy EVE end−start khi có, fallbackage; byte/packet không dựng từ audit. HTTP response headers nhận qua Unix socket rồi allowlist X-Request-Id trước ghi; hostname/redirect/body/cookie không đi vào EVE xuất hoặc features. Nginx/Student được scope bằng observerID kể cảpending; EVE giữ mọi event trong privatePCAP. Source/capture/labels/dataset/model có hash riêng; inventory capture ghi version đã load, processing/training ghi source cuối. Native generic adapter vẫn phục vụ fixtures; ca chính thức yêu cầu gate ba nguồn + long-window, không chỉ policy hai nguồn cũ.

## 0A. Pre-training pilot — snapshot lịch sử27/10/2026

Chỉ sửa packageAI và docs. Đã bổ sung snapshot complete-line prefix có read-back
checksum, observer intent/HTTPexpected-outcome, importlabel cóboundcapture,
reviewCSV giữcontextimmutable, policyreadiness và lifecycle lab riêng.
`configs/pretrain_policy.yaml` chốt ngưỡng cho offlinepilot; không tự gán no-alert
thànhbenign, không sửa thời gian/IP để vượt splitter. Nhãn confidence vàsource tách
biệt; unknown/pending không train. HEAD/OPTIONScatalog403 trong pilot có correction
contract riêng dựa trên SpringSecurityGETmatcher, giữ count/evidence thay vì xóa lịch sử.

Feature tại snapshot27/10 **ai-features-2/148cột**, normalizer2; thêm UA family multi-hot và
missing/unknown (allowlistproduct, có boundary để tránh nmaple→nmap). Không đưa
arbitraryheader,rulefacts hoặc identity vào input. `feature_spec`/golden vectors và
implementationhash đổi version; canonicalv1.0/sourceJava/Rust không đổi. Dataset và
checkpointfeaturev1 cũ không được ép resume với source mới.

Pilot dùng nguồn StudentJSONL và NginxJSON lab riêng giữ các queryprobe giả không
nhạy cảm để nghiên cứu lexicalfeatures. **Đây là inputprofile khác với edge hiện
hành đã bỏ queryvalues**; phải xác minh telemetrydeploy tương thích hoặc sửa
profile/features trước tích hợp. Không có EVE capture thật khi host từ chối packet
socket; flowfeatures giữmissing, không sinh EVE giả. Khả năngpháthiệnnetworkflow,
bodypayload,failedusername hoặc object-levelIDOR chưa được nghiệm thu bằng corpus này.

15campaign có sourceIPloopback bind thực, user/session tách biệt và ba temporalbands
9/3/3; hai khoảngchờ620s là thời gianthật. Variantview được tách theo band và
readiness kiểm variantIDs không chéo partitions. Benign gồmreads/mutations/errors,
rolehardnegatives và fictionalFaculty; STUDENTfixture chưa gắn hồ sơ cá nhân nên
profile404 có chủđích. Behavioralclass là scriptedbulkreadattempt, không khẳng định
exploitthànhcông/zero-day. Humanrealismreview và campaigndài hơn vẫn cần trước
productionbenchmark; contextincomplete/constantcolumns được báo rõ.

**Đã chạy:**27/10/2026 19:48:25–20:17:59+07:00,4.875HTTPrequestthật với fixturegiả;
9.750observations,4.875nhãn intentapproved,0unknown trong phạmvi chiến dịch. Bỏ3Studentaudit
và2Nginxwarmup ngoài observer bằngrequestID, giữrawhash/count vàmọipendingcase;
khônglọc theoHTTPstatus/label/rule. Split2.925/975/975,groups9/3/3,148features;
23readinesschecksPASS.435benignHEAD/OPTIONS403 được correctionnarrow cócontractSHA.
Xem [PRETRAIN_20261027.json](../ai-training/reports/PRETRAIN_20261027.json),
[PRETRAINING.md](../ai-training/PRETRAINING.md) và06mục18. DatasetSHA
`599166880745d6da7042c39c0639478f2150e5d518db8050d839ca56460926db`.
Giờtraincorpus=0. Canonicalsource/config356filegiữnguyên.

Phần0 dưới là evidence của lần triển khai offline/S0 v1 trước cập nhật này.

## 0. Data pipeline đã triển khai — 27/10/2026

Owner triển khai: Codex, nhánh `feat/ai-model-training`, base `fbe078d`; chưa có review người thứ hai. [`ai-training/README.md`](../ai-training/README.md) là runbook CLI hiện hành; [`schema_contract.yaml`](../ai-training/configs/schema_contract.yaml) ghi đúng field/type/unit từ Java exporter, Nginx, EVE và16cột `normalized_events`, kèm hash source. Canonical v1.0 SHA-256 `7e3d82c5785cb8073737ed444ef58de72288ec89766bc24d554bbba285bfb3c4` **giữ nguyên**; không đổi producer, migration hay config dịch vụ.

| Công đoạn | Hợp đồng đã có code/test |
|---|---|
| Input | Student JSONL; Nginx JSON hiện hành/legacy combined; EVE http/flow/alert; canonical JSONL hoặc PostgreSQL export `{canonical: {...}}`. Chỉ đọc snapshot; từ chối file thay đổi. Không có DB connector ghi/đổi config |
| Units/validation | Nginx `latency_seconds`×1000→ms; EVE `flow.age` giây, byte/packet counters giữ units; uint64 flowID không qua float. Canonical validation strict version/unknown fields, bounded line64KiB, đếm partial/oversize/malformed |
| Privacy | HMAC key AI riêng≥32byte, purpose-separated IP/user/session/request/flow/campaign IDs. Route allowlist/template, UA family allowlist (có alias Edge), loại query secret/PII trước numeric projection; không lưu query/body/header/raw evidence vào Parquet |
| Correlation | RequestID+IP tương thích+≤2s, mỗi nguồn tối đa1observation/request, Student ưu tiên actor. Ambiguous IDs không merge/không áp nhãn; cùng IP/thời gian chỉ context. Flow match qua cùng flowID pseudonym và timestamp≤decision, không dùng future/close counters |
| Ground truth | `label`0/1, `attack_family`8lớp, `label_source`, `label_confidence`, `review_status`. Chỉ scenario_manifest/human_review approved; weak_rule/unmatched giữ unknown và không train. HTTP success/no-alert không phải benign |
| Snapshot | Sanitized SQLite scratch có giới hạn memory, streaming Parquet; immutable manifest/hash/input hash/time range/distributions, verify trước prepare/train/resume. Không đưa scratch/raw/key/model vào Git |
| Split | Temporal60/20/20, connected groups campaign/client/user/session, embargo300s, purge group spanning/boundary; từ chối partition reviewed rỗng, không fallback random |
| Feature/scaler | `ai-features-1`:125features request/flow và cửa sổ10/60/300s IP/user; inclusivecurrent một lần, late-event rejected, LRU/event caps +incomplete flags. Scaler fit benign train-only; order/vocab/impute/clip/float32/hash lưu feature_spec |
| Leakage control | IDs/labels/rule_signals/alert count không là model input mặc định; Suricata alert counts chỉ context10/60/300s. Unknown có thể góp context nhân quả trong partition, không làm training row |
| Inference parity | Python stateful reference dùng fused request row +cùng feature library; golden preprocessing fixture và ONNX parity. Rust port/parity chưa làm |

S0 thật đã chạy trên **fixture synthetic**:3403observations→960request→576/192/192 reviewed splits,125features. **42tests PASS**, ONNX960/960 mỗi nhánh; [report](../ai-training/reports/S0_20261027.json). Dữ liệu thật/giờ train thật vẫn0. Không tải public corpus, không đọc service DB live. Kho artifact chung chưa cấp; file local ignored không tự có trên máy bạn cùng nhóm.

Availability phải đi cùng feature: producer mask query/objectID thì không thể suy lại payload, entropy gốc hay unique studentID. `query_original_*` chỉ được dùng khi producer có counters hợp lệ; lexical còn lại là view đã lọc privacy. API/read/diversity chỉ hỗ trợ triage, chưa chứng minh IDOR/zero-day. Decision timestamp sau response; không tuyên bố chặn request đầu tiên. Các phần đề xuất data-readiness/public-data bên dưới vẫn là gate cần làm trên corpus thật.

## 1. Baseline lịch sử trước foundation: chưa có file audit

Ở snapshot khảo sát37bc4d2 (không phải code foundation hiện tại), trong các file nguồn, cấu hình và log được khảo sát, **không thấy file `audit.log`, cấu hình ghi `audit.log`, parser `audit.log`, hay cầu nối từ audit ứng dụng sang `security-web`**. Điều này chỉ mô tả workspace; không chứng minh máy triển khai bên ngoài không có một file như vậy.

Audit của `student-web` hiện là **bảng PostgreSQL `access_logs`**, được tạo bởi Flyway. Không được giả định file này là Linux auditd, ModSecurity audit log hoặc Suricata EVE: đó là các định dạng khác nhau. Bước tích hợp tiếp theo phải chốt hợp đồng audit ứng dụng; tên `audit.log` trong thiết kế này chỉ dành cho NDJSON của `student-web` nếu nhóm chọn bổ sung file export.

Luồng đang có:

```text
HTTP request → Spring SecurityRequestFilter
             → xử lý authentication / authorization / controller
             → finally: SecurityAuditService.record(...)
             → PostgreSQL student_db.access_logs
             → GET /api/access-logs (chỉ ADMIN)

Nginx combined access.log → Rust ingest → chỉ giữ match regex SQLi
Suricata eve.json         → Rust ingest → chỉ giữ event_type=alert
                                           ↓
                               security_db.security_alerts
```

Các request Nginx không match và EVE `http`/`flow` bình thường bị bỏ qua ở parser hiện tại, vì vậy **không thể lấy riêng `security_alerts` làm tập benign đại diện**. Chưa có dữ liệu train có version hay model trong các nguồn này.

### 1.1. Bằng chứng và ý nghĩa dữ liệu

| Nguồn trong repository | Điều code thực hiện | Giới hạn cho AI/detection |
| --- | --- | --- |
| `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityRequestFilter.java:26–45` | Lấy URI không query; ghi API mutation, response ≥400 hoặc exception; lấy IP bằng `getRemoteAddr()` | GET/HEAD/OPTIONS thành công không được ghi; actor có thể null; không có chuỗi đọc hồ sơ đầy đủ |
| `.../accesslog/service/SecurityAuditService.java:15–25` | Tìm actor đã xác thực; cắt IP 45, method 10, path 500 ký tự; lưu status, action tổng quát, latency | Không lưu username được thử khi login thất bại; không phát hiện được password spraying theo tài khoản từ audit hiện tại |
| `.../accesslog/entity/AccessLog.java:17–46` và `src/main/resources/db/migration/V1__initial_schema.sql:4–16` | Có `id`, `user_id`, `client_ip`, `http_method`, `request_path`, `status_code`, `action`, `user_agent`, `request_time_ms`, `created_at` | Có cột không đồng nghĩa đã thu thập: writer hiện **không set `user_agent`** |
| `.../accesslog/dto/AccessLogSummary.java:5–6` | DTO trả `id,userId,clientIp,method,path,statusCode,action,requestTimeMs,createdAt` | Không có `userAgent`; không có incremental cursor API |
| `.../accesslog/controller/AccessLogController.java:12–25` và `.../configuration/SecurityConfiguration.java:36` | API đọc phân trang/chi tiết, ADMIN; sắp theo `createdAt,id` | Offset pagination không phải giao thức ingest bền vững khi có insert/delete đồng thời |
| `.../configuration/AccessLogRetentionConfiguration.java:18–26` và `.../accesslog/service/AccessLogRetentionService.java:13–20` | Sau 60 giây, mỗi 10 phút xoá bản ghi cũ hơn 3 ngày; 500 dòng/transaction, tối đa 20 batch/đợt | Có thể mất cửa sổ lịch sử cần train/điều tra nếu chưa export bền vững trước retention |
| `.../configuration/SecurityRequestFilter.java:46–54` | DB audit lỗi chỉ ghi category/SQLSTATE vào server log | Chưa có durable fallback hay replay; request nghiệp vụ có thể đã commit nhưng audit không tồn tại |
| `.../accesslog/entity/AccessLog.java:44–46` | `LocalDateTime`, DB `timestamp(6)` không timezone | Chưa thể tự coi timestamp cũ là UTC; phải xác nhận JVM/DB timezone |
| `security-web/nginx/pbl4-proxy.conf:5–13` | Nginx ghi combined; forward X-Real-IP/X-Forwarded-For/X-Forwarded-Proto | Combined chứa target có query, referer, UA nên có nguy cơ PII/token; chưa có request ID xuyên nguồn |
| `security-web/src/main.rs:446–462` | Parser giữ source IP và request target; regex SQLi | Không chuẩn hoá status/bytes/latency/UA thành feature; chỉ URL target, không body POST |
| `security-web/src/ingest.rs:25–70` | EVE chỉ alert; Nginx URL decode một lần, đổi `+` thành space rồi xét regex; lưu nguyên dòng evidence của alert | Evidence có thể chứa dữ liệu nhạy cảm trong URL/header; regex không bao phủ payload body, double encoding hay ngữ nghĩa mọi endpoint |
| `security-web/config/suricata/suricata.yaml:179–201,251–286` | Cấu hình EVE có alert/HTTP/DNS/TLS; HTTP extended; payload/body dump chỉ là dòng comment | Chưa được khẳng định có body payload hay mọi loại flow trên sensor thực tế; Rust hiện bỏ các event không phải alert |

Các đường dẫn viết tắt `.../` trong bảng đầu là `student-web/backend/src/main/java/com/pbl4/studentweb/`.

`student-web/backend/startup.log:38–52` là log khởi động ngày **29/09/2026**, có PostgreSQL `28P01`/password authentication failure; không phải HTTP audit dataset và không chứng minh trạng thái vận hành hiện tại. Các file `backend/docs/data/*.json`, catalog tỉnh/xã và SQL seed là **dữ liệu nghiệp vụ/fixture**, không phải traffic có ground truth. Không chuyển tên, CCCD, email, ngày sinh hay thông tin liên hệ trong đó thành feature nhận diện tấn công.

### 1.2. Tín hiệu hiện có, thiếu và không được suy diễn

- Có thể xây thống kê **mutation/rejection quan sát được** theo IP + path + cửa sổ thời gian; không gọi đó là toàn bộ request rate.
- `REQUEST_REJECTED` chỉ là HTTP status ≥400, gồm nhập sai/CSRF hết hạn/không đủ quyền bình thường. `REQUEST_SUCCEEDED` chỉ là status <400, không chứng minh người dùng hợp lệ hoặc exploit thành công.
- Login lỗi thường không có actor; query và body không được audit. Không thể tái dựng tên tài khoản bị thử hay payload tấn công từ dòng audit hiện tại.
- `user_id` không phải session ID; nhiều thiết bị và phiên có thể cùng một user. IP sau proxy có thể là IP Nginx; IP Internet có thể là NAT dùng chung. Không gán một IP = một người dùng.
- TLS làm sensor thụ động trên chặng mã hoá không thấy URL/body. Chỉ lấy HTTP rõ ở điểm terminate được kiểm soát hoặc telemetry từ ứng dụng; không giả định mọi packet có payload đọc được.
- Path hiện là URI thực, chưa phải template. `/api/students/123` làm tăng cardinality và chứa ID đối tượng; phải chuẩn hoá `/api/students/{studentId}` ở feature pipeline.

## 2. Canonical Event Schema v1.0 — ĐÃ KHÓA TRONG CODE

Nguồn chuẩn: [`contracts/canonical-event-v1.schema.json`](../contracts/canonical-event-v1.schema.json), [`contracts/README.md`](../contracts/README.md), fixture [`student-audit-v1.jsonl`](../contracts/fixtures/student-audit-v1.jsonl). Java `AuditJsonlExporter` và Rust `events::CanonicalEvent` được kiểm theo cùng contract. Các tên `event_time_utc/source_event_id/...` trong đề xuất cũ không phải một schema thứ hai được triển khai.

| Nhóm | Trường v1.0 | Quy ước thực hiện |
|---|---|---|
| Phiên bản/identity | `schema_version,event_id,source,source_instance` | Version chính xác1.0; source=STUDENT_AUDIT/NGINX/SURICATA; eventID và instance ASCII1–128; Student sinh UUID một lần/line |
| Thời gian | `timestamp` | ISO8601UTC có Z; PostgreSQL occurred_at nhận timestamp; observed_at là lúc ingest trong DB, không phải field của producer |
| Correlation/mạng | `request_id,client_ip,peer_ip,dest_ip,src_port,dest_port,transport,flow_id` | RequestID không unique; IP literal/null; port0–65535/null; flowID string để không mất chính xác số lớn; không coi1flow=1request |
| Identity ứng dụng | `user_id,username,role,session_hmac` | Ba identity field nullable HMAC purpose-separated `hmac-sha256:<64hex>`; role ADMIN/STAFF/STUDENT/ANONYMOUS/null; không raw username/session/cookie |
| HTTP | `http_method,uri_path,query_string,status_code,latency_ms,user_agent,request_bytes,response_bytes` | Bounded metadata; custom method→OTHER; UA chỉ giữ product families, unknown text→[REDACTED]; path động/ID được mask; query values đều mask hoặc null; latency_ms không âm; status100–599/null |
| Loại và outcome | `event_type,outcome` | Type=http_request/flow/alert/dns/tls/other; outcome=success/failure/unknown chỉ HTTP outcome, **không là nhãn malicious/benign** |
| Flow | `flow` nullable | duration_seconds, bytes/packets_to_server/client, state; chỉ map khi source có, không tạo flow counters từ audit |
| Cấu trúc query | `query_features` nullable | length/parameter_count/percent_count/quote_count/operator_count khi đọc raw target phù hợp; không tính lại thống kê giả từ query đã mask của Student |
| Quality | `redacted,truncated` | Boolean; trường thiếu dùng null. Missing/OOD/drift vector và ML feature_version chưa được implement, không đánh dấu đã có |

Không chấp nhận raw body/header object, field bất ngờ hoặc version không tương thích. Core fields bắt buộc và network extensions optional được liệt kê chính xác trong JSON Schema. Any addition/type/meaning change phải có version mới và review cả hai luồng; ML feature vector phát triển ngoài canonical contract, không sửa v1.0 theo ý một branch.

### 2.1. Luồng hiện tại và delivery semantics

```text
Student request → trusted attribution / request ID → filter (reads configurable)
   → AuditEvent metadata → DB writer (access_logs) + private JSONL exporter
                                                ↓ STUDENT_AUDIT_LOG_PATH
Nginx structured/legacy combined ─────────→ Rust parser/normalizer
Suricata EVE alert/http/flow/other ────────→ Rust parser/normalizer
   → transaction: cursor + receipts + normalized_events (nếu bật) + alerts + jobs
   → policy/worker (OFF mặc định; TTL/deadline/protected-target checks)
```

DB và file của **producer là hai sink độc lập**, không phải atomic outbox. DB fail không ngăn thử file; file/permission/disk-limit fail được cảnh báo bằng loại lỗi/SQLSTATE, không echo secret. File write synchronized+file lock+force, owner-only directory/file, không theo symlink, mở lại mỗi append để theo rename/create. Giới hạn16KiB/line và64MiB/file; phải rotate và monitor lỗi. Crash giữa business commit và audit/file vẫn có cửa sổ mất telemetry; chưa gọi lossless/exactly-once.

Collector ACK cursor chỉ sau transaction commit. Student receipt dùng `(source,source_instance,event_id)` độc lập inode nên copied JSONL không tạo event trùng trong cửa sổ receipt. Nginx/EVE identity vẫn dựa file/inode/generation/offset/hash: copy sang inode mới có thể thành observation mới. RequestID chỉ để correlation, không xóa hai observation hợp lệ của Nginx và app.

Dòng partial bình thường giữ cursor; dòng vượt cap mặc định64KiB vào persistent discard-until-newline, quarantine theo hash/byte range (không raw secret) rồi tiếp event sau. Truncate/reset anchor tăng generation; rename/create rotation được đọc cùng file chưa nén; `.gz` chưa hỗ trợ. Không xóa/nén file trước khi đọc xong.

### 2.2. Kết nối, privacy và các cờ hiện hành

- Student: `STUDENT_AUDIT_LOG_ENABLED=true`, `STUDENT_AUDIT_LOG_PATH=./logs/student-audit.log`, `AUDIT_INCLUDE_SUCCESSFUL_READS=true` mặc định. Cần `STUDENT_AUDIT_HMAC_KEY` tối thiểu32byte và source instance ổn định; tests tắt file nếu không dùng temp path.
- Privacy producer: cả DB/JSONL Student chỉ nhận UA family từ allowlist browser/client/scanner, không giữ arbitrary prose/version/secret trong header. UA null/empty giữ đúng trạng thái thiếu; dài bị bound và bật truncated. Java/Rust chuẩn hóa custom HTTP method thành OTHER, không lưu lại token method tùy ý. Hợp đồng v1.0 vẫn giữ nguyên kiểu/trường; các report trước thay đổi này là snapshot lịch sử.
- `TRUSTED_PROXIES` nhận exact literal/CIDR. Spring auto-forwarding NONE để giữ peer gốc, custom trusted ForwardedHeaderFilter chỉ dùng địa chỉ đã kiểm tra và strip các header không tin cậy. Nginx sinh lại request ID và overwrite XFF; header giả từ client không quyết định audit/rate-limit identity.
- Security: cùng đường dẫn đã đọc được từ user chạy collector, `COLLECT_ALL_EVENTS=true` để lưu observations. Khi false, parser/rules/auth detector vẫn chạy, dataset rows không ghi và cursor vẫn advance; bật lại không tự backfill đoạn đã bỏ qua.
- Retention normalized mặc định7ngày, cap1.000.000row, sweep mỗi60s; đây không phải hard byte quota. Receipt theo cửa sổ retention, auth observation1ngày. Alerts/errors/quarantine/actions chưa có archive/retention hoàn chỉnh — OPS-04 vẫn mở. Dataset snapshot cần được xuất/version trước khi retention xóa.
- Nginx không lưu raw query, chỉ flag rule tính trong memory; legacy combined và EVE được detector đọc trước redaction khi ingest. Canonical/evidence không sao chép body/token/query value. EVE raw ở sensor vẫn cần kiểm quyền/retention và không bật payload/body dump; chưa có source-level redactor tổng quát cho phần mềm bên thứ ba.
- Không có exporter/shipper SSH/S3 tự động xuyên máy. VM/cloud tách host phải cung cấp secure mounted/shipped JSONL đúng path, giữ eventID/source_instance và file rotation contract; HTTP failover không đồng nghĩa file log tự chuyển sang Security Host.

### 2.3. Feature availability sau foundation

Có metadata HTTP/UA/session HMAC khi nguồn có; có counts/bytes/flow fields từ EVE flow, requestID giữa Student/Nginx. Chưa có body payload được phép lưu, attempted-account HMAC cho login lỗi, target ownership/role đầy đủ trên nguồn Nginx, causal ML window library hoặc incident correlation tổng quát. **Payload Byte-CNN trong03 chưa đủ đầu vào production**; phải có policy dataset riêng để thu synthetic/sanitized payload phù hợp trước khi train. Bảng feature ở phần3 giữ cả kế hoạch và ràng buộc, không phải tất cả feature đã có code.

### 2.4. API quan sát và tab Audit ứng dụng

`GET /api/application-audit` dành cho viewer/admin đã đăng nhập, trả `{items,total,limit,offset,collection}`; `GET /api/application-audit/{id}` trả metadata DB, canonical JSON đã che dữ liệu và tối đa10 quan sát khác cùng `request_id`. Không có API ghi/xóa/chỉnh nhãn ở tab này. API giữ `Cache-Control: no-store`; `/api/audit` tiếp tục là nhật ký thao tác firewall.

Filters: `from` bao gồm và `to` không bao gồm (ISO8601 instant, UI chuyển từ múi giờ trình duyệt sang UTC); `source` thuộc STUDENT_AUDIT/NGINX/SURICATA; `client_ip`, `status_code`, `request_id`, `http_method` khớp chính xác; `uri_path` tìm chuỗi con có phân biệt hoa thường trên đường dẫn đã mask. `limit` mặc định25, tối đa200; `offset`0–1000000. Sắp theo `occurred_at DESC,id DESC`; count/page dùng cùng snapshot trong một SQL statement. Các trang khác nhau là các truy vấn mới, có thể dịch chuyển nếu đồng thời nhận/xóa dữ liệu. Unknown/invalid filters trả400, ID không tồn tại trả404.

List chỉ trả summary. Detail deserialize bằng typed contract v1, validate HMAC/enum/identity và áp lại masking path/query/User-Agent trước khi trả JSON; không trả JSON tùy ý hay body/header object. Row vi phạm contract trả lỗi500 chung, không trả nội dung lỗi chứa dữ liệu thô. Bước hiển thị không sửa canonical/receipts trong DB và không thay schema v1 đã khóa.

`collection` cho biết cờ COLLECT_ALL_EVENTS, retention/cap và trạng thái watcher từng nguồn. Cờ false vẫn đọc được lịch sử; cursor vẫn chạy, nên bật lại không backfill phần đã bỏ. UI mặc định Student audit trong24giờ qua, áp bộ lọc khi submit, tải lại thủ công bằng **Tải lại audit** hoặc **Làm mới** ở header khi đang mở tab Audit; giữ filters/page và hủy request cũ khi tải lại/đổi truy vấn/rời tab. Polling5s ở header chỉ cập nhật các summary cũ, không tự refresh bảng audit. Outcome HTTP không phải nhãn attack/benign; cùng Request ID có thể có nhiều quan sát. Suricata flow thiếu requestID không được ghép chỉ vì trùng IP.

Kiểm chứng: 5 integration tests mới, tổng49 Rust PASS; 3 frontend tests cho timezone/encoding/validation PASS, build/format/clippy PASS và HTTP smoke trên demo3001 PASS. Kiểm tra giao diện bằng browser NOT_RUN do Work settings tắt Local browser use; chi tiết tại ledger06 mục14 và `APPLICATION_AUDIT_VALIDATION.json`.

## 3. Feature catalog và điều kiện sử dụng

Ký hiệu: **A** = audit DB hiện tại; **N** = raw Nginx combined hiện có cấu hình nhưng chưa xác minh runtime; **E** = raw EVE theo cấu hình; **P** = telemetry đề xuất, chưa triển khai. Feature từ N/E phải được collector lưu benign trước; alert DB không thay thế raw source.

| Feature / cửa sổ | Rule cứng | Model AI | Điều kiện và xử lý thiếu |
| --- | --- | --- | --- |
| Method, route template, status class | Method/route trái allowlist, chuỗi 401/403 | One-hot/embedding vocabulary có unknown | A có cho subset request; chuẩn hoá ID route; tránh dùng response-only feature cho quyết định trước request |
| Số login rejection/IP/60s; số 429 | Rule threshold + cooldown | Log-count, ratio theo cửa sổ | A có login; 403 có thể chỉ thiếu CSRF, 429 là limiter phản ứng. Không dùng 429 để chứng minh model nhận ra attack độc lập |
| Unique attempted accounts/IP và IP/account | Password spraying/distributed brute force | Cardinality, burst, entropy theo account | P cần HMAC tài khoản được thử; A không có failed username. Chưa có P thì tắt feature, không điền user null thành một tài khoản |
| Tần suất GET, distinct endpoint/60s, 404 ratio | Endpoint enumeration/rate-limit có context | Burstiness, interarrival CV, route entropy, rarity | A thiếu successful GET; N/P cần coverage đủ; admin mở nhiều tab là hard negative |
| Latency, response bytes, error ratio | Error storm và giới hạn tài nguyên | Log latency, rolling median/MAD, size deviation | A có latency subset; N combined không có request_time; cần N JSON/P cho latency đầy đủ. 5xx do lỗi app không tự là attack |
| User/role/session transitions, login → profile → update → logout | Truy cập role không hợp lệ/reauth cần thiết | 16–64 event sequence, transition surprise, time since auth | P; role không suy từ endpoint; current A chỉ hỗ trợ chuỗi theo user bị khuyết, không session |
| Target ID cardinality, đổi đối tượng liên tục | Enumeration/object access bất thường | Count/distinct theo actor/role | A raw path có ID; thay bằng HMAC và route template; phải phân biệt cán bộ quản lý nhiều hồ sơ hợp lệ |
| Query length, số tham số, `%`/quote/comment ratio, encoding depth | Signature SQLi/XSS/traversal có rule ID và normalization version | Byte/char n-gram hoặc char CNN trên payload view an toàn | N có target, **A không query**. Parse percent encoding bounded (ví dụ tối đa hai vòng), giữ raw/decoded views và cờ malformed; không decode vô hạn |
| POST JSON shape/type/length, tên key ngoài schema | DTO/schema rules, content-type/size limits | Structural vector; payload view ở field được phép | P; không lấy password/OTP/CCCD/name/address/bank/email body. Model chỉ thấy feature structural không thể hứa đọc nội dung đã bị xoá |
| User-agent family, referer category | Bot signals chỉ bổ trợ | UA rarity/change rate | N có combined raw; A có column nhưng writer không set, DTO không trả; UA/referer là dữ liệu attacker kiểm soát |
| Flow duration, packet/byte ratio, flags, ports | Scan/connection thresholds | MLP/anomaly cho flow riêng | E/P nếu event flow được bật và parser lưu. Không giả lập CICFlowMeter 80 feature từ audit HTTP |
| Suricata SID/category/severity | Evidence rule / policy allowlist | Chỉ làm context fusion hoặc weak label | Không dùng SID signature làm feature rồi báo kết quả model độc lập cùng rule; giữ đánh giá rule-free |
| Missingness, source lag, parse failure | Sensor health alert | Missing mask/OOD/abstain | P; dữ liệu thiếu không phải benign, source outage không phải user attack |

**Offline/online parity:** cùng implementation/version chuẩn hoá, thứ tự feature, time window, clipping và missing mask. Fit vocabulary/scaler/threshold chỉ trên train/calibration thích hợp; inference không nhìn sự kiện tương lai. Counter cập nhật trước/sau prediction phải được đặc tả nhất quán. Không đưa IP/user ID/run marker/hash trực tiếp thành feature học thuộc lab.

## 4. Thu thập dữ liệu bên ngoài — ĐỀ XUẤT

Nguồn được kiểm tra trên web ngày 26/10/2026; chưa tải file. Các nguồn sau là nguồn tác giả/đơn vị phát hành, không coi một mirror cộng đồng là ground truth.

| Nguồn chính thức | Vai trò trong project | Điều kiện trước khi dùng |
| --- | --- | --- |
| [CIC-IDS2017 — UNB](https://www.unb.ca/cic/datasets/ids-2017.html) | PCAP và labeled flow CSV cho benchmark nhánh mạng; có benign và nhiều kịch bản attack | Dùng schema feature tương thích sensor; không gộp với audit như cùng một bảng. Download chọn phần cần từ liên kết chính thức; lưu citation/terms, parser, checksum |
| [UNSW-NB15 — UNSW](https://research.unsw.edu.au/projects/unsw-nb15-dataset) | Benchmark flow bổ sung và kiểm tra domain shift | Trang cấp quyền nghiên cứu học thuật, mục đích thương mại cần thoả thuận tác giả. Chưa coi đủ quyền cho sản phẩm doanh nghiệp; bản ghi license phải có trước phát hành |
| [WebRequests — kho dữ liệu nghiên cứu Uruguay, DOI 10.60895/redata/RWUUSV](https://doi.org/10.60895/redata/RWUUSV) | Tập URI và nguồn HTTP được tác giả tập hợp; có CSIC2010, phù hợp khởi đầu payload/URI branch | Repository ghi CC BY 4.0; kiểm tra thêm provenance/terms từng thành phần và bản dữ liệu. Chọn raw URI/HTTP; không lấy TF-IDF toàn corpus đã fit để đánh giá split mới |
| CSIC2010 gốc: `https://www.isi.csic.es/dataset/` | Nguồn HTTP có thể nghiên cứu thêm | Domain gốc không truy cập được qua công cụ trong lượt khảo sát. Không mặc định link download sống/terms rõ; chỉ tiếp nhận qua nguồn có provenance kiểm chứng, nếu không bỏ khỏi baseline |

**Quy tắc domain:** public HTTP dùng để học grammar và stress-test; public flow dùng cho nhánh flow. Chất lượng thực tế của `student-web` phải đo trên traffic riêng. Không gọi public corpus cũ là đại diện 100% cho JSON API, tiếng Việt, session/CSRF hoặc TLS topology hiện tại. Không cam kết bắt zero-day chỉ vì đạt benchmark.

Quy trình tiếp nhận: ghi URL/version/ngày truy cập/terms → tải vào vùng quarantine ở giai đoạn triển khai → SHA-256 → giữ raw read-only → parse bounded/validate schema → audit missing/NaN/Inf/duplicates/label distribution → tách dataset family → split trước fit/augmentation. Dữ liệu/pickle/model bên ngoài là untrusted; không chạy script hoặc deserialise object thực thi từ gói tải về.

## 5. Sinh traffic khớp `student-web` — ĐỀ XUẤT

Không viết/chạy generator trong lượt tài liệu này. Giai đoạn triển khai dùng lab cô lập, tài khoản và hồ sơ giả, database có thể reset, SMTP sink cục bộ. Target allowlist chỉ host/IP lab; reject domain ngoài lab; giới hạn request/concurrency/duration và kill switch. Không cần hạ bảo vệ app hoặc tạo lỗ hổng thật để sinh attack attempt. Tái sử dụng kiến thức từ `security-web/scripts/lab-probes.sh`, không mặc định script hiện có đã tạo dataset có nhãn.

### 5.1. Luồng benign dựa trên endpoint có thật

1. GET `/api/auth/csrf` lấy cookie/token; POST `/api/auth/login` dạng form; refresh CSRF sau login. Giữ cookie jar riêng từng phiên; GET `/api/auth/me`.
2. STUDENT: GET `/api/me/profile`, `/api/me/completion`, `/api/me/academic`, `/api/me/academic/classmates`; PUT profile hợp lệ; CRUD `/api/me/addresses`, `/family-members`, `/emergency-contacts`, `/post-graduation-contacts` bằng dữ liệu giả đúng DTO.
3. STAFF/ADMIN: đọc/phân trang/tìm kiếm `/api/students`; CRUD danh mục `/api/faculties`, `/api/majors`, `/api/training-programs`, `/api/classes`; onboarding qua POST `/api/students`. `CreateStudentRequest` hiện không nhận MSSV: backend tự sinh mã và email trường; generator lấy ID/mã từ response.
4. ADMIN: đọc `/api/access-logs`, quản lý `/api/users` theo quyền. Không tạo hàng loạt ADMIN: code giới hạn tối đa 3 kể cả disabled/chưa kích hoạt.
5. Activation/password dùng fixture giả và mail sink: `/api/auth/activation/verify`, `/activation/send`, `/activate`, `/forgot-password`, `/reset-password`, `/change-password`; lưu token tạm trong runner memory, không trong dataset/log. Không bật gửi email thật để sinh tải.
6. POST `/api/auth/logout`; đổi cookie/session/device; think-time, idle, chuyển vai trò và giờ truy cập thay đổi có kiểm soát. UI static và tải catalog cũng cần benign telemetry proxy.

**Hard negatives bắt buộc:** người dùng gõ sai mật khẩu 1–2 lần rồi đúng; token CSRF hết hạn; login sau reset; lỗi validation phone/email/unknown field; STAFF thao tác batch trong quota; nhiều sinh viên cùng NAT; refresh/multi-tab; tên tiếng Việt và Unicode; query tìm kiếm có dấu nháy; copy/paste ký tự `%`/`_`; request retry khi mạng chậm; 404 asset do cache; 5xx do DB/SMTP lab outage. Không dán nhãn các ca này là malicious chỉ do status code.

### 5.2. Ma trận kịch bản attack attempt

| Family | Kịch bản lab | Ground truth phải ghi |
| --- | --- | --- |
| Brute force / password spraying | Burst login sai một user; nhiều user giả; nhiều IP lab; slow-rate xen benign | Ý định runner, tài khoản giả, thời gian, response; kiểm tra limiter 20/IP/endpoint/phút và forgot 5/phút; thêm guard DB 5 OTP tries/5 sends/hour |
| Enumeration / object access | STUDENT đọc admin route; đổi ID bản ghi con của fixture khác; scan endpoint không tồn tại | Expected 401/403/404 theo code; tách unauthorized attempt khỏi khai thác thành công |
| SQLi/XSS/traversal probes | Tham số URI/body field **được phép dùng trong lab**, encoding/case/comment variants và malformed encoding | Attack intent + payload family + response; test bộ detector, không yêu cầu DB bị inject. JPA binding/React escaping có thể chặn tác hại |
| Schema/validation abuse | JSON unknown keys, type mismatch, length boundaries, content-type lạ, method lạ | Attack intent tách khỏi benign validation sai; parser stage, route, observed effects |
| Workflow abuse | Lặp reset/activation, token reuse, sequence truy cập sai role, mass read qua nhiều target | Không ghi token/PII thật; xác nhận side effect ở DB test và counters trong observer riêng |
| Scan / network anomaly | Scan số port lab giới hạn; connection burst thấp, có duration cap | Sensor vantage/tuple/time; giới hạn để không gây outage; flow events cần được thu trước |
| Resilience | Restart collector, log rotate/truncate/partial line, DB tạm gián đoạn, duplicate replay, disk/queue pressure mô phỏng | Nhãn **pipeline fault**, không gán nhãn tấn công người dùng; expected cursor/duplicate/loss outcome |

Phần lớn probe có thể bị CSRF/rate limit từ chối trước khi vào controller. Để đo payload detection, runner phải có phiên/CSRF hợp lệ trong một nhóm kịch bản riêng, ghi rõ stage reached. Không gộp nhóm thiếu CSRF với nhóm detector đã nhìn payload.

### 5.3. Thiết kế chiến dịch và quy mô

- Pilot: vài nghìn request qua mọi role/endpoint quan trọng, kiểm chứng log coverage và ground truth trước khi mở rộng.
- Dataset ứng dụng đầu: đề xuất **100.000–300.000 request** tích luỹ qua nhiều lượt/ngày mô phỏng; chỉ là ngân sách thu thập, không phải số dòng hiện có hoặc điều kiện đủ chất lượng. Tăng benign/hard-negative coverage trước tăng payload lặp.
- Training có thể lấy mẫu attack để học; tập calibration/test theo stream benign áp đảo và một attack challenge set riêng. Không báo accuracy từ bộ cân bằng như hiệu năng vận hành thực.
- Thay user/session/IP lab, think-time, endpoint order, seed và lịch giữa các campaign; đổi family obfuscation để tạo holdout thật. Không chạy cùng thời điểm thu label và train trên laptop nếu vượt ngân sách tải.
- Marker như `run_id`, `pbl4_run`, scenario name và collector metadata dùng để nối nhãn; **loại khỏi input model**. Không để mọi attack có cùng UA/IP/port/time còn benign dùng giá trị khác.

## 6. Nhãn, split và chống rò rỉ

Mỗi event/window có `label_intent` (`benign`, `malicious_attempt`, `unknown`), `attack_family`, `scenario_id`, `campaign_id`, `generator_seed`, `expected_result`, `observed_result`, `label_source`, `review_status`, `label_version`. `exploit_succeeded` là thuộc tính riêng, chỉ true khi observer lab xác nhận side effect. Một 204 không đủ xác nhận exploit; một 403 không đủ xác nhận attack.

Nhãn từ rule/Suricata là **weak label**, không là ground truth độc lập; giữ phần đánh giá dùng runner manifest và review thủ công. Không huấn luyện và chấm model trên chính nhãn rule mà nó nhận làm feature. Các event không khớp runner/không đủ bằng chứng giữ `unknown`, không tự chuyển benign.

Quy trình split đề xuất:

1. Dedup exact và nhóm near-duplicate theo template/payload gốc trước split. Tất cả biến thể của cùng mẫu giữ trong cùng group.
2. Chia **theo campaign/thời gian**, khởi điểm train 60% / validation-calibration 20% / final test 20%; không chia ngẫu nhiên từng dòng trong cùng session. Tách user/session/seed theo campaign; public dataset giữ partition gốc khi benchmark và báo riêng kết quả.
3. Purge/embargo ít nhất bằng lookback window lớn nhất quanh ranh giới; không để window có request của cả train và test. Dữ liệu tương lai không được dùng để tính counter/quyết định hiện tại.
4. Giữ holdout theo họ payload/obfuscation và một đợt normal mới. Nếu rare class không đủ, báo thiếu dữ liệu thay vì nhân bản vào test.
5. Fit scaler, vocabulary, feature selection, resampling/augmentation trên train; chỉnh threshold ở validation/calibration; khoá test đến lần đánh giá cuối. Muốn đổi sau khi xem test phải version bộ test mới, giữ kết quả cũ.
6. Chấm event-level và incident/session-level riêng; bootstrap confidence interval theo campaign/session để không coi các request tương quan là mẫu độc lập. Báo precision/recall từng family, false alert/10.000 benign và false block/user hoặc NAT, cả latency và source coverage.

## 7. Bảo vệ dữ liệu và provenance

**Chính sách đề xuất:** không lưu password, OTP, activation proof/token, Cookie/JSESSIONID, Authorization/CSRF header, CCCD, tài khoản ngân hàng, hồ sơ sức khoẻ, email/name/address body trong detection dataset. HMAC user/session/target với secret ngoài Git; IP đầy đủ chỉ ở vùng vận hành cần block, tập train dùng role/network category và thống kê thay cho định danh trực tiếp. HMAC vẫn là dữ liệu cần kiểm soát, không tuyên bố đã ẩn danh tuyệt đối.

Khuyến nghị logging tham chiếu [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): ghi ngữ cảnh security phù hợp, loại secrets, kiểm soát quyền/độ toàn vẹn và xử lý input log như dữ liệu không tin cậy. Những lựa chọn dưới đây là thiết kế riêng của project, chưa phải cấu hình đã áp dụng:

- Redaction ở source/collector trước lưu bền vững, test bằng canary secret giả; cấm CR/LF/control-character injection và HTML rendering evidence không escape.
- Route/template và payload view lưu tách biệt; raw evidence hạn chế quyền, mã hoá khi lưu/chuyển, TTL ngắn có chủ sở hữu, không commit PCAP/log/DB dump vào Git. Derived features có TTL riêng đã được nhóm duyệt.
- Khởi điểm lab đề xuất raw 7 ngày, metadata chuẩn hoá 30 ngày, dataset đã lọc 90 ngày; **chưa bật**, cần căn dung lượng/mục đích và chính sách thực tế. Không tự kéo dài retention DB đang 3 ngày hoặc coi retention là nghĩa vụ pháp lý đã xác minh.
- Mọi batch có provenance/checksum/license/redaction version; quarantine sự kiện từ nguồn lạ, parser lỗi hoặc campaign chưa review. Không tự động retrain từ mọi alert để tránh poisoning và feedback loop.
- Snapshot raw/normalized/features bất biến; mọi sửa nhãn tạo version mới. Quyền export/label/release model tách người tạo và người review trong nhóm hai người.

## 8. Layout dataset và manifest — ĐỀ XUẤT, chưa tạo

```text
<data-root ngoài Git>/
  raw/<source>/<capture-id>/            # read-only, access restricted
  normalized/<schema-version>/<snapshot-id>/
  features/<feature-version>/<snapshot-id>/
  labels/<label-version>/
  splits/<split-id>/
  manifests/<dataset-version>.json
  quarantine/<reason>/<capture-id>/
```

Manifest tối thiểu: `dataset_version`, `created_at_utc`, owner/reviewer, source URL/terms/capture topology, source commit, file hashes, source timezones, schema/normalizer/redactor/feature/label versions, event/incident/class counts, missingness/duplicates/coverage report, campaign/group split IDs + hashes, cutoffs/embargo, fit-train-only assertion, known biases, retention/expiry, approval status. Training checkpoint tham chiếu đúng dataset/split/feature hash; đổi dữ liệu không resume âm thầm như cùng một run.

Chỉ lưu metadata/manifest không chứa PII trong `/docs`; dữ liệu lớn và artifact train đặt ngoài Git theo hợp đồng trong tài liệu 03. Không tạo bảng tiến độ giả: đến snapshot này `dataset_version`, số dòng train, hash split và checkpoint đều **chưa có bằng chứng**.

## 9. Tiêu chí sẵn sàng trước training đầu tiên

- Thu được benign GET và mutation/error theo coverage đã công bố; đối chiếu số request runner/proxy/app, giải thích phần lệch, không đánh đồng “không alert” với “đã ingest”.
- Có test fixture NDJSON/DB canonical cho IPv4/IPv6, Unicode, malformed URL, giới hạn độ dài, null actor, DST/timezone offset, rotation/truncation/replay và late event; chấp nhận parse lỗi có metric/quarantine.
- Canary secrets giả không xuất hiện ở raw được phép lưu, normalized data, evidence UI hay feature artifact; kiểm chứng trusted proxy/client attribution bằng request có header giả trong lab.
- Có dataset manifest và split hash; held-out campaign/near-duplicate purge; label `unknown` được giữ; review ít nhất một mẫu mỗi family và hard-negative class.
- Replay cùng capture tạo feature deterministic và decision có version; offline/online parity đạt trước khi benchmark model.
- Ghi giới hạn đã biết: payload/body chưa quan sát thì nhánh payload chưa đủ điều kiện; không quảng bá khả năng phát hiện từ dữ liệu vắng mặt. Chỉ chuyển training stage khi các điều kiện trên có evidence, theo roadmap 04.

## 10. Handoff khảo sát cũ — lịch sử, ưu tiên trạng thái hiện hành ở mục2/06

| Mục | Tiến độ đã xác minh | Việc tiếp theo |
| --- | --- | --- |
| Audit ứng dụng | Có writer DB + API ADMIN + retention, coverage một phần | Chốt canonical event, trusted proxy, GET coverage và durable export |
| `audit.log` ứng dụng | Không tìm thấy producer/file/parser trong workspace | Quyết định DB/outbox hay NDJSON; ghi ADR trước triển khai |
| Benign dataset | Chưa có capture/manifest có nhãn trong repository | Pilot lab với runner + observer tách biệt |
| Public dataset | Đã khảo sát nguồn; chưa tải | Review terms, lấy subset, checksum và feature compatibility |
| Feature pipeline | Chưa triển khai | Chốt v1 + parity fixtures + time/window contract |
| Labels/splits | Chưa có bằng chứng | Campaign manifest, weak-label segregation, split/group hash |
| AI | Chưa có bằng chứng train/checkpoint/metrics | Theo 03; không ghi giờ train tích luỹ trước khi có run ledger |

Các test backend liên quan **đã tồn tại trong code**, chưa chạy lại trong lượt khảo sát: `AuditPersistenceTests` kiểm tra commit audit mutation/login lỗi; `SecurityRequestFilterTests` kiểm tra limiter và metadata không nhận password; `AccessLogRetentionTests` kiểm tra boundary/batch. `StudentApiTests` có CSRF/RBAC/object ownership/activation/password workflows. Các suite Flyway/PostgreSQL transaction chỉ bật khi có `MIGRATION_TEST_URL`; không thể dùng sự hiện diện test để khẳng định mọi yêu cầu data pipeline đã pass.
