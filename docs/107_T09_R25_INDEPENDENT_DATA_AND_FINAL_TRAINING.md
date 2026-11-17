# T09 R25 — Independent Data Recovery & Final Model Training

**Đã hoàn thành lượt training nghiên cứu trên 400.000 original request, với SwiGLU URI100 có 400.256 tham số. Chưa đạt chất lượng final/release.** URI100 R25 tăng recall chuyển ngưỡng trên WAF, nhưng false positive tăng trên nguồn benign ngoài WAF. Giữ RI v2 phục vụ Hybrid và R20 shadow. Native TRAIN/DEV vẫn **0/0**. Không kích hoạt model mới hoặc tạo job chờ dữ liệu.

Run ID **`t09-r25-quality-EsMMItaJ`**, ngày 2026-11-17, nhánh `feature/ai-idps-shadow-integration`. [Acceptance và SHA](/home/trung/projects/idps-web-aws/ai-training/contracts/development-bulk-v1/r25-evidence.json) · [Evidence chi tiết](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/acceptance.json)

## Nguyên nhân recall thấp được kiểm chứng

Component **2780** chứa **1.641 normal, 378 anomalous**, toàn bộ là GET, với **7 method/target phân biệt**, không có body. URI76 gộp thành 5 vector, trong đó một vector chung chứa toàn bộ 1.641 normal và **352 anomalous**. Với quyết định chỉ dựa vào URI76, empirical ceiling của component ở FPR 1% là **26/378 = 6,88% recall**. Muốn bắt 90% phải đánh dấu cả vector mixed, gây FPR 100% trong component.

URI100 tách thành **7 vector thuần nhãn**, empirical ceiling đạt 100% recall tại 0 FP. Đây là phép tra cứu hồi cứu nhãn để chẩn đoán capacity. Model URI100 cũng xếp hạng đúng trong component, AP **1,0**, nhưng điểm anomalous thấp hơn ngưỡng ước lượng từ các component khác. Ví dụ URI100 R25 có normal **0,06635**, anomalous khoảng **0,06692–0,49554**. Vì vậy, sau URI100, nút thắt này thuộc **threshold transfer và distribution shift**. Monotone calibration không tạo thêm thông tin phân biệt cho các điểm bằng nhau. [Census, body và method](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/diagnosis.json) · [Score theo component](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/acceptance.json)

Ablation thêm **32 chỉ báo lexical hữu hạn**, sau privacy filtering, chỉ tăng FIT từ **17.164 lên 17.338 vector**, khoảng **1,01%**. Minority mass trong mixed vectors giảm **12.374 → 12.373**. Cả hai lớp của component 2780 có cùng bộ chỉ báo, chỉ bật script extension. Không có bằng chứng để mở rộng full neural training sang URI132. Không dùng literal hashes, learned vocabulary, identity, headers, body hoặc response outcome làm feature. [Schema thử nghiệm](/home/trung/projects/idps-web-aws/ai-training/contracts/development-bulk-v1/r25_features.py) · [Dataset manifest](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/dataset-manifest.json)

## Nguồn dữ liệu và vai trò

WebRequests là bản ghép Malicious-URLs, PKDD và CSIC, có giấy phép repository CC BY 4.0. Publisher cho biết vocabulary TF-IDF được chọn trên toàn corpus. Vì vậy các CSV unigram được giữ ngoài fitting và independent evaluation. Các file query-only không được tự gán method GET. Giới hạn original-license lineage của CSIC trong registry cũ vẫn giữ nguyên. [Nguồn chính thức WebRequests](https://redata.anii.org.uy/dataset.xhtml?persistentId=doi:10.60895/redata/RWUUSV)

| Nguồn được xử lý | Đơn vị quan sát | URI100 vectors | Vai trò R25 |
| --- | ---: | ---: | --- |
| WAF publisher TRAIN, FIT đã khóa | 400.000 distinct original identities | 17.164 | Supervised development, nhãn `normal/anomalous` |
| WAF TUNING đã exposed | 6.042 original | Theo manifest R24 | Chọn checkpoint và so sánh development |
| CSIC normalTraining | 36.000 transcript records; 9.644 exact request identity digests | 2.743 | Benign source-disjoint stress, không fitting |
| PKDD `xml_train.txt` | 24.504 records; 24.070 projectable | 23.428 | Publisher Valid stress, không fitting |

**434 PKDD records unsupported**, score coverage trên toàn file là **98,23%**. Các FPR PKDD dưới đây tính trên 24.070 records có thể chiếu. Không biến unsupported thành benign. PKDD record ID chưa chứng minh physical request identity. CSIC có nhiều bản ghi trùng, vì vậy báo cả FPR theo record và cân bằng vector. Hai nguồn này tách khỏi WAF về nguồn sinh, nhưng chưa phải fresh dual-class acceptance. Vai trò TEST của CSIC/PKDD giữ nguyên, không mở lại. Không thêm mẫu vào canonical TRAIN từ các stress corpus. [Source ledger, SHA và phạm vi quyền](/home/trung/projects/idps-web-aws/ai-training/contracts/development-bulk-v1/r25-sources.json)

## Training và so sánh model

FIT giữ **367.471 normal / 32.529 anomalous** và các fences exact/coarse/template/component R19. Giữ nguyên cả hai nhãn trong vector mixed. Loss mass của parent URI76 được bảo toàn chính xác sau khi thêm feature, đã reconcile về R24. Không majority relabel hoặc nhân bản request. 400.000 là original publisher examples đóng góp vào loss; không phải 400.000 physical captures hoặc independent vectors. Kish effective original weight count theo weighting kế thừa khoảng **8.214**. R19 đã quarantine 10 exact originals xung đột.

Full URI100 warm-start từ R19 step 55, zero thêm input rows và reset Adam. Cấu hình khóa trước training gồm seed **2401**, width **204**, AdamW, peak LR **0,00015**, warmup **5/108 step**, cosine min ratio **0,1**, dropout **0,15**, weight decay **0,001**, smoothing **0,005**, batch tối đa **2.048 label cells**, tối đa **12 epoch**, patience **3**. Chọn theo transferred TUNING recall trong 5 component folds, rồi AP, giữ checkpoint sớm khi hòa. Epoch **9**, step **81** được chọn; kết thúc tại epoch **12**, step **108**. [Training plan](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/training-plan.json)

Tất cả kết quả sau dùng cùng WAF TUNING đã exposed, **2.385 normal / 3.657 anomalous**. Cột ngân sách cho phép tối đa 23 FP, giữ strict `>` và ties. FP thực khác nhau được ghi rõ. OOF là chuyển ngưỡng giữa các component TUNING, không phải model OOF hoặc independent TEST.

| Arm | AP | Recall tại ≤23 FP | FP thực | Recall chuyển ngưỡng | FPR request OOF | FPR vector OOF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R20 isotonic | 0,9442 | 47,91% | 23 | 30,38% | 0,126% | 0,796% |
| R24 URI100 | 0,9757 | 47,03% | 18 | 36,42% | 0,503% | 1,095% |
| HGB URI76 | 0,9392 | 80,12% | 22 | 50,51% | 0,503% | 1,138% |
| HGB URI100 | 0,9921 | 59,91% | 23 | 53,38% | 0,545% | 1,350% |
| HGB URI132 | 0,9934 | 59,31% | 21 | 55,89% | 0,545% | 1,350% |
| Logistic URI132 | 0,9459 | 44,65% | 23 | 34,51% | 0,545% | 1,350% |
| **Full SwiGLU URI100 R25** | **0,9817** | **48,15%** | **23** | **44,11%** | **0,545%** | **1,350%** |

HGB là HistGradientBoostingClassifier, **150 iterations, tối đa 15 leaves/tree, LR 0,05, L2 1**, không early stopping bằng random row split. Đây là kiến trúc đối chứng CPU. HGB URI132 được chọn làm **development diagnostic** trước khi mở stress scores ngoài WAF. Thay đổi representation cũng thay đổi số unique training cells và histogram bins; ablation giữ đúng tổng weighted loss mass. Không suy ra cải thiện universal từ AP.

Tại **dual cutoff khóa trên toàn TUNING**, URI100 R25 có recall **41,70%**, precision **99,80%**, request FPR **0,126%**, vector FPR **0,7665%**, confusion **TN/FP/FN/TP = 2.382/3/2.132/1.525**, Brier **0,17452**, ECE **0,19957**, score coverage **100%** trên roster projectable. GET recall **52,30%**, POST **11,09%**, OTHER **76,92%**. POST chỉ có **22 normal**, chưa đủ để chứng minh FPR vận hành 1%. HGB URI132 có vector OOF recall **90,16%**, nhưng vector FPR **1,350%**, và request recall chỉ **55,89%**. Không đạt mục tiêu 90%/1%. [Metrics, calibration diagnostics, từng method và matched FP budgets](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/acceptance.json)

## Generalization ngoài WAF và quyết định chọn model

Khóa model selection và strict dual cutoff bằng TUNING trước khi chấm các nguồn stress. Không chọn lại threshold từ stress results. Các số dưới đây là **publisher benign FPR theo transcript record projectable**, chưa phải FPR native verified hoặc independent confidence bound.

| Model | CSIC normalTraining FPR | PKDD Valid TRAIN FPR |
| --- | ---: | ---: |
| R20 | 0/36.000 = **0%** | 3.766/24.070 = **15,65%** |
| R24 URI100 | 0% | **14,34%** |
| Full URI100 R25 | 0% | **21,70%** |
| HGB URI76 | **1,42%** | **24,97%** |
| HGB URI100 | **2,78%** | **41,95%** |
| HGB URI132 | **2,78%** | **42,21%** |
| Logistic URI132 | **0,0056%** | **23,14%** |

URI100 R25 trên PKDD GET có **2.842 FP / 19.452**, POST **58/2.294**, OTHER **2.324/2.324**. R20 cũng đánh dấu toàn bộ OTHER của nguồn này. Đây là bằng chứng chuyển profile/method chưa ổn định; không thể chỉ nhìn pooled WAF để kích hoạt model. FPR cân bằng vector của URI100 R25 trên PKDD là **21,53%**. [External metadata, scores, method breakdown và latency](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/verification.json)

**Không chọn model thay thế.** Giữ logistic URI76 R13 AP DEV 0,8874 làm baseline development tham chiếu và RI v2/R20 trong vai trò Local hiện hành. AP R13 thuộc benchmark khác, không so trực tiếp với AP 0,9817 của WAF để tuyên bố R25 tốt hơn. Giữ checkpoint URI100 R25 cho nghiên cứu. Không fit thêm calibrator để che regression trên các nguồn vừa quan sát. ECE 0 của R20 trên TUNING là in-sample của isotonic cũ. CAL_FIT/CAL_OP và TEST độc lập vẫn thiếu.

## Checkpoint, ONNX, Rust và Local

- Best checkpoint manifest SHA **`b96f2d8e686519160261b6305a4b1ce896722cebfe9240bf084d646af654e20b`**, [generation step 81](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/training/uri100/checkpoints/step-000000000081-df8c18dd9879/manifest.json).
- ONNX SHA **`9933a43d1ff7c8eef7667164750d7d7977ab35695d236d996c4980570580c987`**, [artifact URI100](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/swiglu-uri100-r25.onnx). NumPy/ORT parity PASS. Checkpoint selection, Adam state, noise seed, loss và permutation replay **epoch 11 → 12** qua tiến trình mới **bit-exact**. Chưa tuyên bố mid-batch resume.
- Rust standalone load đúng SHA và ABI 100. **256 distinct tensors × 3 fresh processes**, Rust/Python max absolute error **0** và restart scores bit-exact. **5 malformed envelopes** ABSTAIN, frame hợp lệ sau đó được score; wrong SHA/missing model bị từ chối. Warm batch-1 Rust p50/p95 khoảng **0,161/0,396 ms**, model-load của ba tiến trình **54,36/31,57/20,06 ms**. [Runtime evidence](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/runtime.json)
- Phạm vi Rust là **offline tensor replay**. Raw-target URI100 Rust preprocessing và HTTP shadow mới chưa được nghiệm thu. **R25 gửi 0 HTTP request**, không tạo native evidence hoặc fabricated cutoff proof. Không kích hoạt Local HTTP shadow mới khi generalization đã fail. Bốn service R22.1 vẫn active, PID collector **3521**, receiver **3524**, RI **3526**, scorer **3528** tại acceptance. [Model sidecar và điều kiện triển khai](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/model-manifest.json)

## Tài nguyên, regression và phục hồi

**17 tests PASS**, gồm privacy, feature ordering/dtype, protected-source fences, malformed/truncated PKDD records, canonical adapter phase, census và URI100 warm-start. Các nghiệm thu thật bổ sung gồm loss/count reconciliation, epoch replay, NumPy/ORT/Rust parity, ABSTAIN và kernel cleanup. Không chạy lại toàn bộ suite lịch sử không liên quan.

Resource Adapter dùng **1 CPU / 4 GiB / 16 tasks** mỗi phase, kernel readback **`cpu.max=100000 100000`**, `memory.max=4294967296`, guardian và start barrier giữ nguyên. ETL URI132 **85,67 giây**, experiment **32,95 giây**, verifier ngoài nguồn + resume **36,91 giây**. ETL có systemd memory peak **1,1 GiB**, experiment **449,2 MiB**, verifier **487,3 MiB**. Mẫu nhiệt admission **54–62°C**; không đổi policy 90/100°C. [Readback, tiêu thụ systemd và cleanup từng scope](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/acceptance.json)

Hai lỗi thực thi mới đã được ghi lại và xử lý. Supervisor đầu dùng alias `EVAL` ngoài enum Resource Contract; sửa thành `EVALUATE`, thêm regression, tái sử dụng training đã commit. Lần compile Rust đầu chạm `pids.max`, Adapter terminal-stop đúng, cleanup PASS. Giữ nguyên evidence lỗi, không resume attempt safety đã dừng. Sau chẩn đoán, dùng attempt build mới với affinity **1 core**, `CARGO_BUILD_JOBS=1`, `RAYON_NUM_THREADS=1`, `codegen-units=1`, giữ task limit 16. Lần compile tiếp theo phát hiện lỗi chuyển kiểu ORT builder và `u64/usize`; sửa tại scorer cô lập. Build cuối và runtime PASS. Không tăng quota hoặc vô hiệu hóa telemetry. [Supervisor recovery](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/supervisor-recovery.json) · [Build diagnosis](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r25-quality-EsMMItaJ/rust-build-diagnosis.json)

Unit **`t09-r25-quality-EsMMItaJ-supervisor.service`**, PID ban đầu **17776**, đã kết thúc, exit **0**. `Linger=yes`. Không còn workload R25 chạy nền; không cần ETA. **Cả 9 attempt cgroup đã biến mất khi đọc lại kernel**, gồm các lần thất bại; tất cả cleanup flags PASS. Không thay Student Web, Security Web serving code, Hybrid, firewall, VM bền vững, original dataset/model/checkpoint hoặc role của holdout.

## Readiness và bước tiếp theo

| Gate | Kết luận |
| --- | --- |
| 400K original publisher training, loss/count integrity | PASS |
| Epoch checkpoint/resume và ONNX parity | PASS |
| Rust tensor parity, restart, ABSTAIN | PASS |
| Resource limits, giữ service và cleanup | PASS sau các lỗi build đã lưu đầy đủ |
| Fresh independent dual-class evaluation | BLOCKED, chưa có nguồn phù hợp trong role được phép |
| Recall ≥90% tại FPR ≤1%, tổng quát hóa ngoài WAF | BLOCKED |
| Independent calibration, native acceptance | PENDING |
| Raw-target Rust và Local HTTP shadow URI100 mới | PENDING, chưa kích hoạt |
| FINAL / RELEASE_READY / model replacement | **BLOCKED** |

R25 tách đúng **quyền training nghiên cứu publisher** khỏi **điều kiện promotion native**. Không sửa readiness R24 hoặc kết luận lịch sử. Dữ liệu native CAL/TEST không được dùng làm lý do cấm lượt research đã được người dùng ủy quyền. Tuy nhiên chưa có development frame hai lớp mới đủ độc lập để nghiệm thu một final model. [Readiness bổ sung R25](/home/trung/projects/idps-web-aws/ai-training/contracts/development-bulk-v1/r25-evidence.json)

**Đề xuất đúng một nhiệm vụ tiếp theo — R26: intake cohort hai lớp độc lập và calibration theo observation profile.** Ưu tiên raw request được phép sử dụng, actor/policy/Oracle và review rõ ràng cho native; publisher labels giữ task riêng. Khóa lineage, POST/OTHER support, CAL_FIT/CAL_OP và evaluation trước scoring. Dùng các artifact R20/R25 sẵn có để kiểm threshold transfer. Không train lại cùng cohort hoặc tăng tham số trước khi cohort này tạo ra bằng chứng mới.

Các commit chức năng R25 là **`c46a330`** (source/capacity), **`f713c15`** (training/evaluation/recovery), **`5ae39e1`** (Rust tensor integration). Report, acceptance và evidence được commit riêng. Các thay đổi chưa commit đã có trước R25 được giữ nguyên.
