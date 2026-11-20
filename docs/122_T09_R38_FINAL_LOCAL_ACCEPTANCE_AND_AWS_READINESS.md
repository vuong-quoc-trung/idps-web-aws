# R38 — Nghiệm thu cuối hệ thống Local và bàn giao AWS staging

**AI_RUNTIME_READY = PASS.** R37 đang chạy bằng user service bền vững. Trong lượt HTTPS cuối, cả 30 request có đúng HTTP outcome, Student Audit, score và quyết định Hybrid gắn cùng trusted request ID. Có 29 request ghép đủ ba nguồn sau đối soát. Tại cutoff 1.000 ms với guard 1 ms, chỉ 16 request đủ NSA. Profile hệ thống chính thức và chuỗi Hybrid đến firewall vẫn còn điều kiện chưa đạt. [Kết quả máy đọc](../security-web/deploy/local-r38/evidence/acceptance.json) · [Ledger 30 request](../security-web/deploy/local-r38/evidence/requests.json)

| Gate | Trạng thái | Bằng chứng quyết định |
|---|---|---|
| LOCAL_ENGINEERING_READY | **BLOCKED** | Luồng HTTPS, Student, ingest Rust, PostgreSQL và Hybrid đã chạy trong acceptance cô lập. Trên host hiện tại chỉ có user services. Bộ system unit, account, TLS và restore DB của chính deployment đích chưa qua cutover có rollback. |
| AI_RUNTIME_READY | **PASS** | R37 29 request, R36 rollback 1 request, quay lại R37. Vector và Python/Rust ONNX khớp 30/30, SHA sai bị từ chối, ABSTAIN và phục hồi đạt. |
| HYBRID_ENFORCEMENT_READY | **BLOCKED** | 30 quyết định thật đều LOG_ONLY. Actuator nftables đã chặn gói thật và hoàn nguyên trong hai netns. Code C2 hiện đóng quyền thực thi và chưa có chuỗi bằng chứng từ một quyết định Hybrid đến kernel block. |
| AWS_STAGING_PREPARED | **BLOCKED** | Đã có release chuyển giao, topology tham số, cấu hình mạng qua cfn-lint và runbook rollback. Còn thiếu AMI có telemetry hardware phù hợp guardian, inventory TLS và restore DB staging đã kiểm. |
| T07_PRODUCTION_QUALITY | **BLOCKED** | Chưa có cohort native HTTPS hai lớp độc lập, benign exposure và CAL/TEST đủ điều kiện. 30 request engineering đóng góp 0 TRAIN. |

## Luồng đã chạy

Client kiểm tra TLS tới NGINX edge. Edge cấp request ID, gửi bản chiếu method/target qua Unix socket và ký proof trên leg HTTP đã giải mã. Suricata bắt leg này bằng AF_PACKET. Egress xác minh HMAC, tiếp tục qua TLS có xác thực tới proxy Student rồi đến Spring Security và H2 riêng. Student Audit phát event ID. Rust ingest file qua cursor vào PostgreSQL và Hybrid lưu quyết định. Bản ghi scoring chỉ lưu dữ liệu đã lọc. HMAC verifier Rust đối soát các transaction theo generation, flow và tx theo batch. Thời điểm verifier hoàn tất mới xác lập availability của nguồn S trong phép đo. Runtime ingest Lua bảo toàn trạng thái IP sau proxy chưa được xác minh. [Acceptance runner](../ai-training/contracts/https-model-r36/accept.py) · [Verifier](../security-web/src/transaction_proof.rs) · [Hybrid trong PostgreSQL](../security-web/deploy/local-r38/evidence/hybrid.json)

17 GET, 3 POST và 10 HEAD tạo 30 trusted ID và 30 Audit ID riêng. Các kết quả HTTP gồm 6 lần 200, 3 lần 204, 20 lần 401 và 1 lần 403. Cả 30 khớp outcome dự kiến. Login có rotation của session, sau đó ứng dụng trả principal ADMIN trên request đã xác thực. Logout thu hồi session và request dùng cookie cũ nhận 401. Kiểm thử dùng credential ngẫu nhiên trong lab. [Workflow](../ai-training/contracts/https-shadow-r35/extended_https.py)

| Trường hợp | Trusted ID | HTTP | Mask tại cutoff |
|---|---|---:|---|
| Login và session rotation | `f65a1e4f8d6be62bee72047281c81d9a` | 204 | NA |
| Đọc principal sau login | `9543e575f2ad8dd016d892332ff6f6a4` | 200 | NA |
| HEAD bị role guard từ chối | `cac5896b80dbae40b51c15448ade8b4c` | 403 | NA |
| Gửi khi sensor tắt | `55934bba18604e59172490564d0e950f` | 401 | NA |
| Burst trên generation mới, tx 7 | `1891040c9013ed9b31a2fde55c90bb0f` | 401 | NSA |

## Mất telemetry sau restart

Chỉ kiểm `Engine started` cho phép burst sử dụng lại kết nối keep-alive đã được thiết lập trước khi sensor mới bắt gói. Lượt liền trước bản sửa ghi 25 EVE, 24 transaction hợp lệ và 0 NSA tại cutoff. Bản sửa giới hạn idle pool trên leg giải mã ở 2 giây. Trong luồng restart có điều phối, helper đọc đúng tuple và inode qua kernel, đợi hữu hạn cho các kết nối cũ rời trạng thái ESTABLISHED trước khi phát lượt tiếp theo. Client vẫn dùng keep-alive. [Lượt trước](../security-web/deploy/local-r38/evidence/before-sensor-drain.json) · [Readback](../security-web/scripts/proof-flow-readiness.py)

Ở lượt cuối, sensor báo engine ready sau 279,412 ms. Một kết nối cũ còn sống, hết sau 1.732,953 ms chờ. Recovery đo đến lúc cho phát lại traffic là 2.016,749 ms. Kết quả có 29 EVE trong cửa sổ, 29 transaction HMAC hợp lệ trên hai generation và 1 partial do cố ý tắt sensor. Với từng request, 16/30 có NSA đúng hạn (53,3%), 14/30 có NA (46,7%). Trong số 14 NA, 13 có proof S đến muộn và 1 không có sensor. Cả 30 có score request-time đúng hạn. Con số này mô tả một lượt restart có điều phối và tải hữu hạn. Việc mất sensor giữa luồng traffic liên tục vẫn phải giữ partial mask đến khi có proof. [Timing từng nguồn và thống kê](../security-web/deploy/local-r38/evidence/metrics.json)

## AI, Hybrid và firewall

Mặc định `r37-hgb-uri100-v1` giữ nguyên ABI URI100, calibration và threshold 0,7664756774902344. SHA-256 ONNX là `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`. Rollback ExtraTrees có SHA `d4797584ab7eb243725329f08acf160122bf1da27a9fb128850f333fd0ce4bd0`. Trên 11 vector khác nhau của 30 request, sai số score Rust/Python ONNX lớn nhất bằng 0. Sai số lớn nhất với estimator R37 là 4,96 × 10⁻⁸ sau khi làm tròn lên. Frame lỗi cho ABSTAIN rồi scorer phục hồi. Sửa pipe IPC để một deadline 900 ms bao phủ cả ghi, đợi phản hồi và đợi hết frame, kể cả khi worker chỉ trả một byte. [Parity](../security-web/deploy/local-r38/evidence/parity.json) · [Slot registry](../ai-training/contracts/quality-freeze-r37/slots.json)

Rust lưu 30 LOG_ONLY, 0 proposal và 0 lỗi ingest HTTPS. Các kịch bản C2/C3 kiểm phân quyền, protected IP, expiry và trạng thái restore/pending unblock trên DB dùng một lần. Ở phép thử kernel riêng, client có kết nối TCP trước ban. Actuator được kiểm soát thêm đúng một phần tử vào nft set, kết nối bị chặn và counter tăng 1 gói. Ban trùng không nhân phần tử, IP của server được bảo vệ, unban hai lần an toàn, hết TTL tự mở lại kết nối. Bảng thử nghiệm và peer đã được dọn. C2 `execution_enabled()` vẫn trả false. R37 không có quyền ban. [Firewall thật](../security-web/deploy/local-r38/evidence/firewall.json) · [Regression Rust](../security-web/deploy/local-r38/evidence/regression.json) · [Cổng thực thi](../security-web/src/prevention.rs)

## Hiệu năng và phục hồi dữ liệu

Percentile theo nearest rank trên 30 giao dịch, bao gồm các lần đổi slot và restart. Burst riêng có 4 client đồng thời, mỗi client dùng lại một kết nối TLS cho 4 request, đạt 26,40 request/s. Không có lỗi HTTP ngoài dự kiến.

| Đo thực tế | p50 | p95 | p99 |
|---|---:|---:|---:|
| HTTPS end-to-end | 100,649 ms | 976,500 ms | 1.003,435 ms |
| Edge dispatch đến score available | 130,515 ms | 233,520 ms | 367,069 ms |
| Rust preprocessing | 0,693 ms | 66,495 ms | 189,578 ms |
| Rust inference | 0,256 ms | 0,521 ms | 0,749 ms |

Benchmark riêng 50 lần lặp warm trên một frame có inference p50/p95 0,038/0,048 ms và cold model load 25,47 ms. Unit end-to-end giới hạn 1 CPU, 2 GiB RAM, swap 0, chạy 42,366 giây, dùng 37,937 CPU-giây và đạt peak 469,1 MiB. Guardian đọc lại `50000 100000` khi nhiệt lên 94°C và `100000 100000` khi hạ nhiệt. Cleanup xác nhận thành công. [Resource](../security-web/deploy/local-r38/evidence/guard.txt) · [Cleanup](../security-web/deploy/local-r38/evidence/cleanup.json)

PostgreSQL dùng Unix socket riêng. 19 migration, 30 observation, 30 Hybrid incident, 29 Lua row và 5 cursor giữ nguyên số lượng cùng checksum nội dung sau restart và restore sang DB khác. Dump 114.658 byte mất 91,76 ms, restart PostgreSQL 224,10 ms, restore 209,58 ms. Sau khi khởi động lại, backend trả HTTP 200 cùng JSON health trên socket TCP thuộc đúng PID. Backend và DB thoát 0, scratch được dọn. [Database](../security-web/deploy/local-r38/evidence/database.json)

## Triển khai thực tế và bảo mật

Host đang chạy `idps-r38-https-scorer.service` ở user manager, enabled, linger=yes. Ở lần kiểm cuối, worker crash trong cgroup sở hữu làm guardian PID 18045 được thay bằng PID 21040. Probe có inference thật trả 200 và đúng SHA sau 2.630,34 ms. Worker cũ đã thoát hết, số receipt staging giữ ở 0. Giới hạn kernel của scorer riêng là quota 1 CPU, memory.high 384 MiB, memory.max 512 MiB, swap 0 và 48 tasks. Bốn unit R22 RI/scorer/receiver/collector đều active, restart count 0 tại thời điểm kiểm. Host system manager báo các unit NGINX, Suricata, PostgreSQL, Security Web và system scorer chưa được cài. [Readback và PID](../security-web/deploy/local-r38/evidence/services.json) · [Crash recovery](../security-web/deploy/local-r38/evidence/user-service-final.json)

Sửa profile host để cấp ACL cho UID NGINX trên socket, giữ khóa HMAC ngoài group của AI. Kiểm thử với ba UID tách biệt đã xác nhận edge có health 200 và không đọc DB/journal. Reader đọc được journal, không ghi và không gọi scorer. Scorer không đọc được file kiểm quyền có cùng owner/mode như khóa edge. SQLite private mode 0700 cho thư mục, journal chia sẻ read-only. Manifest bắt buộc khớp model đã pin khi bật mirror. Profile user dùng socket 0600 riêng. Các secret TLS, CSRF, cookie, mật khẩu, HMAC và raw body không có trong ledger bàn giao. [Kiểm UID thật](../security-web/deploy/local-r38/evidence/uid-acl.json) · [Runbook Local](../security-web/deploy/local-r38/DEPLOY.md)

Archive scorer x86-64 gồm 23 file, 20.128.095 byte, SHA-256 `323da363861f160102c21a55804df90178bf5aceb63581a1f05c997088f75a53`. Host giữ archive tại `~/.local/share/websentinel/archives/r38-https-v2.tar.gz`. Manifest triển khai có SHA `8713fc007e7425a37ef5f106303a659a510231e586e819ca0f9a38b06527b1f6`. Package khởi động độc lập với checkout và fixture tạm. [SHA từng file](../security-web/deploy/local-r38/evidence/release-files.json) · [Archive](../security-web/deploy/local-r38/evidence/archive.json)

## AWS, Git và bước tiếp theo

Renderer nhận địa chỉ edge, upstream và tên trong chứng thư từ inventory. Cấu hình SG cho topology private qua `cfn-lint 1.38.1`. Hai unit systemd qua verify, sysusers qua dry-run trên root trống. Regression gồm 10 test Python receiver/native/journal, 15 test deploy/rollback, 4 test renderer, 2 test đọc socket cũ và 11 test Rust theo filter. Profile AWS mô tả TLS, IAM/Secrets Manager, PostgreSQL, tách quyền, monitoring, sizing, backup, restore và rollback. Cần kiểm khả năng lấy telemetry CPU trên đúng AMI để guardian hoạt động. [AWS handoff](../security-web/deploy/local-r38/aws/README.md) · [CloudFormation](../security-web/deploy/local-r38/aws/network.yaml) · [Kết quả kiểm tra](../security-web/deploy/local-r38/evidence/acceptance.json)

R38 thực hiện trên nhánh `feature/ai-idps-https-ml-integration`, từ `5800680`. Hai commit kỹ thuật là `e014fe6` và `093312f`. Bộ SHA bao phủ mã đã đổi, registry model, artifact và evidence. Tracked diff ở checkout gốc giữ SHA `1f145523851a18310fafc73273e8c8fc7a1f18569bec65cad1771c94260c708f`. [SHA256SUMS](../security-web/deploy/local-r38/SHA256SUMS)

**Bước tiếp theo** là rehearsal trên một host Local staging có quyền cài system units, bộ chứng thư và snapshot PostgreSQL riêng. Chạy UID isolation, restart, canary có request ID qua các service chính thức và restore/rollback trên chính host đó. Giữ chế độ quan sát của R37 trong suốt rehearsal. Nghiệm thu trực tiếp hành động Hybrid xuống kernel cần một đường thực thi đã được phê duyệt riêng.
