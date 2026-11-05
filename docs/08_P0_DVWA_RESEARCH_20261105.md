# P0 — Prospective DVWA request research, 05/11/2026

**Milestone: PARTIALLY_COMPLETE. Study execution: COMPLETE. Independent semantic review: PENDING.**

The experiment produced new request-bound evidence, frozen-model predictions and a real-packet HTTP-signature comparison. Independent-population Recall/FPR remain unestablished. Formal admission is not a completion prerequisite here and remains zero.

Machine-readable handoff: [P0_DVWA_20261105.json](../ai-training/reports/P0_DVWA_20261105.json).
Private artifacts: `ai-training/.artifacts/p0_dvwa_20261105_1520/`.

## Execution and provenance

DVWA was selected as a PHP/MariaDB application different from the previous Student/Juice evaluations. The official [DVWA compose](https://github.com/digininja/DVWA/blob/master/compose.yml) supplies the image/configuration conventions. Images were pinned in the capture plan:

- DVWA: `ghcr.io/digininja/dvwa@sha256:167b609f577e6d3161bbbfc1189f72549e9ce62cf32eb200050492c3dad3395c`.
- MariaDB: `public.ecr.aws/docker/library/mariadb@sha256:6c65a843396dc6c78dd0da19eccaa0a91d25d9d26a4c2afcb75010ac3f59f5ea` (public mirror after Docker Hub DNS failure).

Rootless containers ran on an internal Podman network, exposing only `127.0.0.1:14280`. The gateway used `127.0.0.1:14281`. The app and DB each had a 1 GiB memory ceiling and initially two CPU quotas; no production stack was started or changed. App source snapshots, fixture identities, a private canary, cases, randomized order, intent rules and image provenance were committed to `capture-final/plan.json` before cohort traffic. No model was loaded during capture.

The initial bootstrap failed before any cohort request. A second attempt captured 111 requests but its eth0-only capture was empty and final chmod failed on a tcpdump-owned file. That attempt and its source are preserved in `capture-attempt2/`. The final replacement used new physical request IDs, `any` interface and rootless-owned tcpdump output. **222 cohort HTTP requests were sent across the two completed attempts; there are only 111 distinct method/URL/body representations across them.** Only the final 111 are evaluated. Six setup HTTP requests per completed capture are excluded; the first failed bootstrap's setup count is not fully accounted. No attempt was fitted or used to select thresholds.

## Ground Truth evidence

| Final cohort unit | Count |
| --- | ---: |
| Physical requests / distinct request IDs | 111 / 111 |
| Distinct method/URL/body representations | 111 |
| Distinct full frozen feature views | 86 |
| Lab benign with semantic Oracle | 59 |
| Precommitted, receipt-bound attack attempts | 48 |
| UNKNOWN | 4 |
| Independent human reviewed labels | 0 |

SQLi Oracles checked injected constant rows or all five fixture identities against a pre-capture DB snapshot. Command injection checked unique stdout canaries. File inclusion checked a private non-public file canary. There were **12 SQLi + 9 command + 12 file-inclusion Oracle-supported successes**. All 12 XSS attempts produced unsafe reflection; browser execution was not tested, so their exploit outcome remains unknown.

The four intended benign ping workflows have empty stdout and remain UNKNOWN. A separate probe on the same pinned image found `/usr/bin/ping` present but denied a raw socket under `www-data` and `no-new-privileges`. Do not silently call these true negatives or interpret failed `&&` command chains as successful exploits.

All 111 receipts and semantic Oracle results were recomputed from persisted request/response files by the verification program, **not an independent human reviewer**. Ground Truth is still collector-controlled internal lab evidence. The reviewer package is `evaluation/review-package.json`; `blind-review.jsonl` omits model predictions and planned labels, and `review-unblind-key.jsonl` must be kept separate during the initial review. It is a research package, not a formal evidence-v2 admission attestation. Raw headers include disposable lab session material; all artifacts are private.

## Frozen model and HTTP-signature results

Request v2 kept threshold `score > 0.8826237916946411`. No fitting or tuning occurred. UNKNOWN is excluded and separately counted; no collision/label-dependent quarantine removed difficult evaluation cases.

| Request v2 | TP | FN | FP | TN |
| --- | ---: | ---: | ---: | ---: |
| SQLi | 12 | 0 | 0 | 20 |
| XSS | 0 | 12 | 0 | 36 |
| Command injection | 0 | 12 | 0 | 0 |
| File inclusion/path traversal | 6 | 6 | 0 | 3 |
| Total | **18** | **30** | **0** | **59** |

The descriptive lab sensitivity is 18/48 = 37.5%; normal flag fraction is 0/59. These are not independent-population Recall/FPR. The descriptive IID two-sided 95% upper bound for 0/59 is about 6.06%, and correlation makes an IID population interpretation inappropriate. Command-family benign FPR cannot be estimated because all four planned benign cases remain UNKNOWN.

Full scanning of the pinned WAF publisher train split (1,924,461 rows) found zero exact method/URL/body overlaps and zero occurrences of the evaluated exact routes. The model train tensor had zero exact feature-view or safe-template overlaps. A 512-view content similarity probe found no pairs at cosine >=0.995. This establishes scoped novelty, not exhaustive semantic decontamination or absence of upstream DVWA patterns. No sealed data was read.

The final real PCAP has 1,110 packets with zero tcpdump kernel drops. Suricata 8.0.3 decoded 111 HTTP transactions, all bound through `X-Request-Id` request headers; HTTP alerts were joined by flow/transaction IDs. Unchanged repository HTTP SIDs 1000002–1000009 produced **TP27/FN21/FP2/TN57**. The SYN-rate SID1000001 was reported but excluded from this predeclared HTTP semantic baseline.

- AI-only attacks: 4 SQLi cases.
- HTTP-rules-only attacks: 13.
- Both: 14.
- Neither: 17.

The two rule false positives were legitimate name text `union select from where` and `../../ in documentation`. This is measurable complementary detection on the lab cohort. It is not the complete Rust/application-rule system, an equal-alert-budget comparison, a fusion deployment or independent acceptance.

GLU207 was not scored: this app does not supply the actual Student/Nginx/Suricata fused 207-feature causal contract. No fake/padded features were created.

## Observability and post-hoc diagnostics

The missingness diagnostic, specified before inference, changed full-header TP18 to headers-missing TP27, including command TP0/12 to TP10/12. Dropping only body did not change the aggregate confusion at the frozen threshold. There were no mixed known-label full feature views in this cohort, so its full-view misses cannot all be attributed to exact feature collisions.

An explicitly post-hoc, separately stored leave-one-header diagnostic yielded TP18 without Cookie, TP17 without Content-Type, TP14 without User-Agent, TP18 without Host and TP27 with no headers. This demonstrates representation/header sensitivity. It does not prove its precise cause or justify stripping headers in deployment. These results are exposed development evidence for designing a subsequent challenger.

Fifteen of the 33 Oracle-supported SQLi/command/file successes were missed by the full-input model: nine command injections and six file inclusions. These and all 12 XSS misses are the highest-value review/error-analysis cases.

## Resources and thermal limitations

Trusted `coretemp` package/core readings were used. The shared system budget was 30,000,000,000 bytes with a 2 GB reserve and available-memory checks, not a dedicated 30 GB AI allocation.

- Supervised-stage CPU temperature: **50 / 54.78 / 96°C** minimum / time-weighted mean / maximum of the package/core maximum at each sample. Authoring gaps are excluded.
- Initial supervisor: six thermal pauses/resumes and three reduction events across pulls/evaluation. It reacted, but one-second sampling and immediate resume admitted unacceptable repeated spikes. This is preserved in original logs/source; no claim of maintaining <80°C is made.
- Fixed supervisor: 0.2-second sampling, proactive pause at74°C, reduction across all existing Linux threads, continuous <70°C for3 seconds before resume, abort after a second80°C event. The follow-up one-thread paced diagnostic ran **51–64°C**, without pauses. Tests cover actual signal decisions through fault injection; no heavy thermal stress certification was attempted.
- Peak shared-system RAM (`MemTotal - MemAvailable`): **11.68 GB**. Peak sampled Python process-tree RSS: **415 MB**, excluding detached container processes. Container peak RSS was not measured separately; its memory contributes to the system reading.
- Observed system CPU peak:69.2% during image work; capture and original evaluation averaged about8.13% each. Other applications are included; these percentages cannot be attributed exclusively to AI.
- Main capture:15.27s; evaluation including scan/pauses:12.16s; follow-up diagnostic:8.66s. Full-input predictor+feature p50/p95:0.506/0.591ms on this small warm run; not a sustained serving benchmark.
- Hardware throttle counter delta was not measured. Sensor updates and software reaction cannot guarantee absence of spikes.

See `resource-summary.json` and the individual stage `samples.jsonl` files.

## Verification, preservation and next decision

`verification.json`: 111 request receipts and Oracles reverified; all19 protected baseline/spec/checkpoint/threshold/manifest files unchanged; Git HEAD unchanged; Student/Security/contracts/Docker/formal-policy diff empty; lab containers and network absent. No sealed holdout, training, champion selection, deployment, IPS action or Git mutation occurred. Fifteen targeted P0/MVP tests pass; full training tests were not rerun.

The bounded experiment is finished. P0 remains **PARTIALLY_COMPLETE** because genuine independent semantic adjudication is pending, not because of formal admission or production requirements. The next task is to review this existing111-request package, prioritizing the15 missed Oracle-supported successes,12 XSS cases and4 UNKNOWN. The evidence already supports designing a bounded body/header robustness challenger with matched benign workflows and a fresh evaluation cohort. It does not support enlarging GLU, retraining frozen models, changing thresholds on these111 requests, or stripping headers for deployment. No next milestone has been started.

## Reproduction entry points

Use the frozen per-run source copies for exact evidence reproduction. Current scripts include subsequent cleanup and thermal fixes. Every execution requires new output directories and a unique run ID; do not overwrite the existing cohort or reuse it as a blind holdout.

```bash
# Capture a new isolated instance; prerequisites: pinned images and CPU sensors.
ai-training/.venv/bin/python -B ai-training/scripts/p0-thermal-run.py \
  --output NEW_RESOURCE_DIR \
  --containers p0-dvwa-repro-unique-app p0-dvwa-repro-unique-db -- \
  ai-training/.venv/bin/python -B ai-training/scripts/p0-dvwa-capture.py \
  --run-id p0-dvwa-repro-unique --output NEW_CAPTURE_DIR

# Evaluate frozen Request v2; consumes only new cohort and publisher train data.
ai-training/.venv/bin/python -B ai-training/scripts/p0-thermal-run.py \
  --output NEW_EVAL_RESOURCE_DIR -- \
  ai-training/.venv/bin/python -B ai-training/scripts/p0-request-evaluate.py \
  --capture NEW_CAPTURE_DIR --output NEW_EVALUATION_DIR

# Compare unchanged HTTP signatures on the real captured packets.
ai-training/.venv/bin/python -B ai-training/scripts/p0-thermal-run.py \
  --output NEW_RULE_RESOURCE_DIR -- \
  ai-training/.venv/bin/python -B ai-training/scripts/p0-suricata-compare.py \
  --capture NEW_CAPTURE_DIR --evaluation NEW_EVALUATION_DIR --output NEW_RULE_DIR
```
