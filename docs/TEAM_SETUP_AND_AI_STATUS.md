# Team setup và trạng thái AI-IDPS

Cập nhật 2026-11-07. Integration branch chứa các milestone local shadow, three-source
và Rule–AI coordination; xem `git log -5 --oneline` để xác định revision clone.
Model release frozen giữ nguyên. Không cần raw research20GB để chạy inference.
Báo cáo integration: [Rule–AI coordination và tối ưu](16_RULE_AI_COORDINATION.md).
Milestone research trước: [Data quality và Oracle cohort](17_DATA_QUALITY_AND_ORACLE_RESEARCH.md).
Milestone trước: [Training data unblock](18_TRAINING_DATA_UNBLOCK.md).
Milestone trước: [Final training unblock và pilot kỹ thuật](19_FINAL_TRAINING_UNBLOCK.md).
Milestone hiện tại: [Scaled matched normalization experiment](20_SCALED_NORMALIZATION_EXPERIMENT.md).

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

**Data/recovery/evaluation gates PASS, cấu hình đã khóa để launch nền.** Git report
là prelaunch snapshot; dùng local`status.json`/status CLI làm runtime truth sau launch.
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
