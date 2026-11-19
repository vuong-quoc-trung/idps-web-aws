> Cập nhật phạm vi: AI Worker là **DEFERRED**, không chặn HTTPS/Suricata.
> Dùng `--ai-mode deferred`; xem [AI-DEFERRED.md](AI-DEFERRED.md). Các yêu cầu
> phục hồi AI baseline bên dưới thuộc checklist cũ, chỉ áp dụng khi bật AI lại.

# Giai đoạn C — candidate review, KHÔNG apply

B hiện xác nhận tại VM: HTTPS / trả 200, /api/auth/me trả401 chưa đăng nhập,
certificate IP SAN 192.168.20.10 được CA xác minh. Chưa có kết quả TLS từ Defender,
assets/HMR/browser và login lab. Đây là pre-deployment gates, không được bỏ qua.

## Các lệnh operator còn cần chạy

VM (chỉ certificate public):

```bash
openssl x509 -in "$HOME/ws-student-lab-pki/student.crt" -noout -dates -ext subjectAltName
sha256sum "$HOME/ws-student-lab-pki/ca.crt"
```

Trên Defender, copy public CA bằng SCP với tài khoản lab của bạn, không copy key:

```bash
mkdir -p "$HOME/ws-student-trust"
scp USER@192.168.20.10:ws-student-lab-pki/ca.crt "$HOME/ws-student-trust/ca.crt"
sha256sum "$HOME/ws-student-trust/ca.crt"
bash student-web/deploy/tls/verify-from-defender.sh "$HOME/ws-student-trust/ca.crt"
```

So sánh checksum hai đầu. Nếu DNS SAN student.lab thực sự có, thêm `student.lab`
làm argument thứ hai để kiểm tra cả DNS SAN. Với IP-only, không tuyên bố DNS check
PASS. Egress candidate dùng tên student.lab: cần chứng chỉ có DNS SAN này trước khi
áp dụng và kiểm thử NGINX upstream thật (không suy rộng từ curl verify-IP).
Không dùng proxy_ssl_verify off, curl -k hoặc sửa DNS để lách certificate mismatch.

Browser: tin CA lab đúng, mở HTTPS /, kiểm tra assets/network console, đăng nhập
và logout tài khoản lab, API me theo role, WebSocket nếu dùng. Đối chiếu request ID,
client IP/Audit, không gửi password/cookie ra report. Chưa bật Secure cookie/đổi
Spring profile tùy tiện trong bước C; kiểm tra hành vi session hiện tại riêng.

## Candidate NGINX có proof

prepare-proof-egress.py tái dùng renderer Edge/Egress và njs đã test. Không có
mock/fault injection, không thêm telemetry Egress. Nonce storage fail-closed;
header proof được Edge ghi đè, Egress xác minh, bỏ trước Student; receipt bị Edge
ẩn. sync-nginx-edge cũ từ chối site có proof thay vì vô tình xóa nó.

Ví dụ render (GID991 chỉ minh họa, phải chọn UID/GID dành riêng sau audit):

```bash
python3 security-web/scripts/prepare-proof-egress.py \
  --cert /etc/nginx/pbl4-tls/lab.crt --key /etc/nginx/pbl4-tls/lab.key \
  --ca /etc/nginx/student-ca/ca.crt --tls-name student.lab \
  --js /etc/nginx/proof/proof.js --keyfile /etc/nginx/proof/key.json \
  --gid 991 --output /tmp/ws-proof-review
python3 security-web/scripts/prepare-suricata-post-proxy.py \
  --profile local-egress --base /etc/suricata/pbl4/post-proxy.yaml \
  --output /tmp/ws-local-egress-review
```

Outputs REVIEW_ONLY: không tự cài njs, tạo user/key hoặc reload. Đừng copy vào /etc
ngay: renderer này chưa nối lifecycle epoch/guard vào script apply. Cần cài module
ABI phù hợp, cấp UID riêng, quyền key/parent root:group, socket AI, logs/temp; xác
minh guard/lifecycle bằng harness trước. Restart phải rotate epoch/key trước khi
nghe, reload chỉ giữ epoch khi shared nonce state được giữ. Không phát hành cấu
hình egress thiếu proof như phương án thay thế.

Hai output context: pbl4-http.conf nằm trong http; pbl4-proxy chứa hai server.
load_module cần main context, không được đặt trong http. Chỉ syntax-check sau khi
module, path và khóa staging đã được chuẩn bị trong môi trường cô lập. Trước apply
thật phải nginx -t trên bản cấu hình đầy đủ; stage hiện chưa tuyên bố check này đạt.

## Suricata, Rust Shadow và các phần chưa triển khai

Profile local-egress đã có; chưa tự chuyển service. Lua phải xuất file riêng theo
sensor generation+flow_id+tx_id, không dump headers/body và không ghi đè eve.json.
Logger cùng vòng đời sensor và key history là điều kiện triển khai, chưa có apply.

Rust verifier vẫn cfg(test). Giai đoạn D cần adapter riêng bật opt-in, bounded
buffer, xử lý trùng/đến trễ/mâu thuẫn và diagnostic Shadow. Không dùng giá trị
response_complete do harness gán như dữ liệu runtime. Khi thiếu nguồn hoàn chỉnh:
Unverified. Không sửa attribution, không đưa shadow evidence vào AUTO_BLOCK.
Chưa có API/DB mapping đã nghiệm thu; không tự migration hoặc hứa Dashboard đã
hiển thị proof. Việc nối runtime vẫn chưa thực hiện trong lần chuẩn bị này.

## Triển khai/rollback độc lập — chỉ sau phê duyệt

1. Backup root-only site+includes+cert paths, Suricata YAML/drop-in và trạng thái
   nft/UID/service; giữ HTTP Student80. Giữ backup immutable ngoài repo.
2. Nghiệm thu TLS Student từ Host trước; nếu fail, không đổi Defender.
3. Staging đầy đủ proof+lifecycle; health HTTPS Edge và API, XFF/RID/Audit/AI một
   event/request. Không chuyển sensor trước khi đường truyền mới đạt.
4. Sau đó đổi sensor profile, suricata -T với đúng rules trước restart; nghiệm thu
   SQLi/XSS/traversal, không duplicate. Không chạy hai sensor trùng logfile.
5. Shadow runtime là bước riêng; feature flag OFF phục hồi ingestion cũ.

Rollback site/includes từ backup HTTPS Edge -> HTTP192.168.20.10:80, nginx -t rồi
operator reload; khôi phục Suricata vmnet3 YAML/drop-in, suricata -T rồi restart.
Chỉ tháo bảng guard chuyên biệt khi không còn local listener phụ thuộc; không flush
ruleset. Không rollback database; không xóa audit. Checklist/backup xem READINESS.md.

Runtime readiness vẫn NOT_ACCEPTED: timing, journal rollback/revocation,
completion provenance và mid-body abort chưa giải quyết. Cùng UID NGINX/root
compromise nằm trong trust boundary. Candidate là phần chuẩn bị, không tuyên bố
proof production hay Rust Shadow đã triển khai xong.

## Candidate runtime acceptance update

Operator confirms Defender->Student HTTPS FE200/API401, IP and student.lab SAN,
wrong CA/hostname rejection. This supersedes the earlier missing TLS gate; full
browser assets/login acceptance is separate unless explicitly reported.

`test-proof-candidate-runtime.py` renders the actual candidate, reusing TLS mock
and temporary certificates/ports from existing fixtures. Changes to fixture are
only addresses/ports, telemetry sink and 0600 key mode for a non-root process.
It does not install njs, modify /etc or contact Student VM. Root-owned group mode
and UID/cgroup policy still require the separate privileged harness.

Non-root command (existing extracted module):

```bash
python3 security-web/scripts/test-proof-candidate-runtime.py \
  --module /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so
```

Checks: actual nginx -t/start; HTTP+HTTPS through candidate; upstream TLS success,
wrong-name and unrelated-CA failure; generated request ID/XFF preserved; proof and
receipt stripped; exactly one AI telemetry per baseline request; direct Egress
without proof denied; sensitive paths/method/body limits; bounded burst429; missing
HMAC key denied without upstream request. Test accepts documented rejection HTTP
403 or server error for missing key, not an arbitrary response.

HTTP listener is preserved but BOTH HTTP and HTTPS currently traverse Egress.
It is not an independent live HTTP bypass if Egress fails. Rollback to the prior
Edge->HTTP VM site is the actual fallback. Do not misrepresent port80 as independent
availability protection. The live harness now calls prepare-proof-egress.render directly;
its prior 72-transaction result does NOT certify this newly wired candidate. Combined
candidate+capture+guard acceptance must be repeated before production cutover.

## Operator gates and controlled cutover plan (NOT executable approval)

1. Preserve root-only snapshots of current site/includes, NGINX unit+drop-ins,
   Suricata YAML+drop-in, package versions and relevant guard state. Never flush
   firewall. Verify backup can be read and original syntax passes.
2. Stage candidate OUTSIDE /etc with confirmed student.lab CA; inspect diff,
   reserve dedicated UID/GID, validate all existing NGINX sites and AI socket access.
   njs ABI installation, UID provisioning and key permissions require operator sudo.
3. Root-managed key generation/epoch rotation and nft UID+cgroup lifecycle must be
   reviewed and installed together. Current renderer does not supply an atomic
   production lifecycle installer: DO NOT use manual reload as a substitute.
4. Run isolated privileged harness first:

```bash
bash security-web/scripts/run-live-transaction-proof.sh \
  /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so --extended
```

This is sudo for a temporary cgroup+namespace only. It is not production deployment.
Re-run against the final candidate integration before approving cutover.
5. In a separately approved deployment window: nginx -t against fully staged
   effective configuration before any reload; verify FE/API/login/Audit/RID/XFF,
   HMAC failure rejection and one telemetry event per request. Suricata stays on
   vmnet3 until the data path passes. Then validate local-egress with suricata -T
   and switch capture, single process/single log owner. No runtime Verified.
6. Rollback independently: restore original NGINX site/includes and syntax-check
   then reload; restore Suricata post-proxy unit/YAML and syntax-check then restart.
   Keep TLS Student443 and HTTP80 available; no Student/DB rollback needed. Remove
   only the dedicated guard after no local-egress traffic relies on it. Healthcheck
   against saved baseline. If nginx -t fails do not reload; report exact error.

No unconditional production apply command is provided while lifecycle and exact
candidate combined acceptance remain missing. Existing sync --apply is NOT the
proof-aware deployment path and intentionally refuses proof-enabled site updates.
Timing, journal rollback/revocation, runtime response completeness and Rust Shadow
mapping remain NOT_ACCEPTED. Do not infer Verified readiness from these TLS tests.


## Integrated candidate acceptance — current revision

The existing live harness now uses the deployment renderer for all Edge/Egress
proof and routing directives. Only fixture addresses/ports, key paths, telemetry
sink and the explicit `/api/no-receipt` fault overlay differ. `candidate_sha256`
identifies the rendered temporary configuration before that fault overlay; it is
not the hash of a production configuration. Keepalive is now supplied by the
renderer itself, rather than an extra harness-only upstream.

The extended run requires **15 PASS cases** (previously 14). The additional case
`ai_telemetry_unique` checks exactly one telemetry record per captured legitimate
or response-fault request. A missing case remains NOT_RUN and prevents total PASS.
Three custom SID counts must each equal one; duplicate HTTP flow/transaction
observations are rejected. Telemetry is captured to a temporary file: this tests
NGINX emission, not delivery to a running AI Worker.

Current non-root acceptance: candidate NGINX/njs runtime checks PASS; 3 renderer,
10 input/result-gate and 7 guard lifecycle unit tests PASS. Combined privileged
candidate execution is **NOT_RUN** by the assistant. Run the extended command above
as your normal user; the wrapper requests sudo for its temporary namespace and
cgroup only. Check `renderer`, `candidate_sha256`, 15 case statuses and empty pending.
Do not transfer PASS from the old fixture run to this candidate.

### Lifecycle contract before a production installer is approved

- Provision an exclusive NGINX UID/GID, no login or unrelated processes. Check all
  existing sites, log/cache paths and AI socket permissions under that identity.
  Root owns key directory (0750) and key (0640, dedicated group); workers only read.
  Same-UID compromise and root compromise remain inside the trust boundary.
- Startup/restart/crash recovery: keep local egress denied, stop all old workers,
  generate fresh random key AND epoch, write a private temporary file, fsync and
  atomically rename, then fsync the parent. Never restore a backed-up active key
  after loss of replay state. Validate key ownership/schema and full NGINX syntax.
- Grant guard only to the observed dedicated worker UID and actual service cgroup;
  validate exact policy before admitting traffic. Missing/invalid key or nonce
  storage must deny at Egress. Guard loss triggers stop and deny-only restoration;
  detection is not instantaneous. HMAC rejection is the independent fallback for
  unprivileged fake traffic during that interval, not protection against root.
- Reload: preserve shared nonce state and key/epoch only when that preservation is
  proven; otherwise use the controlled stop/rotate/start sequence. A UID/cgroup
  change requires revoke, revalidation and regrant; do not reuse stale readiness.
- A failed health check keeps the candidate closed or restores the old site. Back
  up configuration and permissions, not reusable replay epochs. Do not apply the
  rendered site by itself: a production lifecycle installer is still missing.

### Rust Shadow follow-up (not enabled)

Use a separate evidence stream with sensor generation and flow_id/tx_id; retain
native alerts when proof is absent or contradictory. Shadow verdicts must not
change client attribution, block decisions or AUTO_BLOCK. Runtime integration is
still gated by journal rollback/revocation, trusted response-completion provenance
and timing review. The header-abort test is not evidence for all mid-body aborts.
Keep local-egress Verified disabled even if all 15 harness cases pass.

## Controlled deployment tooling follow-up

Operator now reports the renderer-backed extended run passed 15/15, 72 transactions,
with candidate hash c74cfc07bc6425f537dd0bc5c67f4eb27debc9b62b9cc4a2af23a43305b7df18.
The previous NOT_RUN note describes the earlier assistant run, not this new operator
result. See HOST-DEPLOYMENT.md for the new staged bundle, lifecycle supervisor,
transactional apply/rollback and explicit approval gates. The installer has only
filesystem/mocked-service acceptance so far; privileged systemd lifecycle acceptance
is still pending. Runtime Verified remains NOT_ACCEPTED.
