# Sinh viên mẫu CNTT Đặc thù K2024

Nguồn có 52 sinh viên lớp 24T_DT3. Theo yêu cầu, xếp vào lớp nội bộ
CLS-IT-2024-01 → PRG-IT-2024-ENG-DT → MAJ-IT → FAC-IT.

Chỉ nhập họ tên và quan hệ lớp/ngành/chương trình như admin tạo sinh viên.
Không suy ngày sinh, giới tính, CCCD hay điện thoại từ tên/số thẻ. Không nhập điểm
rèn luyện, số môn/tín chỉ hoặc thời điểm xác nhận. Các phần hồ sơ tự khai giữ trống;
profile_status=INCOMPLETE, profile_completed_at=NULL. free_health_insurance=false
là mặc định entity hiện tại, không phải kết luận về quyền lợi sinh viên.

## Chạy script

1. Đã chạy 005–007, 009, 012, 013; dừng backend.
2. Chạy toàn bộ [014_seed_it_2024_students.sql](sql/014_seed_it_2024_students.sql).
3. Truy vấn cuối script trả bảng đối chiếu số thẻ nguồn, student_id, mã mới, email,
   lớp và user_id. Khởi động lại backend và xem danh sách lớp.

StudentCode được cấp từ counter STU-2024-, tối đa 999999, bỏ qua mã/email/username
đã tồn tại; không dùng số thẻ nguồn làm mã PBL4 hoặc CCCD. Email được sinh từ mã mới.
Không giả định mã bắt đầu 000001 nếu database đã có sinh viên. Không giảm counter.

Bảng student_import_sources lưu số thẻ nguồn → student_id với dataset
pbl4-it-2024-dt3, giúp chạy lại không trùng và không ghi đè sinh viên đã chuyển lớp,
đổi tên, nhập hồ sơ hoặc kích hoạt. Không xóa mapping để chạy lại. Khi có sinh viên
trùng số thẻ gốc hoặc trùng tên trong lớp mà chưa có mapping, script rollback để
đối chiếu; không tự gộp người trùng tên. JSON chỉ giữ số thẻ, họ tên, lớp gốc.

## Sinh viên tự kích hoạt

Tài khoản role=STUDENT, enabled=true, password_setup_required=true. Mỗi tài khoản
có hash bcrypt của một mật khẩu ngẫu nhiên đã bỏ đi; không có mật khẩu mặc định.
Không đặt activation token trong seed và không kích hoạt thay sinh viên.

Admin cấp token qua `POST /api/users/{userId}/activation-token` (session + CSRF),
hoặc chức năng cấp lại mã kích hoạt hiện có. Token có hạn 24 giờ; admin chuyển
riêng cho đúng sinh viên, sinh viên tự đặt mật khẩu qua luồng kích hoạt hiện tại.
Chỉ việc seed dữ liệu chưa gửi email/thông báo hoặc tạo mailbox.

Script không sửa hồ sơ/tài khoản đã được import khi chạy lại. Chưa chạy vào database
thực tế của người dùng.
