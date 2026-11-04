# Chuẩn bị và pilot trước train chính thức

## Post-training GLU207: kiểm chứng checkpoint và shadow không nhãn — 2026-11-04

**Candidate khóa:** research GLU207 checkpoint step652 trong [run cuối](.artifacts/research_glu207_bounded_final_20261104/run/latest.json), manifest/checkpoint/freeze SHA khớp, 9.675.784 tham số, đúng `ai-features-5`/207 cột và order trong spec SHA `3f7fe0a8c53d9aacadd5bc4e6070fb1a0f6de2b6a0f4bf208d686e83b5c1c580`; `safe_query_numeric_v2`, post-response. ONNX của chính checkpoint này parity trên train16 và nay trên shadow54 (`rtol1e-5`, `atol1e-6`, max probability abs error `1,19e-7`). Không dùng WAF content encoder/request-only để tạo 207 cột, không sửa model/threshold/checkpoint.

**Ứng viên đánh giá đã kiểm theo artifact hiện có:** (1) `prepared-v5` train/validation có 207 cột nhưng nhãn lab runner và validation đã dùng nhiều lần trong development; train đã fit candidate, test/holdout không mở. `assembled-research` cũng 207 cột nhưng tái dùng cùng source/rows từ prepared-v5, không là nguồn độc lập. (2) Capture offline `glu207_shadow_20261103/collected-54-plus-setup` có 55 requests, 54 tương quan Student/Nginx/Suricata tạo đúng 207 cột, **0 nhãn**; cùng ứng dụng/lab. (3) Các live-shadow 4/12 request cho 207 đường Python có log thật nhưng không có intent Ground Truth, cùng lab và từng được shadow; không là cohort độc lập. (4) Juice Shop factory 33 request có evidence lab cho 28 benign/4 attempts/1 unknown nhưng chỉ request-content 76+512, không có response/flow/behavior 207 đúng contract. (5) WAF v2 có `NORMAL/ANOMALOUS` publisher và 76/588 request-content views; (6) WAMM/AIT có 76 request-only và nhãn publisher/retrospective. Các nguồn (4)–(6) **không** thể padding lên GLU207; Biblio-US17 chưa có dữ liệu được cấp quyền local. **0 cohort mới** vừa có 207 causal features, nhãn intent đáng tin hai lớp, partition độc lập và quyền đánh giá; final holdout vẫn niêm phong.

[Plan khóa trước score](.artifacts/posttrain_shadow_glu207_20261104/plan.json) SHA `90da2c8b4eb2120f6b2b240b1830de363dab402ab7f5d61bc17d8b37afe824b6` cố định checkpoint, spec, capture, train reference, script SHA, `TECHNICAL_DIAGNOSTIC_ONLY`, FPR budget chính sách1% nhưng **không có threshold** cho research checkpoint. [Report private](.artifacts/posttrain_shadow_glu207_20261104/report.json) SHA `21a6a62a9cffa462288e9682d2a68faaf5602c2a6905c8bcc92901486ef5b6fb7`: **54/54 finite predictions** trên request ba nguồn offline; 1 request hai nguồn bỏ qua; **0 HTTP request mới phát**. **Overlap request ID vật lý xuyên capture chưa xác minh được** vì train và shadow dùng hai khóa HMAC khác nhau; 0 `event_key` string khớp không có giá trị chứng minh không trùng request. Có **3/54 exact float32 feature views trùng train** và 3 có nearest cosine≥0,995; cosine chỉ là tương tự vector, không là physical duplicate. Báo cáo v1 đã ghi sai ý nghĩa `event_key` và được giữ riêng để truy vết; plan/report v2 sửa phép diễn giải trước kết luận. 143/207 cột có ít nhất một giá trị khác0, 122 cột biến thiên; không đồng nhất 64 cột toàn0 với 64 feature thiếu. Prior completed flow ở train **36.443/41.607 (87,59%)**, shadow **0/54**; query-original availability0/54, status/latency/request+response bytes54/54. Đây là **feature-availability/domain shift có bằng chứng**, không tự chứng minh model dùng shortcut; chỉ một môi trường train khiến source-label shortcut chưa kiểm được.

Score **không nhãn** min0,0061/median0,1916/p95 0,9951/max0,9987; **không** gán attack/benign theo score hoặc đổi threshold. ONNX forward-only latency trên54: p50 **7,38 ms**, p95 **15,10 ms** (không gồm correlation, feature extraction, IO, load); process RSS peak **628.719.616B**, cgroup4CPU/16GiB, không chạm thermal guard. Offline replay không chứng nhận live edge/Rust parity. Recall, FPR, Precision, PR-AUC, family metrics và confidence intervals **NOT_MEASURABLE** vì 54/54 không có nhãn intent được xác minh; không có bằng chứng tổng quát hóa hoặc cải thiện model. `TRAINING_COMPLETE=true`, `TECHNICAL_INTEGRITY=PASS`, `INTERNAL_EVALUATION=INCONCLUSIVE`, `INDEPENDENT_GENERALIZATION=NOT_ESTABLISHED`, `RELEASE_READY=false`, formal admission0. Không train thêm. Bước tiếp theo có giá trị là cohort mới có cả benign/attack với request-level Ground Truth, 207 features thực quan sát, tách campaign/môi trường và calibration riêng; khóa threshold/protocol trước scoring. Xem ledger 06 mục65.

## Frozen bounded research training GLU 207 — 2026-11-04

Đã chọn **Track A** trên `prepared-v5`, chỉ dùng `split=train`: 41.607 dòng development, **41.585 unique float32 feature views**, 0 view trong train mang nhãn mâu thuẫn; 29.511 benign và 12.096 attack theo **nhãn lab/runner**, chưa phải nhãn intent được review độc lập. Quyền sử dụng là lab của dự án. [Freeze riêng tư](.artifacts/research_glu207_bounded_final_20261104/freeze.json) SHA `8286b2e384e40dacc4407d89a5cd94c8a94f0d17ddfc7d87f9851018212d2ec6` khóa dataset SHA `45ca178b494446451bfeec8e30b655044df02460ef5aa9273a93143d54cd9b08`, `ai-normalizer-5`, `ai-features-5`/207 cột, source runner SHA `a8019a4d21589fdd89e1c6ad94c9f17bea034c56ffa4722d8f0e4399f67e629a`, GLU **9.675.784** tham số, seed17, batch128, AdamW hiện có, LR0,0003 warmup30/cosine, dropout0,1, label smoothing0,02, weight decay0,0001, **2 epoch/652 updates**. Không dùng validation/test đã lộ để chọn cấu hình, early stop hoặc ngưỡng; final holdout vẫn khóa.

Hai tiến trình riêng trong cgroup `CPUQuota=400%`, `MemoryMax=16GiB`, `MemoryHigh=15GiB`, swap0 đã hoàn tất epoch1 rồi **resume thật** epoch2 từ checkpoint. Mỗi epoch đi qua đủ 41.607 dòng: **83.214 sample exposures**, vẫn chỉ 41.585 views duy nhất. Mean train loss epoch1 **0,20418**, epoch2 **0,12902**; first20 batches epoch1 **1,04380**, final20 epoch2 **0,12830**. Tổng wall **141,02s**, peak process RSS **763.199.488B** (~728MiB), peak CPU sensor **76°C**, không chạm thermal guard. Checkpoint cả hai epoch readback exact parameters+Adam; [checkpoint cuối](.artifacts/research_glu207_bounded_final_20261104/run/latest.json) global step652. ONNX từ chính checkpoint cuối đạt parity trên 16 train rows (`rtol=1e-5`, `atol=1e-6`; max probability abs error `4,66e-10`). [Report riêng tư](.artifacts/research_glu207_bounded_final_20261104/report.json) SHA `e805bc04bd956d642624b4cb2b1269ab98af415eee83a185d1e95da880ef3525`.

`RESEARCH_FIT_READY=true`, **`RESEARCH_TRAINING_COMPLETE=true`** cho Track A. `RESEARCH_EVAL_READY=false`, `FORMAL_READY=false`, formal admission **0**: loss/ONNX/chạy đủ epoch chứng minh pipeline tối ưu hóa được, **không** chứng minh Recall, FPR, phát hiện attack hay tổng quát hóa. Chưa score validation development hoặc holdout, chưa chọn champion/triển khai. `pytest` tập trung training/export/scale **18 PASS**; `py_compile` PASS; full `check.sh` **242 pytest PASS**, Ruff/format/compile/contract/Web diff PASS. Run đầu có lỗi style ở runner nên được giữ riêng với source snapshot và checkpoint làm bằng chứng; run cuối dùng source đã format, cùng dataset/seed/hyperparameter và freeze SHA riêng. Bước có giá trị tiếp theo là dữ liệu/nhãn mới và cohort đánh giá độc lập, sau đó khóa protocol trước khi score. Xem ledger 06 mục64.

## Juice Shop evidence-grounded dataset factory — 2026-11-04

Đã chạy factory AI-owned trên **một** OWASP Juice Shop image pinned, Podman rootless network `internal=true`, chỉ bind `127.0.0.1:13081`; proxy AI-owned chỉ bind `127.0.0.1:13082`. [Plan private](.artifacts/juice_gt_factory_20261104/plan.json) SHA `36a3ce43f69e2a131cdb7f090d17961d23a8f890892f3dee70ac078fbb241a2d` khóa 33 cases/8 scenario groups, request ID, URL/body SHA, oracle, image/container/code SHA, max40 và `development_only_no_model_evaluation` **trước khi campaign chạy**. Ứng dụng và proxy đều thuộc lab kiểm soát; không có traffic tấn công tới host ngoài. 33 request qua proxy, 33 proxy receipts đối chiếu request ID/method/path/body/response SHA/status với client; đây là client+AI proxy và target response, **không** là Student/Nginx/EVE hoặc app-side request-ID log.

**Application-state Oracle thật:** challenge `Login Admin` ID45 `solved=false` trước campaign và `solved=true` sau case SQLi login cuối, đồng thời login response trả danh tính admin; không lưu JWT/password. [Raw challenge/catalog snapshots private](.artifacts/juice_gt_factory_20261104/oracle-readback.json) đối chiếu SHA của response trước/sau với plan/report; [run report](.artifacts/juice_gt_factory_20261104/run/report.json) SHA `e7fd267a9a4a3d1650ab4bdb052314756304c764435ee035301ec3a9f613efc0`. Vì case SQLi duy nhất thực thi giữa hai state checks sau các benign/search case, Oracle cho phép ghi **1 `EXPLOIT_SUCCESS_VERIFIED` trong lab**. Nó chứng minh challenge của ứng dụng chuyển trạng thái và danh tính admin trả về, không chứng minh các attack khác thành công hay an toàn production.

**Nhãn request-level theo manifest đã khóa:** 33 campaign HTTP requests/33 unique complete-request representations, **28 `BENIGN_WORKFLOW_VERIFIED`**, **4 `ATTACK_ATTEMPT_VERIFIED`** (XSS, traversal, command, login SQLi), **1 UNKNOWN** (`O'Connor` hard negative HTTP500/SQL error), **1 exploit success** là subset của bốn attempt, không cộng thành request thứ 34. Product browse/search phải khớp ID/tên catalog hoặc response schema; invalid login cần 401 với thông điệp đúng; attack attempt cần precommitted case và proxy receipt/target response. Challenge state không thay review intent độc lập; một app, một run, 8 campaign IDs không phải 8 môi trường/campaign đánh giá độc lập. Setup/discovery/Oracle GET ngoài 33 case không vào corpus và chưa có tổng request vật lý toàn cục được chứng nhận.

[Curation v1](.artifacts/juice_gt_factory_20261104/curated/report.json) xác minh plan/run/code/proxy rồi loại UNKNOWN: 32 labeled rows, **20** unique 76+512 feature views, 1 view hai nhãn (invalid login benign và SQLi login attack) khiến 2 rows bị cách ly, 11 same-label view repeats, còn **19 candidate views** (16 benign/3 attack). Nguyên nhân: rich encoder cũ bỏ cả JSON body khi có `password`. Không thay encoder/checkpoint WAF cũ. [Encoder v2](src/idps_ai/features/rich_content_v2.py) thêm cú pháp JSON theo field, redacts password/token và PII email/username; trên cùng 32 rows tạo **21 unique views/0 mixed-label views**. [Corpus v2 private](.artifacts/juice_gt_factory_20261104/curated-v2/report.json) có 21 views (17 benign/4 attack), tensor chỉ numeric+hashed content, label/group/view; không lưu raw body hoặc credential. Số request vật lý vẫn 33, không biến views thành request mới. Chỉ hai tests privacy/collision mới, không mở WAF validation hoặc làm lại study.

[Quality gate reproducible](.artifacts/juice_gt_factory_20261104/quality-gates-v2.json): 21 views có 15 near-view pairs cosine≥0,995 trong content512 (0 cross-label), 4 attack family chỉ một case mỗi family, 17 benign views. Ngay nếu 0 false positives, cận trên 95% một phía cho FPR với 17 benign views vẫn **16,16%**, không thể chứng minh budget1%. Headers không được proxy lưu đủ để chứng nhận parity content live; 207 Student/Nginx/EVE features không có. `RESEARCH_FIT_READY=false`, `RESEARCH_EVAL_READY=false`, formal admitted **0**. Không tạo train/cal/eval split giả; **0 model được score/train** trên corpus này, Recall/FPR/PR-AUC `NOT_MEASURED`, không chọn champion. [Wrapper](scripts/run-juice-gt-factory.sh) đã chuẩn bị cho lượt mới: tự tạo/dừng mạng và container, khóa plan, lưu challenge/catalog snapshots, chạy campaign, curation và QA dưới resource scope, cleanup bằng trap; `bash -n` và từ chối overwrite **PASS**, **full wrapper end-to-end NOT_RUN** để không lặp cùng campaign chỉ cho thêm views gần trùng. Bước tự động tiếp theo có giá trị là thêm workflow và attack outcomes có Oracle trên **ứng dụng/môi trường lab khác được phép**, thu header/body structure đúng contract, rồi khóa split độc lập trước model score; không nhân bản 33 cases để đạt500–1.500. Container/network/proxy tạm và port13081/13082 đã dọn. [Ledger mục63](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md) ghi lệnh, SHA và test.

## Isolated Juice Shop Ground Truth pilot — 2026-11-04

Đã chạy pilot **development-only** trên OWASP Juice Shop image pinned digest `sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f`, trong Podman rootless network `internal=true`, host bind chỉ `127.0.0.1:13080`, container tối đa 2 CPU/3 GiB; không mở dịch vụ ra LAN/Internet. Ứng dụng MIT theo [repo chính thức](https://github.com/juice-shop/juice-shop), hướng dẫn chính thức cũng dùng loopback bind. `juice-gt-pilot.py prepare` đã khóa [plan private](.artifacts/juice_ground_truth_20261104/plan.json) self-hash `f6e97b4d057ba50635deea733ffb80857b3241f4e4cfcfa57e804491b4648463` trước request: 8 case, method/path/query, request ID, target container/image/network, quy tắc nhãn và `script_sha256`. `run` kiểm lại plan/code/target, rồi phát **8 request GET thật** trên cùng `/rest/products/search`; [report private](.artifacts/juice_ground_truth_20261104/run/report.json) SHA `1edc78f1afcf944662ec6ec94ef16b863a71d6497d0a67f61f332f1470e56e98`, response bytes riêng file0600, SHA và [readback](.artifacts/juice_ground_truth_20261104/runtime-readback.json) PASS. Sau pilot, container và mạng tạm đã biến mất, cổng13080 đóng; một lệnh `podman rm -f` báo lỗi quyền khi kill network process nhưng kiểm trạng thái cuối xác nhận container/network không còn, không sửa quyền host.

Kết quả theo **quy tắc đã khóa**: 3 `BENIGN_VERIFIED_LAB` (tìm kiếm apple/orange/banana, JSON success với tên sản phẩm phù hợp); 3 `ATTACK_ATTEMPT_VERIFIED_LAB` (XSS/traversal/command query được gửi tới target và nhận response hợp lệ); 2 `UNKNOWN` (hard-negative apostrophe và SQLi test đều HTTP500/SQLITE_ERROR, không đạt response Oracle đã precommit). **0 `EXPLOIT_SUCCESS_VERIFIED`** vì không có challenge/application-state Oracle; lỗi SQL, HTTP200 và payload không chứng minh exploit thành công. Có 8 unique complete-request representations/8 response snapshots, 5 campaign IDs precommitted trong **một** app/môi trường, 0 campaign đánh giá độc lập. Request ID nằm trong client request/plan; không có Student/Nginx/Suricata EVE cho lab này, nên **0 request khớp ba nguồn**. Client-response evidence xác nhận giao tiếp với target pinned; chưa có target-side request-ID log. Collector tự khóa intent nên nhãn này chỉ là **lab development Ground Truth theo thiết kế**, không là review độc lập hoặc formal admission.

Pilot **quá nhỏ và thiếu ba nguồn/207 feature** để train hay đo Recall/FPR/PR-AUC có ý nghĩa; MLP/GLU/threshold/checkpoint **không thay đổi**, 0 model được chấm trên pilot, formal admission **0**. Ngay cùng method/path, benign hard-negative dấu nháy và SQLi làm ứng dụng lỗi; đây là ca quan trọng cho quy tắc `UNKNOWN`, không được tự đổi nhãn dựa trên lỗi. Bước kế tiếp cần Oracle ứng dụng về state/challenge và capture target/proxy/EVE nếu muốn machine-verifiable exploit outcome và ba nguồn; sau đó thêm workflow/campaign độc lập thực sự, khóa partition trước fit. Không lặp hàng triệu request cùng endpoint để tăng count. [Kyoushi Zenodo](https://zenodo.org/records/5779411) nói labels chỉ gắn event liên quan attack theo rule, không nói unlabeled=benign; 2.075 dòng không nhãn của slice hiện có vẫn `UNKNOWN`, không tải lại archive hoặc gán benign. Xem ledger 06 mục62.

## HTTP Content Intelligence — cohort WAF mới — 2026-11-04

Chỉ dùng WAF Data v2 **train** đã pin SHA `3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6`, không mở publisher test/heldout. [Collision audit](.artifacts/autonomous_content_intelligence_20261104/collision-attribution-rich-v1.json) phân biệt 192 exact raw representations có hai nhãn trên toàn train với lỗi mất thông tin sau encoder. Trên 101.098 exact representations không mâu thuẫn của cohort v2 cũ, numeric76 tạo 18.237 keys/269 mixed views/77.978 rows trên mixed; safe symbolic+numeric **trước hashing** tạo 28.736 keys/243 mixed/43.167 rows; sau hashing float32 là 28.581/245/43.171. Vậy phần lớn xung đột xuất hiện trước hashing. [Rich encoder](src/idps_ai/features/rich_content.py) thêm word/digit length buckets, query/header/body structure và entropy buckets, chỉ giữ từ an ninh trong allowlist, ẩn secret/PII; không lưu plaintext hay raw-request hash trong cohort mới. Trên đúng mẫu cũ, rich+numeric sau hashing tạo **34.169 keys/241 mixed/28.174 rows trên mixed**. Các mixed view còn lại không được tự sửa nhãn; bucket cấu trúc vẫn có rủi ro fingerprint/dictionary, artifact mode 0600.

[Curation mới](.artifacts/autonomous_content_intelligence_20261104/waf-rich-v1/report.json) chọn raw SHA modulo4 residue1, không trùng raw cohort modulo16 residue0; loại thêm **311.821** selected representations có safe symbolic template từng xuất hiện ở bất kỳ raw row của cohort cũ. Trong 402.108 selected exact representations, 90.287 còn projectable sau loại template; 73 rich feature views trái nhãn/637 rows bị cách ly, same-label views dedup. Kết quả **84.193 unique numeric76+rich content512 views**; train 63.090 (45.011 `ANOMALOUS`/18.079 `NORMAL`), calibration 10.695 (7.706/2.989), validation 10.408 (7.461/2.947). 69.607 safe template groups chia role không overlap; 0 prior safe-group overlap. Đây là biểu diễn duy nhất, **không** là 84.193 physical HTTP requests đã xác minh. Residual near-template similarity, source/campaign/time lineage và bias do quarantine chưa được giải quyết.

[Plan khóa trước fit](.artifacts/autonomous_content_intelligence_20261104/study-plan-v1.json) self-hash `9b23b3c788c7e783cf2bb96e141b77ed6c1d4cd6ab5533434c61577e6a7f4650`: cùng cohort, numeric MLP 17.928 params, rich content MLP 50.696 params, method-only control; seed29, 300 updates/arm, batch128, LR0,001, ngưỡng publisher-normal calibration p99 và FPR budget1%. [Study](.artifacts/autonomous_content_intelligence_20261104/study-v1/report.json) cùng [group-bootstrap analysis](.artifacts/autonomous_content_intelligence_20261104/study-analysis-v1.json) cho validation **10.408 unique views**:

| Publisher-label internal validation | Numeric MLP | Rich content MLP | Method only |
| --- | ---: | ---: | ---: |
| `ANOMALOUS` recall | 69,24% | 75,04% | 0,71% |
| `NORMAL` FPR | 1,188% | 1,086% | 0% |
| Publisher-label PR-AUC | 0,9675 | 0,9893 | 0,7249 |

Paired 300 safe-template bootstrap: content−numeric recall +5,80 điểm phần trăm, 95% [+4,85,+6,61]; PR-AUC +0,0217, 95% [+0,0196,+0,0240]; FPR −0,102 điểm phần trăm, 95% [−0,474,+0,350], **chưa chứng minh giảm FPR**. Mỗi model thực sự tiêu thụ **38.400 distinct train views** trong pool 63.090 (10.958 normal/27.442 anomalous, permutation seed29), chưa qua toàn pool. Cả hai MLP đều vượt budget1% trên validation. POST content recall45,54% và FPR3,94% (426 anomalous/127 normal), còn yếu và cohort nhỏ. Study chỉ đo `NORMAL`/`ANOMALOUS` của publisher trên **một nguồn**; không có attack family, independent campaign, machine-verified intent hay chứng nhận khả năng phát hiện tấn công. 0 formal admitted, 0 champion, GLU 9.675.784/207 và threshold/checkpoint chính giữ nguyên. Validation mới nay đã được xem một lần, không dùng để tiếp tục tune. Full kiểm tra và lệnh chi tiết ở ledger 06 mục61.

[Near-template diagnostic](.artifacts/autonomous_content_intelligence_20261104/near-template-sample-v1.json) với seed113 lấy 2.000 validation và 10.000 train views: **580** validation views có nearest hashed-content cosine≥0,995 dù coarse group khác, **42** nearest pairs trái nhãn publisher. Similarity không chứng minh duplicate physical request, nhưng báo hiệu related-template leakage còn đáng kể; không sửa split/model sau khi xem kết quả.

## HTTP Request Intelligence — WAF Data v2 internal research — 2026-11-04

Giữ nguyên GLU chính 9.675.784/207, WAMM fit/checkpoints, QA v2, admission
policy và mọi holdout. Từ `train.parquet` WAF revision
`b035dc17f875f1f732c10654709abed66a4e9742` (MIT publisher claim),
[curator](scripts/curate-waf-content.py) kiểm lại SHA/1.924.461 rows/six fields,
exact dedup và 192 representation trái nhãn. **1.611.825** exact complete-request
representations còn lại là *ứng viên cấu trúc* cho bài toán nhãn yếu
`NORMAL`/`ANOMALOUS`, **không** là physical request đã chứng minh hoặc toàn bộ
corpus được training. Chọn mẫu cố định SHA modulo16, loại trùng exact và chỉ
xuất vector số: 101.098 exact representations được chọn. [Safe content encoder](src/idps_ai/features/safe_content.py)
chỉ giữ security lexemes/char classes/punctuation, header **names**, URL/query
sau bỏ secret keys và body symbolic; body có private-key family bị bỏ toàn bộ
nội dung. Không lưu plaintext URI/query/header value/body/PII trong corpus.
Artifact raw WAF vẫn private mode0600; không thực thi payload hoặc dùng publisher
test/heldout.

Sau mã hóa 76 numeric + 512 hashed character-ngrams, 245 feature views có
nhãn trái nhau (43.171 selected rows) được **cách ly**, same-label duplicate
views cũng loại. Bản v1 được giữ làm bằng chứng, nhưng kiểm privacy cuối phát
hiện method lạ có thể giữ plaintext. Đã sửa thành allowlist HTTP method và
tái tạo [corpus active v2](.artifacts/autonomous_http_intelligence_20261104/waf-content-v2/report.json)
SHA `82ac932add8984adecd116839f99c1735408cde8dd5c23ebc8076efa743c5b03`:
**28.336 unique numeric+content views** (19.495 anomalous/8.841 normal theo
publisher) trên 25.803 symbolic template groups. Role train/calibration/
validation lần lượt 21.247/3.528/3.561 views; cùng template không qua hai role.
Đây là internal grouped split trên **một nguồn, không có timestamp/campaign**;
near-template khác nhóm và label-selection bias vẫn còn. 76-feature numeric
views của corpus có 18.176 key duy nhất, 4.156 key trùng exact với WAMM
staging (5.628 WAF rows) theo [overlap audit v2](.artifacts/autonomous_http_intelligence_20261104/waf-wamm-numeric-overlap-v2.json)
SHA `eef49e6528bc91c0a4e1b25a54c251d3f14c033b437981993a5b7d06b7624215`;
overlap feature **không** chứng minh cùng physical request hay nhãn tương đương.
Không gộp WAMM publisher attack với WAF anomalous.

Một [plan v2 bất biến](.artifacts/autonomous_http_intelligence_20261104/plan-v2.json)
SHA file `2ddf608c5a0abab34388cd1c24e89f5ff51516b3c4651bec2ef8042def4d846d`
đã khóa trước fit: numeric `deep_mlp` 76 feature/17.928 tham số, combined
numeric+content `deep_mlp` 588 feature/50.696 tham số, mỗi arm 300 update
batch128/LR0,001/seed17, thêm method-only logistic 11 tham số làm control.
Ngưỡng lấy từ 99th percentile publisher-normal ở **calibration**, sau đó
validation chỉ được score một lần, không tune. [Study active v2](.artifacts/autonomous_http_intelligence_20261104/study-v2/report.json)
SHA `4c169f1115f6263c618e5883021585736945315cbe41cdaea1e6fe0412f2fedc`:
Đây là một lần score **trong mỗi run**; nhiều request validation trùng giữa
v1 và v2, nên cohort này đã lộ hai lần và không còn là fresh selection set.

| Internal validation, chỉ theo nhãn publisher | Numeric MLP | Content MLP | Method only |
| --- | ---: | ---: | ---: |
| `ANOMALOUS` recall | 71,60% | **78,57%** | 0,84% |
| `NORMAL` FPR | 0,680% | **1,444%** | 0% |
| Publisher-label Precision | 99,53% | 99,10% | 100% |
| Publisher-label PR-AUC | 0,9615 | **0,9912** | 0,6860 |

[Frozen-score analysis v2](.artifacts/autonomous_http_intelligence_20261104/analysis-v2.json)
SHA `7df18a83b67a67c804c4656c44dde6286f313da4dc2c757cf99bdb2ce658c289`
trên 3.561 validation views/3.261 template groups: paired group-bootstrap
95% khoảng chênh content−numeric PR-AUC **+0,0253 đến +0,0339**, recall
**+0,0561 đến +0,0864**, FPR **+0,00088 đến +0,0148**. Khoảng này chỉ đo biến
thiên mẫu nội bộ, **không** bao gồm sai nhãn/domain shift. Trên GET, content
AP0,9913 so numeric0,9610; method-only chưa giải thích hết tín hiệu, nhưng
header/body/source artifacts và chênh số tham số còn là confound. Content
validation FPR **vượt ngân sách1% đã khóa**; 43.171 rows bị lọc theo
nhãn làm cohort dễ hơn toàn nguồn. Vì vậy **không nhận content model làm
champion**, không tuyên bố attack detection tốt, independent evaluation hoặc
cải thiện production. Hai checkpoint research active ở `study-v2/numeric_mlp`
và `study-v2/content_mlp` đọc lại tham số/Adam exact; v1 giữ làm bằng chứng
cho sửa privacy, ONNX mới **NOT_RUN**.
Formal admitted **0**, machine-verified intent mới **0**. WAMM 200-update
train-only study cũ giữ nguyên, không tái fit/gộp nhãn.

`check.sh` **237 pytest PASS/0 skip/68,76s** sau sửa allowlist;
targeted privacy test **4 PASS**. Full check ghi ở ledger 06 mục60;
Ruff/format/canonical v1.0/Web
diff PASS. Công việc tự động kế tiếp có giá trị là intake nguồn HTTP mới có
benign và attack intent **request-bound trong cùng environment**, capture/
campaign/time và quyền rõ; khóa split trước bất kỳ score. WAF chỉ tiếp tục làm
weak-label research, không thay Ground Truth hoặc GLU207 formal.

## QA-to-training research execution — 2026-11-04

QA v2 nay tách `RESEARCH_FIT_READY`, `RESEARCH_EVAL_READY`, `FORMAL_READY`.
Report active private `ai-training/.artifacts/automated_quality_20261104/report-v7.json`
SHA256 `253cbad3207ca0789f2376cf15c3461f1f550edf4f8e1c700a792673287468a9`
đã chạy lại sau catalog update; plan fit trước đó pin report-v6 SHA
`9ee4f1f41c3144693fa5ebbc94cc020c32e466cfe42e6136387a9fa1704ba7f6`.
Đếm **17 check IDs** đúng bằng 6 PASS + 4 FAIL + 7 INCONCLUSIVE; câu
"16 kiểm tra" ở yêu cầu không khớp report. WAMM train-only **FIT PASS** vì
source/license/SQLite/Parquet/checksum/label mapping đã audit, 757 view xung đột
được cách ly, còn 43.287 unique float32 views hai lớp và 0 exact overlap với
development train/calibration/validation đã lộ. **EVAL FAIL** vì WAMM là dẫn
xuất SR-BH, thiếu campaign/time và near-template exclusion; **FORMAL FAIL** với
0 admitted. `raw_vector_label_consistency=FAIL` vẫn giữ nguyên cho nguồn gốc,
không biến thành PASS chỉ vì curated fit subset sạch.

Đã khóa [plan private](.artifacts/autonomous_research_20261104/wamm_fit/plan.json)
trước fit (file SHA256 `b8492c5c6d8504983abbf36561bd9f38a1afbd09b05763af1d4dd5acb1495978`;
self-hash trong plan `ca0f5d36a6c33b7f78f0477870604618a19fa21082bcd7639afba40c6d201767`).
Hai model `deep_mlp` binary-partial 76→64→8, **17.928 tham số mỗi model**,
seed17/batch128/learning rate0,001, 200 update mỗi arm/25.600 unique fit views,
không decode validation/test. Arm đối chứng xáo nhãn giữ cùng input, thứ tự,
kiến trúc và ngân sách. Train-only probe nằm **trong** fit: loss nhãn publisher
0,8156→0,0671; đối chứng xáo nhãn có loss trên nhãn publisher
0,8156→0,6384. [Report](.artifacts/autonomous_research_20261104/wamm_fit/run-v1/report.json)
SHA256 `01c00566f40eda7c1ef1945e261bebd8c287b2e01ef6bb8ca0b965c5dffc9e50`;
checkpoint riêng ở `.../run-v1/publisher/latest.json` và
`.../run-v1/shuffled_control/latest.json`, readback 200 update và SHA manifest
PASS. Kết luận giới hạn: 76 số có tín hiệu fit publisher labels hơn xáo nhãn;
không suy ra phát hiện attack, Recall/FPR, calibration hoặc tổng quát hóa.
GLU chính 9.675.784/207, checkpoint/ONNX/threshold cũ không đổi.

WAF Data v2 revision `b035dc17f875f1f732c10654709abed66a4e9742`
đã tải và audit **chỉ `train.parquet`** (MIT claim, file SHA256
`3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6`).
[Audit private](.artifacts/autonomous_research_20261104/waf_v2/audit-train-v2.json)
SHA256 `5da2e3a273702c77e367eed3f0cfa005a4477836231a180dc68d3656d605164a`:
1.924.461 publisher rows, 1.539.108 `normal`, 385.353 `anomalous`,
1.612.017 exact complete-request representations sau 1 invalid request,
312.443 dòng lặp và 192 exact representations trái nhãn. Mẫu hash 1/32 có
59.046 dòng/9.826 unique 76-feature views, 180 view trái nhãn; **không** là
full-corpus unique-view count. 77.823 body và 1.924.460 header không rỗng
nhưng encoder 76 hiện không quan sát content này. 13 HTTP methods có 5.228
`anomalous`/0 `normal`, nguy cơ shortcut theo method. Publisher mô tả
`anomalous` là suspicious/attack-like, không có request-level intent evidence,
campaign/time hay phương pháp review; giữ **WEAK_LABEL research candidate**,
không coi 385.353 là confirmed attack, không dùng split test/heldout.

Kyoushi LDS scenario1 được lấy đúng **3 ZIP members** qua HTTPS Range, kiểm CRC
member và SHA file; full 783MB ZIP chưa tải/xác minh SHA. Slice Apache intranet
có 408.477 access lines, 406.402 `attacker_http` publisher labels gắn số dòng,
2.075 dòng không nhãn **UNKNOWN**, 0 explicit benign, 406.692 unique
method+URI request lines. [Slice audit](.artifacts/autonomous_research_20261104/kyoushi_s1/slice-audit.json)
SHA256 `97ce99c060c1f06a79bd4c5bcf9096f56ad6d0b000b5c543585dd679606a381d`.
Rules nối Apache với attacker PCAP/path/time, không phải independent semantic
review cho từng intent. Nguồn testbed tổng hợp và CC BY-NC-SA 4.0 chỉ hỗ trợ
publisher-positive stress sau protocol riêng; lát cắt **không có benign** để
đo FPR. Không cộng WAF/Kyoushi rows thành physical unique requests hoặc formal
admission; không mở locked holdout. Bước dữ liệu quan trọng là tìm matched
benign+attack request-bound ở môi trường mới, có campaign/time và nhãn kiểm toán;
khóa partition trước score. Khi chưa có nguồn đó, `RESEARCH_EVAL_READY=false`,
Precision/Recall/FPR/PR-AUC cho model mới đều **INCONCLUSIVE**.

## Automated Quality Assurance — 2026-11-04

Đã thêm [research quality policy v2](configs/autonomous_research_policy_v2.yaml) giữ riêng `scale_policy.yaml`, và một lệnh [run-autonomous-quality.sh](scripts/run-autonomous-quality.sh) chạy [quality assessor](scripts/assess-autonomous-quality.py) trong cgroup 4 CPU/16 GiB. Assessor đọc lại SHA/self-hash của WAMM audit/overlap, Parquet numeric-only, exposed development train/cal/val, Oracle report, GLU207 bundle/checkpoint, ONNX và live shadow; tham chiếu `test`/sealed trong development bị từ chối. Report active private `.artifacts/automated_quality_20261104/report-v5.json` SHA `b249f80f6cf8387375758651f4f15c5265cf62434bacc5793ead5e653e1233f4`; input handoff/catalog/policy và script được snapshot riêng để tái lập. Không lấy label từ model, rule, status hoặc một bản ghi không có chứng cứ. Policy v2 đặt FPR nghiên cứu ≤1%, recall/precision/PR-AUC ≥0,8 và yêu cầu cohort độc lập đủ hai lớp; các ngưỡng này **không thay formal acceptance** và hiện chưa được áp dụng cho model vì cohort hợp lệ chưa có.

Kết quả active: `publisher_http_parsing`, class balance theo unique view, numeric staging integrity, exposed-view overlap, Oracle observation và GLU207 artifact integrity **PASS**. `raw_vector_label_consistency`, WAMM independent lineage, GLU207 input coverage từ request-only data và formal admission **FAIL**. Campaign partition, related-template/time leakage, source shortcut, nguồn hai lớp độc lập, Oracle intent, Rust/production parity và GLU207 independent quality **INCONCLUSIVE**. Research gate **FAIL** cho WAMM; model technical **PASS**, model quality **INCONCLUSIVE**, formal gate **FAIL**. Các vector đã xung đột được cách ly, nhưng WAMM còn phụ thuộc SR-BH và thiếu campaign/time. Đây là lý do không bật tự động train trên 43.287 staging views.

Đếm nhãn theo hai trục: 704.665 publisher-labeled rows, trong đó 704.649 parseable; **0 machine-verified attack/benign intent**, **0 independently verified intent**. Oracle cũ xác nhận 8 physical requests/8 ba nguồn/1 DB mutation hợp lệ, nhưng **8/8 intent UNKNOWN**. `UNKNOWN_publisher_label_rows=0` chỉ nói rằng nhà phát hành đã điền nhãn cho mọi dòng; toàn bộ intent publisher vẫn chưa được chứng nhận độc lập. Không biến label publisher thành ground truth formal.

Kiểm kỹ thuật GLU: manifest và mọi file bundle/checkpoint khớp SHA, ONNX pilot parity lịch sử 69.345 rows, CPU smoke vector số 207 chiều hữu hạn; phép đo smoke chỉ đo ONNX trên vector zero và không là latency HTTP. Live shadow lab trước đó 4/4 request đủ ba nguồn, 0 packet drop, p95 end-to-end 218,06 ms trên n=4; Rust edge/production parity vẫn chưa đo. Precision/Recall/FPR/PR-AUC mới đều `null`, **0 optimizer update/checkpoint/ONNX mới**, không có cải thiện so với baseline được chứng minh. Giả thuyết được giữ cho vòng có dữ liệu mới: 76 request-only feature gộp nhiều nội dung HTTP khác nhãn; 15.872 dòng là minority-label floor trên nguồn WAMM hiện tại, không phải metric model hoặc nhãn được xác minh.

## Autonomous public-data intake — 2026-11-03T21:07+07:00

Đã lấy bản WAMM `DS_Augmented_v2` từ revision GitHub `2783eab560c4355f5976a57fc2e97a2e6c5c79a1`, lưu raw SQLite nén/giải nén cùng README và LICENSE trong `.artifacts/autonomous_research_20261103/wamm/` (private). SHA256 SQLite `c692dcdebaf9984dff49ad01f1c21964c8a83ebe1c426bd12e26f9bff9ce335d`, `quick_check=ok`; archive `2631c31b8f4bdc389365274e6f22d9753534ef1e2eab52f3d1fd20c4f6bc65c9`. Giấy phép repo CC BY 4.0 yêu cầu attribution. Script [audit](scripts/audit-wamm-research.py) pin checksum/schema/license, parse request line chỉ trong bộ nhớ và xuất 76 số float32; [lọc overlap](scripts/filter-request-view-overlap.py) so với đúng train/calibration/validation development đã lộ, không đọc sealed/test. Báo cáo bất biến `audit-v4.json` SHA `3fd155f90e475e844ea03b7e8330a1e77a22c85f2b99ee8b699c13706f5056df`; `overlap-v2.json` SHA `adf6b46d7eea7730bf019a1cd7f1968c26b741be0512e8ffa09eec38d45d77c8`.

| Đơn vị kiểm đếm | Kết quả |
| --- | ---: |
| Dòng publisher / parseable HTTP representations | 704.665 / 704.649 (16 request line lỗi) |
| Nhãn publisher trên dòng parseable | 493.513 normal / 211.136 attack |
| Biểu diễn HTTP text khác nhau / dòng lặp text | 312.241 / 392.408 |
| Exact float32 76-feature views / dòng lặp vector | 67.620 / 637.029 |
| Views mang cả hai nhãn / số dòng thuộc các view đó | 757 / 448.231; minority-label tối thiểu 15.872 dòng (2,25% parseable) |
| Views không xung đột, lưu numeric-only | 66.863 (25.073 benign, 41.790 attack theo publisher) |
| Views trùng development đã lộ / views còn lại sau lọc | 23.576 / **43.287** (14.242 benign, 29.045 attack theo publisher) |
| Physical requests chứng minh / machine-verified intent / independent intent / formal admitted | **0 / 0 / 0 / 0** |

43.287 là **biểu diễn numeric staging**, không phải request mới hoặc corpus có partition. WAMM phái sinh SR-BH2020, có Burp mutation và lọc nhãn bằng regex/LLM/expert sample; row không có campaign, timestamp hoặc lineage đủ để tách train/calibration/validation và đánh giá nguồn độc lập. Một số số lượng attack family trong README không khớp SQLite thật. Bỏ exact vector overlap vẫn chưa loại near-duplicate hay phụ thuộc template; 757 vector trái nhãn chứng minh profile 76 cột mất tín hiệu phân biệt trong nhiều trường hợp. Các request có body/headers không được bịa thành input 207; model GLU 207 và checkpoint giữ nguyên. Theo [research policy v1](configs/autonomous_research_policy_v1.yaml), **numeric staging sẵn**, `AUTONOMOUS_RESEARCH_READY=false`, `FORMAL_READY=false`; không chạy pilot/train hoặc công bố metric vì chưa có partition/acceptance hai lớp hợp lệ.

WAF Data v2 chỉ kiểm card/API và giữ metadata-only: `anomalous` không tự đồng nghĩa attack intent. Kyoushi LDS scenario 1 là ứng viên tiếp theo từ Zenodo: công bố Apache access log gắn nhãn theo dòng và attacker scenario log, giấy phép CC BY-NC-SA 4.0, archive 783 MB. Lượt thử tải dừng sớm vì tốc độ ~0,26 MB/s, còn bản `.partial` không được dùng làm dataset; **0 dòng Kyoushi đã audit**. Cần xác minh quan hệ với AIT development và nhãn/lineage từng dòng trước khi dùng. Biblio-US17 trở thành tùy chọn, không là điều kiện chặn nghiên cứu. Không nguồn mới nào hiện tạo được evaluation độc lập hay cho phép thay formal gate.

**Bước có tác động lớn nhất:** lấy một nguồn HTTP công khai có *hai lớp trong cùng campaign*, request-level label/clock/group evidence và quyền phù hợp, rồi khóa split/acceptance trước khi fit. Kyoushi có cấu trúc hứa hẹn nhưng chỉ khi tải/kiểm được archive và kiểm độc lập với AIT; nếu không, tiếp tục sàng lọc nguồn khác. Không dùng một source/lab hoặc nhãn publisher để tuyên bố tổng quát hóa production.

## Data unblock: gói gửi quyền, review và study mới — 2026-11-03

**Trạng thái chốt:** Không train thêm trong lượt này. GLU 9.675.784/207 đã đủ bằng chứng *kỹ thuật pilot* để fit, checkpoint/readback và shadow trong lab; research run 100 update chỉ kiểm optimizer. Chưa có đánh giá độc lập về Recall/FPR; formal admission **0**. 118.760 development vectors và 41.607 prepared-v5 train rows không phải request mới có nhãn độc lập. Giữ mọi checkpoint, model, threshold, partition, holdout và gate. Việc thiếu hiện nay là **quyền dữ liệu và semantic Ground Truth**, không phải thêm epoch.

**Hai gói có thể chuyển ngay:** Email tiếng Anh hoàn chỉnh cho chủ Biblio ở [mục xin quyền](#phương-án-truy-cập-biblio-us17-và-nội-dung-xin-quyền-sẵn-dùng); [gói reviewer private](.artifacts/ground_truth_pilot_20261102/APPROVAL_PACKAGE.md) có plan-v3 ký *trước capture*, 8 request Oracle development đã chạy, request ID/ledger hash, giới hạn sự thật Oracle và lệnh review hiện có. Không gửi PCAP, credential hoặc khóa riêng qua email/chat. `plan-v3` readback với code hiện hành **PASS**; ba nguồn review cũ `two_source`, `eve_first`, `eve_novel` reverify **54/54 mỗi nguồn**. `devgt1` 8 request có report/queue còn nguyên hash, nhưng re-verifier hiện hành từ chối vì plan pin collector SHA `38bad2…` và code hiện tại `30c5ee…`; không bỏ qua check, không promote 8 nhãn. Người review có thể xem facts cũ và ký prospective plan-v3, còn formal dùng capture mới sau approval thật.

**Mốc dữ liệu quản lý, không thay scale gate:**

| Mốc | Chất lượng và nguồn | Quyền, nhãn, phạm vi dùng | Admission còn thiếu |
| --- | --- | --- | --- |
| G0 — quyền và schema | Biblio RAW+LABEL+README/terms từ chủ dữ liệu; kiểm mẫu tối đa 1.000 RID để xác lập parser/join, không tính mẫu như request mới độc lập nếu trùng | Chỉ đọc sau grant; giữ raw private, ghi checksum/provenance và nhãn S2/S3 đúng phạm vi | Chưa đủ quyền, không có ba nguồn/207, chưa review theo gate dự án |
| G1 — research hai lớp | Mục tiêu quản lý đầu tiên: ≥1.000 request có khóa nhận dạng `(ngày, RID)` hoặc khóa publisher xác nhận **và** không trùng request vật lý, có nhãn request-bound kiểm được, từ Biblio và ít nhất một source/campaign hai lớp độc lập; đếm riêng exact float32 views, family, missingness | Chỉ fit request-only khi quyền cho phép, mỗi source×train/cal/val×class có ≥32 request và ≥32 views; nhãn yếu/UNKNOWN cách ly | Nghiên cứu ≠ formal; cần môi trường/ba nguồn và evidence-v2 |
| G2 — đa môi trường | Mở rộng theo số request vật lý được chứng minh và unique views, ưu tiên các application/campaign/ngày khác nhau, benign/hard negatives/attack; chỉ đặt mốc 100.000 khi provenance/nhãn giữ được | Mỗi nguồn có điều khoản riêng; reviewer độc lập hoặc publisher evidence được audit; khóa source/campaign/time split trước scores | Chưa mặc định đủ family, 95% ba nguồn hay 120 campaign |
| G3 — formal scale | **2.000.000 admitted**, ≥3 environment, ≥7 ngày, ≥120 campaign, ≥95% ghép ba nguồn, coverage lớp/family/partition và embargo300s đúng `scale_policy.yaml` | Evidence-v2 độc lập, rights cho feature/model, profile `safe_query_numeric_v2`/`ai-features-5`; independent acceptance chưa dùng tuning | Chỉ khi toàn bộ gate PASS mới formal train; mục tiêu số lượng không thay điều kiện chất lượng |

**Protocol study tiếp theo — chuẩn bị, chưa kích hoạt:** Chỉ bắt đầu sau G1 và một acceptance cohort/source chưa từng dùng để chọn cấu hình. Khóa nguồn/phiên bản/checksum, label basis, tập train/calibration/validation và acceptance, dedup RID và exact float32 views giữa partition, tách source/campaign/actor khi có, embargo300s chỉ khi timestamp thật. Ngân sách FPR **1%**, lấy ngưỡng chỉ trên benign calibration theo `experiment_plan.yaml`, tuyệt đối không tuning bằng acceptance/holdout. So MLP và GLU cùng một tập input khả dụng, cùng partition và ngân sách update; báo cáo request-level và unique-view Precision, Recall, FPR, PR-AUC, family/source/campaign và latency. Nếu dữ liệu chỉ có METHOD/URI, dùng cấu hình request-only 76 feature và **không** gọi kết quả đó là GLU chính 207; 207 chỉ tham gia khi đầy đủ tín hiệu ba nguồn đúng thời điểm. Một source/lab hai lớp chưa tạo bằng chứng tổng quát hóa đa môi trường. Không đổi threshold/model hiện tại và không mở sealed holdout.

## Research GLU 207 train-only: kiểm độ ổn định tối ưu hóa — 2026-11-03

Đã khóa [plan private](.artifacts/research_glu207_stability_20261103/plan.json) SHA `75df365788d1dca5bddf4b62ee8d5290b3e4d306f2312b0fd7dccff280447dcc` trước optimizer, dùng prepared-v5 SHA `45ca178b494446451bfeec8e30b655044df02460ef5aa9273a93143d54cd9b08`, spec `ai-features-5`/207 cột SHA `3f7fe0a8c53d9aacadd5bc4e6070fb1a0f4bf208d686e83b5c1c580`, GLU **9.675.784** tham số, seed17. Câu hỏi duy nhất: code hiện tại có thể tối ưu GLU 207 trên train development với loss/gradient hữu hạn và không cần validation/test hay không? Old GLU pilot checkpoint đã có 652 update và exact resume trên source snapshot cũ; implementation hash hiện đổi nên **không force-resume** checkpoint đó, không chạy lại study sampler hoặc tune threshold.

Toàn prepared-v5 có **41.607 train rows**, nhãn lab/runner 29.511 benign và 12.096 attack, 27 groups trong một lab; **41.585 exact float32 views** toàn train. Preflight đếm toàn train đã đọc row group ranh giới chứa cả 377 validation rows; chỉ dùng chúng để xác định split, không score/tune. **Run optimizer** chỉ đọc **81 Parquet row groups hoàn toàn thuộc train** (41.472 rows, 41.450 views), bỏ 135 train rows nằm chung row group với validation; run không decode validation/test. Một permutation seed17 lấy 100 batch ×128 = **12.800 train rows khác nhau / 12.798 unique views**; sampled 9.042 benign/3.758 attack theo nhãn development. Không lấy observations làm request mới.

Run trong systemd user scope hard `CPUQuota=400%`, `MemoryMax=16GiB`, `MemoryHigh=15GiB`, swap0 và Python `resource_envelope(4,16)`: **100/100 updates PASS, 23,14s**, peak process RSS **872,7MB**, nhiệt sample max69°C. Loss trên cùng một probe train 128 dòng **1,4991→0,1857**; gradient L2 **22,10→0,8504**, 10 batch diagnostics hữu hạn, median **1,046**, max **8,380**, 7/10 nằm trên ngưỡng clip1. Checkpoint mới riêng ở [run/latest.json](.artifacts/research_glu207_stability_20261103/run/latest.json), readback tham số+Adam exact; [report private](.artifacts/research_glu207_stability_20261103/report.json) SHA `e8d811cc4450b909771335f247e9cf1bb3fe84c098f328afea9330d13ab22639`. **Không chạy resume mới hoặc ONNX export** vì đây là phép đo train-only; checkpoint subset này không phải continuation của launcher full-dataset. Bằng chứng exact resume/ONNX pilot cũ giữ riêng. Loss giảm và gradient hữu hạn chỉ là **optimization sanity**, không phải Recall/FPR, chất lượng nhãn hay khả năng tổng quát hóa; không dùng validation lộ để chọn model.

**Data track song song:** Biblio-US17 vẫn pending legitimate RAW+LABEL+README. Sàng lọc metadata [WebSpotter paper](https://www.ndss-symposium.org/ndss-paper/achieving-interpretable-dl-based-web-attack-detection-through-malicious-payload-localization/) và [repo MIT](https://github.com/Sec-AI-research/WebSpotter): FPAD có benign từ CSIC và attack do ghép payload/Burp Bounty; CVE có payload attack được tác giả annotate, nhưng thiếu matched benign request-level từ cùng capture. Đây có thể là attack stress research sau kiểm dữ liệu/quyền, **0 physical requests/labels mới locally verified, 0 research-training rows mới, 0 formal admitted**. Không tải archive hoặc audit lại nguồn cũ. Nguồn benign thực WCP/Polish vẫn thiếu positive; không trộn hai nguồn theo class để tạo shortcut. Đường thực tế: owner xin quyền Biblio; song song reviewer độc lập xem/ký plan Oracle hiện có cho capture ba nguồn trên ứng dụng/môi trường được cấp phép khác, bind request/response/oracle/intent ngay lúc thu. Không dùng status/rule/runner để tự cấp nhãn.

**Formal readiness giữ nguyên:** `scale_policy.yaml` đòi 2M admitted, ≥3 môi trường, ≥7 ngày, ≥120 campaign, ≥95% ba nguồn, confidence≥0,9, family/partition coverage, embargo300s và evidence-v2 independent review. Hiện formal0, một lab, không có independent acceptance; research checkpoint trên không thay đổi gate. GLU207 kỹ thuật nhận feature/train được, nhưng live DB→AI receipt-time và chất lượng/tổng quát hóa chưa nghiệm thu. Tiếp theo ưu tiên **Ground Truth request-bound và môi trường độc lập**, không thêm optimizer study trên validation đã lộ.

## Quyết định kiến trúc Security edge → Python AI — 2026-11-03

**Python là encoder/inference backend cho GLU 207; không cần thêm encoder Rust.** `readers.py` đã hỗ trợ canonical v1 và `postgres-export`; kiểm lại trên **5 Student canonical events thật** của capture live đã lưu: bọc thành `{id,canonical}` rồi đọc lại bằng adapter cho 5/5 normalized records bằng exact với đường Student trực tiếp. Contract tests cùng query numeric/shadow **22 PASS**. Không có Security DB/export `normalized_events` đang chạy để so trực tiếp Rust canonical Nginx/SURICATA, nên đây là parity của adapter Student, **không** là parity edge hoàn chỉnh.

Ranh giới dữ liệu được xác minh từ live EVE hiện có: **4/4** HTTP records mang `X-Request-Id` trong `response_headers`, **0/4** có `http.request_id` trực tiếp; **4/4** có AI numeric v2; **36/36** flow records có `start/end`. Rust `events.rs` chỉ lấy `http.request_id`, lưu 5 `query_features` cơ bản, mask target và không giữ `flow.start/end`; DB có `observed_at` ngoài canonical nhưng adapter hiện chưa dùng receipt-time. Vì vậy **Rust canonical ba nguồn một mình không đủ** để ghép 4 request theo ID, tái tạo numeric v2/41 structure values hoặc xác nhận prior-flow timing. Không đoán ID bằng IP/thời gian, không phục hồi query đã mask, không gán 0 cho giá trị thiếu để ép score.

Đường tích hợp AI khả thi, chưa kiểm live end-to-end: export **chỉ Student+Nginx canonical** bằng quyền DB read-only, ghép với **EVE AI numeric v2** nhận trước mask trong sidecar, dùng collector hiện có rồi `InferencePipeline` sau response. Runbook và lệnh offline ở [README](README.md). Nginx capture có ID/latency/request+response bytes **5/5**; status nằm ở trường `status` (Rust parser ánh xạ được). Python v5 vẫn từ chối request thiếu source/ID/bytes/numeric, input trùng và event đến ngược thời gian. Live 12/12 ba nguồn từ các probe trước dùng native log, **không** chứng nhận DB-export→AI sidecar, receipt-time/timeout qua restart, TLS hay production. Để nghiệm thu đường DB cần một export thực đã được cấp quyền đọc kèm `observed_at`, raw EVE sidecar cùng request ID, và phép so giá trị/timing với native capture; nếu không có, giữ trạng thái `NOT_VERIFIED` và không phát thêm campaign giống cũ.

**Dữ liệu/nhãn:** Biblio-US17 vẫn không có RAW+LABEL+README được cấp quyền local; pilot Oracle 8 request là development, intent chưa được reviewer độc lập phê duyệt. Không có nhãn mới cho research study tổng quát hóa hoặc formal admission. `forward-development-v2` 118.760 vectors chỉ phục vụ nghiên cứu nội bộ trên 76 feature; riêng selected train pool có **27.142 exact float32 views khác nhau**, không phải số unique của toàn corpus hay của GLU 207. Report tổng lab 75.360 request chưa global dedup; riêng 207 live probe sau đó có 16 target GET và 4 readiness, không tự cộng vào unique toàn cục. **Số request vật lý duy nhất toàn bộ dự án và số unique 207 views toàn cục chưa được chứng nhận**; số nhãn intent độc lập mới 0/0; formal **0/2.000.000**. Research tiếp theo cần hai nguồn/campaign hai lớp có nhãn request-bound và split/unique-view gate; formal GLU cần thêm dữ liệu ba nguồn, nhãn review độc lập, nhiều môi trường và evaluation chưa dùng để tuning. Hành động bên ngoài ngắn nhất vẫn là [request-a-copy Biblio](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361) theo mẫu bên dưới; với Oracle, reviewer thực sự độc lập phải ký/phê duyệt plan và xác nhận intent theo protocol, không thể thay bằng máy.

## Edge parity và fault replay trên capture live đã có — 2026-11-03T17:51+07:00

Đọc đường Rust hiện có ở `security-web/src/events.rs`, `src/ingest.rs` và `Cargo.toml` (chỉ đọc): Rust nhận/lưu canonical observations và tính 5 thống kê query cơ bản trước khi mask; **chưa có encoder 207 cột, ONNX runtime hoặc đường prediction tại edge**. Do đó không có hai vector độc lập để so; Python training→Python inference đã khớp 512/512 persisted train rows và 4/4 live rows ở các phép trước, nhưng **Rust/edge parity = NOT_VERIFIED**. Không sửa hai Web để ép parity. Chỉ có thể dựa trên thông tin Student/Nginx/EVE quan sát sau response; không chứng nhận TLS/clock/receipt-time ở môi trường khác.

Fault replay AI-only dùng lại ba tệp log của lượt `live_shadow_20261103_v2` (4 target GET, không gửi HTTP mới), giữ SHA đầu vào trong `ai-training/.artifacts/live_fault_replay_20261103_v2/fault-report.json`. Snapshot thiếu EVE bị từ chối trước ONNX; snapshot về sau có EVE chỉ chứng minh availability, **không** hồi tố chấm điểm sau timeout trong replay. Exact duplicate của một Nginx line bị collector dedup và vector vẫn bằng baseline; một line khác payload cùng request ID làm correlation ambiguous và bị từ chối. Đảo thứ tự các dòng nguồn vẫn tạo đúng vector khi collector sắp theo timestamp; đẩy fused request cũ vào inference sau request mới bị từ chối. Trước sửa, dispatcher đưa lại cùng fused request được score lần hai và cập nhật history; `InferencePipeline` v5 giờ từ chối `request_key` trùng **trước** extractor/ONNX. Replay lại: tất cả guard trên PASS; 2 request đầu thiếu prior completed flow, 2 request sau có flow đúng thời điểm. Không có hành động firewall.

Giới hạn: EVE đến muộn là fault injection bằng staged snapshot, không phải packet trễ tự nhiên; chính replay driver quyết định không gọi scorer lại sau timeout, chưa có durable live scheduler/timeout ledger. Bộ nhớ dedup của Python tồn tại trong một process, chưa bền qua restart hay được đo endurance. **Live shadow lab có bằng chứng kỹ thuật 12/12 ở ba probe tốt; chưa đủ căn cứ tuyên bố vận hành ổn định ở edge/production.** Formal admission vẫn 0; không có nhãn độc lập, research study mới không chạy. Biblio-US17 chưa có grant RAW+LABEL+README ở workspace; không gọi lại endpoint nội dung từng trả 401. Bước cần người sở hữu dữ liệu thực hiện: dùng mẫu request-a-copy bên dưới, cung cấp quyền RAW+LABEL+README/điều khoản; reviewer độc lập phải xác nhận nhãn intent theo protocol hiện có. Nguồn Biblio chỉ có thể giúp study **request-only** sau audit, không tự cung cấp 207 feature/ba nguồn; formal GLU còn cần dữ liệu ba nguồn từ môi trường độc lập, nhãn intent được review, split và acceptance đạt gate.

## GLU 207: live three-source shadow trên lab cô lập — 2026-11-03T16:22+07:00

Đã dùng `ai-training/scripts/live-shadow-lab.py` dựng lab AI-owned tạm với Nginx/Student và **Suricata bắt trực tiếp `lo` trong network namespace riêng**, không decode PCAP sau khi gửi request. Chỉ gửi GET vô hại `/api/auth/csrf` và `/api/faculties` để đo timing, không tạo campaign attack/nhãn, không gọi firewall. Bốn lượt kỹ thuật, mỗi lượt 4 request mục tiêu và 1 readiness setup: lượt đầu cấu hình AF_PACKET mặc định mất **100/240 packet (41,67%)**, chỉ **2/4** request khớp ba nguồn/được score, hai request thiếu EVE được bỏ qua có lý do. Sau khi cấu hình ring `lo` 4096 packet (Suricata single runmode thực tế chuyển tpacket v3 về v2), lượt có khoảng chờ 67s đạt **4/4**, **0/208 drop**; lượt ngắn đo tài nguyên đạt **4/4**, **0/80 drop**. Lượt query vô hại có numeric v2 khớp target 4/4 trước inference và 0/80 drop. Tổng 16 target GET phát thật, 14/16 ba nguồn và shadow inference, 2/16 skip, 0 action chặn. Mỗi request đạt đủ nguồn có một observation Student, một Nginx, một EVE HTTP cùng request ID; không thấy duplicate trong 12 request của ba lượt không drop. Lab DB/process/cổng đã dọn.

Lượt 67s cho thấy 2 request đầu **không** có prior completed flow, 2 request sau **có** flow đã phát và qua `flow.end+65s`; bằng chứng này ủng hộ nguyên nhân capture 11,34s quá ngắn, không chứng minh mọi môi trường sẽ có prior flow. Vẫn thiếu 5 original-query metrics trên cả 4 request, nên **197/207 cột giá trị có nguồn** ở hai request đầu, **202/207** ở hai request sau; 207/207 input hữu hạn và 4/4 vector khớp exact giữa collector/reference và inference **cùng Python**. Sáu cờ context-incomplete bật ở hai request đầu, bốn cờ ở hai request sau. Không backfill flow hiện tại hoặc dùng EVE chưa nhận. Train v5 có flow 36.443/41.607, nên sự khác biệt về lịch sử thời gian và query vẫn là domain shift cần kiểm soát.

Trên lượt không drop, EVE HTTP xuất hiện trong **16,7–35,0ms** từ lúc client gửi; không có EVE quá hạn 12s. Lượt ngắn: end-to-end từ client send → đủ ba log → Python collect → feature+ONNX p50/p95/p99 **193,18/218,06/221,13ms** (n=4); riêng feature+ONNX **6,69–7,97ms**. Throughput quan sát trong phép thử tuần tự **5,03 request/s**, không phải công suất tối đa. Bốn process AI worker/Nginx/Suricata/Student có peak RSS mẫu **1,318GB**, PostgreSQL container giới hạn thêm 512MiB nhưng không nằm trong mẫu; CPU trung bình **0,327 core** trong 0,795s, affinity 8 CPU. Mẫu rất nhỏ, loopback và snapshot collector đọc file lại mỗi request; không là SLA production. Hai source order có thể khác nhau, collector chờ đủ ba nguồn; khi EVE mất, request được ghi `skip_reason` và không dự đoán. Không kiểm được nhánh EVE đến rất muộn mà cuối cùng vẫn xuất hiện. Rust Security Web chưa có đường inference 207 được kiểm trong phép này, TLS/edge khác lab và parity production vẫn **NOT_VERIFIED**.

Bằng chứng private/ignored: `live_shadow_20261103/live-report.json` SHA `24f24e022d7010698e088218a9aff076baaf6aaf8e6f035636f803440d81bbc7` (lượt mất gói), `live_shadow_20261103_v2/live-report.json` SHA `16711ba965d6bfc9b2b4b4ad1bf5cd888aa2626819648d3ddbf62bc804b1e143` và `feature-parity-aggregate.json` SHA `ada369e9b1fa315dbe2f343cd10b7296cb75e78b3238035eff933e3f4dc5c149`, `live_shadow_20261103_resource/live-report.json` SHA `12db7446e1a892569718b8b5b5c3a7d1dd6fc72b68ce742e283ca02cf79f713b`, probe query SHA `6297e030a851f21b51efa8ea5b36722c92bd2e4dcb59c66b45dbae535439055c`. Chỉ báo cáo aggregate, không dùng nhãn hoặc score để đo Recall/FPR. GLU 9.675.784/207, bốn checkpoint research, sampler, threshold, gate, holdout giữ nguyên. **0 request formal admitted**, Biblio-US17 vẫn chờ quyền; ưu tiên tiếp theo là nhãn intent độc lập/campaign-môi trường mới và parity của đường edge inference thật, trước mọi formal training.

## GLU 207 feature: đối chiếu capture ba nguồn và shadow offline — 2026-11-03T09:31+07:00

Đã **khóa** bốn checkpoint và kết quả study sampler 76 cột ở mục ngay dưới: không promote sampler, fit thêm epoch, đổi ngưỡng hoặc dùng validation development làm tập đánh giá độc lập. Model chính `residual_glu` **9.675.784 tham số / 207 cột** và bundle cũ giữ nguyên. Lượt này chỉ dùng capture development AI-owned `eve3-1102c` có packet thật, Suricata đọc **PCAP offline**. Collector `safe_query_numeric_v2` tạo **237 observations → 55 fused requests**: **54/54 request mục tiêu** khớp Student audit + Nginx + EVE theo request ID; request setup còn lại chỉ có hai nguồn và bị loại khỏi prediction. Không gửi request mới, không đọc holdout hoặc dùng nhãn.

**Đếm availability trên 54 request:** extractor phát ra **207/207 số hữu hạn**, nhưng chỉ **197 cột giá trị có nguồn quan sát tương ứng** tại lần quyết định post-response: năm giá trị flow từ completed flow quá khứ và năm chỉ số query gốc đã che đều không có; các cờ `*_missing`/`*_available` vẫn được ghi đúng. **122/207 cột thay đổi giá trị** trong capture ngắn này; 0 variance ở cột khác không đồng nghĩa lỗi hay thiếu dữ liệu. URI/query numeric v2, status, latency, request/response bytes có ở **54/54**; `user_key` có **51/54**. Flow hoàn tất đã có tại thời điểm request là **0/54**, trong khi train v5 có **36.443/41.607**; sáu cờ `ip/user × 10/60/300s_context_incomplete` đều bật **54/54** vì capture mục tiêu chỉ trải **11,34 giây**. UA ở capture chỉ có Firefox/Mozilla, còn train có nhiều họ UA. Đây là **visibility/domain shortcut risk**, chưa chứng minh model học shortcut theo nhãn hoặc có leakage thực tế.

**Thời điểm hợp lệ:** spec v5 đặt `inference_stage=post_response`. Status/latency/response size và các error ratio/auth streak dùng status của request hiện tại, nên không được tạo prediction 207 trước response. Flow chỉ lấy record cũ đã phát với `available_at <= timestamp` và lookback 300s; flow của request hiện tại phát muộn tối đa **11,34s** trong capture này, không được backfill. Behavior 10/60/300s gồm request hiện tại và quá khứ, không dùng tương lai. Query numeric v2 được project từ EVE trước redaction trên **đường PCAP offline**, chưa chứng nhận live edge/receipt-time hoặc TLS visibility.

**Lỗi kỹ thuật đã sửa:** `InferencePipeline.observe` trước đây vẫn score request setup chỉ có Student+Nginx. Với profile v5, giờ từ chối trước model nếu ba nguồn không khớp request ID, thiếu status/latency/request/response bytes sau response, hoặc thiếu bridge numeric v2 bắt buộc. Flow và `user_key` vẫn có thể thiếu theo cờ hiện có. Thử trực tiếp request setup: trước sửa **1 prediction**, sau sửa **0**; 54 request đầy đủ vẫn cho **54 output hữu hạn**, không hành động chặn. Kiểm vector train v5 **512/512 rows × 207 chiều** khớp exact giữa persisted feature và `InferencePipeline`; trên capture mới **54/54** vector khớp giữa hai đường **cùng implementation Python**. Đó là parity offline, không phải kiểm chứng độc lập Rust/live edge.

Shadow 54 request trên **4 logical CPU affinity**, giới hạn RAM 16 GiB: Python feature extraction + ONNX p50 **6,76ms**, p95 **7,11ms**, p99 **7,48ms**, model load **208,47ms**, peak process RSS **322,72MB**. Mẫu nhỏ, không gồm thời gian đợi log, correlation, sensor hoặc network; không suy ra latency production. [Báo cáo tổng hợp](reports/ATTACK_EVIDENCE_20261101.json) trỏ đến private plan/report SHA, collector snapshot và phép kiểm train parity; report riêng tư không chứa score từng request, URI/IP/body/user hay label. `pytest` AI **227 PASS / 1 SKIPPED**, Ruff lint/format PASS, Web diff PASS. Formal admission **0/2.000.000**, Biblio-US17 vẫn chờ quyền.

**Hai đường tiếp theo:** research training chỉ mở với câu hỏi khoa học mới và dữ liệu/campaign thích hợp, không tune validation đã lộ; formal training chỉ mở sau nhãn intent độc lập theo request, corpus đa môi trường đủ gate, split/acceptance độc lập và live feature parity. Ưu tiên trước mắt là nguồn nhãn và thử bridge ba nguồn **live post-response shadow** trong môi trường được cấp phép, với feature availability/timing đo thực tế; không chọn champion hoặc bật chặn.

## Study sampler trên development đã lộ — 2026-11-03T08:44+07:00

**Câu hỏi khóa trước train:** sampler `domain_family_balanced` lấy có hoàn lại có khuếch đại false positives vì lặp quá nhiều 206 benign views của Student lab không? [Execution plan](.artifacts/sampling_diagnostic_20261103/execution-plan.json) SHA256 `74d51551878fa3ce5e9959f7fccbdd534f5fe5b300c1d996cdee5945b8ec0e47` được khóa trước mọi score/train mới; bản plan đầu được sửa bằng amendment *trước train* vì checkpoint baseline cũ có implementation SHA khác mã hiện tại. Hai arm được fit lại trên cùng mã/dataset/seed/architecture, chỉ đổi `sampling=domain_family_balanced` sang thứ tự ngẫu nhiên không hoàn lại (`None`); MLP256 và GLU1024 mỗi arm 300 updates, 4 CPU/16 GiB. Dữ liệu chỉ là `forward-development-v2` **118.760 development vectors** với nhãn publisher/runner; 96.423 train rows tạo **27.142 exact float32 views** được trainer chọn, không có mixed-label view hay view/group xuyên role. Validation 11.024 rows/7.129 views đã lộ, tuyệt đối không gọi independent evaluation.

Sampler cũ thực tế đưa 38.278 lượt train qua **14.060** views (một view lặp tối đa 69 lần); Student benign 206 views nhận **9.684** lượt, tối đa 69 lần/view. Sampler không hoàn lại dùng cùng 38.278 lượt nhưng thấy đủ **27.142** views, tối đa 2 lần/view; Student benign chỉ 310 lượt. Thay đổi này đồng thời thay phân bố source/class/family, nên không thể quy một hiệu ứng cho riêng số lần lặp.

| Validation development, ngưỡng từ benign calibration 1% cố định theo policy | MLP cân nguồn | MLP không hoàn lại | GLU cân nguồn | GLU không hoàn lại |
| --- | ---: | ---: | ---: | ---: |
| Student lab, recall **theo exact view** | 17,65% | **0%** | 15,03% | 54,25% |
| Student lab, FPR theo exact benign view | 0% | 0% | **10,22%** | 0% |
| Student lab, PR-AUC theo exact view | 0,797 | 0,766 | 0,726 | 0,887 |
| SR-BH, recall theo exact view | 31,89% | 30,10% | **21,82%** | **3,18%** |
| SR-BH, FPR theo exact benign view | 0% | 0,063% | 0,348% | **2,50%** |
| SR-BH, PR-AUC theo exact view | 0,856 | 0,839 | 0,825 | 0,675 |

Theo request rows, Student GLU recall 18,06%→47,92% và FPR 10,73%→0%, nhưng SR-BH GLU recall 31,37%→5,57% và FPR 0,289%→2,85%; MLP Student recall 12,5%→0%. Đây là **tradeoff mạnh theo nguồn**, không phải cải thiện ổn định hay chứng cứ sampler tốt hơn. Ngưỡng mỗi arm chỉ tính theo cùng quy tắc benign calibration, không chọn bằng validation. Cả bốn bundle ONNX đạt parity trên 118.760 rows (`rtol=1e-5`, `atol=1e-6`), không mở test/holdout, không chọn champion hoặc thay model chính **9.675.784 tham số/207 cột**. [Báo cáo machine](reports/PARTITION_RECOVERY_20261031.json) có tóm tắt và private aggregate `sampling_diagnostic_20261103/report.json` SHA256 `c044f63b0235a5d17f786828d49e2bc1e6932bbbb89dae9248ce91587e1cae60`. Kết luận tiếp theo: ưu tiên nguồn hai lớp có nhãn request-bound và campaign/môi trường mới; không tune thêm trên validation này. Formal admitted **0/2.000.000**.

## Intake nguồn mới và quyết định study — 2026-11-03T08:01+07:00

**Biblio-US17:** API metadata item/bundle của idUS trả 200 và vẫn liệt kê archive 1.223.176.305 byte, nhưng workspace không có bản RAW/LABEL được cấp quyền hay phản hồi cấp phép. Không gọi lại endpoint nội dung từng trả 401; quyền thực tế **PENDING**. Mẫu thư ngắn để bạn gửi ở mục “Phương án truy cập Biblio-US17” bên dưới. Sau khi có RAW+LABEL+README và điều khoản sử dụng, kiểm RID/nhãn S2/S3 và duplicate trước khi nhập bất kỳ row nào.

**Nguồn mở mới được kiểm có giới hạn:** [CIKM 2026 IoT CVE HTTP reproduction artifact](https://github.com/mm-doshisha/CIKM2026-iot-vuln-pipeline) tại commit `bf43a370084d6b59a6e0c29319a51da251a6d6b3`, đối chiếu [bài báo của tác giả](https://arxiv.org/html/2608.22889) và [UNSW-IoTraffic gốc](https://doi.org/10.5061/dryad.w0vt4b94b). Repo nhỏ được giữ private/ignored, không chạy exploit hay gọi target. Bài báo nói 281 CVE attack examples gồm **245 request tái dựng thủ công từ exploit/advisory** và 36 từ tập nghiên cứu khác; 281 benign evaluation examples lấy từ IoT traffic thật. Đây là 281 **CVE examples**, không phải 281 attack requests vật lý đã bắt được. Dryad API ghi CC0-1.0 cho nguồn benign; repo ghi MIT cho code, còn lineage/điều kiện chia sẻ mọi trace attack cần kiểm theo upstream trước khi tái phân phối.

Read-only intake chỉ project method + `path` quan sát được, không ghép `params` object thành wire query giả. Trong 281 attack examples có 167 body, 48 structured params và chỉ 9 path tự chứa query; profile 70+6 sẽ bỏ nhiều tín hiệu attack. Path-only float32 views: **214/281 attack**, **140/281 benign UNSW**, trùng **4 view trái nhãn**; 281 CVE-paired benign authored controls có 114 views, **không** cộng là traffic thật. Độ đa dạng view có nhưng **class gắn chặt với nguồn tạo** (CVE reconstruction vs UNSW real), không có hai source groups đều có hai lớp/role/campaign-time split. Không fit, score, import hoặc dùng làm MLP/GLU study; research-training eligible mới **0**, formal admitted mới **0**. Báo cáo tổng hợp không chứa URI/body ở `.artifacts/source_screen_20261103/iot_cve_intake.json` (SHA256 `4538b1c3207593a750c320a469b7f93ffcfcab6772b2204901612b935d98c62b`). [ForenWebLog](https://arxiv.org/html/2606.08649) chỉ có bài báo pha log thật/synthetic, chưa thấy corpus/license/label trail có thể kiểm; [DEDALE](https://dedale.inria.fr/download.html) có nhãn flow theo time/IP/port, chưa có semantic HTTP request labels. Không tải archive lớn của hai nguồn đó.

**Quyết định:** chưa có corpus mới hợp lệ cho study MLP/GLU. Study đã định nghĩa ở mục bên dưới chỉ chạy khi có ít nhất hai nguồn hai lớp với provenance và nhãn request-bound, đủ unique views cho từng role/class, split theo campaign/source/time và visibility cùng một 76-feature contract. Không sử dụng các validation development đã lộ để điều chỉnh mô hình. 207-feature GLU vẫn cần riêng dữ liệu ba nguồn causal/post-response và live edge parity. Tổng 75.360 request lab theo report lịch sử vẫn **chưa global dedup**; 118.760 development vectors và 843 CIKM examples không cộng vào số request mới/admitted. Formal vẫn **0/2.000.000**.

## Chốt phép đo chống lặp view ở bước export — 2026-11-03T07:45+07:00

Đối chiếu trực tiếp `forward-development-v2/features.parquet` (chỉ train/calibration/val, không mở holdout): 118.760 rows có 118.760 `event_key` khác nhau trong snapshot, nhưng **không chứng nhận** 118.760 request vật lý độc lập. Số view float32 thực sự đi vào model, theo source/split: SR-BH train 25.909/60.000, calibration 7.998/10.000, val **6.839/10.000**; Student lab train 1.233/36.423, calibration 318/1.313, val **290/1.024**. Không có exact encoded-view overlap giữa train/calibration/val, không có group xuyên role và không có mixed-label view trong snapshot này. `feature_key` SR-BH val là 6.840, cao hơn encoded views một do hai bản biểu diễn khác nhau hội tụ sau float32 encoding; vì vậy `feature_key` chỉ là proxy, không phải input tensor chính xác. Không suy ra request trùng chỉ từ vector trùng: nhiều request có thể hợp lệ nhưng cùng view.

Phân bố nhãn train cũng khác nguồn: SR-BH 42.094 attack/17.906 benign, Student lab 6.912 attack/29.511 benign. Probe nguồn trên benign development đã đo balanced accuracy **86,74%**, chứng minh còn tín hiệu domain trong features, nhưng không định danh được feature nào là shortcut và không chứng minh label leakage. Sự đảo recall row/view có bằng chứng từ tần suất biểu diễn; 79 Student false positives vẫn trải trên 14 benign views. AIT scanner là họ hành vi khác payload-family đã fit, với 25 benign views và bốn view trái nhãn; đó là coverage/visibility shift thêm vào domain shift, không thể quy hết cho overfitting. Chưa có đánh giá độc lập mới để định lượng mức góp của từng nguyên nhân.

Code export request-only hiện ghi thêm `validation_encoded_views` và `validation_encoded_views_by_source` vào `model_manifest.json`, cân mỗi **exact float32 input** một lần, báo riêng số row lặp và view trái nhãn. Nếu một view có cả nhãn 0/1, chỉ số view-weighted trả `null`, không tự chọn/xóa/sửa nhãn. Đây là phép đo bổ sung cho validation development, **không** thay threshold từ benign calibration, loss, sampling, checkpoint, ONNX hoặc row-weighted metrics cũ. Test cả ba model export/ONNX và ca xung đột nhãn đều PASS; chưa export lại checkpoint 118.760, chưa chứng minh cải thiện chất lượng dự đoán. Anti-memorization ở train vốn đã khử lặp `feature_key` trên supervised pool và curated split cách ly group/view; không thêm một lớp dedup làm mất hành vi thời gian hay lấy validation đã lộ để chỉnh model. AIT vẫn chỉ 25 benign/3.146 attack views với bốn view trái nhãn; formal admitted 0, Biblio chờ quyền. Bước study kế tiếp cần nhãn request-bound đáng tin ở nguồn/campaign độc lập và protocol khóa trước khi chấm.

**Study kế tiếp chỉ khi gate dữ liệu qua:** khóa trước source/campaign/actor/time roles, seed, exact-view conflict handling, ngưỡng FPR và ngân sách CPU; dùng cùng 76 input và cùng split cho MLP/GLU baseline. So sánh sampler hiện có `None` với `domain_family_balanced` trên *training only* để hỏi liệu cân domain/family có giảm FPR trên campaign mới ở cùng recall; calibration chỉ chọn ngưỡng, validation chỉ chọn cấu hình theo tiêu chí khóa trước, test mới giữ kín đến cuối. Báo cáo cả row và exact-view metrics theo source/family cùng số group, không coi repeated requests là IID. Nếu thiếu nhãn hai lớp, campaign độc lập hoặc feature parity, giữ study `NOT_RUN`; không dùng AIT/SR-BH đã lộ hay Biblio chưa được cấp quyền để lấp gate.

## Study chỉ đọc trên checkpoint development hiện có — 2026-11-03T07:04+07:00

**Câu hỏi đã khóa trước khi chấm:** lợi thế của GLU 76 cột trên `forward-development-v2` có tồn tại khi mỗi `feature_key` chỉ tính một lần, và hai model có mắc cùng lỗi theo nguồn không? Corpus 118.760 **vectors** (`train` 96.423, `calibration` 11.313, `val` 11.024) có `research_training_permitted=true`, nhưng nhãn dựa publisher/runner, không có review intent độc lập. Đã dùng nguyên checkpoint ONNX, `feature_spec`, dataset SHA và **threshold calibration cũ** của MLP 219.144 tham số và GLU 9.541.640 tham số trên cùng 76 cột; không fit, đổi threshold, mở `test`/holdout hoặc chọn champion. Đây **không** phải GLU chính 9.675.784 tham số / 207 cột và MLP 252.680 / 207 cột. Plan và báo cáo riêng tư có SHA trong `ai-training/.artifacts/development_diagnostic_20261103/`; [machine report](reports/PARTITION_RECOVERY_20261031.json) giữ liên kết kiểm toán.

| Validation development, ngưỡng cố định | MLP 76 | GLU 76 |
| --- | ---: | ---: |
| SR-BH, 5.155 attack **theo dòng**: recall | 22,83% | 31,37% |
| SR-BH, 3.675 attack **theo `feature_key` duy nhất**: recall | **31,89%** | 21,82% |
| SR-BH benign, FPR theo dòng | 0/4.845 | 14/4.845 = 0,29% |
| Student lab, 288 attack theo dòng: recall | 12,50% | 18,06% |
| Student lab, 153 attack theo `feature_key`: recall | **17,65%** | 15,03% |
| Student lab benign, FPR theo dòng | 0/736 | **79/736 = 10,73%** |
| Student lab benign, FPR theo `feature_key` | 0/137 | **14/137 = 10,22%** |

**Phát hiện thực nghiệm:** ưu thế recall theo số dòng của GLU biến mất, thậm chí đảo chiều, khi cân đều các biểu diễn khác nhau. Trên SR-BH validation, GLU-only phát hiện 1.492 attack rows nhưng chỉ **677 `feature_key`**; MLP-only 1.052 rows tương ứng **1.047 keys**. Cả hai cùng bỏ sót 2.486 attack rows. Student lab validation chỉ có 290 keys/1.024 rows; các benign GLU báo nhầm vẫn chiếm 14/137 keys, không chỉ là một dòng bị nhân lặp. Đây là **bằng chứng về độ nhạy với tần suất mẫu và nguồn trong development**, chưa chứng minh một feature cụ thể gây shortcut hoặc GLU 207 kém hơn MLP 207. PR-AUC theo dòng SR-BH là 0,854 MLP / 0,837 GLU; Student lab 0,577 / 0,515. Train-vs-val Student lab PR-AUC MLP 0,998→0,577 và GLU 1,000→0,515 cho thấy shift/overfit trên nhãn development; cluster/campaign không độc lập nên không tính khoảng tin cậy IID hay production claim.

**AIT stress trên hai checkpoint 76 cột, không train:** 2.831 benign tiền attack chỉ có **25** vector khác nhau; 7.695 attack publisher có 3.146 vector. Bốn vector mang cả hai nhãn, với class counts `(68,2), (125,1), (252,9), (373,1)`; một classifier tất định chỉ thấy 76 cột phải bất đồng ít nhất **13** nhãn publisher trên bốn vector này, dù trọng số hoàn hảo. Không sửa nhãn hoặc bỏ ca xung đột. **0/25 benign views** và **4/3.146 attack views** trùng với train development; ở ngưỡng đã khóa MLP flag 0/7.695 attack, GLU 5/7.695, cả hai 0/2.831 benign. 0 false positives ở đây **không** chứng nhận FPR vì chỉ 25 benign views; phần lớn attack là dirb/WPScan ngoài phạm vi payload-family đã fit, nên đây là stress về coverage/domain shift, không phải đánh giá độc lập chất lượng SQLi/XSS hay phép so GLU 207. AIT vẫn không đạt cổng study hai nguồn/≥32 views mỗi source-role-class.

| Nguồn hiện có | Giá trị hợp lệ hiện tại | Không dùng để kết luận |
| --- | --- | --- |
| Student/Nginx/EVE Oracle và WAF-Bench synthetic | Kiểm pipeline, schema, parser, privacy, ONNX; lab labels còn pending | Không là independent quality evaluation |
| `forward-development-v2` SR-BH + Student lab, 118.760 vectors | Research fit/diagnostic nội bộ trên 76 cột, split đã khóa, nhãn publisher/runner yếu | Không là 118.760 request mới/nhãn formal; không chọn champion |
| AIT V2.1, một testbed | Stress no-fit, đánh giá đa dạng view và scanner coverage | Không dùng làm dual-class study/evaluation với 25 benign views và nhãn kịch bản |
| WCP đã kiểm ngoài 148 file sealed | Benign-only FPR/hard-negative stress đã lộ | Không đo recall; không mở 148 file dự phòng |
| SOC-MLD, ModSec-WP, Organization X, MWAD; WAMM/CSIC | Chỉ dữ liệu cách ly/retrospective hoặc fixture theo kết luận đã có | Không tự chuyển rule/unknown/anomaly thành attack intent đáng tin |
| Biblio-US17 | Ứng viên lớn có expert review/RID nếu được cấp quyền và kiểm RAW/LABEL/terms | Chưa có local request, chưa là corpus/evaluation; archive vẫn chờ quyền |

**Lộ trình ngắn nhất:** (1) giữ model/checkpoint/ngưỡng và dùng diagnostic trên để định nghĩa trước phép đo source/view weighted; (2) xin quyền Biblio rồi audit nhãn chỉ trên phạm vi thật được phép, đồng thời có thêm nguồn/campaign hai lớp đủ view diversity, request/campaign/time provenance và người review độc lập; (3) khóa train/calibration/validation và đánh giá môi trường mới *trước khi xem score*, purge group/view overlap và giữ test cuối kín; (4) mới mở research study ngắn trên cùng 76 input, so MLP/GLU tại cùng ngân sách FPR; (5) mở rộng physical requests được kiểm chứng, representation duy nhất, nhãn review và admitted **thành bốn số riêng**; (6) formal admission theo gate hiện hành rồi mới cân nhắc training 207 dài/acceptance/champion. Báo cáo capture lab trước Oracle ghi 75.360 HTTP requests **chưa global dedup**; Oracle development sau đó xác minh thêm 8 request riêng, nhưng chưa có một tổng request vật lý toàn cục đã kiểm. 118.760 development vectors không cộng thành request mới; formal **0/2.000.000**. Bước hoàn toàn tự động hiện có: SHA, request/log join, projection, dedup/index, frozen scoring, kiểm split/checkpoint/ONNX; xác nhận intent và quyền nguồn cần người có trách nhiệm thật. Không lặp lại audit nguồn yếu hoặc chỉnh thuật toán chỉ vì chỉ số development.

## Nguồn HTTP độc lập AIT và quyết định research corpus — 2026-11-02T19:10+07:00

Đã tải trực tiếp archive `russellmitchell_no-pcaps.zip` từ [AIT Log Data Set V2.1 trên Zenodo](https://zenodo.org/records/19483937) vào vùng private `ai-training/.artifacts/source_screen_20261102/ait/` (522.084.364 byte, SHA256 `51a03f51daea0fbbdcfe9b8abe0dbbe10633716f4f98074f861204a162ee1978`, MD5 khớp `abb43a46c70939ad9f98669e3510d2b7`). Metadata API ghi **CC BY-NC-SA 4.0** và open access. Đây là Apache HTTP log thu trong testbed doanh nghiệp mô phỏng có hành vi người dùng và attacker chạy thật trong testbed, **không phải traffic Internet sản xuất**. Chỉ dùng nghiên cứu phi thương mại nội bộ; quyền chia sẻ feature/weights cần xem lại điều khoản trước khi công bố. Biblio-US17 vẫn `PENDING`, không thử lại archive 401; mẫu thư xin quyền ở mục dưới.

Audit có mục tiêu trên bốn file Apache intranet: 7.695 JSON label refs **khác số dòng**, đều nằm trong 8.530 dòng của file đích `.2`, có thời điểm trong cửa sổ attack do nhà phát hành công bố; `gather/attacker_0/logs/attacks.log` tồn tại và hash SHA256 `eb7e96b8ad1270ab96c43de8575631aafb48a0a865e97c1c5c9f8cc117289f06`. Label của nhà phát hành chủ yếu là hoạt động scanner (`dirb` 4.462, `wpscan` 3.186); `webshell_cmd` 32, `webshell_upload` 3. Các nhãn sinh từ **rule/timeline của kịch bản**, không phải review ngữ nghĩa độc lập từng request. Chỉ lấy 2.831 dòng intranet **trước** lúc attacker bắt đầu 03:01 UTC làm ứng viên benign hẹp; 604 dòng không nhãn trong/sau cửa sổ attack và 54 dòng không có method/URI parse được vẫn `unknown`/loại khỏi view. Không quy mọi dòng không nhãn thành benign, không suy exploit outcome từ status.

`project_request` parse được **10.526 Apache observations** ứng viên (2.831 benign tiền tấn công, 7.695 attack nhãn publisher) thành 70 số; `bounded_spec` mã hóa đủ 76 số hữu hạn cho từng dòng. Không có Student audit, request ID chung, body, EVE flow hoặc 137 đặc trưng full-only; không điền giả. Có **71** method+target hash khác nhau trong benign và **7.682** trong attack; còn 76-feature views chỉ **25 benign / 3.146 attack**, với **4 view trùng nhãn** (818 benign observations và 13 attack observations). 2.831 benign rows vì vậy không thay được 25 model views. Chỉ một testbed/campaign, phần attack tập trung vào scan, benign tiền tấn công khác pha thời gian; chia ngẫu nhiên từng dòng sẽ leakage/học shortcut. Không thể đạt gate hiện hữu ≥32 views **mỗi source × mỗi role × mỗi class** ngay cả trước split, cũng chưa có hai nguồn đủ hai lớp. **AIT là ứng viên research có provenance tốt hơn các nguồn rule-only trước, nhưng 0 request được đưa vào corpus study đáng tin hay formal admission ở lượt này.**

Kiểm parity thực tế trên 8 request Oracle development cũ: Nginx raw target ↔ EVE `ai_query_numeric` version 2 khớp **8/8** sau ghép `X-Request-Id`; projector request-only/encoder 70+6 chạy **8/8**, tạo 7 model views. Chỉ có 60 tên số trùng giữa projector và EVE; **6/8 request** có ít nhất một giá trị khác vì request-only alias/drop field nhạy cảm còn EVE numeric project từ target trước bước mask. Đây là **hai profile khác nhau**, không được dùng EVE numbers làm vector request-only rồi tuyên bố parity; 137 full-only không được zero-fill. AIT chỉ kiểm profile method/URI, không chứng nhận parity live edge hay GLU 207.

**Quyết định:** 0 request được formal admission, 0 nhãn intent được review độc lập; 10.526 là observations có nhãn/cửa sổ kịch bản từ **một** nguồn ngoài, không phải 10.526 request train-eligible hoặc 10.526 Ground Truth. Không chạy study ngắn. Bước có giá trị nhất: người có email xin quyền Biblio-US17 bằng thư bên dưới; đồng thời cần nguồn/campaign thứ hai có benign và attack được xác minh request-bound, đủ view diversity, rồi khóa split theo source/campaign/time và purge exact-view overlap trước calibration/validation. Không hạ gate hiện hành.

**Cấu hình study tối thiểu khi gate thực sự qua:** hai source groups độc lập đều có hai lớp và ≥32 request **cùng ≥32 distinct 76-feature views** cho từng `train`/`calibration`/`val` × benign/attack; tổng sàn lý thuyết là 384 views trước test riêng. Dùng `training_pool=curated_multisource`, cùng `request-structure-v1`/`bounded-request-v1` 76 cột, cùng split, seeds và ngân sách FPR để so `deep_mlp` nhỏ với baseline lexical cố định; `residual_glu` 76 cột chỉ là ablation nếu dữ liệu đủ. Chỉ pilot 1–2 epoch theo cap hiện hành, threshold trên calibration, báo cáo theo source/campaign/family và latency trên validation. GLU **9.675.784/207** vẫn là model khác input; không gọi phép thử request-only là kết quả của nó và không dùng holdout khóa để chọn threshold.

## Quyết định nguồn nhãn độc lập — 2026-11-02

Đây là **screening có mục tiêu** trên nguồn chưa giải quyết; không chạy lại corpus audit, campaign, study hoặc trainer. Formal evidence-v2 và `configs/scale_policy.yaml` giữ nguyên. Lượt này phát **0 request**, thêm **0 nhãn benign/attack xác minh độc lập**, admission mới **0**; 8 request Oracle trước vẫn UNKNOWN. Raw MWAD chỉ lưu private, không đưa URI/query vào báo cáo hoặc Git.

| Nguồn | Bằng chứng có thật | Quyết định |
| --- | --- | --- |
| [Biblio-US17, bài báo nhà xuất bản](https://link.springer.com/article/10.1186/s42400-024-00336-3) | Tác giả mô tả 47.402.907 request website thật, RID nối RAW/LABEL theo ngày và thứ tự, 327.906 LVL1 attack đã được chuyên gia xác nhận qua S2/S3. S2=0 là cảnh báo giả được xem thủ công. | **Ứng viên nhãn độc lập mạnh nhất**, nhưng con số là claim của tác giả, chưa kiểm row. CLEAN gồm cả S2=-1/S3=-1 chưa review từng request; không lấy toàn CLEAN làm benign. [idUS](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e) ghi CC BY-NC-ND 4.0; endpoint archive trả 401, cần bản được cấp quyền và kiểm quyền dùng. Chỉ có method/URI/status/size/RID; không tạo thời gian chính xác/flow/207 feature. **0 admitted**. |
| [MWAD, repo tác giả](https://github.com/paul12345-cyber/Multimodal-web-attack-Dataset) | Pin revision `a7a19c525bfa94095120c7fa5731ccf33bf2022e`, CC BY 4.0. Hai CSV private: 1.000 URI/1.000 flow vectors, mỗi bảng 500/500 nhãn; 975 URI hash và 989 vector hash khác nhau. | **Research-only**. Không có request ID, timestamp, campaign hoặc khóa ghép URI→flow; nhãn do chiến dịch tác giả sinh, chỉ SQLi, hai block nhãn theo row order. Không chứng nhận 1.000 cặp request vật lý hay independent semantic review; **0 admitted**. |
| [WAF-Bench-77, dataset card](https://huggingface.co/datasets/netgoat-ai/WAF-Bench) | Pin revision `674f8bdcfc2d177beaf323cb80d3d889baaff063`; kiểm private `test.jsonl` 77 ID riêng, 57 malicious/20 benign, CC BY 4.0. | Chỉ fixture kiểm nhanh request-view: chính tác giả ghi **synthetic**, không có physical capture/application oracle, 20 benign còn dưới tối thiểu 32/source/role/class trước khi chia. Public test đã exposed, không train/admission hay coi là final holdout. |
| [CSIC2010 qua IMPACT](https://www.impactcybertrust.org/dataset_view?idDataset=940) | Nguồn gốc ghi rõ `anomalous` gồm request sai cấu trúc **không có ý định độc hại**. | Nhãn binary trong research cũ đo anomaly, **không phải attack intent**; không đổi lịch sử hoặc promote thành formal. |
| [OWASP CRS regression](https://coreruleset.org/docs/index.print), [CICIDS2017](https://www.unb.ca/cic/datasets/ids-2017.html) | Test CRS là expected rule match; CICIDS gắn flow theo lịch attack/network tuple. | Không có per-HTTP-request intent review đủ gate; chỉ fixture/flow research, **0 admitted**. |

**Oracle hiện xác nhận được:** request thật/ID/method/target/clock giữa Student–Nginx–EVE offline, body POST khớp PCAP, response status và thao tác STAFF tạo khoa làm DB `0→1`; đã cleanup lab. Đây là facts về quan sát và side effect **của thao tác hợp lệ**, không xác nhận attack intent hay exploit outcome của SQLi/XSS. Plan intent, HTTP status, rule alert và không thấy side effect đều không tạo ground truth. Cơ chế machine-verifiable có thể được xem xét nếu reviewer độc lập phê duyệt *trước* exact case/body + oracle dự kiến, ký nguồn/plan, capture chứng minh mỗi request khớp, oracle ứng dụng do trust domain khác collector cung cấp và kiểm hậu nghiệm trên mẫu bất đồng. Đây là **tiêu chí đề xuất, chưa được phê duyệt**, và không tự thay evidence-v2/human review.

**Điều kiện study ngắn tiếp theo:** cần ít nhất hai nguồn hai lớp có nhãn request-bound đáng tin; mỗi nguồn × train/calibration/validation × benign/attack có ≥32 request **và** ≥32 model views khác nhau, không trùng group/view giữa partition, embargo 300 giây khi có clock thật; profile request-only phải có cùng feature train/inference và tránh source/label shortcut. Benchmark CSIC/PKDD cũ là retrospective research, không phải study tổng quát hóa mới. Biblio nếu được cấp quyền chỉ có thể mở đường cho **request-only** study sau audit label scope, license, dedup và split; không thể tự đưa vào GLU 207/ba nguồn. Formal `scale_policy.yaml` vẫn yêu cầu 2M admitted, 3 môi trường, 7 ngày, 120 campaign, 95% ba nguồn và family/partition coverage. Chưa có corpus đáp ứng, nên study mới, formal training và champion đều **NOT_RUN**.

**Đường ngắn nhất có giá trị:** xin quyền bản Biblio-US17 qua [idUS request-a-copy](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361), làm rõ quyền nghiên cứu/biến đổi feature, lấy RAW+LABEL+README và xác minh phạm vi S2/S3 trên RID. Song song cần một nguồn/ứng dụng khác có benign+attack được người độc lập review và request/campaign/time provenance; review 162 hồ sơ lab hiện có có thể giúp development nhưng **không** tạo môi trường độc lập. Sau đó mới khóa protocol study, so MLP/GLU trên cùng visible features/FPR budget và tách acceptance chưa xem. Không liên hệ tác giả hoặc tự ký/review thay người có thẩm quyền trong lượt này.

### Phương án truy cập Biblio-US17 và nội dung xin quyền sẵn dùng

Kiểm lại ngày 02/11: trang [request-a-copy](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361) trả HTTP 200, còn endpoint nội dung archive trả **401**. idUS metadata ghi CC BY-NC-ND 4.0, archive khoảng 1,223 GB; giấy phép bài báo khác giấy phép dataset. [Tóm tắt giấy phép Creative Commons](https://creativecommons.org/licenses/by-nc-nd/4.0/) giới hạn mục đích thương mại và chia sẻ bản chuyển thể, nên phải hỏi người cấp quyền về việc giữ feature/model nội bộ và việc chia sẻ artifact trước khi sử dụng. Không dùng đường dẫn thay thế để vượt quyền.

Người sở hữu email có thể mở form trên và dán nội dung ngắn sau. Thay các ô vuông bằng thông tin thật; **không gửi password, khóa riêng hoặc log raw**. Chưa ai trong project gửi yêu cầu thay bạn.

> **Subject:** Authorized research access and use terms for Biblio-US17 (DOI 10.12795/11441/148254)
>
> Dear Biblio-US17 repository team,
>
> I am conducting non-commercial research on HTTP intrusion detection. Could you grant me legitimate access to the complete **RAW, LABEL and README/documentation** files, including the request-ID join instructions, field/label definitions and any available checksums? The archive is not accessible to my account through the repository at present.
>
> Please confirm in writing whether I may securely store the data, extract privacy-preserving numeric features, and use those features to train and evaluate a research model. Please also specify any restrictions on retention, redistribution of raw records, sharing derived features or model weights, publishing aggregate metrics and citing the dataset. I will not redistribute raw requests or assume that every CLEAN record has an independently reviewed benign label.
>
> If access requires a particular agreement or institutional approval, please send the required steps. Thank you.
>
> Name and affiliation: [your real name and institution]
>
> Contact email: [your email]

**Intake khi grant đến — dừng ở từng gate nếu fail:** (1) giữ email/grant/terms và archive ở vùng private, `sha256sum` từng file, ghi nguồn, version và ngày nhận; (2) kiểm README/schema và join RAW↔LABEL bằng RID/ngày/thứ tự *được publisher mô tả*, đếm unmatched/duplicate trước khi tin nhãn; (3) phân tách `LVL1` attack có cơ sở S2/S3, benign có review thật, publisher-only, unreviewed và UNKNOWN; không mặc định toàn CLEAN benign; (4) kiểm cùng RID khác payload/nhãn, exact request duplicate, cross-source collision và unique float32 views 76 cột, giữ mọi xung đột để review thay vì tự sửa; (5) audit missingness của METHOD/URI và các cột không có, không padding lên 207; (6) khóa split theo ngày/source/campaign nếu metadata thực hỗ trợ, purge RID/view trùng và giữ acceptance chưa xem; (7) xuất bảng riêng `raw rows / physical RID / unique request / unique views / publisher labels / independently reviewed labels / research eligible / formal admitted`. Việc được cấp quyền chỉ mở **kiểm định**, không tự chuyển bất kỳ row nào sang formal admission. `S2=-1/S3=-1` không được tự coi là human-reviewed. Không bịa timestamp từ thứ tự RID.

### Accounting development và feature visibility

Corpus cũ `forward-development-v2` có **118.760 research rows/vectors**, trong đó **55.559 nhãn 0** và **63.201 nhãn 1** theo publisher/runner (SR-BH 24.287/55.713; Student lab 31.272/7.488). Admission file cho phép *technical research fitting* và split có 0 group/model-view collision, nhưng `label_basis` ghi rõ **chưa có independent human review**; các rows này không phải 118.760 physical requests đã xác minh, không là final test, và **0 nhãn intent đủ tin cho study tổng quát hóa mới**. Ngoài ra WAF-Bench có 20/57 nhãn do bên ngoài biên soạn, nhưng là synthetic fixture, không cộng vào HTTP requests thực. Oracle 8 case chỉ xác minh sự kiện quan sát, 8 intent UNKNOWN. Formal admitted **0**.

| Dữ liệu | Feature thực sự có thể lấy | Không được suy diễn |
| --- | --- | --- |
| Biblio khi có quyền | `METHOD` + `URI` đủ đầu vào về mặt schema cho projector request-only **70 số gốc**, encoder tạo thêm 6 tương tác thành **76 đầu vào**; chỉ những dòng parse được mới thành development view. `RESP_CODE/SIZE` có sau response và RID cho ngày/thứ tự. | Clock chính xác, client/session/UA/body/flow, latency, 207 full-view, hoặc clean toàn tập được review. |
| MWAD | CSV URI cho cấu trúc URI; CSV flow cho 22 số flow **riêng biệt**. | Method nếu không ghi, khóa URI↔flow, timestamp/campaign, ba nguồn; không ghép hai CSV theo thứ tự để tuyên bố cặp request. |
| WAF-Bench đã kiểm | Method/path/query object/header/body cho fixture. 56/77 có query; **13 body-only**, gồm **8 malicious**, sẽ mất tín hiệu body với profile 76 cột. | Byte/ordering/encoding query gốc từ JSON object, physical request/time/response/flow; không đo FPR thực từ 20 benign synthetic. |
| Student lab development | Ba nguồn offline và request/response/DB Oracle ở 8 case; 207 post-response theo contract hiện hành khi telemetry đủ. | Intent cho 8 case, live Rust/edge receipt-time parity, pre-response blocking hoặc độc lập môi trường. |

So trực tiếp current `request_view.columns()` và `bounded_spec()/feature_spec.json`: projector cho **70 số gốc**, encoder thêm **6 tương tác** thành 76; **70/76 tên cột request-only trùng tên với 207**, còn **137 cột chỉ có trong 207** (behavior theo actor/time, prior-flow, status/latency/response, role/UA, availability). Trùng tên không bảo đảm cùng giá trị hoặc cùng thời điểm; không padding các cột thiếu bằng 0 để dùng lại GLU 207. Request-only research baseline hiện có trong code, dùng cùng phép che bí mật và chỉ method/URI; nó chỉ đo khả năng học cú pháp request. So sánh với GLU 207 chỉ công bằng trên cùng cohort và visibility có thật, không so điểm khác dữ liệu/nhãn như một cuộc đấu model. Chưa có dữ liệu mới đáp ứng research study hai nguồn hai lớp, nên **không chạy pilot mới**.

## Oracle quan sát development đã chạy thật — 2026-11-02T11:09+07:00

Pilot **riêng** `dev-oracle-observation-v1` đã chạy 8 request trên lab AI-owned loopback. Plan ở `ai-training/.artifacts/devgt1/plan/plan.json` được khóa trước request: SHA nội dung `08361b0f05836e4e774b2050f96e3575a09d8803ecc942d9b10fb5a5e3e61936`, SHA file `f73e25029a921834ef9d1f70ec1e21744f9a0f834039b2b16a2991e7d9b163c6`. Plan pin code thực thi, Student backend Git tree, Nginx template, exact 8 case và partition development. Đây **không** phải plan-v3 có chữ ký ở mục kế tiếp: plan-v3 vẫn chưa có reviewer/public key/approval và chưa phát request.

Oracle thực tế tại `ai-training/.artifacts/devgt1/run/oracle-verification/report.json` (SHA nội dung `973faa9afc23e2333d1f8444e5b56e6a0813d83c55084f11aa7b71be0c46db28`) tái kiểm **8/8 request vật lý**, **8/8 Student–Nginx–Suricata EVE**, **8/8 response status**, **2/2 POST body bytes trong PCAP private**, và **1 thao tác STAFF tạo khoa** có DB count `0→1`, HTTP 201, request ID khớp. Suricata decode **offline** từ PCAP thật, không phải sensor realtime. `cleanup-verification.json` xác nhận DB Docker tạm biến mất và cổng lab đóng. Response ledger chỉ lưu SHA/độ dài/status; không xuất password hoặc token. Report pin SHA của plan, capture, ba nguồn, response, before/after DB và cleanup; blind queue `run/review/` tái kiểm 8/8 với nhãn null.

Các điều trên là **sự kiện quan sát do collector/lab kiểm**. Intent benign/attack được xác minh độc lập **0/0**, exploit outcome của attack **0**, cả **8 intent UNKNOWN**, formal admission **0**. HTTP 200/201, rule alert, claim trong plan và DB side effect của một mutation hợp lệ không tự chứng minh ngữ nghĩa attack. Capture mới chỉ dành cho development; không nhập formal training. Không có reviewer độc lập hay môi trường đánh giá độc lập, nên signed pilot và gate evidence-v2 vẫn nguyên trạng.

Audit `ai-training/.artifacts/devgt1/lineage-audit/report.json` đọc lại ba capture pending cũ và lượt mới: **170 request ID khác nhau**, 10 campaign ID trong **một kiểu môi trường lab**, 79 target hash/91 lượt lặp target; 0 va chạm ID trong bốn capture này. Bản `lineage-audit-all-unsealed/report.json` thêm capture v1 cách ly: **218 ID/13 campaign ID/79 target hashes/139 lượt lặp target**, 0 va chạm trong năm capture. Audit mới chưa quét sealed historical cohort hoặc toàn bộ log lịch sử, nên không chứng nhận global dedup hay tăng tổng 75.360 lên 75.368 request duy nhất. 75.360 là tổng theo report lịch sử, còn formal admitted vẫn **0/2.000.000**. Không chạy study mới: 8 nhãn UNKNOWN không đủ tập hai lớp cho validation/calibration có ý nghĩa.

Quy trình đã tự động hóa phần khách quan `plan/code SHA → lab cô lập → request → Student/Nginx/PCAP/EVE → response/DB oracle → cleanup → blind queue → cross-capture ID audit`. Phần cần nguồn độc lập hoặc người có trách nhiệm vẫn là chứng cứ intent/benign request-bound, chính sách chấp nhận machine labels, campaign/môi trường khác, split theo source/campaign/time và parity 207 feature khi inference sau response. Batch/resume SQLite cũ đã kiểm ở 162 hồ sơ, chưa benchmark 2 triệu; không lặp pilot này để tăng số lượng. Pilot chạy với `CPUQuota=400%`, `AllowedCPUs=0-7`, `MemoryMax=12G`, không dùng dịch vụ trả phí hoặc traffic ngoài lab.

## Ground Truth pilot có protocol ký trước capture — 2026-11-02

Đã khóa plan 8 request trong lab AI-owned loopback, gồm 4 GET benign (một hard negative), 2 GET có attack intent SQLi/XSS dự kiến và 2 POST phục vụ đăng nhập/tạo khoa. Plan đọc được mục đích, method, URI và body không chứa password; pin SHA của collector. `plan-v1`/`plan-v2` là bản soạn trước khi collector source ổn định, **superseded, chưa ký/chạy**. Chỉ dùng `ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3/plan.json`: plan SHA `a38ecc02822e9a2618dcfaa442d00492ae4ce438efc5f6bdd73c3866a5129eb2`, file SHA `4a61049c9a8a6bf05345f203ef95d392c8f2ffd54b23366ba37b12b078d7f9e4`, collector SHA `30c5eee796b6a6544eebabb7268f24a135614efa5d5d9b6905cad9e8c367174e`. Sửa collector sau khi ký sẽ làm preflight từ chối chạy.

**Gói reviewer ngắn:** [APPROVAL_PACKAGE.md](.artifacts/ground_truth_pilot_20261102/APPROVAL_PACKAGE.md) nằm private mode 0600, chứa 8 URI/body được phép, giới hạn lab, rủi ro, SHA, hướng dẫn tạo/giữ khóa Ed25519 và lệnh ký. Không có private key/chữ ký trong gói. Approval mới sẽ ký thêm SHA của **10 file thực thi AI**, Git tree của Student backend và SHA mẫu Nginx; `verify-protocol` và collector so lại trước traffic. Chữ ký vẫn chỉ chứng minh key possession; operator cần xác nhận reviewer thật sự độc lập qua kênh riêng.

**Trạng thái thật:** plan đã tạo và test fixture kiểm đường ký/ghép/oracle; **chưa có reviewer độc lập, chữ ký hay capture pilot thật**. Không có thêm nhãn được xác minh: 162 hồ sơ cũ UNKNOWN, 0 benign/0 attack xác nhận độc lập, 0 admission. 29 bất đồng runner/cú pháp được phân nhóm: 7 runner-benign có cue (5 `hard_negative_1`, 2 `hard_negative_2`); 22 runner-attack thiếu cue (7 command, 9 SQLi, 6 XSS). Đây là giới hạn của regex và claim runner, không phải nhãn sai được chứng minh; không lặp lại các kiểm tra ID/hash đã PASS.

Người phê duyệt **khác collector** cần đọc plan thật, xác nhận ngữ nghĩa từng case và phạm vi lab. Họ giữ khóa Ed25519 riêng, công bố public key qua kênh tin cậy, ký từ terminal riêng tư. Lệnh mẫu (thay đường dẫn key và reviewer ID bằng giá trị thật; không gửi private key, password hay raw logs vào chat):

```bash
cd /home/trung/projects/idps-web-aws
PLAN=ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py sign-protocol \
  --plan "$PLAN" --reviewer-id '<reviewer-doc-lap>' \
  --private-key '<private-ed25519-key>' --trusted-reviewer-key '<trusted-public-key>' \
  --output ai-training/.artifacts/ground_truth_pilot_20261102/approval-v3.json
```

Chữ ký chứng minh **quyền sở hữu khóa**, không tự chứng minh danh tính hay tính độc lập của reviewer. Operator phải kiểm điều này qua kênh ngoài hệ thống. Collector `collect-three-source` từ chối pilot thiếu chữ ký hoặc source/plan bị đổi **trước khi khởi động lab**. Sau chữ ký thật, chạy pilot đúng một lần trong lab loopback với cgroup ≤4 CPU/12 GiB, rồi tạo blind queue và `stage-protocol`. Bước stage tái kiểm Student/Nginx/EVE, request ID, method, target SHA, timestamp sau approval/preflight và đúng một request mỗi case. Chỉ GET có đủ ba nguồn mới được ghi `MACHINE_VERIFIED_PROTOCOL_MATCH` ở **staging**; hai POST giữ UNKNOWN vì body thực chưa được bind với signed plan. Oracle DB đọc marker khoa trước và sau POST trong disposable DB; đó là **quan sát do collector ghi**, không phải oracle độc lập và không chứng minh attack intent/exploit outcome. Tất cả `formal_training_eligible=false`; gate evidence-v2 hiện hành không thay đổi.

Collector dừng Student, sensor và PostgreSQL Docker `--rm` trong `finally` sau khi đọc oracle; `verify_lab_cleanup` kiểm marker/cleanup, process identity, container biến mất và ba cổng loopback đóng. Kết quả dự kiến ở `gtp3/cleanup-verification.json`; nếu cleanup fail, pipeline không tiếp tục decode/correlation để tuyên bố pilot PASS. Hai lab ba nguồn cũ đã được kiểm lại bằng verifier này và PASS; pilot mới chưa chạy. Container không có mount persistence được chỉ định, nên mutation tạo khoa biến mất cùng disposable DB khi stop. Đây là xác minh dọn lab, không phải application oracle độc lập.

| Bước có thể tự kiểm | Ý nghĩa cho admission hiện hành |
| --- | --- |
| Chữ ký, plan SHA, 10 code SHA, Student Git tree/Nginx template và thời điểm preflight | Chứng minh integrity và key possession; tính độc lập/đúng ngữ nghĩa của reviewer cần xác nhận ngoài hệ thống |
| Student/Nginx/EVE, PCAP, request ID, method, target, status, timestamp và đúng 1 request/case | Chứng minh request quan sát khớp protocol; không tự xác nhận intent hoặc exploit outcome |
| DB count 0→1 cho `faculty_create` rồi xác minh disposable DB đã bị xóa | Xác nhận collector quan sát được side effect benign và trạng thái lab được dọn; không là oracle độc lập cho attack |
| Evidence-v2 review, prepared dataset/provenance và corpus gate | Vẫn cần reviewer độc lập và điều kiện dữ liệu; pilot staging không tự chuyển sang admitted |

Lệnh tiếp tục **chỉ sau khi chữ ký thật đã có**; người vận hành kiểm SHA/key fingerprint trước khi chạy. Output `gtp3` ngắn để Unix socket của lab không vượt giới hạn đường dẫn:

```bash
cd /home/trung/projects/idps-web-aws
PLAN=ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3
APPROVAL=ai-training/.artifacts/ground_truth_pilot_20261102/approval-v3.json
PUBKEY='<trusted-public-key>'
PILOT=ai-training/.artifacts/gtp3
systemd-run --user --scope -p CPUQuota=400% -p AllowedCPUs=0-7 -p MemoryMax=12G -p MemoryHigh=11G -p MemorySwapMax=0 \
  env PYTHONPATH=ai-training/src PYTHONDONTWRITEBYTECODE=1 \
  ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py collect-three-source \
  --plan "$PLAN" --output "$PILOT" --nginx-bin "$PWD/.local-dev/foundation/tools/runtime/usr/sbin/nginx" \
  --suricata-runtime "$PWD/ai-training/.artifacts/upgrade_20261028/tools/runtime" \
  --protocol-approval "$APPROVAL" --trusted-reviewer-key "$PUBKEY"
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --plan "$PLAN" --lab "$PILOT/lab" --capture "$PILOT/capture" \
  --three-source "$PILOT/correlated" --output "$PILOT/review"
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py stage-protocol \
  --plan "$PLAN" --lab "$PILOT/lab" --capture "$PILOT/capture" \
  --review "$PILOT/review" --three-source "$PILOT/correlated" \
  --approval "$APPROVAL" --trusted-reviewer-key "$PUBKEY" \
  --application-oracle "$PILOT/application-oracle.json" --output "$PILOT/staged"
```

Nếu một bước fail, giữ artifact lỗi để điều tra, không đổi plan đã ký hoặc gán nhãn cho capture một phần. Cần tạo plan mới và ký lại trước lượt thử mới.

Nếu pilot được ký/chạy thành công, cần pin artifact capture/PCAP/EVE, đánh giá độc lập cơ chế trust và sampling audit theo campaign, phê duyệt chính sách machine labels rồi mới xem xét admission. Việc này vẫn chỉ tạo một campaign **development trong một lab**, chưa có tập prospective độc lập, chưa có parity live edge/207 features và chưa mở study/train. Để mở rộng tới 2 triệu request phải có nhiều nguồn/campaign được phép, dedup toàn cục, label provenance và kiểm toán theo batch; không nhân số request bằng observations hoặc lặp plan này.

**Đánh giá mở rộng:** Quy trình ký exact 8 case và `stage-protocol` đọc cả shard vào RAM chỉ phù hợp pilot nhỏ. `review-evidence.py auto` đã có SQLite/batch/resume cho 162 hồ sơ và kiểm lại khi crash, nhưng chưa benchmark 2 triệu. Ở quy mô lớn cần protocol ký theo campaign/template/seed và version code, mapping deterministic tới từng request ID/target, xác minh stream theo shard, dedup toàn cục bằng khóa request vật lý, partition source/campaign/time khóa trước capture, cùng kiểm toán ngẫu nhiên theo family/môi trường. Reviewer độc lập phải phê duyệt ngữ nghĩa và chính sách machine labels cho từng loại generator/oracle; đợt ký này **không** tự mở quyền admission cho các campaign tương lai. Xây phần scale sau khi pilot thật chứng minh ba nguồn và trust boundary hoạt động; hiện 0 throughput/quality evidence ở quy mô 2 triệu.

## Lượt review tự động blind, batch và resume — 2026-11-02

`review-evidence.py auto` đã chạy trên **162/162 request** qua ba capture shards private. Mỗi shard được tái kiểm plan/capture/queue, SHA từng dòng Student/Nginx/EVE khi có, method/status/clock/campaign và PCAP body provenance. SQLite private giữ một record cho một request ID/event key; chạy thử 65 record rồi `--resume` thêm 97, chạy lại thêm 0. Không phát request mới, không đọc holdout. `auto-compare` chỉ được mở claim runner **sau khi** blind DB hoàn tất và pin hash; không sửa blind records. 39 query có một cue cú pháp để ưu tiên triage; khi đối chiếu hậu kiểm có 7 cue trên claim benign và 22 claim attack không có cue. Đây là bất đồng tín hiệu yếu, **không phải nhãn sai đã chứng minh**.

Kết quả nhãn: **0 oracle verified, 0 AI model proposed, 0 independent human reviewed, 162 intent UNKNOWN, 0 admitted**. Bộ cue là luật cú pháp định trước, không được gọi là AI model hoặc ground truth. 12 POST có body PCAP, 6 POST cũ thiếu body; 102 query chỉ nhìn thấy trong Nginx lab private. 162 request có 78 target views, 84 lượt lặp view và 36 view xuất hiện xuyên campaign: không chia các campaign cùng lab thành train/val/test. Dedup ở đây theo request ID trong registry; sealed historical cohort không đọc nên chưa có global dedup. SQL/JSON report không lưu plaintext query, password hoặc token. [Machine report](reports/ATTACK_EVIDENCE_20261101.json) pin artifact và SHA; artifact active private là `ai-training/.artifacts/evidence_campaign_20261102/auto-review-v3/` và `auto-review-v3-unblind/`. V1/V2 là lượt kỹ thuật đã superseded, giữ private để truy vết.

Lệnh chạy lại hoặc tiếp tục trên cùng artifact private:

```bash
REG=ai-training/.artifacts/evidence_campaign_20261102/review-registry.json
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" auto --output ai-training/.artifacts/evidence_campaign_20261102/auto-review-v3 --batch-size 32 --resume
```

Với corpus tương lai, registry có thể chứa nhiều capture shards; mỗi shard được xác minh trước khi ghi batch vào SQLite. Nếu tiến trình bị ngắt sau một commit nhưng trước report, dùng `--resume --recover`: tool kiểm lại **mọi record cũ với capture thật**, từ chối record lạ/sai và ghi report mới; không dùng `--recover` cho bản complete bị đổi SHA. Test đã giả lập mất report ở checkpoint rồi phục hồi. Chưa benchmark luồng này ở 2 triệu request, nên chưa tuyên bố đạt throughput/quy mô production. Capture mới cần pin request ID, UTC clock, source SHA, query visibility, body HMAC và application oracle độc lập *ngay khi thu*, cùng provenance người vận hành; app oracle phải có chứng cứ state/side-effect, không chỉ status/alert. Gate evidence-v2 hiện hành vẫn yêu cầu người review độc lập và dataset/provenance request-bound. Nếu muốn chấp nhận machine-verified labels về sau, cần phê duyệt chính sách riêng về trust boundary của oracle, ký/chứng thực producer, test tamper/disagreement và audit mẫu theo campaign; **chưa sửa gate**. Hiện tự động hóa đã thay thế 162 lượt đối chiếu cơ học, nhưng **0 trong 162 kết luận ngữ nghĩa** có thể bỏ qua người review theo gate hiện hành. 29 disagreement giúp ưu tiên chứ không cấp nhãn.

## Review riêng tư 162 hồ sơ và POST body evidence — 2026-11-02

Đã chuẩn bị công cụ terminal `scripts/review-evidence.py` trên ba queue private, mỗi queue 54 request. Công cụ tái kiểm hash/ID/timestamp/campaign và nguồn Student–Nginx, thêm EVE HTTP/flow khi đã capture; hiện **162 chưa được người độc lập review, 0 benign/0 attack được xác minh, 0 admitted**. Người review xem facts và query được che PII/secret trước; chỉ sau khi lưu quyết định bất biến mới dùng `unblind` để xem claim của runner. Cú pháp/rule/status/plan không là ground truth. Công cụ yêu cầu tự khai danh tính khác collector nhưng không thể xác thực danh tính hay tính đúng của nhãn.

Hai PCAP ba nguồn đã được kiểm byte HTTP/response ID và target SHA: **12/12 POST** có body thực được quan sát (mỗi lượt 6). Artifact private `body-evidence-v1` chỉ lưu độ dài, tên field allowlist và HMAC với khóa 0600; không ghi giá trị password/token. HMAC chứng minh cùng bytes khi đọc lại PCAP, **không cho biết ý định tấn công hoặc exploit thành công**. Sáu POST của queue hai nguồn cũ không có PCAP body tương ứng: phải để `unknown` nếu không có bằng chứng độc lập khác, tuyệt đối không tái dựng từ runner/status. PCAP/khóa/raw Nginx chỉ ở máy riêng tư; không đưa vào Git. Query Nginx lab tồn tại trong capture private và chỉ hiển thị cục bộ sau mask; edge production vẫn chưa chứng nhận numeric query parity.

Người độc lập chạy trong terminal riêng tư từ root repo (không chuyển artifact private qua Git):

```bash
REG=ai-training/.artifacts/evidence_campaign_20261102/review-registry.json
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" sources
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" review --source eve_novel --reviewer-id <id-nguoi-review-thuc> --output ai-training/.artifacts/evidence_campaign_20261102/human-review/eve_novel
```

Lặp lệnh `review` với `eve_first` và `two_source`, thay cả `--source` và thư mục `--output`; có thể thoát `q` rồi chạy lại đúng reviewer ID để tiếp tục. Mỗi request chọn `b`/`a`/`u`, ghi family cho attack và giải thích ngữ nghĩa tối thiểu 20 ký tự dựa trên HTTP/ứng dụng đã quan sát. **Với POST, HMAC không hiển thị nội dung: muốn kết luận benign/attack, người review phải tự xem body trong PCAP private và xác nhận câu hỏi riêng của tool; nếu chưa xem, chọn `u`.** Thiếu bằng chứng thì chọn `u`. Xong từng queue, chạy `status` rồi `finalize` với cùng `--source`/`--output`; `finalize` khóa hash quyết định nhưng **không cấp admission**. Có thể `unblind --source eve_novel --request-id <ID> --output <thư-mục-review>` sau khi đã quyết định ID đó để đối chiếu proposal. Không sửa quyết định cũ nếu bất đồng; mở vòng review mới riêng và truy vết bất đồng.

Sau human review, cần kiểm chứng độc lập danh tính/quy trình và semantics, gắn quyết định với `event_key` của **prepared dataset thực**, lập evidence-v2 manifest có capture + intent provenance + semantic review riêng, rồi chạy `scripts/audit-label-evidence.py` và corpus catalog gate hiện có. Công cụ review chưa tự chuyển self-attestation thành nhãn đủ điều kiện. Cần thêm nguồn/môi trường/campaign được cấp phép độc lập có cả benign/attack, split và live 207-feature parity trước formal training. Không phát campaign cùng lab chỉ để tăng số dòng.

207 feature hiện là hợp đồng **post-response**: status, latency, response bytes và các behavioral counts chỉ có sau response; không hợp lệ để chặn trước response. Causal profile lấy flow đã hoàn tất trước thời điểm request theo `available_at=max(EVE timestamp, flow.end+65s)`; không lấy flow tương lai của chính request. 18 dynamics dùng lịch sử tới request hiện tại. `InferencePipeline` dùng cùng spec `state_limits`/207 cột và từ chối implementation SHA khác, nhưng live bridge Rust, thời gian nhận event và query trước mask chưa được chứng nhận. Không tuyên bố realtime/production parity từ replay PCAP offline.

## Tiếp tục admission và capture khác target — 2026-11-02T08:54+07:00

Hai lượt AI-owned ba nguồn chạy liên tiếp trên **cùng lab loopback** đều khớp 54/54 Student audit + masked Nginx + Suricata EVE HTTP/flow; Suricata đọc PCAP thật **offline**, chưa phải sensor realtime đang chạy liên tục. Lượt mới `ai-training/.artifacts/eve3-1102c/` có 54 request và 42 target hash mới so với các lượt trước. Profile `novel-v2` chốt trước khi gửi, 30 target attack/hard-negative khác hai plan cũ, dùng nhiều endpoint/query/hard-negative mới; 3 campaign vẫn development một môi trường, không dùng làm validation/test. Masked Nginx có `query_string=null` ở 54/54 request; EVE v2 cung cấp numeric query từ packet trước redaction và khớp private Nginx 54/54. Đây là **parity của đường offline trong lab**, chưa chứng minh live production EVE adapter hoặc toàn bộ 207 feature tại inference. Flow EVE kết thúc/phát muộn tối đa 11,341s; chỉ dùng khi đã phát, không điền ngược thông tin tương lai.

Đã tự động lập hồ sơ 3 queue, tổng **162 pending request**: 54 hai nguồn cũ, 54 ba nguồn cũ, 54 ba nguồn mới; 48 request auth-boundary v1 vẫn cách ly. Từng `review-assist.jsonl` lưu **facts blind** (ID, SHA, nguồn, clock, method/status, sự hiện diện query, thiếu oracle) và `review-proposals.jsonl` lưu riêng claim từ runner + gợi ý cú pháp. Reviewer đọc facts/capture riêng tư trước, ghi nhận định độc lập, **sau đó mới mở proposals** để đối chiếu. File proposal không phải model prediction hay ground truth. Ở campaign mới, cue xuất hiện ở 9 request runner khai benign và chỉ 15/18 request runner khai attack; tự gắn nhãn từ cú pháp sẽ sai. Cả 162 vẫn `unknown`/`label=null`, 0 reviewer độc lập, 0 admission. Artifact mới: `ai-training/.artifacts/evidence_campaign_20261102/assist-old54-v2/`, `assist-new54-v2/`, và `ai-training/.artifacts/eve3-1102c/assist-v2/`; report ở mỗi thư mục pin SHA facts/proposals và queue. Raw query/body chỉ ở capture private; facts/proposals không ghi plaintext.

Audit bốn capture + bảy Student log lịch sử chưa sealed: **210 ID request mới khác nhau** (48 cách ly +162 pending), 78 target hash, 132 lượt lặp target, 0 va chạm với **227.619 ID** lịch sử được quét. Log lịch sử có cả setup/observations, không phải count request admission; sealed cohort không đọc nên dedup toàn cục chưa được chứng nhận. Tổng theo capture reports 75.150 lịch sử +210 mới = **75.360 request ghi nhận/2 triệu (3,77%)**; **0/2 triệu admitted**. 9 campaign ID development hợp lệ trong một lab, 3 campaign v1 cách ly, **0 campaign/môi trường đánh giá độc lập**. Mô hình GLU 9.675.784/207 và MLP 252.680 không đổi; formal train bị gate chặn đúng thiết kế.

Quy trình còn cần người review **khác collector** xác nhận semantic intent theo request, campaign và ngữ cảnh ứng dụng; POST thiếu body evidence trong audit/Nginx/EVE, exploit outcome cần oracle ứng dụng độc lập. Plan/response/status/alert và cú pháp không tự xác nhận. Sau review mới tạo evidence-v2 ledger, prepared dataset/provenance và chạy catalog admission; cần thêm campaign ở môi trường hoặc nguồn được cấp phép độc lập, cân bằng benign/attack, cùng live visibility contract trước study MLP/GLU. [Report](reports/ATTACK_EVIDENCE_20261101.json), [handoff](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 38. Không chạy train dài, mở holdout, chọn champion hay bật chặn.

## Capture ba nguồn trên lab AI — 2026-11-02T08:31+07:00

Đã khắc phục khoảng trống EVE của collector evidence: Nginx của lượt capture 01/11 chạy ở host, còn sensor PCAP chạy trong network namespace riêng. Lượt mới dùng Nginx AI-owned trong namespace, `tcpdump` bắt gói TCP loopback thật rồi Suricata đọc PCAP offline. Không sửa Student/Security. `ai-training/.artifacts/eve3-1102b/` giữ PCAP, EVE đã khử query/UA, hai log gốc private, report và queue. `correlated-v2/report.json` xác nhận **54/54 request ID** khớp Student + Nginx + EVE HTTP, 54 flow, 18 alert, 1 stats; 0 sai khác numeric query projection giữa Nginx lab private và EVE; timestamp client→EVE HTTP tối đa 0,708s. Flow được phát ra muộn tới 10,811s sau HTTP: giá trị flow chỉ là bằng chứng khi sensor thực sự phát, không được đưa ngược vào feature tại thời điểm request. Alert không phải nhãn.

Queue mới `eve3-1102b/review-three-source-v2/blind-review.jsonl` giữ **54/54 `unknown`, null-label, 0 admission**, liên kết hash dòng Nginx/Student/EVE HTTP và flow record; không chứa raw query/IP/payload. Tái kiểm chỉ đọc:

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --verify-existing --plan ai-training/.artifacts/evidence_campaign_20261102/plan-v1 \
  --lab ai-training/.artifacts/eve3-1102b/lab --capture ai-training/.artifacts/eve3-1102b/capture \
  --three-source ai-training/.artifacts/eve3-1102b/correlated-v2 \
  --output ai-training/.artifacts/eve3-1102b/review-three-source-v2 \
  --collector-source ai-training/.artifacts/evidence_campaign_20261102/collector-source-v3.py
```

Lượt cũ 54 hồ sơ hai nguồn vẫn pending; không gắn EVE mới ngược về các request đó. Ba campaign mới là development trên **cùng lab và cùng target variants**; không bổ sung môi trường hay syntax độc lập. Audit ba capture: 156 ID request khác nhau (48 cách ly + 54 cũ + 54 mới), 36 target hash, 120 lượt lặp target; 0 ID va chạm trong phạm vi 73.218 ID Student từ ba log *không sealed*. Cohort sealed không đọc và không có chứng nhận unique toàn cục của 75.150 request lịch sử. Tổng số request được ghi nhận theo các báo cáo capture là 75.306/2.000.000 (3,77%) nhưng **scale admitted 0/2.000.000**. Không coi count này là corpus đủ train.

Quy trình review mục dưới vẫn áp dụng: reviewer khác collector xem raw private request và ngữ cảnh ứng dụng trước khi mở planned intent; chỉ xác nhận nhãn nếu có bằng chứng ngữ nghĩa request-bound. EVE flow/alert, status 200/401 và planned label không tự phê duyệt intent hoặc exploit outcome. Queue mới chỉ thêm bằng chứng đối chiếu network. Formal feature profile 207 cột vẫn **chưa chứng nhận parity**: Nginx lab private query và EVE numeric projection nhìn thấy trước mask, còn edge production dùng mask khác. Không đưa capture mới vào training/inference chính thức cho đến khi contract quan sát được thống nhất và evidence-v2 admission qua gate. [Report](reports/ATTACK_EVIDENCE_20261101.json), [handoff](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 37.

## Tiếp tục 54 hồ sơ capture — 2026-11-01T11:45+07:00

**Chưa duyệt nhãn hoặc train:** 54/54 blind-review item đã được đọc lại từ plan/capture và hai log nguồn; tất cả vẫn `unknown`, `label=null`, `training_eligible=false`. Verifier hiện đối chiếu method, status, path + hash target, timestamp ba phía và SHA từng dòng. Bản source collector gốc cho plan-v2 được giữ riêng tại `.artifacts/evidence_campaign_20261101/collector-source-v2.py` đúng SHA đã pin (`3c6aad3e...`); dùng bản này khi kiểm capture cũ, không dùng source hiện hành đã được nâng cấp. Lệnh tái kiểm chỉ đọc:

**Model check không fit:** bundle pilot `scale_upgrade_20261030/pilot/residual_glu-bundle` là đúng mô hình 9.675.784 tham số / 207 đầu vào: ONNX SHA khớp report, inference batch 1 cho output hữu hạn, parity cũ trên 69.345 rows và exact resume đã ghi PASS. Bundle `partition_recovery_20261031/study/glu1024-bundle` là model **khác**, 9.541.640 tham số / 76 đầu vào, cùng MLP 219.144 đối chứng; hai bundle 76 cũng đọc được, hash khớp và inference hữu hạn. Tất cả là pilot/development, chưa có formal model được train trên corpus admitted hoặc live serving được nghiệm thu. Cổng `require_scale_dataset(prepared-v5)` vẫn từ chối vì chưa có 2 triệu admitted + independent calibration.

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --verify-existing \
  --plan ai-training/.artifacts/evidence_campaign_20261101/plan-v2 \
  --lab ai-training/.artifacts/evidence_campaign_20261101/lab-v2 \
  --capture ai-training/.artifacts/evidence_campaign_20261101/capture-v2 \
  --output ai-training/.artifacts/evidence_campaign_20261101/review-v3 \
  --collector-source ai-training/.artifacts/evidence_campaign_20261101/collector-source-v2.py
```

**Quy trình cho reviewer độc lập** (người khác collector; chỉ trong workspace riêng tư):

Artifacts `.artifacts/` bị Git ignore và chỉ tồn tại trên máy hiện tại; reviewer khác máy cần bản sao qua kênh riêng được phép, có checksum/kiểm quyền truy cập. Không đưa raw Nginx query, Student audit hoặc credential vào Git để thực hiện review.

1. Xác nhận lệnh trên trả `BLIND_QUEUE_REVERIFIED_NO_LABELS_APPROVED`, sau đó lấy từng `request_id` từ `review-v3/blind-review.jsonl`. Mỗi ID phải có đúng một dòng ở `lab-v2/access-lab.log` và `lab-v2/student-audit.log` với SHA như queue. Không sao chép raw query, IP, cookie hay credential ra báo cáo công khai.

   Để xem một request trong terminal riêng tư, đặt `REVIEW_REQUEST_ID` rồi chạy đoạn chỉ đọc dưới đây. Nó chỉ in method/path/query/status/timestamp, không in body, IP, user hay header; query vẫn có thể nhạy cảm và không được dán vào chat hoặc issue công khai.

   ```bash
   REVIEW_REQUEST_ID='ID_TRONG_BLIND_QUEUE' python3 - <<'PY'
   import json, os
   from pathlib import Path
   root = Path('ai-training/.artifacts/evidence_campaign_20261101/lab-v2')
   rid = os.environ['REVIEW_REQUEST_ID']
   for name in ('access-lab.log', 'student-audit.log'):
       with (root / name).open() as stream:
           found = [row for line in stream if (row := json.loads(line)).get('request_id') == rid]
       if len(found) != 1:
           raise SystemExit(f'{name}: cần đúng một dòng, thấy {len(found)}')
       row = found[0]
       print(name, {key: row.get(key) for key in
           ('timestamp', 'http_method', 'uri_path', 'query_string', 'status', 'status_code')})
   PY
   ```
2. Trước khi nhìn planned intent, xem request thực trong hai log và ngữ cảnh hợp lệ của ứng dụng. Ghi riêng kết luận semantic `attack` / `benign` / `unknown`, attack family nếu có, mức nhìn thấy payload và lý do gắn với event key. Query Nginx ở lab là dữ liệu private; Student audit đã mask và **không thay thế** query gốc cho semantic review. POST login không có body được xác minh trong hai log, nên thiếu bằng chứng thì giữ `unknown`.
3. Sau kết luận blind, mở `plan-v2/plan.json` để kiểm campaign/case/target hash đã đăng ký trước capture. Runner intent là provenance cần đối chiếu, không tự động là nhãn đúng. HTTP 200/401 hoặc Suricata alert không chứng minh intent hay exploit outcome. Giữ `exploit_outcome=unknown` trừ khi có oracle ứng dụng độc lập.
4. Lưu nhận xét và artifact semantic riêng, bất biến, request-bound; không sửa `blind-review.jsonl`. Reviewer ghi danh tính thật/đơn vị review, khác collector. Bất đồng hoặc thiếu dữ liệu giữ pending; không điền nhãn dựa trên model/rule. Khi có dataset + provenance bất biến, lập evidence-v2 ledger với capture, intent provenance và semantic artifact theo đúng `src/idps_ai/data/label_evidence.py`; chạy `scripts/audit-label-evidence.py` và catalog admission. Event key trong queue phải được bind lại với event key của dataset thực tế, không coi hash queue là ID model mặc định.

Hai capture mới đã được audit cùng nhau: **102 ID khác nhau, 36 target hash khác nhau, 66 lượt lặp target**, 0 ID trùng với **73.218 ID** trong ba log Student lịch sử *không niêm phong* đã chỉ định. Lặp target là request vật lý khác nhau, nhưng không phải độ đa dạng template mới. Log lịch sử có cả setup event; các ID đó không được cộng thành train rows. Cohort lịch sử đã khóa không được đọc, nên **chưa có chứng nhận dedup toàn cục** cho 75.150 request lịch sử. Artifact chỉ chứa count/hash: `.artifacts/evidence_campaign_20261101/lineage-audit-v2/report.json`.

Campaign tiếp theo phải đăng ký trước source/environment/time/seed/template và role; cần ứng dụng hoặc thời điểm độc lập, phiên benign/hard-negative/attack đủ sâu qua cửa sổ 10/60/300 giây, Student + Nginx + EVE với request ID/clock/capture SHA, và cùng khả năng quan sát query với edge. Tách một tập prospective sealed không dùng chỉnh model; 3 campaign hiện tại và 3 campaign v1 bị cách ly đều là development. Không chạy collector mới cho đến khi có target được cấp phép, reviewer độc lập và thiết kế nguồn EVE/feature parity rõ ràng.

## Thu thập HTTP có bằng chứng ngay từ lúc phát request — 2026-11-01T11:21+07:00

AI-owned disposable Student/Nginx lab `127.0.0.1:18881` đã chạy 3 campaign development theo plan có SHA được ghi trước khi gửi. Lượt đầu 48 request bị cách ly: 45/48 trả 401 do runner chưa đăng nhập, không đại diện cho hành vi ứng dụng. Đã sửa **collector AI** để đăng nhập bằng tài khoản fixture riêng và thu lại trên lab mới. Lượt đạt kiểm tra vận hành có **54 request ID duy nhất**, 54/54 khớp Nginx + Student audit về ID/method/status; 0 workload bị 401 chặn trước ứng dụng. Plan gồm 36 benign/hard-negative intent và 18 attack intent, nhưng đây là khai báo hành động của runner, **không phải 36/18 nhãn đã được người độc lập phê duyệt**. 54/54 exploit outcome vẫn `unknown`.

Review queue riêng tư `ai-training/.artifacts/evidence_campaign_20261101/review-v3/blind-review.jsonl` có 54 bản ghi null-label/unknown, SHA source lines và timestamp; không chứa IP, URI/query, UA, body hay password. Chênh lệch clock lớn nhất giữa client/Nginx/Student 0,924s; 30 attack/hard-negative target khác nhau không lặp giữa campaign. Cả 3 campaign thuộc **một lab, một thời điểm và development-only**; không lập validation/test từ chúng. Future holdout chỉ được đặt chỗ, chưa sinh traffic hoặc score. Nginx lab query view vẫn khác edge production mask, EVE chưa thu trong lượt này; cần kiểm parity trước khi đưa vào feature profile hiện hành.

**Admission mới vẫn 0 request; 0 benign/0 attack được review độc lập; 0 campaign đánh giá độc lập.** Cần reviewer độc lập kiểm semantic intent theo capture và plan, sau đó tạo dataset/provenance bất biến + review-v2 evidence ledger và chạy corpus admission gate. Chỉ khi có thêm campaign/source/holdout hợp lệ mới study MLP/GLU. Xem [report](reports/ATTACK_EVIDENCE_20261101.json), handoff và ledger 06 mục 34. Fixture tạm đã dừng Nginx/Student/DB; raw và failed pilot giữ private để truy vết.

## Rà soát 64 hồ sơ và workbook ModSec-WP — 2026-11-01T10:53+07:00

**Formal vẫn NOT_READY; lượt này thêm 0 request admission, 0 positive/0 benign có nhãn độc lập, 0 campaign độc lập được xác minh.** Đã đối chiếu SHA của 64 locator SOC-MLD với raw access log, tạo `ai-training/.artifacts/attack_evidence_20261101/soc-pending-review-final-v2/pending-dossiers.jsonl` (private, mode 600). Cả 64 vẫn unknown/pending; 64 GET, 63 phản hồi 4xx, 1 phản hồi 2xx, 3 có query. Không tìm được EVE HTTP match theo IP/method/target trong ±2s; điều này không chứng minh thiếu traffic. Operator labels thiếu request ID và timezone nên campaign/intent/outcome đều chưa được bind. Hồ sơ chỉ lưu cấu trúc HTTP, SHA và locator; reviewer phải đọc bản capture riêng tư và cung cấp bằng chứng độc lập trước khi quyết định. Split SOC-MLD gốc có 38 attack-instance ID chung, gồm 1.852 train và 1.214/1.220 test rows: không dùng split này để tuyên bố tổng quát hóa.

Đã tải và kiểm SHA workbook ModSec-WP v2 từ [Zenodo DOI](https://zenodo.org/records/21872151), CC BY 4.0 theo API chính thức. Audit streaming 108.883 dòng chỉ thấy 27.686 transaction ID và event key khác nhau; 81.197 dòng lặp, 20 transaction ID có nhãn mâu thuẫn (60 dòng) và 25 request view có nhãn mâu thuẫn. Workbook ghi 108.823 dòng năm 2024 và 60 dòng năm 2026; 18.474 biểu diễn method/URL/body khác nhau. Đây là số dòng/ID/view, **chưa xác minh physical request**. Nhãn publisher có 96.286 attack rows và 12.597 normal rows; toàn bộ chưa được admission do thiếu trail nhãn từng request, campaign IDs và xử lý xung đột. Artifact private `modsec-wp-audit-final/report.json`; không đưa raw payload/PII vào Git. Nguồn e-commerce Ba Lan 2025 có 178.939 log rows theo nhà phát hành, được ghi metadata-only vì không có nhãn intent theo request và URI đã bỏ query. Không có study/training/threshold tuning mới.

## Review nhãn và nguồn attack — 2026-11-01T07:36:28.147641+07:00

**Formal vẫn NOT_READY; không chạy trainer dài.** SOC-MLD mới đã audit198.082 HTTP observations, nhưng không có nhãn request-bound mới đủ tin cậy; 38 attack-instance IDs chung train/test và rule/time fallback phải được review. Không dùng precomputed future-window/SID features. Raw/provenance giữ private, không tạo traffic mới hoặc cộng observations thành request mới.

Corpus gate hiện yêu cầu evidence review v2 theo từng event: capture + intent provenance + independent semantic review, thêm application oracle nếu khẳng định success/failure. Pending/unknown vẫn null, boolean-only approval không còn mở formal. Tool `scripts/audit-label-evidence.py` kiểm integrity/binding; không tự chứng nhận sự thật hoặc tạo nhãn mới. `scripts/audit-soc-mld.py` audit pinned ZIP offline trong resource envelope, không execute code publisher; kết quả active đã có, không cần chạy lại.

Catalog đã cập nhật source screening và điều kiện balanced independent acceptance. Giữ kín toàn bộ holdout, gồm148WCP case files; scale-admitted0/2M, champion=null, formal_command=null. Xem [report](reports/ATTACK_EVIDENCE_20261101.json), [hợp đồng nhãn](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md) và ledger06 mục32. Kết quả model cũ giữ làm bằng chứng, không lặp HPO trên validation đã exposed.

Kiểm chứng cuối: **211 pytest PASS, 0 skip**; Ruff/format/compile/canonical PASS; **53/53 gate kỹ thuật legacy PASS**, corpus formal **NOT_READY/0 eligible** (exit 3 đúng thiết kế). Giữ nguyên SHA của **2.941 file** cũ và source/config freeze trong final test; không sửa hai Web. Handoff format 10, ledger 32.

## Hiện trạng dữ liệu và model — 2026-11-01T06:48:58.523006+07:00

**Chưa sẵn sàng train chính thức hoặc chọn champion.** Đã thêm audit nguồn publisher-benign open-appsec có Apache-2.0: 811.129 record ngoài reserved, 756.548 signature biểu diễn HTTP khác nhau, 54.391 trùng/190 quarantine; 44.437 numeric projections. 148 website case files dự phòng chưa đọc/project/score. Không coi số signature là verified physical requests hoặc automatic training admission.

Frozen weights/threshold MLP 219k và GLU 9,54M trên 13.290 validation/160 case: GLU 5 FP=0,0376%, MLP 174 FP=1,3093%. Ngược với hard negatives lab cũ, GLU FPR 10,73%/MLP 0%. Mô hình có điểm yếu theo miền; nguồn mới chỉ benign nên Recall/F1/PR-AUC không xác định, chưa champion. Trong 139 syntax-benign subset: GLU 2 FP, MLP 34 FP. Giữ toàn bộ primary sample, không retune threshold hoặc HPO từ kết quả này.

**198 pytest PASS/0 skip**, 53 gate kỹ thuật legacy PASS; Student/Security/contracts/Docker giữ nguyên, 2.682 protected SHA giữ nguyên. 0 optimizer update thực mới, không training dài hạn/enforcement. Organization X vẫn unknown; tổng lab 75.150 HTTP giữ nguyên, scale-admitted 0/2M. Cần positive/nhãn/campaign và validation độc lập trước study tiếp.

Xem [report](reports/GENERALIZATION_QUALITY_20261101.json), [handoff format 9](FINAL_TRAINING_HANDOFF.json), [data protocol](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md), ledger 06 mục 31. Root private `ai-training/.artifacts/generalization_quality_20261101/CURRENT_WORK.json` giữ trạng thái tiếp tục. Existing baseline/checkpoint cần frozen source/config/data/environment đúng hash, không force-resume package hiện hành. `formal_command=null`; các lệnh/snapshot phía dưới là lịch sử, không phải authorization chạy formal.

Công cụ mới đọc offline, không gửi traffic đến website gốc: `scripts/import-wcp-http.py` yêu cầu pinned source/provenance/key/protocol và output mới; `scripts/evaluate-wcp-http.py` yêu cầu frozen model registry, validation only và từ chối ghi đè. Không cần chạy lại audit/evaluation đã hoàn tất. Job dữ liệu/eval chạy user cgroup 4 CPU/MemoryMax 16 GiB; ceil toàn luồng≤8 CPU/16 GiB theo runbook.

## Nâng cấp 9,68M / mục tiêu 2M — nghiệm thu kỹ thuật, dữ liệu còn thiếu — 2026-10-30T15:52:59+07:00

**Đã kiểm chứng phần kỹ thuật; chưa hoàn thành mục tiêu dữ liệu/production.**
Chỉ sửa AI và docs. Corpus vẫn **69.345 request duy nhất, một lab**, nhãn scripted
intent; không thêm request hoặc môi trường. Re-extraction v5 không phải dữ liệu mới.
Chưa có review nhãn độc lập, **0 request được admission cho formal scale**; mục tiêu
2M đa dạng chưa đạt. Không nhân bản hoặc cộng các bản projection/cache vào số lượng.

| Giai đoạn | Trạng thái cuối phiên |
| --- | --- |
| Data | Catalog/provenance/replay/holdout checks đã có; corpus 2M và shared-scaler assembly nhiều môi trường còn thiếu |
| Features/architecture/algorithms | v5/207 cột, thêm 18 dynamics; residual SwiGLU **9.675.784** tham số thực; AdamW/smoothing/dropout/warmup-cosine |
| Tests/readiness | **134/134 pytest PASS, 0 skipped**; **53/53 gate kỹ thuật PASS** trên cùng 69k |
| Pilot | 4 neural candidates × 2 epoch, fresh-process resume và reference khớp chính xác; ONNX mọi 69.345 vectors/candidate PASS |
| Evaluation | Calibration 3 campaign, selection 6 campaign; fit không nhìn validation; test quality giữ kín; tree32 iteration đối chứng |
| Integration | Offline shadow512 request PASS, không gọi Web/firewall; live/TLS/receipt-time/response NOT_RUN |
| Formal/champion | NOT_RUN / chưa chọn; không tự chạy ca dài và chưa đủ data gate |
| Cleanup | Chỉ cache tái tạo được: giải phóng 498.14 MiB; giữ raw/checkpoint/log/evidence cũ |

AP selection cao nhất ở lượt ngắn: **gated_residual**. Main challenger
AP **0.997228**, recall **98.92%**, FPR **0.823%**,
p95 ONNX model-only **5.363 ms**. Model lớn không mặc định tốt hơn;
khác biệt thuật toán/regularization không phải thí nghiệm riêng tác dụng số tham số.
Một lab và sáu nhóm selection không chứng minh FPR/zero-day/production generalization.

[Báo cáo đo thực](reports/SCALE_UPGRADE_20261030.json), [handoff hiện hành](FINAL_TRAINING_HANDOFF.json),
ledger06 mục25. Tất cả snapshot cũ bên dưới là lịch sử; không dùng readiness/source
cũ cho source hiện hành hoặc force-resume checkpoint khác contract.

## Bàn giao corpus và mô hình sâu revision 4.1 — 2026-10-30T09:08:21+07:00

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

Ứng viên lớn cho thí nghiệm tiếp: **gated_residual** (AP 0.999077, precision 97.61%, recall 99.16%, FPR 0.996%).
Residual đối chứng: AP 0.999165, precision 97.64%, recall 99.55%, FPR 0.986%. Các số đo trên validation còn sơ bộ
vì cùng tập này được dùng để calibration và so sánh ứng viên. Tăng tham số không
bảo đảm tốt hơn; không kéo dài train chỉ để đủ thời gian.

Manifest hiện hành: [FINAL_TRAINING_HANDOFF.json](FINAL_TRAINING_HANDOFF.json).
Xem [báo cáo](reports/PRETRAIN_EXPANDED_20261030.json) và mục 24 của ledger 06. Các snapshot bên dưới là lịch sử.

Lệnh ca tiếp do người dùng tự chạy, **chưa được thực thi**:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-expanded-session.sh gated_residual
```

## Chuẩn bị mạng sâu/corpus 60–80k — revision 4.1

Phạm vi phiên mới chỉ AI và docs. Đã triển khai projection v2 / 189 đặc trưng cùng ba
mạng sâu (248.072/294.717/445.448 tham số), giữ math/checkpoint/cgroup/ONNX contract.
Corpus mới thu từ Student export của HEAD hiện hành, Nginx và Suricata thật;
45 campaign / 27-9-9 groups, 480 giây/campaign và gap 620 giây. Hard-negative payload
identities được tách như attack views, không chỉ kiểm request ID khác nhau.

Source v4/148 cột cũ và các report/pilot trước không được ghi đè hoặc force-resume.
Revision 4.1 tránh gọi hai vector khác thứ tự/số cột bằng cùng contract. Model sâu
chỉ là candidate; không hứa chống overfit, thêm zero-day detection hoặc train
đủ 150 phút. Pilot 5 epoch phải so fresh-process resume với reference và ONNX toàn
bộ vector; test quality giữ kín. Model/threshold không được promote tại đây.

Runbook mới ở đầu [README](README.md). Handoff hiện hành đặt tại
`ai-training/FINAL_TRAINING_HANDOFF.json`; bản có cùng tên trong
`upgrade_20261028` thuộc experiment lịch sử. Ca dài dùng
`train-expanded-session.sh`, chỉ do người vận hành khởi động sau khi gate/pilot
hoàn tất. Trạng thái đo cuối ghi trong report mới và ledger 06 mục 24.

## Nâng cấp sau chẩn đoán — 29/10/2026

Ca11,616giây trước đó không báo lỗi optimizer/checkpoint/ONNX. Model nhỏ và
early stopping giải thích thời gian; chất lượng vẫn hạn chế:59/148cột hằng số,
query payload counters bằng0, campaign có nhiều lặp. Không ép ca đó chạy tiếp.

Đợt mới bổ sung shared numeric EVE bridge, feature/normalizerv4, policy corpus
sâu hơn và weighted residual candidate có train/validation loss history.
30campaign có plan riêng, nhóm18/6/6,480giây thật/campaign và gap620giây thật;
thêm CRUD, đọc public, UA thường đa dạng, batch hợp lệ và hard negatives.
Canonical1.0, Student/Security và artifact cũ giữ riêng. Đây vẫn là lab một host,
scripted intent và tài khoản giả; cần dữ liệu người dùng/traffic đại diện sau này.

Các alias URL decode về cùng payload được kiểm bằng identity hash. Bản trùng ở
holdout sau giữ làm context nhưng không được nhận nhãn training/evaluation;
evidence có danh sách HMAC request key và lý do loại. Không sửa log gốc hoặc
hạ floor để vượt readiness. Corpus cũ được re-project chỉ là phép chẩn đoán.

Re-projection PCAP cũ là phép chẩn đoán riêng: cùng residual5epoch đạt recall
validation95,39%, khi bỏ projection query/URI ở cùng weights/threshold còn26,93%.
Threshold dùng cùng validation nên kết quả sơ bộ; không tính đây là corpus mới,
không dùng để mở khóa formal gate30campaign. AE và weighted loss không mặc định
tốt hơn supervised residual. Thiếu actor/flow có thể tăng false positives mạnh;
phải đọc cả FPR trong sensitivity, không chỉ recall.

Quy trình/lệnh mới ở đầu [README](README.md#workflow-numeric-query--29102026).
Ca tiếp dùng `train-query-session.sh`; ca `train-first-session.sh` bên dưới đã
terminal. Modelv4 cần cùng bridge trước redaction khi chạy thật; Rust serving,
TLS/receipt-time parity và phản ứng IPS chưa được nghiệm thu trong luồng AI.
Report/ledger mới nhất sẽ ghi số liệu thực của corpus/pilot và trạng thái gate.

**Kết quả cuối corpus mới:**46.230request,198.765observations,30campaign,48/48gate
PASS; feature rows46.134 sau96holdout-overlap exclusions. Split27.738/9.150/9.246,
nhóm18/6/6; canonical1.0/profilev4/148cột. Pilot4ứng viên5epoch, exactresume và
ONNX46.134/46.134từng modelPASS. Residual không trọng số có APvalidation cao nhất
0,99875,recall99,23%,FPR0,747%; đây là candidate cho ca tiếp, chưa champion.
Lệnh `train-query-session.sh` dùng residual seed17/patience8/100epoch/max150phút,
8CPU/16GiB; **ca formal mới chưa chạy**. Chất lượng test vẫn niêm phong và chưa
nghiệm thu live. [Báo cáo](reports/PRETRAIN_UPGRADE_20261029.json), ledger06 mục23
ghi source/hash và các lần kiểm tra thực; các snapshot dưới đây là lịch sử.

## Ca residual đầu tiên — 29/10/2026

Đã thực hiện yêu cầu kiểm data rồi chạy ca tối đa **150 phút** trên source `8171289`.
Data gate mới **35/35 PASS**, dataset **19.275 request / 148 features** giữ nguyên hash.
Ca chạy **17:21:05–17:21:17 +07:00**, hoàn thành sau **11,616 giây**, dừng tại
**epoch 14 / step 2.534** do `early_stopping` (patience 8); checkpoint tốt nhất
ở **epoch 6 / step 1.086**. Không ép chạy tiếp để lấp đầy ngân sách thời gian.
Quota thực **8 CPU / 16 GiB**, MemoryHigh 15 GiB, swap 0; có job nền/log riêng và
sleep inhibitor trong lúc chạy. Đã kiểm checkpoint và ONNX parity **19.275/19.275 PASS**.

Validation-only: precision **90,83%**, recall **44,20%**, FPR **0,943%**, AP **0,7757**;
threshold chọn trên cùng validation nên kết quả sơ bộ. **Không mở test metrics,
chưa chọn champion hoặc triển khai Rust/live/enforcement**. Chưa nghiệm thu endurance
150 phút. Xem [báo cáo ca residual](reports/FORMAL_RESIDUAL_20261029.json) và [ledger06 mục22](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md#22-ca-train-residual-đầu-tiên--29102026). Các mốc “chưa train” ngày28/S0 phía dưới
là lịch sử. Run early-stopped là terminal; không force-resume bằng script ca đầu.

Cập nhật 28/10/2026: luồng AI dùng `ai-features-3` / `ai-normalizer-3`, 148 cột,
canonical event v1.0 giữ nguyên. Báo cáo ngày27 là lịch sử của corpus hai nguồn;
không dùng checkpoint/report cũ để resume với source hoặc dataset mới.
Báo cáo hiện hành: [PRETRAIN_PILOT_20261028.json](reports/PRETRAIN_PILOT_20261028.json), đóng băng sau capture/readiness/pilot; 19.275 request, 35 gate checks và77 testsPASS.

## Luồng ba nguồn thật

1. `lab-start` build bản Student riêng từ Git, DB PostgreSQL rỗng và tài khoản giả.
   Không đọc `.env`, DB hoặc credential của dịch vụ đang dùng.
2. `lab-capture-eve` chuyển Nginx và HTTP client vào **user/network namespace riêng**.
   Backend được nối bằng Unix socket relay riêng. IP127.0.0.10–24 là địa chỉ bind
   thực trong namespace; không sửa timestamp/IP để tạo split. Host networking,
   firewall và cấu hình Student/Security không bị thay.
3. `tcpdump --immediate-mode -i lo` chỉ bắt TCP18881 trong namespace. PCAP riêng tư
   chứa credential/cookie **của fixture giả**: không đưa vào Git hoặc chia sẻ công
   khai. Thư mục0700, PCAP0600, giới hạn512MiB; STOP hoặc lỗi không cấp readiness.
4. `decode-pcap` chạy Suricata8.0.3 offline, một worker, dùng bản config dẫn xuất và
   nguyên bộ9SID của repo. Giữ cả HTTP/flow bình thường, alert và stats. Suricata
   gửi EVE qua Unix socket0600; bộ lọc chỉ giữ response header `X-Request-Id`, mask
   query/path động và UA trước khi ghi `eve.json`. Không ghi cookie/token/body.
5. `lab-finish` đóng băng snapshot, labels/provenance, correlation, split, scaler,
   vectors, readiness, capacity và rule baseline validation. Chế độ ba nguồn dùng
   `three_source_policy.yaml`; corpus ngày27 không qua được gate mới này.
6. `pilot` chạy từng model2epoch rồi **tiến trình mới** resume đến5epoch, so đúng
   weights/Adam/RNG/sampler/scheduler với reference 5 epoch liên tục, export ONNX.
   Chỉ tính metric trên validation; test chỉ được replay để kiểm parity, không
   dùng nhãn test để chọn threshold hoặc chọn model.

## Quyền bắt gói và AppArmor

Máy hiện tại dùng Podman rootless qua lệnh `docker`. `--network host` cùng
NET_RAW/NET_ADMIN không cấp quyền trên host namespace. Cách đã chọn không cần
sudo để mở packet socket trong namespace riêng. Tuy nhiên AppArmor profile
`tcpdump` đã chặn tín hiệu từ Codex (`peer=chatgpt`). Người dùng đã tự bổ sung:

```apparmor
signal (receive) peer=chatgpt,
```

vào `/etc/apparmor.d/local/usr.bin.tcpdump`, reload profile và dừng các probe cũ.
Đây là thay đổi quyền **nhận tín hiệu dừng**, không cấp capture host, không tắt
AppArmor. Máy khác chỉ cần thao tác này nếu kernel audit xác nhận cùng lỗi.
Muốn thu hồi: xóa đúng dòng bổ sung rồi reload profile bằng quản trị hệ thống.
Không chép binary hoặc tắt sandbox để né profile.

## Corpus và feature availability

- 15 campaign × 1.280 request workload, cộng setup/logout: **19.275 request**; nhóm 9/3/3.
- Mỗi campaign420giây thực; các campaign trong cùng band chạy đồng thời, mỗi
  identity có lịch sử riêng. Hai khoảng nghỉ 620 giây thực giữ embargo300giây ở
  hai phía cutoff. Ba role và payload/UA views được phân band trước khi thu.
- Có đọc/ghi hợp lệ, HEAD/OPTIONS bị policy từ chối,404, role denial, tìm kiếm
  Unicode/O'Connor/percent/thuật ngữ kỹ thuật và singleton login typo; attack
  families gồmSQLi/XSS/traversal/command/scanner/auth burst/bulk-read intent.
- `edge_masked_v1`: mọi adapter đều bỏ query lexical và query-original counters,
  chuẩn hóa path cùng cách. Không chọn view raw giàu hơn từ Suricata/lab. Các
  cột query thiếu dữ liệu được ghi đúng trạng thái, không dựng payload giả.
- Flow là **context của flow client đã hoàn tất trước đó**, không là byte/packet
  riêng của request hiện tại. Chỉ dùng flow kết thúc trước request ít nhất65giây
  (closed timeout60giây + biên dự phòng), lookback record300giây. `available_at=max(timestamp EVE, flow.end+65s)` kết hợp hai ràng buộc mà không cộng timeout lần hai; timestamp gốc không bị đổi. Những request warmup vẫn
  missing; không dùng counter đóng flow tương lai để lấp đầy100%.
- Đây là replay theo packet/event time. Receipt-time delay, TLS/vantage, arrival
  reordering và port Rust/live phải được nghiệm thu riêng khi triển khai.

Đồng bộ masking tránh train bằng thông tin không tồn tại khi chạy thật, nhưng
cũng làm một số họ payload trong query không thể phân biệt chỉ bằng metadata.
Rule engine có thể quan sát raw request trong bộ nhớ; AI metadata không được
hứa thay thế bộ rule đó. Query/body model cần telemetry được phê duyệt riêng.

## Ba ứng viên

| Model | Kiến trúc | Vai trò |
|---|---|---|
| MLP cơ sở |148→32→8 | Supervised baseline |
| Autoencoder |148→32→148 | Chỉ fit benign; reconstruction score không phải xác suất attack |
| Residual tabular |148→64→64+skip→8 | Candidate có sức biểu diễn cao hơn; chưa mặc định tốt hơn baseline |

Residual có14.216tham số FP32, dùng ReLU/softmax/CE và Adam hiện có. Params, activations, gradient và optimizer giữFP32; affine reductions tích lũyFP64 rồi roundFP32 trong cảNumPy/ONNX. Cách này xử lý sai lệch BLAS/MLAS gầnzero, vẫn giữtolerance rtol1e-5/atol1e-6. Arithmetic contract ghi trong checkpoint; không force-load các checkpoint của attempt trước bằng source mới. Gradient được
đối chiếu finite difference; optimizer/checkpoint/ONNX có test. Đây là kiến trúc
nhỏ lấy cảm hứng từ residual learning, không phải bản tái lập nguyên xi benchmark
[ResNet cho tabular data](https://arxiv.org/abs/2106.11959). Byte-CNN/TCN vẫn cần
corpus/sequence contract tương ứng; không đưa LLM/Torch/CUDA vào pipeline này.

## Tài nguyên cho ca sắp tới — cập nhật sau pilot

Cấu hình hiện hành là **8 logical CPU**, `CPUQuota=800%`, `Nice=10`,
`MemoryMax=16GiB`, `MemoryHigh=15GiB`, `MemorySwapMax=0`. NumPy/BLAS/OpenMP/
NumExpr dùng tối đa8luồng; ONNX intra-op8, inter-op1 với execution mode sequential
để không nhân hai pool8×8. `--cpus` là alias của `--max-threads`, chấp nhận6–8CPU
trên máy16luồng; bộ guard vẫn kiểm trần nửa CPU affinity và đọc lại cgroup.

16GiB là mức người dùng chỉ định rõ. Hệ điều hành nhìn thấy32.440.909.824byte RAM,
vì vậy16GiB tương đương khoảng**52,96% RAM OS-visible**, không phải chính xác50%.
Guard ghi tỷ lệ thực tế, không đánh đồng32GB với32GiB. Trần16GiB là giới hạn job;
working set không được cấp phát sẵn16GiB. Nhiệt/độ mượt ca dài vẫn cần đo riêng.

Đã chạy **77tests PASS** và probe systemd guard với**0optimizer step**; không
train lại corpus19.275request, không chạy ca chính thức. Báo cáo mới ở
[RESOURCE_GUARD_20261028.json](reports/RESOURCE_GUARD_20261028.json). Các metric và
thông số2CPU/12GiB trong report pilot trước đó giữ nguyên ý nghĩa lịch sử.

Nguồn guard đổi nên đã chạy lại35data-readiness checks, tạo
`dataset-ready/readiness-resource8/readiness.json`. Bản `readiness-final` cũ,
`dataset-ready/prepared` và toàn bộ`pilot-ready` vẫn giữ nguyên byte. Handoff và
script hiện dùng readiness-resource8; checkpoint pilot cũ không được force-resume
bằng source mới. Ca đầu là một experiment mới.

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-first-session.sh
```

Ở mốc 28/10, lệnh này **chưa được thực thi**; ca đầu đã chạy ngày29 và dừng sớm như mục cập nhật đầu trang. Mặc định100epoch, patience8, tối đa150phút,
checkpoint300giây; đạt đích/early stopping sớm thì dừng. Nếu run mới đã cólatest
thì script tiếp đúng run tương thích. Không lặp dữ liệu để đủ số giờ.

## Những gate vẫn riêng

`READY_FOR_OFFLINE_PILOT` không là production certification. Corpus vẫn là lab
loopback với tài khoản/dữ liệu giả, scripted intent, một topology và ít campaign
holdout; chưa có independent human realism review hoặc traffic cloud. Cần thêm
realistic sessions, campaign độc lập, TLS/receipt-time parity, FPR/incident-level
review và shadow trước khi chọn champion hoặc bật phản ứng. Không chạm Rust,
firewall, dashboard hay service config trong luồng AI này.

Xem [README](README.md), [report lịch sử27/10](reports/PRETRAIN_20261027.json) và
[ledger06](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md). Raw/key/Parquet/weights/PCAP
chỉ nằm trong `.artifacts/`, không ở Git; kho artifact chung chưa được cấp.

Lệnh ca đầu lịch sử: `bash ai-training/scripts/train-first-session.sh`. Run đích đã early-stop ngày29; không dùng lại để ép học thêm cùng run.

Artifact được duyệt: `dataset-ready/prepared`, `dataset-ready/readiness-resource8/readiness.json` và `pilot-ready/` (bản readiness-final gốc vẫn được giữ). Xem `.artifacts/upgrade_20261028/FINAL_TRAINING_HANDOFF.json`. Thư mục `dataset`, report `readiness` cũ và `pilot` là các attempt đã fail hoặc stale và đã được dọn theo yêu cầu. Các lệnh NEXT_COMMANDS cũ đã xóa; chỉ dùng script/handoff hiện hành.
