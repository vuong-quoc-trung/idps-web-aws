# Đổi / quên mật khẩu sinh viên

Dừng backend, chạy `sql/016_student_password_reset.sql`, sau đó khởi động phiên bản mới. Không thay thế luồng kích hoạt: tài khoản chưa kích hoạt hoặc đã khóa không được reset mật khẩu.

## API

Tất cả POST vẫn yêu cầu cookie và CSRF: lấy token từ `GET /api/auth/csrf`, gửi tên header và token được trả về. Các endpoint sau thuộc `/api/auth`.

| Endpoint | JSON body | Thành công |
| --- | --- | --- |
| POST /forgot-password | `{"studentCode":"STU-2024-000001"}` | 202, thông báo chung |
| POST /reset-password | `{"studentCode":"STU-2024-000001","code":"012345","newPassword":"new-long-password"}` | 204 |
| POST /change-password | `{"currentPassword":"old-long-password","newPassword":"new-long-password"}` | 204, yêu cầu đăng nhập STUDENT |

Quên mật khẩu: nhập mã sinh viên, nhận OTP vào **schoolEmail đang lưu trong database**, rồi gửi OTP cùng mật khẩu mới. Backend xác thực mã trước khi ghi mật khẩu; không có bước xác thực trên frontend có thể bỏ qua. Không nhận email đích từ request và không gửi sang email cá nhân. Email trường phải là hộp thư thực có khả năng nhận thư; chuỗi email tự sinh chưa đồng nghĩa đã tạo mailbox.

OTP gồm 6 chữ số, có hiệu lực 10 phút, lưu bằng BCrypt. Mỗi tài khoản tối đa 5 lần gửi/giờ, cách nhau ít nhất 60 giây; tối đa 5 lần thử mỗi mã. Gửi lại thay mã cũ. Mã sai/hết hạn/đã dùng trả 400. Mã đúng chỉ dùng một lần. Yêu cầu gửi cho tài khoản không tồn tại, bị khóa, chưa kích hoạt hoặc bị giới hạn đều trả cùng 202 và không gửi thư. Lỗi SMTP cũng không tiết lộ tài khoản; backend ghi thông báo lỗi chung và hủy mã không gửi được.

Mật khẩu có ít nhất 12 ký tự, tối đa 72 byte UTF-8, không trim. Đổi mật khẩu phải nhập đúng mật khẩu hiện tại và mật khẩu mới phải khác. Đổi/reset thành công tăng phiên bản thông tin xác thực; các phiên cũ bị từ chối ở request kế tiếp. Frontend cần chuyển về đăng nhập, lấy CSRF mới nếu phiên đã bị hủy.

## Cấu hình gửi mail sau

Mặc định `PASSWORD_RESET_MAIL_ENABLED=false`; API yêu cầu mã trả 503 khi chưa bật/cấu hình sender. Đổi mật khẩu vẫn hoạt động.

Thiết lập biến môi trường cho tiến trình backend (không commit mật khẩu SMTP):

```dotenv
PASSWORD_RESET_MAIL_ENABLED=true
MAIL_HOST=smtp.example.edu.vn
MAIL_PORT=587
MAIL_USERNAME=your-smtp-account
MAIL_PASSWORD=your-smtp-secret
MAIL_FROM=no-reply@example.edu.vn
```

Backend dùng SMTP xác thực với STARTTLS bắt buộc và timeout 5 giây. Nếu chọn Gmail, dùng thông tin SMTP và phương thức xác thực được quản trị tài khoản cho phép. MAIL_FROM là tài khoản gửi, không phải email của sinh viên. Cấu hình trong `application.yaml`; hiện chưa gửi thử email thật.

Tham khảo cấu hình JavaMailSender chính thức: https://docs.spring.io/spring-boot/reference/io/email.html

Test dùng mail service giả để xác nhận email nhận, mã một lần, hạn sử dụng, giới hạn gửi/thử, CSRF, phân quyền, mật khẩu và thu hồi phiên; không gửi thư thật. Khi đưa lên môi trường public, cấu hình rate limit tại reverse proxy cho cả login và các endpoint mật khẩu để hạn chế lưu lượng từ nhiều địa chỉ/tài khoản.
