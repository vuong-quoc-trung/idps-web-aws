# T09 R22 — Local Shadow and Quality Evidence

**Local KVM shadow PASS. Hybrid release và quality metrics trên native còn BLOCKED.** Run `t09-r22-local-UCE1ALdx` dùng NGINX, Student Web/H2, Suricata và Student Audit thật trong guest không NIC. Host Rust Security Web nhận metadata đã bind với receipt, ghi correlation và quyết định Hybrid vào PostgreSQL riêng. RI v2 phục vụ cả sáu quyết định. SwiGLU R20 có journal riêng và không có đường ghi vào input AI của Hybrid. Không có proposal hoặc firewall action. [Trạng thái](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/status.json) · [Bằng chứng](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/quality-ledger.json) · [T07](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

## Model và parity

SwiGLU R19 **395.360 tham số**, checkpoint step 55, dùng URI76 `float32 [N,76]` và isotonic R20. ONNX SHA-256 `1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525`. SHA manifest checkpoint `0ed456322141181d93b068e2555285f6455e6cad45c9c4856f1bb01b0bd296c0`. Rust nhận pin của manifest và kiểm digest ONNX khi load. Xác minh bytes đã đóng gói vào guest, ABI, transform, score và threshold strict `>` tại **0,9633333086967468**. Ngưỡng này thuộc benchmark WAF development. [R21 handoff](../ai-training/contracts/development-bulk-v1/r21-shadow-handoff.json) · [Manifest trong guest](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/guest-resource/guest/unified-stage.json)

- **Preprocessing 6/6 byte-exact** giữa URI76 của NGINX mirror và phép tính Python độc lập từ benign roster. **Rust/Python ONNX parity 4/4**, sai số tuyệt đối lớn nhất **0**. Chạy lại R19 ONNX gốc và áp dụng mapping isotonic đã pin độc lập trên cùng bốn vector, sai số **0** và quyết định theo ngưỡng khớp **4/4**. [Đối soát độc lập](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/verification.json)
- **RI v2 6/6** khớp Python reference trong sai số kiểm thử `1e-7`. Rust/PostgreSQL bind đúng trusted request ID, flow/transaction Suricata, proof và RI v2 event ID. Điểm được Hybrid sử dụng khớp journal RI v2 trong sai số transport `1e-12`. [Ledger theo request](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/quality-ledger.json)
- Bundle có `swiglu.onnx`, `model-scope.json`, `checkpoint-manifest.json` và `deployment.json`, dùng tên file tương đối. CLI `bundle.py stage <dir>` và `bundle.py verify <dir>` cho phép tạo và kiểm tra lại thư mục sau khi di chuyển. ONNX dành cho inference. Checkpoint manifest là provenance của model. R23 có thể dùng Rust scorer hiện hành với slot `swiglu`, ORT cùng kiến trúc và tham số `--research-manifest-sha` đã pin. [Bundle](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/bundle/deployment.json) · [Stager](../ai-training/contracts/local-shadow-r22/bundle.py)

## Sáu request thật

Mọi offset tính từ dispatch trong guest. Cutoff **1.000 ms**, guard **1 ms**. `NONE` ở ca 3 là fault panel giữ collector polling **1.250 ms** trong khi HTTP và mirror tiếp tục. Ba nguồn có proof thật sau cutoff. URI76 có thể sẵn sàng từ mirror trước cutoff độc lập với mask của ba source receipts. RI v2 bridge và Hybrid là đường advisory sau quan sát. [Guest receipts](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/guest-resource/guest/receipt-ledger.jsonl)

| Ca | HTTP và Oracle | Mask tại cutoff | URI76 sẵn sàng | R20 | Hybrid |
| --- | --- | --- | ---: | --- | --- |
| CSRF | 200, semantic PASS | `NSA` | 6,224 ms | SCORED | LOG_ONLY |
| Login | 204, session rotation và JDBC PASS | `NA` | 0,640 ms | SCORED | LOG_ONLY |
| Principal, collector held | 200, principal và JDBC role PASS | `NONE` | 0,871 ms | SCORED | LOG_ONLY |
| Principal, scorer down | 200, principal và JDBC role PASS | `NSA` | 0,788 ms | ABSTAIN | LOG_ONLY |
| Principal, scorer recovered | 200, principal và JDBC role PASS | `NSA` | 0,677 ms | SCORED | LOG_ONLY |
| Principal, rollback RI-only | 200, principal và JDBC role PASS | `NSA` | 3,072 ms | ABSTAIN | LOG_ONLY |

Login trả header và hoàn tất response bodyless sau **957,93 ms**. NGINX và Audit proof có lúc **960,57 / 960,48 ms**. Suricata producer ghi khoảng **956,58 ms**, collector nhận **1.321,56 ms**, proof sẵn sàng **1.322,06 ms**. Vì vậy login là `NA` tại cutoff dù structural mask là `NSA`. R20 đã score ở **4,32 ms** trên URI76 có sẵn từ dispatch. Oracle kiểm `last_login_at`, session rotation và principal trên các GET sau login. [Timing chi tiết](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/quality-ledger.json)

## Quality evidence và giới hạn

- **6 request mirror**, **4 NSA**, **1 NA**, **1 NONE**, **2 URI76 phân biệt**, **4 cặp score**, **0 bất đồng** theo hai ngưỡng đã pin. Phân bố R20 gồm ba điểm **0,1830** và một điểm **0,9619**. RI v2 gồm năm điểm **0,00371** và một điểm **0,13698**. R20 có **2 ABSTAIN** do hai fault/lifecycle control, RI v2 có **0 ABSTAIN**. Quan sát **0 lỗi suy luận** trong run hoàn tất. [Quality summary](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/quality-summary.json)
- Inference p50/p95 **0,629/3,045 ms** cho R20 và **4,144/62,531 ms** cho RI v2. Mẫu gồm cold start và restart. Cần đo tiếp performance gate T07 với tải cố định và ba cửa sổ warmup đã định. [Latency và score histogram](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/quality-summary.json)
- Ledger lưu trusted ID, lineage campaign/boot, source timing/proof, mask, URI76 đã lọc, field flags, slot model, score, latency, risk rule, policy và Oracle. Causal history giới hạn trong receiver và có cờ incomplete/truncated. Thời điểm sau khi nhận kết quả scorer là cận trên thời gian history sẵn sàng. Session chỉ ghi scope phiên lab đã đối soát bằng Oracle. Không có actor ID hoặc cookie trong feature. Ledger dùng file lock, commit atomic cùng cursor, hash và dedup theo request ID/key. Giới hạn **32** row, **12 KiB/row**. Run ghi khoảng **28,5 KB** cho sáu row. [Schema và checkpoint code](../ai-training/contracts/local-shadow-r22/evidence.py)
- **6 Oracle verified, 0 native label được review độc lập, 0 eligible cho cohort độc lập**. Intake không tìm thấy handoff do custodian pin. Oracle nằm riêng với label. Publisher `normal/anomalous` chỉ mô tả nguồn huấn luyện R20. Run này bỏ ngỏ recall, precision và FPR theo T07. [Intake](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/admission.json)

## Tài nguyên, phục hồi và bàn giao

Unit `t09-r22-local-UCE1ALdx.service` được xác minh RUNNING với PID chính **20460**, supervisor Python **20466**. Local executor giới hạn 1 CPU, 3 GiB. Resource Adapter xác minh QEMU và RI v2 trong cgroup riêng 1 CPU, 3 GiB cùng guardian và kernel readback. PostgreSQL riêng có 0,5 CPU, 384 MiB, không có network. Worker **20758**, QEMU **21438**, RI v2 **21478** đã thoát. Unit kết thúc success, `MainPID=0`. Guest, Podman, sockets và cgroup cleanup PASS. Supervisor `Restart=no` để tránh gửi lại HTTP, giữ one-shot lock và permit. Scorer được khởi động lại trong guest theo permit kế tiếp sau ca dừng kiểm soát. Rollback tắt shadow và đã kiểm HTTP, RI v2, Hybrid ở ca cuối. Host `Linger=no`, chưa kiểm duy trì qua lần logout cuối. Xem journal với `journalctl --user -u t09-r22-local-UCE1ALdx.service`. [Resource Adapter](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/guest-resource/result.json) · [PostgreSQL cleanup](../ai-training/.artifacts/t09-r22-local-UCE1ALdx/postgres-resource.json)

Hai lần chạy trước được giữ. `Z1XeHair` dừng sau hai request do bridge chưa chấp nhận MIME type form URL-encoded. `rl9qtHlv` dừng sau bốn request do ca failover lặp CSRF trên phiên đã tồn tại, trong khi Oracle CSRF yêu cầu cookie mới. Bản cuối dùng Oracle principal cho ca sau login và giữ điều kiện login 204, rotation và JDBC. **98 regression tests PASS** gồm allowlist MIME, dedup/cursor, relocation/tampering, cutoff, Resource Adapter và T07. Không có background job R22 còn chạy. [Lần 1](../ai-training/.artifacts/t09-r22-local-Z1XeHair/status.json) · [Lần 2](../ai-training/.artifacts/t09-r22-local-rl9qtHlv/status.json) · [Tests R22](../ai-training/contracts/local-shadow-r22/test_shadow.py)

Commit triển khai `12c9d37` giữ riêng source R22 trên nhánh hiện tại. Hạ tầng guest và executor tái sử dụng từ workspace hiện có. Model, checkpoint và evidence giữ trong artifact store Local.

**R23** có thể dùng bundle và verifier của R22 để tiếp tục shadow cô lập và kiểm tra một common roster native đã review. Đo Rule-only, RI v2, SwiGLU và Hybrid trên cùng request, cutoff và lineage trước khi quyết định replacement. [Offline verifier](../ai-training/contracts/local-shadow-r22/verify_evidence.py)
