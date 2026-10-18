# Rà soát bảo mật 13/10/2026

## Hiện trạng

| Mục | Hiện trạng và giới hạn |
| --- | --- |
| Authentication | Spring Security session login/logout, kích hoạt tài khoản; tài khoản bị khóa/chưa kích hoạt không đăng nhập được |
| RBAC | ADMIN/STAFF/STUDENT, deny-all cho route chưa khai báo. STAFF hiện là cán bộ có quyền quản lý toàn bộ sinh viên, chưa phải giảng viên theo lớp |
| Object authorization | Sinh viên qua /api/me được ánh xạ từ principal; bản ghi con truy vấn bằng cả id và studentId. Truy cập bản ghi của người khác trả 404 để không tiết lộ tồn tại; route admin trả 403 |
| Password | BCrypt cost 12; đổi mật khẩu cho cả ba vai trò; tăng credentialVersion thu hồi phiên cũ |
| Session | Đổi session id khi login; idle timeout 30 phút, HttpOnly/SameSite=Lax, profile prod dùng Secure và cookie-only |
| CSRF | Giữ bật, cả login/reset cần CSRF token và cookie |
| Input | Bean Validation, DTO giới hạn trường, truy vấn JPA có tham số. React render text; không tìm thấy dangerouslySetInnerHTML trong lượt rà soát. Validation không thay thế escaping/parameter binding |
| HTTPS | Thêm application-prod.yaml cho TLS trực tiếp; cần chứng thư thực, chưa triển khai HTTPS lên server |
| Forgot password | Sinh viên: OTP BCrypt, 5 phút, 5 lần thử, tối đa 5 lần gửi/giờ, cooldown 60 giây, một lần dùng. Gửi thư cần SMTP thực. Admin/staff chưa có khôi phục bằng email |
| Rate limit | POST login/activate/reset/change: 20 request/IP/endpoint/phút; forgot: 5. Trả 429 + Retry-After. Lưu bộ nhớ có giới hạn, độc lập từng instance, mất khi restart; nhiều replica cần gateway/shared limiter |
| Audit | Tự ghi API mutation và request bị từ chối vào access_logs: actor nếu đã xác thực, IP, method, path (không query/body), status, elapsed. Không ghi password/OTP/cookie. Khi ghi DB lỗi có server error log, không đảo ngược thao tác đã commit; cần giám sát log này |
| MFA | Chưa triển khai; cần enrollment, xác thực bước hai, recovery và giao diện phù hợp. Không được coi hệ thống đã có MFA |
| Điểm/phân công giảng viên | Chưa có module, chưa có phân quyền giảng viên theo lớp hay audit thay đổi điểm |

## Triển khai TLS trực tiếp

Bật SPRING_PROFILES_ACTIVE=prod, cung cấp TLS_KEY_STORE (ví dụ file:/run/secrets/server.p12) và TLS_KEY_STORE_PASSWORD qua môi trường/secret manager. Chứng thư phải hợp lệ với tên miền. Chạy các migration trước vì prod dùng ddl-auto=validate. Profile prod tắt bootstrap admin. Không commit secret/chứng thư private key.

Nếu terminate TLS ở reverse proxy/ALB, cần cấu hình riêng: backend chỉ nhận traffic từ proxy tin cậy, Secure cookie và redirect HTTP→HTTPS tại proxy. Không bật tin cậy X-Forwarded-For từ Internet; limiter mặc định dùng remoteAddr, có thể đếm chung IP proxy nếu chưa cấu hình trusted proxy. CSP backend hiện dành cho API (default-src 'none'); frontend host cần CSP riêng phù hợp assets của giao diện.

## Kiểm thử và vận hành

StudentApiTests kiểm tra CSRF, RBAC, cô lập bản ghi con, reset/đổi mật khẩu và thu hồi phiên. SecurityRequestFilterTests kiểm tra 429, cửa sổ thời gian và audit không chứa payload. Suite nghiệp vụ tắt limiter để các test độc lập không tiêu hao quota của nhau; production mặc định bật.

Audit là nhật ký request/kết quả, chưa phải lịch sử before/after cho từng field và chưa có cơ chế chống sửa bởi quản trị database. Cần chính sách lưu trữ, quyền database và giám sát ở môi trường triển khai.

Tham khảo:
- https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

## Tự dọn audit log quá 3 ngày

Backend bật tác vụ retention mặc định: chạy lần đầu sau 60 giây kể từ khởi động, sau đó 10 phút sau mỗi đợt hoàn tất. Mốc hết hạn là thời gian hiện tại trừ 3 ngày (72 giờ), so sánh nghiêm ngặt created_at < cutoff; bản ghi đúng mốc hoặc mới hơn vẫn được giữ. Dùng cùng thời gian local của JVM với timestamp audit hiện có; giữ timezone runtime nhất quán khi triển khai.

Mỗi transaction xóa tối đa 500 bản ghi cũ nhất, tối đa 20 lô/đợt (10.000 bản ghi). Nếu tồn đọng nhiều hơn, đợt tiếp theo dọn tiếp. Dùng index created_at sẵn có; không cần migration mới. Chỉ tác động bảng access_logs, không xóa tài khoản/hồ sơ. Dữ liệu bị xóa vĩnh viễn; không phải chỉ ẩn khỏi giao diện. Khi backend tắt không dọn, khi bật lại sẽ xử lý log quá hạn.

Cấu hình ở application.yaml: app.audit.retention.enabled (biến môi trường AUDIT_RETENTION_ENABLED, mặc định true), initial-delay-ms và interval-ms. Khi tắt tác vụ, ghi chú thời hạn mặc định trên UI không còn phản ánh lịch dọn đang chạy. Không cung cấp endpoint xóa log công khai. Tác vụ ghi số bản ghi đã dọn vào console, không tự tạo thêm audit row.
