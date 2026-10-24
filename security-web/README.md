# PBL4 Security Platform

Security VM nhận cảnh báo Suricata/Nginx, lưu PostgreSQL, phục vụ React/TypeScript dashboard và thực thi block/unblock qua nftables. Đây là bản lab; kiểm thử ba VM và bằng chứng nghiệm thu được hướng dẫn trong `docs/LAB_ACCEPTANCE.md`.

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

`.env` hiện có được giữ nguyên; kiểm tra `APP_ADDR=127.0.0.1:3000` và `AUTO_BLOCK=false` trong lần chạy đầu. Dữ liệu PostgreSQL mặc định ở volume Docker hiện có. Thay biến mật khẩu Compose không đổi mật khẩu của database đã được khởi tạo.

## Truy cập từ máy quản trị

Giữ backend trên loopback, dùng SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 user@SECURITY_MANAGEMENT_IP
```

Sau đó mở `http://127.0.0.1:3000` trên máy quản trị. Nếu triển khai truy cập trực tiếp, cấu hình HTTPS reverse proxy và giới hạn mạng quản trị; không gửi mật khẩu/token qua HTTP trên mạng không tin cậy.

## Triển khai Security VM

Các file Suricata, Nginx và nftables vẫn dùng topology lab:

- Kali: `192.168.10.10` → Security `192.168.10.1` / `enp1s0`.
- Security phía protected: `192.168.20.1` / `enp7s0` → Web `192.168.20.10`.
- Nginx proxy HTTP tới Web; nftables chặn HTTP đi tắt tới Web qua hai NIC.

Các IP/interface được ghi trực tiếp trong một số file. Đổi `.env` không tự render toàn bộ topology. Kiểm tra chúng trước khi deploy. Tạo tài khoản và bật DB như hướng dẫn phía trên trước.

```bash
bash scripts/deploy.sh --check
sudo bash scripts/deploy.sh --deploy
sudo systemctl status pbl4-security --no-pager
sudo journalctl -u pbl4-security -n 100 --no-pager
```

Deploy thay cấu hình host, cấp quyền helper qua sudoers, reload dịch vụ và firewall; chỉ chạy trên Security VM đã chuẩn bị. Script luôn build lại React và Rust release. Chạy trên user có Rust và Node trong login PATH. Cấp quyền đọc log cho user dịch vụ (Nginx và Suricata); dashboard báo lỗi nếu watcher thiếu quyền.

`IP_WHITELIST` là các IP host phân cách dấu phẩy. Mọi block phải qua kiểm tra whitelist và giới hạn `192.168.10.2–254`. Unblock vẫn được phép với IP trong whitelist để khôi phục một block cũ. SID cho auto-block cấu hình qua `AUTO_BLOCK_SIDS`; Nginx SQLi qua `AUTO_BLOCK_NGINX_SQLI`. Bật auto-block chỉ sau khi kiểm thử thủ công.

## Chính sách log và khôi phục

- Lần đầu đọc từ đầu tất cả file log còn tồn tại phù hợp tên (`eve.json`, `eve.json.*`, `access.log`, `access.log.*`), trừ `.gz`. Giữ `AUTO_BLOCK=false` khi nhập lịch sử, tránh phản ứng với cảnh báo cũ.
- Dùng rotation **rename + tạo file mới**, giữ file cũ chưa nén đến khi backend đọc hết; dùng `delaycompress` và retention đủ dài. Không dùng `copytruncate` nếu cần bảo đảm không mất dữ liệu: cơ chế đó có cửa sổ mất dữ liệu và có thể tạo bản sao trên inode khác. Anchor hỗ trợ phát hiện nhiều trường hợp truncate nhưng không thể bảo đảm mọi lần ghi lại giữ nguyên nội dung.
- Checkpoint và khóa sự kiện ngăn ghi trùng khi đọc lại cùng file/inode/offset. Hai nguồn Suricata và Nginx có thể báo cùng một request; đây là hai quan sát, chưa có correlation xuyên nguồn.
- Đọc tối đa 1 MiB mỗi file mỗi lượt. Dòng vượt 1 MiB bị dừng để kiểm tra; file mất/xóa/nén trước khi đọc xong không thể phục hồi bằng checkpoint.
- DB lỗi: retry, không advance checkpoint. Firewall lỗi: audit ERROR, alert vẫn ALERT; quản trị kiểm tra lý do và gửi lại yêu cầu. Lỗi sau khi kernel thành công nhưng DB chưa commit: job vẫn PENDING, thực thi lại idempotent.
- Vận hành một instance backend trên Security VM. Advisory lock tuần tự hóa việc thực thi firewall trong DB; không để chương trình khác tự sửa cùng set mà không kiểm tra trạng thái lệch.

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
| GET | `/health` | Liveness tiến trình, không chứng minh pipeline khỏe |

## Kiểm thử

```bash
# PostgreSQL user phải có quyền tạo DB test; dùng database điều phối postgres,
# không trỏ vào database production. SQLx tạo DB riêng cho mỗi test.
DATABASE_URL=postgres://USER:PASSWORD@127.0.0.1:5433/postgres cargo test
cd frontend && npm run build
```

Test bao phủ đăng nhập/logout/session hết hạn, viewer bị từ chối block, whitelist, audit lỗi, lưu log/rotation/partial/replay, lỗi DB và retry, auto-block thành công/thất bại, unblock và migration từ schema cũ. Firewall trong integration test được thay bằng hàm giả lập tại đúng đường thực thi dùng trong production; không chạy nftables thật.

Để kiểm tra HTTP read-only trên instance đã chạy:

```bash
python3 scripts/smoke-test.py --url http://127.0.0.1:3000 --username admin
```

Kiểm thử packet thật, cấu hình Suricata, SSH quản trị, block/unblock HTTP cần chạy theo `docs/LAB_ACCEPTANCE.md`. Chưa có WebSocket, TTL auto-unblock, correlation xuyên nguồn, hoặc backup/restore tự động.

`GET /api/ready` yêu cầu đăng nhập và trả cùng báo cáo với `/api/status`, nhưng HTTP 503 nếu hệ thống chưa sẵn sàng. Dashboard dùng `/api/status` để không phát sinh lỗi HTTP mỗi lần polling khi test host chưa có firewall. `healthy: false` vẫn được hiển thị; HTTP 200 không khẳng định pipeline đã sẵn sàng.

### Thống kê Tổng quan

`GET /api/stats?range=1h|24h|7d` (mặc định `24h`) dùng cùng mốc `from`/`to` cho toàn bộ thống kê cảnh báo, Top IP, phân bố và 10 cảnh báo mới nhất. Biểu đồ chia lần lượt thành 12 khoảng 5 phút, 24 khoảng 1 giờ hoặc 28 khoảng 6 giờ. Khoảng là `[from, to)` theo thời điểm xảy ra cảnh báo; giao diện hiển thị giờ địa phương.

`jobs` chỉ đếm yêu cầu `BLOCK` được tạo trong khoảng đã chọn, theo trạng thái hiện tại; bao gồm thủ công và tự động. Liên kết audit mở danh sách 100 thao tác gần nhất, không áp dụng bộ lọc thời gian Tổng quan. `unknown_destinations` đếm riêng cảnh báo thiếu IP đích. Một request có thể tạo nhiều cảnh báo từ các nguồn khác nhau; số cảnh báo không phải số cuộc tấn công. Chỉ số tài nguyên trong `system` vẫn là số đo hiện tại, không phải lịch sử theo khoảng chọn.

### Điều tra cảnh báo

- `GET /api/alerts/search`: trả `{items, total}` với bộ lọc `search`, `severity`, `from`, `to`, `source`, `action`, `dest_ip`, `limit`, `offset`. Thời gian ISO 8601 theo khoảng `[from, to)`; IP đích khớp chính xác. `GET /api/alerts` giữ phản hồi mảng để tương thích client cũ.
- `GET /api/alerts/{id}`: chi tiết đầy đủ, tối đa 10 cảnh báo khác cùng IP nguồn trên toàn bộ lịch sử và tác vụ firewall liên kết trực tiếp qua `event_id`. Cả hai API yêu cầu đăng nhập, admin/viewer đều đọc được.
- Tab Cảnh báo có bộ lọc và tổng kết quả. Nút “Chi tiết” mở bảng bên cạnh; Escape hoặc nút Đóng thoát bảng. Request HTTP được trích từ bằng chứng Nginx combined hoặc trường `http` của Suricata EVE khi có. Nút sao chép giữ nguyên bằng chứng gốc, JSON được định dạng chỉ để đọc.
