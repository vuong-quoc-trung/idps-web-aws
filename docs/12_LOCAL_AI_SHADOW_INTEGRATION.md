# Local AI shadow integration

Milestone này được tiếp nối bởi [Local demo stabilization](13_LOCAL_DEMO_STABILIZATION.md).
Policy build hiện tại bổ sung hard stop79°C ở watchdog cho cả build frozen;
các số đo94°C dưới đây là evidence lịch sử, không phải policy được chấp nhận hiện nay.

Trạng thái thực nghiệm của milestone được ghi tại
`ai-training/reports/LOCAL_INTEGRATION_20261106.json`. Không coi build/fixtures là
live integration. Không có training, thay encoder/threshold, admission, IPS hoặc
AWS deployment trong milestone này; chưa commit/push các thay đổi.

## Luồng thực tế được triển khai

```text
Browser/client → local Nginx :18780 → Student API :8080 / frontend :5173
                    │
                    ├─ sanitized access log → existing Rust ingestion
Student audit ──────┘                         → normalized_events
                    │
                    └─ opt-in API access syslog / private Unix datagram socket
                         → bounded RAM queue (64, max8KiB/datagram)
                         → frozen Request Intelligence v2
                         → metadata-only rotating JSONL journal
                         → same Rust file cursor/rotation watcher
                         → ai_shadow_results / ai_shadow_worker
                         → authenticated /api/ai-shadow
                         → AI shadow tab in existing Security Web :3001
                         → above-threshold only: existing security_alerts,
                           source AI_SHADOW, action ALERT, no firewall call
```

Nginx gửi observation ở access-log phase sau response, tách hoàn toàn khỏi đường
inference đồng bộ. HTTP URI và ba header được chọn chỉ đi vào socket private/RAM;
không log ra file, database hoặc báo cáo. Canonical telemetry cũ không bị đổi.
Quan sát cả rule-negative và rule-positive API requests. Nginx log vẫn không lưu
raw query; detector rules cũ vẫn hoạt động. Local opt-in không dùng upstream VM
backup; template production `security-web/nginx/pbl4-proxy.conf` giữ nguyên.

**Shadow bắt buộc:** worker không có endpoint/credentials để block hoặc thay
response. Rust AI ingestion không gọi policy/firewall, không cấp IP cho auto
response. Cấu hình demo `ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false`, helper
`/bin/false`; không sửa cấu hình bảo vệ production. AI score không là Ground Truth.

## Setup và khởi động

Yêu cầu local: Linux/systemd user/cgroup v2, CPU hwmon sensors, Docker cho hai
PostgreSQL dev, Java25/Maven wrapper, Rust toolchain, Node/npm, Python AI pin từ
Team Release. Các cổng bind loopback. Không tạo cloud resource hoặc host service.

```sh
./scripts/bootstrap-team.sh --tests
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx
```

Lệnh thứ hai tái sử dụng foundation launcher/DB volumes hiện có, build ứng dụng
bằng resource guard rồi chạy chúng; thiếu Nginx thì chỉ extract Ubuntu package
vào runtime local. Không cài hoặc thay system Nginx. Không thay firewall/firmware.
Nếu bootstrap/toolchain/build lỗi hoặc thermal guard dừng, sửa điều kiện lỗi rồi
chạy lại; không bỏ check để tuyên bố PASS.

Sau khi đã build đúng source hiện tại:

```sh
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx --skip-build
python3 scripts/verify-ai-local.py
```

Student qua Nginx: `http://127.0.0.1:18780/`.
Security Web: `http://127.0.0.1:3001/` → đăng nhập → **AI shadow**.
Tài khoản/password dev được foundation launcher sinh ngẫu nhiên và giữ trong
`.local-dev/foundation/credentials.json` (ignored/private), không hardcode/công bố.
Student username `foundation-admin`, Security username `admin`. Không dùng các
credentials này cho production. Tài liệu/screenshot không cần chứa password/token.

Copy `X-Request-Id` của một HTTP response rồi tra trong tab AI; bảng hiển thị
score, frozen model version, threshold và comparator `>`, feature availability,
latency, nguồn canonical tương quan. Cảnh báo vượt ngưỡng cũng xuất hiện trong
tab Cảnh báo với source `AI_SHADOW`. Worker heartbeat stale sau10s được hiển thị;
STALE không tự biến thành “model đánh giá request là benign”.

```sh
# Chỉ thao tác AI; giữ Student/Security/Nginx hoạt động
./scripts/dev-up-and-verify.sh --ai-worker stop
./scripts/dev-up-and-verify.sh --ai-worker start
# Tắt riêng local foundation stack; giữ DB volumes, credentials và evidence
./scripts/dev-up-and-verify.sh --stop
```

Không đổi ports/exposure/AI mode khi stack cũ còn chạy; launcher từ chối cấu hình
khác. Worker được giám sát tối đa2giờ/phiên; hết thời gian sẽ dừng an toàn, không
tự restart vô hạn. Sau demo nên stop để không giữ tài nguyên không cần thiết.

## Contract, privacy và reliability

`nginx-ai-1`: timestamp thật, Nginx-generated request ID32hex, method, request URI,
User-Agent/Accept/Content-Type. Không Cookie, Authorization, body, IP, actor,
status/rule/SID/label vào tensor. Giá trị header thiếu `-`/rỗng được loại trước
encoder; không giả header/body là đã quan sát đầy đủ. Đây là profile
`selected_headers_no_body`; có domain-shift/missingness so với dữ liệu nghiên cứu.

Worker chỉ nạp manifest SHA256 pin độc lập, rồi kiểm file hashes của portable
bundle; không chấp nhận bundle tự ký lại bằng manifest mới. Model:
`request-intelligence-v2-frozen-step3072`, 50,696 parameters, encoder frozen
`rich_content_v2+bounded-request-v1`, threshold0.8826237916946411, strict `>`.
Mọi score/error kết quả có request_id và worker_id. `ai-shadow-1` output chỉ có
các trường typed/allowlisted; Rust từ chối extra field, threshold/model mismatch,
flags giả hoặc enforcement_actions khác0. Parser errors không echo raw content.

Socket directory0700/socket0600. Cùng UID local là trust boundary, không phải
cryptographic collector attestation. Queue/socket đầy hoặc worker down thì mất
observation, không block request; không có durable raw replay. Nginx syslog có
giới hạn message của implementation; truncation/JSON sai bị reject, không chấm
phần URI bị cắt như một request đầy đủ. Counters chỉ đo được những datagram worker
đã nhận và queue nội bộ; không khẳng định đo toàn bộ mất mát trước socket.

Journal4 generations, mỗi file2MiB; Rust watcher tái sử dụng inode/offset/anchor
và rotation, DB unique request_id ngăn nhân đôi result/alert. Nếu dashboard/DB
down lâu hơn retention có thể mất metadata. AI result table giữ tối đa10k/7ngày
qua retention worker. `security_alerts` kế thừa chính sách lưu của hệ thống cũ.
Heartbeat không ghi vào bảng results; một singleton status phục vụ readiness.

## Thermal và tài nguyên

Mọi AI worker chạy dưới cgroup guard độc lập, một BLAS thread, ban đầu quota10%
của một CPU, MemoryMax<=2GiB, swap0. Worker tự kiểm CPU hwmon mỗi.2s, pause từ72°C
hoặc tăng nhanh, chỉ resume dưới65°C ổn định5s, stop tại80°C hoặc system RAM30GB.
Sensor failure → `THERMAL_CONTROL_NOT_VERIFIED`, không chạy model tiếp. Watchdog
ngoài worker dừng cgroup ở>=79°C hoặc monitor heartbeat stale3s; vẫn có thể
overshoot giữa hai sample. Không hứa kiểm soát nhiệt của workload khác trên host.

Đã sửa lỗi guard cũ “reduce” thành10% có thể tăng quota ban đầu nhỏ hơn10%; quota
giảm mới không vượt quota người gọi. Test tương ứng có trong
`ai-training/tests/test_integration_candidate.py`. Cả các thermal stops và lần
build bị dừng chủ động phải giữ trong evidence; không xóa kết quả xấu.
Riêng **build tools**, `--build-pause` freeze từ65°C (watchdog riêng từ70°C),
resume dưới60°C ổn định5s, giữ trạng thái compiler thay vì hủy build lặp lại.
Không dùng mode này cho AI inference/training. Sensor/heartbeat lỗi vẫn kill
cgroup. Host có lần đạt94°C trong phiên build; đây không phải chứng nhận giữ
nhiệt toàn máy dưới80°C. AI mode giữ nguyên hard stop. Các lần build dừng do
thermal hoặc lỗi control được giữ trong evidence, không đổi thành PASS.

Local serving processes của chế độ `--ai-shadow` cũng ở scope quota10%/1GiB,
nhưng sensor/AI watchdog không là bộ quản lý nhiệt cho mọi ứng dụng của máy.

## GLU207, Suricata và trước AWS

GLU207: **AVAILABLE_BUT_NOT_LIVE**. Các quan sát Student/Nginx có request ID,
nhưng chưa có causal correlated Suricata flow/byte/history bridge đủ207 cột với
đúng frozen semantics và parity. Không zero-fill các cột để giả live GLU.

Foundation có watcher Suricata cũ, nhưng demo này chưa khởi động packet capture
Suricata live. Không chèn EVE giả để tuyên bố đã có sensor. Nginx heuristic alerts
là nguồn `NGINX`, không được gọi là Suricata detection. Luồng RIv2 không đợi EVE.

Trước AWS còn cần: telemetry vantage sau TLS được cấp phép; full/partial feature
profile policy; loss accounting, queue/retention sizing; service identities,
permissions và deploy supervision; secret management; target-host latency/resource
budget; external/security regression tests; live Suricata integration nếu dùng
GLU; kiểm chứng detection độc lập ở milestone riêng. Không suy ra production
readiness từ việc một đường HTTP local đi qua đủ các thành phần.

## Files và kiểm chứng

Worker/acceptance scripts trong `scripts/ai-shadow-worker.py`,
`scripts/verify-ai-local.py`, `scripts/test-ai-shadow.py`; foundation launcher và
tests được mở rộng opt-in. Rust: `ai_shadow.rs`, migration0005, router/watcher/
retention hooks; UI: `AiShadow.tsx`, navigation/icon/source filter. `.env.example`
thêm đường dẫn journal tùy chọn, không secrets. Student business/auth/DB code,
frozen AI source/model/contracts, production Nginx/Suricata configs giữ nguyên.

Kiểm nhẹ: `python3 scripts/test-ai-shadow.py`,
`python3 scripts/test-dev-launcher.py`, `npm --prefix security-web/frontend test`,
targeted AI guard pytest. Rust có kiểm schema/forged flags và SQLx test idempotency,
alert-only/no-firewall. Kết quả thực tế cuối cùng và tiêu chí chưa đạt phải đọc ở
báo cáo milestone; phần này mô tả cách kiểm, không tự xác nhận PASS.

## Kết quả live đã quan sát ngày06/11/2026

Foundation HTTP/CSRF/login/ADMIN/me và hai source cùng request ID đã PASS.
`verify-ai-local.py` đã hoàn tất một acceptance PASS gồm6 request thật, worker
SIGKILL/restart, heartbeat stale, bundle thiếu/hỏng và canary privacy. API cuối
lọc đúng request ID và hiển thị AI alerts qua storage/search hiện có; browser đã
hiển thị score/correlation/threshold và cả trạng thái lỗi, không xóa lượt lỗi cũ.

| Query thử an toàn tại `/api/auth/csrf` | Score frozen RIv2 | Vượt ngưỡng |
|---|---:|---|
| Benign | 0.007611 | Không |
| Benign search | 0.034860 | Không |
| SQLi-shaped | 0.998343 | Có |
| XSS-shaped | 0.998591 | Có |
| Command-shaped `;id` | 0.028561 | Không |
| Sensitive-field canary | 0.007679 | Không |

Cả6 response là200; đây là syntax probes tới endpoint an toàn, **không có exploit
success hoặc nhãn attack intent độc lập**. Không suy ra Recall/FPR. Command-shaped
query không bị AI flag; không chỉnh threshold để đổi kết quả. Header profile khác
DVWA cũ nên kết quả XSS này không chứng minh đã sửa lỗi generalization.

Sáu score sau warm-up:42.82–60.34ms, mean53.03ms; một client quan sát hoàn tất6
request trong1.55s (~3.87request/s), không phải sustained capacity. Phép đo
`latency_ms` bao quanh `predict()`: wall time gồm cgroup pause/throttling, không
gồm queue wait hoặc transit tới DB/UI. Các lượt khác có cold score~2.24s và một
score sau restart~21.425s do điều tiết nhiệt; HTTP của request restart đó~120ms.
Không dùng số mean warmed để hứa SLA cho mọi request.

Trong fault test, Student trả200 khi worker bịSIGKILL (~238ms) và sau hai lỗi
model. Không replay HTTP bị mất lúc worker down. Restart phục hồi nhưng có thể
bị delay do thermal pause; journal/DB vẫn giữ các kết quả trước đó. RAM tổng dùng
trong các phiên được ghi ở report; peak vẫn dưới30GB. Host temperature từng94°C,
AI hard stops và supervisor refusals được giữ nguyên. Môi trường nhiệt còn là
giới hạn vận hành thực tế, không bị che bởi functional PASS.

Scripts khởi động không xem “PID đã spawn” là model ready: cần heartbeat fresh.
AI startup lỗi không ngăn Student/Nginx/Security khởi động; foundation report và
AI acceptance có scope tách biệt. Cold Student startup tại quota10% từng278s;
launcher chờ tối đa360s. Nếu sửa/build source khi demo đang chạy, `--stop` trước
khi chạy lại để tránh tái sử dụng binary cũ.

Kiểm thử cuối:52/52 Rust regression PASS;2/2 Rust AI tests trên source cuối PASS;
21 targeted Python tests,4 worker tests,3 launcher tests và3 frontend tests PASS.
Frontend build, Ruff phần mới, Rust format và Git diff check PASS.378 protected
original paths không đổi; Student source và frozen AI checkpoint/source/config
không đổi. Xem JSON report cho timestamp/runtime readiness cuối và bằng chứng
resource; test PASS không xóa giới hạn nhiệt đã ghi.

Snapshot nghiệm thu cuối:worker `READY`, heartbeat fresh và một HTTP request mới
tiếp tục được chấm sau lần khởi động cuối. `LOCAL_INTEGRATION_READY=TRUE` áp dụng
cho **demo local shadow nhỏ đã kiểm chứng**, không là cam kết worker sẽ luôn sẵn
sàng khi host tiếp tục quá nhiệt. Các dịch vụ demo được để chạy để kiểm tra UI;
watchdog vẫn bật và phiên AI tối đa2giờ. GLU207 live và AWS preparation vẫn chưa
đạt. Chưa commit/push các thay đổi trong milestone này.
