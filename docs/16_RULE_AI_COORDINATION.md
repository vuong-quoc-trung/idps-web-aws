# Rule–AI coordination, runtime và derivative — 2026-11-07

Đã mở rộng hệ thống hiện có và kiểm bằng HTTP thật. **Không training**: gate dữ
liệu/evaluation/resume còn thiếu. Frozen models/spec/thresholds/rules giữ nguyên,
không AI enforcement hoặc AWS. Milestone trước thực tế đã được commit tới75ad32d;
working tree ban đầu sạch. Handoff mới nằm trên integration branch, không merge main.

## Rules và AI cùng transaction

`/api/ai-shadow` bổ sung `detectors`, giữ API fields/bảng RI và correlation cũ.
Migration0007 chỉ thêm metadata links; không sửa alert lịch sử hoặc policy.

- Application/Nginx rules: link request ID của telemetry producer, không IP/time.
- Suricata native: strict generation/flow/tx khi correlation MATCHED. Alert không
  tx là flow context, không tính thành request alert. Không đoán transaction cho
  legacy alerts thiếu metadata. Chúng vẫn xem được trong quản lý cảnh báo.
- Giữ riêng score, model version, threshold/comparator, observation timestamps,
  sources, missingness, severity và action hiện có. Không có weighted fusion hoặc
  alert tổng hợp mới. Duplicate/replay không tạo detector vote mới.
- View đọc trạng thái mới nhất: rule đến sau được nối khi đủ correlation; nếu
  correlation thành AMBIGUOUS thì sensor transaction/GLU proof không còn được
  trình bày như match chắc chắn. Request ID app link vẫn giữ basis thật của nó.
- Trạng thái: RULE_AND_AI_ALERT, AI_ALERT_ONLY_OBSERVED,
  RULE_ALERT_ONLY_OBSERVED, NO_ALERT_OBSERVED, INCOMPLETE_DETECTOR_EVIDENCE,
  UNCERTAIN_CORRELATION. “Only observed” không chứng minh detector khác âm tính;
  empty rule list không chứng minh tất cả rules đã quan sát. GLU có Suricata-derived
  features nên không phải các phiếu độc lập.

Real acceptance gồm single/concurrent/keep-alive, sensor stop/restart, dummy-secret
privacy canary. Trên cùng connection, tx0 ordinary không có native alert, SQLi-shaped
SID1000002 chỉ tx1, command-shaped SID1000005 chỉ tx2; Rust/Nginx alert giữ nguồn
riêng. SQLi-shaped transaction có Request v2=0.998343 và GLU=0.887269, cùng request ID.
Đây là attempt-shaped lab input, không xác nhận exploit outcome hoặc model quality.
Sensor-stopped request có HTTP200, MISSING_SOURCE và không GLU.

Genuine EVE metadata replay giữ alert count38→38; public verifier chạy lại43→43.
Restart lúc không phát traffic giữ56correlations,24GLU results,43alerts và8links;
hai recent probe scores giữ nguyên. AUTO firewall actions0, unauthenticated API401.
Một probe restart đầu bị nhiễu do chạy trùng real RI acceptance; giữ artifact và
không dùng phép so count đó. Không xóa/reset history để làm PASS.

Code: [SQL view](../security-web/src/detector_view.sql),
[ingest](../security-web/src/ingest.rs), [API](../security-web/src/ai_shadow.rs),
[dashboard](../security-web/frontend/src/AiShadow.tsx),
[real verifier](../scripts/verify-detector-coordination.py).

## Bottleneck và kết quả tối ưu

Code cũ collect toàn snapshot hai lần/request và replay feature history hai lần.
Giữ frozen collector/FeatureExtractor/transform; cache theo immutable batch và
**cùng tập flow đã nhận trước target**. Không có available flow thì dùng HTTP-only
collection đã có (flow=null theo frozen semantics). Tối đa32flow variants/batch;
quá giới hạn dừng, không silently đổi missingness. Prefix vẫn replay causal và
được kiểm exact với tensor thật vào ONNX. Chưa dựng incremental state engine mới:
chi phí collect lặp là phần đáng sửa trước, history prefix hiện nhỏ hơn.

Paired replay **cùng12requests, cùng snapshot/quota100% một CPU**, cùng process;
đã đảo thứ tự hai arms để kiểm ảnh hưởng warm/order:

| Thứ tự | Reference wall / CPU | Cache wall / CPU | Wall speedup |
|---|---|---|---:|
| Reference trước |19.111s /12.661s|3.688s /3.112s|5.18×|
| Cache trước |18.419s /12.719s|3.814s /3.127s|4.83×|

Frozen collect giảm24→3calls;12/12vector207float32 và score exact ở cả hai lượt.
Thông lượng offline:0.63–0.65→3.15–3.25requests/s. Không dùng thông lượng này như
live capacity. Microbenchmark không loại mọi ảnh hưởng page cache/shared host.

Lượt đảo thứ tự, trung bình12requests:

| Stage | Reference | Cache |
|---|---:|---:|
| History prefix replay |159.87ms|131.56ms|
| Current feature extraction |0.120ms|0.112ms|
| Frozen transformation |0.185ms|0.184ms|
| ONNX inference |11.408ms|11.207ms|

Trong số đo đầu, collect là frozen parse/SQL fusion/parquet write/read gộp; chưa
instrument riêng từng câu SQL/decoder. Không gọi các thời gian này là model chậm.
Guard ghi CPU time, wall, cpu.stat/throttling, pauses, memory; profile của live batch
và từng request được giữ. Availability watermark là gate chọn **prior completed
flow**, không bắt mọi current request chờ65s; thiếu flow vẫn có missing flags.

12requests live mới: tensor thực/score qua frozen predict, exact replay kiểm trước
publish. Hai probe HTTP→API đầu3.30–3.34s; public command thêm hai probe2.66–2.69s.
N=2/lượt, không báo p95 hoặc sustained SLA. API polling có interval và đây là thời
gian quan sát đầu tiên, không phải latency nội bộ DB chính xác. Dashboard refresh3s
có thêm delay; UI hiển thị được provenance và cả hai scores, chưa đo refresh SLA.

Run trước quota5% có159–542s, run mới quota100%; **không quy toàn bộ chênh lệch đó
cho code optimization**. Chứng cứ causal hơn là paired replay4.83–5.18× ở cùng quota.
Không chứng nhận phục vụ liên tục/tải cao hoặc multi-environment từ cohort nhỏ.

Code: [cache bridge](../scripts/glu207_snapshot.py),
[consumer](../scripts/glu207-live-shadow.py),
[paired protocol](../scripts/benchmark-glu207-cache.py).

## Derivative và174status conflicts

Đã tạo local-only `ai-training/.artifacts/glu207_derivative_20261107`:

- 41,607train rows và feature rows, source hashes/provenance, riêng app/wire status.
- 41,433consistent research candidates;174quarantined khỏi supervised selection.
- 174đều PATCH `/api/faculties/[id]`, inherited benign label, Student405/Nginx403/EVE403.
  ID/method/route cùng nhau. Chưa tái lập được nguyên nhân dispatch/lifecycle;
  không mặc định attack, label sai hoặc cross-request mix.
- Quarantine giữ source IDs, reason, original feature row và history contribution.
  **Không tuyên bố đã loại ảnh hưởng174rows khỏi history của mọi downstream row.**
  Không fit lại scaler/encoder và không đổi frozen dataset.
- Historical tx_id không còn trong source snapshot: giữ NOT_RETAINED, không tạo mới.
- No new labels approved. Prepared status khác formal admission hoặc independent GT.

Retained method/family counts cho thấy benign POST1897, benign GET16108, benign
HEAD5367 và OPTIONS5446. POST positives chủ yếu brute-force1728; GET positives từng
family1728. Đây là **confounding/scenario balance đáng kiểm**, chưa chứng minh model
đã học shortcut. Không kết luận POST=attack, cũng không coi request counts là diversity.

P0/P0.5 DVWA111requests có semantic technical review nhưng independent review vẫn
PENDING; chúng là exposed development evidence và không có Student/GLU207 fused
contract. Không đưa chúng vào207features bằng padding hoặc dùng để tuning threshold.
Không thu lại cohort hoặc đọc sealed holdout trong milestone.

Code: [derivative preparation](../scripts/prepare-glu207-derivative.py).

## Resource control và độ tin cậy

Guard mặc định đổi từ legacy instant80°C sang **time-weighted rolling300s<80°C**.
Reduce gần77°C, pause>=80°C, pause sớm khi instant/rate nguy hiểm; independent90°C
cutoff, sensor/heartbeat failure kill. Critical coretemp host quan sát105°C, nên90°C
là ngưỡng bảo thủ trên host đã kiểm; thiết bị khác phải kiểm giới hạn và đặt cutoff
thấp hơn nếu cần. Không sửa OS/firmware/power limit, không đóng user apps.

CPUQuota là %một CPU:100%=một CPU. Ceilings có thể tới50% tổng CPUs, giảm theo
external host utilization và nhiệt; không ép đạt50%. Các phép kiểm dùng ceiling100%,
threads1, affinity tối đa8CPU. Không tự cho rằng quota thấp hơn luôn an toàn hơn.

MemAvailable reserve4GiB, cgroup ceiling default4GiB điều chỉnh theo headroom/shared
30GB; có thể request lớn hơn bằng `--memory-gib`, không cap16GB. Theo dõi PSI/full,
swap I/O, cgroup memory/OOM và host utilization; pressure pause. Không lấy RAM cache
làm bằng chứng thiếu RAM. Atomic resource status có version riêng; **không phải
training status/checkpoint completion**.

Tests của time integration, window clipping, emergency/cooldown, mất sensor interval,
independent watchdog, CPU budget và pressure PASS. Live bounded guard có kernel
quota/memory/swap readback, full300s window qua IDS run khoảng559s. Peak các run
thành công và sensor run60°C, không emergency; sensor weighted mean49.98°C.
Đó là mostly low-load telemetry/inference/engineering, **không phải sustained-training
thermal qualification**. “Active” trong resource report nghĩa workload không frozen,
bao gồm thời gian chờ; không dùng số này như nhiệt độ chỉ các training steps bận CPU.
Không cố làm host nóng tới90°C để test cutoff; nhánh emergency kiểm bằng fixtures.
Không tự restart sau emergency. Software không bảo đảm tuyệt đối nhiệt phần cứng.

Các lần lỗi được giữ: UI build đầu thiếu node PATH của systemd (sửa explicit PATH
và fail rõ khi cgroup chưa xuất hiện); benchmark reverse đầu dùng nhầm journal path
(sửa input manifest, không sửa reference results); restart probe đầu nhiễu traffic.
Không gọi các attempts này PASS.

Code: [guard](../ai-training/scripts/integration-guard.py),
[time-weighted policy](../ai-training/scripts/rolling-resource-policy.py),
[tests](../ai-training/tests/test_rolling_resource_policy.py).

## Training decision và handoff

**TRAINING_GATE=BLOCKED; BACKGROUND_TRAINING=NOT_STARTED.** Đã khóa tối đa một design
[glu207-derivative-pilot-v1](../ai-training/configs/research/glu207-derivative-pilot-v1.json).
Design chưa phải executable training config. So C0frozen, C1calibration-only,
C2một fine-tune cùng9.675784M/spec207; rule-only paired khi có observability. Tối đa
một epoch hoặc250updates, không sweep. Nếu C1tương đương, giữ frozen weights.

Thiếu cụ thể: calibration benign mới; evaluation khóa trước từ ít nhất hai môi
trường có outcome/provenance review; split/dedup theo workflow/campaign/time với
embargo>=300s; new-run checkpoint/optimizer/RNG/sampler round-trip; persistent training
supervisor/status/checkpoint writer đã được kiểm với run mới. Không lấy formal
production admission làm điều kiện ngăn nghiên cứu development hợp lệ, nhưng cũng
không dùng research intent labels để chứng nhận independent quality.

**Nhiệm vụ ưu tiên tiếp theo**: thu một cohort benign/application workflows và
verified positive outcomes ở hai lab khác nhau, khóa train/cal/eval roles trước khi
chạy, ưu tiên command injection/XSS và benign POST hard negatives. Phải thu được
207contract hoặc xác định model request-only phù hợp; không train thêm chỉ từ derivative
cùng nguồn rồi gọi generalization improvement. Chưa cần tăng model size.

Full Rust57tests PASS; frontend3, launcher7, worker4, correlation11,
resource/candidate13PASS. Rust/UI build PASS. Giữ authentication/policy/rules,
Student business code, frozen checkpoints/spec/thresholds/dataset và release assets.
Sensitive evidence/derivative/runtime giữ local, không Git public. Foundation và
workloads do nhiệm vụ khởi động được dừng sau verification; volumes còn nguyên.

[Team setup](TEAM_SETUP_AND_AI_STATUS.md) và
[report/evidence index](../ai-training/reports/RULE_AI_COORDINATION_20261107.json)
là điểm bàn giao. Git commit/push chỉ source, tests, safe config và aggregate docs;
không merge main hoặc đổi published release.
