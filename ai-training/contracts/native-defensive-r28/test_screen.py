"""Metadata fixtures exercise lineage without creating or replaying any traffic."""

import copy
import hashlib

import pytest
from screen import INTAKE, VERSION, read_pin, screen

from idps_ai.common import PipelineError


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture()
def case():
    roles = {"campaign-a": "TRAIN", "campaign-b": "DEV"}
    profile = sha("observation profile")
    plan = {
        "version": VERSION,
        "task": "ATTACK_INTENT",
        "scope": "EXISTING_DEFENSIVE_CAPTURE",
        "cutoff_ns": 1_000_000_000,
        "guard_ns": 1_000_000,
        "population_sha256": sha("population"),
        "sampling_sha256": sha("sampling"),
        "profile_sha256": profile,
        "campaign_roles": roles,
    }
    audit = {
        "version": VERSION,
        "plan_sha256": sha("plan"),
        "r27_registry_sha256": sha("role registry"),
        "profile_sha256": profile,
        "cross_domain_resolved": True,
        "near_complete": True,
        "protected_role_screen_complete": True,
        "rows": {},
    }
    bundles = {}
    for campaign, role in roles.items():
        requests = []
        for index, label in enumerate(("BENIGN_VERIFIED", "ATTACK_VERIFIED", "UNKNOWN")):
            request = sha(f"{campaign}-{index}")
            receipt = sha(f"receipt-{request}")
            requests.append(
                {
                    "request_key": request,
                    "label": label,
                    "mask": "NSA",
                    "uri76_sha256_at_cutoff": sha(f"vector-{request}") if index < 2 else None,
                    "receipt_sha256": receipt,
                    "disposition": "REVIEW_FOR_LINEAGE" if index < 2 else "QUARANTINE",
                }
            )
            audit["rows"][request] = {
                "receipt_sha256": receipt,
                "material_template": sha(f"template-{campaign}"),
                "session": sha(f"session-{campaign}"),
                "actor_alias": None,
                "actor_scope_resolved": True,
                "protected_overlap": False,
                "physical_aliases": [],
                "verified_near_keys": [],
            }
        bundles[sha(campaign)] = {
            "version": INTAKE,
            "source_role": "DEVELOPMENT"
            if role == "DEV"
            else "TRAIN_RESEARCH_CANDIDATE_QUARANTINED",
            "campaign": campaign,
            "boot_scope": f"boot-{campaign}",
            "manifest_sha256": sha(f"manifest-{campaign}"),
            "review_sha256": sha(f"review-{campaign}"),
            "receipts_sha256": sha(f"receipts-{campaign}"),
            "requests": requests,
        }
    audit["intake_sha256"] = sorted(bundles)
    return plan, audit["plan_sha256"], audit, bundles, audit["r27_registry_sha256"], set()


def test_complete_fixture_has_candidates_without_formal_admission(case):
    result = screen(*case)
    assert result["state"] == "ELIGIBLE_FOR_CONTRACT_REVIEW"
    assert result["request_count"] == 6
    assert result["labels_before_lineage"]["UNKNOWN"] == 2
    assert result["structural_components"] == 2
    assert result["candidate_unique_views_by_role_and_class"]["TRAIN"] == {
        "BENIGN_VERIFIED": 1,
        "ATTACK_VERIFIED": 1,
    }
    assert not any(result["formal_canonical_counts"].values())


@pytest.mark.parametrize(
    "flag", ["cross_domain_resolved", "near_complete", "protected_role_screen_complete"]
)
def test_unknown_clearance_is_fail_closed(case, flag):
    case[2][flag] = False
    result = screen(*case)
    assert result["state"] == "BLOCKED"
    assert result["missing_clearance"] == [flag]
    assert all(
        count == 0
        for c in result["candidate_unique_views_by_role_and_class"].values()
        for count in c.values()
    )


def test_rejected_rows_still_bridge_cross_role_near_lineage(case):
    audit = case[2]
    a, b = [bundle["requests"][-1]["request_key"] for bundle in case[3].values()]
    audit["rows"][a]["verified_near_keys"] = [b]
    result = screen(*case)
    assert result["state"] == "BLOCKED"
    assert result["structural_components"] == 1
    assert result["blocked_component_reasons"] == {"CROSS_ROLE_LINEAGE": 1}


def test_alias_to_r27_dev_protects_entire_component(case):
    key = next(iter(case[2]["rows"]))
    protected = sha("R27 DEV request")
    case[2]["rows"][key]["physical_aliases"] = [protected]
    case[-1].add(protected)
    result = screen(*case)
    assert result["state"] == "BLOCKED"
    assert result["blocked_component_reasons"] == {"PROTECTED_ROLE_DOMINANCE": 1}
    assert sum(result["candidate_unique_views_by_role_and_class"]["TRAIN"].values()) == 0


def test_alias_to_other_roster_key_cannot_increase_support(case):
    a, b = list(case[2]["rows"])[:2]
    case[2]["rows"][a]["physical_aliases"] = [b]
    result = screen(*case)
    assert result["blocked_component_reasons"] == {"DUPLICATE_PHYSICAL_ALIAS": 1}


def test_mixed_exact_vector_across_bundles_blocks_both_roles(case):
    a, b = list(case[3].values())
    a["requests"][0]["uri76_sha256_at_cutoff"] = b["requests"][1]["uri76_sha256_at_cutoff"]
    result = screen(*case)
    assert result["blocked_component_reasons"] == {
        "CROSS_ROLE_LINEAGE": 1,
        "CONFLICTING_PRIMARY_VIEW_LABELS": 1,
    }


def test_preserve_development_role_and_reject_receipt_rebinding(case):
    changed = copy.deepcopy(case)
    changed[0]["campaign_roles"]["campaign-b"] = "TRAIN"
    with pytest.raises(PipelineError, match="INELIGIBLE_INTAKE"):
        screen(*changed)
    case[2]["rows"][next(iter(case[2]["rows"]))]["receipt_sha256"] = sha("forged receipt")
    with pytest.raises(PipelineError, match="INVALID_REQUEST_LINEAGE_EVIDENCE"):
        screen(*case)


def test_incomplete_lineage_and_unresolved_near_edge_fail(case):
    changed = copy.deepcopy(case)
    changed[2]["rows"].pop(next(iter(case[2]["rows"])))
    with pytest.raises(PipelineError, match="INCOMPLETE_OR_DUPLICATE"):
        screen(*changed)
    case[2]["rows"][next(iter(case[2]["rows"]))]["verified_near_keys"] = [sha("absent")]
    with pytest.raises(PipelineError, match="UNRESOLVED_NEAR_EDGE"):
        screen(*case)


def test_pinned_reader_rejects_tampering_symlink_and_sealed_role(tmp_path):
    document = tmp_path / "input.json"
    document.write_text("{}")
    assert read_pin(document, sha("{}")) == {}
    with pytest.raises(PipelineError, match="PIN_MISMATCH"):
        read_pin(document, sha("[]"))
    link = tmp_path / "link.json"
    link.symlink_to(document)
    with pytest.raises(PipelineError, match="SYMLINK_INPUT"):
        read_pin(link, sha("{}"))
    (tmp_path / "seal.json").write_text('{"role":"sealed_test"}')
    with pytest.raises(PipelineError, match="Sealed holdout"):
        read_pin(document, sha("{}"))
