# R28 defensive evidence screening

R28 screens existing reviewed URI76 intake summaries before T02 export and T07 admission. It operates on opaque request, receipt and representation digests. The source summary is the output of the existing R11 `native-label-audit-v1/intake.py` verification, which binds a capture manifest, receipt ledger and independent review. Keep the original capture and review artifacts in restricted storage.

The caller supplies SHA-256 pins for the frozen plan, lineage audit and each verified intake summary through the custodian's trusted channel. Byte integrity protects the received assertions. Semantic correctness, reviewer independence, sampling independence and the completeness of near or protected-role comparisons still depend on custody evidence.

Run from the repository root with the project environment.

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python \
  ai-training/contracts/native-defensive-r28/screen.py "$screen_output" \
  --plan "$frozen_plan" "$frozen_plan_sha" \
  --lineage "$lineage_audit" "$lineage_audit_sha" \
  --intake "$verified_intake_summary" "$verified_intake_summary_sha"
```

- The plan uses version `idps-r28-defensive-lineage-v1`, scope `EXISTING_DEFENSIVE_CAPTURE`, task `ATTACK_INTENT`, `cutoff_ns` 1000000000, `guard_ns` 1000000, `population_sha256`, `sampling_sha256`, `profile_sha256` and `campaign_roles`. Freeze the population, sampling plan, compatible URI76 observation profile and campaign roles before acquisition. Existing `DEVELOPMENT` stays DEV. A TRAIN entry requires the original quarantined TRAIN-candidate role.
- The lineage audit uses the same version and binds `plan_sha256`, `profile_sha256`, `r27_registry_sha256` and `intake_sha256` for the complete bundle set. It carries `cross_domain_resolved`, `near_complete` and `protected_role_screen_complete` from the accountable audit. Incomplete checks block candidate readiness. The R27 registry is checked against its published pin locally.
- The audit `rows` object covers every scoped request, including quarantined and unknown labels. Each key is the opaque `request_key` and its entry contains `receipt_sha256`, `material_template`, `session`, `actor_alias` (null if inapplicable), `actor_scope_resolved`, `physical_aliases`, `verified_near_keys` and `protected_overlap`. Use common alias domains only after resolution. Every near-edge endpoint must be in the audited roster. A protected link outside the roster uses `protected_overlap`. Keep the evidence supporting these statements with the audit.
- The output counts candidate unique views by role and class. Any exact-view label conflict, physical alias duplication, protected link or cross-role link blocks the affected connected component. Unknown and rejected rows still participate in closure. `ELIGIBLE_FOR_CONTRACT_REVIEW` means both classes have candidate views in both roles. T02 serialization, formal admission, independent cluster support, CAL/TEST and score evaluation remain separate steps under T07.

The separate `inventory.py` command writes a fresh private JSON report of the default defensive handoff location and a bounded set of historical source summaries. Its historical counts carry their original scopes.
