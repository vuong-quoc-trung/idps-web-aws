# R60 — Xác minh danh tính tại ingress và nghiệm thu Prevention

**R60_FINAL_COMPLETION = PARTIAL**

## Nguyên nhân và giải pháp

Trên EC2, NGINX kết thúc TLS. Suricata đọc HTTP trên kết nối mới từ
NGINX đến backend qua loopback. Địa chỉ TCP trên nhánh đó thuộc proxy.
Request ID liên kết được các bản ghi HTTP, nhưng không ràng buộc địa chỉ
nguồn với socket mà kernel sẽ áp dụng lease. Vì vậy Hybrid để trống
`trusted_client_ip` cho pipeline loopback. [Bằng chứng R59](145_T09_R59_FINAL_PROJECT_COMPLETION.md)

R60 bổ sung bộ xác minh trong namespace C2. Trước khi phát GET, bộ quan
sát đọc tuple TCP của socket `ESTABLISHED` thuộc tiến trình NGINX. Sau
HTTP 204, nó đối chiếu cùng tuple và inode với nhật ký NGINX do root
quản lý. Request ID do NGINX tạo chỉ nối bản ghi HTTP. Trên nhánh HTTP
backend, bộ kiểm thử đối chiếu socket nhận request của ứng dụng thử
với một EVE HTTP transaction và một alert có cùng `flow_id` và `tx_id`.
Người gửi có thể đặt header, nhưng không chọn được IP mà actuator dùng.
Actuator đọc lại socket còn tồn tại và kiểm hạn của bằng chứng ngay
trước khi thực hiện BLOCK. [Bộ xác minh](../security-web/deploy/aws-r48/r60_ingress.py)

C2 yêu cầu `OFF` khi Rust ingest dữ liệu Suricata post-proxy. Lượt tích
hợp ban đầu bị từ chối đúng guard này. Bản chạy R60 giữ Rust Prevention
ở C2 `MANUAL` với feed sensor rỗng. Bộ xác minh lab đọc EVE thật ở nhánh
loopback ngoài đường ingest. C2 nhận lệnh từ actor đã được xác minh bằng
Unix peer credentials và chỉ áp dụng cho `10.254.56.2` trên `r56-edge`,
đích `10.254.56.1:18456/tcp`. [Runner C2](../security-web/deploy/aws-r48/r56_prevention_lab.py)

Namespace riêng có đúng loopback và veth, không có default route. IP
được xác minh là peer TCP trực tiếp. Cùng cơ chế trong mạng qua NAT
chỉ xác minh được địa chỉ peer sau NAT; cần đánh giá tác động lên các
client dùng chung IP trước khi cấp quyền chặn ở một scope công khai.

## Điều kiện T07 và phạm vi public

R37 HistGradientBoosting URI100 giữ SHA `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`
và ngưỡng `0.7664756774902344`. WAF development holdout có recall
**86,04%**, FPR **0,41%**, với cận trên bootstrap 95% của FPR là
**1,55%**. SR-BH TUNING có recall **70,93%**, FPR **2,07%**. T07 cần
TEST native hai lớp, tối thiểu 100 mẫu dương và 20 cụm dương độc lập
cho recall, cùng đánh giá false block riêng với cận trên 0,1%. Ngay cả
khi không có false block, một endpoint cần 2.995 benign exposure package
độc lập để chứng minh cận đó. R60 không có cohort TEST phù hợp hoặc
quyền mở sealed TEST. **AI Independent Quality = BLOCKED**. R37 tiếp tục
Advisory và AI Auto-ban giữ OFF. [Chỉ số R37](121_T09_R37_FINAL_AI_QUALITY_AND_MODEL_FREEZE.md) · [Giao thức T07](../ai-training/contracts/evaluation-v1/protocol.json)

Bằng chứng ingress là bước đầu cho triển khai public. Còn cần liên kết
attestation với transaction đã xác minh trong Rust, cấp capability C2
riêng cho phạm vi được duyệt, và kiểm thử canary với tiêu chí false
block, protected targets và rollback đã khóa. Phiên này chỉ sử dụng
EC2 đã có và không thay phần phục vụ công khai.

## Nghiệm thu thực tế trên EC2

Unit `websentinel-r56-prevention.service`, invocation
`07f22fa6801b4c00aaa645714b5f2459`, thoát mã **0**. Hai GET 204 phát
sinh request ID `340ebb4332ceab979ecc47efc32d0b7d` và
`0ec2e849c54149d5ac58ccca2a1633e3`. Hai socket ingress có inode
`722990` và `723335`. Mỗi request khớp đúng một transaction và một alert
marker SID 156001 trên nhánh backend. Backend là HTTP probe riêng.
Ba nguồn có Student Audit và AI trên hệ thống hiện hành đã được kiểm
ở R59. [Evidence máy đọc](evidence/r60/acceptance.json)

| Gate | Kết quả | Bằng chứng |
|---|---|---|
| Client Identity Verification | PASS lab | Hai tuple và inode còn sống khớp với NGINX. Header do test client gửi bị ghi đè. Block trước khi có proof bị actuator từ chối. |
| Enforcement Scope Verification | PASS lab | Một peer, một interface và một đích TCP. Từ chối IP server. API trả 401 khi thiếu xác thực, 403 với Viewer. |
| Firewall Actuator | PASS lab | Kiểm tra peer credentials và kernel readback. Báo `UNVERIFIED` khi actuator offline. |
| Manual Prevention E2E | PASS lab | API Rust thật và PostgreSQL riêng ghi ba thao tác thành công. Kết nối TLS mới bị chặn khi có lease và thành công sau Unblock. |
| Rule-based Prevention | PARTIAL | Hai alert Suricata thật, mỗi transaction một alert. C2 hiện chỉ cấp quyền manual, chưa kiểm chứng `AUTO` tạo lease. |
| Hybrid Adaptive Prevention | BLOCKED | Proof ingress chưa được Rust Hybrid tiếp nhận. Advisory giữ nguyên. Chưa có capability thực thi thích ứng. |
| Block/Unblock/TTL | PASS lab | Block `2`, Unblock `3`, lease `4` Time-to-Live 6 giây. Có packet drop, tự hết hạn và kết nối lại thành công. |
| DB/Audit/Kernel Consistency | PASS lab | `3 SUCCESS`, `1 ERROR` đúng các yêu cầu. DB và kernel cùng có lease lúc Block, cùng rỗng sau TTL. |
| Restart/Recovery/Rollback | PASS lab | Restart Rust khi lease hoạt động giữ được kernel và audit. Unblock khôi phục truy cập. Unit, cgroup, socket, table và scratch đều được dọn. |
| Public Enforcement Readiness | BLOCKED / OFF | Chưa có quyền cho phạm vi public và chưa có kiểm thử đường attestation công khai. DB public có 0 tác vụ và 0 lease. |
| AI Independent Quality | BLOCKED | Thiếu CAL/TEST native độc lập theo T07. AI Auto-ban OFF. |
| AWS Deployment | PASS lab | Chạy bundle SHA-pinned trên EC2 hiện có. Bảy service public active, hai HTTPS 200 với TLS verify thành công. Binary và model serving giữ nguyên. EC2 running, status checks 3/3. |
| Git Delivery | Hai nhóm thay đổi | Commit kỹ thuật `38d8242` và commit tài liệu/evidence. [Nhánh tích hợp](https://github.com/vuong-quoc-trung/idps-web-aws/tree/feature/ai-idps-https-ml-integration) |

Chín kiểm thử Python và kiểm cú pháp Bash đạt. Ba lượt chuẩn bị làm rõ
thiếu helper, guard post-proxy và cooldown 30 giây áp dụng cả khi BLOCK
bị từ chối. Bundle đã bổ sung helper, giữ guard và đợi đúng cooldown.
Lượt đạt dùng 2,412 giây CPU và peak RAM 168,6 MiB trong 79,435 giây
wall time. Hạn mức lab là một CPU, 512 MiB và 80 task. Không thêm tài
nguyên AWS hay sửa cấu hình firewall public.
