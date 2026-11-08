# Request v3 final grounded acquisition — 2026-11-08

**CASE C — bounded preflight dừng tại Juice Shop basket POST500.** Không main
capture, không new supervised dataset/derivative hoặc training. Không đổi roles,
templates, Oracle hoặc acceptance criteria để đi qua lỗi.

Baseline `f22a1f3`, integration branch sạch/remote đồng bộ trước thay đổi.
[Machine report](../ai-training/reports/REQUEST_V3_GROUNDED_DATA_ACQUISITION_20261108.json),
[execution rebind](../ai-training/scripts/resume-request-v3-grounded.py),
[existing collector](../ai-training/scripts/request-v3-final-controls.py).

## Precommitment và environment rebind

Physical execution ID **`request-v3-grounded-20261108-r1`**; final plan fingerprint
`89eaa6b75e73b5fa0365afb3afa64db470c34e631a2b2f4043262ad910572607`.
Environment fingerprint
`3b8231dddcce0834a1545827aebd8ae2b4c6c2dbf0ac76bded3ce14d44b291b0`.
Logical parent plan fingerprint
`b0ef4f45cb77a82d4c1749803bd0028841081ff5cbd873c4e86bd3d3e25fc5e8`.

Rebind khóa source revision/hashes, pinned DVWA/Maria/Juice image IDs/digests,
Oracle version `locked-final-controls-v1`, previous environment addendum và new
request identities trướcHTTP. AST đối chiếu `cases`, `run_case`, `preaudit`, session
reader không đổi so với parent source.12templates,9representatives, assigned TRAIN/
DEVELOPMENT, Oracle definitions, coverage và duplicate rules giữ nguyên. CAL/prospective
không tham gia. Không dùng model scores. Pre-audit cả12planned cases không conflict
với permitted exposed224records theo raw/template/full/full-near/candidate checks.

Effective DVWA namespace được kiểm trước workflow: `ping_group_range=33 33`,
probe process33:33, CapEff0, NoNewPrivs1, seccomp2; no privileged/no cap-add.
Internal network, loopback19280 và limits cũ; sysctl host giữ nguyên. Không thêm
CAP_NET_RAW hoặc sửa Web/Policy. Mỗi main role dự kiến có instance/session riêng,
preflight diagnostics tách biệt. Fresh IDs không được gọi là independent-domain novelty.

Các run-plan preparation directories trước final lock không phátHTTP; final executed
source được archive byte-exact tại `.local-dev/request-v3-grounded-20261108/source-snapshots/`.
Collector bổ sung propagation của fresh execution ID sang ownership watchdog, kiểm
mismatch ID trước lab startup, namespace metadata và receipt execution/environment/
observation fields. Đây là bookkeeping/verification, không đổi Oracle predicates.

## Bounded preflight thực sự đã chạy

| Case | Workflow | HTTP | Internal Oracle | Intent / outcome | Body state |
|---|---|---:|---|---|---|
| control-00 | Legitimate quoted-localhost ping |200|PASS,4transmitted/4received/zero loss|BENIGN_INTENT / BENIGN_SUCCESS|OK|
| control-01 | Public file1.php normal render |200|PASS,declared file/greeting,no rawPHP|BENIGN_INTENT / BENIGN_SUCCESS|MISSING|
| control-02 | Locked UNION canary |200|PASS,declared two output columns|ATTACK_INTENT / VERIFIED_EXPLOIT_SUCCESS|MISSING|
| control-10 | Authenticated login form |302|PASS,server nested session authenticated|BENIGN_INTENT / BENIGN_SUCCESS|OK|
| control-11 | Logout form |302|PASS,session no longer authenticated|BENIGN_INTENT / BENIGN_SUCCESS|EMPTY|
| control-03 | Owned basket JSON POST |**500**|**UNVERIFIED**,owned product/quantity response absent|**UNKNOWN_INTENT / UNKNOWN_OUTCOME**|OK|

**6/9**representatives completed;5verified,1UNKNOWN. `control-04`basket read,
`control-05`product representative và `control-09`identity read **NOT_EXECUTED**.
Authenticated basket readback không chạy sau add500. Main **0/24**, không dùng main
requests để debug. Cả5PASSpreflights cũng giữ PREFLIGHT_DIAGNOSTIC_ONLY, không được
chuyển thành TRAIN/DEV admitted records dù đã có planned-role provenance.

**Exact blocker:** POST `/api/BasketItems/` nhận actualHTTP500. Collector không nhận
được expected owned product/BasketID/quantity response. Không gán benign từ intended
operation, authenticated session hoặc model score. Không có retained sanitized server
exception/state witness cho response này nên **root cause nội bộ vẫn UNKNOWN**;
không suy là constraint/parser/auth failure. Không sửa route/body/schema/Oracle rồi
recapture trong milestone. No-raw-evidence policy giữ nguyên.

Ping recovery vẫnPASS theo precommitted response Oracle. Không chạy lại kernel/PID
observer từ recovery; packet-observation proof cũ giữ riêng, không gọi acquisition
là new independent packet trace. Client request IDs được gửi và response-bound bằng
collector; không claim independent proxy/PCAP identity corroboration cho cohort này.
Intent, execution outcome và observation status được lưu riêng; internal automated
Oracle không phải independent human certification.

## Counts và private evidence

6current dispatches có durable before-send ledger và response received;23setup/auth
HTTP calls được đếm riêng, không supervised receipts. Không equate main budget với
tổngnetworktraffic. Previous campaign1completedUNKNOWN, upper bound2dispatches và
previous recovery2HTTPdiagnostics được ghi riêng, không reuse/relabel.
Conservative historical-inclusive acquisition bound là **8dispatches** (2old+6current),
không bao gồm2recoverydiagnostics. Legacy collector `global_dispatch_upper_bound=7`
chỉ là6current+1olduncertain; không dùng nó để bỏ qua oldcompletedUNKNOWN.

Private capture tại
`ai-training/.artifacts/request_v3_grounded_20261108/campaign-final-r1/` giữ plan,
environment binding, numeric Oracle receipts, dispatch ledger, namespace metadata,
status và diagnostics. Manifest diagnostic fingerprint:
`79c3011e8b6c183195bc44abfc722dbb1c9134344de00adb59c934378cc9616e`.
Mỗi diagnostic có execution/request IDs, original role, workflow, ordinal session/
campaign lineage, planned/verified intent, outcome, observation status, Oracle checks,
feature version và explicit non-admission. Review6PENDING,0independent verification.
Không lưu raw request/response bodies, headers, cookies, tokens hoặc direct secret
digests. Derived per-record diagnostics local-only, không publicGit.

## Dataset, splits và coverage trước/sau

Không có qualified main cohort để materialize; không tạo release rỗng hoặc gọi
preflight metadata là derivative training dataset. New materialization/fresh rebuild
**NOT_RUN**; prior224materialization/rebuild evidence vẫnPASS, không rerun vô ích.
Parent version `request-v3-body-syntax-20261108-v1`, fingerprint
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d` giữ nguyên.

| Metric, before = after | TRAIN | CALIBRATION | DEVELOPMENT |
|---|---:|---:|---:|
| Total receipts |63|37|124|
| Strict eligible |43|13|86|
| Unique candidate views |37|13|83|
| Benign / Attack |23 / 20|11 / 2|40 / 46|
| Benign JSON POST |0|4|0|
| Benign FORM POST |19|1|0|
| Same-surface command / file benign |0 / 0|0 / 2|0 / 1|
| Workflow categories / lineage components |14 / 11|7 / 7|9 / 2|
| UNKNOWN or excluded |20|24|38|

Chi tiết machine report là authoritative cho counters theo masks; workflow categories
không phải independent sessions. Family strict views giữTRAIN SQLi4/XSS8/command4/
file2;CAL0/2/0/0;DEV12/13/3/15. Body states supervised149EMPTY+75OK,0newMISSING:
2naturalMISSINGpreflights là diagnostics, không được thêm vào supervised coverage.
No unsupported/truncated/parser/worker-loss probes mới; fixtures cũ vẫn tách biệt.

Exact/mixed/near và split result giữ nguyên: toàn224unique122→158, mixed35→6records,
identity-excluded JSON login vẫn collision/quarantine. Existing strict candidate
cross-role lineage/exact/nearPASS; sealed candidate overlapUNVERIFIED, không mởholdout.
CAL assignments/eligibility không đổi. Method/body shortcut risk chưa giải quyết:
DEV0benignPOST,6POSTđềuattack; TRAIN thiếuJSON và command/file benign counterparts.
PreflightPASSkhông được dùng để làm đẹp các coverage gates.

## Readiness decision, safety và điểm dừng

| Gate | Kết quả |
|---|---|
| CAMPAIGN_PREFLIGHT | **FAIL**,5PASS/1UNKNOWN trong6completed/9planned |
| MAIN_CAPTURE / NEW_RECEIPTS | **NOT_STARTED**,0/24main;6preflights riêng |
| ORACLE_VERIFICATION | PARTIAL, basket500 chưa xác minh |
| DERIVATIVE_MATERIALIZATION | **NOT_RUN**,không admitted main cohort |
| STRICT_SPLITS | PASS cho existing exposed dataset, không admission mới |
| PRIVACY_FOR_RESEARCH | PASS numeric diagnostic scope; productionNOT_VERIFIED |
| TRAIN / DEV coverage | FAIL,giữ nguyêngaps |
| CAL validity | PASS bounded research limits, không1%populationFPRcertification |
| Feature contract | LOCKED634,không fitstatistics/prefixchange |
| Warm-start/reload/exact-resume | Prior synthetic634proofVERIFIED, không rerun training |
| Evaluation protocol | Existing architecture/LR/budget/sampling/calibration/criteria giữ nguyên |
| RESEARCH_PILOT_READY / independent quality | **FALSE / FALSE** |
| REQUEST_V3_TRAINING | **NOT_STARTED** |
| FROZEN_BASELINE | UNCHANGED |

65targeted Python testsPASS; Ruff/formatPASS. Capture38.48s, active average56.90°C,
peak64°C; toànpreparation/tests peak66°C. Quota25%onecore, outer cutoff85°C,
ownershipwatchdog80°C/reserve4GiB, no watchdog/thermal failure. Limits containers riêng,
không claim single cgroup. Không sustained training, user apps không đóng.

All owned containers/network/listener/watchdogs đã dừng;158protected hashes,
oldUNKNOWNbytes, frozen models/encoders/thresholds, Student/Security/Nginx/Rules/Policy/
Suricata/correlation, existing PGvolumes và Releases giữ nguyên. Candidate defaultOFF,
bootstrap/model restore không đổi; no AWS/enforcement/sealed access.

**Đúng một next action:** bounded source-backed diagnosis cho owned BasketItems
POST500, chỉ giữ sanitized exception class/status và read-only product/ownership/
quantity state. Fresh diagnostic identity, giữ locked role/template/Oracle và tất cả
UNKNOWN. Chỉ tiếp tục capture sau khi application Oracle này xác minh; không nới
privacy, chuyển roles hoặc tăngbudget. Milestone này dừng tại CASE C.
