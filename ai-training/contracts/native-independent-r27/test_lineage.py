import pytest
from lineage import close


def row(key, role, campaign, view, population="TARGET", eligible=True):
    return {
        "key": key,
        "role": role,
        "campaign": campaign,
        "session": campaign + "-session",
        "actor_alias": campaign + "-actor",
        "material_template": campaign,
        "primary_view_sha256": view,
        "task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
        "ABI": "context22",
        "profile": "lab",
        "population": population,
        "identity_verified": True,
        "actor_scope_resolved": True,
        "eligible": eligible,
        "label": "BENIGN_VERIFIED",
    }


def test_same_primary_view_joins_roles_even_for_rejected_target():
    a = row("a", "TRAIN", "first", "same")
    bridge = row("bridge", "TRAIN", "first", "other", eligible=False)
    b = row("b", "DEV", "second", "other")
    result = close([a, bridge, b])
    assert len(result) == 1 and result[0]["blocked"]
    assert "CROSS_ROLE_LINEAGE" in result[0]["reasons"]


def test_setup_retains_custody_but_is_not_a_primary_task_feature():
    rows = [
        row("a", "TRAIN", "first", "one"),
        row("a-setup", "TRAIN", "first", None, "SESSION_SETUP_CONTROL"),
        row("b", "DEV", "second", "two"),
        row("b-setup", "DEV", "second", None, "SESSION_SETUP_CONTROL"),
    ]
    result = close(rows)
    assert len(result) == 2 and not any(r["blocked"] for r in result)
    rows[1]["verified_near_keys"] = ["b-setup"]
    assert close(rows)[0]["blocked"]  # never suppress an actually verified bridge


def test_physical_aliases_unknown_mapping_and_protection_fail_closed():
    a = row("a", "TRAIN", "first", "one")
    b = row("b", "DEV", "second", "two")
    a["physical_aliases"] = b["physical_aliases"] = ["same-request"]
    assert close([a, b])[0]["blocked"]
    a["physical_aliases"] = []
    b["physical_aliases"] = []
    a["actor_scope_resolved"] = False
    assert any("UNRESOLVED_IDENTITY_OR_ALIAS_DOMAIN" in c["reasons"] for c in close([a, b]))
    assert any("PROTECTED_ROLE_DOMINANCE" in c["reasons"] for c in close([a, b], protected=["b"]))


def test_primary_label_conflict_is_quarantined():
    a = row("a", "TRAIN", "first", "same")
    b = row("b", "TRAIN", "first", "same")
    b["label"] = "ATTACK_VERIFIED"
    assert close([a, b])[0]["reasons"] == ["CONFLICTING_PRIMARY_VIEW_LABELS"]


def test_new_guest_or_seed_does_not_remove_material_workflow_bridge():
    a = row("a", "TRAIN", "guest-one", "view-one")
    b = row("b", "DEV", "guest-two", "view-two")
    a["material_template"] = b["material_template"] = "SAME_POLICY_AND_WORKFLOW"
    assert close([a, b])[0]["reasons"] == ["CROSS_ROLE_LINEAGE"]
    with pytest.raises(ValueError):
        close([a, a])
