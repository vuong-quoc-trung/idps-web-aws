# Học liệu AI-IDPS — cập nhật11/11/2026

Ba HTML tiếng Việt dưới đây có phần trạng thái hiện hành ở đầu. **Requestv2 là
model active duy nhất; AI-IDPS10M hoãn.** Chương/metrics cũ là hồ sơResearchMVP,
không phải chứng nhận live hoặc danh sách model đang chạy. Registryhai dòng,
archivevà kế hoạch1M đã nối vào từng tài liệu.

- [Demo hiện hành và lệnhLAN](../44_AI_IDPS_LOCAL_V1_RC1.md).
- [Model/score/policy](../03_AI_MODEL_AND_TRAINING_PLAN.md).
- [1M uniqueTRAIN tương lai](../37_AI_IDPS_STUDENT_2M_DATA_PIPELINE.md).

Acceptance live đang cần hoàn tất; hai máyPENDING do chưa cómáyB; manualblock
chỉ khioperatorduyệt. Clone nhánh`feature/ai-idps-shadow-integration` và mởHTMLoffline.

---

## Mục lục học liệu lịch sử (mốc06/11/2026)

# Bộ học liệu AI-IDPS (`docs/learning-materials/`)

Bộ **3 sổ tay tương tác tiếng Việt** (tự chứa 100% HTML/CSS/SVG/JS, đọc offline, hỗ trợ **In / lưu PDF**) giải thích toàn diện dự án **AI-IDPS** từ cơ bản đến chuyên sâu, đã được cập nhật đồng bộ với cột mốc **`AI-IDPS Research MVP v1.0 — Frozen Baseline`** (commit `09a12e4`, ngày **06/11/2026**):

1. [**Tài liệu 01 — Nhập môn AI và Mô hình (`AI_IDPS_01_Nhap_mon_AI_va_mo_hinh.html`)**](AI_IDPS_01_Nhap_mon_AI_va_mo_hinh.html)
   - Giải thích toàn bộ phần AI từ cơ bản (vector, nơ-ron, hàm kích hoạt, hàm mất mát BCE/MSE, đạo hàm, AdamW, chuẩn hóa Z-score không rò rỉ) đến nâng cao.
   - Hai mặt phẳng đặc trưng: **207 đặc trưng nhân quả (`ai-features-5`)** cho luồng hợp nhất chính tuyến và **588 đặc trưng (`bounded-request-v1` + `rich_content_v2`)** cho tiền huấn luyện quy mô lớn.
   - Đầy đủ các họ mô hình trong dự án: **MLP (5k) → Deep MLP (50.6k / 252.6k) → Autoencoder (9.6k) → Denoising AE (294.7k) → Residual Detector (14.2k / 17.9k) → Gated Residual (450k) → Tree Ensemble → `residual_glu` SwiGLU ~10 triệu tham số (9,675,784 params)**.
   - Quy trình làm sạch & cách ly **413,596 dòng va chạm nhãn (`collision_quarantine`)** trên kho **2,115,317 request**, kiểm thử ngoài phân phối (**OWASP Juice Shop Oracle**), hiệu chuẩn xác suất (**Temperature Scaling**, `ECE = 0.0029`), xuất **ONNX (`max_abs_diff = 0.0`)** và CLI suy luận **`idps-ai infer-mvp`**.

2. [**Tài liệu 02 — Sơ đồ, Luồng hoạt động và Giải phẫu Rule (`AI_IDPS_02_So_do_va_nguyen_ly_he_thong.html`)**](AI_IDPS_02_So_do_va_nguyen_ly_he_thong.html)
   - Kiến trúc tổng thể và hành trình từng bước của gói tin qua **Nginx (`:8088`) → Spring Boot `web-app` (`:18080`) + Suricata 8.0.3 (`eve.json`) → Rust `security-web` (`:8090`) → AI `idps-ai` → Policy Engine → `pbl4-firewall` → `nftables`**.
   - Giải thích chi tiết **Rule là gì, cấu tạo từng thành phần của Rule và ví dụ payload thực tế** trên cả **3 lớp phòng thủ**:
     - **Lớp 1 — Nginx Edge Map Rules** (`security-web/nginx/pbl4-proxy.conf`): chặn sớm User-Agent máy quét và đường dẫn nhạy cảm (`/.env`, `/.git`, `/actuator`, `../`).
     - **Lớp 2 — Suricata 8.0.3 NIDS Rules** (`security-web/suricata/pbl4.rules`): phân tích đầy đủ **9 SID (`1000001`–`1000009`)**, giải thích `sticky buffers` (`http.uri` vs. `http.uri.raw`), toán tử chiều giao dịch `=>`, `pcre`, `bsize`, và `threshold: type both, track by_src`.
     - **Lớp 3 — Rust Application & Stateful Detector** (`security-web/src/detection.rs` & `ingest.rs`): chuẩn hóa chống né chữ ký (`decode_twice`, `strip_sql_comments`), 5 họ tấn công phi trạng thái, che mật khẩu (`redact_target`) và cửa sổ trượt brute-force `10 lần / 60s`.
   - Cơ chế **Collector Durability** (`byte_offset`, `inode`, `file_generation`, `idempotency`), ghép nối nhân quả 2 bậc (`X-Request-Id` + `flow_id`), 3 chế độ phản ứng (`OFF` / `MANUAL` / `ENFORCE`), **3 chốt chặn an toàn** trước khi khóa IP và tường lửa nhân Linux **`nftables`** (`TTL <= 300s` trên cả `INPUT` và `FORWARD`).

3. [**Tài liệu 03 — Từ điển Thuật ngữ Toàn diện & Mức-Mục tiêu Dự kiến (`AI_IDPS_03_Tu_dien_thuat_ngu_va_muc_tieu.html`)**](AI_IDPS_03_Tu_dien_thuat_ngu_va_muc_tieu.html)
   - Hỗ trợ **thanh tìm kiếm tức thì theo từ khóa** và **bộ lọc tách biệt 2 phần**:
     - **Phần I — Thuật ngữ AI, Học sâu, Dữ liệu & Thước đo (Chương 01–05)**: giải thích từng thuật ngữ kèm bảng tổng hợp và hộp đối chiếu song song **`Mức đạt hiện tại (Frozen Baseline v1.0)`** vs. **`Mục tiêu dự kiến sẽ đạt (Target SLA / Next Phase)`**.
     - **Phần II — Thuật ngữ Hệ thống, Mạng, Rule, Bảo mật, Lưu trữ & Hạ tầng (Chương 06–09)**: giải thích toàn bộ các khái niệm Web/Proxy/Auth/RBAC/IDOR, Suricata/TCP/NIDS/Rule syntax, Collector/Parquet/HMAC/Redaction, Policy Engine/`pbl4-firewall`/`nftables`.
   - Kèm **Bảng tổng hợp từ viết tắt (Acronym Cheat Sheet)** và **8 câu hỏi tự kiểm tra** bao quát cả hai phần.

## Cách mở và sử dụng

Sau khi clone hoặc pull nhánh `feat/ai-model-training`, mở trực tiếp bất kỳ file `.html` nào trong thư mục này bằng trình duyệt web (Chrome, Firefox, Edge, Safari). Khi tải về từ GitHub, hãy giữ cả 3 file `.html` trong **cùng một thư mục** để các liên kết chuyển tiếp giữa 3 sổ tay hoạt động liền mạch.

Mọi biểu đồ SVG, thanh tìm kiếm thuật ngữ, bài tập ẩn/hiện đáp án và chức năng **In / lưu PDF** đều hoạt động 100% offline.

## Đối chiếu tài liệu kỹ thuật gốc trong repo

- Tổng quan & tiến độ dự án: [`docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`](../00_PROJECT_OVERVIEW_AND_PROGRESS.md)
- Audit hệ thống & kiến trúc: [`docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`](../01_SYSTEM_AUDIT_AND_ARCHITECTURE.md)
- Chiến lược dữ liệu & đặc trưng: [`docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`](../02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md)
- Mô hình AI & kế hoạch huấn luyện: [`docs/03_AI_MODEL_AND_TRAINING_PLAN.md`](../03_AI_MODEL_AND_TRAINING_PLAN.md)
- Lộ trình & phân công: [`docs/04_ROADMAP_AND_TEAM_TASKS.md`](../04_ROADMAP_AND_TEAM_TASKS.md)
- Sổ cái chạy mô hình & bàn giao: [`docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`](../06_AI_HANDOFF_AND_RUN_LEDGER.md)
- Ứng viên tích hợp AI: [`docs/10_AI_INTEGRATION_CANDIDATE_20261105.md`](../10_AI_INTEGRATION_CANDIDATE_20261105.md)
- Bản phát hành cho nhóm: [`docs/11_TEAM_RELEASE_20261105.md`](../11_TEAM_RELEASE_20261105.md)
- Hướng dẫn huấn luyện AI: [`ai-training/PRETRAINING.md`](../../ai-training/PRETRAINING.md)
- Manifest đóng băng MVP v1.0: [`ai-training/RESEARCH_MVP_V1_0_FROZEN.json`](../../ai-training/RESEARCH_MVP_V1_0_FROZEN.json)
