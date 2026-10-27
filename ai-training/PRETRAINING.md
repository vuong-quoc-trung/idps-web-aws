# Chuẩn bị trước khi train AI

Phạm vi của bước này là AI offline và lab riêng. Code/cấu hình của Student và
Security được giữ nguyên; canonical schema vẫn là v1.0. Feature hiện hành là
`ai-features-2` gồm148cột, dùng `ai-normalizer-2`. Dataset/checkpoint v1 cũ là bằng
chứng lịch sử; không ép resume chúng bằng source mới.

## Quy trình đã xây và chạy

1. **Tạo lab riêng:** xuất Student từ Git sang thư mục AI rồi build tại đó; dùng
   PostgreSQL rỗng, Nginx loopback riêng, tài khoản và bản ghi giả. Không đọc `.env`,
   credential hoặc DB của các dịch vụ hiện có.
2. **Thu request thật:** gửi các thao tác hợp lệ, lỗi hợp lệ và probe có giới hạn.
   Các chiến dịch có IP nguồn thực được bind trên loopback, user/session riêng,
   ba đợt theo thời gian và hai khoảng chờ thật. Observer ghi request ID và kết quả
   HTTP, không ghi password, cookie, token hay response body.
3. **Đóng băng snapshot:** chọn đúng request ID do observer ghi, giữ cả pending;
   warmup/health ngoài chiến dịch có số đếm và hash riêng. Chỉ đọc nguồn, giữ các dòng JSONL hoàn chỉnh, kiểm lại
   prefix/checksum và ghi rõ tail chưa hoàn chỉnh. Nhiều nguồn được chụp độc lập;
   đây không phải transaction nguyên tử giữa mọi nguồn.
4. **Gắn provenance và nhãn:** nối observer → capture → labels → snapshot → dataset
   bằng SHA-256. Nhãn kịch bản mô tả ý định và kết quả HTTP dự kiến; không khẳng
   định SQLi/XSS/RCE hoặc IDOR đã khai thác thành công.
5. **Chuẩn bị dataset:** khử bí mật, correlation, chia theo thời gian/nhóm, áp
   embargo, fit scaler chỉ trên benign train rồi tính các vector feature.
6. **Kiểm tra readiness:** nguồn, role, nhãn/confidence, số mẫu, nhóm/variant không
   chéo partition, vector hữu hạn và replay parity. Dữ liệu synthetic/demo không
   được dùng để chứng nhận corpus lab đủ điều kiện.
7. **Bàn giao trước fit:** baseline bốn cờ Nginx trên validation, kiểm RAM/disk/I/O,
   CSV review và các lệnh train đã chuẩn bị. Không tự thực thi các lệnh train.

Runbook CLI nằm trong [README](README.md). Kế hoạch pilot ở
[experiment_plan.yaml](configs/experiment_plan.yaml), còn ngưỡng readiness ở
[pretrain_policy.yaml](configs/pretrain_policy.yaml).

## Đọc đúng kết quả

`READY_FOR_OFFLINE_PILOT` nghĩa là dữ liệu đã qua những điều kiện tối thiểu cho một
thử nghiệm offline. Nó **không chứng minh model đã tốt hoặc dùng được trong production**.

- Corpus là HTTP thật trong lab với dữ liệu giả, chưa đại diện traffic người dùng.
- View query riêng của lab khác edge hiện hành đã mask query. Trước triển khai
  phải bảo đảm nguồn feature tương thích hoặc đổi profile rồi đánh giá lại.
- EVE capture chưa có vì không được phép mở packet socket. Không dựng EVE giả để
  bù; flow features giữ trạng thái thiếu. Không nghiệm thu nhánh flow, body payload,
  failed username hoặc object-level IDOR bằng corpus này.
- Các chiến dịch ngắn và chỉ có một số variant. Cần phiên dài hơn và review thêm
  để đánh giá các window60/300giây và ý nghĩa của nhãn hành vi.
- Regression tests dùng những lần train fixture nhỏ để kiểm optimizer/resume.
  **Corpus mới chưa được đưa vào optimizer; giờ train corpus mới bằng0.**
- Chưa tạo champion, tích hợp Rust inference, chạy shadow live hoặc cho AI chặn IP.

Kết quả và checksum của phiên thu được lưu trong
[reports/PRETRAIN_20261027.json](reports/PRETRAIN_20261027.json). Raw logs, khóa,
Parquet và các artifact riêng nằm trong `.artifacts/`, đã được loại khỏi Git.

## Khi quyết định bắt đầu train

Đọc report và các giới hạn trước, giữ tập test để đánh giá cuối, chọn run directory
mới cho từng model. Dùng lệnh trong `NEXT_COMMANDS.txt`: có `--readiness-report`,
khởi đầu5epoch,2threads và tối đa150phút. Nếu chạy xong sớm thì dừng, không kéo dài
chỉ để đủ giờ. Source hoặc dataset đổi thì chạy gate lại; thay learning config cần
experiment mới, không ép resume checkpoint không tương thích.
