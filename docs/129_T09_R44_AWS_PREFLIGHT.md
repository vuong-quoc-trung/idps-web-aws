# R44 — AWS connection và preflight

Kiểm tra ngày 23/11/2026 giờ Việt Nam trên nhánh `feature/ai-idps-https-ml-integration`. Tài khoản `680480584595`, region `ap-southeast-1`. Phạm vi gồm API đọc, IAM Simulator và EC2 DryRun. Sau các probe, EC2 và EBS vẫn trả 0 instance và 0 volume tại Singapore.

| Gate | Kết quả |
|---|---|
| AWS_MCP | **PASS**. AWS MCP gọi STS thành công và tiếp tục truy vấn dịch vụ. |
| AWS_CLI | **PASS**. Profile `websecurity-staging` chạy cả STS và DescribeInstances, kết quả EC2 rỗng. |
| AWS_IDENTITY | **PASS**. Hai phiên trả cùng ARN `arn:aws:iam::680480584595:user/Websecurity`. |
| IAM_PERMISSIONS | **BLOCKED**. RunInstances DryRun và các API đọc chính đạt. Còn thiếu xác minh SSM policy, quyền lifecycle, quota và quyền tùy chọn. |
| FREE_TIER | **PASS** cho plan ACTIVE, balance và ngày hết hạn plan. Hạn từng khoản credit **BLOCKED** vì `billing:GetCredits` trả `IAM user access not activated`. |
| EC2_M7I_FLEX | **PASS** cho catalog vùng, AMI và DryRun. Quota hiệu lực và dung lượng cấp phát vẫn chưa xác minh. |
| MONTHLY_COST | **20,63–21,13 USD** theo giá niêm yết, trước credit và thuế. |
| RESOURCE_CONTRACT | **BLOCKED**. Profile Local yêu cầu CPU và cảm biến đã xác minh. |
| READY_TO_LAUNCH_EC2 | **NO**. Cần chốt SSM, quota và AWS Resource Safety Profile trước khi coi staging sẵn sàng. |

## Phiên kết nối và Free Tier

MCP và AWS CLI được kiểm tra độc lập. Kết quả trùng identity xác nhận cùng principal, còn nguồn credential bên trong MCP chưa được chứng minh là profile local. Tám tool MCP hiện có gồm `run_script`, `get_tasks`, `get_presigned_url`, `list_regions`, `get_regional_availability`, `search_documentation`, `read_documentation` và `retrieve_skill`.

`freetier:GetAccountPlanState` trả `FREE / ACTIVE`, **119,999863 USD** credits còn lại và thời điểm hết hạn plan **18/04/2027 lúc 18:25 giờ Việt Nam**. Plan cũng kết thúc nếu credits hết trước ngày đó. `billing:GetCredits` trả `AccessDeniedException` với thông báo `IAM user access not activated`. Chủ tài khoản có thể đối chiếu hạn từng khoản trong mục Credits. `GetFreeTierUsage` cũng đọc được. Cost Explorer trả UnblendedCost ước tính **0 USD** cho khoảng 01–23/11 với ngày kết thúc loại trừ. Đã thấy budget `WebSentinel-Monthly-Budget` **25 USD/tháng**, có ngưỡng actual 85%/100% và forecast 100%. Budget là cảnh báo, mức dừng vận hành do timer và lịch stop kiểm soát. [Free Tier API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_freetier_GetAccountPlanState.html) · [GetCredits API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_billing_GetCredits.html) · [Free và Paid Plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)

## EC2 và quyền đã kiểm

- `DescribeInstanceTypes` trả `m7i-flex.large` có 2 vCPU, 8 GiB, x86-64 và `FreeTierEligible=true`. `DescribeInstanceTypeOfferings` trả cả `ap-southeast-1a`, `1b`, `1c`. AWS công bố baseline 40% mỗi vCPU cho dòng này. R45 cần đo hiệu năng ở tải staging. [M7i-flex](https://aws.amazon.com/ec2/instance-types/m7i/) · [EC2 Free Tier](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- `DescribeImages` với owner Canonical `099720109477`, trạng thái available, HVM, x86-64 và bộ lọc Free Tier trả AMI phù hợp `ami-00094c315dd37d160`, Ubuntu Server 26.04 Resolute amd64 `20261120`, root `/dev/sda1` gp3 8 GiB trước override. Public parameter Canonical trả `AccessDenied` cho `ssm:GetParameter`. Discovery bằng EC2 đã xác minh được AMI để pin. [Xác minh owner AMI Canonical](https://documentation.ubuntu.com/aws/aws-how-to/instances/launch-ubuntu-ec2-instance/)
- VPC mặc định `vpc-08a0a47f1053cd88a` có ba subnet mặc định với public IPv4, route `0.0.0.0/0` qua IGW và một default security group. `RunInstances` với subnet `subnet-0f8467d7317cc7205` ở 1a, AMI đã pin, tag `Project=WebSentinel`, gp3 mã hóa 40 GiB, IMDSv2 và instance profile đã trả **DryRunOperation**. Default security group chỉ dùng trong probe IAM. Deploy dùng group chuyên biệt. DryRun xác nhận quyền trên request thử và dung lượng tại AZ vẫn phụ thuộc lúc cấp phát.
- `GetServiceQuota` cho On-Demand Standard vCPU `L-1216C47A` bị từ chối. Cần giá trị applied quota và ít nhất 2 vCPU khả dụng. `DescribeAccountAttributes` có trường `max-instances` cũ với ngữ nghĩa riêng. [EC2 quotas](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)

| Phạm vi | Đã xác minh | Còn thiếu |
|---|---|---|
| EC2 | DescribeInstances và RunInstances DryRun đạt. | `StartInstances`, `StopInstances`, `RebootInstances`, `TerminateInstances` cho instance đã gắn tag. Tài khoản chưa có instance để thử DryRun trên ID thực. |
| VPC/subnet/IGW/SG | Describe thành công. CreateVpc, CreateSubnet, CreateInternetGateway, AttachInternetGateway, CreateSecurityGroup và AuthorizeSecurityGroupIngress/Egress đều trả DryRunOperation. | R45 dùng VPC và IGW sẵn có. Xác minh giới hạn ingress riêng của staging SG. |
| EBS | DescribeVolumes đạt. 40 GiB gp3 mã hóa nằm trong RunInstances DryRun đã đạt. | `ec2:CreateVolume` độc lập trả UnauthorizedOperation. Snapshot, attach hoặc restore volume riêng cần xác minh nếu dùng. |
| IAM role và instance profile | `GetRole` xác nhận trust `ec2.amazonaws.com`. `GetInstanceProfile` trả profile cùng tên `WebSentinel-Staging-EC2-Role` và đúng role. RunInstances DryRun có profile này đạt. | `iam:PassRole` chưa có kết quả độc lập vì `iam:SimulatePrincipalPolicy` bị từ chối. `iam:ListAttachedRolePolicies` bị từ chối nên attachment **AmazonSSMManagedInstanceCore chưa xác minh**. `ListInstanceProfilesForRole` bị từ chối nhưng profile đích đã đọc được qua GetInstanceProfile. |
| SSM | DescribeInstanceInformation đạt, chưa có managed node. | Attachment của role và `ssm:StartSession`, `TerminateSession` cho operator, sau đó thử kết nối thật. |
| CloudFormation | ListStacks và ValidateTemplate đạt. | Quyền tạo hay thay đổi stack chưa xác minh. Kiến trúc một host có thể triển khai trực tiếp khi R45 được phép. |
| CloudWatch | DescribeLogGroups đạt và chưa có group. | Chưa xác minh quyền ghi log, retention và alarms. Nếu bật log, giới hạn quyền theo log group staging. |
| Billing/Budgets | Free Tier, Cost Explorer, budget và notification đọc được. | Hạn từng khoản credit và quyền chỉnh budget chưa xác minh. |
| EventBridge Scheduler | `scheduler:ListSchedules` trả AccessDeniedException. | Chưa xác minh Create/Update/DeleteSchedule, quyền PassRole cho scheduler và execution role gọi StopInstances. |

`iam:GetContextKeysForPrincipalPolicy`, `iam:SimulatePrincipalPolicy` và các lệnh liệt kê policy của user đều bị từ chối. Vì vậy các quyền chưa có phép thử API an toàn vẫn để **BLOCKED**, kể cả khi API đọc cùng dịch vụ đã đạt. [IAM Policy Simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html) · [SSM prerequisites](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html)

## Ngân sách tháng cho một EC2

USD, trước credit, miễn phí theo usage và thuế. Giá theo AWS Price List Bulk Singapore phiên bản 18–21/11/2026. `pricing:GetProducts` trên account bị từ chối nên dùng catalog công khai. Giới hạn phát sinh trong bảng là giả định vận hành cần giám sát ở R45.

| Hạng mục | Giả định | 120 giờ | 124 giờ |
|---|---|---:|---:|
| EC2 Linux On-Demand | 0,1197 USD/giờ | 14,3640 | 14,8428 |
| gp3 | 40 GiB × 0,096, cả tháng, IOPS/throughput mặc định | 3,8400 | 3,8400 |
| Public IPv4 tự cấp | Một địa chỉ chỉ trong cửa sổ chạy × 0,005 USD/giờ | 0,6000 | 0,6200 |
| CloudWatch Logs | 1 GB ingest Standard và tối đa 1 GB-month lưu trữ, chưa tính Logs Insights | 0,7300 | 0,7300 |
| Snapshot EBS Standard | 10 GB-month snapshot đã tính incremental, 0,05 USD/GB-month | 0,5000 | 0,5000 |
| Data transfer | 5 GB internet egress × 0,12, bảo thủ bỏ qua 100 GB miễn phí dùng chung | 0,6000 | 0,6000 |
| Scheduler | Tối đa 2 invocation/ngày, gross 1,25 USD/triệu | 0,00008 | 0,00008 |
| **Tổng** | | **20,63** | **21,13** |
| **Dự phòng tới 25 USD** | | **4,37** | **3,87** |

Khi dừng EC2, EBS, snapshots và log còn lưu tiếp tục tính tiền. Với dung lượng trong bảng, phần lưu trữ duy trì khoảng **4,37 USD/tháng**. AWS thu hồi public IPv4 tự cấp khi stop. EIP giữ cả tháng sẽ kéo kịch bản 124 giờ lên **24,23 USD** trước thuế, làm giảm dự phòng. Khi snapshot lưu đủ 40 GB-month, kịch bản không EIP lên **22,63 USD** trước thuế. Ví dụ thuế 10% đưa kịch bản cơ sở 124 giờ lên **23,25 USD**. Mức thuế thực tế và các workload ngoài WebSentinel cần đối chiếu Billing. [EC2/EBS SKU Singapore](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-southeast-1/index.csv) · [CloudWatch SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ap-southeast-1/index.json) · [Data transfer SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDataTransfer/current/ap-southeast-1/index.json) · [Scheduler SKU](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSEvents/current/ap-southeast-1/index.csv) · [Public IPv4](https://aws.amazon.com/vpc/pricing/) · [Chi phí khi stop](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html)

## AI-IDPS và đề xuất R45

Giữ stack systemd trên một EC2. NGINX HTTPS phát trusted request ID. Suricata Lua/AF_PACKET quan sát leg HTTP nội bộ cùng kernel. Student Web xuất Audit JSONL đã lọc. Rust giữ cursor, correlation và Hybrid post-observation. PostgreSQL 18 cùng máy, bind loopback và tách role sau khi đối chiếu bootstrap. R37 URI100 và R36 rollback đã đối chiếu SHA với registry của R42. Giữ AI auto-ban OFF và C2 đóng. Bằng chứng 15 request R42 áp dụng cho Local. AWS còn cần xác minh TLS/SAN, điểm capture, latency, cutoff 1.000 ms, guard 1 ms, ABSTAIN, backup và rollback trên đúng host. [R42 Local](126_T09_R42_FINAL_LOCAL_HANDOFF.md) · [Registry](../ai-training/contracts/quality-freeze-r37/slots.json) · [AWS handoff](127_T09_AWS_MIGRATION_HANDOFF.md) · [R43](128_T09_R43_SAFE_PROJECT_CLEANUP.md) · [Chỉ mục](PROJECT_INDEX.md)

**AWS Resource Safety Profile đề xuất, chưa phê duyệt.** `hardware_snapshot()` hiện yêu cầu `coretemp` package/core và allowlist Intel Core Ultra 9 285H. M7i-flex dùng Intel Xeon và cảm biến nhiệt CPU vật lý trong guest chưa được kiểm chứng. Installer gọi đúng hardware preflight này trước khi cài. Cứ giữ scorer ở fail-closed khi thiếu telemetry được contract chấp nhận. Một profile cloud có phiên bản riêng cần xác minh danh tính guest EC2, cgroup v2 và ownership bằng kernel readback, giám sát PSI/OOM, watchdog, disk/log bounds và EC2 status checks. Status checks và CPU metrics không đo nhiệt vật lý. Đề xuất giới hạn tải app toàn slice 150% CPU và 6 GiB RAM cho host 2 vCPU/8 GiB. Điểm bắt đầu cho scorer là 50% CPU, RAM 512 MiB, swap 0, finite PIDs và watchdog 3 giây. Lỗi telemetry, readback, OOM hoặc watchdog phải chuyển trạng thái an toàn, dừng workload phù hợp và giữ ABSTAIN khi scorer unavailable. Tách profile cloud khỏi ngưỡng 90/100°C của host vật lý. Nếu contract vẫn yêu cầu cảm biến vật lý đáng tin, EC2 này tiếp tục BLOCKED cho scorer.

**Checklist trước khi khởi chạy R45**

1. Đọc applied quota và xác nhận tối thiểu 2 vCPU On-Demand Standard còn khả dụng. Xác minh `AmazonSSMManagedInstanceCore` trên role hoặc quyền tương đương, quyền operator và quyền stop/terminate được giới hạn theo `Project=WebSentinel`. Có thể nhờ IAM admin xuất đúng các kết quả đọc/simulation thay cho cấp quyền IAM rộng.
2. Chốt profile an toàn cloud và kiểm điều kiện fail-closed trước khi bật AI. Pin AMI, dùng một gp3 40 GiB mã hóa, IMDSv2, một public IPv4 tự cấp cho kết nối outbound, máy dùng systemd. Dùng SG chuyên biệt mặc định không ingress, không mở SSH/DB. Dùng SSM port forwarding tới HTTPS nội bộ và chứng thư phù hợp. Giữ egress HTTPS cho SSM và nguồn package đã duyệt. [SSM Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
3. Kiểm tra một systemd timer đưa instance về `stopped` sau tối đa 4 giờ và graceful PostgreSQL shutdown. Thời hạn cần giữ theo phiên qua reboot. Khi đã xác minh quyền Scheduler, thêm one-shot stop độc lập theo instance ID qua execution role riêng, retry hữu hạn. Start thủ công trong pilot. Áp giới hạn 124 giờ/tháng, log retention ngắn và đo dung lượng snapshot thực. Cấu hình dự toán loại NAT Gateway, ALB, RDS, EIP và Docker. [Scheduler one-time](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html) · [Scheduler target](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html)
4. Sau khi được phép launch, dùng một vòng nghiệm thu giới hạn để kiểm SSM, app, TLS, ledger ba nguồn, scorer và quota kernel, backup/restore, rồi kiểm readback instance `stopped`. Giữ T07 production và AI auto-ban theo trạng thái R42.
