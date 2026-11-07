# Attack-intent dataset v1 — 2026-11-07

**CASE B — dataset derivative hoàn tất; domain-adaptation training BLOCKED.**
Không tạo checkpoint mới. Blocker chính là observation contract và coverage sau
quarantine, không phải thiếu independent human admission. Oracle labels hợp lệ
vẫn dùng được cho research với tuyên bố đúng mức.

Baseline lúc bắt đầu: branch `feature/ai-idps-shadow-integration`, clean HEAD
`7b3342a`. Normalization challenger tiếp tục rejected. Frozen Request v2, GLU207,
encoders, deployment thresholds, Rules, Web, Nginx, correlation, Policy Engine và
published Releases giữ nguyên. Không enforcement/AWS hoặc thay shadow model.

## Dataset thực sự đã tạo

Dataset version: `attack-intent-v1-20261107`.
Dataset fingerprint:
`fa9a2d87852afea879ed146d4bd8077e8a070d42337d6b36ffe836686a4fef5f`.
Local final release: `ai-training/.artifacts/attack_intent_20261107/release-v3/`.
`v3` là build directory; dataset version vẫn v1. Các build attempts cũ bảo toàn,
không có capture lặp lại. Attempt1 gặp body template chứa CAPTCHA cần binding
động; attempt2 chưa normalize enum P0 `succeeded`. Final build kiểm actual-body
binding và giữ `original_outcome`, map unsafe reflection đúng mức, không sửa source GT.

| Nguồn tái sử dụng | Receipts | Vai trò |
|---|---:|---|
| Quality lab DVWA/Juice đã audit | 62 | Giữ TRAIN/CAL/DEV, bỏ qua toàn bộ prospective rows |
| Training-unblock ledger | 31 | Giữ TRAIN/CAL, chỉ dùng opaque exclusions của sealed |
| Security-state calibration addendum | 2 | CALIBRATION |
| Historical DVWA P0 | 111 | DEVELOPMENT đã lộ |
| Cohort hữu hạn mới | 18 | TRAIN/CAL precommitted |
| **Tổng** | **224** | Không cộng publisher anomaly hoặc sealed samples |

Không chuyển dữ liệu đã lộ thành prospective. 12 sealed samples cũ là external
protected reference, không copy vào tensors, không đọc content/labels/features/scores.
Các nguồn prospective khác cũng không deserialize; chỉ lấy opaque exclusion hashes
đã có. Không coi việc hash seal là cơ chế khiến dữ liệu inaccessible.

## Labels và evidence

Intent: **130 BENIGN_INTENT, 81 ATTACK_INTENT, 13 UNKNOWN_INTENT**.
**207** records có internal application Oracle xác nhận; 4 attack intents còn lại
có collector/receipt provenance nhưng outcome Oracle chưa xác minh. Không đổi
những attack này thành benign hoặc tự xác nhận failed exploit.

| Outcome | Records |
|---|---:|
| BENIGN_SUCCESS | 130 |
| VERIFIED_EXPLOIT_SUCCESS | 51 |
| UNSAFE_REFLECTION | 26 |
| UNKNOWN_OUTCOME | 17 |
| VERIFIED_FAILED_ATTEMPT / NOT_APPLICABLE | 0 |

26 reflections không phải browser execution. Không có negative execution Oracle
đủ để tự gán VERIFIED_FAILED_ATTEMPT. Cả **224** records vẫn human review PENDING,
**0** independent human verifications/formal admissions mới.
BENIGN_SUCCESS bao gồm auth denial đúng dự kiến của một benign workflow; không
đồng nghĩa mọi benign login đều đăng nhập thành công.

Mỗi record giữ stable sample ID, version, source/receipt/checksums, environment,
workflow/session/campaign, declared split, exposure, intent/outcome/evidence riêng,
Oracle replay, review queue, full/runtime view hashes, missingness và exclusion reasons.
Receipt body/headers/response hashes được reverify; Oracle tương thích được replay,
các app-state checks đã audit nhưng không có full standalone replay giữ rõ provenance
`PRIOR_AUDIT_PLUS_BOUND_RECEIPT_RECHECK`. Không gọi đó là independent re-verification.

## Capture mới: chỉ một chiến dịch, 18 requests

Plan fingerprint khóa trước HTTP:
`ee7f7eb1dcd7a4fb77ddf0ebacbc84a8e00e38c493a3d7d793d8dc3c76446f77`.
Chốt roles, sessions/campaign rule, view contracts, coverage gates, exclusions,
images và budget trước capture/scores. Reuse roles là rule kế thừa từ artifacts cũ;
file-by-file source bindings được ghi khi build derivative, không tự gọi chúng là
toàn bộ input hashes đã precommit trước HTTP.

Pin DVWA/MariaDB/Juice digests như nguồn cũ, local loopback 17280/17281, internal
network riêng. Kiểm images, ports, sensors, RAM trước HTTP. Preflight fresh fixtures
chạy **9 Oracle representatives, tất cả PASS**, rồi teardown. Main cohort fresh
fixtures chạy đúng **18** requests: **12 benign, 5 attempts, 1 UNKNOWN**, 17 Oracle matches.
9 preflight requests không nhập dataset. Setup/readiness polling không được cộng
nhầm thành 18 tổng HTTP transactions.

Các gaps đã bổ sung: technical stored notes và interactive markup cùng surface,
command pipeline/control canaries, reflected hard negatives, public-file access,
JSON account creation, auth SQLi và auth-denial/search controls. Không dùng nonce
variants để claim workflow independence. Một login lookalike không đạt exact
auth-denial Oracle: giữ UNKNOWN; không re-label từ status hoặc recapture để ép PASS.

Collector mới dùng lại `quality-lab-cohort.py`, không dựng application/security stack
mới. Chỉ các containers mang ownership label riêng được start/stop. Source chạy thật
được archive ở `capture-source.py`; source public sau capture chỉ bỏ một biến unused.

## Runtime model thực sự nhìn thấy gì

Đối chiếu source và **224/224** actual worker envelope → `model_record` → frozen
tensor parity, sau khi dataset đã khóa. Đây là **runtime-contract emulation trên
lab receipts**, không phải live Nginx delivery proof cho DVWA/Juice.

| Stage | Thực tế và hệ quả |
|---|---|
| Authorized lab source | Receipts có full URI, headers và form/JSON body, session evidence local |
| Nginx producer | `$request_uri` và method + User-Agent/Accept/Content-Type; chỉ access sink tại `/api/`, bounded Unix datagrams |
| Worker envelope | URL ≤4096, mỗi selected header ≤1024, không có body/Cookie/Authorization field |
| `model_record` | Giữ URI và ba selected headers thành text; **body=None** |
| Numeric privacy/features | Frozen `project_request` → numeric76; sensitive query/PII có thể bị bỏ, không recover từ source khác |
| Symbolic content | Frozen rich-v2 URI/query syntax/security words, bounded selected-header syntax; query secret/PII bị redact; JSON/body không thể có nếu input đã thiếu |
| Tensor/inference | Original numeric76 + char3–5 shared-L2 hash512 = 588; frozen weights/threshold nguyên trạng |

URI/query không mặc định bị bỏ khỏi in-memory model input; audit journal không
spool raw values. Parameter names/values có thể thành security vocabulary, syntax,
length/entropy buckets hoặc bị redaction. Percent decoding/normalization và hashing
là transformation, khác với field hoàn toàn không tồn tại.

Lab tensors tách **full receipt** và **runtime observable**; không gộp hai contracts.
GLU207 **NOT_ELIGIBLE**: không tạo features Suricata/history/207 giả. Phần lớn lab
routes không nằm trong producer `/api/`; không nói chúng đã đi qua live deployment.

## Chứng cứ mới: mất khả năng phân biệt intent khi bỏ body

Full tensors không có exact opposite-intent collision. Runtime tensors có **2 nhóm,
35 records**:

- Stored-XSS surface: 19 benign + 10 XSS attempts có cùng tensor khi body mất.
- JSON-login surface: 3 benign + 2 SQLi attempts, thêm 1 UNKNOWN, có cùng tensor.

Một deterministic classifier nhận cùng tensor phải cho cùng score. Không có
optimizer, threshold search hoặc thêm tham số nào phân biệt được từng intent trong
những nhóm này chỉ từ contract hiện tại. Đây là information loss đo trực tiếp,
không suy từ training loss hoặc lời giải thích feature importance.

Finite-cohort optimistic bound, với 130 known benign, empirical FPR≤1% cho phép
tối đa1 false flag: cả hai mixed groups đều vượt budget nếu flag. Có ít nhất12
unavoidable label errors nếu chọn nhãn tối ưu cho từng exact view; overall attack
Recall ceiling tại budget này là69/81≈85.19%, riêng XSS tối đa16/26≈61.54%.
Đây là bound trên **cohort đã lộ và weighted receipts**, không independent population
FPR/Recall, không assertion về detector có thêm state/context. Full-view bound100%
chỉ nói không bị exact contradictions; không chứng minh model có thể học hoàn hảo.

Command coverage có vấn đề khác: nhiều distinct bodies thành cùng view của cùng
endpoint qua roles; benign ping Oracle lịch sử vẫn UNKNOWN. Không dùng endpoint-only
attack flags làm bằng chứng nhận diện command semantics hoặc benign safety.

## Splits, leakage và coverage thực tế

Roles giữ nguyên, không chuyển mẫu sau scores. Audit exact raw/template/full/runtime
views, session/campaign; exhaustive near cosine≥0.995 cùng method/endpoint ở cảhai
views. Cross-role conflict bị quarantine ở **cả hai phía**; đây là coverage cost
công khai, không vứt evidence hoặc sửa frozen datasets.

| Role | Receipts | Benign / Attack / Unknown | Full / runtime unique views | Strict eligible |
|---|---:|---|---|---:|
| TRAIN |63|41 / 22 / 0|58 / 21|10: 4 benign, 6 attacks|
| CALIBRATION |37|26 / 2 / 9|23 / 18|13: 11 benign, 2 attacks|
| DEVELOPMENT |124|63 / 57 / 4|98 / 88|86: 40 benign, 46 attacks|

Strict TRAIN còn 4 SQLi views/2 file-family views, **0 XSS/0 command views**, chỉ4
benign runtime views và0benign POST workflows. Không đạt gates ≥2views/family,
≥12benign views, benign GET+POST. CAL có8unique benign views,4GET/2POST workflow
categories, form+JSON; PASS_WITH_LIMITS. DEVELOPMENT đủ4families nhưng chỉDVWA,
đã lộ; PASS_WITH_LIMITS, không phải independent quality.

Có6cross-role raw groups,4template groups,2full-view groups,4runtime-view groups;
74near pairs tính trên hai representations. Exact identities/session/campaign và
near overlap của **strict eligible subsets** phải sạch. Opaque sealed checks chỉ
biết full/raw/template keys: sealed runtime-view overlap **UNVERIFIED**, không mở
12mẫu để debug. Workflow categories không đồng nghĩa independent session components.

TRAIN cóDVWA+Juice; DEV chỉDVWA, hai môi trường đều đã dùng trước đây. Không có
untouched environment, không claim cross-environment generalization. Historical
DEV có trước một phần TRAIN/CAL mới: không phải temporal future test. Thu thêm
request IDs/timestamps không sửa được những giới hạn này.

## Frozen và calibration-only control, chưa có adaptation candidate

Sau release, khóa analysis protocol riêng trước new scores. Chỉ frozen model,
threshold gốc strict>0.8826237917 và calibration-only strict>max11eligible CAL benign.
Không sửa dataset/roles từ scores, không deploy threshold mới.

| View/operating policy | Threshold | Strict exposed DEV TP/FN/FP/TN | P0 TP/FN/FP/TN |
|---|---:|---|---|
| Full, frozen |0.88262379|19/27/0/40|18/30/0/59|
| Full, calibration-only |0.99825078|7/39/0/40|7/41/0/59|
| Runtime emulated, frozen |0.88262379|20/26/0/40|18/30/0/59|
| Runtime emulated, calibration-only |0.82756305|20/26/0/40|18/30/0/59|

P0 UNKNOWN4 excluded. Runtime calibration-only không cải thiện P0; XSS/cmd vẫn0/12.
Frozen full/runtime thêm4attempt flags ngoài matched P0 Suricata; runtime calibrated
cũng4, full calibrated0. Không có Suricata evidence mới cho18capture hoặc toàn224,
không tạo added-detection metrics giả. Strict DEV0/40FP không chứng minh≤1%FPR:
ngay descriptive IID upper two-sided95% cũng≈8.81%; workflow dependence còn hạn chế.

## Training decision và đúng một nhiệm vụ kế tiếp

**Không warm-start/fine-tune lúc này.** LABEL_PROVENANCE đủ cho các Oracle research
rows, nhưng runtime identifiability FAIL, strict TRAIN coverage FAIL, sealed runtime
split chưa xác minh và chưa có cross-environment evaluation mới. Independent human
review PENDING không phải lý do duy nhất hoặc điều kiện formal bị dùng để chặn pilot.

Chọn hướng adaptation khi các gate được giải quyết: **WARM_START candidate từ weights
Frozen v2, reset optimizer được ghi rõ, architecture50,696parameters, attack-intent
binary objective với benign hard negatives**. Frozen và calibration-only giữ làm
controls. Không normalization-only WAF, không new initialization/parameter increase,
không gọi reset optimizer là EXACT_RESUME. Chưa khóa LR/batch/updates/sampler hay
launch config khi feature/data contract còn chưa xác định; không tạo experiment rỗng.

**Một nhiệm vụ kế tiếp:** privacy-preserving body-syntax observability feasibility
experiment trên **hai mixed groups hiện có**, không capture thêm. Khóa allowlisted
field/syntax contract, test secrets/PII canaries, đo xem candidate projection tách
được known opposite-intent pairs mà không dùng source/IDs/session shortcuts, rồi
kiểm lại split/view gates. Nếu không có tín hiệu quan sát được an toàn, thu hẹp
claim của request-only runtime detector; không ép training để che vấn đề. Đây là
offline candidate research, không tự thay live telemetry/Student/Security/Nginx.

## Kiểm chứng, tài nguyên và bàn giao

17targeted tests PASS: schema/intent-outcome/human provenance, receipt tampering,
fingerprint, actual-worker privacy projection, hidden lineage leakage, information
loss bound; các tests normalization/worker cũ vẫnPASS. Ruff/format/diff checksPASS.
Final validation kiểm224receipts, actual envelope/projection/tensor parity,
fingerprints, protected artifacts và unchanged seal. Không fitmodel nào.

Preflight peak48°C, maincapture peak50°C. Collector và owned containers quota25%
mộtCPU mỗi process/container; reserve4GiB. Collector guard độc lập + ownership
watchdog dừng lab ở80°C/rapid rise gần77°C/stale heartbeat/sensor loss. Containers
không được claim nằm chung workload cgroup; host memory/temperature vẫn giám sát.
Không thay OS/firmware protections, không đóng user apps. All owned lab resources
đã cleanup; đây không phải sustained-training thermal qualification.

Private evidence: `ai-training/.artifacts/attack_intent_20261107/` và
`.local-dev/attack-intent-20261107/`. Final release có records/review queue,
train/calibration/development NPZ riêng full/runtime, release manifest/checksums.
Rebuild trên evidence local bằng `release-attack-intent.py --base ... --output NEWDIR`;
không ghi đè output cũ. Absolute historical receipt paths cần remap nếu di chuyển
evidence sang host khác; chưa claim cross-host dataset bootstrap đã kiểm.

Public:[aggregate report](../ai-training/reports/ATTACK_INTENT_DATASET_20261107.json),
[release builder](../ai-training/scripts/release-attack-intent.py),
[schema](../ai-training/src/idps_ai/data/attack_intent.py),
[finite collector](../ai-training/scripts/attack-intent-capture.py),
[tests](../ai-training/tests/test_attack_intent.py).
Không public HTTP/session/PCAP/tensors/checkpoints. Team clone/bootstrap/frozen
model restore/local demo không cần dataset này và giữ nguyên.
