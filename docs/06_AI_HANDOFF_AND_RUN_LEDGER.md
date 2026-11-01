# 06 — AI handoff, decision log và sổ training

**Handoff hiện hành:**27/10/2026, nhánh `feat/ai-model-training`, base`fbe078d8fe2e35bf60f7a08c7d21331f4522221e`; AI/docs được chia thành4commit theo mục17; chưa push. Package `ai-training/` offline đã hoàn thiện và kiểm chứng S0synthetic. **Không sửa bất kỳ file Student/Security**; SHA356file và gitdiffPASS. Không restart dịch vụ hay truy cập DB live. Foundation trước đó đã commit như mục15; các entry cũ giữ lại để tra lịch sử.

**Cập nhật hiện hành:**pre-training labpilot ởmục18:4.875requestthật,featurev2/148cột,
readiness23checksPASS,capacityPASS,58testsPASS. Khôngfitcorpusmới,giờtrain0.
Featurev1/S0 ở16 và4commit ở17 giữlịch sử; cập nhậtpre-training được chia3commit ở19, chưa push.
Thời gianthu/chờembargo/prep/test không cộng vào optimizerhours.

## 1. Quy trình cho câu “Đọc lại project”

AI ở chat mới làm theo thứ tự:

1. Đọc `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`, sổ này và roadmap 04. Đọc tiếp 01/02/03 theo task; không bỏ qua trạng thái actual/planned.
2. Đọc instructions đang áp dụng trong workspace, `git status --short`, `git rev-parse HEAD` và diff/log từ baseline ghi trong docs. Không reset/clean/stash thay đổi của thành viên khác.
3. Đối chiếu code paths, schema version, manifest và artifacts cho task hiện tại. Manifest 05A là snapshot khảo sát, không phải hash mới nhất sau mọi commit. Không tái đọc node_modules/target thay cho source.
4. Báo ngắn: code/AI đang ở đâu, evidence đã có, chênh lệch docs-code, việc tiếp theo đã được người dùng giao. Nếu chỉ được yêu cầu đọc, đọc và tóm tắt; không tự deploy, đổi firewall hay khởi động training.
5. Nếu người dùng giao tiếp công việc cụ thể, thực hiện theo scope mới, cập nhật status/evidence trong cùng PR/run. Những giới hạn của phiên khảo sát này không tự biến thành phê duyệt thay đổi production ở chat sau.

Không thể đảm bảo chat mới biết 100% trạng thái ở laptop/artifact store nếu nhóm không ghi lại. Mục đích của bộ nhớ sống là làm mọi trạng thái và điều chưa biết hiển thị, để AI kiểm tra nhanh và không suy diễn tiến độ.

## 2. Snapshot bàn giao hiện hành

| Mục | Giá trị / bằng chứng |
|---|---|
| Code base / branch | Base fbe078d8fe2e35bf60f7a08c7d21331f4522221e / feat/ai-model-training; commit theo mục17 |
| Foundation có sẵn | Canonicalv1.0, JavaauditJSONL, Rustdurableingest/rules/AuditAPI+tab; chuỗi8commit và tests nền ở mục15 |
| Vừa hoàn thiện | ai-training read-only adapters/privacy/correlation/Parquet/labels/split/features/MLP/AE/checkpoint/evaluate/ONNX/Pythonreference |
| Contract | Canonicalv1 giữ nguyên; AI schema snapshot có source hashes; derived ai-features-1 có125cột |
| Validation hiện hành |58pytestPASS,ruff/format/compileall/contractPASS;23readinesschecks+capacity+ownedlifecycleHTTPsmokePASS;356protectedfileSHA+gitdiffPASS. S0v1metrics ở16lịchsử |
| AI data/models | Pretraininglab4.875requests/148features;23gatechecksPASS,corpuschưafit. S0v1synthetic làlịchsử, chưa champion; giờtraincorpus0 |
| Runtime | Không thay đổi service/DB/config/host; không đọc credential; kết quả Java89/Rust50 thuộc phiên15, không là test đã chạy lại ở phiên AI |
| Chưa thử | Corpus thật, rule-only comparison, Rustport/parity/shadow, targetZenbook ca2–3h/thermal, hardcgroup quota, VM/AWS/kernel enforcement |
| Việc tiếp theo | Snapshot log bất biến→nhãnreview→data-readiness→train/benchmark máyđích; shared artifact store/reviewer chưa cấp |

## 3. Nhật ký công việc code/docs

| Entry | Ngày | Hạng mục | Trạng thái | Evidence / kết quả |
|---|---|---|---|---|
| DISCOVERY-20261026 | 26/10/2026 | Khảo sát source/config/SQL/tests/frontend/infra/docs/log artifacts | DONE cho đọc tĩnh | Snapshot commit + manifest 05A; limitations 05 |
| DOCS-20261026 | 26/10/2026 | Bộ nhớ sống và kế hoạch dual-engine/data/AI/team | DONE cho tài liệu | 00–06 + 05A; không có chức năng mới |
| FOUNDATION-20261026 | 26/10/2026 | Shared foundation code + schema + local runtime | IMPLEMENTED / validation bên dưới | R02 + phầnR10–R24; không coi mọiR00–R34 hoặc enterprise đã DONE |
| AI-PIPELINE-20261027 | 27/10/2026 | Isolated AI package + synthetic S0 | PASS cho offline pipeline/resume/export |42tests;2+2epoch newprocess cả2model;960/960parity; xem16, realtraining0giờ |

Với entry mới, thêm commit/PR, task ID, owner/reviewer, change summary, tests/env/results, known issue và next step. `DONE` cần đầu ra đã kiểm tra; `IN_PROGRESS` ghi phần còn thiếu. Dùng `BLOCKED` trong bảng này khi task thực bị phụ thuộc và ghi lý do, không coi tài liệu chưa implement là sự cố hiện tại.

## 4. Training ledger — phân biệt synthetic và dữ liệu thật

Snapshot26/10 có0run; không có lịch sử train thật bị xóa. Cập nhật27/10 có **2run synthetic chính với4phiên và2run reference với2phiên**, toàn bộ6row có ID/hash/time ở mục16. Optimizer hai run chính0.015538449s, reference0.015986770s tách riêng. **Training dữ liệu thật0giờ; bên ngoài repo chưa biết.** Chưa có champion hoặc artifact được phát hành.

Giữ một row mỗi phiên; bảng S0 ở16 là ledger đầu tiên, các phiên thật sau này thêm bảng riêng gắn nhãn nguồn dữ liệu. Không dùng checkpoint minh họa làm URI thật.

Mỗi run phải có metadata ngoài bảng: model architecture/env lock, parent/fine-tune relation, feature/redaction version, seed/sampler state, optimizer/scheduler config, thresholds/calibration, target resource quota và measured peaks. Mỗi session có số samples/steps, failures/retries, checkpoint integrity và reviewer khi promote.

Quy ước thời gian: `wall_hours` bao gồm đọc data/validation/checkpoint của phiên; `optimizer_hours` chỉ khoảng đo train tương ứng. Tổng theo run tính từ ledger, không lấy số ca nhân 2,5h nếu thực tế dừng sớm. Resume không tạo lại epoch/step 0. Số giờ đề xuất 70h trong 03 không điền vào cumulative actual.

### 4.1 Checklist cập nhật cuối phiên train

1. Dừng đúng optimizer boundary, ghi latest/previous/best có hash; kiểm file loadable và manifest complete.
2. Ghi epoch/global step và cursor mẫu kế tiếp, LR/scheduler, dataset/config/feature hashes; không lưu secrets/RNG object không rõ nguồn.
3. Ghi metrics và sample counts của validation, chưa sử dụng test khóa để tune; tách FPR request/session và source coverage.
4. Ghi quota hiệu lực/peak RAM/CPU/thermal, giờ phiên/giờ optimizer/giờ tích lũy và lý do dừng.
5. Upload artifact theo chính sách; nếu chưa upload, ghi local-only và path thật. Không giả định file local trên máy A có trên máy B.
6. Cập nhật next command tham số/URI đã kiểm chứng trong handoff riêng của run. Nếu resume incompatible, ghi tạo fine-tune run mới, không ép load.

## 5. Artifact registry — chưa có bản phát hành

| Artifact | Version/hash/URI | Trạng thái hiện hành |
|---|---|---|
| Canonical event schema | contracts/canonical-event-v1.schema.json /1.0 | FROZEN, có fixture/schema/runtime tests |
| Feature pipeline + golden vectors | ai-features-1/125features; ai-training/tests/fixtures/preprocessing_golden.json | Pythonreference/offline parityPASS, RustNOT_RUN |
| Dataset + labels/splits | S0synthetic manifestSHA ở16/report |576/192/192requests; chưa corpus thật |
| Training environment lock | ai-training/requirements.txt +pyproject.toml | Python3.12.14/Linux; exactpins/requirementsSHA ởreport |
| Latest / previous / best checkpoint | local ignored ai-training/.artifacts/synthetic_s0_20261027_final | Atomic manifests/hash; exactresumePASS; sharedstore chưa cấp |
| Candidate ONNX bundles / champion | Local MLP+AE; checksums ở16/report | Synthetic parityPASS; chưa champion/deploy |
| Calibration/threshold/model card | Có trong2bundle synthetic; validation-only empiricalFPR1% | Không chứng minh FPR production; không promote |
| Rule bundle | Repo có9SID + Rust6family | Engine offline PASS; không xác minh bundle đang cài ở host production |

URI phải dùng nơi nhóm thực sự truy cập được, ghi ACL/owner/expiry và checksum. Không commit model/data lớn chỉ để chat mới “thấy” tệp. Secret store riêng, docs chỉ có tên secret/key reference được phép chia sẻ.

## 6. Decision log

Quyết định của người dùng có hiệu lực trong scope phiên này; định hướng kỹ thuật mới là **PROPOSED** cho đến khi nhóm implement/đồng thuận tại task tương ứng. Không gán chữ ACCEPTED cho lựa chọn chưa kiểm chứng.

| ID | Trạng thái | Nội dung | Lý do / cách thay đổi |
|---|---|---|---|
| D00 | HISTORICAL USER CONSTRAINT | Phiên khảo sát đầu chỉ đọc code, tạo docs | Được yêu cầu triển khai foundation thay thế; không áp sai sang phiên này |
| D01 | OBSERVED | Audit student thực tế là `access_logs` | Không tự tạo giả định audit.log có sẵn |
| D02 | PARTIALLY IMPLEMENTED | Collector normalize/redact → PG durable inbox/outbox → rule + AI queues độc lập | Giữ nền Rust/PG; chỉ thêm broker khi benchmark cần |
| D03 | SUPERSEDED FOR FOUNDATION | User chọn direct JSONL exporter song song DB | Có file/cursor, chưa atomic outbox; lỗi sink được báo, không hứa lossless |
| D04 | PROPOSED | CPU-first baseline SGD/aggregates, candidate Byte-CNN/TCN nhỏ | Dữ liệu/hardware/latency quyết định champion, không chọn LLM theo mặc định |
| D05 | USER CONSTRAINT + DESIGN | Khoảng nửa CPU, RAM train dưới 16GB, ca 2–3h, checkpoint/resume | Thiết kế cap12GiB và tổng 70h dự kiến qua 30 phiên ở 03; CPU/OS thực cần S0 |
| D06 | PROPOSED | AI shadow/alert trước; IPS qua policy/TTL/freshness/kill switch | Giảm false block, bảo vệ management/NAT |
| D07 | PROPOSED | Chốt Ubuntu lab trước, AWS/HA sau bằng chứng | Repo chưa có AWS IaC/adapter thực |
| D08 | IMPLEMENTED27/10; user scope | feat/ai-model-training, packageai-training độc lập; MLP/AE NumPyCPU; chỉ đọc snapshots/export | User yêu cầu zero-config modification và cho phép MLP/AE; explicitAdam+NPZ/JSON giảm dependencies và giữ resume đầy đủ. Tree/CNN/TCN so sánh sau data-readiness. OwnerCodex;42tests/S0PASS; chưa reviewer thứ2 |

Entry mới phải ghi alternatives, trade-off, owner/reviewer, ngày, commit/PR và bằng chứng chấp nhận. Nếu bỏ một đề xuất, đổi trạng thái SUPERSEDED kèm quyết định thay thế; giữ lịch sử cần thiết, không xóa lý do khiến team hiểu sai bản hiện tại.

## 7. Điều chưa biết cần xử lý trong roadmap

| Điều chưa biết | Nơi giải quyết | Tác động |
|---|---|---|
| Zenbook CPU SKU/logical cores/OS/GPU và SSD trống | R03/S0 | CPU quota/affinity, throughput, dung lượng checkpoint |
| WebVM serve SPA/API/TLS/ports thực và trusted proxies | R00/R13 | Cookie secure, client attribution, vantage payload |
| DB/service/firewall/log thực đang chạy thế nào | R01/R15 | Runtime readiness; không suy từ config |
| Có train/dataset ngoài repo không | Intake R03/R30 | Đăng ký manifest/parent/checkpoint thật trước nối tiếp |
| Artifact storage, quyền truy cập hai máy, backup | R03/P6 | Resume/handoff và phục hồi bền vững |
| Traffic baseline/FP budget/coverage đủ bao lâu | R31–R34/P5 | Sizing, thresholds và tính tin cậy đánh giá |
| Scope enterprise/AWS/HA và nhu cầu người dùng thật | P6/P7 | Hạ tầng, identity, compliance và chi phí cần thiết |

Các điều kiện này không ngăn hoàn thành foundation local; Cần xác minh chúng trước những bước phụ thuộc; không tự điền bằng thông số tưởng tượng.

## 8. Quy tắc chống bộ nhớ sai

- Source/tests “có” không đồng nghĩa đã deploy/PASS. Log cũ lỗi khởi động không chứng minh code hiện tại lỗi. Alert count không phải attack count.
- Không đánh dấu train xong nhờ số giờ; không suy từ thư mục `trainingprogram` ra AI. CSV trong `.agents` là tài nguyên design skill, không phải IDPS dataset.
- Không mặc định file `audit.log` là auditd/ModSecurity; không mặc định EVE có body hoặc encrypted traffic quan sát được payload.
- Không diễn giải `AUTO_BLOCK=false` thành actuator off ở code baseline. Không dùng `/health`, rule catalog tĩnh, `--check-config` hay `--check` exit0 thay nghiệm thu pipeline.
- Nếu docs/code/artifacts lệch: ghi chênh lệch và bằng chứng mới, cập nhật summary+ledger; không âm thầm giữ tiến độ cũ hoặc xóa thay đổi người khác.
- Cuối mỗi phiên ghi rõ **đã làm**, **chưa làm**, **kiểm tra đã chạy**, **giới hạn**, **bước tiếp theo**. Bàn giao phải đủ để người khác kiểm chứng bằng code và artifact, không dựa ký ức chat.

## 9. Reproduction và dịch vụ đang chạy

Stack foundation riêng, không dùng/migrate hai DB đã tồn tại của người dùng:

| Dịch vụ | Địa chỉ hiện hành | Ghi chú |
|---|---|---|
| Student backend | 127.0.0.1:8080 | ss có thể hiển thị IPv4-mapped IPv6 `[::ffff:127.0.0.1]:8080`, vẫn chỉ loopback |
| Student frontend | 127.0.0.1:5173 | Chạy Vite; truy cập qua edge để correlate |
| Nginx dev edge | 0.0.0.0:18780 | Lần test cuối dùng --expose-lan; host template production/lab vẫn0.0.0.0:80 |
| Security foundation | 127.0.0.1:3001 | Không nhầm với security process cũ trên3000 đã được giữ nguyên |
| Student/Security demo DB | 127.0.0.1:55433 /55434 | Containers idps-foundation-student/security, volumes riêng |
| PostgreSQL có sẵn | 5433/5434 | student-postgres/pbl4-postgres không bị reset/migrate/stop |

Mở Student [local edge](http://127.0.0.1:18780) và [Security foundation](http://127.0.0.1:3001). Mật khẩu admin **dev security** nằm trong `.local-dev/foundation/credentials.json` quyền owner-only; không in/commit vào docs. Student DB demo chỉ có tài khoản giả `foundation-admin` do bootstrap khi chưa có admin; không reset tài khoản đã tồn tại, không seed hồ sơ thật. Password Student và Security demo nằm trong credentials private. `.local-dev/foundation/smoke-report.json` ghi requestID và kết quả không chứa password/token. Authenticated `/api/status` xác nhận3watcher watching, collection true, modeOFF, parse errors0; ready/enforcement healthy=false do không cấu hình helper trên host, đây là trạng thái dự kiến.

Lệnh từ gốc repo (không cần sudo, không sửa firewall):

```bash
# Ubuntu: tải/extract nginx vào private runtime nếu máy chưa có binary
scripts/dev-up-and-verify.sh --bootstrap-nginx --expose-lan
# Chỉ dừng stack foundation do script tạo; giữ volumes, logs và credentials
scripts/dev-up-and-verify.sh --stop
# Muốn quay lại chế độ chỉ-local: stop rồi chạy không --expose-lan
scripts/dev-up-and-verify.sh --bootstrap-nginx
```

Nếu nginx đã cài hoặc có binary đã extract, dùng `NGINX_BIN=/absolute/path/to/nginx` thay cho --bootstrap-nginx. Đổi port bằng DEV_API_PORT/DEV_FRONTEND_PORT/DEV_SECURITY_PORT/DEV_EDGE_PORT/DEV_STUDENT_DB_PORT/DEV_SECURITY_DB_PORT, cần --stop trước khi đổi cấu hình. Mỗi lần build script dùng npm ci và build cả frontend; node_modules tồn tại nhưng thiếu react-router-dom từng làm Student build FAIL ở kiểm tra đầu, đã sửa runtime dependency bằng clean install thay vì sửa code nghiệp vụ để che lỗi.

Template Nginx0.0.0.0:80 cần cài vào http context và quyền mở port80 khi triển khai thật; script demo dùng18780 không thay config/service hệ thống. Dùng HTTPS template với certificate và Secure cookies khi deploy; không bật Spring direct-TLS profile khi dùng HTTP upstream này. WebVM backup phải phục vụ `/` và `/api` trên80, giữ requestID/XFF từ edge tin cậy; cấu hình trust/mạng tương ứng và secure transport log riêng. Default Suricata capture vẫnvmnet2; LAN/AWS chọn interface thực bằng `--af-packet=<iface>` và manual đúngversion. HOME_NET/rule headers đã bỏ giới hạn client VMware, nhưng không tự khởi động live capture.

Privileged helper mới cần **cài đồng bộ** wrapper và module root-owned khi nhóm triển khai IPS (không chạy các bước này trong phiên): `/usr/local/bin/pbl4-firewall` gọi `/usr/local/libexec/pbl4-firewall-policy.py`, policy tùy chọn `/etc/pbl4/firewall-policy.json`. Cả allowed CIDRs và protected upstreams ở root policy phải thống nhất backend env; helper tự khám phá host/gateway trước BLOCK, kernel có protected set/local-address guard. Helper cũ không hỗ trợ TTL; không bật enforcement khi chưa cập nhật và nghiệm thu trong lab. IPv6 vẫn collect-only, never-block.

## 10. Kiểm tra đã chạy và giới hạn

| Lệnh / bằng chứng | Kết quả cuối |
|---|---|
| `mvn test` / `mvn -f student-web/backend/pom.xml test -q`, MIGRATION_TEST_URL trỏ disposable PostgreSQL17:55432/foundation_recovery_20261026 | PASS87, failures0/errors0/skipped0; Surefire XML |
| `DATABASE_URL=postgres://postgres@127.0.0.1:55432/postgres cargo test --locked -j 2` tại security-web (tương đương --manifest-path từ root) | PASS44, gồm SQLx DB thật; executor kernel giả |
| `cargo clippy --locked --all-targets -- -D warnings`, `cargo fmt --check` | PASS |
| `NGINX_BIN=... SURICATA_BIN=... LD_LIBRARY_PATH=... python3 security-web/scripts/test-config-contracts.py` | PASS6: Nginx5 (redaction/IDs/failover) + Suricata1 (syntax+PCAP9SID) |
| `python3 security-web/scripts/test-firewall-policy.py` | PASS3, không gọi nft |
| `CANONICAL_TEST_FILES=<actual Java JSONL>:<actual normalized JSONL> python3 contracts/test-schema.py` | PASS3, gồm output runtime hai ngôn ngữ |
| `unshare -Urn /usr/sbin/nft -c -f security-web/scripts/pbl4.nft` | PASS syntax/semantic check trong netns mới; không áp ruleset lên host |
| Shell syntax, Python compile, launcher lifecycle 2 tests, git diff --check | PASS |
| Student/Security frontend build; Student lint | Build theo script; lint0errors có30warnings hiện hữu, không tự sửa UI ngoài scope |
| `scripts/dev-up-and-verify.sh` và authenticated status | PASS,2 correlated source observations/cùng requestID;8080 loopback; collection true;3watcher watching;0parse errors |
| Host nft apply/block packet thật, remote CI run, LAN/VM/AWS thật, train/ONNX | NOT_RUN; không báo thànhPASS |

Các lỗi ban đầu đã xử lý: API writer/filter mismatch, fixture FlywayV2 trùng số và expectation version, GET audit làm thay đổi test pagination, stale checksum trên DB test khi migration còn viết dở (chạy lại trên DB disposable mới), fixture SYNburst chưa đạt10SYN/5s, clippy too-many-arguments, IPv4-mapped loopback assertion và node_modules thiếu dependency; probe restart đã dùng SO_REUSEADDR để tránh nhầm TIME_WAIT là listener đang chạy. Không dùng skip/ignore để che test fail; legacy StudentApiTests tắt audit reads bằng cờ tương thích, tests mới kiểm reads=true riêng.

Logs báo cáo cuối được giữ trong private `.local-dev/foundation/validation/`; không commit raw log vào Git. Test container idps-foundation-test-pg được dừng/xóa sau kiểm tra; chỉ hai DB demo và các service demo được giữ để người dùng thử. Những bước khai thác dữ liệu/train AI chưa được làm và không tính vào training ledger.

## 11. File thay đổi của foundation

Danh sách lấy từ Git working tree (gồm file xóa/đổi tên và các file viết dở được hoàn thiện), chưa commit/push; base1925764. Runtime/logs/credentials được ignore. Marker testV2 được chuyểnV3 để không trùng migration auditV2; không sửa migrationV1.

- `.github/workflows/ci.yml`
- `.github/workflows/security.yml`
- `.gitignore`
- `contracts/README.md`
- `contracts/canonical-event-v1.schema.json`
- `contracts/fixtures/student-audit-v1.jsonl`
- `contracts/test-schema.py`
- `docker/docker-compose.yml`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`
- `docs/FOUNDATION_VALIDATION.json`
- `scripts/dev-up-and-verify.py`
- `scripts/dev-up-and-verify.sh`
- `scripts/test-dev-launcher.py`
- `security-web/.env.example`
- `security-web/.gitignore`
- `security-web/README.md`
- `security-web/config/firewall-policy.json.example`
- `security-web/config/suricata/suricata.yaml`
- `security-web/docker-compose.yml`
- `security-web/docs/HOST_SECURITY_SETUP.md`
- `security-web/migrations/0003_shared_foundation.sql`
- `security-web/migrations/0004_response_deadlines.sql`
- `security-web/nginx/pbl4-proxy.conf`
- `security-web/nginx/pbl4-tls.conf.example`
- `security-web/scripts/pbl4-firewall`
- `security-web/scripts/pbl4-firewall-policy.py`
- `security-web/scripts/pbl4.nft`
- `security-web/scripts/test-config-contracts.py`
- `security-web/scripts/test-firewall-policy.py`
- `security-web/src/detection.rs`
- `security-web/src/events.rs`
- `security-web/src/firewall.rs`
- `security-web/src/foundation_tests.rs`
- `security-web/src/ingest.rs`
- `security-web/src/integration_tests.rs`
- `security-web/src/main.rs`
- `security-web/src/metrics.rs`
- `security-web/src/network.rs`
- `security-web/suricata/pbl4.rules`
- `student-web/backend/.env.example`
- `student-web/backend/README.md`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/dto/AccessLogSummary.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/entity/AccessLog.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/mapper/AccessLogMapper.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/service/AuditDatabaseWriter.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/service/AuditEvent.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/service/AuditJsonlExporter.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/accesslog/service/SecurityAuditService.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/AccountPrincipal.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/RequestAttribution.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityConfiguration.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/SecurityRequestFilter.java`
- `student-web/backend/src/main/java/com/pbl4/studentweb/configuration/TrustedForwardingConfiguration.java`
- `student-web/backend/src/main/resources/application.yaml`
- `student-web/backend/src/main/resources/db/migration/V2__audit_request_id.sql`
- `student-web/backend/src/test/java/com/pbl4/studentweb/AuditPersistenceTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/FlywayMigrationTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/FlywayStartupTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/StudentApiTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/accesslog/AuditExporterTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/configuration/RequestAttributionTests.java`
- `student-web/backend/src/test/java/com/pbl4/studentweb/configuration/SecurityRequestFilterTests.java`
- `student-web/backend/src/test/resources/application.properties`
- `student-web/backend/src/test/resources/db/upgrade/V2__migration_test_marker.sql`
- `student-web/backend/src/test/resources/db/upgrade/V3__migration_test_marker.sql`
- `student-web/frontend/vite.config.ts`

## 12. Quyết định foundation và điểm khôi phục cuối

- D08 — ACCEPTED: schema v1.0 tại contracts là hợp đồng chung. Timestamp UTCZ; origin event identity tách request correlation. Thay đổi breaking cần version và review cả AI/IPS; không dùng detector flags làm ground truth.
- D09 — ACCEPTED: Compose Student5433/Security5434; dev script dùng DB55433/55434 và Security3001 để bảo toàn dịch vụ cũ. Backend8080/frontend5173 loopback, chỉ edge được mở đa interface.
- D10 — ACCEPTED WITH LIMITS: upstream local-first/VMbackup đã test connection refusal. Session/DB giữa local vàVM không tự đồng bộ; log từVM phải được ship/mount an toàn riêng. Chưa nghiệm thu LAN/VM/AWS thật.
- D11 — ACCEPTED: enforcement OFF mặc định, IPv4 scope có cấu hình, protected root policy độc lập, fresh evidence, deadline/TTL≤300s. IPv6 chỉ collect, không enforce. Host nft chưa được áp/thay đổi.
- D12 — ACCEPTED: tài khoản/demo DB/credentials tách khỏi dịch vụ có sẵn. Chỉ dọn test container do phiên tạo sau khi test kết thúc.

Lần khôi phục cuối đã chạy `git status/branch/diff/log`, `cargo check`, `./mvnw test-compile` trước sửa tiếp. Không thấy source bị cắt ngang hoặc lỗi compile. Đã giữ các chức năng hoàn chỉnh, bổ sung hướng dẫn service/env/helper và hoàn tất báo cáo kiểm chứng mà lần trước dừng ở bước ghi file. Báo cáo công khai không chứa secret: [FOUNDATION_VALIDATION.json](FOUNDATION_VALIDATION.json). Raw validation logs nằm trong ignored private `.local-dev/foundation/validation/`.

Kết quả fresh rerun: Java87/87, Rust44/44, edge/sensor6/6, schema3/3 (có actual Java/Rust output), firewall policy3/3, launcher2/2; không skip ứng dụng. `/api/status` authenticated trả3watcher watching, ingestion_errors0, collect=true, modeOFF. healthy=false là dự kiến do không cài helper/ruleset host. Checksum/schema hash và thời điểm được lưu trong báo cáo JSON.

Giới hạn đã biết: Student lint0errors/30warnings hiện hữu; npm ci Student báo3high advisories trong dependency tree, chưa audit/remediate sâu ở taskfoundation (không tự đổi lockfile). Không gọi buildPASS là dependency scanPASS. Corpus có nhãn, model training, production retention/archive, atomic producer outbox, remote shipping, HA và chặn packet thật vẫn chưa thực hiện. Đây là backlog riêng, không bị ghi làDONE.

### Chạy lại test với PostgreSQL disposable

Các lệnh dưới tạo **test container mới** riêng; nếu cổng55432 đã có listener thì chọn cổng trống và cập nhật URLs, không stop một DB không rõ nguồn.

```bash
docker run --rm -d --name idps-foundation-test-pg -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55432:5432 postgres:17-alpine
docker exec idps-foundation-test-pg pg_isready -U postgres
docker exec idps-foundation-test-pg createdb -U postgres foundation_java_test
DATABASE_URL=postgres://postgres@127.0.0.1:55432/postgres cargo test --manifest-path security-web/Cargo.toml --locked
MIGRATION_TEST_URL=jdbc:postgresql://127.0.0.1:55432/foundation_java_test MIGRATION_TEST_USER=postgres MIGRATION_TEST_PASSWORD= ./student-web/backend/mvnw -f student-web/backend/pom.xml test
docker stop idps-foundation-test-pg
```

Dùng trust chỉ cho disposable loopback testcluster, không cho DB thật. Chờ pg_isready sẵn sàng trước createdb. Lệnh test có thể tạo/xóa DB test riêng, không trỏ DATABASE_URL/MIGRATION_TEST_URL vào dữ liệu ứng dụng. Testcontainer dùng --rm tự xóa khi stop; volumes demo do dev script tạo vẫn giữ nguyên.

## 13. Hướng dẫn nâng bản VM-only — 26/10/2026

Người dùng xác nhận bạn cùng làm giữ code Student từ trước foundation và tiếp tục mô hình Web VM riêng, không chạy Student cùng máy Security. Đã đối chiếu diff từ base1925764 với env/proxy/Flyway/writer/collector hiện tại và tạo [07_VM_ONLY_UPGRADE_GUIDE.md](07_VM_ONLY_UPGRADE_GUIDE.md), thêm index tại00. Chỉ cập nhật tài liệu; không sửa app/config thực, không đọc/ghi `.env` riêng, không commit/push hoặc áp thay đổi lên VM.

Guide phân chia trách nhiệm WebVM/Security, giữ DB credentials/volume cũ, thêm audit key/path/reads/instance, giữ app loopback qua NginxVM, hướng dẫn truyền requestID và XFF qua hai proxy, chuyển upstream Security thànhWebVM chính và đối chiếu port khi hai DB tách máy. **Remote audit shipping vẫn chưa có implementation**: phải bổ sung cơ chế transport thì collector Security mới đọc auditVM; không coi chỉ đặt path/env là đã tích hợp.

Mẫu HTTP/Vite chỉ dùng cho topology minh họa và có giới hạn truy cập WebVM từ Security. Nếu nhóm đang dùng static dist hoặc Spring TLS trực tiếp thì giữ/hòa nhập hợp đồng tương ứng, không chép đè mẫu. IP/NIC thực trên máy bạn cùng làm chưa được cung cấp và chưa được nghiệm thu. Kiểm tra cú pháp Nginx và liên kết tài liệu tại local là kiểm chứng tài liệu, không là kết quả deployVM. Báo cáo FOUNDATION_VALIDATION.json giữ snapshot test code trước khi thêm guide07; không chạy lại toàn bộ app tests cho thay đổi docs-only.

Validation guide07: hai đoạn Nginx PASS kiểm tra cấu hình trong thư mục tạm sau khi thay riêng listenIP/port mẫu bằng loopback khả dụng (máy local không có IP192.168.20.10); 33 liên kết tài liệu nội bộ hợp lệ; git diff --check PASS. Nginx trên WebVM thật, remote log transport và test end-to-end topology đó vẫn NOT_RUN. Không chỉnh config/source đang chạy để tạo guide này.

## 14. Tab Audit ứng dụng — 26/10/2026 22:47 +07:00

**Owner:** Codex theo yêu cầu triển khai trực tiếp của người dùng. **Reviewer:** chưa có review độc lập. **Branch/base:** `codex/foundation-audit-and-schema`, HEAD `1925764a0b4dbbae647797136e17abfd9a122c45`; thay đổi ở working tree, chưa commit/push/PR. Phạm vi phiên này: thêm giao diện Security để xem normalized observations từ foundation. Báo cáo máy đọc được: [APPLICATION_AUDIT_VALIDATION.json](APPLICATION_AUDIT_VALIDATION.json); báo cáo FOUNDATION_VALIDATION giữ nguyên snapshot cũ.

Đã thêm API chỉ đọc `/api/application-audit` và `/{id}` sau auth guard, viewer/admin đều xem được. List/count dùng cùng PostgreSQL snapshot; lọc UTC `[from,to)`, source/IP/endpoint/status/method/requestID, limit25 mặc định/tối đa200, offset cap1triệu, thứ tự timestamp/id giảm dần. Detail trả typed canonical v1 đã validate/mask lần nữa và tối đa10 quan sát cùng requestID. Không ghép chỉ bằng IP, không tự gán nhãn benign/attack, không có hành động firewall/ghi/xóa dữ liệu ở tab này. Unknown/raw fields hoặc identity sai hợp đồng trả500 chung, không phản chiếu nội dung vào response/log lỗi. Redactor giữ placeholder `[id]`/`[redacted]` khi áp lại để đường dẫn hiển thị ổn định.

UI thêm tab **Audit ứng dụng** mặc định Student trong24giờ qua; form submit, phân trang25, tải lại thủ công, loading/error/empty riêng, hủy fetch cũ khi đổi filter/page/rời tab. Native dialog cho canonical JSON và liên kết theo requestID; các giá trị hiển thị bằng React text. Có trạng thái COLLECT_ALL_EVENTS, retention/cap và watcher từng nguồn; cờ tắt vẫn xem lịch sử. Firewall audit/tab **Nhật ký thao tác** tiếp tục dùng `/api/audit`. Không thay producer Student, DB migration, canonical schema, rule engine hoặc chế độ enforcement trong phiên này.

**Files phiên này thêm/sửa (không phải toàn bộ foundation diff):**

- Backend: `security-web/src/application_audit.rs`, `security-web/src/application_audit.sql` (mới); `security-web/src/main.rs`, `security-web/src/events.rs`, `security-web/src/detection.rs`, `security-web/src/integration_tests.rs`.
- Frontend: `security-web/frontend/src/ApplicationAudit.tsx`, `security-web/frontend/src/auditQuery.ts`, `security-web/frontend/tests/audit-query.test.mjs` (mới); `security-web/frontend/src/main.tsx`, `security-web/frontend/src/Icon.tsx`, `security-web/frontend/src/style.css`, `security-web/frontend/package.json`.
- Ops/docs: `.github/workflows/security.yml`, `security-web/scripts/smoke-test.py`, `security-web/README.md`, `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`, `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`, `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`, tệp06 này và báo cáo validation mới. Không thêm dependency hoặc đổi lockfile.

**Các lệnh đã chạy và kết quả:**

| Context / lệnh | Trạng thái | Bằng chứng / giới hạn |
|---|---|---|
| Root: `docker run --rm -d --name idps-foundation-test-pg -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55432:5432 postgres:17-alpine`, `docker exec idps-foundation-test-pg pg_isready -U postgres` | PASS | Cluster test mới riêng, không dùng DB ứng dụng5433/5434 hoặc demo55433/55434 |
| `security-web`: `DATABASE_URL=postgres://postgres@127.0.0.1:55432/postgres cargo test --locked -j 2` | PASS | 49 test, 0 fail/ignored; 5 integration test mới: quyền/đọc lịch sử khi tắt thu thập; filters/count/pagination; invalid input; privacy/strict contract/idempotent display; bounded cross-source correlation |
| `security-web`: `cargo clippy --locked --all-targets -j 2 -- -D warnings`, `cargo fmt --all -- --check`, `cargo build --locked -j 2` | PASS | Không warnings, compile binary dùng cho demo |
| `security-web/frontend`: `npm test` | PASS | 3 Node tests: local time→UTC qua3timezone, encoding IPv6/endpoint/requestID, invalid/reversed bounds; dùng TypeScript support có sẵn của Node24 |
| `security-web/frontend`: `npm run format:check`, `npm run build` | PASS | TSC + Vite; kiểm format cả src/tests; CI đã nối npm test/format |
| `security-web`: `python3 scripts/smoke-test.py --url http://127.0.0.1:3001 --username admin` | PASS | Chạy không tương tác bằng getpass override trong memory từ credentials private; anonymous401, list/detail,400/404, APIs cũ và logout revoke. Không đưa password/token vào argv/log/docs |
| Inline urllib assertions trên demo3001 | PASS | no-store, Student detail đã mask, có Nginx cùng requestID, source filters, bundle mới được serve; private `.local-dev/foundation/application-audit-smoke.json` |
| `git diff --check`; JSON report parse/hash checks | PASS | Kiểm tra whitespace và report, không phải browser visual acceptance |
| Browser/CUA mở demo3001 | NOT_RUN | Tool báo **Local browser use is disabled in Work settings**; không có screenshot, chưa xác minh layout/mobile/keyboard tương tác thực |
| `mvn test` | NOT_RUN trong phiên UI này | Không sửa Student; kết quả87 test PASS trước đó thuộc báo cáo foundation, không ghi thành lần chạy mới |
| VM/AWS deployment, live Suricata capture, packet block, AI training | NOT_RUN | Ngoài phạm vi tab; không áp nftables/helper trên host |

**Runtime đã cập nhật:** build vào `security-web/frontend/dist`; restart riêng demo Security loopback3001 bằng đúng environment cũ sau khi kiểm PID/start token. Giữ nguyên tiến trình Student8080, Vite5173, Nginx18780, Security cũ3000 và các DB volumes. Phiên đăng nhập Security ở RAM bị hủy khi restart, người dùng reload rồi đăng nhập lại với credentials cũ để thấy tab mới. Enforcement vẫn OFF. Smoke ghi nhận25 Student observations,90 Nginx,0 Suricata; cả3 watcher `watching` nhưng EVE demo rỗng, không suy diễn đã capture Suricata thật. `/api/ready` degraded vì thiếu host firewall helper là trạng thái demo dự kiến.

Đã dừng/xóa container test disposable sau kiểm thử; không dừng các container ứng dụng/demo. Bước tiếp theo về UI là nghiệm thu trực quan khi browser được bật; phần remote audit transport của VM-only trong07 vẫn chưa được triển khai và không bị đánh dấu hoàn thành bởi tab mới.

### 14.1. Chẩn đoán log tạo khoa và sửa nút Làm mới — 26/10/2026 22:55 +07:00

Người dùng tạo khoa nhưng không thấy log trên dashboard. Đọc JSONL và API xác nhận Student đã xuất audit, Security đã ingest thành công: event242, `POST /api/faculties`, HTTP201, lúc22:51:39+07:00, observed sau khoảng238ms; detail có quan sát Nginx cùng requestID. Không đọc/log request body, tên khoa hoặc credential. Không tạo lại khoa hay chỉnh dữ liệu người dùng.

Root cause UI được rà soát độc lập bởi agent `audit_refresh_review`: bảng audit chỉ tải khi mount/filter/page hoặc nút local **Tải lại audit**; nút **Làm mới**/timestamp polling ở header chỉ tải các API cũ nên dễ khiến người dùng tưởng audit đã cập nhật. Đã thêm signal từ nút header khi tab Audit đang mở vào dependency của fetch audit. Giữ applied filters/page/drawer; AbortController hủy fetch trước. Local refresh vẫn hoạt động; polling5s giữ phạm vi summary như cũ. Giao diện bổ sung hướng dẫn rõ cách tải lại.

Files sửa: `security-web/frontend/src/main.tsx`, `security-web/frontend/src/ApplicationAudit.tsx`, `security-web/README.md`, docs00/01/02/06; thêm `docs/APPLICATION_AUDIT_REFRESH_VALIDATION.json`. Không đổi backend, database hoặc Student. Report APPLICATION_AUDIT_VALIDATION là snapshot trước patch này; hash các file bị sửa được cập nhật trong report follow-up, không ghi đè bằng chứng cũ.

Validation: `npm test` PASS3; `npm run format:check` PASS; `npm run build` PASS (TSC/Vite). HTTP GET đã xác minh row242 từ normalized API và Nginx correlation. JS/CSS served ở3001 khớp build mới; `git diff --check` và JSON/hash checks PASS. Các unit test frontend hiện có kiểm timezone/encoding/validation, không phải test tương tác nút; wiring được review code. Browser visual/click acceptance NOT_RUN vì Local browser use đang tắt. `cargo test`/`mvn test` NOT_RUN lại ở follow-up chỉ sửa UI này; kết quả49 Rust và87 Java thuộc mốc trước.

Deploy local chỉ build lại dist do Rust serve file trực tiếp; giữ nguyên tiến trình Security181072, Student/Vite/Nginx và toàn bộ DB. Người dùng F5 trang3001 để tải JS mới, đăng nhập lại nếu cần; tab Audit ứng dụng → endpoint `/api/faculties`, methodPOST → Áp dụng bộ lọc/Tải lại audit. Tổng quan/Cảnh báo không liệt kê mọi CRUD thành công; Nhật ký thao tác là lịch sử firewall.

## 15. Kiểm tra trước commit và chia lịch sử — 26/10/2026 23:12 +07:00

**Yêu cầu:** người dùng cho phép git add/commit toàn bộ thay đổi từ đầu phiên theo từng phần để tự push. **Owner:** Codex; review đọc độc lập theo vùng Student, Security, docs bởi các agent trong cùng phiên, chưa có review người thứ hai hoặc remote CI. **Branch:** `codex/foundation-audit-and-schema`; base trước chuỗi commit `1925764a0b4dbbae647797136e17abfd9a122c45`. Không push, không merge, không đổi remote hay cấu hình danh tính Git của người dùng.

Rà soát phát hiện Student giữ UA tự do nếu không khớp denylist. Đã đổi sang allowlist product families giống normalizer Rust: browser/client/scanner nhận tên sản phẩm cố định; unknown text→[REDACTED], null/empty giữ trạng thái thiếu và vẫn bound/truncated. Cả Java/Rust map method tùy biến→OTHER; Rust đặt redacted khi đổi method, API/UI cho lọc OTHER. Bổ sung2 canary tests Java và1 Rust, sửa assertions UA persistence/filter. Schema v1.0 không thêm trường/đổi kiểu. Snapshot report cũ giữ nguyên lịch sử trước các thay đổi này; báo cáo hiện hành [COMMIT_READINESS_VALIDATION.json](COMMIT_READINESS_VALIDATION.json).

### 15.1. Các commit theo phần

| Commit | Phần |
|---|---|
| `7a4b7ab` | `feat(schema): define canonical security event v1 contract` — JSON Schema, synthetic fixture, validator |
| `1894799` | `feat(student): export private audit events with trusted proxy attribution` — Java audit/attribution/exporter, FlywayV2, tests và CI path filter |
| `355cda5` | `feat(security): add durable ingestion and bounded response policies` — canonical parser/collector/rules, safety/firewall/helper, migrations0003/0004 và tests |
| `79b9869` | `fix(infra): separate database ports and normalize proxy telemetry` — Compose/env, Nginx/TLS, EVE config và host setup |
| `e3e75bc` | `chore(dev): add an isolated foundation launcher and smoke workflow` — private runtime launcher, ignore rules và Student Vite loopback |
| `8b762bf` | `feat(audit): expose canonical event search and dashboard details` — read-only API, Audit tab, privacy view/correlation/refresh, tests và smoke script |
| `ed361fe` | `ci: validate shared contracts and security dashboard checks` — workflow dùng đủ scripts/tests đã có ở các commit trước |
| Commit tài liệu chứa mục này | `docs: record foundation validation and VM upgrade handoff` — docs00–07, READMEs và các report lịch sử/hiện hành |

Để tách Audit khỏi foundation mà từng mốc vẫn build được, đã partial-stage `main.rs`, `events.rs`, `detection.rs`, `integration_tests.rs` qua Git index; không thay/checkout/reset file làm việc. Xuất toàn bộ index foundation sang thư mục tạm riêng, chạy test/clippy/fmt tại đó trước commit355cda5:45 test PASS. Commit Audit thêm5 integration test thành tổng50. Bản cuối được đối chiếu manifest source để tránh mất hunk; V2 test marker được rename nguyên vẹn thànhV3 trong commit Student.

### 15.2. Validation chạy lại trong phiên commit

| Lệnh / context | Kết quả | Chi tiết |
|---|---|---|
| Disposable PostgreSQL17, loopback55432; DB `foundation_java_test` | PASS | Container `idps-foundation-commit-test-pg`, không dùng dữ liệu app/demo |
| Student: `MIGRATION_TEST_URL=jdbc:postgresql://127.0.0.1:55432/foundation_java_test MIGRATION_TEST_USER=postgres MIGRATION_TEST_PASSWORD= ./mvnw test` | PASS | **89 tests**,0fail/error/skipped; log private `.local-dev/foundation/commit-maven-test.log` |
| Security: `DATABASE_URL=postgres://postgres@127.0.0.1:55432/postgres cargo test --locked -j 2` | PASS | **50 tests**,0fail/ignored; gồm5 audit API integration tests và custom-method privacy |
| Security: `cargo clippy --locked --all-targets -j 2 -- -D warnings`; `cargo fmt --all -- --check` | PASS | Full source tree và foundation index snapshot riêng |
| Foundation index snapshot: cùng cargo commands | PASS | **45 tests**; xác nhận dependency boundary không cần module Audit chưa commit |
| Security frontend: `npm test`; `npm run format:check`; `npm run build` | PASS | **3 tests**, TSC/Vite và format |
| `python3 contracts/test-schema.py` với `CANONICAL_TEST_FILES` | PASS | **3 tests**, fixture và JSONL từ demo Java/Rust đã chạy trước đó; không coi đây là deploy producer mới |
| `python3 security-web/scripts/test-config-contracts.py` với binary Nginx/Suricata đã extract | PASS | **6 tests**: loopback edge/backup/privacy và PCAP offline đủ9SID; không live capture |
| `python3 security-web/scripts/test-firewall-policy.py` | PASS | **3 tests**, không áp firewall host |
| `python3 scripts/test-dev-launcher.py`; `bash -n scripts/dev-up-and-verify.sh security-web/scripts/pbl4-firewall` | PASS | **2 tests** và shell syntax |
| Runtime credential scan trên85 changed/untracked paths trước stage | PASS |0match với mọi credential private hiện tại; không in giá trị secret |
| `git diff --cached --check` | FAIL→PASS | Lần đầu bắt một trailing space trong launcher mới; đã xóa whitespace và gate PASS trước commit |
| Final Git/source/report checks | PASS | Source hunk manifest, JSON/hash, internal docs links, diff whitespace, staged secret screening; working tree sạch sau commit cuối |
| Browser interaction, GitHub Actions mới, VM/LAN/AWS acceptance, nftables packet enforcement | NOT_RUN | Chưa có bằng chứng mới; browser settings vẫn tắt, kernel mode vẫn OFF |

Files thay đổi trong lần siết privacy: `AuditEvent.java`, `AuditExporterTests.java`, `AuditPersistenceTests.java`, `SecurityRequestFilterTests.java`, Rust `events.rs`, Audit API `application_audit.rs` và `ApplicationAudit.tsx`; các file này được đưa vào đúng commit Student/Security/Audit. Ngoài ra cập nhật docs00/01/02/04/06/07 và Student README để phản ánh privacy/commit state; sửa duy nhất trailing whitespace ở launcher trong gate stage.

Container PostgreSQL test đã stop/auto-remove, snapshot index tạm được dọn sau kiểm chứng. Không restart Student/Security/Nginx hoặc sửa DB ứng dụng trong phiên commit; daemon đang chạy vẫn dùng binary trước lần siết privacy, cần build/restart theo quy trình dev khi muốn chạy chính xác source vừa commit. Phần UI dist đã build lại. Credentials, runtime logs/captures, `.env` cá nhân, cache và build artifacts không được đưa vào commit. Không huấn luyện AI. Các báo cáo FOUNDATION/APPLICATION_AUDIT trước đó là snapshot lịch sử có base/hash/uncommitted ở thời điểm ghi, không phải mô tả Git HEAD mới.

Review sau sửa privacy không phát hiện blocker. Có một backlog P3 về chất lượng metadata: sanitizer nhận raw `edg/` nhưng chưa alias canonical `Edge`, nên qua lần sanitize tiếp theo có thể mất family Edge; các family khác trên cùng UA vẫn được giữ. Chưa sửa trong phiên đóng gói commit; không ảnh hưởng che bí mật hay ingestion. Cần bổ sung alias và idempotence test trước khi dùng UA families làm feature train chính thức.

## 16. AI Data & Training Pipeline — 27/10/2026

**Scope/owner:** Codex triển khai trực tiếp theo yêu cầu user, không tạo agent mới; chưa có reviewer người thứ hai. Nhánh **`feat/ai-model-training`**, base/sourcecommit`fbe078d8fe2e35bf60f7a08c7d21331f4522221e`. Đầu task workingtree sạch; kiểm gitstatus/branch/log, đọc00/02/03/04/06 và Javaexporter/Rustingest/events/allmigrations/Nginx/canonical trước viết code. Thêm toàn bộ AI trong package riêng, không đổi rootcontract/CI/launcher hoặc file Student/Security. Tại thời điểm nghiệm thu S0 chưa gitadd/commit/push; yêu cầu commit tiếp theo của user được thực hiện riêng ở mục17.

### 16.1. Kết quả và quyết định

Read-only bounded parsers đúngfield/unit, canonicalstrict, privacyHMAC/keyriêng, route/UA/query numericprojection, requestcorrelation tránhNAT, past-onlyflowcontext, explicitlabelconflicts/unknown, temporalconnectedgroups/embargo300s, Parquet+manifestsha.125causalfeatures, benign-train-onlyscaler, boundedwindows, sourcefingerprint và Pythonreference/golden vectors. CPU FP32 MLP+AE cóAdam/scheduler/RNG/sampler/cursor, resourceguard, atomiccheckpoint/runlock/fallback, metrics/validation-onlythreshold, ONNXopset18IR9/CPUparity. README ghi CLI đầy đủ. D08 chốt lựa chọn nhẹ thay vì càiTorchCUDA/boosting khi chưa có corpus thật; không có chức năng inference/enforcement trong services.

**S0 pipeline/resume verification trên synthetic fixture**, không phải ca train corpus thật hoặc kết quả phát hiện zero-day. Chạy **2026-10-27T12:39:52.687+07:00 → 2026-10-27T12:40:01.896+07:00**, tổngwall9.209334850s.15campaign×64=960request/3403observations; train576/val192/test192; AE chỉ fit72benign train.125feature; rule/alertfacts excluded khỏi model. Hai run chính2epoch→process mớiresume đến4; reference mỗi model4epoch liên tục. Exact weights/Adammoments/scheduler/RNG/permutationPASS; S0decay_steps5 đi quaLRboundary, defaultconfig100 không thay.

Local artifactroot thật: `ai-training/.artifacts/synthetic_s0_20261027_final/` (ignored). **Local-only**, chưa upload/sharedstore; máy bạn không tự có file này. Public metadata: [S0_20261027.json](../ai-training/reports/S0_20261027.json), chứa source/config/test hashes, fullrun/sessionID, features/env/resources, allmetrics vàbundlehash; không có key/rawdata/weights.


ReportSHA-256 `f478de8d39b30ff4faa024a360e1087a170976b0b75002ef7320c6d11fce8354`. DatasetSHA-256 `2db5c8452c7bf7df7931562c0a55b9db78642495234be10d63ae03f5cbfafc4a`. RequirementsSHA-256 `a62cf5bd2ca14c104060535a1ea52c266c05436a67ed9d9fd609e7686e2594c5`. FeatureSpecSHA-256 `1eec80eae30c3e5ec8e59276c3d2c3b4b90e18c0f70da9c7f54c0a09734edc43`. Code AI còn uncommitted lúc đo; report lưu SHA từngsourcefile để tái kiểm, không gán kết quả cho commit tương lai.


| Model | Immutable learning config SHA-256 | Final checkpoint manifest SHA-256 | ONNX SHA-256 |
|---|---|---|---|
| autoencoder | `30523e0ccf2f9d45c6fb266c5032f6be95ddec80ea7cf83db8a064a612fa80b5` | `fe8896145823b3b4c61dcc2ed33f048e9a9a5fadb0efce3a02ddbaa267f0dc8f` | `24ce67057c7616abc9d68a38596ce1d601455bd2679194d5ac0c91bb1548dc18` |
| mlp | `2fd43ee1edf20763546edb50e7d826f3a4182f819134abadc4ad078d4e0073e8` | `b17c8ce86ef07033619bb7296ffd0314b7c4ab89b243249538d19c543c629b6b` | `83de614dbf185817c38653013e27311bd6e5a5295930d930c96936462eabae87` |

### 16.2. Ledger từng phiên S0 — thời gian đều +07:00

Dataset/configSHA dùng bảng trên, sourcecommitfbe078d+workingtree hashes trongreport. URI checkpoint là artifactroot +`{model}-resumed/` hoặc`{model}-continuous/`+checkpointgeneration dưới đây. Session wall gồm bước khởi tạo/validation/checkpoint; optimizer chỉ thời gian tính step; bảng dùng **giây** để không làm tròn thành giờ giả. ID đầy đủ và cumulative state có trongreport.

| Model / run / session | Start → end (+07:00) | Epoch / global step cuối | Session wall s / optimizer s | Checkpoint generation + manifest SHA-256 | Stop |
|---|---|---|---|---|---|
| autoencoder main<br>run`6051181c123e47d99e9b1c6c5ec14387`<br>session`61e9c6e79b554f30851683c5dbc26816` | 2026-10-27T12:39:58.480+07:00 → 2026-10-27T12:39:58.815+07:00 | 2 / 4 | 0.334937131 / 0.002904527 | `checkpoints/step-000000000004-8afe8c67cb7a`<br>`6135d3e40ea250bcdfeaa5f1638159014d93569f375e05f0f5e9895b6446a27e` | epochs_complete |
| autoencoder main<br>run`6051181c123e47d99e9b1c6c5ec14387`<br>session`4da3c027f2be4658ba40e7009414fac4` | 2026-10-27T12:39:59.449+07:00 → 2026-10-27T12:39:59.711+07:00 | 4 / 8 | 0.261424660 / 0.001892931 | `checkpoints/step-000000000008-829b52957e56`<br>`fe8896145823b3b4c61dcc2ed33f048e9a9a5fadb0efce3a02ddbaa267f0dc8f` | epochs_complete |
| autoencoder reference<br>run`e861cc531a294930a5366f0fdbb83aa1`<br>session`81f680e44b824ac9b2982847fea9e5bb` | 2026-10-27T12:40:00.350+07:00 → 2026-10-27T12:40:00.832+07:00 | 4 / 8 | 0.482148273 / 0.005119749 | `checkpoints/step-000000000008-7defb412cf96`<br>`40b5c5a880b67258a423016096f2de323c9ac24d8d2bae638cb70a67b661210d` | epochs_complete |
| mlp main<br>run`fbd3c1dc86864568af1ac823d78c0d7b`<br>session`9e68708864a54a15a388c6a26d88fe87` | 2026-10-27T12:39:54.242+07:00 → 2026-10-27T12:39:54.621+07:00 | 2 / 18 | 0.378758844 / 0.005566408 | `checkpoints/step-000000000018-aaff5fc7a4f4`<br>`fc1a4b706bd0d37134015b1b3c16c75a81d68185cd5a496ebf1fcd43fecaaddb` | epochs_complete |
| mlp main<br>run`fbd3c1dc86864568af1ac823d78c0d7b`<br>session`2453d031acb3426a97de35a4ef10472e` | 2026-10-27T12:39:55.279+07:00 → 2026-10-27T12:39:55.650+07:00 | 4 / 36 | 0.371193808 / 0.005174583 | `checkpoints/step-000000000036-95af02628246`<br>`b17c8ce86ef07033619bb7296ffd0314b7c4ab89b243249538d19c543c629b6b` | epochs_complete |
| mlp reference<br>run`bc765eda609e464bb5d19da11331b093`<br>session`5ee1d19e99c54ec485dbac109273e518` | 2026-10-27T12:39:56.280+07:00 → 2026-10-27T12:39:56.859+07:00 | 4 / 36 | 0.578946724 / 0.010867021 | `checkpoints/step-000000000036-ee381ac2e8fa`<br>`6bf2e493c7d9b86d29d00b8c3c2567dcffaad472b2dd0340bdad207396d32c73` | epochs_complete |

Tổng optimizer hai mainrun **0.015538449s = 0.000004316236h**; hai continuousreference **0.015986770s** ghi riêng. Preprocessingwall1.067499977s không tính training; ngoài6sessionwall6.801925410s gồm collect/prepare/export/processstartup và orchestration. **Giờ train dữ liệu thật=0**. Tất cả dừng epochs_complete, không dùng maxduration để giả kéo dài ca.

### 16.3. Metrics/resource/export đo thật trên synthetic

| Model | Final step / next LR | ONNX parity | Test PR-AUC(AP) / ROC-AUC / F1 / precision / recall | Recall@FPR≤1% ROC diagnostic | Warm ORT latency p50/p95/p99 ms |
|---|---|---|---|---|---|

| autoencoder | 8 / 0.00196 |960/960PASS, rtol1e-5/atol1e-6 | 0.878891 / 0.469246 / 0.000000 / 0.000000 / 0.000000 | 0.029762 | 0.004543/0.005234/0.005484 |
| mlp | 36 / 0.00173625106649344 |960/960PASS, rtol1e-5/atol1e-6 | 0.936729 / 0.677331 / 0.222222 / 1.000000 / 0.125000 | 0.142857 | 0.003928/0.004404/0.004819 |

ThresholdMLP0.9363242388, AE6.2777276039 fit validation24benign+168attack, target empiricalFPR≤1%; không tune trên test. Test binaryconfusionMLP`[[24,0],[147,21]]`, AE`[[24,0],[168,0]]`; đầy đủ per-family/multiclass/trapezoidPR-AUC và native latency trongreport. AErecall0 phải giữ nguyên, không bỏ kết quả xấu. ROC diagnostic không đổi thresholddeploy. Dữ liệu nhỏ giả lập/không đại diện;0FP trên24benign không bảo đảmFPRproduction/zero-day.

Training6sessions: Python3.12.14/Linux, host32.44GBRAM/16logicalCPUaffinity trước cap (không xác nhận là Zenbook user), cap2threads/affinity[0,1], RLIMIT_AS hiệu lực12GiB=12884901888byte, không childtrainingworker. PeakRSS/process-tree cao nhất218906624byte=208.765625MiB; preprocessingpeak174911488byte. Allocation ceiling làsoftRLIMIT_AS từngprocess vàRSSguard tạistepboundary, **không phải hardcgroup quota cảgroup**. ONNXMLP17678byte/4296parameter; AE33136byte/8157parameter. Latency chỉwarmbatch1/model, không preprocessing/queue/coldstart. Longrun/thermal/hardcgroup/SSDpowerloss/throughputtargetNOT_RUN.

### 16.4. Lệnh kiểm tra và kết quả

Các lệnh dưới chạy từrepo hoặc `cd ai-training` như chỉ rõ; venv không sửa Python global. Phiên này không chạy lại Java/Rust vì không có service code change.

| Lệnh / kiểm tra | Trạng thái | Bằng chứng |
|---|---|---|
| `git status --short --branch`; `git branch`; `git log -n 5`; tạo `feat/ai-model-training` | PASS | Sạch tại basefbe078d, đúng branch user chỉ định |
| `.venv/bin/python -m pytest` qua `ai-training/scripts/check.sh` | PASS | **42passed/0skipped**,9.08s; private `.artifacts/final-checks.log` |
| `.venv/bin/ruff check src tests`; `.venv/bin/ruff format --check src tests`; `python -m compileall -q src` | PASS |33Pythonfiles formatted; khôngsyntax/lint error |
| `.venv/bin/python -m pip check`; `.venv/bin/idps-ai check-contract` | PASS | Exactpins, schema/producersnapshot hashes khớp |
| `.venv/bin/idps-ai s0 --output .artifacts/synthetic_s0_20261027_final --max-threads 2` | PASS | Actualsubprocess2+2epoch/cả2model+2references,960/960ONNXparity từngmodel; stderrfinalrỗng |
| Fault/integrationtests trong42tests | PASS | ActualSIGINT/SIGTERM, mid-epoch, maxduration0, earlystopterminal, runlock, latestcorruptfallback, badconfig/env/dataset/missingshard, simulatedENOSPC, abruptprocessdeathatfsync |
| TDD/intermediate gates | FAIL→PASS | REDAPIimports có chủ đích; tests bắt querymask bỏ feature, NATambiguity/weaklabelconflict, AEparity bỏ trainattacks và fixturediscovery sauformat; đã sửa, full42PASS trước finalS0 |
| `git diff --exit-code fbe078d -- student-web security-web` +SHAmanifest356trackedfiles | PASS | Không thay đổi bất kỳ code/config/script dịch vụ |
| Final source/config/test/bundle SHA, report SHA, scope và docs links; `git diff --check` | PASS |44 file mới chỉ trong AI +5docs;42 local links hợp lệ; artifacts/key không xuất hiện trong danh sách Git untracked được phép commit |
| `mvn test`; `cargo test` | NOT_RUN | Phiên AI không sửa service; Java89/Rust50 của mục15 là evidence lịch sử |
| Realcollect/realtrain, Rustport/parity/liveinference, longsessionthermal/cgroup, VM/AWS/hostenforce | NOT_RUN | Không suy diễn S0synthetic hoàn thành những gate này |

Không có test bị SKIPPED ở suiteAI cuối. ENOSPC được faultinject, không làm đầy ổ thực; kill tạifsync làprocesscrash, không chứng minh SSDsurvive mấtđiện. Không sử dụng .env hoặc secret dịch vụ; keydatasetAI doS0 tựsinh nằmprivateignored.

### 16.5. Danh sách file và bàn giao

Chỉ thêm trong `ai-training/`:

- `.gitignore`, `README.md`, `pyproject.toml`, `requirements.txt`; scripts`bootstrap.sh`, `check.sh`.
- configs`schema_contract.yaml`, `train_config.yaml`, `anomaly_config.yaml`; report`reports/S0_20261027.json`.
- `src/idps_ai/`: `__init__.py`, `__main__.py`, `common.py`, `cli.py`, `inference.py`, `smoke.py`.
- `data/`: `__init__.py`, `readers.py`, `privacy.py`, `dataset.py`, `split.py`, `synthetic.py`; `features/`: `__init__.py`, `pipeline.py`.
- `training/`: `__init__.py`, `models.py`, `checkpoint.py`, `resources.py`, `runner.py`, `evaluation.py`; `export/`: `__init__.py`, `onnx.py`.
- `tests/`: `conftest.py`, `test_cli.py`, `test_contracts.py`, `test_dataset.py`, `test_export.py`, `test_features.py`, `test_models.py`, `test_readers.py`, `test_safety.py`, `test_splits.py`, `test_training.py`; fixture`preprocessing_golden.json`.

Docs sửa:00/02/03/04/06. Inventory path đầy đủ+source/config/testhash trongreport. `.venv`, `.artifacts`, logs/Parquet/NPZ/ONNX/raw/HMACkey vàprotected-baseline.json đềuignored, không commit. Rootcontract/CI/scripts/Student/Security không sửa. ProtectedEdgealiasP3 chỉ xử lý ở trainingadapter riêng, sourceRust/Java giữ nguyên.

Bàn giao CLIcopy/paste tại [README](../ai-training/README.md): `s0` dùng outputdir mới; `collect` nhận snapshotpath tuyệt đối vàkeyAI riêng; `prepare` cần labelsidecar approved, đủ time/groups/benign-attackvalidation; `train` target20epoch/maxduration150phút, `--resume-from` cùngrun đểnối ca. AE dùngconfiganomaly vàrun-dir riêng. Chưa tựcollect/traindữ liệu thật hoặc tạo nhãnbenign từnoalert. Bước sau cần reviewer/data-readiness, snapshot/campaign độc lập vàstoreACL; giữmodel candidateoffline tới khi Rustpreprocessingparity/shadow được giao và nghiệmthu.


## 17. Chia commit luồng AI — 27/10/2026 13:15 +07:00

**Yêu cầu user:** git add và commit các thay đổi, chia nhỏ khi cần. Nhánh giữ nguyên `feat/ai-model-training`; base trước chuỗi commit `fbe078d8fe2e35bf60f7a08c7d21331f4522221e`. Không push, merge, đổi remote hoặc sửa danh tính Git. Chỉ đóng gói code đã nghiệm thu, cập nhật trạng thái bàn giao; không sửa thêm source Python/config/schema. Report S0 giữ nguyên sourcecommitfbe078d và working-tree hashes tại lúc đo, không gán lại kết quả lịch sử cho commit mới.

| Commit | Nội dung |
|---|---|
| `4d81ce2` | `feat(ai-data): add private datasets and causal feature pipelines` — adapters/privacy/correlation/labels/splits/Parquet/features, schema snapshot, pins và data tests |
| `4ab15ba` | `feat(ai-training): add CPU models with durable checkpoint resume` — MLP/AE, Adam/scheduler, integrity/cursor/RNG/atomic checkpoint, resource guards/evaluation và model/training tests |
| `bc15e8d` | `feat(ai-export): add ONNX parity and end-to-end S0 commands` — CLI/package/bootstrap/check scripts, ONNX/Python inference reference, S0 orchestration và fault/integration tests |
| Commit chứa mục này | `docs(ai): record synthetic S0 results and training handoff` — README, public report metadata và docs00/02/03/04/06 |

Để tránh commit phụ thuộc vào source chưa stage, mỗi mốc được xuất từ **Git index** sang thư mục tạm, dùng venv hiện có nhưng `PYTHONPATH` trỏ vào snapshot. Chỉ chạy tests thuộc mốc đã stage. Không checkout/reset/stash file làm việc. Hai commit thư viện đầu có thể kiểm qua Python module/tests; CLI và packaging xuất hiện tại commit thứ3.

| Kiểm tra phiên commit | Trạng thái | Bằng chứng |
|---|---|---|
| Data index snapshot | PASS |6tests,0.07s; private `.artifacts/commit-data-index-tests.log` |
| Training index snapshot | PASS |6tests,1.74s; gồm2+2epoch bằng4epoch liên tục ở cả2model; `.artifacts/commit-training-index-tests.log` |
| Full code index snapshot | PASS |**42tests**,0skipped,9.15s; gồm subprocess S0/fault signals/ONNX; `.artifacts/commit-full-index-tests.log` |
| Ruff check/format; pip check | PASS |33Pythonfiles đã format; không broken dependency |
| Source/config/test SHA với report S0; public report SHA/bundle hashes | PASS |Code đúng bản đã đo S0; report không sửa chỉ để làm đẹp lịch sử Git |
| `git diff --exit-code fbe078d -- student-web security-web contracts docker .github scripts .gitignore` +356servicefileSHA | PASS |Không thay đổi code/config dịch vụ hoặc root contract/infra |
| Staged path/artifact/credential screening; `git diff --cached --check` | PASS |Chỉ44fileAI+5docs; không key/rawlog/Parquet/NPZ/ONNX/.venv/.artifacts; secret-pattern scan không match credential |
| Java/Rust tests, real training, VM/AWS deploy, Rust integration | NOT_RUN |Không sửa dịch vụ; không tính các kết quả foundation cũ là test chạy lại |

Không có FAIL/SKIPPED mới trong phiên đóng gói commit. Không rerun caS0 lớn960requests vì source không đổi; giữ evidence S0 mục16, suite42tests đã chạy lại ở index snapshot và bao gồm S0 nhỏ thực qua subprocess. Các snapshot tạm đã xóa sau test, logs còn localignored. Hash service giữ nguyên, không restart dịch vụ hay chạm DB/firewall. Working tree sạch sau commit cuối; người dùng tự push nhánh khi sẵn sàng. Còn lại real corpus/data-readiness/target-machine long benchmark và Rust integration như mục16.


## 18. Chuẩn bị trước train: corpus lab + gate — 27/10/2026 20:23 +07:00

**Yêu cầu user:** hoàn thiện các bước trước train, chỉ luồngAI; sau khi biết chưa
códata/labels,user cho phép tựtạo/chạy/thu. OwnerCodex,khôngspawnagent; chưa có
reviewer thứhai. Branch`feat/ai-model-training`,base`b5d4a64f6b711b14a8a6d04cc6a66807f6cd2e73`.
Tại thời điểm nghiệm thu pre-training chưa commit/push; yêu cầu đóng gói tiếp theo được ghi riêng ở19. Chỉ sửa `ai-training/` vàdocs00/02/03/04/06;
SHA356fileStudent/Security,canonical/rootinfra giữ nguyên. Không dùng.env/credential
hoặcDBứngdụng. Chỉ khởi động/dừng fixturedoAI sởhữu,trongprivateartifacts.

### 18.1. Triển khai và scope dữ liệu

Thêm snapshotreadonlyprefix/checksum/readback; manualreviewCSV/contextbinding;
observerlabels/captureprovenance; datagate/capacity và Nginx4flagvalbaseline;
CLI`lab-start/capture/finish/stop`. BuildStudent từGitexport dướiAIartifacts,
khôngbuildtrongStudenttarget. PostgreSQL17disposable512MiB/1CPU,Javaheap512MiB/2CPU,
Nginxloopbackports18880/18881/55435. Seed15accountgiả với3ADMIN/6STAFF/6STUDENT,
facultygiả,mail/resetworkflowtắt. Scope chỉHTTPloopback,noroutescanngoàilab.

Actual capture **19:48:25.664→20:17:59.430+07:00**,wall1773.766626s;
15campaign×325observedrequests=4.875. Ba bands9/3/3,hai khoảngchờ620giâythật;
sourceIP127.0.0.10–24 đượcbindthật,user/sessionriêng. Khôngđổitimestamp/IP;
khônggánno-alertthànhbenign. ObserverlấyrequestIDtrảvềvàHTTPoutcome;nhãnscriptedintent
vàexpectedstatus,khôngclaimexploitthànhcông.435HEAD/OPTIONScatalog403đượcsửa
expectedcontractnarrow,savedcount/sourceSHA; ngoàiđó khôngunexpectedoutcomes.
Giữobservergốc,khôngghiđèđểgiấupending.3Student/2NginxwarmupngoàideclaredIDs
đượcscopeoutvớirawhash/count;mọipendingcase trongcapture vẫnđượcgiữ.

**4.875approved intentlabels**,0unknown scopedrequests,9.750observations.
Parquettrain2.925/val975/test975;groups9/3/3;benign1.917/639/639;
mỗiattackfamily144/48/48. VariantIDs/scriptedviews khôngchéo temporalpartitions;
chỉ3view/family,khôngphảibao phủmọibiếnthể. Role/dataset/skew/shortwindowlimitations
đượcgiữtrongreport;corpuskhôngđại diệnproduction.

Featuregap phát hiệntrướcfreeze: UA familylưutrữnhưngchưathànhmodelinput.
Đãbổsungmultihot21family+missing/unknown=23cột,mởallowlistmasscan/acunetix/zgrab,
matchproductboundariesđểcampus-nmaple-browserkhôngthànhnmap. Tăngderivedfeature
**ai-features-2/148cột**,normalizer2,goldenvectorsv2. Canonicalv1.0khôngđổi;
modelrunmớiMLP148→32→8=5.032params,AE148→32→148=9.652params,chưafitcorpusnày.
Khôngforce-resumev1checkpoint. SID/ruleflags/identityvẫnkhônglàmodelinput.

### 18.2. Evidence hiện hành

Publicreport [PRETRAIN_20261027.json](../ai-training/reports/PRETRAIN_20261027.json),
SHA-256`b7f6e28c1380c39d8838e06bdde66be8f6e88c6c03ff822bfba9bb95455acadd`. DatasetSHA
`599166880745d6da7042c39c0639478f2150e5d518db8050d839ca56460926db`;readinessfileSHA
`470ad7a872accfdadd440dd4d510e72032a7f82b6cb2c7c6235aa70c9487a038`. Source/config/test/provenance/artifacthash,
counts,metricsvànextCLIargvtrongreport. Privateartifactroot thật:
`ai-training/.artifacts/pretrain_lab_20261027_v2_ready/`; chưa sharedstore/upload.
Raw/keys/accounts/Parquet không vàoGit. BáocáoS0v1khôngsửabằngsốv2.

**READY_FOR_OFFLINE_PILOT:23checksPASS**, parserquality0invalid/partial/oversized,
source/roles/labels/confidence/reads/mutations/benignerrors đủngưỡng,identity/group/
variantdisjoint,finitevectors vàreplayparity.58testsPASS,0skipped. CapacityPASS:
cacheestimate2.925.000byte,sampledRSS156.57MiB;đây làI/O/capacityestimate,khôngphải
peaktrainingRSS,epochspeed,thermal hoặchardcgroupbenchmark.

Nginx4mapflags trên**validationonly975rows**:confusion`[[639,0],[144,192]]`,
precision1,recall0.5714285714,FPR0trênfixture. KhôngfullRust/Suricataensemble;
khôngtínhmetricstest/tunethreshold vàkhôngdùngflagslàmnhãn.0FP trên639benignlab
khôngchứngnhậnFPRproduction. Modelqualitychưađo,khôngtạochampion.

### 18.3. Commands và trạng thái

| Lệnh / kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| ProtectedsourcebaselineSHA/Gitstatus/log đọc trước sửa | PASS | Baseb5d4a64,sạch banđầu;branchđúng |
| IsolatedStudent `./mvnw -q -DskipTests package` | PASS | Build trongAIprivateGitexport;Java25,không sửaStudenttarget/source |
| Actuallabcapture15campaign | PASS |4.875HTTPrequests,4875uniqueobserverIDs; haiwait620s,khôngtrain |
| `idps-ai lab-finish ...pretrain_lab_20261027_v2` lầnđầu | FAIL→PASS | ReadinessđãPASSnhưngcapacitychiađôiaffinityđãcaplần2. Đãsửa dùngpre-capinventory,thêmregressiontest,khônglowergate hoặc sửa data |
| `idps-ai lab-finish ...pretrain_lab_20261027_v2_ready` | PASS | Snapshot/labels/collect/prepare/23gate/capacity/baseline/reviewqueue/nextcommands;outputversionmới,handofftraining_executed=false |
| `ai-training/scripts/check.sh` | PASS | **58tests,0skipped,8.52s**,ruff/format/compileall/schema+protectedgitdiff; private`.artifacts/pretrain-final-checks-v2.log` |
| TDD newboundarytests | FAIL→PASS | ExpectedREDmissingmodule/UAfeatures/capacityarg;testschođúngpublicAPI/CLI,khôngmockinternalpipeline |
| CLIownedlifecycle recheck từsourcecuối | PASS | `lab-start` trênfixturemới,CSRF200/login204/catalog200/createfaculty201,`lab-stop` đúngPID/create-time/containerlabel |
| Dọnmainlab vàrechecklab | PASS | Student/Nginx/DBđềustopped;dockerpskhôngcòncontainerlab;khôngdừngservicekhác |
| Deriveddatasecretscan | PASS | Actualfixturepassword vàtrainingkeykhôngxuấthiệnởpreparedParquet/readiness;khônginsecret |
| Protected356fileSHA;gitdiffStudent/Security/contracts/rootinfra | PASS | Khôngthayđổisource/configluồngA |
| Final source/test/artifact hashes, report hash, docs links, secret/ignored scope | PASS |51local links;14newfileschỉAI+5docs;actualfixturesecretskhôngxuấthiệntrongchanged/untrackedtext;pipcheckPASS;gitdiffwhitespacePASS |
| Suricatalivecapture | NOT_RUN | Rootlesspacketsocketdenied;khôngthaysettings/permissions,chưacóEVEthậtvàkhôngfake |
| `mvn test`;`cargo test` | NOT_RUN | Dịchvụkhôngsửa;Javafreshbuild+HTTPsmokeđãchạy,khônggánbaseline89/50thànhtestphiênnày |
| Fittingcorpusmới/champion/Rustinference/productionacceptance | NOT_RUN | **0giờtraincorpus**,khôngcóweights/ONNXmới từcorpusnày |

Regressiontests cóoptimizer/S0fixture nhỏ để kiểm cơchế,khôngphảifitcorpusscenario.
Cácbảnartifacts trướcfix giữlịch sử;chỉ`...v2_ready` làđầuvàobàngiao hiện hành.

### 18.4. Giới hạn và quyết định trước khi train

D09 IMPLEMENTED: chấpnhận **offline labpilot**,khôngtuyênbốproductionready.
Lab cóqueryviewNginx riêng vớiprobesgiả;edgehiệnhànhmaskquery. Cầnđốichiếuinput
availability hoặcđổifeatureprofiletrướcdeployment. EVE/flowthiếu phải giữmissing;
khôngcoihttp/tabularpilotlànetworkbenchmark. STUDENTkhôngcóprofilepersonfixture,
profile404/hardnegativecóđịnhnghĩa;behaviorallabellàbulkreadattemptscripted,
khôngprovenIDOR/zero-day. Campaignngắn khiếnwindow60/300contextincomplete;
76cộtconstant đượcreport,khônggiấuthoáihoácoverage. Cầnhumancoverage/realismreview,
phiêndài,representativelabels,ablation vàquality/FPR trướcproduction.

`configs/experiment_plan.yaml` plannedNOT_STARTED:5epoch đầu,mỗiarchitecture
run-dirriêng,2threads,max150phút,12GiB. Khôngépđủ150phút. Modelselectiontrênval,
testkhóacholầnđánhgiácuối. Rule/fullensemblecomparison vàRustparity làgate sau.
`NEXT_COMMANDS.txt`/handoffJSON cóargv `train --readiness-report ... --epochs 5`,
đãchuẩnbịnhưng**chưathựcthi**. Reportgắndataset/sourcehash;codethayđổiphảiauditlại.

Filescode/configthêm: `data/snapshot.py`, `review.py`, `provenance.py`,
`readiness.py`, `capacity.py`, `baseline.py`, `lab_capture.py`, `lab_runtime.py`,
`pretrain.py`;`configs/pretrain_policy.yaml`,`experiment_plan.yaml`;
`tests/test_pretrain.py`;`PRETRAINING.md`;reportmetadata. SửaCLI,privacyPRODUCTS,
featurepipeline/datasetderivedversion,goldenfixture vàREADME;docs00/02/03/04/06.
KhôngthêmMLdependency,khôngcàipackageshệthống;nginxexisting/Studentexport/PGimage
đượctáidùng.ExtractSuricataUbuntu vàoAIprivateđểkhảosát nhưngkhôngdùngthayEVEcapture.


## 19. Commit pre-training và định hướng cloud — 27/10/2026 20:46 +07:00

Người dùng yêu cầu git add/commit các thay đổi hiện có, chưa viết code cho dự tính
cloud. Nhánh giữ nguyên `feat/ai-model-training`, base trước chuỗi commit là
`b5d4a64f6b711b14a8a6d04cc6a66807f6cd2e73`. Không thay code chức năng trong phiên
đóng gói này, không train corpus, không khởi động lab lại, không push hoặc merge.
Chỉ cập nhật trạng thái bàn giao và ghi định hướng người dùng trong tài liệu.

| Commit | Nội dung |
|---|---|
| `dd4c719` | `feat(ai-features): add private user-agent features in schema v2` — UA allowlist/boundaries,148features, normalizer2 và golden vectors |
| `59f3da2` | `feat(ai-data): add isolated lab collection and pretraining readiness gates` — CLI/lab lifecycle, snapshot, labels/provenance/review, readiness/capacity/baseline, configs và tests |
| Commit chứa mục này | `docs(ai): record pretraining corpus validation and handoff` — README/PRETRAINING/public report metadata và docs00/02/03/04/06 |

Mỗi index được export sang thư mục tạm, dùng venv hiện có nhưng PYTHONPATH trỏ vào
snapshot. Mốc feature chạy **42tests PASS/8.58s**; mốc pre-training chạy **58tests
PASS/9.05s**,0skipped. Logs private `.artifacts/commit-features-v2-tests.log` và
`.artifacts/commit-pretrain-index-tests.log`. Các snapshot tạm đã dọn. Không đưa
source chưa stage vào kiểm chứng cho commit trước.

Kiểm tra bổ sung PASS: source/test SHA khớp public report;356protectedservicefileSHA
không đổi; gitdiff rootcontracts/Student/Security/infra rỗng; pipcheck;
stagedwhitespace/scope, actualfixturepassword/trainingkey screening và loại trừ
rawlogs/Parquet/NPZ/ONNX/.venv/.artifacts. Report PRETRAIN/S0 giữ nguyên hash và
trạng thái source tại thời điểm đo, không gán lại evidence lịch sử cho GitHEAD mới.
Java/Rust service tests NOT_RUN trong phiên chỉ commit; kết quả tương ứng ở các
entry trước vẫn là lịch sử. Không có FAIL/SKIPPED mới trong phiên đóng gói.

**Định hướng user cho công việc tiếp theo, chưa triển khai:** bổ sung dữ liệu còn
thiếu và rà/cập nhật model trước khi bắt đầu train; sau pilot có thể thu dữ liệu
trên lab cloud do nhóm sở hữu để cải thiện model. Dữ liệu cloud cần provenance,
privacy, nhãn/holdout và kiểm tra feature availability (TLS/EVE/query masks).
Đổi dataset không dùng `--resume-from` như cùng run hiện tại: cần bổ sung workflow
fine-tune/retrain với parent model, version mới và đánh giá cả dữ liệu cũ/mới.
Không tự học từ mọi traffic live hoặc tự coi alert là nhãn. Model mới được so với
bản cũ, shadow/review rồi mới promote/rollback theo quyết định sau. Chưa tạo cloud
resource, chạy kiểm thử cloud hoặc nâng cấp thuật toán trong phiên commit này.


## 20. Ba nguồn thật + featurev3 + pilot — 2026-10-28T11:10:41.404613+07:00

OwnerCodex, tự review; chưa reviewer độc lập; không spawn agent. Branch`feat/ai-model-training`, base`b9617ccd6afeebf0207e5fd2fd220e8639f61eea`; thay đổi chưa commit/push. User cho phép bổ sung data/model, xử lý quyền nếu cần và chạy pilot; ca train chính thức chỉ chuẩn bị lệnh.

**Trạng thái28/10/2026:** corpus mới có **19.275 request thật / 80.556 observations**, đủ Student audit + Nginx + Suricata EVE từ PCAP thật trong namespace lab. Split **11.565 / 3.855 / 3.855**, nhóm 9/3/3; mỗi campaign ≥420 giây, hai khoảng nghỉ 620 giây thật. Feature v3 / normalizer3, 148 cột, `edge_masked_v1`; canonical v1.0 giữ nguyên. Readiness **35 checks PASS**, **77 tests PASS / 0 skipped**. MLP/AE/residual đều chạy 2 epoch → tiến trình mới resume đến 5 epoch, exact với reference 5 epoch; ONNX parity toàn bộ prepared rows. Chỉ đánh giá validation; test metric chưa mở. [Report có hash](../ai-training/reports/PRETRAIN_PILOT_20261028.json).

Chưa chạy ca chính thức 2–3 giờ, chọn champion, port Rust hoặc bật AI response. Corpus vẫn là loopback với fixture giả / scripted intent; chưa đại diện production. Query bị mask thống nhất nên metadata AI không thấy nội dung payload. Flow chỉ lấy flow client đã kết thúc ≥65 giây trước đó, không backfill bằng đóng flow tương lai. Live receipt-time/TLS/feature parity và human realism review còn riêng.


### 20.1. Capture, privacy và provenance

Capture2026-10-28T10:15:00.258847+07:00→2026-10-28T10:56:41.661908+07:00,wall2501.403061s.15campaign,IP/user/session riêng,1280workload +5setup/logout mỗi campaign;9/3/3band,haiwait620s thật. ActualStudentbuild/DBgiả, Nginx thật, PCAP tronguser/netnamespace riêng; Suricata8.0.3decode offline nguyên9SID. Không syntheticEVE, không sửaIP/timestamp, không xóa pending dựa label/status/rule.

Sourcecounts`{'NGINX': 19275, 'STUDENT_AUDIT': 19275, 'SURICATA': 42006}`; parserquality`{'accepted': 80556, 'duplicates': 0}`. Flow coverage: train: 9757/11565, val: 3233/3855, test: 3236/3855. Readiness35PASS, sourcebinding/PCAP/EVE/labels/featureSHA và parity kiểm đầy đủ. DatasetSHA`eb494a87534b156b3a4f6b1f5746bf798c2f8971ff266f645a603725b840b5c5`. PCAP ghi nhận16packetdrops/199523captured; mộtHTTP thiếuSuri nhưng khôngxóarequest/khôngfake. Dataset đầu`dataset` bịNOT_READY do cộnggrace65s lần2; đãsửathànhavailable_at=max(EVEtimestamp,flow.end+65), giữnguyênrawtimestamp vàgatemin75%, tạo`dataset-ready`; modelarithmeticsourceđổi thìauditsang`readiness-final`. PCAP và credentialfixture chỉprivate; EVE được lọc trước disk, sourcequeryprofileđồngnhất. Thay đổi source capture sau khi worker load chỉ thêm lifecycle/progress/privacy/model; inventory version capture và sourceprocessing giữ riêng.

RootlessPodman host-network capability không cấp hostpacket socket. User đã tự thêm `signal (receive) peer=chatgpt,` vào `/etc/apparmor.d/local/usr.bin.tcpdump`, reload profile và dừng4probe. Không tắt AppArmor/không grant capturehost. FailedlabNginxUIDnobody được dọn, chạy capture mới vớiuserroot chỉ trongnamespace mappeduid1000. GenericSuricatacustomheaderkhôngtrảRID; sửa bằngprivateUnixEVE+allowlistresponseheaders, testcanaryredirect/host/cookiePASS. User service AppArmorkhôngcho tạo namespace nênpackettests/captureởcontextCodexđãđượcphép;train/exportởsystemdquota, khôngbroadeningrootpolicy.

### 20.2. Pilot và tài nguyên

Pilot-ready3model đều2epoch→processmới resume đến5, so exactweights/Adam/RNG/scheduler/permutation/best/patience với5continuous; ONNX19,275/19,275 mỗi model. MLP5.032/AE9.652/residual14.216params; AE/scalerbenigntrainonly.6phiên chính +3reference. Pilotwall47.449917s, optimizerchính0.573298903s (0.000159249695h); referenceoptimizer0.569272400s tách riêng; không cộngdataprep/PCAP/export vàooptimizer. Productiondatatrain0h. Attemptpilotcũcóoptimizer0.265067463s vàreference0.256101581s, ghi riêng; tổngmainoptimizercorpuslabkểcảattemptfail0.838366366s. AttemptcũAEparityFAIL21elements(max3.22e-6); đãsửaaffineaccumulationFP64→roundFP32, gradient/Adam/weightsvẫnFP32, khôngnớitol1e-5/1e-6. Có4096-rowwide-range regression. Oldpilot/sourcegiữlịchsử, khôngforce-resume.

| Model | Global step | Precision val | Recall val | FPR val | Latest checkpoint manifest SHA |
|---|---:|---:|---:|---:|---|
| autoencoder | 750 | 0.693878 | 0.101190 | 0.009425 | 56f5e3b5c95ac8835093e6fa3359083c47a3adeb9153059575013f58d3a71513 |
| mlp | 905 | 0.906832 | 0.434524 | 0.009425 | f8d8b55b8500782c9401d195262e717c58523543f9204cd10edea455f67036b0 |
| residual | 905 | 0.906542 | 0.433036 | 0.009425 | 96ea6d5d507f676281f75cb286975f825aeb47eea2281dae4c76652bce555fed |

Validation dùng cùngcalibration nên chỉsơbộ; testmetricsNOT_RUN. Missing-input sensitivity không phảiablationretraining. Rule-or-AI cóbudgetFPRflag; Nginx+SuricatabaselinekhônggánthànhfullRustensemble. Khôngchọnchampion/promote/enforce.

PilotuserunitCPUQuota 200%,MemoryMax 12 GiB,MemoryHigh 10 GiB,swap0,Nice10; readbackcpu.max/memory.max/swap vàmemory/cpustat trongsessionreport.16CPUhost→2CPU≈12,5%;RAMcapdưới50%. Captureclient/proxy2CPUaffinity; Javafixtuređượcsiết2CPU trongembargocuối, khônggánquotađómộtcáchhồtốchotoànbộcapture. Khôngbenchmarkthermal/endurance2–3giờ.

### 20.3. Commands và kết quả

| Lệnh/kiểm tra | Trạng thái | Evidence |
|---|---|---|
| ĐọcPRETRAINING/report27/docs + source/branchstatus | PASS | Baseb9617cc,workingtreesạchbanđầu |
| `idps-ai lab-start .../upgrade_20261028/lab` | PASS | GitexportStudentbuild+disposablePG,khôngđụngDBuser |
| `capture_lab(...duration=420,requests=1280)` | PASS | actualobserver/PCAP/hash,nguyên15campaign |
| `idps-ai decode-pcap ... --output .../lab/eve` | PASS | actualSuricata8.0.3,HTTP/flow/alerts/stats |
| `idps-ai lab-finish ... --output .../dataset` | FAIL | NOT_READY: grace65s bị cộng hai lần; giữ artifact cũ, không train |
| `idps-ai lab-finish ... --output .../dataset-ready`; `readiness .../readiness-final` | PASS | 35gate/capacity/rulebaseline/reviewqueue; source sau sửa precision được bind lại |
| `systemd-run --user ... CPUQuota=200% MemoryMax=12G ... idps-ai pilot ...` | PASS |3model5epoch,resumeexact,ONNXallrows;sourceđãfreeze |
| `IDPS_AI_TEST_SURICATA_RUNTIME=... taskset -c 0,1 ai-training/scripts/check.sh` | PASS |77 tests,0skipped;ruff/format/compileall/contract/protecteddiff;`.artifacts/upgrade_20261028/checks-final-supported-context.log` |
| Fullsuite trongsystemduserunit | FAIL→PASS theo đúngcontext |2packettests bịAppArmordenyuserns; khôngnới policy; rerun contextđãđượcphép. Testlauncherportabilitysửa1threadassertdướiaffinity2 |
| TDD/gradient/privacy regression | FAIL→PASS | missingmodule/model/headerprojection; finite-differencegradient; secretcanarybefore-disk |
| `pip check`,shellsyntax,derivedsecretlogicalscan,356protectedSHA | PASS | reportmetadata cóhash;khôngraw/key/modelvàoGit |
| Dọnfixture | PASS | `{'database': 'already_stopped', 'student': 'already_stopped'}`; khôngcònownedcontainer/tcpdump/nginx/java |
| `mvn test`;`cargo test` | NOT_RUN | Student/Securitysourcekhôngđổi;Studentisolatedbuild+HTTPthậtđãchạy |
| Ca chính thức/champion/Rust/live/cloud/thermal | NOT_RUN | Chỉchuẩnbịscript;khôngclaimproductionready |

Publicreport [PRETRAIN_PILOT_20261028.json](../ai-training/reports/PRETRAIN_PILOT_20261028.json),SHA`b19ac674e67c0780249a009b9025ec08f9d9ea936188c4bb36d076d6f7f73fb6`. Localprivateartifactroot`ai-training/.artifacts/upgrade_20261028`; sharedstorechưacấp. Report27/S0giữhashvàýnghĩalịchsử.

### 20.4. Bàn giao

Lệnhđầutiênđãchuẩnbị,**chưathựcthi**: `bash ai-training/scripts/train-first-session.sh`. Residualcandidate100epoch/patience8,maximum150phút,2CPU/12GiB/checkpoint 300s,hardcgroup+readback. Gateformalbuộcba nguồn/windowdài/currentSHA; khôngdùngpolicyhai nguồn cũ. Cólatestthìresumeđúngrun; đổilearning/source/data bịtừchối. Xongsớmthìdừng,khônglặpchođủgiờ.

Cònreviewthựctế/campaignđộc lập, studentprofileđầyđủ, TLS/receipt-time/Rustparity, cloudcorpusvàfine-tuneworkflow. Querymaskedkhôngthànhpayloadmodel; anomalykhôngtựlàattack/zero-day. ChỉHTTPfixtureloopback,khôngproductionbenchmark.

Danh sáchfilethayđổi của phiên:

- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/experiment_plan.yaml`
- `ai-training/configs/formal_residual_config.yaml`
- `ai-training/configs/residual_config.yaml`
- `ai-training/configs/three_source_policy.yaml`
- `ai-training/reports/PRETRAIN_PILOT_20261028.json`
- `ai-training/scripts/train-first-session.sh`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/baseline.py`
- `ai-training/src/idps_ai/data/campaigns.py`
- `ai-training/src/idps_ai/data/dataset.py`
- `ai-training/src/idps_ai/data/lab_runtime.py`
- `ai-training/src/idps_ai/data/pretrain.py`
- `ai-training/src/idps_ai/data/provenance.py`
- `ai-training/src/idps_ai/data/readers.py`
- `ai-training/src/idps_ai/data/readiness.py`
- `ai-training/src/idps_ai/data/sensor_decode.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/data/split.py`
- `ai-training/src/idps_ai/export/onnx.py`
- `ai-training/src/idps_ai/features/pipeline.py`
- `ai-training/src/idps_ai/inference.py`
- `ai-training/src/idps_ai/pilot.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/resources.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/session.py`
- `ai-training/tests/fixtures/preprocessing_golden.json`
- `ai-training/tests/test_cli.py`
- `ai-training/tests/test_export.py`
- `ai-training/tests/test_models.py`
- `ai-training/tests/test_pretrain.py`
- `ai-training/tests/test_sensor_lab.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`


## 21. Resource8CPU/16GiB, cleanup và commit — 2026-10-28T12:28:35.118730+07:00

User yêu cầu nâng resource, xóa stale/cache và chia4commit trên`feat/ai-model-training`;
**tuyệt đối không chạy ca train chính thức**. OwnerCodex, tự review, không spawnagent.
Base trước chuỗi là`b9617cc`; ba commit chức năng đã tạo, commit chứa mục này chốt docs.

### 21.1. Policy và bằng chứng không training

- CPU8logical trên16affinity: `CPUQuota=800%`, `Nice=10`; chấp nhận`--cpus6/8`,
  `--cpus` là alias của`--max-threads`. Giữ trần nửa CPU affinity và tối đa8thread.
- `MemoryMax=17179869184` (16GiB), `MemoryHigh=16106127360` (15GiB),swap0.
  User chỉ định16GiB; OS-visibleRAM`32440909824`byte,
  tỷ lệ thực tế**52.96%**, không gán sai thành50%.
- OMP/OpenBLAS/MKL/NumExpr8; ORT intra8/inter1, sequential, tránh pool8×8.
  CPU/memory/high/swap được đọc lại trong guard; RLIMIT_AS16GiB và affinity bổ sung.
- Probe dùng chính cgroup envelope của session nhưng chạy`probe_resources`, không
  đọc dataset vào optimizer, không tạo run chính thức: **optimizer_steps=0**.
  `cpu.max=800000 100000`,memory.max/high/swap đúng như trên.
  Report guard xác nhận BLAS8 và ORT8/1. Ca dài/thermal/throughput8CPU vẫnNOT_RUN.

Nguồn chuẩn bị thay đổi nên report cũ được giữ nguyên và tạo
`dataset-ready/readiness-resource8/readiness.json`: **35/35checks PASS**,
SHA`387ba70ff41a599700328953b6de1e46508fabc0c6dcb8c9447c27afba3afa30`. DatasetSHA vẫn
`eb494a87534b156b3a4f6b1f5746bf798c2f8971ff266f645a603725b840b5c5`. `FINAL_TRAINING_HANDOFF.json` vàscript ca đầu trỏ gate mới,
đồng thời lưu đường dẫn readiness-final gốc. Không nới gate hoặc sửa timestamp/labels.

Báo cáo [RESOURCE_GUARD_20261028.json](../ai-training/reports/RESOURCE_GUARD_20261028.json),
SHA`d0370e9849da7df9dab8442a7557768c4327f78a2677e712c42b35389174b36c`. Report PRETRAIN_PILOT giữ nguyên số đo2CPU/12GiB và metric pilot cũ;
không gán chúng thành benchmark8CPU. Checkpoint pilot là bằng chứng lịch sử; source
mới không force-resume checkpoint cũ. Ca tiếp theo là experiment mới đã chuẩn bị.

### 21.2. Cleanup có kiểm kê

Đã dọn **625file/directory entries**, khoảng
**682.87MiB**. Chi tiết trong localignored
`.artifacts/resource_upgrade_20261028/cleanup-result.json`.

Nhóm chính đã xóa:

- `upgrade_20261028/dataset`, `pilot`, `pilot-failed-source`,
  `failed-namespace-nginx-user`, `parity-diagnostics`, cácprobe/decoded-prefix cũ.
- `dataset-ready/readiness` stale và`NEXT_COMMANDS.txt`/handoff cũ không còn dùng;
  không xóa readiness-final hoặc readiness-resource8.
- Các lab/recheck27/10, pretrainv2 failed/v2_ready đã stale và syntheticS0 duplicate;
  giữ S0final nhỏ và report lịch sử chính thức.
- Gitexport/build tạm của lab, PCAPprefix/ONNXdiagnostic, cácgói.deb cache đã extract,
  scriptsdebug/log tạm đã dừng; giữ nativeSuricata runtime và realcapture evidence.
- `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.pyc/.tmp/.bak/.coverage` phát sinh.
  Xóa3bytecode tracked trong`.agents/skills/ui-ux-pro-max/scripts/__pycache__`,
  giữ toàn bộ source skill. Venv không bị xóa; chỉ dọn bytecodecache bên trong.

**176tệp được bảo vệ giữ nguyên toàn bộ SHA**, gồm tất cảprepared/pilot-ready,
readiness-final gốc và cácreport chính thức. Giữ source/config/test/script đang
hoạt động, datasetparent/provenance/key, realPCAP/EVE/audit/observer và runtime.
Handoff được cập nhật theo yêu cầu, không bị xóa. Không đổi356file Student/Security,
canonical schema, serviceconfig, DB hoặc firewall.

`.gitignore` root và AI bổ sung artifact/venv/rawPCAP/Parquet/ONNX/checkpoints/weights,
secretkey/privatecredentials/runtime logs/cache. Giữ ngoại lệ fixture canonical
được review và `.env.example`. Scan Git index không thấy actualfixturepassword,
trainingkey hoặc binaryartifact mới. Dữ liệu/model/raw vẫn localignored, chưa push.

### 21.3. Kiểm tra và commit

| Kiểm tra | Trạng thái | Bằng chứng |
|---|---|---|
| TDD publicsession policy6/8CPU và16GiB | FAIL→PASS | RED thiếualias`--cpus`, GREEN validator/command/env/ORTpolicy;17GiB vàCPUvượt nửa bịtừchối |
| Fullpytest trên source hiện hành | PASS | **77passed/0skipped/17.92s**, fixture nhỏ; log`resource_upgrade_20261028/pytest.log` |
| Guardprobe systemd8CPU/16GiB/high15GiB/swap0 | PASS |0optimizerstep; cgroupreadback thực, BLAS8/ORT8/1 |
| Data-readiness35checks | PASS | gate mới gắn dataset/source; chuẩn bị readonly, khôngfit |
| Snapshot index commitdata | PASS | **58tests/8.58s**, PYTHONPATHtrỏ source từindex, không dùngfile chưa stage |
| Snapshot index commitmodel/resource | PASS | **63tests/8.72s** |
| Snapshot index commitlab/tests | PASS | **77tests/36.20s**, tempcheckout dọn sau test |
| Ruff/format/pipcheck/bashsyntax/gitdiffcheck | PASS | Không thêm dependency; không sửa numerical model/dataset để nâng tài nguyên |
| Protected176SHA, Student/Security356SHA, indexsecret/artifact scan | PASS | Không có file protected thay đổi; chỉcachetracked3file bị xóa theo yêu cầu |
| Full corpuscapture/pilot/formaltrain | NOT_RUN | User cấm trainchínhthức; chỉtinyregressionfixtures vàguardprobe0step |
| Push/cloud/enforcement | NOT_RUN | Chỉ commit local, không thay luồngIPS |

| Commit | Nhóm |
|---|---|
| `cea18c4` | `feat(ai-data): add three-source pipeline and feature schema v3` |
| `1d526b3` | `feat(ai-train): add residual model and 8-CPU/16GiB resource guard` |
| `6f432a2` | `test(ai-pilot): add lab capture, 77 tests and pretrain evidence` |
| Commit chứa mục21 | Docs00–06, README root/AI vàPRETRAINING, policy8CPU/16GiB và cleanup/handoff |

Lệnh user có thể chạy sau, **chưa thực thi trong phiên này**:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-first-session.sh
```

Trần150phút,100epoch/patience8,checkpoint300giây. Có thể xong sớm; không lặp cho đủgiờ.
Sau commit docs phải kiểm `git status` sạch và`git log -n6`; cácartifact được giữ
sẵn sàng cho experimentoffline, không là nghiệm thuproduction hoặc champion.

File thay đổi/xóa trong chuỗi commit này (so với b9617cc):

- `.agents/skills/ui-ux-pro-max/scripts/__pycache__/core.cpython-314.pyc`
- `.agents/skills/ui-ux-pro-max/scripts/__pycache__/design_system.cpython-314.pyc`
- `.agents/skills/ui-ux-pro-max/scripts/__pycache__/reasoning_contract.cpython-314.pyc`
- `.gitignore`
- `README.md`
- `ai-training/.gitignore`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/anomaly_config.yaml`
- `ai-training/configs/experiment_plan.yaml`
- `ai-training/configs/formal_residual_config.yaml`
- `ai-training/configs/residual_config.yaml`
- `ai-training/configs/three_source_policy.yaml`
- `ai-training/configs/train_config.yaml`
- `ai-training/reports/PRETRAIN_PILOT_20261028.json`
- `ai-training/reports/RESOURCE_GUARD_20261028.json`
- `ai-training/scripts/train-first-session.sh`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/baseline.py`
- `ai-training/src/idps_ai/data/campaigns.py`
- `ai-training/src/idps_ai/data/capacity.py`
- `ai-training/src/idps_ai/data/dataset.py`
- `ai-training/src/idps_ai/data/lab_runtime.py`
- `ai-training/src/idps_ai/data/pretrain.py`
- `ai-training/src/idps_ai/data/provenance.py`
- `ai-training/src/idps_ai/data/readers.py`
- `ai-training/src/idps_ai/data/readiness.py`
- `ai-training/src/idps_ai/data/sensor_decode.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/data/split.py`
- `ai-training/src/idps_ai/export/onnx.py`
- `ai-training/src/idps_ai/features/pipeline.py`
- `ai-training/src/idps_ai/inference.py`
- `ai-training/src/idps_ai/pilot.py`
- `ai-training/src/idps_ai/smoke.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/resources.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/session.py`
- `ai-training/tests/fixtures/preprocessing_golden.json`
- `ai-training/tests/test_cli.py`
- `ai-training/tests/test_export.py`
- `ai-training/tests/test_models.py`
- `ai-training/tests/test_pretrain.py`
- `ai-training/tests/test_safety.py`
- `ai-training/tests/test_sensor_lab.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

Kiểm tra trước commit docs: PASS176artifactSHA,356serviceSHA,35gate,79local links,0cache còn lại,0optimizerstep probe,workingtree chỉ còn docs đang chờ commit. Không có lab container hoặc idps-ai user unit đang chạy.


## 22. Ca train residual đầu tiên — 29/10/2026

**Owner:** Codex; tự kiểm, chưa có reviewer độc lập. **Source commit:** `8171289400453d41c3a095af040c6a85e2880b77`, nhánh `feat/ai-model-training`. Người dùng yêu cầu kiểm data rồi bắt đầu ca150phút theo dự tính. Không thay tracked source/config của trainer, Student hoặc Security; không tạo traffic mới, đổi DB/firewall hay triển khai model. Các tài liệu/report mới chưa commit/push trong lượt chạy này.

### 22.1. Data và chuẩn bị job

- Đối chiếu manifest và SHA dataset `eb494a87534b156b3a4f6b1f5746bf798c2f8971ff266f645a603725b840b5c5`:19.275request,148cột; train11.565/val3.855/test3.855. Ba nguồn thật từ capture lab ngày28, canonical1.0/features3/normalizer3, `edge_masked_v1` giữ nguyên.
- Chạy lại toàn bộ35checks, bao gồm provenance/group identities/variants/embargo, ba nguồn, flow availability, finite vectors và replay exact mọi vector. **35/35PASS**,0nonfinite/0mismatch. Snapshot/report cũ không bị ghi đè.
- Preflight mới: `ai-training/.artifacts/upgrade_20261028/formal/preflight-20261029-171850/`; report gate ở `readiness/readiness.json`, capacity ở `capacity.json`.
- Một lần wrapper kiểm tra report bị `IsADirectoryError` do truyền output directory như JSON file. Đã sửa đường dẫn của artifact do phiên này tạo; gate đã chạy không bị sửa dữ liệu hoặc hạ tiêu chí. Kiểm lại đường dẫn/checksum PASS. Đây là lỗi gọi helper, không phải failure chất lượng corpus.
- `pip check` PASS. Máy có AC online, RAM khả dụng khoảng16GiB, disk trống khoảng165GiB khi preflight. Không dừng các service demo/VM đang dùng.
- Launcher vận hành nằm private trong preflight, dùng lại `session_command()` và policy gốc; thay stdio pipe bằng file log, chạy systemd user service độc lập, giữ kết quả exit để kiểm. Không sửa module bị khóa source hash.
- Probe cùng envelope và sleep inhibitor **PASS,0optimizerstep**: CPUQuota800%, affinity0–7, MemoryMax16GiB/High15GiB/swap0/Nice10, BLAS8. Job có `systemd-inhibit sleep:idle` khi còn chạy; inhibitor nhả sau exit. Không đổi power setting lâu dài.

### 22.2. Lệnh và trạng thái

Các lệnh vận hành từ gốc repo, dùng venv hiện có và `PYTHONDONTWRITEBYTECODE=1`:

```bash
ai-training/.venv/bin/python -m pip check
# audit_readiness(prepared, preflight/readiness, lab_capture,
#                 configs/three_source_policy.yaml, prepared_provenance.json)
# validate_formal_readiness(...) + capacity_check(...) ở preflight wrapper.
ai-training/.venv/bin/python ai-training/.artifacts/upgrade_20261028/formal/preflight-20261029-171850/launch_service.py --probe
ai-training/.venv/bin/python ai-training/.artifacts/upgrade_20261028/formal/preflight-20261029-171850/launch_service.py
```

Actual systemd argv, env policy, timestamps và log paths được lưu trong `guard-launch.json`, `service-launch.json`, `export-launch.json`; không có secret. Probe/train/export đều `Result=success`, `ExecMainStatus=0`. Train unit: `idps-ai-train-residual-20261029-172104.service`; export unit: `idps-ai-export-residual-20261029-172249.service`. Các unit tạm đã kết thúc mới được dọn sau khi chụp result; không còn optimizer hoặc sleep inhibitor của ca này.

| Kiểm tra / thao tác | Trạng thái | Kết quả |
|---|---|---|
| Dataset hash/source gate + full replay | PASS |35checks;19.275vector hữu hạn,0replay mismatch |
| Capacity/dependencies | PASS |Capacity estimate và pip check |
| Caller report-path attempt | FAIL → RESOLVED |Sửa output-directory/file path; không sửa data/source hoặc gate |
| Detached service + resource/inhibitor probe | PASS |0optimizerstep; readback8CPU/16GiB/high15/swap0/Nice10 |
| Formal residual | PASS |Exit0;14epoch/2.534steps;early_stopping |
| latest/previous/best integrity | PASS |Manifest/hash và NPZ load; architecture148→64→64+skip→8,14.216params |
| ONNX best checkpoint | PASS |19.275/19.275;rtol1e-5/atol1e-6;max abs1.7881393e-7 |
| Artifact preservation | PASS |172prepared/pilot fileSHA và4report lịch sử giữ nguyên |
| pytest / mvn / cargo | NOT_RUN |Không đổi tracked source;77tests ngày28 là bằng chứng lịch sử, không tính là rerun ở phiên này |
| Test quality metrics | NOT_RUN |Chỉval; test vectors dùng cho parity, không dùng nhãn test để chọn model/threshold |
| Endurance150phút / live / enforcement | NOT_RUN |Run dừng sớm; chưa champion/Rust live hoặc thay firewall |

### 22.3. Run ledger và kết quả

| Run / session | Thời điểm +07:00 | Actual wall / optimizer | Tiến độ / lý do |
|---|---|---|---|
| `8ea1ded50c7b43aabd98d2ef93236ef9` / `142fb445007b47e880c986c76b48436d` |2026-10-29 17:21:05.862726 →17:21:17.479104 |11.616398388s /0.885849402s |14epoch,2.534steps;early_stopping,patience8 |

Ngân sách150phút/100epoch là trần, không phải số giờ thực tế. Wall≈0.00322678h,optimizer≈0.000246069h; không ghi2,5h vào ledger. Corpus là real HTTP lab với fixture giả, không phải production data. Checkpoint tốt nhất ởepoch6/step1.086; latest ởepoch14/step2.534. Best theo APvalidation, không tự trở thành champion production. Cgroup train peak131.305.472byte (~125,22MiB), process-tree RSS peak196.595.712byte (~187,49MiB), là hai phép đo khác nhau. Không có OOM hoặc throttling ghi nhận trong report. Không coi phép đo ngắn là nghiệm thu thermal150phút.

| Metric validation3.855request, threshold0.5809128284 | Giá trị |
|---|---|
| Precision / recall |90,8257% /44,1964% |
| FPR |0,942507%;30false positives trên3.183benign |
| AP / F1 |0,7756679232 /0,5945945946 |
| TP / FN / TN / FP |297 /375 /3153 /30 |
| Warm ONNX batch1 p95 |0,01519ms; model-only, không bao gồm preprocessing/queue |

Bị đánh dấu attack theo từng họ (không đồng nghĩa phân loại đúng tên họ): scanner96/96,brute-force96/96,behavioral96/96;SQLi1/96,XSS4/96,traversal1/96,command3/96. Recall các họ payload còn thấp, phù hợp giới hạn metadata đã mask query nhưng chưa khẳng định một nguyên nhân duy nhất. Chất lượng validation dùng cùng tập calibration nên là sơ bộ; test quality vẫn niêm phong. Không bỏ masking hoặc mở thêm telemetry chỉ để làm số đẹp.

### 22.4. Artifact và bước tiếp

- Public metadata: [`ai-training/reports/FORMAL_RESIDUAL_20261029.json`](../ai-training/reports/FORMAL_RESIDUAL_20261029.json).
- Private run: `ai-training/.artifacts/upgrade_20261028/formal/residual-seed17/`, gồm `session_report.json`, pointers/checkpoints, `train.log`, `onnx-best/` (model/feature spec/calibration/evaluation/golden/model card) và launch/result JSON. Local-only, không đưa weights/data/key vào Git.
- `FINAL_TRAINING_HANDOFF.json` đã chuyển sang trạng thái completed/early-stopping, lưu bản trước trong preflight. Prepared/pilot/report28 giữ nguyên.
- **Không chạy lại script ca đầu để force-resume run terminal này.** Chỉ tạo experiment khác sau khi review learning curves, telemetry khả dụng và các họ đang bỏ sót. Không tăng epoch chỉ để đủ150phút. Chưa tự khởi chạy model/seed khác hoặc mở test/chọn champion.
- Các guide HTML trong `docs/learning-materials` giữ snapshot biên tập28/10; trạng thái vận hành mới lấy từ report và mục này.


## 23. Nâng cấp corpus/telemetry/model sau ca dừng sớm — 29/10/2026

**Owner:** Codex, theo yêu cầu nâng cấp và chuẩn bị tiếp tục train; luồng AI.
**Chốt bàn giao:** 2026-10-29T20:42:08+07:00. Branch `feat/ai-model-training`.
Capture export tại `8171289400453d41c3a095af040c6a85e2880b77`; processing source
chưa commit, có inventory/snapshot riêng cho từng pilot. HEAD khi chốt là
`fd0fea47dbc30a56dc8a9bed819b15cf3dc66d11`. Không tự add/commit/push ở phiên này.

### 23.1. Nguyên nhân và thay đổi

Ca cũ11,616giây không hỏng optimizer/checkpoint/ONNX: mạng14.216tham số,
patience8, best epoch6 và dừng ở14. Train AP0,869809, validation AP0,775668;
59/148feature hằng số, toàn bộ query payload counters bằng0. Campaign ít và
lặp thứ tự/UA nên tăng giờ học không giải quyết đủ các giới hạn này.

- Thêm opt-in `safe_query_numeric_v1`: Suricata raw URL đi qua shared numeric
  projection trong bộ nhớ **trước redaction**; EVE/Parquet chỉ giữ28 số finite và
  allowlist metadata. Không lưu plaintext query, Cookie/Set-Cookie/body/alert text.
  Credential fields/PII bị loại trước tính số; operator decode bounded hai lần.
- Feature/normalizer v4 vẫn148cột, canonical1.0 giữ nguyên. Missing projection
  có cờ, không dựng lại raw query hoặc dùng rule flag/SID làm model input.
  Profile cũ giữ hành vi. Flow chỉ từ client flow đã kết thúc, causal delay65s.
- Mở rộng30campaign,18/6/6,480giây thật, hai gap620giây thật, plan riêng, UA bình
  thường đa dạng, public reads, CRUD, legitimate batch, hard negatives và payload
  variants. Bootstrap stagger, bounded GET-CSRF retry có observer và relay backlog128.
- Dùng hash payload **sau decode/lowercase**: phát hiện96traversal probe val trùng
  train. Giữ chúng trong log/causal context nhưng bỏ nhãn train/evaluation; evidence
  lưu HMAC request key, identity, band và lý do. Không sửa timestamp/IP hoặc hạ gate.
- Weighted residual dùng inverse-sqrt weights chỉ từ class counts train, weighted
  CE/Adam hiện có. Checkpoint lưu weights/objective running loss/history để exact
  resume giữa epoch; ghi validation objective cùng unweighted all-class loss.
  AE chỉ fit benign; không thêm thư viện nặng hoặc CNN/TCN chưa có dữ liệu tương ứng.
- Thêm sensitivity query/flow/actor/response và per-campaign validation metrics.
  Sensitivity inference-only, không phải ablation retraining; đọc cả FPR/recall.

### 23.2. Capture, nhãn và gate

Capture thật **2026-10-29T18:03:03.394253+07:00 → 2026-10-29T18:47:46.783711+07:00**.
46.230request,198.765observations: Student46.230, Nginx46.230, Suricata106.305
(HTTP46.230/flow46.230/alert13.844/stats1). PCAP119.837.834byte,
478.857packet captured,0kernel drops. Parser accepted198.765,0duplicates,
không ghi invalid/oversized/partial. Nhãn pending do HTTP contract0;96overlap
exclusions; **46.134approved feature rows**. Split27.738/9.150/9.246;30connected
identity groups,18/6/6, không giao identity/approved payload variant giữa các tập.
Campaign ngắn nhất479,588giây; có đủ cửa sổ10/60/300giây và reset ở split boundary.

Readiness **48/48 PASS**, `READY_FOR_OFFLINE_PILOT`; constant columns38/148.
Coverage và diversity thực:

- `train_payload_diversity`: `{'cmd_injection': 8, 'path_traversal': 6, 'sqli': 8, 'xss': 8}` — PASS.
- `val_payload_diversity`: `{'cmd_injection': 8, 'path_traversal': 6, 'sqli': 8, 'xss': 8}` — PASS.
- `test_payload_diversity`: `{'cmd_injection': 8, 'path_traversal': 8, 'sqli': 8, 'xss': 8}` — PASS.
- `train_query_projection`: `{'available': 27738, 'total': 27738}` — PASS.
- `train_past_flow_coverage`: `{'available': 24234, 'reserved_delay_seconds': 65, 'total': 27738}` — PASS.
- `val_query_projection`: `{'available': 9246, 'total': 9246}` — PASS.
- `val_past_flow_coverage`: `{'available': 7922, 'reserved_delay_seconds': 65, 'total': 9246}` — PASS.
- `test_query_projection`: `{'available': 9246, 'total': 9246}` — PASS.
- `test_past_flow_coverage`: `{'available': 8064, 'reserved_delay_seconds': 65, 'total': 9246}` — PASS.

Dataset SHA `b6608d0204781c5c71a9892913ba9ad521be74ff355f737c10a5cc8c4c6465ad`.
PCAP SHA `ae920478081282f635fb647fdda61178c09b65cfd5191d82c41b0f0bbb1d13c1`.
EVE SHA `f5e31361403be5a4120e5be4200a6eadab6b73c4fb515cc22234113006f329f8`.
Readiness file SHA `a5ff10fa1eec7e58895c8657d9603904e931a05d08d15457386b9e9fa71ad825`.

### 23.3. Pilot và chọn ứng viên cho ca tiếp

Bốn ứng viên chạy5epoch:2epoch → process mới resume đến5; reference5epoch riêng.
Tất cả weights, Adam, RNG/sampler/history tương đương chính xác. ONNX parity
**46.134/46.134rows PASS mỗi model**, rtol1e-5/atol1e-6; classifier maxabs1,1921e-7,
AE9,5367e-7. Test vectors dùng cho parity, **không dùng nhãn test để tính quality**.
Pilot wall163,571698s; optimizer các phiên chính2,093619s, reference2,071487s riêng.
Cgroup pilot peak570,6MiB, swap0; không coi đây là endurance150phút.

| Model, validation9.150rows | AP | Precision | Recall | FPR |
| --- | ---: | ---: | ---: | ---: |
| mlp | 0.997807 | 97.946% | 99.344% | 0.823% |
| autoencoder | 0.784669 | 89.764% | 21.991% | 0.991% |
| residual | 0.998749 | 98.130% | 99.228% | 0.747% |
| weighted_residual | 0.998349 | 97.749% | 98.843% | 0.900% |

Residual không trọng số có AP cao nhất, được chuẩn bị cho **experiment tiếp**,
không phải champion production. Confusion[[6509,49],[20,2572]], threshold/calibration
chọn trên cùng validation nên metric sơ bộ. Learning curve và lỗi từng campaign/
họ/benign HTTP errors có đầy đủ trong report. Weighted loss chưa chứng minh tốt
hơn residual trên pilot này; AE recall thấp, không tự gọi anomaly là attack.

Residual khi thiếu query/URI projection: recall23,53%,FPR0,122%; thiếu actor:
recall85,88%,FPR8,798%; thiếu flow:FPR3,248%; thiếu response:recall91,20%,
FPR0,229%. Đây là rủi ro mất nguồn/shortcut cần xử lý trước serving, không ẩn đi
bằng recall tăng. Dữ liệu scripted và một topology chưa chứng minh generalization.

Phép chẩn đoán **PCAP cũ** riêng: residual5epoch recall95,39%,FPR0,817%; bỏ
query/URI projection còn26,93%. Không coi19.275request re-project là corpus mới;
old corpus bị NOT_READY theo gate diverse mới. Source snapshot37file của phép
chẩn đoán được khôi phục đúng hash, tách source cuối dùng xử lý corpus mới.

### 23.4. Lệnh kiểm tra, lỗi đã giải quyết và trạng thái

Các log dưới `ai-training/.artifacts/upgrade_20261029_query/` (private).

| Lệnh / kiểm tra | Trạng thái | Bằng chứng |
| --- | --- | --- |
| `IDPS_AI_TEST_SURICATA_RUNTIME=... OPENBLAS_NUM_THREADS=8 bash ai-training/scripts/check.sh` | PASS |93pytest,0skipped; Ruff/format/compileall/canonical/protected diff; `checks-final-source.log` |
| `MIGRATION_TEST_URL=jdbc:postgresql://127.0.0.1:55437/student_test MIGRATION_TEST_USER=postgres ./mvnw -q test` trong Student backend | PASS |100test,0skipped trên HEADfd0fea4; DB riêng; `mvn-test-current-head.log` |
| `DATABASE_URL='postgres://postgres@127.0.0.1:55436/postgres?sslmode=disable' cargo test --locked --jobs 8 -- --test-threads=4` trong Security | PASS |50test,0ignored trên HEADfd0fea4; DB riêng; `cargo-test-current-head.log` |
| `lab-capture-eve --campaign-seconds 480 --requests-per-campaign 1536` với30campaign | PASS |namespace lab riêng, real HTTP/PCAP; `capture-v2-finished.json`,0packet drops |
| `decode-pcap ... --query-numeric`; `lab-finish ...` | PASS |ba nguồn, immutable snapshots, labels/provenance và48gate; `final-pipeline-result.json` |
| `pilot ... --cpus 8 --include-weighted-residual` trong cgroup8CPU/16GiB | PASS |4model5epoch/exactresume/full-rowONNX; `pilot/pilot-report.json` |
| `probe_session` với dataset/config/launcher ca tiếp | PASS |0optimizerstep; `resource-probe.json`:quota800%,8affinity,MemoryMax16GiB,High15GiB,swap0,BLAS/ONNX8/inter1 |
| Report digest / dataset-source binding / handoff hash / cleanup | PASS |`TRAINING_HANDOFF.json`, report public và inventory |
| Ca formal corpusv4 / test quality / Rust serving / champion | NOT_RUN |chỉ chuẩn bị ca tiếp; không force-resume ca cũ, không promote/enforce |
| Git add/commit/push | NOT_RUN |không nằm trong yêu cầu phiên này |

Attempt đầu FAIL sau mộtGET-CSRF502 do relay bootstrap khi đồng thời18campaign;
17campaign hoàn tất nhưng **không cấp chứng nhận corpus**. Giữ evidence trong
`lab/`; tăng backlog và test45connections, bounded GET retry rồi thu lại `lab-v2/`.
Không nới quyền host packet capture/AppArmor hoặc cần sudo mới. Rust lần đầu
FAIL vì thiếu DB; retry DB riêng vướng SSLRequest, sửa envsslmode=disable cho
DB loopback disposable rồi50PASS. Java lượt đầu89tests gồm7SKIPPED do thiếu
MIGRATION_TEST_URL; rerun89/0skip tạibase8171289, rồi100/0skip tạiHEADfd0fea4.
AI test command từng trỏ nhầm tên file không tồn tại (NOT_RUN), đã chạy đúng suite;
Ruff format gate từng FAIL, đã sửa và toàn suite PASS. `check.sh` guard cũ so
với ref foundationfbe078d gâyFAIL vì frontend đã đổi hợp lệ từ trước; chuyển so
HEAD, cộng inventory SHA riêng, không hoàn nguyên frontend. TDD negative cases
phát hiện thiếu weighting/encoded operators/v4contract/holdout dedup trước khi sửa.

### 23.5. Scope, file thay đổi và artifact

Trong phiên dài, repository nhận fast-forward `8171289`→`fd0fea4` từ
`origin/feature/rust-idps`.21file trong inventory cũ khác do các commit UI/email/
firewall này; **không có diff ứng dụng/contract chưa commit** tại chốt.
Không ghi461artifact cũ; tất cả vẫn đúng SHA. Capture build riêng là8171289,
không gán kết quả capture đó cho mã ứng dụng mới. Các kiểm thử ứng dụng đã rerun
trên HEAD mới. Runtime/source snapshots của AI ghi hash37file, không chỉ dựaHEAD
vì AI changes hiện chưa commit. Schema1.0/Nginx/Suricata config/rules không bị sửa
bởi công việc AI. `FORMAL_RESIDUAL_20261029.json` là thay đổi có trước từ mục22,
được giữ nguyên. Các file thuộc phần chuẩn bị/nâng cấp hiện hành:

- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/formal_mlp_config.yaml`
- `ai-training/configs/query_experiment_plan.yaml`
- `ai-training/configs/query_numeric_policy.yaml`
- `ai-training/configs/weighted_residual_config.yaml`
- `ai-training/reports/PRETRAIN_UPGRADE_20261029.json`
- `ai-training/scripts/check.sh`
- `ai-training/scripts/train-query-session.sh`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/campaigns.py`
- `ai-training/src/idps_ai/data/dataset.py`
- `ai-training/src/idps_ai/data/lab_runtime.py`
- `ai-training/src/idps_ai/data/pretrain.py`
- `ai-training/src/idps_ai/data/privacy.py`
- `ai-training/src/idps_ai/data/provenance.py`
- `ai-training/src/idps_ai/data/query_numeric.py`
- `ai-training/src/idps_ai/data/readers.py`
- `ai-training/src/idps_ai/data/readiness.py`
- `ai-training/src/idps_ai/data/sensor_decode.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/data/split.py`
- `ai-training/src/idps_ai/features/pipeline.py`
- `ai-training/src/idps_ai/pilot.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/session.py`
- `ai-training/tests/test_campaign_upgrade.py`
- `ai-training/tests/test_cli.py`
- `ai-training/tests/test_models.py`
- `ai-training/tests/test_pretrain.py`
- `ai-training/tests/test_query_numeric.py`
- `ai-training/tests/test_sensor_lab.py`
- `ai-training/tests/test_training.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

Public report: [`PRETRAIN_UPGRADE_20261029.json`](../ai-training/reports/PRETRAIN_UPGRADE_20261029.json),
file SHA `bc271a4e9632a0e751a67e8e0e689838127b3b1a7ccb99d58c78517238ac89ec`;
`report_sha256` bên trong kiểm digest nội dung bỏ field digest.
Private root: `ai-training/.artifacts/upgrade_20261029_query/`, gồm `lab-v2/`,
`dataset-ready/`, `pilot/`, `processing-source/`, `replay-source/`, `replay-data/`,
`replay-pilot/`, các log và `TRAINING_HANDOFF.json`. PCAP chứa HTTP/session của
fixture giả,0600; source/output dưới private root0700. Raw,key,Parquet,weights,
PCAP không nằm trong Git. Không dọn evidence failed attempt hoặc artifact cũ.
Container/process của lab và regression DB đều đã dừng; không đụng dịch vụ người dùng.

### 23.6. Lệnh ca tiếp theo — đã chuẩn bị, chưa khởi chạy

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-query-session.sh
```

Đích `upgrade_20261029_query/formal/residual-seed17`, datasetv4 và readiness mới,
config `formal_residual_config.yaml`/patience8,100epoch/max150phút,8CPU/16GiB, checkpoint300s.
Sleep inhibitor chỉ giữ trong lúc lệnh chạy. Có checkpoint hợp lệ thì resume đúng
run; source/data/config khác bị từ chối. Early-stop là terminal, không force tiếp.
150phút là trần, model nhỏ vẫn có thể xong trong vài giây; không train vòng lặp
để lấp thời gian. Chưa bật formal mới, không hẹn thông báo/automation khi chưa yêu cầu.

Trước production còn thiếu corpus người dùng/môi trường đa dạng, review nhãn độc
lập, replication seed, final-test sau freeze, Rust/shared transform/TLS vantage/
receipt-time và nghiệm thu mất nguồn. Raw body/credentials không được phục hồi;
numeric projection không tương đương hiểu ngữ nghĩa toàn bộ payload. Không chạm
live inference, dashboard, kernel/firewall hoặc tự deploy trong phiên AI này.


## 24. Corpus 60–80k, 189 đặc trưng và mô hình sâu — 2026-10-30T09:08:21+07:00

**Owner:** Codex, tự kiểm; chưa có reviewer độc lập. Nhánh
`feat/ai-model-training`, HEAD `fd0fea47dbc30a56dc8a9bed819b15cf3dc66d11`. User yêu cầu chỉ
nâng cấp AI, giữ nguyên Student/Security và không chạy train dài. Trước phiên đã
có thay đổi AI/docs chưa commit từ mục 22–23; giữ nguyên, không reset/stash.
Không git add/commit/push, deploy hoặc thay đổi kernel/firewall trong phiên này.

### 24.1. Quyết định và triển khai

- Đã đọc docs 00–06, pilot 28, FINAL_TRAINING_HANDOFF lịch sử và báo cáo corpus
  46k. Vì feature 4 / 148 cột đã có checkpoint, mở revision **4.1 / 189 cột**,
  projection v2 và normalizer 4.1 với hash riêng; giữ artifact cũ.
- Bổ sung 41 số cấu trúc Query/URI trước redaction: encoding, phân bố ký tự,
  hình dạng tham số, SQL comments/operators/parens, HTML/entities/event assignment,
  path segments và shell punctuation. Loại secret/PII trước phân tích; không trả
  về raw text/body hoặc cờ rule/SID. Offline và live Python bridge dùng chung
  envelope 69 numeric keys; không dựng lại query từ chuỗi đã mask. Canonical 1.0
  giữ nguyên.
- Deep MLP: 189→256→256→256→256→8 (248.072 tham số); DAE:
  189→256→256→128→256→256→189 (294.717); gated residual ba block (445.448).
  Residual nhỏ 16.840 tham số là đối chứng. Chưa triển khai attention/sequence
  model; ngữ cảnh vẫn gồm các aggregate nhân quả 10/60/300 giây.
- DAE chỉ fit benign: Gaussian σ=0,1, xác suất mask=0,1 trên normalized inputs,
  target sạch. Inference không noise; score MSE không là xác suất attack.
  PCG64 theo seed/committed optimizer step; checkpoint ghi corruption contract.
  Có kiểm thử resume giữa epoch và qua process mới.
- Params, activations, gradients và Adam FP32; affine reduction FP64 rồi làm tròn
  FP32; gated sigmoid FP64→FP32. Deep classifier dùng stable log-sum-exp CE;
  lỗi tự tin với margin 1000 có loss 1000, không bị clipping thành 27,63.
  Giữ ONNX tolerance rtol=1e-5, atol=1e-6.
- 45 campaign có seed/plan riêng; nhịp lognormal và jitter, thứ tự kịch bản xáo
  trộn, key/order/paging tham số và bốn endpoint catalog. Có 16 payload views mỗi
  họ/band và 12 hard-negative views/band. So sánh identity sau decode; attack và
  hard-negative holdout không dùng chung identity. Embargo 300 giây giữ nguyên;
  hai gap thực 620 giây bao cả hai phía cutoff, không sửa timestamp/IP.
- Cấu hình mô hình lớn: batch 128, LR 0,0005, gamma 0,98 mỗi 200 step, patience 15.
  Script formal giới hạn 150 epoch / 150 phút, 8 CPU / 16 GiB, checkpoint mỗi
  300 giây; chưa thực thi. Không ép model chạy đủ giờ hoặc thêm dependency nặng.

### 24.2. Capture và dữ liệu

Capture **2026-10-30T08:11:17.535147+07:00 → 2026-10-30T08:56:02.919968+07:00**, fixture riêng từ Git export
`fd0fea47dbc30a56dc8a9bed819b15cf3dc66d11`. PostgreSQL và tài khoản/hồ sơ giả mới.
Nginx và HTTP chạy trong rootless user/network namespace; PCAP thật được Suricata 8
đọc offline. Chỉ env của fixture tăng audit cap lên 256 MiB; không sửa source/config
ứng dụng hoặc dùng DB live.

| Hạng mục | Kết quả đo thực |
| --- | --- |
| Corpus | 69,345 request; 297,685 observations từ Student, Nginx và Suricata thật |
| Split và nhãn | 69,345 vectors có nhãn được duyệt; train: 41,607 / val: 13,869 / test: 13,869; groups 27/9/9 |
| Đặc trưng | ai-features-4.1 / normalizer 4.1, 189 cột, projection v2; canonical 1.0 giữ nguyên |
| Mô hình | Residual nhỏ đối chứng; MLP 248.072 / DAE 294.717 / gated residual 445.448 tham số |
| Readiness | 53/53 PASS; payload và hard negatives có identity riêng giữa các temporal bands |
| Pilot | 4 mô hình × 5 epoch; resume qua process mới khớp reference; ONNX 69,345/69,345 vectors PASS từng mô hình |
| Kiểm thử và phạm vi | 118 pytest PASS, 0 skipped; giữ nguyên hash 366 file dịch vụ/contract và 1.946 artifact cũ |
| Train dài / chất lượng trên test / deploy | NOT_RUN; chưa chọn Champion Model hoặc nghiệm thu Rust/live/enforcement |

Sources: `{'NGINX': 69345, 'STUDENT_AUDIT': 69345, 'SURICATA': 158995}`. EVE: `{'alert': 20303, 'flow': 69345, 'http': 69345, 'stats': 2}`.
Packets: `{'captured': 717792, 'dropped_by_kernel': 4, 'received_by_filter': 1435588}`. Parser: `{'accepted': 297685, 'duplicates': 0}`.
Pending theo HTTP contract: 0; overlap exclusions:
0. Campaign ngắn nhất: 479.382 giây.
Có 46/189 cột hằng, danh sách trong báo cáo; không
che giấu các cột chưa biến thiên. Gate yêu cầu ít nhất 15 cột structure biến thiên,
9 groups/partition, 12 payload views mỗi họ và 12 hard-negative views/partition,
cùng coverage ba nguồn, flow và cửa sổ thời gian.

- Dataset SHA: `f143742a7dd5c130a3adcbc40b611f14938a4759a50816efada9b59308b18f50`.
- PCAP SHA: `a224671b8759c8f3e2bc1fd5057f585e3a8b94ee195be1bc5cc0723f21dbfc26`.
- EVE SHA: `7875e21bed6e18798d742734b2f7db49c53d6a216541bc0d474373a2a808ffee`.
- Readiness SHA: `012ed55f63440388ef154d1bec5f402bbaf92f1c5e6c4cbfe1b38734199c22cc`.

Ground truth dùng scripted intent có provenance, không suy ra từ status, không có
alert hoặc rule hit. Chưa chứng minh exploit thành công, realism được người duyệt
hoặc chất lượng tương đương traffic production.

### 24.3. Pilot, tài nguyên và đánh giá sơ bộ

Bốn model: 2 epoch → process mới resume tới 5; reference 5 epoch riêng.
Parameters, Adam, RNG/sampler/scheduler/history khớp chính xác. ONNX parity toàn bộ
69,345 vectors PASS mỗi model. Test vectors chỉ dùng parity;
chưa dùng test labels để tính chất lượng, chọn candidate hoặc threshold.
Wall time 391.454 giây; optimizer chính
26.005729 giây, reference riêng
29.627361 giây. Run IDs, checkpoint/config/source
hashes và cgroup readbacks nằm trong báo cáo.

| Candidate | AP val | Precision | Recall | FPR |
| --- | ---: | ---: | ---: | ---: |
| deep_mlp | 0.998798 | 97.68% | 99.11% | 0.966% |
| denoising_autoencoder | 0.907042 | 96.06% | 58.68% | 0.986% |
| gated_residual | 0.999077 | 97.61% | 99.16% | 0.996% |
| residual | 0.999165 | 97.64% | 99.55% | 0.986% |

Ứng viên lớn cho thí nghiệm tiếp: `gated_residual`. AP supervised tốt nhất kể cả đối
chứng: `residual`. Chưa chọn champion hoặc deploy. Validation
chia sẻ calibration nên các số đo còn sơ bộ. Đọc cả recall và FPR trong phép thử
mất nguồn và lỗi theo campaign.

Resource probe cùng session envelope: **PASS, 0 optimizer step**;
CPUQuota 800%, affinity ≤8 CPU, MemoryMax 17.179.869.184 bytes,
MemoryHigh 16.106.127.360 bytes, swap=0; BLAS/ORT 8 threads, ORT inter-op 1.
Bốn pilot chạy tuần tự trong cgroup 8 CPU / 16 GiB / Nice 10.
16 GiB là giới hạn user chỉ định, khoảng 52,96% RAM OS nhìn thấy; pilot ngắn chưa
kiểm định nhiệt độ hoặc độ bền ca 150 phút.

### 24.4. Kiểm tra và trạng thái

Logs private dưới `ai-training/.artifacts/upgrade_20261030_deep/`.

| Lệnh / kiểm tra | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Đọc docs/reports/source, protected SHA trước sửa | PASS | 366 file dịch vụ/contract và 1.946 artifact baseline |
| `lab-start --campaigns 45` | PASS | Git export/build riêng; DB/ports riêng; `lab-start.log` |
| `capture_lab(...duration=480,requests=1536)` | PASS | Private namespace, 45 campaign; `capture-finished.json` |
| `decode-pcap ... --query-numeric --projection-version 2` | PASS | Suricata thật; EVE redacted trước ghi disk; decode manifest |
| `lab-finish ...` / `validate_formal_readiness` | PASS | 53 gates, provenance/labels/split/replay/variants; pipeline result |
| `pilot --candidate-set expanded --cpus 8` | PASS | 4 model × 5 epoch, resume chính xác, ONNX toàn bộ vectors |
| `IDPS_AI_TEST_SURICATA_RUNTIME=... OPENBLAS_NUM_THREADS=8 bash ai-training/scripts/check.sh` | PASS | **118 pytest, 0 skipped**; Ruff/format/compileall/canonical; `checks-final.log` |
| `pip check`; `bash -n`; `git diff --check` | PASS | Không thêm dependency hoặc sửa config dịch vụ |
| Resource probe cùng session envelope | PASS | 0 optimizer step; `resource-probe.json` / `guard-probe.log` |
| Secret screen dữ liệu dẫn xuất | PASS | Mật khẩu giả thực tế không xuất hiện trong prepared Parquet/metadata; không in secret |
| Protected SHA | PASS | Giữ nguyên 366 file và 1.946 artifact; không ghi đè FINAL 28 hoặc pilot/báo cáo cũ |
| `mvn test` / `cargo test` | NOT_RUN | Không sửa Student/Security; Java 100 / Rust 50 ở mục 23 là lịch sử |
| Formal dài / chất lượng trên test / Rust live / deploy / enforce | NOT_RUN | User yêu cầu chưa train dài; chỉ chạy pilot và technical fixtures |
| Git add/commit/push | NOT_RUN | Không được yêu cầu trong phiên này |

Các lỗi trong giai đoạn RED đã được sửa: thiếu v2 projection, giữ encoded URI,
deep model hoặc graph ONNX; comparison count từng tính dấu `=` phân cách key/value
(đã chỉ đếm trong values); fixture kiểm thử resume AE từng chạm cuối epoch thay vì
giữa epoch (đổi seam còn một step); gate v2 chưa prepare từng gây UnboundLocalError
(đã trả NOT_READY); CE clipped không phản ánh lỗi tự tin (đã dùng stable CE).
Ruff/format từng FAIL; sau sửa, toàn bộ 118 tests PASS. Không skip hoặc hạ gate.
Source xử lý được freeze sau các bản sửa để dùng đúng implementation đã kiểm thử.
Hash năm file capture vẫn đúng bản worker đã load. Lần capture ngày 29/10 dừng
dở khi máy tắt, không có manifest hoàn tất nên không được chứng nhận hoặc đưa
vào train. Ngày 30/10 thu lại đầy đủ trong root mới;
artifact dở dang giữ riêng kèm `INTERRUPTION.json`. Capture thử đầu ngày 30/10
qua systemd user service **FAIL** ở bước UID mapping của namespace (không có dữ
liệu được chứng nhận); fixture đã dọn. Chạy lại bằng detached process kế thừa
AppArmor context hiện có cùng sleep inhibitor thành công; không đổi policy host.
Bằng chứng startup lỗi nằm tại `failed-namespace-start/`. Kiểm thử regression
encoded credential separator từng **FAIL**, sau sửa chỉ cắt credential tail
trước tính số thì PASS; traversal encoded vẫn giữ tín hiệu.

### 24.5. Bàn giao và danh sách file

Báo cáo [`PRETRAIN_EXPANDED_20261030.json`](../ai-training/reports/PRETRAIN_EXPANDED_20261030.json),
file SHA `2431d367e95a2c48340f78f96243cf6eb50c82fefb5f1d65a8b7313ba75b24ef`.
Manifest [`FINAL_TRAINING_HANDOFF.json`](../ai-training/FINAL_TRAINING_HANDOFF.json),
file SHA `a3f2c940a23b3857ac0a16615509421e6ec2ec0c3e5e88becbf35cadd9a1bf42`. Bản private cùng
nội dung nằm trong root mới. FINAL 28 và handoff query cũ là lịch sử, giữ nguyên hash.
Artifact root local, được Git ignore: `ai-training/.artifacts/upgrade_20261030_deep/`.
PCAP có credential/session fixture giả nên private 0600; raw data, key và weights
không đưa vào Git. Teammate cần chuyển artifact an toàn hoặc tự thu lại; không mặc
định có dataset/model sau Git pull.

File thay đổi của đợt nâng cấp này (không liệt kê mọi dirty change từ mục 23):

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/deep_mlp_config.yaml`
- `ai-training/configs/denoising_config.yaml`
- `ai-training/configs/expanded_experiment_plan.yaml`
- `ai-training/configs/expanded_policy.yaml`
- `ai-training/configs/gated_residual_config.yaml`
- `ai-training/reports/PRETRAIN_EXPANDED_20261030.json`
- `ai-training/scripts/check.sh`
- `ai-training/scripts/train-expanded-session.sh`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/campaigns.py`
- `ai-training/src/idps_ai/data/dataset.py`
- `ai-training/src/idps_ai/data/lab_runtime.py`
- `ai-training/src/idps_ai/data/pretrain.py`
- `ai-training/src/idps_ai/data/provenance.py`
- `ai-training/src/idps_ai/data/query_numeric.py`
- `ai-training/src/idps_ai/data/readers.py`
- `ai-training/src/idps_ai/data/readiness.py`
- `ai-training/src/idps_ai/data/scenario_data.py`
- `ai-training/src/idps_ai/data/sensor_decode.py`
- `ai-training/src/idps_ai/data/split.py`
- `ai-training/src/idps_ai/data/structure.py`
- `ai-training/src/idps_ai/export/onnx.py`
- `ai-training/src/idps_ai/features/pipeline.py`
- `ai-training/src/idps_ai/inference.py`
- `ai-training/src/idps_ai/pilot.py`
- `ai-training/src/idps_ai/training/deep.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/session.py`
- `ai-training/tests/test_cli.py`
- `ai-training/tests/test_deep_models.py`
- `ai-training/tests/test_expanded_corpus.py`
- `ai-training/tests/test_pretrain.py`
- `ai-training/tests/test_structure_features.py`
- `ai-training/tests/test_training.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

Container và process fixture đã dừng/dọn; không dừng hoặc sửa dịch vụ người dùng.
Lệnh người dùng tự chạy, **chưa được thực thi**:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-expanded-session.sh gated_residual
```

Có thể chọn candidate khác bằng đối số. Guard kiểm tra dataset/readiness/source hash;
chỉ resume cùng run khi learning config, dữ liệu và source tương thích. Không ép
resume một run đã early-stop. Còn cần human review, dữ liệu production đa dạng,
đánh giá test sau freeze, TLS/Rust/receipt-time/mất nguồn/shadow/response acceptance.
Không chứng nhận zero-day hoặc chất lượng thực tế chỉ nhờ thêm tham số và request.



## 25. Challenger 9,68M / corpus hướng tới2M — 2026-10-30T15:52:59+07:00

**Trạng thái:**ENGINEERING_VALIDATED_SCALE_DATA_NOT_READY. Owner Codex, tự kiểm;
reviewer độc lập chưa có. Nhánh feat/ai-model-training, HEAD `fd0fea47dbc30a56dc8a9bed819b15cf3dc66d11`.
User giao AI-only, không sửa/xóa/move/restructure Student/Security và không chạy
formal nhiều giờ. User xác nhận chỉ có lab hiện tại; không có traffic/nhãn độc lập.
Có dirty changes từ mục22–24 trước phiên; giữ nguyên, không git add/commit/push.

### 25.1. Dữ liệu và quyết định phạm vi

- Bảo vệ366 file services/contracts và3.742 file artifact cũ bằng SHA256; snapshot
  source/handoff cũ trong `.artifacts/scale_upgrade_20261030/baseline-source/`.
- Dữ liệu vẫn69.345 request thật của fixture localhost, không thêm capture/request
  hoặc environment. v5 là re-extraction của cùng collected snapshot. Nhãn scripted
  intent và HTTP contract, không human realism/coverage review, không exploit success.
- Registry immutable/checksummed, SQLite audit index trên đĩa; reject duplicate
  dataset/PCAP dù reproject, oldtest→train, thiếu provenance/review hoặc profile.
  Audit source/identity/payload/time/family/coverage; attestation không tự chứng
  minh môi trường và ground truth. Chưa có nguồn độc lập để review.
- Scale policy đề xuất2M eligible,3 environments,7 days,120 campaign,4 roles và coverage
  3 nguồn≥95%. Các floor ngoài2M là engineering proposal cần review, không chuẩn
  production phổ quát. Thực tế reference69.345,eligible0,NOT_READY. Không lặp log,
  no-alert→benign, tăng count bằng flow/reprojection hoặc dựng cột Student cho flowCSV.
- **Multi-corpus shared-scaler assembly còn NOT_IMPLEMENTED/NOT_ACCEPTED.** Không
  concatenate vectors normalize riêng. Cần nguồn/labels, identity/split/provenance,
  shared train-only scaler và immutable four-part dataset trước formal main-model.

### 25.2. Features, kiến trúc và thuật toán

- Canonical 1.0 và bridge numeric v2 giữ nguyên. Feature/normalizer5,207 cột=189+18
  causal IP/user dynamics: interarrival+missing,10/60 và60/300burst,URI/method
  transition,CV60/300,gia tốc authfailure. History/current only, reset split,
  bounded2048events/entity; context-incomplete/eviction/missing không giấu.
- Main challenger `residual_glu`:207→1024,3pre-LN residual SwiGLU blocks,head8;
  **9.675.784 tham số thật**, không padding, không ID/rule embedding/dormant tensor.
  Tests mọi tensor nhận gradient; finite-difference check, deterministic inference,
  same-run mid-epoch/fresh-process resume và ONNX strict. Baseline models còn giữ.
- CE stable logits + smoothing0,02; AdamW W-only1e-4,betas0,9/0,999,eps1e-8,
  global L2clip1,dropout0,1train-only; PCG64 seed/step/23 không tiêu thụ sampler RNG.
  Warmup/cosine theo committed global step; metadata lưu contract, không restart
  warmup/optimizer khi resume. Params/activations/grad/Adam FP32; affine and LN
  stats FP64→FP32; sigmoid FP64→FP32,ONNX tolerance1e-5/1e-6 giữ nguyên.
- LayerNorm/GLU có mục đích học interaction, không claim TabM/Transformer/TCN.
  Dựa quyết định tabular/CPU từ primary research trong docs03; hiệu quả chỉ dựa
  benchmark local, không suy ra tối ưu phổ quát.

### 25.3. Training, evaluation và tích hợp

Bốn neural candidates fixed 2 epoch,1→2 qua process mới, reference2 epoch riêng.
Không validation trong fit hoặc early stop; cùngbatch128/LR0,0003/warmup30/cosine1000.
Algorithm/regularizer khác, không gọi đây architecture-only/equal-compute ablation.
Calibration3 campaign/4.623rows,selection6 campaign/9.246rows; group chọn theo thời
điểm trước khi xem label/score. Bootstrap200lần theo campaign, threshold cố định.
Chỉval quality/latency; test vectors chỉ parity, test labels không dùng chọn/tuning.

| Candidate | Tham số neural | AP | Precision | Recall | F1 | FPR | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deep_mlp | 252680 | 0.999436 | 98.63% | 98.92% | 98.77% | 0.564% | 0.092 |
| gated_residual | 450056 | 0.999526 | 97.78% | 99.78% | 98.77% | 0.930% | 0.146 |
| hist_gradient_boosting | cây, không phải neural | 0.999115 | 99.74% | 99.37% | 99.55% | 0.107% | 1.697 |
| residual | 17992 | 0.997758 | 98.14% | 97.99% | 98.06% | 0.762% | 0.014 |
| residual_glu | 9675784 | 0.997228 | 98.01% | 98.92% | 98.46% | 0.823% | 5.363 |

Wall pilot790.413s; optimizer chính
126.775240s,reference
136.867438s riêng. Report lưu session/runID,
data/config/source/checkpoint hashes,history và resource readbacks. Không cộng prep/
export/diagnostics vàooptimizer. AP main − best-other=-0.002298;
best AP`gated_residual`,chưachampion hoặc production quality.
Tree32 iterations fixed,train-only,không HPO/serialization/deploymentbundle.

Offline shadow512 request của main PASS,**0enforcement actions**. Output chỉevent_key
và score/candidate; không rawquery/headers/clientIP. Same versioned fused chronological
contract/scaler/state như train. Live receipt-time/TLS/outages/auth/Web/IPS còn riêng;
chỉ ghi đề xuất, không sửa hai webapps hoặc gọi block APIs.

### 25.4. Hardware, kiểm thử và lỗi đã xử lý

8 CPU/16 logical≈50%,MemoryMax16 GiB/high15/swap0/Nice10. BLAS/ORT/affinity/cgroup
readback,process-treeRSS/RLIMIT_AS và sensor CPU tại optimizer boundaries. Mỗi5s tối
đa sample nhiệt; nếu sensor cócritical thìcheckpoint/dừng trong5C trướccritical;
không cósensor ghiunavailable, khôngbịa0C/khôngkhẳng địnhthermalprotection. Khôngđổi
powergovernor/hostpolicy. Guardprobe0 optimizerstep,không train chínhthức. Pilot ngắn
không chứng nhận2–3giờ endurance;16 GiB làtrầnuser,không tựcoi50%OS RAM.

| Kiểm tra/lệnh | Trạng thái | Evidence |
| --- | --- | --- |
| `corpus-audit` registry hiện tại | PASS audit, NOT_READY dữ liệu | reference69.345/eligible0; `corpus-audit-final/report.json`; exit3 làđúng |
| `prepare ... --behavior-dynamics` | PASS | dataset hash `45ca178b494446451bfeec8e30b655044df02460ef5aa9273a93143d54cd9b08`,207 cột; `prepare.log` |
| v5 readiness/replay/embargo | PASS |53/53; `readiness/readiness.json` |
| `bash ai-training/scripts/check.sh` với Suricata runtime thật | PASS |**134pytest,0skipped**,Ruff/format/compile/canonical/protected diff; checks-final.log |
| `pilot --candidate-set scale` | PASS |4 models2 epoch,exactresume,ONNX69.345rows/model; pilot report |
| `tree-baseline`32 iterations | PASS |separate calibration/selection,perfamily/CI/latency; tree-baseline/report.json |
| Resourceprobe | PASS |0 optimizersteps,actualcgroup/sensors; resource-probe.json |
| `shadow-replay --max-requests512` | PASS |offlineonly,0actions; shadow/report.json |
| `pip check`;shellsyntax;`git diff --check` | PASS |không thêm dependency nặng/không sửa web |
| `mvn test`/`cargo test` | NOT_RUN |source/config web giữ nguyên,không tính kết quả lịch sử làrerun |
| Corpus2M/formaltrain/testquality/live/shadowproduction/enforce | NOT_RUN/NOT_READY |thiếu independent sources/labels/assembly và chưa được cho phép formal |
| Git add/commit/push | NOT_RUN |không được yêu cầu |

Các RED đã sửa: thiếucorpus/model/temporal/scheduler/ONNX/shadow boundaries; gradient,
resume,regime vàsensor cases đềuđược thêm từ seam public. Thermal-test ban đầu FAIL
vì sampler chưa được nối vào check, sau sửa PASS. Latency export ban đầu lấytestfeature
(không nhãn); đã chuyển sangval trước optimizer, dừngattempt readiness trướcđó vàgiữ
ở`superseded_before_latency_partition_fix/`, rerunfull134/gate. Không hạgate,không
skip,nới ONNXtolerance hoặc chọn lạihyperparams theo kết quả. Caller thửsystemPython
không cóeditablemodule được chạy lại bằngvenv; không sửadata để né lỗi.

### 25.5. Cleanup, artifacts và bước tiếp

Đã giải phóng **498.14MiB** cache tái tạo được:
newpilot/tree `cache/*.npy` (load_arrays luôn tạo lại từimmutable dataset trước
fit/resume/export),source/test bytecache,pytest/Ruff cache. Kiểm names/ownership,
không symlink,ghiSHA/size trước xóa. Không xóaNPZ/latest/best/previous/sessions hoặc
raw/labels/logs/source snapshots. Các test đều đangđược collect và docs/logs cũ là
bằng chứng lịch sử/cóthamchiếu nên giữ. Cũng bỏ duplicate probe/main trong resources
và một input_contract assignment bị ghiđè; không đổi Student/Security.
Cleanup manifest:`cleanup.json`; raw/checkpoint/evidence cũ3.742 files giữ nguyênSHA.

Publicreport:[SCALE_UPGRADE_20261030.json](../ai-training/reports/SCALE_UPGRADE_20261030.json),
SHA `a386d11de947af0afad1def6f965d75a356bfb5cf19ce63a162974ea35da9a58`.
Handoff:[FINAL_TRAINING_HANDOFF.json](../ai-training/FINAL_TRAINING_HANDOFF.json),
SHA `e48c10a92dac34aa73c52f017b31af910bde3ae59f68e1b398dd7ccada9d016d`.
Artifact root:`ai-training/.artifacts/scale_upgrade_20261030/` private/localignored.
CURRENT_WORK/CONTINUE vàpipeline-progress làđiểmtiếp tục; source frozen cóhash.
Khôngcókhoartifactchung; teammate không tự córaw/model chỉbằngGitpull.

Tiếp theo:review label/realism vàscope nguồn authorized khác,thu đủđa dạng,
triểnkhai shared-scaler multi-corpus assembly với4part/group/environmentholdout,
nghiệmthu2M resource/readiness,rồi user cho phépformal. Freeze model/threshold trước
mởfinaltest; sau đó live/TLS/receipt-time/outage/shadowacceptance vàintegration web
trong luồng sở hữu tương ứng. Khôngcólệnhformalđược khuyến nghịbây giờ; CLI technical
replay/benchmark ở README. Không tự đẩy10M làm champion dùAPđẹp trongmộtlab.

Danh sách file đợtnày (khônggom mọi dirtychanges cũ mục22–24):

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/scale_model_config.yaml`
- `ai-training/configs/scale_pilot_config.yaml`
- `ai-training/configs/scale_policy.yaml`
- `ai-training/configs/scale_sources.yaml`
- `ai-training/reports/SCALE_UPGRADE_20261030.json`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/corpus.py`
- `ai-training/src/idps_ai/data/readiness.py`
- `ai-training/src/idps_ai/data/split.py`
- `ai-training/src/idps_ai/export/onnx.py`
- `ai-training/src/idps_ai/features/behavior.py`
- `ai-training/src/idps_ai/features/pipeline.py`
- `ai-training/src/idps_ai/inference.py`
- `ai-training/src/idps_ai/pilot.py`
- `ai-training/src/idps_ai/training/deep.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/protocol.py`
- `ai-training/src/idps_ai/training/resources.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/schedule.py`
- `ai-training/src/idps_ai/training/tabular.py`
- `ai-training/src/idps_ai/training/tree_baseline.py`
- `ai-training/tests/test_behavior_features.py`
- `ai-training/tests/test_cli.py`
- `ai-training/tests/test_evaluation_protocol.py`
- `ai-training/tests/test_resource_monitor.py`
- `ai-training/tests/test_scale_corpus.py`
- `ai-training/tests/test_scale_model.py`
- `ai-training/tests/test_shadow_replay.py`
- `ai-training/tests/test_tree_baseline.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`


## 26. Generalization / public HTTP / scaler chung — kết thúc 2026-10-30T16:53:30+07:00

**Trạng thái: ENGINEERING_PASS_GENERALIZATION_NOT_READY.** Owner Codex; reviewer độc
lập chưa có. Branch `feat/ai-model-training`; HEAD không đổi; không commit/push. Chỉ
luồng AI và tài liệu. Không thay Student Web/Security Web/contracts/docker. Resume
work tại `ai-training/.artifacts/generalization_20261030/CURRENT_WORK.json` và
`ai-training/FINAL_TRAINING_HANDOFF.json`; không sửa hoặc force-resume các run cũ.

### Quyết định và kết quả

1. Giữ baseline MLP252.680 và main residual SwiGLU9.675.784, không tăng tham số. Hai
   probe đã preregister trước external scores: smoothing.005, rồi lr.0006; seed17,
   batch128,652updates/2epochs, val không dùng trong fit. AP selection lần lượt
   0.9978115/0.9990035 so với MLP0.9994364 và GLU gốc0.9972278. LR cao tăng recall
   (99.368%) kèm FPR0.869%; không thắng toàn diện, không champion. Loss smoothing
   có entropy floor khác MLP, không so raw loss để kết luận underfitting.
2. Calibration3groups và selection6groups khác identity nhưng cả9campaign chạy đồng
   thời. Trước đây chỉ chứng minh group separation, **chưa temporal/environment
   independence**. Audit train/val: client/user/session/campaign overlap0,2exact-vector
   overlaps benign,3rounded-vector overlaps benign; không suy diễn sạch semantic
   grammar. Labels vẫn scripted intent, không exploit success/human realism review.
   Probe cây depth4 train-only theo actor/UA/response/behavior/flow và stump được lưu;
   đây là development diagnostics, không causal proof hoặc selection bằng test.
3. `corpus-assemble`: SQLite sort/identity/dedup, recompute features, scaler chung fit
   benign train;4vai. Test hai shard với vectors normalize giả999 PASS. Bản69k thật
   có41.607train/4.623calibration/9.246val/13.869test; test không quay lại train.
   `calibration_temporally_independent=false`, formal=false. Train/export/parity hỗ
   trợ calibration riêng; trong fit không mở partition đó để chọn threshold.
   Partial-public profiles bị reject, không bịa flow/actor/time. Reviewed multi-env
   admission và2M endurance vẫn chưa nghiệm thu; catalog actual NOT_READY/0eligible.
4. Nguồn công khai: WebRequests/ANII DOI10.60895/redata/RWUUSV repository CC BY4,
   tải3CSIC raw files, SHA256+MD5 verified,97.065records nhưng34.561observable request
   identities;626identities giao train/test gốc. Không dùng CSV TF-IDF fit vocab toàn
   corpus hoặc đếm lại các bộ gốc overlap. Attack labels binary publisher, family
   unknown, không lấy rule làm truth. Body/header-only positives giữ trong full test;
   curated2.114requests không dùng che những ca khó. Original CSIC license lineage
   chưa tự phục hồi, raw giữ private, attribution và terms ghi trong registry/report.
5. CSIC static view có32vectors khác nhãn;14.967/61.065minimum errors(24.51%) với
   chính view đó. Chỉ1.713/25.065anomalies còn nonempty query,9.977có body mà model
   không quan sát. Không gọi đây là publisher mislabel. Full external challenge giữ
   threshold lab: GLU cả3bản FPR100%; MLP recall1.3246%(332/25.065),FPR0%. Đây là
   OOD/missing-view stress test, không cùng điều kiện full3source, nhưng bác bỏ
   readiness triển khai. Không retune threshold/config bằng external labels.
6. OpenCitations DOI10.5281/zenodo.20289873, API CC0 verified: stream prefix100.000rows,
   loại9.666record trùng →90.334observations,3.754client pseudonyms,~91phút thời gian
   thật. Không lưu token/referer/raw URL/query/IP hash; không extract tar ra filesystem.
   Chưa có nhãn,0supervised/0benign-only admission; không coi HTTP200/no-alert là benign.
   Chỉ verify metadata/license/prefix SHA, full3.6GB archive checksum NOT_RUN.
   Biblio-US17 là nguồn47M/6months đáng nghiên cứu, nhưng quyền tải/terms chưa xác
   minh; chưa tự liên hệ tác giả. PKDD/CICIDS/URL2016 giữ giới hạn schema/label rõ ràng.
7. Isolated CPU thread sweep300repeats sau khi pytest/train dừng: MLP1thread p95~0.079ms;
   GLU8threads p95~4.63–4.78ms; parity1e-5/1e-6 giữa threads PASS. Sweep đầu overlap
   pytest giữ như evidence superseded; không overwrite. Đây là warm model-only
   latency, không Web/throughput SLO. Shadow512candidate mới PASS,p95~6.38ms gồm
   preprocess,0enforcement; không sửa code/cấu hình Web.
8. Resource hard limits8logicalCPU/16GiB/high15GiB/swap0, actual affinity0–7 và cgroup
   readback PASS. Candidate optimizer119.42+121.96=241.38s, continuous verification
   124.05s tách riêng; pilot wall480.75s. Worker memory snapshots peak1.90GiB,
   journal whole development batch~2G. Host CPU sensor peak96°C ở continuous reference,
   guard100°C không trigger; không dùng short pilot làm thermal endurance ca dài.

### Kiểm thử và trạng thái

| Lệnh / nghiệm thu | Trạng thái | Bằng chứng |
| --- | --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 IDPS_AI_TEST_SURICATA_RUNTIME=<existing upgrade_20261028/tools/runtime> taskset -c 0-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**,144tests,0skip,68.15s; Ruff src/tests/scripts,format,compile,contract,Web gitdiff | `checks-acceptance.log` |
| `idps-ai readiness --dataset <scale_upgrade/prepared-v5> --data-kind lab_capture --provenance <prepared_provenance.json> --policy configs/expanded_policy.yaml --output <newroot>/readiness` | **PASS**,53/53 technical checks; không scale admission | `readiness/readiness.json` |
| `idps-ai corpus-assemble --registry <newroot>/assembly-registry.yaml --output <newroot>/assembled-research` | **PASS** research;4roles; chưa temporal cal/val independence | manifest datasetSHA `d04e14874b8968ee7ef37e04c673218043abbd8c6d267bdae0ca003a479de19a` |
| `idps-ai corpus-audit --registry configs/scale_sources.yaml --output <newroot>/scale-catalog` | **NOT_READY**,expected exit3;0eligible/69.345reference | `scale-catalog/report.json` |
| `idps-ai http-fetch --output <newroot>/pinned-source-check` và `http-import --registry <newroot>/public-sources/registry.yaml --output <newroot>/public-http` | **PASS**; pinned hashes/live version/license; hardlinks kiểm tra không data mới | metadata/download/fetch manifests |
| `python scripts/import-public-accesslogs.py --output <newroot>/public-accesslogs --max-requests 100000` | **PASS** bounded projection; labels unknown | accesslog manifest; tar/path/canary CLI test |
| `idps-ai shortcut-audit --dataset <prepared-v5> --output <newroot>/shortcuts.json` | **PASS** diagnostic, development only | `shortcuts.json` |
| `python scripts/validation-probe.py --dataset <prepared-v5> --readiness <newroot>/readiness/readiness.json --plan <newroot>/experiment-plan.json --output <newroot>/development-pilot` | **PASS**2new2epoch probes; fresh-process resume exact vs continuous, full ONNX parity69.345vectors/model | `development-pilot/report.json`, run configs/logs/checkpoints |
| Repeat completed `validation-probe.py` | **PASS** guard: expected rejection, no optimizer, report unchanged | `completed-experiment-guard.json`; executed script snapshot retained |
| `python scripts/compare-operating-points.py ... --repeats 300` | **PASS** same calibration FPR budgets.001/.005/.01; isolated thread sweep | `operating-points-isolated.json` |
| `idps-ai http-challenge --benchmark <newroot>/public-http --bundles <newroot>/frozen-bundles.json --output <newroot>/external-challenge.json --cpus 8` | Execution **PASS**; missing-view transfer/deployment acceptance **FAIL** | `external-challenge.json` |
| `idps-ai shadow-replay ... --partition val --max-requests 512 --cpus 8` | **PASS**,offline only | `shadow/report.json` |
| SHA preservation audit | **PASS**,366protectedfiles+4.233oldartifacts unchanged; prior SCALE report SHA unchanged; HEAD unchanged | `preservation.json` |
| Formal multi-hour train / original final-test quality / live Web-TLS-IPS acceptance | **NOT_RUN** | Không tự chạy formal hoặc chọn champion |

Các RED test trước triển khai và tar-stream adapter Python3.12 lỗi ban đầu đã sửa;
final suite **không** còn FAIL/SKIPPED. Những FAIL/NOT_READY về chất lượng dữ liệu/model
không bị đổi nhãn thành pytest PASS. Không chạy lại baseline đã hoạt động; dùng
artifact immutable cũ để so sánh cùng dataset/seed/batch/steps, vẫn ghi khác optimizer/
regularization, không giả equal-compute HPO hay kết luận riêng tác dụng số tham số.

### Bảo toàn, dọn dẹp và tiếp tục

- Dọn18Numpy memmap cache tái tạo được, **165.86MiB**; checkpoint trước/sau cùng hash.
  Giữ raw, source snapshots, models, history, logs và thí nghiệm cũ. Không xóa docs/test
  có giá trị hoặc source Web. Đã dọn thêm cache `.pyc`/pytest phát sinh; số byte nằm trong `cleanup.json`.
- Gói bằng chứng: `ai-training/reports/GENERALIZATION_20261030.json`;
  artifact local ignored `ai-training/.artifacts/generalization_20261030/`.
  Không raw/key/binary nào được add vào Git; artifact store chung chưa được cấp.
- Những public challenge scores hiện đã xem phải được coi là development nếu tái
  sử dụng để đổi feature/HPO; cần challenge mới giữ kín. Lab final-test quality vẫn
  không dùng tuning/selection; test vectors chỉ tham gia parity kỹ thuật.
- Bước sau: profile request-only có cấu trúc tham số không nhạy cảm rộng hơn allowlist
  Student, label/realism review độc lập, fresh3source campaigns tách thời điểm và
  grammar/hard negatives mới,300s embargo; xin quyền nguồn Biblio hoặc nguồn nhãn
  khác; chỉ formal sau data admission và user cho phép. Không kéo dài train để che
  thiếu thông tin, không relabel unknown public traffic thành benign.

### File sửa trong lượt này (không gộp các sửa đổi từ phiên trước)

- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/assembly.py`
- `ai-training/src/idps_ai/data/corpus.py`
- `ai-training/src/idps_ai/data/http_benchmark.py`
- `ai-training/src/idps_ai/export/onnx.py`
- `ai-training/src/idps_ai/training/generalization.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/runner.py`
- `ai-training/src/idps_ai/training/tabular.py`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/scripts/audit-public-http.py`
- `ai-training/scripts/check.sh`
- `ai-training/scripts/compare-operating-points.py`
- `ai-training/scripts/import-public-accesslogs.py`
- `ai-training/scripts/validation-probe.py`
- `ai-training/tests/test_generalization.py`
- `ai-training/tests/test_http_benchmark.py`
- `ai-training/tests/test_public_accesslogs.py`
- `ai-training/tests/test_scale_corpus.py`
- `ai-training/tests/test_scale_model.py`
- `ai-training/README.md`
- `ai-training/PRETRAINING.md`
- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/reports/GENERALIZATION_20261030.json`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`


## 27. Request profile và hai holdout mới — engineering hoàn tất, chất lượng chưa đạt — 2026-10-30T21:36:36.771093+07:00

### Phạm vi và trạng thái cuối

Tiếp mục 26, chỉ AI và tài liệu trên nhánh `feat/ai-model-training`. Không sửa Student/Security/contracts/docker; không commit/push hoặc train chính thức. Artifact root: `ai-training/.artifacts/request_view_20261030/`. Có baseline source trước lượt, source trước từng study và SHA của 689 protected path. **160 tests PASS/0 skip, 53 technical gate PASS; generalization/production NOT_READY; chưa champion.** Báo cáo mới `ai-training/reports/REQUEST_PROFILE_20261030.json`, handoff format 5; raw/key/binary vẫn private/local ignored.

### Data → features → model/algorithms → training → evaluation → AI integration

1. Profile riêng `request-structure-v1` có 70 số URI/query/method, giữ cấu trúc tham số không nhạy cảm bằng alias. Credentials/PII bị bỏ trước tính số; không plaintext/key name/rule/source/UA/status/actor/flow/time trong tensor. Preprocessor và ngữ nghĩa 207 feature v5 giữ nguyên. Profile SHA: `e1c3df19f511be2773e56af61828ebe201bdbe8eae7cd8475de3b290fab4522b`.
2. EVE decoder có opt-in dual projection v2 + request v1 trước URL mask. Stream bridge giới hạn JSONL 64 KiB, lỗi không echo raw; chỉ giữ request ID cần thiết, không body/header dump. Preflight kiểm tra giới hạn Unix socket path 108 byte đã có test. Lần đầu path dài bị lỗi, log được giữ; final decode PASS.
3. PKDD mirror V1 metadata CC BY 4, MD5/SHA verified, attribution trong report. File thực tế flattened text, thiếu Context/inContext/attackIntervall và vị trí attack của native XML. TRAIN có 24.504 record toàn `Valid`; TEST có 25.612 record, 10.502 normal và 15.110 anomalous. Không đoán family, dùng TF-IDF global hoặc public test cũ làm train. Original publisher license lineage chưa xác minh độc lập, raw giữ private. Biblio-US17 có 47M HTTP thật/6 tháng theo tác giả, nhưng cần quyền tải/terms; chưa tải hoặc gửi email. OpenCitations unknown vẫn 0 training admission.
4. Assemble 115.980 request-profile record: 86.275 train, 12.303 calibration, 17.402 validation; một scaler chỉ fit benign train. Dataset SHA: `1e020f364268a2cee318ae7ee7033c46f5a7cfaba7b1c5d23daf9cdd80998731`. Original lab test quality không đọc. Để public normal-only không tạo shortcut source→label, supervised chỉ fit lab: 1.233 unique view, 1.027 positive/206 benign. AE có 18.713 unique benign view đa nguồn. Toàn fitting corpus có 28.830 numeric view, 600 nhóm giao partition, 0 nhóm trộn nhãn 0/1. View collision không chứng minh raw request trùng hoặc grammar độc lập. Calibration/selection lab cũ vẫn concurrent. Không đếm projection/record benchmark thành HTTP lab mới.
5. Thu **1.935 HTTP thật mới**, 3 client concurrent trong 360 giây, private namespace/owned fixture, seed 991397786; grammar, jitter và hard negative mới, có read/mutation thật. Khoảng cách so timestamp cuối lab cũ **41.276,23 giây**, vượt embargo 300 giây; vẫn chỉ một môi trường và một cohort thời điểm mới. Có 1.882 hợp đồng intent/expected HTTP tự động đúng, 53 HEAD/OPTIONS trả 403 pending (33/20). Giữ raw/full intent diagnostic, không relabel để che mismatch. Chỉ đọc thấy GET matcher không bao phủ HEAD/OPTIONS; ghi đề xuất cho Web owner ngoài phạm vi, không sửa Web.
6. PCAP mới 3.399.289 byte, SHA `edfaba826345dac1238014e8495b41ba4bd528cfe0eb50eec768ed7a08452589`; 19.931 packet, 0 kernel drop. EVE có 1.935 HTTP/1.935 flow/364 alert; correlation đủ 3 nguồn ở 1.935/1.935 request. Collector chỉ dùng past-completed-flow theo quan hệ nhân quả: 1.567 request có giá trị, 368 null; không lấy future flow lấp cột. Tổng lab **71.280 HTTP thật**, scale-admitted=0/2M, independent human review=0. Private DB/backend/sensor đã dừng, không tắt service user.
7. Partial binary loss dùng FP64 logsumexp với `P(attack)=sum(7 non-benign heads)`. Unknown family giữ `-1`; known family có conditional CE weight 0,2; binary smoothing 0,005. Balanced weights chỉ lấy từ selected train. MLP/GLU dùng AdamW W-decay=1e-4, global gradient clip=1; GLU dropout=0,1. Diagnostic warmup=15, cosine tới 300 update, lr=0,0003. Checkpoint pin data/config/source/env, lưu mỗi 30 giây và tại signal/resource boundary; có CPU/RSS/thermal guard. Giữ baseline 252.680/9.675.784 tham số; nhánh 70 input có MLP 217.608/GLU 9.535.496/DAE 233.670 tham số thật, không padding.
8. Study 1: 3 model × 2 epoch; supervised chỉ 20 update do 1.233 unique view. Study 2: diagnostic cố định 300 update, tối đa 180 giây/session. Khóa cấu hình trước parse/score PKDD test và fresh cohort. Test file tải sau study 1, **trước** freeze study 2; không nói tải sau freeze study 2. Fresh-process 100→300 bằng continuous chính xác ở parameters/Adam/RNG/permutation/cursor/history. ONNX toàn 115.980 vector/model/study PASS rtol=1e-5, atol=1e-6. Classifier max abs=2,384e-7; AE=3,815e-6 vẫn PASS tiêu chí relative+absolute, không nói max abs≤1e-6. Study 1 wall=82,93 giây; study 2 wall=185,34 giây gồm reference/export; optimizer MLP=1,00 giây, GLU=46,03 giây, AE=0,91 giây. Đây là diagnostic ngắn, không formal 3 giờ.
9. Calibration dùng max source-specific benign quantile, target FPR 1%, không dùng attack/test score chọn ngưỡng. Cùng corpus/seed/batch/300 update/budget, không equal FLOPs. Cgroup readback lúc chạy: 4 CPU, affinity 0–3, RAM 16 GiB/high 15 GiB/swap 0. Second-session temperature MLP/GLU/AE=56/64/72°C, không thermal stop; chưa long endurance.
10. `RequestInferencePipeline` xác minh bundle/profile/fingerprint, finite output, batch 1–4096; family candidate=None, 0 enforcement. EVE bridge opt-in trước mask đã test secret canary, bounded line và dual-v2 compatibility. Chưa nối vào Web/sensor config hoặc nghiệm thu live TLS/IPS. API/canonical v1.0 giữ nguyên.

### Kết quả đã đo — không chọn champion

Bảng dùng tỷ lệ 0–1 cho Precision/Recall/F1/FPR; AP là average precision. Fresh lab primary task có 1.666 record: 1.378 approved benign và 288 attack thuộc bốn họ payload.

| Request candidate | Validation AP | Fresh lab P / R / F1 / FPR | PKDD test P / R / F1 / FPR | Lab warm batch-1 p95 |
| --- | --- | --- | --- | --- |
| MLP 217k | 0.82914 | 1.00000 / 0.40625 / 0.57778 / 0.00000 | 0.82190 / 0.03726 / 0.07129 / 0.01162 | 0.138 ms |
| GLU 9,535M | 0.80711 | 0.00000 / 0.00000 / 0.00000 / 0.00000 | 0.69231 / 0.01132 / 0.02227 / 0.00724 | 4.483 ms |
| DAE 233k | 0.75786 | 0.29086 / 0.36458 / 0.32357 / 0.18578 | 0.99819 / 0.40212 / 0.57329 / 0.00105 | 0.135 ms |

Full metric/confusion matrix/PR-AUC/per-intent-family/bundle hash trong report là nguồn chính. Pending 53 và scanner/brute/sequence 216 record giữ ở secondary/all-intent diagnostic. Không dùng request-only model để khẳng định phát hiện behavior theo thời gian. Novel-only là sensitivity bổ sung full primary, không lọc ca khó. 0 FP/1.378 không chứng minh production FPR bằng 0: upper bound nhị thức một phía 95% khoảng 0,217%, còn giả định IID bị hạn chế vì cùng cohort.

Frozen legacy 207 feature trên **đúng cohort mới đủ 3 nguồn/common payload task**: GLU gốc recall 71,18%/FPR 73,22%; GLU tuned 80,56%/69,09%; MLP 253k 7,64%/5,52%. Model-only p95 tương ứng 4,175/4,479/0,134 ms; khác scope với latency gồm request preprocessing. Thất bại không thể giải thích chỉ bằng thiếu flow ở public data.

Audit dual projection xác nhận mất thông tin ở v2: trên 288 payload mới nằm trong tham số ngoài allowlist, các lexical counter được chọn ở v2 đều 0, dù `query_lexical_available` vẫn 1 do page/limit. Profile mới giữ SQL keyword ở 72/72 SQLi, event assignment ở 60/72 XSS, path parent ở 52/72 traversal, shell substitution ở 21/72 command. Khắc phục observability không đồng nghĩa model đã học tổng quát.

300 update cải thiện validation, nhưng GLU vẫn overconfident trên OOD benign; max source calibration threshold=0,998768 khiến fresh lab recall bằng 0. AE public recall 40,21%/FPR 0,105% nhưng fresh lab hard-negative FPR=18,58%. Precision public 99,82% đo ở khoảng 59% attack prevalence không chuyển thành precision production. Thiếu positive đa nguồn/human review, unique grammar support ít và source calibration là các giới hạn cần xử lý; chưa có causal ablation đa seed/môi trường để quy về một nguyên nhân duy nhất.

### Kiểm thử, commands và bảo toàn

Các path trong command dưới đây là template rút gọn. Script, argv/plan, log và input/output SHA được giữ trong artifact root/report; không cần chạy lại study đã hoàn tất.

| Lệnh/nghiệm thu | Trạng thái |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 IDPS_AI_TEST_SURICATA_RUNTIME=<upgrade_20261028/tools/runtime> taskset -c 0-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**: 160 pytest/0 skip/74,72 giây; Ruff 97 file/format/compile/contract/Web git diff |
| `idps-ai decode-pcap --pcap <original.pcap> --runtime <existing-runtime> --output <new-output> --query-numeric --projection-version 2 --request-structure` | **PASS**: old-final/new-final, manifest pin PCAP/runtime/rule/config SHA |
| `idps-ai request-prepare --registry <request-sources.yaml> --output <corpus-final>` | **PASS**: mixed request profile/scaler/identity audit |
| `python scripts/request-pilot.py --dataset <corpus-final> --output <pilot> --cpus 4` | **PASS**: fixed 2 epoch/3 model, completed output reject overwrite |
| `python scripts/request-pilot.py --dataset <corpus-final> --output <diagnostic> --cpus 4 --learning-curve` | **PASS**: fixed 300 update, exact resume/continuous/strict ONNX |
| `python scripts/evaluate-public-request.py --dataset <corpus-final> --source <public/xml_test.txt> --identity-key <private-key> --bundles <final-bundles.json> --output <public-test.json>` | Execution **PASS**; generalization acceptance **FAIL/NOT_READY** |
| `python <request-root>/evaluate-fresh.py` | Execution **PASS**; request/legacy model quality chưa đạt; không retune bằng test |
| `idps-ai readiness --dataset <scale_upgrade/prepared-v5> --data-kind lab_capture --provenance <prepared_provenance.json> --policy configs/expanded_policy.yaml --output <request-root>/readiness` | **PASS**: 53/53 technical check trên 69k cũ; không phải 2M/quality admission |
| Source/artifact preservation | **PASS**: 689 protected path và report GENERALIZATION giữ SHA, HEAD không đổi; legacy 207 semantics không đổi |
| Formal training/original old test quality/live TLS/IPS/human review/multi-environment acceptance | **NOT_RUN** |

Sau study chỉ `request_inference.py` khác `source-learning-curve` frozen package: sửa **reporting** từ `bool(flowdict)` đếm sai 1.935 sang 1.567 có non-null finite counter. Giữ before-report, đối chiếu toàn bộ model metrics không đổi; không retune hoặc tính lại quality. Global source identity vẫn đổi: không force-resume bằng source hiện tại, tái lập bằng frozen snapshot. RED test import flow helper FAIL đúng kỳ vọng trước sửa; final 160 PASS không FAIL/SKIPPED. Lỗi draft parser/socket đã có log, không xóa để che bằng chứng.

Dọn 720.632 byte generated Python/pytest cache sau kiểm tra Git tracking và exact reference. Giữ raw, key, checkpoint, source/optimizer/reference/history/experiment và docs/test có giá trị; draft derivative giữ làm evidence. Private DB/student/sensor đã dừng, transient training unit inactive/success; không tắt service khác. Maven/Cargo không chạy vì không sửa Web; AI check-contract và Web source guard PASS.

Đối chiếu cuối `final-verification.json` **PASS**: report/artifact/script hash, PKDD MD5/SHA, profile fingerprint, 689 protected path, Web diff, `git diff --check` và 0 listener còn lại ở ba cổng lab. Hai study đồng thời đổi weighting/schedule/update budget; không coi đây là ablation riêng tác dụng tăng số update.

### Còn mở và tiếp tục

1. Independent human label/realism review; giữ 53 HEAD/OPTIONS pending; đề xuất Web owner xử lý ngoài scope AI.
2. Nguồn HTTP positive và benign độc lập, đa môi trường/thời gian, có quyền sử dụng, hướng tới 2M chất lượng. Biblio-US17 chưa quyền/chưa tải; không nhân bản fixture để đủ số.
3. Mọi public/new-cohort test trong report nay đã exposed. Future HPO/feature changes cần sealed holdout mới; không tái sử dụng làm chứng cứ fresh. Original old test quality vẫn kín.
4. Body/header/missing view, causal live receipt, source-domain calibration và multi-seed fair comparison; chưa đủ cơ sở chọn champion.
5. Chỉ formal 2–3 giờ sau data admission và khi user cho phép. Không in command formal giả ready: `formal_command=null`, engineering iteration complete=true, production objective complete=false.

### File thay đổi đúng lượt này

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/reports/REQUEST_PROFILE_20261030.json`
- `ai-training/scripts/evaluate-public-request.py`
- `ai-training/scripts/prepare-fresh-cohort.py`
- `ai-training/scripts/project-request-eve.py`
- `ai-training/scripts/request-pilot.py`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/http_benchmark.py`
- `ai-training/src/idps_ai/data/request_campaigns.py`
- `ai-training/src/idps_ai/data/request_corpus.py`
- `ai-training/src/idps_ai/data/sensor_decode.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/features/request_view.py`
- `ai-training/src/idps_ai/request_inference.py`
- `ai-training/src/idps_ai/training/models.py`
- `ai-training/src/idps_ai/training/partial.py`
- `ai-training/src/idps_ai/training/request_training.py`
- `ai-training/tests/test_partial_supervision.py`
- `ai-training/tests/test_request_bridge.py`
- `ai-training/tests/test_request_campaigns.py`
- `ai-training/tests/test_request_corpus.py`
- `ai-training/tests/test_request_profile.py`
- `ai-training/tests/test_request_training.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

## 28. Kiểm định đa nguồn và bounded request model — 2026-10-31T06:55:49.389997+07:00

### Phạm vi, kết quả và checkpoint tiếp tục

Tiếp mục 27 trên `feat/ai-model-training`, base HEAD `6c20b27`; nhánh đó đã đồng bộ remote từ yêu cầu trước. Lượt mới chỉ AI/docs: **không sửa Student/Security/contracts/docker, không commit/push mới, không train chính thức**. Root ignored: `ai-training/.artifacts/generalization_20261031/`; report: `ai-training/reports/GENERALIZATION_20261031.json`; handoff format 6. **Engineering PASS; cross-domain quality NOT_READY; chưa champion.** 170 pytest PASS/0 skip, 53 legacy technical gate PASS. Các report cũ và 1.479 protected path giữ SHA.

### Dữ liệu và nguồn công khai

- Thu **1.935 HTTP thật mới** trong private fixture/namespace, seed 7819301, 16 attack core grammar mới và 12 hard-negative text. Không gọi đây là 1.935 grammar độc lập. Ba client concurrent/360 giây, cùng một môi trường; gap 34.167,44 giây so cohort trước, vượt embargo 300 giây. Có 1.875 hợp đồng intent/expected HTTP tự động đúng, 60 HEAD/OPTIONS 403 pending. Giữ raw và full-intent diagnostic, không relabel. EVE: 1.935 HTTP/1.935 flow/443 alert; correlation đủ 3 nguồn ở 1.935/1.935 request. Private DB/backend/sensor đã dừng. Tổng lab **73.215 HTTP đủ 3 nguồn**, không cộng projection/file copy.
- Nguồn mới [SR-BH 2020 publisher](https://doi.org/10.7910/DVN/OGOIXX), metadata V1.2/CC0/unrestricted verified qua export API. File 436.437.661 byte, MD5 `173ec515308bdce5aec19cfd5b792596`, SHA `9c73c90ce6564ae48b14f7179cd864d037a6a130ef69c68c1626ec5d7ce4a910`. Large download gặp HTTP504; tải thành công qua HTTP206 byte ranges chính thức, kiểm Content-Range/size và checksum toàn file. Không dùng mirror hoặc fork relabel bằng LLM.
- Full audit: **907.815 dòng**, khác mô tả 907.814; **905.043 natural observation identities**, 2.772 duplicate, 26 nhóm cùng observation khác nhãn. Flag normal/attack nhất quán trong từng dòng không chứng minh nhãn ngữ nghĩa đã đúng. Hai dòng thiếu timestamp/method/URI giữ null/unavailable; 4.666 timestamp November 2020 ngoài giai đoạn July được mô tả giữ nguyên. Không tự sửa ngày, điền flow hoặc nhận là human review. Source training admission=0.
- HMAC sample 10%, độc lập label/prediction, có **90.531 record**. Full sample/date/duplicate là primary; unique/novel/day/family là sensitivity bổ sung. Có 348 nhóm raw70 numeric view trộn nhãn, ít nhất 3.774 label disagreements (~4,17%) với chính view đó. Không dùng floor này để giải thích mọi lỗi model. Body/header/response/behavior attack có thể ngoài quan sát URI.
- Adapter giới hạn CSV field 1 MiB, tối đa 1M dòng cho bản source đã pin. Không trả raw query/body/cookie/host/IP/header; identity là HMAC metadata, missing client giữ null. CAPEC chỉ là target. CodeInjection242 không được đoán thành XSS; mixed/unmapped family giữ None. Không status200/no-alert→benign. WAF-A-MoLE SQL query không được tính thành HTTP thật; Biblio access/terms chưa xác minh, không email tác giả; OpenCitations unknown vẫn 0 train.

### Phân tích → representation → sampling/loss → study

1. Audit frozen scores: ngưỡng GLU cũ 0,998768 cao hơn mọi 288 payload score ở cohort trước. Đây không phải optimizer/ONNX chưa chạy. Old supervised chỉ có 206 benign view, 16 cột hằng số; public-calibration benign tail đẩy ngưỡng lên. Ablation constant-column trên calibration không giải thích toàn bộ OOD tail; không retune test.
2. Fitting corpus giữ 115.980 record: 86.275 train/12.303 calibration/17.402 val. Old final-test quality không dùng. Pool mới có 19.741 view theo source/label/family: 18.714 benign, 1.027 positive; positive vẫn chỉ từ Student lab. Negative có CSIC/PKDD published normal training gốc. Source/family-balanced sampling chỉ chọn index có lặp trong SGD, không tạo dataset duplicate hoặc nâng HTTP count. Guard cấm double balancing; RNG/permutation/cursor được checkpoint.
3. Ablation 45 số bỏ route/method/length: benign-train-only domain probe balanced accuracy giảm 98,79%→76,92%, nhưng tạo 12 mixed-label vector group và ít nhất 1.249 fitting-label error. Giữ failure evidence, không áp dụng mặc định. Chỉ length/entropy/parameter-count stump đã đạt ~90% balanced accuracy trên original val: cảnh báo scenario shortcut, không phải bằng chứng identity/target leakage.
4. Bounded76 giữ đủ 70 số cũ và 6 minimum-count interaction. Flags/ratios giữ nguyên; số khác dùng `log1p(v)/(1+log1p(v))`. Không fit mean/std/vocabulary/test. Input70 và fused v5/207 không đổi tại chỗ. Encoder có hash riêng; CLI reencode giữ role/label và dữ liệu gốc. Chỉ 331/1.935 request có observed client span ≥300 giây; past flow dùng được 1.571, còn 364 null. Giữ causal v5; cần cohort dài và cold-start audit, không giả full history để train sequence model.
5. Phase1 có 7 config; phase2 có 4 config được chọn từ validation/information-loss audit, trước khi xem chất lượng cohort mới/SR-BH. Mỗi config 300 update, seed17/thêm seed29 cho45, batch128, lr0,0003, warmup15/cosine300, AdamW/clip1. Ở76cột: MLP219.144/GLU9.541.640/GLU615.944 tham số trainable thật, không padding. Family-weight0 so0,2 chỉ đổi raw-GLU val recall 68,945%→69,206%, không là lời giải tổng quát hóa.
6. Cả 11 fresh-process resume100→300 bằng continuous ở parameters/Adam/RNG/permutation/cursor/history. ONNX toàn115.980vector/model PASS rtol1e-5/atol1e-6, không nới tolerance. Controller wall608,63+417,26giây gồm reference/export; optimizer278,88giây, reference359,38giây ghi riêng. Per optimizer process cap300update/180giây; fit4CPU/affinity0–3,16GiB/high15GiB/swap0. Max optimizer sensor sample79°C, không guard trip; long endurance NOT_RUN.
7. Giữ threshold là max source-specific benign calibration quantile tại target FPR1%. Validation eligibility: FPR thực đo ≤1% ở từng source, chọn macro recall4họ rồi AP. Joint selection khóa `bounded76-glu17` trước one-look quality. Đây là research challenger, không champion. Binary temperature đơn điệu không cải thiện ranking ở cùng FPR đã recalibrate; không coi là detection fix. Brier/NLL/ECE và quantile có trong report, không là probability production.

### Hai cohort mới — không chọn từ test

| Candidate | New lab recall / FPR | SR-BH recall / FPR | URI→privacy→ONNX p95 |
| --- | --- | --- | --- |
| Previous MLP217k |18,06% /0%|25,47% /0,268%|0,208ms|
| Previous GLU9,535M |6,94% /0%|7,16% /0,108%|4,684ms|
| Bounded MLP219k |48,26% /6,492%|31,88% /2,118%|0,229ms|
| Bounded GLU9,542M, selected by validation |49,31% /0%|8,64% /1,007%|4,857ms|
| Bounded GLU616k |22,57% /0%|2,03% /0,168%|0,277ms|

New-lab primary có **1.659 record=1.371 benign+288 intent thuộc bốn họ payload**. Full1.935 intent diagnostic, pending60 và unsupported UA/sequence216 giữ nguyên. Selected GLU phát hiện SQLi18/72, XSS72/72, traversal31/72, command21/72; không gọi đây là XSS100% production. Full all-family intent recall28,17%, FPR0. 0FP/1.371 có IID one-sided95% upper bound~0,218%; correlation và nhãn tự động còn hạn chế. Precision/Recall/F1/AP/confusion/day/CAPEC/novel/unique của14candidate nằm trong report; không dùng accuracy đẹp làm chứng nhận.

GLU mới cải thiện lab variant nhưng vẫn kém old MLP ngoài miền: **chưa giải quyết tổng quát hóa**, không tăng epoch hoặc ép model lớn thắng. Positive training vẫn một Student lab; missing body/header, scenario/corpus prior và domain shift còn mở. Scope public multilabel khác lab4payload: chỉ so sánh model trong cùng cohort. Latency100repeat/5warmup một URI, model-only và end-to-end là series riêng, không throughput/network/TLS SLO. Mọi quality cohort vừa chấm nay đã exposed; old final-test quality vẫn kín.

### Kiểm thử, lệnh và bảo toàn

Các path dưới đây là template rút gọn; argv/cgroup, frozen plan, per-model YAML, log và SHA ở artifact root. Không cần chạy lại study đã hoàn tất.

| Lệnh/nghiệm thu | Trạng thái / evidence |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 IDPS_AI_TEST_SURICATA_RUNTIME=<upgrade_20261028/tools/runtime> taskset -c 0-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**170/0skip/66.80giây;Ruff/format/compile/canonical/Web diff, `checks-release.log` |
| `idps-ai request-reencode --dataset <oldrequestcorpus> --output <newboundedcorpus> --encoding bounded-request-v1` | **PASS**, CLI tests giữ roles/labels/source immutable |
| `python scripts/import-real-http.py --raw-dir <private> --output <newaudit> --identity-key <privatekey> --sample-fraction 0.1` | Execution **PASS**; data admission **NOT_READY** |
| `python scripts/study-request-generalization.py --raw-dataset <raw70> --encoded-dataset <encoded> --output <newstudy> --cpus 4 [--plan <fixedphase2.json>]` | **PASS**11config, exact resume/all-row ONNX |
| `python scripts/analyze-request-study.py ...` | **PASS**, validation only; phase/joint selection hash khóa trước test |
| `python scripts/evaluate-request-generalization.py --registry <frozen-registry> --real-data <SRBH-audit> --lab <ownedlab> --eve <actualEVE> --output <newout>` | Execution **PASS**14models; cross-domain quality **FAIL/NOT_READY** |
| `python scripts/evaluate-request-generalization.py --registry <registry> --output <newlatency.json> --latency-only` | **PASS**, sau các CPU job; overwrite guard đã test |
| `idps-ai readiness --dataset <scale_upgrade/prepared-v5> --data-kind lab_capture --provenance <prepared_provenance.json> --policy configs/expanded_policy.yaml --output <newreadiness>` | **PASS**53/53legacy technical; không phải request/SR-BH formal admission |
| Frozen package source/environment/CLI contract replay | **PASS**cả hai source epoch/300step,0optimizer update; không force hash |
| Protected SHA / original Web diff | **PASS**1.479path, old reports/HEAD giữ nguyên |
| Formal training / old final-test quality / independent human review / live TLS/IPS /2M endurance | **NOT_RUN** |

RED tests thiếu module/API, source thiếu timestamp, downloadHTTP504 và lỗi đóng gói replay ban đầu đã sửa; log/partial evidence giữ lại. Final pytest đều PASS; không đổi data/model quality FAIL thành PASS. Replay ban đầu dùng nhầm base interpreter và thiếu schema/producer context; đã bổ sung requirements, schema config và 6 producer file copy pin hash trong artifact AI. Cả source/environment đều khớp checkpoint thực tế, không chạy thêm optimizer.

Core package snapshots và per-model YAML/worker logs giữ nguyên. Phase1 controller sau đó thêm optional plan; không nhận current-controller SHA là SHA cũ. Replay bằng original worker argv/YAML và frozen package. Sau study chỉ `real_http.py` đổi nullable missing-client metadata; 90.531 sample không có empty-client hash nên tensor/score không đổi. Không force-resume bằng active package; dùng frozen package. Sau latency chỉ thêm overwrite guard, không tính lại hoặc phủ metrics.

Dọn **824,883 byte** cache tái tạo được: generated Python/pytest/lint và prefix64KiB đã so từng byte với full original, không runtime reference. Giữ raw/key/checkpoint/source/failure evidence/score matrix. Private lab và các owned training/eval unit đã dừng; không tắt service khác của user.

### Còn mở và tiếp tục

- Review nhãn/visibility/provenance SR-BH:26conflict,2missing,November. Independent human review=0, scale admission=0/2M. Request-profile admission phải phù hợp capability; không ép source thiếu flow thành giả full schema hoặc đánh đồng với53fused gate.
- Freeze source/template/client/time roles và300giây embargo trước real-positive training; cần sealed holdout mới. Không biến test đã exposed thành fresh evidence. Ưu tiên hard negatives khớp độ dài, nhiều application và nhiều thời điểm; không copy/suffix để nâng số lượng.
- Cohort hành vi dài hơn, cold-start/missing-clock/độ phân giải1giây và receipt-time audit; không tự đổi207contract hoặc hai Web.
- Formal multi-seed/endurance/live integration chỉ sau data/model admission và user cho phép. `formal_command=null`; engineering iteration complete=true, production objective complete=false.

### File thay đổi đúng lượt này

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/reports/GENERALIZATION_20261031.json`
- `ai-training/scripts/analyze-request-study.py`
- `ai-training/scripts/evaluate-request-generalization.py`
- `ai-training/scripts/import-real-http.py`
- `ai-training/scripts/prepare-fresh-cohort.py`
- `ai-training/scripts/study-request-generalization.py`
- `ai-training/src/idps_ai/cli.py`
- `ai-training/src/idps_ai/data/real_http.py`
- `ai-training/src/idps_ai/data/request_campaigns.py`
- `ai-training/src/idps_ai/data/request_corpus.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/features/request_encoding.py`
- `ai-training/src/idps_ai/features/request_preprocessing.py`
- `ai-training/src/idps_ai/request_inference.py`
- `ai-training/src/idps_ai/training/generalization.py`
- `ai-training/src/idps_ai/training/request_training.py`
- `ai-training/tests/test_real_http.py`
- `ai-training/tests/test_request_campaigns.py`
- `ai-training/tests/test_request_corpus.py`
- `ai-training/tests/test_request_encoding.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

## 29. Curation toàn bộ SR-BH, admission đa nguồn và holdout mới — 31/10/2026, 10:10 ICT

### Phạm vi và kết luận

Tiếp tục trên `feat/ai-model-training`, HEAD `6c20b27ace91b0cb112dbdea5ca6720adbfc7941`. Đã lưu baseline code/docs và hashes trước khi làm. Chỉ sửa AI/docs, giữ nguyên Student Web, Security Web, contracts và Docker. Không chạy lại 11 study lịch sử, không training dài, không chọn champion hoặc bật enforcement.

**Kỹ thuật PASS; corpus đa nguồn NOT_READY để train.** Có 0 cập nhật trọng số trên dữ liệu mới. Mục tiêu production và 2 triệu request chưa hoàn thành, scale-admitted=0. [Báo cáo dữ liệu](../ai-training/reports/DATA_QUALITY_20261031.json), [handoff format 7](../ai-training/FINAL_TRAINING_HANDOFF.json). Artifact riêng tư nằm tại `ai-training/.artifacts/data_quality_20261031/`.

### Dữ liệu → curation → chia tập

Đã audit/project toàn bộ **907.815 dòng** SR-BH gốc, publisher V1.2/CC0. Một lượt đọc CSV trực tiếp độc lập đối chiếu đủ source SHA, event HMAC, index từ 0, nhãn gốc, timestamp và body availability với ledger. Giữ nguyên file 436.437.661 byte và MD5/SHA; không sửa dữ liệu để khớp mô tả 907.814 dòng của publisher.

Policy `http-curation-1` quarantine mọi thành viên của nhóm mâu thuẫn natural identity hoặc model view; body-present ngoài task URI-only; missing timestamp/client/URI; ngày ngoài July và unsupported attack scope. Không majority vote, sửa ngày, điền IP/flow giả hoặc đoán CAPEC242 thành XSS. Mỗi dòng có quyết định, nhãn gốc và lý do; raw/key/ledger không được publish.

Kết quả: **310.314 accepted research candidates, 597.267 quarantine, 234 quyết định duplicate**, cộng đủ 907.815. Có 2.772 duplicate trong bản gốc; các duplicate bị quarantine vì lý do khác không tính lại vào nhóm 234. Reason counts chồng lấp, không cộng thành tổng số dòng loại. Candidates gồm 69.228 benign và 241.086 positive: 227.784 SQLi, 12.141 traversal, 1.161 command. Không còn exact observation duplicate hoặc binary model-view conflict trong candidates. Một model-view group còn khác positive family; chưa chứng nhận family classification, family inference vẫn tắt. Chưa có review nhãn ngữ nghĩa độc lập.

Full fixed76 input có **1.415 nhóm mâu thuẫn nhãn**, ảnh hưởng 508.500 dòng; tối thiểu 39.641 label disagreements tại cùng biểu diễn. Đây là sự mơ hồ của góc nhìn URI, không tự chứng minh publisher sai hoặc mọi lỗi OOD đều không tránh được. Header/body/response/time-dependent signals còn thiếu.

Registry cố định cutoff 21/07 và 25/07 UTC, vùng biên ±300s. Campaign hoặc client+UTC-day, related variant và exact model view thuộc role sớm nhất; dòng xuất hiện ở role sau bị quarantine, không chuyển về train. SR-BH là development đã exposed. Gen1/gen2 lab cohort từng chấm được declassify rõ thành development calibration/validation, không supervised train. Original final-test quality và holdout mới không dùng.

Input 350.057 dòng tạo **347.323 research staging records**: train 344.980, calibration 1.318, validation 1.025; quarantine thêm 2.734 dòng với ledger riêng. Pilot subset chọn theo event HMAC độc lập nhãn có **98.766 vectors**: 96.423/1.318/1.025. Không tính đây là HTTP mới. Cross-role group/model-view overlap=0, per-source observed time gap ≥300s; chưa chứng minh semantic-template independence hoặc persistent-client-unseen generalization.

### Admission, model và kiểm thử

Audit phát hiện proof ban đầu chỉ kiểm đủ hai lớp toàn corpus, bỏ sót coverage theo nguồn. Viết regression test RED rồi sửa producer và trainer **trước khi có bất kỳ model update nào**. Giữ proof ban đầu làm bằng chứng superseded. Bản `mixed-curated-v2` bind admission mới, giữ nguyên shards và nhãn. Trainer còn kiểm tra trực tiếp class counts của pilot nên proof cũ yếu hơn cũng không được bypass.

Gate yêu cầu hai lớp ở từng source/role và tối thiểu 32 record/class/source/role. Đây chỉ là floor kỹ thuật, không đủ chứng minh FPR thấp. SR-BH positives đủ scope/visibility/consistency chỉ có ngày 17–19/07; theo split đã đăng ký, calibration còn **5 benign/0 positive**, validation **1/0**. Failed gates: `source_role_class_coverage`, `source_role_minimum_support`. Không dịch cutoff, sửa nhãn hoặc bỏ novelty gate để lấy điểm. CLI train thực trả exit 2 trước optimizer, không checkpoint/weights mới. Real-data MLP/GLU study **SKIPPED**.

Thêm opt-in `curated_multisource` và `domain_family_balanced`: class → source → positive family; chỉ resample index SGD, giữ RNG/cursor checkpoint, không nhân bản corpus. Giữ loss/AdamW/schedule, raw70/bounded76/fused207 và inference contract. Không thêm source/nhãn/SID/secret vào tensor. Fixture nhỏ hai nguồn kiểm MLP/GLU exact resume so reference và ONNX tại rtol=1e-5, atol=1e-6. Đây là kiểm thử kỹ thuật synthetic, không phải pilot dữ liệu thực hoặc bằng chứng tăng chất lượng. Các baseline, weights, thresholds, scores và report lịch sử giữ nguyên.

### Holdout mới và nghiên cứu nguồn công khai

Protocol đăng ký trước capture/tải, cấm dùng holdout để train, calibration, selection hoặc phân tích model score. Thu **1.935 HTTP thật trong 720,528 giây**, seed 991473, ba client concurrent và grammar mới. Tổng lab **75.150 HTTP** đủ ba nguồn. Gap so cohort exposed trước là 13.238,17 giây. Vẫn cùng Student fixture, nhãn runner intent, chưa độc lập ứng dụng hoặc human review.

Technical QA xác nhận 1.935/1.935 request có Student/Nginx/EVE và flow; kernel packet drops=0. Có 1.129 request với observed client span ≥300s, 325 với span ≥600s. Một setup record trong audit/Nginx nằm ngoài cohort và không tính thêm. Span hoặc closed-flow evidence không chứng minh flow cùng request đã sẵn sàng tại thời điểm quyết định. Không phân tích chất lượng model/nhãn để thay features.

Lab và EVE dẫn xuất có marker sealed. Curation, assembly và research evaluator từ chối directory hoặc ancestor có marker trước khi đọc observations. Regression RED bắt guard thiếu ở evaluator và trường hợp truyền directory trực tiếp; đã sửa và GREEN. Guard này không kiểm soát việc copy thủ công ra file không có marker.

[Zenodo production 30 ngày](https://zenodo.org/records/17178461), DOI10.5281/zenodo.17178461, CC BY 4.0: archive 29.524.147 byte; MD5 `95b7a8237abc163d8ca31e49f7318efd`, SHA256 `3c4c976f58cd2da61a543a237ede770529ceee59cdb09295a5998d420a8b30b8`. Giữ kín, **chưa giải nén, chưa biết số request đạt kiểm định, chưa score**. Đây là CRS-selected positive-only data; không ground truth độc lập hoặc benign-FPR benchmark, không đủ dùng một mình chọn champion.

Đã nghiên cứu ATRDF/FWAF official repositories nhưng chưa xác minh được license tái sử dụng; không tự import. FWAF query text không được tính thành HTTP thực. Org X/Y Zenodo20001206 có metadata MIT nhưng chưa nhãn request đáng tin; không tự gán benign. CSIC/PKDD original normal training và OpenCitations unknown giữ nguyên; không public test→train hoặc gán nhãn giả.

### Lệnh và kết quả thực chạy

`<root>` dưới đây là `ai-training/.artifacts/data_quality_20261031`. Exact argv/cgroup nằm trong `curation-command.json`, `assembly-command.json`, `blocked-study-proof.json`. Output cũ được bảo toàn.

| Lệnh/check | Kết quả và bằng chứng |
| --- | --- |
| `systemd-run --user --collect --unit=idps-curate-srbh-20261031 -p CPUQuota=400% -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 ... python ai-training/scripts/curate-http-corpus.py --source <original> --download-manifest <pinned> --identity-key <private> --output <new>` | **PASS**, 907.815 dòng; peak RSS 262.877.184 byte, CPU temperature sample tối đa 78°C, không thermal trip; `srbh-curated/resources.json` |
| `python <root>/verify-source-rows.py` | **PASS** đủ 907.815 original metadata/labels; `full-row-verification.json` |
| `systemd-run ... python ai-training/scripts/assemble-curated-http.py --registry <root>/source-registry.yaml --output <root>/mixed-curated` | Execution **PASS**; phát hiện admission bug trước fit; active correction `mixed-curated-v2` là **NOT_READY** |
| `idps-ai request-train --dataset <root>/mixed-curated-v2 --run-dir <root>/blocked-real-run --config <root>/blocked-study-config.yaml --diagnostic-updates 100 --cpus 4` | **PASS_EXPECTED_REJECTION**, exit 2, 0 updates/checkpoints; real study **SKIPPED** |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 IDPS_AI_TEST_SURICATA_RUNTIME=<runtime> taskset -c 4-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**, 183 tests/0 skip/77,97s; Ruff/format/compile/schema/original Web diff; `checks-release-final.log` |
| `idps-ai readiness --dataset ai-training/.artifacts/scale_upgrade_20261030/prepared-v5 --data-kind lab_capture --provenance ai-training/.artifacts/scale_upgrade_20261030/prepared_provenance.json --policy ai-training/configs/expanded_policy.yaml --output <root>/readiness-current` | **PASS** 53/53 legacy technical checks; không phải multisource admission |
| Owned lab capture `request-challenge-3`, `lab-stop`, `decode-pcap`, `python <root>/audit-sealed-metadata.py` | **PASS** technical coverage/cleanup; `sealed-metadata-audit.json`, không model-quality scores |
| `python ai-training/scripts/seal-http-holdout.py ...` | **PASS** metadata/license/hash; archive chưa giải nén; `new-sealed-holdout/seal.json` |
| Protected SHA/raw SHA/manifest verification | **PASS**, 1.599 file, original Web diff=0, HEAD không đổi; `preservation.json` |
| Real-data study / formal training / sealed quality / human review / 2M endurance / live TLS, IPS, enforcement | **SKIPPED** real study vì data NOT_READY; các mục khác **NOT_RUN** |

Một lượt test bị guard từ chối do tôi sửa source khi nó đang chạy: 182 PASS/1 FAIL, `Source changed after readiness; rerun the data gate`. Đã chạy lại toàn bộ trên source cố định: **183 PASS**, không nới guard. Giữ `checks-final-acceptance.log` và worker diagnostic `test-invalidation.stderr.log`. RED failures là bằng chứng bước phát triển; không thay data/model-quality FAIL thành PASS.

### Cleanup và bảo toàn

Chỉ xóa **830.636 byte/73 file cache** Python/pytest/Ruff tái tạo được, đã xác minh untracked. Giữ SQLite curation khoảng 1,2 GB để review; raw, key, PCAP/EVE, checkpoints, model weights, score matrices, frozen packages, failed-attempt evidence và old reports. 1.599 protected file giữ SHA, raw SR-BH giữ toàn-file checksum. Private DB/backend/sensor đã dừng; ports 18880/18881/55435 không listen. Không dừng service khác. Artifact vẫn local/ignored, chưa shared store.

### Điểm tiếp tục

`CURRENT_WORK.json` và handoff format 7 trỏ tới curation manifest, active v2 admission, holdout seals, test logs và report SHA. Không cần làm lại full audit hoặc 11 study lịch sử. Bước tiếp có giá trị là review nhãn/visibility, bổ sung cả benign/attack ở nguồn, môi trường và thời điểm độc lập cùng hard negatives có cấu trúc tương đồng; đăng ký development protocol có đủ source-role support trước fit.

Không dùng sealed holdout để tối ưu, không dịch cutoff chỉ để có score. Sau admission PASS mới chạy matched baseline study ngắn; chỉ xét champion khi có bằng chứng độc lập. Nếu mở rộng input cần đổi hai Web thì chỉ ghi đề xuất cho luồng sở hữu. `engineering_iteration_complete=true`, `production_objective_complete=false`, `formal_command=null`, chưa champion và scale-admitted=0/2M. Không có chất lượng model mới để báo; report lịch sử nguyên byte.

### File thay đổi đúng lượt này

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/reports/DATA_QUALITY_20261031.json`
- `ai-training/scripts/assemble-curated-http.py`
- `ai-training/scripts/curate-http-corpus.py`
- `ai-training/scripts/evaluate-request-generalization.py`
- `ai-training/scripts/seal-http-holdout.py`
- `ai-training/src/idps_ai/data/curated_split.py`
- `ai-training/src/idps_ai/data/http_curation.py`
- `ai-training/src/idps_ai/data/request_campaigns.py`
- `ai-training/src/idps_ai/data/request_corpus.py`
- `ai-training/src/idps_ai/data/sensor_lab.py`
- `ai-training/src/idps_ai/training/request_training.py`
- `ai-training/tests/test_curated_split.py`
- `ai-training/tests/test_http_curation.py`
- `ai-training/tests/test_request_campaigns.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

## 30. Phục hồi partition và study đa nguồn có giới hạn — 31/10/2026, 11:20 ICT

### Phạm vi và kết luận

Nhánh `feat/ai-model-training`, HEAD giữ `6c20b27ace91b0cb112dbdea5ca6720adbfc7941`. Chỉ AI/docs; không sửa Student Web, Security Web, contracts hoặc Docker. Lưu baseline source/docs và 2.284 protected SHA trước khi làm. Không chạy lại full SR-BH projection hoặc các study lịch sử đã hoàn thành; raw/nhãn/quarantine/checkpoint/report/holdout cũ giữ nguyên.

**Đã khôi phục đủ support cho study development hồi cứu. Chưa đạt đánh giá độc lập hoặc production.** Không champion, không formal training, không mở holdout, scale-admitted=0/2M. [Report](../ai-training/reports/PARTITION_RECOVERY_20261031.json), [handoff format 8](../ai-training/FINAL_TRAINING_HANDOFF.json). Root private: `ai-training/.artifacts/partition_recovery_20261031/`.

### 1. Phân tích nguyên nhân, không sửa nhãn

Tái sử dụng 310.314 candidates đã curation. Toàn bộ 241.086 supported positives xuất hiện trước cutoff21/07: protocol cũ tự đặt tất cả vào train. Calibration có 1.134 benign, bỏ3 dòng vì embargo và1.126 vì encoded view đã có trước, còn5; validation622 benign, bỏ1 vì embargo và620 do view, còn1. Tổng embargo cũ chỉ5 dòng, không phải nguyên nhân chính. Timestamp, ngày November và missing metadata giữ nguyên; không sửa parser để tạo thêm attack hoặc chuyển label.

Audit riêng src_ip trên907.815dòng gốc:907.813dòng cùng một địa chỉ private,2missing. Không thể suy ra attacker/campaign identity từ field này. Client+UTC-day chỉ là day block; không đếm thành nhiều chiến dịch độc lập. Kết quả chỉ lưu counts/class, không địa chỉ gốc.

### 2. Protocol development có căn cứ

Đăng ký `FORWARD_PROTOCOL.json` trước fit, chỉ một phương án whole active UTC days: train trước18/07, calibration18/07, validation từ19/07. Đây là dữ liệu đã exposed, không test cuối độc lập. Không tìm nhiều cutoff theo score. Giữ ±300s boundary exclusions và các group/related-view/model-vector conflict/overlap rules. Không đưa dòng tương lai về train, không đổi nhãn hoặc đưa quarantine cũ vào candidates. Protocol cũ giữ làm diagnostic benign drift muộn.

Input339.507 sau10.555 boundary exclusions →328.117 accepted staging +11.390 split quarantine. Staging train132.845/cal172.572/val22.700. HMAC pilot cap theo source/role, độc lập nhãn, tạo118.760vectors:96.423train/11.313cal/11.024val. Không cộng projection/subset thành HTTP mới. Source/role pilot benign/positive:

| Nguồn | Train | Calibration | Validation |
| --- | --- | --- | --- |
| SR-BH |17.906/42.094|1.536/8.464|4.845/5.155|
| Student lab |29.511/6.912|1.025/288|736/288|

Actual group/model-vector overlap xuyên role=0. Pilot gaps SR-BH631s/651s, lab43.480,38s/34.167,89s. Mỗi source/role có≥32record/class và≥32unique model views/class; không dùng repeated vectors để lấp floor. Floor kỹ thuật không chứng nhận FPR hoặc effective sample size.

Assembly đầu chạy producer trước khi thêm audit unique support; giữ bản đó. `forward-development-v2` bind proof bổ sung từ actual feature-shard audit, giữ nguyên mọi data shard/label. Trainer final kiểm actual counts/views/gaps trước optimizer, không chỉ tin manifest. Không chạy lại full assembly chỉ để thay proof. CLI mới có `--audit-dataset` để tiếp tục kiểm phân bố mà không xây lại corpus.

**Giới hạn không được che giấu:** full-source label-dependent curation đã dùng nhãn toàn nguồn để loại contradictions trước split. Đây là population hồi cứu đã lọc; day ordering không làm nó thành prospective estimate không thiên lệch. Không model/threshold fit trên validation nhưng selection bias của curation còn tồn tại. Source day groups không chứng minh independent attackers; SR-BH pilot train thiếu command positives và cal chỉ1 traversal positive. Family loss=0, family inference tắt. Independent/prospective acceptance=false trong EVALUATION_SCOPE/handoff; cần dữ liệu/protocol khác để nghiệm thu thật.

### 3. Nguồn công khai, archive và nhãn

Tải OrganizationX từ Zenodo DOI10.5281/zenodo.20001206, MIT,2.135.289byte, MD5`b4bf79effa6f3ee1b9e53f278d916620`, SHA`1429caba2803c3e8c90e9fb287bc04f6f8249f8bb34712b39127044e134d631f`. Bounded ZIP/gzip streaming, không extract, không xuất PII. Audit17access members:213.205lines,213.182parseable HTTP rows,2.004repeated log observations,211.178distinct observations,23unparsed giữ trong raw. Không có request IDs để chứng minh đây là từng physical request duy nhất.

Có39 YAML pattern rules; ví dụ Python+POST/HEAD→RCE, readme.txt+UA→traversal và nonmatch→benign không phải independent label truth. Không áp dụng chúng để tạo nhãn; **mọi observation giữ unknown,0supervised/benign-only admission**. ArchiveY390MB cùng cơ chế nhãn không được tải chỉ để tăng số lượng.

Mendeley1,8M XSS có license CC BY4.0 nhưng chỉ Query/Label payloads; không cộng thành captured HTTP. HttpParams MIT là parameter values có lineage CSIC/tools/FuzzDB, không coi là source độc lập. MendeleySQLi64k chỉ xác minh landing license, public file API thử trả404, chưa xác minh schema/capture lineage nên không admission. Existing CSIC/PKDD splits và unknown OpenCitations giữ nguyên.

Archive30day đã khóa **không giải nén**: yêu cầu giữ holdout được ưu tiên khi audit archive. Chỉ kiểm metadata/hash từ trước; không score hoặc lấy vào train/calibration. Tổng lab75.150HTTP không đổi,0HTTP mới thu lượt này; không cộng211.178unknown observations vào training count. Scale-admitted=0/2M.

### 4. Study ngắn và kết quả thực

Một plan cố định seed17 trước fit: MLP256(219.144params), GLU256(615.944), GLU1024(9.541.640), mỗi neural300update/batch128/lr0,0003/warmup15/cosine300, cùng eligible unique-view pool/class-source-family sampler. Binary partial loss, family-weight0; không HPO hoặc tăng epoch sau kết quả. Logistic77params,C1/max_iter200 dùng cùng pool và matching weights, là classical control, không giả chi phí optimizer bằng neural.

Threshold=max source-specific benign calibration quantile tại targetFPR1%; không dùng validation/test để chọn ngưỡng. Exact100→300 resume qua process mới khớp continuous parameters/Adam/RNG/permutation/cursor/history ở cả3neural. ONNX toàn118.760vectors/model PASSrtol1e-5/atol1e-6; logistic không ONNX/deployable bundle. Controller241,64s trong cgroup4CPU/16GiB/high15GiB/swap0,không formal training.

| Model | SR-BH Recall/FPR | Lab Recall/FPR | Model-only p95 |
| --- | --- | --- | --- |
| MLP219k |22,83%/0%|12,50%/0%|0,055ms|
| GLU616k |1,03%/0%|0%/0%|0,165ms|
| GLU9,54M |31,37%/0,289%|18,06%/10,73%|4,184ms|
| Logistic77 |49,60%/0,186%|12,50%/16,98%|0,053ms|

MLP/smallGLU empirical FPR budget PASS nhưng recall thấp. LargeGLU/logistic không đạt≤1%FPR từng nguồn, không thắng chỉ vì SR-BH recall cao. Không chọn model/champion. Precision/F1/AP/confusion, calibration và per-source/family scores có trong report; binary family-vs-same-source-benign slices không phải multiclass family classification hoặc extra requests. Latency batch1/50repeat/5warmup, không end-to-end/TLS/throughput SLO.

Threshold vẫn cao, ranking và calibration tail phụ thuộc nguồn; không sửa ngưỡng theo validation. Source probe chỉ fit benign train, depth4, đạt86,74% balanced accuracy trên benign validation;21 cột hằng. Domain cues còn, không tự chứng minh target leakage. Không xóa features hoặc chạy thêm HPO theo probe. Kết quả khác cohort lịch sử nên không tuyên bố controlled independent improvement.

Sau study chỉ sửa edge case diagnostic family=None và pilot cap mất benign train. Không đổi model/input tensors; final-source tests PASS. Giữ frozen package + requirements/config/data của study; frozen source/environment identity readback khớp300step,0extraoptimizerupdate. Không force current-source resume và không lặp study để thay evidence.

### 5. Lệnh và nghiệm thu

`<root>` là artifact root ở trên; các output được giữ nguyên. Exact study argv/cgroup/env ở `study-command.json`; protocol/registry/data/source hashes trong report.

| Lệnh/check | Trạng thái và evidence |
| --- | --- |
| Audit curation metadata và raw src_ip aggregate | **PASS**, `partition-diagnosis.json`, `cutoff-cause-analysis.json`, `source-identity-quality.json`; không làm lại heavy projection |
| `systemd-run --user --collect --unit=idps-forward-assembly-20261031 -p CPUQuota=400% -p AllowedCPUs=0-7 -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 ... python ai-training/scripts/assemble-curated-http.py --registry <root>/forward-source-registry.yaml --output <root>/forward-development` | Execution **PASS**; actual audit và active-v2 proof **PASS retrospective research support only** |
| `systemd-run --user --collect --unit=idps-curated-study-20261031 -p CPUQuota=400% -p AllowedCPUs=0-3 -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 -p RuntimeMaxSec=900 ... python ai-training/scripts/study-curated-http.py --dataset <root>/forward-development-v2 --output <root>/study --cpus 4` | **PASS** technical development only; three neural×300update/exact resume/ONNX,logistic control; `study/report.json` |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 IDPS_AI_TEST_SURICATA_RUNTIME=<runtime> taskset -c 4-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**,191tests/0skip/71,93s,Ruff/format/compile/canonical/originalWebdiff; `checks-release.log` |
| `idps-ai readiness --dataset ai-training/.artifacts/scale_upgrade_20261030/prepared-v5 --data-kind lab_capture --provenance ai-training/.artifacts/scale_upgrade_20261030/prepared_provenance.json --policy ai-training/configs/expanded_policy.yaml --output <root>/readiness` | **PASS**53/53legacytechnicalonly,không independent acceptance cho study mới |
| `audit_http_zip(<original-org-X-archive>)` và validation-only score/source probe | **PASS** technical audit,0pseudo-labels,noholdout/noHPO; artifact archive/score/probe reports |
| Frozen source/environment identity readback | **PASS**,`frozen-replay-identity.json`,0optimizerupdates |
| Protected SHA/original Web diff/HEAD/holdout seals | **PASS**,2.284files nguyên,sourceWebdiff0,HEAD không đổi |
| Formal training / sealed quality / independent review /2M endurance/liveTLS/IPS/enforcement | **NOT_RUN**,chưa champion |

Regression RED logs được giữ: thiếu audit API/unique support; parser bỏ sót web-access.log prefix đã sửa và re-audit; nullable family và empty-benign cap edge case đã sửa. Final suite191PASS. Không biến data/model-quality NOT_READY thành production PASS.

### 6. Bảo toàn và điểm tiếp tục

Chỉ dọn813.083byte/70file Python/pytest/Ruff cache tái tạo được, đã xác minh untracked. Giữ rawZIP/CSV,PCAP/EVE,keys,all-row/quarantine ledgers,SQLite indexes,checkpoints,weights,scores,frozenpackages và failed-attempt evidence. Không khởi động lab service mới; owned study/assembly units đã dừng, không dừng service của user. Artifacts vẫn local/ignored, chưa shared store.

`CURRENT_WORK.json`, handoffformat8 và report chứa điểm tiếp tục. Không chạy lại full audit hoặc study hoàn tất. Tiếp theo cần nhãn độc lập/visibility review, nguồn ứng dụng mới có benign và attack trong nhiều campaign/thời điểm, matched hard negatives; protocol prospective hoặc leave-environment-out không phụ thuộc future-label exclusion. Giữ holdout kín đến final freeze; positive-only archive không đủ đo FPR/chọn champion. Nếu cần input mới sửa hai Web, chỉ đề xuất cho luồng sở hữu. Không formal train/epoch kéo dài khi chưa có data/model admission và user authorization.

Engineering iteration complete=true; production objective complete=false. Corpus hiện chỉ admitted cho bounded retrospective development, không independent/prospective/production acceptance; scale-admitted=0/2M,formalcommand=null,nochampion.

### File thay đổi đúng lượt này

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/reports/PARTITION_RECOVERY_20261031.json`
- `ai-training/scripts/assemble-curated-http.py`
- `ai-training/scripts/study-curated-http.py`
- `ai-training/src/idps_ai/data/curated_split.py`
- `ai-training/src/idps_ai/data/real_http.py`
- `ai-training/src/idps_ai/training/request_training.py`
- `ai-training/tests/test_curated_split.py`
- `ai-training/tests/test_public_accesslogs.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`

## 31. Nguồn benign mới, chẩn đoán domain shift và frozen external stress — 01/11/2026, 06:47 ICT

### Phạm vi và kết luận

Nhánh `feat/ai-model-training`, HEAD giữ `6c20b27ace91b0cb112dbdea5ca6720adbfc7941`. Chỉ AI/docs, không sửa Student Web, Security Web, contracts hoặc Docker. Lưu baseline source/docs và 2.682 protected SHA trước khi làm; toàn bộ raw, nhãn, checkpoint, report và holdout cũ giữ nguyên. Không lặp SR-BH heavy audit hoặc các study đã hoàn tất.

**Đã mở rộng dữ liệu và đo frozen model trên miền benign mới; chưa đủ independent balanced acceptance hoặc formal training.** Không cập nhật trọng số/ngưỡng, không chọn champion hoặc tự động chặn. Scale-admitted=0/2M. [Report mới](../ai-training/reports/GENERALIZATION_QUALITY_20261101.json), [handoff format 9](../ai-training/FINAL_TRAINING_HANDOFF.json). Root private `ai-training/.artifacts/generalization_quality_20261101/`.

### 1. Chẩn đoán trước khi thay thuật toán

Dùng weights/threshold và scores development trước, không mở holdout. GLU có 79 FP/736 benign lab, đều thuộc `new_hard_negative`; cả ba campaign có 25–28 FP. Train pool sau dedup chỉ 206 benign lab views, 1.027 positive; SR-BH 10.059 benign/15.850 positive. Nearest-view L1 trên 76 số: FP gần positive hơn benign (median 1,027 so 1,351), chỉ là numeric proximity, không chứng minh malicious intent hoặc nguyên nhân duy nhất. Các mẫu này có cú pháp giống attack trong hành vi hợp lệ; không relabel.

Calibration threshold cũ GLU 0,9984238, MLP 0,9999802 không đổi. Sampling cân class/source/family không bù thiếu ngữ nghĩa/độ phủ; domain cues và missing body/header/context còn. Monotone temperature không sửa ranking tại cùng FPR. Không mở thêm HPO/epoch/params trên cùng validation khi chưa có positive độc lập. Thay vào đó khóa hai bundle/model hashes và threshold trước một nguồn benign mới, đo stress FPR mà không fit thêm.

Bổ sung helper grouped evaluation: fixed threshold, cluster-bootstrap 200 replicate; dưới 8 nhóm không cấp cluster CI. Trên validation cũ chỉ 3 nhóm/source, CI cluster để null. IID Wilson báo riêng, không dùng 0 FP để khẳng định 0 risk. Đây là floor kỹ thuật và các interval có giả định, không chứng nhận độc lập/human truth.

### 2. Nguồn công khai và audit

[open-appsec WCP publisher](https://github.com/openappsec/waf-comparison-project) công bố legitimate captures từ thao tác browser và cấp Apache-2.0 rõ ràng cho legitimate dataset. Pin revision `8ec8263eebba76816601f7c7052f8ffb83e31312`; README/LICENSE/config SHA khớp revision. Không áp Apache license này cho malicious payload collection từ MGM có mixed copyright/lineage. Không nhập payload được bọc request rồi gọi là HTTP độc lập.

Archive gốc 1.203.983.791 byte, SHA 256 `58faee18c54229759287a574f6f8cb1e3b951fa135e403ea9a679d2b18efd778`. Nguồn không cung cấp checksum crypto riêng; full local SHA được pin sau HTTPS/ETag và resume Content-Range/If-Match verified. Download đầu bị size/time budget dừng, partial được giữ và resume, không thay nguồn hoặc sửa raw.

Archive 692 JSON case files; docs ghi 692 website/14 category nhưng README 185/12. Báo casefile thực, không tự nhận 692 independent environments. Không có per-request timestamp; Last-Modified không bị biến thành clock. Role HMAC khóa trước nội dung:0–1 reserved, 2 calibration, 3–4 validation, 5–9 train_candidates. 148 file reserved **không mở/project/score**, số request unknown. Không suy ra số request reserved bằng phép trừ publisher-declared total.

Audit toàn bộ 544 file còn lại: **811.129 record =756.548 candidate signatures +54.391 duplicate +190 quarantine**. Quarantine 170 URI thiếu/quá dài và 20 object JSON chưa parse được/quá lớn. Ledger đủ source SHA/member HMAC/index/decision/duplicate link/reason, đối chiếu lại tất cả 811.129 quyết định và 756.548 observations. Signature là biểu diễn request được quan sát, không chứng minh unique physical request IDs hoặc thêm traffic mới.

Parser ZIP/JSON streaming không extract, có guard path traversal/symlink/member/expansion/nesting/oversized object. Accepted-object budget 16 Mi-characters giữ nguyên. Import đầu dừng an toàn, không manifest hợp lệ/admission; giữ failed attempt. Viết RED regression cho bounded structural skip, sửa để quarantine object quá lớn rồi đọc đúng request kế tiếp. Không nới cap hoặc gán nhãn cho object chưa parse. Secret/header/body/host không xuất trong derived data/report; full raw và private key nằm riêng, không commit.

HMAC signature modulo 17, không theo label/score, tạo 44.437 projections/26.318 unique bounded 76 views. Staging 443.897 train_candidates/87.189 cal/225.462 val, chưa role nào dùng fit. 187.167 candidate có body nhưng model URI-only không quan sát body; mọi 756.548 candidate thiếu timestamp, không giả flow/actor/behavior. Projections có 2.257 query-lexical unavailable, 1 URI unavailable. Input 70/encoder 76/fused 207 giữ nguyên; không source/label/SID/status/identity vào tensor.

Model views có overlap giữa staging roles, chưa được admitted fitting: train→cal 235, train→val 510, cal→val 207. Benchmark giữ mọi sampled validation làm primary; novel-view sensitivity tách riêng, không xóa lỗi khó. Trong 13.290 public validation, 144 input khớp train cũ (141 benign, 3 positive). Partial numeric collision không chứng minh rawHTTP duplicate, không cho phép majority vote/relabel hoặc chọn lọc metric.

Organization X vẫn 211.178 distinct observations theo audit trước, unknown và 0 nhãn mới. Publisher rules UA/method/readme và nonmatch→benign chưa là independent label truth; cần source-owner/evidence-bound review. Không lặp audit raw đã hoàn tất hoặc tự tạo pseudo-label. Tổng lab 75.150 HTTP không đổi, 0 traffic mới thu lượt này, không cộng observations/projections để đạt 2M.

### 3. Frozen external benign evaluation

`FROZEN_PUBLIC_EVALUATION.json` khóa weights/bundle hashes và threshold trước scores. `EVALUATION_DATA_BINDING.json` bind data/source/protocol/code hashes sau audit nhưng trước evaluation. Numeric syntax subset định trước không đổi; wrapper source sau đó chỉnh undefined benign-only metrics/intervals thành null trước scoring, lineage ghi riêng, không force hash hoặc tính lại score.

Validation **13.290 record/160 website-case groups**, private HMAC sample độc lập score. Không nguồn/calibration/threshold/modelselection mới. Primary kết quả tại ngưỡng cũ:

| Frozen model | FP/N | FPR | Case-bootstrap95% FPR | Model-only p95 |
| --- | --- | --- | --- | --- |
| GLU 9,54M |5/13.290|0,0376%|0,0080–0,0716%|4,489 ms|
| MLP 219k |174/13.290|1,3093%|0,8377–1,8849%|0,145 ms|

Macro-case FPR: GLU 0,0595%, 5 case có FP; MLP 1,0760%, 48 case có FP. Trong 139 publisher-benign syntax-subset từ 60 case: GLU 2 FP/139=1,44%, MLP 34 FP/139=24,46%. Subset dùng các bộ đếm syntax đã định trước, không là attack label hoặc family detection benchmark. Recall/Precision/F1/PR-AUC đặt null trên nguồn chỉ có benign. Existing development family metrics giữ ở report cũ.

Kết quả đảo chiều so hardnegative lab (GLU 10,73%, MLP 0%), cho thấy weaknesses phụ thuộc miền. Không ép big/small model thắng chung. Conditional CI phụ thuộc publisher annotations và case-independence; websites có thể chia sẻ resource/domain/behavior. Không chọn champion hoặc đổi threshold từ số đo này. Latency 50 repeat/5 warmup, batch 1 model-only; không network/TLS/throughput SLO. Old/native parity evidence giữ nguyên; source mới là frozen ONNX inference, không tuyên bố đã rerun native parity mọi public row.

### 4. Lệnh và kết quả kiểm chứng

`<root>` dưới đây là artifact root private đã nêu. Exact source/download/protocol/model/test hashes trong report; argv ở `data-command-v2.json`, `evaluation-command.json`.

| Lệnh/check | Trạng thái |
| --- | --- |
| Official HTTPS download, If-Match/Content-Range resume, full SHA và pinned publisher revision/license | **PASS**, `wcp-public/download.json`, `publisher-provenance.json` |
| `systemd-run --user --collect --unit=idps-wcp-import-v2-20261101 -p CPUQuota=400% -p AllowedCPUs=0-3 -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 ... python ai-training/scripts/import-wcp-http.py --archive <root>/wcp-public/legitimate.zip --download-manifest <root>/wcp-public/download.json --identity-key <private-key> --protocol <root>/PUBLIC_CORPUS_PROTOCOL.json --output <root>/wcp-corpus-v2` | **PASS**544 nonreserved files; retained failed attempt 1; `manifest.json` |
| `python <root>/verify-corpus.py` | **PASS**811.129 decision readback/756.548 observations/44.437 model keys; site groups disjoint, no reserved payload; `corpus-verification.json` |
| `systemd-run ... --unit=idps-wcp-eval-20261101 -p CPUQuota=400% -p AllowedCPUs=0-3 -p MemoryMax=16G ... python ai-training/scripts/evaluate-wcp-http.py --dataset <root>/wcp-corpus-v2 --registry <root>/FROZEN_PUBLIC_EVALUATION.json --output <root>/public-evaluation --cpus 4` | **PASS frozen benign stress only**, 0 optimizer/threshold changes/no champion; `public-evaluation/report.json` |
| `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 IDPS_AI_TEST_SURICATA_RUNTIME=<runtime> taskset -c 4-7 nice -n10 bash ai-training/scripts/check.sh` | **PASS**198 tests/0 skip/102,03 s, Ruff/format/compile/canonical/originalWeb diff; `checks-final-accepted.log` |
| `idps-ai readiness --dataset ai-training/.artifacts/scale_upgrade_20261030/prepared-v5 --data-kind lab_capture --provenance ai-training/.artifacts/scale_upgrade_20261030/prepared_provenance.json --policy ai-training/configs/expanded_policy.yaml --output <root>/readiness-current` | **PASS**53/53 legacy technical checks only; not new formal admission |
| Protected source/oldraw/checkpoint/report/holdout SHA; HEAD vàWeb diff | **PASS**, 2.682 files giữ nguyên,`preservation.json` |
| New real training / formal / sealed quality / independently reviewed attack labels / live IPS | **NOT_RUN**, no automatic blocking or champion |

Final unit accounting: importer 482,698 s wall/470,265 s CPU/423,5M memory peak; evaluation 6,773 s wall/13,897 s CPU/453,3M memory peak. Both quota 4 CPU, MemoryMax 16 GiB/high 15 GiB/swap 0; importer sensor samples tối đa 66 °C, no thermal trip. Đây là data/eval jobs, không ca train dài. Guard RSS/sensor samples và cgroup-entry snapshot khác với final systemd resource accounting; giữ journal riêng.

Regression REDs, early bad fixture source/warmup và incomplete importer được giữ làm bằng chứng. Sửa fixture, không nới trainer guards; accepted source/test cuối 198 PASS. Không dùng technical PASS để đổi production NOT_READY.

### 5. Bảo toàn và điểm tiếp tục

Chỉ dọn 838.709 byte/71 generated untracked Python/pytest/Ruff cache files. Giữ raw ZIP/key/SQLite/decisions/quarantine/failure logs/weights/checkpoints và mọi report cũ. File private đặt mode 600; không publish raw request, query, cookie, headers hoặc body. Owned data/eval units đã dừng, không dừng service khác; không sửa source/config của hai Web. Artifact vẫn local/ignored, chưa shared store.

Existing catalog đã có `prospective_evaluation_plan` cho browser catalog/cart, documentation/code search và structured API/auth sessions: authorized targets, time/seed/template/roles khóa trước, actual 10/60/300 s history, independent evidence-bound label review và không future-label filtering. **DESIGNED_NOT_COLLECTED**, live allowlist rỗng; không giả campaign, timestamp hoặc flow để đánh dấu hoàn tất.

`CURRENT_WORK.json`, report và handoff format 9 là điểm tiếp tục. Không rerun dữ liệu/study đã xong. Cần positive HTTP độc lập và matched benign/hard negatives có nhãn đáng tin, semantic/visibility review, protocol prospective hoặc leave-environment-out và statistical acceptance cân bằng. Giữ 148 case mới cùng holdout cũ kín đến release freeze; benign-only supplement không chọn champion. Formalcommand=null, 0 scale admission/2M, 0 optimizer update thực mới. Engineering iteration complete=true; production objective còn mở.

### File thay đổi đúng lượt này

- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/PRETRAINING.md`
- `ai-training/README.md`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/reports/GENERALIZATION_QUALITY_20261101.json`
- `ai-training/scripts/evaluate-wcp-http.py`
- `ai-training/scripts/import-wcp-http.py`
- `ai-training/src/idps_ai/data/wcp.py`
- `ai-training/src/idps_ai/training/generalization.py`
- `ai-training/tests/test_quality_evaluation.py`
- `ai-training/tests/test_wcp_corpus.py`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`



## 32. Independent attack evidence and admission — hoàn tất engineering; formal NOT_READY — 2026-11-01T07:50:20.924178+07:00

Bắt đầu `2026-11-01T00:08Z` (xấp xỉ07:08+07), hoàn tất ở timestamp trên. Nhánh `feat/ai-model-training`, HEAD `6c20b27ace91b0cb112dbdea5ca6720adbfc7941`. Chỉ AI/data/evidence/docs. Không sửa Student Web, Security Web, canonical contract, Docker, quyền host hoặc cấu hình mạng. Không add/commit/push ở lượt này vì chưa có yêu cầu mới.

Root private `ai-training/.artifacts/attack_evidence_20261101`; `CURRENT_WORK.json`, source/docs snapshots, `SOURCE_FREEZE.json` là điểm tiếp tục. Report máy `ai-training/reports/ATTACK_EVIDENCE_20261101.json`; handoff format10. Engineering iteration complete=true; production objective=false; formal_command=null.

### Dữ liệu và nguồn gốc

SOC-MLD v2 DOI10.5281/zenodo.23116148, official CC BY4.0, attribution Mai Hoàng Đỉnh, Nguyễn Phúc Thịnh, Phan Ngọc Vương, Lê Đăng Giáp (2026). ZIP10.430.367bytes, MD5`764ca570a35753a90f6ac3046750c716`, SHA256`66aafa96a69ab54ee061abbb69284444476919295f1b16985122283dae2b3054`. Official API metadata/checksum + LICENSE trong archive được kiểm; raw không sửa, không execute publisher code hay replay traffic.

Active `soc-audit-v2/report.json`:198.122 access lines,198.082 HTTP parseable,40unparsed còn trong raw;193.220 distinct complete-log observations/4.862 repeat,6.856 partial method/URI/UA representations. EVE178.941 records gồm11.679HTTP/119.330flow/28.013alert và loại khác; không cộng các observation này vào request count. Physical independently verified requests=null; trusted new labels=0; supervised/scale admission=0.

6.600 operator rows đều naive timestamp,0request IDs,45scenario IDs; không đoán timezone/nearest-time để gán nhãn. Publisher code consume time±30s (dòng708) rồi payload-rule fallback(711)/NORMAL(442), network labels dùng signature(749). Feature aggregation nhìn ts±60s(266) và full sessions; không đưa vào model. CSV thực4.786train/1.220test,38attack-instance IDs chung và thời gian chồng lấn; không nhận independent-split claim chỉ vì README. README counts là tài liệu của nguồn, active audit đo file thực.

Attempt đầu `soc-audit/` chỉ hỗ trợ combined log nên đếm thiếu common format; kết quả superseded giữ nguyên. Sửa parser cho optional header pair và thêm regression; v2 đếm đủ198.082 valid. Không nới nhãn hoặc làm giả flow để đạt số lượng.

`pending-source-review.jsonl`:64 distinct-observation source locators được blind hash-sample, có archive/member/line-index và SHA readback từ raw. Tất cả unknown/pending/null;0approved/0training eligible, không chứa URI/query/IP/UA/body. Đây là queue chuẩn bị review, chưa là labeled dataset. Chưa có độc lập human/source-owner semantic review hoặc application oracle.

WAMM revision`2783eab560c4355f5976a57fc2e97a2e6c5c79a1`:SR-BH derivative+Burp mutation, regex/LLM filtering; không coi độc lập hoặc tải archive để bù số lượng. WAF Data v2 revision`b035dc17f875f1f732c10654709abed66a4e9742`:MIT claim nhưng capture/annotation/campaign lineage chưa rõ; resemblance SR-BH chưa là proof duplicate. Biblio-US17 official idUS metadata ghi CC BY-NC-ND4.0 khác license bài báo; pending compatibility/label-scope review, không tải data. ModSec-WP official CC BY4.0,108.883 publisher rows, hybrid time/regex/manual labels chưa có row evidence chain; chỉ metadata. Catalog hiện có được cập nhật, không giả nhãn hay cộng các nguồn chưa audit vào2M.

### Code và điều kiện admission

`label_evidence.py` và `audit-label-evidence.py`: review manifest v2 bind dataset/provenance/environment, ledger SHA, collector/reviewer IDs khác nhau. Approved event cần capture, intent provenance và independent semantic-review artifact riêng; label/family phải khớp row thực tế. Unknown/pending/rejected vẫn null, duplicate/outside-dataset/mismatch/tamper/path escape/sealed refs bị từ chối. Intent khác exploit outcome; failed attack vẫn positive, succeeded/failed cần application oracle. Không dùng rule/model/status/time proximity làm ground truth. Hash/ID xác minh integrity của attestation, không tự chứng minh người review có thật hay nhãn đúng.

`corpus.py`: review theo từng event bằng SQLite; chỉ count matching reviewed rows, không cấp toàn dataset chỉ nhờ approved boolean. Review v1 hoặc cached report thiếu evidence-v2 markers không mở formal. Existing research APIs/contracts và checkpoint/math/ONNX không đổi. `public_http_sources.yaml` thêm provenance/screening, evidence contract và balanced acceptance requirements; không giảm class/source/group/embargo gates.

Không study/tuning/calibration mới vì thiếu nguồn mới đủ điều kiện both-class + semantic evidence. Giữ MLP219.144/GLU9.541.640/baselines; kết quả per-family/precision/recall/AP/latency/score diagnostics ở reports trước. GLU lab FPR10,73% soMLP0%, nhưng WCP benign frozen GLU0,0376% soMLP1,3093% cho thấy lệ thuộc domain, không champion. SR-BH đã exposed retrospective; không gọi thành test mới. Không mở holdout để sửa threshold.

### Lệnh, tài nguyên và kết quả thực

`<root>` là artifact root trên; `commands.json` ghi commands/scope. Các job do lượt này tạo đều đã dừng; không tạo container lab mới, không dừng service khác.

| Lệnh/check | Kết quả |
| --- | --- |
| Official HTTPS SOC download + metadataMD5/SHA/LICENSE + member inventory | **PASS**,10.430.367bytes; raw giữ nguyên |
| `systemd-run --user --collect ... python ai-training/scripts/audit-soc-mld.py --archive <root>/research/SOC-MLD-v1.zip --download-manifest <root>/research/soc-download.json --output <root>/soc-audit-v2` | **PASS structural audit; labels/training QUARANTINED**;4CPUquota/16GiB,5,718s wall/4,730s CPU/77,8M peak |
| `python <root>/prepare-pending-review.py` trong scope4CPU/16GiB, inner guard2threads/1GiB | **PASS**,64unknown/64raw locator readbacks;0labels generated |
| Initial fullcheck qua systemd service | **FAIL**209PASS/2sensor permissions; `unshare` UID map denied in service AppArmor context. Không sửa permission hoặc bỏ test |
| First check qua inherited terminal systemd scope | **FAIL**210PASS/1resume guard: đã sửa corpus guard khi check còn chạy; frozen-source mismatch bị từ chối đúng. Giữ stderr, không force-resume |
| Final `systemd-run --user --scope -p CPUQuota=400% -p AllowedCPUs=4-7 -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 IDPS_AI_TEST_SURICATA_RUNTIME=/home/trung/projects/idps-web-aws/ai-training/.artifacts/upgrade_20261028/tools/runtime bash ai-training/scripts/check.sh` | **PASS**211pytest/0skip/67,34s;125Ruff files/format, compile, canonical/Webdiff; frozen159source/config files không đổi. Job67,968s wall/1,5G peak |
| `idps-ai corpus-audit --registry ai-training/configs/scale_sources.yaml --output <root>/scale-catalog-current` | **PASS fail-closed check: EXPECTED NOT_READY**, exit3/0eligible. Batch set-e dừng trước readiness; chạy readiness riêng sau đó |
| `idps-ai readiness --dataset ai-training/.artifacts/scale_upgrade_20261030/prepared-v5 --data-kind lab_capture --provenance ai-training/.artifacts/scale_upgrade_20261030/prepared_provenance.json --policy ai-training/configs/expanded_policy.yaml --output <root>/readiness-current` | **PASS53/53 legacy technical only**,128,780s wall/129,068s CPU/440,8M peak; không phải formal/public-data acceptance |
| Protected SHA/readback/HEAD/Web diff | **PASS**2.941old raw/weights/report/holdout/source files giữ nguyên;0Web/contracts/Docker diff |
| New real-data study / formal / independent-label approval / final-quality scoring / live IPS | **NOT_RUN**; chưa đủ evidence, không champion/threshold change |

Giới hạn mọi job≤4CPUquota ở lượt này, hard MemoryMax16GiB/high15GiB/swap0; inner queue guard1GiB. Không ca training nhiều giờ. Regression có fit/checkpoint/ONNX trên synthetic test fixtures;0optimizer update thực trên corpus mới, không tuyên bố native parity đã rerun trên public rows. Evidence real118.760vectors và checkpoint cũ giữ nguyên.

Chỉ xóa870.638bytes/73generated cache files; giữ rawZIP, SQLite, pending queue, decision/failure logs, weights/checkpoints, old reports và secrets/identity keys. Root artifact private700/files600, không publish payload/PII.

### Điều kiện còn thiếu và điểm tiếp tục

Cần positive intent labels có bằng chứng theo request từ môi trường/campaign độc lập, matched benign/hard negatives, visibility/lineage và independent semantic review. Nguồn mới chưa đạt; không ép trainer chạy. Thiết lập prospective hoặc leave-environment-out balanced acceptance, freeze trước scores, groups/templates/time và embargo300s, uncertainty theo campaign. Giữ mọi sealed holdout bao gồm148WCP website files chưa đọc/project/score. Publisher-benign-only và SR-BH retrospective không chứng nhận champion hoặc production. Tổng lab75.150HTTP không đổi, verified new live0, scale-admitted0/2M. Chi tiết machine report/handoff10/CURRENT_WORK là điểm tiếp tục, không rerun audit/study đã hoàn tất.

### File thay đổi đúng lượt này

- `ai-training/src/idps_ai/data/label_evidence.py`
- `ai-training/src/idps_ai/data/corpus.py`
- `ai-training/src/idps_ai/data/telemetry_audit.py`
- `ai-training/scripts/audit-soc-mld.py`
- `ai-training/scripts/audit-label-evidence.py`
- `ai-training/tests/test_telemetry_audit.py`
- `ai-training/tests/test_label_evidence.py`
- `ai-training/configs/public_http_sources.yaml`
- `ai-training/README.md`
- `ai-training/PRETRAINING.md`
- `ai-training/FINAL_TRAINING_HANDOFF.json`
- `ai-training/reports/ATTACK_EVIDENCE_20261101.json`
- `docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md`
- `docs/01_SYSTEM_AUDIT_AND_ARCHITECTURE.md`
- `docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md`
- `docs/03_AI_MODEL_AND_TRAINING_PLAN.md`
- `docs/04_ROADMAP_AND_TEAM_TASKS.md`
- `docs/05_DISCOVERY_EVIDENCE_AND_INVENTORY.md`
- `docs/06_AI_HANDOFF_AND_RUN_LEDGER.md`
