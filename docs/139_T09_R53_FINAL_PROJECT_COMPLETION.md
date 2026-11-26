# R53 — Nghiệm thu Prevention và pipeline trên AWS

**R53_FINAL_COMPLETION = PARTIAL.** Pipeline cảnh báo với runtime thật và kernel actuator đã chạy trong môi trường cô lập trên EC2. API thực thi Prevention public vẫn giữ khóa C2. UI AWS đã qua kiểm thử browser cho các thao tác trong bảng. R53 bổ sung harness nghiệm thu, giữ bản serving R52.

## Ba cấp Prevention

| Cấp độ | Trạng thái | Bằng chứng và điều kiện còn thiếu |
|---|---|---|
| 1. Manual Prevention | PARTIAL AWS cô lập | `websentinel-r53-actuator-kernel.service`, invocation `9b84cb37630145dea0d4f43c8f8df7d0`, exit 0. Hai network namespace mới, không có default route. Actuator hiện có chặn đúng peer, kernel đếm 1 drop, một set element khi gọi lại, từ chối IP server bảo vệ, Unblock và TTL khôi phục kết nối, table/peer được dọn. API quản trị thực thi vẫn bị `C2_EXECUTION_DISABLED` trong bản Rust đang phục vụ. Vì vậy chưa có thao tác dashboard nào liên kết được với lease kernel và lịch sử thực thi. |
| 2. Rule-based Prevention | PASS AWS cô lập cho detection đến quyết định, BLOCKED cho thực thi | NGINX HTTPS, Suricata, Java Audit, correlator, Rust và DB riêng dùng request thật. Rule lab tạo một alert, Hybrid `ALERT`, risk 45 và không có firewall action. Rule đúng contract chưa đề xuất block khi thiếu enforcement identity. |
| 3. AI-assisted Prevention | PASS AWS cô lập cho advisory, DISABLED cho thực thi | Scorer R37 thật trả 0,125357 với threshold 0,7664756774902344. Hybrid nhận advisory `LOG_ONLY` và giữ `ALERT` từ rule. R37 manifest giới hạn quyền ở advisory. |

Trình duyệt Security hiện đúng `ACTUATOR_OFFLINE`. Readback xác nhận `/run/ws-native-fw-status.sock` vắng mặt và `firewall_actions=0` trong DB serving. `ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false`. Native actuator của đồng nghiệp yêu cầu direct peer đã duyệt, policy scope, planner và kernel readback. Sensor loopback sau NGINX xác nhận được giao dịch HTTP để quan sát. Thiết kế hiện hành cố ý không chuyển attribution đó thành IP thực thi. API C2, protected IP, phạm vi và fail-closed được giữ. [C2](../security-web/src/prevention.rs) · [Actuator](../security-web/deploy/ubuntu-host/ip-actuator.py) · [Hybrid](../security-web/src/hybrid.rs)

## Runtime AWS cô lập

`websentinel-r53-native-observation.service` chạy trên đúng EC2 staging dưới `PrivateNetwork=yes`, chỉ loopback và không có default route. Hai PostgreSQL DB tạm do lab tạo, Java dùng jar đang phục vụ, NGINX dùng template R52, Suricata dùng rules hiện có cộng SID lab `153001` để đánh dấu một GET CSRF lành tính. Rule đánh dấu chỉ tồn tại trong thư mục tạm. R37 tạo score thật, correlator tạo receipt thật, Rust đọc source logs và SSE gửi `alert.created`. [Harness](../security-web/deploy/aws-r48/r53_runtime_lab.py)

- Request `724a1f0b3f60c2429564959d36e40d6f` trả HTTP 200 qua HTTPS với chứng chỉ lab được xác minh. Mask `NSA` trước cutoff 1.000 ms. Suricata `flow_id=1838904737098514`, `tx_id=0`, một alert SID lab và một liên kết transaction. Hybrid `ALERT`, risk 45, không có firewall action.
- Lượt kiểm triage `websentinel-r53-native-triage.service` (`182041fcbe944a3ebddaf72e289e7324`) tạo request `4cd3f142e69ec8c24b1f2bd98b251a9a` cũng có `NSA`, `SCORED`, `ALERT` và `alert.created`. Viewer nhận 403 khi ghi, admin đổi alert sang `INVESTIGATING` nhận 200, gửi lại version cũ nhận 409. DB có đúng một dòng lịch sử triage. Unit thoát 0 và peak 524,6 MiB.
- Thử X-Forwarded-For với địa chỉ dành cho tài liệu trong namespace. NGINX và Student Audit cùng ghi peer thực `127.0.0.1` và Hybrid để `trusted_client_ip=null` cho thực thi. Kết quả xác minh ranh giới attribution ở lab. Public trusted enforcement vẫn cần acceptance riêng.
- Lab chạy 18,715 s, peak 508,8 MiB, exit 0. Các source và DB lab tách khỏi ứng dụng public. R52 cung cấp regression replay/dedup và không cần ghi fixture vào DB serving. Hành vi marker xác minh việc truyền alert, correlation và policy. Chất lượng phát hiện trên traffic tấn công thực tế nằm ngoài bằng chứng này.

## Nghiệm thu chức năng và vận hành

| Hạng mục | Kết quả |
|---|---|
| `SOURCE_SYNC` | PASS. `798e66a` là HEAD đồng nghiệp tại thời điểm fetch và là ancestor của nhánh tích hợp. |
| `MANUAL_PREVENTION` | PARTIAL. Kernel actuator PASS AWS cô lập. UI/API chưa có đường thực thi được phê duyệt và chưa có đối soát audit xuyên tới kernel. |
| `RULE_BASED_PREVENTION` | PASS AWS cô lập đến Hybrid `ALERT`. Thực thi BLOCKED theo scope và C2. |
| `AI_ASSISTED_PREVENTION` | PASS AWS cô lập advisory. Execution DISABLED. |
| `FIREWALL_ACTUATOR` | PASS AWS cô lập với actuator thủ công hiện có. Native serving actuator DISABLED. |
| `TRUSTED_CLIENT_IP` | PASS so khớp quan sát và loại XFF tự khai ở lab. Trusted enforcement target BLOCKED trên leg sau proxy hiện tại. |
| `PREVENTION_READINESS` | DISABLED trên serving, socket status vắng mặt và browser hiển thị actuator offline. |
| `PUBLIC_ENFORCEMENT_STATE` / `AI_AUTO_BAN_STATE` | OFF / OFF, 0 action trên AWS serving. |
| `REQUEST_COVERAGE` | PASS theo mẫu R52 cho nhóm GET catalog và R53 cho CSRF. Route nhạy cảm giữ direct và báo evidence thực sự có. |
| `NGINX_RULES` | PARTIAL. Gateway và log thật verified, không có alert dương tính NGINX mới. |
| `SURICATA_RULES` | PASS AWS cô lập cho SID marker chạy thực tế. Rule pack staging giữ nguyên. |
| `STUDENT_AUDIT_RULES` | PARTIAL. Java Audit thật có event theo request. Nghiệm thu dương tính application-rule kế thừa fixture. |
| `CORRELATOR` / `AI_R37` / `HYBRID` | PASS AWS cô lập, bằng chứng runtime trong mục trên. 6 test correlate đạt cho scope, conflict, late và duplicate. |
| `ALERT_DEDUPLICATION` | PASS theo mẫu AWS cô lập, một alert và một transaction link. Regression replay R52 vẫn áp dụng. |
| `AWS_ISOLATED_ALERT_PIPELINE` | PASS cho GET lành tính với rule marker, dùng log, receipt và score thật. |
| `STUDENT_WEB_ALL_FUNCTIONS` | PARTIAL. Firefox AWS verified tạo/sửa/xóa Lớp và Chương trình, mở quản lý tài khoản và danh sách sinh viên. Bước xóa chờ hộp thoại `Xác nhận xóa` rồi bấm `button.btn-danger:enabled`. PostgreSQL báo 0 bản ghi catalog thử còn lại. Khoa/Ngành kế thừa R52. Chưa nghiệm thu đầy đủ ghi hồ sơ, contact và vòng đời tài khoản qua browser. |
| `SECURITY_WEB_ALL_FUNCTIONS` | PARTIAL. Firefox mở Cảnh báo, Prevention, lịch sử và trạng thái với dữ liệu staging. Triage/RBAC/lịch sử đạt qua Rust API với alert thật trong lab. Triage bằng trình duyệt và thực thi public chưa được nghiệm thu. |
| `DASHBOARD_AND_SSE` | PASS AWS theo mẫu. Browser kết nối SSE và hiển thị actuator offline. SSE lab nhận đúng alert sau commit. |
| `ENV_PRESERVATION` | PASS. Ba file env khớp từng byte với backup R52, gồm Gmail. R37 SHA `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`. |
| `AWS_DEPLOYMENT` | PASS cho deployment harness tạm thời, baseline ứng dụng serving vẫn R52. Backup R52 kiểm SHA đạt. |
| `SERVICE_STABILITY` | PASS trong cửa sổ kiểm. PostgreSQL nhận kết nối, tám unit/timer active, năm cgroup không có OOM kill, RAM 1.339 MiB, root disk 9%. |
| `GIT_PUSH` / `REMOTE_HEAD` | Xem lịch sử `feature/ai-idps-https-ml-integration`. |
| `REMAINING_BLOCKERS` | Xác minh trusted direct peer, tích hợp cổng quản trị với actuator có trạng thái và audit, phê duyệt phạm vi và đánh giá false block độc lập trước bất kỳ public execution nào. Hoàn tất các thao tác ghi browser ngoài mẫu. |
| `EC2_FINAL_STATE` | RUNNING, AWS status checks 3/3 `ok`. |

## Trình diễn và chi phí

Trên Security Web vào **AI Shadow → Tra cứu** để xem bằng chứng của request AWS serving `c5495071999bc40a04014e9160bcc2a4` từ R52, tùy retention. Alert lab R53 có request ID riêng và DB tạm đã dọn. Có thể chạy lại harness trên chính staging trong một unit mạng riêng và xem `alert.created`, `ALERT`, score và SID bằng output lab. [Security Web](https://websentinal.duckdns.org/) · [R52 evidence](138_T09_R52_FINAL_FUNCTIONAL_CLOSURE.md) · [Runbook R53](AWS_STAGING_OPERATIONS_HANDOFF.md#15-r53--nghiệm-thu-prevention-cô-lập)

Scheduler `ENABLED` mỗi 15 phút. Lambda giữ `MAX_SESSION_MINUTES=480`, `DRY_RUN=true`. AWS Budgets tại thời điểm readback ghi 1,227 USD thực tế, 2,295 USD dự báo và ngân sách 25 USD. [Runbook Billing](AWS_STAGING_OPERATIONS_HANDOFF.md#4-chi-phí-và-billing)
