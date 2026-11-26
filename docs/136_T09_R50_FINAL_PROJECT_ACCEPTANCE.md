# R50 — Nghiệm thu email và AWS staging

**R50_FINAL_ACCEPTANCE = PARTIAL.** Kích hoạt tài khoản và khôi phục mật khẩu đã đi hết vòng đời với hai thư đến Gmail thật. Hai route quan sát mới có bằng chứng ba nguồn đúng cutoff. Phạm vi đã thử là các luồng nghiệp vụ đại diện. Nghiệm thu toàn bộ thao tác quản trị/UI và demo cảnh báo trên AWS còn mở.

## Gmail và xác thực tài khoản

- `PASSWORD_RESET_MAIL_ENABLED` và các tham số SMTP chưa có trong `/etc/websentinel-r47/student.env` của systemd. Điều kiện `PasswordResetMailService.available()` trả false trước khi tạo kết nối SMTP, dẫn đến 503 tại bước gửi. `PUBLIC_APP_URL` đã trỏ tới domain HTTPS chính thức và cookie secure đã bật. EC2 bắt tay TLS với Gmail trên TCP 587, nhận SMTP `220`, xác thực thành công và tiến trình Java sau restart nạp đủ biến. [Ứng dụng Spring Mail](../student-web/backend/src/main/resources/application.yaml) · [Cập nhật cấu hình](../security-web/deploy/aws-r48/mail_config.py)
- Chỉ bổ sung `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_FROM`, `MAIL_PASSWORD` và `PASSWORD_RESET_MAIL_ENABLED`. Các dòng Student khác và toàn bộ Security/scorer env khớp backup. Quyền backup là `0700`, file môi trường `0600`. Git chỉ theo dõi hai file `.env.example`. Transfer SMTP dùng một envelope RSA-OAEP qua SSM shell, với khóa riêng tạm trong `/run`, vì quyền SSM port forwarding bị từ chối. Dữ liệu test và giá trị bí mật nằm ngoài repo.
- Kiểm thử một học viên R50 được tạo qua API quản trị trên class đang có. Dùng alias riêng trên hộp Gmail được cấp, IMAP readonly qua TLS, tìm đúng thư gửi đến alias thử. Đối chiếu thông tin HTTP 200, gửi HTTP 202, nhận thư, mở `/activate` qua HTTPS, lấy token từ fragment thư và hoàn tất HTTP 204. Đăng nhập bằng mật khẩu vừa đặt xác minh role `STUDENT`. Token kích hoạt có hạn 24 giờ, proof đối chiếu 5 phút. Mã khôi phục có hạn 5 phút, chỉ dùng một lần theo luồng hiện hành. [Token kích hoạt](../student-web/backend/src/main/java/com/pbl4/studentweb/user/service/PasswordSetupService.java) · [Mã khôi phục](../student-web/backend/src/main/java/com/pbl4/studentweb/user/service/StudentPasswordService.java)
- Khôi phục HTTP 202, nhận thư thứ hai trong Inbox và dùng đúng mã từ thư, reset HTTP 204, đăng nhập bằng mật khẩu mới và logout. Tài khoản thử chuyển `INACTIVE`, login bị disable bằng API archive hiện hành. Session rotation và role gate Student GET `/api/users` trả 403 đã xác minh bằng HTTP thật. Hồ sơ, academic/classmates, completion, bốn nhóm liên hệ, danh sách và chi tiết class trả HTTP 200 cho API tương ứng.

## Evidence theo trusted request ID

| Hoạt động | HTTP | Request ID | Kết quả |
|---|---:|---|---|
| Đối chiếu học viên | 200 | `cc29e440c7a53db3d9b01baa57658ca3` | NGINX + Student Audit |
| Gửi email kích hoạt | 202 | `12b2549e8c8db134f49c52263d236b32` | Gmail Inbox xác nhận |
| Đặt mật khẩu từ thư kích hoạt | 204 | `69110fa1a21f8cda24ed518bff8c96dd` | Tiêu thụ token thành công |
| Đăng nhập sau kích hoạt | 204 | `669038b6926a809cb1da3155ff55d88e` | NSA tại cutoff, `SCORED`, `LOG_ONLY` |
| `GET /api/classes` | 200 | `eeebd97957daed283a0b3c8031670142` | NSA tại cutoff, `SCORED`, `LOG_ONLY` |
| `GET /api/me/completion` | 200 | `fc3f8346a882d6116fd0b119e5753dbc` | NSA tại cutoff, `SCORED`, `LOG_ONLY` |
| Yêu cầu khôi phục | 202 | `4c91f331d33a8c9eebf5020e3dda3fbc` | Gmail Inbox xác nhận |
| Đặt lại mật khẩu từ mã đã nhận | 204 | `014c5a017af75f09e8d19c442cc1cdad` | Reset thành công |
| Đăng nhập sau khôi phục | 204 | `bbe3e86fb7fe6252195834676a17ff27` | NSA tại cutoff, `SCORED`, `LOG_ONLY` |

Gateway giữ cutoff 1.000 ms và guard 1 ms, tăng từ 8 lên 10 cặp method/target chính xác. Query và dynamic route tiếp tục đi thẳng tới Student. Journal gắn nhãn cố định cho route đã biết, thay phần ID bằng `[id]`, giữ route khác là `/api/[redacted]`. AWS xác minh `GET /api/classes?page=0` (`d66206a561785c6ffcfd3c9ef45082e6`) và class detail (`03710ec1075b108754a45536b4f4b827`). Hai request này có NGINX và Student Audit, phần dispatch của leg có chữ ký rỗng. Activation/recovery cũng ghi hai nguồn theo đường trực tiếp, giữ body ngoài sensor và scorer. Để tránh URI thô, NGINX bỏ error log nguyên văn cho Student API và các trang kích hoạt/khôi phục đã cấu hình. Journal metadata vẫn giữ status và latency cho Student API. [Gateway R50](../security-web/deploy/aws-r48/gateway.py)

Mỗi dòng `NSA` có đúng một observation NGINX và một Student Audit, một correlation và một quyết định Hybrid theo cùng ID. Model R37, SHA và threshold `0.7664756774902344` giữ theo R49. Login sau kích hoạt và sau khôi phục lần lượt 764/627 ms ở NGINX và 680/614 ms trong Java Audit. `/api/classes` và `/api/me/completion` lần lượt 89/106 ms ở NGINX. Đây là hai mẫu login của tài khoản thử, đủ cutoff trong lần kiểm tra.

Đăng nhập Security Web rồi mở **AI Shadow → Tra cứu** với `eeebd97957daed283a0b3c8031670142` để xem source proof, R37 và `LOG_ONLY`. Xem mã kích hoạt hoặc reset tại **Student Audit** theo request ID trong bảng để đối chiếu event nghiệp vụ. [Security Web](https://websentinal.duckdns.org/)

## Nghiệm thu

| Gate | Trạng thái | Bằng chứng |
|---|---|---|
| `LATEST_SOURCE_SYNC` | PASS | `798e66a` là HEAD remote nhánh đồng nghiệp và đã là ancestor của nhánh tích hợp. |
| `ENV_MINIMAL_UPDATE`, `CREDENTIALS_PRESERVED`, `SECRETS_PROTECTION` | PASS | Chỉ sáu biến SMTP thay đổi. Readback process, đối chiếu backup, kiểm `.gitignore` và staged files. |
| `GMAIL_SMTP`, `EMAIL_DELIVERY`, `ACCOUNT_ACTIVATION`, `PASSWORD_RECOVERY` | PASS | STARTTLS, SMTP AUTH, hai thư Inbox và sử dụng đúng proof trong từng thư. |
| `STUDENT_WEB_ALL_FUNCTIONS` | PARTIAL | Luồng mail, auth, role và các API đọc nêu trên đã đạt. Còn các thao tác UI/CRUD ngoài mẫu. |
| `SECURITY_WEB_ALL_FUNCTIONS` | PARTIAL | 11 API đọc trên dữ liệu AWS, SSE và lookup đạt. `/api/ready` trả 503 `ACTUATOR_OFFLINE` theo readiness yêu cầu thấy actuator. Database và cả sáu watcher hoạt động. |
| `HTTPS_FLOW` | PASS | Hai public HTTPS GET trả 200, TLS verify 0. `/activate` phục vụ HTML qua HTTPS. |
| `REQUEST_COVERAGE` | PARTIAL | 10 cặp method/target quan sát đủ leg khi có proof, edge route metadata cho nhóm route còn lại. |
| `NGINX_RULES`, `SURICATA_RULES`, `STUDENT_AUDIT_RULES` | PARTIAL | Watchers native và traffic thật đã xác minh. Tình huống detection dương tính và các ngưỡng đã thử bằng fixture. |
| `RISK_SCORING`, `SECURITY_POLICIES`, `ALERT_DEDUPLICATION` | PASS trong fixture | Rust fixtures xác minh threshold, dedup, late reconciliation, role/policy và rule khi AI thiếu. AWS kiểm tra correlation/decision đơn trên request lành tính. |
| `THREE_SOURCE_CORRELATION`, `AI_R37`, `HYBRID` | PASS trong scope AWS | Bốn match đúng cutoff, cùng ID, model SHA/threshold pinned và `LOG_ONLY`. |
| `PREVENTION_MANAGEMENT` | PASS trong lab | Block/Unblock/TTL và cleanup bằng namespace cô lập. AWS đọc proposals, operation history và blocked IPs. |
| `PUBLIC_ENFORCEMENT_STATE`, `AI_AUTO_BAN_STATE` | OFF / OFF | `enforcement_mode=OFF`, 0 firewall action kiểm witness trên AWS. |
| `DASHBOARD`, `REALTIME_SSE` | PARTIAL / PASS | API thống kê, alerts, status và lookup thật. SSE `resync` qua HTTPS. UI toàn bộ còn ngoài phạm vi đã đo. |
| `AWS_ALERT_DEMO` | BLOCKED | AWS có dữ liệu `LOG_ONLY` và role-denial thật. Demo phát cảnh báo dương tính giữ ở lab. |
| `AWS_END_TO_END` | PARTIAL | Luồng mail và chain có proof đã nêu đạt. Mẫu positive alert AWS chưa có. |
| `SERVICE_STABILITY`, `RESOURCE_SAFETY` | PASS trong cửa sổ kiểm thử | Bảy unit cần thiết active, `oom_kill=0`, `NRestarts=0`, dùng 1.340 MiB RAM, root disk 9%. Timer hoạt động và `logrotate -d` đạt. Recovery scorer/boot kế thừa kết quả R48. |
| `GIT_PUSH`, `REMOTE_HEAD` | Xem Git | Commit triển khai và báo cáo trên `feature/ai-idps-https-ml-integration`. |
| `REMAINING_BLOCKERS` | PARTIAL | Phiên demo cảnh báo có đánh dấu trong môi trường AWS cô lập, các luồng UI/CRUD ngoài mẫu và đo khả năng giữ score khi request đến sát nhau. |
| `EC2_FINAL_STATE` | RUNNING | EC2 3/3 status checks `ok`, Auto-Stop `DRY_RUN=true`. |

Kiểm thử nhanh ngoài AWS gồm merge env và duplicate guard, 4 test Python correlator, 8 test Rust với PostgreSQL fixture và NGINX/njs/Suricata/R37 thật trong namespace với Student Audit fixture. Lần chạy tuần tự có khoảng cách cho 8/8 request khớp và score. Lần gửi sát nhau trước đó có 8 match và 7 score; kiểm thử này chưa định lượng nguyên nhân mất một score. Không dùng fixture làm bằng chứng delivery hoặc model quality trên AWS. [Nghiệm thu R49](135_T09_R49_FINAL_PROJECT_COMPLETION.md)

## Rollback và vận hành

- SHA-256 gateway hiện hành `a045b6bb67cf3264f9896864c753e2ba236bfea59156393efbac074f401d318d`. Hai manifest backup tại `/var/backups/websentinel-r50-mail` và `/var/backups/websentinel-r50-gateway` có SHA `263633159ac10e413a2c27cb6cdd2108ae4fbc4dff6955a933b72bad37d11695` và `7594d7934a67c436ecabbc0fae9b232a9fc8549e08fb047646dd45d8b22d6cca` tương ứng. SHA readback và `pg_restore --list` đạt. [Runbook](AWS_STAGING_OPERATIONS_HANDOFF.md#12-r50--gmail-và-kiểm-tra-readiness)
- Scheduler `ENABLED`, `rate(15 minutes)`, Lambda `MAX_SESSION_MINUTES=480` và `DRY_RUN=true`. AWS Budgets đọc **1,227 USD** actual, **2,295 USD** forecast và trần **25 USD** ở thời điểm bàn giao. Budget là snapshot có độ trễ. EC2 tiếp tục chạy theo yêu cầu. [Chi phí](AWS_STAGING_OPERATIONS_HANDOFF.md#4-chi-phí-và-billing)
