# Scaled normalization experiment — 2026-11-07

**Data/evaluation/recovery gates PASS; experiment khóa để chạy nền.** Git handoff
lưu trạng thái chuẩn bị; trạng thái runtime thực tế nằm ở `status.json` và resource
status local, không được suy ra từ một báo cáo Git tĩnh. Không có kết quả quality
mới trước khi hai model hoàn thành và evaluation được kiểm. Không promote.

Baseline lúc bắt đầu:`585586f`, nhánh`feature/ai-idps-shadow-integration`, working
tree sạch. Không thay Web, Rules, correlation, Policy Engine, frozen models/
encoders/thresholds, GitHub Releases, AI enforcement hoặc AWS.

## Corpus thực sự tái sử dụng

Nguồn:`puyang2025/waf_data_v2`, revision
`b035dc17f875f1f732c10654709abed66a4e9742`. Còn raw publisher TRAIN Parquet77MB,
README và frozen selected tensor74MB. Pinned README khai MIT; attribution/terms
được giữ tại[THIRD_PARTY_DATA](../release/THIRD_PARTY_DATA.md). Đây là license claim
của publisher, không phải bằng chứng về capture/annotation lineage chưa cung cấp.
Chỉ xử lý local, không public raw requests/datasets/tensors.

Raw SHA:`3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6`.
Tensor SHA:`279dca7d03b38bb2092bf775762bfe68904eea131e0d1145a564de0f98441049`.
Dataset card hash và nguồn input khác nằm trong machine report.

Publisher TRAIN có1,924,461records; audit cũ ghi1,612,017exact representations,
312,443duplicate rows,192conflicting representations. Replay lần này kiểm lại
conflicting keys và phục hồi đủ160,796selected views, gồm120,435TRAIN,
20,278CAL/20,083DEV nội bộ. **Control numeric/content khớp bitwise** với tensor
frozen ở tất cả160,796views. Giữ source-row ordinal/fingerprints để lần sau không
phải tìm lại raw representatives từ đầu. Không mở publisher eval/test/heldout.

Nhãn là publisher **NORMAL/ANOMALOUS**, không tự đổi ANOMALOUS thành verified
attack intent hoặc family.0independent physical requests/GT được xác nhận từ nguồn
này; campaign/time/source identities cònUNKNOWN. Số row/view/exposure không được
cộng thành1–2triệu requests có Ground Truth. Data này hợp lệ cho weak-label anomaly
research với đúng giới hạn, không phải độc lập quality/admission evidence.

## Split và near contamination

Original role assignments giữ nguyên. Trước fit, quarantine mixed-label/duplicate
challenger views **trong từng role** cho cả hai arms; không dùng CAL/DEV labels để
đổi TRAIN selection. Lần này không có mixed views hoặc duplicates mới phải loại.

Kiểm cosine content512≥0.995 ở **cả shared và separated representations**. CAL
không giữ row near TRAIN; DEV không giữ row near TRAIN hoặc originalCAL. Đây là
feature-near exclusion, không phải kết luận các requests vật lý là duplicates.
Không chuyển CAL/DEV sang TRAIN và không thay threshold để đạt coverage.

| Role | Ban đầu | Eligible cuối | NORMAL | ANOMALOUS |
|---|---:|---:|---:|---:|
| TRAIN |120,435|120,435|34,282|86,153|
| CALIBRATION |20,278|2,437|1,042|1,395|
| DEVELOPMENT |20,083|2,041|865|1,176|

TRAIN còn88,680safe-template groups; CAL2,007 vàDEV1,746. Role/class minimums đã
khóa trước scores được đáp ứng. Số gần trùng lớn là giới hạn quan trọng của
benchmark cũ, không được bỏ qua chỉ vì frozen model đã train thành công.

Chỉ mục ban đầu dùng coordinate projection32 khá chậm. Cache reconstruction được
bảo toàn, sau đó đổi sang orthonormal PCA16 **chỉ để tìm candidates**, không phải
feature/model PCA. Projection không tăng khoảng cách nên radius search chứa mọi
pair có cosine cần loại; quyết định cuối luôn dùng full512dot và cùng threshold.
Benchmark64queries cho cùng44hits, querytime≈0.36s so với≈2.94s. Đã test projected
filter với brute-force. Short-circuit các rows đã loại bởi representation khác
không đổi union quarantine. Không giảm độ chặt để làm data gate PASS.

## Fair matched control và challenger

Ba đối tượng tách rõ:

1. Frozen Request v2 là deployment reference nguyên trạng, threshold0.8826237917.
2. Matched control được train mới trên đúng120,435TRAIN views, original shared-L2
   numeric76 + rich-v2 char3–5 hash512,50,696parameters.
3. Challenger giữ nguyên numeric, privacy projection, symbolic text/ngrams, hash
   coordinates, parameter count và initialization. Chỉ chuẩn hóa riêng counts
   URI/header/body, cộng lại rồi finalL2. Channel-crossing grams được gán một lần
   theo start offset; cộng raw counts tái dựng đúng original shared representation.

Hai model mới là deepMLP588→64→64→64→64→8, seed31, initial arrays giống nhau. Dùng
native marginalized binary objective, smoothing0.005/family_weight0, family=-1;
không tạo attack-family labels từ publisher annotation. Optimizer, batch256,
learningrate0.001, samplers, thread/resource budget giống nhau. Mỗi arm3,072updates,
786,432sample exposures≈6.53epochs, không phải786,432unique HTTP requests. Chạy
control rồi challenger, không song song. Checkpoint chọn **final3072**, không best
loss/DEV checkpoint hoặc thêm epoch/seed sau kết quả.

Encoder pilot v3 không dùng ở đây: nó đổi cả privacy/hashing coordinate layout,
không chỉ normalization. Module mới`normalization_ablation.py` cô lập giả thuyết,
không sửa frozen encoder. Không claim matched weights tái lập bitwise lịch sử trước
khi full fit hoàn thành; cả hai arms mới có cùng source/environment/CPU settings.

Redaction, missingness và hash collisions cũ vẫn còn. Chuẩn hóa riêng có thể tăng
source/method/missingness shortcuts hoặc không khôi phục được body đã withheld.
Raw corpus cũ ít body/non-GET; không giả định đủ verified XSS/command-family labels.
Negative result là kết quả hợp lệ, không lý do tăng params hoặc sweep.

## Oracle và evaluation protocol

Không pool anomaly supervision với attack-intent/family supervision.49Oracle TRAIN
chỉ exposed diagnostics, không fit trong experiment này.12Oracle CAL (10benign,
2attempts) dùng threshold Oracle riêng.111P0 DEVELOPMENT đã lộ có receipts/Oracle
và matched Suricata signature evidence. Export các inputs này khớp frozen control;
human review vẫnPENDING. Không đọc samples/labels/tensors của prospective12.

Sau training:

- Publisher stratum: cùng retainedCAL NORMAL q99(`higher`), strict`>` cho hai arms;
  frozen reference giữ threshold gốc. Đánh giá retainedDEV TP/FP/TN/FN, PR-AUC,
  method slices và paired template-group bootstrap1,000resamples.
- Oracle stratum: cùng rule max benignCAL score/strict`>` cho hai arms; frozen
  deployment reference giữthresholdgốc. TRAIN49 chỉ diagnostics; P0 báo per-family
  attempt Recall, benign workflow flags và hard negatives. Không gọi unsafe
  reflection là browser execution hoặc unknown outcome là exploit success.
- Header/body missingness và fixed-long-header sensitivity chỉ ở exposedP0, không
  retune threshold. Giữ metadata runtime/ms-per-row và resource telemetry.
- Suricata value-added chỉ trên P0 có request-bound signature evidence. WAF không
  có PCAP/EVE nên không tạo rule-only/added-detection score giả; GLU207 không tham gia
  như một detector độc lập vì contract/source phụ thuộc khác.

Research retention rule khóa trước: publisher anomaly TPR tăng≥0.02 so matched,
NORMAL flag fraction tăng≤0.002; paired group intervals phải hỗ trợ hướng cải
thiện/không regression; P0 thêm≥4attempt flags và không thêm benign flags.
Thiếu confidence/groups thìINCONCLUSIVE, giữfrozen. Recall80%/family và FPR≤1% là
mục tiêu research, không kết quả. Bootstrap trên observed template groups/publisher
labels không tự tạo independent population evidence hoặc inference về nhiều seeds.

Prospective12 tiếp tục seal. Chỉ cân nhắc một lần mở khi người dùng yêu cầu xem
kết quả, model/threshold/protocol fingerprints đã khóa. Flag CLI riêng, default
không mở; marker one-shot được ghi trước access. Không tune tiếp sau đó hoặc gọi
12same-application samples là chứng minh≤1%FPR/cross-domain generalization.

## Recovery, supervision và trạng thái

Fresh-process recovery PASS cho **hai representations**, first600real TRAIN rows,
4updates có epoch-tail wrap: direct4 so với2+resume2, loss/weights/Adam m/v/RNG/
permutation/cursor/scheduler/config khớp bitwise. Đây là verification ở mức subset,
chưa claim full3,072step resume đã được thực nghiệm. Không dùng CAL/DEV/Oracle/
prospective trong recovery. Các validation updates không tính là corpus mới.

Checkpoint mỗi128updates và update1, immutable generations/latest/previous/best;
không dùng best pointer để chọn model. Crash có thể mất tối đa127uncommitted updates;
status tách current step với committed checkpoint step. Không auto restart/promote.

Supervisor dùng cgroup CPU/memory limits,4GiB MemAvailable reserve/30GB shared
budget. Rolling300s tính **active time**, pause không làm giảm rolling mean. Reduce
khi gần77–78°C; fail closed nếu active rolling đạt80°C; instantaneous cutoff90°C,
không tự restart. Không thay hardware thermal protection hoặc đóng user apps.

Watchdog chạy systemd service riêng với workload và monitor; mất monitor heartbeat/
sensors thì kill đúng named unit. Monitor cũng kiểm watchdog còn sống. Probe thật
đã dừng owned sleep workload khi heartbeat stale. Systemd máy này từ chối quota
34.375%; đã tái hiện lỗi và floor quota về integer bảo thủ. Lần prep đầu dừng an
toàn, evidence giữ riêng. Lượt mới trần25% **mộtCPU** ổn định, không cố dùng50%host
khi nhiệt/tải không cần. Wrapper riêng, không sửa historical guard/frozen source.

`plan.json`,`status.json`,`metrics.jsonl`, checkpoints và `resource/` local là
source of truth. Public config/report là **prelaunch transcription**, không phải
live status. Xem trạng thái:

```sh
ai-training/.venv/bin/python ai-training/scripts/scaled-normalization-experiment.py status \
  --root ai-training/.artifacts/scaled_normalization_20261107/scaled-normalization-20261107-v1
```

Không chờ job dài trong Codex; sau verify RUNNING sẽ kết thúc chat. Khi quay lại,
kiểm status/checkpoint/resource integrity trước evaluation. Không tự chọn model mới.

## Resume và team handoff

Không resume tự động. Nếu job bị dừng, kiểm latest/previous/checksums, lưu error và
uncommitted-step gap. Dùng đúng locked source/environment/dataset; không`--force`.
Một explicit resume giữ cùng experiment root/plan/checkpoint nhưng dùng resource
attempt directory **mới**, bảo toàn resource logs cũ:

```sh
# Chỉ sau khi xác minh checkpoint và không còn job cũ; chạy qua systemd supervisor độc lập:
ai-training/.venv/bin/python ai-training/scripts/scaled-active-supervisor.py \
  --output ABS_EXPERIMENT/resource-attempt2 --experiment-root ABS_EXPERIMENT \
  --quota 25 --memory-gib 4 --max-seconds 7200 -- \
  ai-training/.venv/bin/python ai-training/scripts/scaled-normalization-experiment.py train \
  --root ABS_EXPERIMENT --resource ABS_EXPERIMENT/resource-attempt2
```

Trainer kiểm source/environment fingerprints, RunLock và committed sampler/RNG;
không dùng fallback checkpoint âm thầm. Nếu fingerprints khác, dừng và khôi phục
đúng revision trong isolated checkout; không reset/ghi đè dirty worktree.

Sau completion, evaluation mặc định chưa mở prospective:

```sh
ai-training/.venv/bin/python ai-training/scripts/evaluate-scaled-normalization.py evaluate \
  --root ai-training/.artifacts/scaled_normalization_20261107/scaled-normalization-20261107-v1 \
  --oracle ai-training/.artifacts/scaled_normalization_20261107/oracle-exposed
```

Private artifacts:`ai-training/.artifacts/scaled_normalization_20261107/` và
`.local-dev/scaled-normalization/`. Giữ raw/derived tensors/weights/review local,
không public checkpoint hoặc dữ liệu nhạy cảm. Team frozen bootstrap/inference
không cần corpus này.52targeted tests/Ruff PASS; model/role/seal bảo toàn.

[Machine report/evidence index](../ai-training/reports/SCALED_NORMALIZATION_20261107.json),
[config transcription](../ai-training/configs/research/scaled-normalization-20261107.json),
[training](../ai-training/scripts/scaled-normalization-experiment.py),
[evaluation](../ai-training/scripts/evaluate-scaled-normalization.py),
[normalization-only encoder](../ai-training/src/idps_ai/features/normalization_ablation.py).
