> Cập nhật phạm vi: AI Worker là **DEFERRED**, không chặn HTTPS/Suricata.
> Dùng `--ai-mode deferred`; xem [AI-DEFERRED.md](AI-DEFERRED.md). Các yêu cầu
> phục hồi AI baseline bên dưới thuộc checklist cũ, chỉ áp dụng khi bật AI lại.

# Security Host thật — khảo sát, kế hoạch và điểm dừng

Không dùng `test-proof-host-vm.py` trên Host. Người vận hành bỏ bước VM riêng;
16 case VM vẫn NOT_RUN. Live E2E 15/15 là bằng chứng candidate, không chứng nhận
installer/supervisor với systemd production. Chưa cho phép apply ở lần khảo sát này.

## Kết quả chỉ đọc

| Hạng mục | Kết quả |
|---|---|
| Nhánh | feature/https-end-to-end; còn thay đổi chưa commit được giữ nguyên |
| Binary | NGINX 1.28.3, Suricata 8.0.3 |
| Site trên đĩa | Edge 192.168.10.1:80/443 -> HTTP 192.168.20.10:80; chưa Local Egress |
| Edge Protection | rate/connection/body/timeouts, request ID/XFF và AI syslog còn trong site |
| Suricata trên đĩa | drop-in 90-pbl4-post-proxy.conf -> post-proxy.yaml, AF_PACKET vmnet3, XFF extra-data |
| njs | /etc/nginx/modules-enabled rỗng; không thấy module tại /usr/lib/nginx/modules; có bản test dưới /tmp, user-owned |
| UID/GID | getent không tìm thấy websentinel-edge |
| AI trên đĩa | chạy bằng user cá nhân, Group=www-data, RuntimeDirectoryMode=0710, socket-mode=620 |
| AI socket đang chạy | /run/pbl4-ai-shadow không xuất hiện trong view hiện tại; không suy ra trạng thái Host thực |
| Student CA | public CA ~/ws-student-trust/ca.crt đọc được; hiệu lực 17/11/2026–17/11/2027 |
| Edge certificate | /etc/nginx/pbl4-tls/lab.crt chưa đọc được do quyền thư mục; không lấy private key |
| Rust .env | AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF, SURICATA_TRUSTED_EDGE_CONFIRMED=true |
| Rust code | chặn Verified với loopback/lo; chưa xác minh binary và env của process đang chạy |
| Runtime systemd/IP/nft | sandbox chặn bus/netlink; thử ngoài sandbox bị auto-review timeout; CHƯA XÁC MINH |
| TLS tới Student lần này | curl bị chặn mở socket, exit7/HTTP000; KHÔNG PASS, không kết luận Student lỗi |

Fingerprint CA: 93:1C:DF:F4:A0:90:08:3D:8A:D2:EC:BE:84:80:AC:E5:A7:B3:D4:77:F6:97:87:D5:7A:CD:5D:12:E7:34:04:E9.
Kết quả TLS PASS trước đây do người vận hành cung cấp vẫn là bằng chứng lịch sử.
File owner hiện qua sandbox có nobody/nogroup; cần đối chiếu bằng stat trên terminal
Host trước khi kết luận quyền thật. Không xem file trên đĩa là cấu hình đã được nạp.

## Trạng thái preflight/dry-run

**PREFLIGHT: BLOCKED**, chưa phải PASS. Đã đọc target map và trình tự deploy mà không
mutation; **dry-run bundle hoàn chỉnh CHƯA ĐẠT** vì thiếu account/module production,
public Edge CA đọc được và phương án quyền AI. Không dùng CA Student thay CA Edge,
không chọn GID giả chỉ để dry-run xanh. Không chạy nginx -T đặc quyền trong phiên này.

Lệnh người vận hành chạy để bổ sung bằng chứng (chỉ đọc, không restart):

```bash
ip -br addr
systemctl show nginx suricata pbl4-ai-shadow.service \
  -p ActiveState -p SubState -p ExecStart -p ExecReload -p User -p Group -p ControlGroup
systemctl cat nginx suricata pbl4-ai-shadow.service
sudo nginx -T
sudo nft list ruleset
getent passwd websentinel-edge
getent group websentinel-edge
sudo stat /run/pbl4-ai-shadow /run/pbl4-ai-shadow/nginx.sock
sudo getfacl -p /run/pbl4-ai-shadow /run/pbl4-ai-shadow/nginx.sock
sudo openssl x509 -in /etc/nginx/pbl4-tls/lab.crt -noout -subject -issuer -dates -ext subjectAltName
bash student-web/deploy/tls/verify-from-defender.sh "$HOME/ws-student-trust/ca.crt" student.lab
```

Kiểm tra mã thoát script TLS: chuỗi `TLS verified; HTTP=000` in ra khi curl lỗi
không phải bằng chứng xác minh thành công. Cần FE200/API401, DNS SAN student.lab,
sai hostname và sai CA bị từ chối. Không dùng -k/verify off. Không gửi private key,
nguyên env hoặc cấu hình chưa lọc bí mật vào chat.

## Chặn quan trọng: quyền AI và những việc cần duyệt

Không đổi AI Group sang websentinel-edge: như vậy AI có thể đọc HMAC key group0640.
Cũng không thêm worker NGINX vào www-data vì identity validator cấm supplementary
 groups và làm rộng ranh giới tin cậy.

Phương án cần kiểm tra trước: POSIX ACL chỉ cấp UID websentinel-edge quyền traverse
RuntimeDirectory và write socket; giữ AI user/group hiện tại. ACL phải được tạo
lại khi systemd tái tạo RuntimeDirectory và khi worker bind lại socket. Có thể dùng
ExecStartPre trong unit AI để đặt access/default ACL trên RuntimeDirectory, rồi
kiểm chứng default ACL được socket kế thừa và còn hiệu lực sau chmod0620. Đây mới
là thiết kế, chưa nghiệm thu; không chỉ setfacl một lần lên socket đang chạy.
Cần kiểm tra ACL support, hardening unit, mask/effective permissions, restart AI và
NGINX gửi telemetry thành công. Việc thêm hook/restart AI cần duyệt riêng.

Các việc khác: cài module njs ABI đúng tại path ổn định root-owned; tạo UID/GID riêng
nologin; rà soát quyền log/temp/cache/site hiện tại và AppArmor. Logrotate trên đĩa
sử dụng `invoke-rc.d nginx rotate`, không nên mặc định đồng nhất với reload: cần xác
minh rotate gửi reopen đúng master, owner của file mới và cách supervisor quản lý
PID. Rà soát automation/certbot đang gọi reload; không tắt reload rồi mặc định các
luồng cũ vẫn hoạt động.

## Backup trước MỌI thay đổi prerequisite

Script mới chỉ thu snapshot; không chạy trong phiên chuẩn bị:

```bash
sudo bash security-web/scripts/backup-security-host.sh \
  /var/backups/ws-security-before-egress-YYYYMMDD-HHMMSS
```

Gồm NGINX (có TLS private key), Suricata, systemd overrides/units, module, logrotate,
account/group inventory, nft text+JSON, iptables/ip6tables nếu có, network và package
versions. Archive giữ ACL/xattr/owner, có checksum và COMPLETE. Script lỗi thì không
được apply. Backup root-only, không Git/chat; không backup DB hoặc sửa dữ liệu.
ACL paths không tồn tại được ghi vào permissions-errors, cần review. Snapshot cấu
hình không phải snapshot bộ nhớ dịch vụ/replay state.

Không restore toàn bộ `/etc/systemd/system`, passwd/group hoặc flush firewall từ
archive. Khôi phục chọn lọc những file thực sự thay, xác minh trước. Tuyệt đối
không restore HMAC key/epoch cũ nếu đã mất replay state. Firewall dump chỉ là bằng
chứng/phục hồi có review, không `nft -f` nguyên dump vào ruleset đang chạy.

## Trình tự triển khai dự kiến — từng điểm phải kiểm tra

1. Hoàn thành baseline/runtime/TLS và backup COMPLETE; ghi FE/API/login/Audit,
   AI heartbeat/telemetry và Suricata vmnet3 hiện tại. Dừng nếu baseline lỗi.
2. Sau phê duyệt riêng: account/module/quyền/ACL AI. Giữ site cũ, kiểm tra nginx -t,
   AI telemetry và mọi site sau thay prerequisite. Lưu thay đổi vào backup manifest.
3. Xuất bundle bằng stage-proof-host.py theo HOST-DEPLOYMENT.md với GID thật,
   module ổn định và public CA Edge thật. Review site/includes/unit; không đổi VM.
4. Chạy preflight và dry-run dưới đây. Chuyển bản đã duyệt sang thư mục root-owned.
5. Cửa sổ downtime: đóng lưu lượng; deny guard, rotation và khởi động NGINX. Kiểm
   tra guard heartbeat mới, TLS FE/API, proof từ chối, RID/XFF, AI telemetry. Chỉ
   sau khi NGINX ổn mới chuyển Suricata sang lo, kiểm tra -T/active/EVE thật và SID.
6. Kiểm tra Application Audit/Dashboard riêng. EVE local-egress vẫn Unverified;
   giữ AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF; không đổi trusted flag để ép Verified.
7. Lỗi ở bất kỳ checkpoint nào: dừng candidate, khôi phục site cũ và vmnet3.

**Giới hạn installer hiện tại:** apply dừng cả hai service, start NGINX rồi Suricata,
health tổng sau đó; chưa có checkpoint HTTP độc lập giữa hai lần start. Vì yêu cầu
lần này là khảo sát/kế hoạch, chưa sửa lifecycle để giả vờ đã đáp ứng checkpoint đó.
Cần duyệt việc bổ sung/kiểm tra checkpoint trước khi dùng apply trên Host thật.
Installer tự backup các target của nó, không bao gồm prerequisite account/module/
ACL AI thay ngoài bundle; snapshot đầy đủ ở trên và rollback riêng là bắt buộc.

## Lệnh để review, chưa được chạy apply

Sau khi prerequisites và bundle thực sự đầy đủ:

```bash
python3 security-web/scripts/deploy-proof-host.py preflight \
  --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-apply-before
python3 security-web/scripts/deploy-proof-host.py dry-run \
  --bundle /tmp/ws-host-bundle-review --backup /var/backups/ws-proof-apply-before

# Chỉ sau duyệt checkpoint/ACL và chuyển bundle đã review sang root-owned directory:
sudo python3 security-web/scripts/deploy-proof-host.py apply \
  --bundle /root/ws-host-bundle-approved \
  --backup /var/backups/ws-proof-apply-before --approve-host-change
sudo python3 security-web/scripts/deploy-proof-host.py health \
  --bundle /root/ws-host-bundle-approved --backup /var/backups/ws-proof-apply-before

# Rollback target files và trạng thái service của lần apply này:
sudo python3 security-web/scripts/deploy-proof-host.py rollback \
  --bundle /root/ws-host-bundle-approved \
  --backup /var/backups/ws-proof-apply-before --approve-host-change
```

Rollback nhanh đưa Edge về HTTP Student80 và capture vmnet3; Student VM443/80 giữ
nguyên. Nếu còn deny-only table chuyên biệt thì giữ lại đến khi chắc chắn không
còn listener phụ thuộc. Không flush nft. Prerequisite AI ACL/unit cần phục hồi riêng
về snapshot trước prerequisite và nghiệm thu telemetry; không chỉ rollback bundle.
Nếu rollback cũng lỗi, giữ candidate dừng và xử lý lỗi thật, không báo đã phục hồi.

## Rủi ro chấp nhận khi bỏ VM

Supervisor/installer thực với systemd chưa nghiệm thu; downtime do stop/restart,
request đang chạy có thể bị ngắt; sensor có khoảng trống chuyển capture. Key/group
hoặc AI ACL sai có thể làm toàn bộ web/telemetry lỗi. Guard monitoring có khoảng
trễ; root/cùng UID compromise không được giải quyết. Timing HMAC, journal rollback/
revocation, response completion và Rust Shadow runtime vẫn chưa nghiệm thu.
Không triển khai Lua fixture như runtime logger. Không production-ready Verified.
