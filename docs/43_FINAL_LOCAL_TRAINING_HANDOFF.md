# One authorized final publisher training handoff — 2026-11-10

The user explicitly authorized **one** automatic transition from the completed
200K derivative to one real research training run. This supersedes the earlier
stop-before-training instruction for this run only. No evaluation, promotion,
enforcement, AWS or source expansion is authorized. Local live acceptance is
still NOT_ACCEPTED_LIVE; offline source replay is not live readiness.

Starting HEAD `e0ebae3`, clean, on `feature/ai-idps-shadow-integration`.
[Dataset design](42_LOCAL_RELEASE_AND_200K.md),
[one-shot runner](../ai-training/scripts/final-local-publisher.py),
[fail-closed validator](../ai-training/src/idps_ai/data/final_release_validation.py).

## Producer completed; use a direct one-shot service

`local-release200k-20261110-r1` completed all its programmed phases in5272.98s;
supervisor result and independent thermal report agree. Peak84°C, quota20% of
one core, no recorded thermal failure. An active/exited producer unit is retained
success bookkeeping, not a running worker. The new service does not restart or
modify that producer, its source/config/code, data or thermal configuration.
No waiting timer or continuously running handoff monitor is needed.

The immutable source release reports:

| Unit | Count |
|---|---:|
|Source positions: reused / additional|200,000:100,000 /100,000|
|Publisher HTTP observations with offline588 / first-party reference receipts|199,927 /73|
|Accepted SILVER records|21,331|
|Accepted canonical588 views / same-view aliases|17,588 /3,743|
|TRAIN canonical views: old-frame / new-frame|15,890:9,205 /6,685|
|CAL / EVAL canonical views|848 /850|
|Recovered legacy candidate records, before view canonicalization|8,612|
|Accepted new-frame records|10,070|
|Accepted normal / anomalous publisher records|11,026 /10,305|
|Accepted GOLD / SILVER / BRONZE / UNLABELED|0 /21,331 /0 /0|
|Source-primary SILVER / UNLABELED|199,927 /73|
|Verified physical source identities / verified physical TRAIN identities|73 /0|

Source positions, publisher observations, canonical views, source records and
gradient examples remain distinct. All73 physical identities are first-party
reference-only UNKNOWN receipts; publisher physical/campaign/time identities are
unverified. Independent review PENDING. Auxiliary BRONZE teacher proposals never
replace SILVER or receive training gradients. No GOLD label is manufactured.

Dataset fingerprint:
`3544b3da532b9eacba62daba6e8556199399d3f0f659e5a2095cbd9d16d29863`.
Final config fingerprint:
`55dad3110d0cd25f06623d99b86ca835e4c330b2aafd258fb2f0c3273e2f2f96`.
Split fingerprint:
`e91f1603f6bd89bee97c7443f83ff37ebcf191df577b7f8f4d09435adb604263`.
These are producer outputs, not by themselves an independent validation PASS.
Authoritative consumer gate evidence will be in the new run's `validation.json`
or exact failing gate in `gate-failure.json`/terminal status.

## Gates before any optimizer update

The capped worker validates successful producer **and** watchdog completion,
config/data/code fingerprints, SQLite checks,200K unique source coordinates,
all shard shapes/finite values/slots, old shard preservation and additional shard
copies. It verifies typed privacy metadata, label provenance, ledger/index parity,
the full canonical first-row set and inverse-view weights. Locked split tensors
must equal admitted source tensors/labels and reproduced group role assignments.

The existing checksum-bound weighted audit must cover199,927 rows via60,065
distinct content vectors with1,710,578,139 qualifying original-row pairs. The
consumer does not rerun the whole quadratic source audit. It does exhaustively
check **cross-role** common-contract content-near relations and accepted rows
against known protected full588 content references, alongside protected groups/
views and the completed pilot CAL/EVAL identities. No sealed samples are opened.
Determinism is the producer's repeated metadata finalization plus verified locked
split reproduction, **not** a fresh raw feature-extraction rebuild. Unknown global
raw/campaign lineage and the single exposed publisher domain remain limitations.

Training is blocked on any gate failure. There must be meaningful additional
canonical TRAIN views versus the old2,667-view experiment, not merely a renamed
rerun. Reading CAL/EVAL tensors here only verifies integrity/isolation; no model
predictions, optimization, fitted statistics or threshold selection use them.

## Fixed experiment, separate model

Run ID **`final-local-publisher-200k-20261110-r1`**, private root:
`ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1/`.

Reuse the locked50,696-parameter MLP588→64→64→64→64→8 and seed17. Fresh random
weights/optimizer, partial binary publisher-anomaly objective, smoothing0.005,
family weight0, TRAIN-only inverse class weights. AdamW lr0.001, batch64,
10epochs, group round-robin once per canonical view/epoch, **2,490 updates** and
158,900 presentations if all passes complete. Checkpoint every16steps and final;
final-budget selection only. No hyperparameter search or teacher warm-start.
Normal/anomaly are publisher targets, not verified benign/attack intent; the
seven anomaly logits have no supervised attack-family meaning.

The source config's old authorization/NOT_STARTED text is preserved as a historic
prelaunch snapshot. New `authorization.json` binds that exact config/source/code
to this single explicit user authorization; no source artifact is edited to grant
permission. Before training, `plan.json` locks actual counts, seed, optimizer,
update budget, fingerprints and same-task TRAIN majority/body/window controls.
The old experiment/metrics are retained, not treated as a fair unseen comparison.

Actual preflight is part of the same experiment: commit step1, save/reload exact,
compare the next update in memory including weights/Adam/RNG/order/cursor, commit
step2 and continue. Interrupted step1 resumes that same stream; repeated preflight
at step2 makes no extra update. Atomic checkpoints include model, Adam m/v, scheduler,
step/epoch/cursor, RNG/order, loss history and dataset/config/split bindings.
Missing/corrupt latest evidence blocks rather than silently resetting to step0.
Training does not automatically evaluate when completed.

## Persistence and one-shot semantics

User unit: **`idps-final-local-publisher-200k-20261110-r1.service`**, installed in
`~/.config/systemd/user/`, enabled for `default.target`, `Restart=no`.
It survives Codex exit and is started again by the user service manager after a
reboot/login if no terminal decision exists. No system service, linger setting or
hardware policy is changed. Login/start of the user service manager is required
after reboot if the account does not already have lingering enabled.

`authorization.json`, `one-shot-lock`, atomic `launch-marker.json`, immutable plan
and fixed Run ID prevent a second experiment. Existing active worker/watchdog
units must be reconciled before a continuation. An interrupted nonterminal handoff
can create a new supervised **attempt of the same checkpoint stream**, with matching
bindings. A previous safety stop requires review and blocks automatic restart.
Terminal COMPLETED/FAILED/BLOCKED writes `terminal.json` and disables the unit;
`ConditionPathExists=!…/terminal.json` also prevents a repeated launch. No service
or timer advances to another model, evaluation, deployment or500K processing.

The existing proven pilot supervisor starts one quota-limited worker and one
independent adaptive watchdog, publishes heartbeat/status and kills its own worker
on failure. The watchdog fails closed if supervisor/sensors disappear. CPU ceiling
20% of one core, worker≤8GiB/swap0,4GiB reserve and85/90/93/96°C bands/lower hardware
limits remain. Validation and training share that one supervised worker.

```sh
systemctl --user status idps-final-local-publisher-200k-20261110-r1.service --no-pager
cat ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1/handoff-status.json
cat ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1/status.json
```

`active-attempt.json` identifies current `attempts/train-NN/`: worker log,
services/PIDs, supervisor/worker heartbeats and thermal telemetry. Checkpoints:
`model/latest.json` and immutable generations under `model/checkpoints/`.
Terminal success additionally requires the final reloaded checkpoint and planned
step budget, not a process exit. Private data/weights/logs remain outside public Git.

Targeted tests cover config-gate tampering, cross-role near leakage even with
different group IDs, one-shot terminal/lock behavior, actual step1 interruption/
exact continuation and step2 idempotency. The original tests exposed a continuation
comparison of stale serialized generation metadata; the fix compares real sampler/
RNG state while separately verifying updated model/Adam arrays. No real research
optimizer update happened during that fixture failure.34 relevant tests and Ruff
pass before launch. Actual runtime state must still be read from private evidence.

## Local acceptance remains a separate authorized milestone

After this run terminates and the user requests evaluation, verify the final
checkpoint and report same-task metrics/uncertainty/POST failures under the locked
protocol. Do not infer attack-intent improvement or install the publisher model
into frozen live scoring. Then current live HTTP/Rules/AI/correlation/fallback,
startup/shutdown/recovery and Web regression acceptance remain necessary, using
the existing local runbooks. No Student/Security/Nginx/Suricata/Rules/Policy,
frozen models/thresholds or published releases are changed by this handoff.
