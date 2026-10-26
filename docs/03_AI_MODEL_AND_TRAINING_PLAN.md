# 03 — Thiết kế AI và training theo ca 2–3 giờ

**Ngày thiết kế:** 26/10/2026. **Trạng thái toàn bộ phần triển khai trong tài liệu:** ĐỀ XUẤT, chưa có trainer, inference service, model hoặc checkpoint được tạo. Hiện trạng code và data ở [00](00_PROJECT_OVERVIEW_AND_PROGRESS.md), [01](01_SYSTEM_AUDIT_AND_ARCHITECTURE.md), [02](02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md).

**Foundation update26/10/2026:** đã có exporter/canonical metadata cho successful reads/sessionHMAC/requestID/UA/HTTP/flow, nên các mô tả thiếu metadata ở baseline bên dưới cần đọc cùng02 hiện hành. Vẫn chưa có corpus có nhãn, causal ML feature library, payload được phép train, trainer hoặc model; mọi kiến trúc neural/checkpoint/stage của tài liệu này vẫn là thiết kế, chưa có giờ train được ghi nhận.

## 1. Bài toán và lựa chọn ban đầu

Không thể khẳng định một kiến trúc “tối ưu nhất” khi chưa có corpus đại diện, CPU SKU và benchmark. Lựa chọn khởi đầu phù hợp repo là **mô hình nhỏ theo từng loại quan sát**, CPU-first, tách khỏi đường HTTP ứng dụng và khỏi executor firewall. Phải so sánh với rule-only và baseline đơn giản trước khi chấp nhận neural model.

Đầu vào audit hiện tại thiếu successful GET, payload, session identity và request correlation. Vì thế không thể lấy dữ liệu hiện có rồi hứa mô hình bắt đủ chuỗi hành vi/payload/flow. Dùng các tier dữ liệu theo 02; chỉ kích hoạt nhánh model khi source/features của nhánh đó tồn tại và đạt kiểm tra chất lượng.

| Nhánh | Baseline để đo trước | Candidate khi đủ dữ liệu | Vai trò |
|---|---|---|---|
| Payload HTTP đã khử bí mật | Hashing byte/character n-gram + logistic SGD theo mini-batch | Byte-CNN nhỏ, không dùng LLM | Phân loại attempt độc hại/benign và nhóm tấn công; chưa chứng minh khai thác thành công |
| Hành vi audit/proxy | Thống kê cửa sổ + logistic/MLP nhỏ; so với rule ngưỡng | Causal TCN nhỏ cho chuỗi event, head phân loại và head dự báo hành vi tiếp theo | Tần suất, trình tự endpoint, auth failure, truy cập lệch vai trò |
| Bất thường chưa có nhãn | Isolation Forest trên mẫu benign đã duyệt, làm baseline offline | Score dự báo tiếp theo từ TCN hoặc autoencoder nhỏ nếu đem lại ích lợi đo được | Triage/shadow; score bất thường không đồng nghĩa tấn công |
| Network flow | Logistic/MLP nhỏ trên flow chuẩn hóa | Chỉ mở rộng sau khi giữ EVE flow/netflow và đối chiếu feature parity | Phát hiện phụ trợ mạng; không giả lập flow từ bảng audit |

`SGDClassifier.partial_fit` hỗ trợ mini-batch/out-of-core. `IsolationForest.warm_start` thêm cây vào rừng, không phải cơ chế cập nhật online tương đương SGD; không hứa resume optimizer/scheduler cho estimator không có chúng. Tham chiếu chính thức: [SGDClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDClassifier.html), [IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html). Đây là lựa chọn thử nghiệm của dự án, chưa phải kết quả benchmark.

## 2. Kiến trúc neural candidate và ngân sách inference

### 2.1. Payload branch

- Input byte UTF-8, tối đa 1.024 byte mỗi view; giữ raw view và canonical view đã giới hạn decode như 02. Dùng mask, cờ truncation, độ dài gốc. Với payload dài dùng prefix+suffix hoặc vài cửa sổ có giới hạn, không cắt đầu rồi tuyên bố đã kiểm hết payload.
- Byte vocabulary 256 + padding, embedding 16 chiều; Conv1D kernel 3/5/7, khoảng 32 channel mỗi kernel; masked max/mean pooling; hidden 64; sigmoid binary và softmax nhóm known attack. Không đưa token/password/body hồ sơ vào input.
- Candidate khoảng dưới 1 triệu tham số; tính số tham số chính xác khi implement. Khởi đầu batch 32–64 trên CPU, chiều dài cố định, không GPU/NPU mặc định.
- Học trên public HTTP đã xét quyền sử dụng rồi fine-tune bằng student traffic. Mẫu `%`, tiếng Việt, URL/email hợp lệ, rich text hợp lệ, chuỗi SQL trong bài học là hard negatives cần có. Payload ngoài khả năng quan sát được gắn `unavailable`, không gán score 0.

### 2.2. Behavior branch

- Key ưu tiên `session_hmac` + service; có `actor_hmac` và client attribution đi kèm, thống nhất canonical schema 02. Nếu chưa có session, dùng actor/IP với mask độ tin cậy thấp; không coi NAT IP là một người.
- Sliding windows 10 giây, 1 phút, 5 phút tính nhân quả. Input 32–64 event gần nhất gồm endpoint template/method/status/auth outcome/role, time delta, feature tần suất và missing masks. Chỉ dùng event đã xảy ra trước hoặc tại thời điểm quyết định.
- TCN causal 2–3 block, hidden 32–64, dilation tăng dần, pooling causal; head classification và head next-endpoint/status. Huấn luyện next-event trên benign đã duyệt rồi đánh giá anomaly score riêng. Không dự đoán quá khứ bằng dữ liệu cửa sổ tương lai.
- Ban đầu dùng rolling aggregates + MLP; chỉ thêm TCN nếu ablation cho thấy tăng recall ở cùng FPR và vẫn đạt độ trễ. Khởi đầu batch 64–128, không attention lớn. Session state có TTL, giới hạn cardinality và LRU; bị evict phải gắn context incomplete.

### 2.3. Fusion và quyết định

Hard Rules và AI nhận cùng event stream qua hàng đợi riêng. Hard Rules có thể tạo alert/response candidate ngay theo policy; mọi event đủ chất lượng, kể cả **rule âm tính**, vẫn có đường tới AI. Chỉ gửi mẫu rule dương cho AI sẽ làm mất khả năng phát hiện rule miss.

Fusion dùng các score riêng `payload_score`, `behavior_score`, `flow_score`, `anomaly_score`, cùng source availability, quality, rule facts và phiên bản model. Calibration/threshold fit trên calibration split; không cộng score tùy ý rồi gọi là xác suất. Baseline có thể dùng policy minh bạch; logistic stacking chỉ train bằng prediction out-of-fold/holdout phù hợp thời gian, tránh leakage. Điểm thiếu dữ liệu giữ `null` + reason, không điền benign.

AI-only ban đầu chỉ **shadow/alert**. Allowlist, attribution, fresh evidence, TTL, cooldown, cap số block và enforcement mode được xét lại trong response policy; model không trực tiếp gọi `sudo`, không sở hữu credential root. Anomaly đơn độc không tự động chặn.

Các ngân sách sau là **mục tiêu benchmark ban đầu, chưa đo**:

| Hạng mục | Mục tiêu ban đầu | Cách đo |
|---|---|---|
| Payload candidate | Artifact FP32 dưới 10MB; int8 chỉ nếu có lợi | Kích thước bundle thực; không chỉ weights |
| Behavior candidate | Dưới 1 triệu tham số; state bounded | Count tham số + RSS theo số session |
| Inference từng event | p95 dưới 10ms/model, CPU 1–2 thread | Batch1, warm/cold riêng trên máy deploy thật |
| Event đến alert | p95 dưới 2s tại tải nghiệm thu | Timestamp ingest/queue/score/decision/end-to-end |
| AI timeout | Khởi đầu 100ms, retry bounded | Overload/failure tests; không block HTTP/rule pipeline |
| Inference worker | RSS mục tiêu dưới 512MiB cộng state có trần | Đo peak RSS và cgroup trên target |

Mục tiêu độ trễ không thay thế target throughput. Đo baseline RPS và log bytes/s; capacity rule/AI tối thiểu 2 lần tải dự kiến của lab trong kiểm thử bền vững, rồi điều chỉnh. Nếu AI chậm: giảm batch/window/model hoặc phân phối worker; không tăng thread vô hạn trên laptop.

## 3. Giới hạn tài nguyên Zenbook 32GB

### 3.1. Các thông số phải xác nhận ở S0

Ghi CPU model, số logical CPU hiệu dụng `N` trong affinity/cgroup **trước khi áp mask/quota riêng cho training**, topology P/E/SMT, OS, RAM, SSD trống, phiên bản Python/PyTorch/BLAS, power profile và nhiệt khi idle. Không đo lại N sau khi đã cap rồi chia đôi lần thứ hai. Không lấy `nproc` trên một server khác làm số luồng Zenbook. Không mặc định Zenbook có CUDA; NPU/GPU chỉ là thử nghiệm sau baseline CPU, không là điều kiện hoàn thành.

Ngân sách training áp dụng **cho toàn bộ cây tiến trình train**, gồm dataloader/featurizer/validation; quota của tiến trình không bảo đảm toàn máy luôn dưới 50% khi đồng thời build hay chạy VM. Khoảng 50% CPU cũng không bảo đảm nhiệt độ hoặc tiếng quạt; nhiệt/độ mượt phải đo và giảm tải khi cần.

| Tài nguyên | Thiết lập khởi đầu đề xuất |
|---|---|
| Thread tính toán | `T = max(1, floor(N/2))`, có thể giảm thêm do thermal/P-E core |
| CPU hard quota cả nhóm | `CPUQuota = 50 × N %` vì systemd 100% là một CPU; N=16 → 800%, N=8 → 400% |
| Affinity | Tối đa khoảng nửa logical CPU phù hợp topology; không mặc định CPU 0..T-1 là cách chia tốt nhất |
| RAM working set | Mục tiêu 4–8GiB; ngưỡng can thiệp khi trên 10GiB |
| RAM cgroup | `MemoryHigh=10G`, `MemoryMax=12G` (12GiB ≈12,9GB, dưới 16GB) cho cả cây tiến trình |
| Swap | Ưu tiên `MemorySwapMax=0` nếu controller hỗ trợ, để tránh máy bị ì; phải chừa RAM cho OS/code/VM |
| DataLoader | `num_workers=0` ở lần đầu để resume rõ ràng; chỉ thử 1–2 khi đã đo; không preload corpus |
| Torch/BLAS | intra-op T, inter-op 1; OMP/MKL/OpenBLAS cap T, tránh nested parallelism |
| Tác vụ đồng thời | Một training job; validation/export/preprocessing cùng ngân sách, không chạy HPO nhiều process |
| I/O | Đọc shard tuần tự/mmap, cache hữu hạn; checkpoint có đủ khoảng trống cho bản mới và bản cũ |

Linux native: dùng một systemd user service/scope hoặc container cgroup v2 có controller được cấp quyền, Nice thấp, quota/memory trên. Nếu user manager không được delegate controller thì giới hạn có thể không hoạt động: phải đọc `cpu.max`, `memory.max`, kiểm hiệu lực và làm smoke test, không chỉ nhìn file cấu hình. Windows native cần Job Object/affinity phù hợp; WSL2 cần cả giới hạn VM và cgroup bên trong. Chốt OS ở S0 rồi mới viết launcher tương ứng.

Theo [systemd resource control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html), quota CPU tính theo một CPU; `MemoryHigh` gây thu hồi/throttling còn `MemoryMax` là giới hạn cuối có thể dẫn tới OOM. Do đó cap RAM không phải checkpoint mechanism. Chi tiết controller được mô tả trong [Linux cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html).

Monitor mỗi 10–30s: CPU group/host, RSS/cgroup memory.current/peak/events, examples/s, step latency, disk free, queue depth, nhiệt nếu cảm biến khả dụng, AC/battery. Nếu nhiệt kéo dài vượt ngưỡng vận hành đã đo, UI mất mượt hoặc bộ nhớ trên 10GiB: giảm T/prefetch rồi checkpoint+stop nếu chưa hồi phục; giảm effective batch là thay đổi cấu hình học cần child run như dưới. Không tự ấn định ngưỡng nhiệt an toàn của mọi CPU ASUS; lấy giới hạn nhà sản xuất và thử nghiệm thực tế. Laptop vẫn có thể cần thấp hơn 50% quota.

## 4. Training phân mảnh và checkpoint/resume

### 4.1. Phân biệt ba thao tác

- **Resume cùng run:** cùng dataset/split/config/feature version, phục hồi toàn bộ trạng thái rồi tiếp global step. Ranh giới một phiên 2–3h không phải một epoch và không khởi động lại scheduler.
- **Fine-tune dữ liệu mới:** tạo run mới có parent checkpoint và manifest mới; kiểm thay đổi phân phối, giữ replay set đã duyệt để chống quên, đánh giá lại tất cả holdout. Không gắn nhãn resume để lách kiểm version.
- **Incremental estimator:** baseline SGD xử lý shard/mini-batch liên tiếp với `partial_fit` và lưu cả estimator/feature state/cursor; có thể xong trước 60h. Không ép mọi estimator chạy đủ số giờ.

Tách hash **learning config bất biến** (data/split/feature/model/optimizer/scheduler/effective batch) với **operational envelope** (thread/quota/memory cap/prefetch). Đổi operational envelope được resume cùng run nếu ghi ledger, kiểm data-order/parity và chấp nhận tolerance số học đã công bố; không được âm thầm đổi thư viện/môi trường. Đổi effective batch hoặc learning config tạo child/fine-tune run mới. Điều chỉnh số worker cũng phải qua kiểm thử sampler/prefetch, không chỉ đổi flag.

### 4.2. Hợp đồng trainer cần xây

CLI **dự kiến, chưa tồn tại để chạy**: `train --config <versioned-config> --run-id <id> --session-hours 2.5 --checkpoint-every-seconds 300 --resume <checkpoint-uri>`.

Session 2–3h tính theo wall-clock, gồm warmup/checkpoint/validation; lưu riêng thời gian optimizer thực. Bộ đếm monotonic của phiên bắt đầu lại khi resume, còn global steps/scheduler/giờ tích lũy tiếp tục. Dành tối thiểu 5–10 phút cuối phiên cho validation ngắn, ghi checkpoint và kiểm integrity. Checkpoint theo thời gian mỗi 5 phút **hoặc** số step tối đa, tại ranh giới optimizer step đã hoàn tất. Epoch dài hơn 3h vẫn resume được giữa epoch.

Checkpoint neural đầy đủ phải có:

| Nhóm | Trường bắt buộc |
|---|---|
| Identity | format version, run/session ID, parent, code commit, dependency lock/container digest |
| Model | architecture config + state_dict, train/eval mode phục hồi phù hợp |
| Optimization | optimizer state, scheduler state, LR/global schedule, AMP scaler nếu sau này dùng AMP |
| Progress | epoch, global optimizer step, shard ID/hash, row/batch cursor kế tiếp, sampler permutation/seed/state |
| Reproducibility | Python/NumPy/Torch CPU RNG, device RNG nếu có, deterministic settings, dataloader generator |
| Data/feature | dataset manifest/split hash, feature schema version, vocab/hash algorithm, scaler/imputer fitted state |
| Metrics | running loss/count, validation history, best score/checkpoint, early-stopping patience, calibration version |
| Resource/time | session wall time, training compute time, cumulative durations, peak RAM, quota, stop reason |

Chọn gradient accumulation = 1 ban đầu. Nếu thêm accumulation, chỉ checkpoint sau optimizer step hoặc phải lưu gradients và microstep index; không bỏ dở rồi tăng cursor. Với `num_workers>0`, prefetch/sampler position cần phân biệt mẫu đã nạp và mẫu đã commit; nghiệm thu lại resume trước khi dùng. Epoch-shuffle dựa seed+epoch và lưu permutation/cursor để không đọc lại toàn bộ file từ đầu vô tình.

PyTorch hướng dẫn lưu cả optimizer state để tiếp training; `state_dict` weights đơn thuần chưa đủ. Tham chiếu: [Saving and Loading Models](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html). Các trường cursor/hash/RNG/early-stop ở trên là yêu cầu bổ sung của dự án để chia ca và tái lập, không phải artifact đã tồn tại.

### 4.3. Lưu bền và dừng đúng cách

1. Handler Ctrl+C/SIGTERM chỉ đặt stop flag; vòng train hoàn thành step hiện hành rồi vào checkpoint, không thực hiện I/O phức tạp ngay trong signal handler. Launcher/service phải cho grace timeout lớn hơn step lâu nhất cộng checkpoint/flush đã đo, không gửi SIGKILL ngay khi hết session-hours.
2. Ghi file tạm trên **cùng filesystem**; flush/fsync, tính SHA-256, kiểm cấu trúc và load thử cần thiết, atomic rename sang checkpoint mới; đồng bộ thư mục nơi OS hỗ trợ. Chỉ sau đó cập nhật manifest/con trỏ `latest` bằng thay thế nguyên tử. Không ghi đè bản tốt duy nhất.
3. Giữ ít nhất latest, previous và best; ghi manifest hoàn tất riêng để không nhận nhầm file partial. Bản copy lên artifact store được kiểm hash sau upload; tách việc upload với commit local để mạng lỗi không mất checkpoint local.
4. Resume kiểm hash, format/architecture/feature/data/split/learning config/environment; mismatch các phần bất biến thì từ chối và yêu cầu tạo fine-tune run mới. Operational envelope được đổi theo contract ở 4.1 và ghi ledger. Phục hồi model/optimizer/scheduler theo thứ tự tương thích API được pin, kiểm LR và global step, khôi phục RNG/sampler trước lấy batch kế tiếp.
5. Nếu latest hỏng, quay previous có hash đúng và ghi số step cần tính lại. Không tự load checkpoint/model không rõ nguồn; ưu tiên dữ liệu tensor/primitive, manifest JSON, cơ chế load hạn chế của framework.

Mục tiêu: dừng chủ động không mất optimizer step đã checkpoint, không mất dữ liệu nguồn. **Mất điện/SIGKILL/OOM không thể bảo đảm giữ tính toán sau checkpoint gần nhất**; với chu kỳ 5 phút, có thể phải tính lại tối đa khoảng một chu kỳ cộng step/IO đang dở. Độ bền còn phụ thuộc filesystem/SSD và kiểm fsync. Không hứa “zero-loss” tuyệt đối; checkpoint và dữ liệu bất biến cho phép khôi phục có kiểm soát.

## 5. Cổng nghiệm thu trước training dài

S0 phải so sánh hai run cùng seed/data/config trong **cùng môi trường đã pin**: A chạy liên tục K step; B dừng ở giữa shard, save, process mới resume đến K. So sánh global step, LR/scheduler, optimizer state, mẫu cuối/đầu mỗi phiên, metrics và weights trong tolerance đã công bố; nhánh deterministic CPU nhỏ nên đặt tolerance rất chặt. Không đòi bitwise giống giữa OS/library/hardware khác nhau.

Các fault cases bắt buộc: Ctrl+C, SIGTERM, hết wall-time; kill ngay trong lúc ghi file tạm; latest hỏng; disk full; dataset hash/config thay đổi; thiếu shard; resume sau early-stopping; dừng giữa epoch; hai process tranh cùng run. Dùng run lock và báo lỗi rõ thay vì cho hai trainer cùng cập nhật latest.

S0 chỉ PASS khi checkpoint trước vẫn load được sau crash, cursor không bỏ qua mẫu, lịch LR không reset và quota/RAM có hiệu lực. Ghi báo cáo, hash và lệnh tái lập vào 06. Đây là test có ý nghĩa cho chức năng tương lai; chưa được viết hoặc chạy ở phiên tài liệu.

## 6. Stages và ngân sách ca

**Kế hoạch mở rộng là 70 giờ tổng thời gian phiên**, không phải cam kết cần 70 giờ gradient hay đạt chất lượng sau 70 giờ. Nhiều ca có validation/calibration/export; sổ run phải tách `session_wall_hours` và `optimizer_hours`. Có thể kết thúc sớm khi baseline đủ tốt; có thể cần đổi dữ liệu thay vì train lâu hơn nếu validation không cải thiện. Không lặp dữ liệu vô hạn để lấp 60–80 giờ.

| Stage | Ca × giờ | Giờ phiên | Đầu vào / đầu ra | Gate để đi tiếp |
|---|---|---:|---|---|
| S0 — Pipeline/resume/resource smoke | 1 × 2h | 2 | Slice nhỏ có nhãn, snapshot schema → resource report + checkpoint equivalence | CPU/RAM cap hiệu lực; resume/fault tests PASS |
| S1 — Baselines + benign behavior | 4 × 2.5h | 10 | SGD payload, rule-only, aggregate behavior, anomaly offline | Có baseline report trên grouped/time split; benign đại diện |
| S2 — Payload candidate | 8 × 2.5h | 20 | Byte-CNN; public HTTP pretrain có chọn lọc, student fine-tune | Tốt hơn baseline ở cùng FPR trên local validation, không chỉ public |
| S3 — Behavior candidate | 8 × 2.5h | 20 | MLP→TCN nếu cần; chuỗi + time windows, replay benign | Có gain trên attack family/session held-out; causal feature parity |
| S4 — Hard negatives/calibration | 6 × 2h | 12 | Dữ liệu benign/hard negatives mới đã review, threshold trên calibration | FP giảm, không mất recall quá mức; chọn champion rồi khóa config |
| S5 — Export/parity/shadow acceptance | 3 × 2h | 6 | ONNX FP32, tùy chọn int8, load/failure/latency tests | Parity, resource, rollback PASS; test cuối chỉ đánh giá sau chốt |
| **Tổng kế hoạch** | **30 ca, mỗi ca 2–2.5h** | **70** | Khoảng 60–80h gồm dự phòng điều chỉnh được review | Không thay gate bằng số giờ |

Khối công việc thu dữ liệu/label/split phải hoàn tất gate của roadmap trước S0; thời gian người chuẩn bị dữ liệu không cộng giả vào giờ train. Sau S1 có thể chọn baseline làm champion và bỏ neural branch không có lợi. Dự phòng khoảng 10h chỉ cho lỗi có chẩn đoán hoặc dữ liệu mới; không mặc định tiêu hết.

Mỗi ca: kiểm manifest và tài nguyên → resume → mini-validation định kỳ → checkpoint theo 5 phút → cuối ca full validation phù hợp stage và ghi ledger → kiểm latest/previous. Các thử nghiệm hyperparameter giới hạn 1–2 biến/lần, chạy nối tiếp, early-stop theo validation, không chọn nhiều lần trên test cuối.

## 7. Đánh giá chất lượng và báo động giả

Tối thiểu so sánh rule-only, AI-only và dual-engine tại cùng data split, rate và threshold budget. Attack labels là ground truth từ scenario/review, không dùng rule decision/Suricata severity làm nhãn duy nhất. Test rule-miss có family/obfuscation chưa thấy trong train; chỉ được gọi “held-out variant/family”, không khẳng định phát hiện zero-day nói chung.

| Chỉ số | Cách báo cáo / mục tiêu thử ban đầu |
|---|---|
| PR-AUC, precision/recall/F1 | Theo attack family và tổng micro/macro; ROC-AUC phụ, không chỉ accuracy |
| FPR request | FP / benign requests; mục tiêu alert khởi đầu ≤0,1% trên benign holdout đại diện |
| FP hành vi | FP trên benign session/window và số alert/giờ; tách IP dùng chung/NAT |
| Auto-block precision | Chưa cho AI tự block; mục tiêu thử ≥99,9% chỉ có ý nghĩa khi CI/sample đủ và policy đạt gate |
| Calibration | Reliability/ECE hoặc Brier cho score xác suất; anomaly score báo riêng |
| Incremental value | Recall thêm ở cùng FPR/alert budget; overlap rule/AI và ablation từng branch |
| System | p50/p95/p99 latency, queue lag, RSS/CPU, bytes/s, drop/error, throughput ổn định |

Các con số là mục tiêu đề xuất, chưa là SLA hoặc kết quả đạt. Với 0 FP trên n mẫu benign độc lập, xấp xỉ cận trên 95% là `3/n`; 3.000 mẫu không đủ chứng minh FPR cực nhỏ. Request cùng session tương quan nên cần grouped bootstrap/session-level CI, nhiều ngày/người/workload. Ghi cả count, confidence interval và prevalence thật; precision trên corpus cân bằng không đại diện production nhiều benign.

Chống leakage: split theo thời gian + session/user/scenario/template group, dedup payload biến thể trước split; scaler/vocab fit train-only; không dùng request ID, scenario ID, label timestamp, IP tấn công cố định, response firewall/action hoặc rule hit làm shortcut cho AI độc lập. Model input chỉ có thông tin sẵn tại thời điểm quyết định. Chi tiết ở 02.

## 8. Xuất ONNX và tích hợp Rust

Candidate PyTorch được export với input shape/dtype đã pin, chọn opset theo runtime target. Kiểm `onnx.checker`, golden tensor vectors, Python-vs-ONNX và Rust-vs-Python score parity gồm raw/canonical/truncated/missing/Unicode cases. Feature engineering ngoài graph phải có cùng version và golden vectors giữa Python/Rust; một model ONNX đúng không cứu được preprocessor lệch.

Theo [PyTorch ONNX](https://docs.pytorch.org/docs/stable/onnx), exporter chuyển tensor graph; việc export không tự đóng gói toàn bộ parser/feature pipeline. ONNX Runtime cho phép cap thread và tắt spinning để giảm CPU lúc chờ; xem [Thread management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html). Khởi đầu sequential execution, intra-op 1–2, inter-op 1; benchmark thực trước khi tăng.

Rust integration cần chọn và pin binding/runtime tương thích sau một spike riêng; `Cargo.toml` hiện **chưa có ONNX Runtime**. Triển khai worker inference cách ly, load model một lần, queue bounded, timeout/circuit breaker, shadow metrics; lỗi AI không làm rule/HTTP pipeline dừng. Không thêm thư viện/sidecar trong phiên docs này.

Giữ FP32 làm chuẩn. Chỉ dùng int8 sau calibration phù hợp nếu latency/RAM tốt hơn và recall/FPR/parity không suy giảm quá giới hạn đã thống nhất; quantization không mặc định nhanh hơn mọi CPU/op. Tham chiếu [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).

Bundle release gồm: model hash, feature schema/vocab/scaler, calibration/thresholds, model card, dataset/split provenance, commit/env lock, ONNX opset/runtime compatibility, golden vectors, metrics và quyết định review. Rollout shadow → human-reviewed canary theo service/tenant → alert-only production; IPS AI-only chỉ xét sau gate riêng. Champion cũ giữ sẵn, đổi pointer/version nguyên tử, rollback khi FP/drift/resource lỗi. Không tự học từ traffic live chưa duyệt vì nguy cơ data poisoning; version và review trước mỗi fine-tune.

## 9. Quyết định còn mở

Chưa chốt OS/CPU, artifact store, label volume, lưu lượng thật, tỷ lệ benign/attack, inference deployment target, license dataset và tiêu chí enterprise ngoài lab. Những thiếu sót này không cản việc đọc repo/viết docs; chúng là điều kiện phải xác minh ở các task tương ứng trong 04, trước khi chốt lịch và ngân sách cuối. Trạng thái train hiện hành và form bàn giao nằm tại [06](06_AI_HANDOFF_AND_RUN_LEDGER.md).
