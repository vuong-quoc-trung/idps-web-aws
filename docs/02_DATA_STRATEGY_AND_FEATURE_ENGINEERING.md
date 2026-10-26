# 02 — Chiến lược dữ liệu và Feature Engineering

Ngày khảo sát: **26/10/2026** (Asia/Ho_Chi_Minh). Baseline code: `37bc4d2ae1552939659a10647898e2228f1b801f`.

**Trạng thái:** khảo sát tĩnh và thiết kế đề xuất. Chưa tải dataset, sinh traffic, xuất dữ liệu DB hay huấn luyện model trong phiên này. Schema, pipeline và kịch bản có nhãn **ĐỀ XUẤT** dưới đây chưa được triển khai. Đọc cùng [01 — Audit và kiến trúc](01_SYSTEM_AUDIT_AND_ARCHITECTURE.md) và [03 — Model và training](03_AI_MODEL_AND_TRAINING_PLAN.md).

## 1. Kết luận từ code: `audit.log` chưa phải nguồn đang tồn tại

Trong các file nguồn, cấu hình và log dự án được khảo sát, **không thấy file `audit.log`, cấu hình ghi `audit.log`, parser `audit.log`, hay cầu nối từ audit ứng dụng sang `security-web`**. Điều này chỉ mô tả workspace; không chứng minh máy triển khai bên ngoài không có một file như vậy.

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

## 2. Hợp đồng sự kiện chuẩn — ĐỀ XUẤT v1

Chốt một schema chung trước khi viết parser/model. Giữ **event thô có kiểm soát**, **event chuẩn hoá**, **feature** và **decision** thành các lớp có version riêng. Không ghi đè dữ liệu nguồn bằng điểm AI hay nhãn suy luận.

| Nhóm | Trường đề xuất | Mapping từ nguồn đang có / phần cần bổ sung |
| --- | --- | --- |
| Định danh | `schema_version,event_id,source,source_instance,source_event_id,source_cursor,producer_version` | DB audit có `id`; cần thêm instance/epoch để không trùng khi restore. `source_event_id` là identity gốc ổn định, `source_cursor` là vị trí đọc/ACK. File có dev/inode/generation/offset trong ingest hiện tại; cần host/sensor namespace nếu nhiều máy |
| Thời gian | `event_time_utc,observed_at_utc,source_timezone,clock_skew_ms` | Nginx/EVE có offset; audit DB cần timezone nguồn xác nhận. Giữ raw timestamp phục vụ kiểm toán |
| Correlation | `request_id,trace_id,flow_id,session_hmac,actor_hmac,attempted_subject_hmac` | **Chưa có** trong audit hiện tại ngoài user ID. Request ID do proxy tin cậy sinh/ghi đè; session/actor HMAC do app sinh, không lưu token/cookie thật |
| Nguồn mạng | `src_ip,src_ip_provenance,peer_ip,dest_ip,src_port,dest_port,transport,service` | Có IP cơ bản; thiếu port/destination audit. Ghi rõ `peer` hay `trusted_proxy`; không tin header do client tự gửi |
| HTTP | `method,route_template,status,duration_ms,request_bytes,response_bytes,content_type,query_keys` | Method/path/status/duration đã có audit; những trường còn lại cần instrumentation/proxy JSON. Query keys cũng qua giới hạn/allowlist |
| Payload an toàn | `payload_observed,payload_redacted,payload_truncated,payload_length,encoding_depth,char_statistics,payload_view_ref` | **Chưa có** từ audit. Chỉ ghi mẫu đã lọc tại endpoint/trường được phép; auth/identity/profile bí mật không ghi body |
| Ngữ cảnh | `auth_state,role_class,operation,target_type,target_hmac,outcome_reason` | Cần thêm app telemetry; không join toàn bộ hồ sơ sinh viên vào IDPS. Role/outcome không tự suy từ status |
| Chất lượng và vận chuyển | `missing_fields,parse_error,normalizer_version,redaction_version,trusted_source,late_event,raw_ref,replay` | Cần thêm; không điền 0 cho dữ liệu không quan sát được. `raw_ref` trỏ evidence đã kiểm soát quyền; `replay` phân biệt lịch sử với live và không cho phép enforcement hồi tố |
| Detection riêng | `rule_ids,rule_version,model_version,feature_version,scores,decision,policy_version,evidence_refs` | Cần bảng/event quyết định riêng; không dùng làm input của model cùng nhãn khi đánh giá độc lập |

Ví dụ **minh hoạ schema đề xuất**, không phải bản ghi thật:

```json
{
  "schema_version": "1.0",
  "event_id": "student-lab:epoch-01:access-logs:42",
  "source": "student_audit_db",
  "event_time_utc": "2026-10-26T02:00:00Z",
  "source_timezone": "Asia/Ho_Chi_Minh",
  "src_ip": "192.0.2.25",
  "src_ip_provenance": "peer_unverified",
  "method": "POST",
  "route_template": "/api/auth/login",
  "status": 401,
  "duration_ms": 115,
  "actor_hmac": null,
  "session_hmac": null,
  "payload_observed": false,
  "missing_fields": ["request_id", "session_hmac", "attempted_subject_hmac"]
}
```

### 2.1. Chọn cách thu audit, không tạo thêm nguồn mất dữ liệu

**Ưu tiên triển khai nhỏ:** exporter dùng DB role chỉ đọc `access_logs`, chuẩn hoá metadata ra durable inbox của security DB; lưu cursor độc lập và acknowledge sau persist. Không dùng tài khoản ADMIN browser để poll. Bổ sung source event identity + bounded lookback/dedup; không đơn giản `WHERE id > last_id` vì sequence cấp ID không bảo đảm commit theo ID. Lookback phải có giới hạn trễ được đo; nếu không chứng minh được giới hạn, dùng outbox transactional hoặc CDC theo commit position. Retention chỉ xoá sau khi downstream đã giữ bản sao theo chính sách.

**Đích bền vững:** outbox ghi cùng transaction cho security business event, collector đọc và retry/ack; telemetry request độc lập có local spool, bounded queue và counters mất dữ liệu. Nếu chọn `audit.log`, NDJSON phải UTF-8, một JSON/event, không multiline; atomic flush, rotation rename + create, quyền tối thiểu, collector checkpoint/ack, giới hạn dòng, parser lỗi vào quarantine, không âm thầm skip. Không ghi DB và file theo hai lệnh rời rồi tuyên bố exactly-once.

Các GET thành công cần đưa vào telemetry với chính sách lưu đủ metadata để tạo behavioral baseline. Nếu phải sampling, ghi sampling rate và event class; auth/security failure không sampling. Giữ thống kê count đầy đủ tại source khi sampling chi tiết, nếu không không được dùng rate bị sampling để auto-block.

### 2.2. Time, join và chống trùng

- Dùng UTC ở hợp đồng mới, đồng bộ đồng hồ; không sửa timezone các dòng cũ bằng cách nối `Z`.
- Ưu tiên request ID xuyên Nginx → app → collector. EVE có thể dùng flow/transaction ID, tuple và timestamp; HTTP keep-alive tạo nhiều request trong một flow nên không join 1 flow = 1 request.
- Trước khi có request ID, correlation theo IP/route/time chỉ là **ước lượng có confidence**, không tự hợp nhất thành ground truth. Bảo toàn source event ID và evidence độc lập.
- Cửa sổ đề xuất 10 giây, 60 giây, 5 phút; allowed lateness khởi điểm 30 giây rồi đo. TTL state ≥ max window + lateness. Late event quá watermark vẫn lưu nhưng không tạo quyết định IPS hồi tố.
- Dùng deterministic dedup theo source event identity; surrogate event hash nội dung không được xoá hai request hợp lệ giống hệt nhau ở thời điểm khác nhau.

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

## 10. Handoff dữ liệu tại baseline này

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
