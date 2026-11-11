# Kho lịch sử mô hình — 11/11/2026

Registry hiện hành: [`MODEL_STRATEGY.json`](../MODEL_STRATEGY.json). Chỉ có
**Request v2 ACTIVE_FROZEN** và **AI-IDPS 10M POSTPONED**. Archive **tại chỗ**
giữ nguyên đường dẫn để không phá manifest, exact-resume và báo cáo cũ.
`.artifacts` và `RESEARCH_MVP_V1_0_FROZEN.json` là kho lịch sử, không phải danh
sách chọn model live. CLI nghiên cứu cũ không được launcher demo gọi.

| Dòng nghỉ khỏi chiến lược | Đường dẫn dưới `.artifacts/` giữ nguyên | Tái sử dụng |
|---|---|---|
| GLU207, derivative, flow robustness | `research_glu207_bounded_final_20261104`, `glu207_derivative_20261107`, `glu207_flow_robustness_20261104` | causal semantics, watermark, correlation; không dùng weights207 cho live588 |
| Request v3 634, channel, frozen-backbone | `request_v3_pilots_20261108`, `request_v3_grounded_20261108`, `request_v3_body_syntax_20261108`, `request_v3_frozen_backbone_20261109` | body46/privacy, Oracle receipts, collision, kết quả âm; không đổi evaluation roles |
| Scaled normalization và unblock pilots | `scaled_normalization_20261107`, `final_training_unblock_20261107`, `training_unblock_20261107` | normalization controls, source shortcuts, sampler/recovery |
| Publisher100K và final200K | `student_publisher_pilot_20261110`, `final_local_training_20261110`, `local_v1_rc1_20261110` | admission SQLite, weak labels, checkpoint; model50696 này KHÔNG phải Frozen Requestv2 |
| MLP, Deep MLP, AE/DAE, residual, gated-residual, tree | `upgrade_*`, `scale_upgrade_20261030`, `generalization_*`, `synthetic_s0_20261027_final` | số học và optimizer/exporter dùng chung trong `src/idps_ai/training/{models,deep,tabular,tree_baseline}.py` |

Configs/reports cùng tên được giữ để tái lập. Các dataset `autonomous_research_*`,
`request_view_*`, grounded/body evidence và holdout không bị di chuyển hoặc mở lại.
Dataset không phải dòng model thứ ba. Published releases giữ nguyên.

Kiểm kê dựa trên implementation, danh mục artifact và manifest/báo cáo có sẵn;
không chạy lại mọi model hoặc chứng nhận lại toàn bộ checkpoint lịch sử.
Không có asset nào được chứng minh vừa thừa vừa an toàn để xóa trong milestone
này. Shared modules còn cần cho frozen bundle và 10M nên được giữ.

Worker live kiểm tra registry đồng thời pin model ID, bundle hash, feature profile
và threshold độc lập; đổi registry đơn thuần không thể nạp model khác.
GLU collector/schema được giữ để đọc lịch sử DB; launcher không khởi chạy GLU
inference. `POSTPONED.json` chặn mọi action thực thi của large workflow cũ;
status vẫn đọc được. Resume sau này cần yêu cầu mới và kiểm tra source bindings,
không xóa marker rồi chạy mù. Không có training/handoff tự động trong demo.
