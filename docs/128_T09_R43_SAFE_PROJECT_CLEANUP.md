# R43 — Dọn dẹp an toàn sau R42

Dọn trên `/home/trung/projects/idps-r35`, nhánh `feature/ai-idps-https-ml-integration`, từ HEAD `7a5129f`. Dung lượng theo block đã cấp phát trong checkout tại thời điểm cleanup, trước khi tính tài liệu R43 mới.

| Hạng mục | Kết quả |
|---|---:|
| Trước cleanup | 14.027.743.232 byte |
| Sau cleanup | 5.055.008.768 byte |
| Tiết kiệm | **8.972.734.464 byte (8,97 GB)** |
| File xóa | 14.450 |
| File archive | 24.008, cùng 26 symlink được bảo toàn |

## Phân loại và phục hồi

| Phân loại | Xử lý |
|---|---|
| DELETE_SAFE | Cargo build cache, cache Python/Ruff/pytest, các cây giải nén package trùng SHA và bản sao tải về hoặc dependency trùng byte. Dry run kiểm Git ignore, ownership, mount và tiến trình trước khi xóa. |
| ARCHIVE | 12 log bootstrap R41, hai cây dependency frontend R39 và môi trường lint AWS R38. Đã đọc lại SHA của từng file trong archive trước khi xóa bản rời. |
| KEEP | R37, R36, ONNX Runtime, installer, rollback, reports, evidence, lineage, datasets và checkpoint độc nhất. Các báo cáo nghiên cứu giữ đường dẫn hiện dùng trong contracts. Có chỉ mục mới để tìm tài liệu và source. |
| REVIEW_REQUIRED | Giữ nguyên chuỗi đĩa QEMU do overlay tham chiếu backing path tuyệt đối. Bỏ qua chín scratch root-owned ngoài checkout và metadata Git dùng chung. |

Hai archive local mode 0600 nằm dưới `ai-training/.artifacts/r43/`. Lấy đúng file và SHA từ manifest, giải nén vào gốc checkout để phục hồi đường dẫn cũ khi cần tái lập R38/R39 hoặc đọc log R41. Archive toolchain giữ cả symlink của Python và npm. Package Beta tải về không phụ thuộc các cache này. [Manifest cleanup](128_T09_R43_CLEANUP_MANIFEST.json) · [Chỉ mục dự án](PROJECT_INDEX.md)

## Kiểm chứng

- Git connectivity PASS. Diff của checkout gốc giữ SHA trước cleanup. R43 chỉ thêm tài liệu, không thay source và deployment.
- Cả hai model và 22 mục của runtime đã cài khớp SHA. Scorer trả HTTP 200 với đúng SHA R37. Năm user service giữ PID, unit staging dùng một lần của R42 đã được gỡ theo nghiệm thu.
- Kiểm kê ba GitHub releases và bốn tags. Beta.1 và Beta.2 giữ release ID, tag và toàn bộ asset digest theo receipt. Research release và tag archive giữ nguyên. [GitHub Releases](https://github.com/vuong-quoc-trung/idps-web-aws/releases)
- [Handoff Local R42](126_T09_R42_FINAL_LOCAL_HANDOFF.md) và [hồ sơ chuyển sang AWS](127_T09_AWS_MIGRATION_HANDOFF.md) đầy đủ. Giữ trạng thái T07 production và Hybrid enforcement theo R42.
