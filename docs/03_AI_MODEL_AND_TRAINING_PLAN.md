# 03 — Thiết kế AI và training theo ca 2–3 giờ

## Kết luận AI từ hai holdout mới — 2026-10-30T21:35:36.891996+07:00

**Không chọn champion, không train chính thức.** Giữ baseline MLP 252.680 và GLU 9.675.784 tham số/207 cột. Nhánh request 70 cột có MLP 217.608, GLU 9.535.496 và Denoising AE 233.670 tham số trainable; giảm input làm đổi count, không thêm padding.

Partial-label loss mới dùng FP64 logsumexp cho tổng xác suất 7 head non-benign. Unknown family giữ `-1`, không gán bừa SQLi; known family có conditional CE weight 0,2. Binary smoothing 0,005; MLP/GLU dùng AdamW, decay W=1e-4, global gradient clip=1; GLU dropout=0,1. Diagnostic dùng balanced weights **train-only**, seed=17, batch=128, lr=0,0003, warmup=15 rồi cosine tới 300 update. AE chỉ fit benign đa nguồn. Ngưỡng là max source-specific benign calibration quantile tại target FPR 1%, không chọn bằng attack/test scores.

Hai study ngắn: 2 epoch, tương đương chỉ 20 supervised update do 1.233 unique view; sau đó diagnostic 300 update cố định. Fresh-process 100→300 bằng continuous chính xác ở parameters/Adam/RNG/permutation/history. Mỗi study ONNX toàn 115.980 vector/model PASS rtol=1e-5, atol=1e-6. Diagnostic wall time 185,34 giây cho tất cả model/reference/export; riêng GLU optimizer 46,03 giây. Đây là kiểm tra ngắn, không phải train 3 giờ hoặc bằng chứng học tổng quát.

| Request model | Validation AP | Fresh lab recall / FPR | PKDD test recall / FPR | Fresh lab batch-1 p95 |
| --- | --- | --- | --- | --- |
| MLP 217k | 0,82914 | 40,625% / 0% | 3,726% / 1,162% | 0,138 ms |
| GLU 9,535M | 0,80711 | 0% / 0% | 1,132% / 0,724% | 4,483 ms |
| Denoising AE 233k | 0,75786 | 36,458% / 18,578% | 40,212% / 0,105% | 0,135 ms |

Fresh lab primary task gồm 1.378 approved benign và 288 attack thuộc 4 họ payload. Scanner/brute/sequence nằm trong secondary diagnostic vì request-only không quan sát đủ. Latency gồm warm envelope/scaling/ONNX, không gồm URI projection/capture/Web. 0/1.378 FP không chứng minh production FPR bằng 0: upper bound nhị thức một phía 95% khoảng 0,217%, còn giả định IID bị hạn chế do cùng cohort. AE đạt precision public 99,82% ở khoảng 59% attack prevalence; không được chuyển thành precision production.

Vì sao model lớn chưa hơn baseline: profile cũ mask mất token payload ngoài allowlist; positive độc lập ít, campaign dễ đoán và validation concurrent; nhiều tham số không bù thiếu quan sát. Diagnostic cải thiện validation nhưng GLU vẫn overconfident trên OOD benign, ngưỡng max-calibration 0,998768 khiến fresh lab recall bằng 0 dù AP=0,808. Đây là bằng chứng về visibility/calibration/support, **chưa phải causal ablation chứng minh một nguyên nhân duy nhất**.

Đối chứng frozen 207 feature trên đúng cohort mới đủ 3 nguồn: GLU gốc recall 71,18% / FPR 73,22%; GLU tuned 80,56% / 69,09%; MLP 253k 7,64% / 5,52%, tại ngưỡng cũ. Không thể giải thích thất bại này chỉ bằng thiếu flow của public data. Cần positive đa nguồn, human review, multi-seed và cohort sealed mới cho mọi tuning tiếp theo. Không ép GLU thắng hoặc hạ ngưỡng theo test. Original test quality vẫn kín.

[Báo cáo hiện hành](../ai-training/reports/REQUEST_PROFILE_20261030.json), [handoff](../ai-training/FINAL_TRAINING_HANDOFF.json), sổ bàn giao 06 mục 27. Các snapshot phía dưới là lịch sử.

## Challenger 9,68M — kết quả kỹ thuật/validation — 2026-10-30T15:52:59+07:00

| Candidate | Tham số neural | AP | Precision | Recall | F1 | FPR | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deep_mlp | 252680 | 0.999436 | 98.63% | 98.92% | 98.77% | 0.564% | 0.092 |
| gated_residual | 450056 | 0.999526 | 97.78% | 99.78% | 98.77% | 0.930% | 0.146 |
| hist_gradient_boosting | cây, không phải neural | 0.999115 | 99.74% | 99.37% | 99.55% | 0.107% | 1.697 |
| residual | 17992 | 0.997758 | 98.14% | 97.99% | 98.06% | 0.762% | 0.014 |
| residual_glu | 9675784 | 0.997228 | 98.01% | 98.92% | 98.46% | 0.823% | 5.363 |

AP trên 6 campaign selection (9.246 request), threshold fit riêng trên 3 campaign
calibration (4.623 request). Không dùng validation trong fit/early stop; checkpoint
cuối fixed 2 epoch. ONNX p95 neural và sklearn p95 tree là backend khác nhau, warm
batch1 model-only; không là network/end-to-end SLO. Báo cáo có bootstrap95% theo
campaign với threshold cố định, precision/recall/F1/FPR,AP,per-family và latency.

Pilot neural wall790.413s; optimizer chính
126.775240s, reference riêng
136.867438s. Cả 4 models exact resume và
ONNX 69.345/69.345 PASS; test quality giữ kín, latency dùng val. Main AP trừ best-other
**-0.002298**; không mặc định 10M tốt hơn. Best AP hiện
`gated_residual`, chưa champion vì thiếu data/realism/independent
environment acceptance. AE/baseline cũ còn nguyên như các snapshot lịch sử.

Model/resource/source/checkpoint/algorithm metadata đầy đủ trong [báo cáo](../ai-training/reports/SCALE_UPGRADE_20261030.json).
Formal 10M NOT_RUN và data gate NOT_READY; chỉ technical pilot≤2 epoch/8 phút/session.

## Thiết kế đã triển khai: residual SwiGLU v5 — 30/10/2026

Challenger `residual_glu`, **9.675.784 tham số trainable** với 207 đầu vào. Đây
là ứng viên chính để nghiên cứu khi đủ dữ liệu, chưa thay champion/baseline.
Không tăng tham số bằng padding, embedding ID hoặc tensor không dùng.

| Thành phần | Kích thước | Tham số |
| --- | --- | ---: |
| Projection + ReLU | 207→1024 | 212.992 |
| 3 residual blocks | mỗi block: LayerNorm, value/gate/down 1024→1024 | 9.452.544 |
| Final LayerNorm + softmax head | 1024→8 | 10.248 |
| Tổng | toàn bộ tensor tham gia forward/backprop | 9.675.784 |

```text
h = ReLU(x Win + bin)
for block in 0..2:
    n = LayerNorm(h, eps=1e-5)
    a = (n Wvalue + bvalue) * SiLU(n Wgate + bgate)
    h = h + 0.5 * (Dropout(a, p=0.1) Wdown + bdown)
p = softmax(LayerNorm(h) Wout + bout)
```

Không gọi đây là Transformer/TCN/TabM. Gate học tương tác của các đặc trưng
request và hành vi; ngữ cảnh thời gian đến từ aggregate nhân quả, không từ nhãn
hoặc future flow. Quyết định chọn residual tabular cho CPU tham khảo nghiên cứu
[ResNet/Transformer cho tabular](https://arxiv.org/abs/2106.11959) và
[TabM](https://arxiv.org/abs/2410.24210), nhưng implementation là riêng và phải
đấu baseline trên dữ liệu của dự án. Không có model tối ưu phổ quát chỉ từ paper.

**Thuật toán:** cross-entropy từ logits bằng log-sum-exp với label smoothing 0,02;
AdamW (betas 0,9/0,999, epsilon 1e-8), decay 1e-4 chỉ với W; gradient global L2
clip 1,0. Warmup rồi cosine decay theo committed global step. LayerNorm thống kê
FP64 rồi round FP32; affine vẫn FP64 reduction→FP32, params/grad/Adam FP32.
SiLU dùng sigmoid FP64→FP32 như graph ONNX, tolerance giữ rtol=1e-5/atol=1e-6.

Dropout chỉ trong train, PCG64 `SeedSequence(seed, optimizer_step, 23)`, độc lập
sampler. Checkpoint giữ Adam moments, seed/corruption contract, sampler, schedule,
loss history và learning config hash; resume không restart warmup. Inference và
ONNX không dropout. Mọi tensor đã có kiểm thử gradient; kiểm thử số hữu hạn, resume
và ONNX phải PASS trước pilot thật.

**Protocol mới:** fixed 2 epoch technical pilot, cùng data/batch128/LR0,0003 và
warmup30→cosine1000steps cho các neural candidates. Không dùng validation trong
fit hoặc early stopping; dùng checkpoint epoch cuối. Tách1/3 campaign validation
để fit threshold,2/3 để selection; không dựa nhãn/score để chọn nhóm. Báo precision,
recall,F1,FPR,AP,ROC,per-family,latency và campaign-bootstrap CI với threshold cố định.
Đây chưa là environment holdout. Tree baseline HistGradientBoosting32 iterations,
hyperparams cố định trước, chỉ dùng train; không tạo deployment bundle/pickle.
Không diễn giải các pipeline khác algorithm/regularizer như một architecture ablation.

**Giới hạn:** technical pilot≤2 epoch/8 phút mỗi session, formal 10M bị chặn khi chưa
có corpus 2M và calibration độc lập. Registry chưa tự ghép các shard có scaler khác
nhau; cần shared train-only scaler/assembled dataset có lineage trước formal.
Model lớn không bảo đảm tăng chất lượng hoặc chạy hết150phút. Chưa có human review,
đa môi trường thật, official train, test quality hay production/shadow acceptance.

## Pilot revision 4.1 đo thực — 2026-10-30T09:08:21+07:00

Bốn ứng viên đều chạy 5 epoch: process đầu chạy 2 epoch, process mới resume tới 5;
weights, Adam, lịch sử và sampler khớp reference chạy liền 5 epoch. ONNX parity
69,345 vectors/model PASS với tolerance gốc. Chất lượng trên test
vẫn niêm phong. Pilot mất 391.454 giây; thời gian optimizer
chính 26.005729 giây, reference riêng
29.627361 giây.

| Model | AP val | Precision | Recall | FPR |
| --- | ---: | ---: | ---: | ---: |
| deep_mlp | 0.998798 | 97.68% | 99.11% | 0.966% |
| denoising_autoencoder | 0.907042 | 96.06% | 58.68% | 0.986% |
| gated_residual | 0.999077 | 97.61% | 99.16% | 0.996% |
| residual | 0.999165 | 97.64% | 99.55% | 0.986% |

Ứng viên lớn cho thí nghiệm tiếp là `gated_residual`; AP supervised cao nhất kể cả đối
chứng thuộc `residual`. Chưa chọn champion. Báo cáo chứa đường
học, lỗi theo campaign và độ nhạy khi thiếu đầu vào. Cần đọc recall cùng FPR;
không coi recall tăng khi mất nguồn là cải thiện nếu false alarms cũng tăng.
Corpus scripted trên một topology và validation chia sẻ calibration chưa chứng
minh chất lượng production, zero-day hoặc độ bền ca 150 phút. [Báo cáo](../ai-training/reports/PRETRAIN_EXPANDED_20261030.json).

## Các ứng viên sâu, revision 4.1 — 29/10/2026

Yêu cầu mới mở rộng sức biểu diễn trong luồng AI. Các ứng viên dùng **189 đầu
vào**, gồm 148 cột của profile cũ và 41 đặc trưng cấu trúc mới. Không thay canonical
v1.0 hoặc đưa query/body nguyên văn vào mạng. Không dùng rule flags/SID làm đầu vào.
`ai-features-4.1` và projection v2 có contract/hash riêng; không force-resume
checkpoint `ai-features-4`/148 cột bằng revision này.

| Ứng viên | Kiến trúc | Tham số | Vai trò |
| --- | --- | ---: | --- |
| Residual nhỏ |189→64→64+skip→8 |16.840 |Đối chứng trên cùng corpus/split mới |
| Deep MLP |189→256→256→256→256→8 |248.072 |Học tương tác phi tuyến giữa cấu trúc request và cửa sổ hành vi |
| Denoising AE |189→256→256→128→256→256→189 |294.717 |Chỉ học benign; khôi phục vector sạch từ bản bị làm nhiễu |
| Gated residual |189→256, ba block gated, head 8 lớp |445.448 |Học mức đóng góp của từng nhánh residual theo request |

Deep MLP có bốn hidden layer ReLU và head softmax 8 lớp. Gated residual dùng:

```text
h0 = ReLU(x Win + bin)
a  = ReLU(h Wblock + bblock)
g  = sigmoid(h Wgate + bgate)
h_next = h + 0.5 * a * g       # lặp ba block; g là vector 256 chiều
p = softmax(h_final Wout + bout)
```

Gate là phép nhân học được theo từng chiều, không phải self-attention hay
Transformer. Bản này không thêm một sequence model riêng: ngữ cảnh thời gian
vẫn là các cửa sổ nhân quả 10/60/300 giây trong feature pipeline. Đây là lựa chọn
triển khai NumPy riêng, không khẳng định tái lập benchmark của
[nghiên cứu tabular residual/Transformer](https://arxiv.org/abs/2106.11959).

Denoising AE áp Gaussian noise σ=0,1 và masking probability=0,1 trên vector đã
chuẩn hóa trong **bước train**, rồi tối ưu MSE với vector sạch. Inference/ONNX
không thêm noise và dùng reconstruction MSE làm anomaly score; score không phải
xác suất tấn công. Chỉ những hàng benign của train được dùng để cập nhật weights.
Phương pháp lấy ý tưởng khôi phục đầu vào sạch từ
[denoising autoencoders](https://jmlr.org/papers/v11/vincent10a.html); không coi
noise trên feature là mô phỏng đầy đủ việc mất một nguồn log.

Nhiễu dùng PCG64 với `SeedSequence(seed, committed_optimizer_step)`. Seed, phiên
bản corruption và global step được kiểm khi load checkpoint. Cách lấy mẫu này
không tiêu thụ RNG của sampler; resume giữa epoch tái tạo đúng batch/noise kế
tiếp. Tests so weights, Adam moments và loss history với run liên tục, không chỉ
so số epoch hoặc loss gần bằng nhau.

Tất cả params/activations/gradient/Adam giữ FP32; mỗi affine reduction tích lũy
FP64 rồi round FP32 ở cả native và ONNX. Gated sigmoid tính FP64 trên logits đã
round FP32, clip [-80,80], rồi round FP32. Tensor graph dùng các op chuẩn, opset18;
parity vẫn **rtol=1e-5, atol=1e-6**, không nới tolerance để nhận model lớn.
Model metadata lưu architecture version, dimensions, corruption và arithmetic
contract; NPZ/JSON không chứa pickle hoặc object thực thi.

Classifier sâu tính cross-entropy từ logits bằng log-sum-exp với reduction FP64,
thay vì lấy log xác suất đã clip 1e-12. Dự đoán sai có logit margin 1000 phải có
loss 1000 và gradient hữu hạn, không bị làm phẳng thành 27,63. Forward probability
và ONNX vẫn theo contract trên. Validation objective của các classifier sâu dùng
cùng hàm ổn định; profile/model nhỏ cũ giữ ngữ nghĩa lịch sử.

Các config sâu dùng Adam, batch 128, LR 0,0005, gamma 0,98 mỗi 200 step, patience 15.
Đây là điểm xuất phát để đánh giá, không bảo đảm tránh bão hòa hay overfit. Model
lớn hơn cũng có thể học vẹt nhanh hơn. So sánh với residual nhỏ trên cùng corpus,
đọc train/validation loss, AP/FPR và từng campaign trước khi chọn ứng viên.
Pilot 5 epoch chỉ kiểm pipeline; không tự chọn champion hoặc chạy ca dài.

Ca do người vận hành khởi động dùng `train-expanded-session.sh`, tối đa 150 epoch
và 150 phút, 8 CPU / 16 GiB, checkpoint mỗi 300 giây, cgroup/affinity/thread guard như trước.
Early stop hoặc hoàn thành sớm vẫn hợp lệ. Không tăng epoch hoặc lặp ca chỉ để
tiêu hết 150 phút. Các run mới có directory riêng; source/data/learning config
khác bị từ chối resume. Metrics test cuối tiếp tục niêm phong.

## Điều chỉnh sau ca dừng sớm — 29/10/2026

150 phút là **trần wall-time**, không phải thời lượng bắt buộc. Residual 14.216
tham số trên 19.275 request có thể hoàn thành nhiều epoch trong vài giây; patience8
dừng khi AP validation không còn tốt hơn. Ca đầu dừng ở epoch14, best epoch6;
đây là kết thúc hợp lệ. Recall payload thấp và 59/148 cột hằng số là lý do nâng
telemetry/corpus trước khi tăng epoch hoặc kích thước mạng.

Ứng viên thứ tư giữ residual148→64→64+skip→8, thêm weighted cross-entropy:
`w_c ∝ sqrt(N_train / (8 * count_train[c]))`, chuẩn hóa trung bình trọng số bằng1.
Chỉ đếm nhãn train, không dùng tần suất val/test để tính trọng số. Batch loss là
`sum(w_y * -log(p_y)) / sum(w_y)`; Adam, clipping và ONNX inference giữ như cũ.
Đây là candidate để kiểm tra, không mặc định tốt hơn residual không trọng số.
Autoencoder vẫn chỉ fit benign, không dùng class weighting.

Checkpoint lưu class weights, running loss/count giữa epoch và history, nên resume
giữa epoch phải cho cùng weights/optimizer/history với run liên tục. Ghi thêm
training loss, validation loss theo objective tương ứng và unweighted all-class
validation loss. Với AE, validation objective dùng benign MSE; all-class MSE báo
riêng. Training loss là trung bình batch trong lúc cập nhật, không phải full-train
loss đo lại bằng weights cuối epoch.

Pilot mới so sánh bốn candidate ở5epoch,2→5epoch qua process khác và reference
5epoch, parity ONNX trên mọi vector. Threshold và các phép thử thiếu query/flow/
actor/response dùng validation; không mở test để chọn candidate. Sensitivity là
inference-only, không phải huấn luyện lại ablation. Query ablation tính lại view
URI đã mask, nên cũng bỏ raw-URI numeric projection nếu URI đó bị redaction.

Ca tiếp theo có config/script riêng, tối đa100epoch/150phút,8CPU/16GiB. Kết quả
pilot chọn residual không trọng số để thử tiếp (APvalidation0,99875,recall99,23%,
FPR0,747%), dùng `formal_residual_config.yaml`/patience8. Weighted residual với
patience12 vẫn là candidate so sánh. Không resume checkpoint featurev3 bằng featurev4.
Không lặp train để lấp giờ; cần nhiều seed/corpus và kiểm tra nguồn lỗi trước khi
chọn champion. Byte-CNN/TCN chưa được triển khai chỉ từ28 bộ đếm số này.

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
150 phút. Xem [báo cáo ca residual](../ai-training/reports/FORMAL_RESIDUAL_20261029.json) và ledger06 mục22. Các mốc “chưa train” ngày28/S0 phía dưới
là lịch sử. Run early-stopped là terminal; không force-resume bằng script ca đầu.

## Cập nhật resource sau pilot — 28/10/2026

Ca tiếp theo dùng **8logicalCPU/16GiB RAM**, CPUQuota800%, MemoryHigh15GiB,
swap0,Nice10; BLAS/OpenMP8,ONNX intra8/inter1 sequential. CPU là50% của16luồng;
16GiB là**52,96% RAM OS-visible** trên máy32GB danh nghĩa, được user chỉ định rõ.
77testsPASS,35readinesschecksPASS, guardprobe0optimizerstep; **không train chính thức
hoặc chạy lại pilot corpus thật**. [Báo cáo resource](../ai-training/reports/RESOURCE_GUARD_20261028.json).

Dataset prepared và pilot-ready giữ nguyên hash; readiness-final cũ cũng được giữ.
Readiness mới`readiness-resource8` gắn source hiện hành và được handoff/script sử dụng.
Các metric/giới hạn2CPU/12GiB ở các snapshot pilot phía dưới là lịch sử. Các attempt
fail/stale/cache/NEXT_COMMANDS cũ đã dọn; giữ raw capture evidence, runtime và venv
cần thiết. Xem ledger06 mục21 cho kiểm tra, danh sách dọn và commit.

**Ngày thiết kế:**26/10/2026; **cập nhật triển khai:**28/10/2026. MLP/autoencoder offline, causal features, trainer/checkpoint và ONNX đã được triển khai trong `ai-training/`; xem mục0. Byte-CNN/TCN, corpus production, Rust inference và champion/release vẫn là đề xuất. Hiện trạng code và data ở [00](00_PROJECT_OVERVIEW_AND_PROGRESS.md), [01](01_SYSTEM_AUDIT_AND_ARCHITECTURE.md), [02](02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md).

**Foundation update26/10/2026:** đã có exporter/canonical metadata cho successful reads/sessionHMAC/requestID/UA/HTTP/flow, nên các mô tả thiếu metadata ở baseline bên dưới cần đọc cùng02 hiện hành. Tại snapshot foundation chưa có trainer/model; cập nhật27/10 bên dưới thay thế trạng thái đó. Câu trạng thái thiếu corpus/trainer của baseline cũ đã được mục0B bên dưới thay thế cho phạm vi lab offline.

## 0B. Snapshot pilot trước nâng resource — 28/10/2026

**Trạng thái28/10/2026:** corpus mới có **19.275 request thật / 80.556 observations**, đủ Student audit + Nginx + Suricata EVE từ PCAP thật trong namespace lab. Split **11.565 / 3.855 / 3.855**, nhóm 9/3/3; mỗi campaign ≥420 giây, hai khoảng nghỉ 620 giây thật. Feature v3 / normalizer3, 148 cột, `edge_masked_v1`; canonical v1.0 giữ nguyên. Readiness **35 checks PASS**, **77 tests PASS / 0 skipped**. MLP/AE/residual đều chạy 2 epoch → tiến trình mới resume đến 5 epoch, exact với reference 5 epoch; ONNX parity toàn bộ prepared rows. Chỉ đánh giá validation; test metric chưa mở. [Report có hash](../ai-training/reports/PRETRAIN_PILOT_20261028.json).

Chưa chạy ca chính thức 2–3 giờ, chọn champion, port Rust hoặc bật AI response. Corpus vẫn là loopback với fixture giả / scripted intent; chưa đại diện production. Query bị mask thống nhất nên metadata AI không thấy nội dung payload. Flow chỉ lấy flow client đã kết thúc ≥65 giây trước đó, không backfill bằng đóng flow tương lai. Live receipt-time/TLS/feature parity và human realism review còn riêng.

Candidate mới là residual tabular148→64→64+skip→8,14.216 params FP32: `h1=ReLU(xW1+b1); h2=ReLU(h1Wr+br+h1); p=softmax(h2W2+b2)`. CE+Adam hiện có; finite-difference gradient, checkpoint/optimizer và ONNX có test. Lấy cảm hứng từ [tabular residual baselines](https://arxiv.org/abs/2106.11959), không khẳng định tái lập benchmark hoặc luôn thắng MLP. Không thêm framework nặng. Params/activations/AdamFP32; affine accumulationFP64 rồi roundFP32 trong cảNumPy/ONNX để giữ parity1e-5/1e-6 gầnzero; khôngnới tolerance. Byte-CNN/TCN vẫn cần contract/telemetry tương ứng.

Pilot có missing-flow/actor/response sensitivity ở threshold giữ nguyên, không phải ablation retraining. Rule baseline gồm bốn Nginxmap và Suricata thật, có subset web loại SYN-rate định trước; không chạy Ruststateful. OR fusion có báo khả thi budgetFPR1%, không so model và rule ở budget khác rồi kết luận hơn. Metric validation đồng thời dùng calibration nên lạc quan; test khóa cho nghiệm thu sau chọn protocol.

Launcher `python -m idps_ai.training.session` bắt buộc current three-source readiness và đọc lại cgroup. Máy đang chạy có 16 logical CPU affinity/RAM~32GB; CPUQuota 200%=2CPU≈12,5%,MemoryMax 12 GiB,MemoryHigh≤10GiB,swap0,Nice10. Hard quota áp cả service và child, affinity/BLAS thêm cap2. Kiểm thermal/endurance2–3giờ chưa làm. `scripts/train-first-session.sh` chuẩn bị residual100epoch/patience8/max150phút/checkpoint 300s; run mới, không resume pilot bằng config đổi. Script tự resume cùngrun khi cólatest tương thích; early-stopped run là terminal. Chưa thực thi; dừng sớm khi xong, không train cho đủ giờ.

## 0A. Gate trước train — snapshot lịch sử27/10/2026

AI có `lab-start/capture/finish/stop`, `snapshot`, `observer-labels`,
`review-export/import`, `readiness`, `capacity-check`. Các bước này không fit model.
`lab-finish` chuẩn bị Parquet/features/provenance/report và in lệnh train, không
thực thi chúng. `train --readiness-report` kiểm reportPASS, dataset và sourceSHA;
source đổi phải chạy gate lại. CLI cũ khôngreport vẫn phục vụ technicalfixtures,
không phải đường bàn giao pilot đã duyệt.

Featurev2 có148input (thêm UAallowlistmulti-hot/missing/unknown); MLP148→32→8 có
5.032tham số, AE148→32→148 có9.652tham số khi bắt đầurunmới. Chưa fit hai model này
trên corpuspilot. Cấu hình optimizer/checkpoint không bị đổi; không force-resume
checkpoint125input cũ. Canonicalv1.0 không bị thay.

`configs/experiment_plan.yaml` khóa đề xuất firstpilot5epoch, tốiđa150phút/phiên,
2threads/12GiB; chọn trênval, không tunethreshold trêntest. Đây là planNOT_STARTED,
không phải yêu cầu train đủ sốgiờ. Rulebaseline trướcfit chỉ đo bốn Nginxmapflags
trênvalidation, không gọi là fullRust/Suricataensemble. Capacityreport là read-only
I/O/RAM/disk estimate, không giả thành epoch/thermalbenchmark.

READY_FOR_OFFLINE_PILOT chỉ chứng minh preconditions của corpuslab theo policy.
Cần review inputavailability (labquery khác edge đãmask), humanrealism, campaign dài,
modelquality/FPR, response429/statusablation, Rustport/parity, shadow và targetmachine
endurance trước khi chọnchampion hoặc cho phảnứng. Sổ06 mục18 ghi hash/count/test
và giờtraincorpus=0; kết quả S0 v1 ở mục0 là lịch sử.

## 0. Triển khai và bằng chứng S0 — 27/10/2026

Nhánh `feat/ai-model-training`, base `fbe078d`; toàn bộ source/env/config/checkpoint dưới [`ai-training/`](../ai-training/README.md), chỉ đọc snapshot/export. Không sửa Student/Security hay tích hợp inference vào Rust. Quyết định D08 và ledger6phiên ở [06 mục16](06_AI_HANDOFF_AND_RUN_LEDGER.md#16-ai-data--training-pipeline--27102026).

- **Supervised:** NumPy FP32 MLP125→32→8, ReLU/softmax,4296tham số, CE+Adam; score1−P(benign). Đây là lựa chọn MLP nhẹ trong các kiến trúc cho phép, chưa chọn champion.
- **Anomaly:** NumPy FP32 autoencoder125→32→125,8157tham số, MSE+Adam; chỉ fit72benign train ở S0. Scaler cũng chỉ fit benign train; reconstruction error không là xác suất attack.
- **Environment:** Linux/Python3.12.14; exact direct/transitive pins, requirementsSHA trong report. Không cần Torch/CUDA. CPU default≤4 và≤nửa affinity ban đầu, S0cap2; BLAS/ONNX cùng cap. RLIMIT_AS12GiB có readback, process-tree RSS guard ở optimizer boundary; không phải cgroup hard cap toàn nhóm. Không sinh training workers.
- **Resume:** NPZ `allow_pickle=False`+JSON, architecture/learning/data/shard/feature/env/all-source hashes, Python/NumPy RNG, Adam moments, scheduler,nextLR, permutation/cursor,best/patience. Atomic temp/fsync/rename, latest/previous/best, runlock; signal chỉ đặt flag. Code/env/config bất biến lệch bị từ chối. Target epoch là tổng đích, ca150phút là operational limit.
- **Evaluate/export:** validation-only threshold maximize recall với empiricalFPR≤1%; AP/trapezoidPR-AUC/ROC-AUC/F1/confusions/perfamily/ROCdiagnosticrecall@FPR≤1%, warm batch1 p50/p95/p99. ONNXopset18/IR9 CPUExecutionProvider, feature/golden/modelmanifest/checksum/modelcard đi cùng. Test set không chọn deployment threshold.

**S0 pipeline/resume verification trên synthetic fixture:**27/10 12:39:52.687–12:40:01.896+07:00, wall9.209335s. Hai nhánh đều2epoch→newprocessresume thêm2, exact state bằng4epoch liên tục; LR thực sự qua decay boundary (S0decay_steps5; production config100). MLP36steps, AE8steps; ONNX parity **960/960 mỗi nhánh**, rtol1e-5/atol1e-6. **42tests PASS** gồm mid-epoch, process signals, fault/corruption/mismatch tests và reference preprocessing golden vectors.

Peak treeRSS cao nhất6training sessions208.77MiB,2threads; modelONNX17.678/33.136byte. Warm model-only ORTp95 MLP0.004404ms/AE0.005234ms, không gồm preprocessing/queue/coldstart và không là benchmark targetZenbook/production. Hai run chính optimizer0.015538449s, hai reference0.015986770s, preprocessing1.067500s được tách; **training dữ liệu thật0giờ**. [Báo cáo có hash/metrics đầy đủ](../ai-training/reports/S0_20261027.json).

S0 ngắn không nghiệm thu cgroup controller, SSD/power-loss durability thực, nhiệt/độ mượt hay ca2–3giờ. Metrics synthetic thấp/thiên lệch vẫn được giữ nguyên (MLPrecall0.125; AErecall0 ở validation-fitted threshold trên test); không dùng làm chất lượng phát hiện, production FPR hoặc zero-day claim. Bước tiếp theo là corpus thật có nhãn/split, rule-only baseline và target-machine benchmark, rồi mới quyết định train dài. Các kiến trúc neural nâng cao/ngân sách bên dưới vẫn là kế hoạch.

## 1. Bài toán và lựa chọn ban đầu

Không thể khẳng định một kiến trúc “tối ưu nhất” khi chưa có corpus đại diện, CPU SKU và benchmark. Lựa chọn khởi đầu phù hợp repo là **mô hình nhỏ theo từng loại quan sát**, CPU-first, tách khỏi đường HTTP ứng dụng và khỏi executor firewall. Phải so sánh với rule-only và baseline đơn giản trước khi chấp nhận neural model.

Đầu vào audit ở baseline khảo sát thiếu successful GET/session/request correlation; foundation đã bổ sung metadata này, còn payload/object identity đầy đủ vẫn thiếu. Vì thế không thể lấy dữ liệu hiện có rồi hứa mô hình bắt đủ chuỗi hành vi/payload/flow. Dùng các tier dữ liệu theo 02; chỉ kích hoạt nhánh model khi source/features của nhánh đó tồn tại và đạt kiểm tra chất lượng.

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
| RAM cgroup | Hiện hành: `MemoryHigh=15G`, `MemoryMax=16G`, cả cây tiến trình;16GiB là mức user chỉ định (52,96% RAM OS-visible) |
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

CLI đã triển khai: `.venv/bin/idps-ai train --dataset <prepared-dir> --config configs/train_config.yaml --run-dir <run-dir> --epochs 20 --max-duration-minutes 150 --resume-from <run-dir>`. Bỏ `--resume-from` ở phiên đầu; xem README cho pipeline collect/prepare. Checkpoint300s cấu hình trong YAML. CLI cũ `--session-hours/--resume` chỉ là thiết kế đã được thay thế, không dùng để chạy.

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

PyTorch hướng dẫn lưu cả optimizer state để tiếp training; `state_dict` weights đơn thuần chưa đủ. Tham chiếu: [Saving and Loading Models](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html). Bản NumPy CPU hiện hành đã lưu cursor/hash/RNG/early-stop và Adam trong NPZ/JSON; không có Torch state hoặc AMP vì không dùng Torch/AMP. Các candidate Torch tương lai phải nghiệm thu lại checklist này.

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

S0 chỉ PASS khi checkpoint trước vẫn load được sau crash, cursor không bỏ qua mẫu, lịch LR không reset và quota/RAM có hiệu lực. Ghi báo cáo, hash và lệnh tái lập vào 06. Các fault/resume tests đã PASS trong42tests và S0synthetic27/10; nghiệm thu cgroup/thermal/ca dài/mất điện máy thật vẫn NOT_RUN. Không đánh đồng mocked ENOSPC hay process death tại fsync với power-loss SSD.

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

Rust integration cần chọn và pin binding/runtime tương thích sau một spike riêng; `Cargo.toml` hiện **chưa có ONNX Runtime**. Triển khai worker inference cách ly, load model một lần, queue bounded, timeout/circuit breaker, shadow metrics; lỗi AI không làm rule/HTTP pipeline dừng. Nhánh AI chỉ thêm package Python riêng; không thêm thư viện/sidecar vào Rust trong phiên này.

Giữ FP32 làm chuẩn. Chỉ dùng int8 sau calibration phù hợp nếu latency/RAM tốt hơn và recall/FPR/parity không suy giảm quá giới hạn đã thống nhất; quantization không mặc định nhanh hơn mọi CPU/op. Tham chiếu [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).

Bundle release gồm: model hash, feature schema/vocab/scaler, calibration/thresholds, model card, dataset/split provenance, commit/env lock, ONNX opset/runtime compatibility, golden vectors, metrics và quyết định review. Rollout shadow → human-reviewed canary theo service/tenant → alert-only production; IPS AI-only chỉ xét sau gate riêng. Champion cũ giữ sẵn, đổi pointer/version nguyên tử, rollback khi FP/drift/resource lỗi. Không tự học từ traffic live chưa duyệt vì nguy cơ data poisoning; version và review trước mỗi fine-tune.

## 9. Quyết định còn mở

Chưa chốt OS/CPU, artifact store, label volume, lưu lượng thật, tỷ lệ benign/attack, inference deployment target, license dataset và tiêu chí enterprise ngoài lab. Những thiếu sót này không cản việc đọc repo/viết docs; chúng là điều kiện phải xác minh ở các task tương ứng trong 04, trước khi chốt lịch và ngân sách cuối. Trạng thái train hiện hành và form bàn giao nằm tại [06](06_AI_HANDOFF_AND_RUN_LEDGER.md).
