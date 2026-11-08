# AI Shadow — Security host + Student Web VM

## Phạm vi và trạng thái

Bộ cài cho NGINX thật `192.168.10.1:80 → 192.168.20.10:80`, không dùng launcher local, không khởi tạo Student/DB mới. Chỉ chuẩn bị và kiểm thử offline trong phiên Codex; chưa cài service, chưa thay `.env`, chưa nghiệm thu HTTP/model/DB trên host.

Tái sử dụng worker RIv2 `request-intelligence-v2-frozen-step3072`, manifest SHA256 được pin trong installer và worker. Bộ cài kiểm tra tất cả hash model và dependency Python trước khi ghi. Giữ feature schema và Rust ingest hiện có. Đây không phải nghiệm thu GLU207/three-source model. Score là điểm nghiên cứu, không phải xác suất bị tấn công.

## Cài đặt

Trên Security host, Web VM vẫn chạy theo cách cũ. Không chạy `dev-up-and-verify.sh` để thay kiến trúc này. Interpreter dùng `ai-training/.venv/bin/python` hiện có; không xóa/di chuyển repo hoặc venv sau khi cài. Worker không chạy root. Model và source được sao chép thành snapshot root-owned `/opt/pbl4-ai-shadow/<hash>`; interpreter/venv vẫn do người dùng quản lý.

```bash
cd /home/dinh-huynh-nguyen-khang/Projects_PBL4/idps-web-aws
# Chỉ tạo candidate, kiểm tra model/dependency, không sửa host:
python3 security-web/scripts/install-ai-shadow-host.py
# Đọc candidate trong .local-dev/ai-host-plan trước khi cài.
sudo python3 security-web/scripts/install-ai-shadow-host.py \
  --install --backend-user dinh-huynh-nguyen-khang --configure-backend
```

Installer chỉ hỗ trợ site đơn đã kiểm tra `/etc/nginx/sites-available/pbl4-proxy`. Layout khác sẽ dừng để review. Chạy `nginx -t` cho hiện tại và candidate trước thay đổi, backup các file thay đổi trong `/var/backups/pbl4-ai-shadow/<timestamp>/`, kiểm tra cấu hình thật lần nữa, đợi heartbeat READY tối đa 120 giây rồi mới reload NGINX. Lỗi cài đặt sẽ cố khôi phục cấu hình và trạng thái service trước đó; đọc lỗi nếu rollback cũng thất bại. Không restart VMware, Suricata, RELP, firewall hay database.

Các file hệ thống được tạo/sửa:

- `/etc/nginx/conf.d/pbl4-ai-shadow.conf`
- `/etc/nginx/sites-available/pbl4-proxy`
- `/etc/systemd/system/pbl4-ai-shadow.service`
- `security-web/.env` chỉ khi truyền `--configure-backend`: `AI_SHADOW_RESULTS_PATH=/var/log/pbl4-ai-shadow/results.jsonl`, `AUTO_BLOCK=false`, `ENFORCEMENT_MODE=OFF`.

**Access log:** giữ `/var/log/nginx/access.log`, chuyển `combined` sang JSON canonical sẵn có trong repo để có request ID và rule_signals. Rust hiện hỗ trợ format này; các consumer ngoài Rust nếu yêu cầu combined phải được review trước khi cài. Query được kiểm tra trong bộ nhớ để tạo flag rule, không lưu raw query. Không tạo rule/model mới.

Dừng tiến trình Rust cũ bằng cách đang quản lý nó, sau đó chạy lại từ `security-web` (`cargo run`) để nhận `.env`. Không chạy hai Rust instance trùng port. Installer không restart Rust, không tự áp dụng migration và không chỉnh dữ liệu. Nếu Rust báo migration conflict thì xử lý lịch sử migration trước; không reset DB.

## Service, quyền và tính độc lập

`pbl4-ai-shadow.service`: user của backend, group `www-data`; tự enable boot, restart lỗi sau 10 giây, giới hạn 5 lần/300 giây. Runtime directory `0710`, socket Unix datagram `0620` tại `/run/pbl4-ai-shadow/nginx.sock`. NGINX group chỉ được gửi. Journal directory `0700`, file `0600`, Rust cùng user đọc được. Không mở TCP port cho AI.

Worker có CPU/RAM limit và guard nhiệt hiện có. Nhiệt cao, thiếu RAM hoặc không xác minh được cảm biến sẽ dừng với exit 78, không tự restart liên tục. Kiểm tra máy đã nguội, RAM đủ, cảm biến đọc được rồi mới `sudo systemctl restart pbl4-ai-shadow.service`. Không tắt guard để ép inference.

NGINX gửi telemetry bằng syslog Unix datagram ngoài luồng proxy; không chờ kết quả AI. Queue giới hạn và có thể drop khi worker lỗi/quá tải; không cam kết giao nhận AI không mất. Journal giữ tối đa khoảng 4 × 2 MiB; Rust tắt quá lâu có thể bỏ lỡ phần đã rotate mất. Không dùng journal AI thay audit RELP.

Telemetry chỉ API, gồm method, normalized path, request ID, timestamp và ba header User-Agent/Accept/Content-Type đã lọc một số mẫu nhạy cảm. Không query/body/Cookie/Authorization. Các pattern lọc không bảo đảm che mọi bí mật tùy ý nhét vào path/header; không đưa secret vào những trường này. Auth paths được thay bằng `/api/redacted`. Do đó AI không thấy SQLi chỉ nằm trong query/password/body; coverage khác demo có query. Rule NGINX vẫn nhận flag URI/query như trước.

NGINX tự tạo request ID, chuyển tới VM; đặt X-Forwarded-For bằng remote_addr tại edge để không tin header do client gửi. Nếu có trusted proxy khác đứng trước host, cần review chính sách IP trước cài. Student VM cần giữ/ghi request ID được chuyển tiếp; chỉ kết luận correlation khi đối chiếu thấy ID thực sự khớp.

## Nghiệm thu từng tầng

```bash
sudo nginx -t
systemctl status pbl4-ai-shadow.service --no-pager -l
systemctl is-enabled pbl4-ai-shadow.service
sudo journalctl -u pbl4-ai-shadow.service -n 50 --no-pager
sudo stat -c '%a %U:%G %n' /run/pbl4-ai-shadow /run/pbl4-ai-shadow/nginx.sock
# Chạy bằng user backend, không sudo:
python3 security-web/scripts/verify-ai-shadow-host.py
```

Verifier gửi đúng một GET `/api/auth/me` tới host thật, nhận request ID, đợi SCORED trong journal tối đa 60 giây. HTTP 401 là bình thường khi chưa đăng nhập. HTTP 5xx hoặc thiếu ID sẽ fail. PASS chỉ xác nhận HTTP + inference journal, chưa khẳng định DB/Dashboard.

Lấy request ID được in ra để đối chiếu:

1. Trong access log JSON có ID đó; IP đúng nguồn test.
2. Journal có cùng ID, `status=SCORED`, đúng model version, `mode=shadow`, `enforcement_actions=0`.
3. Đăng nhập Security Dashboard → AI shadow, tìm request ID. Trong browser đã đăng nhập, kiểm tra response `/api/ai-shadow?request_id=<ID>`: `items` chứa kết quả đó, `worker.stale=false`, `mode=shadow`, `enforcement=DISABLED`. `correlated_sources` phải phản ánh dữ liệu thật; Student có thể đến sau qua RELP.
4. Audit ứng dụng có NGINX/Student cùng ID khi VM truyền ID đúng. Cảnh báo AI chỉ xuất hiện nếu score **lớn hơn** threshold `0.8826237916946411`; request bình thường không bắt buộc có alert.
5. Test một query SQLi vô hại để xác nhận rule NGINX còn hoạt động (không flood, không thay dữ liệu):

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 8 -i -G \
  --data-urlencode "probe=' OR '1'='1" http://192.168.10.1/api/auth/me
```

Đối chiếu request ID của probe trong log và cảnh báo SQLI NGINX. Không dùng probe query này làm tiêu chí bắt buộc AI alert vì query không được chuyển cho AI.

6. Fail-safe, thực hiện thủ công và luôn bật lại worker:

```bash
sudo systemctl stop pbl4-ai-shadow.service
curl --noproxy '*' --connect-timeout 3 --max-time 8 -i http://192.168.10.1/api/auth/me
# Lặp probe SQLi ở trên, kiểm tra rule NGINX vẫn sinh cảnh báo.
sudo systemctl start pbl4-ai-shadow.service
python3 security-web/scripts/verify-ai-shadow-host.py
```

NGINX có thể ghi lỗi gửi socket trong lúc worker dừng; HTTP phải vẫn tới VM. Sau restart Rust, kiểm tra không tăng số kết quả cho cùng event cũ (unique event_id + checkpoint hiện có). Kiểm tra Dashboard/RELP/Suricata vẫn cập nhật độc lập. Không sửa DB để ép test pass.

Sau reboot do người dùng tự thực hiện: vmnet2/vmnet3 có IP, NGINX active, AI service enabled/active và heartbeat READY mới, Rust được khởi động theo cơ chế hiện có, chạy lại verifier và kiểm tra API. Bộ cài không tạo autostart Rust và không tự reboot.

## Rollback

Dùng đúng thư mục backup được installer in ra; không chọn một bản ngẫu nhiên:

```bash
sudo python3 security-web/scripts/install-ai-shadow-host.py \
  --rollback /var/backups/pbl4-ai-shadow/THAY_BANG_TIMESTAMP_DA_IN
```

Rollback kiểm tra file chưa bị sửa tiếp, khôi phục unit/NGINX/.env đã backup, `nginx -t` rồi reload; khôi phục trạng thái service trước cài. Restart Rust thủ công để đọc `.env` cũ. Không xóa journal/model snapshot, DB, checkpoint, RELP hay log VM. Nếu file đã thay đổi sau cài, script dừng để review, không ghi đè.
