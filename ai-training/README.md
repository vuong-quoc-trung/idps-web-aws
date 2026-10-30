# AI-IDPS Data & Training Pipeline

## Hiện trạng — 2026-10-30T21:35:36.891996+07:00

**Engineering PASS; generalization/deployment NOT_READY.** 160 pytest PASS/0 skip, 53 legacy technical gate PASS. Chỉ AI/docs; không đổi Student/Security, chưa champion hoặc train dài. Tổng lab 71.280 HTTP đủ 3 nguồn sau cohort 1.935 request mới; vẫn một môi trường, 0 scale admission cho mục tiêu 2M. Không đếm projection hoặc public benchmark record thành HTTP mới.

Nhánh riêng `request-structure-v1` gồm 70 số, hỗ trợ cấu trúc tham số không nhạy cảm rộng hơn; fused 207 v5 giữ nguyên. Đã chạy adapter PKDD flattened, shared train-benign scaler, partial unknown-family loss, 3 ứng viên × 2-epoch/300-update study, exact resume/ONNX toàn 115.980 vector và opt-in EVE bridge. Chất lượng mới vẫn chưa đạt: request MLP lab recall 40,6%; GLU recall 0 tại ngưỡng khóa; AE khá trên public nhưng lab FPR 18,6%. Chưa đủ cơ sở chọn champion.

Xem [PRETRAINING](PRETRAINING.md), [báo cáo đo](reports/REQUEST_PROFILE_20261030.json), [handoff](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 27. `RequestInferencePipeline` chỉ trả candidate nhị phân, 0 enforcement; 70 feature và 207 feature là hai contract riêng. Công cụ mới và giới hạn nằm trong PRETRAINING. Các lệnh train/snapshot phía dưới là lịch sử, không phải chỉ dẫn chạy formal hoặc chạy lại study đã hoàn tất.

## Nâng cấp 9,68M / mục tiêu 2M — nghiệm thu kỹ thuật, dữ liệu còn thiếu — 2026-10-30T15:52:59+07:00

**Đã kiểm chứng phần kỹ thuật; chưa hoàn thành mục tiêu dữ liệu/production.**
Chỉ sửa AI và docs. Corpus vẫn **69.345 request duy nhất, một lab**, nhãn scripted
intent; không thêm request hoặc môi trường. Re-extraction v5 không phải dữ liệu mới.
Chưa có review nhãn độc lập, **0 request được admission cho formal scale**; mục tiêu
2M đa dạng chưa đạt. Không nhân bản hoặc cộng các bản projection/cache vào số lượng.

| Giai đoạn | Trạng thái cuối phiên |
| --- | --- |
| Data | Catalog/provenance/replay/holdout checks đã có; corpus 2M và shared-scaler assembly nhiều môi trường còn thiếu |
| Features/architecture/algorithms | v5/207 cột, thêm 18 dynamics; residual SwiGLU **9.675.784** tham số thực; AdamW/smoothing/dropout/warmup-cosine |
| Tests/readiness | **134/134 pytest PASS, 0 skipped**; **53/53 gate kỹ thuật PASS** trên cùng 69k |
| Pilot | 4 neural candidates × 2 epoch, fresh-process resume và reference khớp chính xác; ONNX mọi 69.345 vectors/candidate PASS |
| Evaluation | Calibration 3 campaign, selection 6 campaign; fit không nhìn validation; test quality giữ kín; tree32 iteration đối chứng |
| Integration | Offline shadow512 request PASS, không gọi Web/firewall; live/TLS/receipt-time/response NOT_RUN |
| Formal/champion | NOT_RUN / chưa chọn; không tự chạy ca dài và chưa đủ data gate |
| Cleanup | Chỉ cache tái tạo được: giải phóng 498.14 MiB; giữ raw/checkpoint/log/evidence cũ |

AP selection cao nhất ở lượt ngắn: **gated_residual**. Main challenger
AP **0.997228**, recall **98.92%**, FPR **0.823%**,
p95 ONNX model-only **5.363 ms**. Model lớn không mặc định tốt hơn;
khác biệt thuật toán/regularization không phải thí nghiệm riêng tác dụng số tham số.
Một lab và sáu nhóm selection không chứng minh FPR/zero-day/production generalization.

[Báo cáo đo thực](reports/SCALE_UPGRADE_20261030.json), [handoff hiện hành](FINAL_TRAINING_HANDOFF.json),
ledger06 mục25. Tất cả snapshot cũ bên dưới là lịch sử; không dùng readiness/source
cũ cho source hiện hành hoặc force-resume checkpoint khác contract.

Các lệnh kỹ thuật, dùng output mới mỗi lần và giữ cgroup tối đa 8 CPU / 16 GiB:

```bash
# Audit thực tế: exit3/NOT_READY hiện là kết quả đúng, không phải lỗi cần hạ gate.
ai-training/.venv/bin/idps-ai corpus-audit --output "$PWD/ai-training/.artifacts/catalog-next"

# Chạy lại pilot kỹ thuật, không phải formal/champion. Output phải chưa tồn tại.
systemd-run --user --wait --pipe --collect \
  -p CPUQuota=800% -p MemoryMax=16G -p MemoryHigh=15G -p MemorySwapMax=0 -p Nice=10 \
  "$PWD/ai-training/.venv/bin/idps-ai" pilot --candidate-set scale \
  --dataset "$PWD/ai-training/.artifacts/scale_upgrade_20261030/prepared-v5" \
  --readiness-report "$PWD/ai-training/.artifacts/scale_upgrade_20261030/readiness/readiness.json" \
  --output "$PWD/ai-training/.artifacts/scale-pilot-next" --cpus 8

# AI-only offline integration, fused ordered rows; không đọc trực tiếp từng EVE line.
ai-training/.venv/bin/idps-ai shadow-replay \
  --dataset "$PWD/ai-training/.artifacts/scale_upgrade_20261030/prepared-v5" \
  --bundle "$PWD/ai-training/.artifacts/scale_upgrade_20261030/pilot/residual_glu-bundle" \
  --output "$PWD/ai-training/.artifacts/shadow-next" --max-requests 512 --cpus 8
```

Formal main-model config `scale_model_config.yaml` bị chặn trên 69k. Không có lệnh
formal được khuyến nghị lúc này. Cần nguồn/nhãn được review, shared train-only scaler,
corpus assembly bốn phần có lineage và current-source readiness trước khi xin chạy
ca dài. Raw/data/model là artifact cục bộ được Git ignore; teammate cần chuyển
artifact an toàn hoặc thu lại. Không force-resume bằng source/feature/config mới.
Memmap `cache/*.npy` của pilot đã dọn vì có thể tái tạo từ dataset; checkpoint NPZ,
latest/best/previous/session và báo cáo vẫn đầy đủ. `load_arrays` tự tạo cache trước
fit/resume/export. Xem thuật toán ở docs03, admission ở docs02 và ledger25.

<details>
<summary>Lịch sử các workflow và kết quả trước v5</summary>


## Bàn giao corpus và mô hình sâu revision 4.1 — 2026-10-30T09:08:21+07:00

| Hạng mục | Kết quả đo thực |
| --- | --- |
| Corpus | 69,345 request; 297,685 observations từ Student, Nginx và Suricata thật |
| Split và nhãn | 69,345 vectors có nhãn được duyệt; train: 41,607 / val: 13,869 / test: 13,869; groups 27/9/9 |
| Đặc trưng | ai-features-4.1 / normalizer 4.1, 189 cột, projection v2; canonical 1.0 giữ nguyên |
| Mô hình | Residual nhỏ đối chứng; MLP 248.072 / DAE 294.717 / gated residual 445.448 tham số |
| Readiness | 53/53 PASS; payload và hard negatives có identity riêng giữa các temporal bands |
| Pilot | 4 mô hình × 5 epoch; resume qua process mới khớp reference; ONNX 69,345/69,345 vectors PASS từng mô hình |
| Kiểm thử và phạm vi | 118 pytest PASS, 0 skipped; giữ nguyên hash 366 file dịch vụ/contract và 1.946 artifact cũ |
| Train dài / chất lượng trên test / deploy | NOT_RUN; chưa chọn Champion Model hoặc nghiệm thu Rust/live/enforcement |

Ứng viên lớn cho thí nghiệm tiếp: **gated_residual** (AP 0.999077, precision 97.61%, recall 99.16%, FPR 0.996%).
Residual đối chứng: AP 0.999165, precision 97.64%, recall 99.55%, FPR 0.986%. Các số đo trên validation còn sơ bộ
vì cùng tập này được dùng để calibration và so sánh ứng viên. Tăng tham số không
bảo đảm tốt hơn; không kéo dài train chỉ để đủ thời gian.

Manifest hiện hành: [FINAL_TRAINING_HANDOFF.json](FINAL_TRAINING_HANDOFF.json).
Xem [báo cáo](reports/PRETRAIN_EXPANDED_20261030.json) và mục 24 của ledger 06. Các snapshot bên dưới là lịch sử.

Lệnh ca tiếp do người dùng tự chạy, **chưa được thực thi**:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-expanded-session.sh gated_residual
```

## Corpus mở rộng và mạng sâu — revision 4.1

Đợt hiện hành thêm41 đặc trưng số, đưa vector lên189 cột, projection
`safe_query_numeric_v2` và feature/normalizer 4.1. Các artifact 4/148 cột và report
ngày 28/đầu ngày 29 giữ lịch sử; không dùng checkpoint hoặc readiness cũ với source
mới. `FINAL_TRAINING_HANDOFF.json` ở đầu package sẽ là manifest bàn giao hiện hành,
trỏ artifact local đã kiểm; không chứa raw/key/model binary.

Ba candidate mới: MLP bốn hidden layers / 248.072 tham số, denoising AE 294.717 tham số và
gated residual ba blocks / 445.448 tham số. Có residual nhỏ làm đối chứng cùng dataset.
Denoising AE chỉ fit benign, train noisy→clean, inference sạch; noise phụ thuộc
seed + optimizer step để resume chính xác. FP32/FP64 affine reduction và parity 1e-5/1e-6
giữ nguyên. Không thêm Torch/CUDA hoặc dependency mới. Xem
[thuật toán và giới hạn](../docs/03_AI_MODEL_AND_TRAINING_PLAN.md#các-ứng-viên-sâu-revision-41--29102026).

Để tái lập capture, chọn output mới (không chạy lại vào thư mục có sẵn):

```bash
capture_root="$PWD/ai-training/.artifacts/expanded-capture-next"
ai-training/.venv/bin/idps-ai lab-start --output "$capture_root/lab" \
  --nginx-bin "$PWD/.local-dev/foundation/tools/runtime/usr/sbin/nginx" --campaigns 45
ai-training/.venv/bin/idps-ai lab-capture-eve --lab-dir "$capture_root/lab" \
  --campaign-seconds 480 --requests-per-campaign 1536
ai-training/.venv/bin/idps-ai lab-stop --lab-dir "$capture_root/lab"
ai-training/.venv/bin/idps-ai decode-pcap --pcap "$capture_root/lab/traffic.pcap" \
  --runtime "$PWD/ai-training/.artifacts/upgrade_20261028/tools/runtime" \
  --output "$capture_root/lab/eve" --query-numeric --projection-version 2
ai-training/.venv/bin/idps-ai lab-finish --lab-dir "$capture_root/lab" \
  --output "$capture_root/dataset-ready"
ai-training/.venv/bin/idps-ai pilot --dataset "$capture_root/dataset-ready/prepared" \
  --readiness-report "$capture_root/dataset-ready/readiness/readiness.json" \
  --output "$capture_root/pilot" --candidate-set expanded --cpus 8
```

45 campaign chia27/9/9, khoảng69.345 request kể cả setup/logout; seed lưu trong
capture metadata. Nhịp lognormal/jitter và thứ tự độc lập, tham số/endpoint thay
đổi, attack và hard-negative views tách giữa ba temporal bands. Split vẫn giữ
embargo 300 giây; hai gap 620 giây là thời gian thật. Corpus gate 60–80k, không đổi timestamp
để chia tập. Tăng cap audit chỉ trong environment của fixture lab, không sửa
`student-web`/`security-web` hoặc cấu hình dịch vụ đang dùng. Lỗi capture phải
`lab-stop` rồi dùng version mới; không gắn chứng nhận cho capture chưa hoàn tất.

Live numeric bridge dùng cùng projection:

```bash
ai-training/.venv/bin/idps-ai project-eve --projection-version 2 \
  --input raw-eve.json --output ai-eve.json
```

Chạy trên HTTP view trước redaction (sau TLS termination nếu có), không trên URL
đã mất query. File output immutable; stdin/stdout cần consumer bền vững riêng.
PCAP có credential/session của fixture giả, giữ private 0600 ngoài Git.
Rust live/receipt-time/TLS/missing-source acceptance chưa được triển khai ở đây.

Sau khi đọc handoff/readiness/pilot cuối, lệnh ca dài do người vận hành tự chạy:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-expanded-session.sh gated_residual
```

Có thể thay đối số bằng `deep_mlp`, `denoising_autoencoder` hoặc `residual` để tạo
experiment riêng. Mỗi ca tối đa 150 epoch / 150 phút, 8 CPU / 16 GiB, sleep inhibitor và
checkpoint 300 giây. Early stopping có thể kết thúc sớm; model lớn không bảo đảm tốt
hơn và không bắt buộc dùng hết 150 phút. Preparation/pilot không gọi script này.
Các workflow bên dưới giữ nguyên ý nghĩa lịch sử của corpus trước.

## Workflow numeric query — 29/10/2026

Profile mới `safe_query_numeric_v1` dùng feature/normalizerv4,148cột và vẫn giữ
canonical1.0. AI EVE bridge chỉ giữ28 số cấu trúc sau lọc secret/PII; không ghi
plaintext query vào EVE/Parquet. Xem [contract](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md#ai-input-contract-v4--nâng-cấp-ngày-29102026).
Corpus/checkpoint ngày28 và ca dừng sớm ngày29 là các snapshot lịch sử riêng.

Một capture mới dùng30campaign chia18/6/6,1536workload request/campaign,480giây
thật/campaign và hai khoảng nghỉ620giây thật. Tổng có thể thêm setup/logout hoặc
retry bootstrap. Chọn **đường dẫn mới** mỗi lần; không chạy đè lab/dataset đã tồn tại.
Từ repository root, sau khi venv và trusted Nginx/Suricata runtime đã có:

```bash
capture_root="$PWD/ai-training/.artifacts/query-capture-next"
ai-training/.venv/bin/idps-ai lab-start --output "$capture_root/lab" \
  --nginx-bin "$PWD/.local-dev/foundation/tools/runtime/usr/sbin/nginx" --campaigns 30
ai-training/.venv/bin/idps-ai lab-capture-eve --lab-dir "$capture_root/lab" \
  --campaign-seconds 480 --requests-per-campaign 1536
ai-training/.venv/bin/idps-ai lab-stop --lab-dir "$capture_root/lab"
ai-training/.venv/bin/idps-ai decode-pcap --pcap "$capture_root/lab/traffic.pcap" \
  --runtime "$PWD/ai-training/.artifacts/upgrade_20261028/tools/runtime" \
  --output "$capture_root/lab/eve" --query-numeric
ai-training/.venv/bin/idps-ai lab-finish --lab-dir "$capture_root/lab" \
  --output "$capture_root/dataset-ready"
ai-training/.venv/bin/idps-ai pilot --dataset "$capture_root/dataset-ready/prepared" \
  --readiness-report "$capture_root/dataset-ready/readiness/readiness.json" \
  --output "$capture_root/pilot" --cpus 8 --include-weighted-residual
```

Capture cần rootless user/network namespace được phép; chỉ bắt TCP của fixture
trong namespace riêng, không xin host packet socket. Nếu capture lỗi, chạy
`lab-stop` trong bước dọn và tạo phiên bản mới. Raw PCAP chỉ private0600, chứa
HTTP/session của fixture giả; không đưa lên Git. Không lấy credential/DB của dịch
vụ đang chạy. Lệnh trên chuẩn bị và pilot, không tự train chính thức.

`project-eve --input RAW_EVE --output AI_EVE` dùng cùng projection với offline
decoder; `--input - --output -` hỗ trợ stream stdin/stdout. Output file là bản mới
bất biến, công bố khi kết thúc stream; stdout dành cho consumer có lifecycle bền
vững riêng. Không chạy bridge trên bản đã mất query rồi kỳ vọng phục hồi payload.
Rust live adapter, TLS vantage và receipt-time parity vẫn cần nghiệm thu riêng.

Config thứ tư `weighted_residual_config.yaml` dùng train-only inverse-sqrt class
weights. Pilot kiểm2→5epoch/process mới, reference5epoch, history/Adam exact và
ONNX mọi vector; chỉ tính chất lượng validation. Config/seed khác là experiment
mới, không force-resume old run. `query_experiment_plan.yaml` ghi các so sánh.

Ca kế tiếp dành cho corpus đã bàn giao ngày29:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-query-session.sh
```

Script trỏ đúng `upgrade_20261029_query/dataset-ready`, buộc gate mới,8CPU/16GiB,
100epoch và tối đa150phút. Có thể hoàn thành/dừng sớm; không lặp để lấp giờ.
Chỉ chạy sau khi đọc kết quả readiness/pilot hiện hành trong handoff. Script
`train-first-session.sh` phía dưới thuộc ca masked-query đã kết thúc.

**Kết quả corpus ngày29:**46.230request/198.765observations;96nhãn duplicate
holdout loại trước fit, còn46.134approved vectors, split27.738/9.150/9.246;
48readinesschecksPASS. Pilot4model đều exactresume/ONNX toàn bộ vectorPASS.
Residual APvalidation0,99875,precision98,13%,recall99,23%,FPR0,747%; chọn residual
**không trọng số** cho experiment tiếp theo (`formal_residual_config.yaml`,patience8).
Weighted residual là candidate so sánh. [Report hiện hành](reports/PRETRAIN_UPGRADE_20261029.json)
ghi đủ sensitivity/learning curves; test quality còn niêm phong. Source capture
là8171289, không phải các commit Student/firewall fast-forward nhận về giữa phiên.

## Ca residual đầu tiên — 29/10/2026

Đã thực hiện yêu cầu kiểm data rồi chạy ca tối đa **150 phút** trên source `8171289`.
Data gate mới **35/35 PASS**, dataset **19.275 request / 148 features** giữ nguyên hash.
Ca chạy **17:21:05–17:21:17 +07:00**, hoàn thành sau **11,616 giây**, dừng tại
**epoch 14 / step 2.534** do `early_stopping` (patience 8); checkpoint tốt nhất
ở **epoch 6 / step 1.086**. Không ép chạy tiếp để lấp đầy ngân sách thời gian.
Quota thực **8 CPU / 16 GiB**, MemoryHigh 15 GiB, swap 0; có job nền/log riêng và
sleep inhibitor trong lúc chạy. Đã kiểm checkpoint và ONNX parity **19.275/19.275 PASS**.

Validation-only: precision **90,83%**, recall **44,20%**, FPR **0,943%**, AP **0,7757**;
threshold chọn trên cùng validation nên kết quả sơ bộ. **Không mở test metrics,
chưa chọn champion hoặc triển khai Rust/live/enforcement**. Chưa nghiệm thu endurance
150 phút. Xem [báo cáo ca residual](reports/FORMAL_RESIDUAL_20261029.json) và [ledger06 mục22](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md#22-ca-train-residual-đầu-tiên--29102026). Các mốc “chưa train” ngày28/S0 phía dưới
là lịch sử. Run early-stopped là terminal; không force-resume bằng script ca đầu.

Nhánh `feat/ai-model-training`, nền code `fbe078d`. Package chạy offline, chỉ đọc file log hoặc bản export PostgreSQL. Không sửa hay kết nối để cấu hình Student/Security, không gọi firewall, không triển khai model vào Rust. Source, venv, configs và artifact AI nằm riêng trong thư mục này.

**Hiện hành28/10, sau nâng resource:** 8CPU/16GiB (MemoryHigh15GiB,swap0,Nice10), báo cáo [RESOURCE_GUARD](reports/RESOURCE_GUARD_20261028.json). Pilot cũ vẫn là kết quả đo2CPU/12GiB.

**Workflow:** đọc [PRETRAINING.md](PRETRAINING.md) và mục “Nâng cấp ba nguồn” cho workflow được bàn giao; CLI cơ bản/S0 bên dưới còn dùng cho technical fixtures. Ca chính thức dùng launcher cgroup và report readiness ba nguồn.

## Khởi tạo và kiểm tra

Đã kiểm chứng trên Linux/Python **3.12.14**, CPU. Thư viện được pin cả trực tiếp lẫn bắc cầu trong `requirements.txt`; Python3.12 là môi trường chuẩn để tái lập checkpoint. Feature hiện hành là `ai-features-3` (148cột), normalizer3; profile ba nguồn `edge_masked_v1` và conservative past-flow context. UA product families/missing/unknown vẫn dùng vocab cố định. Canonicalv1.0 không đổi. Ba ứng viên dùng NumPy với tham số/activations/gradient/AdamFP32 (affine tích lũyFP64→roundFP32 để parity ổn định) có trạng thái tường minh: MLP8 lớp, benign-only autoencoder và residual tabular nhỏ; xem phần28/10 phía dưới. Không yêu cầu Torch/CUDA/LightGBM để chạy S0. Đây là lựa chọn triển khai MLP/AE nhẹ của nhánh, chưa chọn champion trên dữ liệu thật.

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

Kết quả S0 **lịch sử featurev1/125cột** đã đo **27/10/2026 12:39:52–12:40:01+07:00**:42tests PASS;960requests/3403observations,125features,train576/val192/test192; exactresume và ONNX960/960 mỗi model. PeakRSS cao nhất208.77MiB,2threads; wall9.209335s. Report metadata có checksum: [`reports/S0_20261027.json`](reports/S0_20261027.json). Hai run chính optimizer0.015538449s, reference0.015986770s riêng; **train dữ liệu thật0giờ**. Artifact binary/checkpoint local nằm `.artifacts/synthetic_s0_20261027_final`, không có trong Git. Model metrics ở report chỉ kiểm việc tính/xuất metrics, không là bằng chứng phát hiện tốt.

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

Output `observations.parquet` giữ quan sát đã lọc; `requests.parquet` gộp HTTP theo requestID + IP tương thích + cửa sổ2s. Student ưu tiên actor/role, Nginx/EVE bổ sung bytes/metadata. Cùng IP/thời gian chỉ là context, không merge các request NAT. Profile `native` giữ same-flow context đã quan sát. Profile `edge_masked_v1` dùng flow client đã hoàn tất ít nhất65giây trước request; không giả thành packet counters của request hiện tại. Xem PRETRAINING cho receipt-time limitation.

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

`feature_spec.json` v3 lưu thứ tự cột, fixed one-hot vocab, imputation0, raw clipping, mean/std train-only, FP32 output/clipping, window/missing semantics và implementation hash. Scaler được fit **chỉ benign thuộc train**, nên autoencoder không học cả phân phối attack qua normalization. Unknown rows trong partition vẫn đóng góp context, chỉ các hàng nhãn được review mới có vector train.

Nhiều query/path đã mask ở producer: không thể tái dựng payload hay object ID. Feature lexical có availability flags, `query_original_*` chỉ có khi producer thực sự cung cấp counters; query length/entropy từ view đã lọc privacy, không giả là độ dài bí mật. URI diversity/bulk API chỉ là tín hiệu phụ trợ, **không đủ chứng minh IDOR**. Model này dùng dữ liệu post-response, chưa dùng để chặn request đầu tiên.

## Train, dừng, resume

```bash
.venv/bin/idps-ai train --dataset .artifacts/prepared-v1 \
  --config configs/train_config.yaml --run-dir .artifacts/runs/tabular-v1 \
  --epochs 20 --cpus 8 --memory-limit-gib 16 --max-duration-minutes 150
# Chạy ở ca sau, tiếp tục đúng cursor/optimizer step:
.venv/bin/idps-ai train --dataset .artifacts/prepared-v1 \
  --config configs/train_config.yaml --run-dir .artifacts/runs/tabular-v1 \
  --resume-from .artifacts/runs/tabular-v1 \
  --epochs 20 --max-duration-minutes 150
```

`--epochs` là **tổng epoch đích**. Chạy2epoch rồi thêm2 thì resume với `--epochs 4`. `--max-steps` là số step tối đa của phiên, dùng kiểm thử dừng giữa epoch. `configs/anomaly_config.yaml` chọn autoencoder; dùng run-dir mới, autoencoder chỉ fit benign. Training/calibration yêu cầu có benign và attack đã review ở validation để chọn threshold theo FPR; không tự tạo nhãn cho corpus chưa đủ.

CPU mặc định≤8threads và≤nửa affinity ban đầu, BLAS/OpenMP cùng cap, inter-op ONNX1. Linux affinity và RLIMIT_AS16GiB được kiểm hiệu lực; guard đo RSS cả process tree tại optimizer boundaries. Trainer không sinh dataloader/subprocess; S0 workers chạy nối tiếp. RLIMIT_AS là allocation ceiling từng process, không thay cgroup host. Memory guard tree không phải hard group cgroup; nếu bổ sung worker sau này phải nghiệm thu lại. Không bảo đảm nhiệt độ chỉ bằng thread cap; S0 không thay benchmark ca2–3giờ trên máy đích.

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

<a id="chuẩn-bị-trước-train--luồng-lab-riêng"></a>

## Chuẩn bị trước train — snapshot lịch sử27/10

Bổ sung27/10: package có `snapshot`, `review-export/import`, `observer-labels`,
`readiness`, `capacity-check` và lifecycle `lab-start/capture/finish/stop`.
Các bước này không fit model. Featurev2 gồm148cột; UA là inputfact từallowlist, không làruledecision. Khi tạo corpus sẽ sinhfeature_spec mới; không ghiđèartifactv1. `train --readiness-report <readiness.json>` kiểm
reportPASS, datasetSHA và sourceSHA trước khi fit; code/dataset đổi phải chạy lại gate.
Checkpoint/dataset v1 cũ không resume bằng source v2 mới; S0report cũ giữ nguyên lịch sử.
CLI cũ không kèm report vẫn giữ cho các kiểm thử kỹ thuật/fixture; đó không phải
đường bàn giao train dữ liệu lab đã duyệt.

`configs/pretrain_policy.yaml` là ngưỡng data-readiness cho **offline lab pilot**:
ít nhất3.000request,90%nhãn reviewed,200benign/partition,8mẫu/family/partition,
2connectedgroups/partition,3role,Student+Nginx,benignreads/mutations/errors,
identity/splitdisjoint/embargo300s và replayvectorparity. `readiness` trả exit3 khi
NOT_READY, vẫn ghi đầy đủ lý do. Không hạ policy để biến corpus thiếu thành PASS.
Đây chưa là chứng nhận dữ liệu đại diện hoặc model đạt chất lượng production.

### Tái lập corpus lab bằng request thực, không tạo log giả

Cần Java25, Docker với imagePostgreSQL17 đã có, Maven wrapper và Nginx binary tin
cậy. Không cài Nginx/Suricata hay thay cấu hình hệ thống. Mọi output nằm trong
`.artifacts/`; sourceStudent được `git archive` sang vùng này và build tại đó.
Lab dùng DB mới,15tài khoản giả (3ADMIN/6STAFF/6STUDENT), bản ghi khoa giả, mail/reset
workflows tắt và portsloopback18880/18881/55435. Không đọc .env/credential hoặc DB
ứng dụng hiện có. Port bận thì từ chối, không tái sử dụng dịch vụ đang chạy.

```bash
.venv/bin/idps-ai lab-start --output .artifacts/my-lab \
  --nginx-bin /absolute/path/to/trusted/nginx
.venv/bin/idps-ai lab-capture --lab-dir .artifacts/my-lab \
  --requests-per-campaign 320 --gap-seconds 620
.venv/bin/idps-ai lab-finish --lab-dir .artifacts/my-lab \
  --output .artifacts/my-pretrain-v1
```

Capture tạo15campaign theo9/3/3temporalbands với hai khoảng chờ620s thật.
SourceIP127.0.0.10–24 được bind thật trên loopback; mỗi campaign dùng user/session
riêng, không spoofXFF, không sửa timestamps. Các URIprobes có giới hạn chỉ đến
loopbacklab; không scan mạng ngoài, không gọi reset/mail, không cần app có lỗ hổng.
Normal/hardnegative và attackattempt được xác định bởi scenario/intent độc lập với
rule; observer ghi requestID từ response và expectedHTTPstatus, không ghi body,
cookie/token hoặc password. Payload/agent views khác nhau giữa temporalbands.

Để dừng thu, tạo file`.artifacts/my-lab/STOP`; không tiếp tục dùng một observer bị
ngắt như thể capture đã hoàn tất. Chạy`lab-stop --lab-dir .artifacts/my-lab` để dọn
đúng ownedPID/create-time và containerlabel. Raw capture lỗi vẫn giữ private để
chẩn đoán; không reset nguồn hoặc thay timestamp. Nếu `lab-finish` lỗi, giữ nguyên
artifact và xử lý nguyên nhân, không ghi đè dataset cũ.

`lab-finish` dừng lab, lọc đúng requestIDs củaobserver (giữcảpending; warmup ngoài chiến dịch cócount/hash riêng),
snapshot complete-line prefixes có checksum/read-back,
tạo labelsidecar, collect/prepare, bindprovenance và chạygate/capacity. Nó xuất
`handoff.json`, `NEXT_COMMANDS.txt`, datasetParquet/feature_spec và reviewqueue.
**Không tự thực thi lệnh train.** Giai đoạn train dự kiến trong
`configs/experiment_plan.yaml`; bắt đầu5epoch để đo, không ép chạy đủ150phút.

Giới hạn của corpus đầu:

- Đây là HTTP thật qua Student/Nginx với tài khoản/đối tượng giả, không phải traffic
  production hoặc bộ hành vi người dùng đại diện.
- Để nghiên cứu lexicalfeatures, lab giữ một NginxJSON view riêng có queryprobes
  không nhạy cảm. Templateedge hiện hành bỏqueryvalues. Trước deployment phải
  nghiệm thu nguồnfeature tương thích hoặc đổi inputprofile; modelpilot không
  được giả định hoạt động giống hệt trên metadata đãmask.
- Không có EVEcapture thật nếu thiếu quyềnpacket-socket. Không sinh EVEgiả để
  thay thế. Flowfeatures giữmissing; pilotnày không nghiệm thu nhánhnetworkflow.
- Nhãn chứng minh scriptedintent và responsecontract, không chứng minh exploit
  thành công. Behavioralclass là scriptedbulkreadattempt; cần dữ liệu/hardnegative
  thực tế và review thêm để đánh giá ý nghĩa phát hiện hành vi.
- Nhiều campaign ngắn nên windows60/300s cócontextincomplete; report ghi tần suất
  flags và cộtconstant. Cần chiến dịch dài hơn trước đánh giá hành vi dài hạn.
- RoleSTUDENT chưa có hồ sơ cá nhân gắn với fixture; một sốprofile404 làhardnegative
  dự kiến. Không dùng corpus này làm bằng chứng toàn bộStudentworkflow đã coverage.

### Review dữ liệu đã có từ VM hoặc snapshot riêng

```bash
.venv/bin/idps-ai snapshot --input student=/snapshot/student-audit.log \
  --input nginx=/snapshot/access.log --data-kind lab_capture \
  --output .artifacts/raw-snapshot-v1
.venv/bin/idps-ai review-export --dataset .artifacts/collected-v1 \
  --output .artifacts/review-page-1 --offset 0 --limit 1000
# Chỉ điền cột family/campaign/confidence/review_status/evidence_ref của labels.csv.
.venv/bin/idps-ai review-import --review-dir .artifacts/review-page-1 \
  --dataset .artifacts/collected-v1 --reviewer reviewer-a \
  --hmac-key-file .artifacts/private/training-redaction.key \
  --output .artifacts/approved-labels-v1
```

CSV chỉ chứa requestkeyHMAC và context đã lọc; không export query/body/PII.
Import kiểm nguyên vẹn context/dataset, cấm sửa request metadata, yêu cầu evidence
và revieweridentifier không nhạy cảm. Blank/pending không được tự chuyển benign.
Chuẩn bị version mới bằng labelsidecar đã review; không sửa dataset cũ.
Provenance là hồ sơ có checksum để audit, không phải chữ ký chứng minh người khai
báo trung thực. Snapshot nhiều nguồn là cácprefix độc lập, không atomiccross-source.

Nhãn observer đầu có correctionđược ghi riêng cho benignHEAD/OPTIONScatalog403:
SpringSecuritygrantGET không tự grant hai method này. Các lỗi bất ngờ khác vẫn
pending; không map403→attack hoặc success→benign. Cần giữ reportcorrection và
sourcecontract, không xóa bất lợi để làm đẹp số liệu.

## Nâng cấp ba nguồn và pilot — 28/10/2026

Feature hiện hành **v3/148cột**, normalizer3, profile `edge_masked_v1`.
Đọc [PRETRAINING.md](PRETRAINING.md) trước khi thu/train. Report27 và S0 là lịch sử.
Các lệnh dưới chạy từ gốc repo, chỉ sử dụng lab do AI tạo:

```bash
ai-training/.venv/bin/idps-ai lab-start \
  --output ai-training/.artifacts/my-three-source-lab \
  --nginx-bin /absolute/path/to/trusted/nginx
ai-training/.venv/bin/idps-ai lab-capture-eve \
  --lab-dir ai-training/.artifacts/my-three-source-lab \
  --campaign-seconds 420 --requests-per-campaign 1280
ai-training/.venv/bin/idps-ai lab-stop \
  --lab-dir ai-training/.artifacts/my-three-source-lab
ai-training/.venv/bin/idps-ai decode-pcap \
  --pcap ai-training/.artifacts/my-three-source-lab/traffic.pcap \
  --runtime /absolute/path/to/trusted-suricata8-runtime \
  --output ai-training/.artifacts/my-three-source-lab/eve
ai-training/.venv/bin/idps-ai lab-finish \
  --lab-dir ai-training/.artifacts/my-three-source-lab \
  --output ai-training/.artifacts/my-three-source-dataset
```

Runtime có `usr/bin/suricata`, `etc/suricata/` và thư viện tương ứng, hoặc dùng `/`
nếu máy đã được quản trị cài runtime đúng phiên bản. Phiên này chỉ tải/extract
các gói Ubuntu8.0.3 trong artifact riêng; không cài global. Nginx/Java25/Podman/
PostgreSQL17 và quyền user namespace là prerequisite. Máy khác có thể cần quản
trị cấp quyền; không dùng host-network/privileged để né lỗi rootless.

`lab-capture-eve` chuyển proxy/client sang namespace riêng; backend/DB vẫn là
fixture đã tạo. File `STOP` trong lab hủy capture, không chứng nhận output dở dang.
Lỗi hoặc ngắt capture cần `lab-stop` để dọn backend/DB trước khi tạo lab mới.
`lab-finish` phát hiện profile/capture ba nguồn, kiểm PCAP/EVE hash và dùng policy
ba nguồn. Không ép corpus cũ qua policy bằng cách hạ các ngưỡng thực.

```bash
ai-training/.venv/bin/idps-ai pilot \
  --dataset ai-training/.artifacts/my-three-source-dataset/prepared \
  --readiness-report ai-training/.artifacts/my-three-source-dataset/readiness/readiness.json \
  --output ai-training/.artifacts/my-three-source-pilot --max-threads 2
```

Pilot chạy tuần tự MLP/AE/residual:2epoch→tiến trình mới resume đến5epoch,
reference 5 epoch, ONNX parity trên mọi prepared row. Metric/threshold chỉ ởval;
có thêm missing-flow/actor/response sensitivity và rule-or-AI diagnostic nếu
`validation-rule-facts.json` đi kèm dataset. Đây không là ablation retraining hay
champion selection. Dùng cgroup cho toàn pilot nếu cần hard cap cả nhóm; bằng
chứng phiên này ghi ở report/ledger.

Ca chính thức dùng launcher có hard cgroup (bắt buộc report readiness):

```bash
ai-training/.venv/bin/python -m idps_ai.training.session \
  --dataset /absolute/path/to/prepared \
  --readiness-report /absolute/path/to/readiness.json \
  --config ai-training/configs/formal_residual_config.yaml \
  --run-dir /absolute/path/to/new-run \
  --epochs 100 --max-duration-minutes 150 --cpus 8 \
  --memory-limit-gib 16 --checkpoint-every-seconds 300
```

Không tự chạy lệnh này sau pilot. Run mới có config học riêng; resume cùng run
thì thêm `--resume-from` và giữ dataset/config/source không đổi. Nếu job xong sớm,
không kéo dài cho đủ2–3giờ. Launcher từ chối vượt50% CPU affinity hoặc trầnRAM16GiB do user chỉ định,
kiểm cgroup thực; MemoryHigh15GiB,Nice10/swap0.16GiB là52,96% RAM OS-visible
trên máy này; không gọi là chính xác50%. Giới hạn tài nguyên riêng job không giới
hạn CPU/RAM của các app/VM khác trên máy.

Kiểm đầy đủ gồm engine thật và packet integration:

```bash
IDPS_AI_TEST_SURICATA_RUNTIME=/absolute/path/to/trusted-suricata8-runtime \
  ai-training/scripts/check.sh
```

Nếu không cấp runtime test engine sẽ ghiSKIPPED rõ ràng. Kiểm packet namespace
cần Linux `unshare`, `ip`, `tcpdump` và AppArmor cho phép dừng process. Không bỏ qua
một lỗi capture rồi báo corpus ba nguồn đã sẵn sàng.


## Handoff sau nâng tài nguyên

Script ca đầu dùng `dataset-ready/readiness-resource8/readiness.json`; artifact
`readiness-final` và `pilot-ready` trước đó vẫn bất biến. Các directory fail/stale,
NEXT_COMMANDS cũ, cache và log tạm đã dọn; metadata lịch sử trong reports vẫn giữ.
Source/config/script/test và dataset đã duyệt không bị xóa. Venv và native runtime
Suricata đang dùng cho tests được giữ; không có dữ liệu/model/khóa vào Git.

</details>
