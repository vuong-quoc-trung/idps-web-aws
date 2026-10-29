# Bốn nhóm phát hiện HTTP bổ sung

Các chữ ký nằm trong `suricata/pbl4.rules`, dành cho Suricata 8.0.3 và HTTP nhìn thấy
trên interface capture. Có 14 chữ ký trong danh mục, gồm các biến thể URI/body.
Backend normalize SID thành tên/category cố định, lưu cảnh báo và dùng hàng đợi
firewall/audit hiện có khi operator bật chính sách. Không đổi canonical event hoặc
feature schema AI, không thu thêm request body vào DB/log.

| Nhóm | SID | Severity | Điều kiện |
|---|---|---|---|
| HTTP Request Flood | 1000010 | 2 | Một IP có 100 request trong 10 giây; tối đa 1 alert/IP/window |
| Time/Blind SQLi | 1000008 URI; 1000013 body | 1 | sleep/pg_sleep, benchmark, WAITFOR DELAY, DBMS_LOCK/DBMS_PIPE; URI giữ các nhánh error/statement cũ |
| Web shell upload | 1000011 | 1 | Tên file thực thi PHP/JSP/ASP và dấu hiệu thực thi server-side trong cùng một multipart part |
| Possible SSRF | 1000012 URI; 1000014 body | 2 | Tham số URL có đích loopback, IPv4 private, metadata hoặc file:// |

SQLi/SSRF body áp dụng với form-urlencoded, application/json và text/plain; giải mã
URL tối đa hai lần. Không giải mã JSON Unicode escapes hay mọi định dạng body.
Rule upload chặn việc ghép tên file ở part này với code ở part khác; chỉ tìm tag và
primitive trong các cửa sổ tối đa 512 byte mỗi bước sau header. Các phần header cũng
có giới hạn độ dài. Chữ ký không bao phủ mọi mã độc/file type, encoding, file nén,
web shell bị làm rối hoặc payload nằm ngoài cửa sổ/giới hạn inspection.

Đây là dấu hiệu attempt, không là bằng chứng thực thi, tải file thành công hay
server đã thực hiện SSRF. Upload source code hợp lệ và webhook nội bộ có thể khớp;
review false positive trước khi cho phép phản ứng. Flood có thể là người dùng sau
NAT/proxy chung hoặc tải trang dev nhiều asset; chỉnh count/seconds trong SID1000010
dựa trên traffic lab. Không bật phản ứng flood chỉ vì vượt một ngưỡng chưa đo.

SSRF kiểm URI/body đầu vào, không chứng minh request outbound. Không bao phủ DNS
rebinding, redirect chain, mọi biểu diễn IP/IPv6, header-only hay body mã hóa. Với
TLS, cần quan sát HTTP sau termination; capture TLS mã hóa không có các buffer này.
Nginx vẫn giữ cơ chế che query/body; các rule mới phụ thuộc Suricata, không giả định
Nginx access log có request body. Default libhtp request-body-limit của repo là
100 KiB và inspection window 4 KiB; không đổi các giới hạn này trong lần bổ sung.

## Kiểm thử không gửi mạng

Từ `security-web/`:

```bash
check_dir=$(mktemp -d /tmp/pbl4-suricata-check.XXXXXX)
suricata -T -c config/suricata/suricata.yaml \
  -S "$PWD/suricata/pbl4.rules" -l "$check_dir"
python3 scripts/test-extended-rules.py
python3 scripts/test-config-contracts.py SensorRuleTests
```

PCAP được tạo trong thư mục tạm và decode offline. Kiểm tra SQLi URI/POST, upload
PHP/JSP và file bình thường, hai multipart part không được ghép nhầm, SSRF URL nội
bộ/public/domain giả, flood 99/100 request, keep-alive, từng IP và window 10 giây.
Body canary không xuất hiện trong EVE. Không chạy tấn công live hoặc thực thi file.

Rust có test catalog SID/severity khớp file rule, tên cố định/không lưu payload,
AUTO_BLOCK allowlist và integration test DB → audit queue → helper mock có TTL.
Integration test phải dùng PostgreSQL test riêng; không dùng database ứng dụng.

## Cài rule trên host: người vận hành thực hiện

Git pull/build backend không cập nhật rule đã cài trên hệ thống. Sau khi syntax
check bản repo thành công, sao lưu và cài đúng file (nếu chưa có bản cũ, bỏ bước cp):

```bash
sudo cp -a /var/lib/suricata/rules/pbl4.rules \
  "/var/lib/suricata/rules/pbl4.rules.backup-$(date +%Y%m%d-%H%M%S)"
sudo install -o root -g root -m 0644 suricata/pbl4.rules \
  /var/lib/suricata/rules/pbl4.rules
sudo suricata -T -c /etc/suricata/suricata.yaml
```

Chỉ sau khi lệnh cuối thành công và rule-files trong YAML có `pbl4.rules`:

```bash
sudo systemctl restart suricata
systemctl status suricata --no-pager
cargo run --locked
```

Giữ `AUTO_BLOCK=false`, `ENFORCEMENT_MODE=OFF` và watcher EVE thật. Trên Kali, gửi
từng probe cố định tới proxy 192.168.10.1 (không tới dashboard hoặc metadata server):

```bash
bash scripts/lab-probes.sh time-sqli
bash scripts/lab-probes.sh time-sqli-body
bash scripts/lab-probes.sh upload
bash scripts/lab-probes.sh ssrf
bash scripts/lab-probes.sh ssrf-body
```

Upload probe chỉ chứa marker PHP trong comment không thực thi. Không tự tạo endpoint
upload/fetch trên Student; đường dẫn probe có thể trả 404 nhưng sensor vẫn quan sát.
Script không sinh flood live; kiểm ngưỡng bằng PCAP để tránh tải bất ngờ lên lab.
Đối chiếu SID/IP/thời gian trong EVE, DB và tab Cảnh báo; danh mục Luật phát hiện
hiển thị đủ 14 SID. Nhiều chữ ký/nguồn có thể quan sát cùng request.

## Chính sách chặn: cấu hình sẵn khả năng, chưa bật trên host

Mặc định và `.env` hiện có vẫn giữ:

```dotenv
AUTO_BLOCK=false
ENFORCEMENT_MODE=OFF
```

Trước tiên nghiệm thu manual BLOCK/UNBLOCK cho đúng IP Kali trong mode MANUAL sau
khi operator duyệt. Không block IP quản trị/host/WebVM/gateway. Kiểm tra helper root,
policy root và sudoers theo HOST_SECURITY_SETUP.md; service boot chỉ nạp bảng lab.

Khi đã được duyệt bật phản ứng, allowlist SID sau bao gồm SQLi, upload và SSRF:

```dotenv
AUTO_BLOCK_SIDS=1000002,1000008,1000011,1000012,1000013,1000014
```

Flood 1000010 vẫn là opt-in riêng: chỉ thêm sau khi đo và chấp nhận ngưỡng. Thực thi
tự động còn cần AUTO_BLOCK=true và ENFORCEMENT_MODE=ENFORCE; tài liệu này không tự
đổi hai biến đó. Chỉ severity1 hoặc thêm SID vào danh mục không tự mở quyền chặn.

Chặn qua nftables sau khi sensor ghi EVE/backend xử lý; request đầu có thể đã tới
ứng dụng. Không gọi đây là inline IPS hoặc bảo đảm ngăn mọi khai thác đầu tiên.
Queue giữ gate freshness, allowlist mạng, protected IP, TTL và audit như trước.
Trong OFF, worker không thực thi PENDING/RESTORE. Khôi phục/chặn lại IP trong DB
không được thực hiện tự động trong lần cập nhật rule này.

Ruleset hash đã đổi: report/readiness AI gắn hash rule cũ là bằng chứng lịch sử;
chạy lại gate/replay phù hợp trước khi dùng rule mới cho một experiment mới. Không
ghi đè report, dataset, checkpoint hoặc sửa label cũ để ép readiness qua.

Tham chiếu chính thức: [HTTP buffers](https://docs.suricata.io/en/suricata-8.0.3/rules/http-keywords.html),
[thresholding](https://docs.suricata.io/en/suricata-8.0.3/rules/thresholding.html),
[transforms](https://docs.suricata.io/en/suricata-8.0.3/rules/transforms.html).
