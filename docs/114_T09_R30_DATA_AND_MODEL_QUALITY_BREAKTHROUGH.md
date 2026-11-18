# T09 R30 — Data and Model Quality

**Đã tải và kiểm hai nguồn, tạo 7.435 view URI100 không nhãn, và chạy một pilot trên 11.082 dòng development.** Native gate là BLOCKED_NO_VERIFIED_DATA. Hiệu chỉnh đuôi theo HTTP method cho cùng kết quả với B16, nên giữ B16 làm bản nghiên cứu. Chưa có cơ sở full training hoặc release. [Bằng chứng R30](/home/trung/projects/idps-web-aws/ai-training/contracts/quality-study-r30/r30-evidence.json)

## Nguồn đã tải và sàng lọc

| Nguồn | Kết quả trên dữ liệu thực | Quyết định |
| --- | --- | --- |
| Organization X, Web Server Log Dataset | MIT theo Zenodo API. Archive 2.135.289 bytes khớp publisher MD5 và SHA-256. Trong 17 access-log members có **213.205 dòng**, **213.182** parseable, **211.178** dòng parseable distinct theo exact bytes, **13.999** cặp method/target exact. Project được 213.162 dòng thành **7.435** URI100 vector khác nhau. 15 ngày có log quan sát được, cùng một tổ chức | Dùng cho khảo sát coverage không nhãn. Archive có 39 rule definitions. Nhãn từ rule và mặc định benign khi không khớp là proxy, thiếu bảng outcome gắn request, trusted clock/receipt và tái dựng cutoff |
| FPAD publisher TRAIN | Tải **chỉ train.jsonl** từ repository release. Kiểm Git blob, SHA và metadata artifact MIT. Có **37.779** dòng, gồm **13.040** publisher normal và **24.739** publisher attack. Không lặp exact (method, target, body) trong shard | Normalizer origin/absolute hiện hành chấp nhận **13.040/13.040 normal** và **0/24.739 attack**. Target ở ngoài phạm vi encoder trùng hoàn toàn với lớp publisher. Paper/ledger còn ghi benign thừa kế CSIC và attack từ dữ liệu sinh. Quyền của package chưa chứng minh clearance lineage của bản ghi thừa kế |

Nguồn và phương pháp công bố tra tại [Organization X và dataset Zenodo](https://zenodo.org/records/20001206), [metadata quyền của Zenodo](https://zenodo.org/api/records/20001206), [FPAD TRAIN directory](https://github.com/Sec-AI-research/WebSpotter/tree/main/datasets/FPAD) và [WebSpotter paper](https://www.ndss-symposium.org/wp-content/uploads/2026-s1029-paper.pdf). Count FPAD dùng bytes thực tải được, lưu pin version. FPAD TEST/OOD, CSIC và PKDD stress giữ nguyên vai trò.

Derivative Organization X chỉ có float32 URI100 và số lần xuất hiện của vector. **7.434/7.435** view không trùng exact với ba TUNING frame đã dùng. Đây là so sánh representation trên ba frame. Kiểm near-duplicate và lineage toàn corpus chưa thực hiện cho nguồn này. B16 frozen flag rate **12,43% theo dòng log được project** và **4,24% theo unique view**. Cả hai là tỷ lệ flag trên dữ liệu không nhãn. FPR và recall chưa xác định. Raw ZIP/JSONL và derivative ở thư mục private. [Census Organization X](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/forensic-census.json) · [Census FPAD](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/fpad-census.json)

FPAD có 6.489 dòng normal và 11.869 attack với body string khác rỗng, nhưng thiếu media/capture metadata cho contract body của Local. Vì target format đã phân tách nhãn, việc thêm dấu slash theo lớp hoặc fit classifier trên format sẽ đo shortcut. R30 dừng nhánh body ở bước kiểm dữ liệu. Cả hai nguồn đưa vào native admission **0 bản ghi**. Native chính thức TRAIN / DEV / CAL_FIT / CAL_OP / TEST_SHADOW **0 / 0 / 0 / 0 / 0**.

## Pilot chất lượng B16

Khóa code, file SHA, cohort và ngưỡng acceptance trước scoring. Một hướng thử là dịch score logit B16 theo đuôi benign của GET/POST/OTHER, dùng **CAL_FIT Notes/SR-BH** và fallback pooled khi dưới 200 benign views hoặc 10 group. WAF/Notes/SR-BH **TUNING** đo chung ngân sách FPR 1% theo original và vector. Các điểm chọn trên TUNING chỉ dùng cho chẩn đoán. Thử transfer bằng cách lấy ngưỡng từ hai nguồn TUNING rồi đo ở nguồn thứ ba. Pilot dùng B16 frozen weights và không thay ngưỡng phát hành nghiên cứu. [Kế hoạch đã pin](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/calibration-plan.json)

| TUNING publisher | Normal / anomalous | B16 recall theo request | FPR theo request / vector | AP theo request |
| --- | ---: | ---: | ---: | ---: |
| Notes | 218 / 56 | 89,29% | 0% / 0% | 0,9326 |
| SR-BH | 676 / 4.090 | 89,00% | 0% / 0% | 0,9995 |
| WAF | 2.385 / 3.657 | 54,33% | 0,46% / 0,84% | 0,8901 |
| Macro | 11.082 dòng | **77,54%** | | |

Các số trong bảng dùng một cutoff TUNING chung và khớp hoàn toàn giữa B16 và arm method-tail. Macro vector-balanced recall **89,60%**. CAL_FIT có **837 / 23 / 14** benign views GET/POST/OTHER. POST và OTHER fallback, điểm đuôi GET trùng pooled, nên cả ba offset bằng 0, gain **0,00 điểm phần trăm**. Khi bỏ WAF khỏi chọn cutoff nghiên cứu, FPR chuyển sang WAF là **0,96% theo request và 3,91% theo vector**. Điều kiện chuyển pilot là macro gain ≥5 điểm, loss từng nguồn ≤2 điểm, transfer có gain và cap ≤1%. Kết quả không đạt. Giữ B16 và dừng hướng hiệu chỉnh hiện tại. [Kết quả pilot và từng arm](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/calibration-pilot.json)

Trong TUNING WAF có 6 URI100 mixed-label groups với 25 dòng anomalous. Cận hồi cứu ở FPR 0% là 99,32% recall trên frame WAF. Cận này dùng nhãn để phân tích, nên chỉ mô tả khả năng phân biệt trên frame. Khoảng cách tới recall tại cutoff cho thấy ranking/transfer còn ảnh hưởng đáng kể trên frame, bên cạnh collision ở những cohort cũ. Phạm vi đo là publisher development đã exposed. Chưa có common native roster đủ nhãn và rule evidence để đo lợi ích AI thêm so với rule hoặc Hybrid. Mục tiêu **recall ≥90% tại FPR ≤1% độc lập** vẫn chưa được chứng minh.

## Vận hành và bàn giao

- **3 regression PASS** về ties của strict cutoff, cận collision và reader chỉ materialize TUNING suffix. Ruff và Git diff check PASS. [JUnit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/tests.xml)
- **3 Adapter attempts COMPLETED exit 0**. Launch mỗi worker 1 CPU / 512 MiB. Telemetry cuối **94–96°C** kèm guardian THROTTLE, kernel cpu.max giảm từ 100000 100000 xuống 50000 100000. Admission lúc 60–66°C, không hardware alarm lúc admission. Bước tổng hợp ban đầu giả định quota giữ nguyên. Đã sửa đối soát theo action guardian và kernel readback. Cả 3 worker/guardian cleanup PASS, cgroup vắng và units inactive. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/acceptance.json)
- Bốn Local services active, PID/restart counter như R29. SHA B16/R20 khớp, RI v2 mặc định và R20 shadow. Không có job R30 hoặc QEMU chạy tiếp. Không có model mới hoặc release.
- Bảo toàn 34 file sửa sẵn và xác minh 215 artifact đã index của R27–R29. Commit triển khai **2187d28**, báo cáo và evidence ở commit riêng. Run **t09-r30-quality-kdnKN1kc**, chỉ mục 50 file giữ private. Hai projector dùng các helper nghiên cứu đã có. Clean checkout độc lập với dữ liệu và dependencies lịch sử chưa được kiểm. [SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/artifact-index.json) · [Push readback](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r30-quality-kdnKN1kc/git-push.json)

Bước ngắn nhất là nhận một cohort phòng thủ hai lớp có outcome gắn trusted request ID, exposure benign đại diện và body hoặc history có receipt trước cutoff. Chạy pilot theo lineage trên thông tin mới, dùng cùng request để đo gain so với rule tại ngân sách false alerts đã khóa.
