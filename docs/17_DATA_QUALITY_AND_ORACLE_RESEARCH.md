# Data quality và Oracle research — 2026-11-07

Milestone này thu dữ liệu thật, kiểm chứng receipts, tách các vai trò dữ liệu và
thử calibration-only. **Không training, không thay frozen model/threshold, không
thay integration, dashboard, Rules hoặc Policy Engine. AI enforcement vẫn DISABLED.**

Baseline Git thực tế lúc bắt đầu: `8b83102`, branch
`feature/ai-idps-shadow-integration`, working tree sạch. GLU derivative cũ được dùng
lại, không chuẩn bị lại hoặc sửa174rows quarantine.

## Inventory: số nào có thể cộng, số nào không

[Inventory máy](../ai-training/reports/RESEARCH_DATA_INVENTORY_20261107.json) ghi
13 nhóm nguồn, đơn vị đếm, label tiers, model compatibility, roles và hashes của
các ledger đã đọc. Counts nguồn cũ là **last-audited metadata**, không giả thành
một lần đọc lại20GB raw evidence.75receipts mới được trực tiếp reverify trong lượt này.
Không mở sealed holdout hoặc public test contents để fit/tuning.

| Nguồn | Quy mô có evidence | Ý nghĩa và giới hạn |
|---|---|---|
| GLU frozen TRAIN |41,607rows;41,585unique float32 views|Scenario research labels;41,433derivative candidates,174quarantine; không independentGT|
| WAF Data v2 |1,924,461publisher rows;1,612,017exact HTTP text representations|160,796selected588views;120,435train; publisher NORMAL/ANOMALOUS,0applicationOracle/verified physical capture|
| SR-BH2020 |907,815source records;310,314curated research candidates|Publisher signature/manual/semi-auto labels; exposed development; không independent attack outcomes|
| WAMM |704,665records;312,241text representations;67,620numeric views|SR-BH derivative; không cộng thành nguồn vật lý độc lập|
| CSIC |97,065transcript requests;34,561observable identities theo audit cũ|Publisher anomalies, body/header observability và train/test overlap; không chuyển test thành train|
| PKDD mirror |24,504train và25,612test records trong metadata cũ|Normal train có thể phục vụ research; context/campaign/time bị thiếu|
| OrganizationX |211,178distinct complete log observations theo audit|Intent UNKNOWN; không tự gán benign|
| SOC-MLD |198,122access lines,198,082parseable observations|193,220distinct complete observations; operator IDs thiếu;38attack-instance IDs cross originaltrain/test|
| ModSec-WP |108,883rows,27,686transaction IDs,18,474text representations|81,197repeated rule rows,20conflicting transaction IDs; publisher labels|
| Kyoushi scenario1 |408,477access records,406,692distinct method/URI lines|Positive-heavy publisher labels; unlabeled không phải benign|
| P0/P0.5 |111primaryreceipts,86frozen Request-v2 views|Exposed DEVELOPMENT;59benignOracle,33successOracle,12unsafe reflections,4UNKNOWN; human review PENDING|
| Cohort mới |75receipts,75method/URL/body representations,59frozen views|70known internal intents,5UNKNOWN; chi tiết bên dưới|
| Reserved/sealed hoặc flow/URL-only |Request count UNKNOWN hoặc không áp dụng|Không mở hoặc gán thành HTTP request Ground Truth|

**Không có tổng distinct physical HTTP requests toàn project được chứng minh.**
Publisher rows, replicated captures, projections và derivative views có overlap/
khác đơn vị đếm. Có hơn một triệu publisher records không đồng nghĩa đã có một
triệu requests đủ Ground Truth. Số independently human-verified labels trong các
ledgers này vẫn0. Admission policy/formal count không thay đổi.

## Cohort mới: dữ liệu đã thu, không mô phỏng

Plan khóa trước capture:75cases hữu hạn trên image DVWA/Juice đã pin digest; cả hai
môi trường có benign và attack attempts. Dùng lại P0 Gateway/Session/HTTP receipts
và Juice challenge Oracle. Không phát traffic đến website bên ngoài lab.75là study requests có đủ receipts,
không phải tổng traffic: còn14DVWA setup responses, ít nhất3Juice ancillary API
observations và readiness polls chưa receipted từng request. Tổng bao gồm mọi retry
vẫn UNKNOWN; không dùng số75 để tuyên bố đã đếm toàn bộ network traffic.

- DVWA46requests: stored-comment POST benign/hard negatives và XSS attempts;
  numeric user lookups, public file workflows, blindSQLi controls/attempts; reflected
  XSS, command stdout và private canary inclusion giữ DEVELOPMENT khi phù hợp.
- Juice29requests: product/search, benign JSON login denial, fixture account
  registration; SQLi auth bypass với admin identity + challenge transition;
  SQLi search có catalog và empty-search negative control.
- Mỗi request có ID duy nhất, method/target/body/header hashes và response hashes.
  Gateway ID là **owned proxy receipt**, không giả thành application audit ID.
- Có offline URI/header/body inputs cho Request v2. Không có Student/207contract:
  **GLU207 eligible=0**; không padding, không thay live body observability.

| Intent hoặc outcome riêng biệt | Số lượng |
|---|---:|
| BENIGN có semantic Oracle |47|
| ATTACK_ATTEMPT có intent/receipt provenance |23|
| UNKNOWN intent/benign Oracle |5|
| Success theo application Oracle nội bộ, trong23attempts |14|
| Unsafe reflection, browser execution chưa xác minh |8|
| Attack outcome UNKNOWN |1|
| VERIFIED_FAILED_ATTEMPT |0|
| Independent human review hoàn tất |0|

Outcome của benign không được diễn giải thành exploit failure. Field UNKNOWN
outcome gốc có cả các benign rows không áp dụng exploit outcome; khi báo cáo
attack outcomes phải filter intent trước, không nhầm với5UNKNOWN labels.

## Những lỗi capture đã giữ và cách phục hồi

Các attempts/control logs/source snapshots giữ riêng, không ghi đè:

1. Watchdog startup đầu resolve Python ra ngoài virtualenv, không import được
   dependencies; **0cohort requests**. Giữ interpreter venv khi launch đã sửa.
2. P0 Session có default port được bind lúc import; đổi module constant chưa đủ.
   Initial DVWA readiness không tới cổng mới; **0cohort requests**. Wrapper session
   bind đúng15280; không sửa frozen P0 source.
3. DVWA đã có46receipts rồi subprocess cleanup trả lỗi; Juice-only continuation
   thu29receipts chưa phát trước đó, cũng gặp cleanup returncode. Không phát lại46
   hoặc75cases để che failed run. Hiện không còn containers/network thuộc run.
4. Original direct DB user snapshot/counts chưa được persist đầy đủ. Assessor
   phục hồi từ receipt/response/captured source và challenge/catalog snapshots.
   **5CALIBRATION user-lookups cần expected DB snapshot vẫn UNKNOWN**, dù có vẻ
   hợp lệ; không tự dựng expected answer từ response để nhận nhãn.

Stored guestbook được kiểm trong rendered persisted-comment block và source
INSERT đã capture; đó là evidence persistence/reflection, không phải independent
human review hoặc XSS execution. Juice before/after challenge và admin response
được kiểm lại từ evidence lưu. Nguyên nhân runtime cleanup returncode cũ **chưa
xác minh được vì stderr gốc không được giữ**, không quy thành lỗi model/dataset.

Collector mới đã sửa để lưu incremental Oracle ledger, giữ cleanup diagnostics
và chỉ coi nonzero removal là đã dọn nếu existence check xác nhận absent. Test
phân biệt absent/present/runtime-error. Đây là sửa trực tiếp độ tin cậy capture;
không mở rộng kiến trúc detection. Chưa chạy lại toàn75cases sau fix vì evidence
hiện có đủ cho phần đánh giá đã nêu; lần capture tiếp dùng source mới.

## Labels, review và splits

75/75receipts được reverify: plan ID/method/target/body, request headers, response
headers/body cùng hashes; tampering bị từ chối trước labeling.69rows có semantic
Oracle match;23attack attempts là intent labels độc lập với14success outcomes.
69Oracle checks không phải69independently verified labels.

Review package private có75blind queue entries: không kèm collector proposed
intent/outcome hoặc model scores, quyết định/reviewer để null. Priority package
bao gồm UNKNOWN/unsafe-reflection cases; **REVIEW_PENDING**. Không có reviewer giả,
không dùng AI agent/Suricata/model prediction thay human verification. Formal
review/admission workflow không bị thay bằng queue research này.

Role plan và Recall targets SQLi/XSS/command/traversal80%, FPR≤1% được khóa trước
model selection. Sau kiểm integrity và feature extraction, role eligibility ledger
được ghi/hash **trước** đọc diagnostic model scores:

| Vai trò | Eligible rows | Phạm vi |
|---|---:|---|
| TRAIN |35|28benign,7attempts; chỉ2connected environment/session groups|
| CALIBRATION |9|Tất cảGET; chỉ3unique frozen views|
| DEVELOPMENT |13|Bao gồm5raw representations đã có trongP0; exposed diagnostics|
| PROSPECTIVE EVALUATION |13|6benign,7SQLi attempts; model scores chưa tính|
| UNKNOWN, excluded |5|Không supervised fit/calibration|

Kiểm exact method/URL/body, exact588float32 view, rich template, route-aware safe
workflow template và session/role cohort groups. Near-content cosine≥.995 được
kiểm exhaustively trên75rows trong cùng method/endpoint; không tìm cross-role
connected overlap hoặc mixed-intent exact view trong cohort này. Coarse safe
symbols trùng giữa route khác nhau được ghi diagnostic, không giả thành proof
hai HTTP requests là cùng physical request. Các IDs/campaigns do collector định
nghĩa không tự chứng minh độc lập;2TRAINgroups là giới hạn nghiêm trọng về diversity.

Có kiểm exact view/rich template với frozen WAF train và raw/template với exposed
P0. **Không claim exhaustive global raw/near dedup giữa mọi corpus** vì WAF staging
không giữ raw hashes, upstream publisher lineage không có. Không chuyển P0 hoặc
các roles mới sau khi xem score. Collection tuần tự theo environment không chứng
minh một future temporal evaluation; không encode future response/history vào
request model và không tuyên bố temporal generalization.

## Calibration-only: kết quả âm tính

Frozen threshold giữ0.8826237916946411, strict `>`. Calibration-only candidate chọn
max score0.07709759473800659 từ **3unique benign calibration views/9physicalrows**,
không dùng prospective data. Cả9đềuGET, không có benignPOST calibration.

| Diagnostic role | Frozen | Calibration-only |
|---|---|---|
| TRAIN35, chưa fit trên chúng |TP1/FN6/FP2/TN26|TP7/FN0/FP18/TN10|
| DEVELOPMENT13 |TP1/FN8/FP0/TN4|TP8/FN1/FP0/TN4|
| CALIBRATION9 |0flags|0flags, cùng dữ liệu dùng chọn threshold|

Candidate giảm misses trong diagnostics nhưng tăng mạnh benign flags. **REJECT
cho deployment/quality claim**, không threshold sweep. Đây là frozen-model
observations trên internal Oracle intent, không phải trained challenger accuracy
hoặc independent evaluation. Không dùng0/9calibration flags làm FPR chứng nhận;
Phép tính binomial minh họa cho0/3views cho upper bound≈70.76%; đây không phải
confidence bound hợp lệ cho population FPR vì threshold được chọn ngay trên cùng
calibration data, các groups còn phụ thuộc. Không có cơ sở kết luận≤1%FPR.

Một report version đầu ghi nhầm3ở physical calibration count thay vì9; original
được giữ và có `report-corrected.json` với parent hash. Scores, labels và threshold
không đổi. Source đã sửa cách đếm hai đơn vị này.

## Quyết định engineering

**TRAINING_GATE=BLOCKED; BACKGROUND_TRAINING=NOT_STARTED.** Không phải vì thiếu
formal admission hoặc human reviewer một cách tuyệt đối: Oracle research labels
được phép cho research. Blocker cụ thể là calibration thiếu benignPOST, quá ít
unique/groups, và prospective cohort chưa có XSS/command/traversal để trả lời giả
thuyết ưu tiên. Hiện chỉ có SQLi prospective support;35TRAINrows chỉ2connectedgroups.
Không train chỉ để tạo optimizer updates rồi không thể đánh giá đúng mục tiêu.

Đã khóa **một** candidate design:
[request-channel-robustness-v3](../ai-training/configs/research/request-channel-robustness-v3.json).
Giữ capacity khoảng50k; tách URI/body/header hash normalization, coarse non-secret
field syntax, ưu tiên benignPOST hard negatives. Frozen encoder giữ nguyên; encoder
mới chưa triển khai. Same588dimensions không có nghĩa warm-start tương thích:
coordinate semantics đổi thì cần new initialization và new-run checkpoint test.
Budget tối đa1epoch/250updates/1seed, không bốn arms hoặc sweep vô hạn. FPR target
1%, Recall targets80%/family là mục tiêu research predeclared, không kết quả đã đạt.

Đây cũng là giới hạn của chính plan lần này: đã có benignPOST ở TRAIN nhưng chưa
phân bổ chúng vào CALIBRATION, và giữ các family cũ ở DEVELOPMENT chưa tạo được
prospective family coverage mới. Không thể sửa bằng cách đổi role sau khi xem scores.

**Đúng một nhiệm vụ tiếp theo:** một cohort gap-filling có role/session isolation,
workflow groups mới đa dạng cho TRAIN, Oracle-supported benignPOST cho CALIBRATION và các workflow XSS/command/traversal
chưa lộ cho PROSPECTIVE EVALUATION; loại các template/views đã ghi ở cohort này
**trước khi phát request**; khóa coverage matrix gồm cả ba vai trò trước capture.
Chỉ thêm CALIBRATION/PROSPECTIVE sẽ không sửa được giới hạn2TRAINgroups. Không thu lại những cases đã đủ evidence và không thêm
payload variants chỉ để tăng count.

## Safety, reproducibility và handoff

Images pin theo digest DVWA, MariaDB và Juice; network internal, chỉ loopback15280/
15281, DB không expose. CPU caps0.5/container; Python guard quota100% **mộtCPU**,
MemAvailable reserve4GiB, không cố chiếm50%host khi HTTP collection không cần.
Detached Podman không được giả là nằm trong collector cgroup: watchdog systemd
độc lập chỉ quản lý exact run label. Stale heartbeat đã dừng một container thật;
sensor-loss/error branches có tests. Parent guard dùng rolling300s/90°Ccutoff;
watchdog labels cũng kill ở90°C, missing heartbeat/sensors hoặc low RAM emergency.
Mọi named lab resources đã dừng/dọn; không đụng user apps hoặc OS protection.

Số đo tài nguyên có trong machine report: capture tối đa52°C, assessment tối đa54°C.
Đây là bounded data work, không phải sustained-training qualification.
Không có training supervisor hoặc checkpoint mới để resume. Không có PCAP/EVE của
75requests mới nên không tạo Rule-only comparative score hoặc claim added detection
value từ cohort này; so sánhP0 cũ vẫn là historical development evidence. Resource report PASS
không phải training completed; labels/Oracle recoveries có provenance riêng.

Raw receipts/session/auth/fixture data, source snapshots, tensors và review queue
ở `ai-training/.artifacts/quality_lab_20261107/` ignored local. Chỉ safe source,
tests, config design, aggregate reports/docs được Git handoff.92frozen/native
bundle files và GLU derivative manifest/files khớp hashes; Rules/Web/Policy Engine,
Frozen Research MVP và published release nguyên trạng. Không sealed data access,
AWS, AI enforcement hoặc model promotion.

Code: [collector](../ai-training/scripts/quality-lab-cohort.py),
[assessment](../ai-training/scripts/assess-quality-cohort.py),
[calibration comparison](../ai-training/scripts/compare-quality-calibration.py),
[inventory](../ai-training/scripts/inventory-research-data.py).
Validation:38tests PASS (receipt/Oracle, frozen MVP, rolling resource policy và
integration candidate), Ruff PASS. Không chạy lại fullstack không thay đổi.
Evidence index: [machine report](../ai-training/reports/AI_QUALITY_PHASE_20261107.json).
