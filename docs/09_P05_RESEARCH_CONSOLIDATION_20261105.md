# P0.5 — Research consolidation, 05/11/2026

**Technical consolidation is complete. P0 independent validation remains PARTIALLY_COMPLETE: all111 requests still await independent human review. Heavy-workload status: THERMAL_CONTROL_NOT_VERIFIED.**

Machine-readable findings and proposed experiment: [P05_CONSOLIDATION_20261105.json](../ai-training/reports/P05_CONSOLIDATION_20261105.json).
New private evidence: `ai-training/.artifacts/p05_consolidation_20261105/`.
Original P0: [08_P0_DVWA_RESEARCH_20261105.md](08_P0_DVWA_RESEARCH_20261105.md).

No cohort was recollected. No training, threshold selection, frozen encoder/model change, formal-policy change, Web change or sealed-holdout access occurred. The original P0 report and evidence were preserved. Only the AI-owned thermal supervisor and its tests were improved; before-edit copies are in the P0.5 artifact directory.

## 1. Ground Truth: technical checks completed, human review pending

The validator read back receipts, raw response hashes, precommitted intent provenance and application Oracles for all111 requests, using the frozen capture source. The unchanged assessments are:

| Technical evidence tier | Requests |
| --- | ---: |
| Benign workflow with internal semantic Oracle | 59 |
| Internal application-Oracle exploit success | 33 |
| Unsafe-reflection attack attempt, browser outcome unknown | 12 |
| Other receipt-bound attack attempt, outcome unknown | 3 |
| UNKNOWN: planned benign workflow without required Oracle | 4 |

The33 successes remain12 SQLi,9 command injection and12 private-file inclusions. Fifteen are Request-v2 false negatives under the internal lab intent:9 command executions and6 file inclusions. For SQLi, the Oracle uses returned first/surname result fields, not an echoed attack string. For command injection, it checks the command-output `<pre>` region, not a reflected form value. The private-file marker is distinct from the requested pathname.

For all12 XSS cases, the checker additionally restricted HTML parsing to `vulnerable_code_area`, verified the exact unescaped `Hello <payload>` reflection and found script/event-bearing elements in that region. Framework scripts elsewhere in the page are excluded. This verifies unsafe reflection; it does not establish browser execution, bypass of browser controls or harmful impact.

Four intended benign ping cases remain UNKNOWN. The actual saved response has empty command stdout. The recorded application capability set excludes CAP_NET_RAW and has `no-new-privileges`; P0's separate same-image/www-data probe also reports raw-socket permission denial. This supports a lab capability explanation. The exact original shell stderr was not preserved in a request-bound artifact, and the separate probe used a different network namespace. Do not overstate it as a complete reconstruction of each failed invocation, or promote labels after observing predictions. Three `&&` attack chains also have unknown exploit outcomes; they remain attempts, not successes.

A49-case priority package contains:

- All15 missed Oracle-supported successes.
- All12 XSS attempts.
- All4 UNKNOWN.
- 12 stratified benign controls, including both Suricata false positives.
- 6 true-positive controls, including all4 AI-only SQLi and2 jointly detected cases.

The priority queue removes case-number/failure-selection hints and model outputs. The complete technical dossier still covers all111. Reviewer instructions require a real identified human, initial blind decisions, request-bound rationale and subsequent source/Oracle adjudication. There is no independent reviewer presently; **independent review remains PENDING for every request, with zero approved independent labels and zero label changes**. This technical automation is not human verification and is not formal admission.

Artifacts: `analysis-v3/technical-review.json`, `priority-blind-review.jsonl` and `human-review-instructions.json`.

## 2. XSS: numeric privacy filtering removes the payload evidence

The numeric projection imports `SENSITIVE`, which matches `name`; `project_request()` drops that query field before computing numeric syntax. DVWA uses `name` for reflected XSS. The other field, `Submit`, survives, so global query availability does not explain the loss on its own. All48 requests on the XSS route—36 benign and12 attempts—have exactly **one numeric76 view**.

The rich-content branch has a different privacy rule and still retains markup syntax from the `name` value. Thus the payload is not absent from the entire588-feature representation. The two channels disagree about what was observed; the existing output availability is not a complete numeric-channel missingness account.

At unchanged threshold0.8826237917, the12 exposed XSS cases yielded:

| Post-hoc mechanism probe | Above frozen threshold | Score range |
| --- | ---: | --- |
| Original full vector | 0/12 | 0.097–0.312 |
| Only numeric76 replaced with a neutral-key `q` projection; original rich512 retained | 12/12 | 0.986–1.000 |
| Only rich512 replaced with the `q` content; original numeric76 retained | 0/12 | 0.131–0.362 |
| Lexical `void`→`alert`, original `name` key | 0/12 | 0.154–0.554 |

These are tensor/input interventions on exposed data, not actual application requests or new Recall estimates. Renaming a live parameter would change the application's semantics; it is not a deployment workaround. The numeric-only intervention isolates a major functional dependency on the filtered numeric channel. The failure is not adequately explained by the word `void` alone or by a lack of model parameters.

Recommendation for a challenger: derive bounded, coarse security syntax and explicit channel availability without persisting PII or credential values. Preserve the privacy protections. Do not simply remove `name` from the sensitive-key list or feed raw identity text.

Relevant code: `features/request_view.py::project_request`, `data/privacy.py::SENSITIVE`, `features/rich_content.py::rich_request`.

## 3. Command injection: payload signal exists, but header mixing attenuates it

Numeric76 observes method/URI/query, not body. All16 command-route requests share one numeric view, including the4 UNKNOWN. The12 attack bodies are not redacted and contain signal in rich512. Scores are0.543–0.822 with full headers, below the frozen threshold. Removing body makes all12 scores equal0.317. It would therefore be inaccurate to say that the model completely ignores body information.

The encoder places URI, headers and body in one character-hash space and jointly L2-normalizes them. Separate interventions on the12 command attempts show:

| Mechanism probe | Above frozen threshold |
| --- | ---: |
| Original full input | 0/12 |
| Remove headers/boundary n-grams, retain the original full-vector L2 denominator | 5/12 |
| Remove headers and apply the encoder's normal new L2 normalization | 10/12 |

The no-header raw-count norm is about0.427–0.436 times the original norm; renormalization rescales the retained vector by roughly2.3. Both the header-related direction/count changes and the subsequent normalization matter. The decomposition is nonlinear and path-dependent, not a unique causal attribution to individual header tokens or proof of source memorization.

Three uncaptured canonical command-text probes (`;id`, `;whoami`, `;cat` on the private canary) also remain below threshold with full headers. Adding familiar command words alone is not demonstrated as a repair.

No mixed known-label full588 feature views exist in the original cohort. The failures cannot all be blamed on exact full-vector collisions. Numeric-channel collapse and global channel coupling are distinct, demonstrated limitations.

## 4. Header sensitivity and shortcuts: what is and is not established

Previous leave-one-header results remain: removing Cookie or Host alone preserves TP18, removing Content-Type givesTP17, removing User-Agent givesTP14, while removing all headers givesTP27. There is no evidence that a single disposable cookie value explains the miss; values from Cookie/Authorization are excluded by the frozen encoder.

New semantically ordinary header-order controls on all111 requests produced zero decision flips. Sorting headers produced identical scores; reversal changed some scores by at most0.0778. Header ordering is not the primary explanation for the observed failures, although score invariance is incomplete.

**Source-specific shortcut learning remains unproven.** What is established is sensitivity to nuisance/header representation and source-dependent parameter conventions interacting with privacy projection. Demonstrating learned source shortcuts requires label-matched, multi-environment controls. The unchanged P0 domain/weak-label caveats still apply.

A further training-data risk is now explicit:

| Method / internal intent | Count |
| --- | ---: |
| GET benign | 59 |
| GET attack | 36 |
| POST attack | 12 |
| POST UNKNOWN | 4 |

There is no labeled benign POST. Fine-tuning on these cases as if method/body/source were balanced would invite a new shortcut. The sample is an exposed diagnostic set, not a new train/test split or blind acceptance cohort.

## 5. AI versus Suricata

P0's request-bound comparison is retained:4 AI-only attacks,13 rules-only,14 both,17 neither. All4 AI-only detections are SQLi variants outside the existing Boolean/equality signature pattern. SQLi application Oracles support all four. This is actual complementary detection within the cohort, not overall superiority.

The command signature SID1000005 inspects `http.uri`, while this DVWA payload is in POST body. Its0/12 therefore has an identifiable coverage limit different from the AI's representation/decision problem. The two XSS signature misses use `details/ontoggle` and `input/onfocus`, outside the configured tag/event patterns. Suricata catches10 XSS attempts that the model misses.

The comparison still excludes full Rust/app-stateful detection, equal-alert-budget claims and independent-population quality. No score fusion was deployed.

## 6. Thermal investigation and actual control tests

P0's unchanged trace contains58→76→78→92°C before a pause, then54°C followed by94°C after immediate resume; subsequent cycles reach95/96°C. Its supervisor polled once per second, resumed on the first cool sample, changed affinity on process leaders only, and imposed no initial Python kernel quota. The old source and trace substantiate those control shortcomings. The trace does not identify an exclusive heat source, individual BLAS threads or host cooling condition; CPU temperatures also include other applications.

A real, sleeping two-thread probe confirmed that reducing the leader's Linux affinity leaves the existing worker's affinity unchanged. This verifies the OS mechanism relevant to the earlier bug without a CPU stress test.

The AI-owned supervisor now:

- Samples CPU package/core drivers every0.2s; excludes NVMe/GPU sensors.
- Reduces all existing threads and pauses at74°C, or at>=68°C with a rise>=5°C/s.
- Requires continuously<70°C for3s before resuming a proactive pause.
- Terminates on the first>=80°C event without automatic resume.
- Handles SIGTERM and keeps paused containers paused on supervisor error.

Real sleeping-process fault-injection checks verified that SIGSTOP halts heartbeat progress, cooldown permits actual progress again, an injected81°C kills the child without resume, and sensor loss/SIGTERM end the child. Physical CPU readings during these tests were46–48°C. Injected values are software control inputs, not actual measured heating.

A transient systemd scope read back `cpu.max=2500 10000` (0.25 CPU), `memory.max=1073741824` and swap0. The bounded inference diagnostics used that quota, one thread/CPU affinity and10ms pacing; all observed thread affinities wereCPU0. Across monitored P0.5 light stages, actual CPU readings stayed44–52°C. The completed analysis stage used about187 MB peak sampled process-tree RSS and11.27 GB shared-system memory, below the30 GB total-system budget. No thermal pause occurred during analysis.

**FUNCTIONAL_CONTROL_VERIFIED_FOR_LIGHT_PROCESS_GROUP_ONLY. THERMAL_CONTROL_NOT_VERIFIED for heavy workloads.** Physical containment below80°C, uncooperative termination, container pause/recovery, escaped process groups and supervisor SIGKILL watchdog behavior were not certified. No heavy workload or physical heating test ran. This qualification is a required execution boundary, not a production or formal-admission gate.

Artifacts: `thermal-functional-report.json`, `thermal-real-sensors.json`, per-control logs, `analysis-v3-resources/resource-report.json`. Early analysis script failures are preserved separately; only `analysis-v3` completed model diagnostics.

## 7. One proposed challenger experiment

**Design-ready: yes. Independent quality acceptance-ready: no. No training has started.**

Hypothesis: privacy-preserving payload syntax and separate URI/body/header normalization recover evidence currently removed or attenuated, while maintaining benign controls. Test representation before increasing model size.

Use the existing small MLP at approximately50k parameters. Retain the frozen model as an untouched reference. Run one bounded2×2 ablation:

| Arm | Syntax/availability improvement | Separate channel normalization |
| --- | --- | --- |
| C0: refit legacy control | No | No |
| C1 | Yes | No |
| C2 | No | Yes |
| C3 | Yes | Yes |

Use identical training membership, sampling, objective and update budget across arms, with controlled parameter counts. A proposed upper budget is3,072 updates per arm/seed and seeds17/29/43. This is a proposal, not an executable training configuration. Retain at least an untouched frozen reference and C0 to distinguish a representation effect from simply fitting again.

Required evidence for executing/interpreting the experiment:

1. Matched benign and attack POST/form-body examples with valid semantic evidence, preserving UNKNOWN and source/group provenance. The current DVWA sample does not supply labeled benign POST.
2. Safe syntax extraction that passes privacy/credential non-retention checks; do not weaken frozen filters.
3. Fresh application/campaign/time evaluation with both classes and adequate family/hard-negative coverage, separate from calibration. The111 DVWA cases may serve as development regression only. Human adjudication remains pending; weak-label fitting can be explicitly labeled research, but cannot certify independent quality.
4. A conservative bounded compute pilot under actual kernel quota and monitoring before authorizing sustained/heavy training; do not run heavy work under THERMAL_CONTROL_NOT_VERIFIED.

Select each arm's threshold on separate calibration at a predeclared1% research flag budget; no DVWA/evaluation threshold search. Primary endpoint is paired target-family macro sensitivity at those fixed thresholds, with benign counts and cluster uncertainty per environment. A useful advance criterion is>=10pp target macro gain, no>5pp regression on other covered families and observed benign flag fraction<=1% in each evaluation environment, with a consistent direction across seeds. These are research criteria, not population FPR certification.

Stop after the fixed four-arm/three-seed budget. If gains are source-specific, unstable, violate the benign budget or remain statistically inconclusive, report failure/inconclusive and stop; do not extend tuning on the same evaluation. Thermal limit, lost sensors, nonfinite state or memory pressure are immediate execution-stop conditions.

## 8. Preservation and stopping point

Seventeen P0/MVP tests pass, including rapid-rise pause, cooldown and hard-stop decisions. Real light-process checks also pass. Ruff/format/diff checks pass. Nineteen baseline checksums remain unchanged; original P0 handoff/docs remain unchanged; protected Web/contracts/Docker/AI-source/formal-config diff is empty. No Git commit/push/reset or IPS action occurred.

The next decision can now be made from explicit failure mechanisms and a finite experiment proposal. Human review and heavy thermal qualification remain named gaps. No additional data collection, challenger implementation or training was started in P0.5.
