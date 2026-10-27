# 02 — Chiến lược dữ liệu và Feature Engineering

Ngày khảo sát: **26/10/2026** (Asia/Ho_Chi_Minh). Baseline code: `37bc4d2ae1552939659a10647898e2228f1b801f`.

**Cập nhật foundation 26/10/2026:** canonical v1.0 đã có code, JSON Schema, fixture và validation; Java xuất JSONL, Rust thu cả Student/Nginx/EVE khi bật dataset. Foundation đã được commit đến `fbe078d` (xem06 mục15); branch AI hiện hành là `feat/ai-model-training`. Phần1 là bằng chứng khảo sát lịch sử tại37bc4d2; phần2 dưới đây là **contract hiện hành đã khóa**. Tại mốc foundation chưa tải public dataset hoặc tạo model; cập nhật AI dưới đây thay thế phần trạng thái đó, không đổi contract v1.0.

## 0. Data pipeline đã triển khai — 27/10/2026

Owner triển khai: Codex, nhánh `feat/ai-model-training`, base `fbe078d`; chưa có review người thứ hai. [`ai-training/README.md`](../ai-training/README.md) là runbook CLI hiện hành; [`schema_contract.yaml`](../ai-training/configs/schema_contract.yaml) ghi đúng field/type/unit từ Java exporter, Nginx, EVE và16cột `normalized_events`, kèm hash source. Canonical v1.0 SHA-256 `7e3d82c5785cb8073737ed444ef58de72288ec89766bc24d554bbba285bfb3c4` **giữ nguyên**; không đổi producer, migration hay config dịch vụ.

| Công đoạn | Hợp đồng đã có code/test |
|---|---|
| Input | Student JSONL; Nginx JSON hiện hành/legacy combined; EVE http/flow/alert; canonical JSONL hoặc PostgreSQL export `{canonical: {...}}`. Chỉ đọc snapshot; từ chối file thay đổi. Không có DB connector ghi/đổi config |
| Units/validation | Nginx `latency_seconds`×1000→ms; EVE `flow.age` giây, byte/packet counters giữ units; uint64 flowID không qua float. Canonical validation strict version/unknown fields, bounded line64KiB, đếm partial/oversize/malformed |
| Privacy | HMAC key AI riêng≥32byte, purpose-separated IP/user/session/request/flow/campaign IDs. Route allowlist/template, UA family allowlist (có alias Edge), loại query secret/PII trước numeric projection; không lưu query/body/header/raw evidence vào Parquet |
| Correlation | RequestID+IP tương thích+≤2s, mỗi nguồn tối đa1observation/request, Student ưu tiên actor. Ambiguous IDs không merge/không áp nhãn; cùng IP/thời gian chỉ context. Flow match qua cùng flowID pseudonym và timestamp≤decision, không dùng future/close counters |
| Ground truth | `label`0/1, `attack_family`8lớp, `label_source`, `label_confidence`, `review_status`. Chỉ scenario_manifest/human_review approved; weak_rule/unmatched giữ unknown và không train. HTTP success/no-alert không phải benign |
| Snapshot | Sanitized SQLite scratch có giới hạn memory, streaming Parquet; immutable manifest/hash/input hash/time range/distributions, verify trước prepare/train/resume. Không đưa scratch/raw/key/model vào Git |
| Split | Temporal60/20/20, connected groups campaign/client/user/session, embargo300s, purge group spanning/boundary; từ chối partition reviewed rỗng, không fallback random |
| Feature/scaler | `ai-features-1`:125features request/flow và cửa sổ10/60/300s IP/user; inclusivecurrent một lần, late-event rejected, LRU/event caps +incomplete flags. Scaler fit benign train-only; order/vocab/impute/clip/float32/hash lưu feature_spec |
| Leakage control | IDs/labels/rule_signals/alert count không là model input mặc định; Suricata alert counts chỉ context10/60/300s. Unknown có thể góp context nhân quả trong partition, không làm training row |
| Inference parity | Python stateful reference dùng fused request row +cùng feature library; golden preprocessing fixture và ONNX parity. Rust port/parity chưa làm |

S0 thật đã chạy trên **fixture synthetic**:3403observations→960request→576/192/192 reviewed splits,125features. **42tests PASS**, ONNX960/960 mỗi nhánh; [report](../ai-training/reports/S0_20261027.json). Dữ liệu thật/giờ train thật vẫn0. Không tải public corpus, không đọc service DB live. Kho artifact chung chưa cấp; file local ignored không tự có trên máy bạn cùng nhóm.

Availability phải đi cùng feature: producer mask query/objectID thì không thể suy lại payload, entropy gốc hay unique studentID. `query_original_*` chỉ được dùng khi producer có counters hợp lệ; lexical còn lại là view đã lọc privacy. API/read/diversity chỉ hỗ trợ triage, chưa chứng minh IDOR/zero-day. Decision timestamp sau response; không tuyên bố chặn request đầu tiên. Các phần đề xuất data-readiness/public-data bên dưới vẫn là gate cần làm trên corpus thật.

## 1. Baseline lịch sử trước foundation: chưa có file audit

Ở snapshot khảo sát37bc4d2 (không phải code foundation hiện tại), trong các file nguồn, cấu hình và log được khảo sát, **không thấy file `audit.log`, cấu hình ghi `audit.log`, parser `audit.log`, hay cầu nối từ audit ứng dụng sang `security-web`**. Điều này chỉ mô tả workspace; không chứng minh máy triển khai bên ngoài không có một file như vậy.

Audit của `student-web` hiện là **bảng PostgreSQL `access_logs`**, được tạo bởi Flyway. Không được giả định file này là Linux auditd, ModSecurity audit log hoặc Suricata EVE: đó là các định dạng khác nhau. Bước tích hợp tiếp theo phải chốt hợp đồng audit ứng dụng; tên `audit.log` trong thiết kế này chỉ dành cho NDJSON của `student-web` nếu nhóm chọn bổ sung file export.

Luồng đang có:

```text
HTTP request → Spring SecurityRequestFilter
             → xử lý authentication / authorization / controller
             → finally: SecurityAuditService.record(...)
             → PostgreSQL student_db.access_logs
             → GET /api/access-logs (chỉ ADMIN)

Nginx combined access.log → Rust ingest → chỉ giữ match regex SQLi
Suricata eve.json         → Rust ingest → chỉ giữ event_type=alert
                                           ↓
                               security_db.security_alerts
```

Các request Nginx không match và EVE `http`/`flow` bình thường bị bỏ qua ở parser hiện tại, vì vậy **không thể lấy riêng `security_alerts` làm tập benign đại diện**. Chưa có dữ liệu train có version hay model trong các nguồn này.

### 1.1. Bằng chứng và ý nghĩa dữ liệu

| Nguồn trong repository | Điều code thực hiện | Giới hạn cho AI/detection |
| --- | --- | --- |
| `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityRequestFilter.java:26–45` | Lấy URI không query; ghi API mutation, response ≥400 hoặc exception; lấy IP bằng `getRemoteAddr()` | GET/HEAD/OPTIONS thành công không được ghi; actor có thể null; không có chuỗi đọc hồ sơ đầy đủ |
| `.../accesslog/service/SecurityAuditService.java:15–25` | Tìm actor đã xác thực; cắt IP 45, method 10, path 500 ký tự; lưu status, action tổng quát, latency | Không lưu username được thử khi login thất bại; không phát hiện được password spraying theo tài khoản từ audit hiện tại |
| `.../accesslog/entity/AccessLog.java:17–46` và `src/main/resources/db/migration/V1__initial_schema.sql:4–16` | Có `id`, `user_id`, `client_ip`, `http_method`, `request_path`, `status_code`, `action`, `user_agent`, `request_time_ms`, `created_at` | Có cột không đồng nghĩa đã thu thập: writer hiện **không set `user_agent`** |
| `.../accesslog/dto/AccessLogSummary.java:5–6` | DTO trả `id,userId,clientIp,method,path,statusCode,action,requestTimeMs,createdAt` | Không có `userAgent`; không có incremental cursor API |
| `.../accesslog/controller/AccessLogController.java:12–25` và `.../configuration/SecurityConfiguration.java:36` | API đọc phân trang/chi tiết, ADMIN; sắp theo `createdAt,id` | Offset pagination không phải giao thức ingest bền vững khi có insert/delete đồng thời |
| `.../configuration/AccessLogRetentionConfiguration.java:18–26` và `.../accesslog/service/AccessLogRetentionService.java:13–20` | Sau 60 giây, mỗi 10 phút xoá bản ghi cũ hơn 3 ngày; 500 dòng/transaction, tối đa 20 batch/đợt | Có thể mất cửa sổ lịch sử cần train/điều tra nếu chưa export bền vững trước retention |
| `.../configuration/SecurityRequestFilter.java:46–54` | DB audit lỗi chỉ ghi category/SQLSTATE vào server log | Chưa có durable fallback hay replay; request nghiệp vụ có thể đã commit nhưng audit không tồn tại |
| `.../accesslog/entity/AccessLog.java:44–46` | `LocalDateTime`, DB `timestamp(6)` không timezone | Chưa thể tự coi timestamp cũ là UTC; phải xác nhận JVM/DB timezone |
| `security-web/nginx/pbl4-proxy.conf:5–13` | Nginx ghi combined; forward X-Real-IP/X-Forwarded-For/X-Forwarded-Proto | Combined chứa target có query, referer, UA nên có nguy cơ PII/token; chưa có request ID xuyên nguồn |
| `security-web/src/main.rs:446–462` | Parser giữ source IP và request target; regex SQLi | Không chuẩn hoá status/bytes/latency/UA thành feature; chỉ URL target, không body POST |
| `security-web/src/ingest.rs:25–70` | EVE chỉ alert; Nginx URL decode một lần, đổi `+` thành space rồi xét regex; lưu nguyên dòng evidence của alert | Evidence có thể chứa dữ liệu nhạy cảm trong URL/header; regex không bao phủ payload body, double encoding hay ngữ nghĩa mọi endpoint |
| `security-web/config/suricata/suricata.yaml:179–201,251–286` | Cấu hình EVE có alert/HTTP/DNS/TLS; HTTP extended; payload/body dump chỉ là dòng comment | Chưa được khẳng định có body payload hay mọi loại flow trên sensor thực tế; Rust hiện bỏ các event không phải alert |

Các đường dẫn viết tắt `.../` trong bảng đầu là `student-web/backend/src/main/java/com/pbl4/studentweb/`.

`student-web/backend/startup.log:38–52` là log khởi động ngày **29/09/2026**, có PostgreSQL `28P01`/password authentication failure; không phải HTTP audit dataset và không chứng minh trạng thái vận hành hiện tại. Các file `backend/docs/data/*.json`, catalog tỉnh/xã và SQL seed là **dữ liệu nghiệp vụ/fixture**, không phải traffic có ground truth. Không chuyển tên, CCCD, email, ngày sinh hay thông tin liên hệ trong đó thành feature nhận diện tấn công.

### 1.2. Tín hiệu hiện có, thiếu và không được suy diễn

- Có thể xây thống kê **mutation/rejection quan sát được** theo IP + path + cửa sổ thời gian; không gọi đó là toàn bộ request rate.
- `REQUEST_REJECTED` chỉ là HTTP status ≥400, gồm nhập sai/CSRF hết hạn/không đủ quyền bình thường. `REQUEST_SUCCEEDED` chỉ là status <400, không chứng minh người dùng hợp lệ hoặc exploit thành công.
- Login lỗi thường không có actor; query và body không được audit. Không thể tái dựng tên tài khoản bị thử hay payload tấn công từ dòng audit hiện tại.
- `user_id` không phải session ID; nhiều thiết bị và phiên có thể cùng một user. IP sau proxy có thể là IP Nginx; IP Internet có thể là NAT dùng chung. Không gán một IP = một người dùng.
- TLS làm sensor thụ động trên chặng mã hoá không thấy URL/body. Chỉ lấy HTTP rõ ở điểm terminate được kiểm soát hoặc telemetry từ ứng dụng; không giả định mọi packet có payload đọc được.
- Path hiện là URI thực, chưa phải template. `/api/students/123` làm tăng cardinality và chứa ID đối tượng; phải chuẩn hoá `/api/students/{studentId}` ở feature pipeline.

## 2. Canonical Event Schema v1.0 — ĐÃ KHÓA TRONG CODE

Nguồn chuẩn: [`contracts/canonical-event-v1.schema.json`](../contracts/canonical-event-v1.schema.json), [`contracts/README.md`](../contracts/README.md), fixture [`student-audit-v1.jsonl`](../contracts/fixtures/student-audit-v1.jsonl). Java `AuditJsonlExporter` và Rust `events::CanonicalEvent` được kiểm theo cùng contract. Các tên `event_time_utc/source_event_id/...` trong đề xuất cũ không phải một schema thứ hai được triển khai.

| Nhóm | Trường v1.0 | Quy ước thực hiện |
|---|---|---|
| Phiên bản/identity | `schema_version,event_id,source,source_instance` | Version chính xác1.0; source=STUDENT_AUDIT/NGINX/SURICATA; eventID và instance ASCII1–128; Student sinh UUID một lần/line |
| Thời gian | `timestamp` | ISO8601UTC có Z; PostgreSQL occurred_at nhận timestamp; observed_at là lúc ingest trong DB, không phải field của producer |
| Correlation/mạng | `request_id,client_ip,peer_ip,dest_ip,src_port,dest_port,transport,flow_id` | RequestID không unique; IP literal/null; port0–65535/null; flowID string để không mất chính xác số lớn; không coi1flow=1request |
| Identity ứng dụng | `user_id,username,role,session_hmac` | Ba identity field nullable HMAC purpose-separated `hmac-sha256:<64hex>`; role ADMIN/STAFF/STUDENT/ANONYMOUS/null; không raw username/session/cookie |
| HTTP | `http_method,uri_path,query_string,status_code,latency_ms,user_agent,request_bytes,response_bytes` | Bounded metadata; custom method→OTHER; UA chỉ giữ product families, unknown text→[REDACTED]; path động/ID được mask; query values đều mask hoặc null; latency_ms không âm; status100–599/null |
| Loại và outcome | `event_type,outcome` | Type=http_request/flow/alert/dns/tls/other; outcome=success/failure/unknown chỉ HTTP outcome, **không là nhãn malicious/benign** |
| Flow | `flow` nullable | duration_seconds, bytes/packets_to_server/client, state; chỉ map khi source có, không tạo flow counters từ audit |
| Cấu trúc query | `query_features` nullable | length/parameter_count/percent_count/quote_count/operator_count khi đọc raw target phù hợp; không tính lại thống kê giả từ query đã mask của Student |
| Quality | `redacted,truncated` | Boolean; trường thiếu dùng null. Missing/OOD/drift vector và ML feature_version chưa được implement, không đánh dấu đã có |

Không chấp nhận raw body/header object, field bất ngờ hoặc version không tương thích. Core fields bắt buộc và network extensions optional được liệt kê chính xác trong JSON Schema. Any addition/type/meaning change phải có version mới và review cả hai luồng; ML feature vector phát triển ngoài canonical contract, không sửa v1.0 theo ý một branch.

### 2.1. Luồng hiện tại và delivery semantics

```text
Student request → trusted attribution / request ID → filter (reads configurable)
   → AuditEvent metadata → DB writer (access_logs) + private JSONL exporter
                                                ↓ STUDENT_AUDIT_LOG_PATH
Nginx structured/legacy combined ─────────→ Rust parser/normalizer
Suricata EVE alert/http/flow/other ────────→ Rust parser/normalizer
   → transaction: cursor + receipts + normalized_events (nếu bật) + alerts + jobs
   → policy/worker (OFF mặc định; TTL/deadline/protected-target checks)
```

DB và file của **producer là hai sink độc lập**, không phải atomic outbox. DB fail không ngăn thử file; file/permission/disk-limit fail được cảnh báo bằng loại lỗi/SQLSTATE, không echo secret. File write synchronized+file lock+force, owner-only directory/file, không theo symlink, mở lại mỗi append để theo rename/create. Giới hạn16KiB/line và64MiB/file; phải rotate và monitor lỗi. Crash giữa business commit và audit/file vẫn có cửa sổ mất telemetry; chưa gọi lossless/exactly-once.

Collector ACK cursor chỉ sau transaction commit. Student receipt dùng `(source,source_instance,event_id)` độc lập inode nên copied JSONL không tạo event trùng trong cửa sổ receipt. Nginx/EVE identity vẫn dựa file/inode/generation/offset/hash: copy sang inode mới có thể thành observation mới. RequestID chỉ để correlation, không xóa hai observation hợp lệ của Nginx và app.

Dòng partial bình thường giữ cursor; dòng vượt cap mặc định64KiB vào persistent discard-until-newline, quarantine theo hash/byte range (không raw secret) rồi tiếp event sau. Truncate/reset anchor tăng generation; rename/create rotation được đọc cùng file chưa nén; `.gz` chưa hỗ trợ. Không xóa/nén file trước khi đọc xong.

### 2.2. Kết nối, privacy và các cờ hiện hành

- Student: `STUDENT_AUDIT_LOG_ENABLED=true`, `STUDENT_AUDIT_LOG_PATH=./logs/student-audit.log`, `AUDIT_INCLUDE_SUCCESSFUL_READS=true` mặc định. Cần `STUDENT_AUDIT_HMAC_KEY` tối thiểu32byte và source instance ổn định; tests tắt file nếu không dùng temp path.
- Privacy producer: cả DB/JSONL Student chỉ nhận UA family từ allowlist browser/client/scanner, không giữ arbitrary prose/version/secret trong header. UA null/empty giữ đúng trạng thái thiếu; dài bị bound và bật truncated. Java/Rust chuẩn hóa custom HTTP method thành OTHER, không lưu lại token method tùy ý. Hợp đồng v1.0 vẫn giữ nguyên kiểu/trường; các report trước thay đổi này là snapshot lịch sử.
- `TRUSTED_PROXIES` nhận exact literal/CIDR. Spring auto-forwarding NONE để giữ peer gốc, custom trusted ForwardedHeaderFilter chỉ dùng địa chỉ đã kiểm tra và strip các header không tin cậy. Nginx sinh lại request ID và overwrite XFF; header giả từ client không quyết định audit/rate-limit identity.
- Security: cùng đường dẫn đã đọc được từ user chạy collector, `COLLECT_ALL_EVENTS=true` để lưu observations. Khi false, parser/rules/auth detector vẫn chạy, dataset rows không ghi và cursor vẫn advance; bật lại không tự backfill đoạn đã bỏ qua.
- Retention normalized mặc định7ngày, cap1.000.000row, sweep mỗi60s; đây không phải hard byte quota. Receipt theo cửa sổ retention, auth observation1ngày. Alerts/errors/quarantine/actions chưa có archive/retention hoàn chỉnh — OPS-04 vẫn mở. Dataset snapshot cần được xuất/version trước khi retention xóa.
- Nginx không lưu raw query, chỉ flag rule tính trong memory; legacy combined và EVE được detector đọc trước redaction khi ingest. Canonical/evidence không sao chép body/token/query value. EVE raw ở sensor vẫn cần kiểm quyền/retention và không bật payload/body dump; chưa có source-level redactor tổng quát cho phần mềm bên thứ ba.
- Không có exporter/shipper SSH/S3 tự động xuyên máy. VM/cloud tách host phải cung cấp secure mounted/shipped JSONL đúng path, giữ eventID/source_instance và file rotation contract; HTTP failover không đồng nghĩa file log tự chuyển sang Security Host.

### 2.3. Feature availability sau foundation

Có metadata HTTP/UA/session HMAC khi nguồn có; có counts/bytes/flow fields từ EVE flow, requestID giữa Student/Nginx. Chưa có body payload được phép lưu, attempted-account HMAC cho login lỗi, target ownership/role đầy đủ trên nguồn Nginx, causal ML window library hoặc incident correlation tổng quát. **Payload Byte-CNN trong03 chưa đủ đầu vào production**; phải có policy dataset riêng để thu synthetic/sanitized payload phù hợp trước khi train. Bảng feature ở phần3 giữ cả kế hoạch và ràng buộc, không phải tất cả feature đã có code.

### 2.4. API quan sát và tab Audit ứng dụng

`GET /api/application-audit` dành cho viewer/admin đã đăng nhập, trả `{items,total,limit,offset,collection}`; `GET /api/application-audit/{id}` trả metadata DB, canonical JSON đã che dữ liệu và tối đa10 quan sát khác cùng `request_id`. Không có API ghi/xóa/chỉnh nhãn ở tab này. API giữ `Cache-Control: no-store`; `/api/audit` tiếp tục là nhật ký thao tác firewall.

Filters: `from` bao gồm và `to` không bao gồm (ISO8601 instant, UI chuyển từ múi giờ trình duyệt sang UTC); `source` thuộc STUDENT_AUDIT/NGINX/SURICATA; `client_ip`, `status_code`, `request_id`, `http_method` khớp chính xác; `uri_path` tìm chuỗi con có phân biệt hoa thường trên đường dẫn đã mask. `limit` mặc định25, tối đa200; `offset`0–1000000. Sắp theo `occurred_at DESC,id DESC`; count/page dùng cùng snapshot trong một SQL statement. Các trang khác nhau là các truy vấn mới, có thể dịch chuyển nếu đồng thời nhận/xóa dữ liệu. Unknown/invalid filters trả400, ID không tồn tại trả404.

List chỉ trả summary. Detail deserialize bằng typed contract v1, validate HMAC/enum/identity và áp lại masking path/query/User-Agent trước khi trả JSON; không trả JSON tùy ý hay body/header object. Row vi phạm contract trả lỗi500 chung, không trả nội dung lỗi chứa dữ liệu thô. Bước hiển thị không sửa canonical/receipts trong DB và không thay schema v1 đã khóa.

`collection` cho biết cờ COLLECT_ALL_EVENTS, retention/cap và trạng thái watcher từng nguồn. Cờ false vẫn đọc được lịch sử; cursor vẫn chạy, nên bật lại không backfill phần đã bỏ. UI mặc định Student audit trong24giờ qua, áp bộ lọc khi submit, tải lại thủ công bằng **Tải lại audit** hoặc **Làm mới** ở header khi đang mở tab Audit; giữ filters/page và hủy request cũ khi tải lại/đổi truy vấn/rời tab. Polling5s ở header chỉ cập nhật các summary cũ, không tự refresh bảng audit. Outcome HTTP không phải nhãn attack/benign; cùng Request ID có thể có nhiều quan sát. Suricata flow thiếu requestID không được ghép chỉ vì trùng IP.

Kiểm chứng: 5 integration tests mới, tổng49 Rust PASS; 3 frontend tests cho timezone/encoding/validation PASS, build/format/clippy PASS và HTTP smoke trên demo3001 PASS. Kiểm tra giao diện bằng browser NOT_RUN do Work settings tắt Local browser use; chi tiết tại ledger06 mục14 và `APPLICATION_AUDIT_VALIDATION.json`.

## 3. Feature catalog và điều kiện sử dụng

Ký hiệu: **A** = audit DB hiện tại; **N** = raw Nginx combined hiện có cấu hình nhưng chưa xác minh runtime; **E** = raw EVE theo cấu hình; **P** = telemetry đề xuất, chưa triển khai. Feature từ N/E phải được collector lưu benign trước; alert DB không thay thế raw source.

| Feature / cửa sổ | Rule cứng | Model AI | Điều kiện và xử lý thiếu |
| --- | --- | --- | --- |
| Method, route template, status class | Method/route trái allowlist, chuỗi 401/403 | One-hot/embedding vocabulary có unknown | A có cho subset request; chuẩn hoá ID route; tránh dùng response-only feature cho quyết định trước request |
| Số login rejection/IP/60s; số 429 | Rule threshold + cooldown | Log-count, ratio theo cửa sổ | A có login; 403 có thể chỉ thiếu CSRF, 429 là limiter phản ứng. Không dùng 429 để chứng minh model nhận ra attack độc lập |
| Unique attempted accounts/IP và IP/account | Password spraying/distributed brute force | Cardinality, burst, entropy theo account | P cần HMAC tài khoản được thử; A không có failed username. Chưa có P thì tắt feature, không điền user null thành một tài khoản |
| Tần suất GET, distinct endpoint/60s, 404 ratio | Endpoint enumeration/rate-limit có context | Burstiness, interarrival CV, route entropy, rarity | A thiếu successful GET; N/P cần coverage đủ; admin mở nhiều tab là hard negative |
| Latency, response bytes, error ratio | Error storm và giới hạn tài nguyên | Log latency, rolling median/MAD, size deviation | A có latency subset; N combined không có request_time; cần N JSON/P cho latency đầy đủ. 5xx do lỗi app không tự là attack |
| User/role/session transitions, login → profile → update → logout | Truy cập role không hợp lệ/reauth cần thiết | 16–64 event sequence, transition surprise, time since auth | P; role không suy từ endpoint; current A chỉ hỗ trợ chuỗi theo user bị khuyết, không session |
| Target ID cardinality, đổi đối tượng liên tục | Enumeration/object access bất thường | Count/distinct theo actor/role | A raw path có ID; thay bằng HMAC và route template; phải phân biệt cán bộ quản lý nhiều hồ sơ hợp lệ |
| Query length, số tham số, `%`/quote/comment ratio, encoding depth | Signature SQLi/XSS/traversal có rule ID và normalization version | Byte/char n-gram hoặc char CNN trên payload view an toàn | N có target, **A không query**. Parse percent encoding bounded (ví dụ tối đa hai vòng), giữ raw/decoded views và cờ malformed; không decode vô hạn |
| POST JSON shape/type/length, tên key ngoài schema | DTO/schema rules, content-type/size limits | Structural vector; payload view ở field được phép | P; không lấy password/OTP/CCCD/name/address/bank/email body. Model chỉ thấy feature structural không thể hứa đọc nội dung đã bị xoá |
| User-agent family, referer category | Bot signals chỉ bổ trợ | UA rarity/change rate | N có combined raw; A có column nhưng writer không set, DTO không trả; UA/referer là dữ liệu attacker kiểm soát |
| Flow duration, packet/byte ratio, flags, ports | Scan/connection thresholds | MLP/anomaly cho flow riêng | E/P nếu event flow được bật và parser lưu. Không giả lập CICFlowMeter 80 feature từ audit HTTP |
| Suricata SID/category/severity | Evidence rule / policy allowlist | Chỉ làm context fusion hoặc weak label | Không dùng SID signature làm feature rồi báo kết quả model độc lập cùng rule; giữ đánh giá rule-free |
| Missingness, source lag, parse failure | Sensor health alert | Missing mask/OOD/abstain | P; dữ liệu thiếu không phải benign, source outage không phải user attack |

**Offline/online parity:** cùng implementation/version chuẩn hoá, thứ tự feature, time window, clipping và missing mask. Fit vocabulary/scaler/threshold chỉ trên train/calibration thích hợp; inference không nhìn sự kiện tương lai. Counter cập nhật trước/sau prediction phải được đặc tả nhất quán. Không đưa IP/user ID/run marker/hash trực tiếp thành feature học thuộc lab.

## 4. Thu thập dữ liệu bên ngoài — ĐỀ XUẤT

Nguồn được kiểm tra trên web ngày 26/10/2026; chưa tải file. Các nguồn sau là nguồn tác giả/đơn vị phát hành, không coi một mirror cộng đồng là ground truth.

| Nguồn chính thức | Vai trò trong project | Điều kiện trước khi dùng |
| --- | --- | --- |
| [CIC-IDS2017 — UNB](https://www.unb.ca/cic/datasets/ids-2017.html) | PCAP và labeled flow CSV cho benchmark nhánh mạng; có benign và nhiều kịch bản attack | Dùng schema feature tương thích sensor; không gộp với audit như cùng một bảng. Download chọn phần cần từ liên kết chính thức; lưu citation/terms, parser, checksum |
| [UNSW-NB15 — UNSW](https://research.unsw.edu.au/projects/unsw-nb15-dataset) | Benchmark flow bổ sung và kiểm tra domain shift | Trang cấp quyền nghiên cứu học thuật, mục đích thương mại cần thoả thuận tác giả. Chưa coi đủ quyền cho sản phẩm doanh nghiệp; bản ghi license phải có trước phát hành |
| [WebRequests — kho dữ liệu nghiên cứu Uruguay, DOI 10.60895/redata/RWUUSV](https://doi.org/10.60895/redata/RWUUSV) | Tập URI và nguồn HTTP được tác giả tập hợp; có CSIC2010, phù hợp khởi đầu payload/URI branch | Repository ghi CC BY 4.0; kiểm tra thêm provenance/terms từng thành phần và bản dữ liệu. Chọn raw URI/HTTP; không lấy TF-IDF toàn corpus đã fit để đánh giá split mới |
| CSIC2010 gốc: `https://www.isi.csic.es/dataset/` | Nguồn HTTP có thể nghiên cứu thêm | Domain gốc không truy cập được qua công cụ trong lượt khảo sát. Không mặc định link download sống/terms rõ; chỉ tiếp nhận qua nguồn có provenance kiểm chứng, nếu không bỏ khỏi baseline |

**Quy tắc domain:** public HTTP dùng để học grammar và stress-test; public flow dùng cho nhánh flow. Chất lượng thực tế của `student-web` phải đo trên traffic riêng. Không gọi public corpus cũ là đại diện 100% cho JSON API, tiếng Việt, session/CSRF hoặc TLS topology hiện tại. Không cam kết bắt zero-day chỉ vì đạt benchmark.

Quy trình tiếp nhận: ghi URL/version/ngày truy cập/terms → tải vào vùng quarantine ở giai đoạn triển khai → SHA-256 → giữ raw read-only → parse bounded/validate schema → audit missing/NaN/Inf/duplicates/label distribution → tách dataset family → split trước fit/augmentation. Dữ liệu/pickle/model bên ngoài là untrusted; không chạy script hoặc deserialise object thực thi từ gói tải về.

## 5. Sinh traffic khớp `student-web` — ĐỀ XUẤT

Không viết/chạy generator trong lượt tài liệu này. Giai đoạn triển khai dùng lab cô lập, tài khoản và hồ sơ giả, database có thể reset, SMTP sink cục bộ. Target allowlist chỉ host/IP lab; reject domain ngoài lab; giới hạn request/concurrency/duration và kill switch. Không cần hạ bảo vệ app hoặc tạo lỗ hổng thật để sinh attack attempt. Tái sử dụng kiến thức từ `security-web/scripts/lab-probes.sh`, không mặc định script hiện có đã tạo dataset có nhãn.

### 5.1. Luồng benign dựa trên endpoint có thật

1. GET `/api/auth/csrf` lấy cookie/token; POST `/api/auth/login` dạng form; refresh CSRF sau login. Giữ cookie jar riêng từng phiên; GET `/api/auth/me`.
2. STUDENT: GET `/api/me/profile`, `/api/me/completion`, `/api/me/academic`, `/api/me/academic/classmates`; PUT profile hợp lệ; CRUD `/api/me/addresses`, `/family-members`, `/emergency-contacts`, `/post-graduation-contacts` bằng dữ liệu giả đúng DTO.
3. STAFF/ADMIN: đọc/phân trang/tìm kiếm `/api/students`; CRUD danh mục `/api/faculties`, `/api/majors`, `/api/training-programs`, `/api/classes`; onboarding qua POST `/api/students`. `CreateStudentRequest` hiện không nhận MSSV: backend tự sinh mã và email trường; generator lấy ID/mã từ response.
4. ADMIN: đọc `/api/access-logs`, quản lý `/api/users` theo quyền. Không tạo hàng loạt ADMIN: code giới hạn tối đa 3 kể cả disabled/chưa kích hoạt.
5. Activation/password dùng fixture giả và mail sink: `/api/auth/activation/verify`, `/activation/send`, `/activate`, `/forgot-password`, `/reset-password`, `/change-password`; lưu token tạm trong runner memory, không trong dataset/log. Không bật gửi email thật để sinh tải.
6. POST `/api/auth/logout`; đổi cookie/session/device; think-time, idle, chuyển vai trò và giờ truy cập thay đổi có kiểm soát. UI static và tải catalog cũng cần benign telemetry proxy.

**Hard negatives bắt buộc:** người dùng gõ sai mật khẩu 1–2 lần rồi đúng; token CSRF hết hạn; login sau reset; lỗi validation phone/email/unknown field; STAFF thao tác batch trong quota; nhiều sinh viên cùng NAT; refresh/multi-tab; tên tiếng Việt và Unicode; query tìm kiếm có dấu nháy; copy/paste ký tự `%`/`_`; request retry khi mạng chậm; 404 asset do cache; 5xx do DB/SMTP lab outage. Không dán nhãn các ca này là malicious chỉ do status code.

### 5.2. Ma trận kịch bản attack attempt

| Family | Kịch bản lab | Ground truth phải ghi |
| --- | --- | --- |
| Brute force / password spraying | Burst login sai một user; nhiều user giả; nhiều IP lab; slow-rate xen benign | Ý định runner, tài khoản giả, thời gian, response; kiểm tra limiter 20/IP/endpoint/phút và forgot 5/phút; thêm guard DB 5 OTP tries/5 sends/hour |
| Enumeration / object access | STUDENT đọc admin route; đổi ID bản ghi con của fixture khác; scan endpoint không tồn tại | Expected 401/403/404 theo code; tách unauthorized attempt khỏi khai thác thành công |
| SQLi/XSS/traversal probes | Tham số URI/body field **được phép dùng trong lab**, encoding/case/comment variants và malformed encoding | Attack intent + payload family + response; test bộ detector, không yêu cầu DB bị inject. JPA binding/React escaping có thể chặn tác hại |
| Schema/validation abuse | JSON unknown keys, type mismatch, length boundaries, content-type lạ, method lạ | Attack intent tách khỏi benign validation sai; parser stage, route, observed effects |
| Workflow abuse | Lặp reset/activation, token reuse, sequence truy cập sai role, mass read qua nhiều target | Không ghi token/PII thật; xác nhận side effect ở DB test và counters trong observer riêng |
| Scan / network anomaly | Scan số port lab giới hạn; connection burst thấp, có duration cap | Sensor vantage/tuple/time; giới hạn để không gây outage; flow events cần được thu trước |
| Resilience | Restart collector, log rotate/truncate/partial line, DB tạm gián đoạn, duplicate replay, disk/queue pressure mô phỏng | Nhãn **pipeline fault**, không gán nhãn tấn công người dùng; expected cursor/duplicate/loss outcome |

Phần lớn probe có thể bị CSRF/rate limit từ chối trước khi vào controller. Để đo payload detection, runner phải có phiên/CSRF hợp lệ trong một nhóm kịch bản riêng, ghi rõ stage reached. Không gộp nhóm thiếu CSRF với nhóm detector đã nhìn payload.

### 5.3. Thiết kế chiến dịch và quy mô

- Pilot: vài nghìn request qua mọi role/endpoint quan trọng, kiểm chứng log coverage và ground truth trước khi mở rộng.
- Dataset ứng dụng đầu: đề xuất **100.000–300.000 request** tích luỹ qua nhiều lượt/ngày mô phỏng; chỉ là ngân sách thu thập, không phải số dòng hiện có hoặc điều kiện đủ chất lượng. Tăng benign/hard-negative coverage trước tăng payload lặp.
- Training có thể lấy mẫu attack để học; tập calibration/test theo stream benign áp đảo và một attack challenge set riêng. Không báo accuracy từ bộ cân bằng như hiệu năng vận hành thực.
- Thay user/session/IP lab, think-time, endpoint order, seed và lịch giữa các campaign; đổi family obfuscation để tạo holdout thật. Không chạy cùng thời điểm thu label và train trên laptop nếu vượt ngân sách tải.
- Marker như `run_id`, `pbl4_run`, scenario name và collector metadata dùng để nối nhãn; **loại khỏi input model**. Không để mọi attack có cùng UA/IP/port/time còn benign dùng giá trị khác.

## 6. Nhãn, split và chống rò rỉ

Mỗi event/window có `label_intent` (`benign`, `malicious_attempt`, `unknown`), `attack_family`, `scenario_id`, `campaign_id`, `generator_seed`, `expected_result`, `observed_result`, `label_source`, `review_status`, `label_version`. `exploit_succeeded` là thuộc tính riêng, chỉ true khi observer lab xác nhận side effect. Một 204 không đủ xác nhận exploit; một 403 không đủ xác nhận attack.

Nhãn từ rule/Suricata là **weak label**, không là ground truth độc lập; giữ phần đánh giá dùng runner manifest và review thủ công. Không huấn luyện và chấm model trên chính nhãn rule mà nó nhận làm feature. Các event không khớp runner/không đủ bằng chứng giữ `unknown`, không tự chuyển benign.

Quy trình split đề xuất:

1. Dedup exact và nhóm near-duplicate theo template/payload gốc trước split. Tất cả biến thể của cùng mẫu giữ trong cùng group.
2. Chia **theo campaign/thời gian**, khởi điểm train 60% / validation-calibration 20% / final test 20%; không chia ngẫu nhiên từng dòng trong cùng session. Tách user/session/seed theo campaign; public dataset giữ partition gốc khi benchmark và báo riêng kết quả.
3. Purge/embargo ít nhất bằng lookback window lớn nhất quanh ranh giới; không để window có request của cả train và test. Dữ liệu tương lai không được dùng để tính counter/quyết định hiện tại.
4. Giữ holdout theo họ payload/obfuscation và một đợt normal mới. Nếu rare class không đủ, báo thiếu dữ liệu thay vì nhân bản vào test.
5. Fit scaler, vocabulary, feature selection, resampling/augmentation trên train; chỉnh threshold ở validation/calibration; khoá test đến lần đánh giá cuối. Muốn đổi sau khi xem test phải version bộ test mới, giữ kết quả cũ.
6. Chấm event-level và incident/session-level riêng; bootstrap confidence interval theo campaign/session để không coi các request tương quan là mẫu độc lập. Báo precision/recall từng family, false alert/10.000 benign và false block/user hoặc NAT, cả latency và source coverage.

## 7. Bảo vệ dữ liệu và provenance

**Chính sách đề xuất:** không lưu password, OTP, activation proof/token, Cookie/JSESSIONID, Authorization/CSRF header, CCCD, tài khoản ngân hàng, hồ sơ sức khoẻ, email/name/address body trong detection dataset. HMAC user/session/target với secret ngoài Git; IP đầy đủ chỉ ở vùng vận hành cần block, tập train dùng role/network category và thống kê thay cho định danh trực tiếp. HMAC vẫn là dữ liệu cần kiểm soát, không tuyên bố đã ẩn danh tuyệt đối.

Khuyến nghị logging tham chiếu [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): ghi ngữ cảnh security phù hợp, loại secrets, kiểm soát quyền/độ toàn vẹn và xử lý input log như dữ liệu không tin cậy. Những lựa chọn dưới đây là thiết kế riêng của project, chưa phải cấu hình đã áp dụng:

- Redaction ở source/collector trước lưu bền vững, test bằng canary secret giả; cấm CR/LF/control-character injection và HTML rendering evidence không escape.
- Route/template và payload view lưu tách biệt; raw evidence hạn chế quyền, mã hoá khi lưu/chuyển, TTL ngắn có chủ sở hữu, không commit PCAP/log/DB dump vào Git. Derived features có TTL riêng đã được nhóm duyệt.
- Khởi điểm lab đề xuất raw 7 ngày, metadata chuẩn hoá 30 ngày, dataset đã lọc 90 ngày; **chưa bật**, cần căn dung lượng/mục đích và chính sách thực tế. Không tự kéo dài retention DB đang 3 ngày hoặc coi retention là nghĩa vụ pháp lý đã xác minh.
- Mọi batch có provenance/checksum/license/redaction version; quarantine sự kiện từ nguồn lạ, parser lỗi hoặc campaign chưa review. Không tự động retrain từ mọi alert để tránh poisoning và feedback loop.
- Snapshot raw/normalized/features bất biến; mọi sửa nhãn tạo version mới. Quyền export/label/release model tách người tạo và người review trong nhóm hai người.

## 8. Layout dataset và manifest — ĐỀ XUẤT, chưa tạo

```text
<data-root ngoài Git>/
  raw/<source>/<capture-id>/            # read-only, access restricted
  normalized/<schema-version>/<snapshot-id>/
  features/<feature-version>/<snapshot-id>/
  labels/<label-version>/
  splits/<split-id>/
  manifests/<dataset-version>.json
  quarantine/<reason>/<capture-id>/
```

Manifest tối thiểu: `dataset_version`, `created_at_utc`, owner/reviewer, source URL/terms/capture topology, source commit, file hashes, source timezones, schema/normalizer/redactor/feature/label versions, event/incident/class counts, missingness/duplicates/coverage report, campaign/group split IDs + hashes, cutoffs/embargo, fit-train-only assertion, known biases, retention/expiry, approval status. Training checkpoint tham chiếu đúng dataset/split/feature hash; đổi dữ liệu không resume âm thầm như cùng một run.

Chỉ lưu metadata/manifest không chứa PII trong `/docs`; dữ liệu lớn và artifact train đặt ngoài Git theo hợp đồng trong tài liệu 03. Không tạo bảng tiến độ giả: đến snapshot này `dataset_version`, số dòng train, hash split và checkpoint đều **chưa có bằng chứng**.

## 9. Tiêu chí sẵn sàng trước training đầu tiên

- Thu được benign GET và mutation/error theo coverage đã công bố; đối chiếu số request runner/proxy/app, giải thích phần lệch, không đánh đồng “không alert” với “đã ingest”.
- Có test fixture NDJSON/DB canonical cho IPv4/IPv6, Unicode, malformed URL, giới hạn độ dài, null actor, DST/timezone offset, rotation/truncation/replay và late event; chấp nhận parse lỗi có metric/quarantine.
- Canary secrets giả không xuất hiện ở raw được phép lưu, normalized data, evidence UI hay feature artifact; kiểm chứng trusted proxy/client attribution bằng request có header giả trong lab.
- Có dataset manifest và split hash; held-out campaign/near-duplicate purge; label `unknown` được giữ; review ít nhất một mẫu mỗi family và hard-negative class.
- Replay cùng capture tạo feature deterministic và decision có version; offline/online parity đạt trước khi benchmark model.
- Ghi giới hạn đã biết: payload/body chưa quan sát thì nhánh payload chưa đủ điều kiện; không quảng bá khả năng phát hiện từ dữ liệu vắng mặt. Chỉ chuyển training stage khi các điều kiện trên có evidence, theo roadmap 04.

## 10. Handoff khảo sát cũ — lịch sử, ưu tiên trạng thái hiện hành ở mục2/06

| Mục | Tiến độ đã xác minh | Việc tiếp theo |
| --- | --- | --- |
| Audit ứng dụng | Có writer DB + API ADMIN + retention, coverage một phần | Chốt canonical event, trusted proxy, GET coverage và durable export |
| `audit.log` ứng dụng | Không tìm thấy producer/file/parser trong workspace | Quyết định DB/outbox hay NDJSON; ghi ADR trước triển khai |
| Benign dataset | Chưa có capture/manifest có nhãn trong repository | Pilot lab với runner + observer tách biệt |
| Public dataset | Đã khảo sát nguồn; chưa tải | Review terms, lấy subset, checksum và feature compatibility |
| Feature pipeline | Chưa triển khai | Chốt v1 + parity fixtures + time/window contract |
| Labels/splits | Chưa có bằng chứng | Campaign manifest, weak-label segregation, split/group hash |
| AI | Chưa có bằng chứng train/checkpoint/metrics | Theo 03; không ghi giờ train tích luỹ trước khi có run ledger |

Các test backend liên quan **đã tồn tại trong code**, chưa chạy lại trong lượt khảo sát: `AuditPersistenceTests` kiểm tra commit audit mutation/login lỗi; `SecurityRequestFilterTests` kiểm tra limiter và metadata không nhận password; `AccessLogRetentionTests` kiểm tra boundary/batch. `StudentApiTests` có CSRF/RBAC/object ownership/activation/password workflows. Các suite Flyway/PostgreSQL transaction chỉ bật khi có `MIGRATION_TEST_URL`; không thể dùng sự hiện diện test để khẳng định mọi yêu cầu data pipeline đã pass.
