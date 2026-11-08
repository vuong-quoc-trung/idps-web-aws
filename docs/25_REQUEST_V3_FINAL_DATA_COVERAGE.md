# Request v3 final data coverage — 2026-11-08

**CASE C — capture infeasible với essential command Oracle trong sandbox hiện tại.**
Chiến dịch đã dừng ở preflight, không chuyển sang main capture. Không có supervised
records hoặc dataset release mới; TRAINING_READY=false, không sustained training.

Baseline `467425a`, branch `feature/ai-idps-shadow-integration`, working tree sạch khi
bắt đầu. Giữ nguyên634input/53,640parameters/warm-start design và existing CAL;
không sửa Web/Nginx/Suricata/Rules/Policy/correlation/frozen models hoặc thresholds.

Machine report: [REQUEST_V3_FINAL_DATA_COVERAGE](../ai-training/reports/REQUEST_V3_FINAL_DATA_COVERAGE_20261108.json).
Collector: [finite controls](../ai-training/scripts/request-v3-final-controls.py).
Recovery proof tool: [synthetic634 recovery](../ai-training/scripts/verify-request-v3-recovery.py).

## Plan đã khóa trước HTTP

12main templates,9Oracle preflight representatives; tối đa24targeted receipts,
không dùng model scores. Pre-audit trên permitted exposed224records kiểm raw,
template, full-view/full-near và634candidate exact/near: cả12planned cases không
có conflict theo checks đã khóa. Giữ exact/near/lineage quarantine ở cả hai phía.

| Role dự kiến | Controls |
|---|---|
| TRAIN | Quoted literal localhost diagnostic; absolute path tới public file1.php và normal render; owned basket JSON POST + authenticated read; một UNION canary query mới để MISSING không là benign-only signal |
| DEVELOPMENT |4legitimate product JSON variants; authenticated identity read; login và empty logout form |

Không dùng quoting để tự xác nhận benign: command phải có actual four-packet/zero-loss
Oracle. Chỉ một literal localhost argument, không command operators/substitution hoặc
quyền ngoài lab. File control chỉ render file công khai, không đọc private file/source.
DEV dự kiến6unique benign POST qua3workflows, FORM+JSON. Các bodies/framing thật quyết
định MISSING/EMPTY/OK, không sửa vector sau capture. Role/application instances riêng
cho main; preflight diagnostics không nhập training. CAL/prospective không sử dụng.

Images pin như các lab trước; loopback19280, internal owned network, mỗi container
quota25%onecore, bounded RAM/PIDs, no-new-privileges và no container log driver.
Collector dùng existing lab/setup/feature helpers với source bindings. Session/CSRF,
request/response bytes và dynamic bindings chỉ ở RAM; không dump raw HTTP receipts.

## Kết quả âm và root cause

Hai setup attempts trước không hoàn tất receipt: helper đọc sai session namespace;
cleanup error đã che exception ban đầu. Source pinned DVWA xác nhận auth là
`$_SESSION['dvwa']['username']`, không phải root username. Reader sửa đúng namespace,
read-only unserialize với allowed_classes=false; **3actual PHP fixtures PASS**:
authenticated nested session, logged-out nested session, reject wrong namespace.
Không sửa authentication/app source hoặc mở permissions để test PASS.

Podman removal có thể return125 dù container đã absent. Collector nay kiểm ownership,
kiểm actual absence và ghi returncode; nếu còn object thì vẫn fail. Không coi nonzero
là success khi chưa kiểm state. Source executed được archive/bind bằngSHA trước khi
publish metadata naming hardening; các attempts cũ không bị overwrite.

Corrected preflight gửi đúng **1targeted request**, nhận HTTP200 nhưng cả bốn checks
đều false: hostname resolved, four transmitted, four received, zero loss. Giữ
**UNKNOWN_INTENT / UNKNOWN_OUTCOME**, reviewPENDING; planned benign không là verified
benign. Main0requests;11templates còn lại chưa phát. Không tiếp tục capture/recapture
để tìm kết quả đẹp hoặc gọi200làOracle. Source data/roles không thay đổi.

Dependency probe riêng, **0HTTP**, dùng cùng pinned image, application UID `www-data`,
no-new-privileges và localhost-only: `ping` exit2, category **PERMISSION_DENIED**.
Binary hiện diện, nhưng chưa vận hành được dưới đúng sandbox của ứng dụng. Đây là
bằng chứng blocker của legitimate command Oracle; không chứng minh duy nhất một
kernel/capability setting nào là nguyên nhân. Không thay host sysctls/capabilities,
OS/firmware protections hoặc giả output của ping.

Ledger corrected attempt ghi trước dispatch và sau response. Conservatively reserve
1possible prior dispatch do first attempt chưa có durable ledger: observed1completed
preflight receipt, **global targeted dispatch upper bound2**, dưới cap24. Setup/auth
calls24qua ba attempts được đếm riêng, không tạo supervised receipts; không claim
tổngHTTPtraffic≤24. Diagnostic trace của attempt thứ hai xác nhận0target dispatch.
Synthetic/unit HTTP fixtures và CLI dependency probes không phải cohort receipts.

## Dataset và coverage giữ nguyên

Parent final release vẫn `request-v3-body-syntax-20261108-v1`, build `release-v2`,
fingerprint `5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`.
Không tạo v3-data release mới chỉ từ một UNKNOWN preflight observation.

| Role | Strict before / after | Unique views before / after | Benign / Attack |
|---|---:|---:|---|
| TRAIN |43 / 43|37 / 37|23 / 20|
| CALIBRATION |13 / 13|13 / 13|11 / 2|
| DEVELOPMENT |86 / 86|83 / 83|40 / 46|

TRAIN vẫn SQLi4/XSS8/command4/file2views; benignGET4/POST19, chỉFORMPOST. DEV vẫn
0benignPOST, cả6POSTđềuattack. Command/file cùng-surface benign controls và TRAIN
JSON gap chưa đóng; các workflow chưa chạy là NOT_CAPTURED, không tự gán OracleFAIL.
Existing224states149EMPTY+75OK; không có natural MISSING supervised examples mới.
Independent review224PENDING không đổi. Một preflight UNKNOWN được giữ riêng,
PREFLIGHT_ONLY_NOT_ADMITTED; không nâng automated checks thành human review.

## Privacy và missingness scope

Không persist raw body/header/response hoặc direct secret digests vào capture metadata.
Request IDs là collector-sent identifiers, không phải independent PCAP/proxy witness.
Oracle checks giữ booleans/counts; không dùng AI/Suricata làm Ground Truth.
Diagnostic manifest dùng ordinal session/campaign aliases và planned-role reference;
source receipt nguyên trạng được giữ riêng. Published collector cũng dùng ordinal IDs;
đây là source-only metadata hardening sau lượt chạy, không đổi executed vectors/labels.
Per-record diagnostics vẫn local-only; production privacy NOT_VERIFIED.

MISSING/EMPTY/MALFORMED/UNSUPPORTED_TYPE/TRUNCATED được kiểm bằng separate contract
fixtures, không nhập supervised dataset. Không có actual truncated HTTP flow mới.
Worker unavailable/telemetry-drop live evidence tái sử dụng từ body-live acceptance;
không có worker/runtime replay mới trong milestone này. Missingness không là nhãn.

## Training infrastructure: phần đã xác minh

**WARM_START_VERIFIED**, **CHECKPOINT_RELOAD_VERIFIED**, **EXACT_RESUME_VERIFIED** ở
mức small synthetic proof cho actual634architecture và partial_binary_v1 objective.
Load actual frozen v2 weights read-only, expand W0 thêm46zero rows; initial synthetic
forward parity atol1e-7. New Adam moments/step0, không reuse optimizer frozen.

Hai synthetic updates, checkpoint step1, process mới restore RNG/permutation/cursor/
epoch/scheduler/data+feature fingerprints; next loss/parameters/Adam m/v bitwise equal.
Final reload step2PASS,53,640parameters. Synthetic checkpoint directory:
`ai-training/.artifacts/request_v3_final_20261108/synthetic-recovery/`.
**Không phải checkpoint train bằng cohort thật**, không dùng inference/promotion.
Existing634data-loader/normalization contract giữ nguyên, fit statistics0; không fit
CAL/DEV hoặc mởsealed. Recovery qua crash/hardware/production còn NOT_VERIFIED.

| Gate | Status hiện tại |
|---|---|
| Existing dataset integrity / feature contract | PASS / LOCKED, parent unchanged |
| Label provenance | PASS_FOR_RESEARCH cho existing Oracle rows; new preflight UNKNOWN excluded |
| Existing strict split / CAL minimum | PASS trong exposed research scope |
| TRAIN coverage | FAIL, gaps giữ nguyên |
| DEV benign POST coverage | FAIL,0records |
| New derivative materialization/rebuild | NOT_RUN, không có admitted main cohort |
| Synthetic warm-start/reload/exact next update | VERIFIED, actual-cohort training0updates |
| Evaluation config | Existing locked design/procedure unchanged; chưa bind release mới |
| Frozen baseline | PROTECTED |

Final targeted Python tests46PASS, Ruff/formatPASS. Guard peak66°C trên các workloads
đã báo cáo, active averages<80°C; no watchdog/thermal failure. Quota25%onecore,
outer cutoff85°C, ownership watchdog80°C/reserve4GiB; containers có limits riêng,
không claim chung cgroup với collector. Không sustained-training qualification.
All owned containers/network/listener/watchdogs đã dừng; original datasets/checkpoints,
158protected hashes, old PG volumes và published Releases giữ nguyên. Không AWS,
enforcement, merge/main hoặc model promotion.

**Đúng một blocker kế tiếp:** vận hành được legitimate localhost ping cho `www-data`
trong source-pinned isolated lab với Oracle packet summary hợp lệ, không nới host
protections hoặc giả nhãn. Chỉ sau đó mới tiếp tục các controls đã precommit theo
bounded budget; không đổi architecture, thresholds hoặc capture filler. Milestone
hiện tại dừng tại CASE C.
