# R37 — Chất lượng phát hiện và đóng băng scorer HTTPS Local

**RESEARCH_MODEL_FROZEN = PASS** · **T07_PRODUCTION_QUALITY = BLOCKED**

Chọn **HistGradientBoosting URI100**, version `r37-hgb-uri100-v1`, làm scorer mặc định cho profile HTTPS Local. Ở ngưỡng duy nhất `score > 0.7664756774902344`, WAF development holdout có **recall 86,04% và FPR 0,41%**. Cùng roster đó, ExtraTrees R36 đạt 73,58% và 4,12%. Mục tiêu 85%/1% đạt theo ước lượng điểm trên hai tập WAF development. Khoảng tin cậy còn rộng và phép chuyển ngưỡng sang nguồn khác chưa đạt. Slot R36 tiếp tục dùng được để rollback. [Manifest đóng băng](../ai-training/contracts/quality-freeze-r37/freeze.json)

## Vì sao ngưỡng R36 không chuyển được

- **Phân bố điểm benign thay đổi theo lineage.** CAL_OP có 349 normal thuộc 49 component, trong đó một component chiếm 146 request. Số component hiệu dụng theo tỷ trọng request chỉ là 4,97, so với 23,84 trên SELECT. Với ExtraTrees, phân vị 99% của điểm normal chuyển từ 0,448 ở CAL_OP lên 0,618 ở SELECT và 0,711 ở holdout. Ngưỡng cũ là 0,514. Trong holdout, 10 FP đều là GET và chỉ thuộc bốn component. Với HGB ở ngưỡng cũ, SELECT có 15 FP, trong đó tám thuộc một component. Ba FP trên CAL_OP đã đánh giá thấp phần đuôi phân bố khi gặp template khác. [Chẩn đoán R36](../ai-training/contracts/quality-freeze-r37/evidence/diagnosis.json) · [Đối soát holdout sau khóa](../ai-training/contracts/quality-freeze-r37/evidence/evaluation.json)
- **URI100 thiếu thông tin cho một phần lớn FIT.** Có 405 vector mang cả hai nhãn, đại diện cho 255.485 normal và 14.671 anomalous. Mọi quyết định tất định chỉ nhìn URI100 phải sai ít nhất 12.366 nhãn trên phân bố FIT. Ngay cả oracle biết nhãn của mọi vector và được phép chia lẻ một nhóm cũng chỉ đạt tối đa **65,13% recall ở FPR 1% trên FIT**. Holdout có một vector mixed với 21 normal và 8 anomalous. Hai tập có độ khó khác nhau. [Cận theo biểu diễn](../ai-training/contracts/quality-freeze-r37/evidence/shift.json)
- **Các nguồn có cấu trúc URI khác nhau.** Ở normal Notes, median của đặc trưng chuyển loại ký tự trong path là 0,194 so với 0,516 ở WAF CAL_OP, khoảng cách Kolmogorov–Smirnov là 0,840. Ở SR-BH, chênh lệch nổi bật ở chiều dài thành phần path. Đây là bằng chứng domain shift trên input. Chưa thể quy false positive cho một feature riêng lẻ. R37 có recall trên FIT 27,48% ở ngưỡng đã khóa dù đạt 86,04% trên holdout. Dữ liệu xác nhận ảnh hưởng của trọng số template và xung đột biểu diễn; chưa đủ để quy mức chênh lệch này cho overfitting. [Chẩn đoán chuyển nguồn](../ai-training/contracts/quality-freeze-r37/evidence/shift.json)

## Dữ liệu và thí nghiệm

Khóa protocol ở commit `ad6f383` trước khi chạy pilot. Nguồn duy nhất đóng góp vào fit là WAF publisher TRAIN với tác vụ normal/anomalous. R37 giữ ABI URI100, normalization và feature quan sát được tại dispatch. Các role tách theo component và được kiểm overlap vector. CAL_FIT, CAL_OP và SELECT thuộc development TUNING lịch sử. Holdout WAF từng được quan sát ở R36. R37 chỉ chấm holdout và các panel ngoài nguồn sau khi ghi khóa model và ngưỡng. Native đã admission có **0 TRAIN, 0 DEV, 0 CAL, 0 TEST**. [Protocol](../ai-training/contracts/quality-freeze-r37/protocol.json) · [SHA và vai trò nguồn](../ai-training/contracts/https-model-r36/plan.json)

| Vai trò WAF | Normal | Anomalous | Component |
|---|---:|---:|---:|
| Full FIT | 367.228 | 31.791 | 3.060 |
| CAL_FIT development | 1.765 | 1.862 | 166 |
| CAL_OP development | 349 | 741 | 193 |
| SELECT development | 271 | 1.054 | 354 |
| Development holdout | 243 | 738 | 319 |

Pilot tách component bên trong FIT. Ba nhánh gồm ExtraTrees, HGB thường và HGB tăng bốn lần trọng số của normal được teacher chấm cao ở fold khác. Mining tìm được 105 vector normal khó. Trên pilot validation, recall của ba nhánh lần lượt là 4,79%, 7,05% và 6,89% tại các FPR 0,0063%, 0,0096% và 0,0093%. Fold validation chứa 363.918 normal trong khi fold fit chỉ có 1.595 normal. HGB thường được chọn để full fit theo quy tắc đã khóa. [Pilot và mẫu số](../ai-training/contracts/quality-freeze-r37/evidence/pilot.json)

Full fit dùng **399.019 original request và 16.453 vector**, 140 vòng boosting, tối đa 15 lá, learning rate 0,08 và L2 bằng 2. Giữ weighting theo cell và cân hai lớp của R36. HGB là kiến trúc đã thử ở R36. R37 fit lại trên toàn FIT đủ điều kiện và thay đổi cách chọn ngưỡng. Mỗi component benign đóng góp tối đa khối lượng tám request trong một phép tính FPR bổ sung. Ngưỡng nhỏ nhất phải thỏa cả ngân sách 1% theo request lẫn theo khối lượng đã giới hạn. Fit Platt ở CAL_FIT, chọn ngưỡng trên CAL_OP bằng raw score ONNX. [So sánh đầy đủ](../ai-training/contracts/quality-freeze-r37/evidence/comparison.json) · [Khóa model trước đánh giá](../ai-training/contracts/quality-freeze-r37/evidence/selection.json)

## Kết quả tại ngưỡng cố định của mỗi model

| WAF development | Model | Recall | FPR | Accuracy | Balanced accuracy | AP |
|---|---|---:|---:|---:|---:|---:|
| SELECT | R36 đã triển khai | 71,73% | 1,48% | 77,21% | 85,13% | 0,9835 |
| SELECT | ExtraTrees với quy tắc ngưỡng mới | 56,07% | 0,37% | 64,98% | 77,85% | 0,9835 |
| CAL_OP | R37 HGB | 93,79% | 0,29% | 95,69% | 96,75% | 0,9987 |
| SELECT | R37 HGB | **89,94%** | **0,74%** | 91,85% | 94,60% | 0,9977 |
| Holdout | R36 đã triển khai | 73,58% | 4,12% | 79,10% | 84,73% | 0,9874 |
| Holdout | R37 HGB | **86,04%** | **0,41%** | **89,40%** | **92,82%** | **0,9945** |

Trên SELECT, recall tăng 18,22 điểm phần trăm so với R36. Khoảng 95% bootstrap ghép cặp theo component là **+8,71 đến +29,01 điểm**. Khoảng cho chênh lệch FPR là **−2,05 đến 0,00 điểm**. HGB ở ngưỡng R36 cũ đạt recall 97,82% nhưng FPR 5,54% trên SELECT. Cùng quy tắc ngưỡng mới, ExtraTrees mất nhiều recall hơn HGB. [Đối chứng và khoảng tin cậy](../ai-training/contracts/quality-freeze-r37/evidence/comparison.json)

Trên holdout, R37 có **TP 635, FN 103, FP 1, TN 242**, precision 99,84%, Brier 0,07092 và coverage 100% trên roster đã có vector. Brier của R36 là 0,06992. Bootstrap 2.000 lượt theo 319 component cho khoảng 95% của **recall 79,09–91,37%** và **FPR 0–1,55%**. Khoảng nhị thức mô tả theo original là 83,33–88,46% và 0,01–2,27%. Một FP nằm ở GET. POST chỉ có bốn normal. [Confusion và phân nhóm HTTP](../ai-training/contracts/quality-freeze-r37/evidence/evaluation.json)

## Chuyển nguồn sau khi khóa

| Cohort publisher | Request | R36 recall / FPR | R37 recall / FPR | R37 accuracy | R37 balanced accuracy |
|---|---:|---:|---:|---:|---:|
| Notes TUNING | 274 | 53,57% / 23,85% | 55,36% / 17,89% | 76,64% | 68,73% |
| Notes FIT lịch sử | 1.745 | 73,03% / 25,62% | 54,16% / 19,69% | 73,64% | 67,23% |
| SR-BH TUNING | 4.766 | 47,78% / 2,07% | 70,93% / 2,07% | 74,76% | 84,43% |
| SR-BH FIT lịch sử | 31.516 | 65,89% / 1,41% | 82,56% / 1,47% | 84,90% | 90,55% |

Các panel giữ định nghĩa nhãn riêng và cùng roster cho hai model. Không có component ngoài nguồn nào đụng exact vector WAF trong bốn panel đã đo. Trên Notes TUNING, 17 trong 39 FP đến từ một component, Brier tăng từ 0,316 lên 0,614. Trên SR-BH TUNING, cả hai model đều gắn cờ 12/20 POST normal. Output xác suất chỉ được hiệu chuẩn cho WAF. [Kết quả theo nguồn và method](../ai-training/contracts/quality-freeze-r37/evidence/evaluation.json)

## Nghiệm thu HTTPS Local

ONNX **121.554 byte**, SHA-256 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`. Đã lưu checkpoint sklearn, schema, calibration, ngưỡng, phiên bản thư viện và checksum. Resume ở giai đoạn hoàn thành đã kiểm SHA và trả về model đã khóa. Sai số lớn nhất giữa estimator và ONNX trên 6.042 request TUNING là 1,39 × 10⁻⁷, sai số output xác suất là 1,06 × 10⁻⁷. [Manifest release](../ai-training/contracts/quality-freeze-r37/release/manifest.json) · [Chỉ mục SHA](../ai-training/contracts/quality-freeze-r37/SHA256SUMS)

Sáu HTTPS request lành tính thật đi qua NGINX, Student Web/H2, Suricata, Rust và Hybrid với PostgreSQL cô lập. Trusted request ID của từng lượt nối được score, sensor transaction, Audit và quyết định. R37 phục vụ năm lượt. R36 phục vụ HEAD ở lượt rollback. POST logout và GET lấy lại CSRF đi qua R37 sau khi khôi phục. Cả sáu score có trước cutoff. Tại 1.000 ms với guard 1 ms có **5 NSA, 1 NA**. Khi đối soát sau cùng có 6 structural NSA. Có năm vector khác nhau. Hybrid ghi **6 LOG_ONLY, 0 đề xuất block, 0 lỗi ingest**. [HTTPS và Oracle](../ai-training/contracts/quality-freeze-r37/evidence/https.json) · [Quyết định Hybrid](../ai-training/contracts/quality-freeze-r37/evidence/hybrid.json)

Rust và Python trích cùng vector, score ONNX khớp 6/6. Load R37 mất **13,43 ms**. Trong 50 phép lặp warm của cùng frame, một thread, inference p50/p95 **0,023/0,035 ms**, preprocessing **0,151/0,207 ms**. SHA sai bị từ chối, frame lỗi cho ABSTAIN và frame hợp lệ kế tiếp thành công. Đã thực hiện restart và rollback thật. Scorer nghiên cứu chỉ phát quan sát và cảnh báo. 11 regression Rust, 7 test Python và 15 test staging/rollback đều qua. [Parity](../ai-training/contracts/quality-freeze-r37/evidence/parity.json) · [Rust](../ai-training/contracts/quality-freeze-r37/evidence/rust-regression.json) · [Python](../ai-training/contracts/quality-freeze-r37/evidence/python.log) · [Staging](../ai-training/contracts/quality-freeze-r37/evidence/stage.log)

Guardian giới hạn 1 CPU và RAM 2 GiB. Pilot và full training chung mất 8,128 giây, peak RAM 159,2 MiB. Lượt HTTPS mất 23,109 giây, peak RAM 437,9 MiB. Khi đo 96°C, kernel quota giảm còn nửa CPU. Backend và DB thoát 0, scratch được dọn và restart không gửi lại HTTP. Chưa benchmark tải đồng thời hoặc AWS. [Resource training](../ai-training/contracts/quality-freeze-r37/evidence/train.log) · [Resource Local](../ai-training/contracts/quality-freeze-r37/evidence/https.log) · [Cleanup](../ai-training/contracts/quality-freeze-r37/evidence/cleanup.json)

## Bàn giao Local

Nhánh `feature/ai-idps-https-ml-integration` bắt đầu từ `b8e00f5`. Ba commit kỹ thuật là `ad6f383` (chẩn đoán và protocol), `d7ad75a` (full fit và đánh giá) và `a484433` (scorer và rollback). Commit bàn giao chứa báo cáo và evidence. Đối chiếu HEAD bằng `git ls-remote --heads origin refs/heads/feature/ai-idps-https-ml-integration`. [Nhánh remote](https://github.com/vuong-quoc-trung/idps-web-aws/tree/feature/ai-idps-https-ml-integration)

R38 có thể bắt đầu nghiệm thu vận hành Local với model đã đóng băng. Điều kiện còn thiếu cho production là cohort HTTPS hai lớp với nhãn và lineage được xác minh độc lập, benign exposure đại diện, cùng CAL/TEST đủ cỡ mẫu cho T07. [Registry mặc định và rollback](../ai-training/contracts/quality-freeze-r37/slots.json) · [Cách chạy Local](../ai-training/contracts/https-model-r36/LOCAL.md)
