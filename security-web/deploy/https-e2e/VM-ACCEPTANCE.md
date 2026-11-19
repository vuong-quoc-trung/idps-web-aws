# Nghiệm thu installer/lifecycle trên VM dùng một lần

**Không chạy các lệnh sudo dưới đây trên Ubuntu Security Host.** Chọn VM Ubuntu
riêng, snapshot được, PID1/systemd/kernel/cgroup/nftables riêng. Network namespace
trên Host không đáp ứng điều kiện này. Container dùng systemd/privileged và mount
Host /run, /etc, /sys cũng không được dùng thay VM.

## Chuẩn bị VM (người vận hành thực hiện)

1. Tạo VM mới tên dễ phân biệt, ví dụ `ws-installer-disposable`. Không dùng Student
   VM hoặc Defender production. Copy repository (kể cả thay đổi chưa commit) qua
   archive; không mount thư mục production, SSH agent, Docker socket hoặc thư mục
   chia sẻ có quyền ghi. Không copy private key/DB/log/session production.
2. Khi còn mạng, cài NGINX **1.28.3**, module njs **0.9.4** tương thích ABI từ cùng
   bộ đã thử, Suricata **8.0.3**, Python3+PyYAML, openssl, curl, iproute2, nftables,
   util-linux và công cụ useradd/groupadd. Không đưa lệnh apt không ghim phiên bản
   vì repository Ubuntu có thể cung cấp phiên bản khác. Kiểm tra đường dẫn binary
   `/usr/sbin/nginx`, `/usr/bin/suricata`, module root-owned không ghi được bởi user.
3. Đảm bảo VM không có cấu hình WebSentinel cũ/drop-in tùy chỉnh. Tạo snapshot
   **clean-before-installer-test** sau khi có package và code. Có console VMware
   trước khi ngắt mạng; không dùng SSH cho bài này.
4. Ghi lại machine ID Security Host bằng `cat /etc/machine-id` (chỉ đọc, không sudo).
   Ghi riêng machine ID VM bằng cùng lệnh trong VM. Hai ID phải khác nhau.
5. Tắt tất cả NIC ngoài `lo` trong VM từ console; ngắt cả NAT/bridged/host-only ở
   hypervisor. Ví dụ *trong VM*, thay ens33 bằng tên thực tế:

```bash
sudo ip link set ens33 down
ip -br link
systemd-detect-virt --vm
cat /proc/1/comm
cat /etc/machine-id
```

Harness từ chối nếu NIC ngoài lo còn flag UP, không phải VM, PID1 không phải
systemd, không có cgroupv2, ID trùng production hoặc sai ID VM. Đây là chốt chống
nhầm môi trường, không phải bằng chứng chống root cố ý khai báo sai machine ID.

## Phạm vi tác động — CHỈ trong VM bỏ được

`test-proof-host-vm.py` thật sự tạo UID/GID `websentinel-edge`; sửa NGINX/Suricata
unit và config trong VM; chạy daemon-reload/start/restart/stop; tạo bảng nft riêng;
xóa bảng thử nghiệm; kill master/supervisor; tạo khóa và chứng chỉ lab mới.
Nó thêm 192.168.10.1/32 và 192.168.20.10/32 vào **lo của VM**, chạy HTTPS Student
mock tại địa chỉ thứ hai và Unix datagram AI collector giả. Không kết nối Student
Web thật/DB/AI Worker/Dashboard. Dùng installer, renderer và supervisor hiện có,
không thay mock cho các lệnh systemd/nftables của bài đặc quyền.

Bản config baseline VM được dựng để kiểm tra rollback, không phải bản sao nguyên
production. CA lab tạo mới tự ký; không lấy CA private key từ Host. Bundle được tạo
ở /root/ws-proof-vm-test, key runtime ở /etc/nginx/pbl4-proof. Chỉ riêng môi trường
VM mới được phép thay đổi các đường dẫn này.

## Lệnh chạy trong VM từ console

Thay ba giá trị bằng thông tin đã đối chiếu; không lấy production ID bằng lệnh
cat trên VM. Dùng module njs đã cài/giải nén ổn định và root-owned trong VM.

```bash
cd /duong/dan/idps-web-aws
sudo python3 security-web/scripts/test-proof-host-vm.py \
  --vm-machine-id '<32-hex-cua-VM>' \
  --production-machine-id '<32-hex-cua-Security-Host>' \
  --module /usr/lib/nginx/modules/ngx_http_js_module.so \
  --ack-disposable-vm-destruction
```

Không dùng `python -O`; harness từ chối khi assertions bị tắt. Không chạy script
nhiều lần trên VM đã bẩn; revert snapshot trước lần tiếp theo. Script không gọi sudo
nội bộ, không tải/cài package tự động. Precondition lỗi không được xem là PASS.

## 16 case bắt buộc và tiêu chí

| Case | PASS khi |
|---|---|
| identity | Tạo account/group riêng, nologin, identity validator xác nhận độc quyền |
| apply | Preflight/dry-run/apply thật thành công, heartbeat mới, HTTPS FE200/API401, không rò proof |
| key_permissions | Root sở hữu 0640, đúng GID; worker đọc được, nobody không đọc, worker không ghi |
| module_permissions | Module root-owned, không group/world writable, worker đọc được và NGINX load thật |
| ai_socket | Request đi qua Edge tạo đúng một datagram có request ID ở Unix socket mock |
| log_cache_site_permissions | UID mới phục vụ asset, POST 32KiB qua body temp và ghi access log; không Permission denied |
| restart_rotation | Restart đổi cả epoch/key, HTTPS hoạt động lại |
| reload_refused | systemctl reload thất bại, service vẫn chạy, key không đổi, HTTPS vẫn hoạt động |
| master_crash | SIGKILL master làm supervisor đóng listener/xóa readiness và key; start lại đổi key/epoch |
| supervisor_crash | SIGKILL supervisor dọn worker qua systemd, heartbeat hết hạn; start không nhận stale policy; phục hồi riêng bảng VM rồi rotate |
| guard_deleted | Xóa đúng bảng VM được phát hiện, listener đóng, key xóa, policy trở về deny-only |
| key_missing | Xóa khóa làm listener đóng và policy deny-only; start lại phục hồi |
| bad_config | Syntax lỗi khiến start thất bại, không listener/readiness/key; sửa fixture rồi start lại |
| rollback | Restore nội dung từng file theo hash và trạng thái service; bỏ file vốn không tồn tại |
| nginx_start_failure | ExecStartPre=/usr/bin/false gây lỗi khởi động thật; installer trả lỗi và phục hồi baseline |
| suricata_start_failure | Fault tương tự ở Suricata; NGINX/Suricata baseline đều được phục hồi |

Dừng ở case thất bại đầu tiên; các case sau NOT_RUN. Không PASS tổng khi thiếu case,
FAIL hoặc cleanup lỗi. Kết quả ở `/root/ws-proof-vm-test/results.json` (0600), gồm
version/hash module, trạng thái từng case; không chứa key/cookie/proof thô.

## Phân biệt kết quả và giới hạn

- Unit/mock mới chỉ kiểm tra chốt VM và tổng hợp kết quả; installer mock vẫn riêng.
- Chưa chạy harness sudo trong phiên chuẩn bị này: **16 case đặc quyền NOT_RUN**.
- PASS VM không bằng PASS production. Quyền site/log/cache/AI được kiểm tra trên
  fixture VM. Trước deploy, lập bảng từng đường dẫn thật, owner/mode/ACL, AppArmor,
  quyền traverse thư mục, cache/temp, log rotation và quyền socket sau AI restart.
- Fixture kiểm tra body temp, chưa nghiệm thu tất cả proxy-cache/static/websocket
  và các site trên Host. Không sửa quyền production từ suy luận fixture.
- Vô hiệu reload là thay đổi vận hành: certbot, logrotate và automation gọi reload
  phải được rà soát. Bài test chỉ chứng minh reload bị từ chối mà lưu lượng hiện
  tại còn hoạt động; không chứng minh các automation cũ vẫn tương thích.
- Supervisor SIGKILL có thể để file heartbeat/key cũ; TTL và stale-policy refusal
  là chốt, không khẳng định file luôn biến mất ngay. Root/worker UID compromise,
  timing HMAC, journal/revocation/response completion vẫn chưa được nghiệm thu.
- Suricata ở bài này là daemon thật và syntax/start thực; bộ 15/15 Live E2E vẫn là
  bài riêng cho SID/Lua/proof. Không nhân kết quả SID cũ thành assertion mới.

## Dọn dẹp và lấy bằng chứng

`finally` dừng NGINX/Suricata và đóng mock. Nó **không cam kết khôi phục toàn bộ VM**:
account, unit, IP lo, deny table, log và bundle có thể còn, đặc biệt sau crash.
Không dùng VM này phục vụ thật hoặc nối lại mạng khi còn fixture.

1. Xem report tại console bằng `sudo cat /root/ws-proof-vm-test/results.json`.
2. Nếu FAIL, xem `sudo journalctl -u nginx -u suricata --no-pager -n 100` trong VM;
   không chia sẻ private key hoặc nguyên bundle. Có thể gửi report và đoạn lỗi đã
   kiểm tra. Nếu bị ngắt trước khi có report, coi bài chưa hoàn thành.
3. Export report ra phương tiện riêng (chỉ JSON), tắt VM rồi **revert snapshot
   clean-before-installer-test hoặc xóa VM**. Không dùng cleanup bằng flush nft trên
   Host. Không copy key test vào production, không giữ snapshot chứa key để triển khai.
4. Chỉ sau khi revert mới nối lại NIC. Các script production apply vẫn cần phê
   duyệt riêng. Không bật Verified/AUTO_BLOCK kể cả khi VM đạt 16/16.
