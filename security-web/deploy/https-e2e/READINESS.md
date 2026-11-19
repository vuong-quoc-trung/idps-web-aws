# HTTPS hai chặng — Giai đoạn A / chuẩn bị, chưa triển khai

## Trạng thái đã khảo sát

- Nhánh feature/https-end-to-end. Người vận hành báo Live extended 14/14 PASS,
  72 accepted / 2 rejected. Đây là bằng chứng người vận hành cung cấp, không phải
  lần chạy production được thực hiện trong giai đoạn A.
- NGINX 1.28.3, Suricata 8.0.3 qua binary version.
- Site trên đĩa: 192.168.10.1:80 và :443; cert/key lab tại /etc/nginx/pbl4-tls;
  upstream HTTP 192.168.20.10:80; edge limits, request ID và AI syslog tồn tại.
- /etc/nginx/modules-enabled rỗng. Module njs đã giải nén phục vụ test không có
  nghĩa là production đã cài/nạp module.
- Suricata service drop-in 90-pbl4-post-proxy.conf chọn
  /etc/suricata/pbl4/post-proxy.yaml, không phải YAML mặc định còn ghi vmnet2.
- systemd bus và netlink bị sandbox từ chối: chưa xác nhận service đang active,
  interface/IP hiện tại, cgroup worker hoặc bảng nft runtime.
- Rust transaction_proof là cfg(test); không có ingest proof runtime. Attribution
  local loopback bị từ chối Verified dù biến trusted-edge được bật.
- Student repo có TLS trong application-prod.yaml nhưng profile này còn thay đổi
  bootstrap, cookie, public URL/JPA. Không bật prod chỉ để bật TLS. VM chưa được
  truy cập; chưa xác nhận service/connector nào thực sự phục vụ cổng 80.

## Thành phần tái sử dụng và khoảng trống

prepare-nginx-host.py / sync-nginx-edge.py: TLS Edge, egress CA/name/port, metadata
bảo toàn khi render lại. Template egress hiện CHƯA tích hợp proof; không áp dụng
bản render này như thể nó đã có HMAC. Hai server block vẫn một NGINX instance.
Proof njs, Lua chọn lọc, nonce, rotation và guard lifecycle hiện thuộc harness.
Cần nối chúng vào renderer/lifecycle trước khi cho phép apply, kiểm tra sync chạy
lại không xóa proof, không thêm AI telemetry ở Egress. Không copy nguyên harness
thành cấu hình production: nó có mock, fault injection, key test và đường dẫn tạm.

Student TLS overlay bên cạnh chỉ thay TLS connector/cookie, không đổi API, DB,
Audit hoặc authentication. Spring một connector sẽ chuyển port, không giữ HTTP
song song. Nếu VM có NGINX frontend, ưu tiên bổ sung TLS tại frontend và giữ
connector Spring hiện tại; phải đọc cấu hình VM trước khi chốt cách triển khai.

UID riêng: dùng prepare-proof-identity.py và DEDICATED-IDENTITY.md làm đầu vào;
kiểm tra độc quyền UID/GID, socket AI, log/temp, TLS key, njs và mọi site chung.
Không tạo user/copy khóa trong bước A. Root/worker UID compromise nằm trong trust
boundary. Guard UID+cgroup không thay thế bảo vệ khóa.

## Lệnh khảo sát do người vận hành chạy (chỉ đọc)

```bash
sudo nginx -T
systemctl cat nginx suricata
systemctl status nginx suricata --no-pager -l
ip -br addr
sudo nft list ruleset
ps -eo pid,ppid,user,group,cgroup,comm
sudo openssl x509 -in /etc/nginx/pbl4-tls/lab.crt -noout -dates -ext subjectAltName
```

Không gửi nguyên env, khóa hoặc output có bí mật vào chat/Git. Trên Student VM:
đọc service unit/override thực tế, `ss -lntp`, bản build/profile, đường log Audit,
TLS hiện có và reverse proxy; tránh in Environment chứa password. Kiểm tra tài
khoản lab, audit HMAC, trusted proxy hiện tại trước khi thay gì.

## Backup và rollback dự kiến (chỉ sau phê duyệt triển khai)

Backup root-only cả /etc/nginx, Suricata YAML+drop-in đang dùng, unit overrides,
phiên bản package/module, cấu hình service Student và TLS trước khi chuyển.
Ví dụ trên Defender, operator tự chạy, không đặt backup chứa khóa trong repo:

```bash
sudo install -d -m 700 /var/backups/websentinel-e2e
sudo sh -c 'umask 077; tar -czf /var/backups/websentinel-e2e/defender-before.tgz /etc/nginx /etc/suricata /etc/systemd/system/suricata.service.d'
```

Tên backup phải mới, không ghi đè bản trước. Ghi nhận hash và baseline health:
HTTP/HTTPS status thực tế, request ID, fresh EVE/Audit, số AI event/request và
trạng thái Unverified. Không chỉ kiểm tra service running.

Rollback: đưa Student về connector/profile/env trước thay đổi, kiểm tra HTTP
192.168.20.10:80 nội bộ; khôi phục site Edge HTTPS -> HTTP VM cùng includes và
Suricata post-proxy YAML/drop-in từ backup đã kiểm tra. Chạy nginx -t và suricata
-T với đúng YAML/rules trước reload/restart. Nếu syntax lỗi, không reload. Nếu
unit thay đổi thì operator daemon-reload; giữ nguyên nft guard cho đến khi site
không còn phụ thuộc egress. Chỉ gỡ bảng guard riêng sau cùng, không flush ruleset.
Không restore PostgreSQL hoặc xóa dữ liệu lịch sử. Kiểm tra lại health baseline.

## Chuẩn bị B/C: CA và TLS

Chốt tên ổn định ví dụ student.lab, port theo VM; SAN chứa đúng DNS/IP được dùng.
Private CA/key và PKCS12 ở ngoài Git, chỉ CA public được đưa sang Defender.
Không dùng -k, proxy_ssl_verify off hoặc CA dùng cho test. Cấp password qua cơ chế
bí mật của service, không CLI/history. Overlay dùng spring.config.additional-location
(file ngoài repo); không thay spring.config.location làm mất cấu hình hiện có.

Sau khi operator cài certificate/connector trên VM và trước đổi Egress:

```bash
curl --cacert /path/to/student-ca.crt --resolve student.lab:8443:192.168.20.10 https://student.lab:8443/api/auth/me
```

401 khi chưa đăng nhập có thể đúng; cần xác minh TLS thành công, auth và Audit
không đổi. Negative test CA/tên sai phải thất bại. Đồng bộ tên với proxy_ssl_name,
proxy_ssl_server_name on, proxy_ssl_verify on. Chỉ đổi Suricata sang lo khi Edge
-> Egress -> HTTPS VM đã qua healthcheck và có rollback.

Render vào staging để review (chưa phải cấu hình proof production hoàn chỉnh):

```bash
python3 security-web/scripts/prepare-nginx-host.py --host-ip 192.168.10.1 --upstream-ip 192.168.20.10 --tls-cert /etc/nginx/pbl4-tls/lab.crt --tls-key /etc/nginx/pbl4-tls/lab.key --egress-ca /path/to/student-ca.crt --egress-name student.lab --egress-port 8443 --output /tmp/ws-e2e-review
python3 security-web/scripts/prepare-suricata-post-proxy.py --profile local-egress --base /etc/suricata/pbl4/post-proxy.yaml --output /tmp/ws-sensor-review
```

Các lệnh apply/reload chưa được phê duyệt; không chạy sync --apply ở giai đoạn A.

## Chuẩn bị D: contract Shadow, chưa nối vào runtime

Default OFF, bật riêng bằng cấu hình được review ở giai đoạn D. Proof logger riêng,
không ghi đè EVE. Join generation+flow_id+tx_id; giới hạn kích thước, thời gian và
cache, xử lý duplicate idempotent, thiếu/mâu thuẫn => Shadow Unverified. Kết quả
HMAC hợp lệ chỉ là shadow evidence, tuyệt đối không sửa client_ip_verified hoặc
quyết định enforcement. Không bật AUTO_BLOCK; giữ ENFORCEMENT_MODE=OFF.

Rà soát schema metadata JSON/API hiện có trước chọn nơi lưu; không mặc định tạo
migration hay ghi proof/key/headers nhạy cảm vào DB. Không hứa Dashboard đã hiển
thị shadow proof: runtime ingest và mapping API vẫn chưa được triển khai. Dùng
feature flag để tắt shadow mà không ngừng ingestion NGINX/Suricata/Audit.

Gates: timing chưa nghiệm thu; journal chưa chống rollback/thu hồi runtime;
response_complete trong harness không phải nguồn runtime đáng tin; mid-body abort
chưa đầy đủ. Không biến kết quả shadow thành Verified. Giai đoạn E cần bằng chứng
fresh log, trạng thái DB/API/UI, không duplicate và rollback thực tế.

## Điểm dừng

A hoàn tất ở mức khảo sát source/đĩa và chuẩn bị. Operator cần cung cấp kết quả
runtime read-only và khảo sát VM để chốt B/C. Cài njs, tạo UID, cấp khóa/chứng chỉ,
chuyển connector, nft, đổi capture và reload/restart đều cần bước triển khai riêng.
Không tự chuyển sang B hoặc áp dụng bất kỳ template nào.
