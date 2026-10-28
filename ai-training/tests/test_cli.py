import json
import os
import subprocess
import sys


def test_s0_runs_training_resume_in_new_processes_and_onnx_on_both_branches(tmp_path):
    environment = os.environ | {
        "PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src")
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "idps_ai",
            "s0",
            "--output",
            str(tmp_path / "s0"),
            "--campaigns",
            "10",
            "--requests-per-campaign",
            "16",
            "--max-threads",
            "1",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "s0/s0_report.json").read_text())
    assert report["purpose"] == "S0 pipeline/resume verification on synthetic fixtures"
    for model in ("mlp", "autoencoder"):
        assert report["models"][model]["resume_equivalent"]
        assert (
            report["models"][model]["first_process_id"]
            != report["models"][model]["resumed_process_id"]
        )
        assert report["models"][model]["onnx_parity"]["all_rows_match"]


def test_pilot_verifies_all_candidates_resume_and_seals_test_metrics(prepared, tmp_path):
    import yaml

    from idps_ai.cli import main
    from idps_ai.common import AI_ROOT, atomic_json, digest
    from idps_ai.data.dataset import verify_dataset
    from idps_ai.data.readiness import audit_readiness

    # Explicit tiny technical fixture, not certification of real lab provenance.
    policy = yaml.safe_load((AI_ROOT / "configs/pretrain_policy.yaml").read_text())
    policy.update(
        require_variant_provenance=False,
        minimum_requests=100,
        minimum_groups_per_partition=1,
        minimum_benign_per_partition=1,
        minimum_family_per_partition=1,
    )
    policy_path = tmp_path / "test-policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy))
    proof = {
        "format_version": 1,
        "data_kind": "lab_capture",
        "dataset_sha256": verify_dataset(prepared)["dataset_sha256"],
        "limits": ["Test-only synthetic provenance declaration"],
    }
    proof["provenance_sha256"] = digest(proof)
    proof_path = tmp_path / "provenance.json"
    atomic_json(proof_path, proof)
    report = audit_readiness(prepared, tmp_path / "gate", "lab_capture", policy_path, proof_path)
    assert report["offline_pilot_training_permitted"]
    import pytest

    from idps_ai.training.session import validate_formal_readiness

    with pytest.raises(ValueError, match="three-source"):
        validate_formal_readiness(tmp_path / "gate/readiness.json", prepared)
    assert (
        main(
            [
                "pilot",
                "--dataset",
                str(prepared),
                "--readiness-report",
                str(tmp_path / "gate/readiness.json"),
                "--output",
                str(tmp_path / "pilot"),
                "--max-threads",
                "1",
            ]
        )
        == 0
    )
    result = json.loads((tmp_path / "pilot/pilot-report.json").read_text())
    assert set(result["models"]) == {"mlp", "autoencoder", "residual"}
    assert result["test_metrics_computed"] is False
    for model in result["models"].values():
        assert model["exact_resume"] is True
        assert model["epoch"] == 5
        assert model["onnx_parity"]["rows"] == 160
        assert model["validation_evaluation"]["partition"] == "val"
        assert "without_flow" in model["validation_diagnostics"]
        assert "without_response" in model["validation_diagnostics"]
