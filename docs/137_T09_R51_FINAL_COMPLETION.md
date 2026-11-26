# R51 — Nghiệm thu giám sát và bàn giao

**R51_FINAL_COMPLETION = PARTIAL.** R51 đã triển khai và nghiệm thu luồng giám sát, sửa lỗi mất score khi burst ngắn và dedup replay NGINX. Demo incident đã xuất hiện trên dashboard AWS dưới dạng bản phát lại lab. Các luồng UI/CRUD chưa kiểm hết trên trình duyệt và profile vận hành giữ Prevention OFF.

## Source và phạm vi

Remote `dev/i5-hybrid-prevention` ở `798e66a`, đã có trong nhánh tích hợp trước R51. R51 giữ model R37 HGB URI100, threshold `0.7664756774902344`, cutoff 1.000 ms, guard 1 ms, R36 rollback và chính sách phát hiện hiện hành. R50 cung cấp bằng chứng Gmail nhận thư kích hoạt và thư khôi phục. [Nghiệm thu R50](136_T09_R50_FINAL_PROJECT_ACCEPTANCE.md)

## Điều tra và sửa lỗi

| Hạng mục | Bằng chứng và thay đổi |
|---|---|
| Điểm AI thiếu khi request đến sát nhau | Fixture HTTPS với scorer đã warm, 8 GET đồng thời và pause có kiểm soát 180 ms. Cấu hình cũ tạo 8 correlation, 6 receipt/score và 2 lỗi `EAGAIN` của upstream Unix socket, tức hai request thiếu receipt trước inference. Backlog 16 và một worker cho 8/8 receipt và score, 0 lỗi kết nối. Giữ nguyên deadline, SQLite một writer và điều kiện late/clock. Log R50 thiếu mã lỗi kết nối của lượt 7/8, vì vậy fixture chứng minh cơ chế lỗi, còn nguyên nhân chính xác của request lịch sử chưa thể đối chiếu trực tiếp. [Receiver](../ai-training/contracts/https-shadow-r35/receiver.py) |
| Alert trùng khi ghi lại log | Fixture ghi hai bản sao cùng dòng NGINX ở hai offset. Baseline tạo hai cảnh báo vì physical key khác nhau. R51 ghi và xác minh `r51-main-<trusted-request-id>` như định danh sự kiện NGINX. Replay dòng có cùng ID được khử trùng. Luồng cũ dùng physical identity khi thiếu marker. Sensor identity theo generation/flow/tx và chính sách tổng hợp giữ nguyên. [Parser](../security-web/src/events.rs) |
| Monitoring và Prevention readiness | `/api/ready/monitoring` trả trạng thái DB và watcher. `/api/ready` giữ gate toàn bộ profile. `/api/status` thêm `monitoring_ready` và `prevention_state`. `DISABLED` giữ ý nghĩa cấu hình OFF. Với MANUAL hoặc ENFORCE, trạng thái READY cần readback đồng bộ và discovery hợp lệ. `ACTUATOR_OFFLINE` vẫn hiển thị ở dòng Firewall. [Readiness](../security-web/src/metrics.rs) |

## Hợp đồng theo nhóm API

Đối soát 87 khai báo method/path từ controller và hai action login/logout do Spring Security cấu hình. Tất cả path thuộc đúng một nhóm trong bảng. Biến `route_group` và `observation_leg` phản ánh tuyến quan sát, còn kết quả match, missing hoặc late lấy từ evidence thực tế.

| Nhóm | Khai báo | Leg và giới hạn |
|---|---:|---|
| Identity | 4 | Bốn cặp auth có sẵn đủ điều kiện leg ký và projection khi target trùng chính xác. |
| Account recovery | 6 | Direct, NGINX + audit nếu audit có mặt. Body có proof/token/OTP nằm ngoài leg sensor và scorer. |
| Catalog | 21 | GET chính xác cho profile-options, faculties, majors, training-programs và classes đủ điều kiện leg ký. CRUD, query và detail có nhãn route đã ẩn ID. |
| Student self-service | 25 | GET chính xác `/api/me/completion` đủ điều kiện leg ký. Hồ sơ, academic và contacts dùng metadata direct. |
| Student administration | 26 | Direct. Nhãn route có `[id]`, chưa xác minh match ba nguồn cho các thao tác này. |
| Security administration | 7 | Direct. Log edge giữ route template và loại query. |

Mười cặp đủ điều kiện leg ký giữ cùng contract với R50. Nhóm chưa nhận dạng ghi `unclassified` và đường dẫn ẩn. Quan sát NGINX/Student Audit của direct lane không tự tạo Suricata observation, R37 score hoặc incident match. [Gateway](../security-web/deploy/aws-r48/gateway.py)

## Trình diễn và bàn giao

Trong Security Web mở **AI Shadow → R51 · Demo fixture từ lab cô lập**. Demo replay công khai nguồn dữ liệu lab trong UI. ID `51515151515151515151515151515151` thuộc fixture PostgreSQL riêng. Một rule tạo alert từ metadata NGINX fixture và Rust ghép receipt correlation cùng ID, nhận advisory R37 fixture và ghi một incident `REVIEW`. Fixture chạy re-ingest để kiểm đếm trùng. Replay trong UI tách khỏi DB thật, bộ đếm và SSE AWS. Kiểm SSE `alert.created` dùng lab, SSE `resync` kiểm bằng HTTPS thật. [Demo fixture](../security-web/tests/fixtures/r51-demo.json) · [Security Web](https://websentinal.duckdns.org/)

Các phép thử chọn lọc gồm Student API CRUD, permission, session và completion với 9 test. Security frontend đạt 19 test view model, bộ lọc, session SSE và Hybrid lookup. Python scorer và correlator bao phủ cutoff, conflict, partial worker response, missing health và recovery. Lab Prevention dùng namespace cô lập để kiểm Block, Unblock, TTL và cleanup. Model inference thực tế được đối chiếu riêng với fixture advisory của demo.

## Bảng nghiệm thu

| Chức năng | Trạng thái | Bằng chứng hoặc giới hạn |
|---|---|---|
| HTTPS và Student auth | PASS AWS | Hai website HTTP 200 với xác minh TLS. Student login `f2483dabe98de9b3752d2afb65cac78f` HTTP 204, 654,68 ms. Logout và session rotation đã thử. |
| Gmail, kích hoạt và khôi phục | PASS AWS kế thừa R50 | Hai thư Gmail thật đã được nhận và sử dụng ở R50. R51 đối chiếu `student.env` giống từng byte với backup R50 và giữ nguyên Java PID. |
| Student catalog CRUD | PASS AWS theo mẫu | Tạo, đọc, sửa và xóa Faculty thử trả 201, 200, 200, 204. PostgreSQL xác nhận bản ghi thử đã được xóa. Lần thử đầu nhận 400 vì short code fixture dài hơn giới hạn 10 ký tự, lần sau dùng giá trị đúng contract. Detail `4c903aaac28265c7497f3d88d61193b4`, query `7af9d9281865f8f0aba54ce45be9e365` ghi `catalog/direct`. |
| Student profile, academic, contacts, users và quyền | PASS lab / PARTIAL AWS | 9 Java test có CRUD contact, catalog, phân quyền, user và thu hồi session. Kế thừa R50 cho các API đọc thật. Chưa thực hiện mọi thao tác ghi hoặc kiểm mọi màn hình trên trình duyệt AWS. |
| NGINX, Suricata, Audit, correlator và R37 | PASS AWS theo mẫu | 8/8 GET CSRF qua HTTPS nội bộ EC2 và hai request login/classes đều `NSA` tại cutoff, `SCORED`, `LOG_ONLY`. Burst dùng tối đa bốn client đồng thời, thời gian nhận header 27,15–138,33 ms. Thiếu proof ngoài lane ký được giữ là thiếu. |
| Rules, risk, policies, incident và dedup | PASS lab / PARTIAL AWS | 11 Rust test gồm positive rule với metadata fixture, alert filter/history, triage, SSE, late/conflict và trạng thái khi AI thiếu. Demo có 1 source alert, 1 incident `REVIEW`, advisory `ALERT`, 1 decision audit và 0 thao tác firewall sau replay. AWS xác minh decision thật của request lành tính. |
| Security Dashboard, Audit, Alerts, Rules, AI Shadow, Hybrid, Statistics, operation history | PASS AWS ở lớp HTTP/API / PARTIAL UI | 11 API đọc trả dữ liệu thật. Asset frontend đang phục vụ có demo và trạng thái actuator. Các tương tác frontend đã kiểm bằng 19 test. Chưa có nghiệm thu thao tác trình duyệt cho toàn bộ màn hình. |
| SSE | PASS AWS / lab | AWS nhận `resync` qua HTTPS. Lab kiểm `alert.created` đến hai viewer sau commit. |
| Demo AWS | PASS bản phát lại lab | UI AWS phân biệt fixture. Lookup live theo ID fixture trả danh sách rỗng. Positive alert bằng traffic AWS chưa chạy. |
| Prevention management | PASS lab / DISABLED AWS | Block, Unblock và TTL theo kernel, dedup và cleanup trong namespace. AWS tra proposals/history/block list và giữ 0 action. Public enforcement và AI auto-ban OFF. |
| Readiness | PASS AWS | `/api/ready/monitoring` HTTP 200 với PostgreSQL và sáu watcher. `/api/ready` HTTP 503 với `ACTUATOR_OFFLINE`, Prevention `DISABLED`. |
| Resource và hồi phục | PASS trong cửa sổ kiểm | Scorer, Security và correlator hồi phục qua restart khi cập nhật. Scorer socket chờ readiness một lượt trước khi trả 200. Bảy service active, 0 OOM kill, 0 restart tự động, 1.251 MiB RAM đang dùng và root disk 9%. `logrotate -d` đạt. Reboot toàn host kế thừa R48. |

Mẫu live để trình diễn là `7bb75a337696fca65d9b2100401924e4` cho `GET /api/classes`, hoặc `c2d5a9bc885d2b1a4d2f6fff565322fe` cho một GET CSRF trong burst. Dán ID vào **AI Shadow → Tra cứu** để xem bằng chứng ba nguồn, R37 và Hybrid cùng request. Các ID phụ thuộc retention hiện hành. [Security Web](https://websentinal.duckdns.org/)

## Triển khai, rollback và chi phí

Đã xác minh hai DB có 2 migration Student và 20 migration Security, tạo logical backup và archive release tại `/var/backups/websentinel-r51`, kiểm `pg_restore --list` và manifest SHA. Update unit `websentinel-r51-update.service` thoát 0. `student.env` và `security.env` khớp backup, `scorer.env` chỉ đổi `RELEASE_SHA256` cho manifest runtime chứa bản sửa transport. HTTPS, app data, credentials và Gmail giữ nguyên. Backup manifest `4eb842b3da1b481f1e0feacd22510e12b52e21f92ae409a554c84543c850af87`, NGINX `99fa902dd1602e3e55c11c5ca8100361322a3e4572d78656a674b312fca49203`, Rust binary `f7bd0ae1945e18359de2f006aa8d46aae35af9cdd50980922d2e55eb42db26c7`, scorer manifest `f9969986b131b4a54591462e02227563141a381931713c2be97f0ac3b433d901`. Đường rollback đã cài và backup đọc lại đạt. Lần cập nhật thành công nên chưa thực thi rollback trên AWS. [Runbook R51](AWS_STAGING_OPERATIONS_HANDOFF.md#13-r51--giám-sát-và-demo)

EC2 giữ RUNNING, 3/3 status checks `ok`. Scheduler `ENABLED` mỗi 15 phút, Lambda `MAX_SESSION_MINUTES=480` và `DRY_RUN=true`. AWS Budgets đọc 1,227 USD actual, 2,295 USD forecast và giới hạn 25 USD tại thời điểm kiểm. Các số này là snapshot theo kỳ. [Runbook Billing](AWS_STAGING_OPERATIONS_HANDOFF.md#4-chi-phí-và-billing)
