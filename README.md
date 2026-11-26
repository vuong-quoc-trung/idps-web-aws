# idps-web-aws
A comprehensive monitoring, early warning, and attack prevention system for AWS web infrastructure.


[Chỉ mục dự án](docs/PROJECT_INDEX.md) · [Local Beta R42](docs/126_T09_R42_FINAL_LOCAL_HANDOFF.md) · [Bàn giao AWS](docs/127_T09_AWS_MIGRATION_HANDOFF.md)

## WebSentinel trên AWS staging

WebSentinel giám sát các ứng dụng web đi qua NGINX HTTPS. Suricata quan sát
nhánh HTTP nội bộ, Student Audit ghi kết quả nghiệp vụ và Rust hợp nhất bằng
chứng theo request ID. Security Web hiển thị cảnh báo, quyết định Hybrid và
cập nhật qua SSE. Mô hình đang phục vụ là HistGradientBoosting URI100
`r37-hgb-uri100-v1`, giữ vai trò tư vấn. Public enforcement và AI auto-ban tắt.

[Nghiệm thu R58 và sơ đồ triển khai](docs/144_T09_R58_FINAL_PROJECT_COMPLETION.md) ·
[Runbook AWS staging](docs/AWS_STAGING_OPERATIONS_HANDOFF.md)

## AI offline và bàn giao nhóm

Frozen Research MVP v1.0 gồm GLU207 và Request Intelligence v2. Xem
[hướng dẫn clone/setup/inference và giới hạn bàn giao](docs/11_TEAM_RELEASE_20261105.md),
[bộ nhớ dự án](docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md) và
[Integration Candidate](docs/10_AI_INTEGRATION_CANDIDATE_20261105.md).

Trên Linux x86_64 có Python 3 và kết nối Internet:

```sh
./scripts/bootstrap-team.sh --tests
```

Bootstrap tải môi trường và model bundle có SHA256, không train hoặc khởi động
dịch vụ. Các assets của release `ai-research-team-20261105` đã được publish và
kiểm chứng bằng clean clone cùng máy: hai model inference và 19 tests PASS.
Training handoff là PARTIAL; xem tài liệu bàn giao về dữ liệu giữ private.

Không dùng lại cấu hình CPU 800% trong các báo cáo lịch sử. Máy nghiên cứu đã có
thermal stops; các công việc bàn giao hiện dùng quota bảo thủ 10% của một CPU,
giám sát cảm biến và watchdog. HTTP/PCAP, session material và evidence riêng vẫn
giữ local; inference không yêu cầu tải corpus nghiên cứu.
