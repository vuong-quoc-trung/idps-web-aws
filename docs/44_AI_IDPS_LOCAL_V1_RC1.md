# AI-IDPS Local Demo v1.0 — vận hành và acceptance

## Chế độ mọi nguồn IPv4 — yêu cầu chủdựán11/11/2026

`run-all.sh` mặcđịnh bind`0.0.0.0:18782`, allow`0.0.0.0/0`. Khônggiới hạn
192.168.1.x: nhậncảWiFi10.10.x.x, mạngVM192.168.122.x vàIPv4khác córoute tới máy.
Mọi HTTP vẫnđi quaSuricata gateway→NGINX→Student→AI/Rules→HybridPolicy/audit.
AdminSecurity/DB vẫnlocalhost; khôngmởfirewall tựđộng hoặcportforwardrouter.

`health` probe127.0.0.1 khi wildcardbind đểkhôngnhầm0.0.0.0 làURLclient;
LAN_URL/LAN_URLS tínhIPinterfacehiệntại (ưu tiêndefault route), cậpnhậtkhiđổiWiFi.
Máyngoài dùnghttp://IP_WIFI_MAY_CHU:18782; KaliNATdefault cóthểdùng
http://192.168.122.1:18782. Khôngcầnđổiallow-cidr saumỗiWiFi.
Lệnhoverrideprivate/subnet cũ vẫn dùngđược khi chủđộng chỉđịnh.
NhậnmọiIP khôngvượtđượcAPclientisolation hoặcfirewallmạngtrường; kiểmthửtừ
máyBvẫnPENDING chođếnkhicórequestthực. Modelv2/frozenweights và10MPOSTPONED giữnguyên.

---


## Sửa lỗi run-all từ terminal — 11/11/2026

Session864530730917 bịthermalstop90°C sau14,37s, chưa tớisensor; không phải lỗipassword
hayworkingdirectory/opt/antigravity. Demo serving/startup naygiớihạn50%ONEcore thay200%
(chỉ50% của1core, không50% toànmáy). Guardcutoff90/rolling80, independentwatchdog
vẫngiữnguyên. Acceptance cũ giữngân sáchriêng. Cho phépstartupđến240s vàinphase.

Session020608654766 trướcđóthoátvìsystemd từchốiCPUQuota139.98631520507138%.
MọiCPUQuota gửisystemd nayđịnhdạng2chữsốthậpphân139.99%; đãxácminhparse bằng
transientscope vôhại. Regression+thermal22testsPASS. Guardresourcefailure vànhiệtđỉnh
đượcđưa vàoJSONlỗistartup, khôngchỉđưađườngdẫn. Khôngauto retrykhiemergencystop.
Dùngrun-all.sh saukhimáynguội; khôngvôhiệu thermalprotection hoặcđóngappngườidùng.

---


## Phục hồi LAN và health — 11/11/2026

Session321973593298 dừng vìindependent watchdog đo92°C (cutoff90), không tựrestart.
Session077476605445 sau đóFAILED do`unshare` bịtừchối`uid_map` tronglaunchcontext
khác; servicecleanup đãdừngruntime. VìvậyRustREADY trongsnapshot cũ không làLANready.
Sensor giờ ưu tiên`podman unshare unshare -n` dùngprofile distro hiệnhữu, kiểmtra
permission trước startup; không thayAppArmor/sysctl/firewall. Namespace vẫnprivate.

`start` phục hồi cấu hìnhLAN từ`.local-dev/demo-network.json`, chờHTTP thật và
SCORED/MATCHED/policy trướcHEALTHY. Startkhi cósession sống chỉreporthealth,
không spawnjobtrùng; filelocktồn tại không tựcó nghĩa lockđanggiữ. `health` trảexit1
vàdiagnostic cóaction khi LANrefused, guardpaused/stale, sensor/model/correlation
khôngsẵn sàng. Không lấyRustalive/AIready đơnlẻ làmHEALTHY.

URL192.168.1.28:18782 làsensor gateway;NGINX thực nghe127.0.0.1:18780 phía sau,
adminAPI127.0.0.1:3001. Không bypasssensor hoặc mởadminAPI raLAN. MáyB thật vẫn
PENDING_EXTERNAL_CLIENT. Kiểmtraendpoint từhost chỉlàHOST_TO_LAN_LISTENER.
Tiếp tụcgiữcutoff90°C: nhiệt doứngdụngkhác cóthể khiếnfailsafe dừngdemo; khôngraise
threshold để che sựkiện92°C. Dùngstatus/health đểxácđịnhsession sống trước gọistart.

---


## Kết quả mới nhất — localPASS, phục vụLAN

`demo-acceptance-20261111-r7/final-status.json`: mọi localgatePASS, failures=[],
RESOURCE_SAFETY=PASS, peak64°C, watchdog0trip. GlobalreleasePARTIAL chỉ vì máyB
chưa có vàoperator chưaduyệt firewall. Khôngclaim externaltest/manuallyblockPASS.
PhiêndemoLAN sauvalidation dùngcontinuousscope, giữdịchvụchạy saukiểmthử.
IPhiện192.168.1.28:18782, allow192.168.1.0/24; hostadmin127.0.0.1:3001.
Dùng`./scripts/idps-demo.sh status`/`health`; `history`xem100incidents gầnnhất;
`stop`chỉkhi muốn kếtthúc. Lấy X-Request-Id từB đểtraAI/rules/policy trênA.
Cácghi chú bên dưới làlịch sử/giới hạn. HướngdẫnLAN vàoperator giữnguyên.

---


Cập nhật **11/11/2026**, branch `feature/ai-idps-shadow-integration`, HEAD lúc
kiểm tra `2cd32b0` (đã merge attack-simulator; không reset các sửa đổi chưa commit).
**LOCAL_DEMO chưa ACCEPTED**. Lượt`demo-acceptance-20261110-r2` đã PASS2test
policy Rust +2testresponse, nhưng watchdog dừng88°C tại cutoff85 trước live HTTP.
Không chuyển NOT_RUN thành FAIL chức năng hoặc PASS từ sơ đồ/fixtures.
Lượt tiếp theo: `demo-acceptance-20261111-r3`; xem`final-status.json` sau khi kết thúc.

## Recovery r3 → r4

r3 đã kết thúcBLOCKED: Web/auth/audit PASS nhưng AI startupNOT_READY. `ai.log`
ghi guard con từ chối resource startup; guard ngoàiPASS, peak79°C, không có
thermal emergency. Launcher cũ tạo nestedguard ngay trong acceptance scope.
`assert` kiểm tra READY không có message nên failure.reason rỗng.

Recovery dùng chung scope đã xác minh + independentwatchdog; standaloneAI vẫn
có guard riêng. Trước AI launch chờ CPU<70°C/RAMavailable≥4GiB có deadline90s.
Worker vẫn tự kiểm tra nhiệt/RAM. Lỗi mới lưutype/reason/evidencepath;
guard startup ghi nhiệt/RAM và ngưỡng thực tế (rolling75°C, không nhầm65°C).

Run`demo-acceptance-20261111-r4` tái sử dụng Rust build/policy/response/6parser
và frontend tests từr3 khi fingerprints nguồn/weights còn khớp. Không build/test
lại toàn suite. Giai đoạnLOCAL_STARTUP_INDEPENDENT phải cóHTTP/auth, heartbeatREADY
và requestSCORED thật trong connection-check mới được ghistartup-independent.json
PASS và chạy tiếp nativeRule+AI/correlation/recovery. Trạng thái hiện tại phải đọc
trongrun directory; ghi chú này chưa chứng nhận livePASS. LAN máyB vàmanualoperator
vẫn là hai gate riêng đangPENDING.

## Recovery Suricata/correlation r4 → r5

r4=PARTIAL. Startup/NGINX/HTTPGET/POST/Requestv2SCORED/backend/fallback/recovery/
resourcePASS. THREE_SOURCE_HTTP fail: gateway nhậnrequest trước engine readiness,
EVE chỉstats+reverse flow, không cóHTTP event; correlation đúng khi giữMISSING_SOURCE.
Chưa khẳng định race là nguyên nhân duy nhất cho đến khi chạy lại capture.
NativeNGINX chết vìchownUID65534 khôngmapped; preflight sau sửa còn phát hiện
missingdefaultfastcgi tempdir. Đã dùnguserrootmapped và cả5temp paths dướilabroot;
`unshare -Urn nginx -t` PASS. Không đổihostNGINX hoặcStudent/Securitysource.

R5 đợilogEngine started của đúngsensor generation trước mởgateway; restartcũng
cófreshreadiness. Nativepolicy test chỉ phátrequest sau sensorready/configtest.
Failures cópaths/proofs; correlationtimeout lưurequestIDs vàsources thực thiếu.
Hybridfailr4 xảyra trướcpolicyinput nên chưa làbằng chứng lỗilogic; r5 dùnggate
BLOCKED_BY_LIVE_EVIDENCE nếu prerequisite chưađạt, không tự đổi thànhtestPASS.

`demo-acceptance-20261111-r5 --resume-from ...r4` táisửdụng Rust/frontend và
fallback/restartPASS theo fingerprints; startup cần chạy lại đểphục hồi dịchvụ đãdừng,
sau đó chạy freshsensor/nativepolicy/DBaudit/cleanup. Khôngtrain/rebuild/modelmigration.
Xem`reused-evidence.json`,`reused-live-gates.json`,`native-lab/result.json` vàfinalgates.
LệnhLAN ở dưới giữnguyên; máyBthật vàmanualapproval vẫnPENDING.

## Sửa resource closure và phiên LAN giữ chạy — 11/11/2026

R5 đãPASS toàn bộ functional gates, gồm actualSuricata+AI+PROPOSE+DBaudit;
RESOURCE_SAFETY=FAIL vìworker exit1 dohai writer cùngrename`wrapper-status.writing`,
không phảioverheat (peak75°C, watchdogkhôngtrip). GhiJSON hiện dùngtempfileduynhất+
fsync; test8threads×30writesPASS. R6preflight phát hiệnchainreuse logfallback nằmởr4,
đã sửa truynguồn theoSHA; evidencecũ giữnguyên. R7 xácminhresourceclosure sau sửa.

PhiêndemoLAN đượcstart riêng sauvalidation, **không chạycleanup sau các request
kiểm thử**. Chạyđếnkhioperatorstop hoặcresource/sensorfailsafe. Guardscope continuous
(max-seconds0) vẫn cówatchdog độc lập, thermal90°C/rolling80°C, RAMreserve4GiB;
telemetrygiữtốiđa20.000samples đểkhông tăngRAM vôhạn. Researchjobs vẫnfinite.

Lệnhquan sát bổsung: `./scripts/idps-demo.sh history` liệtkê100incidents mới nhất.
MachineA dùngAI/rules/policy/incident với`--request-id` lấy từX-Request-Id củaB.
HostAPI/DB chỉloopback; chỉgateway192.168.1.28:18782 mởsubnet192.168.1.0/24.
Manualfirewall khôngđược duyệt trongacceptance; kernelreadback trênhostMODEOFF
cóthểUNAVAILABLE doactuator bịvôhiệu hóa. Khôngđược coi làblock/unblockPASS.

## Model và đường dữ liệu thực

**Duy nhất Requestv2 live:**50.696params/588features/120.435TRAIN views metadata,
step3072, frozenstrict`>0.8826237916946411`. Bundle giữ nguyên tại
`ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle`.
[Registry](../ai-training/MODEL_STRATEGY.json), [hai dòng model](03_AI_MODEL_AND_TRAINING_PLAN.md).
10M hoãn; GLU207/publisher200K/v3 chỉ archive, không live.

HTTP→NGINX→Student; NGINX syslog riêng→588encoder→Frozenv2→inference journal;
Application Audit + NGINX logs + EVE đã privacy-project→Rust normalize/DB;
request_id và sensor response-ID/flow/tx→correlation→`hybrid::evaluate`→incident/
proposal/audit. Sensor là passive private namespace gateway; chỉ traffic qua
port18782 có sensor coverage. Alert đến sau HTTP là quyết định hậu quan sát,
không thể chặn ngược request đã hoàn tất. SameIP/flow không đủ ghép request.

Policy severity1..5→risk90/70/45/20/20, lấymax rule request-bound; AI compatible
above-threshold thêm10, không gọi score là attack probability. Payload rule và
AI có thể phụ thuộc cùng evidence, không tính thành hai xác nhận độc lập.
Ba App401/403 khác request cho behavioral support10, không tự coi là attack GT.
High rule→REVIEW dù AI thấp/mất; AI alone→ALERT; rule+AI có thể ALERT→REVIEW.
PROPOSE_BLOCK cần rule≥70+AIhigh+matched/fresh+3denials+approved disposableIP+
khôngprotected. PROPOSE không gọi firewall. DefaultAUTO_BLOCKfalse/MODEOFF.

## Lệnh demo

Chỉ start sau khi acceptance đã dừng (flock ngăn chạy chồng). Tại repo:

```sh
./scripts/idps-demo.sh start
./scripts/idps-demo.sh status
./scripts/idps-demo.sh health
./scripts/idps-demo.sh normal
./scripts/idps-demo.sh ai
./scripts/idps-demo.sh test
./scripts/idps-demo.sh rules
./scripts/idps-demo.sh policy
./scripts/idps-demo.sh incident
./scripts/idps-demo.sh response
./scripts/idps-demo.sh stop
```

Chờ`demo-ready.json`/healthREADY; AI/correlation bất đồng bộ nên dùngrequest_id
trongreceipt để tra lại sau vài giây. Các lệnh`ai/rules/policy/incident` hỗ trợ
`--request-id HEX32`. Demo tối đa90phút, sensor≤2048requests; không dùng flood.
Stop gửi marker để cleanup graceful, giữDB/logs; status cho biết supervisor sống
và finalgates, không coi heartbeat cũ làRUNNING. Raw/credentials chỉ`.local-dev`.

## Máy B cùng mạng LAN

User xác nhận **chưa có máyB**; kiểm thửhai máy =PENDING_EXTERNAL_CLIENT.
Host hiện`wlo1=192.168.1.28/24`, gateway192.168.1.1; IP có thể đổi theoDHCP.
Kiểm tra`ip -brief address` trước demo. Không mở adminAPI/DB raLAN.

```sh
# Máy A — bind đúng IP private, chỉ nhận subnet lab đã cho phép
./scripts/idps-demo.sh start --listen 192.168.1.28 --allow-cidr 192.168.1.0/24
# Máy B — đổi HOST nếu DHCP thay; không chạy ngoài lab được cho phép
HOST=http://192.168.1.28:18782
curl --connect-timeout 5 -i "$HOST/api/auth/csrf"
curl --connect-timeout 5 -i --get --data-urlencode "search=1' OR 1=1--" "$HOST/api/auth/csrf"
# Máy A — lấy X-Request-Id từ response B, rồi tra sự kiện thật
./scripts/idps-demo.sh ai --request-id HEX32
./scripts/idps-demo.sh rules --request-id HEX32
./scripts/idps-demo.sh policy --request-id HEX32
```

HTTP200 chỉ chứng minh app trả lời; query này kiểm tra rule/AI, không tuyên bố
SQLi exploit thành công. Nếu không kết nối: kiểm tra cùngsubnet, AP client-isolation,
route, listener18782 và firewall hiện hữu; chưa sửa host firewall/routing tự động.
Gateway ACL từchối ngoài subnet trước relay. TCPpeerIP lưu riêng trong
`gateway-peers.jsonl`; không lấy X-Forwarded-For client gửi làm danh tính tin cậy.
NGINX phía sau relay thấy127.0.0.1 (protected). Vì vậy LAN demo này dùng
ALERT/REVIEW và **không block máyB theoIP**; không mạo nhậnPROPOSE_BLOCK LAN PASS.
PROPOSE/response kiểm tra riêng bằng native veth client, không gọi đó là máyB.

## Response và chứng cứ phải tách

A: actualHTTP receipt+SCORED; B: `policy-effect-fixture.json` dùngproductionRust,
giữrule cố định,scorefixture0.1/0.99→ALERT/REVIEW; C:`native-lab/result.json`
phải có SuricataSENSOR_TRANSACTION+AI cùngrequest. Không lấyB thayA/C.

Manualblock/unblock/TTL =**PENDING_APPROVAL** cho đến khi operator chủ động chạy:

```sh
./scripts/idps-demo.sh manual-proof --operator-approved-isolated-client
```

Chỉ clientdisposable10.203.17.2 trongprivate user/network namespace; không sửa
hostnftables. TTL15/4s,cooldown,protectedIP,DBqueue vàkernelreadback được kiểm tra.
Chưa cóoperator action thì không gửi approveAPI. Không triển khai AWS/enforcement.

## Tài nguyên và trạng thái

CPUCoreUltra9 285H,16logical; localcoretempcritical105°C. [Intel specs](https://www.intel.com/content/www/us/en/products/sku/241747/intel-core-ultra-9-processor-285h-24m-cache-up-to-5-40-ghz/specifications.html)
cho max110°C; dùng mức bảo thủ **cutoff90°C**, dưới yêu cầu<96 vàlocalcritical.
Quota khởi200%ONEcore (không phải200%host), workloadhai slowcores, threadsBLAS1;
rolling300s<80, reduce từ77, freeze nóng/rise nhanh, independentwatchdog0,2s,
RAM≤8GiB/keep4GiBavailable. Không đổi firmware/governor hoặc đóng app khác.
Không hứa khống chế nhiệt do ứng dụng ngoài scope.

Final acceptance phải có startup,normalGET/POST,realAI,Suricata,correlation,policy,
DBaudit,AIoutage fallback,sensor/backendrestart,shutdown,preservation vàresourcePASS.
Hai máy vàmanualapproval là gate riêng; chưa có thì toàn bộ vẫnPARTIAL.
Không commit/push mixed working tree trước khi kết quả/diff được review.

---

## Hồ sơ lịch sử (không phải trạng thái live hiện hành)

**MODEL_EVALUATION=PASS under locked research criteria; LOCAL_RELEASE=PENDING
current real-HTTP acceptance.** No production readiness, attack-intent quality,
publisher live deployment or promotion is claimed.

[Aggregate metrics](../ai-training/reports/FINAL_LOCAL_MODEL_EVALUATION_20261110.json),
[evaluator](../ai-training/scripts/evaluate-final-local.py),
[finite acceptance runner](../scripts/local-v1-acceptance.py).
Starting HEAD `e5cf579`, clean, integration branch. No new training/data expansion.

## Verified model and data

Run `final-local-publisher-200k-20261110-r1`:588→64×4→8,50,696 parameters,
15,890 TRAIN views,10epochs/2490 updates/158,900 presentations. Generation
`step-000000002490-0e7072f8ce1d`, manifest
`bb040534768e76b645f4a81055cfac2b97f17b7b22659aeee827d4077d9d366f`.
Payloads, Adam/scheduler/RNG/cursor/code/data bindings pass. Evaluation marks arrays
read-only and verifies model/optimizer fingerprints remain unchanged.

Dataset fingerprint
`3544b3da532b9eacba62daba6e8556199399d3f0f659e5a2095cbd9d16d29863`.
200K source positions=199,927 compatible publisher HTTP observations+73 first-party
reference receipts, not independent physical requests. Accepted21,331 SILVER records
→17,588 canonical views,3,743 aliases. Split TRAIN15,890/CAL848/EVAL850. Accepted
GOLD/BRONZE/UNLABELED0; source retains73 UNLABELED. Physical publisher identities
unverified, intent UNKNOWN, independent human review PENDING.

Quarantined178,669. Overlapping flags: duplicate34,428; protected/conflict component
145,242; current-contract protected-near124,195; legacy-near61,498; completed pilot
heldout1,293. Do not sum flags. Existing verified evidence is reused; no full ingestion
or quadratic source audit is repeated, and no source roles/data are edited.

## Final evaluation

CAL-only balanced-accuracy maximum/highest tie/strict`>` gives threshold
**0.004070103168487549**, persisted before EVAL scoring. No EVAL tuning or checkpoint
selection. CAL is a fitting partition. Fixed0.5 is a precommitted second point.

| Partition / threshold | Precision | Recall | F1 | AP | FPR |
|---|---:|---:|---:|---:|---:|
|TRAIN / CAL threshold|91.39%|94.97%|93.15%|0.98017|10.85%|
|CAL / CAL threshold|93.92%|94.64%|94.27%|0.98487|9.82%|
|EVAL / CAL threshold|**92.65%**|**94.11%**|**93.37%**|**0.98095**|**11.14%**|
|EVAL / fixed0.5|99.57%|44.99%|61.98%|0.98095|0.29%|

EVAL341normal/509anomalous, matrix`[[303,38],[30,479]]`, FNR5.89%. Nominal Wilson95%
precision90.07–94.60%, recall91.71–95.84%, FPR8.23–14.93%. IID intervals omit group/
source selection and label noise. Fixed0.5 misses280/509 anomalies;1/341normal FP
does not establish deployment FPR≤1%.

Control AP: prior0.59882/window0.61320/body0.61900. Candidate AP margin0.36196 and
balanced accuracy0.91481 pass locked margin≥0.05/BA≥0.75. This research PASS does
not establish low false positives. Equal weight per790 EVAL groups gives F10.93454,
AP0.98102/FPR11.20%;859 retained EVAL records include9aliases, separately reported.

GET817:334normal/483anomalous,36FP/30FN. POST19:2normal/17anomalous,**2FP/0FN**;
insufficient normal POSTs for reliable FPR. Other methods have1–5examples each.
MISSING body769:15FP/29FN. EMPTY70=source window1:40normal/30anomalous,
**22FP/1FN/FPR55%**. Present-body11:one normal, falsely flagged. Binary publisher
labels do not support SQLi/XSS/command-family recall.

Calibration is poor: EVAL Brier0.29707/ECE10fixed-bins0.32147 versus prior Brier
0.24280. Operating-threshold fitting is not probability calibration. Final full
objective TRAIN0.98905/CAL1.11714/EVAL1.19603 differs from last-batch loss0.01806.
Saved-sampler diagnostic: final epoch ends with1750normal views; last1024belong to
one group. Round-robin exhausts small queues first. This is a plausible operating-
point bias, not causal proof; no optimizer replay/alternate training was performed.

### Previous checkpoint comparison

New CAL has zero known overlap with old TRAIN; new EVAL has **one content-near
overlap**, though raw/view/template overlaps are zero. A fair common holdout is
therefore unavailable. No row is removed and the old model is not scored there
to manufacture a paired gain. Old EVAL520: F195.18/AP0.98881/FPR6.52%; new EVAL850:
F193.37/AP0.98095/FPR11.14. Different cohorts cannot establish paired improvement
or regression. Better calibration, POST behavior or cross-domain generalization
versus the old model is not demonstrated. Same exposed publisher/global campaign/
time/raw lineage PARTIAL limits remain. Evaluation guard completed14.84s, peak78°C.

## Local architecture and acceptance job

Existing Nginx/Student→asynchronous telemetry→Frozen Requestv2 shadow→journal→Rust/
DB/API/UI remains. Rules/Policy retain authority and AI never changes enforcement.
Passive gateway Suricata evidence is response-ID/flow/tx-bound; base traffic without
the gateway is not a three-source match. GLU207 remains unchanged and causal-contract-
gated; this job does not exercise its scoring or fabricate missing207 inputs.
New publisher model is **EVALUATED_OFFLINE / LIVE_UNSUPPORTED**: publisher full
header/body input differs from live selected-header/no-body, despite both being588.

Launcher previously allocated100% of one core per serving/AI scope; local defaults
now20%. The acceptance-only opt-in keeps children inside the existing guarded
scope instead of escaping its common envelope, and refuses an unguarded caller.
No Student/Security/Nginx/Suricata/Rules source is changed.

One finite independent job `AI-IDPS-Local-v1.0-rc1`, output
`.local-dev/rc1-acceptance/`, uses existing integration guard scope mode,20% one
core/≤8GiB/4GiB reserve,85°C conservative cutoff,2400s deadline and independent
watchdog. Scope mode retains permitted user-namespace capture; no host capture,
AppArmor/capability/thermal protection changes. No automatic retry/follow-up work.

Fresh owned runtime `.local-dev/rc1`, DB prefix`idps-rc1`: harmless Rust policy
fixtures/frontend tests; cached startup; actual GET-CSRF/POST-login/GET-me; passive
gateway concurrent/keepalive/sensor-stop/restart tests; per-request logs/model/
score/latency/source proof; existing AI outage/model-fault/restart/backend persistence;
graceful shutdown. No exploit or GT claim. Tracked Web/source and frozen payloads
are hashed before/after. Worker and outside supervisor both attempt owned cleanup;
DB volumes and private evidence remain. No gate is PASS before its evidence exists.

Current8launcher+5worker+11correlation+11targeted evaluation/handoff tests PASS.
Current Rust/frontend/live gates remain pending until the job executes them.
Final artifacts: `AI-IDPS-Local-v1.0-rc1.json`/`.md`, stage logs, `worker-status.json`,
`supervisor.json`, `guard/` resource evidence and `request-proofs-private.json`.
Final ACCEPTED/PARTIAL/BLOCKED requires resource closure too. No raw sessions,
credentials, private tensors/model weights or request-level evidence enter Git.

## Operations after the acceptance job stops

```sh
./scripts/bootstrap-team.sh --tests
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx --skip-build
./scripts/dev-up-and-verify.sh --status
curl -i http://127.0.0.1:18780/api/auth/csrf
# Security Web http://127.0.0.1:3001/ ; credentials remain private in runtime
./scripts/dev-up-and-verify.sh --ai-worker stop
./scripts/dev-up-and-verify.sh --ai-worker start
python3 scripts/verify-ai-local.py --stop-after
./scripts/dev-up-and-verify.sh --stop
```

Use matching cached binaries for`--skip-build`; otherwise the existing guarded
build path is required. This is not a clean-machine build claim. Team clone/
bootstrap/checksum model restore remains unchanged and does not require private data.
For this acceptance runtime, prefix status/stop commands with
`IDPS_DEMO_RUNTIME="$PWD/.local-dev/rc1" IDPS_DEMO_CONTAINER_PREFIX=idps-rc1`.
Correlated metadata resides in its`ai/results.jsonl`, `correlation/results.jsonl`,
sanitized access/audit logs and `.local-dev/rc1-ids/`; only gateway18782 has sensor
coverage. Read the final RC artifact for the first failing gate and one corrective
action. Do not substitute historical acceptance or offline replay for current live PASS.