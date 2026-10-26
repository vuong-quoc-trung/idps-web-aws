# 06 — AI handoff, decision log và sổ training

**Trạng thái chuẩn tại 26/10/2026:** audit tài liệu hoàn tất; chức năng dự án vẫn ở commit `37bc4d2ae1552939659a10647898e2228f1b801f`. Tài liệu này là điểm tiếp tục, không phải danh sách tác vụ đã chạy. Đọc [00](00_PROJECT_OVERVIEW_AND_PROGRESS.md) trước, rồi phần cần làm trong 01–04; đối chiếu [05](05_DISCOVERY_EVIDENCE_AND_INVENTORY.md) khi cần kiểm drift.

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
| Last reviewed code | `37bc4d2ae1552939659a10647898e2228f1b801f` |
| Last reviewed date | 2026-10-26, Asia/Ho_Chi_Minh |
| Phạm vi thay đổi của lần khảo sát | Chỉ tệp trong `docs/`; không commit/push |
| Worktree ban đầu | Sạch theo `git status --short` trước khi tạo docs |
| Môi trường triển khai được mô tả | Ubuntu Security host + Kali VM + Web VM; runtime chưa nghiệm thu trong chat |
| Audit student | DB `access_logs`; chưa file `audit.log`/exporter/connector |
| Security sources | EVE alert + Nginx SQLi; không all-event baseline |
| Rule/IPS code | Có; AUTO_BLOCK không phải global stop, chưa TTL/freshness |
| AI implementation | Chưa có trong repo đã kiểm kê |
| Dataset registry | Chưa cấp dataset ID/hash/split được review |
| Training registry | Chưa có run/session/checkpoint/metrics trong repo |
| Runtime validation lần này | `NOT_RUN` cho Java/Rust/FE/app/DB/packet/train |
| Chặn cần người dùng trả lời ngay | Không có cho nhiệm vụ tài liệu; các điều kiện triển khai ở mục 7 |
| Việc tiếp theo | R00/R02/R03 rồi IPS safety và telemetry theo 04 |

## 3. Nhật ký công việc code/docs

| Entry | Ngày | Hạng mục | Trạng thái | Evidence / kết quả |
|---|---|---|---|---|
| DISCOVERY-20261026 | 26/10/2026 | Khảo sát source/config/SQL/tests/frontend/infra/docs/log artifacts | DONE cho đọc tĩnh | Snapshot commit + manifest 05A; limitations 05 |
| DOCS-20261026 | 26/10/2026 | Bộ nhớ sống và kế hoạch dual-engine/data/AI/team | DONE cho tài liệu | 00–06 + 05A; không có chức năng mới |
| R00–R34 | Chưa triển khai | Backlog roadmap | PROPOSED | Không gán owner thật hoặc ngày hoàn thành giả |

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
| Canonical event schema | Chưa có file schema thực | Specification đề xuất tại 02 |
| Feature pipeline + golden vectors | Chưa cấp version | Chưa triển khai |
| Dataset + labels/splits | Chưa có manifest | Chưa thu/tải trong phiên này |
| Training environment lock | Chưa tạo | Chọn/pin ở R03/S0 |
| Latest / previous / best checkpoint | Chưa có | Không thể resume |
| Champion model + ONNX bundle | Chưa có | Không thể deploy AI |
| Calibration/threshold/model card | Chưa có | Phải gắn cùng model version |
| Rule bundle production | Repo có 8 SID; hash tệp trong 05A | Chưa xác minh rule installed hoặc runtime acceptance |

URI phải dùng nơi nhóm thực sự truy cập được, ghi ACL/owner/expiry và checksum. Không commit model/data lớn chỉ để chat mới “thấy” tệp. Secret store riêng, docs chỉ có tên secret/key reference được phép chia sẻ.

## 6. Decision log

Quyết định của người dùng có hiệu lực trong scope phiên này; định hướng kỹ thuật mới là **PROPOSED** cho đến khi nhóm implement/đồng thuận tại task tương ứng. Không gán chữ ACCEPTED cho lựa chọn chưa kiểm chứng.

| ID | Trạng thái | Nội dung | Lý do / cách thay đổi |
|---|---|---|---|
| D00 | USER CONSTRAINT | Phiên khảo sát chỉ đọc code, tạo docs | Không thay chức năng, config hay runtime |
| D01 | OBSERVED | Audit student thực tế là `access_logs` | Không tự tạo giả định audit.log có sẵn |
| D02 | PROPOSED | Collector normalize/redact → PG durable inbox/outbox → rule + AI queues độc lập | Giữ nền Rust/PG; chỉ thêm broker khi benchmark cần |
| D03 | PROPOSED | Pilot audit export từ DB; outbox/CDC nếu commit ordering/durability yêu cầu | Quyết định file NDJSON hay DB cần chốt ở R02/R21 |
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

Không cần chờ các câu trả lời này để hoàn thành tài liệu khảo sát. Cần xác minh chúng trước những bước phụ thuộc; không tự điền bằng thông số tưởng tượng.

## 8. Quy tắc chống bộ nhớ sai

- Source/tests “có” không đồng nghĩa đã deploy/PASS. Log cũ lỗi khởi động không chứng minh code hiện tại lỗi. Alert count không phải attack count.
- Không đánh dấu train xong nhờ số giờ; không suy từ thư mục `trainingprogram` ra AI. CSV trong `.agents` là tài nguyên design skill, không phải IDPS dataset.
- Không mặc định file `audit.log` là auditd/ModSecurity; không mặc định EVE có body hoặc encrypted traffic quan sát được payload.
- Không diễn giải `AUTO_BLOCK=false` thành actuator off ở code baseline. Không dùng `/health`, rule catalog tĩnh, `--check-config` hay `--check` exit0 thay nghiệm thu pipeline.
- Nếu docs/code/artifacts lệch: ghi chênh lệch và bằng chứng mới, cập nhật summary+ledger; không âm thầm giữ tiến độ cũ hoặc xóa thay đổi người khác.
- Cuối mỗi phiên ghi rõ **đã làm**, **chưa làm**, **kiểm tra đã chạy**, **giới hạn**, **bước tiếp theo**. Bàn giao phải đủ để người khác kiểm chứng bằng code và artifact, không dựa ký ức chat.
