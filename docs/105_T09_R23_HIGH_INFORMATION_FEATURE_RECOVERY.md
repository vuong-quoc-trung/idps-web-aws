# T09 R23 — High-Information Feature Recovery

**Capacity pilot PASS. Mở rộng ETL, thay model và mục tiêu recall ≥90% tại FPR ≤1% còn BLOCKED.** Giữ SwiGLU R19 + isotonic R20 làm ứng viên Local shadow và **RI v2** làm serving model của Hybrid. Phối điểm cấu trúc 30% cho kết quả TUNING có triển vọng nhất trong các thử nghiệm R23, còn thiếu **0,20 điểm phần trăm** so với mức cải thiện recall tối thiểu đã ghi trong plan. [R23 plan](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/plan.json) · [R21](103_T09_R21_MODEL_QUALITY_AND_RELEASE_READINESS.md) · [R22.1](104A_T09_R22_1_PERSISTENT_LOCAL_AI.md)

## Nguyên nhân URI76 mất khả năng phân biệt

R23 đối chiếu **406.042 tọa độ original** được phép từ WAF publisher TRAIN với SHA đã pin. Original là identity phân biệt theo các trường mà publisher cung cấp. Chỉ đọc method, URL và nhãn để đo R23. Hostname của absolute-form được bỏ khi chiếu origin-form. Khóa định danh method/target dùng salt ngẫu nhiên trong RAM và không đi vào artifact hoặc model. [R19 manifest và cách chia](101_T09_R19_PROBABILISTIC_400K_TRAINING.md) · [Collision audit](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/collision-audit.json)

| Chỉ số | FIT | TUNING |
| --- | ---: | ---: |
| Original request | 400.000 | 6.042 |
| Method/target chuẩn hóa phân biệt | 388.854 | 2.414 |
| URI76 phân biệt | 8.213 | 1.841 |
| URI76 gộp nhiều method/target | 1.032 | 266 |
| Method/target có cả hai nhãn publisher | 34 | 5 |
| Original trong nhóm URI76 lớn nhất | 301.867 | 1.993 |
| Method/target phân biệt trong nhóm URI76 lớn nhất | 301.865 | 2 |

1. **Collision biểu diễn.** Riêng một vector FIT gộp **301.865** method/target khác nhau. Nội dung bị mất khi bỏ literal và tổng hợp path/query thành các thống kê chung. Feature mới chỉ phục hồi quan hệ giữa lớp ký tự và dấu phân cách trong phần đã qua lọc riêng tư. [URI76 projector](../ai-training/src/idps_ai/features/request_time.py) · [R23 projector](../ai-training/contracts/development-bulk-v1/r23_features.py)
2. **Label ambiguity.** Cùng method/target có thể mang hai nhãn vì headers, body hoặc ngữ cảnh khác nhau. R19 đã quarantine 10 exact original có nhãn đối lập. 34 nhóm FIT và 5 nhóm TUNING trùng method/target với nhãn khác nhau chưa có review để xác định nhãn sai. Tỷ lệ publisher noise chưa đo được. [Collision audit](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/collision-audit.json)
3. **Khả năng xếp hạng.** Trong **2.364 FN** của R20 trên TUNING, **1.986** nằm trong các vector thuần anomalous. Con số này cho thấy giới hạn ở thứ hạng hoặc operating point hiện tại, chưa tách được nguyên nhân tổng quát hóa ngoài publisher. Đối chiếu lịch sử HOLDOUT R20 ghi **730/873 FN** ở nhóm thuần anomalous. R23 dùng lại số liệu tổng hợp, không chấm lại HOLDOUT. [R20 error analysis](102_T09_R20_MODEL_QUALITY_RECOVERY.md) · [Pilot R23](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/pilot.json)

## Biểu diễn và capacity pilot

`idps-request-time-uri76-shape-r23-v1` giữ nguyên URI76, thêm **24** thống kê cấu trúc hoặc **128** ô băm bigram/trigram. Chỉ băm ký hiệu thuộc bảng hữu hạn sau khi lọc field có dấu hiệu bí mật, PII và token đục. Chữ và số đã chuyển thành lớp ký tự, độ dài chuỗi cùng lớp và số đếm đều bị chặn. Không dùng literal, hostname, header, body, response hoặc thông tin sau cutoff. Hai arm dùng cùng sample **12.456** original FIT, tối đa 8 mỗi vector/label và chia lại trọng số cell R19 để giữ tổng mass. TUNING giữ đủ **6.042** original. [Feature code](../ai-training/contracts/development-bulk-v1/r23_features.py) · [Plan và pin](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/plan.json)

Giữ nguyên closure exact URI76, bucket và symbolic template của R19. R23 đối chiếu **0 overlap** method/target chuẩn hóa và **0 bucket overlap** trên các vector mở rộng. Không chấm R19 HOLDOUT, publisher eval, TEST hay sealed holdout. Quá trình đọc chỉ join các tọa độ FIT/TUNING đã được phép. [Runner và quy tắc split](../ai-training/contracts/development-bulk-v1/r23_pilot.py)

| Chỉ số | URI76 | + Structure | + Symbol n-gram |
| --- | ---: | ---: | ---: |
| Distinct vector trên FIT sample | 8.213 | 9.367 | 9.343 |
| Distinct vector TUNING | 1.841 | 2.086 (+13,31%) | 2.106 (+14,39%) |
| Original TUNING trong vector va chạm | 4.611 | 4.344 (−5,79%) | 4.348 (−5,70%) |
| Mixed vectors TUNING | 8 | 6 | 6 |
| Original TUNING trong vector mixed | 2.121 | 126 | 126 |
| Anomalous TUNING trong vector mixed | 378 | 25 | 25 |
| FN của R20 trong nhóm mixed URI76 nay có vector thuần anomalous | 0 | 353 | 353 |

Các arm được gán điểm từ FIT chỉ phát hiện **0–20** anomalous trong panel mixed URI76. Tách biểu diễn làm giảm giới hạn thông tin, nhưng model vẫn phải học được thứ hạng ở ngưỡng ít FP. Oracle dùng trực tiếp nhãn TUNING cho cận hồi cứu **90,32% → 99,95%** ở mức 23 FP. Đây là cận lý tưởng trên cohort publisher này. [Capacity, FN panel và oracle](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/pilot.json)

## Quality tại low FPR

Ngưỡng các arm R23 xét cả FPR original request và FPR cân bằng vector trên TUNING. Hai mốc frozen giữ ngưỡng cũ. Bảng tính score và nhãn publisher trên cùng original roster. Confusion theo thứ tự TN/FP/FN/TP. [Metrics chi tiết](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/pilot.json)

| Arm | AP | Recall | Precision | FPR request / vector | Recall vector | Brier / ECE | Confusion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Logistic URI76, fit pilot | 0,8745 | 31,26% | 99,05% | 0,461% / 0,872% | 46,69% | 0,2014 / 0,2258 | 2.374/11/2.514/1.143 |
| Logistic R19 frozen | 0,8746 | 31,34% | 98,96% | 0,503% / 1,138% | 46,90% | 0,2017 / 0,2205 | 2.373/12/2.511/1.146 |
| SwiGLU R20 frozen | 0,9442 | 35,36% | 99,77% | 0,126% / 0,796% | 53,47% | 0,0831 / ≈0 | 2.382/3/2.364/1.293 |
| Logistic + Structure | 0,9297 | 33,72% | 99,12% | 0,461% / 0,839% | 54,75% | 0,1747 / 0,1939 | 2.374/11/2.424/1.233 |
| Logistic + Symbol n-gram | 0,8169 | 37,82% | 99,21% | 0,461% / 0,842% | 61,83% | 0,2015 / 0,3199 | 2.374/11/2.274/1.383 |
| R19 raw + 15% structure score | 0,9712 | 34,32% | 99,76% | 0,126% / 0,766% | 55,59% | 0,1893 / 0,1973 | 2.382/3/2.402/1.255 |
| R19 raw + 30% structure score | **0,9716** | **37,16%** | 99,20% | 0,461% / 0,839% | **59,64%** | 0,1829 / 0,1809 | 2.374/11/2.298/1.359 |

Blend 30% tăng **66 TP** và **8 FP** so với operating point của R20. Recall tăng **1,80 điểm** theo request và **6,17 điểm** theo vector. Symbol n-gram có recall request cao nhất trong pilot, đồng thời AP giảm **0,1274** so với R20. Ngưỡng mở rộng đã ghi trước phép thử yêu cầu ≥5% gain distinct, ≥2 điểm gain recall request, giữ recall vector và không mất AP quá 0,005. Không arm nào đạt toàn bộ. R20 isotonic đã fit trên chính TUNING, nên Brier/ECE của arm đó là in-sample. Arm mới giữ điểm thô. Tuning phân biệt component theo publisher, chưa đo generalization ngoài corpus. [Gate và kết quả](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/pilot.json)

## Runtime, parity và bước tiếp theo

- **Rust/Python numeric parity 256/256, byte-exact** cho cả hai lane trên sketch đã lọc. Khâu này dùng dữ liệu đầu vào đã chuyển lớp trong Python. R23 chưa kiểm raw-target parser độc lập bằng Rust. p50/p95 Python trên các target cache miss, gồm URI76 và cả hai extension, khoảng **0,19/0,41 ms** ở pilot ban đầu. Phép đo riêng numeric stage trong Python đạt khoảng **0,026/0,048 ms**. [Collision audit pilot ban đầu](../ai-training/.artifacts/t09-r23-pilot-pWxTpFx2/collision-audit.json) · [Parity cuối](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/parity.json) · [Rust projector](../ai-training/contracts/development-bulk-v1/r23_features.rs)
- **97 regression tests PASS**. Pilot xác minh cuối chạy khoảng **10,61 giây** dưới Resource Adapter, RAM cap **4 GiB**, một mẫu dùng khoảng **355 MiB**. Kernel đọc lại quota **50% của một CPU** khi guardian giảm quota ở **94°C**. Exit 0, cleanup PASS, các unit pilot đã ngừng. `Linger=yes` và bốn service R22.1 vẫn active. [Resource result](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/resource-1/result.json) · [Readback](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/resource-1/status.json)
- **Candidate giữ lại** là checkpoint R19 step **55**, manifest SHA `0ed456322141181d93b068e2555285f6455e6cad45c9c4856f1bb01b0bd296c0`, ONNX R20 SHA `1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525`. Gate pilot chưa đạt nên không bulk train, xuất ONNX R23 hay chuyển Local shadow. Nghiệm thu HTTP shadow áp dụng cho R20 theo R22/R22.1. Recall/FPR HOLDOUT lịch sử của R20 là **61,91% / 0,964%** theo request và FPR **2,224%** cân bằng vector. [Bundle handoff](../ai-training/contracts/development-bulk-v1/r21-shadow-handoff.json) · [R22 acceptance](104_T09_R22_LOCAL_SHADOW_AND_QUALITY_EVIDENCE.md)
- **Native vẫn BLOCKED.** Intake không có custodian-pinned handoff. Evidence runtime có 34 observation, gồm 6 engineering receipt R22 KVM và 28 mirror, tất cả chưa có nhãn native được review. Hiện có 0 cohort hai lớp độc lập. T07 cần tối thiểu 100 attack đã biết từ 20 cụm cho mỗi claim, benign anchor độc lập đủ cận ≤1%, CAL tách biệt và nonregression theo strata. Ví dụ một cận cần 299 benign anchor nếu quan sát 0 false alert. [T07](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md) · [Runtime census](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/status.json)

Phép thử tiếp theo nên khóa **structure** làm lane ưu tiên và đo với cutoff giống R20 trên một roster publisher development chưa exposed, theo nhóm method/target và template. Phối điểm 30% là mốc research để đối chiếu. Đặt cùng ngân sách FP trước khi so recall. Với native, ưu tiên thu nhận evidence request-bound đã được review, rồi ablation causal history cùng structure trên cùng lineage. [Kết quả R23](../ai-training/.artifacts/t09-r23-verified-vASgKZV1/pilot.json)

Commit `f33a6e8` chứa biểu diễn và Rust numeric projector. Commit `3cdf7d4` chứa ETL audit, capacity pilot và regression. Cả hai nằm trên nhánh `feature/ai-idps-shadow-integration`.
