# Tự nạp bảng PBL4 khi Ubuntu boot

Chạy trên Ubuntu Security host. `AUTO_BLOCK=false`, `ENFORCEMENT_MODE=OFF` vẫn giữ nguyên.
Không sửa helper `/usr/local/bin/pbl4-firewall`, sudoers, `/etc/nftables.conf`, hoặc các
bảng Docker/UFW. Không khởi động lại nftables và không có thao tác xóa bảng khi stop/restart.

## Cơ chế

- Nguồn Git: `scripts/pbl4.nft`, `scripts/pbl4-load-firewall`,
  `deploy/systemd/pbl4-firewall.service`.
- Bản cài: `/etc/pbl4/pbl4.nft` (root:root,0644),
  `/usr/local/libexec/pbl4-load-firewall` (root:root,0755),
  `/etc/systemd/system/pbl4-firewall.service` (root:root,0644).
- `Type=oneshot`, `RemainAfterExit=yes`, sau `network.target` và sau nftables/UFW/Docker
  nếu các service đó cùng nằm trong giao dịch boot. Unit không tự kéo các service đó lên.
  Rule dùng tên interface, không cần vmnet2/vmnet3 tồn tại ngay lúc load.
- Loader khóa giữa các lần gọi, xác minh file root-owned, kiểm scope chỉ một bảng PBL4,
  rồi chạy `/usr/sbin/nft -c -f /etc/pbl4/pbl4.nft`.
- Bảng có sẵn: kiểm tương thích, giữ nguyên rule/counter/IP. Lỗi đọc kernel không được
  coi là bảng chưa tồn tại. Bảng thiếu set/chain/timeout phù hợp: dừng, không sửa bảng.
- Bảng chưa có: kiểm và nạp một giao dịch có `create table inet pbl4_demo` cùng nội dung
  ruleset. Nếu tác nhân khác tạo bảng đồng thời, giao dịch thất bại nguyên khối; loader
  đọc lại và giữ bảng tương thích. Không nối thêm rule vào bảng vừa xuất hiện.
- Không có ExecStop/ExecReload xóa bảng. `systemctl restart` không reset firewall.

## Cài đặt có kiểm tra và sao lưu

Từ `security-web/`:

```bash
command -v nft
sudo nft list table inet pbl4_demo
sudo nft -c -f scripts/pbl4.nft
```

Nếu bảng chưa có, lệnh list sẽ báo thiếu bảng; syntax check vẫn phải thành công. Đọc
ruleset trước khi tiếp tục: nó có rule ngăn đi tắt HTTP tới Web VM trên vmnet3, kể cả
khi `blocked_ips` rỗng. Đây là rule lab sẵn có trong repo.

Sau khi duyệt ruleset, cài bằng một lệnh:

```bash
sudo bash scripts/install-firewall-service.sh
```

Bộ cài kiểm scope, bảng hiện có và syntax trước khi thay file. Nó dừng nếu gặp đích
symlink, file/parent không thuộc root hoặc cho group/others ghi, hoặc systemd drop-in
chưa được rà soát. Bảng cũ không tương thích cũng làm bộ cài dừng.

Các file đích đã tồn tại được sao lưu trước khi ghi tại
`/etc/pbl4/backups/firewall-<thời gian>.<suffix>/`; file chưa từng tồn tại và trạng thái
enable trước đó được ghi vào manifest. Không ghi đè bản backup cũ.

Bộ cài chạy `systemd-analyze verify`, `systemctl daemon-reload`, `enable`, `start`,
`status` và đọc lại bảng/set. Không reboot. Nếu `sudo` đòi mật khẩu, nhập trực tiếp
trong terminal của người vận hành; không gửi mật khẩu vào chat.

Sau đó chạy **bằng user chạy backend**, không phải root shell:

```bash
systemctl is-enabled pbl4-firewall.service
systemctl status pbl4-firewall.service --no-pager
sudo nft list table inet pbl4_demo
sudo nft list set inet pbl4_demo blocked_ips
sudo -n /usr/local/bin/pbl4-firewall list-json
```

Kỳ vọng: `enabled`, `active (exited)`, helper trả JSON không hỏi mật khẩu. Nếu helper
không được phép, cơ chế boot có thể vẫn hoạt động; kiểm sudoers riêng theo
`HOST_SECURITY_SETUP.md`. Bộ cài này không mở rộng quyền sudoers.

## Kiểm tra restart không nạp trùng

Khi không có tác nhân khác sửa rule trong lúc kiểm tra:

```bash
sudo nft -a list chain inet pbl4_demo input
sudo nft -a list chain inet pbl4_demo forward
sudo systemctl restart pbl4-firewall.service
sudo journalctl -u pbl4-firewall.service -n 20 --no-pager
sudo nft -a list chain inet pbl4_demo input
sudo nft -a list chain inet pbl4_demo forward
```

Kỳ vọng: journal có `already exists; preserved`, số rule và handle giữ nguyên. Counter
có thể tăng theo traffic; các block có timeout vẫn có thể hết hạn bình thường.

## Checklist sau khi bạn tự reboot

Chỉ reboot khi đã lưu công việc và chủ động sẵn sàng; bộ cài không reboot hộ.

```bash
ip -br addr show vmnet2
ip -br addr show vmnet3
systemctl is-enabled pbl4-firewall.service
systemctl status pbl4-firewall.service --no-pager
sudo journalctl -b -u pbl4-firewall.service --no-pager
sudo nft list table inet pbl4_demo
sudo nft list set inet pbl4_demo blocked_ips
sudo -n /usr/local/bin/pbl4-firewall list-json
```

- [ ] vmnet2=192.168.10.1/24; vmnet3=192.168.20.1/24.
- [ ] Service enabled và active/exited, không lỗi syntax/quyền/Netlink.
- [ ] Table inet pbl4_demo tự có, đủ protected_ips/blocked_ips và input/forward.
- [ ] Helper đọc được blocked_ips bằng user backend.
- [ ] Khởi động Security với ENFORCEMENT_MODE=OFF, AUTO_BLOCK=false; dashboard báo
      Firewall sẵn sàng sau Làm mới.
- [ ] So DB/kernel riêng nếu dashboard vẫn báo chưa đồng bộ. Block tạm thời không
      được lưu qua reboot; OFF không khôi phục IP từ DB, bộ cài không chỉnh DB.

Nếu sau boot bảng đã có rồi bị một dịch vụ khác xóa, xem thứ tự journal. Không sửa
bằng cách tự nạp lặp hoặc khởi động lại toàn bộ nftables. Service này giữ trạng thái
oneshot, không theo dõi hay sửa ruleset thay các dịch vụ khác.

## Nâng cấu hình hoặc ngừng tự nạp

Git pull không cập nhật bản root-owned. Chạy lại bộ cài sau khi review source mới;
file được backup lại. Nếu bảng đang tồn tại, cấu hình mới chưa thay runtime; restart
vẫn giữ nguyên bảng. Không xóa bảng để ép cập nhật bằng quy trình boot này.

Để ngừng tự nạp ở lần boot sau:

```bash
sudo systemctl disable pbl4-firewall.service
```

Stop/disable service không gỡ bảng đang chạy. Khi cần phục hồi file, dùng đúng backup
do bộ cài in ra và review từng file; không phục hồi nguyên ruleset toàn máy.
