# T09 R26.1 — Autonomous Recovery and Model Quality

**Kết luận: `QUALITY_IMPROVED_NATIVE_BLOCKED`.** Đã nghiệm thu checkpoint B, hoàn thành một continuation, chọn lại **B16 URI100 SwiGLU, 400.256 tham số**, export/calibrate/parity và khôi phục khả năng vận hành Local trong cửa sổ đã kiểm. Đã có **3 ATTACK_VERIFIED theo tác vụ authorization-policy violation attempt** và 3 đối chứng benign từ HTTP thật. Native independent split và mục tiêu 90% recall/1% FPR vẫn chưa đạt; không promote model.

Run **`t09-r261-recovery-drliluc_`**, ngày **18/11/2026 ICT**, nhánh `feature/ai-idps-shadow-integration`, parent HEAD `6f1f695`. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/acceptance.json) · [SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/artifact-index.json) · [Entry points và scope](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-recovery-r261/README.md)

## Host recovery và trạng thái thực tế

Host đã có boot ID mới ngay khi bắt đầu R26.1; cả bốn service đã active. R26.1 **không reboot, sửa kernel/firmware, tắt AppArmor hoặc bỏ cảm biến**. Không tuyên bố đã chữa nguyên nhân ACPI ở kernel. Boot vẫn ghi cảnh báo ACPI deferred workqueue, nhưng SensorReader thực tế đọc đủ coretemp/platform/auxiliary sensors: năm mẫu đầu **47°C**, không alarm, **11–108 ms/read**. Guardian tiếp tục chạy trong các phase.

Sau gián đoạn phiên làm việc có thêm một boot ID mới. Training và capture đã hoàn tất trước gián đoạn, không khởi chạy lại. Artifact/checkpoint vẫn nguyên vẹn. Probe cuối trên boot hiện tại có năm mẫu **66/66/66/66/54°C**, tối đa **89,9 ms/read**, không alarm. Đây là PASS trong cửa sổ quan sát; nguy cơ ACPI stall tái diễn còn tồn tại.

| Local user service, readback cuối | PID | Trạng thái | Restart trong boot hiện tại |
| --- | ---: | --- | ---: |
| `idps-r22-local-ri.service` | 4207 | RUNNING | 0 |
| `idps-r22-local-scorer.service` | 4208 | RUNNING | 0 |
| `idps-r22-local-collector.service` | 4205 | RUNNING | 0 |
| `idps-r22-local-receiver.service` | 4206 | RUNNING | 0 |

`Linger=yes`. Các service đã tự start sau boot mới; chưa claim thử logout/reboot có kiểm soát dưới tải. Model serving và unit configuration giữ nguyên: RI v2 phục vụ mặc định, R20 ở shadow. [Probe cảm biến](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/sensor-health.json) · [Boot/gián đoạn](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/interruption-recovery.json) · [Readback tài nguyên](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/resource-acceptance.json)

## Resource integration và hai ngưỡng nhiệt

Đo được **16 logical CPU**, RAM vật lý khoảng **30,21 GiB**, available lúc staging khoảng **22,81 GiB**. Resource Contract tính ceiling khoảng **13,75 core-equivalents/17,75 GiB** sau reserve; không tự cấp toàn bộ ceiling. Benchmark 8 scratch updates trên đúng kiến trúc cho thời gian **1,7175 / 1,5277 / 1,3448 giây** với **1/2/4 BLAS threads**. Chọn 4 threads theo wall time, không chọn theo CPU utilization. RAM 4 GiB đủ cho peak khoảng 1,3 GiB; không tăng RAM vô ích.

Sửa hai bất cập tại nguồn:

1. Adapter CLI/controller mặc định chỉ cho một CPU. Bổ sung **pinned bounded-allocation evidence** theo quyền nghiên cứu R26.1, xác minh benchmark, hardware hash, phase và fresh host ceilings. Default cũ giữ nguyên; đường mới không tự thay production scaling gate 300 giây.
2. Start barrier luôn ghi `OPENBLAS/OMP/MKL/NUMEXPR=1`, bỏ qua môi trường caller. Bổ sung `--blas-threads`, bind vào request, chỉ cho nhiều threads khi allocation review hợp lệ và không vượt quota. Probe cuối xác nhận **hai BLAS pools và OpenMP đều 4 threads**, kernel **`cpu.max=400000 100000`**, RAM **4 GiB**, swap0, pids16. Scratch 8 updates sau sửa mất **1,1401 giây**; không ghi vào checkpoint nghiên cứu.

**Continuation đã hoàn tất trước khi phát hiện lỗi barrier, nên numerical training thực tế dùng 1 thread, dù quota ceiling là 4 CPU.** Exact replay được thực hiện đúng môi trường 1 thread. Không train lại để thay con số sử dụng CPU. Các workload tương lai có đường 4-thread đã được live-verify.

Boundary fixture dùng một sleep child trong cgroup thật, không làm nóng máy:

| Nhiệt fixture | Software state | Kernel quota readback, base400% |
| --- | --- | --- |
| 89°C / 90°C | NORMAL | `400000 100000` |
| 90,1°C / 99°C / 100°C | THROTTLE | `200000 100000` |
| 100,1°C | Stop/pause compute | Worker dừng, cleanup PASS |

Hardware alarm/limit vẫn ưu tiên. Hardware profile hiện tại có stop protection 100°C; không bỏ bảo vệ này để ép tiếp tục ở 100°C. Predicate phục hồi software-only được test với complete trip proof, no alarm, cleanup/checkpoint và stable ≤90°C; **chưa có live over-temperature pause/resume để claim**. Watchdog, sensor outage hoặc hardware stop không tự resume. [Benchmark](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/compute-benchmark.json) · [Final effective allocation](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/final-allocation.json) · [Kernel boundary fixture](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/thermal-boundary-kernel.json)

## Checkpoint B và continuation

Đối soát parent B epoch **16/step400**, best/latest/previous, arrays/state SHA, original code/config/data bindings, seed, scheduler, permutation và finite parameters. Worker mới replay **epoch15→16 bit-exact** cả weights, Adam, sampler và loss. NumPy/ONNX max error **1,1921e−7**. Không sửa checkpoint R26 gốc.

Trước continuation, đánh giá B16 và A trên cùng TUNING; calibrate cố định ở CAL riêng nhưng **quyết định continuation đã khóa bằng TUNING**, không dùng CAL/TEST để chọn. B16 tăng macro source recall **24,80%→77,54%**, đủ điều kiện ≥5pp và không giảm WAF/Notes quá2pp. Đây là research TUNING, không phải production metric.

Tạo namespace checkpoint mới, giữ weights/Adam/seed/sampler/schedule. Không khởi tạo lại epoch0, không đổi nhiều hyperparameters. Continuation từ **epoch16/step400**, early stopping tại **epoch21/step525**, **best vẫn epoch16**; khoảng **45,02 giây** gồm training và so logistic. Năm epoch bổ sung không cải thiện tiêu chí đã khóa, nên không kéo dài. Replay độc lập **epoch20→21** khớp bit. Không claim mid-batch exact resume.

| Cohort research dùng cho B | Original requests |
| --- | ---: |
| FIT | **433.261** |
| TUNING | **11.082** |
| CAL_FIT | **11.354** |
| CAL_OP | **3.901** |
| Source2 RESEARCH_TEST | **3.750** |

FIT gồm WAF400K, Notes1.745 và SR-BH31.516, có **50.230 unique URI100**. Kish effective original weight khoảng **10.256,73**, không tương đương 433K samples độc lập. Giữ nhãn publisher theo source/task, cả hai nhãn trong mixed groups và equal-source/class weighting. Source2 research subroles thuộc **R13 FIT đã exposed**; không chuyển chúng thành pristine/native TEST. Publisher eval/test/heldout và historical SR-BH DEV/CAL/TEST không được mở. Notes RESEARCH_TEST cũ không được mở lại để chọn B. [Checkpoint audit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/checkpoint-audit.json) · [Selection](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/model-selection.json) · [Replay](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/continuation-replay.json)

## Calibration, quality và generalization

Khóa model bằng TUNING trước scoring. Positive-slope Platt fit trên Notes/SR-BH CAL_FIT với equal source mass, giữ prevalence trong từng source. Một global strict `>` threshold lấy max theo request/vector FPR cap **0,5%** của từng CAL_OP source. **Không thay threshold theo stress/TEST/native capture.** WAF không có CAL mới đủ vai trò để claim calibration toàn deployment.

B raw SHA **`02bdfa4e3587b05940381561bdd9401321387fc00ce5934e5dac9229374562bd`**; calibrated SHA **`fdff05ee91f181268121ee7c72e573a4b2d771c3a8ee60cfa28e9d11860f2271`**. Platt slope **1,00062419**, intercept **−0,37847205**. Threshold **0,9420260190963745**, little-endian float32 **`9e28713f`**. Best checkpoint SHA **`0f0b0d8ab173d8c7ff0dba43809837d240c5dd307f75c340b6706fda9593d6e7`**.

Trên cùng Source2 research holdout, 1.083 normal/2.667 CAPEC-labeled, cùng CAL protocol:

| Model | Recall | FPR | Precision | AP | Brier | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R20 research recalibration | 0% | 0% | Không có positive prediction | 0,96047 | 0,14764 | 0,20749 |
| R25 research recalibration | 1,84% | 0% | 100% | 0,98153 | 0,12098 | 0,21823 |
| R26A, common CAL protocol | 73,42% | 1,108% | 99,39% | 0,96209 | 0,11024 | 0,09358 |
| Logistic ba nguồn | 47,54% | 4,524% | 96,28% | 0,94477 | 0,11963 | 0,10531 |
| **B16 / B_FINAL** | **83,76%** | **0%** | **100%** | **0,99899** | **0,02565** | **0,03963** |

B16 và B_FINAL có cùng weights và ONNX SHA. Confusion **1083/0/433/2234**. Vector-balanced trùng request-weighted trên cohort này vì vector unique. Paired recall gain so A **+10,35pp**, component-bootstrap95% **[+3,74;+20,53]pp**; FPR giảm **1,108pp**. Đây là diagnostic research groups, không phải paired native T07. Old active R20 threshold khác research recalibration trong bảng; không diễn giải recall0 thành chất lượng serving lịch sử. Logistic R13 AP0,8874 giữ benchmark khác, không xếp hạng trực tiếp bằng AP giữa cohort.

| Method, B trên source2 research holdout | Normal / anomalous | Recall | FPR |
| --- | ---: | ---: | ---: |
| GET | 1.049 / 2.425 | 87,13% | 0% |
| POST | 34 / 152 | 78,29% | 0% |
| OTHER | 0 / 90 | 2,22% | Không đủ benign support |

Cluster-bootstrap recall95% của B khoảng **[72,24%;91,47%]**. 0/1.083 FP có unadjusted request-binomial upper95% **0,276%**, nhưng chỉ có **103 benign template anchors**: 0 FP cho upper95% **2,87%**. Không dùng request count để giả native exposure independence hoặc claim đạt adjusted T07 FPR.

CAL_OP của B: **Notes recall28,13%, FPR1/374=0,267%; SR-BH recall83,03%, FPR1/617=0,162%**. Notes vẫn fail recall80%. FPR stress frozen: **CSIC0/36K**, **PKDD10,69%**, cải thiện từ A17,81% trên cùng research CAL protocol nhưng còn quá cao. PKDD GET FPR **13,17%**, POST **0,480%**, OTHER0%; không có attack class ở stress này để claim recall. Không fit hoặc chọn lại threshold từ stress. [Evaluation lock](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/evaluation-lock.json) · [Metrics và confidence](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/evaluation.json) · [Paired comparison](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/paired-comparison.json)

### Nguyên nhân giới hạn được định lượng

Notes CAL_OP có **40/64 positives** trong một component với **63 normal**. B bỏ sót cả40 ở group đó; tổng46FN gồm24 chia vector với normal. R26A cũng bỏ sót40 group này. Scores positive trong group khoảng **0,132–0,274**, thấp hơn rất nhiều cutoff0,942. Research TEST Notes cũ có template/method mixture khác, chỉ44 malicious GET; không có POST malicious. Vì vậy recall29,69% CAL so84,09% TEST cũ không chứng minh generalization ổn định. Không dùng TEST cũ để chọn feature/ngưỡng mới.

SR-BH CAL có nhiều pure-positive groups bị rank thấp; source riêng có cutoff diagnostic thấp hơn global Notes-driven cutoff. Collision, ranking và threshold transfer cùng tồn tại. Các thí nghiệm URI164/HTTP244 đã kém control được giữ nguyên kết luận; không lặp hoặc tăng tham số vô căn cứ. Native contrast mới bên dưới còn chứng minh URI-only thiếu authorization context cho một task khác. [Diagnosis, từng method/source/group](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/diagnosis.json)

## Native HTTP thật và semantic ground truth

Đối soát lại 101 receipts cũ vẫn khớp: **87 NSA/14NA, 101 Oracle, 74 pending candidates**. Không tự nâng37 attack-intent thành verified; chúng thiếu actor/session/role/owner/policy và URI76 cutoff cần thiết. Sáu authorized-read witnesses R8/R10 được corroborate lại, không tạo attack class từ benign controls.

R26.1 bổ sung một contrast task có ground truth độc lập với runner intent: **ADMIN đọc record được phép**, và **STUDENT đọc cùng record ngoài quyền**, trên guest disposable `-nic none`, H2/session mới, NGINX/Suricata/Audit thật. Static policy source và class trong JAR khớp SHA R8 đã kiểm. Oracle nối principal response/JDBC role, actor/session HMAC trong Audit, owner trước/sau, target request key và application marker/denial. Cookie/token/password không xuất vào receipt.

Lần đầu gửi8requests, dừng đúng ở STUDENT login401. Root cause: transport lab cũ luôn dùng username `labu1`, dù đã chọn password STUDENT. Còn hai lỗi tooling: helper stage chỉ copy khi file chưa tồn tại nên giữ Oracle legacy, và verifier import kéo nhầm module `run` của pipeline khác. Đã sửa account routing, explicit owned-guest replacement+SHA verification, tách URI100 reference khỏi legacy training imports, thêm regression. Không sửa Student/Security Web production, không hạ BCrypt/session/CSRF.

Đối soát offline8receipts đầu thành BLOCKED, giữ nguyên ledger và proof. Một campaign repair mới được preregister trước boot, tối đa12requests, guest/H2/session mới; không gửi lại dưới ID/campaign cũ. Tổng thực tế **20 HTTP requests** trong hai campaign, không che lần lỗi.

| Repair campaign | Kết quả |
| --- | --- |
| HTTP / application Oracle | **12/12** |
| URI76/Rust legacy parity | **12/12** |
| URI100 projection thật trước cutoff, Python parity | **12/12**, 4 vectors |
| Native masks tại cutoff1000ms, guard1ms | **11 NSA, 1 NONE** |
| Authorized record-read witnesses | **3 BENIGN_VERIFIED** |
| Outside-privilege record-read witnesses | **3 ATTACK_VERIFIED**, outcome failed |
| Adapter / QEMU / guest cleanup | **COMPLETED, exit0 / PASS** |
| Native TRAIN/DEV/CAL/TEST | **0/0/0/0** |

`ATTACK_VERIFIED` ở đây có task **AUTHORIZATION_POLICY_VIOLATION_ATTEMPT**, provenance machine policy/Oracle theo quyền R26.1. Không đồng nghĩa malicious payload hoặc independent-human review; không fabricate human attestation, không gộp với WAF publisher anomaly. Các ground-truth Oracle proof hoàn tất sau response được giữ **GROUND_TRUTH_ONLY**, không dùng làm request-time input.

URI100 được chiếu ngay trong trusted NGINX mirror, thêm R23 shape24 trước timestamp availability. Receipt giữ vector SHA, code SHA, request key và clock/receipt offsets. Cả ba cặp cùng method/URI có vector bằng nhau giữa hai role; sáu task witnesses nằm trong **2 mixed URI100 vectors**. Một scorer chỉ nhìn URI100 không thể biết quyền thay đổi khi input không đổi. Không chạy native pilot bằng random-row split trong một guest, không train để ép model ghi nhớ role mà feature không quan sát.

Request NONE và evidence muộn giữ đúng trạng thái; không dịch cutoff hoặc bổ sung nguồn giả. Task này chưa đạt independent lineage/support T07. **Canonical TRAIN vẫn0**. [Old evidence audit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/native-evidence.json) · [Repair plan](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/native-recovery-plan.json) · [12-request summary và proofs](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/native-live-v2/summary.json)

## Runtime, reliability và lỗi đã sửa

- B raw-target Rust/Python: **1.391 inputs ×3 fresh processes**, max feature/score error **0**; 1.368 scored và23 decoded-Unicode ABSTAIN mỗi process. ASCII scope giữ nguyên, 6 malformed cases ABSTAIN và recovery PASS; wrongSHA bị từ chối. Restart scores bit-exact. Preprocess p50/p95 **0,284/0,525ms**, inference **0,375/0,421ms**, tổng **0,659/0,936ms**; cold load **131,70/45,94/50,81ms**. Đây là bounded offline replay, không phải T07 load benchmark.
- Staging từng dùng symlink ONNX, Rust từ chối đúng. Sửa bằng regular verified copy, không nới validator. Một lỗi missing import của harness được sửa và regression stage PASS. Combined verifier/compiler chạm pids16, Adapter terminal-stop và cleanup đúng. Tách compiler thành worker một thread/affinity1CPU, giữ pids16; **2 Rust unit tests PASS**. Không auto-resume safety attempt hoặc tăng limit để tạo PASS. Final composite verify PASS.
- RI v2/R20 Local private-UDS liveness PASS; một first-use RI probe **537,06ms**, năm warm probes p50/p95 **8,13/9,00ms**. R20 live/Python error0, invalid schema ABSTAIN rồi valid recovery PASS. Những message này là synthetic protocol fixtures, **không phải HTTP/native samples** và không inject vào mirror dataset. Controlled restart/rollback R22.1 được tái sử dụng vì serving code không đổi; không chủ động restart service đang phục vụ.
- **157 Python regression PASS**, Ruff PASS; boundary/scale/thread/Oracle/account-routing/staging được test. Numerical driver execution bytes được giữ trước formatting, AST-equivalence xác nhận không đổi training/calibration/evaluation logic. Không sửa tolerance hay metric để PASS.
- **17 Adapter attempts** có cleanup receipt, gồm failed tooling/native lần đầu và task-limit stop. Worker/guardian cgroups vắng mặt khi readback; guest/kernel/initramfs/socket tạm được cleanup. Absence sau boot bổ sung không được dùng để thay receipt cleanup đã ghi trước reboot. Các transient jobs đã kết thúc; không tạo job chờ dữ liệu hoặc training vô ích.

[Technical verification](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/verification.json) · [Live liveness](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/local-acceptance.json) · [Tests](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/final-tests.xml)

## Artifact, Git và final readiness

[Research bundle](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r261-recovery-drliluc_/research-bundle/manifest.json) có ONNX, schema, calibrator, threshold bytes, checkpoint provenance và rollback scope. R26.1 không tạo official release hoặc cutover. Model/checkpoint/private logs vẫn ở artifact store Local, không push chúng lên GitHub. Không claim clean-checkout release installation khi quality/independence gates chưa đạt.

34 tracked dirty files có sẵn giữ nguyên SHA; original R26 artifact hashes khớp. Adapter vốn là source untracked trong checkout được đưa vào commit cùng phần sửa trực tiếp R26.1; không stage các thay đổi không liên quan. Không rewrite history hoặc force push. Commit chức năng: **`824f03d`** resource integration, **`b3c5ecb`** checkpoint/quality/runtime, **`48cf9cd`** native ground truth; report/finalizer/evidence commit riêng. [Evidence bàn giao có SHA](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-recovery-r261/r261-evidence.json)

| Gate | Kết luận |
| --- | --- |
| Sensor/Local health trong cửa sổ kiểm | PASS; kernel ACPI recurrence chưa được chữa |
| Resource allocation, real threads, kernel quota và thermal boundaries | PASS scoped; boundary temperatures là fixture |
| B checkpoint, one continuation, exact epoch replay | PASS; best16, stop21 |
| Matched research quality gain / ONNX / raw Rust / ABSTAIN | PASS scoped |
| First-party native security-task witnesses | PASS **3 benign +3 attack**, một repair campaign |
| Recall≥90%, per-source FPR≤1%, Notes CAL recall | **BLOCKED** |
| Native independent TRAIN/DEV/CAL/TEST và Hybrid promotion | **BLOCKED** |
| FINAL / RELEASE_READY | **NO** |

**Bước ngắn nhất tiếp theo:** xây projection authorization/session context có proof thật trước cutoff cho task đã chứng minh, đối chiếu với URI-only và deterministic policy control, rồi thu cohort lineage độc lập. Role/Oracle đến muộn vẫn chỉ làm ground truth. Không train lại URI100 hoặc tăng tham số trên cùng dataset để xử lý một cặp có input giống hệt nhưng quyền khác nhau. Với payload-anomaly task, vẫn cần nguồn/profile độc lập có đủ POST/OTHER và kiểm threshold transfer, không dùng PKDD stress/Notes TEST đã exposed để tuning.
