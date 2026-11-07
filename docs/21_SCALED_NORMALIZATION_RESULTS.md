# Scaled normalization — kết quả ngày 2026-11-07

**COMPLETED; REJECT candidate cho mục tiêu nâng cấp đã khóa. Giữ Frozen Request
Intelligence v2 trong shadow.** Không đủ bằng chứng kết luận normalization riêng
luôn vô ích; thí nghiệm một seed này không đạt tiêu chí cải thiện đã precommit.
Không train thêm, thay threshold frozen, promote, mở prospective hoặc sửa hệ thống.

## Completion và tính toàn vẹn

Experiment `scaled-normalization-20261107-v1`, branch
`feature/ai-idps-shadow-integration`, training source revision `3d932d0`.
Hai arms cùng120,435TRAIN views,50,696parameters,seed31,batch256,lr0.001,
3,072updates/arm và786,432sample exposures/arm. Đây không phải requests mới.
Chỉ fit publisher NORMAL/ANOMALOUS;0Oracle fitting exposures.

Dataset fingerprint:
`e35dae2dc79f9fa43860ff75d4cb694733c9e42d42a687f0f6b59ffe05a0fba5`.
Plan SHA:
`c3b92cd2afddf6c4b585bce02b57160ca2c063e0f98e4324379827ba9d0d4bc3`.
TRAIN/CAL/DEV files, source/environment bindings và native checkpoint manifests
được kiểm trước evaluation. Hai metrics logs có đủ step1–3072 liên tục. Final
RNG/sampler cursor/scheduler/config giống nhau giữa haiarms; không chọn best loss.

| Arm | Final checkpoint directory, dưới experiment root | Manifest SHA256 | Final batch loss |
|---|---|---|---:|
| Control |`control/checkpoints/step-000000003072-8e9b465eb0d4`|`6092dbe90c665c085f4d806ea81155fbc5adc047b2a09811e56eda14eead6131`|0.09039544|
| Challenger |`challenger/checkpoints/step-000000003072-8ea2f2482b41`|`14bf04ede2febaf3695ab4f4592db42d009677f4660253bb97edbc02b6dfc697`|0.08956445|

Loss thấp hơn không phải quality gate. Recovery proof vẫn chỉ first600TRAIN,
4updates/fresh-process/epoch-wrap bitwise; chưa có full3072-step interruption/resume.

## Publisher DEVELOPMENT, nhãn anomaly của publisher

CAL retained2,437views, trong đó1,042NORMAL. DEV retained2,041views gồm1,176ANOMALOUS
và865NORMAL,1,746template groups; near quarantine và original roles không đổi.
New-arm threshold là q99(higher) trên CAL NORMAL, strict`>`; frozen giữ threshold gốc.

| Model | Threshold | TP | FN | FP | TN | Anomaly TPR | NORMAL flag fraction | Average precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen v2 |0.88262379|1,085|91|9|856|92.26%|1.04%|0.995851|
| Matched control |0.66185158|1,091|85|10|855|92.77%|1.16%|0.995885|
| Challenger |0.66136199|1,100|76|12|853|93.54%|1.39%|0.995911|

Challenger-control: TPR **+0.7653pp**, NORMAL flags **+0.2312pp**.
Paired observed-template bootstrap1,000resamples,95%percentiles:
TPR delta[-0.1721,+1.7483]pp; NORMAL delta[-0.2387,+0.8226]pp.
Không đạt point gates≥+2pp TPR/≤+0.2pp flags, cũng không đạt interval gates.
Khoảng trên không bao gồm seed-to-seed, annotation hoặc environment uncertainty.

POST benign DEV bị flag3/56 ở cảnewarms, GET6/784. Hai FP tăng thêm thuộc OPTIONS:
control1/13 thành challenger3/13. Không suy ra toàn bộ improvement đến từ POST.
Publisher TRAIN có112,977GET so với6,426POST; các method CONNECT/HEAD/OTHER/PATCH/PUT
không có NORMAL (tổng646ANOMALOUS). Đây là cấu trúc có nguy cơ shortcut, chưa phải
chứng minh model đã dùng method như nguyên nhân quyết định.

## Internal Oracle, exposed DEVELOPMENT và Rules

OracleCAL có10benign/2attempts. Control threshold=max benign0.9975697398,
challenger0.9925589561, strict`>`, theo protocol có sẵn. Cảhai đạt0/10CAL flags
nhưng **0/2attack detections**. Những số CAL này không chứng minh population FPR.
Frozen giữ0.8826237917, flag4/10benignCAL và0/2attempts; không được recalibrate
frozen để làm đẹp kết quả. So sánh newarms có cùng selection rule; so sánh frozen
là deployment-reference comparison, không phải cùng numerical operating point.

P0 có111receipts:48attempts,59benign,4UNKNOWN bị loại khỏi confusion metrics.
Labels dựa internal application Oracle/collector intent, human review **PENDING**.
Attack attempt không đồng nghĩa exploit success hoặc browser execution.

| Model | TP | FN | FP | TN | Attempt recall | SQLi | XSS | Command | Traversal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen v2 |18|30|0|59|37.50%|12/12|0/12|0/12|6/12|
| Matched control |3|45|0|59|6.25%|3/12|0/12|0/12|0/12|
| Challenger |3|45|0|59|6.25%|3/12|0/12|0/12|0/12|

P0 gate≥4extra attempts không đạt:deltaTP0,deltaFP0. P0benign toànGET nên0/59
không cho bằng chứng benignPOST; ngay giả định IID độc lập, two-sided95%upper
bound cũng≈6.06%, không đủ chứng minh≤1%FPR. Cảhai arms mới đều bỏ lỡ traversal
và phần lớn SQLi ở operating policy Oracle, nhưng không quy toàn bộ chênh lệch
với frozen cho encoder vì training initialization/threshold cũng khác.

49Oracle TRAIN không fit lần này, chỉ exposed diagnostics: frozenTP7/17,FP4/32;
controlTP1/17,FP0/32; challengerTP3/17,FP0/32. XSS vẫn0/8 ở cảba. Không cộng với
P0 thành một evaluation độc lập hoặc dùng để chọn checkpoint.

Suricata trên matched P0 receipts:TP27,FN21,FP2,TN57. Frozen thêm4attempt flags
ngoài Suricata: unionTP31/48,FP2/59. Control/challenger thêm0; union giữTP27/48,
FP2/59. Đây là mô phỏng union diagnostic, không thay coordination/policy runtime.
Không có WAF Rule evidence hoặc GLU207 evaluation mới để tạo three-source metrics.

## Failure analysis có giới hạn

Các phân tích dưới là **post-hoc trên exposed data**, không independent evaluation
và không thay model/threshold/retention gates.

- **Không chỉ do threshold:** áp cảhai publisher thresholds đã khóa vào exposed
  P0 cho control21/48,challenger15/48,FP0 ở cảhai. Đây chỉ diagnostic, không phải
  threshold được lựa chọn hay đề xuất thay thế. XSS score tối đa0.1715control và
  0.2962challenger đều thấp hơn publisher thresholds≈0.661. XSS failure không
  được giải thích chỉ bởi max-benign Oracle threshold quá cao.
- **Calibration/domain mismatch rõ:** ở OracleCAL, benign max≈0.998control/
  0.993challenger, trong khi hai attempt scores chỉ0.0277–0.0380control và
  0.0707–0.2538challenger. Không phải thiếu một threshold search tinh hơn. Labels
  anomaly WAF không đảm bảo ranking attack-intent trên lab; chưa đủ để phân biệt
  định lượng task mismatch, coverage và source shortcuts như những nguyên nhân
  riêng rẽ. Không suy ra Oracle label sai chỉ vì score cao/thấp.
- **Header sensitivity chưa giải quyết:** original P0 TP18/3/3 ở frozen/control/
  challenger; bỏheader thành27/3/7, thêmfixedlongheader thành16/2/7. Median absolute
  score delta khi thêmheader dài giảm0.0660control→0.0336challenger, nhưng khi bỏ
  header lại tăng0.0314→0.2739. Chuẩn hóa riêng giảm một dạng length dilution,
  không tạo invariance; hash bins vẫn dùng chung, không channel-separated features.
- **Không đổ lỗi sai cho body redaction:** cả12command requests P0 có body,
  0body bịredact; XSS query không bịredact. Cảhai representations có86unique full
  views/111receipts,0group giống hệt chứa cảbenign vàattack. Điều này loại trừ
  complete cross-label collisions trên P0 như lời giải thích trực tiếp; không
  loại trừ partial collisions/hash interference hoặc thiếu tín hiệu đủ phân biệt.
  Redaction vẫn là hạn chế ở các workflow khác; production shadow không thu body,
  vì vậy không suy khả năng full-receipt model sang production visibility.

## Resource và runtime

Training guard PASS:206.44s wall, active205.90s, active mean45.08°C, max66°C,
0pauses/thermal stops/watchdog failures/restarts. Kernel quota25% **mộtCPU**,
MemoryPeak598,937,600bytes≈571.2MiB, shared peak≈11.34GiB, reserve4GiB.
Run training ngắn hơn300s: average dùng cửa sổ active đã có≈206s; không tự nhận
đã kiểm full sustained training window300s hoặc thermal safety cho mọi workload.
Supervisor/worker/watchdog đều đã kết thúc success, không còn job training này.

Evaluation guard PASS,max54°C; posthoc guard PASS,max61°C. Exposed publisher
batched model-only wall time≈0.0291/0.0291/0.0330ms/view frozen/control/challenger.
Một pass P0 encoder diagnostic shared≈6.85ms/request, shared-numeric+separate
≈16.74ms/request; helper tính shared content thừa ở challenger. Quota scheduling,
single pass và helper overhead khiến đây không phải production throughput benchmark.

## Quyết định và bước kế tiếp

Reject challenger **cho nâng cấp này** vì point gates và uncertainty gates fail,
XSS/cmd không đạt mục tiêu và không thêm Rule coverage. Checkpoints được giữ để
tái lập; không tăng params/epochs, sweep seed hoặc mở prospective để cứu kết quả.
12prospective vẫn seal, chưa xem content/labels/features/scores. Model/threshold/
protocol đã khóa nhưng việc mở là tùy chọn; candidate đã bị loại trước đó nên
không tiêu hao tập nhỏ này. Các sealed holdouts khác không được mở.

**Ưu tiên tiếp theo: một release dữ liệu attack-intent có Oracle để domain adaptation,
không lặp lại normalization-only fit trên WAF.** Tái dùng49Oracle TRAIN và receipts
đã có làm điểm xuất phát, xác định gap theo workflow/family/feature visibility trước
capture bổ sung hữu hạn. Bổ sung đúng gaps benignPOST/JSON hard negatives và XSS/cmd/
traversal với disjoint campaign/template roles; không tăng count bằng repetition.
Không dùng75/111exposed diagnostics làm prospective mới; không lấy publisher
ANOMALOUS làm family label. Cần chuẩn bị cả request-full và production-visible
views để xác định mục tiêu nào có thể học với dữ liệu thực sự sẵn có ở runtime.

Chỉ sau coverage/Oracle/split gates khóa, kiểm một adaptation experiment với frozen
initial weights và representation gốc làm control, cùng ngân sách hữu hạn và
attack-intent supervision tách rõ khỏi publisher-anomaly task. Giữ architecture
50,696parameters trước; normalization mới hiện không có bằng chứng để ưu tiên.
Đây là khuyến nghị cho yêu cầu tiếp theo, **chưa thực hiện capture/training**.

## Evidence local và bàn giao

Local experiment root:
`ai-training/.artifacts/scaled_normalization_20261107/scaled-normalization-20261107-v1/`.
Nguồn chính:`plan.json`,`training-completion.json`,`status.json`,two-arm checkpoints/
summaries/metrics,`resource/resource-report.json`,`evaluation-lock.json` và
`evaluation-exposed.json`. Evaluation source giữ nguyên SHA trước training.

Review local:`.local-dev/scaled-normalization/results-review-20261107/` có
`pre-evaluation-integrity.json`,`posthoc-diagnostics.json`,`diagnostics.py`, guards.
18protected model/spec/threshold manifests đã được verify trước evaluation;
kiểm lại trước handoff. Raw/receipts/session/tensors/checkpoints không public.

Public aggregate:[machine results](../ai-training/reports/SCALED_NORMALIZATION_RESULTS_20261107.json).
Protocol/corpus/source/recovery:[experiment design](20_SCALED_NORMALIZATION_EXPERIMENT.md).
Bootstrap/release/inference giữ nguyên; đồng nghiệp không cần corpus để chạy frozen AI.
