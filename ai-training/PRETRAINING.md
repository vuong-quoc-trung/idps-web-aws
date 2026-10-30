# Chuẩn bị và pilot trước train chính thức

## Hiện trạng — 2026-10-30T21:35:36.891996+07:00

**Engineering PASS; generalization/deployment NOT_READY.** Chỉ AI/docs; Student/Security/contracts/docker không đổi. 160 pytest PASS/0 skip, 53 gate legacy 69k PASS. Chưa champion hoặc train chính thức. Nguồn hiện hành: [REQUEST_PROFILE_20261030](reports/REQUEST_PROFILE_20261030.json), [handoff format 5](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 27. Report GENERALIZATION trước đó giữ nguyên.

- Tổng lab 71.280 HTTP đủ 3 nguồn: 69.345 cũ + 1.935 mới/360 giây, embargo 41.276 giây. Có 1.882 hợp đồng intent/HTTP tự động đúng và 53 HEAD/OPTIONS trả 403 pending; chưa human review. Ba client concurrent vẫn cùng một môi trường và thời điểm. Lab đã dừng, 0 packet drop.
- Profile riêng `request-structure-v1` có 70 số từ URI/query/method; alias tên tham số sau khi bỏ credential/PII. Không raw query, UA, status, actor, flow/time, source hoặc rule. Legacy 207 v5 giữ nguyên. EVE dual projection chạy trước mask; legacy causal past flow dùng được ở 1.567/1.935 request, 368 còn null.
- Corpus 115.980 record: 86.275 train, 12.303 calibration, 17.402 validation; scaler chỉ fit benign train. Public training gốc có 36.000 CSIC normal + 24.504 PKDD normal; không test→train. Supervised chỉ 1.233 unique lab view; AE 18.713 unique benign view. Có 600 nhóm numeric view giao partition, không có nhóm trộn nhãn 0/1. Không coi projection/benchmark record là HTTP lab mới hoặc positive độc lập.
- Hai study: 2 epoch và diagnostic 300 update, tối đa 180 giây/session diagnostic. MLP 217.608, GLU 9.535.496, DAE 233.670 tham số trainable. Cùng 300 update/seed 17/batch 128/calibration target FPR 1%; khác FLOPs và inductive bias, không equal compute. Exact resume 100→300 so continuous và ONNX toàn 115.980 vector/model/study PASS rtol=1e-5, atol=1e-6.
- Fresh lab request task có 1.666 record: MLP recall 40,625% / FPR 0 trên 1.378 benign; GLU recall 0 / FPR 0; AE recall 36,46% / FPR 18,58%. PKDD test 25.612 record: AE recall 40,21% / FPR 0,105%; MLP 3,73% / 1,16%; GLU 1,13% / 0,724%. Frozen 207-feature GLU cũng có FPR 73,22% trên cohort 3 nguồn mới. **Không chọn champion**, không hạ threshold theo test. Các test mới nay đã exposed; cần test sealed khác cho phát triển tiếp. Original old lab test quality vẫn kín.
- Study mới dùng 4 CPU/16 GiB/high 15 GiB/swap 0; pin source/config/data hash, checkpoint mỗi 30 giây và tại signal/resource boundary, có thermal guard. Sau study chỉ sửa reporting flow count trong `request_inference.py`; frozen source và before-report giữ nguyên, model metrics không đổi. Không force-resume khác source.
- Mục tiêu 2M chưa đạt; scale-admitted=0. OpenCitations chưa nhãn không được gán benign; Biblio-US17 cần quyền tải/terms, chưa tự liên hệ. Thiếu positive đa nguồn/human review và live production acceptance. Không kéo dài train hoặc nhân bản dữ liệu để làm đẹp.

Công cụ mới, chạy từ project root, output phải mới. Ví dụ để hiểu pipeline; **không cần chạy lại study đã hoàn tất**:

```bash
ai-training/.venv/bin/idps-ai request-prepare --registry <request-sources.yaml> --output <new-request-corpus>
ai-training/.venv/bin/python ai-training/scripts/request-pilot.py --dataset <new-request-corpus> --output <new-short-pilot> --cpus 4
# Diagnostic tùy chọn: thêm --learning-curve; max 300 update/180 giây mỗi session.
# Chạy trong cgroup tối đa 8 CPU/16 GiB theo runbook hiện có; study vừa rồi dùng 4 CPU.
```

Inference offline trong Python với bundle 70 feature, **không dùng bundle 207 v5**:

```python
from idps_ai.request_inference import RequestInferencePipeline
pipeline = RequestInferencePipeline("<request-bundle>", max_threads=1)
result = pipeline.observe_uri("/api/catalog?search=example", "GET")
assert result["enforcement_actions"] == 0
```

`project-request-eve.py` đọc stdin JSONL giới hạn 64 KiB, xuất stdout dual numeric v2 + request v1 sau privacy. Nguồn EVE phải được nối **trước mask**, không phục hồi query đã mask. Không lưu input thô ra file để làm bridge; lượt này không đổi Web/sensor config. Common threshold là nghiên cứu, chưa production calibration. Metric, family, confusion matrix và command đã chạy nằm trong report.

Các lệnh train lịch sử bên dưới **không phải chỉ dẫn chạy formal lúc này**.

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

## Chuẩn bị mạng sâu/corpus 60–80k — revision 4.1

Phạm vi phiên mới chỉ AI và docs. Đã triển khai projection v2 / 189 đặc trưng cùng ba
mạng sâu (248.072/294.717/445.448 tham số), giữ math/checkpoint/cgroup/ONNX contract.
Corpus mới thu từ Student export của HEAD hiện hành, Nginx và Suricata thật;
45 campaign / 27-9-9 groups, 480 giây/campaign và gap 620 giây. Hard-negative payload
identities được tách như attack views, không chỉ kiểm request ID khác nhau.

Source v4/148 cột cũ và các report/pilot trước không được ghi đè hoặc force-resume.
Revision 4.1 tránh gọi hai vector khác thứ tự/số cột bằng cùng contract. Model sâu
chỉ là candidate; không hứa chống overfit, thêm zero-day detection hoặc train
đủ 150 phút. Pilot 5 epoch phải so fresh-process resume với reference và ONNX toàn
bộ vector; test quality giữ kín. Model/threshold không được promote tại đây.

Runbook mới ở đầu [README](README.md). Handoff hiện hành đặt tại
`ai-training/FINAL_TRAINING_HANDOFF.json`; bản có cùng tên trong
`upgrade_20261028` thuộc experiment lịch sử. Ca dài dùng
`train-expanded-session.sh`, chỉ do người vận hành khởi động sau khi gate/pilot
hoàn tất. Trạng thái đo cuối ghi trong report mới và ledger 06 mục 24.

## Nâng cấp sau chẩn đoán — 29/10/2026

Ca11,616giây trước đó không báo lỗi optimizer/checkpoint/ONNX. Model nhỏ và
early stopping giải thích thời gian; chất lượng vẫn hạn chế:59/148cột hằng số,
query payload counters bằng0, campaign có nhiều lặp. Không ép ca đó chạy tiếp.

Đợt mới bổ sung shared numeric EVE bridge, feature/normalizerv4, policy corpus
sâu hơn và weighted residual candidate có train/validation loss history.
30campaign có plan riêng, nhóm18/6/6,480giây thật/campaign và gap620giây thật;
thêm CRUD, đọc public, UA thường đa dạng, batch hợp lệ và hard negatives.
Canonical1.0, Student/Security và artifact cũ giữ riêng. Đây vẫn là lab một host,
scripted intent và tài khoản giả; cần dữ liệu người dùng/traffic đại diện sau này.

Các alias URL decode về cùng payload được kiểm bằng identity hash. Bản trùng ở
holdout sau giữ làm context nhưng không được nhận nhãn training/evaluation;
evidence có danh sách HMAC request key và lý do loại. Không sửa log gốc hoặc
hạ floor để vượt readiness. Corpus cũ được re-project chỉ là phép chẩn đoán.

Re-projection PCAP cũ là phép chẩn đoán riêng: cùng residual5epoch đạt recall
validation95,39%, khi bỏ projection query/URI ở cùng weights/threshold còn26,93%.
Threshold dùng cùng validation nên kết quả sơ bộ; không tính đây là corpus mới,
không dùng để mở khóa formal gate30campaign. AE và weighted loss không mặc định
tốt hơn supervised residual. Thiếu actor/flow có thể tăng false positives mạnh;
phải đọc cả FPR trong sensitivity, không chỉ recall.

Quy trình/lệnh mới ở đầu [README](README.md#workflow-numeric-query--29102026).
Ca tiếp dùng `train-query-session.sh`; ca `train-first-session.sh` bên dưới đã
terminal. Modelv4 cần cùng bridge trước redaction khi chạy thật; Rust serving,
TLS/receipt-time parity và phản ứng IPS chưa được nghiệm thu trong luồng AI.
Report/ledger mới nhất sẽ ghi số liệu thực của corpus/pilot và trạng thái gate.

**Kết quả cuối corpus mới:**46.230request,198.765observations,30campaign,48/48gate
PASS; feature rows46.134 sau96holdout-overlap exclusions. Split27.738/9.150/9.246,
nhóm18/6/6; canonical1.0/profilev4/148cột. Pilot4ứng viên5epoch, exactresume và
ONNX46.134/46.134từng modelPASS. Residual không trọng số có APvalidation cao nhất
0,99875,recall99,23%,FPR0,747%; đây là candidate cho ca tiếp, chưa champion.
Lệnh `train-query-session.sh` dùng residual seed17/patience8/100epoch/max150phút,
8CPU/16GiB; **ca formal mới chưa chạy**. Chất lượng test vẫn niêm phong và chưa
nghiệm thu live. [Báo cáo](reports/PRETRAIN_UPGRADE_20261029.json), ledger06 mục23
ghi source/hash và các lần kiểm tra thực; các snapshot dưới đây là lịch sử.

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

Cập nhật 28/10/2026: luồng AI dùng `ai-features-3` / `ai-normalizer-3`, 148 cột,
canonical event v1.0 giữ nguyên. Báo cáo ngày27 là lịch sử của corpus hai nguồn;
không dùng checkpoint/report cũ để resume với source hoặc dataset mới.
Báo cáo hiện hành: [PRETRAIN_PILOT_20261028.json](reports/PRETRAIN_PILOT_20261028.json), đóng băng sau capture/readiness/pilot; 19.275 request, 35 gate checks và77 testsPASS.

## Luồng ba nguồn thật

1. `lab-start` build bản Student riêng từ Git, DB PostgreSQL rỗng và tài khoản giả.
   Không đọc `.env`, DB hoặc credential của dịch vụ đang dùng.
2. `lab-capture-eve` chuyển Nginx và HTTP client vào **user/network namespace riêng**.
   Backend được nối bằng Unix socket relay riêng. IP127.0.0.10–24 là địa chỉ bind
   thực trong namespace; không sửa timestamp/IP để tạo split. Host networking,
   firewall và cấu hình Student/Security không bị thay.
3. `tcpdump --immediate-mode -i lo` chỉ bắt TCP18881 trong namespace. PCAP riêng tư
   chứa credential/cookie **của fixture giả**: không đưa vào Git hoặc chia sẻ công
   khai. Thư mục0700, PCAP0600, giới hạn512MiB; STOP hoặc lỗi không cấp readiness.
4. `decode-pcap` chạy Suricata8.0.3 offline, một worker, dùng bản config dẫn xuất và
   nguyên bộ9SID của repo. Giữ cả HTTP/flow bình thường, alert và stats. Suricata
   gửi EVE qua Unix socket0600; bộ lọc chỉ giữ response header `X-Request-Id`, mask
   query/path động và UA trước khi ghi `eve.json`. Không ghi cookie/token/body.
5. `lab-finish` đóng băng snapshot, labels/provenance, correlation, split, scaler,
   vectors, readiness, capacity và rule baseline validation. Chế độ ba nguồn dùng
   `three_source_policy.yaml`; corpus ngày27 không qua được gate mới này.
6. `pilot` chạy từng model2epoch rồi **tiến trình mới** resume đến5epoch, so đúng
   weights/Adam/RNG/sampler/scheduler với reference 5 epoch liên tục, export ONNX.
   Chỉ tính metric trên validation; test chỉ được replay để kiểm parity, không
   dùng nhãn test để chọn threshold hoặc chọn model.

## Quyền bắt gói và AppArmor

Máy hiện tại dùng Podman rootless qua lệnh `docker`. `--network host` cùng
NET_RAW/NET_ADMIN không cấp quyền trên host namespace. Cách đã chọn không cần
sudo để mở packet socket trong namespace riêng. Tuy nhiên AppArmor profile
`tcpdump` đã chặn tín hiệu từ Codex (`peer=chatgpt`). Người dùng đã tự bổ sung:

```apparmor
signal (receive) peer=chatgpt,
```

vào `/etc/apparmor.d/local/usr.bin.tcpdump`, reload profile và dừng các probe cũ.
Đây là thay đổi quyền **nhận tín hiệu dừng**, không cấp capture host, không tắt
AppArmor. Máy khác chỉ cần thao tác này nếu kernel audit xác nhận cùng lỗi.
Muốn thu hồi: xóa đúng dòng bổ sung rồi reload profile bằng quản trị hệ thống.
Không chép binary hoặc tắt sandbox để né profile.

## Corpus và feature availability

- 15 campaign × 1.280 request workload, cộng setup/logout: **19.275 request**; nhóm 9/3/3.
- Mỗi campaign420giây thực; các campaign trong cùng band chạy đồng thời, mỗi
  identity có lịch sử riêng. Hai khoảng nghỉ 620 giây thực giữ embargo300giây ở
  hai phía cutoff. Ba role và payload/UA views được phân band trước khi thu.
- Có đọc/ghi hợp lệ, HEAD/OPTIONS bị policy từ chối,404, role denial, tìm kiếm
  Unicode/O'Connor/percent/thuật ngữ kỹ thuật và singleton login typo; attack
  families gồmSQLi/XSS/traversal/command/scanner/auth burst/bulk-read intent.
- `edge_masked_v1`: mọi adapter đều bỏ query lexical và query-original counters,
  chuẩn hóa path cùng cách. Không chọn view raw giàu hơn từ Suricata/lab. Các
  cột query thiếu dữ liệu được ghi đúng trạng thái, không dựng payload giả.
- Flow là **context của flow client đã hoàn tất trước đó**, không là byte/packet
  riêng của request hiện tại. Chỉ dùng flow kết thúc trước request ít nhất65giây
  (closed timeout60giây + biên dự phòng), lookback record300giây. `available_at=max(timestamp EVE, flow.end+65s)` kết hợp hai ràng buộc mà không cộng timeout lần hai; timestamp gốc không bị đổi. Những request warmup vẫn
  missing; không dùng counter đóng flow tương lai để lấp đầy100%.
- Đây là replay theo packet/event time. Receipt-time delay, TLS/vantage, arrival
  reordering và port Rust/live phải được nghiệm thu riêng khi triển khai.

Đồng bộ masking tránh train bằng thông tin không tồn tại khi chạy thật, nhưng
cũng làm một số họ payload trong query không thể phân biệt chỉ bằng metadata.
Rule engine có thể quan sát raw request trong bộ nhớ; AI metadata không được
hứa thay thế bộ rule đó. Query/body model cần telemetry được phê duyệt riêng.

## Ba ứng viên

| Model | Kiến trúc | Vai trò |
|---|---|---|
| MLP cơ sở |148→32→8 | Supervised baseline |
| Autoencoder |148→32→148 | Chỉ fit benign; reconstruction score không phải xác suất attack |
| Residual tabular |148→64→64+skip→8 | Candidate có sức biểu diễn cao hơn; chưa mặc định tốt hơn baseline |

Residual có14.216tham số FP32, dùng ReLU/softmax/CE và Adam hiện có. Params, activations, gradient và optimizer giữFP32; affine reductions tích lũyFP64 rồi roundFP32 trong cảNumPy/ONNX. Cách này xử lý sai lệch BLAS/MLAS gầnzero, vẫn giữtolerance rtol1e-5/atol1e-6. Arithmetic contract ghi trong checkpoint; không force-load các checkpoint của attempt trước bằng source mới. Gradient được
đối chiếu finite difference; optimizer/checkpoint/ONNX có test. Đây là kiến trúc
nhỏ lấy cảm hứng từ residual learning, không phải bản tái lập nguyên xi benchmark
[ResNet cho tabular data](https://arxiv.org/abs/2106.11959). Byte-CNN/TCN vẫn cần
corpus/sequence contract tương ứng; không đưa LLM/Torch/CUDA vào pipeline này.

## Tài nguyên cho ca sắp tới — cập nhật sau pilot

Cấu hình hiện hành là **8 logical CPU**, `CPUQuota=800%`, `Nice=10`,
`MemoryMax=16GiB`, `MemoryHigh=15GiB`, `MemorySwapMax=0`. NumPy/BLAS/OpenMP/
NumExpr dùng tối đa8luồng; ONNX intra-op8, inter-op1 với execution mode sequential
để không nhân hai pool8×8. `--cpus` là alias của `--max-threads`, chấp nhận6–8CPU
trên máy16luồng; bộ guard vẫn kiểm trần nửa CPU affinity và đọc lại cgroup.

16GiB là mức người dùng chỉ định rõ. Hệ điều hành nhìn thấy32.440.909.824byte RAM,
vì vậy16GiB tương đương khoảng**52,96% RAM OS-visible**, không phải chính xác50%.
Guard ghi tỷ lệ thực tế, không đánh đồng32GB với32GiB. Trần16GiB là giới hạn job;
working set không được cấp phát sẵn16GiB. Nhiệt/độ mượt ca dài vẫn cần đo riêng.

Đã chạy **77tests PASS** và probe systemd guard với**0optimizer step**; không
train lại corpus19.275request, không chạy ca chính thức. Báo cáo mới ở
[RESOURCE_GUARD_20261028.json](reports/RESOURCE_GUARD_20261028.json). Các metric và
thông số2CPU/12GiB trong report pilot trước đó giữ nguyên ý nghĩa lịch sử.

Nguồn guard đổi nên đã chạy lại35data-readiness checks, tạo
`dataset-ready/readiness-resource8/readiness.json`. Bản `readiness-final` cũ,
`dataset-ready/prepared` và toàn bộ`pilot-ready` vẫn giữ nguyên byte. Handoff và
script hiện dùng readiness-resource8; checkpoint pilot cũ không được force-resume
bằng source mới. Ca đầu là một experiment mới.

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-first-session.sh
```

Ở mốc 28/10, lệnh này **chưa được thực thi**; ca đầu đã chạy ngày29 và dừng sớm như mục cập nhật đầu trang. Mặc định100epoch, patience8, tối đa150phút,
checkpoint300giây; đạt đích/early stopping sớm thì dừng. Nếu run mới đã cólatest
thì script tiếp đúng run tương thích. Không lặp dữ liệu để đủ số giờ.

## Những gate vẫn riêng

`READY_FOR_OFFLINE_PILOT` không là production certification. Corpus vẫn là lab
loopback với tài khoản/dữ liệu giả, scripted intent, một topology và ít campaign
holdout; chưa có independent human realism review hoặc traffic cloud. Cần thêm
realistic sessions, campaign độc lập, TLS/receipt-time parity, FPR/incident-level
review và shadow trước khi chọn champion hoặc bật phản ứng. Không chạm Rust,
firewall, dashboard hay service config trong luồng AI này.

Xem [README](README.md), [report lịch sử27/10](reports/PRETRAIN_20261027.json) và
[ledger06](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md). Raw/key/Parquet/weights/PCAP
chỉ nằm trong `.artifacts/`, không ở Git; kho artifact chung chưa được cấp.

Lệnh ca đầu lịch sử: `bash ai-training/scripts/train-first-session.sh`. Run đích đã early-stop ngày29; không dùng lại để ép học thêm cùng run.

Artifact được duyệt: `dataset-ready/prepared`, `dataset-ready/readiness-resource8/readiness.json` và `pilot-ready/` (bản readiness-final gốc vẫn được giữ). Xem `.artifacts/upgrade_20261028/FINAL_TRAINING_HANDOFF.json`. Thư mục `dataset`, report `readiness` cũ và `pilot` là các attempt đã fail hoặc stale và đã được dọn theo yêu cầu. Các lệnh NEXT_COMMANDS cũ đã xóa; chỉ dùng script/handoff hiện hành.
