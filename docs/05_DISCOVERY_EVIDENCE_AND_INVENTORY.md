# 05 — Bằng chứng khảo sát, phạm vi và giới hạn xác minh

## Development oracle pilot có capture thật — 2026-11-02T11:09+07:00

Private root `ai-training/.artifacts/devgt1/`: `plan/plan.json` SHA nội dung `08361b0f05836e4e774b2050f96e3575a09d8803ecc942d9b10fb5a5e3e61936`; `run/lab/traffic.pcap`, `run/eve/eve.json`, `run/correlated/`, `run/capture/`, `run/application-oracle-before.json`, `run/application-oracle.json`, `run/cleanup-verification.json`, `run/oracle-verification/report.json` và `run/review/`. Oracle report SHA nội dung `973faa9afc23e2333d1f8444e5b56e6a0813d83c55084f11aa7b71be0c46db28`: 8 request vật lý/8 ba nguồn/8 response, 2 POST body byte match, DB 0→1 cho một mutation STAFF, cleanup PASS, 8 unknown/0 admission. `lineage-audit/report.json`: 170 distinct IDs, 79 target hashes, 91 repeated-target observations, 0 collision trong bốn capture pending; `lineage-audit-all-unsealed/report.json` thêm v1 cách ly thành 218 IDs/79 target hashes/139 lượt lặp, 0 collision. Historical sealed không đọc. PCAP/credential/DB evidence chỉ local, Git ignored. Signed plan-v3 ở mục dưới **vẫn chưa chạy**; báo cáo cũ về 0 request chỉ nói về signed pilot đó.

## Gói phê duyệt và cleanup pilot — 2026-11-02

Gói private `ai-training/.artifacts/ground_truth_pilot_20261102/APPROVAL_PACKAGE.md` mode 0600 có case/URI, phạm vi, rủi ro, SHA và lệnh ký; chỉ reviewer thật tạo private key/approval. Plan-v3 vẫn active, chưa có `approval-v3.json`, public key, PCAP/EVE/oracle của pilot. `verify_lab_cleanup` đã PASS trên hai lab EVE cũ: Docker disposable không còn, ports 18880/18881/55435 đóng; không biến capture cũ thành dữ liệu Ground Truth mới. Machine report/handoff và ledger 06 mục 42 ghi trạng thái kỹ thuật; **0 new requests/labels/admission**.

## Pilot Ground Truth chưa capture — 2026-11-02

Plan private active `ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3/plan.json` pin 8 case, SHA nội dung `a38ecc02822e9a2618dcfaa442d00492ae4ce438efc5f6bdd73c3866a5129eb2`, file SHA `4a61049c9a8a6bf05345f203ef95d392c8f2ffd54b23366ba37b12b078d7f9e4`, collector SHA `30c5eee796b6a6544eebabb7268f24a135614efa5d5d9b6905cad9e8c367174e`. `plan-v1`/`plan-v2` là bản soạn superseded, chưa ký/chạy. Không có approval, PCAP/EVE, application-oracle artifact **thật** từ pilot; test fixture key/oracle không được tính. Nguồn hiện tại vẫn 162 pending UNKNOWN và 0 admission. Thông tin ở [PRETRAINING](../ai-training/PRETRAINING.md), ledger 06 mục 41.

## Blind review artifact — 2026-11-02

`ai-training/.artifacts/evidence_campaign_20261102/auto-review-v3/auto-review.sqlite` là DB private 0600 với 162 request-bound records, 0 plaintext query/credential; `report.json` pin SHA DB và method source. Lượt 65→162→162 xác nhận batch/resume/idempotence; test còn giả lập report chưa kịp ghi sau commit và khôi phục bằng `--recover` với full record readback. `auto-review-v3-unblind/` chứa comparison JSONL riêng, chỉ tạo sau blind complete; 162 claim được so, 7 benign-claim có cue và 22 attack-claim không có cue. Không có oracle/application side-effect hoặc semantic human review, do đó comparison **không cấp nhãn**. V1/V2 là các lượt thử kỹ thuật, giữ private làm bằng chứng; active là v3. SHA chi tiết trong [machine report](../ai-training/reports/ATTACK_EVIDENCE_20261101.json), ledger 06 mục 40.

## Review registry và POST PCAP readback — 2026-11-02

Private registry `ai-training/.artifacts/evidence_campaign_20261102/review-registry.json` pin ba queue 54 hồ sơ; SHA nội dung `28b6d001387679aece34f9be856d8fd343a8bd37f298815e0fcf2728672bdac0`. Hai artifact `eve3-1102b/body-evidence-v1/` và `eve3-1102c/body-evidence-v1/` kiểm lại PCAP gốc, response `X-Request-Id`, method/status/source IP/target hash: mỗi capture 54/54 request, 6 POST body thật. Ledger HMAC/field names 0600, khóa 0600 và PCAP private; không đưa giá trị credential vào report. Không có body tương ứng cho 6 POST của capture hai nguồn cũ. Human review decision artifacts hiện chưa tồn tại, 0 nhãn được xác minh/0 admission; HMAC không chứng nhận semantic intent. Xem [PRETRAINING](../ai-training/PRETRAINING.md) và ledger 06 mục 39.

## Bằng chứng capture và review mới — 2026-11-02T08:54+07:00

Private `ai-training/.artifacts/eve3-1102c/` có plan `evidence_campaign_20261102/plan-novel-v2`, frozen `collector-source-v4.py`, PCAP gốc, EVE đã redaction, `correlated-v3/`, `review/` và `assist-v2/`. Lượt mới 54 request/54 EVE HTTP/54 flow/18 alert; masked Nginx query null và EVE v2 numeric khớp 54/54. PCAP SHA `80efea9c0803722a28df75705b18b76feffb63002c75888aefea80641f27309e`; EVE SHA `0cb5fd45b0fa1b3e846a3d40b51815690db9aa4a37cde173a1f8aa015aa6784a`. `evidence_campaign_20261102/lineage-unsealed-v5/report.json` quét bốn captures và bảy Student logs chưa sealed: 210 IDs mới, 227.619 lịch sử được quét, 0 collision, 78 target hashes. Không mở sealed holdout. Facts/proposals của 54 cũ hai nguồn và 54 cũ ba nguồn nằm trong `assist-old54-v2/` và `assist-new54-v2/`; mọi label vẫn null, không có reviewer attestation. Raw/PCAP/credential chỉ local, Git ignored; SHA chi tiết trong [machine report](../ai-training/reports/ATTACK_EVIDENCE_20261101.json).

## Bằng chứng ba nguồn AI-owned — 2026-11-02T08:31+07:00

Private artifacts: `ai-training/.artifacts/eve3-1102b/` chứa `lab/traffic.pcap`, `eve/eve.json`, `correlated-v2/three-source-evidence.jsonl`, `review-three-source-v2/blind-review.jsonl`; plan/frozen collector ở `.artifacts/evidence_campaign_20261102/plan-v1` và `collector-source-v3.py`. PCAP SHA `b9c4d623fb12c8c513cdaaa729c03466d9c135187caf737e8d41acd6c535a384`, EVE SHA `c36937f2fe3b1957d2a22614cc36dd38732b0ea57aecf949a8f1cac109da5e1a`, correlation ledger SHA `6521b8728410ca095d0088ff2e7bfed0a04d7bc3b7a36d03e88b906031dfc76d`; report JSON pin toàn bộ SHA. 54/54 three-source match; 54 flow/18 alert/1 stats; queue có 54 unknown/0 admitted. `lineage-audit-v3/report.json` ở root evidence 20261102 đối chiếu 156 ID qua ba capture và 73.218 ID lịch sử chưa sealed, không chứng nhận dedup toàn cục. Raw private không đưa vào Git.

## Bằng chứng capture lab mới — 2026-11-01T11:21+07:00

Private root `ai-training/.artifacts/evidence_campaign_20261101`: `plan-v2/plan.json` SHA file `82d37a82e5fc3296d304d792ca8aef454e980893fa70bb118464bbedba3660bb`; `capture-v2/report.json` SHA `3e79796c29ad3375e13dedc33ea7f0c2f99fc8a54bccd8a480f8c85d934b030b`; `review-v3/blind-review.jsonl` SHA `85c433dc4bcdf90bcbd9a0d01091a41fa3a50804d9d5eb1d880fde652e4dbf3d`. V1 48 request/45 auth 401 và source collector snapshot giữ lại để chứng minh quyết định cách ly; v2 54 request được reverify từ hai log. Review queue không có nhãn được duyệt, payload hoặc PII. `plan-v2` chỉ dùng development; future holdout chưa phát/request/score. Nginx/Student/DB fixture đã dừng.

## Kiểm tra tiếp nguồn và hồ sơ review — 2026-11-01T10:53+07:00

- SOC-MLD: `soc-pending-review-final-v2/report.json` và `pending-dossiers.jsonl` trong artifact root private; 64/64 locator/SHA raw khớp, 0 nhãn được duyệt. Mọi dossier giữ campaign/intent/outcome `unknown`, ghi riêng mức tin cậy; không xuất payload, IP, URI, query, UA. 38 attack-instance IDs chung train/test chứa 3.066 rows, trong đó 1.214/1.220 test rows.
- ModSec-WP [Zenodo DOI](https://zenodo.org/records/21872151): API chính thức CC BY 4.0, workbook MD5 `6d02547829e0b460ef6473d5603a84db`, SHA256 `f959c79e185502b03206f6fdeb29306a65571394c2f009dda503d43ba306d16d`. Local private `modsec-wp-audit-final/report.json`: 108.883 rows, 27.686 transaction IDs/event keys, 81.197 repeated rows, 20 transaction IDs mâu thuẫn nhãn. 60 rows có timestamp năm 2026, còn 108.823 năm 2024. Không có campaign ID và per-row label-basis trail; chưa admission.
- [Polish e-commerce logs](https://zenodo.org/records/18895701): CC BY 4.0, publisher 178.939 anonymized access rows từ môi trường e-commerce thật. Có ích cho observability, nhưng không có nhãn intent từng request và query đã bị bỏ; metadata-only, không download/admit.

## Nguồn và bằng chứng mới — 2026-11-01T07:36:28.147641+07:00

Root private: `ai-training/.artifacts/attack_evidence_20261101`. Giữ snapshot source/docs và protected SHA từ đầu lượt; report máy [ATTACK_EVIDENCE_20261101.json](../ai-training/reports/ATTACK_EVIDENCE_20261101.json)/ledger 32 trỏ evidence thực, không ghi payload hoặc PII vào report.

- SOC-MLD Zenodo DOI10.5281/zenodo.23116148: CC BY 4.0 trong official metadata và LICENSE; ZIP10.430.367 bytes, MD5`764ca570a35753a90f6ac3046750c716`, SHA256`66aafa96a69ab54ee061abbb69284444476919295f1b16985122283dae2b3054`. Member hashes, SQLite index và report ở `soc-audit-v2/`; không execute publisher code. Attempt đầu chỉ hiểu combined log, đọc thiếu common-log rows; giữ kết quả superseded và sửa parser, active v2 tính đủ198.082 HTTP observations.
- SOC-MLD metadata/card và source khác nhau về split/counts. Code evidence: `extract_features.py` dòng708 time consume,711 payload fallback,442 NORMAL fallback,266 future window,749 signature label. 38 attack-instance IDs chung giữa CSV train/test; không nhận claim independent split tự động.
- WAMM revision`2783eab560c4355f5976a57fc2e97a2e6c5c79a1`: README thừa nhận SR-BH derivative, Burp augmentation, regex/LLM filtering; không tải archive hay coi là nguồn độc lập mới.
- WAF Data v2 revision`b035dc17f875f1f732c10654709abed66a4e9742`: MIT claim, card không cung cấp capture/label lineage; SR-BH resemblance chỉ là nghi vấn cần kiểm, không kết luận đã chứng minh duplicate. Không tải data.
- Biblio-US17 DOI10.12795/11441/148254: official idUS metadata ghi CC BY-NC-ND4.0, khác CC BY của bài báo. Cần kiểm compatibility và label-scope trước tích hợp; chưa tải data, không phát biểu toàn bộ dùng được chỉ vì paper open access.
- ModSec-WP DOI10.5281/zenodo.21872151: official CC BY4.0, 108.883 publisher transactions, mixed scenario/time/regex/manual annotation; chưa có request-bound evidence chain được xác minh, chỉ lưu metadata.

Các nguồn chưa admission đóng góp0 vào mục tiêu formal. Không mở WCP148 hoặc các holdout cũ. Dataset identities/observations/modelviews không được tự coi là physical requests. Các công cụ mới chỉ đọc offline, không có traffic đến website gốc.

Kiểm chứng cuối: **211 pytest PASS, 0 skip**; Ruff/format/compile/canonical PASS; **53/53 gate kỹ thuật legacy PASS**, corpus formal **NOT_READY/0 eligible** (exit 3 đúng thiết kế). Giữ nguyên SHA của **2.941 file** cũ và source/config freeze trong final test; không sửa hai Web. Handoff format 10, ledger 32.

## Bằng chứng nguồn mới và frozen evaluation — 2026-11-01T06:48:58.523006+07:00

Root private `ai-training/.artifacts/generalization_quality_20261101/`; [report hiện hành](../ai-training/reports/GENERALIZATION_QUALITY_20261101.json), handoff format 9, ledger 06 mục 31. Các report/checkpoint/source/holdout cũ giữ nguyên SHA.

- **PASS:** 198 pytest/0 skip/102,03 s; Ruff/format/compile/canonical/originalWeb diff. 53/53 legacy technical readiness trên 69.345 fused-v5, không phải admission mới.
- **PASS dữ liệu:** 811.129 row decisions và 756.548 unique-signature observations readback; 44.437 encoded keys kiểm lại; case groups disjoint. 190 quarantine và 54.391 duplicate có trace; 148 file reserved chưa mở, số request unknown.
- **PASS frozen stress:** 13.290 validation/160 case, weights/ngưỡng nguyên; GLU 5 FP, MLP 174 FP. 200 replicate case bootstrap, macro-case và syntax subset báo riêng. Benign-only không xác định recall/PR-AUC hoặc chọn champion.
- **NOT_READY:** independent reviewed labels, positive đa môi trường, prospective/campaign acceptance, formal scale và production quality. Organization X vẫn unknown, 0 relabel. Partial numeric overlap không tự thành rawHTTP duplicate hoặc lý do xóa lỗi validation.
- **PASS tài nguyên:** data unit 482,698 s wall/423,5M memory peak; eval 6,773 s/453,3M; quota 4 CPU/16 GiB/high 15 GiB/swap 0. Đây là data/eval jobs, không train 2 h. Sensor samples tối đa 66 °C ở importer, không thermal trip; long endurance NOT_RUN.
- **PASS bảo toàn:** 2.682 file bảo vệ, Web/contracts/Docker diff 0, HEAD nguyên. Chỉ dọn 838.709 byte/71 file cache tái tạo được; giữ raw ZIP/key/SQLite/ledgers/failed attempt/checkpoint/report. Các unit riêng đã dừng, không dừng service khác.

Attempt đầu download bị budget/time guard dừng được resume Content-Range/If-Match và full SHA verified. Import đầu dừng ở object quá lớn, không có manifest hợp lệ/admission; giữ attempt, thêm bounded structural skip+quarantine và regression trước khi complete v2. Không tăng accepted-object cap. Một test fixture ban đầu sai source/warmup đã sửa ở fixture, không nới trainer guards; final suite PASS.

Raw/private key không ở Git; artifact vẫn local, chưa shared store. Số record nguồn/labels/metrics có scope rõ trong report, không tuyên bố 2M, review độc lập hoặc production readiness.

## Cập nhật resource sau pilot — 28/10/2026

Ca tiếp theo dùng **8logicalCPU/16GiB RAM**, CPUQuota800%, MemoryHigh15GiB,
swap0,Nice10; BLAS/OpenMP8,ONNX intra8/inter1 sequential. CPU là50% của16luồng;
16GiB là**52,96% RAM OS-visible** trên máy32GB danh nghĩa, được user chỉ định rõ.
77testsPASS,35readinesschecksPASS, guardprobe0optimizerstep; **không train chính thức
hoặc chạy lại pilot corpus thật**. [Báo cáo resource](../ai-training/reports/RESOURCE_GUARD_20261028.json).

Dataset prepared và pilot-ready giữ nguyên hash; readiness-final cũ cũng được giữ.
Readiness mới`readiness-resource8` gắn source hiện hành và được handoff/script sử dụng.
Các metric/giới hạn2CPU/12GiB ở các snapshot pilot phía dưới là lịch sử. Các attempt
fail/stale/cache/NEXT_COMMANDS cũ đã dọn; giữ raw capture evidence, runtime và venv
cần thiết. Xem ledger06 mục21 cho kiểm tra, danh sách dọn và commit.

**Snapshot khảo sát lịch sử (không phải hash code foundation):** 26/10/2026, Asia/Ho_Chi_Minh. **Git HEAD được khảo sát:** `37bc4d2ae1552939659a10647898e2228f1b801f`. Worktree ban đầu sạch. Bản ghi này mô tả cách có được kết luận trong 00–04; không thay thế kết quả kiểm thử runtime.

## 1. Phạm vi thực sự đã kiểm kê

`git ls-files` tại baseline có **524 tệp**: **340 tệp thuộc dự án/deliverables** và **184 tệp công cụ `.agents/`**. Phần dự án gồm 288 tệp `student-web`, 43 tệp `security-web`, 9 tệp root/CI/docker/deliverables. Source/config/test/docs được đọc theo module và đối chiếu xuyên service; tài nguyên phụ trợ được phân loại theo vai trò thay vì giả vờ mọi byte là logic IDPS.

| Loại khảo sát trong manifest | Số tệp | Phạm vi |
|---|---:|---|
| Source, config, test, tài liệu văn bản | 322 | Backend Java/Rust, frontend TS/React/CSS, SQL, shell/Python vận hành, manifests, README/CI và log artifact |
| Dependency inventory | 3 | Hai package-lock và Cargo.lock; đối chiếu phiên bản, không đọc thuật toán của từng thư viện bên thứ ba |
| Business data schema review | 7 | Sáu JSON seed/danh mục nghiệp vụ và JSON địa giới; đọc cấu trúc/nguồn/quan hệ, không sao chép PII vào docs |
| Document text review | 2 | Hai DOCX Ubuntu host: trích nội dung để đối chiếu hướng dẫn và code, không chỉnh DOCX |
| Asset inventory | 6 | Logo/hero/SVG; nhận diện vai trò và metadata, không coi là dữ liệu ML |
| Agent tooling inventory only | 184 | Skill scripts/CSV/reference design; không thuộc runtime IDPS và không bị nhầm thành dataset/trainer |
| **Tổng** | **524** | Snapshot tracked files trước khi tạo docs |

Manifest tại [05A_SOURCE_MANIFEST.tsv](05A_SOURCE_MANIFEST.tsv) có đường dẫn, scope, loại review, byte size và SHA-256 của mọi tệp tracked ở baseline. Manifest không chứa mật khẩu hay nội dung hồ sơ. Hash phục vụ phát hiện drift, không chứng minh chức năng đúng hoặc an toàn.

Đã liệt kê cấu trúc thư mục và tìm các patterns model/training/log/TODO trên source. Không coi thư viện cài đặt, Git object database, build artifacts/caches, `.agents` dataset thiết kế và bí mật local là mã chức năng cần đưa vào bản đồ kiến trúc. Những file ignored/local có thể khác giữa hai máy; không lấy việc không có trong Git để khẳng định không tồn tại ngoài repo. Không đọc/công bố giá trị `.env` cá nhân.

## 2. Các hướng khảo sát độc lập đã đối chiếu

| Hướng | Đã đọc và đối chiếu | Kết luận quan trọng |
|---|---|---|
| Student backend | 158 tệp Java trong repo, module controller/service/entity/DTO/mapper/repository, Security filters, config, SQL, test, docs/data/startup artifact | Audit ở DB; app có auth/CRUD thực; thiếu telemetry cho hành vi đầy đủ |
| Security core | Toàn bộ module Rust, SQL/migrations, parser/policy/firewall/auth/metrics, tests, rule và config/script vận hành | Durable cursor/jobs đã có; chưa AI/audit connector/TTL/freshness/global enforcement stop |
| Frontend và hạ tầng | Hai frontend source/config, routes/API/state, CI, hai Compose, topology/proxy/systemd, docs và hai DOCX | API thật; polling/stale và contract TLS/ports cần hoàn thiện; AWS chưa có implementation |
| Thiết kế dữ liệu/ML | Dựa trên fields thật, blind spots, nguồn public primary, tài liệu checkpoint/resource/export chính thức | CPU-first candidate, data parity trước training; 60–80h là ngân sách điều kiện |

Các tài liệu phụ thuộc quan trọng đã đối chiếu gồm `student-web/backend/docs/API.md`, `SECURITY_REVIEW.md`, `DATABASE_MIGRATIONS.md`, các hướng dẫn activation/password/profile/catalog và SQL 001–019; `security-web/README.md`, `HOST_SECURITY_SETUP.md`, `LAB_ACCEPTANCE.md`, `DETECTION_PROBES.md`. Một số hướng dẫn cũ mâu thuẫn code: đã ghi cụ thể trong 01/02, không âm thầm sửa các file đó ở phiên docs-only.

Không phát hiện TODO/FIXME là bằng chứng chính cho phần AI dở dang: **AI chưa có module thực**, thay vì có trainer mock đang chạy. Placeholder content như footer mẫu hoặc systemd template chưa render được phân biệt với backend mock. Tên `trainingprogram` là chương trình đào tạo sinh viên.

## 3. Bản đồ bằng chứng nên kiểm lại đầu tiên

| Khẳng định | Bằng chứng tại baseline | Mức xác minh |
|---|---|---|
| Audit student là DB, không phải audit.log | `SecurityRequestFilter.java:42`, `SecurityAuditService.java:15`, `AccessLog.java:17` | Đọc code + kiểm kê config/log; môi trường ngoài repo chưa biết |
| Không audit successful reads | `SecurityRequestFilter.java:28,42` | Logic filter đọc tĩnh |
| Không set user-agent/session/query/body | `SecurityAuditService.java:16–25` | Fields writer; không suy từ entity column |
| Retention >3 ngày và batch | `AccessLogRetentionService.java:13`, `AccessLogRetentionConfiguration.java:18` | Đọc code/config, chưa chạy scheduler |
| Rust chỉ đăng ký Nginx và Suricata | `security-web/src/main.rs:228–244` | Đọc entry point |
| EVE non-alert và Nginx non-SQLi bị bỏ | `security-web/src/ingest.rs:28,51` | Đọc parser và tests source |
| Alert/job/cursor cùng transaction | `security-web/src/ingest.rs:174–255` | Đọc code + integration test source |
| AUTO_BLOCK=false chưa tắt worker | `security-web/src/main.rs:246`, `security-web/src/firewall.rs:166–190` | Đọc call graph, không thực thi helper |
| Không TTL và freshness check | `migrations/0001_initial.sql`, `scripts/pbl4.nft`, `ingest.rs:235–240` | Đọc schema/helper/decision; không suy hiệu ứng kernel thật |
| Port scan rule thực là SYN burst threshold | `security-web/suricata/pbl4.rules:7` | Đọc semantics threshold; FP cần đo |
| Prod TLS/upstream cần chốt | `student-web/backend/src/main/resources/application-prod.yaml:1`, `security-web/nginx/pbl4-proxy.conf:8` | Gap giữa config, chưa tái hiện lỗi deployment |
| Hai Compose port5433 nếu co-host | `docker/docker-compose.yml:14`, `security-web/docker-compose.yml:11` | Config conflict có điều kiện, không kết luận hai DB đang cùng máy |
| Source tests có sẵn | 13 lớp test Java/79 `@Test`, unit/integration Rust | Đếm source, **không phải số test PASS** |
| Không có trainer/model được đăng ký | Inventory source/manifests/deps và tìm artifact theo extension | Không bao phủ ổ đĩa/cloud/laptop khác |

Các đường dẫn Java rút gọn trong bảng này nằm dưới `student-web/backend/src/main/java/com/pbl4/studentweb/`, test dưới `src/test/java/`. Nguồn link/code đầy đủ và phân tích hệ quả nằm ở 01/02.

## 4. Những xác minh chưa thực hiện

| Loại | Trạng thái | Lý do / cách làm tiếp |
|---|---|---|
| Maven/Rust unit+integration tests | NOT_RUN | Phiên giới hạn tài liệu, không tạo target/artifact hoặc DB test; R01 sẽ chạy trên DB disposable |
| Frontend lint/typecheck/build/`.mjs` tests | NOT_RUN | Không install/build; CI config được đọc không chứng minh run PASS |
| Browser E2E/session/CSRF reproduction | NOT_RUN | APP-01 và các rủi ro UI giữ nhãn cần tái hiện |
| Suricata syntax/rule load/capture | NOT_RUN | Không gọi service/capture; manual đúng version cần kiểm ở host |
| nftables/helper/sudo/block/unblock/packet | NOT_RUN | Không thay firewall hoặc tác động mạng; test source dùng executor giả |
| App/database/service deployment | NOT_RUN | Không chạy Compose, migration, seed, deploy hay SMTP |
| Throughput/lag/FP/latency/thermal | NOT_MEASURED | Cần corpus và hardware target; các số trong 03 là mục tiêu |
| Public dataset download/intake | NOT_RUN | Chỉ duyệt nguồn phát hành chính thức; chưa có dataset/hash/license manifest cục bộ |
| Training/resume/ONNX | NOT_RUN | Chưa có implementation; stages là backlog |
| Dependency vulnerability scan/SBOM/secret scan | NOT_RUN | Không khẳng định không có CVE/secret chỉ từ đọc manifests |
| Kiểm chứng nội dung docs/links/hash/scope | Được kiểm tĩnh trong phiên | Không thay thế các kiểm thử ứng dụng ở trên |

`student-web/backend/startup.log` là artifact ngày 29/09/2026, chứa SQLSTATE 28P01 và startup failure thời điểm đó; không phải log audit web, không dùng để khẳng định bản hiện tại không khởi động. Tương tự thông tin “đã kiểm trên máy…” trong docs cũ chỉ là lịch sử do tác giả ghi, không được chuyển thành PASS mới.

## 5. Nguồn bên ngoài và cách sử dụng

Các URL chính thức đã duyệt ngày 26/10/2026 được đặt gần đề xuất trong 01–03: Nginx log module, Suricata EVE, PostgreSQL locking; UNB/UNSW/WebRequests và OWASP logging; scikit-learn incremental estimators, PyTorch checkpoint/ONNX, systemd/cgroup và ONNX Runtime threading/quantization. Chúng cung cấp cơ chế và điều kiện, **không chứng minh code repo đã có chức năng đó**.

Tài liệu `stable/latest/current` có thể thay đổi. Khi triển khai phải pin package/runtime, lưu link manual đúng phiên bản và test API trên môi trường lock. Dữ liệu public cần xét terms của từng bản/thành phần trước khi tải/phát hành; việc có URL không thay cho quyền sử dụng. Không tải bộ dữ liệu hoặc script bên ngoài trong đợt này.

## 6. Duy trì evidence sau baseline

Giữ manifest 05A là snapshot lịch sử gắn commit khảo sát. Khi có PR mới, ghi commit/evidence mới vào 00/06 và cập nhật finding đã giải quyết trong 01; không bắt buộc hash lại toàn repo sau từng thay đổi nhỏ. Nếu cần audit lớn lần sau, tạo manifest snapshot mới có tên/mốc riêng hoặc cập nhật kèm lịch sử rõ ràng.

Kiểm `git diff --name-only`, `git ls-files --others --exclude-standard` và đối chiếu hash baseline để bảo đảm đợt khảo sát chỉ thêm `docs/`. Không chạy formatter toàn repo, tự sửa file cấu hình lỗi hoặc clean cache chỉ để báo cáo đẹp. Các finding được xử lý bằng task/PR riêng theo 04.

Kết quả QA tài liệu trong phiên: đủ 5 tệp bắt buộc và 2 tệp hỗ trợ cùng manifest TSV; 28 link Markdown nội bộ trỏ đúng tệp, JSON minh họa parse hợp lệ, code fence đóng đủ và không có trailing whitespace. SHA-256 của **524/524 tệp tracked** vẫn khớp manifest; tracked diff rỗng, chỉ có **8 tệp mới trong `docs/`**. Hai lượt review độc lập đã đối chiếu trạng thái, tên trường schema, IPS semantics và kế hoạch tài nguyên/resume; không có test ứng dụng hoặc training được chạy để đạt các kết quả QA này.

## 7. Foundation continuation

Từ base1925764, nhánhfoundation đã có code thay đổi và kiểm thử runtime theo00/06. Manifest05A giữ nguyên snapshot lịch sử37bc4d2; không dùng số524unchanged của khảo sát đầu để khẳng định code hiện tại không đổi. Trạng thái mới, filelist và kết quảPASS/NOT_RUN nằm trong06.
