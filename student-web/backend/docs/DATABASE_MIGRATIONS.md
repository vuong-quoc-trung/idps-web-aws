# Quản lý schema bằng Flyway

Backend dùng `spring-boot-starter-flyway` và module PostgreSQL; phiên bản theo Spring Boot BOM.
Khi khởi động: Flyway kiểm tra checksum → áp dụng migration chưa chạy → Hibernate `validate` → phục vụ API.
Nếu migration hoặc validate thất bại, ứng dụng không khởi động bình thường. Không dùng Hibernate `update` nữa.

## Database mới

Tạo database PostgreSQL rỗng, cấu hình DB_URL/DB_USERNAME/DB_PASSWORD như trước và khởi động backend.
`src/main/resources/db/migration/V1__initial_schema.sql` tạo toàn bộ bảng, khóa ngoại, unique, check, index và dòng khóa admin.
Database/schema cần đúng quyền tạo bảng; Flyway không tạo database PostgreSQL giúp bạn.
Lịch sử/checksum được lưu ở `public.flyway_schema_history`. Các lần khởi động sau không chạy lại V1.

V1 là bản schema hiện tại, bao gồm cấu trúc sau các script cũ 001–019, không phải bản sao script 001.
Không tự tạo danh mục mẫu, sinh viên hay tài khoản. Có thể dùng API hoặc chọn chạy seed 006, 008–011, 013–014
sau khi đọc dữ liệu và phụ thuộc của từng script. Không tự chạy seed chứa thông tin sinh viên trên production.

## Tiếp nhận database đang dùng — chỉ một lần

1. Dừng backend, sao lưu database và kiểm tra có thể phục hồi bản sao lưu.
2. Xác nhận DB_URL trỏ đúng database. Database phải có schema hiện tại của ứng dụng.
   Nếu còn thiếu cập nhật cũ, rà soát và chạy **chỉ script cấu trúc còn thiếu**, theo thứ tự:
   001–005, 007, 012, 015–019 (đọc yêu cầu sửa dữ liệu của mỗi script).
   Một số script cũ cần dữ liệu hợp lệ trước khi thêm NOT NULL/constraint; không chạy mù toàn bộ thư mục.
3. Sau khi schema đã sẵn sàng, tại thư mục backend, nạp biến môi trường như thường lệ rồi chạy:

```bash
# Nếu dùng .env của project; không đưa nội dung file này lên GitHub.
set -a
source .env
set +a
FLYWAY_BASELINE_ON_MIGRATE=true ./mvnw spring-boot:run
```

Lần này Flyway ghi **BASELINE phiên bản 1**, bỏ qua việc tạo lại bảng của V1, giữ dữ liệu hiện tại.
Baseline **không** sửa schema cũ và không chứng minh schema đã đúng: Hibernate kiểm tra mapping sau đó,
nhưng không kiểm tra đầy đủ constraint/index/default. Phải hoàn tất bước 2 trước.
Nếu validate lỗi, sửa thiếu sót được báo; không xóa history hoặc đổi checksum để che lỗi.

4. Khi khởi động thành công, dừng và chạy lại bình thường không có cờ baseline:

```bash
./mvnw spring-boot:run
```

Không lưu `FLYWAY_BASELINE_ON_MIGRATE=true` lâu dài trong .env/prod.
Mặc định cờ này là false: schema có dữ liệu nhưng chưa có history sẽ bị từ chối để tránh tiếp nhận nhầm database.
Nếu `.env` trước đây có `DDL_AUTO=update`, bỏ biến đó; cấu hình mới cố định `validate`.
Không đặt `SPRING_JPA_HIBERNATE_DDL_AUTO=update/create/create-drop` trên database thật.

## Thay đổi schema từ bây giờ

- Tạo file mới `V2__describe_change.sql`, sau đó V3, V4… trong `src/main/resources/db/migration`.
- Dùng hai dấu gạch dưới sau phiên bản; số này độc lập với tên script lịch sử trong docs/sql.
- Commit migration cùng entity/service cần schema đó. Không sửa V1 hoặc migration đã triển khai.
- Không thêm `BEGIN/COMMIT`: Flyway quản lý transaction. Tránh SQL không transactional nếu chưa thiết kế riêng.
- Không thêm seed demo hoặc dữ liệu cá nhân vào migration production.
- Kiểm thử trên database mới và bản sao database hiện tại trước khi triển khai; sao lưu trước migration thay đổi dữ liệu.
- `clean-disabled=true` chặn thao tác Flyway clean. Không dùng `repair` để bỏ qua checksum thay đổi ngoài ý muốn.
- Tài khoản chạy migration cần quyền DDL; có thể cấu hình `SPRING_FLYWAY_USER/PASSWORD` riêng,
  tài khoản datasource chạy ứng dụng chỉ có quyền runtime cần thiết.

## Kiểm tra lịch sử trong DBeaver

```sql
SELECT installed_rank, version, description, type, installed_on, success
FROM public.flyway_schema_history
ORDER BY installed_rank;
```

## Kiểm thử

`./mvnw test` chạy các test nghiệp vụ H2 với Flyway tắt trong test resources.
`FlywayMigrationTests` và `FlywayStartupTests` chỉ chạy khi có `MIGRATION_TEST_URL`.
Chỉ trỏ biến này tới PostgreSQL **tạm dành riêng cho test**, không dùng student_db thật:
startup test tạo schema, migration test tạo/xóa database tạm; user test cần CREATEDB.
URL test có dạng `jdbc:postgresql://localhost:PORT/migration_test` (không thêm query parameters).

```bash
MIGRATION_TEST_URL=jdbc:postgresql://localhost:PORT/migration_test \
MIGRATION_TEST_USER=postgres \
MIGRATION_TEST_PASSWORD=migration-test-only \
./mvnw test
```

CI đã có PostgreSQL 16 riêng cho các test này: tạo schema mới, xác nhận Hibernate validate,
khởi động lại không lặp migration, checksum sai bị chặn, database cũ cần bật baseline rõ ràng,
giữ dữ liệu và áp dụng V2 thử nghiệm đúng một lần. V2 thử nghiệm nằm ở test resources, không đóng gói vào JAR.

Tham khảo:
- https://docs.spring.io/spring-boot/how-to/data-initialization.html
- https://documentation.red-gate.com/flyway/reference/commands/baseline
