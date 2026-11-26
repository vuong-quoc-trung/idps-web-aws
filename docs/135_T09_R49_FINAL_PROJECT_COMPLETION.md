# R49 — Tích hợp và nghiệm thu AWS staging

**R49 = PARTIAL.** Bản cập nhật đã chạy trên EC2 staging. Bốn API đọc danh mục mới và một lần đăng nhập có đủ bằng chứng ba nguồn tại cutoff, điểm R37 và quyết định Hybrid `LOG_ONLY`. Phạm vi ký proof hiện gồm tám cặp method/target. Kiểm thử R49 bao phủ các route đại diện và dữ liệu hợp lệ. Phần trình diễn cảnh báo trên AWS và nghiệm thu toàn bộ API vẫn còn mở.

## Bản cập nhật

- Nhánh tích hợp đã chứa `798e66a462dd29426772146bff7c02ad6acead1f` từ `dev/i5-hybrid-prevention` qua lần tích hợp R47. R49 dùng lại source và binary đó.
- Gateway chuyển các GET chính xác của `/api/profile-options`, `/api/faculties`, `/api/majors` và `/api/training-programs` qua leg quan sát có chữ ký. Bốn cặp auth của R48 vẫn trong danh sách. Các Student `/api/` còn lại đi thẳng tới origin và chỉ ghi evidence NGINX. Journal mới ghi route đã chuẩn hóa hoặc `/api/[redacted]`, số byte, latency và cờ rule dạng số. Query, body, cookie và token nằm ngoài định dạng journal. Ba nguồn và AI chỉ được ghi khi có proof tương ứng. Việc ẩn path giới hạn các rule cần đường dẫn chi tiết ngoài danh sách.
- Refresh kiểm tra EC2 identity qua IMDSv2, revision R47, SHA gateway R48, SHA R37, trạng thái enforcement, dung lượng trống và số migration thành công (Student 2, Security 20). Stage có manifest SHA. Unit `websentinel-r49-update.service` kết thúc mã 0 với invocation `26bf4512df4540138ef8e66257c08536`. `nginx -t`, restart correlator, reload NGINX và health probe đạt. Java, Rust, scorer, sensor và PostgreSQL giữ PID đang chạy trong lần cập nhật.
- Root backup `/var/backups/websentinel-r49` có quyền `0700` và gồm active release, cấu hình gốc, runtime cũ và hai logical dump. `pg_restore --list` và SHA readback đạt. `cmp` xác nhận `student.env`, `security.env` và `scorer.env` giống từng byte với bản backup. Số biến thêm hoặc sửa là **0**. Git chỉ quản lý các file `.env.example`. [Gateway](../security-web/deploy/aws-r48/gateway.py) · [Updater](../security-web/deploy/aws-r48/refresh.py)

## Bằng chứng AWS

Đo ngày 26/11/2026 khoảng 07:56 ICT trên EC2 staging, qua HTTPS với hostname và CA hợp lệ trong guest. Các giá trị latency dưới đây là mẫu đơn. Cột R37 đo từ dispatch tới clock availability của score. NGINX, EVE/Lua và Java Audit có cùng trusted request ID. Evidence có trước cutoff 1.000 ms theo quy tắc timing R48. Mỗi request có một bản ghi NGINX, một Student Audit và một Lua observation khớp. Các API danh mục trả HTTP 200 và login trả HTTP 204.

| API | Trusted request ID | HTTP header (ms) | R37 (ms) | Mask / Hybrid |
|---|---|---:|---:|---|
| GET `/api/profile-options` | `34101f49a717755fb53fdb815d65931c` | 56,12 | 2,668 | `NSA / LOG_ONLY` |
| GET `/api/faculties` | `0a19b0077d4f2ae3a1562588e7577029` | 83,74 | 2,069 | `NSA / LOG_ONLY` |
| GET `/api/majors` | `598d7a18d90a99b7dbc324f076b92549` | 24,24 | 2,552 | `NSA / LOG_ONLY` |
| GET `/api/training-programs` | `7493faa11857ce112c71c35e687546b6` | 64,85 | 2,275 | `NSA / LOG_ONLY` |
| POST `/api/auth/login` | `8e0d975d809bb4bfe9c3ca45b69fe211` | 625,46 | 9,448 | `NSA / LOG_ONLY` |

- `GET /api/faculties?page=0` trả HTTP 200, có đúng một observation NGINX và không có correlation hoặc score. Local cũng xác minh fallback với query và route ngoài danh sách. Student CSRF, session rotation, `ADMIN`, logout và cookie cũ trả 401 đã đạt.
- Login lần này hoàn tất trong 625,48 ms. Java Audit ghi 610 ms. Trong cửa sổ login, cgroup Student dùng 268.095 µs CPU và tăng 357.413 µs throttled time qua 6 kỳ. Kernel readback Student `40000 100000` và parent `150000 100000`. R48 ghi 2,66–2,99 s trong các lượt login chậm. R49 xác định phần lớn thời gian của lượt đo nằm trong ứng dụng. Số đo cgroup bao gồm các luồng cùng service và chưa tách được BCrypt, truy vấn DB và từng bước Spring Security. Chưa có bằng chứng độ trễ đã ổn định qua cold start hoặc tải đồng thời. [Kết quả R48](133_T09_R48_AWS_CLOUD_BETA.md)
- Public GET `/` trên cả hai website trả HTTP 200 và TLS verification code 0. Trong guest, Security admin đọc Rules, Status, Application Audit, Prevention Proposals và Blocked IPs. API evidence/SSE/prevention trả 401 khi chưa xác thực. SSE xác thực trả `event: resync`. UI được phục vụ và API Dashboard xác minh được dữ liệu thật. Kiểm thử sự kiện alert mới chạy bằng fixture cô lập. [Student Web](https://student-dut.duckdns.org/) · [Security Web](https://websentinal.duckdns.org/)
- Để xem mẫu, đăng nhập Security Web bằng tài khoản AWS staging đã cấp, mở mục AI Shadow và tìm một request ID trong bảng. Xem bảng Three-source và quyết định Hybrid cho cùng request. Có thể đối chiếu qua các API `/api/ai-shadow?request_id=…` và `/api/hybrid-incidents?request_id=…`. Các ID trên là mẫu R49 `LOG_ONLY`, thuộc retention hiện hành. [Màn hình AI Shadow](../security-web/frontend/src/AiShadow.tsx)

## Gate nghiệm thu

| Hạng mục | Kết quả và phạm vi |
|---|---|
| Source, môi trường, credentials, secrets | PASS. HEAD đồng nghiệp đã tích hợp, cấu hình AWS khớp backup, `.env` bị ignore. |
| HTTPS end-to-end | PASS cho hai public vhost và đường quan sát Student đã kiểm tra. TLS kết thúc ở NGINX, leg nội bộ HTTP chỉ listen loopback. |
| NGINX / Suricata / Student Audit rules | PARTIAL. Ba nguồn live đã ghi bằng chứng cho request đại diện. Cờ rule NGINX đi vào journal, EVE/Lua tạo bằng chứng và Audit có event native. Nghiệm thu rule dương tính dựa trên fixture cô lập, chưa có demo cảnh báo AWS được đánh dấu. |
| Risk scoring / security policies | PASS trong fixture đại diện. Scope từ proxy, threshold, phía actor, quyền admin/viewer và chống cộng phiếu từ AI/rule đã qua test. AWS quan sát `LOG_ONLY` với mẫu lành tính. |
| Correlation / duplicate handling | PASS trong phạm vi thử. 5/5 match đơn tại cutoff, regression Rust bao phủ replay, giao dịch đến muộn và đếm bỏ trùng. Bao phủ ba nguồn ngoài 8 cặp method/target còn PARTIAL. |
| AI R37 / Hybrid | PASS cho inference AWS và quyết định `LOG_ONLY`. Model `r37-hgb-uri100-v1` giữ threshold `0.7664756774902344`. Kế thừa R48 cho ABSTAIN và hồi phục scorer. R36 rollback giữ sẵn. |
| Prevention Management | PASS trong namespace cô lập với Block/Unblock/TTL, chặn target bảo vệ, không nhân đôi entry và cleanup. Trạng thái đọc quản trị AWS kiểm tra đạt. |
| Public firewall / AI auto-ban | OFF / OFF. Số AWS `firewall_actions` ghi nhận là 0 tại nghiệm thu. |
| Student Web / Security Web | PASS cho HTTPS, auth và nghiệp vụ đọc đã thử. |
| Dashboard / Realtime SSE | Dashboard PARTIAL theo phạm vi API và lookup đã thử. SSE PASS trong phạm vi auth và `resync`. |
| AWS end-to-end | PARTIAL. Chuỗi thật hoạt động cho các ID trong bảng. Full route coverage, phép thử tải và demo alert AWS còn mở. |
| Service stability / Resource safety | PASS trong cửa sổ kiểm tra. Dịch vụ cần thiết active, `oom_kill=0` ở năm cgroup ứng dụng/AI/sensor, RAM 1.295 MiB đang dùng trên 7.775 MiB và root disk 9%. Giữ quota và Cloud Resource Safety Profile R48. Timer rotation active, cấu hình qua `logrotate -d` với chu kỳ ngày, tối đa 3 bản cũ và ngưỡng 8 MiB kiểm mỗi 5 phút. |
| EC2 | RUNNING, status 3/3 `ok` lúc readback. |

Local regression dùng NGINX, njs, Suricata và R37 thật trong namespace với origin Audit fixture, 6/6 request match và score đúng hạn. Bốn test Python correlator và sáu test Rust chọn lọc đạt. PostgreSQL fixture đã được dọn. Prevention lab tạo đúng một packet drop, vượt test duplicate, unblock, TTL và gỡ table. R48 cung cấp bằng chứng boot/restart và failover của các thành phần giữ nguyên. [R49 Prevention fixture](../security-web/deploy/local-r38/firewall_acceptance.py) · [R48 acceptance](133_T09_R48_AWS_CLOUD_BETA.md)

## Runtime, chi phí và rollback

- Scheduler `ENABLED`, `rate(15 minutes)`. Lambda đang đặt `MAX_SESSION_MINUTES=480`, `DRY_RUN=true`. EC2 vẫn chạy theo yêu cầu bàn giao. Phiên chạy từ 25/11/2026 13:27 UTC đến lúc readback khoảng 11,6 giờ, tương đương khoảng **1,39 USD** compute theo ước tính R45 `0,1197 USD/giờ`, trước EBS, EIP, thuế và credit. 100 giờ/tháng tương đương **21,38 USD** trong kịch bản R45. Hóa đơn và credit thực tế cần đọc ở Billing. [Giá giả định và ngân sách R45](130_T09_R45_AWS_INFRASTRUCTURE_ACCEPTANCE.md#billing-và-ngưỡng-chi-phí) · [Runbook Billing](AWS_STAGING_OPERATIONS_HANDOFF.md#4-chi-phí-và-billing)
- Rollback riêng R49 dùng `sudo python3 -B /opt/websentinel-r48/runtime/refresh.py rollback` trên đúng EC2 qua SSM. Kiểm lại backup SHA, gateway R48, chế độ enforcement và health của HTTPS sau thao tác. DB dump dành cho tình huống phục hồi được phê duyệt riêng. Lần cập nhật R49 thành công trên AWS và chưa phải thực thi rollback. [Runbook staging](AWS_STAGING_OPERATIONS_HANDOFF.md#11-r49--phạm-vi-quan-sát-và-rollback)
- SHA-256 của kit staging `8114bb2a1eabad288c5afb5f6d131df323c6b60f0dcd5f11438601ee0c320e2f`, gateway đang phục vụ `11bc07397e23c57ff4d6130a656a88785e9deabea371d89c7af682ee78f1007c`, manifest backup `224fe86fae7fe73723a9372ace663d1ff2d3cf14fd0803528402d1cd4569154e` và ONNX R37 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`.
