# R40 — Hoàn thiện ứng viên Beta và kiểm tra điều kiện phát hành

**Ứng viên Local Monitoring `0.1.0-beta.1` đã đóng gói lại và kiểm thử các thành phần sửa đổi. GitHub Release vẫn BLOCKED.** Resource Contract đã chấp nhận cảm biến trên host vật lý hiện tại. Phiên chạy thiếu quyền quản trị hệ thống để cài và nghiệm thu profile systemd trên một host vật lý phù hợp. Guest KVM từ chối preflight vì thiếu mapping package/core. [Evidence máy đọc](../security-web/deploy/local-r40/evidence/acceptance.json)

| Gate | Kết quả | Bằng chứng |
|---|---|---|
| `LOCAL_BETA_READY` | **BLOCKED** | Còn thiếu nghiệm thu cài đặt đầy đủ trên một host vật lý tương thích. |
| `AI_RUNTIME_READY` | **PASS** | Kế thừa test runtime và rollback R39. SHA của mọi file trong cây scorer của gói R40 khớp bản đã kiểm. |
| `GITHUB_RELEASE_INSTALLABLE` | **BLOCKED** | Chưa có HTTPS → R37 → Hybrid gắn cùng request trên máy cài sạch từ archive R40. |
| `GITHUB_RELEASE_PUBLISHED` | **BLOCKED** | Chưa đạt gate cài đặt. Phiên chưa có xác thực GitHub Release API quyền ghi. |
| `HYBRID_ENFORCEMENT_READY` | **BLOCKED** | C2 execution đóng. Bằng chứng firewall cô lập R38 áp dụng trong phạm vi thử nghiệm đó. |
| `T07_PRODUCTION_QUALITY` | **BLOCKED** | Còn thiếu native HTTPS evaluation hai lớp độc lập. |

## Phần cứng và nghiệm thu

Installer có lệnh `hardware-check` chạy bằng user thường từ chính archive. Preflight gọi cùng `hardware_snapshot`, `SensorReader` và `admission` mà delegated guardian dùng, trước khi tạo tài khoản, unit, DB hay cấu hình. Backend hiện allowlist chính xác **Intel Core Ultra 9 285H**, yêu cầu mapping package/core từ `coretemp` và giữ đọc hardware critical/alarm. Host vật lý đã trả ACCEPT với 17 sensor. `sudo -n -l` yêu cầu xác thực tương tác. KVM thiếu mapping và trả lỗi trước mọi thao tác cài đặt. [Preflight vật lý](../security-web/deploy/local-r40/evidence/physical-preflight.txt) · [Kernel coretemp](https://docs.kernel.org/hwmon/coretemp.html)

Archive cuối được tải vào guest KVM qua kênh quản trị loopback và xác minh SHA trước thử nghiệm. Dùng riêng transient system unit để kiểm Student Web từ JAR ứng dụng và 82 JAR đã pin, trên DB PostgreSQL mới. App trả CSRF HTTP 200 và Flyway chạy đủ 2 migrations. Trình render lấy YAML nền của gói Ubuntu. Một lượt kiểm phát hiện YAML đó mặc định tìm `suricata.rules`. R40 pin lại `pbl4.rules` như R39 và kiểm `suricata -T` thành công từ archive cuối. Thử nghiệm này bao phủ các thay đổi trong gói. HTTPS, Backup/Restore và rollback của R39 giữ phạm vi R39. [Log cài thử](../security-web/deploy/local-r40/evidence/guest-components.txt)

Không có kết quả HTTPS → R37 → Hybrid cùng request cho ứng viên R40. Giữ số đo R38 là 16/30 NSA ở cutoff 1.000 ms và guard 1 ms. Các proof đến muộn giữ nguyên thời điểm sẵn sàng. Gói vẫn đặt auto block OFF. R37 có SHA ONNX `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`. Recall 86,04% và FPR 0,41% đo trên WAF development. Transfer sang Notes và SR-BH còn hạn chế. [R37](121_T09_R37_FINAL_AI_QUALITY_AND_MODEL_FREEZE.md) · [R38](122_T09_R38_FINAL_LOCAL_ACCEPTANCE_AND_AWS_READINESS.md) · [R39](123_T09_R39_LOCAL_RELEASE_FOR_USERS.md)

## Package và phân phối

Ứng viên `idps-local-monitoring-0.1.0-beta.1-linux-amd64.tar.gz` có **29.711.577 byte**, SHA-256 `cc2f927e53a1c7d3a49d342f9f2a00796f4078b8243259c682e199d3174c3d31`. Archive nằm trong `ai-training/.artifacts/r40/candidate/`. Hướng dẫn cài và release notes nằm trong archive. [SHA-256](../security-web/deploy/local-r40/evidence/ARCHIVE_SHA256SUMS) · [Hướng dẫn cài](../security-web/deploy/local-r39/INSTALL.md) · [Release notes](../security-web/deploy/local-r39/RELEASE_NOTES.md)

- Gói mang notice của **12 bản ghi npm** gồm Vite runtime helper, **185 Rust crates** từ hai cây dependency đã khóa, cùng LICENSE và ThirdPartyNotices của ONNX Runtime. Inventory trong archive có tên, phiên bản, nguồn và đường dẫn từng notice.
- Student JAR chỉ chứa app classes và resources. Đã tải đủ **82 JAR** từ Maven Central và đối chiếu SHA với đúng bytes trong bản Student R39. Classpath giữ thứ tự gốc. Spring Boot jarmode của trình đóng gói được bỏ khỏi runtime.
- Ảnh trường, logo chưa xác minh quyền và tài nguyên frontend dư đã được loại bỏ khỏi release. Hai frontend dùng ký hiệu Beta cục bộ. Suricata lấy cấu hình nền khi cài từ gói distro. Kiểm filename và dấu hiệu private key/token trên file văn bản không phát hiện dữ liệu bị cấm. [License và kiểm tra archive](../security-web/deploy/local-r40/evidence/license-audit.json)

15 test deploy/rollback và 2 test flow readiness đạt. Student probe đã dừng. Guest đã poweroff, QEMU exit 0 và guardian xác nhận cleanup. Worktree gốc giữ SHA tracked diff của R39. [Regression](../security-web/deploy/local-r40/evidence/regression.txt) · [Cleanup](../security-web/deploy/local-r40/evidence/cleanup.txt)

## GitHub và điều kiện còn thiếu

GitHub public API còn một prerelease nghiên cứu cũ. Remote chưa có tag `v0.1.0-beta.1`. SSH Git hoạt động, còn GitHub CLI, token trong phiên và Git credential helper hợp lệ cho API chưa có. Tag, release URL, upload receipts và download verification hiện để trống. Quyền tối thiểu cho bước phát hành là GitHub authentication có **Contents: write** trên đúng repository. [GitHub Releases](https://github.com/vuong-quoc-trung/idps-web-aws/releases) · [Quyền tạo Release](https://docs.github.com/en/rest/releases/releases#create-a-release)

Điều kiện kỹ thuật còn thiếu là một máy staging Ubuntu 26.04 amd64 sạch có CPU và telemetry được preflight chấp nhận, cùng quyền quản trị để chạy đúng archive R40. Trên máy đó cần xác nhận system scorer, cùng request ID qua HTTPS và Hybrid, rồi kiểm restart, chuyển hai slot, backup/restore và uninstall. Chỉ khi gate này đạt mới thực hiện tag, publish và tải lại để đối chiếu SHA.
