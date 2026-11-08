# Student Audit: SSHFS → rsyslog RELP/TCP

## Trạng thái và giới hạn

**SSHFS: deprecated / rollback-only.** Pipeline đã cutover sang RELP và backend đọc
`STUDENT_AUDIT_LOG_PATH=/var/log/pbl4/student-audit.log`.

Ngày 30/10/2026 (Asia/Ho_Chi_Minh), đã unmount sạch SSHFS thủ công bằng fusermount3;
mountpoint `~/.local/share/pbl4/student-vm-live` được giữ rỗng. Không gỡ package/key,
không xóa log, queue hoặc checkpoint/DB. AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF.

Receiver active, listener chỉ 192.168.20.1:2514; kết nối từ 192.168.20.10 được quan sát.
GET /api/auth/me (401 bình thường do chưa đăng nhập) sau unmount tạo event
`402fed1a-0265-4364-bc4b-28c1d2ae2e51`, request ID
`sshfs-retire-fe80da21-d110-4dc7-825e-4817a02b9764`.
File local tăng từ 685372 lên 686073 byte; DB có event lúc 22:27:53 giờ Việt Nam,
khoảng một giây sau lúc phát sinh. Đây là bằng chứng forwarding + ingest sau unmount.
Chưa kiểm tra trực tiếp hiển thị trình duyệt có đăng nhập; bấm Tải lại audit để xem.

Không tìm thấy autostart SSHFS trong repo, /etc/fstab, systemd system/user, user
autostart, profile/zshrc và cron đã kiểm tra. Mount unit cũ do /proc/self/mountinfo,
không có FragmentPath/UnitFileState: mount thủ công, không có unit cần disable.
SSH BatchMode vào VM chưa xác thực nên chưa xác nhận trực tiếp systemctl sender;
forwarding mới đã được chứng minh bằng event tới file local/DB. Trên VM có thể kiểm
tra bổ sung: `systemctl is-active pbl4-audit-sender.service`.

Các bước cài đặt bên dưới là hướng dẫn tái triển khai, không cần chạy lại trên hệ
thống đã hoạt động. UI polling vẫn là task riêng; nút Tải lại audit vẫn cần.

Lab dùng **RELP/TCP không mã hóa**, port 2514 chỉ bind 192.168.20.1, firewall giới hạn
vmnet3 + 192.168.20.10, receiver lọc source/schema. Không dùng UDP. Không tuyên bố
exactly-once hoặc chịu mất điện tuyệt đối. RELP ACK không phải DB commit.
TLS là hardening tiếp theo: omrelp/imrelp hỗ trợ tls, CA, cert/key, authMode name và
permittedPeer; triển khai mTLS hai đầu và kiểm tra danh tính trước khi dùng ngoài
host-only lab/EC2. Không đưa private key vào Git.

Luồng:
`Student JSONL → imfile → disk queue → RELP → imrelp/disk queue → raw JSONL → Rust → DB`.
Không thêm body/cookie/token, không thay event_id/source_instance/timestamp/schema.

## 0. Preflight, chạy trên từng máy

```bash
rsyslogd -v
systemctl status rsyslog --no-pager
find /usr/lib -path '*/rsyslog/imfile.so' -o -path '*/rsyslog/imrelp.so' -o -path '*/rsyslog/omrelp.so'
```

Trên Web VM, dưới user khang1901:

```bash
cd /home/khang1901/idps-web-aws/security-web
stat -c '%U %G %a %s %y %n' ../student-web/backend/logs ../student-web/backend/logs/student-audit.log
bash scripts/verify-student-audit-forwarding.sh --source ../student-web/backend/logs/student-audit.log
```

Thao tác đọc Student Web rồi chạy stat lần nữa. File phải tăng, không chỉ bảng DB Student.
Writer ghi DB và file độc lập; lỗi JSONL không làm mất dòng trong DB Student nhưng
shipper không thể khôi phục event chưa xuất. Giới hạn writer mặc định 64 MiB, dòng
16 KiB, file0600/thư mục0700. Không chmod world-readable. Sender chạy user khang1901.
Kiểm tra file hiện dưới 64 MiB; nếu gần đầy, cần rotation được kiểm soát trước.

## 1. Cài receiver trước, vẫn giữ backend đọc SSHFS

Trên Security host:

```bash
cd /home/dinh-huynh-nguyen-khang/Projects_PBL4/idps-web-aws/security-web
sudo bash scripts/install-student-audit-receiver.sh --install-packages
```

Installer chỉ cài package còn thiếu trong rsyslog, rsyslog-relp, logrotate. Không
apt upgrade, không sửa cấu hình rsyslog chung, không restart rsyslog chung. Package
manager có thể chạy maintainer hooks của package; kiểm tra trạng thái dịch vụ sau cài.
Installer KHÔNG enable/start PBL4 service. Backup file trước ghi tại
`/etc/pbl4/backups/audit-receiver-TIMESTAMP/`. Nếu thư mục đích đã tồn tại với owner/mode
khác, installer dừng, không tự chown dữ liệu có sẵn.

Config `/etc/pbl4/audit/receiver.conf`; unit `pbl4-audit-receiver.service` chạy `syslog`,
group của backend user. `/var/log/pbl4` syslog:backend-group0750, file0640;
`/var/lib/pbl4-audit-receiver` syslog:backend-group0700. Queue disk giới hạn1GiB.
AppArmor: nếu profile có include rsyslog.d, installer thêm snippet hẹp có backup và
reload profile, không disable AppArmor. Profile không tương thích thì dừng.

### Firewall trước khi start

```bash
sudo /usr/local/libexec/pbl4-audit-guard
```

Lệnh in ruleset và chạy `nft -c`. Hai rule dự kiến, table riêng `inet pbl4_audit_transport`:

```nft
ip daddr 192.168.20.1 tcp dport 2514 iifname != "vmnet3" drop
ip daddr 192.168.20.1 tcp dport 2514 ip saddr != 192.168.20.10 drop
```

Chỉ khi đã review:

```bash
sudo /usr/local/libexec/pbl4-audit-guard --apply
sudo systemctl enable --now pbl4-audit-receiver.service pbl4-audit-receiver-rotate.timer
systemctl status pbl4-audit-receiver.service --no-pager
ss -ltnp 'sport = :2514'
```

Guard backup danh sách table trước tạo vào `/var/lib/pbl4-audit-guard`, không sửa table
cũ. Nếu table cùng tên tồn tại mà rule khác thì dừng. Không flush/delete, không chạm
pbl4_demo, Docker, UFW hay /etc/nftables.conf. ExecStartPre kiểm tra/nạp guard khi boot.
Đích hợp lệ không bị guard drop, nhưng guard **không vượt qua DROP của UFW/table khác**.
Nếu firewall đang có default drop, cần review thêm allow rule đúng chain hiện có;
không tự mở rộng policy. Interface vmnet3/IP phải được tạo trước listener. Service
retry nếu bind thất bại; kiểm tra VMware networking sau boot.

## 2. Cài sender trên Web VM

Đưa các file repo mới sang Web VM trước (commit/pull cùng nhánh, không chép `.env`).

```bash
cd /home/khang1901/idps-web-aws/security-web
sudo bash scripts/install-student-audit-sender.sh --install-packages
sudo systemctl enable --now pbl4-audit-sender.service pbl4-audit-sender-rotate.timer
systemctl status pbl4-audit-sender.service --no-pager
```

Config `/etc/pbl4/audit/sender.conf`; process riêng user khang1901. Spool/state
`/var/lib/pbl4-audit-sender`0700 trên persistent disk, queue disk1GiB, checkpoint mỗi
record, sync queue, retry vô hạn với thời gian kết nối giới hạn. Shutdown sạch có thời
gian drain/save; không chạy kill -9. Không xóa queue/state để khắc phục kết nối.

imfile đọc producer `student-audit.log*` gồm file current và generations để khôi phục
khi agent nghỉ lúc rotation. Chỉ đặt JSONL audit không nén dưới prefix đó; không đặt
backup cấu hình, snapshot hoặc gzip ở đó. Không thu toàn bộ syslog.

### Rotation

Config riêng `/etc/pbl4/audit/{sender,receiver}.logrotate`, timer riêng kiểm tra mỗi
phút, rotate khi >16MiB hoặc daily, rename/create, không copytruncate, không nén.
State logrotate riêng root-owned `/var/lib/pbl4-audit-rotation`.
Sender tạo file0600 đúng owner; receiver tạo0640 và HUP chỉ receiver sau rename.

`rotate -1` cố ý chưa tự xóa generations trong giai đoạn nghiệm thu để không xóa
backlog chưa gửi/ingest. Phải theo dõi đĩa và định nghĩa cleanup sau khi xác nhận
checkpoint/receipt; không để chạy vô hạn không giám sát. Queue đầy có thể gây
backpressure và cuối cùng mất dữ liệu nếu source hết chỗ. Rotation mỗi phút không
bảo đảm tránh trần64MiB nếu >48MiB sinh thêm giữa hai lần kiểm tra. Đo tốc độ thực tế,
giảm chu kỳ/điều chỉnh writer limit có review nếu cần. Không xóa log để ép pipeline chạy.

## 3. Acceptance song song — chưa sửa .env

Dùng thao tác GET/UI bình thường, không test tấn công. Sau từng case lưu snapshot nguồn
ngoài thư mục logs; chờ queue gửi hết rồi so với receiver. Tool chỉ đọc, không in payload.

Trên Web VM:
```bash
cp /home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log /tmp/pbl4-audit-source-snapshot.jsonl
```
Trên host:
```bash
scp khang1901@192.168.20.10:/tmp/pbl4-audit-source-snapshot.jsonl /tmp/pbl4-audit-source-snapshot.jsonl
bash scripts/verify-student-audit-forwarding.sh --source /tmp/pbl4-audit-source-snapshot.jsonl --destination /var/log/pbl4/student-audit.log /var/log/pbl4/student-audit.log.1
```
Chỉ liệt kê file rotated thực sự tồn tại (bỏ `.1` nếu chưa rotate); có thể liệt kê nhiều.
PASS yêu cầu mọi source ID và toàn bộ JSON giống nhau; báo số dòng trùng do retry,
không coi số dòng thô là số event duy nhất. File đang ghi dở thì chụp snapshot lại.

| Case | Thao tác được phép sau review | Kỳ vọng |
|---|---|---|
| A Normal | GET/UI Student, so snapshot | ID/content giống, JSONL không prefix/wrapper |
| B Receiver restart | `sudo systemctl restart pbl4-audit-receiver` trên host | Reconnect, event mới tới |
| C Mất đích | Stop chỉ receiver, thao tác Student, start receiver | Queue gửi bù; không ngắt vmnet/firewall |
| D Sender restart | Restart chỉ pbl4-audit-sender trên VM | Resume, ID không mất |
| E/F Reboot | Người dùng tự reboot từng máy sau khi A–D/G đạt | Services/timers tự chạy, bind đúng IP |
| G Rotation | Chạy logrotate `--force` với config và state riêng của role trong cửa sổ kiểm soát | Current + generations đủ event |

Trước force rotation lưu stat/count, đảm bảo app đang hoạt động, không xóa generations.
Không thực hiện reboot tự động. Không ghi fixture vào file audit thật để làm đẹp số liệu.

Kiểm thử cô lập (loopback + temp files, không DB) có sẵn:
```bash
python3 scripts/test-student-audit-forwarding.py
```
Nó không thay thế acceptance trên vmnet3, AppArmor, systemd hay reboot thực tế.

## 4. Cutover chỉ sau khi acceptance đạt

Backup `.env` quyền0600 ngoài Git. Sửa DUY NHẤT đường dẫn:
```dotenv
STUDENT_AUDIT_LOG_PATH=/var/log/pbl4/student-audit.log
COLLECT_ALL_EVENTS=true
AUTO_BLOCK=false
ENFORCEMENT_MODE=OFF
```
Không thay DB URL/hash hoặc reset log_cursors/source_event_receipts/normalized_events.
Restart backend theo cách đang chạy (terminal cargo run thì Ctrl-C rồi chạy lại;
không tự tạo/đoán service). Kiểm tra watcher watching, last_success/last_data tăng,
không parse error, API Audit có ID mới sau GET, retry không nhân bản DB.
Backend vẫn poll1s, dedup theo source/source_instance/event_id trong retention hiện có.
Bảng Audit UI vẫn cần Tải lại; polling UI là task riêng, không liên quan forwarding.

## 5. Rollback và ngừng SSHFS

Chưa unmount SSHFS trước acceptance đầy đủ. Khi đã đạt, người vận hành mới unmount
read-only; không xóa mountpoint/log remote. Giữ file mới và queue để điều tra.

Rollback trên host:
```bash
bash scripts/uninstall-student-audit-receiver.sh
# Nếu SSHFS đang mount thì giữ nguyên, KHÔNG mount chồng:
mountpoint "$HOME/.local/share/pbl4/student-vm-live"
# Chỉ chạy khi chưa mount:
sshfs khang1901@192.168.20.10:/home/khang1901/idps-web-aws/student-web/backend/logs \
 "$HOME/.local/share/pbl4/student-vm-live" \
 -o ro,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no
```
Trên VM: `bash scripts/uninstall-student-audit-sender.sh`.
Uninstall chỉ disable/stop service/timer riêng; không xóa config, queue, DB hay logs.
Khôi phục STUDENT_AUDIT_LOG_PATH về đường dẫn SSHFS cũ, restart backend như trước.
Guard table được giữ nguyên; không ảnh hưởng traffic ngoài port2514 tại .20.1.
Không chạy xóa table hoặc gỡ package chung trong rollback tự động.

## Theo dõi và nghiệm thu cuối

`journalctl -u pbl4-audit-sender` / `-u pbl4-audit-receiver`, trạng thái timer,
`du -sh /var/lib/pbl4-audit-*`, dung lượng đĩa, file source/receiver tăng và so ID.
Listener phải chỉ có `192.168.20.1:2514`. TLS hiện chưa bật. Dữ liệu chảy một chiều;
ACK RELP/TCP vẫn có chiều ngược. Watcher watching không chứng minh sender còn sống.

Tham chiếu: https://docs.rsyslog.com/doc/configuration/modules/imfile.html,
https://docs.rsyslog.com/doc/configuration/modules/omrelp.html,
https://docs.rsyslog.com/doc/configuration/modules/imrelp.html,
https://docs.rsyslog.com/doc/concepts/queues.html.

## Lịch sử kiểm tra bộ triển khai trước cutover (không phải trạng thái hiện tại)

- Host rsyslog8.2512.0, có imfile/mmjsonparse, thiếu imrelp/omrelp.
- Chỉ tải/extract rsyslog-relp/librelp vào /tmp để thử; KHÔNG cài package.
- Config sender/receiver vượt `-N1` và chạy hai daemon tạm trên loopback.
- Test RELP thật trong thư mục tạm đạt: JSON >8KiB, normal, receiver outage + backlog,
  sender restart lúc receiver dừng, reconnect, sender restart bình thường, rename/create
  sender và receiver. Full JSON và event identity được giữ nguyên.
- Ba test tool đạt: replay/duplicate hợp lệ, missing/modified/wrapper bị phát hiện;
  guard dry-run không apply và từ chối table xung đột (mock nft).
- Unit syntax verify đạt với ExecStartPre guard thay bằng true trong BẢN TẠM, vì helper
  chưa được cài. Installer verify lại unit thật trước khi đưa lệnh start.
- Python/shell syntax và git diff --check đạt.
- CHƯA kiểm thử live vmnet3, firewall kernel guard, AppArmor deployed, module package
  installation, root installer, reboot, queue đầy/mất điện, cutover/API/DB/UI.
- SSHFS/.env/DB/Suricata/firewall hệ thống chưa thay đổi. Không coi các test tạm là
  nghiệm thu migration trên hai máy thật.
