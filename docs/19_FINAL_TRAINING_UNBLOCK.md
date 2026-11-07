# Final training unblock — 2026-11-07

**CALIBRATION hoàn tất; một pilot kỹ thuật đã COMPLETED.** Không có training nền
đang chạy. Pilot này kiểm chứng pipeline fit/checkpoint/calibration trên tập nhỏ;
**không chứng minh cải thiện detection hoặc generalization**, không promote model.
Frozen Request v2/GLU207, thresholds, Rules/Web/Policy Engine và release giữ nguyên.
Git bắt đầu ở `27ed2b5`, nhánh `feature/ai-idps-shadow-integration`, working tree sạch.

## Hai POST mới và Oracle

Trước capture, lab DVWA pin đúng digest cũ được kiểm `/security.php`: source xử lý
POST `security`/`seclev_submit`, kiểm `user_token`, session đã login, response đặt
cookie `security`, GET tiếp theo có selected option đúng. Preflight tách riêng,
không đưa các requests kiểm cơ chế vào cohort. Không thêm quyền để sửa ping.

Sau preflight PASS, khóa một addendum CALIBRATION gồm đúng2POST, đổi `low→medium`
và `medium→low` trên **session mới**. Mỗi POST có before-GET token, request/response
receipts, Set-Cookie và read-after-write GET. Hai transitions đều khớp semantic
Oracle; HTTP status riêng lẻ không được dùng làm nhãn.

Hai values tạo **2candidate views nhưng1frozen view**. Encoder frozen redaction
withholds body chứa token; candidate bỏ field bí mật trước khi đo syntax nên giữ
khác biệt của security setting. Đây là2views của **một workflow/session**, không
phải2nhóm độc lập. Không lấy token, request ID hoặc timestamp làm novelty.

Có2study POST +4verification GET được receipted; setup/readiness tách riêng.
Preflight có evidence riêng. Hai nhãn BENIGN/Oracle nội bộ, human review PENDING.
Không chuyển3ping UNKNOWN cũ thành benign; không replay43requests.

## Dataset và gates

Calibration eligible mới có12rows:10benign/2attempts,4benign workflow components,
2GET groups,2POST groups (1form+1JSON),8unique frozen benign views và9candidate benign
views. Các minimum đã khóa đều đạt. Ba UNKNOWN vẫn giữ role cũ và bị loại khỏi fit.

Original18TRAIN, original calibration, prospective seal và các role assignments
không thay đổi. Prospective12rows không mở samples/labels/tensors hoặc chấm score;
chỉ dùng opaque hashes/role/template identifiers của index đã khóa để loại overlap.
Không gọi seal bằng hash là inaccessible holdout hoặc independent cross-domain test.

| Gate | Kết quả |
|---|---|
| DATA_COVERAGE |PASS cho finite research/engineering pilot, không phải đủ population quality evidence|
| LABEL_PROVENANCE |PASS_FOR_RESEARCH; Oracle/intent provenance, human review PENDING|
| SPLIT_INTEGRITY |PASS trong phạm vi exact identifiers/templates/views đã khóa; không claim global/exhaustive near decontamination|
| FEATURE_CONTRACT |PASS riêng Request588, frozen contracts không đổi; GLU207 không áp dụng|
| EVALUATION_PROTOCOL |LOCKED, prospective không mở/chấm score|
| CHECKPOINT_RECOVERY |Synthetic cross-process exact next update đã test; real run kiểm reload đầy đủ, chưa claim actual RESUME_EXACT|
| RESOURCE_MONITORING |Guard cgroup + independent sensor/heartbeat watchdog, active/paused thermal accounting|
| FROZEN_BASELINE |PROTECTED; pinned artifacts/checkpoints/encoders/thresholds không đổi|

### Chọn dữ liệu fit thực tế

Không mặc định18rows đủ cho50,696parameters. Kiểm tra thêm đúng35Oracle TRAIN
cũ thuộc quality cohort75 bằng receipts/response/previously audited application
semantics; không truy cập actual prospective records. Re-encode bằng candidate đã
khóa, không dùng shared512content tensor cũ làm channel-separated features.

31legacy TRAIN rows đạt checks;4rows bị loại vì duplicate candidate view. Dataset
fit derived gồm **49unique views:32benign,5SQLi,8XSS,2file-inclusion,2command**,
11workflow/session components trong cùng hai application sources. Original18rows
được giữ nguyên; không đưa CALIBRATION/P0 DEVELOPMENT/publisher test vào TRAIN.
Legacy stored XSS vẫn là attempt/unsafe-reflection evidence, không browser execution.

WAF có quy mô lớn hơn nhưng labels NORMAL/ANOMALOUS không đồng nghĩa grounded
attack-intent/family. Tensor shared-normalization cũ không thể tách ngược thành
URI/body/header channels. GLU207 khác contract. Không silent mix để tăngcount.

49rows vẫn quá nhỏ, positive command/file chỉ2mỗi family và shared app lineage có
nguy cơ memorization/source shortcuts. **Chọn engineering/small-sample feasibility
pilot**, không gọi fine-tune hoặc quality-improvement training. Không chạy thêm
seed, architecture hoặc epoch để tìm kết quả đẹp.

## Pilot đã khóa và hoàn thành

Run:`request-v3-pilot-20261107-01`.
Encoder riêng `research_request_channels.py` giữ nguyên hash đã khóa trước capture
milestone trước:76numeric + URI256/body192/header64, normalization riêng. Model
50,696parameters, deepMLP588→64→64→64→64→8, **new initialization**; frozen first-layer
weights không warm-start vào tọa độ mới.

Seed17, Adam0.001, batch4,1epoch,**13optimizer updates**, checkpoint mỗi update.
Dataset/config/source/dependency fingerprints khóa trước fit. Pilot rất ngắn nên
chạy trực tiếp dưới guard, không tạo job nền kéo dài giả. Status/metrics và full
checkpoint được lưu. Final arrays sau reload khớp bitwise với model trong RAM.

Checkpoint có weights, Adam m/v, RNG, permutation/cursor, epoch/step, scheduler,
config, dataset fingerprint và metrics. Native checkpoint pruning giữ latest,
previous và first-saved best pointer; không sửa checkpoints cũ. Không tự resume/restart.
**Reload roundtrip không phải chứng minh exact next-update resume trên real data.**

Train mean cross-entropy giảm **2.104734→1.317241**. Đây là training diagnostic.

## Controls và kết quả âm tính

Frozen và calibration-only control được tính trước optimizer, chỉ TRAIN/CAL.
Threshold rule khóa trước: strict `>` max benign CALIBRATION score của từng model.
Không chọn threshold bằng prospective hoặc attack labels; không sweep.

| Model | Research threshold | TRAIN TP/FN/FP/TN | CAL TP/FN/FP/TN |
|---|---:|---|---|
| Frozen Request v2 |0.8826237917|7/10/4/28|0/2/4/6|
| Calibration-only frozen |0.9982507825|2/15/0/32|0/2/0/10|
| Challenger sau13updates |0.5897039175|6/11/5/27|2/0/0/10|

Calibration-only tránh benign flags trong calibration bằng cách giảm mạnh attack
flags trên TRAIN. Challenger bắt được2CAL attempts nhưng TRAIN ítTP/nhiềuFP hơn
frozen. Không dùng TRAIN để chứng minh generalization, hoặc0/10CAL false flags để
chứng nhận population FPR≤1%: đó chính là benign data chọn threshold, ít groups.
Không có căn cứ promote hoặc tuyên bố normalization hypothesis đã được xác nhận.

**Quyết định: giữ frozen baseline; giữ challenger/evidence như feasibility artifact.
Không tăng epoch trên49mẫu này và không tự mở prospective.** Chỉ đánh giá prospective
khi người dùng yêu cầu giai đoạn kiểm kết quả; không cần train lại để kiểm checkpoint.

## Tài nguyên, bảo toàn và bàn giao

47targeted tests PASS, Ruff PASS. Actual training max50°C, active weighted mean50°C;
shared system-used peak trong toàn phase≈11.71GB, dưới30GB. Toàn phase max68°C ở
prepare control. CPU quota50% **mộtCPU**, MemAvailable reserve4GiB, no swap/OOM event,
không emergency restart. Các run ngắn không phải sustained300s thermal qualification.
Không dùng cooldown/idle để làm đẹp active training mean.

Tất cả lab containers/network/watchdog/workload services đã dừng; status COMPLETED,
không còn background training. Pinned model/derivative artifacts và role files cũ
khớp hashes. AI vẫn SHADOW/enforcement DISABLED; không AWS, firmware/thermal-policy
change hoặc published-model release mới. Team bootstrap/inference không thay.

Private artifacts (ignored local):
`ai-training/.artifacts/final_training_unblock_20261107/` gồm `security-preflight`,
`security-calibration`, `dataset` và `request-v3-pilot-20261107-01`.
Run có`status.json`,`result.json`,`plan.json`,`baseline-control.json`,`metrics.jsonl`,
`latest.json` và native checkpoint generations. Không public HTTP/session/review/
tensors/weights; không cần chúng để chạy frozen inference của team.

Nguồn: [capture](../ai-training/scripts/final-calibration-capture.py),
[dataset preparation](../ai-training/scripts/prepare-final-request-pilot.py),
[pilot](../ai-training/scripts/final-request-pilot.py).
[Machine report/evidence index](../ai-training/reports/FINAL_TRAINING_UNBLOCK_20261107.json).
