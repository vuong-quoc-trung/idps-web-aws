# Training data unblock — 2026-11-07

**CASE B — DATA IMPROVED, TRAINING BLOCKED.** Không train trên cohort này, không
thay model/encoder/threshold frozen, không thay Rules, Web hoặc Policy Engine.
AI enforcement vẫn DISABLED. Git bắt đầu ở `4b0c8e2`, nhánh
`feature/ai-idps-shadow-integration`, working tree sạch.

Milestone này thực hiện một campaign 43 study requests trên hai image DVWA/Juice
đã pin, kiểm tra receipts, Oracle và leakage. Đây không chỉ là một kế hoạch mới.
Kết quả còn thiếu đúng một loại coverage: **benign form POST có Oracle hoạt động
trong CALIBRATION**. Không đổi roles hoặc hạ gate để ép training.

## Thiết kế khóa trước traffic

Roles, workflow/session/campaign IDs, expected intent/outcome Oracle, payloads,
coverage gates và exclusion rules được hash trước HTTP. Candidate riêng cũng khóa
trước capture: encoder 588 chiều, numeric76 + URI256/body192/header64, normalization
riêng từng channel; deep MLP64, 50,696 parameters, new initialization, seed17,
Adam0.001, batch4, tối đa1epoch/250updates. Với18TRAINrows, một epoch chỉ5updates.
Đây là pilot feasibility, không phải ngân sách đủ để chứng minh chất lượng.

| Role | Gate khóa trước | Kết quả thực tế |
|---|---|---|
| TRAIN |≥6workflow groups; GET/POST benign; đủ4families;≥12views|PASS:18rows,9workflow/session components,18views;8benign/10attempts|
| CALIBRATION |≥4benign groups;≥2GET groups;≥2POST groups, cả form vàJSON;≥8benign views|FAIL:8benign/2attempts eligible,3UNKNOWN;3benign groups,2GET/1JSON-POST group;7benign views|
| PROSPECTIVE |2templates mỗiSQLi/XSS/command/file-inclusion family; benignGET/POST;≥10views|PASS:12rows,6workflow groups,12views;8attempts và4benign; scores chưa tính|

TRAIN gồm shell compound commands, stored media-event XSS, technical notes,
SQL expression UNION, file-transform wrappers, reflected technical names và Juice
product list/filter/SQL compound search. Cả hai environment đều có benign/attempts;
TRAIN có cả benignPOST và attackGET. Chưa loại được mọi endpoint/source shortcut:
TRAIN command route vẫn positive-only, prospective benign chỉ có4rows. Không dùng
các giới hạn này để tuyên bố FPR≤1%, Recall80% hoặc cross-domain generalization.

Calibration mới đã có **4JSON feedback POST** với CAPTCHA binding, returned record
và persisted feedback state Oracle; thêm public-file GET và CAPTCHA arithmetic GET.
Hai XSS attempts ở CALIBRATION chỉ dành cho diagnostics; threshold rule đã khóa chỉ
sử dụng benign calibration. Chưa chọn threshold mới trong milestone này.

Các group là workflow/session components theo những tiêu chí đã ghi, không phải
9môi trường độc lập: cùng application source và fixture DB vẫn là shared lineage.
Đây là phạm vi research pilot, không phải independent population evaluation.

## Preflight và thất bại được giữ

Các bản offline đầu không phải dataset release: một bản lỗi schema `_request`,
một bản còn thiếu automatic HTTP headers. Sau khi mô phỏng đúng Host,
Accept-Encoding/Content-Length và cookie presence, preflight tìm5rows trong các
cross-role overlap components; prospective thiếu1command/1SQLi template.
Plan đó bị loại **trước traffic và trước mọi model score**. Thay cú pháp campaign
shell/SQL ở bước thiết kế, giữ nguyên roles/gates, rồi khóa plan cuối43cases.

Capture startup đầu không gửi HTTP: watchdog import ML dependencies ở quota10%
mộtCPU quá chậm, vượt readiness deadline. Sửa lazy imports, giữ nguyên43cases,
roles và gates; kiểm chính systemd watchdog entrypoint khởi tạo/thoát trong≈1.44s.
Probe heartbeat cũ cũng dừng được container thật thuộc đúng run label. Capture
sau đó hoàn thành43/43, không replay các study cases; cleanup thành công.

Một audit strengthening attempt lỗi import `re` trước khi tạo release; giữ log và
thư mục partial. Bản audit cuối chạy đầy đủ. Không sửa hoặc ghi đè các run thất bại.

## Ground Truth thực tế

- 43receipts/IDs và43method/URL/body representations,42frozen views,42candidate views.
- 20BENIGN,20ATTACK_ATTEMPT,3UNKNOWN;40semantic Oracle matches.
- Trong20attempts:14successes theo Oracle nội bộ và6unsafe reflections. Không xác
 nhận browser execution. Intent và outcome được lưu riêng.
- 43automated semantic rechecks; hashes request/response headers/body khớp, snapshot
 users DB được lưu lần này; feedback CAPTCHA binding và persisted state kiểm lại.
- 43human reviews PENDING,0independently verified,0formal admissions mới.
- GLU207 eligible=0: không có đúng207causal fused features; không tạo Suricata giả.

### Vì sao form POST không đạt

Ba benign-intended requests đến DVWA command form có đầy đủ receipts, correct
Content-Type/body/low-security cookie, HTTP200 nhưng `<pre>` rỗng. Oracle đã khóa
đòi loopback ping output; cả ba không đạt và vẫn UNKNOWN.

Ancillary runtime probe trên **cùng image, user www-data**, network=none, không HTTP,
cho thấy `/usr/bin/ping` tồn tại nhưng thất bại với `Operation not permitted` và
thiếu raw-socket capability/setuid. Đây là bằng chứng trực tiếp về dependency
failure và giải thích phù hợp với response rỗng; stderr của chính ba HTTP
transactions không được giữ, nên không giả thành app stderr đã capture.
Command-injection printf canary vẫn thành công khi ping lỗi; success của printf
không chứng minh benign ping workflow hoạt động.

**Thiếu sót của lượt này:** preflight đã kiểm representation/overlap nhưng chưa
kiểm runtime prerequisite của ping Oracle. Test watchdog/resources không thay thế
application Oracle preflight. Tôi không thêm capability, thay policy host, đổi
Oracle hoặc gọi200là benign sau capture. Các rows vẫn ở CALIBRATION/UNKNOWN.

## Leakage, privacy và evaluation seal

Kiểm exact raw representation, coarse route-aware template, rich template,
frozen/candidate float32 view, campaign và actual session digest. Near content
cosine≥.995 trong cùng method/endpoint; quarantine connected component cross-role,
không chuyển role. Actual inputs được kiểm lại, gồm runtime CAPTCHA body binding.
Không có cross-role connected overlap hoặc mixed-intent candidate views phát hiện
trong43rows này. Chỉ3UNKNOWN bị loại khỏi supervised/calibration eligibility.

Prospective được đối chiếu186exposed P0/quality requests và toàn bộ exact views
trong selected WAF tensor. Không claim global raw/near decontamination với mọi
publisher corpus. Cookie/token/request-ID/nonce không làm bằng chứng novelty.
Same DVWA/Juice environment và source đã lộ; không gọi cohort này blind independent.

Sau capture, chương trình tạo prospective manifest/features và seal bằng hashes;
không in per-case outcomes để thiết kế model, không tính score. Seal là integrity
record và local permissions, không phải inaccessible cryptographic holdout.
Không mở old sealed holdout. Encoder/architecture đã khóa trước capture và không
thay theo prospective contents, labels hoặc scores. Independent human review còn PENDING.

Encoder mới là module research riêng; secret fields bị loại trước length/syntax
measurement, header allowlist loại Cookie/Auth/ID. Test xác nhận đổi password/
Cookie/Auth không đổi vector; kéo dài allowed headers không renormalize URI/body;
missing body khác observed empty body. Không đổi live worker body observability.

## Training gates

| Gate | Trạng thái |
|---|---|
| DATA_COVERAGE |FAIL — thiếu benign formPOST calibration, thiếu1benign group và1unique view so với minimum|
| LABEL_PROVENANCE |PASS_FOR_RESEARCH trên40known labels;3UNKNOWN excluded; human review PENDING|
| SPLIT_INTEGRITY |PASS trong phạm vi các checks nêu trên; global provenance chưa được chứng minh|
| FEATURE_CONTRACT |PASS offline588; new encoder có source lock/privacy tests; GLU207 không áp dụng|
| EVALUATION_PROTOCOL |LOCKED,12prospective rows hash-sealed,0scores|
| CHECKPOINT_RECOVERY |VERIFIED ở mức cross-process exact next update trên synthetic fixture|
| RESOURCE_MONITORING |READY cho bounded work; không phải sustained-training qualification|
| FROZEN_BASELINE |PROTECTED; pinned model/derivative artifacts và helper hashes không đổi|

Recovery dùng chính deepMLP588×64 và checkpoint API hiện có, kiểm Adam m/v,
parameters và next loss bitwise equal khi resume trong process khác; lưu RNG,
sampler/cursor, step và constant-scheduler state. Chỉ synthetic updates, không fit
cohort, không có research-trained challenger hoặc checkpoint mới để deploy.
Không tạo training service/status RUNNING giả trong lúc data gate FAIL.

## Tài nguyên và validation

Capture tối đa60°C. Trong targeted tests có spike84°C; guard FREEZE_AND_REDUCE
quota100→50% **mộtCPU**, rồi THAW khi nguội. Peak chưa chạm independent cutoff90°C;
không emergency restart. Log phân biệt≈3.58s active với≈16.34s paused; active
weighted mean≈51.18°C. Không dùng full-run/cooldown mean để chứng minh active
training safety; chưa có sustained300s training qualification.

Shared system-used peak≈12.83GB, dưới30GB; guard giữ4GiB MemAvailable reserve.
Không đóng app của người dùng, không chỉnh thermal/power protection. Tất cả owned
containers/network/watchdog/workload units đã dừng.44tests PASS và Ruff PASS.

## Đúng một nhiệm vụ tiếp theo

**Bổ sung một calibration workflow benign formPOST không phụ thuộc ICMP:** dùng
DVWA `/security.php` với CSRF/session-state Oracle, kiểm điều kiện runtime và
expected Set-Cookie/selected security level từ pinned source **trước khi khóa
capture**. Giữ CALIBRATION session riêng, cần ít nhất2meaningful feature views,
kiểm overlap với manifests hiện có trước HTTP; không thu lại43cases hoặc đổi role.

Đây là một tác vụ nhỏ nhằm điền đúng group/form/view còn thiếu, không mở lại một
chiến dịch nhiều môi trường hoặc thiết kế encoder mới. Giữ nguyên prospective
seal và candidate design; sau khi coverage đạt, dùng recovery/resource evidence
hiện có để xét gate, không tự coi thiếu human admission là cấm mọi research.

## Artifacts và handoff

Raw/session/DB/feedback/receipts/review/tensors ở ignored local:
`ai-training/.artifacts/training_unblock_20261107/`. Capture active:
`campaign-capture-v2`; dataset active:`dataset-release-final-v2`.
Controls/probes/resource reports:`.local-dev/training-unblock/`.

Nguồn chia sẻ an toàn: [collector](../ai-training/scripts/training-unblock-cohort.py),
[auditor](../ai-training/scripts/audit-training-unblock.py),
[encoder research](../ai-training/src/idps_ai/features/research_request_channels.py),
[recovery verifier](../ai-training/scripts/verify-request-channel-recovery.py).
[Machine report/evidence index](../ai-training/reports/TRAINING_DATA_UNBLOCK_20261107.json)
và [pilot config](../ai-training/configs/research/request-channel-unblock-pilot.json).
Frozen GitHub Release/bootstrap/local system không thay đổi; inference không cần
raw research data. Không AWS, AI enforcement hoặc model promotion.
