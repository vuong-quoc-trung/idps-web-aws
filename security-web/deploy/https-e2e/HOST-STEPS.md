# HTTPS Host — thứ tự thực hiện cần operator duyệt

AI DEFERRED; không cài hook ACL AI, không start AI. Không VM mới. Chỉ operator chạy
các bước có sudo; tài liệu không phải xác nhận đã triển khai. Cần console/local
terminal để rollback khi HTTP gián đoạn. Giữ AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF.

## 0. Snapshot và baseline — dừng nếu lỗi

```bash
sudo bash security-web/scripts/backup-security-host.sh /var/backups/ws-prereq-before
systemctl is-active nginx suricata
bash student-web/deploy/tls/verify-from-defender.sh "$HOME/ws-student-trust/ca.crt" student.lab
sudo nginx -T
sudo nft list ruleset
```

Backup COMPLETE/checksum hợp lệ; FE200/API401, wrongCA/SAN refused. Không cần AI.
Ghi lại package/module/account trước thay đổi. Các đường dẫn đích dưới đây phải chưa
có, nếu đã có DỪNG và review; không ghi đè module/account hiện có.

## 1. Module riêng, không package maintainer reload

Theo PREREQUISITES.md tải package 0.9.4-1build2 từ kho đã xác thực, giải nén tại
$HOME/ws-njs-staging. Không `dpkg -i` tự động; không auto-enable modules-enabled.

```bash
python3 security-web/scripts/check-njs-abi.py --module "$HOME/ws-njs-staging/extracted/usr/lib/nginx/modules/ngx_http_js_module.so"
sudo test ! -e /usr/local/lib/nginx/modules/ngx_http_js_module.so
# Chỉ tiếp tục nếu test vừa rồi exit0; không chạy cả block bỏ qua lỗi.
sudo install -d -o root -g root -m 0755 /usr/local/lib/nginx/modules
sudo install -o root -g root -m 0644 "$HOME/ws-njs-staging/extracted/usr/lib/nginx/modules/ngx_http_js_module.so" /usr/local/lib/nginx/modules/ngx_http_js_module.so
python3 security-web/scripts/check-njs-abi.py --module /usr/local/lib/nginx/modules/ngx_http_js_module.so
sha256sum "$HOME/ws-njs-staging/extracted/usr/lib/nginx/modules/ngx_http_js_module.so" /usr/local/lib/nginx/modules/ngx_http_js_module.so
systemctl is-active nginx suricata
```

Health: ABI PASS, hai hash giống, service cũ không đổi. Dừng nếu bất kỳ lỗi nào.
Rollback: chỉ tháo file mới sau khi khôi phục config và chắc chắn không process maps,
nginx includes hoặc service nào dùng; hash phải đúng bản vừa cài. Nếu chưa chắc giữ
file root-owned bất hoạt và ghi RETAINED_FOR_REVIEW, không xóa module dùng chung.

## 2. Identity và quyền — không chown đệ quy

```bash
getent passwd websentinel-edge
getent group websentinel-edge
# Hai lệnh không tìm thấy mới tạo; nếu tìm thấy phải review thay vì sửa:
sudo groupadd --system websentinel-edge
sudo useradd --system --gid websentinel-edge --no-create-home --shell /usr/sbin/nologin websentinel-edge
id websentinel-edge
```

Không supplementary groups. Supervisor tạo key root:dedicated-group0640 trong
parent0750 và rotate mỗi start; không tạo/copy khóa bằng tay. Master root đọc
cert/key TLS; module/config/site phải readable nhưng không writable bởi worker.

Từ `sudo nginx -T` lập danh sách thật `root/alias`, client_body_temp_path,
proxy_temp_path/cache. `nginx -V` cho đường dẫn temp mặc định nếu không khai báo.
Với TỪNG path đã duyệt, backup ACL rồi cấp tối thiểu, không chạy với placeholder:

```bash
sudo getfacl -p /PATH_DA_DUYET > acl-before.txt
sudo setfacl -m u:websentinel-edge:rwx /TEMP_HOAC_CACHE_DA_DUYET
sudo setfacl -m u:websentinel-edge:r-x /STATIC_DIRECTORY_DA_DUYET
sudo getfacl -p /PATH_DA_DUYET
```

Cần traverse parent và đọc file static; không cấp write static/source/private key.
Không cấp ACL rộng cho /home. Backup ACL mỗi path ở tên riêng; default ACL chỉ dùng
nếu có yêu cầu file mới và đã review. Log do master mở; kiểm tra logrotate/reopen
không mặc định worker cần sở hữu toàn bộ /var/log/nginx. Quyền site chưa nghiệm thu
vẫn BLOCKED; không tự chọn tất cả paths để sửa.
Rollback ACL bằng `sudo setfacl --restore=acl-before.txt` tương ứng. Không tự userdel:
kiểm tra process/file/service/ACL references trước; nếu còn sử dụng giữ account
nologin và báo retained. Không restore /etc/passwd/group nguyên file từ tar.

## 3. Public Edge CA và bundle thật

Student CA đã có. Đọc public Edge cert (không private key):

```bash
sudo openssl x509 -in /etc/nginx/pbl4-tls/lab.crt -noout -subject -issuer -ext subjectAltName
```

Nếu cert tự ký, có thể xuất public trust anchor sau kiểm tra:

```bash
mkdir -m 700 "$HOME/ws-edge-trust"
sudo openssl x509 -in /etc/nginx/pbl4-tls/lab.crt -outform PEM > "$HOME/ws-edge-trust/ca.crt"
```

Nếu CA-signed phải lấy public CA đúng, không mặc định leaf là CA. Xác minh trước:

```bash
curl --noproxy '*' --cacert "$HOME/ws-edge-trust/ca.crt" --max-time 10 https://192.168.10.1/api/auth/me -o /dev/null -w '%{http_code}\n'
python3 security-web/scripts/stage-current-proof-host.py \
 --edge-ca "$HOME/ws-edge-trust/ca.crt" --output /tmp/ws-host-bundle-deferred
```

Helper dùng đúng UID/GID đã tạo, Student CA thật và module stable, chạy ABI, staging,
preflight/dry-run. Không start service hay sinh key. Thiếu input trả BLOCKED exit2,
không tạo partial bundle. Review diff, hashes và ai_worker=DEFERRED. Syntax/full
runtime checks đặc quyền vẫn chưa thay thế bởi dry-run.

## 4. Cửa sổ apply — chỉ sau approval và quyền site đã nghiệm thu

Chuyển bundle đã review sang /root/ws-host-bundle-approved, root:root, không cho user
thường sửa; kiểm tra lại SHA256. Không cấp root chạy bundle chưa review.

```bash
sudo python3 security-web/scripts/deploy-proof-host.py apply --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
sudo python3 security-web/scripts/deploy-proof-host.py health --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before
```

NGINX dừng/start với rotation/guard; checkpoint HTTP+HTTPS trước chuyển Suricata.
Lỗi tự rollback target config. Có downtime, khoảng trống sensor khi đổi đường đi.
Nghiệm thu thêm login/assets/Audit/Dashboard/SID/EVE local-egress riêng; không bật
Verified. Lua/Rust Shadow runtime chưa triển khai. Không xem HTTP health là SID PASS.

## 5. Rollback

```bash
sudo python3 security-web/scripts/deploy-proof-host.py rollback --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-before --approve-host-change
sudo nginx -t
systemctl is-active nginx suricata
```

Khôi phục site cũ -> Student80 và sensor vmnet3, không sửa Student443. Rollback cũ
có thể phục hồi dòng AI syslog cũ; không tự start AI. Sau đó restore ACL prerequisite,
tháo module/account chỉ khi không còn tham chiếu. Không flush firewall hoặc nạp
nguyên nft snapshot; chỉ review bảng pbl4_local_egress sau khi listener18080 đóng.
Giữ deny-only nếu chưa rõ. Không restore HMAC key/epoch cũ. Nếu rollback thất bại,
giữ candidate dừng, kiểm tra log, không báo đã phục hồi.

## Trạng thái ở lần chuẩn bị này

Core checkpoint tests PASS, ABI test bản test PASS; AI DEFERRED. Account, module
production và public Edge CA readable còn thiếu, helper hiện trả BLOCKED. Chưa tạo
bundle production đầy đủ, chưa chạy privileged lifecycle. Đây là ranh giới quyền
operator, không thể giải quyết bằng GID/CA giả. Không thay cấu hình đã PASS ngoài
helper/ tài liệu; không commit/push.
