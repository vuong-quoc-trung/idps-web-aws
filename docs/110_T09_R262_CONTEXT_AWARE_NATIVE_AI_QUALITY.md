# T09 R26.2 — Context-Aware Native AI Quality

**Kết luận: `CONTEXT_PROOF_PASS_DATA_INSUFFICIENT`.** Đã thu HTTP thật, bổ sung trusted context, chứng minh thông tin phân biệt mới trước cutoff và kiểm Python/Rust parity. Chưa có native split độc lập để train hoặc chứng minh recall ≥90% tại FPR ≤1%. Giữ RI v2 phục vụ mặc định, R20 shadow và B16 ở research.

Run **`t09-r262-context-yaqvp710`**, nhánh `feature/ai-idps-shadow-integration`, parent **`b3f54e3`**. Cửa sổ acceptance **18/11/2026 12:09:59–12:42:22 ICT**, khoảng **32,4 phút**, dưới timebox 8 giờ. Không chạy training, tải lại dataset hoặc mở protected evaluation. [Machine handoff](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-context-r262/r262-evidence.json) · [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/acceptance.json) · [SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/artifact-index.json)

## Trusted context và giới hạn thời điểm

Giữ nguyên HTTP topology. Producer thật là `SecurityRequestFilter`: Authentication/authorities từ `SecurityContextHolder`, session từ `request.getSession(false)`. `AuditJsonlExporter` ghi event ID, producer scope, role và actor/session HMAC vào file riêng. Collector hiện có xác minh trusted NGINX ID, native Audit event, method/route, edge TCP leg, Suricata flow/tx, receipt và clock. Không tin role/user headers do client gửi. [Producer source/class SHA](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/trusted-producer.json)

ABI mới **`idps-trusted-context20-r262-v1`**, float32, gồm authentication known/state, bốn role flags, actor/session binding, bốn resource categories, sáu missingness states và ba source flags. URI100 giữ nguyên lane/version. Resource category chỉ là loại endpoint của request đã xác minh, không phải verdict authorization. Chính sách authorization chỉ xuất thành **deterministic advisory control riêng**, không nằm trong vector hoặc được tính là ML score. [Schema/ordering](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-context-r262/schema.json) · [Python reference](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-context-r262/context.py) · [Rust projector](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-context-r262/context_rust/src/main.rs)

| Nhóm | Provenance và availability | Hướng xử lý |
| --- | --- | --- |
| Authentication, role, actor/session binding | Chính Audit của request hiện tại; producer scope/native event/correlation proof; encode trong collector song song HTTP | Chỉ dùng nếu hoàn tất trước **999 ms** và clock/correlation hợp lệ |
| Resource category | Mapping đã pin từ method/route thực sự được liên kết; không nhìn response hoặc nhãn | Hỗ trợ GET student-directory và self-principal |
| Source presence | Causal cutoff view T04, không lấy structural mask thay time-valid mask | Giữ N/S/A/NS/NA/SA/NSA/NONE; không tự bổ sung source |
| Owner relationship | JDBC + application Oracle sau diagnostic drain | **GROUND_TRUTH_ONLY**, không vào vector |
| Session age/history | Chưa có freshness/revocation custody phù hợp | **WITHHELD**, không dùng cache principal cũ |
| Login/logout/CSRF và route chưa hỗ trợ | Authentication có thể thay đổi trong chính request | **WITHHELD**, không suy benign |

Sáu trạng thái `AVAILABLE_BEFORE_CUTOFF / OBSERVED_LATE / MISSING / WITHHELD / UNTRUSTED / GROUND_TRUTH_ONLY` có mask tường minh. Unavailable context ABSTAIN, không biến zero thành quan sát hợp lệ. Không đưa literal actor/resource ID, HMAC, username, cookie, credential, status, latency, outcome, authorization verdict hoặc Oracle label vào model input. HMAC chỉ được kiểm trong RAM rồi bỏ; private evidence giữ full-envelope SHA và proof references.

Đây là **context của protected GET tại thời điểm quyết định sau xử lý request**, không phải cam kết context trước khi authorization chạy. Không sửa Student Web hoặc thêm synchronous I/O/network dependency vào application path. Private Rust JSON replay cũng **không phải** cơ chế xác thực: binding phải lấy từ registry/receipt custody do collector quản lý, không nhận self-asserted binding của HTTP client.

## HTTP thực tế, lỗi và phục hồi hữu hạn

| Campaign | HTTP / Oracle | Mask tại cutoff | Vai trò evidence |
| --- | --- | --- | --- |
| `capture-a` | **12 / 12** | 12 NSA | 3 benign + 3 attack record witnesses; draft context timing |
| `capture-b` | **0 / 0** | Không có | Global Adapter flock bị verifier giữ; guardian từ chối trước worker/boot |
| `capture-b2` | **7 / 6** | 6 NSA, 1 NONE | Dừng đúng tại Oracle CSRF khi dùng session đã authenticated |
| `capture-b3` | **6 / 6** | 6 NSA | Cookie jar đổi ADMIN→STUDENT; 2 context vectors thật trước cutoff |
| `capture-c` | **12 / 12** | **12 NSA** | Final two-class capture, 8 protected GET context vectors trước cutoff |
| Tổng | **37 / 36** | **36 NSA, 1 NONE** | 37 trusted physical request keys, không che lần lỗi |

Ba lỗi đã được xử lý, giữ evidence gốc:

1. Tôi khởi chạy hai Adapter phase đồng thời. Adapter cố ý chỉ cấp một managed allocation/user; global flock từ chối campaign trước preflight/worker, trả `GUARDIAN_EXIT_WITHOUT_RESULT`. Sau đó các phase chạy **tuần tự**; không thay contract hoặc biến lỗi thành COMPLETED.
2. Oracle CSRF lab cũ đòi một `Set-Cookie` mới cho mỗi GET. Khi session HttpOnly hợp lệ đã tồn tại, ứng dụng không cần gửi lại cookie. Sửa Oracle để ghi **existing HttpOnly-session continuity riêng**, giữ nguyên quan sát `http_only_session=false` khi không có Set-Cookie mới. Vẫn xác minh cấu trúc XOR token; login tiếp theo phải dùng CSRF thật, có JDBC mutation và session rotation. `capture-b3` chứng minh switch principal bằng HTTP thật. Không sửa authentication của ứng dụng.
3. Draft đầu chỉ timestamp khi bắt đầu snapshot; vector được assemble sau drain. Không tính draft đó là proof materialization của ABI20. Bản cuối encode ngay trong collector, timestamp **sau** encoding, tạo immutable versions khi source tới và chọn đúng phiên bản hợp lệ tại cutoff. Không lấy timestamp Oracle hoặc finalization làm timestamp sớm giả.

Các amendment được ghi **trước boot**; tổng ngân sách sau sửa là 37 HTTP, không tự chạy thêm. Guest mới có H2/session mới; không gửi lại dưới campaign identity cũ. [Dispatch failure](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/dispatch-recovery.json) · [Timing amendment](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/context-timing-amendment.json) · [Final capture lock](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/final-capture-amendment.json)

Client của các capture gửi `X-Role: ADMIN`, `X-User-Id: 1`, spoof request ID và XFF kiểm thử. Request STUDENT vẫn có role STUDENT từ producer thật. `capture-c` có đúng 12 permits/receipts/Oracle, trusted ID/correlation/URI76 Rust parity/URI100 projection PASS, không duplicate hoặc false join; QEMU exit0, Adapter COMPLETED và cleanup PASS. Không dịch **cutoff 1.000 ms / guard 1 ms**.

Timing đo trên `capture-c`:

| Request | HTTP header latency | Full context vector hoàn tất | Oracle |
| --- | ---: | ---: | --- |
| ADMIN GET record, 3 request | 46,54–74,41 ms | **274,69–569,44 ms** | VERIFIED; ground truth sau khoảng 3.003–3.006 ms |
| STUDENT GET cùng records, 3 request | 14,80–29,35 ms | **195,51–423,89 ms** | VERIFIED denial + actor/session/role/owner/policy |
| ADMIN/STUDENT GET principal | 63,51 / 28,86 ms | **188,69 / 495,48 ms** | Principal response + JDBC role |
| ADMIN/STUDENT POST login | 595,48 / 204,04 ms | WITHHELD | 204 bodyless, JDBC mutation và rotation VERIFIED |

Source S thực sự tới muộn hơn N/A nhưng vẫn trước cutoff trong final capture; không suy arrival từ producer timestamp. NONE của partial run được giữ nguyên. Các source masks còn lại và fault injection là **fixture**, không claim native seven-mask coverage. [Receipts, raw features, timing và semantic reconciliation](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/native-reconciliation.json)

## Information proof và lựa chọn kiến trúc

Final panel dùng **cùng 8 GET**: 3 authorized record reads, 3 denied outside-role attempts trên đúng URI/method/resource và 2 principal controls. Attack task là **`AUTHORIZATION_POLICY_VIOLATION_ATTEMPT`**, không phải exploit thành công, malicious payload hoặc malicious motivation được suy từ 403. Ground truth nối actor/session Audit với principal/JDBC role, owner ổn định trước/sau, pinned policy và application record-marker/denial. Oracle không được dùng để tạo context.

Ba cặp HTTP có URI100 giống nhau, context khác nhau và đều có actual encoding completion trước cutoff. Census hồi cứu trên panel:

| Input/control | Groups / mixed | Sai số tối thiểu nếu quyết định theo group | Empirical recall ceiling khi 0 FP |
| --- | --- | ---: | ---: |
| URI100 | 3 / 2 | 3 | 0% |
| Role-only | 2 / 1 | 1 | 0% |
| Resource-category-only | 2 / 1 | 3 | 0% |
| Availability-only | 1 / 1 | 3 | 0% |
| Context20 | 4 / 0 | 0 | 100% |
| URI100 + Context20 | 6 / 0 | 0 | 100% |

Đây là **information census dùng nhãn hồi cứu**, không phải fitted classifier hoặc generalization score. STUDENT principal control hợp lệ ngăn việc coi mọi STUDENT là attack. Shared template/role/policy confounding còn tồn tại ngoài panel.

| Arm trên cùng 8 GET, threshold frozen | TN / FP / FN / TP | Phạm vi |
| --- | --- | --- |
| B16 URI100, `>0.9420260190963745` | **5 / 0 / 3 / 0** | Offline scoring của input request thật; authorization task mới |
| R20 URI76, `>0.9633333086967468` | **5 / 0 / 3 / 0** | Cùng roster, không đổi threshold |
| Deterministic role/resource policy | **5 / 0 / 0 / 3** | **Control, không phải ML**; advisory replay, không enforcement mới |
| RI v2 | Không score | Không có full selected-header tensor quan sát ở cutoff; không dựng input giả |

B16 score cùng principal khoảng 0,83636; record scores khoảng 0,00639–0,00646 và giống nhau giữa hai role. R20 cũng không phân biệt role từ URI76. Thêm epoch hoặc tham số URI-only không xử lý được missing information này.

**Không train context model.** Known deterministic authorization đã xử lý đúng trường hợp role/resource này; chưa có dữ liệu độc lập để chứng minh ML mang lợi ích thêm. Không fit logistic trên vài role rồi báo chất lượng cao. Không gộp native task với `PUBLISHER_ANOMALOUS`. Publisher B16 vẫn là nghiên cứu 400.256 parameters / 433.261 originals / 50.230 vectors; Notes CAL_OP recall **28,13%**, PKDD benign FPR **10,69%** chưa được giải quyết. Không mở lại stress/TEST để tune và không full-train lại URI100.

## Admission, diversity và T07

37 physical requests tạo **111 source observations**: 37 N, 37 S, 37 A; có 6 method/target signatures và 4 unique URI100. Không gọi 6 signatures là full HTTP original identities vì credential/body được withheld. Không cộng publisher và native khác ontology vào tiến độ 400K.

Trong tất cả các lượt mới có **9 benign và 6 attack record witnesses** theo machine semantic Oracle. Chỉ final capture có **3+3 record witnesses với full context completion proof**. Cộng 4 strict principal controls từ `capture-b3/c` có **10 candidate views**: 7 benign controls / 3 violation attempts, **4 unique context vectors**, **6 unique URI100+context combinations**. Đây không phải 10 canonical TRAIN samples.

Tất cả cùng fixture actors/policy/templates và có representation/session/campaign bridges; bảo thủ gom **một lineage component**. Chưa có native TRAIN/DEV/CAL_FIT/CAL_OP/TEST hợp lệ: **0/0/0/0/0**, canonical TRAIN **0**. Candidate ledger giữ pending lineage/role/admission; không fake human review. Human review pending không tự trở thành lệnh cấm internal machine research, nhưng chưa có đủ independent split/support để pilot hợp lệ.

T07 vẫn cần ≥100 attack/≥20 independent clusters cho claim, CAL tối thiểu 200 benign/50 attacks/10 clusters mỗi lớp mỗi stratum, cùng adjusted benign-anchor confidence và các calibration/coverage gates. Không suy FPR vận hành 1% từ 0/5 FP trong một panel chung policy. Chưa có source-mask/environment/method support và production performance windows. Toàn bộ data đã exposed để thiết kế context không thể trở thành pristine TEST.

101 receipts lịch sử và **74 pending candidates** giữ nguyên trạng thái. **266 artifacts R26.1** khớp SHA; không sửa checkpoint, nhãn, source role hoặc sealed holdout. [Candidate ledger](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/candidate-ledger.json)

## Technical acceptance, resources và Local

- **43 Python tests PASS**: trust binding, all masks/NONE, cutoff boundary, unsupported/missing/late, privacy, spoofed fields, stale snapshots, no-cache revocation behavior, cross-request isolation, duplicate idempotency/conflict, frozen prefix và CSRF-session Oracle. Logout/revocation/concurrent-request schedules là fixture; không claim live concurrent hoặc logout acceptance.
- **3 Rust unit tests PASS**. **985 synthetic envelopes ×3 fresh processes**, vector error **0**, restart bit-exact, malformed ABSTAIN/recovery PASS. **10 real native context frames** có Rust/Python parity error0 qua offline replay. Rust context chưa được deploy thành persistent scorer. [Final runtime/parity](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/final-checks/context-runtime.json)
- Bounded Rust projection+serialization/IPC p50/p95 **0,056 / 0,509 ms**; không thay cho T07 load test. Không có context model/ONNX mới. B16 ONNX/raw URI100 parity, wrongSHA/ABSTAIN/restart và RI/R20 recovery/rollback được kế thừa từ R26.1/R22.1 vì các thành phần đó không đổi.
- Fresh capacity cuối khoảng **13,75 core-equivalents / 18,75 GiB**, sau reserve. Công việc chính bị chi phối bởi I/O và drain3s/request; tái sử dụng envelope KVM đã nghiệm thu **1 CPU / 3 GiB / 16 tasks**, guardian **25% CPU / 256 MiB /32 tasks**. Compiler/parity/census chạy tuần tự, một thread, RAM 512–1.024 MiB theo phase. Không cấp thêm RAM/CPU để làm đẹp utilization.
- **37 dispatch kernel readbacks**: 35 lần `cpu.max=100000 100000`, 2 lần **`50000 100000`** khi guardian THROTTLE; không frozen, action/quota/ownership/invocation hợp lệ. Nhiệt tại dispatch **56–95°C**. Policy90/100 và hardware priority giữ nguyên. Không cố làm nóng, nâng ngưỡng hoặc bypass cảm biến. Snapshot cuối KVM có memory.current khoảng1,75GiB; không gọi đó là peak đầy đủ.
- **10 Adapter attempts có cleanup receipt**, gồm refusal trước worker và partial HTTP failure. Readback worker/guardian cgroups vắng mặt; owned kernel/initramfs/staging được cleanup, QEMU exit0 ở các live completed runs. Không còn job capture/training R26.2. Checkpoint failed/partial giữ nguyên, không resend.
- Bốn Local services vẫn ACTIVE, PID RI **4207**, R20 **4208**, collector **4205**, receiver **4206**, không restart trong boot; health hiện hành READY, `Linger=yes`. Không restart service khỏe, không thay model mặc định/Hybrid/firewall, không đụng VM bền vững. ACPI kernel issue chưa được chữa tận gốc; SensorReader và guardian khỏe trong cửa sổ này, không claim loại bỏ nguy cơ tái diễn.

## Git, SHA và bước tiếp theo

Functional commits: **`07ac1e1`** — context ABI, causal collector/capture, Oracle repair và tests; **`cc8beba`** — offline information census, admission boundaries, serial final checks và cleanup. Báo cáo/handoff commit riêng trên cùng branch. Chỉ stage các file R26.2; **34 dirty tracked files** ban đầu giữ nguyên SHA. Private artifacts, raw receipts, model weights, keys và checkpoints không commit. Chưa chứng nhận clean-checkout release packaging của các legacy dependency đang untracked.

SHA index **`396892e17c46977c832a1c5e2856de002dc77009eb45c4f7347eeb75943338dd`**; acceptance **`ec5f2c4b410b28814c77ef9210e821c6b84a9b9ea8f20451bb006e0989fdb9cf`**. Rust context binary SHA **`d519e397828a6574db3898a86eaf09f6ebe7d7556579222f2be1837e05d79974`**. Exact execution/staging source snapshots được giữ riêng trước formatting; current reference được kiểm lại offline. [Push readback sau commit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r262-context-yaqvp710/git-push.json)

| Gate | Trạng thái |
| --- | --- |
| Trusted causal context, current protected GET scope | **PASS Local lab** |
| Information gain so URI-only; negative controls | **PASS**, không cần train để chứng minh |
| Python/Rust preprocessing, ABSTAIN, restart | **PASS trong scope fixture/offline native replay** |
| HTTP/correlation/Oracle/final encoding | **PASS final capture** |
| Resource control, serving preservation, cleanup | **PASS**, failure history được giữ đầy đủ |
| Canonical admission, independent native pilot | **BLOCKED**, lineage/role/support chưa đủ |
| Recall ≥90% / FPR ≤1%, calibration, release | **BLOCKED** |
| Persistent context-model Local/AWS deployment | **Chưa triển khai**, không có model qualified để promote |

**Đúng một nhiệm vụ tiếp theo — R27: independent task-specific cohort và custody acceptance.** Khóa lineage/roles trước acquisition; bổ sung actor/resource/ownership hoặc causal-behavior scenarios khác có bằng chứng trước cutoff, giữ whole components cho DEV/CAL/TEST. So deterministic control với ML chỉ tại phần có thông tin/lợi ích thêm; không mở rộng lại cùng template chỉ để tăng n. Publisher threshold-transfer/PKDD failure giữ track đánh giá riêng. Chưa tạo release hoặc tự triển khai R27.
