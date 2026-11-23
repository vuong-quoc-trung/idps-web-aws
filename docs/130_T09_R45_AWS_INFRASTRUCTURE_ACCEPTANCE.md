# R45 — Nghiệm thu hạ tầng AWS staging

Kiểm tra ngày 23/11/2026. Nhánh R45 dựa trên `0eedb93b76c62b1695519e0aa3661ff9c916831e`, HEAD remote của `feature/ai-idps-https-ml-integration` tại lúc tạo worktree. Remote đi trước worktree `idps-r35` ba commit cùng lịch sử. R45 dùng một worktree riêng và chỉ thay đổi tài liệu. [Kiến trúc Local R42](126_T09_R42_FINAL_LOCAL_HANDOFF.md) · [Handoff AWS](127_T09_AWS_MIGRATION_HANDOFF.md) · [Preflight lịch sử R44](129_T09_R44_AWS_PREFLIGHT.md) · [Runbook staging](AWS_STAGING_OPERATIONS_HANDOFF.md)

**R45_AWS_INFRASTRUCTURE = PARTIAL.** Inventory EC2, mạng, bảo vệ cơ bản và budget đã đối chiếu. Chưa thể nghiệm thu auto-stop thực tế với quyền của `Websecurity`. Readback cuối lúc `2026-11-23T13:51:15Z` xác nhận EC2 ở trạng thái `stopped`, cùng EIP và EBS. Trong R45, các phép thử lifecycle chỉ dùng `DryRun` và không cập nhật cấu hình AWS.

## Infrastructure inventory

| Gate | Kết quả và bằng chứng |
|---|---|
| AWS_IDENTITY | **PASS**. MCP `GetCallerIdentity` và CLI profile `websecurity-staging` độc lập trả cùng ARN `arn:aws:iam::680480584595:user/Websecurity`. Region `ap-southeast-1`. |
| EC2 | **PASS** cho cấu hình API. `websentinel-ai-idps-staging`, `i-0b6f2e4f3ed32f514`, `m7i-flex.large`, 2 vCPU, 8 GiB, x86-64, On-Demand. `DescribeInstanceTypes` và `DescribeInstanceTypeOfferings` xác nhận cấu hình và cả ba AZ. AMI Canonical `ami-00094c315dd37d160`, Ubuntu Server 26.04 amd64 build `20261120`. Phiên bản guest 26.04.1 do người vận hành bàn giao, chưa đọc lại `/etc/os-release` trong R45. |
| EC2 lifecycle | **PASS** cho `StartInstances` và `StopInstances` của operator trên đúng ID, cả hai trả `DryRunOperation`. Protection `DisableApiTermination=true`, `DisableApiStop=false`, instance-initiated shutdown behavior `stop`. `DescribeInstanceStatus` hiện `not-applicable` vì máy đã dừng. CloudWatch ghi `StatusCheckFailed=0` từ 12:21 đến 12:36 UTC trong lần chạy trước. Kết quả 3/3 do người vận hành bàn giao. |
| EBS | **PASS**. `vol-06f41700f2be0f4c3`, root `/dev/sda1`, 40 GiB gp3, 3.000 IOPS, 125 MiB/s, `Encrypted=true`, `DeleteOnTermination=true`. `DescribeVolumes` xác nhận KMS-backed encryption. `kms:DescribeKey` bị từ chối nên alias `aws/ebs` là thông tin bàn giao chưa xác minh lại. `DescribeSnapshots` không thấy snapshot do tài khoản sở hữu cho volume này tại lần đọc. |
| VPC_NETWORK | **PASS** cho cấu hình. VPC mặc định `vpc-08a0a47f1053cd88a` (`172.31.0.0/16`), subnet `subnet-0f8467d7317cc7205` (`172.31.32.0/20`, `ap-southeast-1a`, auto-assign IPv4 bật). Main route table `rtb-03da8a87995fae995` có route `0.0.0.0/0` active qua `igw-0b1b6662e78680eb1`. Không có IPv6 trên ENI staging. Outbound/DNS trong guest đã có kết quả thủ công, chưa đo lại trong R45. |
| SECURITY_GROUP | **PASS** cho ingress: `websentinel-staging-sg` (`sg-00f4d98eabf65afca`), có TCP 80/443 public IPv4. Cổng 22/5432 và backend không có rule ingress. Egress hiện allow-all IPv4, cần giới hạn theo dependency thực tế khi triển khai. IMDSv2 `HttpTokens=required`, IPv6 metadata tắt, hop limit 2, instance tags qua metadata tắt. Tags instance `Project=WebSentinel` và `Environment=Staging`. |
| ELASTIC_IP | **PASS**. `13.229.169.1` còn liên kết tới `172.31.33.245` trên đúng instance đã stopped. Allocation `eipalloc-0ac40a8944068063a`. Một EIP trong region và không có EIP chưa gắn tại lần đọc. |
| IAM | **PARTIAL**. `GetInstanceProfile` trả đúng role `WebSentinel-Staging-EC2-Role`, `GetRole` xác nhận trust `ec2.amazonaws.com`. `ListAttachedRolePolicies` và `ListRolePolicies` của role, liệt kê policy của user, `iam:SimulatePrincipalPolicy` đều bị từ chối. Chưa xác minh attachment `AmazonSSMManagedInstanceCore`, ngữ cảnh quyền toàn bộ của operator và phạm vi quyền auto-stop của hai role. |
| SSM | **PASS** cho kết nối lịch sử bằng đúng IAM user. `DescribeSessions` có hai session `Websecurity` kết thúc lúc 12:39:01 và 12:46:20 UTC. Không có session Active khi kiểm và `GetConnectionStatus=notconnected` khi máy dừng. Kết nối hiện thời chỉ có thể kiểm lại trong phiên bảo trì. |
| EC2_QUOTA | **BLOCKED**. `servicequotas:GetServiceQuota` cho `L-1216C47A` bị từ chối. `DescribeAccountAttributes` trả legacy `max-instances=20` và EIP `vpc-max-elastic-ips=5`. Giá trị legacy không xác định được số vCPU On-Demand Standard còn lại. |

Bằng chứng cấu hình lấy từ `DescribeInstances`, `DescribeInstanceStatus`, `DescribeInstanceAttribute`, `DescribeImages`, `DescribeVolumes`, `DescribeAddresses`, `DescribeVpcs`, `DescribeSubnets`, `DescribeRouteTables`, `DescribeInternetGateways`, `DescribeNetworkInterfaces` và `DescribeSecurityGroups` trên account/region đã xác nhận. Các lệnh kiểm tra được ghi trong [runbook](AWS_STAGING_OPERATIONS_HANDOFF.md).

## Auto-stop tám giờ

| Gate | Kết quả và cách kiểm tra |
|---|---|
| LAMBDA | **PARTIAL**. CloudWatch log group `/aws/lambda/websentinel-autostop-8h` có `INIT_START` Python 3.13 và `REPORT` 128 MiB. `lambda:GetFunction`, `GetFunctionConfiguration`, `GetPolicy` bị từ chối. Chưa đọc code/deployed SHA, handler, timeout, role binding hoặc biến môi trường. |
| SCHEDULER | **BLOCKED**. Console bàn giao `default/websentinel-autostop-check-15m`, `ENABLED`, `rate(15 minutes)`. `GetSchedule` và `ListSchedules` bị từ chối. Chưa đọc được flexible window, target ARN, input, retry/DLQ và execution role. |
| LAMBDA_READ_TEST | **PASS theo bằng chứng vận hành bàn giao**. Console Test trên một instance đang dừng trả `{"status":"SKIPPED","instance_state":"stopped"}`. R45 không tái hiện kết quả này vì `lambda:InvokeFunction` trả `AccessDeniedException` kể cả ở `InvocationType=DryRun`. CloudWatch log của R45 chỉ ghi lifecycle, chưa có outcome từ handler. |
| SCHEDULER_INVOKE_TEST | **BLOCKED**, có bằng chứng thời gian tương thích với lịch. Ba lượt START cách nhau 899,853 giây và 900,120 giây. Ba bucket một phút cùng có một Lambda invocation và một Scheduler invocation attempt của group `default`. Log không ghi schedule ARN/execution ID. Metric group không xác định được schedule nào đã gọi. `cloudtrail:LookupEvents` bị từ chối và CloudTrail Event History mặc định cũng không chứa Lambda `Invoke` data events. |
| AUTO_STOP_DRY_RUN | **BLOCKED**. Chưa thể đọc hoặc sao lưu `DRY_RUN` hiện hành, chạy unit test trên mã đã deploy hoặc invoke handler. EC2 `DryRunOperation` của operator chỉ xác minh quyền EC2 của operator. |
| AUTO_STOP_REAL_STOP | **BLOCKED**. Chưa thể xác minh scope Lambda, role, config backup/restore và danh tính Scheduler. EC2 đã dừng tại lúc kiểm tra. Không khởi động phiên thử nếu chưa đủ điều kiện kiểm chứng và phục hồi. |
| AUTO_STOP_8H_CONFIGURATION | **BLOCKED**. Mục tiêu `MAX_SESSION_MINUTES=480`, `DRY_RUN=false`, `ENABLED`, `rate(15 minutes)` chưa được xác nhận trực tiếp. |
| AUTO_STOP_PRODUCTION_STATE | **BLOCKED**. Chưa có bằng chứng Lambda thực thi `StopInstances`, EC2 chuyển `stopping → stopped` và cấu hình chính thức được đọc lại. |

### Bằng chứng CloudWatch

| Lambda START (UTC) | Request ID prefix | Lambda `Invocations` | Scheduler `InvocationAttemptCount` |
|---|---|---|---|
| `2026-11-23T13:19:54.406Z` | `726b043d` | 1 ở bucket `13:19Z` | 1 ở bucket `13:19Z`, group `default` |
| `2026-11-23T13:34:54.259Z` | `726b0440` | 1 ở bucket `13:34Z` | 1 ở bucket `13:34Z`, group `default` |
| `2026-11-23T13:49:54.379Z` | `726b0444` | 1 ở bucket `13:49Z` | 1 ở bucket `13:49Z`, group `default` |

Metric Lambda `Errors` là 0 trong hai bucket 15 phút đã đọc trước lượt 13:49 UTC. `TargetErrorCount` và `InvocationDroppedCount` chưa có datapoint trong cửa sổ đọc. Không suy ra một lần giao hàng cụ thể từ metric thưa. Các quyền đọc cần trước khi thử gồm `lambda:GetFunction` và `lambda:GetFunctionConfiguration` trên đúng function, `scheduler:GetSchedule` trên đúng schedule và quyền đọc trust/policies của hai execution role. Chấp nhận bản export cấu hình đã lọc do chủ tài nguyên cung cấp, miễn pin được revision/hash và ARN đang chạy. Sau khi audit, một principal có quyền giới hạn theo ARN thực hiện invoke và cập nhật cấu hình thử rồi khôi phục. Lambda role chỉ cần describe và stop đúng instance kèm tag guard. Không cần AdministratorAccess. [Scheduler metrics](https://docs.aws.amazon.com/scheduler/latest/UserGuide/monitoring-cloudwatch.html) · [Scheduler context](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-schedule-context-attributes.html) · [CloudTrail Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)

## Billing và ngưỡng chi phí

`GetAccountPlanState` trả **FREE / ACTIVE**, tổng credit còn **139,999863 USD**, hết hạn **plan** lúc **18:25 ngày 18/04/2027 giờ Việt Nam** (`11:25 UTC`). `GetCredits` trả `IAM user access not activated`. Ngày hết hạn, phạm vi bù phí của từng khoản và thông tin về khoảng 35 USD chưa xác minh được. Credit hiển thị là số dư tại thời điểm đọc. Dự toán không tính khoản cấp định kỳ. Cost Explorer cho 01–22/11 UTC có Usage `0,000137 USD` và Credit `−0,000137 USD`, còn ước tính và chưa bao phủ chi phí mới nhất. [Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/) · [GetCredits](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_billing_GetCredits.html)

**BUDGET_ALERTS = PASS.** `WebSentinel-Monthly-Budget` là 25 USD/tháng, loại Credit và Refund. Cảnh báo khi actual vượt 85% và 100%, forecast vượt 100%. Ba cảnh báo ở trạng thái `OK`. `DescribeBudgetActionsForBudget` trả 0 action. Budget theo dõi chi phí. Auto-stop theo dõi tuổi từng phiên chạy.

| Hạng mục ở Singapore | Giả định trước thuế, credit và miễn phí |
|---|---:|
| m7i-flex.large Linux On-Demand | 0,1197 USD/giờ chạy |
| EBS gp3 40 GiB | 40 × 0,096 = 3,84 USD/tháng |
| EIP giữ suốt tháng 31 ngày | 744 × 0,005 = 3,72 USD/tháng, kể cả khi stopped |
| CloudWatch Logs | 1 GB ingest Standard + 1 GB-month lưu trữ + 1 GB Logs Insights 0,737 USD |
| Snapshot Standard | 10 GB-month incremental giả định × 0,05 = 0,50 USD, chưa có snapshot quan sát được |
| Egress Internet | 5 GB tính giá 0,12 USD/GB = 0,60 USD, bỏ qua hạn miễn phí dùng chung |
| Lambda | 2.976 lượt × 128 MiB × 1 s giả định và phí request khoảng 0,007 USD |
| Scheduler | 2.976 attempts/tháng theo chu kỳ 15 phút, khoảng 0,004 USD ở đơn giá gross; usage thực có thể rơi trong mức miễn phí |

| Giờ EC2/tháng | EC2 + gp3 + EIP + hai dịch vụ auto-stop | Kịch bản có cả logs, snapshot, egress | Dự phòng tới 25 USD |
|---:|---:|---:|---:|
| 0 | 7,57 | 9,41 | 15,59 |
| 80 | 17,15 | 18,98 | 6,02 |
| 100 | 19,54 | 21,38 | 3,62 |
| 110 | 20,74 | 22,57 | 2,43 |
| 160 | 26,72 | 28,56 | −3,56 |

Chọn **100 giờ/tháng** làm giới hạn vận hành ban đầu. 110 giờ đã dùng gần hết dự phòng nếu tổng thực tế có thuế 10%. 160 giờ vượt ngân sách ngay ở chi phí lõi. Không có giả định mua thêm NAT Gateway, ALB, RDS hay software subscription. Chưa có retention trên log group Lambda tại thời điểm đọc. Cần đặt vòng đời log khi phê duyệt logging và giám sát ingest ngoài chi phí nền. [EC2 và EBS SKU Singapore](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-southeast-1/index.csv) · [IPv4](https://aws.amazon.com/vpc/pricing/) · [CloudWatch SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ap-southeast-1/index.csv) · [Lambda](https://aws.amazon.com/lambda/pricing/) · [Scheduler SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSEvents/current/ap-southeast-1/index.csv) · [Data transfer SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDataTransfer/current/ap-southeast-1/index.csv) · [Chi phí khi EC2 dừng](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html)

## Phạm vi dành cho R46

| Gate | Kết quả |
|---|---|
| DOMAIN_DNS | **PENDING**. Resolver trả `NXDOMAIN` cho A và AAAA của `student-dut.duckdns.org` và `websentinal.duckdns.org` tại lúc kiểm. |
| NGINX_HTTPS | **PENDING**. Virtual hosts, Certbot/chứng thư, HTTPS public và HTTP redirect chưa nghiệm thu trên staging. |
| AI_IDPS_DEPLOYMENT | **PENDING**. Student Web/Audit, Security Web/Rust Hybrid, PostgreSQL, Suricata, R37 ONNX, request-ID correlation, telemetry và acceptance đều cần chứng minh trên EC2. |
| RESOURCE_SAFETY_PROFILE | **BLOCKED** cho chạy scorer AWS. Local guard đòi `coretemp` và nền tảng CPU đã bind. EC2 status/CPU metrics không đo nhiệt CPU vật lý. Cần profile cloud được phê duyệt, kiểm kernel quota/ownership, watchdog, pressure/oom và ABSTAIN trước khi bật scorer. |
| DOCUMENTATION | **PASS**. Kết quả và runbook tham chiếu tại [chỉ mục dự án](PROJECT_INDEX.md). |

Không có sửa đổi AWS trong R45. Vấn đề ưu tiên là quyền đọc auto-stop ở phạm vi hẹp, sau đó xác nhận một phiên staging rảnh để nghiệm thu Scheduler → Lambda → IAM → EC2 Stop và đọc lại cấu hình tám giờ. Xem trình tự và rollback trong [hướng dẫn bàn giao](AWS_STAGING_OPERATIONS_HANDOFF.md).
