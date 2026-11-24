# Cửa sổ automatic BLOCK_REQUEST của ws-i5-dev

Tất cả lệnh dưới chạy bằng root **trong guest**, sau phê duyệt. Bundle đã kiểm SHA256 đặt tại /opt/ws-auto-canary, root sở hữu, service chỉ đọc. Không thay service Beta.2 hay binary REVIEW. Thư mục journal bền vững /var/lib/ws-adaptive-dev phải do root sở hữu, mode 0700. Chỉ --init-journal trong lần provision đầu có xác nhận; nếu journal cũ mất, dừng. Dùng chung journal và kill switch với operator. Không dùng publisher cũ song song.

## Điểm duyệt 1 — listener cô lập, chưa cấp lease

```bash
set -eu
test "$(hostname)" = ws-i5-dev
test "$(cat /run/systemd/container)" = systemd-nspawn
cd /opt/ws-auto-canary
sha256sum -c SHA256SUMS
test -f /var/lib/ws-adaptive-dev/approvals.sqlite3
test -z "$(ss -Hln 'sport = :19443')"
if ! test -d /run/ws-dev-request-leases; then
  install -d -m 0750 -o root -g websentinel-evidence /run/ws-dev-request-leases
fi
test "$(stat -c '%U:%G:%a' /run/ws-dev-request-leases)" = root:websentinel-evidence:750
test ! -e /run/ws-dev-request-leases/dev-canary
systemd-run --unit=ws-auto-gate --collect -p User=websentinel-security -p Group=websentinel-evidence \
  -p RuntimeDirectory=ws-auto-gate -p RuntimeDirectoryMode=0750 -p NoNewPrivileges=yes \
  -E WS_DEV_GATE_DIR=/run/ws-auto-gate -E WS_DEV_GATE_LEASE_DIR=/run/ws-dev-request-leases \
  /opt/ws-auto-canary/pbl4-security-demo --dev-edge-gate
systemd-run --unit=ws-auto-edge --collect -p DynamicUser=yes -p SupplementaryGroups=websentinel-evidence \
  -p RuntimeDirectory=ws-auto-edge -p NoNewPrivileges=yes \
  /bin/bash /opt/ws-auto-canary/start-canary-edge.sh
```

Kiểm hai đường trả 204 và audit ghi origin tương ứng trước khi mở cửa sổ.
Chứng chỉ tạm chỉ dùng cho listener riêng trong guest, thay khi service restart.

```bash
for p in /normal /__ws_dev__/canary; do
  curl -sS -D - -o /dev/null --cacert /run/ws-auto-edge/cert.pem "https://127.0.0.1:19443$p"
done
```

## Điểm duyệt 2 — chạy tối đa năm phút

Chỉ chọn rule cũng đã bật trong policy REVIEW đang chạy. Phương án dưới duyệt APP-1012 và APP-1013 cho selector demo duy nhất. Không cho một CRITICAL đứng riêng tự chặn (dấu trừ cuối). Nếu operator phê duyệt immediate riêng, truyền tập con rule ở tham số cuối; Rust vẫn đòi severity=1, standalone=true và đạt trọng số. Một nguồn AI không cấp lease. Cửa sổ hành vi dùng tối đa 60 giây, cùng source_instance, actor và session đã xác thực, mỗi rule chỉ tính một lần dù có nhiều HTTP ID. Một request có bằng chứng ứng dụng và payload tương quan có thể đạt ngưỡng combined. Sau khi đã duyệt:

```bash
start=$(date +%s)
end=$((start+300))
systemd-run --unit=ws-auto-window --collect -p RuntimeMaxSec=310 \
  /bin/bash -ec 'while (( $(date +%s) < $2 )); do python3 /opt/ws-auto-canary/approve_session.py --auto-canary "$1" "$2" APP-1012,APP-1013 -; sleep 3; done' window "$start" "$end"
```

Tạo traffic kiểm thử được duyệt riêng qua Edge thật. Plan dùng bằng chứng **sau** thời điểm mở cửa sổ. Khi có lease, lặp hai GET bình thường ở trên. Cần thấy /normal 204 và canary 403 với upstream=-; đối chiếu ID chặn trong access.log vắng ở origin.log, journalctl -u ws-auto-gate có trigger/request. Sau tối đa 15 giây cần thấy canary 204. Cooldown ít nhất 60 giây sau deadline cũ. Dùng journal SQLite để đối chiếu decisions/audit (operator auto-canary), không xuất selector session hoặc credentials. Nếu không có incident đủ chuẩn, không được tuyên bố chặn thành công.

## Rollback

```bash
systemctl stop ws-auto-window.service   # nếu cửa sổ còn chạy
python3 /opt/ws-auto-canary/approve_session.py --action BLOCK_REQUEST --approve "$rid" --revoke  # ID trigger đã cấp lease
systemctl stop ws-auto-edge.service ws-auto-gate.service
```

Khi khẩn cấp dùng --emergency-stop thay lệnh revoke. Kill switch này rút cả các lease thủ công còn hoạt động. Giữ nguyên journal, sao lưu log thử trước khi dừng edge (RuntimeDirectory tạm). AUTO_BLOCK=false và ENFORCEMENT_MODE=OFF vẫn áp dụng với firewall. Session yêu cầu principal/session đã ràng buộc và operator; account yêu cầu xác nhận riêng, STAFF/STUDENT và thêm rule standalone severity=1 với weight >= max(95, standalone); IP không có ngưỡng auto khả dụng trên relay.
