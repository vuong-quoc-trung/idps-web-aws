# Chỉ mục AI-IDPS

| Phần | Điểm bắt đầu |
|---|---|
| Kiến trúc và nghiệm thu Local hiện hành | [R42](126_T09_R42_FINAL_LOCAL_HANDOFF.md) · [Evidence](../security-web/deploy/local-r42/evidence/acceptance.json) |
| Cài đặt và vận hành | [Installer và systemd profile](../security-web/deploy/local-r39/) · [Hướng dẫn tiếng Việt](../security-web/deploy/local-r39/INSTALL.md) · [Beta.2](https://github.com/vuong-quoc-trung/idps-web-aws/releases/tag/v0.1.0-beta.2) |
| Mã ứng dụng | [Student backend](../student-web/backend/src/) · [Student frontend](../student-web/frontend/src/) · [Rust Security Web](../security-web/src/) · [Migrations](../security-web/migrations/) |
| Edge và cảm biến | [NGINX](../security-web/nginx/) · [Suricata](../security-web/config/suricata/) |
| AI và resource | [Registry R37 và rollback R36](../ai-training/contracts/quality-freeze-r37/slots.json) · [Code AI](../ai-training/src/idps_ai/) · [Protocol T07](../ai-training/contracts/evaluation-v1/protocol.json) |
| AWS staging | [Gateway và Suricata R46](131_T09_R46_AWS_WEB_INFRASTRUCTURE_SETUP.md) · [Nghiệm thu R45](130_T09_R45_AWS_INFRASTRUCTURE_ACCEPTANCE.md) · [Runbook vận hành](AWS_STAGING_OPERATIONS_HANDOFF.md) · [Preflight R44](129_T09_R44_AWS_PREFLIGHT.md) · [Thiết kế AWS](127_T09_AWS_MIGRATION_HANDOFF.md) · [Topology R38](../security-web/deploy/local-r38/aws/) |
| Nghiên cứu | [Báo cáo cũ trong docs](./) · [Chỉ mục evidence nghiên cứu](../release/research-history-index.json) · [Bàn giao nhóm](11_TEAM_RELEASE_20261105.md) |
| Bảo trì | [Kết quả và phục hồi cache R43](128_T09_R43_SAFE_PROJECT_CLEANUP.md) |

Bản Local Beta dùng R37 URI100. Quy trình bootstrap bàn giao nhóm dùng GLU207 và Request Intelligence v2 cho mục đích tái lập nghiên cứu. Xem đúng manifest của từng profile trước khi cài hoặc đổi model.
