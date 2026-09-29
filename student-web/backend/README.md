# Student Web — REST API quản lý sinh viên

Java 25, Spring Boot 4.1.1, PostgreSQL 16. Hibernate tạo/cập nhật schema từ entity.

## Cấu trúc theo chức năng

`src/main/java/com/pbl4/studentweb/` có các module:
`user`, `faculty`, `major`, `trainingprogram`, `studentclass`, `student`, `studentaddress`,
`familymember`, `emergencycontact`, `postgraduationcontact`, `accesslog`.
Mỗi module có `controller`, `dto`, `entity`, `mapper`, `repository`, `service`.
`common/entity` chứa ID và timestamp; `configuration` chứa BCrypt encoder.

Backend có REST API CRUD cho khoa, ngành, chương trình đào tạo, lớp, sinh viên và các phần
hồ sơ liên quan. Xác thực dùng Spring Security, session cookie và CSRF, với ba vai trò
ADMIN / STAFF / STUDENT. Giao diện frontend chưa nằm trong phần triển khai này.

Xem [hướng dẫn API, phân quyền và ví dụ request](docs/API.md).

Quan hệ bắt buộc: **Khoa → Ngành → Chương trình đào tạo → Lớp → Sinh viên**.
Tạo ngành cần `facultyId`; tạo chương trình cần `majorId`; tạo lớp cần `programId`; tạo sinh viên chỉ cần `classId`
cùng MSSV và họ tên. Với database cũ, xem [hướng dẫn chuyển đổi dữ liệu](docs/ACADEMIC_HIERARCHY.md)
trước khi chạy bản mới vì các liên kết khoa/chương trình trước đây chưa bắt buộc nay phải có giá trị,
và `degreeType` chỉ nhận `BACHELOR`, `ENGINEER`, `MASTER` hoặc null.

## Chạy tạo bảng

Đảm bảo PostgreSQL có database `student_db`; Hibernate tạo bảng, không tạo database.
Thiết lập biến môi trường trong IDE hoặc terminal:

```bash
export DB_URL=jdbc:postgresql://localhost:5432/student_db
export DB_USERNAME=postgres
read -s 'DB_PASSWORD?PostgreSQL password: '
export DB_PASSWORD
sh mvnw spring-boot:run
```

Ví dụ trên dùng zsh. Với Bash dùng `read -s -p 'PostgreSQL password: ' DB_PASSWORD`.
Không commit mật khẩu thật. Không có mật khẩu mặc định trong cấu hình.
Mặc định `DDL_AUTO=update` dành cho DEV; khi triển khai production dùng migration
và `DDL_AUTO=validate`. `open-in-view=false`; chuyển entity sang DTO trong transaction.

Trong DBeaver: kết nối `localhost:5432/student_db`, schema `public`, refresh Tables.
Có 11 bảng: `users`, `faculties`, `majors`, `training_programs`, `classes`, `students`,
`student_addresses`, `family_members`, `emergency_contacts`,
`post_graduation_contacts`, `access_logs`. Có 14 khóa ngoại; enum lưu tên,
ID identity, unique và index theo đặc tả. Không cascade xóa bảng danh mục.

```sql
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT table_name, constraint_name FROM information_schema.table_constraints
WHERE table_schema = 'public' AND constraint_type = 'FOREIGN KEY';
```

## Quyền sở hữu dữ liệu và luồng khởi tạo

Theo các ô xám trong ảnh, `CreateStudentRequest` dành cho admin gồm MSSV (cũng là
username), họ tên, ngày sinh, giới tính, CCCD, ngành, lớp, chương trình chính/phụ,
email trường và điện thoại gia đình. MSSV, họ tên và lớp là bắt buộc khi tạo;
backend lấy ngành và chương trình chính từ lớp. Lớp phải có chương trình, chương trình
phải có ngành và cả ba phải đang hoạt động. Nếu request còn gửi ID ngành/chương trình,
chúng phải khớp với lớp. PUT đổi lớp cũng cập nhật đồng thời ngành và chương trình chính.
CCCD và điện thoại gia đình tạm thuộc admin theo màu ô ảnh, có thể điều chỉnh DTO
nếu quy định thực tế khác. Tài khoản ngân hàng do ADMIN/STAFF cập nhật qua `UpdateStudentRequest`.
MSSV và username không đổi sau khi tạo. PUT thay toàn bộ nhóm trường của request;
trường tùy chọn bỏ trống sẽ bị xóa về NULL; riêng ngành/chương trình chính luôn suy ra từ lớp.

`StudentOnboardingService.create` tạo User và Student trong cùng transaction,
role STUDENT, status ACTIVE, profile INCOMPLETE. Không lấy dữ liệu cá nhân thật từ ảnh
để seed. Không có cột mật khẩu Office365.

`PasswordSetupService` tạo token ngẫu nhiên 256 bit có hạn 24 giờ, chỉ lưu SHA-256
của token. `password_hash` ban đầu là BCrypt của bí mật ngẫu nhiên không giao cho
người dùng; `password_setup_required=true`. API tạo sinh viên trả token một lần cho ADMIN/STAFF để chuyển cho đúng sinh viên qua
kênh đã xác minh. Chưa tự gửi email. Không ghi token vào log.
Sinh viên dùng token để gọi service đặt mật khẩu lần đầu (ít nhất 12 ký tự,
tối đa 72 byte UTF-8). Khóa pessimistic ngăn dùng token đồng thời; thành công
thì xóa token/hạn dùng và tắt cờ chờ đặt mật khẩu. ADMIN có thể cấp lại token cho tài khoản đang chờ đặt mật khẩu qua `POST /api/users/{id}/activation-token`; token cũ mất hiệu lực.

`StudentProfileService.updateForUser` thay toàn bộ các trường cá nhân ô trắng
được khai báo trong `UpdateStudentProfileRequest`; field bỏ trống sẽ thành NULL.
Không cho request sinh viên sửa MSSV, họ tên, CCCD, ngày sinh, giới tính hoặc ngành/lớp.
API `/api/me/**` lấy userId từ tài khoản đang đăng nhập. CRUD bản ghi con kiểm tra cả
ID bản ghi lẫn studentId, nên sinh viên không thể truy cập dữ liệu của người khác.
Service được gọi bên trong ứng dụng; ranh giới HTTP được bảo vệ bởi `SecurityConfiguration`.

`StudentProfileCompletionService.refresh` trả trạng thái và danh sách mục thiếu,
đồng thời cập nhật `profile_status`/`profile_completed_at`:

- Đủ trường cá nhân bắt buộc trong đặc tả và chương trình chính.
- Địa chỉ CURRENT còn hiệu lực và PERMANENT hoặc FAMILY_HOME, đủ số nhà/đường,
  tỉnh/thành phố, xã/phường.
- Cha và mẹ có tên/ngày sinh hoặc đánh dấu unavailable.
- Có liên hệ khẩn cấp với tên, điện thoại và priority dương.
- BHYT cần số thẻ/ngày hết hạn, kể cả thẻ miễn phí. Chưa có quy tắc miễn yêu cầu
  BHYT; `free_health_insurance` không có nghĩa là không cần BHYT.

Các trường optional không chặn hoàn thiện. Khi thiếu lại dữ liệu, trạng thái quay
về INCOMPLETE và xóa thời điểm hoàn thiện. Sau khi ghi các bảng liên quan, phải gọi
`refresh` trong cùng transaction. `requireComplete` là hàm kiểm tra để tích hợp vào
các tính năng sau; hiện chưa có bộ lọc HTTP chặn tính năng. Luôn cho phép sinh viên
chưa hoàn thiện hồ sơ truy cập màn hình bổ sung thông tin.

`access_logs` có API đọc phân trang/chi tiết dành riêng ADMIN, chưa có filter thu thập HTTP tự động.
Không cung cấp API sửa/xóa nhật ký.
Khi tích hợp chỉ lưu metadata, path template không có query/token/PII; không lưu
body, password, CCCD, địa chỉ, cookie hay Authorization header.

## Kiểm thử

```bash
sh mvnw test
```

Kiểm thử dùng H2 in-memory (PostgreSQL compatibility mode), dữ liệu giả và rollback;
không xóa hoặc seed database PostgreSQL của bạn. Kiểm tra mapping/schema, khóa ngoại,
hồ sơ thiếu/đủ rồi thiếu lại, khởi tạo sai ngành, mật khẩu và token hết hạn/dùng lại;
kiểm thử HTTP gồm đăng nhập thực, CSRF, phân quyền, CRUD, sở hữu dữ liệu, validation,
ngừng hoạt động sinh viên và thu hồi session của tài khoản bị khóa.
H2 không thay thế kiểm chứng trực tiếp PostgreSQL; dùng truy vấn trên sau khi chạy app.

## Tài khoản quản trị ban đầu

Không có tài khoản hoặc mật khẩu mặc định. Để tạo ADMIN đầu tiên, ngoài biến kết nối
PostgreSQL ở trên, đặt các biến sau trong zsh trước khi chạy:

```bash
export BOOTSTRAP_ADMIN_ENABLED=true
export BOOTSTRAP_ADMIN_USERNAME=admin
read -s 'BOOTSTRAP_ADMIN_PASSWORD?Initial admin password: '
export BOOTSTRAP_ADMIN_PASSWORD
sh mvnw spring-boot:run
```

Mật khẩu tối thiểu 12 ký tự và tối đa 72 byte UTF-8. Bootstrap chỉ tạo tài khoản khi
chưa tồn tại ADMIN; không ghi đè mật khẩu cũ. Sau lần tạo đầu tiên, bỏ các biến
`BOOTSTRAP_ADMIN_*` khỏi môi trường chạy. Trong Bash, dùng cú pháp `read -s -p` như trên.
Khi chạy HTTPS, đặt `SESSION_COOKIE_SECURE=true`. Frontend dùng cùng origin qua
Nginx/dev proxy; chưa mở CORS cho origin khác.
