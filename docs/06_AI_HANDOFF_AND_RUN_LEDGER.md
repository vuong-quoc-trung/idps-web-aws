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
