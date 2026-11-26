# R52 — Nghiệm thu chức năng và AWS staging

**R52_FINAL_FUNCTIONAL_CLOSURE = PARTIAL.** Bản cập nhật đang phục vụ trên EC2. Đã kiểm trực tiếp hai website bằng Firefox, mở rộng observability theo nhóm danh mục, và chạy actual Rust pipeline với fixture đánh dấu trong một namespace riêng trên AWS. Các luồng ghi ngoài mẫu, phát hiện dương tính từ traffic thật và nghiệm thu enforcement public vẫn còn giới hạn.

## Phạm vi và bản sửa

HEAD `798e66a` của `dev/i5-hybrid-prevention` đã có trong nhánh tích hợp. R52 dùng các bản build và nghiệm thu R50–R51 cho Gmail, scorer R37, thời hạn 1.000 ms và guard 1 ms. [R51](137_T09_R51_FINAL_COMPLETION.md)

- Leg ký đã mở rộng theo cả nhóm GET của Khoa, Ngành, Chương trình và Lớp. Hai mẫu mới là một ID số có giới hạn cho detail và tham số phân trang `page`/`size` dạng số. Query tự do, tham số trùng, ID ngoài giới hạn, request có body trên các mẫu mới và route hồ sơ hoặc auth recovery đi direct. Log NGINX giữ nhãn `/api/<nhóm>/[id]` hoặc collection template. Giá trị phân trang và catalog ID được quan sát trên leg loopback có phạm vi cố định, theo contract URI100 đã có. [Gateway](../security-web/deploy/aws-r48/gateway.py)
- HMAC xác minh đúng method và target trên wire. Correlator kiểm scope sensor, receipt và status như trước rồi đối chiếu nhãn route với Student Audit. Hai request có cùng nhãn chuẩn hóa vẫn có HMAC target riêng. Regression sửa giá trị số trên wire và nhận `AMBIGUOUS`, với danh sách nguồn rỗng. [Correlator](../security-web/deploy/aws-r48/correlate.py) · [Regression](../security-web/deploy/aws-r48/test_correlate.py)
- Browser tái hiện lỗi sửa Khoa. Form điền `FAC-…` vào trường `shortCode` bị khóa và validation từ chối Lưu. Khoa và Ngành giờ ưu tiên `shortCode` do DTO trả về. Trường hợp DTO cũ được xử lý bằng việc bỏ đúng tiền tố display code. [Khoa](../student-web/frontend/src/components/catalog/FacultyTab.tsx) · [Ngành](../student-web/frontend/src/components/catalog/MajorTab.tsx)

## Evidence AWS theo request ID

| Giao dịch | Request ID | HTTP header | Kết quả |
|---|---|---:|---|
| Lớp phân trang | `c5495071999bc40a04014e9160bcc2a4` | 23,79 ms | `NSA / SCORED / LOG_ONLY` |
| Lớp detail | `3bc0f851eb1b2b0bbcf2fa2e7f8d7610` | 71,44 ms | `NSA / SCORED / LOG_ONLY` |
| Khoa phân trang | `6d5968a42e721631f57ba7d374b4ff11` | 26,17 ms | `NSA / SCORED / LOG_ONLY` |
| Khoa detail | `169d59d1d14ec8def321aca6177a67fa` | 71,48 ms | `NSA / SCORED / LOG_ONLY` |
| Ngành phân trang | `df71b9b19d300e79a91540cbf3161131` | 97,70 ms | `NSA / SCORED / LOG_ONLY` |
| Ngành detail | `c3d2f8c60faaa1ee34f089345264f89b` | 88,86 ms | `NSA / SCORED / LOG_ONLY` |
| Chương trình phân trang | `7a7bfb373d22681a7e7c32563629b4af` | 93,92 ms | `NSA / SCORED / LOG_ONLY` |
| Chương trình detail | `f16d48e73abe31033c573cd006c8b9c4` | 94,75 ms | `NSA / SCORED / LOG_ONLY` |

Tất cả mẫu trên có một NGINX observation và một correlation theo ID, score R37 đúng SHA và nằm trong cutoff. Query direct có giá trị canary `5c1c89996f73edede522dc69589809f9` giữ nguyên phản hồi ứng dụng và không phát score. Kiểm đuôi bốn journal NGINX, EVE, Student Audit và scorer xác nhận giá trị canary không xuất hiện. Tra một ID thuộc bảng ở **Security Web → AI Shadow → Tra cứu**. [Security Web](https://websentinal.duckdns.org/)

## Browser và rollback

Firefox điều khiển bằng WebDriver trên hai public URL. Student đăng nhập, mở cả bốn tab danh mục và thực hiện tạo, sửa, xóa Khoa/Ngành bằng form. Khoa giữ giá trị sửa sau reload. Bản ghi thử của cả hai lượt dựng lại lỗi và kiểm thử bản sửa đều được dọn. Security đăng nhập, mở tám tab, thấy SSE `Đã kết nối`, kiểm dòng actuator và tra ID `c5495071999bc40a04014e9160bcc2a4`, hiển thị quyết định `LOG_ONLY` của request thật.

Build Student TypeScript và Vite đạt, 7 test utility đạt. Test correlator 6/6. Namespace fixture NGINX, Suricata và R37 thấy 10/10 match và score trước cutoff với Audit origin fixture, gồm mẫu detail, phân trang và các mẫu direct kiểm riêng. Dịch vụ AWS PostgreSQL nhận kết nối, bảy unit active và năm cgroup ứng dụng/AI/sensor báo `oom_kill=0`. RAM 1.346 MiB, root disk 9% lúc readback. Ba env giữ từng byte, bao gồm Gmail. SHA model R37 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`.

Gateway SHA `45fb9408b6e4983318398008180e864659dd0ab1e212c0317baac1cd30b36bdc`, backup manifest SHA `58da5afff9a703bef4f23f20c20abe761fdbf5fa537aeddc60b7375d7e23eb70`. Student index SHA `cbacf75ec98ffe7da2c8b5cb10e3038f4e11ad88c274410576ae0da7adc72752`, backup manifest SHA `71b0fea5e7366c9720542c608b5f3ad34dfe00fc6477c523b53979d09dc9b890`. Logical dumps và archive release thuộc backup gateway. Hai manifest đã đọc lại thành công. [Runbook R52](AWS_STAGING_OPERATIONS_HANDOFF.md#14-r52--catalog-observation-và-student-ui)

## Nghiệm thu theo hạng mục

| Hạng mục | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| `REQUEST_COVERAGE` | PASS AWS nhóm catalog, PARTIAL ngoài nhóm | 8/8 request AWS trong bảng. Route nhạy cảm tiếp tục direct, khi có Audit thì giữ hai nguồn theo evidence. |
| `STUDENT_UI_CRUD` | PASS AWS theo mẫu, PARTIAL toàn bộ | Firefox thử Khoa/Ngành Create, Read, Update, Delete. Chương trình và Lớp đã kiểm qua các tab dùng API thật. Các form ghi hồ sơ, contacts, lớp/chương trình và vòng đời user chưa có bước browser tương đương. |
| `SECURITY_UI_FUNCTIONS` | PASS AWS theo mẫu, PARTIAL thao tác ghi | Tám tab, tình trạng actuator, SSE và Hybrid lookup thật. Triage và quyền của API Prevention chạy trong fixture AWS cô lập. UI write trên các incident thật nằm ngoài mẫu. |
| `CORRELATION_AND_DEDUP` | PASS AWS theo mẫu và fixture | 8 match NSA đúng hạn, mỗi request có đúng một NGINX observation. Đổi wire target trong cùng template bị quarantine. Rust fixture kiểm replay và giao dịch đến muộn. |
| `AI_RUNTIME` | PASS AWS | 8 R37 score với SHA và threshold đã khóa. Projection ngoài allowlist không tạo score trong mẫu privacy. |
| `HYBRID` | PASS AWS theo hai chế độ kiểm | Traffic lành tính `LOG_ONLY`, mẫu đánh dấu trong lab `REVIEW` với advisory fixture `ALERT`. |
| `AWS_ISOLATED_ALERT_PIPELINE` | PASS AWS cho fixture runtime, PARTIAL native positive end-to-end | Unit `websentinel-r52-pipeline-proof.service` trong network namespace chỉ có `lo`, PostgreSQL tạm với Unix socket, chạy Rust build đã xác minh SHA. 5/5 test, exit 0, 180,1 MiB peak. Fixture `51515151515151515151515151515151` đi qua ingestion từ log NGINX, tạo một alert, một incident và một decision audit khi replay. Correlation receipt và điểm advisory dương tính là dữ liệu đầu vào fixture. Sensor và inference thật được kiểm riêng bằng request lành tính. |
| `DASHBOARD_AND_SSE` | PASS AWS theo mẫu và fixture | Browser kết nối SSE và hiển thị Hybrid theo ID thật. Test AWS cô lập quan sát `alert.created` sau PostgreSQL commit tới hai viewer. Alert fixture nằm trong DB tạm và không xuất hiện trên gateway công khai. |
| `PREVENTION_LAB` | PASS lab | Kernel trong namespace cô lập thực hiện Block, Unblock, TTL và cleanup. Fixture AWS kiểm quyền/route đóng. Browser public hiển thị actuator chưa hoạt động. |
| `PUBLIC_ENFORCEMENT_STATE` | DISABLED | Prevention `DISABLED`, `/api/ready` 503 và monitoring ready. Số `firewall_actions` AWS vẫn là 0. AI auto-ban OFF. |
| `AWS_DEPLOYMENT` | PASS | Gateway và Student UI đã deploy thành công, backup và resource readback đạt. |
| `GIT_PUSH` | Xem Git | Commit vào nhánh tích hợp hiện có. |
| `REMAINING_BLOCKERS` | PARTIAL | Browser write ngoài mẫu, native positive alert qua toàn bộ chuỗi và gate public enforcement. |
| `EC2_FINAL_STATE` | RUNNING | EC2 3/3 status checks `ok`. |

Điều kiện trước khi cân nhắc Public Firewall hoặc AI auto-ban gồm ràng buộc IP client qua trusted edge thực tế, phạm vi được phép, danh sách IP bảo vệ, actuator đã kiểm tra readback/TTL/rollback và kết quả đánh giá độc lập cho false block. R37 chỉ có quyền advisory theo manifest hiện hành. Cần chính sách phát hành độc lập cho bất kỳ quyền thực thi mới nào. [Baseline R51](137_T09_R51_FINAL_COMPLETION.md)
