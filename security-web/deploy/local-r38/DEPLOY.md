# Triển khai scorer HTTPS Local

Profile hệ thống đặt scorer mặc định R37 và rollback R36 vào cùng một release. NGINX, Student, Suricata và Security Web giữ lifecycle riêng. Profile user có socket riêng để chạy thử trên máy vận hành. Hệ thống đích chỉ nhận traffic sau khi xác minh CA, account, backup và health của chính máy đó.

## Chuẩn bị release

Từ gốc checkout, dùng GNU/Linux x86-64, Python có `hashlib.file_digest`, systemd có `DelegateSubgroup`, cgroup v2 được delegate, bộ cảm biến CPU tương thích và gói ACL có `/usr/bin/setfacl`. Máy nghiệm thu dùng systemd 259, Python 3.14 và thư viện CPU ONNX Runtime 1.31.1. Scorer Rust và thư viện native phải khớp [hai digest được nghiệm thu](native-dependencies.json). Xem [digest từng file](evidence/release-files.json) và [archive chuyển giao](evidence/archive.json).

```sh
python3 security-web/deploy/local-r38/package.py \
  --scorer "$RUST_SCORER" --ort "$ORT_LIBRARY" --output "$NEW_RELEASE"
(cd "$NEW_RELEASE" && python3 - <<'PY'
import hashlib, json
from pathlib import Path
for name, expected in json.loads(Path("files.json").read_text()).items():
    with Path(name).open("rb") as f:
        assert hashlib.file_digest(f,"sha256").hexdigest() == expected, name
PY
)
sha256sum "$NEW_RELEASE/files.json"
```

Ở host đích, đặt bản đã đối chiếu digest vào thư mục version riêng trong `/opt/websentinel/https/releases/`, do root sở hữu, các thư mục cho phép traversal và không cho service user ghi. Đặt symlink `/opt/websentinel/https/current` trỏ đến bản đã stage. Giữ bản trước và SHA trước để rollback. Đối chiếu digest archive từ kênh bàn giao tin cậy trước khi giải nén.

## Danh tính và thứ tự khởi động

1. Stage [sysusers](websentinel-https.sysusers) dưới tên `/usr/lib/sysusers.d/websentinel-https.conf`. Kiểm tra existing identity rồi dùng systemd-sysusers. `websentinel-edge` phải có UID/GID riêng, primary group trùng tên và không có supplementary group. Kiểm tra `getent passwd`, `getent group` và `id` trên host đích.
2. Stage [unit](websentinel-https-scorer.service) và file root-owned mode 0600 `/etc/websentinel/https-scorer.env`. Ghi `RELEASE_SHA256` bằng SHA của `files.json`, `MODEL_SLOT=candidate` và `EVIDENCE_LINEAGE` bằng deployment ID mới. Bất đồng pin hoặc safety failure trả 78 và chặn vòng restart. systemd giới hạn số lần restart khi có crash khác.
3. Dùng [drop-in NGINX](scorer-order.conf) cho `nginx.service` và [drop-in Rust](ingest.conf) cho `pbl4-security.service`. Kiểm `systemd-analyze verify` trên effective units. Scorer nhận HTTPS qua Unix socket. `SO_PEERCRED` kiểm UID. ACL cho edge ghi socket. Tài khoản Rust chỉ đọc journal qua group `websentinel-evidence`. DB/outbox ở `/var/lib/websentinel-https/private` mode 0700. Tài khoản AI không được thuộc group ký proof của edge.
4. Dùng [stage-proof-host.py](../../scripts/stage-proof-host.py) với `--https-ml-shadow --ai-mode enabled`, đúng GID và CA. Chạy [preflight và dry-run](../../scripts/deploy-proof-host.py) trên bundle. Giữ private key của hai đầu TLS, key HMAC và mật khẩu DB ngoài release. Trang bị chứng thư có SAN phù hợp. Local health qua HTTPS dùng IP SAN chứng thực cho địa chỉ bind của edge. Kiểm upstream SNI và CA riêng. Profile host có nftables guard riêng bảo vệ leg HTTP giải mã trên loopback.
5. Sao lưu trước cutover. Chạy [backup hiện hành](../../scripts/backup-security-host.sh), chụp DB trước migration, lưu SHA và xác minh restore vào DB khác. Kiểm checksum `_sqlx_migrations`, nhất là lịch sử 0014, trước khi chạy binary mới. Cấp account migration theo lịch triển khai và phân quyền DB ứng dụng theo bảng. Bản nghiệm thu dùng DB PostgreSQL dùng một lần, SQLx 19 migration. Student dùng H2 cho acceptance. Môi trường dữ liệu nghiệp vụ cần backup/restore riêng cho DB Student.
6. Bật scorer trước, kiểm health từ UID của edge. Sau đó kiểm readiness của ingest, sensor generation mới, Student Audit và request ID trên một giao dịch lành tính trước khi chuyển traffic. `Wants` cho phép HTTPS nghiệp vụ tiếp tục khi AI abstain. Chỉ apply bundle hệ thống qua quy trình snapshot + rollback của [host deployment](../https-e2e/HOST-DEPLOYMENT.md).

```sh
runuser -u websentinel-edge -- curl --fail --include --max-time 2 \
  --unix-socket /run/websentinel-edge-shadow/receiver.sock http://localhost/healthz
systemctl show websentinel-https-scorer -p MainPID -p NRestarts -p ControlGroup -p MemoryCurrent
journalctl -u websentinel-https-scorer --since today
```

Health gọi inference thật và trả SHA, không ghi receipt. Theo dõi watchdog, lần restart, `cpu.max` của leaf `ai-worker`, `memory.events`, tuổi cursor, số ABSTAIN, outbox backlog và dung lượng đĩa. Journal chỉ xuất score, version, thời điểm và request ID. Bảo vệ TTL, quyền đọc và dung lượng riêng cho EVE/access log, SQLite và backup. Chỉ archive đoạn journal sau khi đối chiếu cursor. Hạn chế quyền audit trên kho nội bộ vì log gốc có thể chứa dữ liệu nhạy cảm.

## Phục hồi và rollback

Dừng riêng scorer để chụp nhất quán thư mục state cùng journal và SQLite, kiểm `PRAGMA quick_check` và đối chiếu các receipt đã commit sau restore. Giữ cursor Rust và DB cùng thế hệ backup. Khởi động lại chỉ xử lý outbox đã commit. Không phát lại HTTPS nghiệp vụ. Với rollback model, ghi `MODEL_SLOT=rollback`, restart scorer và đòi health trả SHA R36 từ slot registry. Đảo lại về `candidate` bằng cùng quy trình. Nếu lỗi package, phục hồi cả symlink release và pin tương ứng trước restart. Nếu lỗi route, dùng backup theo lệnh rollback của host deployer. Kiểm TLS, connectivity và nft readback sau rollback. Giữ chế độ ngăn chặn đã phê duyệt.

## Profile user đã chạy

Có thể tạo lại unit riêng qua `stage_user.py ABSOLUTE_RELEASE RELEASE_SHA256 OUTPUT_UNIT`, rồi kiểm `systemd-analyze --user verify`. Khi được cài vào user manager, dùng `systemctl --user enable --now idps-r38-https-scorer.service`. Socket, state và nhật ký độc lập với bốn service R22. Health nằm tại `$XDG_RUNTIME_DIR/idps-r38-https/receiver.sock`. Dừng có chủ đích bằng `systemctl --user disable --now idps-r38-https-scorer.service`. Host nghiệm thu đã có linger bật.

## Chạy lại acceptance có giới hạn

Chạy `ai-training/contracts/https-shadow-r35/guard.py --` trước mỗi runner. `ai-training/contracts/https-model-r36/accept.py --extended --help` liệt kê binary Rust, proof verifier, Student/H2, ONNX Runtime và PostgreSQL cần thiết. Dùng output mới, sau đó chạy `https-model-r36/verify.py` cho output của lượt đó và `summarize.py RUN NEW_EXISTING_EMPTY_OUTPUT` để đối soát. Trong một namespace rootless mới, `check_permissions.py` kiểm profile UID và `firewall_acceptance.py` kiểm nftables trên veth riêng. Cả hai từ chối network namespace ban đầu.

Khi xoay sensor theo kế hoạch, tạm ngừng dispatch mới trên tuyến thử nghiệm. Sau khi generation mới báo `Engine started`, chạy `python3 security-web/scripts/proof-flow-readiness.py --timeout 5` trong đúng network namespace của edge rồi gửi canary. Helper chỉ đọc socket leg riêng đang ESTABLISHED và đợi hữu hạn cho các socket cũ đóng. Nếu ingress vẫn bận hoặc canary chưa có flow/tx/receipt hợp lệ, giữ trạng thái partial cho các request liên quan. Chỉ khôi phục traffic được điều phối sau khi kiểm xong canary. Kiểm tra mỗi request vẫn dùng cutoff 1.000 ms và guard 1 ms.
