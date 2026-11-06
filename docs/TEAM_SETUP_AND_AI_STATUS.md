# Team setup và trạng thái AI-IDPS

Cập nhật 2026-11-06. Tài liệu phản ánh integration candidate local, **chưa commit/
push các thay đổi mới**. Remote branch hiện chưa tự chứa working tree này; người
bàn giao phải review/commit/push được cho phép trước khi yêu cầu đồng nghiệp clone
để tái lập milestone mới. Không tải raw research20GB để chạy inference.

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
  --scope --output .local-dev/ids-guard-demo --quota 5 --max-seconds 1800 -- \
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
  --output .local-dev/glu-guard-demo --quota 5 --max-seconds 900 -- \
  ai-training/.venv/bin/python scripts/glu207-live-shadow.py \
  --sensor .local-dev/ids-demo --output .local-dev/glu-demo --max-requests 12
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

Đây là **bounded asynchronous shadow consumer**, chưa phải continuous low-latency
serving: snapshot/collector/history replay có overhead lớn, nhất là quota5%.
Đừng nhầm inference-only latency với event-to-result latency. Collector status
JSON không phải heartbeat của GLU worker riêng; xem journal/API và resource report.
Run12requests: predict-call280–357ms, nhưng event-to-result159–542s, mean381s.
Chưa đạt yêu cầu phục vụ liên tục. Không tự tăng tải để che bottleneck này.

## Kiểm tra và quan sát

```sh
ai-training/.venv/bin/python scripts/test-three-source.py
python3 scripts/verify-three-source.py --sensor .local-dev/ids-demo
python3 scripts/verify-ai-local.py
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
nhưng không tuyên bố host luôn an toàn; full56Rust tests chưa hoàn tất do thermal
stop/deadline. Không tự đóng user apps hoặc tăng quota để vượt gate. Total shared
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
