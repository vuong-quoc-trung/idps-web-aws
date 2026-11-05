# idps-web-aws
A comprehensive monitoring, early warning, and attack prevention system for AWS web infrastructure.


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
dịch vụ. Chỉ chạy thành công sau khi các assets của release
`ai-research-team-20261105` đã được publish. Xem trạng thái kiểm chứng trong tài liệu
bàn giao; không coi URL dự kiến là artifact đã upload.

Không dùng lại cấu hình CPU 800% trong các báo cáo lịch sử. Máy nghiên cứu đã có
thermal stops; các công việc bàn giao hiện dùng quota bảo thủ 10% của một CPU,
giám sát cảm biến và watchdog. HTTP/PCAP, session material và evidence riêng vẫn
giữ local; inference không yêu cầu tải corpus nghiên cứu.
