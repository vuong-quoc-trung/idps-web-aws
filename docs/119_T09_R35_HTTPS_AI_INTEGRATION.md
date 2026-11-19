# R35 — Tích hợp HTTPS và chuẩn bị huấn luyện AI-IDPS

**Đã nghiệm thu tích hợp Local trong môi trường cô lập.** Hai GET thật đi qua HTTPS, Student Web/H2 và Suricata. Rust xác minh được hai transaction trên cùng kết nối và tính được hai score shadow trước cutoff. Chỉ một request có đủ ba nguồn tại cutoff. Pipeline huấn luyện, export và nạp ONNX đã chạy trên dữ liệu WAF có quyền sử dụng. Huấn luyện native HTTPS và promotion vẫn **BLOCKED** vì chưa có cohort hai lớp được tiếp nhận độc lập.

## Git và tương thích dữ liệu

| Thành phần | Commit hoặc quyết định |
|---|---|
| Điểm tách, nhánh AI R34 | `feature/ai-idps-shadow-integration` · `0cde3f0bc86cbb677554e7143ac45c6f699a0767` |
| Nhánh HTTPS | `feature/https-end-to-end` · `39945a4814248851c717e93a81373fbc9d98967a` |
| Merge hai parent theo thứ tự trên | `ee2c984e05b2218d214a02665578a68ce9e64721` |
| Nhánh bàn giao | `feature/ai-idps-https-ml-integration` |
| Các commit triển khai | `5cb5d03` phụ thuộc cho checkout sạch, `0173638` shadow tại HTTPS edge, `45ce72b` kiểm tra exit của worker, `8f37b0c` training/handoff, `8e674d2` nghiệm thu và replay |

Worktree riêng giữ nguyên 34 file tracked đã sửa ở worktree nguồn. SHA-256 của toàn bộ tracked diff trước và sau là `1f145523851a18310fafc73273e8c8fc7a1f18569bec65cad1771c94260c708f`.

Xung đột văn bản nằm ở firewall Rust. Merge giữ quyền điều khiển của kiến trúc HTTPS tại entry point, cả enqueue trong transaction, worker và restore. Đồng thời vẫn kiểm tra yêu cầu trùng, cooldown và pending unblock. Cổng Hybrid manual kiểm tra quyền thực thi trước khi ghi. Local egress chưa chứng minh IP gốc sẽ không tạo đề xuất hành động nhắm vào IP đó.

Hai nhánh còn có xung đột ngữ nghĩa ở migration 0014. Giữ nguyên các migration HTTPS 0014–0017. SQL Hybrid cũ được chuyển sang 0018. Checkout mới và nâng cấp từ lịch sử HTTPS đi theo SQLx bình thường. DB đã chạy 0014 của nhánh AI cần dừng migrator, sao lưu và dùng script rekey có kiểm tra checksum, sau đó mới chạy migration. Bài test PostgreSQL bao phủ cả lịch sử AI cũ. R35 chỉ thực hiện chuyển đổi trên DB dùng một lần. [Script chuyển đổi](../security-web/scripts/rekey-ai-hybrid-migration.sql) · [Kết quả PostgreSQL](../ai-training/contracts/https-shadow-r35/evidence/postgres.jsonl)

## Luồng HTTPS, identity và quyền thực thi

Client kiểm tra CA/SAN của NGINX edge. Trên leg HTTP riêng đã giải mã, edge giữ `proxy_bind 127.77.0.1` và đích `127.77.0.2:18080`. Suricata bắt trên leg này bằng AF_PACKET. Egress xác minh proof njs/HMAC trước khi proxy qua TLS có xác thực upstream tới đầu nhận Student. App thật dùng H2 riêng và tạo Student Audit. Trong lab, TLS phía Student kết thúc ở proxy Student trước khi vào Java trên loopback. Khóa proof chỉ đọc được theo ownership/gid yêu cầu. Rust ràng buộc request ID với receipt, sensor generation, flow và transaction. Hai transaction keep-alive có cùng flow ID nhưng tx ID riêng.

AI thử nghiệm lấy method, target gốc trong bộ nhớ và request ID do edge cấp ngay tại dispatch qua mirror chỉ dành cho HTTPS API. Socket Unix kiểm tra UID của peer. Socket tạo với mode 0600 trong thư mục private. Lượt live dùng UID bên trong user namespace. Trước khi bật mirror ở host có service account riêng, cần kiểm chứng quyền kết nối của đúng NGINX worker cùng quyền riêng biệt của kho evidence. Renderer chỉ thêm mirror khi bật `--https-ml-shadow` ở chế độ AI enabled. Body, cookie và các header client không được sao chép vào mirror. Receiver ghi vector đã lọc và metadata vào SQLite, phát hiện receipt trùng hoặc mâu thuẫn. Thiếu scorer, dữ liệu lỗi hay score đến muộn dẫn tới abstain. Dòng telemetry `nginx-ai-1` sau request tiếp tục phục vụ RI v2. Model URI100 ở shadow không có đường cấp phép ban. [Cấu hình mirror](../security-web/nginx/https-shadow-mirror.conf) · [Receiver](../ai-training/contracts/https-shadow-r35/receiver.py)

## Nghiệm thu trên request thật

Có **4 GET trong hai lượt tích hợp**. Lượt đầu gồm hai GET và phát hiện hash khác nhau giữa `-0.0` và `+0.0`. Sau khi chuẩn hóa signed zero khi băm float32 little-endian, hai GET mới cho kết quả dưới đây. Test TLS và MockMvc được đếm riêng. Cả hai GET cuối có chung sensor generation `2bc7f99020a41db5f7a9263c82f5bce8` và flow `582206122571814`.

| GET và trusted ID | HTTP / thời gian | Shadow sẵn sàng sau dispatch | Source mask tại 1.000 ms, guard 1 ms | RI v2 và Hybrid replay |
|---|---:|---:|---|---|
| `/api/auth/csrf` · `9fd06b1000e9acc00eab18a950288d2a` · tx 0 | 200 / 1.041,727 ms | 127,060 ms | **NONE** | 0,003709 · **ALERT** với rule canary thụ động |
| `/api/auth/me` · `ea0e76a637073aaa4e089dedc78936f9` · tx 1 | 401 / 100,712 ms | 7,594 ms | **NSA** | 0,003709 · **LOG_ONLY** |

Oracle kiểm nội dung CSRF và session của GET đầu trong bộ nhớ. GET thứ hai xác nhận yêu cầu xác thực đối với client ẩn danh. Hai request có hai Audit event ID riêng. Khi thu đủ evidence sau response, cả hai có structural NSA. Ở GET đầu, cả completion NGINX, Student Audit và proof Suricata đã xác minh đều đến sau cutoff. Điểm URI100 sớm là telemetry nghiên cứu. Theo T07, mask NONE vẫn abstain ở quyết định đa nguồn tại cutoff. Hai request tạo **một** vector URI100 duy nhất và cùng score shadow **0,4998559**.

Replay đưa input RI v2 đã redacted và rule gắn đúng transaction vào code Hybrid Rust. Rule SID 9100035 là canary lành tính ở tx 0. Rust trả ALERT ở tx 0, LOG_ONLY ở tx 1, AI_UNAVAILABLE khi mô phỏng mất RI. Không có hành động thực thi. Verifier Rust chạy theo batch trên proof thật, thời điểm S đủ điều kiện là lúc verifier hoàn tất. Đây là bằng chứng correlation trên đường truyền và replay sau quan sát. Continuous ingest của daemon triển khai, end-to-end enforcement trên firewall host và triển khai AWS vẫn chưa được nghiệm thu ở R35. [Receipt, clock và tx](../ai-training/contracts/https-shadow-r35/evidence/live.json) · [Vector và provenance](../ai-training/contracts/https-shadow-r35/evidence/observations.jsonl) · [Kết quả replay](../ai-training/contracts/https-shadow-r35/evidence.json)

## Kiểm thử vận hành và phục hồi

| Phạm vi | Bằng chứng |
|---|---|
| TLS/routing | 2 test TLS edge, 2 test HTTPS upstream gồm sai identity, hai GET thực trong network namespace chỉ có loopback |
| Student Web | Hai test MockMvc/H2 đạt cho quyền trên dữ liệu lớp và login/CSRF/logout/session. 184 class cùng hai cấu hình ứng dụng trong JAR live trùng byte với bản build checkout. |
| PostgreSQL, Hybrid, ban/unban | 12 nhóm lọc Rust, 38 lượt chạy test trên các test binary, có lặp. Bao phủ phân quyền, verdict, prevention simulation, migration, restart cursor, correlation, restore/unblock. Actuator mô phỏng và DB thật dùng một lần. |
| Rollback và guard triển khai | 15 test staging/rollback, 7 + 3 test guard đạt. Chưa áp dụng nftables theo UID trên host. Bỏ tùy chọn mirror và dùng bundle HTTPS/backup đã xác minh để hoàn nguyên staging. |
| AI và phục hồi | 2 test projector Rust, 67 test Python resource/thermal/receiver/native. Restart scorer giữ digest và score, input malformed trả ABSTAIN. Phép so sánh Rust và Python ONNX trên từng GET có sai số 0. |
| Tài nguyên | Mỗi unit acceptance tối đa 1 CPU, 2 GiB, swap 0 và 240 giây. Lượt HTTPS cuối chạy 26,423 giây, CPU 24,748 giây, peak 362,1 MiB theo systemd. Smoke training chạy 1,193 giây, CPU 0,867 giây, peak 116,1 MiB. |
| Thermal và cleanup | Khi chạy test Student, kernel quota từ `100000 100000` về `50000 100000` ở 94°C, phục hồi ở 88°C. Unit live exit 0, cleanup xác minh. Bốn service R22 RI/scorer/receiver/collector active, PID giống nhau ngay trước và sau lượt test, restart count 0. |

Một lượt chạy training ghi bundle rồi Adapter trả RUNTIME_CONTROL_FAILURE khi kiểm containment lúc kết thúc. Evidence cũ không đủ xác định chính xác counter gây lỗi ở lượt đó. Bản sửa chỉ xử lý trường hợp toàn bộ cgroup đã bị thu hồi với xác nhận exit, invocation, identity, trạng thái systemd và cleanup. Kiểm thử fail-closed được giữ lại. Lượt kiểm định Adapter thật sau đó trả COMPLETED, exit 0, cleanup verified. [Kết quả Adapter](../ai-training/contracts/https-shadow-r35/evidence/adapter-result.json) · [Student và CPU readback](../ai-training/contracts/https-shadow-r35/evidence/student.json) · [Rollback](../ai-training/contracts/https-shadow-r35/evidence/rollback-stage.log)

Khi bàn giao, host có thời điểm boot 16:32 ngày 19/11/2026 (UTC+7), sau cửa sổ test. Cả bốn service R22 đã active từ 16:32:35 với PID mới, mỗi service có NRestarts=0 trong lần boot hiện tại. Kết quả này áp dụng cho các service R22 đang phục vụ. [Trạng thái khi bàn giao](../ai-training/contracts/https-shadow-r35/evidence/host-handoff.json)

## Dataset, model và kết quả training

Giữ ABI URI100 v1 gồm 76 đặc trưng method/URI và 24 đặc trưng cấu trúc path/query. Schema khóa thứ tự, dtype và quy tắc băm. Không đưa response, Oracle, rule, status code hoặc lệnh ban vào vector. Body B16, Context20/22, session/history và thông tin actor/resource cần một contract riêng chứng minh dữ liệu đến trước cutoff, có quyền sử dụng và có giá trị bổ sung. [Schema](../ai-training/contracts/https-shadow-r35/schema.json)

| Cohort | FIT | TUNING | CAL | TEST |
|---|---:|---:|---:|---:|
| WAF publisher TRAIN đã đóng băng tại R32 | 12.456 (2.756 normal) | 6.042 (2.385 normal) | 0 | 0 |
| HTTPS native đã admission trong R35 | 0 | 0 | 0 | 0 |

WAF có 9.367 vector FIT riêng biệt, tổng trọng số FIT 9.766,122 và 0 group/vector overlap với TUNING. Task giữ nhãn publisher normal/anomalous. Logistic smoke có 101 tham số. Trên TUNING, tại ngưỡng 0,868940 chọn trên chính TUNING, **AP 0,92388, recall 41,07%, precision 98,49%, FPR 0,9644%, Brier 0,18219**. TP 1.502, FP 23, TN 2.362, FN 2.155. Các số liệu này mô tả development WAF. R35 chưa đo recall/FPR trên HTTPS native độc lập.

Export ONNX opset 17 dùng CPU. Sai số lớn nhất Python/ONNX trên toàn TUNING là 2,69 × 10⁻⁷. Model SHA-256 `4777557bdb0307b09dcac8caec01e0b49c4181bb834cd1630aeb21f0a35f9137`. Hai lần tạo bundle cho cùng SHA. Khi resume sau fit, inode, mtime và kích thước cả model và manifest giữ nguyên. Runner kiểm pin dataset, trainer, receiver và model. R35 chứng minh resume tại ranh giới fit đã commit. [ONNX và manifest](../ai-training/contracts/https-shadow-r35/bundle/manifest.json) · [Smoke](../ai-training/contracts/https-shadow-r35/evidence/smoke-final.log) · [Resume](../ai-training/contracts/https-shadow-r35/evidence/smoke-resume.log)

## Tái lập và bước R36

Từ root của checkout, đặt `PY` trỏ Python của môi trường AI có sklearn, ONNX, ONNX Runtime và `WAF_R32` trỏ NPZ R32 được ủy quyền. Trainer khóa SHA dataset `57960dea5e8a15110d51abb1c342d577d7b1a45b4cdf38577f1a3224495579f3`. `OUT` là thư mục bundle mới của run.

```sh
(cd ai-training/contracts/https-shadow-r35 && sha256sum -c SHA256SUMS)
R35=ai-training/contracts/https-shadow-r35
"$PY" "$R35/guard.py" -- "$PY" "$R35/train.py" "$WAF_R32" "$OUT"
```

Chạy lại cùng lệnh và thư mục để kiểm checkpoint đã commit. `live.py` nhận dependency và output riêng cho namespace lab. `replay.py` nhận bundle, hai receipt đã thu cùng scorer, RI v2 và binary test Hybrid. Digest của binary thực dùng, kết quả theo request và log đã loại bỏ dữ liệu nhạy cảm có trong [chỉ mục evidence](../ai-training/contracts/https-shadow-r35/evidence.json). Khóa TLS/HMAC, token CSRF, cookie, raw traffic và DB nghiệp vụ không được xuất bản.

**TRAINING_READY** cho development smoke WAF. **TRAINING_BLOCKED** cho native HTTPS. **PRODUCTION_PROMOTION = BLOCKED**. Bước R36 là tiếp nhận một cohort HTTPS hai lớp đã review độc lập và được phép dùng trước khi chạy full training. Chốt vai trò và nhóm theo campaign trước khi thu, khóa request ID, receipt, provenance, cutoff, source masks, semantic label và lineage. Kiểm tra exact/near-duplicate cùng protected registry theo T07. Custodian xuất canonical TRAIN có FIT/TUNING với cả hai lớp, kèm SHA ở kênh tin cậy. `train.py --native-handoff-sha` đã có đường nạp cho phép chạy ngay sau admission. Sau khi có candidate, khóa candidate trên DEV, tách CAL_FIT/CAL_OP, giao TEST_SHADOW độc lập cho custodian và đo recall/FPR, abstention, calibration cùng latency theo profile. Chỉ mở gate promotion khi có bằng chứng đạt yêu cầu. [Native intake](../ai-training/contracts/https-shadow-r35/native.py) · [Giao thức T07](../ai-training/contracts/evaluation-v1/protocol.json)
