# T09 R21 — Model Quality and Release Readiness

**Thử nghiệm development và bàn giao Local shadow đã hoàn tất. Mục tiêu recall ≥90% tại FPR ≤1% và kích hoạt trong Hybrid còn BLOCKED.** Giữ SwiGLU **395.360 tham số** của R19 với isotonic R20 cho Local shadow. Giữ RI v2 làm model phục vụ và đầu vào AI của Hybrid. Run `t09-r21-quality-ddf4q6Pq` hoàn tất trên checkpoint, dữ liệu và ngưỡng đã khóa. [R19](101_T09_R19_PROBABILISTIC_400K_TRAINING.md) · [R20](102_T09_R20_MODEL_QUALITY_RECOVERY.md) · [T07](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md) · [Trạng thái R21](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/status.json)

## Model và ngưỡng

R21 giữ 400.000 original request và 8.213 URI76 của R19 FIT cùng toàn bộ nhãn publisher. Ba logistic thử thay đổi riêng trọng số. `uniform_vector` cân bằng mass theo vector. `class_mass_preserved` giữ mass theo lớp sau cap R19. `hard_normal` tăng trọng số cell benign khó trên FIT, xác định bằng phân vị 90 của điểm R19 trên vector có benign, sau đó cân bằng lại lớp. Giữ cùng solver, regularization và ABI 76 float. Mỗi ngưỡng mới được khóa trên R19 TUNING bằng strict `>` với FPR ≤1% theo request và vector. Giữ nguyên ngưỡng isotonic R20. Quy tắc R21 yêu cầu tăng ít nhất 2 điểm recall theo request trên tuning, bảo toàn recall theo vector và giới hạn suy giảm AP ở 0,005. Không có arm mới đạt. [Plan](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/plan.json) · [Tuning và ngưỡng](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/selection.json)

| Arm | Tuning recall theo request | WAF holdout recall / precision / FPR theo request | Holdout AP | Brier / ECE | Holdout recall / FPR cân bằng vector | ORT CPU p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic R19 | 31,34% | 54,58% / 99,29% / 0,964% | 0,9640 | 0,1284 / 0,1109 | 52,44% / 2,224% | 0,009 ms |
| SwiGLU R19 | 35,36% | **61,91% / 99,37% / 0,964%** | **0,9704** | 0,1259 / 0,1211 | **63,32% / 2,224%** | 0,146 ms |
| SwiGLU R20 isotonic | 35,36% | **61,91% / 99,37% / 0,964%** | 0,9644 | 0,1176 / 0,0898 | **63,32% / 2,224%** | 0,151 ms |
| R21 uniform vector | 31,88% | 57,46% / 99,32% / 0,964% | 0,9636 | 0,1287 / 0,1099 | 56,60% / 2,224% | 0,004 ms |
| R21 class mass preserved | 31,17% | 53,23% / 99,27% / 0,964% | 0,9636 | 0,1141 / 0,0431 | 50,25% / 2,224% | 0,003 ms |
| R21 hard normal | 32,27% | 58,46% / 99,33% / 0,964% | 0,9638 | 0,1359 / 0,1272 | 57,20% / 2,224% | 0,004 ms |

WAF holdout gồm **3.226 original, 1.683 vector, 693 component**, từng được dùng ở R19–R20. Nhãn là `normal/anomalous` của publisher. Bảng dùng để đối chiếu development sau khi khóa ngưỡng, không dùng để chọn thêm model. Đây là CPU microbenchmark batch 1 với ORT 1.31.1. AP, precision, confusion, Brier và ECE cân bằng vector có trong JSON. Logistic URI76 26K R13 vẫn là tham chiếu SR-BH. AP DEV 0,8874 của R13 thuộc cohort khác. [Metrics đầy đủ](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/evaluation.json) · [R13](95_T09_R13_TEMPORAL_DEVELOPMENT_TRAINING.md)

`hard_normal` phát hiện thêm **89** anomalous so với logistic R19 ở cùng 9 FP, vẫn kém SwiGLU **79** ca. Tất cả arm bỏ sót **143/143** anomalous thuộc **11 vector mixed**. SwiGLU R19/R20 giữ confusion **925 / 9 / 873 / 1.419**. Việc đổi trọng số giúp logistic xếp hạng một số request, còn mỗi vector mixed vẫn chỉ có một điểm dùng chung. R20 tiếp tục là lựa chọn shadow nhờ Brier và ECE toàn cohort tốt hơn bản raw và giữ operating point. R19 raw vẫn có AP tốt hơn. [Confusion và mixed panel](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/evaluation.json)

## Ablation theo feature và khả năng quan sát

Để so sánh công bằng sau khi bỏ cột, mọi arm logistic dùng cùng FIT đã embargo theo exact vector và `floor(16 × vector)` trong **tất cả** biểu diễn rút gọn. Bước này loại **299 URI76 / 302.618 original** khỏi FIT của ablation, giữ **7.914 / 97.382** và nguyên 6.042 request TUNING. Phần lớn original bị loại tập trung trong các nhóm lặp lớn. Lần chạy đầu chưa xét overlap phát sinh sau khi bỏ cột được giữ làm evidence, không dùng trong kết luận. [Plan embargo](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/feature-v2/feature-plan.json) · [Kết quả ablation sau embargo](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/feature-v2/feature-ablation.json)

| Cột bỏ khỏi URI76 | Recall / FPR theo request trên tuning | Recall / FPR theo vector rút gọn | Vector distinct / mixed |
| --- | ---: | ---: | ---: |
| Không bỏ | 31,26% / 0,461% | 46,69% / 0,872% | 1.841 / 8 |
| Method | 29,70% / 0,461% | 43,50% / 0,877% | 1.836 / 9 |
| Path structure | 31,64% / 0,126% | 49,03% / 0,798% | 1.840 / 8 |
| Query structure | 31,31% / 0,461% | 47,58% / 0,879% | 1.794 / 8 |
| Encoding | 30,68% / 0,461% | 45,74% / 0,872% | 1.841 / 8 |
| Availability flags | 31,20% / 0,461% | 46,56% / 0,872% | 1.841 / 8 |

Method có ích trong phép thử này. Bỏ path structure chỉ tăng **0,38 điểm recall theo request** trên tuning, chưa có phép đo độc lập về lợi ích. Query giữ lại 47 vector phân biệt trong panel. Giữ URI76 và mask hiện hành. Không lấy AP hoặc recall từ bài ablation tuning làm số liệu release. [Ablation JSON](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/feature-v2/feature-ablation.json)

R21 kiểm lại SHA, cutoff và Oracle của sáu receipt native R10. Ba lần đọc lành tính giống URI76 có **1** biểu diễn tĩnh và **3** biểu diễn khi thêm số lượt cùng vector đã thấy trước đó. URI76 projection chậm nhất **0,923 ms**, toàn cửa sổ quan sát receiver đã có dữ liệu và không bị truncate. Lịch sử này có scope receiver. Session, tần suất theo actor và header/source evidence đúng hạn chưa đủ dữ liệu hai lớp để đo tác dụng phân loại. WAF thiếu sequence và session gắn request. Không thêm feature vào serving stack nên không phát sinh hợp đồng Python/Rust mới. [Kiểm tra native và lịch sử](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/native.json) · [Timing của lịch sử R10](92_T09_R10_CAUSAL_HISTORY_AND_CRASH_RECOVERY.md)

## Hybrid, giữ checkpoint và bàn giao R22

Replay R11/R12 đã đối chiếu theo SHA. Fixture giữ rule risk 45 và `ALERT` khi AI không đóng góp. Cùng input rule, RI v2 trên ngưỡng cho `REVIEW`. Ba request benign native R12 cho `LOG_ONLY`, gồm một lần scorer unavailable. Không có handoff native đã được custodian pin. Native TRAIN/DEV **0/0**, Rule-only/Hybrid recall và FPR **BLOCKED** vì chưa có common roster hai lớp cùng cutoff. Không dùng rule alert làm ground truth và không có firewall action. [Replay](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/hybrid-evaluation.json) · [T07 Hybrid gates](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

- **Ứng viên shadow**. Dùng bundle R20 trên checkpoint **step 55**, SHA manifest checkpoint `0ed456322141181d93b068e2555285f6455e6cad45c9c4856f1bb01b0bd296c0`. SHA ONNX `1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525`. R21 nạp lại checkpoint và xác minh state manifest. ONNX URI76 và đường Rust không đổi, dùng lại evidence parity, ABSTAIN và restart của 11 HTTP attempts R20. Ba ONNX logistic R21 kiểm parity Python trên TUNING. Chúng giữ vai trò thử nghiệm và không được chọn cho R22. [Manifest bàn giao R22](../ai-training/contracts/development-bulk-v1/r21-shadow-handoff.json) · [Checkpoint](../ai-training/.artifacts/t09-r19-waf-vhrrfJw8/training/model/checkpoints/step-000000000055-e0eccd7bd125/manifest.json) · [ONNX chọn giữ](../ai-training/.artifacts/t09-r20-quality-OktqJbDt/bundle/swiglu.onnx) · [Rust parity](../ai-training/.artifacts/t09-r20-quality-OktqJbDt/http-parity.json)
- **Resource và regression**. **93 tests PASS** gồm weighting, embargo, ngưỡng, T07, request-time và Resource Adapter. Các worker ablation dùng kernel `cpu.max=100000 100000`, `memory.max=4294967296`, thermal guardian, exit 0 và cleanup PASS. Không còn workload nền của R21. Hai commit chỉ chứa file R21. Artifacts nặng và các thành phần kế thừa đang có sẵn trong workspace giữ nguyên cách lưu trữ hiện hành. [Resource objective ablation](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/resource-1/result.json) · [Resource feature ablation](../ai-training/.artifacts/t09-r21-quality-ddf4q6Pq/resource-feature-2/result.json)
- **Việc có tác động lớn nhất cho R22**. Dùng manifest trên để tích hợp shadow cô lập và giữ RI v2 trong serving. Đưa defensive evidence native đã được review vào common roster rồi đối chiếu URI76 với causal history trên cùng lineage và cutoff **1.000 ms, guard 1 ms**. Tiếp tục CAL_FIT, CAL_OP và TEST_SHADOW tách biệt theo T07. Chỉ xem xét đổi model hoặc hợp nhất Hybrid khi paired quality, coverage, hiệu năng và rollback đều đạt. [T07 release requirements](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)
