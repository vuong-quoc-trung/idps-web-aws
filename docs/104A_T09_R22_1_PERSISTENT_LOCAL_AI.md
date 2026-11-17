# T09 R22.1 — Persistent Local AI và evidence

**Bốn user service đang active và enabled. Linger đã được bật và đọc lại là `yes`. Nghiệm thu runtime PASS trong phạm vi Local cô lập. Native quality và model replacement còn BLOCKED theo T07.** R22.1 không có site Student Web/Suricata/Hybrid đang chạy trên host để nghiệm thu luồng full-stack liên tục. Bài kiểm thử mới dùng NGINX thật với backend benign riêng. Bằng chứng full-stack và ba nguồn được giữ theo lineage R22 KVM khi nhập lại. [R22](104_T09_R22_LOCAL_SHADOW_AND_QUALITY_EVIDENCE.md) · [Trạng thái đang chạy](../ai-training/.artifacts/t09-r221-local-Q1aqGhzf/status.json) · [T07](53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

## Lifecycle và tài nguyên

Model `uri76-swiglu-dev-v1` dùng SwiGLU R19 **395.360 tham số**, checkpoint step 55, URI76 và isotonic R20. SHA ONNX `1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525`. Rust kiểm SHA và ABI khi load. Runtime kiểm thêm SHA manifest, checkpoint manifest, Rust binary và ORT. Ngưỡng `0,9633333086967468` là ngưỡng nghiên cứu. RI v2 giữ serving slot đã pin, là model duy nhất Hybrid hiện hành chấp nhận. [R21 handoff](../ai-training/contracts/development-bulk-v1/r21-shadow-handoff.json) · [Runtime](../ai-training/contracts/local-shadow-runtime/runtime.py)

| User unit | PID ghi nhận | Quota CPU `cpu.max` | RAM tối đa | RAM đang dùng |
| --- | ---: | --- | ---: | ---: |
| `idps-r22-local-scorer.service` | 26275 | `25000 100000` | 384 MiB | 34,4 MiB |
| `idps-r22-local-receiver.service` | 26257 | `25000 100000` | 256 MiB | 19,1 MiB |
| `idps-r22-local-collector.service` | 26260 | `20000 100000` | 128 MiB | 19,2 MiB |
| `idps-r22-local-ri.service` | 24653 | `50000 100000` | 768 MiB | 108,1 MiB |

Kernel xác nhận swap cap 0, ownership và một child trong mỗi inference cgroup. Scorer và RI v2 chạy qua `delegated_guard` với sensor, readback và systemd watchdog. Mỗi unit có `Restart=on-failure`, nghỉ 3 giây và tối đa 3 start trong 180 giây. Exit 78 của safety guard chặn tự restart. Collector và receiver có heartbeat JSON. Socket Unix riêng thuộc user, runtime directory mode 0700. Runner R22 KVM giữ one-shot lock và permit. Service restart chỉ xử lý work đã nhận, không có đường dispatch HTTP. [Source cài unit](../ai-training/contracts/local-shadow-runtime/install.py) · [Kernel readback và PID](../ai-training/.artifacts/t09-r221-local-Q1aqGhzf/status.json)

User manager vẫn active khi transient acceptance unit đã dừng và `MainPID=0`. `Linger=yes` cho phép user service được giữ qua logout theo cấu hình. R22.1 chưa thực hiện logout hoặc reboot thật. [Kết quả acceptance](../ai-training/.artifacts/t09-r221-local-Q1aqGhzf/acceptance.json)

## Reliability acceptance

Run `t09-r221-local-Q1aqGhzf` xử lý **11/11 HTTP 200** qua private NGINX. R20 chấm **9**, trả **2 ABSTAIN** khi scorer chết và khi rollback. URI76 khớp byte Python **11/11**, Rust/Python ONNX đạt sai số tối đa **0** trên các ca chấm điểm. RI v2 có point score cho toàn bộ request trong run sau khi collector drain. SIGKILL chỉ gửi qua PID descriptor tới child scorer đã xác minh ownership. Systemd ghi đúng **1** lần auto-restart và child mới `26053` thay `25876`. Lúc collector dừng, cursor giữ **30** và inbox giữ **2**. Sau restart cursor tới **32**, hai ID vào evidence đúng một lần. Dừng scorer để rollback vẫn giữ ứng dụng HTTP và RI v2, sau đó khôi phục scorer. NGINX và backend tạm đã cleanup. [Biên bản thực nghiệm](../ai-training/.artifacts/t09-r221-local-Q1aqGhzf/acceptance.json)

| R20 inference | n | p50 | p95 |
| --- | ---: | ---: | ---: |
| Cold, lần đầu sau mỗi `READY` | 3 | 0,891 ms | 1,009 ms |
| Warm | 6 | 0,727 ms | 0,746 ms |

Thông số trên đo trong Rust scorer. Đây là cửa sổ chẩn đoán ngắn, chưa đại diện tải T07. Lần thử `SeYlMZww` xác nhận start limiter hoạt động khi chuỗi test chủ động chạm trần. Lần `OixY4KsO` gặp một ABSTAIN sau khởi động lại vì probe gửi ngay khi socket xuất hiện. Phép thử cuối bắt đầu với budget start đã được reset thủ công để đo riêng chu kỳ và chờ heartbeat `READY` của đúng PID mới. Giữ nguyên restart cap và thermal limits. [Biên bản lần thử sau crash](../ai-training/.artifacts/t09-r221-local-OixY4KsO/progress.json)

## Evidence và retention

Receiver lấy trusted ID và dispatch timestamp ở main NGINX request rồi chiếu URI76. NGINX mirror gửi qua socket nội bộ. Evidence ghi timestamps quan sát/sẵn sàng, cutoff **1.000 ms**, guard **1 ms**, URI76, availability flags, causal history và lineage riêng theo host boot/invocation. R20 và RI v2 có điểm, version, latency và provenance tách biệt. RI v2 join theo trusted ID, event ID, thời điểm và model SHA từ journal có rotation. Kết quả RI v2 và policy phía host là advisory sau quan sát. Mirror đơn không chứng minh native source mask, nên lưu `null`. [NGINX include generator](../ai-training/contracts/local-shadow-runtime/nginx.py) · [Store](../ai-training/contracts/local-shadow-runtime/store.py)

Collector nhận native Oracle và proof đã kiểm từ ledger R22, đóng dấu `R22_ARCHIVED_KVM_ENGINEERING`. Nhập lại cùng sáu receipt trả **0** insert và tăng **6** duplicate, cursor giữ nguyên. Enrichment Local có tùy chọn `hybrid-readonly.json` cho named PostgreSQL service. Lookup thực hiện theo batch giới hạn, read-only và kiểm liên kết RI event/score trước khi nhận quyết định từ Rust. Structural proofs sau quan sát không thay đổi cutoff mask. Kết nối PostgreSQL chưa được bật tại host này. Fixture xác nhận policy join từ chối RI binding sai. Đường full-stack được kiểm trong R22 KVM. [Read-only adapter](../ai-training/contracts/local-shadow-runtime/policy.py) · [R22 full-stack](104_T09_R22_LOCAL_SHADOW_AND_QUALITY_EVIDENCE.md)

SQLite commit inbox, evidence và cursor trong một transaction với `synchronous=FULL`, digest kiểm lại sau restart. Inbox tối đa **256** row. Evidence giữ **768** row hoặc **7 ngày**. Giới hạn **12 KiB/row**, file chính giới hạn **16 MiB** và rollback journal có thể dùng thêm dung lượng cùng cỡ trong giao dịch. Rotation logic đã chạy trên **69** row fixture, evict **67**, giữ đúng hai gần nhất và kiểm `quick_check`. Runtime hiện dùng **176.128 byte**. Journal RI v2 có cap riêng kế thừa. Dedup áp dụng trong cửa sổ giữ evidence. Context join đợi cố định **2 giây** trước commit. Metadata đến sau cửa sổ này cần đối soát bằng một handoff có provenance. [Regression và rotation](../ai-training/contracts/local-shadow-runtime/test_runtime.py)

| Lane | Request committed | Distinct URI76 | Cặp point score | R20 ABSTAIN | Native mask |
| --- | ---: | ---: | ---: | ---: | --- |
| NGINX mirror Local, gồm các lần nghiệm thu | 28 | 3 | 22 | 6 | 28 chưa xác minh |
| R22 KVM đã đối soát | 6 | 2 | 4 | 2 | 4 `NSA`, 1 `NA`, 1 `NONE` |
| Tổng giữ | 34 | 5 | 26 | 8 | Báo riêng theo lane |

**110 regression tests PASS.** Ảnh chụp trạng thái giữ số liệu tích lũy từ cả lần nghiệm thu không đạt để không làm mất evidence. Riêng run PASS có 11 request. [Snapshot](../ai-training/.artifacts/t09-r221-local-Q1aqGhzf/status.json)

## Vận hành và R23

State đang chạy ở `~/.local/state/idps-r22-local`. `runtime.json` ghi socket, journal và units. `nginx-includes/` chứa hai include dùng khi NGINX Local chạy cùng user và có quyền vào socket. Site hệ thống hiện chưa gắn các include này. Khi host có luồng Student Web và Suricata thật, xác minh thêm source receipts tại cutoff trước khi claim coverage native. Để rollback shadow, chạy `systemctl --user stop idps-r22-local-scorer.service`. Receiver sẽ ghi ABSTAIN, RI v2 tiếp tục. Dùng `disable --now` cho rollback qua reboot và giữ state cho đối soát. Xem log với `journalctl --user -u idps-r22-local-scorer.service`.

Commit `e24269b` chứa evidence, rotation và regression. Commit `1a9fd53` chứa service runtime, installer và acceptance. Cả hai nằm trên nhánh hiện tại.

R21–R22 giữ **11 vector mixed** chứa **143 anomalous bị bỏ sót**, cùng **730 FN** ở nhóm thuần nhãn ngoài panel mixed. Causal history theo receiver có mặt trong pipeline trước inference. URI shape tĩnh, cùng mode, cùng vector vẫn chỉ cho một score. Ưu tiên đối chiếu scoped history và route/workflow availability trên common roster. Login R22 cho thấy Suricata proof **1.322 ms** và Oracle đến sau cutoff. Giữ chúng cho review, không hồi tố feature. Dữ liệu thu lần này bổ sung engineering evidence nhưng có **0 cohort native hai lớp đủ điều kiện độc lập**. Cần review request-bound, closure theo session/campaign và native CAL/TEST độc lập trước khi đánh giá **recall ≥90% tại FPR ≤1%**, cải tiến feature hoặc thay model trong Hybrid. [R21 ablation](103_T09_R21_MODEL_QUALITY_AND_RELEASE_READINESS.md) · [R22 cutoff](104_T09_R22_LOCAL_SHADOW_AND_QUALITY_EVIDENCE.md)
