# R54 — Hoàn thiện chức năng và cập nhật AWS staging

**R54_FINAL_COMPLETION = PARTIAL.** Hai frontend và Security API R54 đang phục vụ trên EC2. PostgreSQL đã thêm 117 bản ghi danh mục. Firefox đã nghiệm thu các thao tác ghi trên sinh viên và tài khoản thử nghiệm. Manual Prevention qua API vẫn bị khóa C2. Public enforcement và AI auto-ban đều OFF. [Baseline R52](138_T09_R52_FINAL_FUNCTIONAL_CLOSURE.md) · [Bằng chứng R53](139_T09_R53_FINAL_PROJECT_COMPLETION.md)

## Prevention, Hybrid và phạm vi quan sát

| Mục | Kết quả và bằng chứng |
|---|---|
| SOURCE_SYNC | PASS. Remote `dev/i5-hybrid-prevention` ở `798e66a462dd29426772146bff7c02ad6acead1f` đã thuộc lịch sử tích hợp khi fetch. Hai checkout khác giữ nguyên trạng thái. |
| C2_GATE_STATUS | CLOSED. R54 sửa báo cáo readiness. Khi bật cấu hình MANUAL hoặc ENFORCE mà C2 đóng, API trả trạng thái Prevention `BLOCKED`, kể cả nếu readback đồng bộ. Monitoring giữ readiness riêng. |
| MANUAL_PREVENTION | PARTIAL. Block, Unblock, TTL và readback kernel kế thừa PASS AWS cô lập của R53. Dashboard/API đến kernel còn BLOCKED. R52 kiểm RBAC và API fail-closed. R54 ẩn thao tác chặn và bỏ chặn khi Prevention chưa READY. |
| ACTUATOR_INTEGRATION | BLOCKED. Socket native `/run/ws-native-fw-status.sock` vắng trên serving. Actuator native đòi direct peer, scope đã duyệt, planner, TTL và readback. Cổng quản trị chưa có luồng thực thi đã nghiệm thu xuyên qua các điều kiện này. |
| TRUSTED_ENFORCEMENT_IDENTITY | BLOCKED trên serving. Request ID liên kết giao dịch qua loopback. Sensor đó thiếu danh tính direct peer cần cho thực thi. Lab R54 xác nhận NGINX bỏ X-Forwarded-For tự khai, Hybrid giữ enforcement target rỗng. |
| PREVENTION_READINESS | DISABLED, `ACTUATOR_OFFLINE` hiển thị từ readback. DB serving có 0 `firewall_actions`. |
| PUBLIC_ENFORCEMENT_STATE / AI_AUTO_BAN_STATE | OFF / OFF. Readback xác nhận `ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false` và `PBL4_FIREWALL_CMD=/bin/false`. |
| RULE_BASED_PREVENTION | PASS AWS cô lập tới Hybrid `ALERT`. Thực thi BLOCKED theo C2 và trusted peer scope. |
| AI_ADVISORY / AI_R37_RUNTIME | PASS AWS. Scorer thật trả `SCORED`; R37 có quyền advisory. Threshold 0,7664756774902344 và SHA `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff` giữ nguyên. |
| NGINX_RULES | PARTIAL. Gateway, log và request ID thật được xác minh. Rule dương tính R52 dùng fixture. |
| SURICATA_RULES | PASS AWS cô lập với sensor và SID marker lành tính. Rule pack public giữ nguyên. |
| STUDENT_AUDIT_RULES | PARTIAL. Java Audit thật liên kết cùng request. Bằng chứng application rule dương tính kế thừa fixture. |
| CORRELATOR / MULTI_SOURCE_ALERTS | PASS AWS theo mẫu quan sát và PASS AWS cô lập với một cảnh báo dương tính. Kiểm 6 ca correlation local qua, gồm sai scope, conflict, late và duplicate. Chưa có mẫu thật với cả ba detector cùng phát alert. |
| HYBRID_DECISION / RISK_SCORING | PASS AWS theo mẫu `LOG_ONLY` và PASS AWS cô lập cho `ALERT`, risk 45. Năm test Hybrid local qua. Mẫu ba nguồn giữ ba alert ID, loại bản sao và flow context, rule risk lấy mức cao nhất là 90. Không chỉnh scoring hay policy. |
| ALERT_DEDUPLICATION / INCIDENT_AGGREGATION | PASS theo mẫu lab. R54 một alert và một link; R52 replay tạo một incident và một decision audit. Giao diện mới hiển thị risk, nguồn, trạng thái tương quan và cho mở từng cảnh báo nguồn có ID ràng buộc. |

`REQUEST_COVERAGE = PARTIAL`. Đối chiếu 89 cặp method/route duy nhất, gồm hai route auth filter. Mỗi cặp thuộc đúng một nhóm. Signed observation R52 được giữ cho 10 route cơ sở và các biến thể GET detail/phân trang số của cả bốn danh mục. Trên đường direct, gateway ghi metadata chuẩn hóa và Student Audit cung cấp evidence tùy vào nghiệp vụ. Suricata/R37 chỉ tham gia khi có leg hoặc projection đã xác minh. [Gateway](../security-web/deploy/aws-r48/gateway.py) · [Correlator](../security-web/deploy/aws-r48/correlate.py)

| Nhóm | Cặp route | Phạm vi và ngoại lệ |
|---|---:|---|
| Danh tính | 4 | Signed. CSRF xác minh lại AWS R54. Login, logout và auth/me kế thừa. |
| Khôi phục và kích hoạt | 6 | Direct. Giữ nghiệm thu Gmail R50. Mật khẩu, token và OTP nằm ngoài projection. |
| Danh mục và tùy chọn hồ sơ | 21 | Signed cho GET allowlist theo nhóm, gồm detail/phân trang đã nghiệm thu R52. Direct cho thao tác ghi và query tự do. |
| Sinh viên tự phục vụ | 25 | Signed cho completion. Hồ sơ, học tập và liên hệ direct. |
| Quản trị sinh viên | 26 | Direct. Browser R54 đã qua danh sách, hồ sơ, liên hệ khẩn cấp và lưu trữ. |
| Quản trị tài khoản và nhật ký | 7 | Direct. Browser R54 xác minh xem, tắt và bật tài khoản thử. |

### Giao dịch dùng để trình diễn

- **AWS serving:** `e741dd580a68956382b0145096e02d9e`, một GET CSRF hợp lệ. PostgreSQL đọc ra `MATCHED`, NGINX/Student Audit/Suricata, `late=false`, `SCORED`, `LOG_ONLY`. Firefox xác minh cùng kết quả hiển thị và SSE kết nối. Sau cập nhật asset cuối, Firefox tra request mới `c68292ead668259aaf92f3a27f884e39` thành công. Vào **AI Shadow → Tra cứu** và nhập request ID khi dữ liệu còn trong retention. [Security Web](https://websentinal.duckdns.org/)
- **AWS cô lập:** `71b2d6b42fca7ac29637e6b97639be9c`, HTTP 200, ba nguồn và `late=false`, Suricata flow `1680111123653190` tx 0. Một cảnh báo marker, một liên kết, R37 0,125357, Hybrid `ALERT`, risk 45 và SSE `alert.created`. Viewer triage 403, admin 200, phiên bản cũ 409, một dòng lịch sử. Unit `websentinel-r54-native-smoke.service`, invocation `7c469a4b33a440e8a46e5d771b34259b`, exit 0, peak 533,8 MiB. DB lab đã dọn. Marker xác minh pipeline cho hành vi thử nghiệm lành tính. [Harness R53](../security-web/deploy/aws-r48/r53_runtime_lab.py)

## PostgreSQL và UI nghiệp vụ

`SQL_FILES_DISCOVERED = 51` file SQL được Git theo dõi, gồm 22 trong Student Web và 29 trong Security Web. Kiểm thêm bản làm việc liên quan. Nguồn nhập là seed danh mục `006`, `008`, `009`, `010`, `011`, `013`. Flyway giữ schema V1/V2, PostgreSQL áp dụng PK/FK/unique. Seed `014` chứa 52 họ tên và số thẻ nguồn chưa xác minh quyền đưa lên AWS. Các bảng giảng viên và seed giảng viên hợp lệ chưa tìm thấy. Có 154 chương trình nguồn chưa xác nhận loại bằng, vẫn chờ nghiệp vụ. [SQL danh mục](../student-web/backend/docs/sql/) · [Nguồn sinh viên](../student-web/backend/docs/IT_2024_STUDENTS.md)

Lượt thử đầu rollback vì seed chuẩn hóa Khoa hiện có. Chế độ insert-only giữ tên, mã, mô tả và ID hiện hữu. So sánh danh mục trước/sau trong cùng transaction. Diễn tập lại trên schema và dữ liệu danh mục sao từ backup, thành công lần đầu rồi thêm 0 dòng khi chạy lại. Trên AWS, unit `websentinel-r54-catalog.service` exit 0. Giữ hai seed catalog đã có và không đụng tài khoản, mật khẩu hay thông tin sinh viên. [Runner](../security-web/deploy/aws-r48/r54_catalog.py)

| PostgreSQL AWS | Trước | Sau | Bổ sung |
|---|---:|---:|---:|
| Sinh viên | 3 | 3 | 0 |
| Tài khoản | 4 | 4 | 0 |
| Khoa | 1 | 16 | 15 |
| Ngành | 1 | 10 | 9 |
| Lớp | 1 | 7 | 6 |
| Chương trình | 1 | 88 | 87 |
| Giảng viên | Chưa có schema | Chưa có schema | 0 |

`SQL_DATA_VALIDATION`, `DATABASE_BACKUP`, `DATABASE_IMPORT`, `CATALOG_DATA`, `DATA_INTEGRITY` và `AWS_DATABASE_SYNC` đạt cho dữ liệu danh mục. Hai kiểm tra chain lớp/chương trình và sinh viên/lớp đều 0 mismatch. `STUDENT_DATA` giữ 3 dòng đã xác minh và không nhập seed chưa rõ quyền. `LECTURER_DATA = BLOCKED` vì chưa có nguồn/schema.

| Hạng mục UI | Kết quả |
|---|---|
| AWS_UI_DATA_VERIFICATION | PASS AWS Firefox. Tab Lớp hiển thị `CNTT Đặc thù K2024 - Lớp 01` vừa nhập. |
| STUDENT_WEB_ALL_FUNCTIONS | PARTIAL. R54 PASS AWS cho tạo, xem, sửa hồ sơ, CRUD liên hệ khẩn cấp, xem/tắt/bật tài khoản và lưu trữ sinh viên thử. Dọn 1 sinh viên, 1 tài khoản, 0 fixture còn lại. Khoa, Ngành, Lớp, Chương trình và email kế thừa R50–R53. Chưa chạy đầy đủ các form tự phục vụ và vai trò giảng viên. |
| SECURITY_WEB_ALL_FUNCTIONS | PARTIAL. Browser AWS qua login, Prevention state, tra Hybrid/R37 và SSE. Triage/RBAC đạt AWS cô lập qua API. Dashboard → API → kernel vẫn BLOCKED. |
| UI_CLEANUP / UNNECESSARY_CONTENT_REMOVAL | PASS theo thay đổi. Bỏ nhãn PBL4 và hai nhãn trang trí Security, giữ logo WebSentinel. Bỏ thông tin liên hệ mẫu và nhãn đồ án khỏi footer Student. Giữ trạng thái bảo mật, dữ liệu nguồn và nhãn lab cho replay. |
| UI_CONSISTENCY / BROWSER_UI_ACCEPTANCE | PASS theo các màn hình thay đổi và các thao tác nêu trên. Hai frontend build đạt. Security 19 test qua trước bản vá một dòng cho nút chặn trong chi tiết alert. Build lại, 4 test liên quan và Firefox qua sau vá. |
| DASHBOARD_AND_SSE | PASS AWS theo mẫu browser. PASS AWS cô lập cho phát `alert.created` đúng cảnh báo sau DB commit. |

## Deployment, tài nguyên và rollback

- `AWS_DEPLOYMENT = PASS`, unit `websentinel-r54-deploy.service` exit 0. `SERVING_RELEASE_VERSION = R54`. Bản serving cập nhật Security binary và hai static build trong release hiện có. Student Java, NGINX, R37 và R36 giữ nguyên. Security asset hậu kiểm được cập nhật riêng, xác minh lại qua Firefox.
- SHA serving: Security binary `33de408556d22c60950ac00a66b8de18a6fa9aa35073bba0f21dd9e18b6da99f`, Security index `bc091063ee08d118df11471921949b434b6fee909977407bb6fdc81d9493bc70`, Student index `54c5415982a3792a98502678ac43fd72a0db5a47fc06454c147d84fe79afa7aa`.
- `DATABASE_BACKUP = PASS`. Backup root-only `/var/backups/websentinel-r54` có hai PostgreSQL logical dump, cấu hình và archive active release. SHA manifest `1d222b9d50baafa7ca9baf6c5214744b932a83ab708e950afd5c184f643aecf2`. Verify manifest qua AWS. [Runbook rollback](AWS_STAGING_OPERATIONS_HANDOFF.md#16-r54--rollback-ứng-dụng-và-danh-mục)
- `ENV_PRESERVATION / SECRETS_PROTECTION = PASS`. Ba file cấu hình Student, Security và scorer khớp từng byte với backup. Không có dữ liệu cá nhân hay credential trong thay đổi Git R54.
- `SERVICE_STABILITY / RESOURCE_SAFETY = PASS` trong cửa sổ quan sát. Tám unit/timer active, PostgreSQL nhận kết nối, NGINX config hợp lệ, 0 OOM kill ở năm cgroup. RAM 1.307 MiB, disk 10%. Kernel Security CPU 15%, RAM 512 MiB; scorer CPU 25%, RAM 768 MiB. Cả hai swap 0 và PID 64. Không thay Cloud Resource Safety Profile.
- `EC2_FINAL_STATE = RUNNING`, status checks 3/3. AWS Budgets ghi 1,227 USD thực tế, 2,295 USD dự báo và hạn mức 25 USD. Scheduler ENABLED mỗi 15 phút, `MAX_SESSION_MINUTES=480`, `DRY_RUN=true`. Auto-Stop chưa thực hiện Stop thật.
- `GIT_PUSH / REMOTE_HEAD` được đối chiếu trên `feature/ai-idps-https-ml-integration`. R54 dùng đúng checkout hiện tại, push thường và chỉ commit các đường dẫn của R54.

Còn thiếu nghiệm thu một đường thực thi quản trị có direct peer được duyệt, danh sách địa chỉ bảo vệ, DB/audit/kernel readback, lỗi/recovery và rollback trên phạm vi cô lập. Public enforcement cần phê duyệt độc lập. Các chức năng tự phục vụ và giao diện theo vai trò còn ngoài mẫu browser R54.
