# AI-IDPS Data & Training Pipeline

Nhánh `feat/ai-model-training`, nền code `fbe078d`. Package chạy offline, chỉ đọc file log hoặc bản export PostgreSQL. Không sửa hay kết nối để cấu hình Student/Security, không gọi firewall, không triển khai model vào Rust. Source, venv, configs và artifact AI nằm riêng trong thư mục này.

## Khởi tạo và kiểm tra

Đã kiểm chứng trên Linux/Python **3.12.14**, CPU. Thư viện được pin cả trực tiếp lẫn bắc cầu trong `requirements.txt`; Python3.12 là môi trường chuẩn để tái lập checkpoint. Hai mô hình dùng NumPy FP32 và Adam có trạng thái tường minh: MLP8 lớp cho supervised baseline, autoencoder cho anomaly. Không yêu cầu Torch/CUDA/LightGBM để chạy S0. Đây là lựa chọn triển khai MLP/AE nhẹ của nhánh, chưa chọn champion trên dữ liệu thật.

```bash
cd ai-training
AI_PYTHON=python3.12 ./scripts/bootstrap.sh
./scripts/check.sh
```

Nếu venv đã tồn tại thì bootstrap giữ interpreter của venv. `AI_PYTHON` chỉ dùng khi tạo venv mới. Phiên triển khai dùng Python3.12 đi kèm Codex để tạo `.venv`; không thay Python hệ thống. Các nền tảng khác chưa được nghiệm thu, đặc biệt resource guard hiện cần Linux `resource`/affinity và `fcntl`.

## S0 chạy đầy đủ

```bash
.venv/bin/idps-ai s0 --output .artifacts/synthetic_s0 --max-threads 2
```

Chọn đường dẫn mới cho mỗi lần chạy. S0 sinh15campaign ×64request, log đúng cấu trúc Student/Nginx/EVE, ground truth riêng. Mỗi nhánh MLP/AE chạy **2 epoch → checkpoint → tiến trình mới resume đến tổng4 epoch**. Một tiến trình khác chạy4epoch liên tục để đối chiếu weights, moments Adam, scheduler, Python/NumPy RNG và sampler. Sau đó export ONNX, kiểm tất cả hàng dataset, đánh giá holdout và benchmark batch1. `s0_report.json` chứa hash và giờ optimizer thực; preprocessing/export/reference-run tách riêng. **Không dùng kết quả synthetic để tuyên bố chất lượng thật, FPR production hoặc zero-day detection.**

Kết quả đã đo **27/10/2026 12:39:52–12:40:01+07:00**:42tests PASS;960requests/3403observations,125features,train576/val192/test192; exactresume và ONNX960/960 mỗi model. PeakRSS cao nhất208.77MiB,2threads; wall9.209335s. Report metadata có checksum: [`reports/S0_20261027.json`](reports/S0_20261027.json). Hai run chính optimizer0.015538449s, reference0.015986770s riêng; **train dữ liệu thật0giờ**. Artifact binary/checkpoint local nằm `.artifacts/synthetic_s0_20261027_final`, không có trong Git. Model metrics ở report chỉ kiểm việc tính/xuất metrics, không là bằng chứng phát hiện tốt.

## Thu log thật thành snapshot

Chỉ đọc bản sao bất biến/rotation đã hoàn tất; file đang thay đổi sẽ bị từ chối. Source inputs không được nằm trong thư mục output. Không lấy cấu hình hoặc HMAC key của dịch vụ đang chạy: tạo key riêng cho dataset AI, giữ ngoài Git và dùng lại khi nối nhãn/campaign.

```bash
mkdir -p .artifacts/private
umask 077
openssl rand 32 > .artifacts/private/training-redaction.key
.venv/bin/idps-ai collect \
  --input student=/absolute/path/snapshot/student-audit.log \
  --input nginx=/absolute/path/snapshot/access.log \
  --input suricata=/absolute/path/snapshot/eve.json \
  --hmac-key-file .artifacts/private/training-redaction.key \
  --output .artifacts/collected-v1
```

Nếu chỉ có một/hai nguồn thì bỏ input còn lại. Adapter `canonical=/path/events.jsonl` hoặc `postgres-export=/path/events.jsonl` đọc mỗi dòng là canonical JSON hoặc `{ "canonical": {...} }`. Có thể xuất bằng query `SELECT canonical FROM normalized_events ORDER BY occurred_at,id` trong transaction **REPEATABLE READ, READ ONLY** bằng tài khoản read-only hiện có; package không tạo DB role, không sửa DB/config và không tự mở kết nối PostgreSQL. Không dùng riêng `security_alerts` làm dataset benign.

Output `observations.parquet` giữ quan sát đã lọc; `requests.parquet` gộp HTTP theo requestID + IP tương thích + cửa sổ2s. Student ưu tiên actor/role, Nginx/EVE bổ sung bytes/metadata. Cùng IP/thời gian chỉ là context, không merge các request NAT. Flow chỉ gắn qua cùng flowID đã HMAC và timestamp không vượt quyết định; counters là snapshot flow, không giả thành packet counters của một request.

## Gán nhãn, chuẩn bị split/feature

Sidecar JSONL dùng `request_id` gốc hoặc `request_key` từ dataset, `campaign_id`, `attack_family`, `label`0/1, `label_source`, `label_confidence`0–1, `review_status`:

```json
{"request_id":"example-request-id","campaign_id":"reviewed-campaign-01","label":1,"attack_family":"sqli","label_source":"human_review","label_confidence":1.0,"review_status":"approved"}
```

Các lớp: benign, sqli, xss, path_traversal, cmd_injection, scanner_recon, brute_force, behavioral_anomaly. Chỉ `human_review`/`scenario_manifest` đã approved trở thành ground truth. `weak_rule` và request không khớp nhãn giữ unknown, không train; HTTP201/401 hoặc không có alert không tự quyết định nhãn. Mâu thuẫn nhãn phải giải quyết trước khi tạo dataset.

```bash
.venv/bin/idps-ai prepare --dataset .artifacts/collected-v1 \
  --labels /absolute/path/reviewed-labels.jsonl \
  --hmac-key-file .artifacts/private/training-redaction.key \
  --output .artifacts/prepared-v1
.venv/bin/idps-ai inspect --dataset .artifacts/prepared-v1
```

Splitter temporal60/20/20, nhóm liên thông campaign/IP/user/session, embargo300s quanh cả hai ranh giới; group xuyên ranh giới bị purge. Không fallback random split. IP dùng chung toàn corpus có thể khiến mọi group nối nhau và split bị từ chối: cần thêm campaign/IP thực sự độc lập hoặc review thiết kế split, không sửa IP/nhãn để làm đẹp metrics.

Feature pipeline gồm lexical/structural numeric projection, method/status/role/auth, latency/bytes, flow context, và windows10/60/300s cho IP/user: count/rate,4xx/5xx, auth streak, URI diversity, API/read ratios. Counter gồm event hiện tại một lần; event đến muộn bị từ chối. Có lookback300s, LRU/cardinality/event cap và cờ context incomplete khi clip/khởi động. Không đưa IP/user/request/campaign IDs vào model. Counter Suricata alert có trong context, **bị loại khỏi input model mặc định** để tránh học lại rule.

`feature_spec.json` lưu thứ tự cột, fixed one-hot vocab, imputation0, raw clipping, mean/std train-only, FP32 output/clipping, window/missing semantics và implementation hash. Scaler được fit **chỉ benign thuộc train**, nên autoencoder không học cả phân phối attack qua normalization. Unknown rows trong partition vẫn đóng góp context, chỉ các hàng nhãn được review mới có vector train.

Nhiều query/path đã mask ở producer: không thể tái dựng payload hay object ID. Feature lexical có availability flags, `query_original_*` chỉ có khi producer thực sự cung cấp counters; query length/entropy từ view đã lọc privacy, không giả là độ dài bí mật. URI diversity/bulk API chỉ là tín hiệu phụ trợ, **không đủ chứng minh IDOR**. Model này dùng dữ liệu post-response, chưa dùng để chặn request đầu tiên.

## Train, dừng, resume

```bash
.venv/bin/idps-ai train --dataset .artifacts/prepared-v1 \
  --config configs/train_config.yaml --run-dir .artifacts/runs/tabular-v1 \
  --epochs 20 --max-threads 4 --max-duration-minutes 150
# Chạy ở ca sau, tiếp tục đúng cursor/optimizer step:
.venv/bin/idps-ai train --dataset .artifacts/prepared-v1 \
  --config configs/train_config.yaml --run-dir .artifacts/runs/tabular-v1 \
  --resume-from .artifacts/runs/tabular-v1 \
  --epochs 20 --max-duration-minutes 150
```

`--epochs` là **tổng epoch đích**. Chạy2epoch rồi thêm2 thì resume với `--epochs 4`. `--max-steps` là số step tối đa của phiên, dùng kiểm thử dừng giữa epoch. `configs/anomaly_config.yaml` chọn autoencoder; dùng run-dir mới, autoencoder chỉ fit benign. Training/calibration yêu cầu có benign và attack đã review ở validation để chọn threshold theo FPR; không tự tạo nhãn cho corpus chưa đủ.

CPU mặc định≤4threads và≤nửa affinity ban đầu, BLAS/OpenMP cùng cap, inter-op ONNX1. Linux affinity và RLIMIT_AS12GiB được kiểm hiệu lực; guard đo RSS cả process tree tại optimizer boundaries. Trainer không sinh dataloader/subprocess; S0 workers chạy nối tiếp. RLIMIT_AS là allocation ceiling từng process, không thay cgroup host. Memory guard tree không phải hard group cgroup; nếu bổ sung worker sau này phải nghiệm thu lại. Không bảo đảm nhiệt độ chỉ bằng thread cap; S0 không thay benchmark ca2–3giờ trên máy đích.

SIGINT/SIGTERM chỉ đặt cờ; save sau step hoàn tất, mỗi300s và cuối phiên. Checkpoint có optimizer/scheduler, RNG, permutation/cursor, epoch/step/best/patience, shard/dataset/config/feature/environment/code hash. Ghi temp cùng filesystem +fsync +rename, pointer latest/previous/best và run lock. Latest hỏng có thể fallback previous đã kiểm SHA. Mất điện/OOM/SIGKILL có thể mất phần tính toán **sau checkpoint gần nhất**; không hứa zero-loss tuyệt đối. Run early-stopped là terminal; đổi learning config/dataset/env/code cần run mới thay vì ép resume.

## Export, evaluate, inference reference

```bash
.venv/bin/idps-ai export --dataset .artifacts/prepared-v1 \
  --checkpoint .artifacts/runs/tabular-v1 \
  --output .artifacts/bundles/tabular-v1 --max-threads 2
```

Bundle có `model.onnx`, `model_manifest.json`, `feature_spec.json`, `golden_vectors.json`, `evaluation.json`, model card. Threshold fit trên validation để tối đa recall dưới empirical FPR1%; test không được dùng chọn deployment threshold. Báo AP/PR-AUC trapezoidal, ROC-AUC, precision/recall/F1, confusion matrix binary/theo family/multiclass, recall@FPR≤1% dạng ROC diagnostic và latency native/ORT p50/p95/p99 (warm batch1, không gồm preprocessing). Small synthetic benign count không chứng minh FPR nhỏ trong production.

`idps_ai.inference.InferencePipeline` là reference streaming cho **fused-request row**, dùng lại FeatureExtractor/transform, load ORT session một lần. Tests so vector online với offline từng hàng. Không truyền một raw log line vào model rồi coi đó là cùng preprocessing. Model graph chỉ nhận tensor đã chuẩn hóa; Rust cần port đúng feature contract + golden vectors và nghiệm thu parity riêng. Không có thay đổi Rust, live inference service, shadow integration hoặc enforcement trong nhánh này. Anomaly score chỉ là candidate để review, không phải bằng chứng zero-day hay nhãn attack tự động.

Artifact/key/raw/data/model chỉ lưu trong `.artifacts/` (ignored) hoặc kho được kiểm soát ngoài Git; repo chỉ giữ code/config/tests/report metadata. Không lưu credential hay dataset thật vào Git.
