# Command Oracle sandbox recovery — 2026-11-08

**CASE A — command Oracle VERIFIED cho isolated localhost lab.** Main capture và
Request v3 training **NOT_STARTED**; dataset coverage/fingerprints giữ nguyên.
Baseline `33e0b0d`, integration branch sạch và đồng bộ remote trước thay đổi.

[Machine report](../ai-training/reports/COMMAND_ORACLE_SANDBOX_RECOVERY_20261108.json),
[lab environment addendum](../ai-training/configs/research/command-oracle-sandbox-20261108.json),
[bounded verifier](../ai-training/scripts/verify-command-oracle.py),
[socket probe source](../ai-training/scripts/helpers/icmp-socket-probe.c).

## A. Root cause đã đo trực tiếp

Application PHP worker và command chạy UID/GID **33:33 (`www-data`)**. Namespace
mặc định có `net.ipv4.ping_group_range = 0 0`; GID33 không nằm trong khoảng được phép
mở ICMP datagram sockets. Native probe gọi đúng syscall, không gửi packets:

| Check | Baseline | Lab fix |
|---|---|---|
| `socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)` | EACCES13 | Success |
| Raw ICMP socket | EPERM1 | EPERM1 |
| `ping localhost` CLI exit |2|0|
| Effective/permitted/inheritable/ambient capabilities |0|0|
| Bounding set |`00000000800405fb`|unchanged|
| NoNewPrivs / seccomp mode |1 / 2|unchanged|

Ping binary `/usr/bin/ping` executable0755, root:root, không setuid; capability xattr
trên cùng pinned image là ENODATA61. Binary chạy được, nhưng socket không mở được;
không phải file-execution permission. Loopback UP (`0x9`), namespace khác host.
Ping fallback sang raw socket rồi bị EPERM vì không có quyền raw cần thiết.

Paired probes giữ cùng image/UID/security settings, chỉ đổi namespace group range.
Vì datagram syscall chuyển EACCES→success, không cần giả định CAP_NET_RAW hoặc tháo
security profile để giải thích kết quả. Không cần quyền đọc host audit logs; không
claim đã audit toàn bộ seccomp/AppArmor denials. Rootless runtime hiện báo AppArmor
`unconfined` từ trước, profile không bị thêm/gỡ bởi milestone. Seccomp vẫn mode2.

## B. Minimum lab-only fix

Chỉ trong nhánh DVWA app của existing research launcher:

```text
--sysctl "net.ipv4.ping_group_range=33 33"
```

Không áp dụng cho MariaDB, Juice, Student/Security/Nginx hoặc production. Không
CAP_NET_RAW/cap-add, không privileged container, không thay UID của PHP worker,
không setuid/setcap binary, không nới seccomp/AppArmor hoặc sửa host sysctls/firewall.
Apache master giữ bootstrap identity vốn có của image; actual HTTP PHP worker và
ping được xác minh là33:33, không chạy workflow bằng root để vượt restriction.

Quyền mới chỉ là ICMP datagram cho đúng GID33 trong owned namespace; đây không phải
destination allowlist. Internal lab network, loopback-only published port và inputs
hardcoded localhost giới hạn phạm vi thử nghiệm. Raw socket vẫn bị từ chối sau fix.
Host range trước/sau giữ `0 2147483647`; fresh unmodified namespace sau cleanup vẫn
`0 0`, DGRAM_EACCES/RAW_EPERM. Không có permission change tồn tại ở host hoặc namespace
mới khi bỏ cấu hình opt-in. Không vô hiệu hóa thermal/hardware protections.

## C. Real Oracle verification

Một fresh owned DVWA/MariaDB lab, đúng pinned images trước đây, quota25%onecore mỗi
container. Không gọi main collector/capture. Chỉ2command-workflow HTTP diagnostics,
request IDs mới dưới recovery run; setup/login có counter riêng. Không SQLi/attack
workflow. Setup và login vẫn dùng CSRF token/session bình thường; PHP source không sửa.

| Evidence | Positive localhost | Negative: no authenticated session |
|---|---|---|
| Client / Apache status |200 / 200|302 / 302|
| Packet summary |4transmitted,4received,0%loss|Không có successful summary|
| Namespace ICMP counters |+4outgoing echo,+4incoming reply|0 / 0|
| Request identity |Client ID khớp metadata-only server log|ID riêng, redirect khớp|
| Session |Nested authenticated session vẫn hợp lệ sau test|Không có valid session, auth gate giữ nguyên|
| Outcome |Verified HTTP packet execution|UNKNOWN_SESSION_MISMATCH|

Apache observer tạm thời chỉ ghi requestID/PID/status, không URI/body/cookies; không
thêm endpoint. Actual ping PID ancestry khớp server worker PID của positive request.
Ping/shell/worker effective UID/GID33, CapEff0, NoNewPrivs1. Kernel ICMP MIB snapshots
ở đúng network namespace, không giả packet summary hoặc thay binary; không thu PCAP.
Metadata observer bị xóa cùng lab, không chỉnh application business logic.

**Exit status scope:** separate `proc_open` witness chạy exact argv ping-c4-localhost
bằng33:33 trong cùng namespace có exit0 và coherent4/4summary. DVWA `shell_exec` không
expose child exit trực tiếp; **không claim đã đo exit của chính HTTP-spawned child**.
HTTP proof dùng actual process observation, summary và kernel packet deltas. Diagnostic
verifier tách hai evidence paths; missing exit status trả UNKNOWN, không mặc định0.
Published verifier có pure verdict hardening sau lượt HTTP; numeric replay PASS,
không phát lại HTTP, raw execution report/source snapshot vẫn giữ nguyên.

Actual default-sandbox permission probe là negative control khác: exit2 và socket
errno13/1. Unit fixtures kiểm permission denied, command-not-found127, timeout,
invalid/incoherent/multiple summaries, packet observation thiếu, session mismatch,
application error và missing exit. Mọi failure là UNKNOWN; không suy benign/attack
chỉ từ successful command hoặc HTTP200. Diagnostics không được admit vào dataset.

63targeted Python testsPASS;3actualPHPsession fixturesPASS (authenticated nested,
logged-out nested, reject wrong namespace). Một private helper tên `inspect.py` ban
đầu shadowed stdlib và khiến lượt fixture import lỗi/repeat CLI probes; đã rename,
stdout gốc được giữ, fixtures chạy lại PASS. Không có extra HTTP/cohort từ lỗi đó.

## D. Preservation và resumption

AST của `cases`, `prepare`, `preaudit`, `run_case`, `capture`, session reader và cleanup
không đổi so với `33e0b0d`; chỉ lab launch thêm group-range argument.12main templates,
9preflight reps, roles, budget, exclusions, session/workflow rules và Oracle predicates
cũ giữ nguyên. Không có material Oracle contract change; strict diagnostic checks
không sửa historical labels hoặc formal admission policy.

UNKNOWN receipt cũ giữ nguyên bytes/checksum và UNKNOWN. Dataset fingerprint vẫn
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`:
TRAIN43/37views, CAL13/13views, DEV86/83views. Không new derivative, checkpoint hoặc
model scores. Independent human review vẫnPENDING; đây là automated technical proof.

**Existing bounded protocol có thể tiếp tục sau yêu cầu mới.** Trước HTTP lần sau,
rebind source/environment hashes bằng addendum đã lưu, khóa fresh physical execution
ID/lineage với logical parent precommit, không reuse requestID của UNKNOWN hoặc sửa
plan cũ tại chỗ. Đây là execution bookkeeping, không đổi role/template/Oracle để tìm
scores đẹp. Other workflow preflights chưa được chạy ở milestone recovery này; không
claim cả campaign hoặc training gates đãPASS. Không tự chạy main acquisition.

## E. Safety và evidence

Tất cả owned services/containers/network/listener/watchdogs đã dừng.158protected
hashes, oldPGvolumes, models/encoders/thresholds, Rules/Policy, Web/Nginx/Suricata/
correlation và published Releases giữ nguyên. Sealed samples không mở; không AWS
hoặc AI enforcement. Candidate defaultOFF, team bootstrap/model restore không đổi.

Outer quota25%onecore, cutoff85°C, ownership watchdog80°C, reserve4GiB; container
limits riêng, không claim chung cgroup với collector. Peak đã đo64°C; finite lightweight
probes, không sustained-training thermal qualification. Host applications không đóng.

Private evidence `.local-dev/command-oracle-20261108/`: paired socket probes,
HTTP receipts dạng numeric/boolean, request/PID/packet correlation, source snapshots,
3PHPfixtures, rollback proof, resources và integrity. Không publish raw HTTP/session
metadata/IDs. Production privacy vẫnNOT_VERIFIED; lab proof không phải quality/
generalization certification. No independent human admission mới.

Final: root causeVERIFIED; localhost/packetOracle/negative/isolationPASS;
main captureNOT_STARTED; Requestv3 trainingNOT_STARTED; coverageUNCHANGED.
