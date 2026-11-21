# R42 — Bàn giao Local Beta Monitoring

R42 tiếp tục từ [Beta.1 và evidence R41](125_T09_R41_FINAL_GITHUB_BETA_RELEASE.md). Profile Beta.2 sửa tích hợp file giữa Student, scorer và Rust. Hệ thống vẫn dùng scoring và cảnh báo, với C2 execution đóng và AI auto-ban OFF.

## Kiến trúc và phạm vi

Client xác minh TLS tới NGINX. NGINX sinh trusted request ID, gửi projection qua Unix socket cho scorer và nhận response Student qua proxy có TLS nội bộ. Suricata quan sát leg giải mã đã giới hạn trong kernel. Student xuất audit JSONL đã lọc. Security Web dùng cursor PostgreSQL để ingest, ghi trạng thái evidence và cập nhật Hybrid. Quyết định Hybrid là post-observation. Đo nguồn tại cutoff giữ 1.000 ms và guard 1 ms.

| Systemd unit | Chức năng |
|---|---|
| `websentinel-beta-edge.service` | NGINX, TLS và guard cho leg giải mã |
| `websentinel-beta-sensor.service` | Suricata EVE và transaction journal |
| `websentinel-beta-student.service` | Student API, session, CSRF và Audit |
| `websentinel-https-scorer.service` | Thermal guardian, ONNX và SQLite receipt/outbox |
| `websentinel-beta-security.service` | Rust ingest, cursor, Security Web và Hybrid |
| `postgresql@18-main.service` | Database tách role cho Student và Security |

Mặc định là `r37-hgb-uri100-v1` SHA-256 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`. Slot R36 có SHA-256 `d4797584ab7eb243725329f08acf160122bf1da27a9fb128850f333fd0ce4bd0`. ABI URI100, calibration, threshold và model giữ nguyên từng byte. R37 đạt recall 86,04% và FPR 0,41% trên WAF development. [Registry](../ai-training/contracts/quality-freeze-r37/slots.json) · [R37](121_T09_R37_FINAL_AI_QUALITY_AND_MODEL_FREEZE.md)

## Bản sửa R41

- Installer chờ backend Java nhận kết nối và kiểm truy cập thực tế dưới đúng UID và groups của Rust.
- Student Audit chỉ bật group-read ở Beta. File mới và file sau rotation dùng `0640` trong thư mục setgid do Student sở hữu. ACL socket edge và private SQLite của scorer tách riêng khỏi log reader.
- Rust watcher cần cả quyền liệt kê thư mục và mở journal. Lượt đầu giữ được ACL có tên nhưng probe `test -r` chưa chấp nhận đường dẫn journal. Unit scorer ở lượt đạt cấp quyền qua group riêng; Rust nhận supplementary group. Health kiểm mở file và xác minh quyền ghi bị từ chối. Publish package chỉ dùng archive đã qua acceptance.
- 7 kiểm thử Student Audit đạt, gồm scope group và rotation. Các dependency pin, notices, assets frontend và hai ONNX giữ nguyên SHA so với Beta.1. Bản cài sạch giữ yêu cầu Ubuntu 26.04 amd64, PostgreSQL 18 và Intel Core Ultra 9 285H với mapping `coretemp` hợp lệ.

## Vận hành

Kiểm SHA và hardware admission trước khi cài lên máy riêng. Sau cài dùng `manage.py health`, tra `manage.py request <request_id>` theo ID của response và xem journal của systemd. Khi có 502 kiểm backend Java và Flyway. Khi thiếu Audit hoặc AI, kiểm UID, group, mode và backlog thay vì cấp quyền cho tài khoản ngoài profile. Runbook mô tả TLS, restart, backup/restore, slot rollback và gỡ units. Beta.1 cần sao lưu và rehearsal trên profile sạch trước khi chuyển. [Hướng dẫn cài đặt](../security-web/deploy/local-r39/INSTALL.md)

Giữ bằng chứng firewall R38 trong phạm vi netns thử nghiệm. Các phép đo Beta Monitoring và development không cấp quyền production enforcement. [R38 firewall và recovery](122_T09_R38_FINAL_LOCAL_ACCEPTANCE_AND_AWS_READINESS.md)

## Kết quả nghiệm thu

Staging Ubuntu 26.04.1 amd64 dùng Ubuntu Base đã xác minh chữ ký Canonical, systemd lồng trong namespace mạng riêng và 17 cảm biến coretemp thật. Guardian giữ envelope 3 CPU và 5 GiB RAM, throttle về 1,5 CPU khi vượt 90°C. Lượt chạy mất 3 phút 2 giây và đạt peak RAM 1,5 GiB. Staging exit 0, không còn unit thuộc lượt thử. Uninstall giữ cấu hình và dữ liệu như thiết kế. [Log giới hạn và khôi phục](../security-web/deploy/local-r42/evidence/staging.txt)

- **15/15 request HTTPS** có trusted request ID, Student Audit và incident Hybrid. Rust thấy 14 score khớp journal, gồm 13 R37 và 1 R36. Khi scorer ngừng, incident giữ `LOG_ONLY` và không có score. Tất cả 15 incident thử nghiệm là `LOG_ONLY`. HTTP p50 35,456 ms, p95 429,764 ms theo nearest rank trên mẫu hữu hạn.
- **14 transaction Suricata** được ràng buộc bằng HMAC của request và receipt trên đúng generation, flow và transaction. Collector nghiệm thu ghi 13 NSA và 1 NA tại cutoff. Request lúc tắt scorer thiếu mốc dispatch từ AI, giữ `UNMEASURED`. Mask mô tả availability đã đo tại collector. Hybrid ghi quyết định sau ingest, và runtime Rust lưu Lua/EVE dưới phạm vi shadow thay vì cấp client attribution từ sensor.
- GET/POST, login với session rotation, principal ADMIN, logout và cookie cũ trả 401 đều đạt cùng kết nối TLS. Audit sau rotation, sensor generation mới, scorer phục hồi, restart systemd, restart PostgreSQL và chuyển R37 → R36 → R37 đều đạt. Quyền authorization và lỗi frame ABSTAIN ở R38 kế thừa cho các đường logic giữ nguyên.
- PostgreSQL chạy đủ 2 Flyway và 19 SQLx migration. Restore vào DB mới đối chiếu số hàng lẫn checksum của sáu bảng, gồm audit/ingest, Hybrid, score và cursor. Uninstall gỡ năm unit Beta và socket. [Evidence theo request](../security-web/deploy/local-r42/evidence/requests.json)

| Gate | Kết quả |
|---|---|
| LOCAL_ENGINEERING_READY | PASS trên cấu hình staging hỗ trợ |
| AI_RUNTIME_READY | PASS |
| HTTPS_AI_HYBRID_READY | PASS cho Beta post-observation |
| LOCAL_BETA_READY | PASS trên cấu hình staging hỗ trợ |
| GITHUB_RELEASE_INSTALLABLE | PASS với archive đã nghiệm thu |
| GITHUB_RELEASE_PUBLISHED | PASS |
| HYBRID_ENFORCEMENT_READY | BLOCKED do C2 production đóng |
| AWS_MIGRATION_HANDOFF_READY | PASS cho kế hoạch |
| T07_PRODUCTION_QUALITY | BLOCKED do thiếu independent native HTTPS TEST |

Gói `0.1.0-beta.2` build tại `12b1d3f61a518bada81d784b22648e9f8c344e6c`, SHA-256 `7cd56aab50f744f7ce94e460aa4d86fbae6af1b02a66a95b59fba11fcf7cb061`. Prerelease công khai có archive, INSTALL.md, RELEASE_NOTES.md và SHA256SUMS. Đã tải lại bốn tệp qua URL công khai, đối chiếu byte và chạy verify từ archive đã tải. Annotated tag trỏ đến commit `3f65f68a6e886d01ee43d300aef51b32e9a796d2`. Git diff của checkout gốc giữ SHA `1f145523851a18310fafc73273e8c8fc7a1f18569bec65cad1771c94260c708f`. [GitHub Release](https://github.com/vuong-quoc-trung/idps-web-aws/releases/tag/v0.1.0-beta.2) · [GitHub API receipt](../security-web/deploy/local-r42/evidence/github-release.json) [Checksum](../security-web/deploy/local-r42/evidence/ASSET_SHA256SUMS) · [Acceptance JSON](../security-web/deploy/local-r42/evidence/acceptance.json) · [Bàn giao AWS](127_T09_AWS_MIGRATION_HANDOFF.md)
