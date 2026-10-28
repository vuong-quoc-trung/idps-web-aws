# idps-web-aws
A comprehensive monitoring, early warning, and attack prevention system for AWS web infrastructure.


## AI offline và chuẩn bị train

Xem [hướng dẫn AI](ai-training/PRETRAINING.md) và [bộ nhớ dự án](docs/00_PROJECT_OVERVIEW_AND_PROGRESS.md).
Cấu hình ca tiếp theo:8logicalCPU (`CPUQuota=800%`,nice10),RAMmax16GiB/high15GiB,
swap0.16GiB tương đương52,96% RAM mà OS hiện nhìn thấy; đây là mức user chỉ định.
[Báo cáo guard](ai-training/reports/RESOURCE_GUARD_20261028.json) xác nhận77tests
và probe0optimizerstep; chưa chạy ca train chính thức. Artifact train nằm local,
được Git ignore. Metric pilot trước đó là số đo lịch sử2CPU/12GiB.
