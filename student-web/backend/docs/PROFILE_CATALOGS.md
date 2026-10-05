# Danh mục hồ sơ và liên hệ

Dừng backend và chạy `docs/sql/015_profile_countries.sql` trước khi triển khai. Script giữ nguyên dữ liệu cũ, thêm quốc gia mặc định VN. Cần chọn lại quốc gia cho địa chỉ nước ngoài đã có.

`GET /api/profile-options` yêu cầu đăng nhập và cung cấp danh mục chung cho frontend/backend. Việt Nam dùng dropdown tỉnh và xã/phường/đặc khu phụ thuộc tỉnh; nước ngoài cho nhập tự do. Quốc gia nơi sinh, quê quán và địa chỉ độc lập với quốc tịch. Quê quán hỗ trợ cả tỉnh trước sáp nhập. Dân tộc, tôn giáo và quan hệ với nơi ở dùng enum tại common/catalog; dữ liệu vẫn lưu bằng tên để tương thích bản ghi cũ. Giá trị cũ ngoài danh mục được giữ nếu không thay đổi.

## Nguồn dữ liệu

Snapshot tại `src/main/resources/catalogs/vietnam-divisions.json`: 34 tỉnh/thành phố, 3.321 xã/phường/đặc khu, đối chiếu ngày 05/10/2026.

- Tỉnh: https://danhmuchanhchinh.nso.gov.vn/
- Xã/phường: https://danhmuchanhchinh.nso.gov.vn/DiaBan1.aspx
- XLS nền và tỉnh cũ: https://thongkehochiminh.nso.gov.vn/Category/ChiTietDanhMucTinh?ma=11
- Dân tộc: https://www.nso.gov.vn/phuong-phap-luan-thong-ke/danh-muc/cac-dan-toc-viet-nam/

Dữ liệu đóng gói cùng backend, không gọi website ngoài khi mở form. sourceSha256 là checksum XLS nền; provinceCheckedAt và wardCheckedAt ghi ngày đối chiếu trực tuyến. Khi cập nhật snapshot cần đối chiếu nguồn chính thức và chạy ProfileValidationTests. Tôn giáo là danh sách lựa chọn nội bộ của ứng dụng.

## Validation

Email và điện thoại được kiểm tra ở cả frontend và backend cho hồ sơ, người thân, liên hệ khẩn cấp, liên hệ sau tốt nghiệp và số điện thoại gia đình do admin nhập. Email chấp nhận mọi nhà cung cấp, bỏ khoảng trắng đầu/cuối và kiểm tra cấu trúc. Điện thoại hỗ trợ dạng Việt Nam 0/+84 và quốc tế có dấu +; bỏ khoảng trắng, dấu chấm, ngoặc và gạch nối khi lưu. Trường tùy chọn có thể trống; số liên hệ khẩn cấp vẫn bắt buộc. Đây là kiểm tra định dạng, không xác minh chủ sở hữu hay khả năng nhận thư/cuộc gọi.

Các trường quốc gia mới là birthCountryCode, originCountryCode và countryCode (địa chỉ), dùng mã ISO hai ký tự. API cập nhật hồ sơ giữ ngữ nghĩa thay thế hiện có: gửi đủ trường cần giữ, bao gồm boolean freeHealthInsurance. Email trường tự sinh không thay đổi.
