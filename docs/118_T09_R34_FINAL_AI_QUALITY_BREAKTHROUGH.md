# T09 R34 · Giá trị phát hiện của cấu trúc HTTP và ngữ cảnh đăng nhập

**R34 đã hoàn tất hai thí nghiệm phòng thủ. Chưa có model đạt recall ≥90% tại FPR ≤1% trên cohort độc lập theo T07.** B16 tiếp tục là ứng viên nghiên cứu payload. RI v2 phục vụ Hybrid và R20 chạy shadow. Kết quả chính của R34 là đo được giá trị của trường body và chỉ ra một trường hợp cụ thể khiến ngưỡng báo động khi đăng nhập mất khả năng chuyển nguồn.

## Phạm vi quyết định

| Tác vụ | Bằng chứng và cách đánh giá |
|---|---|
| Payload HTTP | So sánh theo cùng original request có nhãn publisher trên WAF, Notes và SR-BH. Đối chứng gồm R20, B16 và rule kiểm tra kiểu trường. |
| Lạm dụng tài khoản | Một login có cờ takeover từ nguồn RBA được đối chiếu với lịch sử tài khoản và tần suất ngữ cảnh trước thời điểm login. Nhóm tham chiếu là các login không được nguồn gắn cờ. |
| Hành vi HTTP và bot | R33 đã đo lịch sử điều hướng. Các nhãn tự động hóa và red-team của R33 giữ nguyên phạm vi riêng. |
| Vi phạm phân quyền | Context20/22 và policy có thể phân biệt một số quan hệ actor–resource. Kết quả Oracle sau response chỉ dùng xác minh nhãn. Một quyết định đúng của rule thuộc về rule. |

Mỗi nhánh có schema, quyền dùng dữ liệu và mẫu số riêng. Một verdict ở Hybrid cần các điểm AI, rule, nguồn và Oracle trên cùng request. Ba nguồn publisher HTTP thiếu input đầy đủ cho RI v2 và Hybrid. Sáu receipt Local cho phép đối chiếu vận hành, còn số positive đã xác minh trên roster Local này bằng 0. [T07](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md) · [Context xác thực](110_T09_R262_CONTEXT_AWARE_NATIVE_AI_QUALITY.md) · [R33](117_T09_R33_AI_INTELLIGENCE_BREAKTHROUGH.md)

## Payload HTTP

R34 giữ nguyên tọa độ FIT/TUNING của R32, tái tạo URI76 từ từng record, kiểm SHA nguồn và kiểm tra giao URI100 giữa các partition. Pilot có **45.717 FIT và 11.082 TUNING**. Bộ chiếu thêm 142 thống kê hữu hạn cho query và body. Chúng mô tả vai trò trường công khai, kiểu giá trị, trường lặp, kiểu mâu thuẫn và cấu trúc lồng. Dữ liệu thiếu giữ trạng thái thiếu. Nhánh bổ sung của B16 quay về điểm gốc khi không quan sát được trường. [Bộ chiếu](../ai-training/contracts/context-quality-r34/field_schema.py) · [Thí nghiệm](../ai-training/contracts/context-quality-r34/http_study.py)

| Mô hình | Recall WAF | Recall Notes | Recall SR-BH | Macro recall |
|---|---:|---:|---:|---:|
| R20 | 0,00% | 0,00% | 0,00% | 0,00% |
| B16 | 54,33% | 89,29% | 89,00% | 77,54% |
| Rule kiểm tra kiểu | 0,00% | 1,79% | 0,00% | 0,60% |
| Logistic trên trường có kiểu | 0,52% | 1,79% | 0,00% | 0,77% |
| B16 + logistic hiệu chỉnh score | 54,44% | 89,29% | 89,00% | 77,58% |
| B16 + cây boosting | 54,47% | 89,29% | 89,02% | 77,59% |

Mỗi hàng dùng một ngưỡng riêng. Cả ba nguồn đều phải nằm trong cùng ngân sách FPR 1% theo request và vector. Ngưỡng thực nghiệm của R20 bằng 1,0 với phép so sánh strict `>`, nên R20 không phát cảnh báo ở điểm này. Các ngưỡng đang phục vụ tại Local vẫn do manifest R22 quy định. [Kết quả và ngưỡng đầy đủ](../ai-training/contracts/context-quality-r34/r34-evidence.json)

**Thông tin bổ sung có thật nhưng hiếm.** Trong WAF FIT, nhánh mới tách thêm 5 biểu diễn trong nhóm URI100 có hai nhãn và giảm số record thuộc lớp thiểu số trong nhóm trùng từ 96 xuống 92. Trên WAF TUNING, con số giảm từ 13 xuống 12. Chỉ **14/6.042** request WAF TUNING, **2/274** Notes và **0/4.766** SR-BH có tín hiệu body đủ điều kiện. Điều này giới hạn tác dụng thực tế của việc đổi kiến trúc trên cùng roster. [Census theo nguồn và role](../ai-training/contracts/context-quality-r34/r34-evidence.json)

Cây thu hồi thêm 5 positive WAF, 1 SR-BH và 0 Notes so với B16, giữ toàn bộ TP cũ. Trên WAF, FPR theo request là 0,46%, theo vector là 0,84%; recall theo vector đạt 87,79%. Khoảng bootstrap 95% cho chênh lệch recall WAF tại ngưỡng cố định là **[+0,023; +0,360] điểm phần trăm**. Macro chỉ tăng **0,054 điểm**, dưới gate +5 điểm. Khi giữ một nguồn ngoài bước chọn ngưỡng, FPR xấu nhất lên **4,16%**. Khi loại hẳn Notes khỏi cả FIT và chọn ngưỡng của logistic cấu trúc, FPR tại Notes là **5,50%**. Các kết quả này bác bỏ việc full-train nhánh payload theo gate đã khóa. [Kế hoạch đã khóa](../ai-training/contracts/context-quality-r34/plan.json) · [Đối chứng và bootstrap](../ai-training/contracts/context-quality-r34/r34-evidence.json)

## Kiểm chứng Local

Sáu POST lành tính đi qua NGINX trên Unix socket được sở hữu riêng và backend thử nghiệm. Backend đọc body, chiếu vector, tính điểm bằng checkpoint logistic và ghi thời điểm hoàn tất trên đồng hồ monotonic. Cả **6/6** request khớp ID do NGINX cấp, digest receipt khớp, RI v2 và R20 đều có score. Cùng một URI76 cho **4 vector cấu trúc**; cùng giá trị số trong form và JSON cho cùng vector. Cả sáu kết quả đều sẵn sàng trong **999 ms** cho phép. p50/p95 của chiếu và tính điểm là **0,194/0,553 ms**. p50/p95 vòng HTTP là **0,910/2,137 ms**. Đây là sáu phép đo khả dụng tại backend lab. Mirror R22 chưa quan sát body và cả sáu mask đa nguồn ở cutoff có giá trị null. Chưa có bằng chứng cho latency production của nhánh mới. [Probe](../ai-training/contracts/context-quality-r34/local_probe.py) · [Readback](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/local-readback.json)

## Ngữ cảnh đăng nhập và nguồn nhãn

R34 dùng **Login Data Set for Risk-Based Authentication**, v1.0.0 của Wiefling, Jørgensen, Thunem và Lo Iacono, CC BY 4.0. Nhóm ứng cứu của dịch vụ gốc xác định cờ takeover. Bản công bố phục vụ nghiên cứu RBA, đã tổng hợp lại giá trị thuộc tính và thêm ngẫu nhiên vào thời gian. Đích đánh giá ở đây là *truy hồi cờ sự cố do nguồn công bố*. Tần suất cảnh báo ở các login không gắn cờ là một phép đo riêng; nhãn âm native cần quy trình xác minh độc lập. Tác giả cảnh báo về việc áp dụng các giá trị tổng hợp vào IDS production. [Dataset và giới hạn sử dụng](https://zenodo.org/records/6782156) · [Nghiên cứu gốc](https://doi.org/10.1145/3546069)

RBA có hai nhóm đầu vào. Nhóm thứ nhất dùng tối đa năm login cùng tài khoản trong 30 ngày trước đó, đo mức quen thuộc của mạng và thiết bị, khoảng cách thời gian và độ đa dạng. Các anchor đồng thời dùng chung một prefix, lịch sử có thứ tự nhập nhằng dẫn tới ABSTAIN. Nhóm thứ hai chỉ giữ độ hiếm đã chặn biên và cờ khả dụng cho chín nhóm thuộc tính. Bảng tần suất này lấy từ tài khoản FIT trong một phần tư thời gian đầu. Một login có thể dùng bảng ngay ở lần đầu thấy tài khoản nếu thời điểm login đã qua biên chốt bảng. Model không nhận danh tính tài khoản, IP, địa danh, chuỗi user agent, kết quả xác thực, RTT hay cờ attack-IP. Nguồn RBA chỉ chứng minh thứ tự theo timestamp publisher; chưa có receipt Local xác nhận availability ở 999 ms. [Phép chiếu causal](../ai-training/contracts/context-quality-r34/login_data.py)

Tài khoản được gán duy nhất một role. FIT, SELECT, CAL_FIT và CAL_OP chỉ dùng anchor trong 75% thời gian đầu. TRANSFER dùng tài khoản riêng ở 25% thời gian cuối. FIT và SELECT giữ toàn bộ cờ sự cố cùng mẫu hash 1/32 của nhóm tham chiếu. Đánh giá SELECT khôi phục trọng số lấy mẫu; CAL và TRANSFER dùng toàn bộ login trong role và cửa sổ tương ứng. Kiến trúc chọn ở SELECT. Sigmoid đơn điệu, nếu đủ support, fit riêng ở CAL_FIT. Ngưỡng strict được lấy tại CAL_OP với cap tham chiếu 0,5%. Checkpoint, thứ tự cột, code, phép chiếu và các ngưỡng đã khóa trước khi đánh giá TRANSFER. [Huấn luyện và đánh giá](../ai-training/contracts/context-quality-r34/login_study.py)

Bản phát hành đã kiểm checksum gồm **31.269.264 login và 4.304.857 mã tài khoản phân biệt**. Bảng tần suất quá khứ sử dụng 2.211.944 sự kiện FIT. Đây là số đếm theo mã giả danh trong archive. Mỗi mã có thể có số quan sát rất khác nhau.

| Role RBA | Login trong đúng cửa sổ | Login dùng | Cờ takeover dùng |
|---|---:|---:|---:|
| FIT | 6.465.071 | 201.557 | 79 |
| SELECT | 2.014.437 | 62.842 | 21 |
| CAL_FIT | 902.846 | 902.846 | 4 |
| CAL_OP | 1.031.237 | 1.031.237 | 9 |

Đã fit sáu logistic có regularization (support, network, device, history chung, peer, history + peer) và một cây boosting độ sâu 3. Bốn đối chứng deterministic gồm điểm hằng, ASN mới, mức mới so với lịch sử cá nhân và độ hiếm trong quần thể FIT. Tại SELECT, logistic **PEER** phát hiện 13/21 cờ, so với 11/21 của history + peer và 3/21 của cây lịch sử. CAL_OP cho **6/9**, 3.382 cảnh báo trên 1.031.228 login tham chiếu và coverage 65,71%. Cỡ mẫu 4 positive ở CAL_FIT và 9 ở CAL_OP giới hạn ý nghĩa vận hành của calibration. Thời gian tính điểm Python trên vector đã có của PEER là **0,094/0,109 ms p50/p95**, đo ở 128 lượt FIT batch 1 sau lần gọi đầu. [Checkpoint đã khóa](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/login-lock.json)

### Chuyển sang tài khoản và thời gian giữ riêng

Trong **6.245.585 login**, từ **338.426 mã tài khoản**, có **0 cờ takeover**. Recall, AP và khoảng tin cậy recall ở TRANSFER đều không xác định. PEER có điểm cho toàn bộ roster và phát **2.260.865 cảnh báo, 36,20%**. Khi cân bằng theo 5.887.562 vector ngữ cảnh riêng, tỷ lệ này là **38,25%**. Rule độ hiếm toàn cục phát cảnh báo trên **39,77%**. Cây lịch sử có tỷ lệ **0,0325%**, nhưng roster thiếu positive để đánh giá độ nhạy của cây. [Kết quả chuyển miền đã khóa](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/login-transfer.json)

**Độ tập trung giải thích sự thất bại của ngưỡng.** Một mã giả danh đóng góp **5.398.464/6.245.585 login** và **2.256.961** cảnh báo PEER. Trên 847.121 login của phần còn lại, cùng ngưỡng phát 3.904 cảnh báo (**0,461%**). Bootstrap 400 lần theo tài khoản cho khoảng 95% tỷ lệ cảnh báo toàn roster **[0,43%; 39,77%]**. Mã xuất hiện nhiều nhất vẫn nằm trong mẫu số chính. Cờ nguồn bằng 0 không đủ để kết luận các cảnh báo là false positive đã xác minh, hoặc mọi login của mã đó thuộc một người thật. [Phân tích theo actor và độ sâu lịch sử](../ai-training/contracts/context-quality-r34/r34-evidence.json)

### Kiểm tra thăm dò phần có sự cố

Sau khi quan sát TRANSFER thiếu positive, R34 khóa thêm một phép đo trên **toàn bộ** giai đoạn sớm của đúng nhóm tài khoản giữ riêng. Hai head và hai ngưỡng vẫn là phiên bản đã chọn trước TRANSFER. Cửa sổ sớm có 11.215.366 login, 691.170 mã, 27 cờ sự cố thuộc 26 mã. Chỉ 19/27 cờ có tín hiệu peer; tính recall trên toàn bộ 27 ca. Cửa sổ này chia sẻ tập actor với phép đo chính và được đề xuất sau khi biết số ca ở TRANSFER. Vai trò của nó là chẩn đoán. [Kế hoạch và SHA trước khi chạy](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/early-actor-lock.json) · [Evidence](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/early-actors.json)

| Trên cùng 11.215.366 login | Sự cố phát hiện | Effective recall | Cảnh báo trên nhóm không gắn cờ |
|---|---:|---:|---:|
| Rule độ hiếm PEER_NOVELTY | 5/27 | 18,52% | 1.122.732 (10,01%) |
| Logistic PEER | 8/27 | 29,63% | 1.304.085 (11,63%) |

AI tìm thêm **3 cờ sự cố** và giữ được cả 5 ca rule đã phát hiện. Đổi lại, AI làm tăng ròng **181.353** cảnh báo tham chiếu. Hai tỷ lệ đều vượt 1% ở ngưỡng đã khóa, nên kết quả chưa chứng minh lợi thế AI ở cùng FPR vận hành. Khoảng bootstrap theo tài khoản cho recall PEER là **[13,03%; 45,45%]**, cho tỷ lệ cảnh báo là **[0,32%; 13,69%]**. Nâng độ phức tạp của model không giải quyết được số ca xác nhận ít, alias tập trung và thiếu một bộ CAL đại diện. [So sánh paired, AP và coverage](../ai-training/contracts/context-quality-r34/r34-evidence.json)

## Runtime, khôi phục và tái lập

- Lần tải ngày 18/11 kết thúc cùng lúc host shutdown. Receipt lịch sử ghi `GUARDIAN_EXIT_WITHOUT_RESULT` và cleanup thành công. Ngày 19/11, run mới kiểm lại SHA của 38 phần đã tải (637.534.208 byte), chỉ tải phần thiếu, sau đó đối chiếu checksum toàn archive. SHA-256 nguồn là `ca1d974e97aebfb30878a613f4ca5c793860a98ba2acb5185c9bc610d7432a33`. [Đối soát hai boot](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/predecessor.json) · [Manifest nguồn](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/source.json)
- Một bucket chứa **14.194.928** login. Guardian freeze phép chiếu ban đầu ở giới hạn RAM 1.536 MiB. Worker thuộc run được kết thúc và Adapter giữ receipt `RUNTIME_CONTROL_FAILURE`, cleanup PASS. Bản sửa tiếp tục từ 93 shard đã kiểm SHA, chia phần lớn thành block 65.536, giữ sáu quan sát biên để tính đúng năm sự kiện trước, xử lý các mốc trùng thời gian và đối soát toàn bộ record. So với phép sort toàn actor trên fixture, vector và mask khớp từng dòng. Worker mới dùng lại cùng giới hạn và hoàn tất trong **40,4 giây**. [Receipt lần lỗi](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/adapter-project/result.json) · [Bản sửa](../ai-training/contracts/context-quality-r34/bounded_project.py) · [Receipt khôi phục](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/adapter-project-bounded/result.json)
- Resource Adapter trả `COMPLETED` cho HTTP, Local, tải nguồn ở run mới, ETL, phép chiếu đã sửa, training, TRANSFER và kiểm tra thăm dò. Training mất **12,9 giây**, TRANSFER **37,2 giây**. Worker TRANSFER có RAM peak khoảng **1.751 MiB**. Ở mẫu cuối của kiểm tra bổ sung, guardian đọc **96°C**, giảm quota 85% xuống **42,5% của một CPU**, kernel báo `42500 100000`. Tất cả worker đã cleanup. Bốn service Local active với cùng PID từ đầu tới cuối run sau reboot, `NRestarts=0`. [Telemetry](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/adapter-early-actors/status.json) · [Resource readback](../ai-training/contracts/context-quality-r34/r34-evidence.json)
- **34 test PASS**, gồm 11 ca R34 và 23 regression R32/R33. Kiểm lại SHA của **34 tracked file đã có thay đổi** trước R34. Hai commit triển khai là `a714223` và `a71f0e4`; mã và bằng chứng được bàn giao trên nhánh `feature/ai-idps-shadow-integration`. Run chính là `t09-r34-reconciled-wir_bfhv`. Checkpoint logistic/cây đăng nhập SHA-256 `91c04e3b3688ec04428347b88380c35c00d74fa9f8897804e4ec32cd937ee23d`; checkpoint cây HTTP `ec11077e7a12a5e9a80c3b92b6eca6bf0f4ae0a81fcabacc712ae067e96713e4`. Index riêng trong workspace có **628** digest. Git chứa mã, kế hoạch, metrics tổng hợp và SHA. [Regression](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/regression.xml) · [Checkpoint và SHA](../ai-training/.artifacts/t09-r34-reconciled-wir_bfhv/artifact-index.json) · [Evidence công bố](../ai-training/contracts/context-quality-r34/r34-evidence.json)

## Quyết định T07 và bước tiếp theo

**Nghiên cứu R34 hoàn tất. Production và GitHub Release vẫn BLOCKED.** Với payload, trường có kiểu tách được một số va chạm B16, nhưng phạm vi quan sát quá nhỏ và chuyển ngưỡng làm vượt ngân sách FPR. Với login, so sánh với phân bố quá khứ có giá trị hơn phần lịch sử ngắn trên SELECT; khi thời gian và tập tài khoản đổi, tỷ lệ cảnh báo thay đổi mạnh. Không có ứng viên mới vượt cả hai mục tiêu trên roster development chung đủ support. Các checkpoint tiếp tục nằm ở research. Parity và rollback đã có của model đang chạy vẫn là bằng chứng của chính model đó; R34 chưa cấp chứng nhận ONNX/Rust, Hybrid hoặc AWS cho head mới.

Không xuất hiện `index.json` hoặc `handoff.json` mới trong inbox R29. Native formal **TRAIN/DEV/CAL_FIT/CAL_OP/TEST_SHADOW = 0/0/0/0/0**, số ATTACK_VERIFIED mới bằng 0. Sáu POST Local cho bằng chứng vận hành. Tập RBA cho một nhiệm vụ xác thực khác với dữ liệu phiên được tổng hợp. AIT-LDS v2.1 cũng có access log và nhãn theo dòng từ tám testbed mô phỏng; chỉ kiểm metadata, chưa đưa vào FIT. Cả hai nguồn bên ngoài đều thiếu bộ request production đã được phân xử độc lập cho mục tiêu T07. [Defensive handoff](../ai-training/contracts/defensive-handoff-r29/README.md) · [AIT-LDS v2.1](https://zenodo.org/records/19483937) · [Evaluation Protocol](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

**Bước có giá trị nhất** là tiếp nhận một cohort defensive hai lớp trên cùng workflow đăng nhập, có request ID, actor/session scope, nguồn và bằng chứng trước 999 ms, kết quả điều tra độc lập và benign được lấy mẫu đại diện. Cần ghi rõ alias dùng chung hoặc không xác định; giữ cả request của alias lớn trong thống kê tải. Chia theo actor, môi trường và thời gian trước khi chọn ngưỡng. Phép thử đầu tiên là so sánh PEER với rule đã khóa trên cùng request và cùng ngân sách cảnh báo. T07 yêu cầu tối thiểu 200 benign, 50 attack và 10 nhóm riêng mỗi lớp ở CAL slice bắt buộc; TEST cần số cụm độc lập tương ứng mức tin cậy và số endpoint đã đăng ký. Đây là điều kiện còn thiếu để đánh giá mục tiêu recall 90% tại FPR 1% và giá trị tăng thêm của AI cho Hybrid.
