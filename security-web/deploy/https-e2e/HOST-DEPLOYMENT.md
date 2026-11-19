> Cập nhật phạm vi: AI Worker là **DEFERRED**, không chặn HTTPS/Suricata.
> Dùng `--ai-mode deferred`; xem [AI-DEFERRED.md](AI-DEFERRED.md). Các yêu cầu
> phục hồi AI baseline bên dưới thuộc checklist cũ, chỉ áp dụng khi bật AI lại.

# Security Host — bundle triển khai có kiểm soát (chờ phê duyệt)

Người vận hành báo candidate Live E2E 15/15 PASS, 72 transactions, pending [],
SHA256 c74cfc07bc6425f537dd0bc5c67f4eb27debc9b62b9cc4a2af23a43305b7df18.
Đây là hash cấu hình tạm của harness, không phải hash bundle production.
Installer/supervisor mới chưa được nghiệm thu với systemd/nftables đặc quyền.
Không suy ra production-ready hoặc Client IP Verified từ kết quả trên.

## Thành phần và ranh giới

- `stage-proof-host.py`: tái sử dụng renderer proof và Suricata local-egress; xuất
  bundle và SHA256, không ghi /etc, không tạo khóa/account hay cài module.
- `deploy-proof-host.py`: preflight/dry-run; snapshot các file sẽ thay; dừng dịch vụ;
  cài bundle; kiểm tra unit hiệu lực, nginx -t, suricata -T; start và health.
  Lỗi sau snapshot sẽ restore file, daemon-reload và khôi phục trạng thái active cũ.
  Rollback lỗi được báo riêng, không được xem là đã phục hồi thành công.
- `proof-nginx-lifecycle.py`: chạy trong chính nginx.service, không thêm NGINX
  instance hoặc service song song. Dùng lại Guard hiện có. Root quản lý khóa;
  worker UID/GID `websentinel-edge` riêng, không supplementary groups.
- Mỗi start đổi key/epoch trước khi nhận request. Không backup/khôi phục khóa cũ.
  Supervisor kiểm tra key/guard/process mỗi 0,5 giây; lỗi sẽ revoke và dừng master.
  Readiness có timestamp, luôn client_ip_verified=false. Polling không loại bỏ
  khoảng hở trước phát hiện; HMAC Egress là lớp từ chối request giả độc lập.
- ExecReload bị vô hiệu; dùng restart có downtime và rotation. Restart=no: crash
  không tự hồi phục. KillMode=control-group dọn worker khi service dừng.
- Nếu supervisor bị SIGKILL: chỉ nhận lại deny-only snapshot đã ghi hợp lệ. Policy
  allow còn sót hoặc policy lạ khiến startup từ chối, cần người vận hành kiểm tra.
- Cùng UID NGINX, root hoặc quyền đọc khóa bị xâm phạm nằm ngoài bảo đảm chống
  tiến trình không đặc quyền. Chmod/cgroup không giải quyết compromise cùng UID.

## Phần giữ nguyên và phần CHƯA có

Student VM không được truy cập/sửa bởi staging: giữ HTTP80/HTTPS443. Candidate
upstream `https://192.168.20.10:443`, `proxy_ssl_name student.lab`, verify on, public
CA từ `~/ws-student-trust/ca.crt`. Không dùng verify off hoặc curl -k.
Edge Protection, proof/receipt, telemetry và SID dùng code đã có. Giữ file YAML
vmnet3 và drop-in cũ; drop-in local-egress mới tên 99 để đứng sau bản 90 cũ.
Không thay Rust/DB/Dashboard/AUTO_BLOCK. Operator phải xác nhận runtime đang OFF.

Lua evidence generation và Rust Shadow ingestion production chưa được nối trong
installer này. Local-egress YAML giữ output/rules từ base; không tự gắn logger Lua
fixture (chưa có lifecycle sensor generation đủ tin cậy). Alert EVE vẫn hoạt động,
Client IP local-egress vẫn Unverified. Timing HMAC, journal rollback/revocation và
response completeness vẫn là điều kiện chưa nghiệm thu.

## Chuẩn bị cần duyệt trước

1. Duyệt tài khoản/group độc quyền `websentinel-edge`, shell nologin; không dùng
   UID của www-data/nobody. Không có tiến trình khác chạy UID/GID này.
2. Duyệt cài njs tương thích ABI NGINX; module ở đường dẫn ổn định root-owned,
   không dùng bản /tmp cho production. Không load trùng modules-enabled.
3. Duyệt quyền log/cache/temp/AI Unix socket cho UID mới. Tool không chmod các
   thư mục đó, không tự thêm supplementary group. Kiểm tra mọi site dùng NGINX.
4. Xác nhận public CA Student và CA Edge; certificate/key Edge có sẵn, đúng SAN.
5. Rà soát unit hiện tại: capabilities, User, AppArmor, sandbox, ExecStartPre và
   ExecStartPost. Drop-in mới bỏ các hooks này để rotation diễn ra trước syntax
   test; mọi hook cần giữ phải được đưa vào bản review. Suricata unit phải hỗ trợ
   Type=forking hiện tại với -D. Kiểm tra effective ExecStart không bị override.
6. Cần nghiệm thu supervisor + installer trong VM/namespace thử nghiệm có systemd
   và snapshot, bao gồm SIGKILL supervisor, stale policy, reboot, AI socket permission,
   rollback service lỗi. Unit tests mock chưa chứng minh các mục này.

## Lệnh staging và kiểm tra (không sudo)

Sau khi các prerequisite được chuẩn bị/duyệt; thay đường dẫn Edge cho đúng máy:

```bash
# Chạy tại root repository. Đây là ví dụ đường dẫn; phải đối chiếu thực tế.
export EDGE_CERT=/etc/nginx/pbl4-tls/lab.crt
export EDGE_KEY=/etc/nginx/pbl4-tls/lab.key
export EDGE_CA=/duong/dan/public-edge-ca.crt
export NJS_MODULE=/usr/lib/nginx/modules/ngx_http_js_module.so
export EDGE_GID="$(getent group websentinel-edge | cut -d: -f3)"

python3 security-web/scripts/stage-proof-host.py \
  --output /tmp/ws-host-bundle-review \
  --suricata-base /etc/suricata/pbl4/post-proxy.yaml \
  --student-ca "$HOME/ws-student-trust/ca.crt" \
  --edge-ca "$EDGE_CA" --edge-cert "$EDGE_CERT" --edge-key "$EDGE_KEY" \
  --module "$NJS_MODULE" --gid "$EDGE_GID"

python3 security-web/scripts/deploy-proof-host.py dry-run \
  --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-before-c
python3 security-web/scripts/deploy-proof-host.py preflight \
  --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-before-c
```

Dry-run chỉ xác nhận bundle/plan, không phải host readiness. Preflight kiểm tra
identity, module có mặt, CA còn hạn, cgroup v2 và đường dẫn. Quyền đọc thiếu sẽ FAIL;
không tự nâng quyền. preflight chưa thay thế nginx -t/suricata -T với config cài đặt.
Không stage khi output đã tồn tại; tạo thư mục tên mới để tránh ghi đè bản review.

## Apply và rollback — CHỈ sau phê duyệt, chưa chạy

Bundle áp dụng và mọi ancestor phải root-owned, không group/world writable. Người
vận hành chuyển bản đã duyệt sang `/root/ws-host-bundle-approved`, kiểm tra lại
SHA256/ownership; không chạy privileged từ bundle còn sửa được bởi user thường.
Đường dẫn backup phải mới, parent root-owned. Các bước tạo UID/cài module/copy
bundle là phê duyệt riêng, script không thực hiện thay.

```bash
sudo python3 security-web/scripts/deploy-proof-host.py apply \
  --bundle /root/ws-host-bundle-approved \
  --backup /var/backups/ws-proof-before-c --approve-host-change

sudo python3 security-web/scripts/deploy-proof-host.py health \
  --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before-c

sudo python3 security-web/scripts/deploy-proof-host.py rollback \
  --bundle /root/ws-host-bundle-approved \
  --backup /var/backups/ws-proof-before-c --approve-host-change
```

Health hiện kiểm tra services active, heartbeat guard mới, FE200/API401 bằng CA
Edge. Sau đó người vận hành nghiệm thu assets/login/Application Audit, request ID,
SID và AI telemetry; health HTTP không thay thế nghiệm thu các detector.
Apply dừng NGINX/Suricata trong cửa sổ thay đổi, có downtime. HTTP80 Edge cũng đi qua
Egress; fallback là khôi phục site cũ -> HTTP Student80, không phải tự chuyển tuyến.
Rollback giữ nguyên TLS Student443/HTTP80, không rollback DB/audit. Bảng deny-only
chuyên biệt được giữ lại; không flush firewall. Nếu service cũ không start được,
script báo rollback failure và cần xử lý thủ công, không báo thành công giả.

Nếu supervisor crash để lại policy allow: dừng nginx.service, xác nhận không còn
master/worker/listener 18080; đối chiếu đúng bảng `inet pbl4_local_egress` với backup.
Chỉ khi xác nhận bảng thuộc deployment này mới xóa riêng bảng đó rồi start lại để
rotation mới. Không tự động xóa policy lạ và không khôi phục key cũ.

## Bước Rust Shadow sau này

Tách kết quả shadow khỏi attribution hiện tại; ingest chọn lọc proof/receipt với
sensor generation + flow_id + tx_id, không ghép chỉ request ID. Chưa được triển khai
logger fixture vào production. Cần lưu journal bền vững/chống rollback, cơ chế
revocation và nguồn xác nhận response hoàn chỉnh. Alert thiếu bằng chứng vẫn giữ
Unverified; không kích hoạt block và không đánh đồng guard snapshot với event-time
trust. Không chuyển bước này tự động sau apply.
