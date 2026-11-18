# R29 defensive data handoff

The envelope groups authorized, already recorded defensive evidence with its frozen role plan. The schema is `handoff.schema.json`. Put all inputs in a restricted directory outside tracked Git files. The custodian supplies the expected envelope SHA-256 through a trusted channel. Keep the underlying grants, review evidence, capture metadata and access logs in the custodian's restricted store.

- `plan` pins the R28 TRAIN/DEV plan with population, sampling strategy, observation profile, cutoff, clock guard and campaign roles fixed before collection or selection.
- `intake` pins one to eight **verified output summaries** from R11 `native-label-audit-v1/intake.py`. R11 validates scoped receipts, semantic review and feature availability. The wrapper consumes those outputs and their externally supplied pins. Give each reviewed summary a separate permission entry.
- `rights` pins a JSON object using the `rights` definition in the schema. Each grant binds an original manifest SHA and exact role to its usage permission record SHA. The approval code is `RESTRICTED_NATIVE_RESEARCH`. A grant establishes the asserted scope of use; the custodian retains the actual license or usage grant and determines its applicability.
- `lineage` pins the R28 audit bound to the same plan, all summary SHAs and the R27 protected registry. Include all scoped roster rows, including unknown and quarantined rows. Carry the evidence for protected overlap, near-edge completeness and cross-domain alias resolution.
- `protected_partitions` can register manifest and custody pins for separately held CAL_FIT, CAL_OP, TEST_SHADOW and TEST_BLOCK. The development envelope has no path to those partitions. The separate T07 evaluator owns preregistration, custody proof, access tracking, unseal and run authorization.

Run from the repository root.

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python \
  ai-training/contracts/defensive-handoff-r29/handoff.py \
  "$handoff_file" "$trusted_envelope_sha256" "$private_result_file"
```

Valid envelopes proceed straight to R28 closure. The result gives candidate views by role and class and component blocking reasons. A valid schema and digests prove integrity within the trusted handoff. They leave semantic accuracy, sampling independence, T02 native export and formal T07 admission to their respective checks.

A pilot needs screened two-class TRAIN and DEV with resolved request identity, causal features and disjoint lineage, followed by native admission. Release evaluation also needs disjoint CAL_FIT, CAL_OP and protected TEST with the population, endpoint family and comparator locked before unseal. See [T07](../../../docs/53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md) and the [R28 plan and lineage format](../native-defensive-r28/README.md).

`reconcile.py` runs the bounded historical recovery described in the report and writes a fresh aggregate JSON file pinned to the evidence read.
