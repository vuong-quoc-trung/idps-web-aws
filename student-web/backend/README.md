# Student Web — database Code First

Java 25, Spring Boot 4.1.1, PostgreSQL 16. Hibernate tạo/cập nhật schema từ entity.

## Cấu trúc theo chức năng

`src/main/java/com/pbl4/studentweb/` có các module:
`user`, `major`, `trainingprogram`, `studentclass`, `student`, `studentaddress`,
`familymember`, `emergencycontact`, `postgraduationcontact`, `accesslog`.
Mỗi module có `controller`, `dto`, `entity`, `mapper`, `repository`, `service`.
`common/entity` chứa ID và timestamp; `configuration` chứa BCrypt encoder.

Bước hiện tại triển khai tầng DB và service nội bộ. Các package `controller` mới là
khung (`package-info.java`), chưa có REST endpoint, đăng nhập, phân quyền hay giao diện.
Các service danh mục cung cấp đọc phân trang; chưa phải bộ API CRUD hoàn chỉnh.
Các bảng liên hệ đã có entity/repository; API ghi địa chỉ, nhân thân và liên hệ sẽ làm ở bước sau.

## Chạy tạo bảng

Đảm bảo PostgreSQL có database `student_db`; Hibernate tạo bảng, không tạo database.
Thiết lập biến môi trường trong IDE hoặc terminal:

```bash
export DB_URL=jdbc:postgresql://localhost:5432/student_db
export DB_USERNAME=postgres
read -s 'DB_PASSWORD?PostgreSQL password: '
export DB_PASSWORD
./mvnw spring-boot:run
```

Ví dụ trên dùng zsh. Với Bash dùng `read -s -p 'PostgreSQL password: ' DB_PASSWORD`.
Không commit mật khẩu thật. Không có mật khẩu mặc định trong cấu hình.
Mặc định `DDL_AUTO=update` dành cho DEV; khi triển khai production dùng migration
và `DDL_AUTO=validate`. `open-in-view=false`; chuyển entity sang DTO trong transaction.

Trong DBeaver: kết nối `localhost:5432/student_db`, schema `public`, refresh Tables.
Có 10 bảng: `users`, `majors`, `training_programs`, `classes`, `students`,
`student_addresses`, `family_members`, `emergency_contacts`,
`post_graduation_contacts`, `access_logs`. Có 13 khóa ngoại; enum lưu tên,
ID identity, unique và index theo đặc tả. Không cascade xóa bảng danh mục.

```sql
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT table_name, constraint_name FROM information_schema.table_constraints
WHERE table_schema = 'public' AND constraint_type = 'FOREIGN KEY';
```

## Quyền sở hữu dữ liệu và luồng khởi tạo

Theo các ô xám trong ảnh, `CreateStudentRequest` dành cho admin gồm MSSV (cũng là
username), họ tên, ngày sinh, giới tính, CCCD, ngành, lớp, chương trình chính/phụ,
email trường và điện thoại gia đình. MSSV, họ tên, ngành, lớp là bắt buộc khi tạo;
các thông tin khác có thể bổ sung sau. Nếu không chọn chương trình chính, lấy
chương trình mặc định của lớp. Service kiểm tra lớp/chương trình chính cùng ngành.
CCCD và điện thoại gia đình tạm thuộc admin theo màu ô ảnh, có thể điều chỉnh DTO
nếu quy định thực tế khác. Tài khoản ngân hàng trong ảnh là ô xám: DB đã có cột,
nhưng chưa có luồng chỉnh sửa vì không phải dữ liệu bắt buộc lúc khởi tạo.

`StudentOnboardingService.create` tạo User và Student trong cùng transaction,
role STUDENT, status ACTIVE, profile INCOMPLETE. Không lấy dữ liệu cá nhân thật từ ảnh
để seed. Không có cột mật khẩu Office365.

`PasswordSetupService` tạo token ngẫu nhiên 256 bit có hạn 24 giờ, chỉ lưu SHA-256
của token. `password_hash` ban đầu là BCrypt của bí mật ngẫu nhiên không giao cho
người dùng; `password_setup_required=true`. Admin phải chuyển token cho đúng sinh
viên qua kênh đã xác minh ở bước API/email sau này. Không ghi token vào log.
Sinh viên dùng token để gọi service đặt mật khẩu lần đầu (ít nhất 12 ký tự,
tối đa 72 byte UTF-8). Khóa pessimistic ngăn dùng token đồng thời; thành công
thì xóa token/hạn dùng và tắt cờ chờ đặt mật khẩu. Chưa có cơ chế gửi/cấp lại token.

`StudentProfileService.updateForUser` thay toàn bộ các trường cá nhân ô trắng
được khai báo trong `UpdateStudentProfileRequest`; field bỏ trống sẽ thành NULL.
Không cho request sinh viên sửa MSSV, họ tên, CCCD, ngày sinh, giới tính hoặc ngành/lớp.
Khi làm API, userId phải lấy từ principal đã xác thực, không nhận userId tùy ý từ client.
Tất cả service hiện tại là nội bộ, không thay thế cơ chế xác thực/phân quyền.

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

`access_logs` mới có schema và đọc phân trang, chưa có filter thu thập HTTP tự động.
Khi tích hợp chỉ lưu metadata, path template không có query/token/PII; không lưu
body, password, CCCD, địa chỉ, cookie hay Authorization header.

## Kiểm thử

```bash
./mvnw test
```

Kiểm thử dùng H2 in-memory (PostgreSQL compatibility mode), dữ liệu giả và rollback;
không xóa hoặc seed database PostgreSQL của bạn. Kiểm tra mapping/schema, khóa ngoại,
hồ sơ thiếu/đủ rồi thiếu lại, khởi tạo sai ngành, mật khẩu và token hết hạn/dùng lại.
H2 không thay thế kiểm chứng trực tiếp PostgreSQL; dùng truy vấn trên sau khi chạy app.
