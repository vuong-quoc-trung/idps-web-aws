# PBL4 Security Platform

Security Host nhận cảnh báo Suricata/Nginx, lưu PostgreSQL, phục vụ React/TypeScript dashboard và thực thi block/unblock qua nftables. Đây là bản lab; kiểm thử ba VM và bằng chứng nghiệm thu được hướng dẫn trong `docs/LAB_ACCEPTANCE.md`.

## Shared Foundation hiện hành

Bắt đầu tại [docs/00](../docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md), [schema v1.0](../contracts/README.md) và [hồ sơ test](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md). Các hướng dẫn lab cũ bên dưới cần đối chiếu cấu hình mới:

- Security Compose mặc định `127.0.0.1:${SECURITY_DB_PORT:-5434}:5432`; Student dùng5433. DATABASE_URL trong `.env.example` đã đổi5434; **kiểm và cập nhật port trong `.env` riêng** khi chuyển cấu hình cũ. Không tự đổi mật khẩu/volume DB đã có.
- `STUDENT_AUDIT_LOG_PATH` bật watcherStudent khi path không rỗng. Nginx structured/combined và EVE alert/http/flow đều được normalize; `COLLECT_ALL_EVENTS=true` lưu observations vào normalized_events, false vẫn parse/detect nhưng không backfill dữ liệu đã bỏ qua.
- Retention dataset7ngày, cap1triệu rows, sweep60s; INGEST_MAX_LINE_BYTES mặc định65536. Oversized records bị cách ly theo hash/range, không copy raw secrets; partial/rotation/dedup tiếp tục dùng durable cursor.
- Rust có SQLi/XSS/traversal/command/scanner và auth-burst theo IP+route; auth counter dedup Nginx/Student theo request ID. Suricata có9SID, SYNburst được đặt tên đúng và không auto eligible mặc định. Các family Rust mới là alert-only.
- **ENFORCEMENT_MODE=OFF** mặc định chặn mọi thực thi PENDING/RESTORE. MANUAL chỉ cho BLOCK nguồnAPI; ENFORCE vẫn phải qua protected-target/deadline/freshness/policy. AUTO_BLOCK=false riêng lẻ vẫn không là global stop.
- `ENFORCE_ALLOWED_SUBNETS` mặc định các dảiIPv4 private; WEB_SERVER_IP/PROTECTED_GATEWAY_IP và IP_WHITELIST bổ sung miễn trừ. Backend/helper khám phá host/default gateways; khi không xác minh an toàn thì từ chốiBLOCK. IPv6 collect-only, không block.
- Helper mới gồm wrapper + root-owned Python policy module; phải cài đồng bộ theo update trong HOST_SECURITY_SETUP.md trước bật enforcement. TTL/deadline tối đa300s, restore giữ deadline gốc. Chưa áp ruleset host bởi script dev.
- Nginx template nghe0.0.0.0:80, ưu tiên API127.0.0.1:8080/frontend127.0.0.1:5173, WebVM192.168.20.10:80 backup. Query values không ghi disk; edge tính rule flags trong memory. TLS cần certificate/template riêng và Secure cookies. Local session/DB không tự đồng bộ với VM khi failover.

Từ gốc repo chạy `scripts/dev-up-and-verify.sh --bootstrap-nginx` để dùng hai DB demo riêng55433/55434 và Security3001; thêm--expose-lan để mở dev edge18780 ra mạng. `scripts/dev-up-and-verify.sh --stop` chỉ dừng stackdemo, giữ dữ liệu. Credentials dev trong ignored `.local-dev/foundation/credentials.json`, không in vào Git/docs. Service cũ3000 và DB5433/5434 được giữ nguyên.

## Các thay đổi chính

- Đăng nhập admin/viewer bằng mật khẩu Argon2id. Session ngẫu nhiên 256 bit, hết hạn sau một giờ, lưu hash ở server; frontend giữ token trong bộ nhớ. Logout thu hồi session. Restart backend hoặc reload trang yêu cầu đăng nhập lại.
- Mọi API dữ liệu cần Bearer token; chỉ admin gửi block/unblock. Không dùng cookie xác thực hoặc bật CORS; trình duyệt không tự đính kèm quyền vào request từ website khác.
- Đọc log có checkpoint PostgreSQL, nhận diện inode và anchor, xử lý dòng chưa ghi xong; transaction lưu alert, công việc firewall và checkpoint cùng lúc. Lỗi DB giữ nguyên checkpoint để retry. Dòng không hợp lệ được đếm trong `ingestion_errors`.
- Firewall có hàng đợi bền vững: API trả **202 PENDING**, worker mới thực thi; audit ghi actor, reason, SUCCESS/ERROR. `AUTO-BLOCK` chỉ được ghi sau thành công. Lệnh idempotent có timeout 5 giây, dùng `sudo -n`; restart tiếp tục job pending và tạo job phục hồi IP active, không ghi đè yêu cầu unblock đang chờ.
- Dashboard so sánh IP thực tế trong nftables với DB, báo lỗi khi không đọc được hoặc không khớp. Không tự che giấu lệch trạng thái bằng số liệu DB.
- React dashboard có tìm kiếm/phân trang từ server, CSV **trang hiện tại**, audit, rules, trạng thái dịch vụ, biểu đồ số alert theo giờ từ DB.
- Chỉ hiển thị số đo thật: memory, load average 1 phút (không gọi là CPU%), byte RX tích lũy theo NIC, TCP established của máy. Không có dữ liệu thì hiển thị chưa có dữ liệu.
- SQLx migrations chạy lúc startup; schema cũ được nâng cấp, giữ dữ liệu hiện có.

## Chạy trên máy phát triển

Yêu cầu: Rust 1.88 trở lên (edition 2024), Node phù hợp Vite 8, npm, Docker Compose, Python 3 cho script thiết lập tài khoản. Chạy mọi lệnh dưới đây tại `security-web/`.

```bash
test -f .env || cp .env.example .env
docker compose up -d postgres
cd frontend
npm ci
npm run build
cd ..
cargo build
python3 scripts/setup-auth.py
# Tùy chọn tài khoản chỉ xem:
python3 scripts/setup-auth.py --role viewer
cargo run
```

`setup-auth.py` hỏi mật khẩu qua terminal, yêu cầu ít nhất 12 ký tự và chỉ ghi Argon2 hash vào `.env` (quyền 0600). Không có mật khẩu quản trị mặc định. Không commit `.env`.

Mở `http://127.0.0.1:3000`. Không cần nạp `schema.sql` thủ công nữa. Với DB cũ, sao lưu trước lần chạy nâng cấp. File `sql/schema.sql` được giữ làm fixture schema cũ cho test migration; thư mục `migrations/` là nguồn chính thức.

Nếu phát triển frontend riêng: giữ Rust ở cổng 3000, chạy `npm run dev` trong `frontend/`; Vite proxy `/api` về Rust. Production Rust phục vụ `frontend/dist` nên phải build frontend trước khi chạy.

`.env` hiện có được giữ nguyên; kiểm tra `APP_ADDR=127.0.0.1:3000`, `ENFORCEMENT_MODE=OFF` và `AUTO_BLOCK=false` trong lần chạy đầu. Dữ liệu PostgreSQL mặc định ở volume Docker hiện có. Thay biến mật khẩu Compose không đổi mật khẩu của database đã được khởi tạo.

## Truy cập từ máy quản trị

Giữ backend trên loopback, dùng SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 user@SECURITY_MANAGEMENT_IP
```

Sau đó mở `http://127.0.0.1:3000` trên máy quản trị. Nếu triển khai truy cập trực tiếp, cấu hình HTTPS reverse proxy và giới hạn mạng quản trị; không gửi mật khẩu/token qua HTTP trên mạng không tin cậy.

## Triển khai Security Host

Để tự nạp riêng bảng `inet pbl4_demo` sau reboot, dùng
[hướng dẫn service firewall boot](docs/FIREWALL_BOOT.md). Bộ cài có syntax check,
sao lưu file hệ thống và giữ nguyên bảng đang tồn tại; không thay `/etc/nftables.conf`.

Các file Suricata, Nginx và nftables vẫn dùng topology lab:

- Kali: `192.168.10.10` → Security `192.168.10.1` / `vmnet2`.
- Security phía protected: `192.168.20.1` / `vmnet3` → Web `192.168.20.10`.
- Nginx proxy HTTP tới Web; nftables chặn HTTP đi tắt tới Web qua hai NIC.

Các IP/interface được ghi trực tiếp trong một số file. Đổi `.env` không tự render toàn bộ topology. Kiểm tra chúng trước khi deploy. Tạo tài khoản và bật DB như hướng dẫn phía trên trước.

Thực hiện từng bước trong [hướng dẫn nghiệm thu Ubuntu host](docs/HOST_SECURITY_SETUP.md): kiểm tra Suricata, quyền đọc log, dữ liệu firewall cũ, syntax nftables rồi mới cài helper và sudoers. Các lệnh cần sudo do người vận hành tự chạy; không áp ruleset tự động.

`deploy.sh --deploy` đã khóa để tránh thay cấu hình host bằng quy trình cũ. Giữ `AUTO_BLOCK=false` trong toàn bộ nghiệm thu. Lưu ý worker vẫn xử lý tác vụ PENDING và khôi phục IP active từ DB: phải rà các bản ghi này trước khi chạy backend có quyền helper.

`IP_WHITELIST` là các IP host phân cách dấu phẩy. Mọi block phải qua kiểm tra whitelist và các dải `ENFORCE_ALLOWED_SUBNETS` và protected-target policy hiện hành. Unblock vẫn được phép với IP trong whitelist để khôi phục một block cũ. SID cho auto-block cấu hình qua `AUTO_BLOCK_SIDS`; Nginx SQLi qua `AUTO_BLOCK_NGINX_SQLI`. Bật auto-block chỉ sau khi kiểm thử thủ công.

## Chính sách log và khôi phục

- Lần đầu đọc từ đầu tất cả file log còn tồn tại phù hợp tên (`eve.json`, `eve.json.*`, `access.log`, `access.log.*`), trừ `.gz`. Giữ `AUTO_BLOCK=false` khi nhập lịch sử, tránh phản ứng với cảnh báo cũ.
- Dùng rotation **rename + tạo file mới**, giữ file cũ chưa nén đến khi backend đọc hết; dùng `delaycompress` và retention đủ dài. Không dùng `copytruncate` nếu cần bảo đảm không mất dữ liệu: cơ chế đó có cửa sổ mất dữ liệu và có thể tạo bản sao trên inode khác. Anchor hỗ trợ phát hiện nhiều trường hợp truncate nhưng không thể bảo đảm mọi lần ghi lại giữ nguyên nội dung.
- Checkpoint và khóa sự kiện ngăn ghi trùng khi đọc lại cùng file/inode/offset. Hai nguồn Suricata và Nginx có thể báo cùng một request; đây là hai quan sát, chưa có correlation xuyên nguồn.
- Đọc tối đa 1 MiB mỗi file mỗi lượt. Dòng vượt 1 MiB bị dừng để kiểm tra; file mất/xóa/nén trước khi đọc xong không thể phục hồi bằng checkpoint.
- DB lỗi: retry, không advance checkpoint. Firewall lỗi: audit ERROR, alert vẫn ALERT; quản trị kiểm tra lý do và gửi lại yêu cầu. Lỗi sau khi kernel thành công nhưng DB chưa commit: job vẫn PENDING, thực thi lại idempotent.
- Vận hành một instance backend trên Security Host. Advisory lock tuần tự hóa việc thực thi firewall trong DB; không để chương trình khác tự sửa cùng set mà không kiểm tra trạng thái lệch.

## API

| Method | Endpoint | Quyền / ý nghĩa |
|---|---|---|
| POST | `/api/auth/login` | username/password; giới hạn 10 lần/phút toàn instance |
| GET | `/api/auth/me` | Session hiện tại |
| POST | `/api/auth/logout` | Thu hồi token |
| GET | `/api/alerts?limit=25&offset=0&search=...&severity=1` | Viewer/admin |
| GET | `/api/stats` | Tổng số và series 24 giờ từ DB |
| GET | `/api/status` | Báo cáo DB, watchers, firewall; HTTP 200, xem `healthy` trong JSON |
| GET | `/api/rules` | Danh mục rule đi kèm và policy đã bật |
| GET | `/api/blocked-ips` | Object `database`, `kernel`, `in_sync`, `error` |
| POST | `/api/blocked-ips` | Admin; `{ip, reason}` → 202 + ID job |
| DELETE | `/api/blocked-ips/{ip}` | Admin; → 202 + ID job |
| GET | `/api/audit` | 100 thao tác gần nhất |
| GET | `/api/application-audit` | Viewer/admin; quan sát canonical, lọc/phân trang và trạng thái thu thập |
| GET | `/api/application-audit/{id}` | Viewer/admin; JSON đã che dữ liệu + tối đa10 quan sát cùng requestID |
| GET | `/health` | Liveness tiến trình, không chứng minh pipeline khỏe |

Tab **Audit ứng dụng** mặc định xem Student audit trong 24 giờ qua, có bộ lọc thời gian/nguồn/IP/endpoint/mã HTTP/method/requestID, phân trang25 dòng và JSON chi tiết đã mask. Dùng `request_id` để xem quan sát tương ứng từ Nginx. API hỗ trợ `limit`1–200, `offset`0–1000000; `from` bao gồm, `to` không bao gồm; endpoint tìm chuỗi con, các trường khác khớp chính xác. Xem hợp đồng tại [docs02](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md#24-api-quan-sát-và-tab-audit-ứng-dụng).

Trạng thái thu thập/watcher hiển thị ngay trong tab. `COLLECT_ALL_EVENTS=false` vẫn xem được lịch sử nhưng không thêm observations mới và không tự backfill khi bật lại. Outcome HTTP chỉ phản ánh kết quả request; nhãn attack/benign cần được đánh giá riêng.

Sau thao tác trên Student, mở **Audit ứng dụng** và bấm **Tải lại audit** hoặc **Làm mới** phía trên. Cả hai giữ bộ lọc/trang đang xem; bảng audit tải thủ công. Thao tác tạo khoa xuất hiện dưới `POST /api/faculties`, thường HTTP201, không làm tăng số cảnh báo ở Tổng quan.

## Kiểm thử

```bash
# PostgreSQL user phải có quyền tạo DB test; dùng database điều phối postgres,
# không trỏ vào database production. SQLx tạo DB riêng cho mỗi test.
DATABASE_URL=postgres://USER:PASSWORD@127.0.0.1:5434/postgres cargo test --locked
cd frontend && npm test && npm run format:check && npm run build
```

Test bao phủ đăng nhập/logout/session hết hạn, viewer bị từ chối block, whitelist, audit lỗi, lưu log/rotation/partial/replay, lỗi DB và retry, auto-block thành công/thất bại, unblock và migration từ schema cũ. Firewall trong integration test được thay bằng hàm giả lập tại đúng đường thực thi dùng trong production; không chạy nftables thật.

Để kiểm tra HTTP read-only trên instance đã chạy:

```bash
python3 scripts/smoke-test.py --url http://127.0.0.1:3000 --username admin
```

Kiểm thử packet thật, cấu hình Suricata, SSH quản trị, block/unblock HTTP cần chạy theo `docs/LAB_ACCEPTANCE.md`. Chưa có WebSocket hoặc backup/restore tự động. Foundation đã thêm TTL/deadline và request-ID correlation giữa Student/Nginx; nghiệm thu host packet thật vẫn cần riêng.

`GET /api/ready` yêu cầu đăng nhập và trả cùng báo cáo với `/api/status`, nhưng HTTP 503 nếu hệ thống chưa sẵn sàng. Dashboard dùng `/api/status` để không phát sinh lỗi HTTP mỗi lần polling khi test host chưa có firewall. `healthy: false` vẫn được hiển thị; HTTP 200 không khẳng định pipeline đã sẵn sàng.

### Thống kê Tổng quan

`GET /api/stats?range=1h|24h|7d` (mặc định `24h`) dùng cùng mốc `from`/`to` cho toàn bộ thống kê cảnh báo, Top IP, phân bố và 10 cảnh báo mới nhất. Biểu đồ chia lần lượt thành 12 khoảng 5 phút, 24 khoảng 1 giờ hoặc 28 khoảng 6 giờ. Khoảng là `[from, to)` theo thời điểm xảy ra cảnh báo; giao diện hiển thị giờ địa phương.

`jobs` chỉ đếm yêu cầu `BLOCK` được tạo trong khoảng đã chọn, theo trạng thái hiện tại; bao gồm thủ công và tự động. Liên kết audit mở danh sách 100 thao tác gần nhất, không áp dụng bộ lọc thời gian Tổng quan. `unknown_destinations` đếm riêng cảnh báo thiếu IP đích. Một request có thể tạo nhiều cảnh báo từ các nguồn khác nhau; số cảnh báo không phải số cuộc tấn công. Chỉ số tài nguyên trong `system` vẫn là số đo hiện tại, không phải lịch sử theo khoảng chọn.

### Điều tra cảnh báo

- `GET /api/alerts/search`: trả `{items, total}` với bộ lọc `search`, `severity`, `from`, `to`, `source`, `action`, `dest_ip`, `limit`, `offset`. Thời gian ISO 8601 theo khoảng `[from, to)`; IP đích khớp chính xác. `GET /api/alerts` giữ phản hồi mảng để tương thích client cũ.
- `GET /api/alerts/{id}`: chi tiết đầy đủ, tối đa 10 cảnh báo khác cùng IP nguồn trên toàn bộ lịch sử và tác vụ firewall liên kết trực tiếp qua `event_id`. Cả hai API yêu cầu đăng nhập, admin/viewer đều đọc được.
- Tab Cảnh báo có bộ lọc và tổng kết quả. Nút “Chi tiết” mở bảng bên cạnh; Escape hoặc nút Đóng thoát bảng. Request HTTP được trích từ bằng chứng Nginx combined hoặc trường `http` của Suricata EVE khi có. Nút sao chép giữ nguyên bằng chứng gốc, JSON được định dạng chỉ để đọc.

### Trạng thái thu thập theo nguồn

Tab Trạng thái hiển thị riêng Nginx/Suricata: lần quét đọc thành công, lần quan sát file có dữ liệu mới/thay đổi, byte chưa xử lý, lần lưu cảnh báo vào DB, số dòng sai định dạng và lỗi phân tích gần nhất. `watchers` trong `/api/status` hiện là object trạng thái cho từng nguồn; `collection` chứa thống kê lịch sử từ DB.

Mốc đọc/quan sát được giữ trong bộ nhớ và bắt đầu lại khi backend khởi động. File có nội dung từ trước được tính là lần quan sát đầu tiên; file rỗng không được tính. Đây không phải kiểm tra tiến trình Suricata/Nginx. Byte chờ là tổng kích thước còn lại sau checkpoint của file hiện tại và các file rotation chưa nén, gồm dòng chưa hoàn tất. Khi quét lỗi, byte chờ là `null` (không xác định), không phải 0. Lần cảnh báo là thời điểm lưu vào DB, không phải timestamp gốc của sự kiện. Thống kê lỗi lấy từ DB, không tăng lại khi đọc lại cùng dòng lỗi.

### Liên kết firewall và audit

Danh sách IP hiển thị thời điểm chặn từ DB và phân biệt có ở cả DB/kernel, chỉ DB, chỉ kernel hoặc chưa xác định kernel. Không suy luận “không có IP bị chặn” khi không đọc được kernel. Audit hiển thị nguồn yêu cầu, người thực hiện, thời điểm tạo và hoàn tất; `RESTORE` là khôi phục bởi hệ thống, `AUTO` là tự động và `API` là thao tác quản trị.

`GET /api/audit?event_id=<id>` lọc tác vụ trực tiếp theo cảnh báo trước khi giới hạn 100 kết quả. Từ bảng chi tiết cảnh báo có thể chuyển đến audit đã lọc; từ dòng audit có `event_id` có thể mở lại cảnh báo. Nút “Xem tất cả thao tác” bỏ bộ lọc.

### Ngữ cảnh tài nguyên backend

Tab Trạng thái hiển thị hostname, interface `ATTACKER_IFACE`, RX/TX theo KiB/s và bộ đếm tích lũy. Backend lấy mẫu nền (nghỉ 2 giây giữa các lượt), tính tốc độ bằng chênh lệch byte / thời gian thực giữa hai mẫu; không có interface, mẫu đầu tiên hoặc reset bộ đếm trả `null` thay vì tốc độ 0.

`METRICS_DISK_PATH` mặc định `/`: đo tổng dung lượng và byte khả dụng của filesystem chứa đường dẫn bằng `df` (timeout 2 giây). Chọn đường dẫn log hoặc mount cần giám sát nếu khác `/`. Số đo không đại diện DB ở máy/volume khác. Các số liệu thuộc môi trường backend, không tự động là Security Host; container có thể giới hạn phạm vi quan sát. `sampled_at` là thời điểm công bố mẫu mạng/đĩa; lần dashboard tải API và lần nguồn nhận log mới hiển thị riêng.
