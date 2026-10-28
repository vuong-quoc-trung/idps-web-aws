import json


def test_private_namespace_captures_real_http_without_host_packet_privileges(tmp_path):
    from idps_ai.data.sensor_lab import probe_capture

    result = probe_capture(tmp_path)
    assert result["http_status"] == 200
    assert result["pcap_bytes"] > 100
    assert result["namespace_isolated"] is True
    assert result["host_namespace_unchanged"] is True
    assert result["packet_capture_returncode"] == 0


def test_extended_plan_has_disjoint_payload_views_and_real_window_depth():
    from idps_ai.data.campaigns import campaign_plan

    variants = []
    for band in range(3):
        plan = campaign_plan(band, 1280, 420)
        assert len(plan) == 1280
        assert plan[-1]["at_seconds"] >= 419
        assert sum(case["at_seconds"] >= 300 for case in plan) >= 300
        assert any(case["scenario"] == "benign_login_typo" for case in plan)
        assert any(case["scenario"] == "hard_negative_search" for case in plan)
        variants.append({case["variant_group"] for case in plan if case["family"] != "benign"})
    assert not variants[0] & variants[1]
    assert not variants[0] & variants[2]
    assert not variants[1] & variants[2]


def test_edge_profile_never_uses_private_query_and_reads_only_response_request_id():
    from idps_ai.data.readers import normalize_record

    value = {
        "timestamp": "2026-10-28T00:00:00Z",
        "event_type": "http",
        "src_ip": "127.0.0.10",
        "flow_id": 18446744073709551600,
        "http": {
            "url": "/api/faculties?q=UNION%20SELECT%20password",
            "http_method": "GET",
            "status": 200,
            "request_headers": [{"name": "X-Request-Id", "value": "untrusted"}],
            "response_headers": [{"name": "X-Request-Id", "value": "edge-generated"}],
        },
    }
    event = normalize_record("suricata", value, b"k" * 32, "event", input_profile="edge_masked_v1")
    from idps_ai.data.privacy import pseudonym

    assert event["request_key"] == pseudonym(b"k" * 32, "request", "edge-generated")
    assert event["numeric"]["query_lexical_available"] == 0
    assert event["numeric"]["sqli_keywords"] == 0
    assert event["numeric"]["query_original_available"] == 0
    assert "password" not in json.dumps(event)


def test_flow_context_uses_completed_past_client_flow_and_never_future_totals(tmp_path):
    from idps_ai.data.dataset import collect, iter_rows
    from idps_ai.data.readers import Input

    source = tmp_path / "eve.json"
    rows = [
        {
            "timestamp": "2026-10-28T00:00:01Z",
            "src_ip": "127.0.0.10",
            "flow_id": 1,
            "event_type": "flow",
            "flow": {
                "age": 1,
                "bytes_toserver": 123,
                "bytes_toclient": 321,
                "pkts_toserver": 3,
                "pkts_toclient": 4,
            },
        },
        {
            "timestamp": "2026-10-28T00:01:42Z",
            "src_ip": "127.0.0.10",
            "flow_id": 2,
            "event_type": "http",
            "http": {
                "request_id": "r2",
                "url": "/api/faculties",
                "http_method": "GET",
                "status": 200,
            },
        },
        {
            "timestamp": "2026-10-28T00:01:43Z",
            "src_ip": "127.0.0.10",
            "flow_id": 2,
            "event_type": "flow",
            "flow": {"age": 2, "bytes_toserver": 999999},
        },
    ]
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    collect(
        [Input("suricata", source)], tmp_path / "data", b"k" * 32, input_profile="edge_masked_v1"
    )
    result = list(iter_rows(tmp_path / "data/requests.parquet"))
    assert len(result) == 1
    assert json.loads(result[0]["flow_json"])["bytes_to_server"] == 123
    assert result[0]["label"] is None


def test_session_launcher_bounds_the_entire_process_group_and_preserves_learning_args(
    prepared, monkeypatch
):
    import os

    import pytest

    from idps_ai.training.session import session_command

    # OS inventory is the external boundary. Policy must accept both6/8 CPUs
    # on a16-thread machine, including the explicitly requested16GiB ceiling.
    with monkeypatch.context() as context:
        context.setattr(os, "sched_getaffinity", lambda _pid: set(range(16)))
        for cpus, quota in [(6, "600%"), (8, "800%")]:
            command, policy = session_command(
                [
                    "--dataset",
                    str(prepared),
                    "--run-dir",
                    "/tmp/new-idps-run",
                    "--readiness-report",
                    "/tmp/ready.json",
                    "--epochs",
                    "5",
                    "--cpus",
                    str(cpus),
                    "--memory-limit-gib",
                    "16",
                ]
            )
            assert "CPUQuota=" + quota in command
            assert "MemoryMax=17179869184" in command
            assert "MemoryHigh=16106127360" in command
            assert "MemorySwapMax=0" in command
            assert "Nice=10" in command
            assert policy["memory_max_bytes"] == 17179869184
            assert command[command.index("--epochs") + 1] == "5"
            from idps_ai.export.onnx import session_options
            from idps_ai.training.resources import configure_threads

            assert configure_threads(cpus) == cpus
            assert all(
                os.environ[name] == str(cpus)
                for name in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            )
            options = session_options(cpus)
            assert options.intra_op_num_threads == cpus
            assert options.inter_op_num_threads == 1
        with pytest.raises(ValueError, match="16"):
            session_command(
                [
                    "--dataset",
                    str(prepared),
                    "--run-dir",
                    "/tmp/new-idps-run",
                    "--readiness-report",
                    "/tmp/ready.json",
                    "--cpus",
                    "8",
                    "--memory-limit-gib",
                    "17",
                ]
            )


def test_session_rejects_more_than_half_host_cpu_before_launch(prepared):
    import os

    import pytest

    from idps_ai.training.session import session_command

    with pytest.raises(ValueError, match="50%"):
        session_command(
            [
                "--dataset",
                str(prepared),
                "--run-dir",
                "/tmp/new-idps-run",
                "--readiness-report",
                "/tmp/ready.json",
                "--max-threads",
                str(len(os.sched_getaffinity(0))),
            ]
        )


def test_suricata_offline_retains_generated_id_without_persisting_response_secrets(tmp_path):
    import os
    from pathlib import Path

    import pytest

    from idps_ai.data.sensor_decode import decode_pcap
    from idps_ai.data.sensor_lab import probe_capture

    runtime = os.environ.get("IDPS_AI_TEST_SURICATA_RUNTIME")
    if not runtime:
        pytest.skip("Set IDPS_AI_TEST_SURICATA_RUNTIME to a trusted extracted Suricata 8 runtime")
    probe_capture(tmp_path / "probe")
    report = decode_pcap(tmp_path / "probe/traffic.pcap", tmp_path / "eve", Path(runtime))
    assert report["event_counts"]["http"] == 1
    assert report["event_counts"]["flow"] == 1
    assert report["request_ids"] == 1
    text = (tmp_path / "eve/eve.json").read_text()
    assert "SENSOR_SECRET_CANARY" not in text
    assert "Set-Cookie" not in text
    assert "probe-edge-id" in text


def test_three_source_gate_explicitly_rejects_the_old_native_profile(prepared, tmp_path):
    from idps_ai.common import AI_ROOT
    from idps_ai.data.readiness import audit_readiness

    report = audit_readiness(
        prepared, tmp_path / "gate", "lab_capture", AI_ROOT / "configs/three_source_policy.yaml"
    )
    failures = {c["id"] for c in report["checks"] if not c["pass"]}
    assert "input_availability_profile" in failures
    assert "real_eve_evidence" in failures
    assert "train_long_campaigns" in failures
    assert report["offline_pilot_training_permitted"] is False


def test_every_source_uses_identical_masked_query_features():
    from idps_ai.data.readers import normalize_record

    base = {
        "timestamp": "2026-10-28T00:00:00Z",
        "request_id": "edge-id",
        "client_ip": "127.0.0.10",
        "http_method": "GET",
        "status": 200,
        "uri_path": "/api/faculties",
        "query_string": "q=UNION+SELECT+secret",
        "query_features": {"length": 500, "quote_count": 20},
    }
    a = normalize_record("nginx", base, b"k" * 32, "one", input_profile="edge_masked_v1")
    base["query_string"] = None
    base["query_features"] = None
    b = normalize_record("nginx", base, b"k" * 32, "two", input_profile="edge_masked_v1")
    assert a["numeric"] == b["numeric"]
    assert a["numeric"]["query_original_quote_count"] == 0


def test_rule_comparison_is_validation_only_and_never_treats_missing_alert_as_truth(
    prepared, tmp_path
):
    from idps_ai.common import load_json
    from idps_ai.data.baseline import three_source_rule_baseline

    raw = prepared.parent / "raw"
    report = three_source_rule_baseline(
        prepared,
        raw / "access.log",
        raw / "eve.json",
        (raw / "redaction.key").read_bytes(),
        tmp_path / "baseline.json",
    )
    assert report["partition"] == "val"
    assert report["all_nine_sids"]["rows"] == 32
    facts = load_json(tmp_path / "validation-rule-facts.json")
    assert len(facts["facts"]) == 32
    assert all("label" not in row for row in facts["facts"])


def test_flow_duration_uses_observed_subsecond_bounds_instead_of_quantized_age():
    from idps_ai.data.readers import normalize_record

    event = {
        "timestamp": "2026-10-28T00:00:04Z",
        "src_ip": "127.0.0.10",
        "event_type": "flow",
        "flow": {"age": 3, "start": "2026-10-28T00:00:00Z", "end": "2026-10-28T00:00:03.125Z"},
    }
    row = normalize_record("suricata", event, b"k" * 32, "flow")
    assert row["flow"]["duration_seconds"] == 3.125


def test_sensor_projection_drops_unneeded_free_text_and_redirect_secrets():
    from idps_ai.data.sensor_decode import redact_eve

    value = {
        "http": {
            "url": "/api/auth/activate?token=SECRET_CANARY",
            "http_method": "GET",
            "redirect": "/activate?token=SECRET_CANARY",
            "hostname": "SECRET_CANARY",
            "http_user_agent": "SECRET_CANARY",
            "response_headers": [{"name": "Set-Cookie", "value": "SECRET_CANARY"}],
        }
    }
    assert "SECRET_CANARY" not in json.dumps(redact_eve(value))


def test_flow_observation_time_and_close_grace_are_combined_without_double_delay(tmp_path):
    from idps_ai.data.dataset import collect, iter_rows
    from idps_ai.data.readers import Input

    # EVE emitted at70s for a flow ending at1s. At75s the record is already
    # observed AND its65s close grace has elapsed. Waiting another65s is wrong.
    rows = [
        {
            "timestamp": "2026-10-28T00:01:10Z",
            "event_type": "flow",
            "src_ip": "127.0.0.10",
            "flow_id": 1,
            "flow": {
                "start": "2026-10-28T00:00:00Z",
                "end": "2026-10-28T00:00:01Z",
                "age": 1,
                "bytes_toserver": 123,
                "bytes_toclient": 321,
                "pkts_toserver": 3,
                "pkts_toclient": 4,
            },
        },
        {
            "timestamp": "2026-10-28T00:01:15Z",
            "event_type": "http",
            "src_ip": "127.0.0.10",
            "flow_id": 2,
            "http": {
                "request_id": "next",
                "http_method": "GET",
                "url": "/api/faculties",
                "status": 200,
            },
        },
    ]
    source = tmp_path / "eve.json"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    collect(
        [Input("suricata", source)], tmp_path / "data", b"k" * 32, input_profile="edge_masked_v1"
    )
    row = next(iter_rows(tmp_path / "data/requests.parquet"))
    assert json.loads(row["flow_json"])["bytes_to_server"] == 123
