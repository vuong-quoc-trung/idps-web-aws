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
