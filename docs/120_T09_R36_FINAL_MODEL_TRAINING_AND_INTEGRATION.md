# R36 — Huấn luyện và thay scorer nghiên cứu trên HTTPS Local

**Model được chọn là ExtraTrees URI100 R36**, 48 cây, giới hạn độ sâu 9, refit mới từ dữ liệu WAF. Model chỉ nhận method và đặc trưng URI có tại dispatch ở NGINX. Mốc operating point là raw score strict `> 0.5138319730758667`. Trên 981 request holdout WAF theo component, recall đạt **73,58%** và FPR **4,12%** tại cùng ngưỡng. Mục tiêu 85%/1% chưa đạt. Các nhãn WAF là normal/anomalous do publisher cung cấp.

## Dữ liệu và lựa chọn

Nguồn chính là 400.000 original WAF publisher TRAIN đã khóa cùng 17.164 vector URI100. Các original khác nhau có cùng vector vẫn đóng góp theo số lượng từng nhãn. R36 kế thừa khối lượng loss theo parent, cân hai lớp và không nhân bản các request. SHA dữ liệu, phép gán component bằng hash và quy tắc chọn model đã ghi trong [kế hoạch](../ai-training/contracts/https-model-r36/plan.json).

| Vai trò WAF | Normal | Anomalous | Vector | Component |
|---|---:|---:|---:|---:|
| FIT cho hai model R36 mới | 367.228 | 31.791 | 16.453 | 3.060 |
| Holdout R36 trong WAF publisher TRAIN | 243 | 738 | 711 | 319 |
| SELECT trong TUNING lịch sử | 271 | 1.054 | 952 | 354 |
| CAL_FIT development | 1.765 | 1.862 | 407 | 166 |
| CAL_OP development | 349 | 741 | 727 | 193 |

Hai model mới fit toàn bộ **399.019** original đủ điều kiện sau khi giữ riêng 319 component. Cả hai model cũ được chấm từ ONNX đóng băng. Các component và vector tách biệt giữa các role mới. Chỉ dùng method/URI theo ABI HTTPS R35. B16 có thêm input body, RBA có actor/history và task cờ chiếm tài khoản. Receipt HTTPS trong R35 chưa chứng minh các trường đó sẵn sàng. Notes và SR-BH mang hai ontology publisher khác, được dùng để kiểm chuyển nguồn. Native HTTPS của chiến dịch có **0 TRAIN, 0 DEV, 0 CAL, 0 TEST** đã admission.

Với mỗi model, fit Platt có slope dương trên CAL_FIT. Chọn ngưỡng strict trên CAL_OP với ngân sách false positive 1% theo original. Lựa chọn trên SELECT ưu tiên model đáp ứng ngân sách, sau đó tối đa recall. Khi tất cả vượt ngân sách trên SELECT, chọn model có mức vượt thấp nhất. Không chỉnh ngưỡng sau khi thấy holdout.

| Model | Recall SELECT | FPR SELECT | Accuracy | Balanced accuracy | AP | Recall / FPR CAL_OP |
|---|---:|---:|---:|---:|---:|---:|
| R35-logistic | 60,06% | 4,80% | 67,25% | 77,63% | 0.9599 | 70,45% / 0,86% |
| R25-SwiGLU | 72,39% | 3,69% | 77,28% | 84,35% | 0.9835 | 85,43% / 0,86% |
| R36-HistGradientBoosting | 97,82% | 5,54% | 97,13% | 96,14% | 0.9977 | 97,84% / 0,86% |
| R36-ExtraTrees | 71,73% | 1,48% | 77,21% | 85,13% | 0.9835 | 83,00% / 0,86% |

ExtraTrees có 4 FP trên 271 normal ở SELECT. HistGradientBoosting thu hồi nhiều positive nhất nhưng có 15 FP trên cùng 271 normal. Bài toán yêu cầu cân nhắc hai đại lượng ở cùng một ngưỡng. Holdout của model được chọn có TP 543, FP 10, TN 233, FN 195, accuracy **79,10%**, balanced accuracy **84,73%**, precision **98,19%**, AP **0,9874**, Brier **0,06992**. Coverage 100% trong cohort số đã chiếu được. 243 benign holdout giới hạn độ chính xác của ước lượng FPR. Holdout này nằm ngoài FIT, SELECT và hai phần calibration của hai model mới. Các checkpoint cũ đã từng dùng phần dữ liệu gốc tương ứng.

**Hai lỗi thực thi đã được xử lý.** Converter thử ban đầu phát thuộc tính boolean trong trường integer của ONNX-ML. Exporter cuối ghi chính xác node, lá, ngưỡng float32 và trọng số của cây, sau đó đối chiếu với estimator. Ở lượt đầu, calibration float32 làm các score cao bão hòa thành 1 và ngưỡng strict 1 không phát hiện request nào. Artifact cuối xuất hai output riêng biệt, `score` cho ranking và operating point, `publisher_probability` cho đánh giá calibration. Giữ nguyên split, estimator, ngân sách FPR và thứ tự chọn. Loại operating point có 0 TP trên CAL_OP. Holdout và chuyển nguồn của lượt đầu đã được quan sát trước khi sửa lỗi số học. Kết quả sau sửa có giá trị kiểm thử development, chưa phải một lần mở blind TEST. [Lượt đầu](../ai-training/contracts/https-model-r36/evidence/first-pass.json) · [Số liệu cuối](../ai-training/contracts/https-model-r36/evidence/metrics.json)

## Chuyển nguồn ở ngưỡng đã khóa

| Cohort publisher ngoài WAF | Request | Recall | FPR | Accuracy | Balanced accuracy |
|---|---:|---:|---:|---:|---:|
| NOTES TUNING | 274 | 53,57% | 23,85% | 71,53% | 64,86% |
| SRBH TUNING | 4766 | 47,78% | 2,07% | 54,89% | 72,85% |
| NOTES FIT lịch sử, chỉ chấm sau khóa | 1745 | 73,03% | 25,62% | 74,04% | 73,71% |
| SRBH FIT lịch sử, chỉ chấm sau khóa | 31516 | 65,89% | 1,41% | 70,68% | 82,24% |

Đã kiểm exact URI100 với các role WAF. Với phép đo bổ sung trên FIT lịch sử, loại toàn bộ component đụng exact view WAF. Hai nguồn không đóng góp vào fit, calibration hay lựa chọn R36. Những phép đo này đánh giá sự chuyển ngưỡng giữa các nhãn publisher. Tỷ lệ false positive trên Notes là giới hạn rõ nhất. Chưa có bằng chứng về calibrated attack probability trên HTTPS của Student Web. [Transfer sau khi khóa](../ai-training/contracts/https-model-r36/evidence/transfer.json)

## Artifact và rollback

ONNX 215.640 byte, SHA-256 `d4797584ab7eb243725329f08acf160122bf1da27a9fb128850f333fd0ce4bd0`. ABI `idps-uri100-raw-ascii-r26-v1`, tensor `float32[N,100]` với thứ tự và normalization của R35. Checkpoint sklearn là estimator sau fit, calibration nằm trong ONNX. Runner resume tại ranh giới candidate và sau khi hoàn thành, đối chiếu SHA trước khi tái sử dụng. Sai số estimator/ONNX lớn nhất trên 6.042 hàng TUNING là 4,35 × 10⁻⁷, sai số xác suất calibration là 8,55 × 10⁻⁷. Bản build cuối tái tạo cùng digest model.

Registry Local mặc định chọn `r36-extratrees-uri100-v1`. `--slot rollback` chọn logistic R35. Mỗi receiver giữ đúng một process scorer. SQLite outbox ghi observation theo cùng transaction với receipt. Journal được fsync trước khi xác nhận, Rust hấp thụ duplicate và cách ly xung đột. Security Web kiểm schema, release, clock, request ID và threshold khi ingest, ghi vào bảng riêng ở migration 0019. Hybrid dùng scorer này làm trường AI chính cho request có observation HTTPS, còn evidence RI v2 phục vụ chính sách đã phê duyệt được lưu ở trường riêng. Research chỉ có thể nâng LOG_ONLY thành ALERT, không cộng risk cho PROPOSE_BLOCK. Trên host R22 đang phục vụ, các unit production cũ vẫn độc lập với profile Local tích hợp.

[Schema](../ai-training/contracts/https-shadow-r35/schema.json) · [Checkpoint và model](../ai-training/contracts/https-model-r36/release/selection.json) · [Cấu hình mặc định và rollback](../ai-training/contracts/https-model-r36/slots.json) · [Cách chạy Local](../ai-training/contracts/https-model-r36/LOCAL.md)

## Nghiệm thu HTTPS Local trên bản bàn giao

**LOCAL_AI_INTEGRATED = PASS.** Trong lần chạy cuối trên loopback cô lập, NGINX cấp sáu request ID. Mỗi ID đối soát được với một Student Audit event, một Suricata flow/transaction, một vector có digest, một kết quả Rust ONNX và một quyết định của Hybrid ghi ở PostgreSQL. Cả sáu đều có đủ ba nguồn khi đối soát cuối. Tại cutoff 1.000 ms với guard 1 ms, năm request có NSA. Request đầu có NA do proof Suricata sẵn sàng khoảng 1.151 ms sau dispatch. Cả sáu vector và điểm HTTPS đều có trước cutoff. [Receipts và thời điểm](../ai-training/contracts/https-model-r36/evidence/https.json) · [Đối soát bằng request ID](../ai-training/contracts/https-model-r36/evidence/acceptance.json)

| Lượt | HTTPS | HTTP | Model thực nạp | Mask tại cutoff | Kết quả Hybrid | Thời gian HTTP |
|---:|---|---:|---|---|---|---:|
| 1 | GET lấy CSRF và session | 200 | R36 | NA | LOG_ONLY | 436,966 ms |
| 2 | GET thông tin tài khoản khi chưa đăng nhập | 401 | R36 | NSA | LOG_ONLY | 37,439 ms |
| 3 | GET CSRF với query sau restart scorer | 200 | R36 | NSA | LOG_ONLY | 44,411 ms |
| 4 | HEAD profile options khi chưa đăng nhập | 401 | R35 rollback | NSA | ALERT | 13,030 ms |
| 5 | POST logout với cookie và CSRF của session trước | 204 | R36 khôi phục | NSA | LOG_ONLY | 16,257 ms |
| 6 | GET CSRF với cookie cũ sau logout, được cấp session mới | 200 | R36 | NSA | LOG_ONLY | 45,634 ms |

Có năm vector URI100 phân biệt. R36 cho cùng score 0,223551 trên cả năm lượt của nó dù đầu vào có khác nhau. R35 cho 0,903313 và một ALERT ở lượt rollback. Sáu request này kiểm chứng đường truyền và hành vi ứng dụng. Chúng chưa cung cấp nhãn độc lập để suy ra chất lượng phát hiện. Backend ghi **0 lỗi ingest, 0 đề xuất block**. Ban/unban và protected IP được kiểm ở regression của controller. Lượt live dừng ở quan sát chính sách, chưa đo tác động ban/unban trên firewall hệ điều hành. [Kết quả Hybrid](../ai-training/contracts/https-model-r36/evidence/hybrid.json) · [Journal của scorer](../ai-training/contracts/https-model-r36/evidence/https-research.jsonl)

**Parity và độ trễ.** Sáu vector khớp giữa preprocessing Python và Rust, sai số Python ONNX/Rust bằng 0 trên cả sáu lượt. Rust từ chối SHA sai và trả ABSTAIN cho đầu vào lỗi, rồi phục hồi với frame hợp lệ. Load model mất **16,15 ms**. Với 50 lượt warm trên cùng một frame, một thread CPU, preprocessing p50/p95 **0,122/0,283 ms**, inference p50/p95 **0,023/0,043 ms**. Chưa đo phân vị tải đồng thời hoặc trên AWS. [Parity và benchmark](../ai-training/contracts/https-model-r36/evidence/parity.json)

**Khả năng phục hồi.** Lượt phát triển phát hiện hai giả định sai trong harness. Oracle logout giờ kiểm tra cookie cũ dẫn đến session mới. Collector chờ receipt của từng request trước khi đối soát nguồn. Thời điểm proof ghi nhận vẫn quyết định mask tại cutoff. Thư mục NGINX tạo qua user namespace được dọn bằng đúng UID mapping. Khi restart gặp một dòng journal ghi dở, receiver giữ nguyên phần byte đã ghi, ngăn cách dòng đó rồi phát tiếp từ SQLite outbox. Regression kiểm tra duplicate và xung đột cùng ID. [Regression Python](../ai-training/contracts/https-model-r36/evidence/python-final.log)

**Resource và cleanup.** Training và live dùng guardian, quota cơ sở 1 CPU và giới hạn RAM 2 GiB. Trong lượt live 23,153 giây, peak RAM 442,6 MiB theo systemd. Tại 93°C, kernel readback chuyển từ quota 1 CPU xuống 0,5 CPU và trở về 1 CPU khi hạ nhiệt. Backend và PostgreSQL thoát mã 0, scratch được thu hồi, restart không gửi lại HTTP. Bốn unit Local R22 vẫn active khi bàn giao. Có 8 test Python, 15 test staging/rollback và 11 test Rust có liên quan đã qua. Resume hoàn tất ở ranh giới candidate và xác minh lại SHA checkpoint. [Resource](../ai-training/contracts/https-model-r36/evidence/handoff.log) · [Cleanup](../ai-training/contracts/https-model-r36/evidence/cleanup.json) · [Staging](../ai-training/contracts/https-model-r36/evidence/stage.log) · [Rust](../ai-training/contracts/https-model-r36/evidence/rust-regression.json) · [Resume](../ai-training/contracts/https-model-r36/evidence/resume.log)

## Quyết định bàn giao

**T07_PRODUCTION_QUALITY = BLOCKED.** R36 đạt nghiệm thu kỹ thuật cho scorer mặc định của profile HTTPS Local. Mục tiêu recall ≥85% đồng thời FPR ≤1% chưa đạt trên WAF holdout. FPR chuyển sang Notes còn cao và chưa có cohort HTTPS native hai lớp đã admission để định ngưỡng vận hành hoặc đánh giá độc lập. Các kết quả R36 dùng nhãn publisher và có phạm vi development. Model nghiên cứu chỉ phát điểm và cảnh báo.

**Bước R37** là nghiệm thu toàn hệ thống Local với slot đã khóa, giữ rollback R35 và thu evidence HTTPS có ground truth độc lập cho cả hai lớp. Trước khi xem xét quyền enforcement, khóa CAL/TEST theo lineage, đo recall và FPR tại cùng ngưỡng trên TEST và kiểm tra tác động Hybrid. [Chỉ mục SHA-256](../ai-training/contracts/https-model-r36/SHA256SUMS) · [Registry runtime](../ai-training/contracts/https-model-r36/slots.json)
