# Kích hoạt tài khoản sinh viên qua email

## Áp dụng

Dừng backend, chạy `sql/017_student_activation_email.sql`, rồi khởi động lại. Giữ các biến SMTP đã cấu hình; chức năng gửi link dùng chung cờ `PASSWORD_RESET_MAIL_ENABLED`. Thêm `PUBLIC_APP_URL=http://localhost:5173` khi chạy local. Production phải là URL HTTPS frontend thực tế; không lấy host của request làm URL email. Profile prod bắt buộc khai báo PUBLIC_APP_URL.

## Luồng

1. `/activate` khi không có token hiển thị đối chiếu hồ sơ: mã sinh viên, họ tên, ngày sinh, giới tính, CCCD, mã lớp và điện thoại gia đình nếu đã được trường lưu. Không yêu cầu ngân hàng. Mã lớp cần được trường cung cấp, không có API công khai để tra cứu hồ sơ.
2. POST `/api/auth/activation/verify` trả proof ngẫu nhiên nếu khớp. Proof giữ trong bộ nhớ trang, hash SHA-256 trong DB, hết hạn 5 phút. Mỗi tài khoản tối đa 5 lần đối chiếu/giờ kể cả thành công; có thêm IP limiter. Không công khai trường nào bị sai.
3. Nhập email cá nhân, POST `/api/auth/activation/send` với `{proof,email}`. Gửi thành công tiêu thụ proof và thay token cũ bằng token mới. Lỗi SMTP rollback thay token để có thể thử lại. Không trả token kích hoạt trong API này.
4. Email có link `/activate#token=...`; phần fragment không gửi lên server trong URL. Frontend đọc token vào bộ nhớ, xóa khỏi thanh địa chỉ và hiển thị đặt mật khẩu, không tự kích hoạt bằng GET.
5. POST `/api/auth/activate` với token và password: kích hoạt một lần, lưu email đã nhận link vào personalEmail, xóa token/proof/email chờ. Đổi mật khẩu lần đầu vẫn áp dụng 12 ký tự/72 byte UTF-8.

Mọi POST cần CSRF cookie/header. Token sinh bằng SecureRandom 32 byte (256 bit), mã hóa biểu diễn Base64URL, lưu SHA-256 trong database, hết hạn 24 giờ. Base64URL không phải mã hóa bí mật; email chứa token gốc để sử dụng, HTTPS bảo vệ đường truyền. Không ghi token, proof, CCCD hay mật khẩu vào log. Gửi lại link làm link cũ hết hiệu lực.

## Dữ liệu cũ và giới hạn

- Hồ sơ thiếu ngày sinh, giới tính hoặc CCCD không được kích hoạt tự phục vụ: admin cần bổ sung dữ liệu đúng trước. Không bỏ qua bước đối chiếu chỉ vì dữ liệu thiếu.
- Tài khoản đã kích hoạt hoặc bị khóa không được dùng luồng này. Quên mật khẩu là luồng riêng.
- Luồng cấp/reissue token của admin vẫn được giữ tương thích; admin reissue xóa email chờ từ luồng tự phục vụ.
- Gmail là một ví dụ email cá nhân; chấp nhận nhà cung cấp khác.
- Đối chiếu dữ liệu cá nhân không chứng minh danh tính tuyệt đối nếu thông tin đã lộ. Nhà trường cần kiểm soát nguồn dữ liệu, xử lý tranh chấp và cung cấp thông tin nhập học qua kênh tin cậy.
- Trang mới chưa được kiểm tra gửi thư thực tế trên Gmail trong lần triển khai này.
