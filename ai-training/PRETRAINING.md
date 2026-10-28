# Chuẩn bị và pilot trước train chính thức

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

Lệnh này **chưa được thực thi**. Mặc định100epoch, patience8, tối đa150phút,
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

Lệnh ca đầu đã chuẩn bị: `bash ai-training/scripts/train-first-session.sh`; chưa thực thi.

Artifact được duyệt: `dataset-ready/prepared`, `dataset-ready/readiness-resource8/readiness.json` và `pilot-ready/` (bản readiness-final gốc vẫn được giữ). Xem `.artifacts/upgrade_20261028/FINAL_TRAINING_HANDOFF.json`. Thư mục `dataset`, report `readiness` cũ và `pilot` là các attempt đã fail hoặc stale và đã được dọn theo yêu cầu. Các lệnh NEXT_COMMANDS cũ đã xóa; chỉ dùng script/handoff hiện hành.
