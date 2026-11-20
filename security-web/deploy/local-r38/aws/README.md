# AWS staging handoff

**Phạm vi bàn giao** gồm release scorer, renderer topology có tham số, quy trình restore và CloudFormation cho ranh giới mạng. R38 đã kiểm cấu hình offline. Triển khai EC2/RDS và quyền vận hành trên AWS thuộc lượt staging kế tiếp.

## Topology đề xuất

Một máy ứng dụng Linux x86-64 private chạy edge NGINX, egress TLS, Suricata AF_PACKET, Student và Rust. Dùng địa chỉ private ENI thật cho edge và địa chỉ loopback riêng cho proxy TLS Student. Cách đặt này giữ leg giải mã trong cùng kernel và cho Rust đọc Student Audit qua file chỉ đọc. Không đưa file audit qua mạng bằng RELP plaintext. Tách database và SQL role cho Student và Security trên PostgreSQL private, cưỡng chế TLS và xác minh CA. Nếu tách Student sang instance khác, cần nghiệm thu transport audit có xác thực hai đầu và clock bound riêng trước khi dùng profile đó.

Ước tính ban đầu cho acceptance quy mô nhỏ là 4 vCPU x86, 8 GiB RAM, 40 GiB EBS mã hóa cho ứng dụng và data volume PostgreSQL từ 20 GiB với autoscaling. Đây là giả định sizing để đo lại bằng p95, IOPS, tốc độ log và thời gian lưu. Số đo Local bao gồm H2 và PostgreSQL thử trong cùng namespace tài nguyên. Binary AI pin theo x86-64 Linux. Xác minh dynamic loader, glibc, ORT CPU, NGINX/njs ABI, Suricata với Lua/AF_PACKET, Java, PostgreSQL client, cgroup v2, systemd delegation và ACL trong AMI.

## Hạ tầng và quyền

- [network.yaml](network.yaml) nhận VPC, private tester prefix list, SG DB và SG VPC endpoints. Chỉ mở TCP 443 từ prefix list đến app, TCP 5432 từ app đến PostgreSQL và TCP 443 từ app đến interface endpoints. Xác minh prefix-list membership, route private, security group khác gắn trên ENI, endpoint policy, private DNS và đồng hồ trước chạy. Template không tạo EC2, RDS hay VPC. [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
- Quản trị qua Session Manager với IAM role giới hạn và endpoint đã provision. Bật IMDSv2, giữ instance private và quyền đọc secrets đúng ARN/KMS. Cấp cert/CA cho edge và Student, phân phối khóa theo UID và version. Khóa ký được quản lý trong trust boundary của edge, không đóng gói trong model. Xác minh audit CloudTrail và rotation. [Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html) · [Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- Nạp release theo [hướng dẫn Local](../DEPLOY.md), restore sang DB staging rỗng, xác minh migration và checksum. Dùng môi trường staging cấp SQL credentials riêng và volume mã hóa. Giới hạn CloudWatch vào counters, latency, lỗi và backlog. Giữ dữ liệu nghiệp vụ và token ngoài log tập trung.

## Render từ inventory của staging

Các biến dưới đây lấy từ inventory đích, gồm CA công khai được review, đường dẫn private key trên host và module khớp gói NGINX. `EDGE_IP` phải có trong SAN của cert edge cho health bằng IP. `STUDENT_TLS_NAME` phải khớp SAN upstream. Socket, HMAC và BPF của leg nội bộ giữ nguyên profile Local.

```sh
python3 security-web/scripts/stage-proof-host.py --output "$NEW_BUNDLE" \
  --nginx-base "$NGINX_BASE" --suricata-base "$SENSOR_BASE" \
  --edge-ip "$EDGE_IP" --student-ip "$STUDENT_BIND_IP" --student-tls-name "$STUDENT_TLS_NAME" \
  --edge-cert "$EDGE_CERT" --edge-key "$EDGE_KEY" --edge-ca "$EDGE_CA" --student-ca "$STUDENT_CA" \
  --module "$NJS_MODULE" --gid "$EDGE_GID" --ai-mode enabled --https-ml-shadow
python3 security-web/scripts/deploy-proof-host.py dry-run --bundle "$NEW_BUNDLE" --backup "$NEW_BACKUP"
cfn-lint -t security-web/deploy/local-r38/aws/network.yaml
```

## Điều kiện cho lượt AWS đầu tiên

Kiểm AMI có nguồn cảm biến CPU và hardware alarm hợp lệ cho guardian. Thiếu sensor phải dừng trước khi launch workload. Đo cutoff/clock guard trên host đích, warm/cold percentile và tỷ lệ partial mask. Chạy restore PostgreSQL sang database khác, health từ UID edge, restart scorer, chuyển R36 rồi quay lại R37. Đối chiếu trusted ID qua Rust và Hybrid. Giữ quyền AI ở observation-only. Triển khai AWS còn phụ thuộc AMI/thermal đã kiểm, bộ chứng thư và hai DB/role của môi trường đích, cùng kết quả readiness Local chính thức.
