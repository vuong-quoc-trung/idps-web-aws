# R62 — Triển khai gói Prevention và chốt phạm vi vận hành

**R62_FINAL_COMPLETION = PARTIAL.** Gói Prevention đã nghiệm thu trong
R61 được cài trên EC2 staging để chạy theo nhu cầu trong namespace C2.
Deployment kiểm SHA của bundle, runner, binary lab tái tạo và binary đang
phục vụ. Kết quả kiểm thử thực thi R58–R61 được tái sử dụng.
[Bằng chứng R61](evidence/r61/acceptance.json) · [Bằng chứng triển khai R62](evidence/r62/deployment.json)

| Hạng mục | Phạm vi đã đạt | Trạng thái public sau R62 |
|---|---|---|
| Firewall Actuator và nftables | Gói đã cài. Thực thi thật đạt trong namespace riêng ở R60–R61. | **OFF** |
| Prevention, Manual Block/Unblock và TTL | Gói đã cài. Block, Unblock, TTL và RBAC đạt ở R61. | **OFF** |
| Rule-based và Hybrid Adaptive Prevention | Gói đã cài. Hai lease thật và hai ca đối chứng đạt trong canary R61. | **OFF** |
| Database/Audit/Firewall | Đồng bộ sau thao tác, restart và cleanup ở R61. | **UNVERIFIED**. Đọc thấy 0 action và 0 lease, chưa có actuator public để đối soát. |
| NGINX, Suricata, Student Audit, AI Advisory, Correlator, Hybrid, SSE | Giữ nguyên bản phục vụ, model và threshold. | **ACTIVE**. Hai website HTTPS hoạt động. |

`nginx -T` trên EC2 xác nhận access log `r48_access` ghi `$remote_addr`
và `$request_id`, thiếu `$remote_port` và `$connection`. Bộ xác minh R61
chỉ cấp quyền cho socket thật trong namespace sở hữu. Chưa có bên phát
bằng chứng ràng buộc request public với socket NGINX, đích canary public
dành riêng và readback cùng phạm vi cho rollback. Các flag public tiếp tục
`ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false`. Dashboard tiếp tục phản ánh
trạng thái runtime và AI Auto-ban vẫn tắt. Không cấp thêm quyền hay tạo tài nguyên AWS.
[Kiểm tra trên EC2](evidence/r62/deployment.json)

## Bản đóng băng

Gói được cài tại `/opt/websentinel-r62/prevention-r61` với quyền root.
Dùng runner R61 theo nhu cầu từ SSM. Profile `r60` chạy đường manual,
profile `r61` chạy đường canary rule/Hybrid. Cả hai vẫn dùng unit có
`PrivateNetwork=yes`, TTL giới hạn và cleanup theo runner. Gói được cài
sẵn, unit không chạy nền hoặc bật lúc boot. [Trình cài](../security-web/deploy/aws-r48/r62_install.sh) · [Runbook](AWS_STAGING_OPERATIONS_HANDOFF.md#24-r62--gói-prevention-đã-cài-trên-ec2)

## Kiểm tra sau cài

Hai website HTTPS trả HTTP 200 và TLS verify 0. EC2 Running với 3/3
status checks và bảy dịch vụ active. Tệp chuyển tạm đã dọn, khu vực
C2 không có tiến trình, runtime directory hoặc cgroup đang mở. SSE kế
thừa nghiệm thu R61 trên cùng binary đang phục vụ.
