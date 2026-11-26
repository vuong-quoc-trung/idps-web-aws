# R61 — Kích hoạt Prevention canary và chốt phạm vi bàn giao

**R61_FINAL_COMPLETION = PARTIAL.** Đã chạy Rule-based Automatic
Prevention và Hybrid Adaptive Prevention trên EC2 trong namespace C2
riêng. Dashboard public vẫn phản ánh trạng thái chặn công khai **OFF**.
EC2 giữ cấu hình giám sát đang phục vụ. [Bằng chứng R60](146_T09_R60_FINAL_PROJECT_COMPLETION.md)

## Tích hợp ingress vào Rust Hybrid

C2 trước đây chỉ cấp quyền manual. Suricata post-proxy quan sát socket
loopback của NGINX, nên địa chỉ trên EVE không dùng làm IP đích của
actuator. R61 bổ sung capability canary riêng cho build `isolated-c2`.
Capability phải có đúng file chấp thuận do root sở hữu, IPC thuộc root,
và network namespace tách host. Rust đối chiếu đúng một quan sát NGINX
còn mới với bằng chứng socket và transaction qua IPC. Request ID chỉ
tra cứu bản ghi. Actuator kiểm lại quy tắc, phạm vi và socket còn sống
ngay trước khi đặt lease. Trần TTL tự động là 6 giây. Lease chỉ tác động
peer `10.254.56.2` qua `r56-edge` tới `10.254.56.1:18456/tcp`.
[Đối chiếu Rust](../security-web/src/c2_ingress.rs) · [Actuator](../security-web/deploy/aws-r48/r56_prevention_lab.py)

Hybrid lưu bằng chứng vào incident và đưa lệnh canary vào hàng đợi trong
cùng transaction. Hai nguồn thao tác `CANARY_RULE` và `CANARY_HYBRID`
được ghi trong audit. Worker đọc lại nftables trước khi xác nhận thành
công. Các đường manual và canary dùng chung cooldown 30 giây, kiểm protected
targets, RBAC và kernel readback. AI R37 tiếp tục Advisory. Điểm và ngưỡng AI
không tham gia quyết định chặn. [Hybrid](../security-web/src/hybrid.rs) · [Hàng đợi và readback](../security-web/src/firewall.rs)

## Kết quả chạy EC2

Canary chạy trên instance `i-0b6f2e4f3ed32f514`, invocation
`8740626a84f94ba681a75913205f1938`. Unit thoát mã 0 sau 52,969 giây,
dùng 3,050 giây CPU và 179,1 MiB RAM đỉnh. Lượt đầu không tạo action
vì hai URL thử nghiệm bị redaction. Bản sửa dùng các route đã nằm
trong danh mục bảo vệ dữ liệu và giữ nguyên bộ redaction.

| Ca kiểm thử | Kết quả quan sát |
|---|---|
| Rule `/health`, HTTP 204 | `daf524ab80a16a3ed81672d7b6014f31` tạo action 1. Có packet drop thật. Admin Unblock bằng action 2 và kết nối phục hồi. |
| Hybrid `/api/profile`, HTTP 403 | `fa3af2ddc0b33586383626288c5b6530` tạo action 3. Kết hợp đúng alert Suricata, socket ingress và kết quả từ chối session của ứng dụng lab. Kết nối phục hồi sau TTL. |
| Rule có alert nhưng thiếu attestation | `25249309f6b72472bf64f395e19a450d` không tạo action. |
| Cùng URL `/api/profile` và SID nhưng session hợp lệ, HTTP 204 | `a5facc1fe26641b893797f4984f9301d` không tạo action. |
| Restart và cleanup | Restart Rust không phát lại action. Ba action thành công, DB và kernel cùng về rỗng. Từ chối tiếp nhận yêu cầu khi actuator offline. Unit, socket, cgroup và tệp tạm đã được dọn. |

Bản build cùng SHA cũng chạy lại Manual Block/Unblock và TTL trong
invocation `32b8e2c133634e8dab9e7aa1aa1362e8`. Ba action thành công.
Một yêu cầu thiếu attestation ghi ERROR và không tạo lease. Restart khi
lease đang hoạt động giữ nguyên trạng thái kernel và audit.

Backend canary là một ứng dụng HTTP riêng, có kiểm tra session để phát
bằng chứng từ chối độc lập với URI. Kiểm thử public dùng Student Web
thật. Request lành tính `37a7a368aeeb37f4abbff6b432f37acb` có NGINX,
Suricata, Student Audit, một incident `LOG_ONLY` và AI `SCORED` sau
2,154 ms. Dashboard đã đăng nhập hiển thị SSE **Đã kết nối**.
[Bằng chứng máy đọc](evidence/r61/acceptance.json)

## Trạng thái bàn giao

| Thành phần | Trạng thái R61 |
|---|---|
| NGINX, Suricata, Student Audit | **ACTIVE AWS**. Cả ba cùng request public đã đối soát. |
| AI Advisory, Correlator, Hybrid | **ACTIVE AWS**. R37 URI100 và threshold `0.7664756774902344` giữ nguyên. |
| Firewall Actuator và nftables | **PASS canary**. Public **OFF**. |
| Manual Block/Unblock và TTL | **PASS lab**. Admin thao tác với kernel thật, Viewer nhận 403. |
| Rule-based Automatic Prevention | **PASS canary** trong phạm vi một peer, một listener và một SID thử nghiệm. |
| Hybrid Adaptive Prevention | **PASS canary** với bằng chứng từ ứng dụng lab. |
| DB/Audit/Firewall | **VERIFIED & SYNCED canary**. Public **UNVERIFIED**, 0 action và 0 lease. |
| SSE | **CONNECTED AWS** trên Dashboard đang phục vụ. |
| AWS Deployment | **PASS canary**. 7 unit public active, EC2 Running và 3/3 status check. Binary serving giữ nguyên. |
| Git Push | Commit kỹ thuật `87f19a1` và commit tài liệu trên nhánh tích hợp hiện có. [Nhánh remote](https://github.com/vuong-quoc-trung/idps-web-aws/tree/feature/ai-idps-https-ml-integration) |

Hai kiểm thử Rust, chín kiểm thử Python và kiểm cú pháp Bash đạt.

Trạng thái công khai chưa đủ điều kiện bật. Capability canary chỉ có thể
thực thi trong namespace lab. Gateway public vẫn thiếu nguồn attestation
cho đúng worker NGINX đang phục vụ, ràng buộc socket với request trên kết
nối tái sử dụng, cùng một peer công khai được xác minh dành riêng để đo
phạm vi và rollback. Vì vậy chưa có bằng chứng quyền thực thi và đồng bộ
đối với public. Chốt mã và evidence trong phạm vi đã đạt, giữ AI Advisory
và không triển khai thay đổi lên binary đang phục vụ.
