# Adaptive Prevention trên ws-i5-dev

## Phạm vi

Rust đánh giá bằng chứng đã ingest theo policy ở [HYBRID-REVIEW](../HYBRID-REVIEW.md). NGINX và R37 thường thấy cùng payload. Suricata phải khớp sensor/flow/transaction, Student Audit phải có quyết định phía server. Một rule standalone đã duyệt đủ mạnh có thể đủ điều kiện. Bằng chứng xảy ra sau request chỉ được dùng cho phiên hoặc hành động tương lai. Shared IP, relay hoặc chưa rõ danh tính luôn giữ ở REVIEW khi xét IP.

**BLOCK_REQUEST** có gate Rust UDS và auth_request trước proxy cho đúng path canary. Selector do NGINX ghi đè; chỉ một lease do operator cấp, tối đa 120 s. Mất gate hoặc timeout trả 5xx trên canary; path bình thường vẫn dùng Edge Protection cũ. R37 giữ nguyên bất đồng bộ. Gate là phép nghiệm thu quyết định trước upstream; chưa có cache selector tổng quát được cấp từ một incident. Không dùng request ID đã kết thúc để hồi tố, và không đưa hook này vào tất cả location.

**BLOCK_SESSION** là đề xuất sau quan sát. Dùng HMAC của principal + session do Student ký và rule quyết định ứng dụng; loại username nộp khi đăng nhập sai. CLI Rust chỉ đọc DB theo request ID để xuất plan, cần operator duyệt một lease. Student kiểm lease mỗi request của đúng phiên đăng nhập và gọi Spring Security logout. Phiên đã hủy yêu cầu đăng nhập lại; sau TTL hoặc gỡ lease không tiếp tục thu hồi. Không khóa tài khoản. Trường hợp hai principal/session cho cùng ID bị từ chối khi xuất plan. Thư mục root-owned, Student có quyền đọc và không có quyền xuất bản. Không dùng selector làm cookie, không gửi plan lên Dashboard.

**BLOCK_IP** giữ actuator hiện có, TTL 1–300s, protected IP, cooldown, audit và khóa C2. Nghiệm thu trực tiếp dùng namespace riêng theo hướng dẫn ở thư mục cha. Một IP public cũng có thể là NAT của nhiều người: luôn REVIEW cho đến khi biết phạm vi ảnh hưởng. Chính sách hệ thống đang chạy không cấp quyền chặn tùy ý IP public hoặc private.

## Test có thể lặp lại

Từ repository:

```bash
(cd security-web && cargo build --locked --features dev-hybrid-review)
python3 -B security-web/deploy/dev-i5/adaptive/test_edge.py security-web/target/debug/pbl4-security-demo
(cd student-web/backend && ./mvnw -Dtest=DevSessionLeaseHttpTests,StudentApiTests test)
```

Rust/NGINX dùng cổng loopback cao tự chọn và upstream đếm request; Spring mở Tomcat trên loopback, H2 riêng, hai session thật cùng tài khoản. PostgreSQL regression phải chỉ định DATABASE_URL của cluster test riêng. Kiểm tra toàn bộ bằng `cargo test --locked --features dev-hybrid-review`. Lặp bài nftables và kiểm đếm packet theo [harness namespace](../HYBRID-REVIEW.md). Không chạy trực tiếp helper trong namespace Host hay namespace đang phục vụ.

## Staging sau khi duyệt

Hai ứng dụng là artifact **development**. Kiểm tra backup/restore dữ liệu guest trước khi thay binary: Rust gọi SQLx migrate khi start, Student có Flyway. Chỉ thay khi toàn bộ migration/checksum của nhánh đúng với guest; nếu có pending, dừng. Sao lưu bằng `manage.py backup` và `restore-test` của profile hiện có. Việc restart Student làm mất session đang dùng. Tạo cửa sổ demo riêng.

1. Build và chép artifact vào guest. Các lệnh trên Host, từ root repo, yêu cầu Java 25, Rust, Maven và systemd-container. JAR dùng bên dưới là JAR thin từ classes đã biên dịch để phù hợp classpath của unit Beta. So sánh dependency và unit với bản đã cài trước khi tiếp tục.

```bash
set -e
(cd security-web && cargo build --release --locked --features dev-hybrid-review)
(cd student-web/backend && ./mvnw -DskipTests compile)
stage=$(mktemp -d)
install -m 0755 security-web/target/release/pbl4-security-demo "$stage/"
jar --create --file "$stage/student-dev.jar" -C student-web/backend/target/classes .
install -m 0644 security-web/deploy/dev-i5/adaptive/approve_session.py "$stage/"
(cd "$stage" && sha256sum pbl4-security-demo student-dev.jar approve_session.py > SHA256SUMS)
sudo machinectl copy-to ws-i5-dev "$stage" /root/ws/adaptive-stage
sudo machinectl shell root@ws-i5-dev /bin/bash
```

2. Trong guest, xác nhận tên máy, backup và unit. Các lệnh sau giả định đúng profile Beta, hai service đang active, và hai thư mục drop-in chưa có file 85-adaptive-dev.conf. Giữ bản phát hành cũ trên đĩa. Unit Student được tạo từ đúng dòng ExecStart cũ, thay riêng JAR.

```bash
set -eu
test "$(hostname)" = ws-i5-dev && test "$(cat /run/systemd/container)" = systemd-nspawn
cd /root/ws/adaptive-stage
sha256sum -c SHA256SUMS
bin=/opt/ws-adaptive-dev
test ! -e "$bin"
install -d -m 0755 "$bin"
install -m 0755 pbl4-security-demo "$bin/"
install -m 0644 student-dev.jar approve_session.py "$bin/"
test ! -e /etc/tmpfiles.d/ws-adaptive-dev.conf
printf '%s\n' 'd /run/ws-dev-session-leases 0750 root websentinel-evidence -' 'd /run/ws-dev-request-leases 0750 root websentinel-evidence -' >/etc/tmpfiles.d/ws-adaptive-dev.conf
systemd-tmpfiles --create /etc/tmpfiles.d/ws-adaptive-dev.conf
S=websentinel-beta-security.service
J=websentinel-beta-student.service
for u in "$S" "$J"; do systemctl is-active --quiet "$u"; systemctl cat "$u" > "/root/ws/adaptive-stage/$u.before"; done
start=$(systemctl cat "$J" | grep '^ExecStart=/usr/bin/java ')
test "$(printf '%s\n' "$start" | wc -l)" = 1
case "$start" in *'/opt/websentinel-beta/current/student/student.jar:'*) ;; *) exit 1;; esac
for u in "$S" "$J"; do test ! -e "/etc/systemd/system/$u.d/85-adaptive-dev.conf"; done
install -d "/etc/systemd/system/$S.d" "/etc/systemd/system/$J.d"
cat > "/etc/systemd/system/$S.d/85-adaptive-dev.conf" <<'UNIT'
[Service]
ExecStart=
ExecStart=/opt/ws-adaptive-dev/pbl4-security-demo
Environment=WS_DEV_HYBRID_MODE=REVIEW
Environment='WS_DEV_HYBRID_POLICY={"rules":[{"source":"STUDENT_AUDIT","rule":"APP-1013","weight":70,"standalone":false,"max_severity":2}],"combined":120,"standalone":95,"fresh_seconds":60,"r37_weight":55}'
UNIT
# Require that there was no pre-existing override of the active Spring profiles.
# Otherwise merge ws-i5-development with those profiles before proceeding.
( echo '[Service]'; echo 'Environment=SPRING_PROFILES_INCLUDE=ws-i5-development'; echo 'Environment=APP_DEV_SESSIONLEASEDIR=/run/ws-dev-session-leases'; echo 'ExecStart='; printf '%s\n' "${start/\/opt\/websentinel-beta\/current\/student\/student.jar/\/opt\/ws-adaptive-dev\/student-dev.jar}"; ) > "/etc/systemd/system/$J.d/85-adaptive-dev.conf"
systemctl daemon-reload
systemctl restart "$J" "$S"
cd /root/ws/profile && python3 -B manage.py health
```

tmpfiles.d tạo lại thư mục lease trống sau khi boot; session trong bộ nhớ cũng mất khi Student restart. Profile khởi động từ chối nếu cấu hình có đường dẫn sai. Sau health, tra request bình thường, kiểm FE/API và score R37, kiểm audit còn mới. Lệnh trên chỉ bật review và khả năng đọc lease; không cấp lease, không bật nftables. Ví dụ policy chỉ dùng APP-1013 và R37; tự duyệt danh mục rule riêng. Gate canary được chạy riêng bằng test_edge.py; chưa thêm vào site đang phục vụ.

3. Duyệt một incident trong guest. Operator chọn đúng loại hành động. Dispatcher chạy Rust dưới UID Security để đọc plan từ DB, kiểm tra selector, thời hạn, xung đột và ghi syslog theo request ID. Retry cùng plan đang hiệu lực không kéo dài TTL. Ví dụ dưới đây dành cho session.

```bash
read -r -p 'Request ID đã kiểm tra: ' rid
python3 /opt/ws-adaptive-dev/approve_session.py --approve "$rid" --action BLOCK_SESSION
```

Với listener canary đã được phê duyệt và kiểm tra, dùng cùng lệnh với `--action BLOCK_REQUEST`. Gate cần `WS_DEV_GATE_LEASE_DIR=/run/ws-dev-request-leases` chỉ đọc và `WS_DEV_GATE_DIR` riêng do UID gate sở hữu. Cấp quyền traverse thư mục socket và connect socket cho worker Edge, kiểm tra bằng đúng UID trước khi đưa listener vào phục vụ. Giữ khóa HMAC tách khỏi nhóm đọc lease. Request ID của incident cấp lease và ID từng request bị từ chối được ghi riêng. Chỉ include template ở test Edge với upstream canary riêng. Đường relay hiện tại luôn bị dispatcher từ chối với BLOCK_IP.

Thu hồi bằng cách chạy lại lệnh với cùng action và thêm `--revoke`. Thu hồi session đã logout yêu cầu người dùng đăng nhập lại. Lease mất khi reboot. Journal SQLite và audit nằm ở /var/lib/ws-adaptive-dev, do root sở hữu, tách khỏi /run. Quyết định đã tiêu thụ không thể cấp lease lần thứ hai khi file biến mất. Muốn chặn lại cần incident mới, Request ID mới và phê duyệt mới. Request đang xử lý trước khi revoke có thể đã qua gate. Chỉ duyệt thủ công trong cửa sổ thử nghiệm.

4. **Rollback** trong guest. Dừng cấp lease, gỡ đúng hai override đã tạo, khởi động lại hai unit về artifact gốc. Không phục hồi database khi chỉ rollback binary. Giữ backup kiểm tra cho tới khi nghiệm thu xong.

```bash
test "$(hostname)" = ws-i5-dev && test "$(cat /run/systemd/container)" = systemd-nspawn || exit 1
rm -f /etc/systemd/system/websentinel-beta-{security,student}.service.d/85-adaptive-dev.conf /etc/tmpfiles.d/ws-adaptive-dev.conf
systemctl daemon-reload
systemctl restart websentinel-beta-student websentinel-beta-security
cd /root/ws/profile && python3 -B manage.py health
```

## Demo LAN và nguồn IP

Tận dụng listener 10443 chỉ trên loopback Host đã mô tả trong README dev. Từ laptop khác, nếu Host có SSH đã được phép dùng và port forwarding được cho phép:

```bash
ssh -N -L 127.0.0.1:10443:127.0.0.1:10443 USER@HOST_LAN
# Terminal khác trên laptop đó, dùng CA công khai của guest
curl --cacert dev-ca.crt https://127.0.0.1:10443/api/auth/csrf
```

Cách này demo request/session từ LAN; không thể dùng để demo IP ban theo IP laptop. Kiểm tra IP nguồn trên kết nối SSH ở Host và peer tại Edge theo cùng thời điểm; đó là hai kết nối riêng. Đóng SSH hoàn nguyên port forward. Không tin XFF từ trình duyệt hoặc dùng IP relay làm target.

Để demo IP ban từ một laptop vật lý, phương án riêng là **USB Ethernet dành riêng cho guest**, cùng segment lab với laptop, không nối vmnet. Cần người vận hành xác nhận adapter và subnet chưa dùng, chuyển riêng adapter vào guest dev, bind một listener Edge mới vào địa chỉ guest với certificate SAN tương ứng; giữ 9443 loopback. Trước khi cho phép ban, cần đối chiếu địa chỉ do Edge quan sát với packet source tại hook input trong guest, kiểm chứng lease DHCP không thay đổi chủ thể, rồi loại trừ IP guest, gateway, proxy, quản trị, NAT/shared IP. Chỉ rollback listener và adapter thử nghiệm. Chưa có thông số adapter/địa chỉ và quyền triển khai LAN thật; không tự đổi network trên máy đang chạy.

Với hai laptop dùng cùng Wi-Fi, phương án kiểm tra peer trực tiếp là adapter Wi-Fi USB riêng cho guest, cùng SSID lab, AP cho phép hai client liên lạc trực tiếp. Giữ nguyên adapter quản trị của Host. Trước khi thử block, gửi một HTTPS canary bình thường và đối chiếu địa chỉ laptop với peer ở socket Edge và source ở hook input trong guest. Request ID liên kết access log với incident; địa chỉ IP và thời điểm riêng lẻ không chứng minh danh tính. Nếu qua relay, AP NAT, địa chỉ dùng chung hoặc thiếu thông tin đối chiếu, giữ BLOCK_IP ở REVIEW.

### Điều kiện staging canary độc lập

Chỉ staging listener thử nghiệm riêng sau khi đối chiếu SQLx/Flyway với candidate, xác nhận backup đã restore trên DB riêng và kiểm tra quyền gate bằng UID thật. Không dùng bước thay JAR hoặc restart Student ở trên cho canary request. Dừng publisher cũ và đợi hết TTL 120 giây trước chuyển đổi; giữ nguyên journal cũ khi nâng cấp. Chỉ khởi tạo **một lần cho lần cài đầu**, trên filesystem local bền vững trong guest, sau phê duyệt:

```bash
install -d -m 0700 -o root -g root /var/lib/ws-adaptive-dev
python3 /opt/ws-adaptive-dev/approve_session.py --init-journal
```

Không tạo lại DB nếu bị mất, hỏng, hoặc sau khi dừng khẩn cấp. Ngừng cấp lease, đối chiếu backup và audit trước khi quyết định phục hồi. Khôi phục snapshot cũ có thể làm mất tombstone. Sao lưu journal bằng SQLite backup API; không thay riêng file DB khi publisher đang hoạt động. Mọi đường cấp lease phải dùng duy nhất publisher mới.

Dừng khẩn cấp trong guest sau khi staging:
```bash
python3 /opt/ws-adaptive-dev/approve_session.py --emergency-stop
```
Lệnh khóa cấp mới trước khi rút các lease. Nếu bị ngắt hãy chạy lại; lease chưa rút vẫn chịu TTL. Không tự mở lại khi restart. Nếu rollback listener thì dừng listener canary riêng, giữ journal; không quay lại publisher cũ. BLOCK_IP bị từ chối vì topology relay chưa có danh tính peer tin cậy.

Kiểm tra chỉ đọc từ root checkout trên Host sau khi operator xác thực sudo:
`python3 -B security-web/deploy/dev-i5/adaptive/preflight_guest.py --backup /duong/dan/backup-trong-guest`.
Script so SQLx SHA-384 và Flyway CRC32 với source hiện tại. Đối chiếu kết quả restore riêng với cùng manifest trước cutover.

### Nghiệm thu song song với Rust REVIEW đang chạy

Dùng bundle chứa candidate Rust, student-dev.jar, guest-canary.sh, gate.conf.template,
test_edge.py và approve_session.py. Copy vào thư mục mới /opt/ws-adaptive-acceptance
trong guest, kiểm checksum, quyền root sở hữu và service chỉ đọc. Không cài đè
/opt/ws-rust-review. Lệnh dưới chạy từ Ubuntu Host sau khi operator cho phép.
Thay REQUEST_ID bằng incident mới, đủ điều kiện của Rust REVIEW (còn TTL);
không dùng ID của request đã kết thúc để tuyên bố request đó đã bị chặn.

```bash
sudo systemd-run -M ws-i5-dev --wait --collect --pipe --quiet \
  -p User=websentinel-security -p Group=websentinel-evidence -p PrivateTmp=yes \
  -p EnvironmentFile=/etc/websentinel-beta/security.env \
  -p WorkingDirectory=/opt/ws-adaptive-acceptance \
  /bin/bash ./guest-canary.sh REQUEST_ID
```

Scope chỉ gồm listener loopback TLS tạm, Rust gate, journal test và upstream đếm
request. Harness thu hồi lease, dừng các process thử và dọn thư mục khi kết thúc.
Dùng --fixture thay ID nếu chỉ test actuator; kết quả đó không nghiệm thu detector.
Chưa gắn listener này vào site thật. Không chạy rollback của cả hai unit ở phần
trên cho bài này. Chỉ dừng transient unit thử nếu cần hủy sớm.

### BLOCK_ACCOUNT (development, phê duyệt riêng)

Student phải được staging riêng với profile ws-i5-development và session lease dir.
Đặt APP_DEV_ACCOUNTLOCKS=true riêng cho lần nghiệm thu đã duyệt; mặc định false.
Trước khi restart Student, đối chiếu classpath, giữ bản gốc và lên lịch mất session.
Publisher và CLI cấp plan phải cùng bản có hỗ trợ BLOCK_ACCOUNT. Operator chọn
incident từ Student Audit đã liên kết duy nhất với principal và session được xác thực.
Plan account có selector HMAC riêng theo principal. Lease nằm cùng thư mục với
session, phân biệt bằng tiền tố account-. Security filter từ chối protected request
của tất cả phiên của đúng account, login hợp lệ mới bị từ chối sau xác thực.
Tài khoản không bị sửa trong DB. Phiên hiện hữu dùng lại được sau TTL hoặc unlock.

```bash
python3 /opt/ws-adaptive-dev/approve_session.py --action BLOCK_ACCOUNT --approve "$rid" --confirm-account-lock
python3 /opt/ws-adaptive-dev/approve_session.py --action BLOCK_ACCOUNT --approve "$rid" --revoke
```

Audit approval/revoke/expiry deadline nằm trong journal, tác động HTTP ghi decision ID
và request ID vào Student log khi có header từ Edge. Dừng tất cả cấp mới bằng
--emergency-stop. Nếu rollback Student, gỡ đúng override thử nghiệm của Student
rồi daemon-reload/restart riêng Student trong cửa sổ được duyệt. Giữ journal.
Không cấp account lock qua auto-policy. Không bật AUTO_BLOCK toàn cục hoặc ban IP relay.
