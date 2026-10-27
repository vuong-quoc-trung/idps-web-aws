import errno
import json
import os
import signal
import subprocess
import sys
import time

import numpy as np
import pytest
import yaml

from idps_ai.common import AI_ROOT
from idps_ai.data.dataset import collect, iter_rows, load_labels, verify_dataset
from idps_ai.data.privacy import request_numbers
from idps_ai.data.readers import Input, read_events
from idps_ai.features.pipeline import FeatureExtractor, feature_columns
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.evaluation import evaluate, threshold_at_fpr
from idps_ai.training.models import Model
from idps_ai.training.resources import MemoryGuard
from idps_ai.training.runner import train

KEY = b"test-only-redaction-key-32-bytes!!"


def nginx(timestamp="2026-01-01T00:00:00Z", **kwargs):
    return {
        "timestamp": timestamp,
        "client_ip": "2001:db8::1",
        "http_method": "GET",
        "uri_path": "/api/students",
        "status": 200,
        **kwargs,
    }


def write(path, values):
    path.write_text("".join(json.dumps(value) + "\n" for value in values))
    return path


def test_native_http_units_lexical_features_and_bounded_secret_projection(tmp_path):
    path = write(
        tmp_path / "access.log",
        [
            nginx(
                latency_seconds=0.125,
                request_id="r1",
                query_string="q=UNION%20SELECT&password=BARE_CANARY_SECRET",
            )
        ],
    )
    row = next(read_events([Input("nginx", path)], KEY))
    assert row["latency_ms"] == 125.0
    assert row["numeric"]["sqli_keywords"] == 2
    assert "CANARY" not in json.dumps(row)
    assert row["client_key"] != "2001:db8::1"


def test_oversized_malformed_and_partial_records_cannot_poison_the_next_record(tmp_path):
    path = tmp_path / "access.log"
    path.write_bytes(
        b"X" * 300 + b"\n{bad CANARY\n" + json.dumps(nginx()).encode() + b"\npartial-CANARY"
    )
    stats = {}
    rows = list(read_events([Input("nginx", path)], KEY, stats, max_line_bytes=256))
    assert len(rows) == 1
    assert stats == {"oversized": 1, "invalid": 1, "accepted": 1, "partial": 1}
    assert "CANARY" not in json.dumps(stats)


def test_reader_refuses_a_live_file_changed_during_snapshot_read(tmp_path):
    path = write(tmp_path / "access.log", [nginx()])
    stream = read_events([Input("nginx", path)], KEY)
    next(stream)
    with path.open("a") as file:
        file.write(json.dumps(nginx()) + "\n")
    with pytest.raises(ValueError, match="changed"):
        list(stream)


def test_masked_values_and_missing_queries_are_explicitly_unavailable():
    values = request_numbers("/api/students/[id]", "q=[REDACTED]")
    assert values["uri_lexical_available"] == 0
    assert values["query_lexical_available"] == 0
    assert values["sqli_keywords"] == 0
    assert values["object_identity_available"] == 0
    assert request_numbers(None, None)["uri_lexical_available"] == 0


def test_client_time_proximity_does_not_merge_distinct_requests_on_nat(tmp_path):
    path = write(tmp_path / "access.log", [nginx(), nginx("2026-01-01T00:00:00.100Z")])
    collect([Input("nginx", path)], tmp_path / "dataset", KEY)
    rows = list(iter_rows(tmp_path / "dataset/requests.parquet"))
    assert len(rows) == 2
    assert all(row["observation_count"] == 1 for row in rows)
    assert rows[-1]["ip_time_ambiguous"]


def test_label_conflicts_are_rejected_and_weak_labels_never_become_ground_truth(tmp_path):
    weak = {
        "request_id": "request-one",
        "campaign_id": "campaign",
        "attack_family": "sqli",
        "label_source": "weak_rule",
        "review_status": "approved",
    }
    path = write(tmp_path / "labels.jsonl", [weak])
    assert next(iter(load_labels(path, KEY).values()))["label"] is None
    write(path, [weak, {**weak, "attack_family": "xss"}])
    with pytest.raises(ValueError, match="Invalid|Conflicting"):
        load_labels(path, KEY)


def test_feature_state_is_bounded_and_rule_context_is_excluded_by_default():
    extractor = FeatureExtractor(max_entities=1, max_events_per_entity=1)
    base = {
        "client_key": "ip",
        "user_key": None,
        "timestamp": 0,
        "uri_path": "/api/students",
        "status_code": 200,
    }
    extractor.observe(base)
    latest = extractor.observe({**base, "timestamp": 1, "suricata_alert_counts": [1, 2, 3]})
    assert latest["ip_10s_count"] == 1
    assert latest["ip_10s_context_incomplete"] == 1
    assert latest["context_suricata_alerts_60s"] == 2
    assert not any(name.startswith("context_suricata") for name in feature_columns())


def test_checkpoint_corruption_falls_back_to_verified_previous_generation(tmp_path):
    model = Model(2, 3)
    save_checkpoint(tmp_path, model, {"global_step": 0}, np.array([0]))
    model.train_batch(np.zeros((1, 2), np.float32), np.array([0]), 0.01)
    newest = save_checkpoint(tmp_path, model, {"global_step": 1}, np.array([0]))
    (newest / "arrays.npz").write_bytes(b"corrupt")
    loaded = load_checkpoint(tmp_path)
    assert loaded.used_previous
    assert loaded.state["global_step"] == 0


def test_disk_failure_during_checkpoint_cannot_replace_the_last_good_pointer(tmp_path, monkeypatch):
    model = Model(2, 3)
    save_checkpoint(tmp_path, model, {"global_step": 0}, np.array([0]))
    old = (tmp_path / "latest.json").read_bytes()
    with monkeypatch.context() as context:

        def full(_):
            raise OSError(errno.ENOSPC, "simulated full checkpoint filesystem")

        context.setattr(os, "fsync", full)
        with pytest.raises(OSError):
            save_checkpoint(tmp_path, model, {"global_step": 0}, np.array([0]))
    assert (tmp_path / "latest.json").read_bytes() == old
    assert load_checkpoint(tmp_path).state["global_step"] == 0


def test_abrupt_death_during_temporary_checkpoint_write_keeps_latest_loadable(tmp_path):
    model = Model(2, 3)
    save_checkpoint(tmp_path, model, {"global_step": 0}, np.array([0]))
    script = """import os,sys,numpy as np
from idps_ai.training.checkpoint import load_checkpoint,save_checkpoint
r=load_checkpoint(sys.argv[1])
os.fsync=lambda fd: os._exit(71)
save_checkpoint(sys.argv[1],r.model,r.state,r.permutation)
"""
    env = os.environ | {"PYTHONPATH": str(AI_ROOT / "src")}
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env, timeout=15)
    assert result.returncode == 71
    assert load_checkpoint(tmp_path).state["global_step"] == 0


def test_deadline_stops_at_a_checkpoint_and_can_resume(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    run = tmp_path / "run"
    first = train(prepared, run, config, epochs=2, max_duration_minutes=0, max_threads=1)
    assert first["stop_reason"] == "duration_limit"
    assert first["global_step"] == 0
    resumed = train(prepared, run, config, epochs=1, resume_from=run, max_threads=1)
    assert resumed["epoch"] == 1
    assert resumed["resources"]["peak_tree_rss_bytes"] < 16_000_000_000
    assert resumed["resources"]["address_space_limit_effective"] <= 12 * 1024**3


def test_resume_mid_epoch_does_not_repeat_or_skip_optimizer_steps(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    config["training"]["batch_size"] = 7
    full, interrupted = tmp_path / "full", tmp_path / "interrupted"
    train(prepared, full, config, epochs=2, max_threads=1)
    partial = train(prepared, interrupted, config, epochs=2, max_steps=2, max_threads=1)
    assert partial["cursor"] == 14
    train(prepared, interrupted, config, epochs=2, resume_from=interrupted, max_threads=1)
    a, b = load_checkpoint(full), load_checkpoint(interrupted)
    assert a.state["global_step"] == b.state["global_step"]
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_actual_signals_stop_a_new_process_at_safe_optimizer_boundary(prepared, tmp_path, signum):
    run = tmp_path / "run"
    env = os.environ | {"PYTHONPATH": str(AI_ROOT / "src")}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "idps_ai",
            "train",
            "--dataset",
            str(prepared),
            "--run-dir",
            str(run),
            "--epochs",
            "100000",
            "--max-threads",
            "1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while (
            not (run / "latest.json").exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert (run / "latest.json").exists()
        process.send_signal(signum)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["stop_reason"] == signal.Signals(signum).name
        assert load_checkpoint(run).state["stop_reason"] == signal.Signals(signum).name
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_metrics_and_float32_threshold_respect_the_empirical_fpr_budget():
    scores = np.array([0.1, 0.2, 0.8, 0.9], np.float32)
    labels = np.array([0, 0, 1, 1])
    calibration = threshold_at_fpr(labels, scores)
    result = evaluate(labels, scores, calibration["threshold"])
    assert result["pr_auc_average_precision"] == 1
    assert result["roc_auc"] == 1
    assert result["confusion_matrix"] == [[2, 0], [0, 2]]
    tied = np.ones(4, np.float32)
    strict = threshold_at_fpr(labels, tied)
    assert (tied[:2] >= strict["threshold"]).sum() == 0
    adjacent = np.array([1, np.nextafter(np.float32(1), np.float32(np.inf))], np.float32)
    boundary = threshold_at_fpr(np.array([0, 1]), adjacent)
    assert adjacent[0] < boundary["threshold"]
    assert adjacent[1] >= boundary["threshold"]


def test_modified_dataset_shards_are_never_silently_resumed(prepared, tmp_path):
    import shutil

    changed = tmp_path / "changed"
    shutil.copytree(prepared, changed)
    with (changed / "features.parquet").open("ab") as file:
        file.write(b"changed")
    with pytest.raises(ValueError, match="modified"):
        verify_dataset(changed, "prepared")


def test_memory_guard_counts_the_current_process_without_allocating_gigabytes():
    guard = MemoryGuard(1)
    assert guard.check()
    assert guard.peak_tree_rss_bytes >= guard.peak_rss_bytes > 0
