# Local v1.0 release plan and bounded200K derivative — 2026-11-10

The academic priority is now a reproducible local shadow system, with **up to200K
HTTP source observations**, not2M examples or a larger model. Local v1.0 is **not
declared accepted**. Existing100K, its completed publisher pilot, frozen models,
thresholds, Web applications and Rules/Policy remain unchanged.

Starting HEAD: `49b0acbcfea1a83d1a393ffbe3c1dead6290a763`, clean, branch
`feature/ai-idps-shadow-integration`.
[Locked data/training specification](../ai-training/configs/research/local-release-200k-20261110.json),
[finite worker and existing-supervisor adapter](../ai-training/scripts/local-release-200k.py),
[previous completed experiment](41_STUDENT_PUBLISHER_EVALUATION.md).

## Current local capability and shortest release path

Read-only status found no owned foundation processes, no IDPS user services and
no running Docker containers. The historical foundation READY heartbeat was stale,
not evidence of a currently serving system. Prior live acceptance remains useful
historical evidence in [local integration](12_LOCAL_AI_SHADOW_INTEGRATION.md),
[demo stabilization](13_LOCAL_DEMO_STABILIZATION.md) and subsequent three-source/
body-ingress reports; it was not rerun as current live acceptance here.

The existing local launcher, model restore/bootstrap, Nginx telemetry socket,
bounded metadata journal, Rust ingestion/AI API and UI already provide the shortest
path. Do not introduce a new inference server or dashboard. Rules/Policy retain
their authority; Rust AI ingestion requires shadow/zero enforcement and does not
call firewall/policy execution. Existing GLU207 snapshot processing remains
contract-gated; absent causal flow/history inputs cannot be zero-filled. Body-syntax
research mode stays OFF by default. The new publisher model is **offline only**;
it is not installed as an attack-intent detector or combined with frozen risk scores.
All research scores are uncalibrated risk scores, not probabilities of real attack.

One guarded **offline source replay** passed: an actual pinned WAF publisher row,
position49964, was parsed through the existing HTTP contract/588 encoder and frozen
Requestv2 inference. Opaque replay record ID was preserved in output. Frozen score
0.6701612473, threshold0.8826237917; the separate completed publisher model returned
0.7950594425 in its own publisher-anomaly namespace. Neither score is Ground Truth.
Missing request representation raised an explicit required-feature error and
produced no score. No synthetic live vector, HTTP request, new Oracle, label change
or optimizer update was manufactured. The replay coordinate is counted only once
when the additional frame is materialized, not as an extra captured request.
Independent adaptive guardian completed7.85s, peak60°C. The preflight loaded pinned
frozen weights and the existing step420 publisher checkpoint; raw HTTP stayed in RAM.
This is **not** a live HTTP→Nginx→Rules→DB/UI smoke test, nor a current acceptance of
GLU207 live correlation. Private evidence:
`.local-dev/local-release-20261110/smoke/local-offline-smoke.json` and
`attempts/smoke-v1/thermal-report.json` in that runtime.

Final live acceptance remains one bounded existing-stack session after the data job
is inactive, to avoid competing workloads:

```sh
./scripts/bootstrap-team.sh --tests
./scripts/dev-up-and-verify.sh --ai-shadow --bootstrap-nginx --skip-build
python3 scripts/verify-ai-local.py --stop-after
```

`--skip-build` requires verified binaries matching current application source; if
not available, use the documented guarded build path first. Do not claim the
above commands ran this turn. Reuse the existing three-source runbook for passive
Suricata/GLU acceptance; do not infer all207 features from the request-only replay.

| Release criterion | Current evidence / remaining check |
|---|---|
|Startup/shutdown, no unrelated process termination|Existing launcher +7 current launcher tests; actual live start/stop pending|
|Rules/Policy authority and no AI blocking|Read existing shadow boundary; no policy/config change; live regression pending|
|Valid AI features/model integrity|Current real-source offline588 replay PASS; existing pinned model loader|
|Correlation|Replay ID preserved; live request→journal→DB/UI pending|
|Failure fallback|Missing offline input explicitly rejected;5 current worker tests; live outage/bundle-fault acceptance pending|
|Resource/thermal|Independent capped smoke PASS, peak60°C; reuse tested controller for data|
|Student/Security regression|Source untouched; actual HTTP/auth/UI regression pending live session|
|GLU207 availability|Existing causal/snapshot gate retained; unavailable without supported source inputs|
|Publisher versus attack intent|Separate offline result namespace, no publisher deployment|
|Reproducibility|Existing bootstrap/restore/runbooks; current end-to-end session still required|

## Frozen200K source design and requalification

Original run `student-training-v1-100k-r2` stays immutable:100K positions,
99,927 offline588 publisher rows and73 first-party reference-only receipts.
Original eligible3,783 SILVER records/3,751 views and pilot TRAIN2,667 remain
historical counts, not the new derivative's promised yield.

The additional source is the already authorized/hash-pinned WAF publisher TRAIN
Parquet,1,924,461 rows. Reuse the recorded MIT publisher-card basis and source SHA
`3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6`.
No download, publisher test, sealed file or new lab campaign is needed. New
zero-based, end-exclusive windows are **[49964,99964)** and
**[1098539,1148539)**,50K each. They are coordinate-disjoint from the original
[0,49964) and[1048576,1098539) publisher windows. Coordinate novelty is not physical
independence or representation novelty; cross-frame exact/view/template/conflict
checks happen in the combined index before admission.

The worker reuses all391 old feature shards byte-for-byte with their previously
verified hashes. It reconstructs normalized metadata in a new index; it does not
re-ingest the first100K source observations. Reading old raw coordinates for the
finite legacy-encoder/route provenance checks is not new ingestion or new data.

Legacy review is fixed to the previously identified **27,235 candidates**:

- Keep all historical CAL/DEV group/view protections and runtime protected routes.
  Add the completed publisher pilot's CAL/EVAL groups, views and588 content-near
  references; never turn those exposed holdouts into TRAIN.
- Compare candidates with the original safe-content and rich-content-v1 heldout
  embeddings in their **respective original encoders**, using the existing0.995
  metric/tolerance. Do not compare incompatible encoder spaces. Checks are also
  applied to newly materialized source rows. Unverifiable inputs remain blocked.
- Only remove a candidate's legacy-template flag when its finite evidence supports
  doing so; retain other reasons and entire-component label conflicts. Direct
  group/view/route matches and current-contract protected-near matches remain
  blocked. Review decisions/checkpoints stay private with source fingerprints.
- Preserve the old experiment and source roles. All admitted old/recovered
  components are **TRAIN-only** in the new candidate mapping; connected new rows
  inherit that role. New-only components use the precommitted seed17 SHA70/15/15
  assignment after exact plus exhaustive eligible near closure. Canonical588 views
  receive one gradient weight. Roles are never chosen by model scores.

This targeted derivative revises the conservative legacy-TRAIN exclusion scope,
not the formal admission policy. Protected samples/conflicts are not reclaimed.
The original100K ledger, checkpoints and conclusions remain intact. The old32
same-view aliases retain their existing accounting; their count is not inflated.

Publisher labels stay SILVER publisher anomaly, with UNKNOWN attack intent/outcome;
first-party UNKNOWN receipts remain reference-only. Auxiliary teacher proposals
never replace SILVER or receive gradient labels. No GOLD/human review is invented;
independent review remains PENDING. Historical/global campaign/time/raw lineage
remains PARTIAL; new timestamps/coordinates do not make a blind cross-domain test.

## One independent finite data job

Run: **`local-release200k-20261110-r1`**.
Private root:
`ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1/`.
The public report describes the locked design; actual live/final status is private.

Phases: verify source bindings → offline smoke → role-aware protection → checkpointed
legacy review → reuse old shards/metadata →100K additional-only ingestion → combined
200K exact/conflict index → resumable weighted content audit → deterministic metadata
finalization → eligible near-group split → exact-count final config. The additional
frame and combined frame have separate transaction cursors. No source positions
are added a second time. Finalization repeats metadata decisions to verify
determinism; it does not claim a second independent raw-feature rebuild.

CPU ceiling remains20% **of one core**,8GiB cap/swap0 and at least4GiB reserve;
85/90/93/96°C adaptive bands honor lower hardware limits. Same tested independent
watchdog, supervisor monotonic heartbeat and worker heartbeat are reused, with
no host/firmware protection change. One worker holds the existing global pipeline
lock. Maximum job21600s, no automatic retry, no other background data/train job.
Legacy SQLite commits every64 candidates; ingestion/index commits≤256 rows;
near audit saves cursor and accumulator atomically with binding/checksums.
Failures preserve artifacts; resume requires matching sources/config/code/key.

Inspect without a polling loop:

```sh
cat ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1/status.json
systemctl --user status idps-local-release200k-20261110-r1.service --no-pager
```

Other private paths: `attempts/data-v1/services.json`, `supervisor-heartbeat.json`,
`worker-status.json`, `worker.log`, `thermal-status.json`, `thermal-report.json`,
`legacy-review.sqlite`, `additional/progress.json`, `materialized/progress.json`,
`materialized/near-resumable-v1/checkpoint.json` and final `completion.json`.
Stop this job only if needed via its supervisor unit; the independent watchdog
also detects lost supervisor health and stops its worker. Do not stop unrelated apps.

Completion requires supervisor/resource success plus verified completion marker,
unique source positions/SQLite, finite588 features, matching hashes and finalized
ledger/split, not a cursor or process exit alone. `release-accounting.json` reports
valid/admitted/source-tier counts, recovered candidate records, canonical views and
the actual remaining source gap. Physical training-request identity is still
unverified for publisher rows.200K positions are not200K accepted training examples.

## Final training preparation, no launch

The public config fixes fresh588→64×4→8,50,696 parameters, publisher-anomaly
SILVER objective, seed17, AdamW lr0.001, batch64,10epochs, group sampling and final
checkpoint selection. No model-size search or architecture change is justified.
After final data processing, `final-training-config.json` binds the actual dataset,
TRAIN count, role/class/group counts, all data hashes, split fingerprint and exact
`10*ceil(TRAIN/64)` optimizer budget. `final-data/*.npz` and split remain private.
Before that file exists, the new training count/fingerprint are intentionally
unresolved and the template cannot authorize execution.

At the next user-authorized training milestone, consume this exact-count config
with the existing `student_publisher` model/update/atomic-checkpoint primitives;
do not invoke the old hardcoded2,667-example pilot launcher against the new data.
Checkpoint requirements: Adam/scheduler, step, epoch/cursor, RNG/order and all
fingerprints, with actual next-update exact-resume verification. No optimizer is
called by the data worker. Coverage failure records BLOCKED rather than reseeding.

Acceptance is precommitted now: final model AP must exceed every same-task prior/
metadata baseline by≥0.05 and CAL-threshold balanced accuracy must be≥0.75 on the
new internal EVAL. Report fixed0.5 too, all FP/FN, uncertainty and POST/body strata.
Threshold fitting uses only CAL; no EVAL gradients/statistics/checkpoint selection.
These are research acceptance criteria, not low-FPR, attack-intent, live-deployment
or promotion approval. Old pilot comparisons would be exposed-source diagnostics,
not independent gains. Existing normal-POST weakness and publisher label noise
remain material limitations.

No training, evaluation of a new candidate, deployment, promotion, enforcement,
AWS or500K processing is part of this data job. Once independently running and
checkpoint progress are verified, the Codex turn ends; completion is inspected
only on the user's next request. Source/tests/config/docs may be pushed; private
features, raw HTTP, aliases, labels, identities, keys, model files and logs stay local.

Current verification:32 targeted data/split/legacy/reliability/thermal tests,
5 worker tests and7 launcher tests PASS; Ruff and Git whitespace checks PASS.
These tests and the source replay do not replace the pending live release checks.
