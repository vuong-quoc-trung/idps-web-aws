# R41 — GitHub Beta Research Monitoring

**Smoke cài đặt PASS. Nghiệm thu Local đầy đủ BLOCKED.** Phát hành fast track dùng đúng archive R40 đã xác minh, với giới hạn được công bố trong release notes. T07 production quality và Hybrid enforcement vẫn BLOCKED. AI auto-ban OFF. [Evidence máy đọc](../security-web/deploy/local-r41/evidence/acceptance.json)

Ubuntu Base 26.04.1 amd64 đã kiểm chữ ký Canonical, chạy systemd trong staging có network namespace riêng trên Intel Core Ultra 9 285H với 17 cảm biến. Installer và PostgreSQL đã chạy. TLS, nội dung CSRF và SHA scorer R37 đã xác minh. Guardian readback ghi quota 150% ở 94°C, trở lại 300% ở 84°C và cleanup PASS. [Preflight](../security-web/deploy/local-r41/evidence/physical-preflight.txt) · [Smoke](../security-web/deploy/local-r41/evidence/staging.txt) · [Guardian](../security-web/deploy/local-r41/evidence/guardian-cgroup.txt)

Request CSRF khớp bản ghi NGINX, chain Suricata, Student Audit và journal R37. Score sẵn sàng sau 3,72 ms. Hybrid ghi `LOG_ONLY`, thiếu score R37 và Student Audit do lỗi quyền đọc. HTTP 502 ở lượt trước xảy ra khi backend Java chưa mở cổng. Lượt smoke tiếp theo chờ Java 3,51 giây rồi kiểm tra HTTPS thành công. Correlation ba nguồn có proof tại cutoff và restart, rollback, backup/restore, uninstall trong cùng deployment còn chưa nghiệm thu. Bước sửa tiếp theo là kiểm tra readiness Java trong installer, cấp quyền liệt kê journal cho Rust và cấu hình Audit group-read riêng cho Beta. [Smoke](../security-web/deploy/local-r41/evidence/staging.txt)

Archive 29.711.577 byte có SHA-256 `cc2f927e53a1c7d3a49d342f9f2a00796f4078b8243259c682e199d3174c3d31`. License và dependency audit kế thừa R40 trên cùng bytes. Giữ R37 mặc định và R36 rollback. Recall 86,04% và FPR 0,41% áp dụng cho WAF development. [SHA-256](../security-web/deploy/local-r41/evidence/ASSET_SHA256SUMS) · [Audit R40](124_T09_R40_FINAL_BETA_RELEASE_PUBLICATION.md)

GitHub device login và quyền ghi đã xác minh. Tag và phát hành là bước tiếp theo sau lần commit evidence này.
