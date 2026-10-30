import json

import yaml

from idps_ai.common import AI_ROOT


def test_shadow_replay_is_read_only_bounded_and_never_emits_payload_or_actions(prepared, tmp_path):
    from idps_ai.export.onnx import export_bundle
    from idps_ai.inference import shadow_replay
    from idps_ai.training.runner import train

    config = yaml.safe_load((AI_ROOT / "configs/scale_pilot_config.yaml").read_text())
    config["model"]["hidden_dim"] = 8
    train(prepared, tmp_path / "run", config, epochs=1, max_threads=1, max_duration_minutes=1)
    export_bundle(
        prepared,
        tmp_path / "run",
        tmp_path / "bundle",
        max_threads=1,
        evaluation_partition="val",
        independent_validation=True,
    )
    from idps_ai.common import load_json

    metrics = load_json(tmp_path / "bundle/evaluation.json")
    assert metrics["latency_ms"]["sample_partition"] == "val"
    assert metrics["final_test_metrics_computed"] is False
    report = shadow_replay(
        prepared, tmp_path / "bundle", tmp_path / "shadow", max_requests=5, max_threads=1
    )
    assert report["requests"] == 5
    assert report["mode"] == "offline_shadow_only"
    assert report["enforcement_actions"] == 0
    rows = [json.loads(s) for s in (tmp_path / "shadow/predictions.jsonl").read_text().splitlines()]
    assert len(rows) == 5
    assert all(
        set(r) <= {"event_key", "score", "above_threshold", "decision", "family_candidate"}
        for r in rows
    )
    assert all("query_string" not in r and "client_ip" not in r for r in rows)
