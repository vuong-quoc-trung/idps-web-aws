# Team setup và trạng thái AI-IDPS

Cập nhật 2026-11-08. Integration branch chứa các milestone local shadow, three-source
và Rule–AI coordination; xem `git log -5 --oneline` để xác định revision clone.
Model release frozen giữ nguyên. Không cần raw research20GB để chạy inference.
Báo cáo integration: [Rule–AI coordination và tối ưu](16_RULE_AI_COORDINATION.md).
Milestone research trước: [Data quality và Oracle cohort](17_DATA_QUALITY_AND_ORACLE_RESEARCH.md).
Milestone trước: [Training data unblock](18_TRAINING_DATA_UNBLOCK.md).
Milestone trước: [Final training unblock và pilot kỹ thuật](19_FINAL_TRAINING_UNBLOCK.md).
Protocol: [Scaled matched normalization experiment](20_SCALED_NORMALIZATION_EXPERIMENT.md).
Kết quả model gần nhất: [Scaled normalization — candidate rejected](21_SCALED_NORMALIZATION_RESULTS.md).
Dataset milestone: [Attack-intent v1 — released, training blocked](22_ATTACK_INTENT_DATASET_V1.md).
Nền tảng representation: [HTTP body syntax — prototype](23_HTTP_BODY_SYNTAX_RESEARCH.md).
Live prerequisite: [Body-syntax live acceptance — verified for lab](../ai-training/reports/BODY_SYNTAX_LIVE_ACCEPTANCE_20261108.json).
Data prerequisite: [Request v3 data readiness — CASE B](24_REQUEST_V3_DATA_READINESS.md).
Coverage milestone: [Request v3 final coverage — CASE C](25_REQUEST_V3_FINAL_DATA_COVERAGE.md).
Command prerequisite: [Command Oracle recovery — CASE A](26_COMMAND_ORACLE_SANDBOX_RECOVERY.md).
Acquisition milestone: [Grounded acquisition — CASE C](27_REQUEST_V3_GROUNDED_DATA_ACQUISITION.md).
Milestone hiện tại: [Basket Oracle root cause — VERIFIED](28_BASKET_ORACLE_ROOT_CAUSE.md).

## Repository, model release và dependencies

```sh
git clone --branch feature/ai-idps-shadow-integration https://github.com/vuong-quoc-trung/idps-web-aws.git
cd idps-web-aws
./scripts/bootstrap-team.sh --tests
```

Model release: [ai-research-team-20261105](https://github.com/vuong-quoc-trung/idps-web-aws/releases/tag/ai-research-team-20261105).
Bootstrap dùng `release/assets.json`, tải và kiểm SHA256 trước khi restore:

| Asset | Mục đích | Kích thước | SHA256 |
|---|---|---:|---|
| models-core.tar.gz | Inference mặc định, RIv2 và GLU207 |158265099bytes|89666610a3078fcb93703794b651dc7b4ebe09d1a873366ab1d6ae3cf75483dc|
| request-training-recovery.tar.gz | Recovery/tensors WAF tùy chọn |419514083bytes|4b9ab5ca0e67255e9f827070b42fc5c87c629fd6c4ca2b751cdb6849381b4d61|
| historical-baselines.tar.gz | Baselines lịch sử tùy chọn |398550668bytes|af493ef31e29de2a4f22c88af0b1149a3e4e8eb6a86d71333dff4265a72e3773|

`--with-research-data` và `--with-historical-models` là opt-in, không cần cho demo.
Không coi recovery WAF là full GLU training dataset. GLU resume còn cần đúng
source revision3a67d15 và prepared-v5 hạn chế phân phối; RIv2 frozen chỉ có
inference/resume claim đúng như `release/assets.json`. Không tự train khi setup.

Môi trường được kiểm: Linux/systemd user/cgroupv2, CPU hwmon, Java25, Rust>=1.88,
Node/npm, Python3.12.14 do bootstrap quản lý, PostgreSQL16/17 qua Docker-compatible
CLI. Máy phát triển hiện dùng rootless Podman qua `docker`. Host khác/OS khác:
**NOT_TESTED**, không suy ra tương thích từ máy phát triển. Không hardcode home.

## Foundation và RIv2

```sh
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx
# Sau khi build đã khớp source, tái sử dụng cache:
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx --skip-build
./scripts/dev-up-and-verify.sh --status
```

Student qua Nginx `http://127.0.0.1:18780/`, Security `http://127.0.0.1:3001/`.
Credentials tự sinh trong `.local-dev/foundation/credentials.json`, private và
ignored. Không copy vào chat, repo, screenshot hoặc CLI history. Security username
`admin`, Student `foundation-admin`. Sau Rust restart cần đăng nhập lại.

RIv2:50,696parameters, step3072, threshold0.8826237916946411, strict `>`.
Worker dùng manifest pin độc lập và kiểm hashes; User-Agent/Accept/Content-Type
được đưa vào encoder dưới dạng text. Cookie/Authorization/body không được thu thập
cho RIv2. Đây là partial observability, không phải full request. Worker lỗi không
nằm trên đường xử lý Student. Score và cảnh báo nghiên cứu không phải Ground Truth.

## Suricata runtime và passive gateway

Binary8.0.3 và dependencies cũ thực ra đã đủ khi dùng đúng `LD_LIBRARY_PATH`;
nhận định trước đây chỉ dựa trên `ldd` không đặt loader path là chưa đầy đủ.
Không cần cài system service, sudo, host packet capture hoặc IPS.

Để chuẩn bị runtime riêng trên Ubuntu, helper chỉ download/extract packages:

```sh
python3 scripts/bootstrap-suricata.py --runtime "$PWD/.local-dev/suricata-runtime" --prepare
python3 scripts/bootstrap-suricata.py --runtime "$PWD/.local-dev/suricata-runtime"
```

Không ghi đè runtime có sẵn; chọn thư mục mới nếu cần thay version. `--prepare`
phụ thuộc metadata/repositories của distro; trạng thái kiểm của từng nhánh helper
được ghi trong báo cáo milestone, không coi fresh machine là đã kiểm nếu chỉ
check runtime có sẵn. Profile/rules được kiểm với8.0.3, không tự nhận version khác.
`--prepare` đã extract34packages vào thư mục mới trên cùng host, kiểm ldd/version
và live HTTP probe PASS với cùng binary/rules hashes. Clean host khác chưa được kiểm.

Mở terminal riêng, sau foundation và kiểm nhiệt an toàn:

```sh
ai-training/.venv/bin/python ai-training/scripts/integration-guard.py \
  --scope --output .local-dev/ids-guard-demo --quota 100 --max-seconds 1800 -- \
  ai-training/.venv/bin/python scripts/three-source-shadow.py host \
  --output .local-dev/ids-demo \
  --sensor-runtime "$PWD/.local-dev/suricata-runtime"
```

Output/guard directories phải mới để giữ evidence. `--scope` cần thiết: namespace
được tạo với quyền vốn có của caller; systemd service trên máy này không cho ghi
uid_map, nhưng scope cho phép. Giữ nguyên kernel quota/MemoryMax/watchdog; không
thay AppArmor/OS protections để cấp quyền mới.

Gateway opt-in `http://127.0.0.1:18782/` chuyển byte stream qua Unix relays tới TCP
loopback18881 trong private user/network namespace, rồi tới Nginx18780 hiện có.
Suricata nghe **chỉ** TCP18881 của namespace đó. Nó không nằm inline/IPS và không
thay routing/firewall host. Student thật xử lý request; không mock application.
Base18780 vẫn độc lập và traffic đi thẳng base không mặc nhiên có EVE.

Tuple thay đổi qua relay: không giả tuple hoặc flow_id của sensor là tuple trên
upstream Student. Trong lab này client behavior là nhóm loopback quan sát được,
chưa phải multi-client/NAT production attribution. TLS opaque hoặc gateway bị
bypass sẽ thiếu HTTP evidence; không suy ra benign.

EVE response headers chỉ đi qua Unix socket/RAM, giữ generated response
`X-Request-Id`; bỏ Set-Cookie/Authorization/payload/body trước disk. Numeric query
projectionv2 được tính trước URL redaction. Raw PCAP không được tạo trong demo.
Config/rules repository giữ nguyên; runtime config riêng có SHA/provenance.

## Correlation và feature semantics

- Nginx ↔ Student: generated request ID, method/route/status consistency.
- Suricata: response ID do Nginx sinh + sensor/logger generation + flow_id + tx_id.
  Route kiểm bằng keyed fingerprint trước privacy redaction, không join IP/time.
- Keep-alive có nhiều tx trong một flow. Alert có tx_id chỉ được gắn theo đúng
  generation/flow/transaction; alert không tx_id giữ flow-level context.
- Duplicate exact events idempotent; duplicate conflicting observations hoặc
  cùng transaction chứa nhiều IDs → AMBIGUOUS. Thiếu nguồn → MISSING_SOURCE.
  Arrival chậm hơn event watermark2s được đánh dấu LATE_EVENT, không score GLU.
- Metadata/source presence trong bảng RI không thay kết luận strict MATCHED của
  bảng correlation. Thiếu EVE không phải prediction benign.

GLU dùng **chung** frozen `collect`, `FeatureExtractor`, `transform` và spec5.
Collector numeric profile4.1 + behavior_dynamics tạo pipeline5; không fit scaler
mới.207float32 cột đúng thứ tự/mean/std/clipping, role/UA/missingness và windows
10/60/300s. Current request được tính một lần; không replay response tương lai.

Flow features là **previous available completed client flow context**, không phải
byte counters của request hiện tại. Gate event availability
`max(EVE timestamp,flow.end+65s)` và actual receipt trước target; flow chưa có là
null với missing flags theo encoder frozen, không điền207số0 để ép model chạy.
History reset/replay bounded, target đến muộn không được đổi thành score hợp lệ.
Student timestamp ở `finally` sau xử lý; Nginx-only history trong giây chưa hoàn tất
bị gate từ chối vì timestamp nguồn này chỉ chính xác tới giây.12snapshots đã chấm
không có trường hợp không chắc này; gate bổ sung được kiểm bằng unit test.

## GLU207 post-response shadow

Sau khi source/feature checks PASS, terminal riêng chạy consumer được guard độc lập:

```sh
ai-training/.venv/bin/python ai-training/scripts/integration-guard.py \
  --output .local-dev/glu-guard-demo --quota 100 --max-seconds 900 -- \
  ai-training/.venv/bin/python scripts/glu207-live-shadow.py \
  --sensor .local-dev/ids-demo --output .local-dev/glu-demo --max-requests 16 --since-now
```

Chỉ MATCHED không late mới được xét; frozen collector còn phải xác nhận đủ ba
nguồn, identity/time/response/numeric contract. Snapshot post-response private,
không training. Replay prefix bao gồm canonical requests thiếu EVE cho history,
nhưng không chấm chúng như full-source requests. Tensor thực vào ONNX được đối
chiếu exact với shared feature replay. Repeated metadata không đổi score cũ;
backend chỉ hiển thị GLU nếu proof digest còn khớp correlation hiện tại. Kết quả
AMBIGUOUS mới không thể bị score cũ nâng thành MATCHED.

Model `glu207-step652-e663b0979f6f`,9,675,784parameters. Ngưỡng frozen
0.5396780371665955, comparator`>=`, **PROVISIONAL_BENIGN_ONLY**. Hai model hiển thị
riêng; không fusion, blocking, firewall hoặc sửa security policy.

Đây là **bounded asynchronous shadow consumer**. Snapshot bất biến được collect
một lần/batch; các target có cùng tập completed-flow receipt được dùng chung kết
quả frozen collect. Công thức feature/history không thay đổi, chưa tạo state engine
mới. Mỗi input ONNX vẫn được kiểm parity trước khi publish.

Benchmark12requests cùng snapshot/quota100% của **một CPU**: reference18.42–19.11s,
cache3.69–3.81s, nhanh4.83–5.18lần; exact207vectors và scores. Đây không phải so sánh
trực tiếp với run quota5% trước. Probe mới qua HTTP tới API có GLU sau3.30–3.34s
(n=2); chưa là sustained-load SLA. Predict-call và end-to-end phải báo riêng.
Collector status không phải GLU heartbeat; xem journals/API, batch profile và guard.

## Rules + AI coordination

Security Web → AI shadow có bảng **Rules và AI trên cùng transaction**. API
`/api/ai-shadow` thêm `detectors`; các bảng/fields cũ vẫn giữ. Request ID hoặc
sensor-generation/flow/tx là basis; không join bằng IP/time. Late alerts tự xuất
hiện khi API được đọc lại, không tạo alert tổng hợp hoặc weighted fusion.

- Rule alerts giữ source, severity/action/timestamp hiện có. Nginx-source alerts
  do Rust signatures/edge hints phát hiện; Suricata-native alerts giữ SID.
- Request v2/GLU giữ score, threshold/comparator, model version và timestamp riêng.
- Thiếu inference là MISSING_INFERENCE/NOT_READY, không phải benign.
- Flow-only alert là context, không tính thành request alert; AMBIGUOUS không join
  sensor transaction hoặc hiển thị score GLU từ proof cũ.
- “Chỉ thấy AI/Rules cảnh báo” mô tả evidence quan sát, không chứng minh detector
  còn lại đã đánh giá âm tính. GLU dùng Suricata-derived metadata, không là phiếu độc lập.
- Migration0007 tự tạo metadata links cho events mới; alert cũ thiếu transaction
  metadata không được tự suy link. Chúng vẫn còn trong quản lý cảnh báo.

## Kiểm tra và quan sát

```sh
ai-training/.venv/bin/python scripts/test-three-source.py
python3 scripts/verify-three-source.py --sensor .local-dev/ids-demo
python3 scripts/verify-ai-local.py
# Sau three-source acceptance, khi GLU consumer còn đủ request budget:
python3 scripts/verify-detector-coordination.py --sensor .local-dev/ids-demo \
  --output .local-dev/detector-proof-demo.json
```

Security Web → **AI shadow** → correlation ba nguồn/GLU207 và bảng RI riêng.
Tra response `X-Request-Id`. Correlation journal:
`.local-dev/foundation/correlation/results.jsonl`; GLU journal:
`.local-dev/foundation/glu207/results.jsonl`; EVE sanitized:
`.local-dev/foundation/suricata/eve.json`. Các journal rotation4×2MiB, kết quả DB
bounded10k/7ngày. Không publish runtime hoặc raw historical logs.

Nếu nâng một DB đã ingest adapter EVE bằng parser cũ sang stable identity mới:
dừng riêng Rust watcher, giữ PostgreSQL, rồi chạy helper một lần **trước khi parser
mới replay các lines cũ** (không cần cho DB mới):

```sh
python3 scripts/reconcile-suricata-identities.py \
  --legacy-source-instance local --output .local-dev/identity-cutover-team.json
```

Helper chỉ alias exact existing physical receipts khi giữ được versioned identity;
không reset cursor, xóa alert hoặc dedupe bằng timestamp/URI. Milestone đã gặp một
alert duplicate ở ranh giới parser cũ/mới; giữ nguyên nó làm evidence, sau alias
metadata replay và restart không tăng alert count. Không suy alert count=attack count.

Dừng: Ctrl+C hai terminal guard IDS/GLU, rồi
`./scripts/dev-up-and-verify.sh --stop`. Các cgroup guard dừng descendants; không
xóa volumes/checkpoints/evidence. Terminal có model consumer kết thúc khi đạt
bounded request limit; không gọi kết thúc đó là service crash hoặc tự restart vô hạn.

## Training đã có, điều đã kiểm và điều chưa chứng minh

GLU frozen đã train2epochs/652updates trên41,607train rows,83,214sample exposures,
41,585unique float32 views. Đây là fitting diagnostics, không chứng nhận Recall/FPR
hoặc generalization. RIv2 frozen step3072 vẫn được giữ; candidate augmentation
trước đã không đạt selection rule nên không thay champion demo.

Milestone mới kiểm trực tiếp toàn bộ41,607training rows và normalized observations:
đủ ba nguồn cho từng row,41,433triplets nhất quán HTTP.174PATCH records có Student
status405 nhưng Nginx/EVE403; không có method/route mismatch trong nhóm đó. Không
coi chúng là verified response semantics hoặc tự sửa Frozen Dataset.36,443row có
prior flow đều tái dựng đúng;5,164row thiếu flow là missingness có thật.

Native producer snapshot audit và các giới hạn như historical tx_id retention,
original packet attestation, source checksums được ghi trong báo cáo. Dataset có
ba nguồn không đồng nghĩa independent Ground Truth. Scenario labels vẫn là runner
intent/HTTP contract, chưa human-verified attack outcomes. Formal admitted count
không được tăng trong milestone.

Saved train-prefix512rows: exact207features; live tensors/flow watermark và các
correlation cases có evidence riêng. Không ngoại suy parity này thành kiểm định
mọi môi trường, parser, late regime hoặc chất lượng model.

Đã có benign-shaped probes vượt ngưỡng GLU: không che kết quả xấu, không đổi
threshold trên cohort đã lộ, không dùng cohort này tính population FPR. Chưa chứng
minh giá trị phát hiện tấn công bổ sung độc lập so với RIv2/Suricata.

| Hạng mục | Phạm vi trạng thái |
|---|---|
| RIv2 inference | VERIFIED qua HTTP, frozen contract; quality scope vẫn research |
| Suricata | VERIFIED bằng live EVE trên gateway plaintext riêng |
| Correlation | VERIFIED ở các cases đã chạy; topology/multi-environment PARTIALLY_VERIFIED |
| Historical lineage | PARTIALLY_VERIFIED;174status conflicts, thiếu original packet reattestation |
| GLU feature pipeline | Shared frozen implementation, bounded parity; scope cụ thể trong report |
| Production/all-traffic behavior | NOT_READY |
| Sustained training mới | NOT_TESTED, không chạy |
| Independent detection quality | NOT_READY / chưa có evaluation mới đủ nhãn |

Nhiệt độ đã chạm86°C trong lần Rust test đầu, vượt yêu cầu80°C. Watchdog kill
workload; sửa lỗi ưu tiên KILL/FREEZE và kiểm lại gate. Các run sau tối đa60–68°C,
nhưng không tuyên bố host luôn an toàn. Full56Rust tests của milestone2026-11-06
chưa hoàn tất do thermal stop/deadline; milestone2026-11-07 đã chạy full57/57PASS. Không tự đóng user apps hoặc tăng quota để vượt gate. Total shared
RAM vẫn30GB, các resource reports ghi peak khoảng11.88GB.

Backend restart kiểm lại đủ12GLU scores,29correlations và32alerts không tăng/mất;
Student200, AUTO firewall0. Probe login đầu timeout/retry chạm429 được giữ, probe
đã sửa GET readiness + một login timeout60s. Credentials/session không publish.

Báo cáo A–H, trạng thái và quyết định training:
[Three-source intelligence](15_THREE_SOURCE_INTELLIGENCE.md).
Hệ thống/workloads kiểm thử đã dừng sau nghiệm thu; volumes/evidence giữ nguyên.

## Việc tiếp theo

Ưu tiên tách application-observed status với wire status, tạo derivative mới có
strict provenance/missingness, và có benign calibration/review đa workflow/domain.
Giữ nguyên Frozen Baseline; không tự sửa nhãn174rows để tăng accepted count.
Tối ưu incremental feature state/collector sau khi giữ được parity, rồi mới đầu
tư training lớn.9.68Mparameters đã gần mục tiêu10M; nút thắt là dữ liệu, nhãn và
khả năng đánh giá, không phải thiếu số tham số. Thí nghiệm tiếp theo cần precommit
hypothesis, fixed baseline, train/cal/eval tách biệt và tiêu chí dừng; xem báo cáo
`ai-training/reports/THREE_SOURCE_INTEGRATION_20261106.json`.

## Resource policy hiện hành và background training

Policy cũ79/80°C trong báo cáo2026-11-06 là lịch sử. Guard mặc định hiện dùng
rolling300s time-weighted average<80°C; reduce gần77°C, pause>=80°C, thêm pause sớm
khi nhiệt tức thời/rate tăng nguy hiểm. Emergency cutoff90°C (device coretemp critical
quan sát105°C); sensor/monitor heartbeat lỗi cũng kill. Không auto restart emergency.
Active/pause averages, CPU utilization/throttling, MemAvailable, cgroup memory,
PSI/swap/OOM events và sensor health được ghi vào `resource-status.json` atomic,
`samples.jsonl`, `resource-report.json`. Không dùng cooldown để làm đẹp active average.

CPUQuota tính theo **một CPU**, không theo phần trăm toàn host.100%=một CPU; guard
cho phép ceiling tới50% tổng CPUs và giảm theo nhiệt/tải từ app khác, không ép đạt
50%. Các run kiểm dùng ceiling100% và threads1, affinity tối đa8CPU; tăng concurrency
cần đo riêng. `--policy legacy` chỉ tái lập policy cũ. Không sửa firmware/OS protection.

`--memory-gib` là cgroup ceiling (mặc định4GiB), được hạ theo MemAvailable để giữ
reserve4GiB và shared30GB. Không có cap16GB; không hứa cấp đủ giá trị request nếu
host thiếu headroom. PSI/full hoặc swap-I/O cao cũng pause. Không tự đóng user apps.

```sh
cat .local-dev/glu-guard-demo/resource-status.json
cat .local-dev/glu-guard-demo/resource-report.json
systemctl --user list-units 'idps-integration-*'
```

**Không có training job mới đang chạy.** Derivative local:
`ai-training/.artifacts/glu207_derivative_20261107/manifest.json`:
41,607train rows,174quarantine,41,433research candidates; separate application/wire
status, giữ original features/history/missingness và inherited label tier. Không
đưa derivative/raw evidence này lên public; clone không tự có restricted train data.

Thiết kế tối đa một pilot ở
`ai-training/configs/research/glu207-derivative-pilot-v1.json`; trạng thái
DESIGN_LOCKED_NOT_SCHEDULED, **không phải executable training configuration**.
Chưa có calibration/evaluation mới đa môi trường hoặc new-run exact-resume test.
P0 DVWA111requests vẫn exposed development/independent-review PENDING và không có
GLU207 fused contract; không ép chúng vào training207features.

Không có lệnh resume mới hợp lệ để team chạy ở thời điểm này. Historical GLU cần
pinned revision/dataset như release notice; không tuyên bố RESUME_EXACT. Khi gate
đủ, run mới phải khóa config/dataset, kiểm checkpoint round-trip rồi mới dùng
persistent systemd supervisor + atomic status/checkpoints. Không tạo job giả chỉ để
có RUNNING; không để Codex polling một training dài. Chi tiết blocker và proposal
trong báo cáo milestone hiện tại.

## Milestone trước: Data quality / Oracle research — 2026-11-07

Đã thu **75requests thật** ở DVWA/Juice (46+29),75unique method/URL/body representations,
59frozen Request-v2 feature views. Hai environment đều có benign và attack attempts.
47benign có semantic Oracle;23attempts gồm14successes theo Oracle nội bộ,8unsafe
reflections và1unknown outcome.5intended-benign user-lookups thiếu snapshot expected
DB vẫn UNKNOWN. Tất cả independent human review PENDING, không formal admission mới.

Vai trò khóa trước:35TRAIN,9eligibleCALIBRATION,13DEVELOPMENT,13PROSPECTIVE EVALUATION,
5UNKNOWN excluded. Có raw/view/template/near/session checks; chỉ2connectedTRAINgroups.
9calibrationrequests đềuGET và chỉ3uniqueviews.13prospective rows chưa bị chấm score,
chỉ có SQLi positives; chưa đủ XSS/command/traversal để trả lời hypothesis.

Calibration-only0.07709759473800659 được thử riêng, **không deploy**: TRAIN diagnostic
FP2→18 trong khi TP1→7; không thể dùng3GETviews để chứng nhậnFPR≤1%. Frozen threshold
0.8826237916946411 giữ nguyên. Đây là offline full-body/header research; liveworker
vẫn không capturebody. GLU207 eligible từ75requests này bằng0, không padding.

Capture artifacts/receipts/catalog/challenge/source snapshots và review queue:
`ai-training/.artifacts/quality_lab_20261107/` (private,ignored). Assessment active:
`assessment-v2/report-corrected.json`, `training-gate.json`,
`calibration-comparison.json` ở root của phase. Có failed attempts/cleanup errors,
source snapshots và recoveries; không ghi đè hoặc phát lại DVWA để tạo run đẹp.
Collector đã sửa interpreter/port binding, incremental Oracle ledger và cleanup
verification cho lần dùng tiếp; không replay75cases để test cleanup.

Source tools (cần môi trường Python bootstrap và pinned cached lab images):

```sh
ai-training/.venv/bin/python ai-training/scripts/inventory-research-data.py \
  --output .local-dev/research-inventory-new.json
# Chỉ dùng output mới; đọc/handoff plan và resource policy trước capture:
ai-training/.venv/bin/python ai-training/scripts/quality-lab-cohort.py prepare \
  --output ai-training/.artifacts/NEW_COHORT_DIRECTORY
```

Lệnhprepare không phát traffic. Collector cố định một finite case set và run-owner;
không chạy lại chỉ để tăngcount. Capture tiếp theo phải chọn gap-filling cases theo
manifest mới và exclude các template/views hiện có **trước khi phát**. Không xem
prepare ở trên như permission tự train hoặc một run tiếp theo đã khóa.

**TRAINING_GATE=BLOCKED, BACKGROUND_TRAINING=NOT_STARTED.** Candidate duy nhất:
`ai-training/configs/research/request-channel-robustness-v3.json`, design-only,
không executable config; giữ khoảng50kparameters, riêng URI/body/header normalization
và coarse non-secret field syntax. Encoder frozen nguyên trạng. Same588width không
đồng nghĩa warm-start compatibility khi coordinates thay đổi; cần new initialization
và checkpoint roundtrip. Không có checkpoint/run mới đểresume.

Inventory hiện phân biệt13nhóm nguồn. WAF1.924Mpublisherrows không đồng nghĩa1.924M
Oracle requests; SR-BH/WAMM có liên hệ upstream, log/transaction/featurecounts không
được cộng thành total physical groundtruth. Global distinct physical count cònUNKNOWN.
Dữ liệu held-out/sealed không mở. Xem aggregate reports:
`ai-training/reports/RESEARCH_DATA_INVENTORY_20261107.json`,
`ai-training/reports/AI_QUALITY_PHASE_20261107.json`.

**Một việc tiếp theo:** một cohort role-isolated bổ sung workflow groups đa dạng
choTRAIN, benignPOST choCALIBRATION và
workflow XSS/command/traversal chưa lộ choPROSPECTIVE EVALUATION; giữ Oracleprovenance,
không di chuyển currentTRAIN sangcalibration sau khi đã xemscore. Không thêm model,
policy hoặc dashboard ở bước này. Human review chưa có không chặn mọi research,
nhưng không được nâng internalOracle thành independent validation.


## Training data unblock — 2026-11-07

**CASE B — DATA IMPROVED, TRAINING BLOCKED.** Một campaign mới 43study requests,
khóa roles/gates/candidate trước traffic:18TRAIN,13CALIBRATION,12PROSPECTIVE.
43receipts verified,42frozen views và42candidate views;20benign,20attempts,
3UNKNOWN.40semantic Oracle matches;14internal exploit successes,6unsafe reflections;
43human reviews PENDING. Không formal admission mới hoặc independent quality claim.

TRAIN đạt9workflow/session components và4attack families. Prospective đạt2templates
mỗiSQLi/XSS/command/file-inclusion,4benignGET/POST;12rows đã hash-seal,0scores.
Cùng DVWA/Juice/source/fixture lineage, không gọi là independent cross-domain.
Calibration có4benign JSON feedback POST được Oracle/persisted-state kiểm chứng,
nhưng thiếu benign **formPOST**:3ping cases trả response rỗng, giữ UNKNOWN.
Cùng-image/user runtime probe cho thấy ping thiếu raw-socket capability. Không
thêm quyền hoặc đổi Oracle để ép PASS. Gate còn thiếu1benign workflow group,
1formPOST group và tối thiểu1unique benign view so với plan.

Encoder research riêng: `ai-training/src/idps_ai/features/research_request_channels.py`;
76numeric + URI256/body192/header64, normalization riêng, privacy/missingness tests.
Frozen encoder/model/threshold không thay. Config precommitted được lưu ở
`ai-training/configs/research/request-channel-unblock-pilot.json`;50,696parameters,
new initialization, seed17, Adam0.001, batch4,1epoch/max250updates, chưa launch.
Cross-process synthetic next-update recovery đã PASS; đây không phải actual cohort
training hoặc checkpoint để promote.44tests và Ruff PASS.

Capture max60°C; test có spike84°C, guard đã freeze/reduce/thaw, không chạm90°C.
Active/paused thermal accounting tách riêng; chưa sustained-training qualification.
Shared RAM peak≈12.83GB, tất cả owned lab resources đã cleanup. Existing frozen
release, bootstrap và local-system workflow nguyên trạng; AI enforcement DISABLED.

Dataset/private evidence: `ai-training/.artifacts/training_unblock_20261107/`,
active capture `campaign-capture-v2`, active dataset `dataset-release-final-v2`.
Không push receipts/session/tensors/review queue. Chi tiết, failures và hashes:
`docs/18_TRAINING_DATA_UNBLOCK.md`,
`ai-training/reports/TRAINING_DATA_UNBLOCK_20261107.json`.

**Đúng một việc tiếp theo:** bổ sung calibration formPOST qua DVWA`/security.php`
với CSRF/session-state Oracle, kiểm runtime prerequisite trước capture, ít nhất
2meaningful views và loại overlap trước HTTP. Không thu lại43cases, không đổi
prospective seal hoặc candidate theo evaluation. Chưa có training job đang chạy.


## Final training unblock — 2026-11-07

**CALIBRATION PASS; pilot kỹ thuật COMPLETED, không có training nền đang chạy.**
Bổ sung đúng2POST DVWA`/security.php` trên session mới sau preflight tách riêng;
CSRF/Set-Cookie/GET state Oracle xác nhận2transitions.2candidate views/1frozen view,
1workflow. Không replay43cases hoặc đổi3ping UNKNOWN thành benign.
Calibration có10benign/2attempts eligible,4benign groups, cảformPOST/JSONPOST/GET,
8frozen benign views/9candidate views, đạt minimum đã khóa. Human review PENDING.

Fit derived giữ nguyên18TRAIN cũ, bổ sung31/35Oracle TRAIN legacy sau re-encode và
loại4duplicate views:49unique samples,11workflow/session groups trong2apps.
Không trộn publisher anomaly labels hoặc207features. Không mở/chấm prospective12;
chỉ dùng opaque identifiers/templates để exclusion. Roles/seal cũ giữ nguyên.

Run local:`ai-training/.artifacts/final_training_unblock_20261107/request-v3-pilot-20261107-01/`.
Model50,696parameters, encoder riêng frozen-design hash, new initialization, seed17,
Adam0.001,batch4,1epoch/13updates. Checkpoint weights/Adam/RNG/sampler/scheduler/config/
dataset/metrics đã lưu và reload arrays khớp. Không claim real-data RESUME_EXACT.
49samples chỉ đủ engineering/small-sample feasibility, chưa quality-improvement proof.

Train loss2.104734→1.317241; frozenTRAIN TP7/FP4, challengerTP6/FP5, nên không promote.
Calibration-only threshold0.99825078 giảmTRAIN flags cònTP2/FP0. Candidate threshold
0.58970392 chỉ là research artifact; frozen live threshold0.88262379 không đổi.
CAL0false flags không chứng nhậnFPR vì cùng benign data chọn threshold, ítgroups.
Chưa xác nhận normalization hypothesis; không tự tăng epochs hoặc mở prospective.

47tests/Ruff PASS; actual training max50°C; phase peak68°C, shared RAM≈11.71GB,
all own resources stopped. Frozen baseline/Rules/Web/Policy/release/bootstrap nguyên
trạng, AI enforcement DISABLED. Raw/session/tensors/review/checkpoints mới local-only.
Xem `docs/19_FINAL_TRAINING_UNBLOCK.md` và
`ai-training/reports/FINAL_TRAINING_UNBLOCK_20261107.json` để kiểm chứng.


## Scaled normalization experiment — 2026-11-07

**COMPLETED: hai arms đủ3,072updates, checkpoint reload/hash PASS. Candidate không
đạt retention criteria; giữ Frozen Requestv2.** Báo cáo chuẩn bị
`SCALED_NORMALIZATION_20261107.json` vẫn là prelaunch snapshot; kết quả hoàn thành ở
`SCALED_NORMALIZATION_RESULTS_20261107.json` và tài liệu21. Runtime local vẫn là
source of truth, không suy ra RUNNING từ snapshot cũ.
Nguồn WAF publisher TRAIN/README/tensor còn sẵn, pin revision + SHA và MIT declaration.
Reconstruction160,796views khớp original control bitwise. Không mở publisher heldouts.

Fit cùng120,435TRAIN views (34,282NORMAL/86,153ANOMALOUS), không fit49Oracle labels.
Không đổi original roles. Sau full-cosine≥.995 quarantine ở cả representations,
CAL còn2,437(1,042NORMAL), DEV2,041(865NORMAL); nhiều near views cũ bị loại khỏi
measurement. Đây là feature-near, không chứng minh physical duplicate transactions.

Matchedcontrol dùng exact original rich-v2 sharedL2. Challenger cùng privacy/text/
numeric/hash coordinates, chỉ đổi per-channelL2 trước finalL2; không dùngv3encoder
pilot vốn thay thêmprivacy/hash layout. Cùng50,696parameters,seed31,initial arrays,
batch256/lr0.001,3,072updates mỗiarm, finalcheckpoint-only; khôngloss-based selection.
Native partial-binary task chỉpublisher NORMAL/ANOMALOUS,familyunknown; Oracle49TRAIN
exposed diagnostics,12CAL và111P0DEV/Suricata riêng strata, không silent pool labels.

Fresh-process recovery cả2arms first600realTRAIN,4updates cóepochwrap PASS bitwise.
Full3,072-step resume chưa được thực nghiệm. Independent watchdog systemd + active
rolling300s (không pha cooldown), cutoff90°C/active-limit80°C, reserve4GiB/shared30GB.
Quota floor fix được probe trênmáy; trần conservative25% mộtCPU.52tests/Ruff PASS.

Experiment local:
`ai-training/.artifacts/scaled_normalization_20261107/scaled-normalization-20261107-v1/`.
`plan.json`,`status.json`,arm`latest.json`,metrics và`resource/` chứa runtime/checkpoint.
Source/config/dataset hashes được khóa trước fit. Không tự chạy evaluation hoặc mở
prospective12 khi completion; chỉ mở một lần sau yêu cầu kiểm kết quả và khóa model/
threshold. Publisher/Oracle/exposed/prospective/independentGT không gộp metrics.

Xem`docs/20_SCALED_NORMALIZATION_EXPERIMENT.md` cho status/evaluation/resumecommands,
corpus provenance và giới hạn. Research retention criteria không phải auto promotion.
Frozen release/GLU207/Requestv2/encoders/thresholds/Web/Rules/Policy nguyên trạng,
AI enforcement DISABLED; noAWS. Raw/tensors/weights local-only, team inferencebootstrap
không cần download research corpus.

Evaluation2026-11-07: publisherDEV2,041views, matched Recall92.77%/NORMAL flags1.16%,
challenger93.54%/1.39%; delta Recall+0.77pp, NORMAL+0.23pp, không đạt gates
≥2pp/≤0.2pp và paired bootstrap không xác nhận lợi ích. Đây là publisher anomaly
labels, không phải verified HTTP attack Recall. OracleCAL max-benign thresholds:
control0.9975697398/challenger0.9925589561; frozen giữ0.8826237917. P0 exposed:
control/challenger đềuTP3,FN45,FP0,TN59; frozenTP18,FN30,FP0,TN59; UNKNOWN4 excluded.
XSS/cmd đều0/12 ở cảba, challenger không thêm phát hiện ngoài Suricata. Frozen
thêm4attempt flags ngoài Rules trên chính P0; không suy ra independent generalization.

Training resource PASS:206.4s wall, peak66°C, active mean45.08°C, workload peak≈571MiB,
shared peak≈11.34GiB; không thermal stop/watchdog failure. Run ngắn hơn300s nên chưa
phải kiểm chứng thermal sustained dài.12prospective vẫn sealed vì candidate đã fail;
không tiêu hao để tìm kết quả cứu candidate. Human review vẫnPENDING. Không promote,
không đổi shadow model/threshold/policy. Checkpoints haiarms giữ local ở experiment
root nêu trên; exact resume mới được chứng minh subset4updates, không full3072resume.

## Attack-intent dataset v1 — 2026-11-07

**CASE B: derivative dataset hoàn tất, chưa domain-adaptation training.** Dataset
`attack-intent-v1-20261107`, fingerprint
`fa9a2d87852afea879ed146d4bd8077e8a070d42337d6b36ffe836686a4fef5f`.
Tái dùng206receipts hợp lệ/unknown có provenance, thêm18precommitted lab requests
sau9Oracle preflight checksPASS. Không dùng publisher anomaly labels hoặc mởsealed12.

224records:130BENIGN_INTENT/81ATTACK_INTENT/13UNKNOWN_INTENT;207internal Oracle
verified,0independent human verification,224reviewPENDING. Outcomes:130benign success,
51verified exploit successes,26unsafe reflections,17unknown; không gọi reflection
là browser execution. New18:12benign/5attempts/1UNKNOWN,17Oracle matches.

Giữ original roles:TRAIN63/CAL37/DEV124, cùng full-receipt và runtime-emulated
tensors588 riêng. After strict exact/near/lineage quarantine cònTRAIN10/CAL13/DEV86.
Runtime projection khớp actual worker envelope/model_record/tensor224/224; body=None,
selected headers only. Fullview không có mixed-intent exact collision; runtimeview
có2groups/35records chứa benign+XSS/SQLi. TRAIN sauquarantine thiếuXSS/cmd, benignPOST
vàbenignview diversity. Không fit để tạo checkpoint trên contract mất thông tin.

CAL có11benign+2attempts,8benign runtimeviews, form/JSON POST vàGET; đủminimum research
coverage với limits. Frozen/runtime calibration-only trên P0 đều18/48attempts,
0/59benignflags, XSS/cmd0/12; chưa có independent FPR≤1% hoặccross-domain evidence.
Threshold deployment0.8826237917 giữ nguyên. 12prospective vẫn sealed; human review
PENDING không bị dùng làm formal blocker tuyệt đối cho Oracle research.

Private final release:`ai-training/.artifacts/attack_intent_20261107/release-v3/`.
Public metadata:`ai-training/reports/ATTACK_INTENT_DATASET_20261107.json`.
17tests/Ruff PASS; preflight/capture peak48/50°C, ownedlabs cleanup. Không training,
promotion, newreleaseweights, AWS hoặc enforcement. Full artifacts/session/tensors
local-only; frozen inference bootstrap giữ nguyên.

Một nhiệm vụ kế tiếp: offline privacy-preserving body-syntax observability experiment
trên hai mixed groups đã có, với allowlist/privacy canaries vàview/split checks;
không tăng request count hoặc tự thay live telemetry. Xem tài liệu22 cho evidence,
coverage, label tiers và hướng WARM_START có điều kiện.

## HTTP body-syntax candidate — 2026-11-07

**CASE B — CANDIDATE PARTIAL; production LIVE_OBSERVABILITY=NOT_READY.** Không train,
không checkpoint, không đổi frozen inference/encoders/thresholds hoặc live Nginx,
Web, Rules, correlation, Policy Engine. Không mở12sealed hoặc thêmGT cohort.

`http-body-syntax-v1`:46numeric columns, JSON/formbounded8KiB,32fields,depth8;
allowlisted noncredential text only, protected/unknown values không profile/emit.
Không raw bodies, arbitrary names/values hoặc secret hashes trong telemetry.
ContractSHA:`0e163b7392a9bb68131e4c66486fa5827ce6259295f0d703b403a8efad96982c`.
Joint634view chỉ dùng collision diagnostics, không feed vào frozen model588.

224records exposed: runtime122uniqueviews/2mixedgroups/35affected thành
candidate158views/1mixedgroup/6affected. Stored-XSS29records tách thành23views,
0mixed; JSONlogin6records vẫncollision do policy loại email/password. Không dùng
labels để tinh chỉnh feature từngsample, không coi separation là Recall improvement.

Actual isolatedHTTP→extractor→datagram→candidateworker parity224/224; byte/path/header
forwardingwitnessPASS. Nominal235events,0drops; malformed/oversize/multipart/gzip/chunked
không chặn forwarding.6canary families,0literal/encoded leaks ở exercised journals/
serializers/features/errors; Rust/DB/dashboard candidate paths NOT_EXERCISED.
Nginx bodytemp non-persistence chưa kiểm nên production privacy NOT_VERIFIED.

49tests/RuffPASS; FrozenP0full/runtime giữ18/48attemptflags,0/59benignflags; không
retune threshold. Pythonshadow/correlation regressionPASS, fullRust/DB/API tests
không chạy lại. Studymax56°C, buffersbounded, ownedsocketsclosed. Bodyvectors/journals
local-only tại`ai-training/.artifacts/body_syntax_20261107/`; publicreport
`ai-training/reports/BODY_SYNTAX_20261107.json`. Dataset224/207Oracle/reviewPENDING
không đổi; chưa re-audit candidate split/coverage, không training-ready tự động.

Một nhiệm vụ kế tiếp: opt-in real ingress integration verification với canary
non-persistence qua buffering và candidate-worker delivery, giữ identity exclusions
và frozen path. Xem tài liệu23; team clone/bootstrap/frozen models/local demo giữ nguyên.

## Real-ingress lab Nginx preflight fix — 2026-11-07

**NGINX_PREFLIGHT=PASS; REAL_INGRESS/PRODUCTION_PRIVACY=NOT_VERIFIED.** Chỉ sửa và
kiểm tra preflight; chưa chạy full OFF/ON acceptance, không attack probes/training.
Ba source/test files của phiên gián đoạn được giữ và tiếp tục sử dụng; full ingress
harness vẫn experimental, không được bootstrap tự động hoặc coi là đã kiểm chứng.

Root cause đã tái hiện trên isolated Nginx **1.28.3 (Ubuntu)**, exit1:
`mkdir() "/var/lib/nginx/fastcgi" failed (2: No such file or directory)`.
Cú pháp config hợp lệ; binary đóng gói có compiled-in absolute FastCGI/SCGI/uWSGI
temp paths. `-p` không chuyển các absolute defaults này vào lab. Generator trước đó
chỉ override body/proxy temp paths, nên `nginx -t` vẫn thử tạo system temp directory
dù không có FastCGI upstream. Không phải lỗi Rules maps hoặc Unix upstream socket.

`ai-training/scripts/validate-real-body-ingress.py` nay dùng chung deterministic
generator với đủ5temp paths trong output riêng: body/proxy/fastcgi/scgi/uwsgi.
Không tạo `/var/lib/nginx`, không sudo, không sửa Nginx global/production. Preflight
lưu run ID, exact argv/cwd, exit code, config/binary SHA256, bounded stdout/stderr
(redact credential-bearing lines) và failure category vào local diagnostic directory;
FAIL/timeout dừng với đường dẫn evidence, trước HTTP traffic.

Chạy riêng preflight bằng output **mới**, không cần runtime/secrets hoặc services:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
ai-training/.venv/bin/python ai-training/scripts/validate-real-body-ingress.py \
  --nginx-preflight-only --output "$PWD/.local-dev/nginx-preflight-check-01"
```

Chế độ này giữ candidate OFF, không tạo listener/worker/container và không gửi HTTP.
Binary lab phải tồn tại tại `.local-dev/foundation/tools/runtime/usr/sbin/nginx`;
không fallback vào Nginx của hệ thống. Không kết hợp với `--enable-body-syntax`.

Verification: actual `nginx -t` exit0 qua nhiều lần kiểm tra; 7targeted tests PASS
(bao gồm actual valid/invalid preflight, timeout/redaction, deterministic paths,
default OFF và các ingress unit tests trước đó); Ruff/syntax/import PASS.
Guard25% của1CPU, RAM cap2GiB, reserve4GiB; peak51°C, active average50.28°C trên
4.92giây quan sát, không phải bằng chứng thermal endurance300giây. Guard cleanup
hoàn tất; không còn test listeners/workers. Frozen/data/source protected34checksums
PASS; prospective seal chỉ kiểm checksum, không mở nội dung. PostgreSQL volume và
ignored historical research artifacts giữ nguyên. Diagnostics local-only:
`.local-dev/nginx-preflight-20261107/` (reproduce/, fixed-v1/, test-guard/).

Next action duy nhất: bounded real-ingress OFF/ON privacy acceptance trong yêu cầu
tiếp theo. Preflight PASS không chứng minh live parity hoặc end-to-end privacy.

## Safe recovery / real-ingress acceptance — 2026-11-08

**CASE B — PARTIAL. Candidate mặc định/final OFF; chưa training-ready.** Local và
remote đã cùng ở `340c2e0` khi bắt đầu, chứa cả `391d34c` và các cập nhật Rust/host
worker; không cần merge lại. Backup local:
`codex/backup-real-ingress-391d34c-20261108`. Review36incoming historical commits/
121files: body-syntax implementation/contract không đổi; worker chỉ thêm startup
status và optional group-write socket (default0600), không đổi model_record/model.
Schema thêm constrained security signals; AI ingress vẫn tách Rules/Policy.
Migrations AI đã rename thành0011–0013: dùng **database lab mới**, không upgrade
volume cũ có migration history0005–0007. Không chạy host installer hoặc đổi services
ngoài lab. Binaries Rust/Student được build offline từ source hiện tại; binary cũ
được backup local. Frozen models/encoders/thresholds/releases không đổi.

Một workflow campaign được khóa trước traffic; hai startup attempts dừng trước
workflow do PID budget. Diagnostics xác nhận `pthread_create failed`,
`pids.max=64`, `pids.events max22`. Guard nay cho phép explicit `--tasks-max 128`,
default64 giữ nguyên, chỉ chấp nhận64–256.
CPU/RAM/thermal/independent watchdog giữ nguyên. Full lab dùng128, peak89tasks,
0PID-limit events; giảm Rust/Podman worker threads cũng được giữ. Không vô hiệu hóa
OS/firmware protection. Mọi startup evidence được bảo toàn, không dùng retry để
chọn scores hoặc đổi roles/cases/representation.

Actual Nginx preflight PASS. OFF chạy24requests:23qua locked checks gồm11CSRF,
form login204/me200, JSONlogout204/session401,6canary auth-denial401, empty và
malformed JSON400. Request24 (`POST /api/auth/activate`, octet-stream) gây dừng:
**expected415, edge401, StudentAudit415 với cùng request ID**. Student log xác nhận
`HttpMediaTypeNotSupportedException`. Khả năng error-dispatch bị authentication
chi phối phù hợp source, nhưng chưa trace hoặc so direct/backend để chốt chuỗi lỗi.
Không sửa Web/Policy, không đổi415 thành401 rồi chạy lại để báo PASS.

Candidate chưa bật,0numeric body events. ON/live body parity, oversized/chunked,
DVWA execution, worker/socket fail-open và final Rust/DB/API privacy scans chưa chạy.
Hai DVWA containers chỉ setup/preflight, đã cleanup; không thu cohort training mới.
6canary families đã gửi trongOFF nhưng final literal/encoded/digest scans chưa tới;
không gọi đây là privacy PASS. Nginx file trace trong phạm viOFF có0temp-file
O_CREAT và0entries còn lại ở5temp dirs; chưa chứng minh ON/error/oversize paths.
Privacy exclusions vẫn nguyên: không cho email/password/token vào syntax; derived
counts/syntax vẫn có side-channel risk, không có tuyên bố privacy tuyệt đối.

Postmortem offline (không replayHTTP): Frozen Requestv2 live/offline **24/24scores
khớp tuyệt đối**, threshold không đổi, body_observed=false, enforcement_actions0.
24unique Nginx IDs đều match StudentAudit;1status mismatch như trên. GLU207 chỉ
kiểm checksum/contract/correlation tests, không có actual Suricata-derived score;
không synthesize207features và không gọi whole-model/ON regression PASS.

Resource: full run106.36s, active90.17s average58.23°C, spike86°C; guard freeze+
reduce về25% của1CPU rồi thaw, cutoff90°C không chạm, watchdog healthy. Pause15.98s
được tách khỏi active average. Không có300s endurance claim. MemAvailable tối thiểu
19.87GiB, job memory peak551.22MiB; CPU ceiling50% của1CPU, mỗi container25% của1CPU.
Không đóng ứng dụng của người dùng. Lab listeners/workers dừng, DVWA/Maria/network
đã xóa; cả PostgreSQL cũ/mới dừng và volumes giữ nguyên. Không xóa artifacts cũ,
không mởsealed12, reviewPENDING không đổi.26historical artifact pins vẫn khớp;
worker source update c71f002 có provenance riêng, không hạ gate bảo vệ model.

Public sanitized acceptance matrix:
`ai-training/reports/REAL_BODY_INGRESS_20261108.json`.
Private diagnostics, protocols, logs, PostgreSQL material và binary backups:
`.local-dev/real-ingress-20261108/` — không publish. Existing clone/bootstrap/model
restore path không đổi. Harness mới ghi actual/expected status khi failure, không
lưu raw response. Tests/Ruff/syntax được kiểm riêng; full acceptance vẫn FAIL/PARTIAL.

**Một nhiệm vụ kế tiếp:** bounded OFF-only diagnosis so direct Student với Nginx
cho unsupported-media error dispatch, khóa baseline ứng dụng đúng theo evidence,
rồi chạy lại một OFF/ON privacy acceptance hữu hạn. Giữ evidence401/415 hiện tại;
chưa bắt đầu domain-adaptation research/training hoặc promotion.

## HTTP 415/401 recovery — 2026-11-08

**Original unsupported-media case FIXED; bounded Student OFF remains PARTIAL.**
Baseline `66fbe58`, working tree sạch trước nhiệm vụ. Không bật candidate ON,
không chạy full privacy acceptance, training, AWS hoặc thay Rules/Policy/frozen AI.

Equivalent harmless POST activation, fresh anonymous CSRF session mỗi route:

| Phase | Direct wire | Student Audit | Nginx upstream | Edge/client |
|---|---:|---:|---:|---:|
| Before fix | 401 | 415 | 401 | 401 |
| After fix | 415 | 415 | 415 | 415 |

Selected security-chain logs xác nhận thứ tự: POST activation → MVC unsupported
media (`DefaultHandlerExceptionResolver.sendError415`) → filter finally/audit415 →
container **GET `/error`** → security denial/anonymous entry point401. Nginx giữ
nguyên upstream401; không có `error_page`, `proxy_intercept_errors` hoặc `auth_request`
trong isolated config. Method của internal redispatch khác original HTTP request;
đó không phải một request mới từ client. IDs từng lượt riêng biệt, không tái dùng.

Minimal fix ở `ApiExceptionHandler`: map `HttpMediaTypeNotSupportedException` thành
complete generic JSON415 trong original dispatch, giữ negotiation headers từ
exception. Không bypass media validation, không mở `/error`/ERROR dispatch hoặc
đổi auth/CSRF/audit writer. Expected415 của harness không đổi. Actual post-fix trace
không còn ERROR redispatch cho case này. Success CSRF200, malformed JSON400,
missing-CSRF403, protected-anonymous401 và explicit `/error`401 đều giữ nguyên.
New embedded HTTP tests dùng servlet container thật vì MockMvc không tự thực hiện
container ERROR redispatch. **60fresh Java tests PASS**, gồm50existing API tests,
3real HTTP regression tests,3request-filter và4attribution tests; offline packagePASS.
43Python tests/Ruff/syntax PASS, gồm OFF-only refuses opt-in và giữ status conflicts.

### Status contract và Ground Truth

| Field | Meaning |
|---|---|
| Student Audit `status_code` | Observation khi request filter finally ghi audit; có thể intermediate hoặc synthetic500 khi `failed=true`. Không mặc định là final wire status. |
| Nginx `$upstream_status` | Upstream HTTP status proxy nhận; retry có thể tạo sequence, không tự ép thành scalar. |
| Nginx `$status` | Edge response log status; vẫn cần client receipt để xác nhận client đã quan sát response. |
| Client status | Status client thực sự nhận trong lượt kiểm tra. |

Giữ source/phase và identity riêng; không overwrite audit bằng wire để che conflict.
ID/method/route khớp không có nghĩa statuses bắt buộc bằng nhau. Existing derivative
đã giữ `application_status`, `wire_status`, `source_statuses`; không đổi feature
contracts207/588, datasets hoặc labels. Historical174 PATCH405/403 vẫn quarantine;
cơ chế415/401 mới **không chứng minh** nguyên nhân của174rows hay loại history impact.

### Bounded OFF result và điểm dừng

New `--off-only` chạy Student subset của protocol cũ, từ chối opt-in, bỏ DVWA/ON/
privacy stages. 32requests đã hoàn tất explicit wire-status checks: login204/me200,
JSONlogout204/session401,6fake auth denials401, empty/malformed/gzip/oversize JSON400,
unsupported415, chunked invalid JSON400; malformed form chưa có fixed expected status
trong protocol gốc và trả401. 32unique IDs match32audits. Frozen Requestv2 live/offline
parity32requests trong tolerance1e-7 đã PASS trước audit-consistency check.
0ONrequests,0candidate numeric events; không có DVWA attack probes.

**OFF dừng** ở một conflict khác: malformed form `%FF` tại login có audit500/wire401.
Source có synthetic500 mapping trong filter nhưng selected logs chưa xác định exact
exception/dispatch cho case này; không suy nguyên nhân chỉ từ415case. Giữ OFF PARTIAL,
không đổi expected status/nhãn hoặc ép PASS. Harness nay lưu structured PARTIAL
report trước khi fail, thay vì generic assertion; diagnostics patch được unit-test
nhưng không chạy lại traffic sau lần dừng. Original failed evidence giữ nguyên;
executed harness snapshot được khôi phục byte-exact bằng protocol SHA256.

Actual Nginx preflightPASS. Post-fix/OFF guard peak67°C, active average56.86°C;
watchdog healthy, lab processes/listeners dừng, PostgreSQL cũ/mới giữ nguyên volumes.
Frozen artifacts/seal checksumsPASS; không mở sealed samples, human reviewPENDING
không đổi. GLU207 không có new sensor score; chỉ giữ compatibility/hash evidence.
Production privacy vẫn NOT_VERIFIED. Clone/bootstrap/model restore flow không đổi.

Public aggregate: `ai-training/reports/HTTP_STATUS_RECOVERY_20261108.json`.
Private trace/log/receipts/source snapshots: `.local-dev/status-mismatch-20261108/`;
không push credentials, cookies, CSRF values hoặc raw HTTP evidence.

Một nhiệm vụ kế tiếp: bounded direct/proxy OFF trace cho malformed form để tách
audit500 với wire401 và xác định đúng exception/dispatch trước khi sửa hoặc qualify
semantics. Chỉ tiếp tục ON/privacy sau OFF PASS; không tự training.

## Final malformed-form recovery / bounded OFF PASS — 2026-11-08

**CASE A — bounded Student OFF PASS. Candidate vẫn OFF; ON/privacy chưa chạy.**
Baseline `aa5c89f`. Milestone này giải quyết conflict còn lại, không thay dataset,
models/encoders/thresholds, Rules/Policy, Suricata, correlation hoặc published releases.

Root cause đã chứng minh trên cả direct và Nginx, anonymous và valid authenticated
sessions: `org.apache.tomcat.util.http.InvalidParameterException`, declared400.
Khi validCSRF, lỗi nằm ở `UsernamePasswordAuthenticationFilter.obtainUsername`
qua `StrictHttpFirewall.StrictFirewalledRequest.getParameter`, **trước credential
verification**, ngoài MVC advice. Khi thiếuCSRF, parameter parsing lỗi tại
`CsrfTokenRequestHandler.resolveCsrfTokenValue`, trước khi token resolution hoàn tất.
Response lúc exception thoát còn200; audit500 trước đây đến từ `failed?500` nên là
synthetic status. Container tạo ERROR dispatch với original error_status400;
security trả401anonymous/403authenticated tại `/error`. Nginx giữ upstream status.
Không phải mọi500 đều là bad input; exception type, declared status và dispatch
attributes đã được kiểm riêng thay vì suy từ response hoặc exception message.

Shared fix ở `SecurityRequestFilter`: direct container parser exceptions với explicit
400/413 được trả generic JSON4xx ngay trong original dispatch. Unexpected uncommitted
Servlet/Runtime exceptions vẫn500; không map theo message hoặc arbitrary nested cause.
Audit ghi observed response status sau khi error được hoàn tất. IOException và
response đã commit tiếp tục propagate; không bịa wire status mới. MVC400/415 handlers
giữ nguyên. `/error`, auth/CSRF policy không mở quyền; metadata DEBUG logs không chứa
messages, body, credentials, cookies hoặc stack dump và không bật global mặc định.

Regression bắt được stale `Content-Length` khi chỉ resetBuffer; bản cuối reset response
chưa commit rồi restore security/session/request-ID headers, bỏ entity framing cũ.
Tests xác nhận buffered content không lọt, CSP/identity giữ nguyên; genuine internal
fault vẫn500/audit500 với generic body, không lộ private error details.

| Test surface | Result |
|---|---|
| Paired direct/proxy | 30requests mỗi phase; sau sửa mọi malformed-form variants400/audit400, không ERROR redispatch; session sau lỗi vẫn200 |
| Controls | Success200/204, malformed JSON400, auth failure401, CSRF403, unsupported media415; `/error` vẫn protected |
| Real embedded HTTP fault | Genuine unexpected service exception500/audit500; test-only injection, không cài fault endpoint vào lab app |
| Final-source Java | 15targeted testsPASS:5real HTTP,6filter-boundary,4attribution |
| Earlier API coverage | 50API testsPASS trước final framing-header correction; không gọi là full-suite rerun trên source cuối |
| Python / lint | 45tests, Ruff/syntaxPASS |
| Bounded Student OFF | **32requests PASS**,32unique IDs/32audits,0status conflicts; malformed form expected400 có căn cứ từ container exception contract |
| Frozen Requestv2 | Actual Nginx/worker offline-live parity32/32 trong tolerance1e-7; body_observed=false |
| GLU207 | Frozen hash/compatibility giữ nguyên; không tạo features hoặc new score khi thiếu sensor evidence |

Nginx preflight actualPASS. Candidate0ONrequests/0numeric events, không DVWA attack
probes hoặc full privacy scans. Đây là OFF PASS cho Student subset, không phải
full-system/production privacy hoặc model-quality evaluation. Status vẫn có source/
phase semantics ở các paths chưa qualify;174historical405/403 records và quarantine
giữ nguyên, không suy cùng cause hoặc sửa training/history/labels. Human reviewPENDING.

Thermal history được giữ đầy đủ: một rerun tại100% của1core bị watchdog cutoff90°C
dừng khi sensor đạt92°C, không auto-restart. Sau kiểm tra sensors ổn định, giảm xuống
25% của1core, cutoff85°C, chỉ rerun targeted tests cần thiết. Final OFF peak66°C,
active average57.35°C, watchdog healthy. Không đóng ứng dụng người dùng hoặc đổi
OS/firmware protections. Lab processes/listeners dừng; PostgreSQL cũ/mới và volumes
được bảo toàn, không xóa ignored research artifacts hoặc mở sealed samples.

Public sanitized report: `ai-training/reports/MALFORMED_FORM_OFF_RECOVERY_20261108.json`.
Private protocols, source snapshots, logs và receipts: `.local-dev/malformed-form-20261108/`.
Clone/bootstrap/model restore flow giữ nguyên. Không training, checkpoint mới,
promotion, enforcement hoặc AWS.

**Next action:** bounded real-ingress ON và end-to-end privacy acceptance trong
milestone riêng khi người dùng yêu cầu. OFF đã PASS; lượt này dừng tại đây.

## Body-syntax live acceptance — 2026-11-08

**CASE A — LIVE_OBSERVABILITY = VERIFIED_FOR_LAB.** Baseline `909680f`, cây Git sạch
khi bắt đầu. Một lượt acceptance hữu hạn đã PASS; không thu thêm cohort DVWA,
không dùng sealed samples, không training hoặc thay model đang chạy. Candidate
`http-body-syntax-v1` vẫn mặc định OFF; chỉ opt-in trong lab. Frozen models,
encoders, thresholds, Student Web, Rust main, Rules/Policy, Suricata và correlation
không đổi. Bootstrap/model restore và published Releases giữ nguyên.

Báo cáo tổng hợp có phạm vi từng gate:
[Body-syntax acceptance](../ai-training/reports/BODY_SYNTAX_LIVE_ACCEPTANCE_20261108.json).
Báo cáo do harness thực thi tạo, giữ nguyên để đối chiếu:
[Execution report](../ai-training/reports/BODY_SYNTAX_LIVE_20261108.json).
Private protocols, source snapshots, receipts, numeric vectors, traces và DB material
ở `.local-dev/body-live-20261108/`; không publish chúng hoặc runtime credentials.

### Luồng lab và contract

Nginx thật → trusted lab ingress/extractor → Unix datagram → candidate worker →
private numeric bridge → isolated Rust receiver → schema riêng → authenticated API.
Do Rust main cố ý từ chối body-version events ngoài frozen contract, thêm duy nhất
example `security-web/examples/body_syntax_lab.rs`, không sửa main ingestion/models.
Example chỉ build khi yêu cầu rõ `cargo build --example body_syntax_lab --locked
--offline -j1` trong `security-web`; không nằm trong normal bootstrap/build/run.
Khởi động còn đòi `IDPS_BODY_LAB_OPT_IN=YES`, loopback bind, private token tối thiểu
32 ký tự, private input/journal paths và DB URL qua environment. Thiếu opt-in bị
refuse. Không đưa credentials vào command history hoặc tài liệu. Test-only receiver
này không phải dịch vụ production được cài sẵn cho đồng nghiệp.

Receiver strict typed schema chỉ cho version, contract hash, request ID và 46 numeric
features; reject raw/unknown fields, sai ranges/state/version. Persistence dùng
`idps_body_syntax_lab.observations`, numeric journal và readonly `GET /observations`
trên loopback. API không auth401/auth200. Không gọi normalizer/model/alert/Rules/Policy;
không đưa 46 features vào frozen 588-input Request v2 hoặc GLU207.
Contract SHA256 không đổi:
`0e163b7392a9bb68131e4c66486fa5827ce6259295f0d703b403a8efad96982c`.

### Kết quả acceptance và giới hạn

| Gate | Status | Bằng chứng/phạm vi |
|---|---|---|
| NGINX_PREFLIGHT | PASS | Actual nginx configuration test |
| REAL_INGRESS_OFF_BASELINE | PASS | Reuse OFF baseline, 32 bounded paired controls; 0 numeric events |
| REAL_INGRESS_ON | PASS | 32 ON requests, explicit lab opt-in |
| APPLICATION_BEHAVIOR | PASS | OFF/ON statuses bằng nhau; login/session/logout, malformed400, unsupported415 |
| REQUEST_IDENTITY | PASS | Toàn bộ 73 Nginx IDs/statuses khớp Student Audit, 0 conflicts |
| BODY_SYNTAX_LIVE_PARITY | PASS | Reference/worker/Rust journal/DB/API khớp 32/32 vector, đủ 46 features |
| PRIVACY_CANARIES | PASS | Phạm vi canary hữu hạn bên dưới |
| BODY_TEMP_FILE_NON_PERSISTENCE | PASS | Không tạo temp files trong workload đã exercise |
| RUST_DB_DASHBOARD_PRIVACY | PASS | Isolated persistence và authenticated API; không qualify browser UI mới |
| FROZEN_REQUEST_V2_REGRESSION | PASS | 67 current-worker offline/live comparisons, tolerance 1e-7 |
| GLU207_REGRESSION | PARTIAL | Hashes/contracts/correlation tests giữ nguyên; không có sensor-derived live score |
| RULE_POLICY_REGRESSION | PASS | Core source/binary giữ nguyên, 0 firewall actions |
| RESOURCE_SAFETY | PASS | Guard healthy, quota/thermal/RAM bên dưới |
| LAB_CLEANUP | PASS | Owned services/listeners stopped, PG volumes giữ nguyên |

73 HTTP transactions gồm 32 OFF + 32 ON, 3 failure-phase CSRF GET và 6 direct
failure login/session requests. Execution report `HTTP_request_count=67` đếm helper
rows; 67 cũng là số Request v2 score comparisons thực tế. Normal Rust DB count160
là cumulative từ các lượt lịch sử, không phải số inference mới hoặc chất lượng model.

32 ON states: MISSING17, EMPTY1, OK8, MALFORMED2, OVERSIZE1,
UNSUPPORTED_ENCODING1, UNSUPPORTED_TRANSFER1, UNSUPPORTED_TYPE1. Missing khác empty;
body vượt 8 KiB bị withheld/OVERSIZE, không parse prefix rồi gọi TRUNCATED. Incomplete
HTTP truncation chưa exercise. 0 nominal drops, worker ổn định trước fault injection;
max numeric datagram278 bytes. Ba lỗi chủ động — extractor exception, worker thực sự
đóng socket, target không phải socket — đều latch candidate OFF, login204/session200;
không làm lỗi ứng dụng hoặc lộ exception details. Candidate/receiver cuối lượt OFF.

Sáu fake-secret families được đặt vào protected/unknown body values, Authorization
và extra Cookie, giữ nguyên session cookie hợp lệ. Quét literal, URL/base64/hex,
SHA1/SHA256, JSON-escaped trên 20 acceptance files, 15 runtime files, 21 security DB
và 14 Student DB tables, numeric telemetry/journals/artifacts và cả hai authenticated
APIs: PASS. Feature invariance khi thay protected values: PASS. Không publish canary
values hoặc fingerprints của chúng. Nginx temp dirs (body/proxy/fastcgi/scgi/uwsgi)
đều0700; inotify kể cả transient create/delete self-test healthy; file-only strace
0 temp O_CREAT; 0 residual entries. Không có raw body temp file để chứng minh lifecycle
ở những inputs không được chạy. Giữ nguyên private evidence thay vì coi quét canary
là chứng minh không thể có bất kỳ dữ liệu nhạy cảm nào.

**PRODUCTION_PRIVACY = NOT_VERIFIED.** Numeric counts/syntax/state/media/timing vẫn
có side channels, không có DP hoặc bảo đảm confidentiality tuyệt đối. Không qualify
arbitrary URI/User-Agent placements, mọi shutdown/persistence path, production
TLS/LAN/multitenancy/RBAC, multipart uploads, incomplete HTTP hoặc socket saturation.
API research chỉ loopback/token; không có browser frontend qualification mới.

### Hiệu năng, nhiệt và cleanup

Extractor trên 32 nominal ON calls: p50 **0.0094 ms**, p95 **0.0682 ms**, max
**0.1210 ms**. OFF/ON HTTP medians lần lượt258.74/141.65 ms; coarse cgroup CPU
24.44/23.94% của một core. Sequential order, warmup và reference inference/scanners
chi phối phép đo; không kết luận candidate tăng tốc hoặc ước lượng causal CPU overhead.
Harness RSS OFF122.1→183.8 MB, ON184.4→184.6 MB bao gồm predictor/caches/scanners;
không coi đây là isolated candidate memory overhead hoặc production benchmark.

Guard quota **25% của một core**, instantaneous cutoff85°C, no pauses, sensor/watchdog
healthy. Acceptance224.66s, active average **59.76°C**, peak **74°C**; không có đủ300s
để tuyên bố endurance dài hơn lượt chạy. Peak cgroup memory538.4 MiB; toàn hệ thống
MemAvailable tối thiểu19.13 GiB, vượt reserve4 GiB; không OOM/swap-thrashing event.
Không đóng ứng dụng của người dùng hoặc sửa OS/firmware protections. Build guard peak
76°C; targeted Python tests peak66°C. 57 Python tests, 1 Rust strict-contract test,
offline Rust example build, Ruff và Rustfmt PASS. Không rerun Java suite vì Student
source/jar không đổi; actual HTTP application acceptance là bằng chứng lượt này.

Tất cả owned lab processes/listeners/sockets đã dừng. PostgreSQL Nov7/Nov8 đều stopped,
volumes giữ nguyên. 158 protected current-file hashes và 26 legacy artifact pins
khớp; không mở sealed samples hoặc sửa datasets/labels/checkpoints/releases.

### Training readiness và đúng một bước tiếp theo

Candidate **đủ điều kiện làm đầu vào cho nghiên cứu representation trong lab**;
**TRAINING_READY=false, TRAINING=NOT_RUNNING**. Chưa có bằng chứng cải thiện
Recall/FPR/generalization từ acceptance này. 73 functional requests không phải
training release mới hoặc independent evaluation. Independent human review vẫn
**PENDING**; labels hiện có chỉ ở internal-Oracle research tier.

Còn phải khóa candidate encoder/model riêng (46 features không tự tương thích frozen
588/207); materialize/re-audit existing attack-intent release sau privacy projection;
kiểm exact/near/lineage collisions và strict group splits. Giữ identity exclusions,
không khôi phục email/password/token để xóa 6 residual login collisions. Kiểm lại
TRAIN/CAL workflow, benign POST và XSS/command-injection coverage sau quarantine;
khóa evaluation protocol trước model selection, giữ prospective samples sealed.
Chỉ training ở milestone khác khi data/feature/evaluation/recovery/resource gates đạt.

**Một nhiệm vụ kế tiếp:** bounded offline materialization/re-audit các candidate views
và strict group splits của attack-intent release hiện có, để chốt data readiness cho
một challenger được khóa riêng. Không capture thêm, tune threshold, training,
promotion hoặc deployment trong nhiệm vụ acceptance này. Dừng tại đây.

## Request Intelligence v3 data readiness — 2026-11-08

**CASE B — derivative hoàn tất, TRAINING_READY=false; không training.** Baseline
`8e069f0`. Chi tiết: [dataset readiness](24_REQUEST_V3_DATA_READINESS.md) và
[machine report](../ai-training/reports/REQUEST_V3_DATA_READINESS_20261108.json).

Final local build `ai-training/.artifacts/request_v3_body_syntax_20261108/release-v2/`,
version `request-v3-body-syntax-20261108-v1`, fingerprint
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`.
224records materialize/parity/reference checks PASS; fresh rebuild7files byte-identical.
634float32 input: frozen runtime numeric76/content512 + fixed-scale46body features;
no fitted normalization, no raw body/value/identity/secret-hash inputs added.

| Role | Parent strict | Candidate strict | Candidate unique views | Benign / Attack |
|---|---:|---:|---:|---|
| TRAIN |10|43|37|23 / 20|
| CALIBRATION |13|13|13|11 / 2|
| DEVELOPMENT |86|86|83|40 / 46|

TRAIN XSS8/command4/SQLi4/file2unique attack views, benign POST19 qua3FORM workflows;
đã cải thiện thiếu family/form coverage. TRAIN còn thiếu benign JSON POST và benign
command/file counterparts cùng surface. CAL minimumPASS, không population FPR claim.
DEV0benignPOST trong khi6POSTđềuattack: apparent gain có thể chỉ là method/body
shortcut.224receipts chỉ149EMPTY+75OK, khác live availability cóMISSING; giữ đúng
states, không tạo fake samples. All224mixed collision records35→6, stored-XSS group
29→0mixed; identity-excluded JSON-login6vẫn quarantine. Đây không phải Recall gain.

Roles/labels và raw/template/full/full-near/prior-admission/Oracle/lineage exclusions
giữ nguyên; chỉ tính lại runtime-representation/within-role view exclusions. Strict
candidate cross-role exact/near/lineage0overlaps; frozen-prefix similarity có thể
còn khi body khác. Sealed candidate overlapUNVERIFIED;12sealed không mở.142eligible
rows có internal Oracle; independent review224PENDING,0human verification mới.

Privacy scan đầu phát hiện inherited session_group chứa cookie digests: rejected.
Bản cuối dùng ordinal aliases, verify grouping bijection224rows. Chỉ bỏ unsafe
records copy vừa tạo của rejected build; source evidence/parent dataset không sửa
hoặc xóa, rejection diagnostics giữ local. Final scan137source values và transformed
forms,6canary families PASS_FOR_RESEARCH; per-request artifacts local-only.
PRODUCTION_PRIVACY vẫnNOT_VERIFIED, syntax/metadata side channels còn nguyên.

Khóa một [design](../ai-training/configs/research/request-v3-body-syntax-design-20261108.json):
634→64→64→64→64→8,53,640parameters, warm-startW0 thêm46zero rows, reset optimizer.
Synthetic initial-function parityPASS,0updates/0checkpoints. Frozen/calibration-only
controls và same-data CAL/DEV protocol khóa; actual634 recovery proof chưa chạy,
phải xác minh trước future fit. GLU207 livePARTIAL không chặn request-only offline
research. Không có runID, training service, checkpoint mới hoặc model promotion.

40final Python tests/Ruff/formatPASS. Quota25%onecore,cutoff85°C,reserve4GiB;
materialization v2 peak71°C, active average66.09°C, short finite workloads only.
158protected files/parent release giữ nguyên. Student/Security/Nginx/Rules/Policy/
Suricata/correlation, frozen weights/encoders/thresholds và Releases không đổi;
candidate mặc địnhOFF. Team clone/bootstrap/model restore flow giữ nguyên.

**Đúng một nhiệm vụ tiếp theo:** control-only Oracle campaign tối đa24receipts,
precommit TRAIN/DEVELOPMENT groups, bổ sung3TRAIN gaps và≥6uniqueDEVbenignPOSTviews
qua≥3workflows/FORM+JSON; thêm genuine missing-body controls khi feasible. Preflight
lineage/template/full-near/candidate-near trước HTTP; không copy templates giữaroles,
không mởsealed, không gán benign từ200 hoặc phát filler. Nếu không có Oracle/workflow
novelty phù hợp, dừng với coverage gap; không lặp capture vô hạn. Chưa thực hiện.

## Request v3 final coverage — 2026-11-08

**CASE C — command-control Oracle không vận hành được trong sandbox hiện tại.**
Baseline `467425a`. [Báo cáo](25_REQUEST_V3_FINAL_DATA_COVERAGE.md) và
[machine evidence](../ai-training/reports/REQUEST_V3_FINAL_DATA_COVERAGE_20261108.json).

Plan12main/9preflight, total targeted cap24, roles/templates/Oracles/coverage đã khóa;
pre-audit cả12planned cases không overlap theo checks đã định. Hai setup aborts do
session Oracle đọc sai namespace và cleanup masking được bảo toàn. Sửa reader theo
pinned DVWA `$_SESSION['dvwa']['username']`,3actualPHPfixturesPASS. Corrected preflight
1HTTP200nhưng không có ping packet/hostname Oracle: **UNKNOWN**, không admit benign;
main0, không tiếp tục capture. CLI probe cùng image/UIDwww-data/no-new-privileges
localhost-only exit2/PERMISSION_DENIED. Không đổi host security/thermal settings.

Observed1completed targeted receipt; conservatively reserve1possible prior dispatch,
global upper bound2≤24. Setup/auth24calls tách riêng, không là supervised receipts;
không claim toàn bộ HTTP traffic≤24. Per-request diagnostics local-only tại
`ai-training/.artifacts/request_v3_final_20261108/`; không raw bodies/headers/responses
hoặc cookie digests trong telemetry. Ordinal lineage aliases không chứa session values.

Parent dataset giữ nguyên fingerprint
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`:
TRAIN43/37views (23benign/20attack), CAL13/13views (11/2), DEV86/83views (40/46).
Không có new derivative release. TRAIN JSON/command/file benign gaps và DEV0benignPOST
còn nguyên; không thêm missingness giả. Review224PENDING, new UNKNOWN diagnostic riêng.

**Positive infrastructure proof:** actual634/53,640parameter warm start từ frozen v2,
new Adam step0, checkpoint reload và cross-process exact next update trên synthetic
fixturesPASS. Chỉ2synthetic updates,0actual-cohort updates. Proof/checkpoints ở
`ai-training/.artifacts/request_v3_final_20261108/synthetic-recovery/`, không inference/
promotion. Existing architecture/evaluation/thresholds không đổi, GLU207livePARTIAL
không là blocker của request-only offline research. TRAINING_READY=false.

46final Python tests/Ruff/formatPASS; peak guard66°C, quota25%onecore, reserve4GiB,
no thermal/watchdog failure. All owned lab resources dừng;158protected hashes, old
PG volumes, checkpoints/encoders và Releases giữ nguyên. Candidate defaultOFF;
clone/bootstrap/model restore, Web/Nginx/Rules/Policy/Suricata/correlation không đổi.

**Một blocker tiếp theo:** legitimate ping/Oracle cho application UID trong isolated
lab. Chỉ tiếp tục campaign đã khóa sau khi dependency đó được xác minh; không nới
privacy, sửa labels/roles hoặc thu filler. Không training/AWS/enforcement lượt này.

## Command Oracle sandbox recovery — 2026-11-08

**CASE A — command Oracle VERIFIED; không main capture/training.** Baseline `33e0b0d`.
[Báo cáo](26_COMMAND_ORACLE_SANDBOX_RECOVERY.md),
[machine evidence](../ai-training/reports/COMMAND_ORACLE_SANDBOX_RECOVERY_20261108.json),
[lab addendum](../ai-training/configs/research/command-oracle-sandbox-20261108.json).

Root cause: namespace `ping_group_range=0 0` loại GID33; ICMP datagram EACCES13,
ping fallback raw EPERM1. Binary0755/nosetuid/no capability xattr, loopbackUP;
không phải binary execution failure. Minimal fix chỉ DVWA research app launch:
`--sysctl "net.ipv4.ping_group_range=33 33"`. Worker/ping vẫn33:33/caps0/NNP1/seccomp2;
không thêmCAP_NET_RAW/root app/privileged hoặc đổi host/firewall/security profile.
Fresh default namespace sau cleanup vẫndeny; host range0–2147483647 giữ nguyên.

Real HTTP positive200:4tx/4rx/0%loss, ICMP kernel counters+4/+4; actual ping ancestry
khớp server worker PID/request ID. Negative thiếu authenticated session302,0packets,
UNKNOWN; valid session vẫn giữ. Separate same-identity/argv CLI exit0. HTTP child
exit không được DVWA expose trực tiếp; không bịa status0. Không admit diagnostic
benign/attack labels. Metadata observer chỉrequestID/PID/status, xóa cùng lab.

63Python tests và3actualPHPfixturesPASS; peak64°C, quota25%onecore, cutoff85°C,
reserve4GiB. Private evidence ở `.local-dev/command-oracle-20261108/`; raw HTTP/
cookies/session values và direct secret hashes không publish. Production privacy
NOT_VERIFIED, independent reviewPENDING.158protected hashes/oldPGvolumes/frozenmodels/
Rules/Policy/Web/Nginx/Suricata/correlation/Releases giữ nguyên; no sealed access.

12main/9preflight templates, roles, budget và Oracle predicates không đổi; UNKNOWN
cũ byte-identical. Parent fingerprint vẫn
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`;
TRAIN43/37views, CAL13/13, DEV86/83. Không derivative release/checkpoint/score mới.

**Next action:** tiếp tục bounded campaign đã khóa khi được yêu cầu, rebind source/
environment hashes và fresh physical execution IDs theo addendum, giữ logical parent
plan/roles/lineage; không reuse UNKNOWN ID hoặc sửa history. Recovery này không chạy
các workflow khác hoặc xác nhận overall training-ready. Main captureNOT_STARTED,
Requestv3 trainingNOT_STARTED; candidateOFF, bootstrap/model restore flow giữ nguyên.

## Request v3 grounded acquisition — 2026-11-08

**CASE C — preflight stopped at JuiceShop basket POST500.** Baseline `f22a1f3`.
[Báo cáo](27_REQUEST_V3_GROUNDED_DATA_ACQUISITION.md),
[machine evidence](../ai-training/reports/REQUEST_V3_GROUNDED_DATA_ACQUISITION_20261108.json).
Execution `request-v3-grounded-20261108-r1`: fresh IDs/source/environment bindings;
12templates/9preflights, roles/Oracle/coverage predicates ASTunchanged, planned overlap
checks clear. Effective DVWAlab33:33/CapEff0/NNP1/seccomp2,ping_group_range33 33;
nohostchange/capadd. Historical UNKNOWN không relabel/reuse.

6/9preflightscompleted: ping/publicfile/UNIONcanary/login/logoutPASS, basket-add500
UNKNOWN. Basket expectedownedproduct/quantityresponse absent; server-side cause
chưa giữ được sanitized witness nên không suy rootcause. Basketread/product/whoami
preflights chưa chạy. Main0/24;6diagnosticskhôngadmit supervised, không chạy mainđểdebug.
23setup/authcalls táchriêng. Existing prior2dispatchupperbound+current6=8, previous
recovery2diagnosticsriêng; không coi legacycounter7làhistorical-inclusive.

Private numeric diagnostics tại
`ai-training/.artifacts/request_v3_grounded_20261108/campaign-final-r1/`, execution/
request IDs, ordinal lineage, intent/outcome/observationstatus và explicit non-admission;
review6PENDING. Không rawHTTPbody/headers/responses,cookie/token/digests trong artifacts.
2naturalMISSINGchỉlàpreflight; nofakecoverage hoặc independentGTclaim.

Không derivative release/freshrebuild vì chưa có admittedmaincohort. Parent224release
fingerprint vẫn `5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`;
TRAIN43/37views(23benign/20attack),CAL13/13(11/2),DEV86/83(40/46). TRAINJSONPOST0,
command/filebenigncounterparts0;DEVbenignPOST0,coverageFAIL. CALroles,strictsplits,
35→6mixedcollisionrecordsevidence giữ nguyên,sealedcandidateoverlapUNVERIFIED.
634contract/53,640parameterdesign/LR/budget/evaluation/recoveryproof giữ nguyên;
RESEARCH_PILOT_READY=false,INDEPENDENT_QUALITY_CERTIFIED=false,trainingNOT_STARTED.

65tests/Ruff/formatPASS. Capturepeak64°C,activeavg56.90°C;overallpeak66°C;
quota25%onecore,cutoff85°C,reserve4GiB,no thermal/watchdogfailure. LabcleanupPASS,
158protectedhashes/oldUNKNOWN/PGvolumes/frozenmodels/Rules/Policy/Web/Nginx/Suricata/
correlation/Releases giữ nguyên,candidateOFF. ProductionprivacyNOT_VERIFIED.

**Next action duy nhất:** bounded diagnosis ownedBasketItems POST500, sanitized
errorclass/status+readonlystatewitness, freshdiagnosticID; không đổi templates/roles/
Oracle để épPASS và không capturemain trước Oracle verification. Dừng milestone.

## Basket Oracle HTTP500 root cause — 2026-11-08

**CASE A — root cause VERIFIED: TEST_FIXTURE_ERROR.** Baseline `2ba9722`.
[Báo cáo](28_BASKET_ORACLE_ROOT_CAUSE.md),
[machine evidence](../ai-training/reports/BASKET_ORACLE_ROOT_CAUSE_20261108.json).

Fixture đăng nhập seededadmin; ownbasket đã cóProductId1/quantity2. POSTCREATE
ProductId1/quantity1vào cùngbasket chạm unique(ProductId,BasketId). Read-only state
xác nhận ownership/product/stock/limit hợp lệ, existingpair1row,3basketitems.
Actual POST500 với SequelizeUniqueConstraintError/SQLITE_CONSTRAINT, stack
`basketItems.js:79` tại `.save()`. GETauthenticated200khớpDB, quantityvẫn2;
statebefore/afteridentical,0successfulmutation. Không phải Oracle cần đổi500thành200.

Đúng2BasketdiagnosticHTTP+1loginsetuphoàn tất, không main/preflight campaign.
Các earlierreadiness/toolattempts chưa hoàn tất BasketHTTP;1earlierloginsetupdispatch
responseunconfirmed ghi riêng. Diagnostic helper dùng installed `/nodejs/bin/node`,
OPEN_READONLY và sanitized error class/category/known locations; no rawHTTP/session/
secret values/digests. Product-witness helper cũ cũng dùngnodequaPATH là separate
blocker chưa sửa, không phải cause của Basket500.

**Correction đề xuất duy nhất, chưa thực hiện:** dedicated authenticated fixtureaccount
vớiownbasketrỗng; readonlyverifyProductId1pairabsent trước existingCREATE,giữProductId1/
quantity1/method/endpoint/dynamicBasketID. Version/reviewfixtureenvironmentrevision;
không xóa/repairseed, đổiPOST→PUT/upsert, đổirole/expectedstatus hoặc relabelUNKNOWN.
CurrentOracle refusal đúng nhưng successworkflow vẫnBLOCKED_FIXTURE_PRECONDITION;
preflightNOT_RERUN/mainNOT_STARTED/trainingNOT_STARTED.

Parent224release fingerprint vẫn
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`;
TRAIN43/37views,CAL13/13,DEV86/83,roles/strictsplits/UNKNOWN giữ nguyên.
13targetedtests/Ruff/formatPASS,peak64°C,quota25%onecore/cutoff85°C/reserve4GiB;
labcleanupPASS,158protectedhashes/oldPGvolumes/frozenmodels/Rules/Policy/Web/Nginx/
Suricata/correlation/Releases giữ nguyên. Nosealedaccess/checkpoints/enforcement/AWS.
Evidenceprivate tại `.local-dev/basket-oracle-20261108/`; independentreviewPENDING,
noindependentquality hoặc productionprivacyclaim. Dừng,khôngautofix/capture.
