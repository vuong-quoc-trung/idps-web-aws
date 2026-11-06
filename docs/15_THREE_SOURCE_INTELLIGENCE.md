# Three-source intelligence — kết quả local ngày 2026-11-06

Milestone đã tạo được đường đi từ HTTP thật qua ba nguồn tới frozen GLU207,
PostgreSQL/API và dashboard. Phạm vi đã kiểm là gateway plaintext local và consumer
post-response hữu hạn. Chưa có bằng chứng chất lượng phát hiện mới, phục vụ liên
tục độ trễ thấp hoặc host luôn giữ dưới 80°C. Không training, đổi threshold,
enforcement, AWS, commit hoặc push trong milestone này.

Máy kiểm thử đã dừng foundation và workload do milestone khởi động sau khi lấy
bằng chứng; dữ liệu/volumes được giữ. Các cờ LIVE/READY dưới đây chỉ năng lực đã
kiểm, không khẳng định process vẫn chạy lúc đọc báo cáo.

## A. Suricata

- Suricata **8.0.3**, binary SHA256
  `6ebe94439533bedac44ec8dc6ab634a061ca4d874101252364f4d7907187ca27`.
  Chín rules giữ nguyên, SHA256
  `e2d792c7bd17e75b9adece83ce5b6d43efda28d93a23a896b9f178ff65dcb654`.
- Thư viện runtime cũ đã có đủ; thiếu `LD_LIBRARY_PATH` khiến lần kiểm trước kết
  luận dependency chưa chính xác. Helper mới download/extract 34 Ubuntu packages
  vào runtime riêng, ldd/version PASS, cùng binary/rules hash, đã chạy thêm HTTP
  thật. Đây là fresh extraction trên cùng host, chưa phải clean machine test.
- Không có quyền capture host bằng sudo/capabilities hiện tại. Gateway18782 dùng
  Unix relays qua private user/network namespace, Suricata passive nghe loopback
  TCP18881, rồi chuyển tới Nginx18780 và Student thật. `systemd --scope` giữ cgroup
  quota/watchdog và cho phép quyền user namespace vốn có của caller; không thay
  AppArmor, firewall hay OS protection.
- Run4 có 12 EVE HTTP, 20 flow và 3 alert; một probe dùng runtime mới bổ sung
  một HTTP/command-shaped alert. Không coi các số này là coverage của toàn host.
  Traffic bypass gateway hoặc TLS opaque thiếu HTTP evidence; relay không giữ
  network tuple gốc của client. Multi-client attribution chưa được kiểm.

Code: [collector](../scripts/three-source-shadow.py),
[runtime helper](../scripts/bootstrap-suricata.py).

## B. Correlation

Nginx sinh request ID, truyền tới Student và response. Sensor lấy ID từ **response
header thực**, cộng sensor generation/flow_id/tx_id và kiểm method, route, status.
Route fingerprint có khóa được tính trước privacy redaction. Không ghép IP/time
đơn thuần. Flow alert không tx_id chỉ là context; alert có tx chỉ gắn đúng transaction.

Acceptance thật có 12 receipts: single, bốn concurrent, ba request keep-alive,
sensor stop/restart và privacy probe. Keep-alive cùng flow `1245616393568927`,
tx0/1/2 khác nhau; SQLi-shaped SID1000002 chỉ tx1, command-shaped SID1000005 chỉ
tx2. TCP threshold SID1000001 không tx vẫn flow-level. Sensor dừng nhưng Student
trả200 và correlation MISSING_SOURCE; sau restart EVE có lại. Không chạy exploit.

11 tests bổ sung chứng minh conflict→AMBIGUOUS, thiếu ID không fallback IP/time,
late/out-of-order/duplicate, generation collision, redaction collision và causal
prefix. Late là cờ riêng trên trạng thái correlation, arrival trễ >2s bị loại khỏi
GLU. Duplicate exact idempotent; dữ liệu conflict không được nâng thành match.
Delayed/out-of-order là fixtures, không giả thành các packet mới.

Phát hiện một lỗi chuyển tiếp thực: alert đã qua parser cũ có physical receipt ID;
replay qua parser mới tạo thêm **một alert** ở ranh giới migration. Alert này được
giữ, không xóa lịch sử. Helper reconciliation chỉ alias receipt khi file identity,
cursor generation, byte offset và raw-line hash khớp receipt cũ:256 records,
255 aliases mới. Replay sau đó giữ nguyên alert count4→4; backend restart cũng
không tăng count. Không suy ra unversioned records có stable ID khi thiếu evidence.

Code: [correlator](../scripts/three_source_core.py),
[live acceptance](../scripts/verify-three-source.py),
[tests](../scripts/test-three-source.py),
[migration helper](../scripts/reconcile-suricata-identities.py).

## C. Historical training

Kiểm **41,607 train rows, 41,607 unique request keys** bằng observations và native
producer snapshots, không đọc sealed holdout. Cả ba nguồn có native ID tương ứng
cho toàn bộ41,607rows; Suricata ID đến từ response header. Không có duplicate mapping
trong phần đã kiểm. Không suy coverage từ feature khác0.

- **41,433** triplets nhất quán HTTP.
- **174** PATCH `/api/faculties/[id]`: Student405, Nginx403, EVE403; ID/method/route
  khớp. Chưa chứng minh ghép nhầm request; cũng chưa chứng minh nguyên nhân dispatch
  làm status đổi. Không tự sửa các rows này hoặc công nhận response semantics đúng.
- Historical EVE có flow_id cho41,607rows nhưng **không giữ tx_id**. Không thể làm
  lại kiểm tra transaction như live cohort. Chưa decode lại PCAP gốc.
- **36,443** rows có previous completed client-flow context, tái dựng đều đúng frozen
  SQL, **5,164** thiếu flow có explicit missingness. Flow không phải byte counters
  của chính request. Tie-break SQL là available_at DESC, timestamp DESC, event ID ASC;
  lỗi tie-break ở phiên bản auditor đầu đã được sửa, không quy nhầm thành dataset bug.
- Saved tensor512 chronological train-prefix rows ×207float32 **bit-exact**,
  max absolute error0, implementation fingerprint/spec/source hashes khớp.

405/403 cùng4xx và route không phải auth nên khác biệt cụ thể này không đổi current
status-family/auth-failure features theo code. Điều đó không xác nhận nhãn hoặc
application oracle đúng. Provenance tổng thể PARTIAL, independent human Ground Truth
vẫn PENDING; không tăng formal admitted count. Các labels scenario/runner là evidence
intent/contract, không đồng nghĩa exploit success.

Code: [lineage audit](../scripts/audit-glu207-lineage.py),
[native ID audit](../scripts/audit-glu207-native-ids.py).

## D. Feature pipeline

Dùng lại frozen `collect(profile=safe_query_numeric_v2)`, `FeatureExtractor`,
`transform`, spec5: đúng207float32, ordering, categorical/role/UA, mean/std/clipping,
missingness, history10/60/300s. Không fit encoder, không tạo vector bằng padding.
Tensor thực đưa vào ONNX của12requests đã đối chiếu exact với replay chung.

Student timestamp được phát ở `SecurityRequestFilter.finally`, sau `chain.doFilter`;
fused timestamp lấy max các observations. Replay chỉ prefix tới target, target chỉ
observe một lần. Nginx-only timestamp có độ phân giải giây: gate mới từ chối prefix
nếu giây của bản ghi đó chưa kết thúc trước target. Không có trường hợp không chắc
này trong12snapshots đã chấm; gate được kiểm bằng test riêng, chưa thu lại cohort.

Flow availability = max(EVE timestamp,flow.end+65s), thêm actual receipt <= target
timestamp. Chưa available thì encoder dùng null/missing flags đúng frozen semantics.
Snapshot bao gồm canonical partial-source rows cho history nhưng chỉ target MATCHED,
không late và được frozen validation xác nhận ba nguồn mới có score. Đây là parity
trên các evidence đã nêu, không phải chứng minh mọi parser/environment/history regime.

Code: [bounded consumer](../scripts/glu207-live-shadow.py),
[Student timestamp](../student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityRequestFilter.java).

## E. AI inference và quality

GLU207 frozen step652: **9,675,784parameters**, model version
`glu207-step652-e663b0979f6f`; threshold
**0.5396780371665955**, comparator **>=**, PROVISIONAL_BENIGN_ONLY.
RIv2 frozen step3072:50,696parameters, threshold0.8826237916946411, comparator **>**.
Không thay weights/threshold hoặc fusion scores.

12GLU scores:0.201403–0.942719;5vượt ngưỡng.3có prior flow,9thiếu;12đều có
context_incomplete. Predict-call279.924–357.032ms, mean326.180ms (bao gồm frozen
validation/target feature extraction/inference, không phải riêng ONNX kernel). **Event-to-result
158.761–541.960s, mean380.897s** ở quota5%, do snapshot/fusion/history replay nhiều
lần; không coi là continuous low-latency serving.
Tập12GLU scores có cả các probes bổ sung; không đồng nhất nó với12receipts của
acceptance. Request sensor-stopped thiếu EVE không được chấm GLU.

Một benign-shaped ordinary query: GLU0.742114, RIv2 cùng request0.048009, không có
attack-rule alert tương ứng trong cohort. Keep-alive benign cũng GLU0.684369; các
SQLi/command-shaped probes GLU0.942719/0.850478. Đây là adverse evidence về calibration/
domain behavior; không phải Recall/FPR hay true additional detection.

Counterfactual hậu nghiệm một ordinary probe: bỏ prior flow bằng frozen encoder
làm score **tăng**0.742114→0.776736, chỉ10flow value/missing features đổi. Vì vậy không
quy lỗi đơn giản cho missing flow.207inputs không có rule-context columns; vẫn có
Suricata-derived flow/HTTP features nên không gọi AI/rules là hoàn toàn độc lập.
Chưa đủ evidence để khẳng định shortcut learning hoặc causal attribution chính xác.

## F. System, tests và thermal

- Rust/UI build PASS; Rust targeted RIv2 tests3PASS và correlation tests2PASS.
  Frontend tests3PASS; launcher7PASS; guard/candidate7PASS; correlation/causality11PASS.
- Full56Rust suite **chưa hoàn tất**: lần đầu thermal stop, lần sau wall limit600s.
  Không gọi toàn suite PASS. Những run lỗi/timeouts và stdout được giữ.
- RIv2 acceptance thật6requests PASS, latency139.999–260.420ms; model fault và worker
  restart không làm Student ngừng. New backend nhận thêm RI request và giữ ID/score.
- Authenticated API kiểm12GLU proofs/scores PASS, unauth401. Restart giữ29correlations,
  12GLU rows và32security alerts, Student200, AUTO firewall actions0. Probe restart
  đầu timeout3s/retry chạm login429; giữ evidence, sửa probe thành GET readiness rồi
  một login timeout60s; lần sau PASS, không sửa authentication policy.
- Có peak **86°C** vượt yêu cầu80°C. Watchdog đã kill cgroup, baseStudent vẫn200;
  sửa lỗi marker watchdog có thể override KILL bằng FREEZE. KILL nay luôn ưu tiên.
  Sau cooldown120samples/60s48–54°C mới chạy tiếp. Các run sau tối đa60–68°C;
  GLU guard62°C, cgroup peak566,870,016bytes. Peak shared system used trong các
  resource reports khoảng11.88GB, dưới30GB.
- Guard dùng kernel quota5–10% giảm dần, CPU affinity, MemoryMax/swap0, warning/rate
  of rise/freeze, independent watchdog và deadline. Không bảo đảm ngăn spike giữa
  các lần đọc hoặc kiểm soát nhiệt từ ứng dụng khác. Vì đã có86°C, **LOCAL_SYSTEM_STABLE
  = FALSE** theo điều kiện toàn milestone; không che bằng các run sau mát hơn.

## G. Handoff và preservation

[Team setup](TEAM_SETUP_AND_AI_STATUS.md) có release, checksum, dependency, commands,
privacy, scope, restart và stop. Release `ai-research-team-20261105` tương thích frozen
models; không cần raw20GB cho inference. Raw/session material/evidence giữ local.

Branch `feature/ai-idps-shadow-integration`, HEAD
`2f756a727293cf0d5e2266bca049cb797b6b8510`; changes **chưa commit/push**. Remote chưa
tự chứa milestone mới. Kiểm6checkpoint files và378protected source/config files:
không đổi. Không sửa Student business code, frozen data/spec/threshold, formal gate,
rules hoặc sealed holdout. Không dùng IPS/cloud.

## H. Quyết định engineering và thí nghiệm tiếp theo

**Không bắt đầu sustained training từ cohort hiện tại.** Đủ evidence để thiết kế
challenger, chưa đủ representative benign/attack outcomes để chứng minh lợi ích.
Không tăng parameters:9.68Mđã gần mục tiêu10M.1–2triệu requests chỉ có ý nghĩa khi
đúng identity, causal features, diversity và labels.

Công việc đầu tiên: derivative preparation tách application-observed/wire status,
giữ tx/generation/availability, quarantine174status conflicts để review, tạo benign
workflows đa vai trò/session/history ít nhất hai môi trường. Giữ frozen dataset.
Tiếp theo tối ưu incremental collector/history dùng chung implementation, yêu cầu
bit-exact với replay trước khi chạy liên tục; không duy trì công thức207thứ hai.

Một thí nghiệm ưu tiên sau khi có dữ liệu: **fine-tune có giới hạn trên benign
behavior đa workflow cùng verified positive outcomes**, giữ architecture/spec207,
so sánh C0=frozen weights+threshold cũ, C1=frozen weights+calibration mới chỉ từ
benign calibration, C2=một challenger+calibration cùng quy tắc. Giả thuyết: giảm
benign alerts do shift mà giữ coverage vượt C1; nếu C1 đủ tốt, không thay weights.

Precommit split theo môi trường/thời gian/workflow identity, dedup và embargo>=300s;
calibration/evaluation tách train, không dùng DVWA/current exposed probes để chọn
threshold. Labels tách intent/attempt/success/unsafe reflection/UNKNOWN; review
provenance rõ, không coi rule alert là GT; independent quality claims còn chờ human
review và evaluation mới khóa trước experiment. Ưu tiên benign hard negatives và
command injection/XSS outcomes vì đã là failure families ở P0, không suy nhãn từ
HTTP200. Không yêu cầu formal production admission để làm thí nghiệm development.

Cap thí nghiệm: một configuration, tối đa một epoch hoặc250updates, dừng khi thermal
gate kích hoạt, data/causality/hash gate sai hoặc không cải thiện development objective.
Không thử vô hạn augmentation/threshold. Chỉ promote khi evaluation mới đạt upper95%
FPR<=0.1% trên benign đại diện (0/3000 chỉ vừa đủ để kiểm mức này trong giả định IID;
workflow correlation còn cần group analysis), không giảm recall family trọng yếu
quá5percentage points và có lợi ích trên C1 được kiểm paired/grouped uncertainty.
Đây là tiêu chí đề xuất phải khóa trước thu evaluation, không phải kết quả đã đạt.

## Trạng thái chốt

```text
SURICATA_LIVE = TRUE
THREE_SOURCE_CORRELATION = VERIFIED
HISTORICAL_TRAINING_PROVENANCE = PARTIAL
GLU207_FEATURE_PARITY = PASS
GLU207_LIVE_SHADOW = READY
REQUEST_V2_REGRESSION = PASS
LOCAL_SYSTEM_STABLE = FALSE
NEXT_TRAINING_READINESS = PARTIAL
TEAM_DOCUMENTATION_UPDATED = TRUE
```

VERIFIED/PASS/READY áp dụng **bounded plaintext local shadow** và cases đã kiểm,
không phải continuous/production readiness, độc lập GT hoặc quality certification.
Evidence index có hashes: [JSON report](../ai-training/reports/THREE_SOURCE_INTEGRATION_20261106.json).
