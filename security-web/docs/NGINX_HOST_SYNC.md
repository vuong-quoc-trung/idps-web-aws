# Đồng bộ NGINX Host → Web VM

## Đối chiếu ngày 10/11/2026

Đã đọc nginx.conf, site enabled và conf.d trên đĩa. `sudo nginx -T` cần mật khẩu tương tác, chưa chạy thành công. Nginx -T kiểm tra file trên đĩa, không dump bộ nhớ worker; không khẳng định mọi chỉnh sửa trên đĩa đã được reload.

| Thành phần | Host trên đĩa | Git mới |
|---|---|---|
| Listen | VMware + Wi-Fi riêng của máy | VMware mặc định; LAN tùy chọn, không lưu IP Wi-Fi vào Git |
| Upstream | Web VM port 80, tất cả URL | Giống host; local 8080/5173 + VM backup tách sang local-demo |
| Access log | pbl4_ai_access, bốn rule_signals | Chung pbl4-access.conf với AI installer |
| AI | Unix syslog, chỉ /api/ | Giữ nguyên socket, telemetry format/filter |
| IP/ID | remote_addr, ghi đè XFF/request ID | Giữ nguyên; không tin header client |
| Method/paths | Chưa có guard trong site | Giữ policy Git: method ngoài allowlist →405, sensitive paths →403 |
| Timeout | Không override trong site | Connect 2s; send/read 60s |
| Error log | Kế thừa nginx.conf | Theo privacy policy Git: /dev/null crit, mất chẩn đoán lỗi request của site |

Send/read timeout tính giữa các lần I/O, không phải tổng thời gian request. Không thêm retry non_idempotent. Các sensitive paths là .env, .git và actuator/env, heapdump như mẫu Git trước đó.

Mẫu 1 MB cuối access.log: 744 JSON event có client_ip, request_id, rule_signals; 6 SQLI và 3 XSS dương tính. Chưa thấy traversal/command dương tính trong mẫu; không kết luận chúng thiếu. NGINX cô lập đã kiểm chứng cả bốn map.

Rust src/events.rs đọc JSON không phụ thuộc tên log_format, nhận status, latency_seconds, request/response_bytes và signals số1/boolean true. SQLI/COMMAND_INJECTION severity1; XSS/PATH_TRAVERSAL severity2, tránh trùng detection trong event. Signals dùng trước canonical redaction, không thành input AI. NGINX_ACCESS_PATH mặc định /var/log/nginx/access.log. Không sửa parser/detection/schema/dedup/checkpoint.

AI nhận method, path đã che và User-Agent/Accept/Content-Type; không query/body/Cookie/Authorization/rule_signals. Telemetry phát ở access-log phase, worker xử lý bất đồng bộ. Unix datagram có thể mất khi worker/socket không sẵn sàng; không đảm bảo mọi request có score. Giữ shadow mode, resource guard và request ID xuyên response/upstream/access/AI.

IP edge là TCP peer: qua NAT/tunnel có thể chỉ thấy IP NAT/tunnel. Spring chỉ tin XFF và request ID khi peer thuộc trusted-proxies. Cần kiểm tra proxy trên Web VM giữ chain/ID và trust từng hop; chưa xác minh runtime Web VM, không sửa nó. Không mở trust toàn mạng.

Readiness service chỉ chờ vmnet2/vmnet3 tối đa90s, không đợi Wi-Fi. LAN listener yêu cầu IP đã tồn tại khi start NGINX; nếu Wi-Fi chưa lên, bind có thể fail. Không thay đổi service trong công việc này.

## Tạo candidate, không tác động hệ thống

Từ root repository:

```bash
python3 security-web/scripts/prepare-nginx-host.py --output /tmp/pbl4-nginx-plan
# Nếu cần Wi-Fi: thêm --lan-ip <IP-LAN-hiện-tại-của-Defender>
# Có --host-ip và --upstream-ip cho môi trường khác.
```

Script chỉ render hai file: pbl4-proxy và pbl4-ai-shadow.conf. Cùng tham số cho cùng nội dung; không cài service, không sửa .env. Luôn giữ AI access sink, không bật/tắt worker. Dùng cả hai file, không copy riêng template vào sites-enabled. Không nạp đồng thời pbl4-access.conf riêng: maps đã nằm trong candidate pbl4-ai-shadow.conf. Không cài pbl4-local-demo.conf lên host.

AI installer giữ nguyên site đã gắn AI (kể cả LAN listener) khi chạy lại. Installer legacy cho layout lạ sẽ từ chối thay vì đoán cách patch. Với host/upstream khác mặc định, dùng renderer và review thủ công; AI installer legacy vẫn kiểm tra topology mặc định.

## Triển khai thủ công sau khi review

Không chạy deploy.sh --deploy (đã bị khóa). Các lệnh sau chỉ dành cho người vận hành, chưa được chạy bởi agent. Giữ cùng tham số LAN ở bước render/check.

```bash
sudo nginx -T
sudo python3 security-web/scripts/prepare-nginx-host.py --output /tmp/pbl4-nginx-reviewed --check-system
# Thêm --lan-ip nếu cần, như bước tạo candidate.
diff -u /etc/nginx/sites-available/pbl4-proxy /tmp/pbl4-nginx-reviewed/pbl4-proxy
diff -u /etc/nginx/conf.d/pbl4-ai-shadow.conf /tmp/pbl4-nginx-reviewed/pbl4-ai-shadow.conf
```

--check-system thay candidate vào bản sao nginx.conf, giữ tất cả site/include khác để bắt trùng format/listener; chỉ nginx -t, không reload. Review diff, đặc biệt LAN, methods, sensitive paths và error logging. Không công khai nginx -T nếu có thiết lập riêng/secret.

Ví dụ cài trên layout hiện tại (hai file đã tồn tại, symlink enabled đã đúng). Dừng nếu layout khác; không tạo thêm site cạnh site cũ:

```bash
PBL4_BACKUP="/var/backups/pbl4-nginx-$(date +%Y%m%d-%H%M%S)"
sudo mkdir -m 700 "$PBL4_BACKUP"
sudo cp -a /etc/nginx/sites-available/pbl4-proxy "$PBL4_BACKUP/pbl4-proxy"
sudo cp -a /etc/nginx/conf.d/pbl4-ai-shadow.conf "$PBL4_BACKUP/pbl4-ai-shadow.conf"
sudo cp -a /etc/nginx/sites-enabled/pbl4-proxy "$PBL4_BACKUP/enabled-link"
sudo install -o root -g root -m 644 /tmp/pbl4-nginx-reviewed/pbl4-proxy /etc/nginx/sites-available/pbl4-proxy
sudo install -o root -g root -m 644 /tmp/pbl4-nginx-reviewed/pbl4-ai-shadow.conf /etc/nginx/conf.d/pbl4-ai-shadow.conf
sudo nginx -t && sudo systemctl reload nginx
```

Nếu test/reload thất bại hoặc cần rollback, dùng đúng thư mục backup vừa in/ghi lại; không restart worker:

```bash
sudo cp -a "$PBL4_BACKUP/pbl4-proxy" /etc/nginx/sites-available/pbl4-proxy
sudo cp -a "$PBL4_BACKUP/pbl4-ai-shadow.conf" /etc/nginx/conf.d/pbl4-ai-shadow.conf
sudo nginx -t && sudo systemctl reload nginx
```

Symlink enabled không bị thay đổi. Sau reload kiểm tra nginx active, listener đúng, request thường tới VM, request ID xuyên NGINX/Student Audit, và heartbeat/score AI. Chạy probe lab chỉ sau khi người vận hành cho phép. Không coi thiếu AI score hoặc không có alert ở request thường là lỗi. Nếu cùng nội dung đã cài, bỏ qua install/reload.

## Kiểm thử

- test-nginx-host.py: 10/10 đạt; real NGINX cô lập, upstream giả, log tạm, telemetry file sink thay socket worker.
- test-ai-shadow-host.py: 7/7 đạt; backup/restore, idempotence, privacy, unit limits.
- test-dev-launcher.py: 7/7 đạt.
- test-config-contracts.py EdgeConfigTests: 5/5 đạt, giữ local failover.
- Rust safe_nginx_edge_hints_do_not_require_logging_query_values: đạt.
- Lượt cargo test lọc nginx rộng: 3 test đạt, 3 test cần DB bị sandbox chặn kết nối. Không chạy lại với quyền DB; không có nghiệm thu DB/end-to-end/live worker mới.

Không thay đổi /etc, service, firewall, database, VMware, Student Web, Rust, Suricata hoặc AI Worker. Chưa commit/push.
