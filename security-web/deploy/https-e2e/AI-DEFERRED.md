# Đợt triển khai hiện tại: AI Worker DEFERRED

Quyết định của người vận hành thay thế các checklist cũ yêu cầu phục hồi AI trước
HTTPS: AI chưa hoàn thiện, không phải incident cần sửa. Không sửa/start AI service.
Ưu tiên HTTPS End-to-End + Suricata passive; Rust Shadow và AI tích hợp sau.

## Chế độ cấu hình

`--ai-mode deferred` trên prepare-proof-egress.py và stage-proof-host.py comment
đúng một access_log syslog AI; giữ nguyên đường socket và dòng cấu hình để review,
giữ log format/map AI, JSON access log NGINX, Request ID, XFF và HMAC. Không tạo
telemetry thay thế, không gửi vào file giả production, không yêu cầu socket tồn tại.
Manifest ghi ai_worker=DEFERRED. Validator kiểm tra manifest khớp active sink; thiếu
TLS/HMAC hoặc chế độ mâu thuẫn vẫn FAIL. Enabled mặc định giữ tương thích harness cũ.

HTTP/HTTPS không cần AI. Suricata capture HTTP lo và Application Audit không đổi.
Trong thời gian deferred KHÔNG có telemetry mới từ NGINX tới AI; không có cam kết
inference/score mới. Dashboard có thể giữ dữ liệu cũ, không được gọi là AI READY.
Không xem AI telemetry unique của harness cũ là nghiệm thu AI production.

## Tạo bundle sau khi prerequisite cốt lõi được duyệt

UID/GID thật, module njs ABI đúng ở path root-owned ổn định, quyền site/log/temp,
Edge CA/cert/key và Student CA vẫn bắt buộc. Chưa tạo account/module/khóa production.
Lệnh staging không sudo, không sửa runtime (điền public Edge CA thực tế):

```bash
python3 security-web/scripts/stage-proof-host.py \
 --output /tmp/ws-host-bundle-deferred \
 --suricata-base /etc/suricata/pbl4/post-proxy.yaml \
 --student-ca "$HOME/ws-student-trust/ca.crt" \
 --edge-ca /duong/dan/public-edge-ca.crt \
 --edge-cert /etc/nginx/pbl4-tls/lab.crt \
 --edge-key /etc/nginx/pbl4-tls/lab.key \
 --module /usr/local/lib/nginx/modules/ngx_http_js_module.so \
 --gid "$(getent group websentinel-edge | cut -d: -f3)" \
 --ai-mode deferred

python3 security-web/scripts/deploy-proof-host.py preflight \
 --bundle /tmp/ws-host-bundle-deferred --backup /var/backups/ws-proof-before
python3 security-web/scripts/deploy-proof-host.py dry-run \
 --bundle /tmp/ws-host-bundle-deferred --backup /var/backups/ws-proof-before
```

Preflight/deploy không truy vấn hoặc đòi AI active. Tuy nhiên không bỏ qua identity,
module, CA, cgroup hay ownership vì AI deferred. Bundle production hoàn chỉnh chưa
được sinh khi thiếu GID thật/public Edge CA; không dùng giá trị giả để báo PASS.

## Sau phê duyệt riêng

Chạy backup-security-host.sh như tài liệu prerequisites. Review và chuyển bundle
sang /root/ws-host-bundle-approved, root-owned. Không cài ACL/helper AI ở đợt này.

```bash
sudo python3 security-web/scripts/deploy-proof-host.py apply \
 --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
sudo python3 security-web/scripts/deploy-proof-host.py rollback \
 --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
```

Apply vẫn có downtime; HTTP/HTTPS checkpoint trước chuyển Suricata, lỗi rollback.
Rollback khôi phục site cũ nguyên trạng, kể cả dòng gửi AI vốn có trong backup;
không tự start AI. Nếu muốn rollback site cũ nhưng vẫn deferred, cần review một
candidate rollback riêng, không âm thầm sửa backup. Module/account prerequisites
rollback có review, giữ lại nếu nơi khác dùng; không flush nftables.

## Bật lại AI sau này

Nghiệm thu worker/ACL/socket restart theo PREREQUISITES.md, tạo bundle mới với
`--ai-mode enabled`, review diff chỉ mode và metadata mong muốn, syntax/runtime test,
apply có rotation/guard như bình thường. Không uncomment runtime thủ công hoặc
reload bỏ qua supervisor. Xác nhận telemetry thật một request ID một record và
inference thật riêng; không cần thiết kế lại Edge/Egress/Suricata.
Verified/AUTO_BLOCK vẫn tắt. VM/systemd privileged acceptance chưa chạy giữ NOT_RUN.
