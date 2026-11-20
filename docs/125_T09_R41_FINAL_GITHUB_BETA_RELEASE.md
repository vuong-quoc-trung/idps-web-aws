# R41 — Nghiệm thu Beta và trạng thái GitHub Release

**GitHub và sudo đã xác thực. Ứng viên Beta chưa phát hành vì chưa có kết quả nghiệm thu end-to-end trong cùng deployment.** API GitHub xác nhận tài khoản có quyền push và admin trên repository vuong-quoc-trung/idps-web-aws. Host vật lý đã qua hardware preflight với Intel Core Ultra 9 285H và 17 sensor coretemp. [Evidence máy đọc](../security-web/deploy/local-r41/evidence/acceptance.json) · [Preflight vật lý](../security-web/deploy/local-r41/evidence/physical-preflight.txt)

| Gate | Kết quả |
|---|---|
| LOCAL_BETA_READY | **BLOCKED**. Còn thiếu log nghiệm thu system deployment. |
| AI_RUNTIME_READY | **PASS** trong phạm vi runtime R39 được R40 đối chiếu byte. |
| GITHUB_RELEASE_INSTALLABLE | **BLOCKED**. Chưa xác minh HTTPS → R37 → Hybrid gắn cùng request trong một bản cài. |
| GITHUB_RELEASE_PUBLISHED | **BLOCKED**. Thiếu nghiệm thu cài đặt. |
| HYBRID_ENFORCEMENT_READY | **BLOCKED**. C2 execution đóng. |
| T07_PRODUCTION_QUALITY | **BLOCKED**. Thiếu native HTTPS evaluation hai lớp độc lập. |

## Nghiệm thu staging

Dùng Ubuntu Base 26.04.1 amd64 đã kiểm chữ ký Canonical, cài dependency từ cache APT vào rootfs riêng. Nspawn dùng network namespace riêng và workload ở dưới transient systemd unit quản lý nhiệt. Đã sửa ba lỗi bootstrap gồm APT xử lý đường dẫn offline, rootfs mode 0700 chặn tài khoản dịch vụ, và bind mount timezone khiến postinst tzdata không cập nhật được /etc/localtime. Lượt sau cấu hình dependency thành công và launcher boot/poweroff thoát 0. Log systemd bên trong chưa được chuyển ra terminal ở lượt đó. Đã cấu hình lưu log trong rootfs để lần chạy lại xuất được bằng chứng trực tiếp. [Log staging](../security-web/deploy/local-r41/evidence/staging.txt)

Cài đặt, system units, HTTPS → R37 → Hybrid, restart, rollback, PostgreSQL backup/restore và uninstall của R41 vẫn cần xác minh. Resource guardian ghi cleanup thành công cho lượt staging đã kết thúc. Rootfs nằm trong thư mục scratch riêng cho lượt xác minh log.

## Package và GitHub

Archive idps-local-monitoring-0.1.0-beta.1-linux-amd64.tar.gz giữ nguyên SHA-256 cc2f927e53a1c7d3a49d342f9f2a00796f4078b8243259c682e199d3174c3d31. Bộ upload cục bộ gồm archive, SHA256SUMS, INSTALL.md và RELEASE_NOTES.md. Đã đối chiếu checksum tại chỗ. License notice, loại trừ dữ liệu nhạy cảm và 82 Maven JAR pin SHA kế thừa R40. Supported profile vẫn là Ubuntu 26.04 amd64 trên CPU đã được Resource Contract phê duyệt. [Manifest assets](../security-web/deploy/local-r41/evidence/ASSET_SHA256SUMS) · [R40](124_T09_R40_FINAL_BETA_RELEASE_PUBLICATION.md)

GitHub CLI được giải nén cục bộ từ gói Ubuntu và đã hoàn tất device flow. Tag v0.1.0-beta.1, release URL, upload receipt và download verification vẫn chưa có vì gate cài đặt còn mở. R37 giữ ONNX SHA 91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff và R36 làm rollback. Recall 86,04% và FPR 0,41% thuộc WAF development. Beta ở chế độ Research Monitoring với AI automatic ban tắt. [GitHub Releases](https://github.com/vuong-quoc-trung/idps-web-aws/releases)

Để tiếp tục, xác thực sudo trong cửa sổ staging R41. Nếu cửa sổ đã hết thời hạn chờ, mở lại runner cục bộ bằng lệnh bên dưới. Runner dùng lại archive và dependencies đã chuẩn bị và ghi log systemd trực tiếp từ staging.

```sh
bash /home/trung/projects/idps-r35/ai-training/.artifacts/r41/staging-console-resume.sh
```
