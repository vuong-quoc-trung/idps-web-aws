# Request v3 dataset completion — stopped at diagnostic gate (2026-11-08)

Baseline `514bedf`, branch `feature/ai-idps-shadow-integration`.
Machine report: [REQUEST_V3_DATASET_COMPLETION_20261108.json](../ai-training/reports/REQUEST_V3_DATASET_COMPLETION_20261108.json).

**CASE C — PREFLIGHT INSTRUMENTATION STOP.** Basket fixture đã sửa và positive
CREATE đã được xác minh. Campaign chưa đạt 9/9 preflight, main **0/24**,
không có derivative mới, checkpoint mới hoặc training. Lỗi dừng lần này nằm
trong logic kiểm tra do lượt này bổ sung; chưa chứng minh một application bug mới.

## Fixture và bằng chứng thực tế

Fixture `dedicated-empty-owned-basket-v2.1`, execution
`request-v3-completion-20261108-r2` dùng tài khoản customer tạo qua registration
bình thường trong Juice Shop cô lập. Credential, token, email và BasketId chỉ ở
RAM. Trước CREATE: session được xác minh qua response `whoami`, user/basket
ownership, ProductId 1, stock, quantity hợp lệ; DB read-only xác nhận basket rỗng.
Giữ nguyên `POST /api/BasketItems/`, ProductId 1, quantity 1, expected HTTP 200,
role, template và ý nghĩa Oracle cũ. Không sửa seed hay unique constraint.

Positive response **200**, DB từ **0 pair / 0 item** sang **1 pair / quantity 1**.
Read-after-write là kết nối SQLite độc lập ở chế độ `OPEN_READONLY`.
Giỏ admin vẫn quantity 2 và toàn bộ witness của nó không đổi. Request ID khớp
receipt và dispatch ledger; không có tuyên bố packet-level correlation.

Amendment được khóa trước HTTP, liên kết source/image và parent plan:

- Plan: `2d5df40eb8712c31e9fcb5145642b933632829b6d0344b480991a1e95ec254b8`.
- Fixture/environment: `c8ad864926ce0aebaa6b2e071c14c2d52cf04a3edfbca3a724b0081cbf126a1a`.
- Exact executed source được lưu local và đối chiếu hash trước khi sửa kiểm tra offline.

Lượt setup r1 trước đó đăng ký/login thành công nhưng dừng trước mọi targeted
request: `whoami` của image pin đọc **token cookie**, không đọc Bearer header.
Source `currentUser.js` đã được đối chiếu. r2 thêm binding cookie cho cùng token
RAM tại riêng endpoint đó. Không thay auth policy, không giả lập authenticated user.
Đây là sửa transport binding, không chuyển role hay đổi ý nghĩa intent/Oracle.

DB witness của product được sửa từ `node` sang `/nodejs/bin/node` đúng image
pin. Representative product chưa chạy nên sửa này chưa được live-qualified.

## Vì sao dừng dù positive CREATE đã thành công?

Negative diagnostic cố CREATE lại cùng pair sau positive:

- HTTP **500**.
- Pair vẫn đúng một dòng quantity 1; toàn bộ read-only state không đổi.
- Không có supervised label, không được gọi benign success.
- Sanitizer chỉ giữ được exception taxonomy **UNKNOWN**; response gốc và media
  type không được lưu. Không suy đoán chắc chắn JSON/HTML hay exception class.

Code mới đã dùng `diagnosis.classify(...)["verified"]` làm negative gate. Hàm
đó phục vụ **xác minh root cause** và yêu cầu exception class cụ thể. Vì taxonomy
UNKNOWN, gate false; wrapper còn ghi đè positive Oracle thành UNKNOWN rồi dừng.
Đây là lỗi ghép hai tiêu chí của implementation, không phải bằng chứng CREATE thất bại.

Bản sửa offline tách:

1. Positive CREATE: response hợp lệ + trước chưa có pair + sau có đúng quantity.
2. Negative rejection/non-creation: HTTP 500 + pair đã tồn tại + DB không đổi.
3. Exception/root-cause taxonomy: giữ UNKNOWN nếu thiếu bằng chứng.

Nếu negative gate không đạt, campaign vẫn dừng qua flag riêng, giữ nguyên kết luận
positive khi nó có bằng chứng. Test regression bao gồm negative body không parse
được JSON. **Không chạy thêm HTTP để kiểm chứng bản sửa trong lượt này.**
Đánh giá non-creation offline từ metadata hiện có PASS; đây không phải một live
preflight mới. Receipt `UNKNOWN` và gate false đã ghi trên disk giữ nguyên.

## Campaign accounting và Ground Truth

Năm DVWA representative cũ (`00/01/02/10/11`) được tái sử dụng sau kiểm tra
hash/protocol, không tính thành evidence độc lập mới. r2 phát đúng **2** targeted
HTTP: một positive preflight Basket, một negative diagnostic; cả hai có response.

Preflight ledger hiện có **6/9** representative receipts: 5 Oracle verified cũ,
1 UNKNOWN do gate ghép ở trên. Positive DB proof riêng PASS không được dùng để
âm thầm sửa ledger thành 6 PASS. Các representative `04` (basket read), `05`
(product), `09` (whoami theo locked case) **chưa chạy**. Identity setup có dùng
whoami nhưng không được tính thay representative 09.

Main **0**. Không đưa bất kỳ preflight/negative/setup nào vào TRAIN/CAL/DEV.
Independent human review **PENDING**, không có human verification mới.

## Dataset và readiness

Giữ nguyên 224-record release:
`request-v3-body-syntax-20261108-v1`, fingerprint
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`.

| Metric | Before | After |
|---|---:|---:|
| TRAIN strict records | 43 | 43 |
| TRAIN unique views | 37 | 37 |
| CAL strict records | 13 | 13 |
| CAL unique views | 13 | 13 |
| DEV strict records | 86 | 86 |
| DEV unique views | 83 | 83 |

Coverage per role, intent, method, media, family, workflow/session component và
missingness trước/sau được giữ trong machine report. Không có sample mới nên
không có duplicate audit, parity/rebuild hay fingerprint **của derivative mới**.
Bằng chứng deterministic rebuild 7 file của parent vẫn được bảo toàn, không chạy lại.
Collision counts không phải Recall/FPR hay kết quả cải thiện detection.

| Gate | Kết luận |
|---|---|
| DATASET_INTEGRITY | PASS cho parent 224, không có release mới |
| ORACLE_PROVENANCE | PARTIAL diagnostics; positive CREATE verified, ledger giữ UNKNOWN |
| STRICT_SPLITS | PASS cho các role exposed hiện có; không có admission mới |
| TRAIN_COVERAGE | FAIL: chưa có eligible JSON POST, command/file benign counterpart mới |
| DEV_COVERAGE | FAIL: vẫn 0 eligible benign POST |
| CALIBRATION_VALIDITY | PASS minimum nghiên cứu cũ, vẫn nhỏ và phụ thuộc nhóm |
| FEATURE_CONTRACT | 634 fixed, frozen prefix 588 + body syntax 46, không thay đổi |
| PRIVACY_FOR_RESEARCH | PASS trong phạm vi diagnostic, giới hạn scan bên dưới |
| CHECKPOINT_RECOVERY | Warm-start/reload/exact resume synthetic 634 đã VERIFIED trước đó |
| EVALUATION_PROTOCOL | Locked exposed research cũ; chưa bind derivative mới |
| RESEARCH_PILOT_READY | **false** |
| INDEPENDENT_QUALITY_CERTIFIED | **false** |

Không đổi challenger `634→64→64→64→64→8`, 53,640 parameters; không chọn threshold,
không tính model scores, không fit statistics hay train.

## Privacy, resource và bảo toàn

Per-request diagnostic metadata chỉ giữ các trường đã giới hạn: boolean/count,
ordinal groups, request IDs, status, safe schema và source/environment bindings.
Không tạo raw HTTP/body/header/response, email/token/cookie dump, secret digest,
PCAP hay tensor file mới. Scan các JSON/log mới đối với secrets local đã biết và
literal/URL/base64/hex/SHA1/SHA256/JSON-escaped forms không thấy match. Các random
credential của phiên chỉ ở RAM và không giữ để exact-scan sau exit; không tuyên bố
đã scan mọi actual random value. Test output-boundary dùng canary cũng PASS.
Không có production privacy certification.

CPU quota 25% một core, container quota riêng; guard cutoff 85°C, ownership
watchdog 80°C, reserve khoảng 4 GiB. Nhiệt cao nhất guard quan sát **61°C**, không
thermal trip, watchdog failure hoặc restart. Hai capture dừng bởi assertion,
không phải nhiệt; không gọi chúng PASS toàn workload.

158 protected hashes và hai historical UNKNOWN files byte-identical. UNKNOWN
mới r2 cũng được giữ. Models/encoders/thresholds/checkpoints, web/nginx/sensor,
Rules/Policy/correlation và published Releases không đổi. Không mở sealed data,
AWS hay AI enforcement. Lab container/network/listener đã hết, inventory volume
không đổi, hai PG cũ vẫn stopped với mount được giữ.

Private evidence (ignored):

- `ai-training/.artifacts/request_v3_completion_20261108/campaign-r1/`
- `ai-training/.artifacts/request_v3_completion_20261108/campaign-r2/`
- `.local-dev/request-v3-completion-20261108/` — executed source, resource,
  privacy và final-integrity proofs.

**Một bước tiếp theo:** tiếp tục hữu hạn phần Juice preflight còn thiếu bằng
negative gate đã sửa; tái tạo basket state cần cho readback được tính là setup,
không evidence độc lập. Chỉ sau đủ 9/9 mới chạy 12 main templates cũ và materialize.
Không redesign, không đổi acceptance thresholds hay tự bắt đầu training.
