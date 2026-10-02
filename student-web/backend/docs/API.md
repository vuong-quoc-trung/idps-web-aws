# Student Web REST API

Base URL: `/api`. JSON cho request/response, riêng đăng nhập dùng form URL encoded.
Không trả entity JPA, password hash hoặc token hash. Token kích hoạt chỉ xuất hiện
trong kết quả tạo tài khoản hoặc cấp lại token. Không ghi body chứa mật khẩu/token vào log.

## Đăng nhập và session

1. `GET /api/auth/csrf` → `{ "headerName": "X-CSRF-TOKEN", "token": "..." }` và session cookie.
2. `POST /api/auth/login`, body form `username=...&password=...`, gửi cookie và header CSRF → `204`.
3. Gọi lại `/api/auth/csrf` sau đăng nhập để lấy token mới, tiếp tục gửi cookie trên mọi request.
4. Các request `POST`, `PUT`, `PATCH`, `DELETE` đều cần header CSRF, kể cả kích hoạt tài khoản và logout.
5. `GET /api/auth/me` trả tài khoản hiện tại; `POST /api/auth/logout` hủy session → `204`.

Sai thông tin đăng nhập hoặc tài khoản chưa đặt mật khẩu/bị khóa → `401`.
Session hết hạn sau 30 phút không hoạt động; tài khoản bị vô hiệu hóa bị từ chối ngay
ở request tiếp theo kể cả đang giữ session cũ. Cookie HttpOnly, SameSite=Lax.
Frontend dùng cùng origin qua reverse proxy/dev proxy; chưa cấu hình CORS liên miền.
Thiết kế CSRF dựa trên [tài liệu Spring Security](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Ví dụ trong trình duyệt cùng origin:

```javascript
let csrf = await fetch('/api/auth/csrf', { credentials: 'same-origin' }).then(r => r.json());
const response = await fetch('/api/auth/login', {
  method: 'POST', credentials: 'same-origin',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded', [csrf.headerName]: csrf.token },
  body: new URLSearchParams({ username, password })
});
if (!response.ok) throw new Error('Đăng nhập thất bại');
csrf = await fetch('/api/auth/csrf', { credentials: 'same-origin' }).then(r => r.json());
// Gửi [csrf.headerName]: csrf.token trên các request ghi tiếp theo.
```

## Phân quyền

| Chức năng | ADMIN | STAFF | STUDENT |
| --- | --- | --- | --- |
| Xem danh mục khoa/ngành/lớp/chương trình | Có | Có | Có |
| Thêm/sửa/xóa danh mục | Có | Có | Không |
| Danh sách, tạo, cập nhật, ngừng hoạt động sinh viên | Có | Có | Không |
| Quản lý địa chỉ/nhân thân/liên hệ của sinh viên | Có | Có | Chỉ của mình qua `/me` |
| Sửa thông tin cá nhân do sinh viên khai báo | Không qua API quản trị | Không qua API quản trị | Chỉ của mình |
| Quản lý tài khoản, cấp lại token và đọc nhật ký | Có | Không | Không |

Không có đăng ký công khai. ADMIN/STAFF tạo sinh viên; ADMIN tạo tài khoản ADMIN/STAFF.
Sinh viên chưa hoàn thiện hồ sơ vẫn được dùng các API bổ sung hồ sơ.

## Danh mục và sinh viên

| Resource | Danh sách | Chi tiết | Thêm | Sửa | Xóa |
| --- | --- | --- | --- | --- | --- |
| `/faculties` | GET | GET `/{id}` | POST | PUT `/{id}` | DELETE `/{id}` |
| `/majors` | GET | GET `/{id}` | POST | PUT `/{id}` | DELETE `/{id}` |
| `/training-programs` | GET | GET `/{id}` | POST | PUT `/{id}` | DELETE `/{id}` |
| `/classes` | GET | GET `/{id}` | POST | PUT `/{id}` | DELETE `/{id}` |
| `/students` | GET | GET `/{id}` | POST | PUT `/{id}` | DELETE `/{id}` (ngừng hoạt động) |

Danh sách có `page` (từ 0, mặc định 0), `size` (1–100, mặc định 20), sắp xếp ID tăng dần.
Kết quả: `{ "content": [], "page": 0, "size": 20, "totalElements": 0, "totalPages": 0 }`.
`GET /students` thêm `search` (MSSV/họ tên, không phân biệt hoa thường), `majorId`, `classId`,
`status` (`ACTIVE`, `GRADUATED`, `SUSPENDED`, `INACTIVE`). Dữ liệu ngừng hoạt động vẫn có trong
kết quả nếu không truyền `status`. Tìm kiếm coi `%`/`_` là ký tự thường, không phải wildcard.

Payload danh mục dùng chung cho POST/PUT, theo thứ tự khoa → ngành → chương trình → lớp:

```json
{ "shortCode": "IT", "name": "Khoa Công nghệ thông tin", "description": "", "active": true }
```

```json
{ "shortCode": "IT", "name": "Công nghệ thông tin", "facultyId": 1, "description": "", "active": true }
```

```json
{
  "name": "Chương trình CNTT", "majorId": 1, "cohort": 2026,
  "degreeType": "ENGINEER", "numberOfSemesters": 10, "totalCredits": 150,
  "requiredCredits": 120, "electiveCredits": 30, "active": true
}
```

```json
{ "name": "Lớp 26T1", "programId": 1, "cohort": 2026, "academicYear": "2026-2031", "active": true }
```

ID trong ví dụ phải thay bằng ID thật. Khoa/ngành nhận `shortCode`, không nhận `code`.
Chương trình/lớp/sinh viên được backend sinh mã; xem [quy ước mã](CODE_GENERATION.md).
Tên ngành/chương trình bắt buộc;
`facultyId` bắt buộc cho ngành; `majorId` bắt buộc cho chương trình; `programId` bắt buộc cho lớp; `active` bắt buộc.
Khoa/ngành/chương trình cha phải tồn tại. Lớp tự lấy ngành từ chương trình; nếu gửi thêm
`majorId` thì phải khớp. Tên lớp và các trường mô tả có thể bỏ trống.
Xóa danh mục đang được tham chiếu trả `409`; có thể PUT `active=false` để ngừng sử dụng.
Không đổi khoa của ngành đang được sử dụng; không đổi ngành của chương trình đang được sử dụng; không đổi chương trình của lớp
đã có sinh viên, kể cả đổi sang chương trình cùng ngành.

`degreeType` là enum lưu bằng tên: `BACHELOR`, `ENGINEER`, `MASTER`; `degreeType` và `cohort` (năm 4 chữ số) bắt buộc cho chương trình.
Bốn trường học kỳ/tín chỉ là số nguyên tùy chọn: `numberOfSemesters` phải > 0; `totalCredits` phải >= 0;
`requiredCredits` và `electiveCredits` phải >= 0. Khi có tổng, mỗi phần không được vượt tổng;
khi có đủ cả ba, tổng phải bằng bắt buộc + tự chọn. PUT thay toàn bộ trường, giá trị tùy chọn
bỏ trống sẽ thành null. Response trả đủ enum và bốn trường này.

Tạo sinh viên:

```json
{
  "fullName": "Sinh viên mẫu",
  "dateOfBirth": "2006-01-01", "gender": "OTHER", "citizenId": "TEST001",
  "classId": 1, "secondaryProgramId": null,
  "schoolEmail": "sv001@example.invalid", "familyPhoneNumber": "0900000000"
}
```

Họ tên và `classId` bắt buộc; MSSV do backend sinh. Backend luôn lấy ngành và chương trình chính từ lớp;
lớp phải có chương trình và cả lớp/chương trình/ngành/khoa phải đang hoạt động.
Không cần gửi `majorId` hay `trainingProgramId`. Nếu gửi, phải khớp với lớp đã chọn.
Chương trình phụ vẫn tùy chọn, không thay thế chương trình chính. Tạo thành công trả `201`, header `Location`, body
`{ "student": {...}, "activationToken": "..." }`. User + Student được tạo trong một
transaction. Người quản lý chuyển token qua kênh đã xác minh cho sinh viên.

`POST /auth/activate` nhận `{ "token": "...", "password": "..." }` → `204`.
Token dùng một lần, hạn 24 giờ. Mật khẩu tối thiểu 12 ký tự, tối đa 72 byte UTF-8.
API kích hoạt vẫn yêu cầu cookie và CSRF; người dùng chưa đăng nhập lấy token CSRF
qua `/auth/csrf` trước khi gọi.

PUT `/students/{id}` gồm họ tên, ngày sinh, giới tính, CCCD, ngành/lớp/chương trình,
email trường, điện thoại gia đình như POST, thêm `bankAccountNumber`, `bankName`,
`status` bắt buộc; không nhận `studentCode`. MSSV và username không đổi sau khi tạo.
PUT bắt buộc có `classId`. Ngành và chương trình chính luôn được lấy từ lớp, kể cả khi
bỏ trống/gửi null hai ID đó. Đổi lớp cập nhật đồng thời ngành và chương trình chính.
Các trường tùy chọn khác bị bỏ trống sẽ thành NULL. Không chuyển sang lớp có chuỗi cha
ngừng hoạt động; vẫn cho sửa hồ sơ giữ nguyên lớp cũ sau khi danh mục ngừng hoạt động.
Xem [quan hệ và chuyển đổi database cũ](ACADEMIC_HIERARCHY.md).

DELETE sinh viên đặt `status=INACTIVE`, khóa tài khoản và hủy token kích hoạt; giữ
hồ sơ, liên hệ và nhật ký. `SUSPENDED`/`INACTIVE` trong PUT cũng khóa tài khoản.
Để khôi phục: ADMIN/STAFF cập nhật lại trạng thái phù hợp, sau đó ADMIN bật tài khoản
qua `/users/{id}/enabled`. Việc cập nhật hồ sơ không tự mở khóa tài khoản.

## Hồ sơ cá nhân và các bản ghi liên quan

- `GET /me/profile`: xem đầy đủ trường hồ sơ của mình.
- `PUT /me/profile`: cập nhật các trường sinh viên được khai báo.
- `GET /me/completion`: trạng thái tính từ dữ liệu hiện tại và danh sách `missingFields`.
- ADMIN/STAFF xem trạng thái qua `GET /students/{id}/completion`.

PUT hồ sơ chỉ chấp nhận: `avatarUrl`, `placeOfBirth`, `oldPlaceOfBirth`, `ethnicity`,
`nationality`, `religion`, `citizenIdIssueDate`, `healthInsuranceNumber`,
`healthInsuranceExpiry`, `freeHealthInsurance`, `personalEmail`, `phoneNumber`, `facebookUrl`.
Đây là thay toàn bộ nhóm trường; trường tùy chọn bỏ trống được xóa. Các ngày theo `YYYY-MM-DD`.
Sinh viên không được sửa MSSV, họ tên, ngày sinh, giới tính, CCCD, ngành/lớp, tài khoản ngân hàng.

Các resource con sau có GET danh sách, GET `/{id}`, POST, PUT `/{id}`, DELETE `/{id}`:

| Resource con | Trường request | Bắt buộc |
| --- | --- | --- |
| `addresses` | `addressType`, `addressLine`, `provinceCity`, `wardCommune`, `residenceRelation`, `current` | `addressType`, `current` |
| `family-members` | `relationship`, `fullName`, `dateOfBirth`, `hasCollegeDegree`, `unavailable`, `phoneNumber` | `relationship`, `hasCollegeDegree`, `unavailable` |
| `emergency-contacts` | `fullName`, `relationship`, `phoneNumber`, `address`, `priority` | tên, điện thoại, `priority` > 0 |
| `post-graduation-contacts` | `fullName`, `phoneNumber`, `email`, `address` | Không; cho phép lưu thông tin chưa đủ |

ADMIN/STAFF dùng `/students/{studentId}/{resource}`; sinh viên dùng `/me/{resource}`.
Danh sách bản ghi con trả mảng JSON theo sinh viên. Không truyền studentId trong body.
Mọi truy cập bản ghi con kiểm tra chủ sở hữu; ID thuộc sinh viên khác trả `404`.
PUT thay toàn bộ bản ghi. Thêm/sửa/xóa đều tính lại `profile_status` trong cùng transaction.

`addressType`: `CURRENT`, `PERMANENT`, `FAMILY_HOME`.
`relationship` của nhân thân: `MOTHER`, `FATHER`, `GUARDIAN`, `OTHER`.
`relationship` của liên hệ khẩn cấp là chuỗi tự do. Những phần chưa đủ thông tin có thể
lưu nháp; API completion chỉ đánh COMPLETE khi đáp ứng toàn bộ điều kiện trong README.

## Quản trị tài khoản và nhật ký

ADMIN có:

- `GET /users`, `GET /users/{id}`: đọc tài khoản, không trả mật khẩu/token hash.
- `POST /users`: `{ "username": "staff01", "role": "STAFF" }`; role chỉ ADMIN/STAFF.
  Trả `201` với `{ "user": {...}, "activationToken": "..." }`.
- `PATCH /users/{id}/enabled`: `{ "enabled": false }` hoặc `true`; không tự khóa chính mình.
  Không bật tài khoản của sinh viên đang INACTIVE/SUSPENDED.
- `POST /users/{id}/activation-token`: cấp lại token cho tài khoản đang bật và chưa đặt
  mật khẩu; token cũ mất hiệu lực. Không dùng để đặt lại mật khẩu tài khoản đã kích hoạt.
- `GET /access-logs`, `GET /access-logs/{id}`: đọc nhật ký. Chưa có filter tự thu thập HTTP;
  API trả các bản ghi hiện có. Không cung cấp sửa/xóa nhật ký.

## Mã phản hồi

- `200`: đọc/sửa, `201`: tạo (kèm Location), `204`: xóa/logout/kích hoạt thành công.
- `400`: dữ liệu không hợp lệ, trường không được khai báo trong DTO, ID sai định dạng,
  quan hệ ngành/lớp/chương trình không hợp lệ hoặc token kích hoạt sai/hết hạn.
- `401`: cần đăng nhập; `403`: thiếu quyền hoặc CSRF.
- `404`: bản ghi không tồn tại hoặc không thuộc hồ sơ đang truy cập.
- `409`: mã/CCCD/email đã tồn tại, danh mục còn được sử dụng, hoặc trạng thái không cho phép thao tác.

Lỗi nghiệp vụ/validation có dạng `{ "status": 400, "message": "Invalid request data" }`;
không trả nội dung input bị từ chối, SQL hoặc stack trace. Kiểm thử chạy trên H2;
chưa xác minh runtime trên PostgreSQL/Nginx của máy ảo.
