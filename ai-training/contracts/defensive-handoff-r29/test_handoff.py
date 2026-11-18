"""Exercise the new envelope and rights checks with opaque metadata fixtures."""

import json

import handoff
import pytest

from idps_ai.common import PipelineError, atomic_json, file_sha256

with pytest.MonkeyPatch.context() as fixture_path:
    fixture_path.syspath_prepend(str(handoff.HERE.parent / "native-defensive-r28"))
    from test_screen import case as case


@pytest.fixture()
def package(tmp_path, case, monkeypatch):
    plan, _, lineage, bundles, registry, protected_keys = case
    monkeypatch.setitem(handoff.CHECKS, "protected_registry", lambda: (registry, protected_keys))

    def pin(name, value):
        path = tmp_path / name
        atomic_json(path, value)
        return {"file": name, "sha256": file_sha256(path)}

    plan_ref = pin("plan.json", plan)
    summaries = [pin(f"summary-{i}.json", bundle) for i, bundle in enumerate(bundles.values())]
    lineage["plan_sha256"] = plan_ref["sha256"]
    lineage["intake_sha256"] = [ref["sha256"] for ref in summaries]
    grants = [
        {
            "manifest_sha256": bundle["manifest_sha256"],
            "role": plan["campaign_roles"][bundle["campaign"]],
            "permission_ref_sha256": "a" * 64,
            "approved_use": "RESTRICTED_NATIVE_RESEARCH",
        }
        for bundle in bundles.values()
    ]
    rights = {
        "version": "idps-r29-defensive-rights-v1",
        "plan_sha256": plan_ref["sha256"],
        "grants": grants,
    }
    envelope = {
        "version": "idps-r29-defensive-handoff-v1",
        "scope": "EXISTING_DEFENSIVE_CAPTURE",
        "plan": plan_ref,
        "lineage": pin("lineage.json", lineage),
        "rights": pin("rights.json", rights),
        "intake": summaries,
        "protected_partitions": {
            "TEST_SHADOW": {
                "manifest_sha256": "b" * 64,
                "custody_record_sha256": "c" * 64,
                "sealed": True,
            }
        },
    }
    return tmp_path, envelope, pin


def validate(package):
    root, envelope, pin = package
    ref = pin("handoff.json", envelope)
    return handoff.run(root / ref["file"], ref["sha256"])


def test_metadata_bundle_runs_closure_and_never_opens_protected_payload(package):
    result = validate(package)
    assert result["protected_partitions"] == {"TEST_SHADOW": "PIN_REGISTERED_AWAITING_CUSTODIAN"}
    screened = result["development_screen"]
    assert screened["state"] == "ELIGIBLE_FOR_CONTRACT_REVIEW"
    assert screened["request_count"] == 6
    assert not any(screened["formal_canonical_counts"].values())


def test_external_pin_and_tampered_grant(package):
    root, envelope, pin = package
    ref = pin("handoff.json", envelope)
    with pytest.raises(PipelineError, match="PIN_MISMATCH"):
        handoff.run(root / ref["file"], "f" * 64)
    (root / "rights.json").write_text("{}")
    with pytest.raises(PipelineError, match="PIN_MISMATCH"):
        handoff.run(root / ref["file"], ref["sha256"])


def test_validated_rights_must_grant_original_scope_and_role(package):
    root, envelope, pin = package
    rights = json.loads((root / "rights.json").read_text())
    rights["grants"][0]["role"] = "DEV"
    envelope["rights"] = pin("rights.json", rights)
    with pytest.raises(PipelineError, match="SOURCE_PERMISSION_OR_ROLE_NOT_GRANTED"):
        validate(package)


def test_protected_manifest_may_not_reenter_development(package):
    root, envelope, _ = package
    intake = json.loads((root / envelope["intake"][0]["file"]).read_text())
    envelope["protected_partitions"]["TEST_SHADOW"]["manifest_sha256"] = intake["manifest_sha256"]
    with pytest.raises(PipelineError, match="PROTECTED_MANIFEST_REUSE"):
        validate(package)


def test_schema_refuses_external_paths_and_protected_payload_reference(package):
    _, envelope, _ = package
    original = envelope["plan"]["file"]
    envelope["plan"]["file"] = "../plan.json"
    with pytest.raises(PipelineError, match="INVALID_HANDOFF_SCHEMA"):
        validate(package)
    envelope["plan"]["file"] = original
    envelope["protected_partitions"]["TEST_SHADOW"]["file"] = "test.json"
    with pytest.raises(PipelineError, match="INVALID_HANDOFF_SCHEMA"):
        validate(package)
