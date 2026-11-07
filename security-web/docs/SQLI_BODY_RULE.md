# SQLi Boolean/Union trong POST body — SID 1000025

Giữ SID 1000002 cho URI; thêm SID 1000025, severity 1, `alert http` cho body POST `application/x-www-form-urlencoded` hoặc `application/json`. Rule giải mã URL tối đa hai lần, nhận mẫu quote + OR/AND + phép so sánh và UNION [ALL] SELECT. Đây là heuristic, không phải SQL parser, không bao phủ mọi biến thể/nội dung multipart hoặc body vượt giới hạn inspect. Không kết luận khai thác thành công. Mật khẩu hợp lệ cũng có thể trùng mẫu; không tự bật chặn. Không thay AUTO_BLOCK/ENFORCEMENT_MODE hay allowlist SID.

Rule chỉ thấy HTTP giải mã trên interface sensor. Không bắt buộc client là Kali: mọi client đều có thể được phát hiện nếu request đi qua điểm capture HTTP plaintext. Với lab capture vmnet2, Kali qua 192.168.10.1 là một đường kiểm thử phù hợp. Truy cập localhost:5173 qua VS Code Remote SSH chuyển HTTP bên trong đường hầm SSH tới Vite trên Web VM, nên sensor trên host không đọc được payload. Request từ host tới IP của chính host cũng không bảo đảm đi qua vmnet2. HTTPS không được giải mã tại điểm capture cũng không thể kiểm tra body. Không đưa password/body vào access log hoặc EVE payload. Student Audit vẫn là audit hành vi; alert này mang source SURICATA.

Kiểm thử không phát lưu lượng mạng:

```bash
python3 scripts/test-extended-rules.py ExtendedRuleTests.test_boolean_union_post_body
```

Script tạo PCAP tạm, chạy `suricata -T`, rồi replay offline, kiểm tra form encoded, UNION và JSON dương tính cùng dữ liệu bình thường âm tính.

Cài trên host (người quản trị tự chạy từ security-web):

```bash
# Kiểm tra bản repo trước, không chạy service thứ hai.
sudo suricata -T -c /etc/suricata/suricata.yaml -S "$PWD/suricata/pbl4.rules"
# Chỉ tiếp tục khi -T thành công. Giữ lại bản backup để rollback.
sudo cp -a /var/lib/suricata/rules/pbl4.rules "/var/lib/suricata/rules/pbl4.rules.bak-$(date +%Y%m%d-%H%M%S)"
sudo install -o root -g root -m 0644 suricata/pbl4.rules /var/lib/suricata/rules/pbl4.rules
sudo suricata -T -c /etc/suricata/suricata.yaml
# Chỉ restart khi kiểm tra toàn bộ cấu hình thành công.
sudo systemctl restart suricata
systemctl status suricata --no-pager
```

Nếu kiểm tra sau cài thất bại, khôi phục file backup vừa tạo và chạy -T lại trước khi restart. Backend cần chạy bản code mới để /api/rules và alert SID 1000025 có tên chuẩn. Không có migration DB cho thay đổi này.
