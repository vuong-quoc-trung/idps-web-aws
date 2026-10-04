# Sinh mã PBL4

API thay đổi: các request khoa/ngành dùng `shortCode` thay cho `code`.
Request chương trình/lớp không nhận `code`; tạo sinh viên không nhận `studentCode`.
Các field không được khai báo bị trả 400, không âm thầm dùng mã client gửi.
Response giữ `code`/`studentCode`; khoa/ngành trả thêm `shortCode`.

| Entity | Quy tắc | Input tạo mã |
|---|---|---|
| Faculty | FAC-IT | shortCode |
| Major | MAJ-IT | shortCode, facultyId |
| TrainingProgram | PRG-IT-2024-ENG | majorId, cohort, degreeType |
| StudentClass | CLS-IT-2024-01 | programId |
| Student | STU-2024-000001 | classId |
| School Email | stu2024000001@sv.pbl4.edu.vn | studentCode |

`shortCode` trim và uppercase bằng Locale.ROOT, 1–10 ký tự ASCII chữ/số,
bắt đầu bằng chữ. Không nhận prefix FAC-/MAJ-. `cohort` là năm 4 chữ số.
Degree mapping: ENGINEER=ENG, BACHELOR=BSC, MASTER=MSC.
Program lấy shortCode từ entity Major qua FK, không parse majorCode/classCode.
Class lấy Major và cohort từ Program; cohort client gửi nếu có phải khớp.
Student lấy cohort từ Class. Tài khoản mới có username bằng studentCode sinh ra.

## Ví dụ request (cần session + CSRF như trước)

```json
{"shortCode":" it ","name":"Công nghệ thông tin","active":true}
```
POST /api/faculties -> FAC-IT.

```json
{"shortCode":"it","name":"Công nghệ thông tin","facultyId":1,"active":true}
```
POST /api/majors -> MAJ-IT.

```json
{"name":"Kỹ sư IT 2024","majorId":1,"cohort":2024,"degreeType":"ENGINEER","active":true}
```
POST /api/training-programs -> PRG-IT-2024-ENG.

```json
{"name":"Lớp IT 01","programId":1,"active":true}
```
POST /api/classes -> CLS-IT-2024-01.

```json
{"fullName":"Nguyễn Văn A","classId":1}
```
POST /api/students -> student.studentCode=STU-2024-000001, kèm activationToken.
ID trong ví dụ phải thay bằng ID thật trả về từ API trước đó.

## Đồng thời và cập nhật

CodeGenerationService tập trung quy tắc; CodeCounterAllocator dành số trong
transaction REQUIRES_NEW, khóa PESSIMISTIC_WRITE trên mỗi dòng code_counters.
Khởi tạo scope cạnh tranh được bảo vệ bởi PK; nếu thua insert thì rollback
transaction khởi tạo, đọc lại trong transaction mới rồi mới khóa/tăng counter.
Scope lớp là shortCode ngành + cohort (dùng chung giữa các loại bằng), scope
sinh viên là cohort. Không dùng COUNT+1. Counter tồn tại qua restart; có thể
có khoảng trống khi nghiệp vụ rollback. Số sinh viên tối đa 999999/khóa, vượt
ngưỡng trả lỗi thay vì lặp lại mã. Sequence lớp tối thiểu 2 chữ số, mở rộng 100…
Mã đã có trong DB được bỏ qua; UNIQUE trên entity và username vẫn là bảo vệ cuối.
Không reset counter khi xóa dữ liệu. Không dùng mã làm PK hay suy luận quan hệ.

Mã sinh viên và username không đổi khi chuyển lớp/ngành. Mã lớp giữ nguyên khi
sửa tên/năm học; đổi chương trình hợp lệ thì backend cấp mã lớp mới. Mã chương
trình được tính lại từ dữ liệu; tổ hợp ngành + khóa + loại bằng + variantCode bị trùng trả 409.
Không đổi shortCode ngành đã có chương trình/lớp/sinh viên. Không đổi cohort
đã có của chương trình đang được sử dụng để tránh làm lệch cohort của lớp.
Các quy tắc kiểm tra quan hệ, tín chỉ và phân quyền trước đây vẫn được giữ.

## Database hiện có

Chạy docs/sql/005_generated_codes.sql sau 001–004. Script chỉ thêm cấu trúc,
không tự đổi mã cũ hoặc tài khoản đã có. Chưa chạy script trên PostgreSQL thật.
Khoa/ngành cũ có shortCode=null cần được gán giá trị rõ ràng qua API cập nhật;
không tự đoán từ tên hoặc mã cũ. Việc gán shortCode đầu tiên đồng thời sinh mã
FAC-/MAJ- tương ứng. Program cũ cần cohort/degreeType; nếu cohort trước đó null
có thể bổ sung qua API. Sau đó cập nhật lớp để lấy cohort từ Program qua FK.
Chỉ tạo sinh viên mới khi lớp đã có cohort hợp lệ.
Không chuyển đổi studentCode cũ: giữ nguyên định danh/tên đăng nhập đã sử dụng.

Frontend đã chuyển form tương ứng; với dữ liệu cũ hãy bổ sung từ khoa -> ngành
-> chương trình -> lớp trước khi tạo sinh viên.

## Biến thể chương trình và dữ liệu Khoa Cơ khí

`variantCode` tùy chọn, trim/uppercase, 1–6 chữ/số ASCII bắt đầu bằng chữ.
Null hoặc chuỗi trắng giữ mã cũ; có giá trị thì thêm `-{variantCode}` sau loại bằng.
Ví dụ `PRG-MTE-2020-ENG` và `PRG-MTE-2020-ENG-CLC` cùng tồn tại.
Không suy biến thể từ tên. POST/PUT nhận và response trả `variantCode`;
PUT là thay thế đầy đủ, nên phải gửi lại biến thể khi sửa chương trình đặc biệt.
Độ dài tối đa của mã là 30 ký tự, vừa cột hiện tại.

Chạy [007_program_variants.sql](sql/007_program_variants.sql) trước khi dùng backend mới.
Xem [danh mục Khoa Cơ khí](MECHANICAL_CATALOG.md) để đối chiếu 3 ngành, 55 dòng nguồn,
21 chương trình đã rõ loại bằng và 34 dòng chờ xác nhận.

Danh mục bổ sung: [CNTT, Giao thông/Năng lượng và Nhiệt](ADDITIONAL_CATALOGS.md),
seed 009–011 gồm 6 ngành và 66 CTĐT đã rõ bằng; 120 dòng nguồn chờ xác nhận.

## School Email

`CodeGenerationService.schoolEmail(studentCode)` trim, bỏ dấu `-`, lowercase với
`Locale.ROOT`, nối `@sv.pbl4.edu.vn`. Email chỉ sinh lúc onboarding sau khi cấp mã.
Không có trong request tạo/cập nhật, nhưng có trong response. Mã và email giữ
nguyên khi đổi tên hoặc quan hệ học thuật. Database bắt buộc NOT NULL, UNIQUE.
Chạy migration [012](sql/012_student_school_email.sql) cho database đã có dữ liệu;
email cũ không trống được giữ nguyên, chỉ backfill email thiếu từ mã sinh viên.
