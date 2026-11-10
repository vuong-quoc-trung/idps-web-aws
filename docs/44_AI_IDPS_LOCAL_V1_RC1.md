# AI-IDPS-Local-v1.0-rc1 — 2026-11-10

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
