#!/usr/bin/env python3
"""Bounded evidence-ledger inventory, never opens raw/held-out request contents."""

import argparse
import json
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256

ROOT = Path(__file__).resolve().parents[2]


def inventory(capture=None):
    evidence = []

    def read(path):
        p = ROOT / path
        r = json.loads(p.read_text())
        evidence.append({"path": path, "sha256": file_sha256(p)})
        return r

    waf = read("ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2/report.json")
    wa = read("ai-training/.artifacts/autonomous_research_20261104/waf_v2/audit-train-v2.json")
    quality = read("ai-training/reports/DATA_QUALITY_20261031.json")
    p0 = read("ai-training/reports/P0_DVWA_20261105.json")
    glu = read("ai-training/.artifacts/glu207_derivative_20261107/manifest.json")
    ky = read("ai-training/.artifacts/autonomous_research_20261104/kyoushi_s1/slice-audit.json")
    am = read("ai-training/.artifacts/automated_quality_20261104/report-v7.json")
    src = quality["SRBH"]
    rows = [
        {
            "source": "GLU207 frozen train / derivative",
            "frozen_training_rows": 41607,
            "derivative_research_candidates": glu["supervised_candidates"],
            "status_conflict_quarantine": 174,
            "training_unique_float32_views": 41585,
            "raw_HTTP_count": None,
            "native_three_source_training_IDs_previously_attested": 41607,
            "prior_flow_present": 36443,
            "prior_flow_missing": 5164,
            "labels": "Scripted scenario/runner research labels; not independent exploit outcomes",
            "independent_verified": 0,
            "application_Oracle_rows": None,
            "GLU207_compatible": 41607,
            "Request_v2_compatible": "Not interchangeable with request-text corpus",
            "role": "Frozen TRAIN only; no reserved/evaluation data contents opened",
            "limitations": [
                "Historical tx_id not retained",
                "174quarantine retained for history impact",
                "Frozen train is subset of69345prepared fused rows, not additional raw requests",
            ],
        },
        {
            "source": "WAF Data v2 publisher TRAIN",
            "raw_publisher_HTTP_rows": wa["counts"]["publisher_rows"],
            "unique_exact_HTTP_representations": wa["exact_request_representations"],
            "duplicate_rows": wa["exact_duplicate_rows"],
            "raw_label_conflicts": wa["exact_request_label_conflicts"],
            "labeled_publisher_rows": wa["counts"]["publisher_rows"],
            "verified_physical_requests": 0,
            "application_Oracle_rows": 0,
            "independent_verified": 0,
            "label_basis": "Publisher NORMAL/ANOMALOUS, not confirmed attack intent",
            "selected_unique_Request_v2_views": waf["selected_unique_numeric_content_views"],
            "model_train_views": sum(waf["role_class_coverage"]["train"].values()),
            "model_calibration_views": sum(waf["role_class_coverage"]["calibration"].values()),
            "model_development_views": sum(waf["role_class_coverage"]["validation"].values()),
            "unknown_intent": "All publisher rows lack our independent intent verification",
            "GLU207_compatible": 0,
            "role": "Publisher train partition only; internally curated role0/1/2; no publisher test opened",
            "limitations": [
                "Exact template roles disjoint but sampled near cosine cross-role overlaps exist",
                "Upstream physical/campaign/time lineage not supplied",
                "Do not equate publisher anomaly labels to Oracle attack labels",
            ],
        },
        {
            "source": "SR-BH2020",
            "raw_publisher_rows": src["physical_rows_checked"],
            "natural_observation_identities": src["natural_observation_identities"],
            "exact_observation_duplicate_rows": src["duplicate_original_rows"],
            "curated_research_candidates": src["curation"]["decisions"]["accepted_research"],
            "quarantine_rows": src["curation"]["decisions"]["quarantine"],
            "label_basis": "Publisher signature-assisted/manual/semi-automatic annotation; not our independent review",
            "application_Oracle_rows": 0,
            "independent_verified": 0,
            "GLU207_compatible": 0,
            "Request_v2_compatible": "URI-only candidates; body-present excluded from this curation",
            "role": "Exposed development; do not repurpose as blind evaluation",
            "limitations": [
                "Not an independent source from WAMM derivative",
                "Curated rows are not full-text or model-view unique counts",
                "Temporal source/class support limits in existing admission remain",
            ],
        },
        {
            "source": "WAMM numeric research derivative",
            "raw_publisher_rows": am["data_accounting"]["raw_publisher_rows"],
            "unique_HTTP_text_representations": am["data_accounting"][
                "unique_http_text_representations"
            ],
            "numeric_views_after_quarantine_overlap": am["data_accounting"][
                "numeric_views_after_quarantine_and_exposed_overlap"
            ],
            "label_tiers": am["label_tiers"],
            "GLU207_compatible": 0,
            "Request_v2_compatible": "76numeric view, not equivalent to588URI/body/header contract",
            "role": "Train-only publisher fitting diagnostic; no independent evaluation",
            "limitations": [
                "SR-BH upstream derivative, do not sum with SRBH as novel requests",
                "Numeric feature views cannot recover raw payload or full body",
            ],
        },
        {
            "source": "Kyoushi scenario1 Apache slice",
            "HTTP_access_records": ky["counts"]["access_lines"],
            "unique_method_URI_lines": ky["unique_method_uri_request_lines"],
            "publisher_attack_parseable": ky["counts"]["publisher_attack_parseable"],
            "unknown_unlabeled_parseable": ky["counts"]["unlabeled_unknown_parseable"],
            "benign_Oracle_labels": 0,
            "independent_verified": 0,
            "GLU207_compatible": 0,
            "Request_v2_compatible": "Partial Apache fields; no complete body/header/Student contract",
            "role": "Single-source/scenario research evidence, not certified benign or cross-domain evaluation",
            "limitations": [
                "Positive-only publisher label support; unlabeled is UNKNOWN",
                "Range/CRC slice verification, not fullZIPSHA",
            ],
        },
        {
            "source": "P0 DVWA primary / P0.5",
            "request_receipts": p0["primary_cohort_requests"],
            "unique_request_IDs": p0["primary_unique_request_ids"],
            "unique_method_URL_body": p0["primary_unique_method_url_body_representations"],
            "unique_frozen_Request_v2_views": p0["primary_unique_feature_views"],
            "intent_counts": p0["lab_intent_counts"],
            "benign_application_Oracle": 59,
            "exploit_success_internal_Oracle": 33,
            "unsafe_reflection_execution_unknown": 12,
            "attempt_receipt_outcome_unknown": 3,
            "UNKNOWN": 4,
            "independent_verified": 0,
            "GLU207_compatible": 0,
            "Request_v2_compatible": 111,
            "role": "Exposed DEVELOPMENT; never new blind evaluation",
            "limitations": [
                "Earlier capture attempt is repeated representation, not111additional novel requests",
                "No labeled benignPOST; do not use as method-balanced fit",
            ],
        },
    ]
    historical = read("ai-training/reports/GENERALIZATION_20261030.json")
    profile = read("ai-training/reports/REQUEST_PROFILE_20261030.json")
    attacks = read("ai-training/reports/ATTACK_EVIDENCE_20261101.json")
    org = read("ai-training/reports/GENERALIZATION_QUALITY_20261101.json")["Organization_X"]
    soc = attacks["data"]["new_source"]["structural_audit"]
    mod = attacks["continuation_20261101"]["modsec_wp"]
    rows.extend(
        [
            {
                "source": "CSIC2010 transcript benchmark",
                "raw_transcript_requests_last_audited": historical["data"]["csic"]["raw_requests"],
                "unique_observable_HTTP_identities_last_audited": historical["data"][
                    "csic_quality"
                ]["unique_observable_request_identities"],
                "source_records": historical["data"]["csic_quality"]["source_records"],
                "independent_verified": 0,
                "application_Oracle_rows": 0,
                "GLU207_compatible": 0,
                "role": "Only original normal TRAIN may be used for research; public original test remains exposed evaluation, never moved tofit",
                "limits": [
                    "Publisher anomaly is not verified attack intent",
                    "Historical metadata only read now, not raw public test or sealed data",
                    "626request identities cross originaltrain/test; view collisions and body omission documented",
                ],
            },
            {
                "source": "PKDD2007 flattened WebRequests mirror",
                "historical_metadata_files": next(
                    x["files"] for x in profile["public_sources"] if x["name"].startswith("PKDD")
                ),
                "independent_verified": 0,
                "application_Oracle_rows": 0,
                "GLU207_compatible": 0,
                "role": "Original train normal only for research; test not reused forfit",
                "limits": [
                    "No context/campaign/time or attack-location fidelity",
                    "Metadata counts not additional captured physical requests",
                ],
            },
            {
                "source": "OrganizationX access logs",
                "distinct_complete_log_observations_last_audited": org[
                    "previous_verified_distinct_log_observations"
                ],
                "intent": "UNKNOWN",
                "independent_verified": 0,
                "application_Oracle_rows": 0,
                "GLU207_compatible": 0,
                "role": "Unlabeled observability only; not benign bydefault",
                "limits": [
                    "Publisher unmatched-to-normal or pattern labels are not per-request semantic evidence"
                ],
            },
            {
                "source": "SOC-MLD",
                "raw_access_lines": soc["counts"]["raw_access_lines"],
                "parseable_HTTP_observations": soc["counts"]["parseable_http_observations"],
                "distinct_complete_log_observations": soc["counts"][
                    "distinct_complete_log_observations"
                ],
                "unique_partial_method_URI_UA": soc["counts"][
                    "distinct_method_target_user_agent_representations"
                ],
                "curated_publisher_rows": soc["curated"]["dataset"]["rows"],
                "request_bound_Oracle_labels": 0,
                "independent_verified": 0,
                "GLU207_compatible": 0,
                "role": "Quarantined pending request-bound intent review",
                "limits": soc["limits"],
                "leakage": {
                    "shared_attack_instance_ids": 38,
                    "affected_originaltrain_test_rows": 3066,
                },
            },
            {
                "source": "ModSec-WP",
                "publisher_rows": mod["publisher_rows"],
                "distinct_transaction_ids": mod["distinct_transaction_ids"],
                "distinct_HTTP_text_representations": mod["distinct_request_representations"],
                "duplicate_rule_rows": mod["repeated_transaction_rows"],
                "conflicting_transaction_ids": mod["conflicting_transaction_ids"],
                "independent_verified": 0,
                "application_Oracle_rows": 0,
                "GLU207_compatible": 0,
                "role": "Publisher/mixed annotation research only; not Oracle groundtruth",
                "limits": [mod["limitation"]],
            },
            {
                "source": "Reserved/sealed datasets and URL/flow-only sources",
                "raw_HTTP_request_count": "UNKNOWN_OR_NOT_APPLICABLE",
                "role": "NOT_OPENED_OR_NOT_REQUEST_LEVEL",
                "GLU207_eligible_for_this_milestone": 0,
                "Request_v2_eligible_for_this_milestone": 0,
                "limits": [
                    "No count inferred from file count, row count in flow tables or reserved source title",
                    "Existing release/catalog metadata retained; no sealed content accessed",
                ],
            },
        ]
    )
    if capture:
        p = Path(capture)
        r = json.loads(
            (
                p / ("capture.json" if (p / "capture.json").exists() else "report-corrected.json")
            ).read_text()
        )
        evidence.append(
            {
                "path": str(
                    p
                    / ("capture.json" if (p / "capture.json").exists() else "report-corrected.json")
                ),
                "sha256": file_sha256(
                    p
                    / ("capture.json" if (p / "capture.json").exists() else "report-corrected.json")
                ),
            }
        )
        rows.append(
            {
                "source": "Fresh DVWA + Juice75cohort",
                "request_receipts": r.get("requests_sent", r.get("physical_receipts")),
                "intent_counts": r["intent_counts"],
                "outcome_counts": r.get("outcome_counts", r.get("outcomes")),
                "independent_verified": 0,
                "GLU207_compatible": 0,
                "Request_v2_raw_input_eligible": r.get("requests_sent", r.get("physical_receipts")),
                "role": "Predeclared roles; actual leakage-safe eligibility audited separately",
                "label_basis": "Precommitted intent + exact receipts + application semantics; independent review PENDING",
            }
        )
    return {
        "schema_version": "research-inventory-1",
        "scope": "Bounded existing evidence ledgers plus new capture; not raw20GB reread or global distinct-request census",
        "global_raw_physical_HTTP_count": "UNKNOWN; publisher rows, fused views, multiple copied captures and overlapping derivatives cannot be summed",
        "global_unique_requests": "UNKNOWN without cross-corpus full physical identity lineage",
        "global_independent_human_verified_labels": 0,
        "formal_admitted_count_changed": False,
        "datasets": rows,
        "accounting_freshness": "Existing source counts are hash-bound historical audit metadata; only fresh75receipts were directly reverified now. No new all-source raw census or certification.",
        "sealed_holdout": "NOT_OPENED; not enumerated or scored",
        "evidence": evidence,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    atomic_json(a.output, inventory(a.capture))
