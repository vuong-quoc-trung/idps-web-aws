# Nhiệm vụ 01 — Project reconnaissance & master plan

**Khảo sát ngày 13/11/2026, khoảng 20:03 ICT. Chỉ khảo sát và lập kế hoạch.**
Branch `feature/ai-idps-shadow-integration`, HEAD `47a6a3c47d89cc92800ed1f3565061d4147668e9`.
Kết luận: **400K tham số khả thi; 400K mẫu TRAIN có chất lượng và năng lực đa nguồn chưa được chứng minh. Ưu tiên hợp đồng dữ liệu, nhãn, correlation và đánh giá độc lập trước training.**

Đây là bản tổng hợp cho mục tiêu mới; không sửa registry, quyết định lịch sử hay quyền thực thi. Không khởi chạy/dừng dịch vụ, training, capture, deploy, firewall; không sửa hai Web hoặc xóa artifact. Các kết quả thử nghiệm dưới đây là bằng chứng đã lưu, trừ những kiểm tra read-only được ghi rõ là thực hiện trong khảo sát này.

## 1. Current State

| Thành phần | Trạng thái có bằng chứng |
|---|---|
| Runtime tại máy này | `ss`, process inventory, system/user units, Docker/Podman không cho thấy ứng dụng IDPS đang phục vụ, container đang chạy hoặc job training đang hoạt động. Docker daemon vẫn hoạt động. Không suy rộng sang AWS/máy nhóm chưa truy cập. |
| Snapshot mới nhất | `.local-dev/demo-session.json` trỏ tới session `629663954966`; wrapper còn ghi RUNNING nhưng guard ghi **INTERRUPTED / monitor signal 15 lúc 17:08:39 ICT 13/11**. Heartbeat cũ không phải dịch vụ live. Không tự restart. |
| Student Web | Spring Boot 4.1.1/Java 25, React/TypeScript/Vite; PostgreSQL 16. Request attribution kiểm trusted proxy; audit JSONL có request ID, source instance và HMAC. |
| Security Web | Rust/Axum/Tokio/SQLx, PostgreSQL 17, frontend riêng; ingest/normalize, rule detection, AI metadata, correlation, incident/proposal/audit và actuator nftables. |
| Luồng demo đã có | Gateway Suricata namespace `18782` → NGINX `18780` → Student; AI đọc telemetry Unix syslog bất đồng bộ; Rust nhận audit/NGINX/EVE/AI và áp Hybrid Policy. Admin Security ở loopback `3001`. Gateway không có nghĩa mọi traffic host đều được sensor quan sát. |
| Model phục vụ được cấu hình | **Request Intelligence v2 frozen step3072**, `588→64→64→64→64→8`, **50.696 tham số**, strict `score > 0.8826237916946411`. Hiện không có process serving để gọi là model đang chạy. |
| Feature contract live | 76 numeric bounded + 512 hashed character features; profile `selected_headers_no_body`, body không quan sát. Demo và installer Security-host có projection khác nhau: installer không gửi query/body. Không mặc định offline HTTP, demo và VM có cùng coverage. |
| Correlation hiện có | NGINX tự tạo request ID, chuyển vào Student và response; EVE response-ID cùng `(sensor_instance, flow_id, tx_id)` và HTTP consistency. Không join bằng IP/time. `MATCHED` hiện yêu cầu đủ ba nguồn; partial/ambiguous/late được ghi riêng. |
| Hybrid hiện có | `LOG_ONLY / ALERT / REVIEW / PROPOSE_BLOCK`; max rule risk rồi cộng điều chỉnh AI/behavior có giới hạn. AI high một mình chỉ ALERT. PROPOSE không tự gọi firewall. Model/hash/profile/threshold v2 được pin trong worker và policy. |
| Enforcement | Mặc định `ENFORCEMENT_MODE=OFF`; `.env` đọc chọn lọc cho thấy `AUTO_BLOCK=false`. Actuator đã có IPv4 allowlist, bảo vệ host/gateway/upstream, TTL≤300s, cooldown30s, rate limit<10 BLOCK/phút và audit. Chưa chứng nhận host enforcement từ khảo sát này. |
| Acceptance gần nhất | Run r7 ngày 11/11: local functional/resource gates PASS, nhưng **release PARTIAL**: máy B thật còn PENDING, manual block/unblock/TTL/nftables còn PENDING_APPROVAL. Đây không phải acceptance của working tree hiện tại. |
| AWS | Có thiết kế và bộ cài host/VM; chưa tìm thấy bằng chứng deploy AWS hoàn tất. Cloud sensor/resource policy, TLS, capacity và restore còn phải nghiệm thu. |

Nguồn chính: [registry](../ai-training/MODEL_STRATEGY.json), [worker](../scripts/ai-shadow-worker.py), [correlator](../scripts/three_source_core.py), [Rust correlation](../security-web/src/three_source.rs), [hybrid](../security-web/src/hybrid.rs), [firewall](../security-web/src/firewall.rs), [r7 evidence](../.local-dev/demo-acceptance-20261111-r7/final-status.json), [host installer scope](../security-web/deploy/ai-shadow/README.md).

**Kiểm tra trực tiếp trong phiên này:** toàn bộ **84/84 tệp** của bundle v2 khớp manifest `b90383c5…`; payload `arrays.npz` và `state.json` của v2, GLU207 cuối và publisher200K cuối khớp checkpoint manifest. Đọc header tensor xác nhận kích thước kiến trúc, không inference/train. Không chạy lại pytest/build/E2E hoặc mở sealed holdout; hash đúng không chứng minh chất lượng model.

**Working tree và tài nguyên:** có 5 script sửa sẵn: `integration-guard.py`, `rolling-resource-policy.py`, `dev-up-and-verify.py`, `hybrid-system-acceptance.py`, `idps-demo.py`. Hiện launcher có thể xin toàn bộ **16 CPU/24 GiB**, DB containers có quota riêng 4 CPU/2 GiB mỗi container, Java heap4GiB; guard cho RAM tối đa32GiB. Commit trước đã nâng cutoff lên100°C và bỏ thermal pause trung gian; tài liệu90°C cũ không phản ánh code. Còn có seed/reset tài khoản demo trong launcher: không được dùng launcher đó như deployment/migration production. Giữ nguyên các thay đổi này trong nhiệm vụ01, đưa việc đối soát thành prerequisite.

Máy khảo sát: Core Ultra9 285H,16 logical CPU, khoảng30GiB RAM; MemAvailable khoảng22GiB, filesystem còn126GiB. **Ngân sách nhiệm vụ tương lai vẫn≤8 CPU/16GiB tổng workload**, không lấy cấu hình vật lý làm quyền tăng tài nguyên. Kiểm kê1.710 tracked files; artifact AI khoảng23,75GiB, `.local-dev`2,01GiB, `.team-verify`6,04GiB logical, chưa gồm dependencies/build trees. Đây không phải dung lượng có thể xóa. Catalog release có269 entries checkpoint/ONNX, không phải269 model độc lập.

Profile AI tương lai đề xuất bắt đầu0,25–1core, BLAS/ONNX1thread, tăng sau pilot nhiệt bền; rolling80°C pause/throttle, emergency≤90°C và thấp hơn hardware critical, resume có hysteresis/cooldown. Đây là profile cần kiểm chứng ở T03, không phải thay cấu hình demo hiện tại. Tính cả containers ngoài scope vào ngân sách tổng; mất sensor/watchdog phải dừng workload do mình quản lý, không dừng ứng dụng người dùng.

Phạm vi: đã kiểm kê cây repository/artifact, đọc luồng vận hành và AI/data trọng yếu, báo cáo/manifest lịch sử và trạng thái runtime. Chưa đọc lại từng dòng raw HTTP/PCAP, xác minh mọi checkpoint lịch sử hoặc audit từng dòng toàn bộ UI/business code; số liệu nguồn lớn được ghi là audit lịch sử, không giả là census mới.

## 2. Reusable Assets

| Tài nguyên | Bằng chứng và cách sử dụng |
|---|---|
| Frozen Request v2 | Baseline/rollback chính;120.435 TRAIN views theo metadata, nhãn publisher. Tái dùng encoder/privacy, loader/export/parity và inference worker. Không chuyển120.435 thành physical requests hoặc attack GT. |
| GLU207 step652 |9.675.784 params;41.607 train rows/41.585 unique views,2epochs. Rehash payload PASS. Tái dùng temporal features/causal replay/watermark và resume; không ghép weights207 vào encoder588. Cần đủ input hợp lệ; không có independent attack recall. |
| Baseline nhỏ/cây | Deep MLP252.680, gated-residual450.056, residual17.992 và histogram gradient boosting. Pilot207 cũ: gated AP0,999526, tree FPR0,107%, GLU AP0,997228; cùng lab/exposed selection, không đủ chọn champion. Hợp lý để đưa small MLP/tree vào đối chứng mới. |
| Publisher100K/200K |100K pilot:2.667 TRAIN views, EVAL FPR6,52%.200K cuối: **21.331 accepted SILVER records →17.588 views; TRAIN15.890/CAL848/EVAL850**,10epochs/2.490updates. Không phải Frozenv2. EVAL recall94,11% nhưng **FPR11,14%** ở CAL-balanced threshold; fixed0,5 FPR0,29% nhưng recall44,99%. Giữ admission index/checkpoint; không promote weights theo F1. |
| V3/body/normalization | Tái dùng46 body-syntax features, body state/privacy, Oracle receipts, collision diagnostics. Full-v3 không chứng minh cải thiện; frozen-adapter1.984 trainable giữ DEV nhưng body detection0/4 tại ngưỡng khóa. Normalization study bị REJECT. Dùng làm kết quả âm/ablation, không tiếp tục từ giả định đã thắng. |
| Grounded corpus | Union236 receipts/219 Oracle-supported labels theo audit; profile strict mới giữ74 records, TRAIN48records/**42views**. Đây là pilot đã exposed, không phải toàn bộ GT mới; review độc lập còn pending. Oracle nội bộ hợp lệ vẫn hữu ích cho research nếu ghi đúng scope. |
| Run10M tạm hoãn | SQLite đọc read-only có **15.902 receipt/request hashes**,496templates; tất cả BRONZE,1.216rows có conflict;11.186 TRAIN rows không conflict **chưa phải qualified**. DSL server xác nhận valid/rejected filter, không thực thi/Oracle exploit; không có ba nguồn thật trong nhánh capture này. Dataset NOT_QUALIFIED, optimizer actual-data0; kiến trúc10.065.928 params mới là random-tensor preflight. Tái dùng durable receipts/resume, không tự resume hoặc đếm thành attack GT. |
| Hạ tầng dữ liệu/training | SQLite cursor cùng transaction, versioned shards, source/code/config hashes, exact/near conflict graph, aliases, protected roles, partial-label objective, Adam/RNG/sampler checkpoints, watchdog độc lập và ONNX parity. Cần sửa sampler tail và kiểm lại guard trước dùng cho mục tiêu mới. |

Nguồn: [model history](03_AI_MODEL_AND_TRAINING_PLAN.md), [publisher evaluation](../ai-training/reports/FINAL_LOCAL_MODEL_EVALUATION_20261110.json), [200K accounting](../ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1/release-accounting.json), [v3](33_REQUEST_V3_FROZEN_BACKBONE.md), [normalization](21_SCALED_NORMALIZATION_RESULTS.md), [10M stop](../.local-dev/large-request-2m-20261110-r1/POSTPONED.json), [DSL capture](../ai-training/scripts/large-request-workflow.py).

**Nguồn lớn — số liệu audit lịch sử, chưa cộng gộp uniqueness:**

| Nhóm | Số lượng được ghi nhận | Quyết định |
|---|---:|---|
| WAFv2 publisher TRAIN |1.924.461rows;1.612.017 exact representations,192 representations trái nhãn | Tái kiểm cho auxiliary publisher task; thiếu physical ID/time/campaign và attack intent. |
| SR-BH / WAMM |907.815 /704.665rows; WAMM chỉ312.241 text representations | Cùng lineage/derivative; tránh cộng hai lần, giữ nguồn/weak-label semantics và exposed roles. |
| Open-appsec legitimate |811.129 nonreserved records;756.548 retained signatures | Benign-domain stress theo quyền/scope cũ; không tự chuyển148 reserved case files vào TRAIN. |
| SOC-MLD / ModSec-WP |198.122 access lines /108.883rows nhưng ModSec chỉ27.686 transaction IDs | Cần tái kiểm request binding/leakage; ModSec nhiều rule rows/request, không dùng rule làm GT độc lập. |
| Kyoushi / CSIC |408.477 access lines /97.065 transcripts | Kyoushi slice positive-only; CSIC anomaly có invalid benign,626 identities cross split. Dùng đúng task; không làm test độc lập nếu đã exposed. |
| OrganizationX / OpenCitations |211.178 distinct observations /100.000-row prefix | Unlabeled: tham khảo phân phối/biểu diễn; không suy benign từ200/no-alert. |
| Biblio-US17 | Bản RAW+LABEL có quyền dùng còn thiếu | Chưa tính capacity; không tải hoặc hứa dùng. |

Chi tiết lineage/license và phạm vi nằm trong [source inventory](34_AI_IDPS_2M_DATA_SCALING_READINESS.md) và [machine report](../ai-training/reports/AI_IDPS_2M_DATA_SCALING_READINESS_20261109.json). Mọi nguồn cần giữ phiên bản/quyền dùng; không phân phối raw/session material.

## 3. Final Architecture

**Chọn một model nhỏ đa nhánh, chung trunk và một bundle triển khai; không ensemble các điểm GLU/v2/publisher.** Dùng lại Python feature pipeline/worker và Rust policy/actuator. Không cần thêm dashboard hoặc inference service mới ở bước này.

```text
NGINX ────────┐
Suricata ─────┼→ validate + provenance + request correlation + causal watermark
Student Audit┘          ├→ canonical HTTP một lần + context riêng + masks
                        │                → ONE masked model → score/family/support
                        └→ rule evidence theo request ────────┐
                                        Hybrid Policy ←──────┘
                                  PASS / ALERT / REVIEW / BLOCK
                                      audit → guarded actuator
```

**Correlation và tính nhân quả.** Khóa request theo namespace producer/deployment + trusted edge request ID. Sensor dùng `(instance/boot, flow_id, tx_id)`; response-ID và method/path/status chỉ xác nhận match, không lấy similarity thay identity. Với nguồn đơn chưa có edge ID, giữ event-local transaction key, không tự ghép với request khác. Dedup theo event/transaction identity, giữ nhiều evidence types có liên quan; nhiều alert trên một flow không biến thành nhiều request. Repository đã dùng flow/tx đúng hướng; [EVE documentation](https://docs.suricata.io/en/suricata-8.0.2/output/eve/eve-json-format.html) phân biệt flow và transaction.

Lưu `event_time`, `received_at`, `decision_time`, watermark/version và evidence IDs. Chỉ dùng dữ liệu đã sẵn có tại decision time; prior completed flow không được đưa ngược vào request trước đó. Giữ history warm-up/incomplete. Late data tạo revision/idempotent audit, không thêm sample hoặc cộng risk lặp. Timeout phải đo theo ingest delay thực, không lấy2s hiện tại làm chuẩn AWS. Ambiguous identity không được fused hoặc auto-block.

**Feature và missingness.** HTTP method/URI/content chung chỉ encode một lần với provenance từng nhóm trường; request context, sensor/network context và application auth/authorization context có namespace riêng. Bắt đầu từ76+512 và46 body-syntax đã có; chọn lọc từ207 causal features sau khi bỏ phần lặp. Raw secret/body không lưu; numeric projection ở producer khi cần. Rule SID/count/severity/prediction không đi vào AI core đầu tiên: policy giữ evidence này để tránh circular labels và tính hai lần cùng payload.

Có source mask, field-group mask, trạng thái `OBSERVED / EMPTY / MISSING / PARSE_ERROR / TRUNCATED / LATE / UNSUPPORTED` và chất lượng history. Tensor thiếu có thể dùng zero placeholder **chỉ sau khi mask rõ và train đúng cách**; không tạo log hoặc feature quan sát giả. Audit-only không thể biết payload không được ghi. Không đủ quan sát thì trả unsupported/abstain và REVIEW theo policy, không trả benign chắc chắn.

Huấn luyện source dropout trên mẫu có nguồn thật, đủ7mask `N,S,A,NS,NA,SA,NSA`; recompute history từ phần quan sát còn lại. Giữ cùng partition cho mọi mask của một request; không đếm7 bản thành7 mẫu độc lập. Đánh giá cả mất nguồn tự nhiên, mất theo burst, delayed/corrupt logs và mask-only/source-only controls. `000` không score và không chứng minh an toàn. Public HTTP rows là content-only auxiliary observations, không giả gắn nhãn NGINX capture.

**Ngân sách mạng minh họa, chưa phải feature contract đã khóa:**

| Khối dense có bias | Kích thước | Parameters |
|---|---:|---:|
| HTTP chung |634→384|243.840|
| Sensor context |32→64|2.112|
| Audit context |24→64|1.600|
| Fusion với16 availability/quality inputs |528→256|135.424|
| Shared hidden |256→64|16.448|
| Task heads |64→9|585|
| **Tổng** ||**400.009**|

9logits có thể là8logits benign+7behavior families với partial supervision, và1auxiliary publisher-anomaly logit. Chỉ xuất family khi có supervision/support phù hợp; unknown family không ép nhãn. Bật/tắt nhánh bằng mask sau activation để bias không giả nguồn hiện diện. Chọn số feature thực ở T02/T05; nếu khác thì điều chỉnh width để khoảng350–450K, không padding/tensor chết cho đủ400K. Kiểm gradient của mọi tensor. Giữ loss/optimizer/checkpoint hiện có khi phù hợp; nhánh/mask/auxiliary head cần implementation và exporter mới, không giả đã hỗ trợ.

**Nhãn và reuse weights.** Receipt-bound semantic Oracle/review hỗ trợ intent/family; publisher chỉ supervise auxiliary publisher task; heuristic/teacher BRONZE không được biến thành trusted intent. Unknown có thể dùng cho reconstruction/representation thí nghiệm riêng nếu pilot chứng minh lợi ích, không gắn benign. Confidence phải kèm evidence basis/task, không là điểm tự phong. Tái sử dụng kỹ thuật trước; distillation/warm-start là một ablation có kiểm soát, không cộng/chuyển weights giữa các feature spaces khác nhau. Đối chứng supervised-only giúp phát hiện negative transfer từ weak labels.

**Hybrid Policy đề xuất:** PASS là tiếp tục xử lý theo coverage/health đã khai báo, không là khẳng định request sạch. Rule mạnh vẫn ALERT/REVIEW khi AI thấp/mất; AI high đơn lẻ ALERT/REVIEW. Mỗi evidence group chỉ được tính một lần; max rule theo nhóm, không majority vote AI+NGINX+Suricata cùng payload. BLOCK chỉ sau gate kiểm định: trusted client attribution, evidence request-bound đủ mạnh, ngưỡng khóa từ CAL, nguồn/correlation fresh, IP không protected, TTL/rate/cooldown, audit và rollback. Thiếu nguồn không tự làm giảm risk; mask chưa được chứng minh an toàn cho BLOCK chỉ có quyền ALERT/REVIEW. `PROPOSE_BLOCK` vẫn là trạng thái trung gian cần tách khỏi BLOCK đã thực thi/readback.

Luồng hiện tại là **post-response/post-observation**: có thể chặn request sau, không chặn ngược request đã xong. Inline first-request prevention cần một milestone và latency/failure contract khác, không nằm trong việc thay model này.

## 4. Risks & Gaps

1. **Thiếu tập học đa nguồn đáng tin và test mới.** Không có global ledger chứng minh400K unique eligible TRAIN. Grounded cohorts nhỏ/đã exposed;200K chủ yếu publisher,10M receipts chỉ DSL BRONZE. Không thể tạo Suricata/Audit giả cho public data. Giữ các holdout cũ đúng role; tạo evaluation campaign/environment mới trước khi fit.
2. **Leakage/shortcut.** Request identity, representation, feature view và campaign là bốn đơn vị khác nhau. WAMM/SR-BH overlap, HMAC khác key, mixed-label collisions, near-template và method/body/source imbalance còn tồn tại. Near-similarity là dấu hiệu cần kiểm, không tự đồng nghĩa cùng physical request; tránh graph over-merging loại hết data và tránh approximate index miss được coi là zero overlap.
3. **Calibration/quality chưa đạt.** Publisher200K FPR11,14%, Brier≈0,297/ECE≈0,321; last-batch loss thấp không đại diện full loss. Sampler cũ kết thúc epoch bằng1.750normal views, cuối1.024 cùng group. V2 cross-source publisher-NORMAL flag34,45%; GLU0/27benign FP không chứng minh FPR≤1%. Chưa có paired holdout hợp lệ để kết luận200K hơn v2.
4. **Missing-source và semantics chưa có end-to-end.** Correlator hiện chỉ MATCHED3/3; request-only v2 khác GLU complete contract. Một số raw features mất khi canonical redaction; phải thiết kế producer projection và thông tin provenance. Không tự cộng vector588+207 chứa trường trùng.
5. **Operational gaps.** Guard và tài liệu lệch; quota DB ngoài parent scope có thể vượt ngân sách tổng. Demo relay làm NGINX thấy loopback, không đủ authority block IP máy B; TLS trên AWS cần sensor tại đoạn traffic quan sát được sau termination, không coi encrypted capture là HTTP coverage. IPv6 actuator chưa hỗ trợ.
6. **Migration không chỉ thay file weights.** Worker/registry, Rust AI decode/hybrid và installer pin model v2. Cần versioned contract, migration tương thích, bundle rollback và test nguồn dữ liệu thực. Không nới validation để model mới lọt qua.

**Khả thi và chi phí — ước lượng có điều kiện:**

| Hạng mục | Căn cứ / ngân sách |
|---|---|
|400K tham số| FP32 weights≈1,6MB; weights+Adam m/v≈4,8MB chưa gồm gradient/buffers/cursor. Không cần GPU từ bằng chứng hiện có. |
|400K TRAIN rows|706float32/input minh họa≈**1,05GiB**; còn indices, validation, copies và history. Dùng shards/memmap và bounded caches, worker8GiB trước, tổng≤16GiB.400K là TRAIN, CAL/test riêng; không tính aliases/epochs/dropout views. |
|Sản lượng dữ liệu|200Kpositions→15.890TRAINviews:7,945%. Ngoại suy cơ học cần≈**5,03M positions** để có400K cùng loại TRAIN; nguồn WAF hiện chỉ1,924M và các tập cũ overlap. Không dùng tỉ lệ này dự đoán trusted intent yield. |
|Chuẩn bị|Job200K lịch sử5.273s≈88phút tại ceiling20% một core, bao gồm reuse100K; protected-near audit≈1,71tỷpairs. Pilot admission10K170s≈58,7candidates/s ở25% một core. Đây là hai pipeline khác nhau; doubling dữ liệu không bảo đảm doubling thời gian. Dự trù vài giờ→nhiều ngày tùy dedup/GT; đo10K trước. |
|Training|Publisher cuối493s cho158.900presentations/50.696params. Ngoại suy theo presentations×parameters cho400K×10epochs/400.009params≈**27,2giờ ở cùng quota20% một core**; linear ideal1–4cores≈5,4–1,4giờ, chưa benchmark. Study khác có throughput tốt hơn nhiều, nên khoảng này chỉ budget scenario. Pilot đo cả feature/optimizer/checkpoint/thermal rồi thay ETA. |
|Chia phiên|Data shards≤25K, training slices≤30–60phút; mỗi slice kết thúc bằng checkpoint/next cursor. Tổng run có thể kéo dài nhiều phiên nhưng mỗi nhiệm vụ hữu hạn. Không launch một job nhiều ngày dưới tên “một phiên”. |
|Inference|Gate đề xuất model-only p95≤10ms, feature+queue+score p95≤50ms ở workload đã khóa; correlation wait báo riêng. So cùng hardware/quota/input với baseline. ONNX1thread trước, kiểm batch nhỏ; [ONNX docs](https://onnxruntime.ai/docs/performance/tune-performance/threading.html) cho phép giới hạn thread và tắt spinning để giảm CPU/power. |
|Local/cloud compute|Local không phát sinh tiền thuê cloud; điện chưa đo, không gán giá điện giả. Không mua GPU/train AWS trong roadmap mặc định. AWS dùng inference-only. |

**Ngân sách AWS tham chiếu:** kế thừa demo x86_64 trong [kế hoạch AWS](14_AWS_SHADOW_DEMO_PLAN.md), t3a.large8GiB chỉ là candidate thấp tải. Giá Linux us-east-1 hiện niêm yết$0,0752/h; xlarge16GiB$0,1504/h. Với40GBgp3 **giả định**$0,08/GB-tháng và1IPv4$0,005/h: khoảng$61,75/tháng hoặc$6,41/40giờ cho large; xlarge khoảng$116,64/tháng hoặc$9,42/40giờ. Giả định730giờ/tháng, disk giữ cả tháng, IPv4 chỉ tính giờ sử dụng ở cột40giờ; chưa thuế/logs/backup/domain/transfer. [EC2 pricing](https://aws.amazon.com/ec2/instance-types/t3/), [EBS pricing example](https://aws.amazon.com/ebs/pricing/), [IPv4 pricing](https://aws.amazon.com/vpc/pricing/).

Credit Standard có thể throttle khi hết credit; cần đo tải liên tục cả Java/DB/Suricata trước chốt instance, không chỉ model400K. [AWS Standard behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html). Chưa chọn region thực hoặc tạo tài nguyên. Cloud policy phải dùng CPU/memory/queue/health phù hợp guest, không giả thermal sensor và không tắt bảo vệ của laptop.

## 5. Execution Roadmap

Các bước dưới là **đề xuất, chưa thực thi**. Mỗi bước có manifest/source/config hashes, evidence PASS/FAIL, artifact/checkpoint và next action; FAIL hoặc thiếu bằng chứng thì không mở gate phụ thuộc. Thời lượng dự kiến30–120phút/phiên, riêng xử lý lớn lặp bằng shard/slice hữu hạn; không tự nối cả roadmap. Không sửa source artifacts/roles để hợp thức hóa kết quả.

| Task | Phụ thuộc | Phạm vi một phiên / đầu ra | Gate PASS; trường hợp còn lại FAIL hoặc BLOCKED |
|---|---|---|---|
|**T02 Contract + asset ledger**|T01|Chốt counting units, nhãn/task/source mask, field provenance và ledger tham chiếu tài nguyên hiện có; kiểm một frame≤10K metadata/records nonsealed, không capture/train.|Mỗi trường có producer/availability/decision-time; mỗi sample có nguồn/role/evidence; unknown nêu rõ; không cộng overlap hay đổi holdout.|
|T03 Resource contract|T02|Đối soát5script sửa sẵn; tạo profile AI riêng≤8CPU/16GiB tổng, reserve4GiB, giới hạn DB/jobs ngoài scope; kiểm controller bằng fixtures.|Quota/affinity/memory/descendants đúng; cảm biến lỗi, watchdog mất, nhiệt cao đều fail-safe; checkpoint/resume không auto-retry safety stop. Không revert thay đổi người dùng mù.|
|T04 Correlation tests|T02|Replay cô lập từ evidence hiện hữu: keep-alive, tx collision, duplicate, restart, late/reordered, spoofed ID,1/2/3nguồn; output proof ledger.|0false joins trong suite; ambiguity không fused; idempotency và prefix invariance PASS. Không traffic mới.|
|T05 Encoder contract|T04|Chọn feature thực, masks/body states/history và golden vectors; map local/host/AWS producers.|Không fabricated observations, không secret/label/ID leakage; cùng evidence cho cùng vector; missing khác empty; chỉ nguồn quan sát được được dùng.|
|T06 Admission pilot|T03,T05|≤10K existing records, tier/task decisions, incremental exact/template/near audit và yield/time/RSS.|Resume/rebuild deterministic; conflict quarantine rõ; không saturated/unchecked bucket được đánh dấu sạch; actual TRAIN count đúng.|
|T07 Evaluation protocol|T06|Khóa campaign/environment split, train/dev/cal/test, seven masks, controls, metrics/CI và preregister thresholds.|0known identity/group/near leakage qua roles theo contract; CAL không test; cohort chưa đủ support phải BLOCKED.|
|T08 Capture pilot|T03–T07|Một campaign được phép,≤1Krequests hoặc≤20phút, matched benign/attack workflows qua ba nguồn; giữ defenses bật.|Receipts+source identity+semantic Oracle đọc lại được; attempt/outcome tách; health/drop counters rõ. Tấn công bị chặn vẫn là attempt có nhãn, không cần vô hiệu bảo vệ.|
|T09 Model + optimizer|T05,T06|Implement masked branches/partial+auxiliary losses; fixture gradients, parameter count và checkpoint next-update proof.|~350–450K trainable hữu ích; mọi tensor có gradient khi input/loss tương ứng; fresh-process exact resume; unknown labels không gradient supervised.|
|T10 ONNX/export|T09|Exporter và golden parity7masks/invalid inputs; pin artifact schema.|rtol1e-5/atol1e-6 với native, identical threshold decisions trừ tolerance boundary được ghi; invalid/000 không benign.|
|T11 Bounded model pilot|T07–T10|Một budget nhỏ≤10Keligible views,≤1Kupdates/arm; frozenv2/reference, smallMLP/tree và masked candidate; mỗi arm một phiên.|Finite loss/state, resource PASS, report per-source/mask và auxiliary/no-aux ablation; không chọn trên test. Nếu không hơn baseline thì giữ model nhỏ hơn.|
|T12[k] Qualified-data shards|T06,T08,T11|Mỗi phiên≤25Kpositions hoặc30–60phút; acquire/convert/admit một shard, ledger+resume cursor.|Unique/label/coverage tăng thật; không duplicate weighting, giữ heldout. Dừng expansion khi yield/novelty thấp; chưa đủ400K thì báo số thật.|
|T13 Dataset freeze|T12 đủ chất lượng|Manifest TRAIN/CAL/test, toàn bộ roles/aliases/tier/masks, licenses, freeze code/env.|Count400K chỉ khi đủ eligible canonical TRAIN; thiếu thì freeze bản nhỏ có tên đúng và báo unmet target; không training chính thức với count giả.|
|T14[k] Final training slices|T11,T13|Một seed/budget đã khóa, mỗi phiên≤60phút; shard/sampler/RNG/optimizer checkpoint.|Continuation giống next-update reference; config/data không đổi; budget/thermal/memory PASS. Không HPO tự kéo dài.|
|T15 Calibration|T14 complete|CAL-only probability calibration nếu đủ nhãn và threshold cho action/mask; lock comparator/support.|Không đọc test để tuning; mask ít benign→no-block/abstain. Fit auxiliary publisher không hiệu chuẩn attack probability.|
|T16 Blind comparison|T15|Một lần test độc lập chung,7masks, same-request paired baseline, rule-only/AI-only/hybrid và stress faults.|Gate chất lượng dưới đây PASS; test thiếu coverage→INCONCLUSIVE, không promote. Giữ báo cáo lỗi và cost/latency.|
|T17 Shadow integration|T16|Versioned bundle/registry/worker/Rust contract ở môi trường riêng, rollback pointer; không bật blocking.|HTTP→log→score→policy→DB đúngID,1/2/3nguồn, AI outage vẫn rule; package hash và rollback load PASS.|
|T18 Local E2E + rollback|T17|Session bounded: GET/POST/auth, source loss, queue/rotate, restart/recovery, rollback old bundle.|Student/Security regressions PASS; fresh evidence không tái dùng READY cũ; expected decisions, bounded resources,0unexpected actuator calls.|
|T19 Manual response lab|T18|Client disposable namespace, manual approve/block/unblock/TTL/readback và protected-IP negative cases.|Kernel action+audit khớp; expiry/restart/rollback/cooldown/rate PASS; host/management/upstream không bị chặn.|
|T20 Bounded auto canary|T19 + quality gate|Một scope/IPset và thời hạn giới hạn đã được giao; dry-run trước, rồi canary với kill switch.|0protected/wrong-target blocks, false-block budget đạt, automatic rollback khi sensor/model/identity invalid. Không coi fixture là real-block proof.|
|T21 AWS package + sizing|T18; T20 nếu bật IPS|TLS/cleartext sensor placement, private DB/admin, IAM/secrets, systemd, cloud resource policy, cost và restore plan.|Local VM/package test PASS, manifest deploy reviewable, capacity budget đo được; không copy demo account seeding vào AWS.|
|T22 AWS shadow acceptance|T21, nhiệm vụ deploy riêng|Deploy candidate, TLS/auth/network/3nguồn/recovery/backup-restore; rollback drill.|Current target checks PASS; migration additive; canary đủ support mới cân nhắc enforcement AWS trong nhiệm vụ riêng.|
|T23 Cleanup inventory|T18,T22 ổn định|Dependency/reference graph và dry-run delete candidates; giữ champion+previous bundle, canonical data/splits/code/env, evidence và resume state cần thiết.|Restore từ bản giữ lại PASS, không referenced/sealed artifacts trong delete list; chờ task cleanup cụ thể rồi mới xóa.|

**Quality gates đề xuất để khóa tại T07, không phải thành tích hiện tại:**

- Primary: attack-intent recall/PR-AUC, precision và FPR tại operating point CAL; family/method/body/environment/mask riêng, uncertainty theo campaign. Báo coverage/abstention và tính miss trên mọi request được kỳ vọng bảo vệ, tránh cải thiện giả bằng bỏ mẫu khó.
- Shadow promotion: recall gain≥5 điểm phần trăm so small baseline mạnh nhất trên mask có support, paired campaign95%CI lower bound>0; không family/mask trọng yếu nào giảm>2pp; FPR upper95%≤1% cho strata được claim hỗ trợ. Gate quá ít mẫu→INCONCLUSIVE, không đổi ngưỡng từ test. Các con số là mục tiêu kỹ thuật cần khóa trước fit.
- BLOCK có gate riêng: trên trusted/matched scope, benign false-block upper95%≤0,1%,0protected-IP violations, explicit attribution và rollback PASS. Theo công thức zero-event IID,0/299 benign chỉ xấp xỉ upper1%;0/2.995 mới xấp xỉ0,1% (one-sided95%). Request cùng campaign không độc lập; cần nhiều campaign và phân tích cluster, không sinh lặp để đạt con số.
- Đối chứng frozen models giữ thresholds hiện có; baseline retrain dùng cùng TRAIN và cùng CAL rule. GLU chỉ chấm subset thật có contract207; thiếu input báo N/A. Không so metric khác cohorts để kết luận thắng.
- Calibration/threshold chia theo7mask chỉ khi đủ support; nếu không dùng policy bảo thủ không BLOCK. Head family không có nhãn thì trả UNKNOWN. Policy rule-only vẫn hoạt động khi AI mất, nhưng không coi mất logging là an toàn.
- Hiệu năng: đo end-to-end trên cùng workload; p95/model và p95/pipeline theo budget mục4, queue/drop và delayed sources tách riêng; checkpoint fresh-process, bounds CPU/RAM/nhiệt và fault recovery đều PASS.

Cleanup chỉ bắt đầu sau một khoảng quan sát đã khóa trước (đề xuất≥7ngày có traffic đại diện, không chỉ7ngày lịch trống) và restore drill. Ưu tiên kiểm tra download caches/bản sao trong `.team-verify`, intermediate shards và superseded checkpoints; giữ original manifests/provenance, source pins, license evidence, frozenv2 rollback và bản final tái lập. Dung lượng logical trùng chưa phải reclaimable bytes: phải kiểm hardlinks/references và có danh sách xóa cụ thể trước task xóa.

## 6. Next Task

**Đề xuất giao đúng T02: “Khóa hợp đồng dữ liệu đa nguồn và ledger tài nguyên kế thừa cho mục tiêu400K”.**

Một phiên read-only đối với vận hành; chỉ tạo artifact AI/data nhỏ. Đầu ra: (1)contract có schema/version cho request identity, observed features, seven masks, label task/confidence và decision time; (2)ledger tham chiếu model/data/checkpoint theo SHA, role/tier và trạng thái REUSE/CONVERT/REVERIFY/EXCLUDE; (3)capacity table phân biệt source rows, physical receipts, unique representations, canonical TRAIN và từng source mask. Dùng metadata hiện có và frame≤10K nonsealed; không mở lại holdout/test để chọn dữ liệu.

PASS khi mỗi kết luận có evidence/path, unknown không bị lấp bằng giả định, mọi nhãn giữ đúng semantics và phụ thuộc protected roles được liệt kê. Capacity có thể kết luận “chưa đủ”; đó là kết quả khảo sát hợp lệ. Không sửa Student/Security, không chạy launcher, không train/capture/deploy/enforcement. T02 kết thúc bằng bàn giao T03; không tự thực thi roadmap.

**Điểm dừng nhiệm vụ01:** chỉ lưu báo cáo này; mọi hành động triển khai ở trên chờ nhiệm vụ tiếp theo. Không cần quyết định bổ sung của chủ dự án để hoàn tất bản khảo sát. Region/domain/ngân sách AWS và phạm vi canary chỉ cần chốt khi tới milestone tương ứng.
