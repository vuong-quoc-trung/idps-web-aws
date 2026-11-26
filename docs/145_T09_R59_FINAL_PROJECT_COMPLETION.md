# R59 — Nghiệm thu Prevention và phạm vi vận hành AWS

**R59_FINAL_COMPLETION = PARTIAL** · **26/11/2026**

Giám sát AWS và bản vá bảo vệ hàng đợi đã nghiệm thu. Public Enforcement
giữ **OFF**. Hybrid hoạt động với AI advisory. Manual Block/Unblock và TTL
có bằng chứng trình duyệt với kernel thật từ R58 trong namespace cô lập.
Các điều kiện chặn công khai chưa đạt. [Nghiệm thu R58](144_T09_R58_FINAL_PROJECT_COMPLETION.md) · [Bằng chứng R59](evidence/r59/acceptance.json)

## Phát hiện và bản sửa

- Bộ ingest từng có thể ghi tác vụ `AUTO/PENDING` chỉ dựa trên cờ policy
  và rule match. Worker bị C2 chặn nhưng hàng đợi vẫn tồn tại. R59 yêu cầu
  capability tự động và danh tính đã xác minh trước khi ghi. Worker kiểm
  quyền lần nữa với tác vụ đã tồn tại. Bộ lọc rule và Dashboard dùng
  cùng điều kiện hiệu lực. Các cảnh báo và cấu hình rule hiện có được
  giữ.
- API duyệt đề xuất Hybrid kiểm khả năng đọc actuator trước khi nhận
  thao tác. Quyết định có điểm HTTPS đến đúng hạn ghi lý do advisory.
  Điểm, threshold, chính sách quyết định và quy tắc chống đếm lặp bằng
  chứng giữ nguyên.
- Regression xác nhận candidate rule ở cả ba chế độ cấu hình
  `OFF`, `MANUAL`, `ENFORCE` vẫn ghi alert. Khi thiếu capability,
  hàng đợi tự động rỗng và worker không gọi actuator. Tổng cộng **26
  lượt kiểm thử Rust** có chọn lọc, gồm cấu hình build mặc định và
  `isolated-c2`. [Guard](../security-web/src/prevention.rs) · [Enqueue](../security-web/src/ingest.rs) · [Worker](../security-web/src/firewall.rs) · [Hybrid](../security-web/src/hybrid.rs)

## Bằng chứng AWS và điều kiện công khai

Sau deploy, một GET CSRF lành tính có ID
`9196ad0d4b696cfaf877c73f56032c2d`. NGINX và Student Audit đồng ý về IP
quan sát. Suricata nối được cùng transaction trên **loopback sau NGINX**.
Correlator ghi đủ NSA, không late. AI nhận bằng chứng sau **2,335 ms**,
Hybrid ghi đúng một incident `LOG_ONLY` kèm lý do advisory.
`trusted_client_ip` của Hybrid vẫn rỗng. Bằng chứng này xác nhận tương
quan HTTP và ghi nhận IP tại edge. Nó chưa ràng buộc danh tính đó với
điểm cưỡng chế tại kernel. [Read-only probe](../security-web/deploy/aws-r48/r59_preflight.py)

Trực tiếp trên EC2, `ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false`.
Không có socket trạng thái, capability lab hoặc table nftables public
của WebSentinel. Đọc kernel được nhưng không có deployment firewall
công khai để đối soát với Database/Audit. PostgreSQL có **0** tác vụ
firewall, **0** lease đang hoạt động. Báo cáo giữ trạng thái
`UNVERIFIED` cho đồng bộ public. Inbound của Security Group chỉ mở TCP
80 và 443 cho IPv4. Không thay đổi Security Group.

| Thành phần | Trạng thái R59 | Phạm vi bằng chứng |
|---|---|---|
| NGINX, Suricata, Student Audit | ACTIVE | Request thật qua ba nguồn. Detection dương tính độc lập kế thừa lab R58. |
| AI, Correlator, Hybrid | ACTIVE / ADVISORY | Model HistGradientBoosting URI100 và threshold 0,7664756774902344. Một incident đúng request. |
| SSE, Dashboard | PASS theo phạm vi | HTML và HTTPS kiểm lại trên AWS. Bằng chứng SSE trình duyệt trực tiếp kế thừa R58. |
| Actuator, nftables, Manual Block/Unblock, TTL | PASS lab R58, BLOCKED public | Namespace lab có DB/Audit/kernel thật. Public chưa có capability và phạm vi cưỡng chế được xác minh. |
| Rule-based Automatic, Hybrid Adaptive | OFF | Regression chặn enqueue và apply nếu thiếu quyền. Chưa nghiệm thu khả năng chặn tự động public. |
| DB/Firewall public | UNVERIFIED | 0 tác vụ và 0 lease. Không có table/scope được cấp quyền để xác minh đồng bộ. |
| Public Enforcement | OFF | Chưa có proof IP tại điểm cưỡng chế, capability C2 public và rollback firewall theo scope. |
| AI Auto-ban độc lập | OFF | Chưa có cohort native hai lớp độc lập đạt T07. |
| AWS deployment | PASS cho bản vá | Chỉ restart Security Web. Hai hostname HTTPS 200, bảy unit active, EC2 running 3/3. |
| Backup và cleanup | PASS | Hai DB dump, bản R58, cấu hình, SHA và rollback runner. Các file chuyển bundle của R59 đã được dọn. |

R37 từng đạt recall **86,04%**, FPR **0,41%** trên WAF development holdout.
Trên SR-BH TUNING với cùng ngưỡng, recall **70,93%**, FPR **2,07%**. Các
kết quả này chưa đủ để cấp quyền chặn độc lập. [Đánh giá R37](121_T09_R37_FINAL_AI_QUALITY_AND_MODEL_FREEZE.md) · [Protocol T07](../ai-training/contracts/evaluation-v1/protocol.json)

## Bàn giao vận hành

Bản deploy chỉ thay binary backend. Digest của frontend, model và cấu
hình Student Web, Security Web, scorer, NGINX đã đối chiếu. Backup
`/var/backups/websentinel-r59` xác minh SHA và giữ bản phục hồi R58.
Có một phản hồi 502 trong lúc restart, sau đó smoke và kiểm tra sống đều
đạt. Rollback runner đã được cài và kiểm checksum. Lượt này không kích
hoạt rollback trên AWS sau khi deploy đạt. [Runner và rollback](../security-web/deploy/aws-r48/r59_deploy.py) · [Runbook](AWS_STAGING_OPERATIONS_HANDOFF.md#21-r59--giám-sát-và-điều-kiện-prevention)

Gate kỹ thuật kế tiếp là chứng minh trên ingress cô lập rằng một request
có thể gắn với peer thật tại cùng điểm kernel sẽ áp dụng lease. Bài thử
cần kiểm xung đột danh tính, protected scope, hết hạn, restart và rollback.
Một phê duyệt riêng cho scope cụ thể chỉ có ý nghĩa sau khi có bằng chứng đó.
