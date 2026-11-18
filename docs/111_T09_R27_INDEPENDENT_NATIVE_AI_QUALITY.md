# T09 R27 — Native Data & AI Quality Advancement

**Kết luận: `NATIVE_RESEARCH_ADMISSION_IMPROVED_FINAL_QUALITY_BLOCKED`.** Đã chạy **26 HTTP thật**, xác minh Oracle/correlation/cutoff và tạo **6 mẫu canonical nghiên cứu theo task**, gồm **TRAIN2 / DEV4**, trên ba workflow khác về ngữ nghĩa. Chưa chứng minh sampling độc lập, đại diện theo T07; corpus global `ATTACK_INTENT`, CAL/TEST và mục tiêu recall≥90% / FPR≤1% vẫn **BLOCKED**. Không train một classifier để học lại authorization policy đã chính xác; không promote hoặc release model.

Run **`t09-r27-native-q6u9j3bg`**, nhánh `feature/ai-idps-shadow-integration`, parent **`b95bd72`**. Cửa sổ acceptance **18/11/2026 15:09:22–16:16:17 ICT**, khoảng **66,9 phút**, dưới timebox8h. [Handoff](/home/trung/projects/idps-web-aws/ai-training/contracts/native-independent-r27/r27-evidence.json) · [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/acceptance.json) · [Artifact SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/artifact-index.json)

## Acquisition đã thực hiện

Kế hoạch role, population, ontology, cutoff và lineage được khóa **trước acquisition**. Tái sử dụng KVM disposable `-nic none`, H2 riêng, BCrypt12 warm-up, cookie rotation, collector song song, NGINX, Suricata, Student Audit, URI100/URI76 projection và Rust shadow cũ. Không sửa application policy hoặc business serving code. [Preregistration](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/preregistration.json) · [App source/class/JAR pins](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/application-pins.json)

| Workflow / role nghiên cứu | Actor thực tế và target | HTTP / Oracle | Target labels |
| --- | --- | --- | --- |
| User read / TRAIN | ADMIN đọc user khác:200; STAFF đọc chính account nhưng thiếu quyền ADMIN:403 | **8/8** | 1 benign, 1 policy-violation attempt |
| Self profile / DEV | STUDENT đọc hồ sơ do principal resolve:200; ADMIN sở hữu hồ sơ nhưng thiếu role STUDENT:403 | **8/8** | 1 benign, 1 policy-violation attempt |
| Catalog creation / DEV | STAFF POST tạo chương trình học:201; STUDENT POST cùng action:403 | **10/10** | 1 benign, 1 policy-violation attempt |
| Tổng | **18 GET + 8 POST**, gồm20 setup/control và6 targets | **26/26** | **3 BENIGN_VERIFIED + 3 ATTACK_VERIFIED trong task hẹp** |

Đây không phải thay ID rồi lặp cùng case: user-read là ADMIN-only và user-resource lookup; self-profile resolve owner từ principal; catalog-create thực hiện transaction tạo row. Các role được counterbalance: **ADMIN, STAFF, STUDENT đều xuất hiện ở một target được phép và một target bị từ chối**. Không coi tên mới, seed hoặc guest boot mới là bằng chứng independence.

Oracle target nối trusted request ID, principal response/JDBC role, native Audit event và actor/session HMAC, policy đã pin, selected business-resource state trước/sau và nội dung response. Với self-profile, `userId`/record marker/owner được kiểm theo principal. Với POST được phép, JDBC xác nhận count0→1 và rowID1000 cùng response fields. Với POST bị từ chối, selected business-resource state giữ nguyên; không chỉ dựa vào201/403. Audit rows vẫn có thể được ghi như bình thường, nên “không mutation” chỉ nói tới business resource được kiểm.

Các usernames và role chỉ được tạo trong H2 guest. Bổ sung `major.short_code` và next identity phù hợp cho catalog seed; không đổi validation/service để endpoint dễ PASS. Transport gửi JSON POST thật với CSRF cùng session; refresh CSRF sau login. Các tên slot legacy `admin/student` trong transport không quyết định actual role: server/JDBC/Audit kiểm role thật, có cả STAFF. Runner intent được để không dùng cho ground truth.

**26 permits, 26 receipts, 26 physical request keys, 26 Oracle VERIFIED; 26 NSA tại cutoff.** Có **78 selected HTTP observations**, 26 mỗi N/S/A; không tính Suricata stats thành HTTP requests. Correlation dùng trusted ID, producer scope và TCP/flow/transaction evidence; không ghép bằng IP/thời gian/similarity. Không duplicate request hoặc false join. Native partial masks chưa được thu trong R27; không claim seven-mask coverage. [Reconciliation](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/admission.json)

## Context22 và timing

Giữ URI100 và Context20 nguyên version. Bổ sung **`idps-trusted-context22-r27-v1`**, primary representation **URI100+Context22 =122 float32**. Context22 giữ current-request authenticated state/role/binding, sáu resource categories, sáu missingness states và source flags. Category mới phân biệt user-admin, self-profile và academic-write. Catalog POST được whitelist vì không thay authentication/session; login/logout và route chưa hỗ trợ vẫn WITHHELD. [Schema](/home/trung/projects/idps-web-aws/ai-training/contracts/native-independent-r27/schema.json) · [Python](/home/trung/projects/idps-web-aws/ai-training/contracts/native-independent-r27/context22.py) · [Rust](/home/trung/projects/idps-web-aws/ai-training/contracts/native-independent-r27/context_rust/src/main.rs)

Không đưa literal IDs, username, cookie, HMAC, current status/outcome, Oracle, authorization verdict hoặc JDBC mutation vào vector. Owner relationship vẫn **GROUND_TRUTH_ONLY**, history/session age **WITHHELD**. Role lấy từ SecurityContext qua chính Audit của request; không dùng client headers hoặc snapshot session cũ. Các request vẫn gửi spoofed role/user/request-ID headers kiểm thử; actual roles và principal binding được giữ đúng.

Collector mã hóa trong lúc HTTP client và source readers chạy song song, timestamp sau encoding và giữ immutable versions. Giữ **cutoff1.000ms, guard1ms**; sáu target hoàn tất Context22 tại:

| Workflow | Allowed / denied encoding completion |
| --- | ---: |
| User read | **402,73 / 417,19 ms** |
| Self profile | **449,53 / 520,90 ms** |
| Catalog POST | **518,34 / 436,49 ms** |

Oracle hoàn tất sau diagnostic drain, không được đổi thành feature sớm. Đây là current protected request **tại cutoff sau application processing**, không cam kết context có trước authorization hoặc dùng cho inline prevention. Rust Context22 hiện là projector/replay riêng, chưa phải persistent Local scorer.

## Lineage, admission và phạm vi counts

Ba component khác nhau về policy branch, resource resolution và operation đã được kiểm. Exact primary view không overlap giữa role TRAIN/DEV; census exhaustive **15 cặp target**, không dùng approximate/saturated near index. Physical/session/campaign/material-template links giữ toàn bộ raw setup custody. Rejected TARGET records vẫn làm bridge; alias/near/protected conflicts phải quarantine connected component. Setup thuộc task session-establishment, không được biến coarse URI-only hoặc unavailable tensor của setup thành target-sample equivalence. Test xác nhận đổi guest/ID không xóa material-template bridge. [Graph/census](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/lineage-graph.json)

**Ba component structurally disjoint không đồng nghĩa ba mẫu IID từ population vận hành.** Chúng còn chung Local lab, ứng dụng, policy code và cách chọn case. Có **0 representative independent final exposure anchors**; không claim independence từ IDs hoặc seed. Không tạo thêm hàng trăm request giống nhau để làm n lớn.

| Đơn vị | Kết quả |
| --- | ---: |
| Physical HTTP requests | 26 |
| Target requests, cùng task hẹp | 6 |
| URI100 vectors trên targets | **3**, cả3 mixed-label |
| URI100+Context22 vectors / canonical research rows | **6** |
| Research TRAIN / DEV | **2 / 4**, labels1/1 và2/2 |
| Research CAL_FIT / CAL_OP / TEST | **0 / 0 / 0** |
| Formal/global T07 `ATTACK_INTENT` TRAIN/DEV/CAL/TEST mới được chứng nhận | **0/0/0/0** |

R27 profile **`ELIGIBLE_FOR_DECLARED_TASK_RESEARCH`** là một mở rộng T09 cho `AUTHORIZATION_POLICY_VIOLATION_ATTEMPT`, không phải chứng nhận serializer task enum v1 cũ, malicious motivation, publisher anomalous hoặc exploit success. Không tự chuyển6 research rows vào corpus global/formal. Không fake human-review attestation. Không gộp chúng vào433K publisher FIT hoặc tiến độ400K của task khác. [Admission profile](/home/trung/projects/idps-web-aws/ai-training/contracts/native-independent-r27/admission-profile.json) · [Research ledger](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/canonical-research-ledger.json)

Registry mới khóa các research roles và bảo vệ DEV khỏi future TRAIN reuse; intake tương lai phải load registry này. CAL/TEST không được thu/unseal. Cohort đã xem để phân tích không thể trở thành pristine TEST. Cần formal contract export/task compatibility và representative independent custody trước khi dùng cho global/final acceptance. Các thresholds/support/confidence gates T07 không đổi. [Role registry](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/native-source-role-registry.json)

## Vai trò AI và kết quả cùng cohort

Các B16/R20 scores dưới đây là **offline frozen-model replay** trên features đã chứng minh trước cutoff. Không phải live B16/R20 decisions trong guest hoặc bằng chứng score availability/runtime acceptance tại cutoff. Guest dùng Rust URI76 logistic shadow cũ để kiểm pipeline; không giả nó thành R20.

Trên cùng sáu targets, mỗi cặp authorized/unauthorized có method/URI100 giống nhau. URI100-only, role-only, category-only, campaign-only, method-only và availability-only đều có mixed groups; empirical recall ceiling khi không cho FP là0 trên panel này. Context22 tách được6 groups. Đây là **information census hồi cứu**, không phải classifier đã học hoặc kết quả independent evaluation. [Controls](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/information-proof.json)

| Arm, thresholds frozen | TN / FP / FN / TP | Recall / FPR | AP | Brier / ECE10 |
| --- | --- | --- | --- | --- |
| B16 URI100, `>0.9420260190963745` | **3/0/3/0** | **0% / 0%** | **0,5** | **0,43762 / 0,43270** |
| R20 URI76, `>0.9633333086967468` | **3/0/3/0** | **0% / 0%** | **0,5** | **0,37859 / 0,35462** |
| Deterministic authorization control | **3/0/0/3** | **100% / 0% point** | Không dùng làm ML metric | Không phải calibrated probability |
| Context-aware ML | Không train | Chưa có added value so policy | — | — |
| RI v2 / Hybrid | Không score chung | Thiếu observed full RI input/rule envelope | — | — |

B16 scores từng cặp giống nhau, khoảng0,06567 /0,09246 /0,04378; R20 cũng giống nhau trong từng cặp. GET4 và POST2 đều có AP0,5/recall0 tại threshold cũ. Request-weighted và balanced full-feature counts trùng vì cả6 primary vectors unique; mỗi mixed URI100 group cũng có đúng1/1 hai lớp. Precision của hai model ở operating point này không xác định vì không flag request nào.

Đây là **task-transfer diagnostic của publisher models trên authorization cases**, không kết luận model bị regression trên publisher task. Calibration numbers chỉ mô tả panel enriched3/3, không đại diện deployment prevalence. Không chọn model hoặc threshold mới từ các số này.

Policy control được kiểm theo policy normative và semantic outcome, nên **không tính3/3 thành ML breakthrough**. Không chứng minh được lợi ích ML thêm so authorization hiện hành. Do đó không fit logistic/SwiGLU trên6 rows để học một lookup và không full-train URI-only lần nữa. Giữ deterministic authorization cho task đã kiểm; RI v2 default, R20 shadow và B16 publisher research giữ nguyên. Notes CAL_OP recall **28,13%** và PKDD benign FPR **10,69%** vẫn chưa được giải quyết. Không mở lại TEST/stress hoặc fit ngưỡng theo chúng. Existing ETL đã chuẩn hóa absolute/origin URL; không có bằng chứng mới để lặp hướng normalization/training cũ.

Không có confidence bound T07 hợp lệ từ panel này. Nếu giả sử3 benign/3 attacks IID, 0/3 FP vẫn cho upper95% khoảng **63,16%**, 3/3 recall cho lower95% khoảng **36,84%**; giả định đó không được dùng để PASS. Cluster outcome còn suy biến/thiếu support. T07 cần ≥100 attacks/≥20 clusters mỗi claim, CAL support, adjusted benign anchors và performance/coverage strata; R27 chưa đạt. Không tuyên bố90%/1%.

## Technical acceptance và vận hành

- **36 R27 Python tests PASS**; suite chung Context20/Context22 có **79 checks PASS** gồm43 legacy compatibility. **3 Rust unit tests PASS**; **1.480 synthetic envelopes ×3 fresh workers**, error0, restart bit-exact, malformed ABSTAIN/recovery PASS. **6 real target contexts** có Rust/Python parity error0. Bounded projector+serialization/IPC p50/p95 **0,041/0,288 ms**, không thay T07 load windows.
- Tách host module `context22` tránh cache module Context20 trong interpreter chung. Guest vẫn nhận module riêng trong namespace cô lập. Functional AST khớp captured execution; original execution bytes và source hashes được giữ. Không đổi schema20 hoặc Rust/Python URI100. [Compatibility](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/namespace-compatibility.json)
- Supervisor serial, checkpoint và no-redispatch; acquisition **154,04 giây**, unit **`idps-r27-native-q6u9j3bg.service`**, PID ban đầu **22301**, đã kết thúc exit0. Source cuối tự nối admission→information→finalizer. Bản acquisition đầu dùng capture-only supervisor; admission chạy qua managed phase riêng. Recovery source cuối đã được chạy thật ở `--finalize-existing`: **0 HTTP thêm**, ledger SHA giữ nguyên. Test mới bắt một missing import trước live, đã sửa và giữ failure XML. [Offline resume proof](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/offline-resume-proof.json)
- **8 Resource Adapter attempts COMPLETED/exit0, cleanup PASS**; kernel worker/guardian cgroups vắng mặt, QEMU exit0, guest shutdown và private staging cleanup PASS. Capture giữ **1 CPU /3GiB /16 tasks**, guardian25% CPU/256MiB/32 tasks; compiler/parity/admission dùng bounded one-thread phases. Fresh ceiling cuối khoảng13,75 core-equivalents/15,25GiB; không cấp thêm tài nguyên cho workload bị chi phối bởi I/O/drain.
- **26 dispatch kernel readbacks `cpu.max=100000 100000`**, không freeze, action/ownership/invocation/deadline hợp lệ. Nhiệt tại dispatch **54–90°C**; policy90/100, hardware priority, watchdog và fail-safe giữ nguyên. Không cố làm nóng hoặc bypass sensor. Đây không phải full peak thermal/memory time series.
- Bốn Local services active, PID RI **4207**, R20 **4208**, collector **4205**, receiver **4206**, restart0 trong boot, health READY. `Linger=yes`; không deliberate logout/reboot/suspend test ở R27. Không còn R27 job hoặc QEMU thử nghiệm chạy. Không training, service restart, firewall/Hybrid change, VM bền vững hoặc AWS deploy.
- ONNX/Rust model acceptance/restart/rollback của frozen artifacts kế thừa R26.1/R22.1 và model SHA được kiểm khi scoring. Không có new model/ONNX hoặc persistent Context22 deployment để claim production readiness. Clean-checkout legacy dependencies/private model packaging cũng chưa được chứng nhận.

## Git, preservation và quyết định tiếp theo

Giữ nguyên SHA **34 dirty tracked files**, **266 artifacts R26.1 +193 artifacts R26.2**, models/checkpoints và protected roles. Không mở sealed payloads hoặc rewrite historical reports. Chỉ commit source/contract/report R27; private receipts, actor/session evidence và data không push.

Functional commits: **`876417b`** — Context22 và ba native workflows; **`bb2d4db`** — scoped admission/lineage; **`087c858`** — offline supervisor finalization không redispatch. Report/handoff commit riêng cùng branch. Artifact index SHA **`2833799aa26cb025f70d14a6597665654a4283574cb7d0a217553d959537f3ab`**; acceptance SHA **`5738a34fcfb1b451ebfcef423db263c967e3a000845c9d9c5af1f6b41bb2333f`**; Rust binary SHA **`79003ed422e46b0a674163ed8c61da1c297e986549aed5e025e67e36ea14c27e`**. [Push readback sau commit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r27-native-q6u9j3bg/git-push.json)

**Đã giải quyết:** native STAFF/ownership/POST ground truth, pre-cutoff context cho các policy khác nhau, role shortcut controls, internal research admission có role registry, ABI coexistence và no-HTTP finalization recovery.

**Còn BLOCKED:** representative independent native cohort; global task compatibility/formal export; CAL/TEST/support/confidence T07; publisher generalization; lợi ích ML thêm; persistent Context22/new-model Local/AWS acceptance và release. Không có lý do chạy tiếp các bản sao của ba policy hoặc training trên cùng400K cũ.

**Đúng một nhiệm vụ tiếp theo:** thu một cohort **payload/behavior có outcome Oracle**, ngoài ba authorization lookups đã biết, với sampling/custody và formal task export khóa trước. Tập trung thông tin mà deterministic authorization không cung cấp; giữ whole components và CAL/TEST độc lập. Chỉ pilot/full-train khi cohort đó chứng minh được thông tin và lợi ích ML mới. Chưa tự triển khai nhiệm vụ tiếp theo.
