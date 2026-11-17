> Cập nhật phạm vi: AI Worker là **DEFERRED**, không chặn HTTPS/Suricata.
> Dùng `--ai-mode deferred`; xem [AI-DEFERRED.md](AI-DEFERRED.md). Các yêu cầu
> phục hồi AI baseline bên dưới thuộc checklist cũ, chỉ áp dụng khi bật AI lại.

# Prerequisites thực tế — chờ operator duyệt và chạy

Kết quả mới: NGINX/Suricata active; vmnet2=192.168.10.1, vmnet3=192.168.20.1.
AI Worker failed: phải phục hồi baseline AI trước chuyển UID, không tính telemetry
production PASS. nft list tables cần root, chưa xác minh. Không chạy sudo trong
phiên chuẩn bị. Không yêu cầu VM mới; các bài VM cũ vẫn NOT_RUN.

## 1. Backup và thứ tự rollback

Chạy backup-security-host.sh trước mọi prerequisite. Đã rà soát thêm từ chối
/var/backups symlink và bắt buộc getfacl. Backup chứa khóa TLS, phải root-only.
Không restore passwd/group từ tar; inventory chỉ để đối chiếu. Không flush ruleset.
Ghi lại đường dẫn backup và chỉ những file/ACL/account/module mới tạo vào nhật ký.
Rollback: site/services bằng deploy-proof-host.py trước; AI hook/ACL tiếp theo;
module/account cuối cùng, chỉ tháo khi xác minh không có người dùng khác.

## 2. Module: đường dẫn riêng ổn định, không cài package tự reload

Bản đã thử: libnginx-mod-http-js 0.9.4-1build2, dependency nginx-abi-1.28.3-1.
Nginx đang 1.28.3-2ubuntu1.12. check-njs-abi.py đã PASS load/import/shared dict với
binary hiện tại, không start daemon. Không chứng minh nguồn gốc package từ checksum
cục bộ: phải tải package qua kho Ubuntu đã xác thực, kiểm tra version/dependency.
Không dùng dpkg -i tự động vì maintainer scripts có thể reload và cài module stream.

Lệnh operator (sau duyệt; apt download không sudo, dùng thư mục chuẩn bị riêng):

```bash
mkdir -m 700 "$HOME/ws-njs-staging"
cd "$HOME/ws-njs-staging"
apt download libnginx-mod-http-js=0.9.4-1build2
dpkg-deb -f libnginx-mod-http-js_0.9.4-1build2_amd64.deb Package Version Depends
dpkg-deb -x libnginx-mod-http-js_0.9.4-1build2_amd64.deb extracted
# Tại root repo, test bản vừa tải, không module /tmp production:
python3 security-web/scripts/check-njs-abi.py \
 --module "$HOME/ws-njs-staging/extracted/usr/lib/nginx/modules/ngx_http_js_module.so"
# Không ghi đè nếu đích đã tồn tại; kiểm tra trước.
sudo install -d -m 0755 /usr/local/lib/nginx/modules
sudo install -o root -g root -m 0644 \
 "$HOME/ws-njs-staging/extracted/usr/lib/nginx/modules/ngx_http_js_module.so" \
 /usr/local/lib/nginx/modules/ngx_http_js_module.so
```

Không thêm modules-enabled: staging main config load đúng một lần. Ghi SHA256
source/dest. Re-run check-njs-abi.py với path cuối. Rollback restore bundle cũ trước;
kiểm tra nginx -T, mọi config include và /proc/*/maps không còn tham chiếu module.
Chỉ xóa file mới nếu không còn sử dụng và hash bằng bản đã cài; không apt remove
module/nginx của thành phần khác. Nếu không xác định được, giữ module bất hoạt và
báo RETAINED_FOR_REVIEW, không tuyên bố rollback prerequisite sạch hoàn toàn.

## 3. UID/GID và thư mục

```bash
getent passwd websentinel-edge
getent group websentinel-edge
# CHỈ tạo nếu cả hai chưa có; không thay account sẵn có:
sudo groupadd --system websentinel-edge
sudo useradd --system --gid websentinel-edge --no-create-home \
 --shell /usr/sbin/nologin websentinel-edge
id websentinel-edge
```

Không supplementary groups. HMAC parent root:group0750, file0640 do supervisor
rotation tạo, không tạo key trước bằng tay. Module/site/config root-owned readable;
master root đọc TLS private key, không mở quyền private key cho tất cả worker.
Không chown -R /var/log hoặc /var/lib. Lấy nginx -T xác định từng client_body_temp,
proxy_temp/cache và root/alias thực tế; backup getfacl từng path trước sửa. Cấp ACL
đúng nhu cầu UID mới tại những path đã duyệt, kiểm tra mask và traverse các parent.
Log master mở và logrotate reopen phải kiểm tra; không mặc định worker cần sở hữu
mọi log. Thiếu quyền bất kỳ site nào giữ BLOCKED.

Rollback không tự userdel/groupdel: kiểm tra ps UID, process group, file ownership,
ACL numeric UID, service/config references; khi không đủ bằng chứng thì giữ account
nologin/locked không process. Không tái sử dụng UID. Chỉ xóa account mới tạo khi
operator xác nhận không còn tham chiếu; không xóa account/module dùng chung.

## 4. AI socket: ACL named UID, không chia sẻ HMAC group

Helper prepare-ai-socket-acl.py chạy bằng CHÍNH user AI trong ExecStartPre, không
root. Nó cấp traverse cho UID websentinel-edge và default ACL write trên socket;
giữ group www-data, socket-mode620. Test temp thật PASS qua rebind/chmod, nhưng
AI service thật đang failed, chưa nghiệm thu service restart/hardening/telemetry.
Không đổi AI Group sang websentinel-edge và không thêm AI vào HMAC group.

Sau backup và phục hồi AI baseline, operator cài helper root-owned:

```bash
sudo install -d -m 0755 /usr/local/lib/websentinel
sudo install -o root -g root -m 0644 security-web/scripts/prepare-ai-socket-acl.py \
 /usr/local/lib/websentinel/prepare-ai-socket-acl.py
```

Chuẩn bị drop-in `/etc/systemd/system/pbl4-ai-shadow.service.d/90-edge-socket-acl.conf`
(chưa được tạo trên Host):

```ini
[Service]
ExecStartPre=/usr/bin/python3 /usr/local/lib/websentinel/prepare-ai-socket-acl.py
```

Review unit effective và existing hooks, sau đó operator daemon-reload/restart AI
(trong cửa sổ được duyệt). RuntimeDirectory được tạo trước ExecStartPre, default ACL
được đặt lại mỗi service start, socket rebind kế thừa. Nếu helper lỗi, start phải
FAIL. Kiểm tra `getfacl -n` directory/socket, effective named UID write, AI READY và
request ID mới có telemetry/inference. Thử restart AI rồi kiểm tra lại trước deploy.
Rollback: stop AI, restore/remove CHỈ drop-in/helper mới và ACL snapshot, daemon-reload,
start lại theo trạng thái trước; RuntimeDirectory mới trở lại mode0710 www-data.
Nếu không stop/recreate directory, phải `setfacl --restore=<snapshot>` (bao gồm default
ACL), không chỉ xóa named entry. Không giữ default ACL ngoài ý muốn. Không xóa helper
nếu có unit khác tham chiếu. Account AI không được đọc HMAC key.

## 5. Bundle/checkpoint/rollback

stage-proof-host.py dùng GID THẬT, stable module path ở trên, public Student CA
~/ws-student-trust/ca.crt và Edge CA thật. Không dùng GID giả/CA Student thay Edge.
Preflight/dry-run thật vẫn BLOCKED khi chưa tạo account/cài module và lấy Edge CA.
Không thể hoàn thành các điều kiện này bằng chỉ đọc; operator phải duyệt prerequisite.

Installer đã sửa: giữ Suricata process cũ, start NGINX -> chờ guard mới + HTTP/HTTPS
FE200/API401 -> mới stop/start Suricata lo -> health tổng. Test checkpoint lỗi kích
hoạt rollback và chứng minh chưa stop/start Suricata trước checkpoint. Vẫn có khoảng
trống quan sát khi đường NGINX đổi trước capture; không tuyên bố zero downtime.

```bash
python3 security-web/scripts/deploy-proof-host.py preflight \
 --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-before
python3 security-web/scripts/deploy-proof-host.py dry-run \
 --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-before
# Chỉ sau phê duyệt, bundle root-owned và baseline AI/TLS hợp lệ:
sudo python3 security-web/scripts/deploy-proof-host.py apply \
 --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
sudo python3 security-web/scripts/deploy-proof-host.py rollback \
 --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
```

Rollback installer khôi phục target files/service, nhưng prerequisite thủ công phải
rollback theo mục 2–4. Không có auto-rollback module/account an toàn khi chưa chứng
minh độc quyền; không báo đã tự phục hồi toàn bộ prerequisites. nftables chỉ quản lý
bảng riêng; deny-only còn lại giữ cho đến khi listener18080 đóng và không còn phụ
thuộc. Chỉ xóa bảng đã xác minh thuộc deployment, không restore/flush firewall chung.
Giữ AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF, loopback Unverified. Không sửa Student,
Rust, Audit hoặc Dashboard. Không coi bài VM chưa chạy là PASS.
