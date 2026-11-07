# APP-1011–1016: quyết định bảo mật từ Student Web

Các rule mới dùng nguồn `STUDENT_AUDIT`, chỉ tạo `ALERT`, không gọi firewall hoặc khóa tài khoản. Spring tiếp tục từ chối request ngay tại nơi kiểm tra quyền. Giữ `AUTO_BLOCK=false`, `ENFORCEMENT_MODE=OFF` khi nghiệm thu.

| Rule | Điều kiện, phạm vi đang triển khai | Severity |
|---|---|---|
| APP-1011 | Cùng IP/source_instance, 8 tài khoản đăng nhập thất bại khác nhau trong 300 giây; dùng username HMAC, không phải 8 lần cùng tài khoản | 2 |
| APP-1012 | Cùng user HMAC/source_instance bị từ chối 5 đối tượng khác nhau trong 60 giây. Hiện áp dụng family-members, emergency-contacts, post-graduation-contacts; chỉ đánh dấu khi đối tượng tồn tại nhưng không thuộc student đang truy cập. Giữ response 404 | 2 |
| APP-1013 | Một JSON request vào DTO record chứa trường top-level bị cấm: role, isAdmin, ownerId, userId, studentId, authorities, permissions. Trả 400 trước binding. Riêng role của CreateUserRequest admin được phép | 1 |
| APP-1014 | Người đã xác thực không đủ quyền thực hiện mutation tại /api/users hoặc /api/users/{id}/enabled, /activation-token; Spring trả 403. Không suy diễn từ lỗi CSRF | 1 |
| APP-1015 | Cùng IP 10 lần sử dụng session không hợp lệ/bị thu hồi trong 60 giây; trả 401. Request không có session và chưa đăng nhập không được tính | 2 |
| APP-1016 | Một mutation dùng phiên của tài khoản đã disabled hoặc đang bắt buộc thiết lập mật khẩu; ActiveAccountFilter từ chối 401. Không có rule “hồ sơ khóa” vì hệ thống chưa có nghiệp vụ đó | 2 |

Rate limiter đăng nhập hiện có vẫn được giữ; đây không phải cơ chế rate limit mới động theo APP-1011. Không khẳng định tài khoản bị chiếm đoạt hay đối tượng đã bị truy cập thành công. NAT/proxy có thể gộp nhiều người vào một IP; cấu hình trusted proxy và IP attribution phải đúng.

## Dữ liệu và tương thích

Schema canonical 1.0 có thêm object tùy chọn `security`: `reasons`, `account_hmac`, `object_hmac`, `forbidden_fields`. Giá trị username/ID đối tượng chỉ giữ trong request rồi HMAC trước JSONL; không xuất password, token, cookie, body hoặc giá trị trường bị cấm. Parser giới hạn danh sách lý do/trường, không nhận object tùy ý. Payload JSON quá 1 MiB bị từ chối trên các DTO được kiểm tra. Chỉ xét top-level, chưa tuyên bố bao phủ mọi kiểu mass assignment/nested JSON.

- Audit cũ không có `security` vẫn đọc được. Backend cũ có deny_unknown_fields sẽ từ chối audit mới chứa `security`: phải triển khai consumer trước producer.
- RELP sender/receiver và đường dẫn log không đổi; JSONL vẫn một event/một dòng.
- Migration `0007_security_signals.sql` thêm bảng trạng thái riêng; không sửa/xóa bảng cũ. TTL theo thời gian nhận 10 phút, tối đa 100.000 dòng, dedup theo event_key; cùng transaction ingest. Cửa sổ theo thời gian sự kiện, nhận trễ trong cửa sổ có thể hoàn tất threshold. Quá giới hạn TTL/cap có thể mất ngữ cảnh đếm, không mất canonical log do cơ chế này.
- Các nhóm tách theo source_instance, IP; riêng APP-1012 theo user HMAC kể cả nhiều IP. Cooldown gộp cùng rule/subject, không tạo alert cho từng lần lặp. HMAC key phải ổn định; thay key sẽ bắt đầu nhóm danh tính mới.
- Rule dựa vào dữ liệu server-confirmed, không tái gán lý do cho các 401/403 cũ. APP-1001–1010 vẫn giữ logic.
- Snapshot hợp đồng AI được cập nhật cho trường tùy chọn, reader bỏ qua security; feature schema/vector và nhãn AI không đổi. Dataset manifest cũ có hash schema cũ có thể bị kiểm tra phiên bản từ chối: giữ dataset cùng revision cũ hoặc tái export bằng bản mới, không sửa hash của artifact cũ để lách kiểm tra.

## Triển khai và nghiệm thu

1. Sao lưu DB theo quy trình hiện tại. Build/test Rust và frontend. Triển khai Security backend mới trước; SQLx tự áp dụng migration khi backend khởi động (chưa áp dụng DB thật trong lần sửa code).
2. Sau khi backend hoạt động, build và triển khai Student Web mới. Giữ HMAC key/RELP config hiện có. Không cần thay .env, schema DB Student hoặc network/firewall.
3. Dùng tài khoản lab và dữ liệu thử để kiểm tra các hành vi trên. Với thao tác bị từ chối, xác nhận dữ liệu nghiệp vụ không thay đổi; không dùng tài khoản thật/production cho thử nghiệm.
4. Đối chiếu event JSONL nguồn → file receiver → Audit ứng dụng → Cảnh báo. Các alert hiển thị APP-1011…1016, source STUDENT_AUDIT, action ALERT; xem evidence để biết số distinct/decision. Request bình thường, anonymous 401 và CSRF 403 không tạo các nhãn nhạy cảm này.
5. Kiểm tra trang Luật phát hiện có 16 rule ứng dụng từ metadata backend. Test restart/replay không tạo lại cùng event; không xóa cursor/receipt để thử.

Rollback: ngừng producer mới/chuyển Student về bản cũ trước, xử lý hết backlog chứa security bằng backend mới. Backend cũ không đọc được backlog mới nên không hạ backend khi còn log mới chưa ingest. Giữ migration/bảng dữ liệu, không reset DB, cursor hoặc rsyslog queue. Không thay SSHFS/RELP.
