# R39 — Gói Beta Local Monitoring và kết quả cài trên Ubuntu sạch

**Ứng viên 0.1.0-beta.1 đã build và đã thử từ chính archive trên Ubuntu KVM mới. Chưa phát hành GitHub.** Unit scorer trong guest tự từ chối bằng exit 78 với predicate `No verified package/core sensor mapping`. Cùng archive chạy được R37 và nạp được R36 trên host vật lý dưới user systemd. Hai phép thử có phạm vi khác nhau. [Gates và evidence](../security-web/deploy/local-r39/evidence/acceptance.json)

| Gate | Trạng thái | Bằng chứng |
|---|---|---|
| `LOCAL_BETA_READY` | **BLOCKED** | HTTPS, Student, Security Web, PostgreSQL, sensor và Hybrid chạy trên guest. Scorer system service thiếu cảm biến CPU đã xác minh. |
| `AI_RUNTIME_READY` | **PASS** | Scorer trong archive nạp R37, health 200, projection ghi `SCORED`. Một unit riêng nạp đúng SHA R36. Phép thử này dùng host vật lý và socket nội bộ. |
| `HYBRID_ENFORCEMENT_READY` | **BLOCKED** | Guest quan sát `LOG_ONLY`, `automatic_block=false`. R38 đã chứng minh tác động, TTL và unban trên kernel trong netns riêng. Quyền C2 vẫn đóng. |
| `GITHUB_RELEASE_INSTALLABLE` | **BLOCKED** | Archive xác minh được và triển khai các dịch vụ còn lại trên guest. Chưa có lần cài đủ scorer bằng system unit trên máy sạch có sensor tương thích. |
| `GITHUB_RELEASE_PUBLISHED` | **BLOCKED** | Chưa đủ nghiệm thu, quyền ghi GitHub Release API chưa có, rà soát notice cho dependency đóng gói còn pending. |
| `T07_PRODUCTION_QUALITY` | **BLOCKED** | Chưa có native HTTPS TEST hai lớp và độc lập đủ tiêu chuẩn. |

## Ứng viên và hướng dẫn

- `idps-local-monitoring-0.1.0-beta.1-linux-amd64.tar.gz`, **84.327.963 byte**, SHA-256 `b610bfc41ffc206e845ac752a454586dd77c217354c8de262309f25fc63da64f`. Archive và `SHA256SUMS` nằm trong `ai-training/.artifacts/r39/build/out-3/`. Git lưu công cụ đóng gói, mã installer và SHA. [Manifest archive](../security-web/deploy/local-r39/evidence/ARCHIVE_SHA256SUMS)
- Cả Student JAR, hai frontend và Rust Security Web được build từ snapshot Git `3cda364e`. Gói có scorer Rust, ONNX Runtime 1.31.1 với license và notice, model R37 và R36, renderer NGINX/Suricata, các Python helper và lifecycle systemd. Migration đi cùng app binaries. Hạ tầng Ubuntu, Java và PostgreSQL cài qua distro. [Packager](../security-web/deploy/local-r39/package.py) · [Installer và vận hành](../security-web/deploy/local-r39/INSTALL.md)
- Đích dự kiến là **Ubuntu 26.04 amd64, cgroup v2, systemd và CPU có telemetry tương thích Resource Contract**. Hai ứng dụng đặt trên loopback, có TLS được xác thực. Installer nhận chứng thư của người vận hành, tạo mật khẩu DB riêng bằng RNG và tách service accounts. C2 ở chế độ đóng và helper firewall chỉ được bàn giao trong phạm vi sử dụng đã phê duyệt.
- Build dùng allowlist. Archive có 73 file. Kiểm tra tệp loại trừ private key, checkpoint, dataset, telemetry thô và DB dumps. Quét dấu private key/token trong file text cùng cấu hình của Student JAR đạt. Cần hoàn tất notice của frontend, JAR và Rust dependencies trước khi phân phối công khai. [Kiểm archive](../security-web/deploy/local-r39/evidence/archive-audit.json)

## Cài đặt và vận hành trên KVM

Dùng Ubuntu cloud image ký bởi Canonical, SHA image verified bằng distro keyring. Guest boot bằng QEMU/KVM và systemd thật, kết nối quản trị chỉ bind loopback trên host. Apt giải được NGINX/njs, Suricata, PostgreSQL 18, ACL và Java 25. Trong hai lần thử đầu, installer thiếu `/etc/sysusers.d` trên image sạch và quyền giải nén với umask 077 khiến unprivileged services không đọc được executable. Bản cuối tự tạo thư mục sysusers và đặt lại mode file/thư mục theo vai trò trước khi start. Từng lần thử dùng staging riêng trong guest và các DB tên chính thức được tạo mới. [Image Ubuntu](https://cloud-images.ubuntu.com/releases/resolute/release/) · [Phiên bản packages](../security-web/deploy/local-r39/evidence/guest-dependencies.txt) · [Log cài và trạng thái unit](../security-web/deploy/local-r39/evidence/guest-install.txt)

- HTTPS Student và dashboard đều trả 200. GET CSRF thật trả 200 và nội dung hợp lệ. Trusted request ID `249eb149a57af0ec4a82ae53f92f3bc4` có đúng một record NGINX, một Audit và một transaction Suricata ghép đúng generation/flow/tx. Hybrid ghi `LOG_ONLY`, research score chưa có vì scorer chưa start. Đây là bằng chứng cấu trúc sau quan sát. Không có số đo native NSA tại cutoff trong lượt guest R39. [HTTPS, correlation và Hybrid](../security-web/deploy/local-r39/evidence/https-postgresql.txt)
- Student Flyway chạy **2 migration**, Security SQLx chạy **19 migration**. Backup cả hai PostgreSQL DB và restore vào hai DB mới đạt. Bảng migration giữ count và checksum. Edge restart xong trả HTTPS 200. Sensor restart cùng helper readback hoạt động với 0 kết nối cũ trong ca kiểm này. Upgrade từ DB cũ chưa nghiệm thu. [Đối chiếu restore](../security-web/deploy/local-r39/evidence/restore-checksums.txt)
- Guardian bao QEMU tối đa 3 CPU và 5 GiB. Kernel hạ xuống 1,5 CPU khi host đo 94–95°C. Peak RAM 4,2 GiB, swap 0. Guest đã gỡ 5 units, dọn listeners/socket, giữ backup và guard deny-only đến lúc poweroff. QEMU exit 0 và guardian xác nhận cleanup. [Cleanup](../security-web/deploy/local-r39/evidence/cleanup.txt) · [Tài nguyên](../security-web/deploy/local-r39/evidence/guest-resource.txt)

## R37 và nguyên nhân coverage R38

R37 giữ SHA-256 ONNX `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`, ABI URI100 và ngưỡng `0,7664756774902344`. Trên host vật lý, một projection fixture qua Unix socket của archive ghi score `0,1253570318222046`, sẵn sàng sau dispatch 3,261 ms. R36 trả health SHA `d4797584ab7eb243725329f08acf160122bf1da27a9fb128850f333fd0ce4bd0`. Cả hai thử nghiệm user systemd dùng đúng archive. [R37 smoke](../security-web/deploy/local-r39/evidence/host-archive-smoke.json) · [R36 rollback](../security-web/deploy/local-r39/evidence/rollback-sha.txt)

R38 có 29/30 EVE đúng hạn, nhưng thời điểm EVE nhận được khác thời điểm verifier HMAC hoàn tất. Có **13 proof S đến muộn** và **1 request gửi khi sensor tắt**, nên còn 16/30 NSA tại 1.000 ms và guard 1 ms. R39 giữ generation ID và helper drain cho planned restart. Snapshot EVE, Lua ingest theo cursor và HMAC proof tuyệt đối vẫn có thời điểm khác nhau. Cần verifier theo từng transaction có dedup và revocation đã kiểm chứng để tăng coverage sớm. R39 chưa nối verifier batch vào luồng quyết định. [Timing R38](../security-web/deploy/local-r38/evidence/metrics.json)

Ngưỡng R37 đo **86,04% recall** và **0,41% FPR** trên WAF development benchmark. Transfer sang Notes và SR-BH còn hạn chế. Số đo phụ thuộc dữ liệu WAF publisher. Chưa có native HTTPS TEST độc lập đạt T07. R37 chỉ quan sát và cảnh báo theo chính sách hiện hành. [Báo cáo R37](121_T09_R37_FINAL_AI_QUALITY_AND_MODEL_FREEZE.md)

## Git và phần còn lại

Nhánh `feature/ai-idps-https-ml-integration` tiếp tục từ R38 `3cda364e`. GitHub có prerelease nghiên cứu `ai-research-team-20261105`. Chưa tạo tag `v0.1.0-beta.1`, release URL hoặc upload asset. SSH Git dùng được. Phiên hiện tại thiếu token ghi Release API. Worktree gốc giữ tracked-diff SHA `1f145523851a18310fafc73273e8c8fc7a1f18569bec65cad1771c94260c708f`. Regression 15 test deploy/rollback và 2 test flow readiness đạt. [Log regression](../security-web/deploy/local-r39/evidence/proof-regression.txt) · [Release đã tồn tại](https://github.com/vuong-quoc-trung/idps-web-aws/releases/tag/ai-research-team-20261105)

Để chốt beta, cần chạy đúng archive trên host Ubuntu sạch có quyền quản trị và sensor package/core thật, xác nhận ít nhất một request HTTPS có kết quả R37 gắn với Hybrid, rồi chạy restart và rollback dưới system units. Hoàn tất notice phân phối và cấp quyền Release API trước khi upload. AWS tiếp tục chờ nghiệm thu Local và xác minh guardian trên hạ tầng đích.
