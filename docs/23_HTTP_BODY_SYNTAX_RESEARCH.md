# HTTP body syntax v1 — 2026-11-07

**CASE B — CANDIDATE PARTIAL.** Một candidate giảm mixed-label collision records
từ35 xuống6 và có actual HTTP/socket/worker parity trong isolated prototype.
**Production LIVE_OBSERVABILITY=NOT_READY; production privacy gate=NOT_VERIFIED.**
Không training, không checkpoint, không nối candidate vào frozen inference hoặc
Rules/Policy/DB/dashboard. Không claim Recall/FPR improvement từ feature separation.

Baseline: clean branch `feature/ai-idps-shadow-integration`, HEAD`0762535`.
Chỉ tái dùng attack-intent release224receipts, fingerprint
`fa9a2d87852afea879ed146d4bd8077e8a070d42337d6b36ffe836686a4fef5f`.
12sealed samples và các prospective khác không mở; labels/review/roles không đổi.

## Root cause, loại bỏ giả thuyết novelty từ request ID

| Nhóm | Requests/bodies khác nhau | Intent | Selected headers | Session lineage |
|---|---:|---|---|---:|
| POST`/vulnerabilities/xss_s/`, form |29/29|19benign,10XSS|1profile|4|
| POST`/rest/user/login`, JSON |6/6|3benign,2SQLi,1UNKNOWN|1profile|2|

29stored-XSS requests có29full views; cả29responses200 nhưng19benign operation
success và10unsafe reflections được kiểm bằng guestbook block/prior persistence
audit. Cookie có4distinct values; Content-Length22distinct; request ID29distinct.
Không đưa các giá trị hoặc hashes secrets này vào candidate.

6login requests có6bodies khác nhau nhưng chỉ2full frozen views. Ba benign requests
có expected auth denial401, hai SQLi có auth identity/challenge-transition Oracle200,
một UNKNOWN500. Cookie/Authorization không khác theo meaningful credential profile;
Host có2giá trị theo lab instances và Content-Length6giá trị. Hai session groups
là conservative collection lineages, không khẳng định hai authenticated users.

Ngay khi bỏ **toàn bộ headers**, method+target+body vẫn khác nhau ở cả29/6requests,
không có opposite-intent pair cùng meaningful ingress input. Đây là **CASE A:
information loss tại `scripts/ai-shadow-worker.py:model_record` đặt body=None**,
không phải kết luận dựa vào IDs/timestamps hoặc model scores. CASE B — cùng HTTP
input khác outcome chỉ vì state — **không được chứng minh trong hai nhóm này**.
Oracle outcomes vẫn phụ thuộc application state; không suy rằng body luôn đủ để
phân loại mọi intent/outcome. Không kiểm browser execution.

## Một contract mới, khóa trước diagnostics

Version`http-body-syntax-v1`, **46integer columns**; contract SHA:
`0e163b7392a9bb68131e4c66486fa5827ce6259295f0d703b403a8efad96982c`.
[Contract JSON](../ai-training/configs/research/http-body-syntax-v1.json).
Không source/session/route/label/time input, không learned vocabulary, không raw
ngrams/token hashes. Features:

- One-hot observation/parser state và coarse media type.
- Bucketed counts: root fields, allowed/ignored/analyzed/restricted/nonstring values.
- 17aggregate punctuation counts, mỗi count clip0–3.
- 8fixed generic syntax flags: HTML tag, event assignment, script scheme,
  SQL boolean/union structure, shell substitution, percent escape, HTML entity.

Không exact body/value length, arbitrary field names/values, identities hoặc
hashes của chúng. Chỉ root string values thuộc allowlist mới được profile; không
flatten arbitrary JSON. Allowlist research: message/comment/text/description/content,
q/query/search và DVWA`ip`/`mtxMessage`. Nguồn/phạm vi: generic noncredential text
inputs và form contracts từ pinned DVWA snapshots đã có; **không phải policy được
phê duyệt cho mọi application**. Unknown fields bị bỏ giá trị hoàn toàn.

Email/username/password/token/session/cookie/Authorization không nằm trong allowlist.
Allowed values khớp fixed PII/secret patterns cũng bị withheld trước statistics.
Đổi protected-field values trong giới hạn parser không đổi vector. JSON parsing vẫn
đọc cấu trúc transiently để kiểm định dạng; không claim chưa từng quan sát bytes.

Candidate là object riêng. Để **đếm collisions** dùng joint view588runtime+46syntax
=634dimensions; không feed634 vào model588. Không đổi feature ordering hoặc tham số
model frozen. Chưa thiết kế/khóa kiến trúc training sử dụng signal mới.

## Privacy boundary và giới hạn parser

Form-urlencoded/JSON UTF-8, body≤8192bytes,≤32fields, JSON depth≤8, allowed value
≤1024characters. Trước decode/parse kiểm size; depth guard trước JSON parser.
Malformed/duplicate-key/nonfinite JSON, excessive fields/depth/value size và invalid
UTF-8 có state rõ ràng. Missing/empty/truncated khác nhau. Không xem unsupported là
benign hoặc sinh partial syntax như thể đã có đủ body.

Multipart, compressed bodies và chunked **syntax** chưa hỗ trợ. Không decompress
hoặc đoán body bị thiếu. Chunked framing/compressed bytes vẫn được prototype relay
chuyển tiếp; event chỉ có unavailable state/media. Candidate parser lỗi không đổi
forwarding decision. Trần8KiB là extraction buffer, khác với lab transport budget
≤1MiB. Prototype chưa qualified TLS/Expect100/pipelining/malformed HTTP framing.

Trusted boundary của prototype giữ body trong RAM rồi chỉ gửi version/contract ID,
trusted request ID và46integers qua Unix datagram. Không URI/header/body output.
Datagram nonblocking; worker schema deny extra fields, invalid version/shape/ranges,
error log chỉ constant status. Worker finite budget512events/64rejection log lines.
Socket ở private short temporary directory, chỉ có socket node; không có body files.

Allowlist/filter không phải anonymity hoặc differential privacy. Coarse syntax vẫn
có thể disclose content properties/fingerprint payload biết trước; parse state và
field count cũng tiết lộ cấu trúc. PII heuristics không nhận biết mọi secret trong
free text. Derived per-request artifacts vẫn local-only. Không nới policy để tách
được nhóm login, không lưu secret digest để tránh dictionary guessing.

## Collision diagnostics trên224records đã lộ

| Representation | Unique views | Mixed groups | Affected records |
|---|---:|---:|---:|
| Current runtime588 |122|2|35|
| Runtime + body-syntax candidate |158|1|6|

Stored-XSS group trở thành23unique joint views, **0mixed groups/records**. Không
nhất thiết mỗi request có vector riêng; benign/attack exact collisions đã được tách.
JSON login còn1view/6records: password/email values bị loại nên syntax v1 không
tách được SQLi intent. Đây là **information có ở ingress nhưng policy cố ý loại**,
không chứng minh các HTTP inputs vốn giống nhau hoặc application state là nguyên
nhân duy nhất. Kết quả âm này được giữ nguyên; không chỉnh features sau labels.

States trên224records:149EMPTY,75OK. Không cóunsupported body trong corpus này;
các trường hợp unsupported được kiểm bằng fixtures riêng. Không thêm dữ liệu mới
vào TRAIN/CAL/DEV, không dùng cohort sealed, không chạy candidate detector.

## Canary và actual isolated live parity

Sáu canary families giả lập: password, API key, session token, random unique secret,
email và phone. Fake secrets gửi trong body fields, Cookie, Authorization; canaries
chỉ tồn tại trong test RAM, không ghi lại giá trị/hashes của chúng trong report.
Đã kiểm serialization, real Unix datagram, worker candidate input, numeric journal,
worker error log và NPZ feature artifact; scan raw/base64/URL-encoded/escaped forms
trên5output files: **0leaks**. Sáu raw/secret-bearing poisoned events bị worker reject
và chỉ log`REJECTED_SCHEMA`. Metamorphic tests kiểm protected-value invariance.

Scan thêm17existing foundation logs/journals không thấy canaries. Tuy nhiên các
Rust/database/dashboard candidate paths **NOT_EXERCISED_NO_CONNECTION**; không dùng
absence này để tuyên bố đã kiểm production privacy. Không khởi động DB/Web chỉ để
làm đẹp canary coverage. Không log new raw bodies, request receipts hoặc debug locals.

Live path thực sự đã chạy:

`HTTP client -> loopback ingress extractor -> Unix datagram -> candidate worker`.

Replay224existing receipts, không tạo new GT cohort. **224/224parity** với offline
vector, cùng trusted request IDs; witness nhận body/path/headers nguyên vẹn. Witness
là real no-log HTTP server kiểm byte/header semantics trong RAM, **không phải**
DVWA/Student application-state execution. Không giả chứng minh app business behavior.

Thêm5actual HTTP cases: malformed JSON, oversize9008bytes, multipart, gzip, chunked:
đều response witness200/bodyOK, bytes không đổi và unavailable-state parityPASS.
Extractor exception và absent worker gây2deliberate telemetry drops, app vẫnOK;
extractor disabled cũngOK. Nominal235events gồm224replays+6canaries+5format cases,
**0drops**. Không claim lossless delivery hoặc production availability.

Production**NOT_READY**: existing Nginx producer vẫn chỉ URI+3headers, body=None
tại frozen worker. Nginx runtime config có`client_body_temp_path`; lúc kiểm thư mục
trống nhưng chưa test non-persistence qua real Nginx/Student/DB/API. Candidate chưa
nối vào những đường này; buffering, TLS/framing/correlation provenance và schema
delivery ở môi trường thật còn phải kiểm. Không sửa Nginx/Web/Rules/Policy trong lượt này.

## Performance, regressions và readiness

Extraction CPU dưới tracemalloc: p50≈0.0146ms,p95≈0.3092ms,max≈1.9903ms;
peak traced extractor allocations43,753bytes. HTTP replay p50≈10.25ms,p95≈19.89ms.
12probe pairs trên cùng proxy: extraction-off p50≈5.80ms, on≈10.91ms. Đây là wall
times có quota/thread/socket/disk scheduling, không coi hiệu median là overhead
CPU thuần hoặc production throughput. Không có hard preemptive parse deadline;
resource bounds dựa size/depth/field limits và finite regex patterns.

Observed prefix peak443bytes; code cap8192, over-limit body không được giữ prefix.
Không claim total process memory≤8KiB. Study guardPASS,max56°C, khoảng8.44s;
regression/evidence guards max52°C, shared peak≈11.55GiB, reserve4GiB. CPU25%mộtcore,
active-time supervisor và watchdog, không thermal stop/restart. Không phải sustained
300s thermal qualification. All sockets/servers đã đóng sau finite probes.

**49tests PASS**: body syntax/privacy/error/live-forwarding tests và existing
attack-intent/normalization/shadow/correlation tests. Ruff/formatPASS. Frozen RIv2
P0 replay full/runtime đều giữTP18,FN30,FP0,TN59,UNKNOWN4, threshold0.8826237917.
36source/artifact bindings được verify; Rust Rules/AI decode/correlation SQL sources
giữ hash. Python shadow/correlation regressionsPASS; full Rust/DB/API integration
**NOT_RUN**, không gọi đây là production Rule–AI acceptance mới.

Candidate extraction contract/isolated privacy/HTTP parity có bằng chứng tích cực.
Production observability/privacy chưa đủ, login collision còn nguyên. Dataset role
assignments và old strict masks không sửa; **chưa re-audit splits/near-overlap/coverage
cho634view**, không mặc định strict TRAIN10 tự thành training-ready. Human review vẫn
PENDING. Không model quality gain, checkpoint hoặc model promotion mới.

**Một nhiệm vụ tiếp theo:** opt-in real ingress integration verification của numeric
body contract, gồm non-persistence canaries qua body buffering và actual candidate
worker delivery. Giữ identity fields excluded và frozen path riêng nguyên trạng;
không mở dashboard hoặc training trước live/split/coverage gates.

## Evidence và tái lập

Public:[machine report](../ai-training/reports/BODY_SYNTAX_20261107.json),
[extractor](../ai-training/src/idps_ai/features/body_syntax_v1.py),
[isolated transport](../ai-training/src/idps_ai/features/body_syntax_transport.py),
[study](../ai-training/scripts/research-body-syntax.py),
[tests](../ai-training/tests/test_body_syntax_v1.py).

Private:`ai-training/.artifacts/body_syntax_20261107/` giữ plan, candidate lock,
archived source, numeric NPZ, root-context verification, HTTP numeric worker journals
và report. `.local-dev/body-syntax-20261107/` giữ guarded test/performance logs.
Không public per-request artifacts/raw evidence. Study dùng outputdirectory mới,
refuse overwrite; exact source/contract/protected hashes phải khớp lock.
Lỗi phân loại form-field limit trong test đầu đã sửa trước diagnostics; socket path
được đổi sang short private directory trước224replay. Initial evidence giữ riêng,
không có feature sweep hoặc label-driven refinement. Team frozen bootstrap/release
vẫn nguyên trạng và không cần candidate artifacts.
