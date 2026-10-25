# Kiểm tra ghi nhận cảnh báo bằng request lab

Các mẫu này kiểm tra signature/pipeline. Có cảnh báo không có nghĩa Student Web có lỗ hổng hoặc khai thác thành công. Script không thử đăng nhập, không gửi form thay đổi dữ liệu và không đọc nội dung response. Các chuỗi XSS/SQLi/traversal chỉ gửi đến đường dẫn kiểm thử; scanner test chỉ đổi User-Agent, không chạy sqlmap.

## Chạy ở đâu

- **Kali VM:** chạy `scripts/lab-probes.sh`. Đích cố định là proxy HTTP `192.168.10.1:80`; không gửi đến dashboard `:3000` hoặc Web VM trực tiếp.
- **Security VM:** Suricata trên NIC phía Kali, Nginx và Rust backend hoạt động. Xem log/DB tại đây.
- **Máy quản trị:** mở dashboard qua mạng quản trị hoặc SSH tunnel.

Trước khi chạy: đặt `AUTO_BLOCK=false` trong `.env` của Security VM và restart backend (Ctrl+C/cargo run hoặc systemctl restart pbl4-security, tùy cách đang chạy). Nếu có biến AUTO_BLOCK được export trong terminal, cần cập nhật hoặc unset vì biến môi trường có ưu tiên hơn `.env`. Tắt auto-block không bỏ chặn IP cũ: vào dashboard bỏ chặn Kali, chờ audit SUCCESS và kiểm tra kernel đã bỏ IP.

## Kiểm tra điều kiện

Trên Security VM:

```bash
sudo systemctl status suricata nginx --no-pager
sudo suricata -T -c /etc/suricata/suricata.yaml
sudo tail -F /var/log/suricata/eve.json | jq --unbuffered -c 'select(.event_type == "alert") | {timestamp,src_ip,dest_ip,sid:.alert.signature_id,signature:.alert.signature}'
```

Lệnh lọc dùng jq; nếu chưa có, xem trực tiếp `sudo tail -F /var/log/suricata/eve.json`. Giữ terminal log mở. Chạy Rust backend từ security-web hoặc dịch vụ đã deploy; dashboard Trạng thái phải cho biết watcher đang đọc được log.

Trên Kali, HTTP bình thường phải tới được proxy trước:

```bash
curl --noproxy '*' --max-time 8 -I http://192.168.10.1/
```

## Chạy script

Nếu repo nằm trên Kali, từ thư mục security-web:

```bash
# Xem lệnh trước, không gửi mạng:
bash scripts/lab-probes.sh all --dry-run
# Thử từng dạng:
bash scripts/lab-probes.sh xss
bash scripts/lab-probes.sh sqli
bash scripts/lab-probes.sh traversal
bash scripts/lab-probes.sh sensitive
bash scripts/lab-probes.sh scanner
# Hoặc 1 request bình thường + 5 request kiểm thử, cách nhau 2 giây:
bash scripts/lab-probes.sh all
```

Nếu Kali chưa có repo, chép riêng file lab-probes.sh sang Kali rồi chạy `bash lab-probes.sh all`. Không cần Rust/Node trên Kali; script chỉ cần Bash và curl.

| Case | Chuỗi gửi | SID Suricata kỳ vọng |
|---|---|---|
| normal | HTTP thông thường | Không có alert từ các rule PBL4 cho request đơn lẻ này |
| xss | `<script>alert(1)</script>` trong query | 1000003 |
| sqli | `' OR 1=1--` trong query | 1000002; Rust cũng có thể nhận diện qua Nginx |
| traversal | `../../pbl4-probe.txt` trong query | 1000004 |
| sensitive | `/.env` trong query tại đường dẫn kiểm thử | 1000006 |
| scanner | User-Agent `sqlmap/pbl4-lab-probe` | 1000007 |

SID kỳ vọng dựa trên `suricata/pbl4.rules` trong repo. Chỉ xác nhận đạt sau khi thấy event thực tế; rule đang cài trên VM, interface và HTTP normalization có thể ảnh hưởng kết quả. Không chạy liên tục thành burst vì rule SYN có ngưỡng 10 trong 5 giây và có thể thêm cảnh báo scan.

HTTP 400/404 vẫn có thể sinh cảnh báo: IDS quan sát request trước khi ứng dụng trả response. HTTP 000 là curl không nhận được response, cần kiểm tra routing/block/proxy. Script không tự kết luận PASS chỉ từ HTTP status.

## Đối chiếu DB và dashboard

Trong DBeaver, kết nối `pbl4_security`:

```sql
SELECT id, occurred_at, source, host(src_ip) AS src_ip,
       rule_name, severity, action, evidence
FROM security_alerts
WHERE created_at >= now() - interval '15 minutes'
ORDER BY id DESC
LIMIT 100;

SELECT id, host(ip) AS ip, actor, action, status, reason, details, created_at
FROM firewall_actions
WHERE created_at >= now() - interval '15 minutes'
ORDER BY id DESC;
```

Dashboard → Cảnh báo → lọc IP Kali (thường `192.168.10.10`) → Làm mới; polling khoảng 5 giây, có thể cần thêm thời gian xử lý log. Với AUTO_BLOCK=false và không có yêu cầu manual khác, các sự kiện mới chỉ ALERT. Một SQLi có thể có hai dòng nguồn SURICATA và NGINX; đây là hai nguồn quan sát, không phải tự động chứng minh đọc log trùng.

Mỗi case ghi lại: giờ UTC script in ra, IP nguồn, SID trong eve.json, ID trong DB và ảnh UI. `pbl4_run` giúp tìm request trong Nginx access.log; không phải mọi event Suricata đều kèm trường HTTP URI.

## Nếu không thấy cảnh báo

1. Không có request trong access.log: kiểm tra Kali có đi qua đúng proxy và có đang bị block hay không.
2. Có request nhưng không có EVE alert: tcpdump đúng NIC (`sudo tcpdump -ni vmnet2 host 192.168.10.10 and tcp port 80`), kiểm tra Suricata đang chạy đúng interface và đã nạp pbl4.rules. Thay IP/interface nếu topology lab thực tế khác.
3. Có EVE nhưng DB không có: xem trạng thái watcher, quyền đọc log, kết nối DB và log Rust (`journalctl -u pbl4-security -f` nếu chạy service).
4. DB có nhưng UI chưa thấy: làm mới, bỏ lọc, về trang 1, kiểm tra đúng backend/database.
5. Test từ host hoặc ngay Security VM có thể không đi qua NIC Suricata đang nghe; hãy chạy từ Kali.

## Sau khi ghi nhận đã đạt

Kiểm thử manual block/unblock theo LAB_ACCEPTANCE.md trước. Auto-block là bước riêng: bật AUTO_BLOCK=true, restart backend, thử đúng một case sqli, đối chiếu audit SUCCESS, trạng thái AUTO-BLOCK, nftables và truy cập từ Kali. Không chạy cả bộ khi auto-block bật vì IP có thể bị chặn ngay ở SQLi khiến các case sau không tới Nginx.
