# Hybrid prevention — profile dev i5

## Chế độ

Binary biên dịch với `cargo build --locked --release --features dev-hybrid-review` mới có đánh giá bổ sung. Bản phát hành Beta.2 và build mặc định không chứa module này. `WS_DEV_HYBRID_MODE=LOG_ONLY` (mặc định) giữ quyết định Hybrid hiện hữu. `REVIEW` tính thêm `incidents[].dev_prevention` trong API Hybrid, ghi vào audit theo fingerprint hiện hữu. `ENFORCEMENT` bị từ chối; worker tiếp tục phát hiện theo policy gốc. Luôn giữ `AUTO_BLOCK=false`, `ENFORCEMENT_MODE=OFF` và helper của guest ở `/bin/false`.

Ví dụ **chỉ để review**, các trọng số là tham số thử nghiệm. Khi chuẩn bị binary dev trong bản sao profile, cung cấp hai biến dưới đây cho Rust. Đo tỷ lệ báo sai trước khi cấp quyền standalone cho bất kỳ rule nào. Chưa cần sửa systemd hay env của guest đang phục vụ.

```bash
export WS_DEV_HYBRID_MODE=REVIEW
export WS_DEV_HYBRID_POLICY='{"rules":[{"source":"SURICATA","rule":"SURICATA: SID 1000002: SQL Injection Boolean or Union Attempt","weight":70,"standalone":false,"max_severity":2},{"source":"STUDENT_AUDIT","rule":"APP-1013","weight":65,"standalone":false,"max_severity":2}],"combined":120,"standalone":95,"fresh_seconds":60,"r37_weight":55}'
```

Rust yêu cầu rule khớp chính xác nguồn, tên/code, mức độ, liên kết request/transaction và độ mới. Rule `standalone:true` còn phải đạt severity 1 và trọng số standalone. Trọng số payload lấy max giữa NGINX, Suricata HTTP và R37; quyết định đã xác nhận từ Student tạo nhóm độc lập. R37 đọc đúng slot đã được Rust kiểm tra tại ingest. R37 trên ngưỡng có thể bổ trợ nhóm payload, một mình chỉ REVIEW. Chứng cứ mâu thuẫn về transaction không đủ điều kiện. `evidence_eligible` đánh giá chứng cứ; `action` còn xét danh tính có thể thực thi. Cả hai đều là dry-run.

## Danh tính và điểm chặn

Xác nhận guest trước nghiệm thu bằng `ip -br addr`, `ip route` trong ws-i5-dev và đối chiếu đúng request tại ingress. Relay socket-proxyd khởi tạo kết nối mới vào loopback guest. Trong cấu hình này Rust không có danh tính IP đầu xa đủ tin cậy; một header do client cung cấp không chứng minh danh tính đó. Cấm ban IP của relay, Edge/Egress và gateway. Ngay cả nếu biết IP thật qua metadata, firewall trong guest không thể drop gói theo source IP đầu xa khi kernel guest chỉ thấy relay. Muốn thử packet enforcement, dùng đường TCP trực tiếp của peer trong hai namespace thử riêng. Giữ đường vận hành VMware hiện tại.

## Nghiệm thu lặp lại

Từ thư mục `security-web`, chạy bằng user thường trên máy dev có Rust, jq, nft, iproute2 và unprivileged user/network namespaces:

```bash
set -e
cargo test --locked --features dev-hybrid-review --bin pbl4-security-demo hybrid_review::tests
manifest=$(mktemp)
cargo test --locked --features dev-hybrid-review --bin pbl4-security-demo \
  --no-run --message-format=json > "$manifest"
binary=$(jq -r 'select(.executable != null) | .executable' "$manifest")
evidence=$(mktemp)
outer=$(readlink /proc/self/ns/net)
unshare -Urn python3 -B deploy/dev-i5/test_hybrid_namespace.py "$outer" "$binary" "$evidence"
cat "$evidence"
```

Nếu chạy từ trong guest, cần có repo, test binary tương thích, Python, iproute2, nft và hỗ trợ namespace lồng. Có thể mang test binary build sẵn và cây scripts/deploy vào môi trường thử để bỏ qua bước build. Nếu user namespace bị từ chối, dừng; không chạy helper trực tiếp trên namespace mặc định, không thêm quyền vào dịch vụ đang chạy. Harness dùng peer thật trên veth tạm, dữ liệu detector fixture, policy Rust test và actuator thật. Khoá feature production vẫn đóng. Lỗi giữa chừng được dọn theo vòng đời namespace. Đây không phải nghiệm thu telemetry live tới firewall của ứng dụng.

Với PostgreSQL **test riêng** đã cấp quyền tạo database cho SQLx, chạy `cargo test --locked --features dev-hybrid-review`. Test của dev đối chiếu request/event key của Student Audit, chạy refresh hai lần, kiểm chứng đúng một decision audit, các alert gốc được giữ và không có firewall action. Không dùng DATABASE_URL của guest đang phục vụ.

## Điều kiện trước khi xét mở chặn

- Chứng minh danh tính thật và điểm thực thi nhìn thấy cùng IP bằng traffic kiểm soát, bao gồm request qua relay, IPv4 nội bộ bảo vệ, allowlist và sự kiện đến muộn.
- Chốt rule/phiên bản đủ độ chính xác trên dữ liệu benign đại diện. Tập trọng số review chưa được hiệu chuẩn chống false positive.
- Hybrid hiện lấy tối đa 128 request gần nhất mỗi lượt; cần checkpoint/work queue trước khi hứa xử lý mọi sự kiện dưới tải. Cần re-evaluate theo thời điểm xử lý, khóa chống replay và đi qua một hàng đợi chung. Rà soát cả enqueue AUTO cũ trong ingest.
- Nghiệm thu đường Hybrid → quyết định được ủy quyền → worker → packet drop → đối soát kernel/audit bằng traffic có danh tính xác minh. Kiểm tra cấu hình đổi, race, restart, hết hạn, lỗi helper và rollback. Kill switch phải chặn job mới và cho phép dọn riêng block hệ thống sở hữu. Giữ guard của local egress và các bảng VMware tách biệt.
