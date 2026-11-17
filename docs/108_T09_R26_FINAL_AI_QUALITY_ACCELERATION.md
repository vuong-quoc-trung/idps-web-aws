# T09 R26 — Final AI Quality Acceleration

**Đã hoàn thành một ứng viên nghiên cứu SwiGLU URI100, 400.256 tham số, huấn luyện từ 401.745 original publisher requests. Chưa đạt mục tiêu recall ≥90% tại FPR ≤1% hoặc điều kiện promotion T07.** Trên cohort publisher mới được khóa trước scoring: recall **84,09%**, FPR **0/227**, precision **100%**, AP **0,94527**. Đây là nhãn synthetic publisher, không phải native ATTACK_VERIFIED.

Một lượt bổ sung ba nguồn đã commit đến epoch **16**, step **400**, rồi bị guardian watchdog dừng. Cleanup PASS; không tự resume. Probe chỉ đọc sau đó xác định `/sys/class/thermal/thermal_zone0/temp` không trả về trong ngân sách 5 giây. **RI và shadow service Local hiện cũng FAILED do watchdog**, collector và receiver còn active. Không bỏ qua cảm biến để phục hồi service hoặc tiếp tục training.

Run **`t09-r26-acceleration-zfyPqyt3`**, nhánh **`feature/ai-idps-shadow-integration`**, bắt đầu `2026-11-17T10:05:35Z`, ngân sách tối đa đến `22:05:35Z`. Các phase chạy độc lập qua systemd; không còn job R26 đang chạy. Dừng compute sớm do lỗi an toàn host, giữ đầy đủ kết quả đã hoàn tất. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/acceptance.json) · [SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/artifact-index.json) · [Nguồn và entry points](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-acceleration-r26/README.md)

## Hai hướng feature và nguyên nhân bỏ sót

Giữ URI76/URI100 và checkpoint cũ. Chỉ thử **hai** hướng feature mới: URI164 thêm 64 bins của ngữ cảnh token hữu hạn; HTTP244 bổ sung 64 bins body và 16 chỉ báo header/availability. Không học vocabulary từ corpus, không lưu literal URI/body/header values trong derivative, không dùng response, status, nhãn, identity hoặc future evidence làm feature. Body có secret-key bị withheld; header chỉ giữ tên đã whitelist, không giữ giá trị. Missing, observed-empty và withheld khác nhau. Nội dung chỉ được dùng khi thực sự quan sát trước cutoff; publisher serialized content không tự chứng minh native availability.

| Representation trên cùng WAF FIT 400K | Unique vectors | Mixed-label vectors | Minority originals trong mixed vectors |
| --- | ---: | ---: | ---: |
| URI100 control | 17.164 | 406 | 12.374 |
| URI164 A | 17.566 | 402 | 12.355 |
| HTTP244 B | 18.099 | 385 | 12.324 |

Hướng tốt nhất về capacity chỉ tăng **5,45%** số vector, giảm minority mass **50/12.374**. HTTP244 tách gần hết mixed groups của TUNING, nhưng phần FIT còn mơ hồ rất lớn. Không nhầm phép tra cứu nhãn hồi cứu với khả năng học/tổng quát hóa. Pilot lấy 12.456 WAF originals có bảo toàn loss mass của parent và 1.745 originals nguồn mới; kiểm các profile URI_ONLY/content, method-only và availability-only.

| Arm pilot 4 epoch | Macro source recall | Macro vector recall | Macro AP |
| --- | ---: | ---: | ---: |
| R25 frozen, cùng global dual-FPR protocol | 11,90% | 18,43% | 0,74642 |
| Logistic URI100 | 50,54% | 61,63% | 0,90318 |
| Logistic URI164 | 49,27% | 62,89% | 0,87626 |
| Logistic HTTP244, URI-only profile | 42,69% | 55,55% | 0,87107 |
| **SwiGLU URI100** | **57,39%** | **70,18%** | 0,92589 |
| SwiGLU URI164 | 54,67% | 66,21% | 0,92710 |
| SwiGLU HTTP244, URI-only profile | 56,22% | 68,19% | 0,93443 |

Cùng một global strict `>` threshold, tối đa FPR 1% cho từng nguồn theo cả original-request và vector-balanced. Method-only recall khoảng 1,04%, availability-only 0% ở chính protocol đó; không coi đây là bằng chứng loại bỏ mọi shortcut. **Hai schema mở rộng không được chọn**. Full training dùng URI100 và data recovery/source balance. Pilot có auxiliary views giữ chung identity/role và chia loss mass, không tăng original count. [Census](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/data-v2/waf-manifest.json) · [Pilot](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/pilot.json)

Sau khi model/ngưỡng đã khóa, chẩn đoán cohort Notes CAL_OP cho thấy ceiling URI100 tại FPR 0,5% chỉ **53/64 = 82,81% recall**; muốn 90% cần ít nhất 3/374 FP = 0,802%. Model thực tế chỉ đạt 19/64 tại ngưỡng CAL. Vì vậy tồn tại cả **collision** lẫn **ranking/threshold transfer**. Trên research holdout, 7 FN có 1 trường hợp chia URI100 với normal; cả 7 có body observed-empty. Không có bằng chứng rằng mở body rộng hơn sẽ xử lý sáu FN còn lại. Chẩn đoán sau TEST không được dùng để sửa model/ngưỡng R26A. [Replay và thông tin phân biệt](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/verification.json)

## Nguồn mới, permission và role

Nguồn mới **notesbymuneeb/ai-waf-dataset** công bố MIT và dữ liệu synthetic phục vụ huấn luyện. Pin revision `1b4d732b3c227fe2345240cbb7e6c30e936ed81b`; tải đúng một file TRAIN, 1.637.726 bytes, SHA `78a2aca0816824b42cfc1083d863427d10577087ac0283186c366cadbf1e6fcf`. Giữ task synthetic publisher `benign/malicious`, không nâng thành native ground truth. [Dataset card chính thức đã pin](https://huggingface.co/datasets/notesbymuneeb/ai-waf-dataset/blob/1b4d732b3c227fe2345240cbb7e6c30e936ed81b/README.md)

11.949 raw records → 11.769 parse/project được; 180 malformed/unsupported, 3 exact duplicates, 8.814 bị quarantine do closure chạm role bảo vệ; **2.952** original còn lại. Closure nối coarse URI76 và symbolic URI template, giữ cả record bị loại làm bridge. Hash component với seed 2601, không tìm seed theo score. Không có exact canonical request overlap cross-publisher sau đối soát HMAC; điều này không chứng minh physical request hoặc campaign độc lập.

| Nguồn/role dùng cho R26A | Original requests | Normal / anomalous | Nhóm lineage |
| --- | ---: | ---: | ---: |
| WAF FIT đã khóa | 400.000 | 367.471 / 32.529 | Giữ manifest R19 |
| WAF TUNING đã exposed | 6.042 | 2.385 / 3.657 | Giữ manifest R19 |
| Notes FIT | 1.745 | 1.300 / 445 | 720 |
| Notes TUNING | 274 | 218 / 56 | 116 |
| Notes CAL_FIT | 224 | 159 / 65 | 104 |
| Notes CAL_OP | 438 | 374 / 64 | 92 |
| Notes RESEARCH_TEST | 271 | 227 / 44 | 107 |

WAF chỉ dùng publisher TRAIN và coordinates FIT/TUNING đã được phép. Không đọc publisher eval/test/heldout, không lấy SR-BH DEV/CAL/TEST để train. Notes là nguồn mới ngoài WAF/SR-BH nhưng không có native clock/receipt/Oracle hoặc campaign metadata đủ chứng minh independence T07. Các role CAL/TEST trên đây là **research publisher**, không phải native final acceptance. Chuẩn hóa newline trong serialized parser là giới hạn của hypothesis body chưa được chọn; selected URI100 chỉ đọc method/target.

ModSec-learn chỉ kiểm metadata, chưa có explicit training license nên không fit. BiblioUS17 tiếp tục hạn chế quyền/access; WebRequests TF-IDF giữ ngoài fitting do vocabulary trên toàn corpus và lineage/license đã ghi ở R25. Không lặp download hoặc nới source role. [Source ledger](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/source-ledger.json) · [Intake manifest](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/notes/manifest.json) · [Cross-source identity audit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/cross-source-overlap.json)

## Training, selection và calibration R26A

SwiGLU URI100 width 204, **400.256 parameters**, warm R25 best step 81, reset Adam. Seed 2601; AdamW peak LR 0,0003, warmup 5 step, cosine floor 0,1; dropout 0,15, weight decay 0,001, smoothing 0,005, tối đa 24 epoch, patience 5, batch 2.048 label cells. Giữ cả hai publisher labels trong mixed vectors. Group mass `min(8,sqrt(n))`, class-balanced trong từng source, equal source mass; không majority relabel.

**401.745 distinct publisher originals**, **18.714 unique URI100**, Kish original effective weight khoảng **4.913,82**. 400K original contributions không tương đương 400K độc lập hoặc 400K vectors. WAF riêng còn 270.185 originals nằm trong mixed groups. Việc bổ sung synthetic source nhỏ và cân bằng nguồn làm giảm effective original weight; đây là giới hạn quan trọng.

Chọn epoch **11**, step **110**, dừng early stopping epoch **16**, step **160**, 36,51 giây compute training. Chọn trên TUNING trước CAL/TEST. Tại global TUNING dual-cut, WAF recall **46,08%**, FPR **0,461%**; Notes recall **82,14%**, FPR 0%. Đây là exposed TUNING, không phải independent score.

Fit positive-slope Platt bằng Notes CAL_FIT, chọn một global float32 strict `>` threshold bằng CAL_OP, cap FPR 0,5% theo cả request và vector. Lock hash model, calibrator, metric code, role files và threshold **trước khi load RESEARCH_TEST**. R26A slope **1,43502517**, intercept **−0,83266806**, cutoff **0,8816564083099365**, little-endian bytes **`3cb4613f`**. CAL_OP recall **29,69%**, FP **1/374**, không đạt T07 recall ≥80%. Không thay cutoff để tạo PASS. [Training plan](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/training-plan.json) · [Selection](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/model-selection.json) · [Evaluation lock](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/evaluation-lock.json)

| Model trên cùng Notes research holdout, CAL protocol đã khóa | Recall | FPR | Precision | AP | Brier | ECE 10 bins |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R20, research recalibration | 0% | 0% | Không có positive prediction | 0,46107 | 0,12920 | 0,14584 |
| R25, research recalibration | 0% | 0% | Không có positive prediction | 0,45602 | 0,12251 | 0,14021 |
| R26 logistic URI100 | 81,82% | 0,881% | 94,74% | 0,92240 | 0,03482 | 0,03240 |
| **R26A SwiGLU URI100** | **84,09%** | **0%** | **100%** | **0,94527** | **0,01800** | **0,01530** |

R26A confusion **TN/FP/FN/TP = 227/0/7/37**. Vector-balanced recall **85,65%**, AP **0,95141**, FPR 0%. Research holdout GET có 210 normal/44 malicious; POST chỉ 4 normal/0 malicious, OTHER 13 normal/0 malicious. **Không đủ support để claim POST detection**. Source/method tables đầy đủ nằm trong evaluation/transfer artifacts. Chỉ có 74 benign template anchors; 0 FP cho upper one-sided 95% khoảng **3,97%**, chưa đạt confidence gate 1%. Template anchors synthetic chưa phải independent native exposure units.

R20/R25 trong bảng dùng calibrator/ngưỡng research mới, **không phải threshold phục vụ lịch sử**. Các model cũ có score saturation và ngưỡng cap khiến không alert trong protocol mới; không lấy FPR 0 để tuyên bố chúng an toàn hoặc kết luận superiority vận hành. R20 lịch sử recall 61,91%/FPR 0,964% thuộc cohort và operating point khác. Logistic R13 AP 0,8874 tiếp tục là baseline benchmark cũ, không so trực tiếp với AP trên nguồn Notes. RI v2 và Rule-only/Hybrid không có common-request inputs/rule evidence trong corpus publisher này, nên **BLOCKED paired comparison**, không giả lập 3 nguồn. [Evaluation](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/evaluation.json)

## Generalization và lượt data recovery B

Khóa ngưỡng từ CAL trước khi chấm stress. R26A trên CSIC normalTraining: FPR **10/36.000 = 0,0278%**. Trên PKDD Valid TRAIN projectable: FPR **17,81%**, vẫn không chấp nhận được. Chỉ dùng các file TRAIN benign đã được phép làm stress, không fit và không mở evaluation files. Source role và label publisher giữ nguyên.

SR-BH: tái dựng đúng **58.241** original representatives thuộc R13 FIT đã được phép bằng HMAC coordinates; loại 3.599 chạm coarse/template của WAF/Notes roles và 17 unsupported. Còn **54.625**, 7.723 normal/46.902 CAPEC-labeled. Frozen R26A recall **76,48%**, FPR **2,77%**, AP **0,99112**. Ranking cao nhưng global threshold không transfer được. Đây là diagnostic trên nguồn FIT cũ; không tuyên bố pristine independent TEST. [Transfer, từng method và label scope](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/transfer.json)

Vì transfer của nguồn **vốn có quyền FIT** vượt FPR 1%, thực hiện một lượt recovery URI100 không thêm feature/hyperparameter search. Giữ source role toàn cục R13 FIT; không lấy historical DEV/CAL/TEST. Group closure mới, seed 2602 cố định 60/10/10/10/10. Nguồn FIT này đã exposed aggregate trước khi chia research subroles, nên holdout mới **không phải pristine final evaluation**.

| SR-BH research subrole | Originals | Normal / anomalous | Nhóm |
| --- | ---: | ---: | ---: |
| FIT | 31.516 | 4.617 / 26.899 | 2.305 |
| TUNING | 4.766 | 676 / 4.090 | 392 |
| CAL_FIT | 11.130 | 730 / 10.400 | 428 |
| CAL_OP | 3.463 | 617 / 2.846 | 368 |
| RESEARCH_TEST | 3.750 | 1.083 / 2.667 | 386 |

Pilot ba nguồn tăng matched TUNING macro recall **24,80% → 65,80%**, không giảm hai source cũ vượt 2 điểm; đủ điều kiện full training trên **433.261 originals**. Đã commit epoch 16/step400, best epoch16, TUNING macro recall **77,54%**, vector recall **89,60%**. Từng source tại cut đó: WAF recall 54,33%/FPR 0,461%; Notes recall 89,29%/FPR 0%; SR-BH recall 89,00%/FPR 0%. Đây chỉ là TUNING; WAF AP giảm còn 0,89007, nên chưa thể chọn làm model tốt nhất tổng quát.

Guardian watchdog dừng B trước early stopping/export/final evaluation. **Không có ONNX hoặc holdout metrics B**, không tự resume. Checkpoint best/latest/previous digest vẫn khớp arrays/state. Không dùng lại Notes RESEARCH_TEST để chọn B. Giữ driver evaluation đã chuẩn bị nhưng chưa thực thi. [Recovery protocol](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/source2-recovery/protocol.json) · [Pilot](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/source2-recovery/pilot.json) · [Terminal status](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/augmentation-b/status.json)

## ONNX, Rust và recovery

- NumPy/ONNX max absolute error **1,1921e−7**. Raw ONNX SHA **`0183cd4e3b14d7ff4868d66e1056477cec07a8f420498b696ee37a6f2c6ef107`**; calibrated SHA **`67814a37f3a7de586a0d64a2085aee252153e77e840118472ecc7e271fbff69e`**. Best checkpoint manifest SHA **`007ece541ca5d1d3fd81df0a5d112b5ef5daa8559c0c619aaf1cd7bc0a74135f`**.
- **Raw-target Rust preprocessing đã được thực thi**, mở rộng phạm vi so với R25 tensor replay. 1.391 inputs gồm 167 synthetic fixtures và 1.224 TUNING/CAL cases; ba fresh workers. Mỗi worker score 1.368, ABSTAIN 23 decoded-Unicode cases. Python/Rust feature và score max error **0**, quyết định strict threshold giống nhau. Scope đã kiểm là raw và three-round decoded **ASCII**; Unicode/invalid envelope không được giả chiếu thành vector.
- Rust preprocessing p50/p95 **0,147/0,326 ms**, inference **0,189/0,251 ms**, tổng **0,337/0,606 ms**; cold model load **33,27 / 26,18 / 31,35 ms**. Đây là bounded offline batch-1 replay, không phải ba cửa sổ throughput 300 giây hoặc end-to-end queue acceptance T07.
- Restart ba tiến trình score bit-exact; 6 malformed frames ABSTAIN, frame hợp lệ tiếp theo phục hồi; wrong SHA bị từ chối. Scorer riêng không có đường Hybrid/enforcement. Không đổi service mặc định. **0 request HTTP nghiệp vụ/capture mới**, chưa chạy candidate HTTP shadow/Hybrid vì quality gate và host safety chưa đạt.
- A replay epoch **15 → 16** ở worker mới, parameters/Adam m,v/permutation/loss bit-exact, global step160. Không claim mid-batch resume. ETL chunks rebuild exact, không thiếu hoặc đếm lại original. B chỉ xác minh committed checkpoint digests, chưa xác minh continuation qua terminal stop.

[Model manifest](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/model-manifest.json) · [Feature ABI](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/feature-schema.json) · [Runtime evidence](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/runtime.json)

## Lỗi đã sửa và safety thực tế

Sửa header parser để giá trị JSON header không giả tên header khác; recompute derivative vào `data-v2`, giữ v1. Sửa ONNX calibration namespace để graph đã calibrated không trùng SSA tên và giữ mọi public output. Hai lỗi export trước TEST được lưu; chỉ mở TEST sau graph/lock hợp lệ. Sửa parity raw Rust cho PII screening trên raw query value và tập ASCII whitespace của Python. Thất bại parity ordinal được giữ; final worker cùng raw cases PASS. Không sửa model/ngưỡng bằng TEST hoặc nới tolerance. **14 Python regression PASS**, Ruff PASS. Rust unit fixture ban đầu PASS; extra unit test cuối chưa chạy lại do host sensor lỗi, còn final Rust executable/raw parity đã build và chạy thành công trước sự cố. [JUnit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/regression.xml)

19 Resource Adapter attempts đều cleanup verified và **cgroup/PID worker/guardian vắng mặt khi readback cuối**. Worker limits **1 CPU/4 GiB/16 tasks**, kernel `cpu.max=100000 100000`, `memory.max=4294967296`, swap0, invocation/ownership/start barrier giữ nguyên. Guardian 25% CPU/256 MiB/32 tasks, watchdog 3 giây, policy 90/100 °C và hardware alarms không đổi. B admission 57°C; sample cuối 84°C, NORMAL. Không có bằng chứng terminal thermal >100°C trong result B; lý do chính xác là **GUARDIAN_EXIT_WITHOUT_RESULT / service result watchdog**.

Kernel cùng thời điểm ghi ACPI EC workqueue hog/stalls. Probe một lần chỉ đọc, CPUQuota10%, memory128MiB, RuntimeMax5s, đã đọc qua coretemp rồi kẹt ở thermal_zone0/temp (`acpitz`). SIGKILL bị kernel read trì hoãn; journal ban đầu ghi process còn tồn tại sau stop, **readback sau xác nhận PID35457 và cgroup đều biến mất**. Không tuyên bố timeout có thể hủy đồng bộ một sysfs read kẹt trong kernel. Probe chứng minh path kẹt sau sự cố; không có stack của guardian lúc chết để khẳng định tuyệt đối cùng wait site. Không thay kernel, ACPI, AppArmor, firewall hoặc threshold để vượt qua.

Tại bàn giao: collector **PID3521 active**, receiver **PID3524 active**, RI/scorer **MainPID0, failed/watchdog, NRestarts4**. Systemd tự thử lại theo policy cũ rồi chạm start limit; R26 không thêm vòng retry. Các service files/model artifacts/serving code không đổi. **Không thể ghi Local continuity PASS** trong tình trạng này. Linger **yes**, nhưng không còn job để chạy qua logout. [Resource acceptance/readback](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/resource-acceptance.json) · [Hardware diagnosis và journals](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r26-acceleration-zfyPqyt3/host-safety/diagnosis.json)

## Acceptance và bước tiếp theo

| Gate | Kết quả |
| --- | --- |
| New-source provenance, role fences, publisher labels | PASS research; chưa chứng minh native/campaign independence |
| Hai feature pilots, capacity và shortcut controls | PASS; giữ URI100 |
| ≥400K original training, best checkpoint, epoch exact replay | PASS R26A |
| CAL/TEST lock, Python/ONNX/raw Rust parity, restart/ABSTAIN | PASS scoped research |
| Recall ≥90%, FPR ≤1% và generalization | **BLOCKED**: Notes84,09%; SR-BH FPR2,77%; PKDD17,81% |
| T07 CAL recall, POST/support, adjusted false-alert bound | **BLOCKED / insufficient support** |
| Native TRAIN/DEV/CAL/TEST, all-mask/Hybrid common-request | **BLOCKED, 0/0/0/0** |
| Recovery training B, Local service continuity | **BLOCKED host sensor/watchdog** |
| R26 process/cgroup/probe cleanup | PASS readback |
| FINAL / RELEASE_READY / promotion | **BLOCKED** |

**Chọn R26A làm ứng viên nghiên cứu đã hoàn tất tốt nhất trên cohort Notes mới; không chọn model thay RI v2/R20.** B chỉ là checkpoint nghiên cứu chưa nghiệm thu. Không coi AP cao hoặc FPR0 trên 227 benign là bằng chứng production. Các artifact, schema, preprocessing, threshold, source roles và SHA đã xuất; giữ mọi dataset/checkpoint/evidence lịch sử và 34 tracked dirty files có sẵn.

**Một nhiệm vụ tiếp theo:** khôi phục bounded ACPI sensor reads và RI/scorer bằng nguyên policy, review terminal event, rồi nghiệm thu checkpoint ba nguồn đã commit trước khi quyết định tiếp tục training. Không cần capture/preflight mới để tái chứng minh các parity/ETL đã PASS. B chỉ được tiếp tục qua fresh owned attempt sau safety review; giữ Notes TEST cũ exposed và cần cohort chưa dùng cho quyết định promotion cuối.

Các commit chức năng là **`53ccaa3`** (data/features), **`680a10f`** (training/evaluation), **`9b38884`** (Rust preprocessing/runtime). Report/finalizer và [evidence bàn giao có SHA](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-acceleration-r26/r26-evidence.json) được commit riêng; chỉ stage các file mới của R26 trên nhánh hiện tại.
