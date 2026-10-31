# Layer 2 — Application Behavior Detection

`STUDENT_AUDIT → ingest/dedup → application_detection → security_alerts → API/React`.
Không thay producer Student, Schema v1, feature schema AI hay Suricata. Không gọi nft
trong detector/frontend. Mọi APP rule luôn ALERT_ONLY, kể cả AUTO_BLOCK=true.

| Code | Cửa sổ theo timestamp | Severity / đề xuất |
|---|---|---|
| APP-1001 | 10 lần401/403 tới /api/auth/* trong60s, cùngIP/producer; gồm GET /api/auth/me | 2; từ20:1, đề xuất BLOCK nếu IP được phép |
| APP-1002 | 8 lần403 tới /api/* trong60s | 2, ALERT_ONLY |
| APP-1003 | 5 đường dẫn nhìn thấy khác nhau trong60s:404 hoặc401/403 tới nhóm sensitive | 2, ALERT_ONLY |
| APP-1004 | 100 http_request trong10s | 2; từ300:1, đề xuất BLOCK nếu IP được phép |
| APP-1005 | 15 outcome=failure, status400/401/403/404 cùng đường dẫn trong60s | 2 nếu có401/403, còn lại3 |

Nhóm sensitive nhỏ gồm admin/actuator/swagger/api-admin/config/.env và endpoint thật
/api/users, /api/access-logs. **Student hiện che segment lạ thành [redacted]**:
/actuator và /.env có thể cùng trở thành /[redacted]. Không khôi phục đường dẫn gốc,
không suy đoán5endpoint từ5request vào cùng chuỗi đã che. Các ID động cũng được che
thành [id]; đây là giới hạn có chủ đích của schema privacy hiện tại, chưa sửa Student.

## State, thời gian và chống spam

Migration0005 chỉ thêm `application_observations` và index. Lý do: detector cần state
ngắn hạn độc lập với COLLECT_ALL_EVENTS, không phụ thuộc retention dataset7ngày.
Các field tối thiểu: event_key, producer, IP, thời gian, path đã chuẩn hóa, status,
outcome; không raw payload/user credentials.

- Cửa sổ (T-window,T], T là timestamp lớn nhất đã thấy cho producer/IP còn trong state.
- Event tới trễ vẫn được đếm nếu còn trong cửa sổ; quá60s so với watermark không tạo alert.
- Timestamp quá5s trong tương lai bỏ qua ở detector để không đẩy watermark sai;
  vẫn lưu canonical event theo ingest hiện có. Đồng bộ đồng hồ các máy.
- Có thể detect lịch sử được replay nhanh theo event time; đây không phải chứng cứ
  tấn công đang diễn ra. Không tự phản ứng với lịch sử.
- State tồn tại qua restart PostgreSQL/backend nhưng hết hạn5phút theo received_at,
  prune mỗi phút và khi nhận event; hard cap100000 hàng giữ dữ liệu nhận gần nhất.
  Khi cap bị vượt hoặc replay cách nhau >5phút, cửa sổ có thể thiếu observation.
- Event identity source+source_instance+event_id được dedup; source receipts hiện có
  vẫn áp dụng khi collect_all=true. State và alert cùng transaction với cursor.
- Advisory lock toàn detector giúp tránh duplicate/đua cập nhật trong MVP. Đây không
  phải thiết kế throughput lớn/distributed; cần đo tải trước khi dùng production.
- Trong cooldown60s (APP1004:10s) tính từ lúc tạo alert, update cùng alert thay vì spam.
  Severity và event_count giữ đỉnh cửa sổ trong episode; window_event_count là số
  hiện tại, first_seen giữ lần đầu, last_seen cập nhật. event_count không là số cuộc
  tấn công. Hết cooldown, nếu vẫn vượt ngưỡng có thể tạo episode mới.

Giữ Suricata riêng source/SID; không gộp hoặc xóa nguồn. Bộ auth counter cũ vẫn nhận
observation Student để hỗ trợ correlation Nginx nhưng không phát legacy auth alert
với source Student nữa: APP1001 chịu trách nhiệm cho nguồn đó. Các detector hiện có
khác vẫn hoạt động. Nhiều APP rule có thể cùng khớp một chuỗi request.

## Hiển thị và response

Rule metadata do `/api/rules` trả, gồm source/code/action_mode/threshold/window.
Alert aggregate nằm trong evidence JSON hiện có, signature=APP-code. API list/detail
hiện tại giữ tương thích. React chỉ đọc, không tự tính threshold.

Cột tổng hợp và drawer hiển thị count/endpoint/reason/đề xuất/first_seen/last_seen.
Admin có nút yêu cầu chặn thủ công. POST /api/blocked-ips nhận event_id tùy chọn,
kiểm tra alert có đúngIP, dùng queue/TTL/whitelist và audit hiện có (actor/API/event_id).
Kết quả manual là BLOCK, không ghi nhầm AUTO-BLOCK. source alert/rule truy ngược qua
foreign key và lý do. Enqueue không đồng nghĩa chặn thành công: OFF vẫn không thực thi.

null IP: bỏ qua detector. Loopback vẫn có thể alert nhưng không đề xuất chặn.
IPv6 có thể detect nhưng actuator hiện chỉ hỗ trợIPv4, nên không đề xuất/thực thi block
IPv6. Host/gateway/WebVM/whitelist được kiểm bằng Safety hiện có cả khi khuyến nghị
và khi admin gọi API. Không đọc X-Forwarded-For trực tiếp.

## Kiểm tra và chạy

Không migrate DB thật trong phiên lập trình. Backend khi khởi động sẽ chạy migration
0005 như các migration hiện có; không reset bảng cũ. Sao lưu DB theo quy trình dự án
trước triển khai. Giữ AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF.

```bash
cd security-web
cargo fmt --all -- --check
cargo check --locked --offline
# DATABASE_URL phải trỏ tới PostgreSQL TEST RIÊNG; sqlx tests tạo DB test.
cargo test --locked --offline
cd frontend
npm test
npm run build
```

Các test mới kiểm9/10 auth, cooldown/25escalation, resend không tăngcount,
99/100/300burst, loopback/IPv6/nullIP, Suricata đồng thời, APP1002/1003/1005,
redacted path không bị đếm sai, windowexpiry/lateevent/restart, manual response
liên kết actor/alert và reject IP protected/mismatch. Helper firewall luôn mocked.

Manual demo sau khi tự restart backend bản mới: trên Kali, chỉ vào lab proxy:
```bash
for i in $(seq 1 10); do
  curl --noproxy '*' --connect-timeout 3 --max-time 5 -s -o /dev/null \
    http://192.168.10.1/api/auth/me
  sleep 0.2
done
```
401 chưa đăng nhập là bình thường; mở Alerts lọc STUDENT_AUDIT, tìm APP-1001.
Không cần đăng nhập sai tài khoản thật. Kiểm tra chuỗiđến file local qua RELP và timestamp
phù hợp trước khi kết luận detection lỗi. Thêm10request trong60s tăng cùngalert lên
severity1/recommendBLOCK nếu IP không protected; không có firewall action tự động.
APP1004/300 nên nghiệm thu bằng fixture/testDB riêng để không tạo tải app thật.

Application Audit là quan sát thô; Alerts là tổng hợp. Bảng Application Audit hiện
vẫn cần nút Tải lại; migration này không thêm polling/SSE. Không tự đổi .env hoặc
restart dịch vụ host trong phiên triển khai code.
