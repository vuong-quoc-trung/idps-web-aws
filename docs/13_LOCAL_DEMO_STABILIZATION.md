# Local demo stabilization — 2026-11-06

Tiếp nối milestone12; không training, thay encoder/threshold, commit/push hoặc
tạo tài nguyên AWS. Kết quả máy đọc được ở
`ai-training/reports/LOCAL_STABILIZATION_20261106.json`; evidence runtime nằm
trong `.local-dev/stabilization/` và các acceptance JSON private của từng runtime.
Report trước vẫn giữ nguyên, gồm cả thermal failures và inference errors lịch sử.

## Những thay đổi có mục đích

**Khởi động:** launcher không nhận heartbeat cũ làm bằng chứng cho worker mới.
Sau model-ready, gửi tối đa3HTTP probes qua Nginx và chỉ nhận startup PASS khi
request ID đã được chính worker hiện tại chấm. Nếu Nginx còn giữ peer Unix cũ,
datagram đầu có thể mất; các probe IDs chưa được chấm được ghi lại. Startup check
không hứa mọi request sau đó sẽ được nhận. Không có replay raw HTTP.

**Quan sát thiếu telemetry:** endpoint `/api/ai-shadow` trả thêm `delivery`, đếm
distinct request IDs Nginx trong5phút gần nhất, bỏ15giây đang xử lý. Hiển thị
scored, inference errors và unresolved trên tab AI cũ. Unresolved có thể do mất
datagram, rejection, worker down hoặc ingestion chậm. Denominator chỉ gồm request
đã được canonical ingestion quan sát; nếu cả hai kênh mất thì không đo được.
Không gọi đây là loss rate hay lossless delivery. Cửa sổ rỗng không chứng minh
kênh đang tốt. `collection_enabled=false` được cảnh báo rõ.

**Lifecycle:** launcher lock ngăn hai lệnh thay runtime đồng thời; PID start token
ngăn thao tác PID tái sử dụng. Các service mới chạy trong named user scopes để
stop cả descendants. Dừng Nginx trước worker, rồi frontend/Rust/Student, sau cùng
hai DB; giữ volumes/credentials/evidence. Chỉ reuse/stop container có ownership
label `idps.foundation=true`. Không tự restart worker vô hạn sau lỗi nhiệt/model.
Java opt-in giới hạn heap768MiB và active processor count1, phù hợp scope quota;
HTTP startup timeout10phút vì cold Spring/JIT có thể lâu ở quota10% một CPU.
Timeout không được coi là readiness. CLI `--status` không thay đổi dịch vụ.

Runtime sạch đã phát hiện race mà DB cũ che khuất: Tomcat/CSRF nhận HTTP trước
khi `AdminBootstrap` CommandLineRunner commit tài khoản. Khi AI startup bị guard
từ chối ngay, login smoke chạy sớm và trả401. Launcher nay đợi row admin commit
(bounded120s) trước AI/login; không sửa Student hoặc tự seed/reset password.
Unit test mô phỏng DB chưa có admin rồi mới có để kiểm điều kiện readiness này.

## Thermal policy hiện tại

Trước mỗi build opt-in: lấy25samples/5giây trên toàn bộ coretemp/k10temp/zenpower,
chỉ bắt đầu nếu max<65°C và system used RAM<28GB. Khi chạy build, freeze65°C hoặc
tăng>=5°C/s từ60°C; giảm quota10→5%, resume<60°C ổn định5s. Watchdog riêng freeze
70°C và **kill>=79°C ngay cả khi build đang frozen**; sensor/heartbeat failure kill.
Điểm này thay policy build cũ đã cho phép host đạt94°C khi compiler frozen.

AI giữ policy riêng: pause72°C hoặc tăng nhanh từ65°C, hard stop80°C, watchdog
79°C; worker chỉ resume dưới65°C ổn định5s. Kernel quota/MemoryMax/swap0 vẫn giữ;
ngân sách RAM toàn host30GB dùng chung. Không hạ thermal protection OS/firmware.
Unit tests inject79/80°C và sensor failure; không cố làm nóng máy để test hard stop.
Nhiệt bên ngoài có thể tăng giữa các sample; không chứng nhận nhiệt toàn host.

## Cách trình diễn cho đồng nghiệp

Yêu cầu và bootstrap model/toolchains theo [hướng dẫn integration](12_LOCAL_AI_SHADOW_INTEGRATION.md).
Không cần raw research dataset; inference dùng bundle có checksum từ Team Release.
Các port mặc định đều loopback, credentials tự sinh trong ignored runtime0600.

```sh
./scripts/bootstrap-team.sh --tests
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx
# Những lần sau, khi artifact build khớp source hiện tại:
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx --skip-build
./scripts/dev-up-and-verify.sh --status
```

Student `http://127.0.0.1:18780/`, Security `http://127.0.0.1:3001/`.
Đăng nhập bằng credentials private trong `.local-dev/foundation/credentials.json`;
không copy credentials vào báo cáo/chat. Tab AI phải có heartbeat READY mới.
Gửi request an toàn, lấy `X-Request-Id` rồi tra trong tab AI:

```sh
curl -i 'http://127.0.0.1:18780/api/auth/csrf?search=ordinary-course'
python3 scripts/verify-ai-local.py
```

Acceptance dùng sáu query vô hại trên endpoint CSRF; chuỗi trông giống SQLi/XSS
không được thực thi như exploit. Kết quả chứng minh đường tích hợp, không phải
Recall/FPR hoặc độc lập đánh giá chất lượng model. Canary query nhạy cảm giả được
loại trước encoder, không lưu raw value. Threshold frozen strict `>` giữ nguyên.

```sh
./scripts/dev-up-and-verify.sh --ai-worker stop
curl -I http://127.0.0.1:18780/
./scripts/dev-up-and-verify.sh --ai-worker start
# Kiểm crash/model faults, restart Rust giữ dữ liệu, rồi tắt sạch:
python3 scripts/verify-ai-local.py --stop-after
# Hoặc tắt trực tiếp:
./scripts/dev-up-and-verify.sh --stop
```

Không vừa chạy acceptance vừa thao tác launcher khác. Sau sửa source, stop rồi
build/start lại để không reuse process cũ. Build bị guard từ chối/dừng: chờ host
ổn định và xem resource report; không bỏ check hoặc tăng quota để ép hoàn thành.

## Runtime sạch và giới hạn tái lập

Launcher và acceptance hỗ trợ `IDPS_DEMO_RUNTIME`, `IDPS_DEMO_CONTAINER_PREFIX`
và các `DEV_*_PORT`; không hardcode home directory. Ví dụ cùng checkout, sau khi
stop demo cũ, tạo runtime/credentials/DB mới, dùng build/dependency cache hiện có:

```sh
export IDPS_DEMO_RUNTIME="$PWD/.local-dev/demo-clean-2"
export IDPS_DEMO_CONTAINER_PREFIX=idps-demo-clean-2
export DEV_EDGE_PORT=18781 DEV_API_PORT=18080 DEV_FRONTEND_PORT=15173
export DEV_SECURITY_PORT=13001 DEV_STUDENT_DB_PORT=55435 DEV_SECURITY_DB_PORT=55436
export NGINX_BIN="$PWD/.local-dev/foundation/tools/runtime/usr/sbin/nginx"
./scripts/dev-up-and-verify.sh --ai-shadow --skip-build
python3 scripts/verify-ai-local.py --stop-after
```

Socket pathname phải ngắn hơn104bytes; không có dấu phân cách Nginx. Runtime mới
không tương đương clean clone + build mọi dependency; phạm vi kiểm chứng thực tế
ghi trong report. Không publish runtime, DB dumps, raw logs hay evidence chứa
session material. GitHub Release chỉ phục vụ portable model bundle đã duyệt.

## Kết quả kiểm chứng cuối

- Hai acceptance runs PASS, mỗi run6HTTP requests, Nginx + Student audit correlation,
  frozen scores và zero AI enforcement. Runtime thứ hai dùng DB/credentials mới.
- Worker SIGKILL: Student vẫn200; heartbeat stale được thấy, scoring phục hồi qua
  launcher. Missing/invalid bundle fail safely, không dùng status cũ cho probe mới.
- Restart Rust giữ51/51AI rows ở runtime cũ,11/11ở runtime sạch. API không auth
  trả401. Browser session bị vô hiệu sau Rust restart: đăng nhập lại là hành vi
  đúng, không nới auth hoặc lưu token để che trạng thái này.
- Đối soát runtime cũ8Nginx/7scored/1unresolved; runtime sạch12/8/4, gồm thời gian
  AI chưa được phép khởi động và worker outage. Các số này là snapshot5phút có
  grace15s, không phải tỷ lệ mất gói hoặc tỷ lệ phát hiện tấn công.
- Warm inference: runtime cũ120–180ms, mean149.04ms; runtime sạch108–220ms,
  mean147.64ms. First cold probe runtime sạch5337.93ms; không giấu cold start hoặc
  suy ra capacity/SLA từ6samples. Command-shaped query vẫn dưới frozen threshold.
- Launcher7tests, worker4, thermal/candidate7, frontend3 và Rust AI3 PASS. Rust
  regression52tests của snapshot integration trước được giữ làm evidence lịch sử;
  không nói đã rerun toàn bộ53tests hiện tại. Rust/UI build PASS.
- Guarded Rust build max58°C; UI build max76°C và nhiều lần freeze/reduce/thaw;
  Rust targeted tests max74°C. System RAM peak được đo trong các build/test đó
  khoảng12.15GB. Một test build trước bị hết300s trong khi phần lớn thời gian
  frozen, một lần preflight bị từ chối; giữ nguyên cả hai kết quả.
- Bootstrap race lần đầu ở DB sạch được giữ trong report; retest bằng DB sạch
  khác PASS sau fix. AI lần đầu vẫn bị từ chối khi host nóng; preflight sau đó
  max56°C/5s mới start lại. Không gọi NOT_READY là PASS inference.
- Cả hai runtime và hai DB container của mỗi runtime đã stop, toàn bộ configured
  ports free; volumes/credentials/evidence được giữ. Không để demo chạy ngầm.

Đủ điều kiện review/commit integration candidate, **chưa commit/push hoặc publish
integration mới lên remote**. Team readiness ở đây là source candidate và runbook
đã kiểm trên Linux local, không phải clone remote đã có các thay đổi chưa commit.

## Phạm vi AI và các blocker

| Thành phần | Trạng thái | Bằng chứng / còn thiếu |
|---|---|---|
| Request v2 shadow | CURRENTLY_WORKING khi live acceptance PASS | Frozen50,696params; metadata journal → Rust/DB/UI |
| Suricata live | AVAILABLE_NOT_INTEGRATED | Existing watcher có, chưa chạy capture; extracted binary thiếu shared libraries |
| GLU207 live | BLOCKED_BY_FEATURE_CONTRACT | Chưa có causal flow/response/history bridge đủ frozen207features/parity |
| Body observation | Chưa cung cấp | Capture POST/auth bodies làm tăng nguy cơ credentials/session; không thêm raw body logging |
| Headers | Partial: UA/Accept/Content-Type | Đủ representation text mà frozen API yêu cầu; không giả đầy đủ header/body |
| AWS | Architecture prepared | Cần cloud resource policy, identities/TLS/secrets/deploy/restore tests |

Không thêm Cookie/Authorization hoặc response bodies để làm đẹp feature coverage.
Luồng syslog8KiB/queue64/journal4×2MiB vẫn bounded và có thể mất; DB giữ AI results
tối đa10k/7ngày, alerts theo retention cũ. Rotation/replay/idempotency và schema
reject được kiểm bằng tests, không stress test lớn. Xem
[phương án AWS](14_AWS_SHADOW_DEMO_PLAN.md) cho sizing, giá và deployment blockers.
