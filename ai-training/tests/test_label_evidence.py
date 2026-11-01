import copy
import json

import pytest

from idps_ai.common import PipelineError, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.label_evidence import audit_label_evidence, iter_evidence_decisions


def review_fixture(tmp_path, prepared):
    directory = tmp_path / "review"
    directory.mkdir()
    manifest = verify_dataset(prepared)
    actual = list(iter_rows(prepared / "requests.parquet"))
    attack = next(r for r in actual if r["label"] == 1)
    benign = next(r for r in actual if r["label"] == 0)
    # Deliberately artificial evidence, exclusively a unit-test fixture.
    for name in ("test-only", "semantic-test-only"):
        (directory / (name + ".txt")).write_text("TEST FIXTURE, NOT REAL LABEL EVIDENCE " + name)
    decisions = []
    for row in (attack, benign):
        kinds = ["request_capture", "intent_provenance", "independent_semantic_review"]
        if row["label"]:
            kinds.append("application_oracle")
        decisions.append(
            {
                "event_key": row["event_key"],
                "label": row["label"],
                "intent": "attack" if row["label"] else "benign",
                "attack_family": row["attack_family"],
                "review_status": "approved",
                "exploit_outcome": "failed" if row["label"] else "not_applicable",
                "evidence": [
                    {
                        "file": "test-only.txt",
                        "sha256": file_sha256(directory / "test-only.txt"),
                        "kind": k,
                        "event_key": row["event_key"],
                        "dataset_sha256": manifest["dataset_sha256"],
                    }
                    for k in kinds
                ],
            }
        )
    unknown = next(
        r for r in actual if r["event_key"] not in {attack["event_key"], benign["event_key"]}
    )
    decisions.append(
        {
            "event_key": unknown["event_key"],
            "label": None,
            "intent": "unknown",
            "attack_family": None,
            "review_status": "pending",
            "exploit_outcome": "unknown",
        }
    )
    review = {
        "format_version": 2,
        "dataset_sha256": manifest["dataset_sha256"],
        "provenance_sha256": "b" * 64,
        "environment_id": "test-only",
        "approved": True,
        "independent_review": True,
        "review_kind": "independent_human",
        "reviewer_id": "test-reviewer",
        "collector_id": "test-collector",
        "scope": "label_protocol_and_environment_realism",
        "decisions_file": "decisions.jsonl",
    }

    def save(rows=None, meta=None):
        rows = decisions if rows is None else rows
        meta = review if meta is None else meta
        for row in rows:
            for evidence in row.get("evidence", []):
                if evidence["kind"] == "independent_semantic_review":
                    evidence["file"] = "semantic-test-only.txt"
                    evidence["sha256"] = file_sha256(directory / "semantic-test-only.txt")
        (directory / "decisions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        meta = dict(meta, decisions_sha256=file_sha256(directory / "decisions.jsonl"))
        meta["review_sha256"] = digest(meta)
        (directory / "review.json").write_text(json.dumps(meta))
        return directory / "review.json"

    return save, review, decisions, manifest


def test_failed_attack_stays_positive_and_unreviewed_stays_unknown(prepared, tmp_path):
    save, _, _, _ = review_fixture(tmp_path, prepared)
    result = audit_label_evidence(save(), prepared, "b" * 64, "test-only", tmp_path / "audit")
    assert result["counts"]["reviewed_labeled_dataset_rows"] == 2
    assert result["counts"]["intent_attack"] == 1
    assert result["counts"]["outcome_failed"] == 1
    assert result["counts"]["unresolved"] == 1
    assert result["counts"]["unreviewed_dataset_rows"] == 157
    assert not result["formal_training_permitted"]


@pytest.mark.parametrize(
    "bad_kind", ["detector_rule", "model_prediction", "http_status", "timestamp_join"]
)
def test_detectors_and_proximity_cannot_supply_ground_truth(prepared, tmp_path, bad_kind):
    save, _, rows, manifest = review_fixture(tmp_path, prepared)
    rows[0]["evidence"][0]["kind"] = bad_kind
    with pytest.raises(PipelineError, match="detector"):
        list(iter_evidence_decisions(save(), manifest["dataset_sha256"], "b" * 64, "test-only"))


def test_outcome_needs_oracle_and_unknown_cannot_be_reclassified(prepared, tmp_path):
    save, _, rows, manifest = review_fixture(tmp_path, prepared)
    changed = copy.deepcopy(rows)
    changed[0]["evidence"] = changed[0]["evidence"][:-1]
    with pytest.raises(PipelineError, match="oracle"):
        list(
            iter_evidence_decisions(
                save(changed), manifest["dataset_sha256"], "b" * 64, "test-only"
            )
        )
    rows[2]["label"] = 0
    with pytest.raises(PipelineError, match="Unknown"):
        list(iter_evidence_decisions(save(), manifest["dataset_sha256"], "b" * 64, "test-only"))


def test_review_verifies_actual_row_labels_and_never_counts_extra_events(prepared, tmp_path):
    save, _, rows, _ = review_fixture(tmp_path, prepared)
    changed = copy.deepcopy(rows)
    changed[0].update(label=0, intent="benign", attack_family="benign", exploit_outcome="unknown")
    with pytest.raises(PipelineError, match="conflicts"):
        audit_label_evidence(save(changed), prepared, "b" * 64, "test-only", tmp_path / "relabel")
    rows[0]["event_key"] = "f" * 64
    for e in rows[0]["evidence"]:
        e["event_key"] = "f" * 64
    with pytest.raises(PipelineError, match="outside"):
        audit_label_evidence(save(), prepared, "b" * 64, "test-only", tmp_path / "extra")


def test_evidence_tampering_repeated_reviews_and_self_review_are_rejected(prepared, tmp_path):
    save, meta, rows, manifest = review_fixture(tmp_path, prepared)
    path = save()
    artifact = path.parent / "test-only.txt"
    original = artifact.read_text()
    artifact.write_text("changed")
    with pytest.raises(PipelineError, match="checksum"):
        list(iter_evidence_decisions(path, manifest["dataset_sha256"], "b" * 64, "test-only"))
    artifact.write_text(original)
    with pytest.raises(PipelineError, match="Duplicate"):
        audit_label_evidence(
            save(rows + [rows[0]]), prepared, "b" * 64, "test-only", tmp_path / "duplicate"
        )
    meta["collector_id"] = meta["reviewer_id"]
    with pytest.raises(PipelineError, match="attestation"):
        list(iter_evidence_decisions(save(), manifest["dataset_sha256"], "b" * 64, "test-only"))


def test_review_rejects_sealed_evidence_before_reading_it(prepared, tmp_path):
    save, _, rows, manifest = review_fixture(tmp_path, prepared)
    path = save()
    sealed = path.parent / "reserved"
    sealed.mkdir()
    (sealed / "AI_HOLDOUT.json").write_text('{"role":"sealed_final"}')
    (sealed / "hidden.txt").write_text("Do not read")
    rows[0]["evidence"][0]["file"] = "reserved/hidden.txt"
    with pytest.raises(PipelineError, match="Sealed"):
        list(iter_evidence_decisions(save(), manifest["dataset_sha256"], "b" * 64, "test-only"))
    assert load_json(sealed / "AI_HOLDOUT.json")["role"] == "sealed_final"


def test_catalog_no_longer_admits_a_boolean_only_review(prepared, tmp_path):
    from idps_ai.data.corpus import audit_catalog

    save, meta, _, manifest = review_fixture(tmp_path, prepared)
    proof = {"dataset_sha256": manifest["dataset_sha256"], "data_kind": "lab_capture"}
    proof["provenance_sha256"] = digest(proof)
    proof_path = tmp_path / "provenance.json"
    proof_path.write_text(json.dumps(proof))
    meta["provenance_sha256"] = proof["provenance_sha256"]
    meta["format_version"] = 1
    registry = {
        "format_version": 1,
        "sources": [
            {
                "id": "test-only-source",
                "environment_id": "test-only",
                "collection_kind": "scripted_lab",
                "authorization_ref": "test-only",
                "dataset": str(prepared),
                "provenance": str(proof_path),
                "review": str(save()),
                "partition_map": {"train": "train", "val": "validation", "test": "test"},
            }
        ],
    }
    result = audit_catalog(registry, tmp_path / "catalog")
    assert result["eligible_requests"] == 0
    assert result["sources"][0]["independent_review_attested"] is False
    assert result["status"] == "NOT_READY"


def test_catalog_qualifies_only_the_rows_with_matching_evidence(prepared, tmp_path):
    import yaml

    from idps_ai.common import AI_ROOT
    from idps_ai.data.corpus import audit_catalog

    save, meta, _, manifest = review_fixture(tmp_path, prepared)
    proof = {"dataset_sha256": manifest["dataset_sha256"], "data_kind": "lab_capture"}
    proof["provenance_sha256"] = digest(proof)
    proof_path = tmp_path / "provenance.json"
    proof_path.write_text(json.dumps(proof))
    meta["provenance_sha256"] = proof["provenance_sha256"]
    registry = {
        "format_version": 1,
        "sources": [
            {
                "id": "test-only-source",
                "environment_id": "test-only",
                "collection_kind": "scripted_lab",
                "authorization_ref": "test-only",
                "dataset": str(prepared),
                "provenance": str(proof_path),
                "review": str(save()),
                "partition_map": {"train": "train", "val": "validation", "test": "test"},
            }
        ],
    }
    policy = yaml.safe_load((AI_ROOT / "configs/scale_policy.yaml").read_text())
    policy.update(
        required_profile=manifest["input_profile"],
        required_feature_version=load_json(prepared / "feature_spec.json")["feature_version"],
    )
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy))
    result = audit_catalog(registry, tmp_path / "catalog", policy_path)
    assert result["eligible_requests"] == 2
    assert result["unreviewed_requests"] == 158
    assert result["sources"][0]["independent_review_attested"] is True
    assert result["status"] == "NOT_READY"
    assert not result["formal_training_permitted"]
