# 06 — AI handoff, decision log và sổ training

**Handoff hiện hành:** 2026-10-26T22:11:48+07:00. Nhánh `codex/foundation-audit-and-schema`, base commit `1925764a0b4dbbae647797136e17abfd9a122c45`, foundation chưa commit/push. Đã bảo toàn và hoàn thiện các file viết dở của lần gián đoạn; không reset/revert, không đụng dữ liệu/container/service có sẵn. Quy định chỉ-đọc của khảo sát trước là lịch sử, không còn giới hạn nhiệm vụ triển khai mới.

Đọc trạng thái hiện hành trong 00/01/02 cùng contract tại `contracts/`. Chưa có AI model/training/dataset labels. Thời gian làm code/test không phải giờ train.

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
| Code base / branch | 1925764; codex/foundation-audit-and-schema; thay đổi working tree chưa commit |
| Có sẵn ở đầu lần tiếp tục | Port config5433/5434, expanded rule/config và các lớp AuditEvent/exporter/attribution + Rust events/detection viết dở; chưa nối filter/ingestion, chưa khóa file schema |
| Vừa hoàn thiện | Java attribution/filter/reads/UA/correlation/JSONL, Flyway V2; Rust normalizer/durable dataset/auth/counters/quarantine; schema1.0+fixtures; network safety/TTL/deadline; dev script và tests |
| Audit/collection | JSONL path cấu hình được; Student+Nginx+EVE; dataset opt-in, alerts riêng; exporter hai sink độc lập |
| Canonical contract | contracts/canonical-event-v1.schema.json + typed Rust + Java + cross-language runtime validation |
| Response | OFF mặc định; new Rust families alert-only; protected-target discovery/root helper policy; TTL/deadline/freshness; không áp nft lên host |
| Validation | Java87 PASS; Rust44 PASS; clippy/fmt PASS; edge5+sensor1 PASS; schema3 PASS; firewall policy3 PASS; isolated nft syntax PASS; smoke PASS |
| AI | Chưa trainer/model/labels/run/checkpoint. Training ledger vẫn0run có bằng chứng |
| Môi trường đã thử | Ubuntu local, PostgreSQL test17; demo Student16/Security17; Nginx1.28.3; Suricata8.0.3 offline |
| Chưa thử | Kernel enforcement thật; packet capture live; máy LAN/Wi-Fi/VM/AWS thật; throughput/FP; remote file shipping/HA/restore drill |
| Việc tiếp theo | A: operational hardening/reconcile/load/proxy deploy; B: R30–R34 manifests/labels/splits/causal features trước S0 |

## 3. Nhật ký công việc code/docs

| Entry | Ngày | Hạng mục | Trạng thái | Evidence / kết quả |
|---|---|---|---|---|
| DISCOVERY-20261026 | 26/10/2026 | Khảo sát source/config/SQL/tests/frontend/infra/docs/log artifacts | DONE cho đọc tĩnh | Snapshot commit + manifest 05A; limitations 05 |
| DOCS-20261026 | 26/10/2026 | Bộ nhớ sống và kế hoạch dual-engine/data/AI/team | DONE cho tài liệu | 00–06 + 05A; không có chức năng mới |
| FOUNDATION-20261026 | 26/10/2026 | Shared foundation code + schema + local runtime | IMPLEMENTED / validation bên dưới | R02 + phầnR10–R24; không coi mọiR00–R34 hoặc enterprise đã DONE |

Với entry mới, thêm commit/PR, task ID, owner/reviewer, change summary, tests/env/results, known issue và next step. `DONE` cần đầu ra đã kiểm tra; `IN_PROGRESS` ghi phần còn thiếu. Dùng `BLOCKED` trong bảng này khi task thực bị phụ thuộc và ghi lý do, không coi tài liệu chưa implement là sự cố hiện tại.

## 4. Training ledger — chưa có run nào được đăng ký

**Số run có bằng chứng tại snapshot: 0. Giờ optimizer được ghi nhận trong repo: 0. Giờ training ở nơi khác: chưa biết.** Không có latest/best/champion để resume hoặc deploy. Không dùng checkpoint minh họa trong tài liệu làm đường dẫn thật.

Khi bắt đầu, thêm một row mỗi phiên, không ghi đè row trước:

| Run / session | Stage / model | Dataset + split hash | Commit + config hash | Start/end có timezone | Wall / optimizer hours | Global step | Checkpoint URI + SHA-256 | Validation / review | Stop reason / next |
|---|---|---|---|---|---|---|---|---|---|

Bảng trống là chủ ý: **chưa có ca thực**, không phải lỗi mất dữ liệu. Có thể giữ bảng gọn và link tới manifest phiên ở artifact store; không bỏ trường hash/step chỉ để vừa màn hình.

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

| Artifact | Version/hash/URI | Trạng thái tại baseline |
|---|---|---|
| Canonical event schema | contracts/canonical-event-v1.schema.json /1.0 | FROZEN, có fixture/schema/runtime tests |
| Feature pipeline + golden vectors | Chưa cấp version | Chưa triển khai |
| Dataset + labels/splits | Chưa có manifest | Chưa thu/tải trong phiên này |
| Training environment lock | Chưa tạo | Chọn/pin ở R03/S0 |
| Latest / previous / best checkpoint | Chưa có | Không thể resume |
| Champion model + ONNX bundle | Chưa có | Không thể deploy AI |
| Calibration/threshold/model card | Chưa có | Phải gắn cùng model version |
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
