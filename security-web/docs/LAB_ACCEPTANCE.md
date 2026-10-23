# Nghiệm thu lab trên ba VM

Chỉ chạy traffic trên tài nguyên của nhóm. Giữ AUTO_BLOCK=false ban đầu. Các test Rust mô phỏng firewall không thay thế quy trình này. Ghi thời gian, IP, SID, alert ID, audit ID và ảnh trước/sau cho từng tình huống.

## Chuẩn bị

1. Backup PostgreSQL trước migration. Kiểm tra topology và route chiều đi/về bằng ip route, tcpdump trên NIC attacker/protected.
2. Chạy deploy --check, suricata -T theo cấu hình cài trên VM, kiểm tra nginx -t và nft list ruleset.
3. Tạo admin/viewer bằng setup-auth.py. Thêm IP quản trị thật vào IP_WHITELIST. Truy cập dashboard qua mạng quản trị/SSH tunnel để không mất giao diện khi chặn Kali.
4. Kiểm tra trang Trạng thái: DB, watchers và firewall sẵn sàng, DB/kernel đồng bộ. Kiểm tra quyền đọc log của systemd user.

## Các kịch bản bắt buộc

| Kịch bản | Thao tác | Kết quả cần ghi nhận |
|---|---|---|
| HTTP bình thường | Từ Kali: curl -I http://192.168.10.1/ | Web trả response, capture cho thấy đi qua proxy |
| Cảnh báo XSS | Từ Kali: curl --globoff 'http://192.168.10.1/test?q=%3Cscript%3Ealert(1)%3C/script%3E' | Alert Suricata SID 1000003, DB/UI cùng IP và thời gian; chỉ ALERT |
| Quyền viewer | Đăng nhập viewer và thử POST bằng token viewer qua công cụ API | Không có nút quản trị; API trả 403 và không tạo job |
| Whitelist | Admin gửi block IP quản trị được whitelist | API trả 400, không tạo job/block |
| Manual block | Admin chặn 192.168.10.10, có lý do | 202/PENDING rồi audit SUCCESS; DB/kernel khớp |
| Kiểm tra thực sự bị chặn | Từ Kali: curl --max-time 5 -I http://192.168.10.1/ | Không truy cập Web; đối chiếu nft set/counter hoặc tcpdump |
| Unblock | Admin bỏ chặn Kali, chờ audit SUCCESS rồi curl lại | Truy cập Web phục hồi |
| Backend restart | Sinh alert khi backend dừng, giữ nguyên log; khởi động lại | Alert chưa đọc được nhập, alert đã đọc không tăng trùng |
| Rename rotation | Đổi file log theo cấu hình logrotate của dịch vụ, giữ file cũ chưa nén | Backend đọc nốt file cũ và file mới, checkpoint không mất |
| DB gián đoạn | Trong lab, tạm dừng DB, sinh log rồi khởi động DB | Watcher báo lỗi; sau phục hồi alert được lưu, không trùng |
| Firewall lỗi | Trong môi trường test riêng cấu hình helper không tồn tại | Audit ERROR, không ghi AUTO-BLOCK; dashboard báo degraded |
| Khôi phục chặn | Chặn một IP lab, restart backend | Job RESTORE có audit; trạng thái nftables khớp DB |
| Auto-block tùy chọn | Bật AUTO_BLOCK khi đã kiểm thử các bước trên, sinh traffic rule được phép | Job system, audit SUCCESS, alert AUTO-BLOCK; rule khác vẫn ALERT |

Không reset nftables/routing trên máy phát triển. Giữ phiên SSH quản trị riêng khi thao tác VM. Không dùng copytruncate hoặc nén/xóa log chưa đọc nếu cần bảo đảm phục hồi.

## Tiêu chí hoàn thành

- Tất cả kịch bản bắt buộc có kết quả thực tế; failure được ghi rõ, không coi có source code là đã đạt.
- Video thể hiện alert → UI → block → không truy cập được → unblock → truy cập lại.
- Dựng lại được từ README và backup, kiểm tra dữ liệu còn sau restart.
- Đo và ghi hạn chế: độ trễ polling, false positive, rule chỉ quan sát HTTP phù hợp cấu hình; không tuyên bố ngăn chặn mọi tấn công.
