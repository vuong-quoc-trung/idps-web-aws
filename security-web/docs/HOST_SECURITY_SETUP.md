# Nghiệm thu Security trên Ubuntu host

> Bộ rule hiện hành có 14 SID, bổ sung HTTP flood, Time/Blind SQLi URI/body, web shell
> upload và SSRF URI/body. Xem [EXTENDED_RULES.md](EXTENDED_RULES.md) để kiểm thử và
> nâng bản rule; các mô tả số lượng rule trong hướng dẫn lịch sử bên dưới là bản cũ.

> **Cập nhật foundation26/10/2026:** dùng `ENFORCEMENT_MODE=OFF` khi nghiệm thu; code/config đã hỗ trợ dảiprivate, host/gateway exclusions và TTL, thay cho dảiKali cố định trong hướng dẫn lịch sử. Không áp helper/ruleset cũ lẫn bản mới. Cài đồng bộ **wrapper**, **policy module** và `pbl4.nft` sau khi kiểm tra backup/management access; scriptdev không thực hiện việc này.
>
> Module mới: `scripts/pbl4-firewall-policy.py` → `/usr/local/libexec/pbl4-firewall-policy.py`, root-owned0755; wrapper vẫn `/usr/local/bin/pbl4-firewall`, root-owned0755. Policy tùy chọn `config/firewall-policy.json.example` → `/etc/pbl4/firewall-policy.json`, root-owned0644, protectedIPs phải gồm WebVM/gateway và assets quản trị thực tế. ENV backend không thay thế policy root. Tệp root policy không được group/world writable.
>
> Nginx template mới ưu tiên backend/frontendloopback rồi backupWebVM80; Security DB5434, Student DB5433. Tham chiếu [`../README.md`](../README.md) và [`../../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`](../../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md) cho trạng thái kiểm chứng. Những dòng dưới mô tả snapshot lab cũ nếu không được ghi đè bởi update này.


Kiến trúc cố định: Kali 192.168.10.10 (VMnet2) → Nginx host 192.168.10.1:80 → Web 192.168.20.10 (VMnet3); host vmnet3=192.168.20.1. AUTO_BLOCK=false. Các lệnh sudo bên dưới do người vận hành tự chạy, không phải script tự triển khai. Không dùng deploy.sh --deploy (đã khóa trước bước sudo).

Chạy các lệnh từ `security-web/`. Không đổi mạng/IP, không flush ruleset, không thay /etc/nftables.conf. Dừng backend đang chạy trước khi cấp quyền firewall; chỉ khởi động lại sau bước rà tác vụ DB.

## 1 Suricata

Repo capture AF_PACKET chỉ trên vmnet2. HOME_NET=[192.168.10.1/32,192.168.20.0/24], EVE bật, file eve.json, bộ 8 rule dành cho nguồn 192.168.10.0/24 tới proxy. HTTP dùng URI chuẩn hóa; các rule này là chữ ký demo, không bao phủ mọi biến thể tấn công hoặc HTTPS mã hóa.

Kiểm tra repo sau mỗi lần sửa YAML/rule (không sudo, không capture mạng):

```bash
check_dir=$(mktemp -d /tmp/pbl4-suricata-check.XXXXXX)
suricata -T -c config/suricata/suricata.yaml \
  -S "$PWD/suricata/pbl4.rules" -l "$check_dir"
```

Kỳ vọng: `Configuration provided was successfully loaded`, không lỗi rule. `-S` nạp chính xác rule trong repo, không phụ thuộc bản đã cài. Thư mục /tmp này chỉ chứa kết quả kiểm tra, không phải nguồn ingest.

Cài cấu hình sau khi kiểm tra:

```bash
backup_dir="/var/backups/pbl4-host-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup_dir"
sudo cp -a /etc/suricata/suricata.yaml "$backup_dir/"
# Nếu rule đã tồn tại, sao lưu trước:
if sudo test -f /var/lib/suricata/rules/pbl4.rules; then
  sudo cp -a /var/lib/suricata/rules/pbl4.rules "$backup_dir/"
fi
sudo install -d -m 0755 /var/lib/suricata/rules
sudo install -o root -g root -m 0644 suricata/pbl4.rules /var/lib/suricata/rules/pbl4.rules
sudo install -o root -g root -m 0644 config/suricata/suricata.yaml /etc/suricata/suricata.yaml
sudo suricata -T -c /etc/suricata/suricata.yaml
systemctl cat suricata
```

Kiểm tra ExecStart không ép capture NIC cũ. Nếu service không dùng AF_PACKET theo YAML, tạo override bằng `sudo systemctl edit suricata`:

```ini
[Service]
Type=simple
PIDFile=
ExecStart=
ExecStart=/usr/bin/suricata --af-packet=vmnet2 -c /etc/suricata/suricata.yaml
```

Sau khi kiểm tra đường dẫn binary bằng `command -v suricata`, chỉ dùng override nếu đúng `/usr/bin/suricata`. Chạy:

```bash
sudo suricata -T -c /etc/suricata/suricata.yaml
sudo systemctl daemon-reload
sudo systemctl restart suricata
systemctl status suricata --no-pager
sudo journalctl -u suricata -n 40 --no-pager
sudo tail -n 3 /var/log/suricata/eve.json
```

Checklist: service active; capture vmnet2; không có lỗi rule; request mẫu trên Kali tạo alert EVE. Không lấy việc file tồn tại hoặc -T pass làm bằng chứng phát hiện thành công.

## 2 Backend và quyền đọc log

.env đã chuyển vmnet2/vmnet3, log thật và helper /usr/local/bin/pbl4-firewall; giữ DATABASE_URL và hash hiện có. Không source .env vào shell. Nếu terminal từng export biến test, bỏ override trước khi chạy:

```bash
unset ATTACKER_IFACE PROTECTED_IFACE SECURITY_IP WEB_SERVER_IP
unset SURICATA_EVE_PATH NGINX_ACCESS_PATH PBL4_FIREWALL_CMD AUTO_BLOCK
source "$HOME/.cargo/env"
test -r /var/log/nginx/access.log && echo nginx-readable
test -r /var/log/suricata/eve.json && echo eve-readable
```

Tại lần rà soát, cả hai file đều đọc được bằng tài khoản hiện tại. Nếu quyền đổi sau rotation, kiểm tra `ls -ld /var/log/nginx /var/log/suricata` và `ls -l` từng log. Có thể cấp ACL cho đúng user backend (chạy các lệnh này bằng tài khoản sẽ chạy backend, không phải root shell):

```bash
sudo setfacl -m "u:$(id -un):r-x" /var/log/nginx /var/log/suricata
sudo setfacl -m "d:u:$(id -un):r-x" /var/log/nginx /var/log/suricata
sudo setfacl -m "u:$(id -un):r--" /var/log/nginx/access.log /var/log/suricata/eve.json
```

Xác nhận lại sau rotation vì công cụ rotate/chmod có thể đổi ACL mask. Không tạo EVE rỗng thay cho Suricata.

**Trước khi chạy backend có helper thật:** AUTO_BLOCK=false chỉ ngăn tạo phản ứng tự động mới. Worker vẫn xử lý hàng đợi và restore IP active. Trong DBeaver, chạy read-only:

```sql
SELECT id, host(ip), action, source, status, created_at
FROM firewall_actions WHERE status='PENDING' ORDER BY id;
SELECT host(ip), reason, blocked_at FROM blocked_ips WHERE active;
```

Nếu có tác vụ/active IP cũ, chưa khởi động backend với quyền helper; xem xét từng bản ghi và quyết định riêng. Không tự xóa hay áp lại chúng khi chưa duyệt.

Sau khi xác nhận dữ liệu cũ và hoàn thành firewall bên dưới:

```bash
cd frontend
npm ci
npm run build
cd ..
cargo build --locked
./target/debug/pbl4-security-demo --check-config
AUTO_BLOCK=false cargo run
```

Checklist: watcher NGINX/SURICATA đọc thành công; mốc log mới thay đổi khi Kali gửi request; alert có IP Kali và hiện trong DB/UI; dashboard vẫn chỉ truy cập quản trị tại loopback. Không tự chạy backend trong quá trình rà soát để tránh worker tác động firewall.

## 3 Ruleset chỉ dành cho lab

scripts/pbl4.nft dùng vmnet2/vmnet3, table inet pbl4_demo và set blocked_ips. INPUT chặn nguồn trong set đến host; FORWARD chặn đi tắt HTTP tới Web và nguồn trong set. Không thay bảng Docker/UFW. Các IP khác .2–.254 không được helper nhận; IP whitelist vẫn do backend kiểm tra, không coi helper là nơi giữ toàn bộ whitelist.

Kiểm tra và sao lưu do người vận hành chạy:

```bash
sudo nft list ruleset > /tmp/pbl4-before-host.nft
sudo nft list table inet pbl4_demo
sudo nft -c -f scripts/pbl4.nft
```

Nếu bảng chưa tồn tại, lệnh list table báo thiếu là bình thường; `nft -c` phải exit 0. Nếu bảng đã tồn tại, không nạp file lặp lại vì có thể nhân đôi rule. Xem counter, IP đang chặn và xác nhận trước khi thay bảng.

**Chỉ áp dụng sau khi bạn duyệt:**

```bash
# Chỉ khi bảng pbl4_demo CHƯA tồn tại:
sudo nft -f scripts/pbl4.nft
# Nếu bảng ĐÃ tồn tại và bạn đồng ý thay riêng bảng lab:
# Cách này xóa block/counter hiện tại trong bảng lab; không chạy khi chưa duyệt.
lab_update=$(mktemp /tmp/pbl4-table-update.XXXXXX)
{ echo 'delete table inet pbl4_demo'; cat scripts/pbl4.nft; } > "$lab_update"
sudo nft -c -f "$lab_update"
# Sau khi đọc lại nội dung và xác nhận:
# sudo nft -f "$lab_update"
```

Không chạy cả hai nhánh. Không dùng `flush ruleset`, không restart nftables, không ghi đè /etc/nftables.conf. Áp dụng trên chỉ là runtime; chưa thiết lập tự nạp khi reboot.

## 4 Helper và sudoers giới hạn

Sau khi kiểm tra bảng lab, cài helper từ repo (không cho backend ghi helper):

```bash
sudo install -o root -g root -m 0755 scripts/pbl4-firewall /usr/local/bin/pbl4-firewall
sudo visudo -f /etc/sudoers.d/pbl4-security
```

Với tài khoản hiện tại, nội dung:

```sudoers
dinh-huynh-nguyen-khang ALL=(root) NOPASSWD: /usr/local/bin/pbl4-firewall
```

Nếu systemd dùng tài khoản khác, thay đúng User của service. Không cấp NOPASSWD ALL.

```bash
sudo chmod 0440 /etc/sudoers.d/pbl4-security
sudo visudo -cf /etc/sudoers.d/pbl4-security
sudo -n /usr/local/bin/pbl4-firewall list-json
```

Kỳ vọng: JSON set blocked_ips, không hỏi mật khẩu. Đây là đọc, chưa chặn IP. Lỗi thiếu table khác lỗi sudo; quay lại kiểm tra bảng tương ứng.

## 5 Nghiệm thu thủ công trước auto-block

Giữ AUTO_BLOCK=false. Kali chạy `curl --noproxy '*' --max-time 8 -I http://192.168.10.1/`. Trên Kali, dùng lab-probes.sh từ repo với từng case; không chạy tất cả nếu cần đối chiếu rõ từng rule. Theo dõi EVE bằng:

```bash
sudo tail -f /var/log/suricata/eve.json
```

Checklist:

- Request bình thường tới được Student Web; SQLi/XSS/probe tạo cảnh báo đúng nguồn/rule.
- Dashboard admin gửi manual BLOCK cho **192.168.10.10** sau khi bạn xác nhận đây là Kali, không phải IP quản trị.
- Audit chuyển PENDING → SUCCESS; DB và kernel cùng có IP; request mới từ Kali thất bại; counter nft tăng.
- Manual UNBLOCK từ dashboard làm request mới thành công, audit đầy đủ.
- Kali truy cập thẳng http://192.168.20.10 bị ngăn theo chính sách proxy; không thay route/IP để ép bài test khác.
- Giữ AUTO_BLOCK=false đến khi kết thúc nghiệm thu. Không tuyên bố Suricata inline IPS: cơ chế hiện tại phát hiện rồi chặn qua nftables.

Nếu bị chặn nhầm Kali và backend không dùng được, người vận hành có thể tự chạy `sudo /usr/local/bin/pbl4-firewall unblock 192.168.10.10`, sau đó đối chiếu lại DB; không flush bảng hoặc toàn ruleset.
