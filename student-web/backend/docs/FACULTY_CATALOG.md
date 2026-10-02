# Danh mục khoa PBL4 từ ảnh người dùng

Giữ riêng các mục có hậu tố theo xác nhận của người dùng: 16 khoa.
Tên tiếng Anh và shortcode là quy ước nội bộ PBL4, không phải tên/mã chính thức của trường.
Tên hiển thị giữ tiếng Việt trong faculty_name; tên tiếng Anh lưu thêm trong description.
Không diễn giải ý nghĩa (N), (SK), (MT), (X2), (X3), (122), (123); giữ nguyên để phân biệt.

| Tên khoa | Tên tiếng Anh | shortCode | facultyCode |
|---|---|---|---|
| Khoa Cơ khí | Faculty of Mechanical Engineering | ME | FAC-ME |
| Khoa Công nghệ Thông tin | Faculty of Information Technology | IT | FAC-IT |
| Khoa Cơ khí Giao thông và Năng lượng | Faculty of Transportation and Energy Engineering | TEE | FAC-TEE |
| Khoa Cơ khí Giao thông và Năng lượng (N) | Faculty of Transportation and Energy Engineering (N) | TEEN | FAC-TEEN |
| Khoa Điện | Faculty of Electrical Engineering | EE | FAC-EE |
| Khoa Điện tử và Trí tuệ nhân tạo | Faculty of Electronics and Artificial Intelligence | EAI | FAC-EAI |
| Khoa Hóa, Môi trường và Khoa học sự sống | Faculty of Chemical, Environmental and Life Sciences | CELS | FAC-CELS |
| Khoa Cơ khí Giao thông và Năng lượng (SK) | Faculty of Transportation and Energy Engineering (SK) | TEESK | FAC-TEESK |
| Khoa Xây dựng (X3) | Faculty of Civil Engineering (X3) | CEX3 | FAC-CEX3 |
| Khoa Xây dựng | Faculty of Civil Engineering | CE | FAC-CE |
| Khoa Xây dựng (X2) | Faculty of Civil Engineering (X2) | CEX2 | FAC-CEX2 |
| Khoa Hóa, Môi trường và Khoa học sự sống (MT) | Faculty of Chemical, Environmental and Life Sciences (MT) | CELSMT | FAC-CELSMT |
| Khoa Quản lý dự án và Công nghiệp | Faculty of Project and Industrial Management | PIM | FAC-PIM |
| Khoa Kiến trúc | Faculty of Architecture | ARCH | FAC-ARCH |
| Khoa Điện tử và Trí tuệ nhân tạo (122) | Faculty of Electronics and Artificial Intelligence (122) | EAI122 | FAC-EAI122 |
| Khoa Điện tử và Trí tuệ nhân tạo (123) | Faculty of Electronics and Artificial Intelligence (123) | EAI123 | FAC-EAI123 |

## Phạm vi

- Bỏ “Tất cả” vì đây là bộ lọc.
- Không đưa “P. Đào tạo và BĐCL” và “Trung tâm AEC” vào bảng khoa.
- Khoa cùng tên nhưng khác hậu tố là bản ghi riêng, có ID và mã riêng.
- Không gộp, xóa hoặc chuyển quan hệ ngành của bất kỳ khoa cũ nào.

## Áp dụng

Chạy `docs/sql/006_seed_pbl4_faculties.sql` sau migration 005 trên PostgreSQL.
Script đối chiếu tên hoặc mã với danh sách cố định, cập nhật đúng ID nếu có;
nếu chưa có sẽ thêm khoa. Giữ active của khoa cũ, mô tả cũ và mọi foreign key.
Nếu có nhiều bản ghi khớp hoặc mã đã thuộc khoa tên khác, script dừng/rollback
để người quản lý đối chiếu. Không tự sửa ngành/chương trình/lớp/sinh viên.
Chạy lại không thêm khoa trùng hoặc lặp phần mô tả tiếng Anh.

`docs/data/pbl4-faculties.json` chứa payload POST /api/faculties từng khoa;
chỉ dùng cách này cho khoa chưa tồn tại (API tạo trùng trả 409).
Không cần chạy cả seed SQL và POST lại cùng danh sách.
