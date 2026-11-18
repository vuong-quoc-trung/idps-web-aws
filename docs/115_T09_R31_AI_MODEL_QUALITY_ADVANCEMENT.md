# T09 R31 — AI model quality

**Hai pilot đã huấn luyện xong. Giữ B16 vì cả hai biến thể giảm recall trong ngân sách FPR đã khóa.** Biến thể so cặp trong cùng nguồn giảm macro recall **5,20 điểm phần trăm**, còn biến thể so cặp giữa các nguồn giảm **1,76 điểm**. Không đủ điều kiện chạy full FIT, đổi ngưỡng hay phát hành model. Run **t09-r31-ranking-YQPyf0ay**. [Kết quả đầy đủ](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/pilot.json)

## Giả thuyết và thí nghiệm

Trong R30, WAF TUNING có sáu URI100 mixed-label groups, gồm 25 dòng anomalous. Cận hồi cứu ở FPR 0% trên frame WAF là 99,32% recall, trong khi B16 đo 54,33% tại cutoff TUNING chung. Điều này cho thấy ranking ở đuôi benign là một đích tối ưu đáng kiểm tra riêng. Một thay đổi threshold theo method đã cho gain bằng 0. R31 kiểm thử thay đổi thứ tự score trực tiếp. Tối ưu một phần đường ROC là động lực cho surrogate này. [R30](/home/trung/projects/idps-web-aws/docs/114_T09_R30_DATA_AND_MODEL_QUALITY_BREAKTHROUGH.md) · [Narasimhan và Agarwal, ICML](https://proceedings.mlr.press/v28/narasimhan13.html)

Giữ frozen backbone, URI100 và checkpoint B16 step 400. Huấn luyện một readout tuyến tính 204 hệ số trên hidden representation để cộng hiệu chỉnh vào log odds attack-vs-benign. Hai arm cố định so cặp positive với hard negative ở cùng nguồn hoặc ở cả ba nguồn. Loss pairwise logistic ưu tiên 5% đuôi benign theo trọng số FIT và phạt dịch điểm quá xa B16. Hai lượt cố định gồm chọn hard negatives theo B16 và chọn lại theo readout sau vòng đầu. Từng lượt ghi checkpoint. Phương pháp này là surrogate có lấy mẫu đuôi.

- FIT gồm **12.456 WAF**, **1.745 Notes** và **31.516 SR-BH**, tổng **45.717** dòng hoặc đại diện FIT kế thừa. Sau gom vector/nhãn có **42.481 weighted cells**. Dùng trọng số WAF pilot đã khóa, cân nguồn/lớp, giữ cả hai nhãn trong mixed vectors. Nhánh WAF có 46 mixed vectors, Notes có hai và SR-BH có 0 trong FIT sử dụng.
- **11.082 publisher TUNING rows** dùng cùng B16 và hai arm. Mỗi arm dùng một cutoff strict lớn hơn, chọn ở FPR thực nghiệm ≤1% theo cả original-request và vector-balanced trên từng nguồn. Advance cần macro gain ít nhất 5 điểm, giảm không quá 2 điểm trên từng nguồn và phép chuyển cutoff cải thiện trong cap 1%.
- Input SHA, checkpoint và code khóa trước huấn luyện. CAL_FIT, CAL_OP, protected TEST, Notes TEST đã exposed và PKDD stress không tham gia chọn arm hoặc ngưỡng. Organization X không có nhãn, còn FPAD đã có shortcut theo định dạng target, nên pilot dùng ba cohort FIT đã có. [Kế hoạch và SHA input](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/plan.json)

## Kết quả cùng ngân sách FPR

| Nguồn TUNING | Normal / anomalous | Recall B16 | Recall cùng nguồn | Recall khác nguồn | FPR request / vector của cả ba |
| --- | ---: | ---: | ---: | ---: | ---: |
| WAF | 2.385 / 3.657 | **54,33%** | 50,72% | 51,46% | 0,46% / 0,84% |
| Notes | 218 / 56 | **89,29%** | 87,50% | **89,29%** | 0% / 0% |
| SR-BH | 676 / 4.090 | **89,00%** | 78,80% | 86,58% | 0% / 0% |
| Macro request recall | 11.082 dòng | **77,54%** | 72,34% | 75,78% | |

Tại cùng 11 false positives trên WAF, B16 flag 1.987 anomalous, arm cùng nguồn flag 1.855 và arm khác nguồn flag 1.882. AP WAF của arm khác nguồn tăng từ **0,8901 lên 0,8956** trong khi recall ở cutoff giảm 2,87 điểm. Loss FIT giảm ở cả bốn lượt tối ưu. Cả bốn chạm cap 70 iteration, với 23–24 hard-negative representatives phân biệt mỗi nguồn/lượt. Thí nghiệm chứng minh phần cải thiện loss và AP quan sát được chưa chuyển thành cải thiện recall ở vùng FPR thấp. Kết quả giới hạn ở frozen readout và ngân sách này. [Checkpoint và loss](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/acceptance.json)

Trong phép chuyển cutoff, mỗi arm lấy ngưỡng từ hai TUNING sources rồi đo trên nguồn thứ ba. Ngưỡng bỏ WAF cho FPR WAF theo vector **3,91% B16, 2,63% cùng nguồn và 3,65% khác nguồn**. Cả hai cách học readout giảm phần lệch này nhưng vẫn vượt 1% và giảm macro recall transfer lần lượt **5,00** và **1,07 điểm**. Ba nguồn đều có FIT trong nghiên cứu, vì vậy đây là chuyển ngưỡng giữa nguồn development, chưa phải unseen-source generalization. Notes CAL_OP 28,13% recall và PKDD 10,69% FPR chỉ là số lịch sử R26.1. [Metrics transfer](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/pilot.json) · [R26.1](/home/trung/projects/idps-web-aws/docs/109_T09_R261_AUTONOMOUS_RECOVERY_AND_MODEL_QUALITY.md)

## Model và dữ liệu native

Kết luận **KEEP_B16**. Full training 0 lượt vì lợi ích trên FIT chưa giữ được ở TUNING, recall giảm ở WAF/SR-BH và chuyển cutoff chưa đạt cap. Giữ B16 400.256 tham số cho nghiên cứu, RI v2 mặc định và R20 shadow. Calibration mới, export, parity và runtime acceptance cho model mới chưa có ứng viên để thực hiện.

Handoff phòng thủ mới vẫn vắng. Bộ đếm native chính thức **TRAIN / DEV / CAL_FIT / CAL_OP / TEST_SHADOW = 0 / 0 / 0 / 0 / 0**. R31 kiểm trạng thái inbox một lượt. Cohort đại diện hai lớp với verified outcomes, receipt trước cutoff, lineage và custody độc lập vẫn là điều kiện thiếu để đo 90% recall và 1% FPR theo T07. Bằng chứng cùng request với rule cũng còn thiếu. [Protocol T07](/home/trung/projects/idps-web-aws/docs/53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

## Vận hành và bàn giao

- **2 regression PASS**, kiểm gradient khi hard negative lặp do trọng số và giữ khối lượng đuôi đúng. Ruff và Git diff check PASS. [JUnit](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/tests.xml)
- Resource Adapter **COMPLETED**, exit 0. Worker 20,08 giây, phần pilot 16,98 giây. Kernel quota 75% một CPU, RAM 768 MiB. Mẫu nhiệt khi admission 56°C và mẫu cuối 62°C, policy 90/100°C và hardware protection giữ nguyên. Cleanup PASS theo unit và cgroup. Bốn Local services giữ PID/restart count. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/acceptance.json)
- Bảo toàn 34 file sửa sẵn, SHA B16/R20 và 265 artifact đã index từ R27–R30. Commit kỹ thuật **ac4e921**. Bàn giao có 21 file private, checkpoint của cả bốn lượt, code/data pins và log. Có các dependency nghiên cứu lịch sử trong workspace. Clean checkout độc lập với các dependency đó chưa được kiểm. [Manifest SHA](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/artifact-index.json) · [Push readback](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r31-ranking-YQPyf0ay/git-push.json)

Bước có giá trị nhất là lấy một cohort phòng thủ hai lớp có thêm body hoặc history đã chứng minh thật sự sẵn sàng trước cutoff. Đo xem tín hiệu mới có phân biệt những request cùng URI100 hay không, sau đó chạy pilot low-FPR theo lineage và đối chiếu cùng rule. Thêm epoch vào readout hiện tại chưa có cơ sở từ kết quả R31.
