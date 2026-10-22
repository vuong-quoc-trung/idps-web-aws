# PBL4 Web IDPS/IPS — Modern Security Core, Suricata, Nginx, nftables & PostgreSQL

Hệ thống **Web Intrusion Detection & Prevention System (IDPS/IPS)** thuộc đồ án PBL4, kết hợp giám sát lưu lượng mạng ở tầng giao vận (Suricata NIDS), phân tích nhật ký ứng dụng web ở tầng ứng dụng (Nginx reverse proxy), động cơ phản ứng nhanh bằng tường lửa hạt nhân (nftables) và lõi xử lý trung tâm hiệu năng cao viết bằng **Rust** (`pbl4-security-demo`) lưu trữ dữ liệu tại **PostgreSQL** cùng giao diện giám sát hiện đại theo chuẩn NIDS Security Operations Center (SOC).

---

## 1. Kiến trúc mạng và Luồng dữ liệu (Traffic Flow)

Môi trường kiểm thử (Lab) gồm ba máy ảo (VM) độc lập:

```text
+-----------------------+              +------------------------------------------------------+              +-----------------------+
|    Kali Attacker      |              |                     Security VM                      |              |      Web Server       |
|    192.168.10.10      |              |                                                      |              |     192.168.20.10     |
|                       |              |  [enp1s0: 192.168.10.1]    [enp7s0: 192.168.20.1]    |              |                       |
|  - SYN Port Scanner   |              |            |                           |             |              |  - Backend HTTP app   |
|  - SQLi/XSS Exploits  |              |            v                           v             |              |  - Nginx web service  |
|  - Path Traversal     |              |  +------------------------------------------------+  |              |                       |
|  - Scanner Tools      |              |  |                nftables (inet)                 |  |              +-----------^-----------+
+-----------+-----------+              |  |  - input hook : drop ip saddr @blocked_ips     |  |                          |
            |                          |  |  - forward hook: drop bypass HTTP to .20.10    |  |                          |
            |                          |  +--------+-------------------------------+-------+  |                          |
            |                          |           |                               |          |                          |
            | (1) HTTP Request / Scan  |           | (2) Traffic Mirror / Inspect  |          | (5) Reverse Proxy Pass   |
            +------------------------->|           v                               |          +--------------------------+
                                       |     +------------+                        |
                                       |     |  Suricata  | (AF_PACKET: enp1s0)    |
                                       |     +-----+------+                        |
                                       |           | (3) EVE JSON alert            |
                                       |           v                               |
                                       |     +------------+                        |
                                       |     | eve.json   |                        |
                                       |     +-----+------+                        |
                                       |           |                               v
                                       |           |                    +---------------------+
                                       |           |                    |  Nginx Reverse Proxy|
                                       |           |                    |  192.168.10.1:80    |
                                       |           |                    +----------+----------+
                                       |           |                               | (4) HTTP access.log
                                       |           v                               v
                                       |     +------------------------------------------------+
                                       |     |      Rust Security Core (pbl4-security-demo)   |
                                       |     |      - Decoupled Policy Engine (ALERT/BLOCK)   |
                                       |     |      - Async log tailing (Tokio)               |
                                       |     |      - SQLi WAF signature detection            |
                                       |     |      - Modern Dashboard UI & REST API (:3000)  |
                                       |     |      - Telemetry Engine (CPU, Mem, Net I/O)    |
                                       |     +--------+-------------------------+-------------+
                                       |              |                         |
                                       |              | (6) SQL Queries         | (7) sudo pbl4-firewall block <ip>
                                       |              v                         v
                                       |     +------------------+     +---------------------+
                                       |     | Docker Postgres  |     | nftables Set        |
                                       |     | 127.0.0.1:5433   |     | @blocked_ips (DROP) |
                                       |     +------------------+     +---------------------+
                                       |
                                       |  [enp8s0: 192.168.122.x - Management & Dashboard Access]
                                       +------------------------------------------------------+
```

### Luồng xử lý chi tiết:
1. **Luồng Web HTTP bình thường:**
   `Kali (192.168.10.10) → Nginx Reverse Proxy (192.168.10.1:80) → Web Server (192.168.20.10:80)`.
   Nếu Kali cố gắng gửi gói tin trực tiếp tới `192.168.20.10:80`, chain `forward` của nftables sẽ chặn lại để buộc toàn bộ lưu lượng qua proxy.
2. **Luồng phát hiện Suricata NIDS:**
   Suricata bắt gói tin trực tiếp trên `enp1s0` qua socket `AF_PACKET`. Áp dụng bộ 8 luật tấn công kinh điển trong `pbl4.rules`, sự kiện được ghi vào `/var/log/suricata/eve.json`.
3. **Luồng phát hiện Nginx / WAF:**
   Mọi request HTTP gửi tới Nginx được ghi vào `/var/log/nginx/access.log`. Rust backend đọc luồng log theo thời gian thực và kiểm tra chữ ký SQL Injection từ Request URI.
4. **Động cơ Phân định Chính sách (Policy Engine):**
   - **`ALERT`:** Ghi nhận cảnh báo, phân loại mức độ và hiển thị trực quan trên Dashboard theo thời gian thực; tuyệt đối không chặn IP.
   - **`AUTO-BLOCK`:** Chỉ kích hoạt chặn IP khi luật đó được cấu hình cho phép tự động chặn (Whitelist SID: `1000001`, `1000002`). Các luật mới bổ sung mặc định ở chế độ cảnh báo (`ALERT`).
   - **Nguyên tắc bảo đảm:** Nếu lệnh tường lửa thất bại, sự kiện được ghi nhận là `ALERT` (ghi lỗi vào `firewall_actions`), tuyệt đối không ghi nhận là `AUTO-BLOCK` nếu hạt nhân chưa thực sự chặn thành công.

---

## 2. Bộ luật phát hiện tấn công Suricata (`suricata/pbl4.rules`)

Hệ thống triển khai 8 luật phát hiện tấn công kinh điển tương thích hoàn toàn với Suricata 8.x:

| SID | Tên luật | Phân loại (Classtype) | Priority | Chính sách mặc định |
| :--- | :--- | :--- | :---: | :---: |
| **`1000001`** | TCP SYN Port Scan Detected | `attempted-recon` | 2 | **AUTO-BLOCK** (khi bật `AUTO_BLOCK=true`) |
| **`1000002`** | SQL Injection - Boolean or Union Attempt | `web-application-attack` | 1 | **AUTO-BLOCK** (khi bật `AUTO_BLOCK=true`) |
| **`1000008`** | SQL Injection - Generic Keywords Attempt | `web-application-attack` | 1 | **ALERT** (Ghi nhận cảnh báo) |
| **`1000003`** | Cross-Site Scripting (XSS) Attempt | `web-application-attack` | 2 | **ALERT** (Ghi nhận cảnh báo) |
| **`1000004`** | Path Traversal / Directory Traversal Attempt | `web-application-attack` | 2 | **ALERT** (Ghi nhận cảnh báo) |
| **`1000005`** | OS Command Injection Attempt | `web-application-attack` | 1 | **ALERT** (Ghi nhận cảnh báo) |
| **`1000006`** | Sensitive Configuration / Credential Probing | `attempted-recon` | 2 | **ALERT** (Ghi nhận cảnh báo) |
| **`1000007`** | Automated Vulnerability Scanner Tool Detected | `attempted-recon` | 3 | **ALERT** (Ghi nhận cảnh báo) |

---

## 3. Giao diện Giám sát Hiện đại (NIDS Dashboard)

Toàn bộ giao diện được thiết kế lại theo phong cách Dark Mode chuyên nghiệp của Security Operations Center (SOC) với bảng màu Tailored HSL (`#080c14` background, dark slate cards, viền tinh tế `#1e293b`):

- **Sidebar thương hiệu:** Logo Shield NIDS, danh mục điều hướng Dashboard, Alerts, Blocked IPs, Rules & Policy, Traffic Monitor, System Status cùng trạng thái hoạt động trực tiếp (*All systems operational*).
- **Top 5 Stat Cards:**
  1. *Total Alerts* (Tổng số cảnh báo, biểu đồ sparkline, xu hướng tăng giảm).
  2. *Critical Alerts* (Cảnh báo mức độ nghiêm trọng cao).
  3. *Blocked Attacks* (Số cuộc tấn công đã chặn thành công).
  4. *Traffic Analyzed* (Dung lượng lưu lượng thực tế đo từ kernel `enp1s0`).
  5. *Active Connections* (Số kết nối TCP hoạt động từ `/proc/net/tcp`).
- **Traffic Overview Chart:** Biểu đồ đa đường cong mềm mại (Normal Traffic [Xanh dương], Suspicious Traffic [Vàng], Malicious Traffic [Đỏ]) với bộ lọc chu kỳ thời gian.
- **Top Attack Types Donut Chart:** Biểu đồ tròn thể hiện cơ cấu các loại tấn công (SQL Injection, XSS, Port Scan, Path Traversal, Command Injection, Sensitive Files, Scanner Tools, Others) kèm tổng số ở tâm và tỷ lệ phần trăm động.
- **Recent Alerts Stream:** Bảng sự kiện trực tiếp với phân định rõ nét nhãn **`ALERT`** (viền xanh/vàng quan sát) và **`AUTO-BLOCK`** (viền đỏ hạt nhân chặn). Cung cấp thao tác nhanh Block/Unblock ngay trên bảng.
- **System Status Meters:** 4 thanh đo phần cứng trực tiếp từ Linux kernel: CPU Usage (`/proc/loadavg`), Memory Usage (`/proc/meminfo`), Disk Usage, Network I/O.
- **Firewall Manager Modal:** Hộp thoại chặn IP thủ công an toàn (giới hạn dải `192.168.10.2` - `192.168.10.254`) và danh sách IP đang bị chặn trong kernel nftables `@blocked_ips`.
- **Export Report:** Xuất toàn bộ báo cáo sự cố an ninh ra định dạng CSV chỉ với 1 click.

---

## 4. Cấu trúc thư mục nguồn và Ánh xạ cấu hình Git

Dự án áp dụng nguyên tắc **Git là nguồn quản lý cấu hình duy nhất (Single Source of Truth)**. Tên file đã được chuẩn hóa (loại bỏ hậu tố `-demo`):

```text
security-web/
├── .env.example                            # File mẫu biến môi trường (được track trong Git)
├── .gitignore                              # Cấu hình bỏ qua .env, target/ và các file tạm
├── Cargo.lock                              # Khóa phiên bản dependency Rust
├── Cargo.toml                              # Metadata và cấu hình gói pbl4-security-demo
├── docker-compose.yml                      # Cấu hình container PostgreSQL (port host 5433)
├── README.md                               # Tài liệu hướng dẫn toàn diện
├── config/
│   ├── nftables/
│   │   └── nftables.conf                   # Cấu hình nftables chính (include pbl4.nft)
│   └── suricata/
│       └── suricata.yaml                   # Cấu hình Suricata chuẩn (AF_PACKET, chỉ nạp pbl4.rules)
├── deploy/
│   └── systemd/
│       └── pbl4-security.service           # Template systemd (động theo RUN_USER và PROJECT_DIR)
├── nginx/
│   └── pbl4-proxy.conf                     # Cấu hình reverse proxy cho Nginx
├── scripts/
│   ├── deploy.sh                           # Script tự động hóa (--check & --deploy)
│   ├── pbl4.nft                            # Luật nftables chuẩn hóa (table inet pbl4_demo)
│   └── pbl4-firewall                       # Helper script quản lý set blocked_ips (block/unblock/list)
├── sql/
│   └── schema.sql                          # Lược đồ cơ sở dữ liệu PostgreSQL
├── src/
│   └── main.rs                             # Toàn bộ mã nguồn Rust Security Core, Policy Engine & APIs
├── suricata/
│   └── pbl4.rules                          # 8 luật Suricata NIDS (SIDs 1000001 - 1000008)
└── dashboard/
    ├── index.html                          # Cấu trúc giao diện NIDS Dashboard mới
    ├── style.css                           # Toàn bộ CSS giao diện Dark Theme cao cấp
    └── app.js                              # Logic biểu đồ Canvas, polling thời gian thực và modals
```

### Bảng ánh xạ File nguồn Git ⟷ Vị trí triển khai hệ thống:

| File nguồn trong Git | Vị trí triển khai trên Ubuntu | Quyền | Mục đích |
| :--- | :--- | :--- | :--- |
| `config/suricata/suricata.yaml` | `/etc/suricata/suricata.yaml` | `0644 root:root` | Cấu hình Suricata daemon |
| `suricata/pbl4.rules` | `/var/lib/suricata/rules/pbl4.rules` | `0644 root:root` | File 8 luật Suricata PBL4 duy nhất |
| `nginx/pbl4-proxy.conf` | `/etc/nginx/sites-available/pbl4-proxy` | `0644 root:root` | Vhost proxy (symlink sang `sites-enabled/`) |
| `config/nftables/nftables.conf` | `/etc/nftables.conf` | `0755 root:root` | File nạp nftables chính lúc boot |
| `scripts/pbl4.nft` | `/etc/nftables.d/pbl4.nft` | `0644 root:root` | Bảng luật `inet pbl4_demo` |
| `scripts/pbl4-firewall` | `/usr/local/bin/pbl4-firewall` | `0755 root:root` | Script helper chặn/bỏ chặn IP |
| `deploy/systemd/pbl4-security.service` | `/etc/systemd/system/pbl4-security.service` | `0644 root:root` | Dịch vụ systemd (được thế biến động lúc deploy) |

---

## 5. Hướng dẫn Vận hành và Triển khai

### 5.1. Kiểm tra môi trường trước khi triển khai (`--check`)

Chạy an toàn, không yêu cầu `sudo`, không làm thay đổi file hệ thống:

```bash
./scripts/deploy.sh --check
```

Lệnh sẽ kiểm tra toàn diện:
- Sự tồn tại của các file cấu hình nguồn.
- Các công cụ bắt buộc (`cargo`, `docker`, `nginx`, `suricata`, `nft`, `sudo`).
- Topology mạng (`enp1s0`, `enp7s0`, IP `192.168.10.1`).
- Cú pháp cấu hình Suricata bằng thư mục log cô lập an toàn trong `/tmp`.
- Cú pháp cấu hình Nginx và nftables.
- So sánh diff giữa file nguồn trong Git và file đang chạy trên hệ thống.

### 5.2. Triển khai tự động bằng một lệnh (`--deploy`)

```bash
sudo ./scripts/deploy.sh --deploy
```

Quy trình tự động hóa thực hiện:
1. Tạo thư mục sao lưu có timestamp tại `/var/backups/pbl4/YYYYMMDD_HHMMSS/`.
2. Biên dịch bản release `cargo build --release`.
3. Cài đặt các file cấu hình vào `/etc/suricata/`, `/var/lib/suricata/rules/`, `/etc/nginx/`, `/etc/nftables.d/pbl4.nft`, `/usr/local/bin/pbl4-firewall`. Dọn dẹp an toàn file cũ `pbl4-demo.nft`.
4. Cấu hình sudoers `/etc/sudoers.d/pbl4-security` và cấp quyền nhóm `adm`.
5. Kiểm tra cú pháp trên file vừa cài đặt; tự động **rollback** nếu phát hiện lỗi.
6. Reload an toàn Nginx, Suricata rules và nạp nftables kernel ruleset.
7. Kích hoạt hoặc khởi động lại dịch vụ `pbl4-security.service`.

---

## 6. Danh mục REST API

| Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `GET` | `/` | Giao diện Dashboard NIDS trực quan |
| `GET` | `/style.css` | CSS styling nhúng cho giao diện |
| `GET` | `/app.js` | Javascript điều phối biểu đồ và polling |
| `GET` | `/health` | Kiểm tra trạng thái hoạt động (trả về `"OK"`) |
| `GET` | `/api/stats` | Thống kê tổng số cảnh báo, đòn tấn công bị chặn, kết nối TCP và thông số phần cứng |
| `GET` | `/api/rules` | Danh sách 8 luật và cờ cho phép `auto_block_eligible` |
| `GET` | `/api/alerts?limit=N` | Lấy danh sách N cảnh báo gần nhất |
| `GET` | `/api/blocked-ips` | Lấy danh sách các IP đang bị chặn trong kernel nftables |
| `POST` | `/api/blocked-ips` | Chặn IP thủ công (`{"ip": "...", "reason": "..."}`) |
| `DELETE` | `/api/blocked-ips/{ip}` | Bỏ chặn IP thủ công khỏi kernel |

---

## 7. Kịch bản Kiểm thử Lab (Lab Attack Scenarios)

### 7.1. Kiểm thử Phát hiện XSS (Chính sách `ALERT` — Không chặn IP)
Từ máy Attacker (`192.168.10.10`):
```bash
curl 'http://192.168.10.1/test?q=<script>alert(1)</script>'
```
- Suricata kích hoạt luật SID `1000003` (Cross-Site Scripting Attempt).
- Backend ghi nhận sự kiện vào `security_alerts` với `action = "ALERT"`.
- IP `192.168.10.10` **không bị chặn**, kết nối vẫn hoạt động bình thường.

### 7.2. Kiểm thử Phát hiện Path Traversal (Chính sách `ALERT`)
```bash
curl 'http://192.168.10.1/../../../../etc/passwd'
```
- Suricata kích hoạt luật SID `1000004` (Path Traversal Attempt).
- Backend ghi nhận `action = "ALERT"`.

### 7.3. Kiểm thử Tự động chặn SQL Injection (Chính sách `AUTO-BLOCK`)
Khi cấu hình `AUTO_BLOCK=true` trong `.env`:
```bash
curl 'http://192.168.10.1/login?user=%27%20OR%201%3D1'
```
- Nginx WAF / Suricata kích hoạt luật SQL Injection (SID `1000002`).
- Backend kiểm tra Policy Engine: SID `1000002` đủ điều kiện tự động chặn.
- Gọi firewall helper: `sudo /usr/local/bin/pbl4-firewall block 192.168.10.10`.
- Sự kiện được lưu với `action = "AUTO-BLOCK"`. Bảng `blocked_ips` và `firewall_actions` được cập nhật.
- nftables kernel lập tức `DROP` mọi gói tin từ `192.168.10.10`.

---

## 8. Kiểm thử Tự động (Unit Tests)

Chạy bộ kiểm thử tự động của dự án:

```bash
cargo test
```

Bộ test bao gồm:
- `test_policy_whitelist_evaluation`: Kiểm tra danh sách trắng SID và chế độ bật/tắt chính sách.
- `test_execute_action_alert_only`: Xác minh luật cảnh báo đơn thuần không gọi tường lửa.
- `test_execute_action_auto_block_success`: Xác minh quy trình tự động chặn thành công.
- `test_execute_action_auto_block_failure_fallback`: Xác minh bảo đảm an toàn: nếu firewall lỗi, hệ thống phải ghi nhận là `ALERT` chứ không được ghi nhận là đã chặn.
- `test_validate_lab_attacker_ip`: Xác minh kiểm tra dải IP an toàn trong mạng lab.
- `test_parse_suricata_timestamp`: Xác minh parse thời gian từ Suricata EVE log.
- `test_sqli_regex_patterns`: Xác minh nhận diện chữ ký SQL Injection.
