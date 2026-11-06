# AWS shadow demo: phương án triển khai, chưa triển khai

Ngày đánh giá: 2026-11-06. Không tạo tài nguyên, không giả định free tier.
Đây là demo shadow có kiểm soát truy cập, chưa phải production IDPS.

## Quyết định kiến trúc

Dùng **một EC2 t3a.large Linux x86_64, 8 GiB RAM, 40 GB encrypted gp3**, tại
us-east-1. Chọn CPU credit **Standard**, không để Unlimited phát sinh phí credit.
Chưa cần ALB, NAT Gateway, RDS, ECS hoặc Kubernetes cho demo một máy.
Một lỗi máy có thể làm dừng toàn demo; chấp nhận giới hạn này ở milestone đầu.

```text
Tester CIDR → HTTPS443 Nginx → Student API loopback8080
                         └→ compiled Student frontend
                         └→ private Unix telemetry → frozen RIv2 worker
Student audit + sanitized Nginx + AI metadata → Rust loopback3001 → PostgreSQL
Admin → SSM port forwarding → existing Security Web loopback3001
```

Security Group chỉ mở443 từ CIDR tester đã được duyệt. Không công khai PostgreSQL,
8080, 3001 hoặc frontend dev server; mặc định không mở SSH. DNS/TLS certificate
và quyền sở hữu domain cần xác nhận trước triển khai. Nginx serve frontend đã build,
không chạy Vite dev trên AWS. Giữ hai database đúng major version hiện tại
(Student PG16, Security PG17), chỉ bind loopback; không dùng production credentials.

Worker vẫn shadow: `ENFORCEMENT_MODE=OFF`, `AUTO_BLOCK=false`, firewall helper
`/bin/false`. Không ghép score GLU207/RIv2, không tự block. Suricata live là phần
mở rộng riêng; demo Request v2 không phụ thuộc sensor chưa được tích hợp.

## Packaging và vận hành

- Build ngoài VM; pin Java25, Rust >=1.88 và lockfiles, Python từ Team Release.
  Deploy artifact theo thư mục version; giữ bản hiện tại và bản trước để rollback.
  Không chạy compiler cạnh ứng dụng trên VM8GiB.
- Tải model inference bundle từ GitHub Release bằng bootstrap hiện có, kiểm
  SHA256 và pinned manifest. Core bundle khoảng158MB; không cần20GB raw research.
  Kiểm golden smoke trên CPU AMD mục tiêu trước khi nhận deploy.
- systemd units riêng cho Student, Rust, Nginx và worker; restart có backoff và
  giới hạn số lần, readiness khác process-alive. Worker failure không restart Student.
  Readiness triển khai phải kiểm model + HTTP telemetry receipt, không chỉ socket.
- Dùng service accounts riêng. Thiết kế group telemetry cho Nginx/worker, socket
  0660 trong thư mục0750; journal0640 cho worker/Rust. **Chưa thay quyền local**;
  cần test permission/negative access trước AWS. Local cùng UID không chứng minh
  được trust boundary nhiều service accounts.
- IAM instance role tối thiểu cho SSM; nếu thêm S3 backup thì chỉ cấp đúng bucket/
  prefix. Không IAM admin hoặc access key lưu trong repo. Secrets qua private
  EnvironmentFile0600 được cấp bằng phiên SSM, hoặc SecureString được duyệt;
  không nhét vào user-data, artifacts, command logs hoặc dashboard.
- Nhật ký rotation có hạn mức, chỉ metadata. Theo dõi worker stale/thermal-resource
  stop, observed-unscored requests, queue/rejection/error, disk và CPU credits.
  CloudWatch log/alarms chỉ bật sau khi chốt retention/chi phí; không upload raw HTTP.

Ước lượng RAM để bắt đầu đo: OS/services nền1GiB, Student <=1GiB, Rust <=512MiB,
AI <=1GiB, hai PostgreSQL tổng<=2GiB, Nginx/static assets<=256MiB, còn headroom.
Đây là ngân sách thiết kế, chưa phải sizing đã kiểm tải. Một máy8GiB không được
coi là đủ capacity chỉ từ demo local vài request. CPU credits hết sẽ làm Standard
throttle; phải đo latency và credit balance trên target trước khi chấp nhận tải.

## Blocker triển khai quan trọng

Worker/guard local hiện yêu cầu CPU hwmon thật. EC2 guest có thể không cung cấp
cảm biến đó và khi thiếu, code **fail closed**. Không giả nhiệt độ hoặc bỏ check
để chạy. Milestone deployment cần một policy dành cho cloud, kiểm được CPU/RSS,
queue/time budget và sự cô lập workload, tách rõ với thermal policy máy vật lý.
Policy này chưa được viết hoặc kiểm chứng trong milestone local.

Còn cần deploy units/config có secrets và permission boundary đúng, TLS/CIDR,
khởi động/migration trên VM sạch, smoke frozen model, test crash/recovery và
backup restore trên môi trường mục tiêu. Vì vậy `AWS_DEPLOYMENT_READY=FALSE`.

## Chi phí với giả định rõ ràng

Giá tham chiếu ngày2026-11-06, Linux On-Demand us-east-1, chưa thuế, discount hay
free tier. T3a.large: $0.0752/giờ; gp3: giả định vùng $0.08/GB-tháng; IPv4:
$0.005/address-giờ. Nguồn: [EC2 T3 pricing](https://aws.amazon.com/ec2/instance-types/t3/),
[EBS gp3](https://aws.amazon.com/ebs/volume-types/),
[public IPv4 pricing](https://aws.amazon.com/vpc/pricing/).

| Khoản | 730 giờ/tháng | Demo40giờ, giữ disk cả tháng |
|---|---:|---:|
| EC2 t3a.large | $54.896 | $3.008 |
| 40GB gp3 baseline IOPS/throughput | $3.20 | $3.20 |
| Một public IPv4, chỉ giữ khi máy chạy | $3.65 | $0.20 |
| Tổng cơ sở | **$61.75** | **$6.41** |

Cột40giờ yêu cầu public IPv4 được giải phóng khi stop; nếu giữ Elastic IP cả
tháng thì IPv4 vẫn $3.65 và tổng khoảng$9.86. Chưa gồm snapshot/S3 backup,
logs/alarms, DNS/domain và outbound transfer; không gọi tổng cơ sở là hóa đơn
trọn gói. Dự toán sơ bộ$65–75/tháng chạy liên tục chỉ có ý nghĩa nếu các khoản
phụ được giới hạn; phải xác nhận region và calculator khi xin triển khai.
Standard mode tránh phí surplus credit nhưng có thể giảm tốc độ:
[AWS Standard credit behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html).

## Backup, rollback và điều kiện hoàn thành milestone AWS

Đề xuất logical `pg_dump` hai DB mỗi ngày, encrypt backup và giữ7bản trong kho
được duyệt; scope IAM chỉ prefix backup, không công khai. EBS snapshot bổ sung
không thay kiểm chứng logical restore. Chưa có bucket hoặc backup trả phí nào
được tạo. Mục tiêu RPO24h/RTO1h phải kiểm bằng restore, chưa được chứng minh.

Trước upgrade: backup/restore thử, ghi schema và artifact versions. Rollback app
bằng chuyển release path; migration0005 hiện thêm bảng, không tự drop bảng để
rollback. Khôi phục database chỉ theo runbook đã test và quyết định operator.

Chỉ nhận AWS demo khi fresh deployment, TLS/auth/network isolation, frozen model
parity, loss visibility, resource-budget policy, bounded restarts và restore đều
PASS. Không yêu cầu training mới hoặc GLU207 live để đạt milestone này.
