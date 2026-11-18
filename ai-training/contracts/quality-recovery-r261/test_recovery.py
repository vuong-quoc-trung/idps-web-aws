# isort: skip_file

import copy

import pytest

from idps_ai.common import PipelineError
from idps_ai.training.allocation_review import reviewed_plan
from idps_ai.training.thermal_policy import cpu_state, quota_for_state


@pytest.mark.parametrize(
    "temperature,state,quota",
    [
        (89, "NORMAL", 400),
        (90, "NORMAL", 400),
        (90.1, "THROTTLE", 200),
        (99, "THROTTLE", 200),
        (100, "THROTTLE", 200),
    ],
)
def test_two_thermal_thresholds(temperature, state, quota):
    assert cpu_state(temperature, False) == state
    assert quota_for_state(400, state) == quota


def test_stop_never_masquerades_as_cool_and_alarm_takes_priority():
    assert cpu_state(100.1, False) == "THERMAL_EMERGENCY"
    assert cpu_state(47, True) == "THERMAL_EMERGENCY"
    for value in (None, float("nan"), float("inf"), -1):
        assert cpu_state(value, False) == "SENSOR_FAILURE"


def inputs():
    plan = {
        "phase": "TRAIN",
        "hardware_hash": "test",
        "worker_cpu_ceiling": 12,
        "worker_memory_ceiling_bytes": 16 * 1024**3,
    }
    evidence = {
        "version": "idps-r261-bounded-allocation-review-v1",
        "phase": "TRAIN",
        "hardware_hash": "test",
        "authorization_request_sha256": "x",
        "reviewed_cpu_cores": 4,
        "reviewed_memory_bytes": 4 * 1024**3,
        "benchmark_guardian_verified": True,
        "benchmark_cleanup_verified": True,
        "benchmark_kernel_cpu_max": "400000 100000",
        "allow_production_scale_claim": False,
        "benchmark": {
            "selected_threads": 4,
            "arms": [{"threads": 1, "seconds": 2}, {"threads": 4, "seconds": 1}],
        },
    }
    return plan, evidence


def test_explicit_research_allocation_does_not_mutate_default_plan():
    plan, evidence = inputs()
    original = copy.deepcopy(plan)
    reviewed = reviewed_plan(plan, evidence, 4, 4 * 1024**3)
    assert reviewed["approved_cpu_cores"] == 4
    assert plan == original


@pytest.mark.parametrize(
    "key,value",
    [
        ("hardware_hash", "wrong"),
        ("benchmark_guardian_verified", False),
        ("benchmark_cleanup_verified", False),
        ("benchmark_kernel_cpu_max", "max 100000"),
        ("reviewed_cpu_cores", 8),
        ("allow_production_scale_claim", True),
    ],
)
def test_invalid_scale_evidence_fail_closed(key, value):
    plan, evidence = inputs()
    evidence[key] = value
    with pytest.raises(PipelineError):
        reviewed_plan(plan, evidence, 4, 4 * 1024**3)


def test_ancestor_capacity_and_unproven_speedup_fail_closed():
    plan, evidence = inputs()
    plan["worker_cpu_ceiling"] = 2
    with pytest.raises(PipelineError):
        reviewed_plan(plan, evidence, 4, 4 * 1024**3)
    plan, evidence = inputs()
    evidence["benchmark"]["arms"][1]["seconds"] = 1.99
    with pytest.raises(PipelineError):
        reviewed_plan(plan, evidence, 4, 4 * 1024**3)


def test_semantic_verifier_requires_actor_policy_and_oracle_not_status_or_intent():
    from native import semantic_disposition

    assert semantic_disposition({"http_status": 403, "intent": "ATTACK"}) == "INSUFFICIENT_EVIDENCE"
    proof = dict.fromkeys(
        (
            "actor_verified",
            "session_verified",
            "role_verified",
            "policy_verified",
            "target_verified",
            "request_binding_verified",
            "application_oracle_verified",
        ),
        True,
    )
    proof.update(expected_authorized=False, observed_action="DENIED")
    assert semantic_disposition(proof) == "ATTACK_VERIFIED"
    assert semantic_disposition(proof | {"role_verified": False}) == "INSUFFICIENT_EVIDENCE"
    assert (
        semantic_disposition(proof | {"expected_authorized": True, "observed_action": "ALLOWED"})
        == "BENIGN_VERIFIED"
    )


def test_thermal_recovery_needs_complete_no_alarm_trip_and_stable_cool_samples():
    from supervisor import recoverable_software_pause

    result = {"reason": "THERMAL_EMERGENCY", "cleanup_verified": True}
    trip = {"software_threshold_only": True, "hardware_alarm": False, "temperature_c": 100.1}
    health = {
        "stable_samples": 5,
        "all_readings_fresh": True,
        "hardware_alarm": False,
        "maximum_c": 90,
    }
    assert recoverable_software_pause(result, trip, health)
    assert not recoverable_software_pause(result, trip | {"hardware_alarm": True}, health)
    assert not recoverable_software_pause(result, trip, health | {"maximum_c": 90.1})
    assert not recoverable_software_pause(result, {}, health)
    assert not recoverable_software_pause(
        result | {"reason": "GUARDIAN_EXIT_WITHOUT_RESULT"}, trip, health
    )


def test_runtime_stages_regular_immutable_model_instead_of_symlink(tmp_path):
    import onnx
    from onnx import TensorProto, helper
    from verify import stage_model

    source = tmp_path / "original.onnx"
    model = helper.make_model(
        helper.make_graph(
            [helper.make_node("Identity", ["x"], ["y"])],
            "test",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])],
        )
    )
    onnx.save(model, source)
    target = tmp_path / "staged.onnx"
    target.symlink_to(source)
    stage_model(target, source)
    assert target.is_file() and not target.is_symlink()
    assert target.read_bytes() == source.read_bytes()


def test_worker_thread_limits_follow_reviewed_spec_and_default_stays_one():
    from idps_ai.training.allocation_review import worker_environment

    assert (
        worker_environment({"cpu_percent": 100}, {"OPENBLAS_NUM_THREADS": "99"})[
            "OPENBLAS_NUM_THREADS"
        ]
        == "1"
    )
    spec = {"cpu_percent": 400, "blas_threads": 4, "allocation_review": {"sha256": "pin"}}
    assert worker_environment(spec, {})["OPENBLAS_NUM_THREADS"] == "4"
    with pytest.raises(PipelineError):
        worker_environment(spec | {"blas_threads": 5}, {})
    with pytest.raises(PipelineError):
        worker_environment(spec | {"allocation_review": None}, {})


def test_guest_student_login_is_never_sent_to_admin_identity():
    from lab_auth import login_username

    assert login_username("login-admin") == "labu1"
    assert login_username("login-student") == "labu2"
    with pytest.raises(ValueError):
        login_username("unknown")


def test_guest_stage_replaces_legacy_oracle_only_inside_owned_root(tmp_path):
    from lab_auth import stage_guest_python

    root = tmp_path / "fs"
    root.mkdir()
    source = tmp_path / "new.py"
    source.write_text("new fixture")
    (root / "lab").mkdir()
    (root / "lab/oracle.py").write_text("legacy fixture")
    stage_guest_python(source, root, "/lab/oracle.py")
    assert (root / "lab/oracle.py").read_text() == "new fixture"
    with pytest.raises(ValueError):
        stage_guest_python(source, root, "../escape.py")


@pytest.mark.parametrize(
    "role,number,basis,label",
    [
        ("ADMIN", 1, "RECORD_ID_AND_JDBC_MARKER", "BENIGN_VERIFIED"),
        ("STUDENT", 2, "DENIAL_WITHOUT_JDBC_MARKER", "ATTACK_VERIFIED"),
    ],
)
def test_first_party_native_authorization_needs_bound_principal_policy_owner(
    tmp_path, role, number, basis, label
):
    import json
    from native_authorization import AuthorizationOracle

    journal = tmp_path / "audit.jsonl"
    events = [
        {
            "request_id": rid,
            "event_id": "event-" + rid,
            "source_instance": "fixture",
            "user_id": "hmac-sha256:" + "a" * 64,
            "session_hmac": "hmac-sha256:" + "b" * 64,
            "role": role,
        }
        for rid in ("principal", "target")
    ]
    journal.write_text("".join(json.dumps(e) + "\n" for e in events))
    oracle = AuthorizationOracle(
        journal,
        "fixture",
        b"fixture-key",
        lambda _, q: {f"ROLE {number}": role, "OWNER 113": "113"}[q],
    )

    def receipt(rid, basis):
        return {
            "request_key": "key-" + rid,
            "identity_verified": True,
            "clock_valid": True,
            "oracle_verified": True,
            "oracle_basis": basis,
            "send_monotonic_ns": 0,
            "events": [
                {"source": "A", "native_event_id": "event-" + rid, "proof_sha256": "proof-" + rid}
            ],
        }

    oracle.observe(
        {"oracle": "principal-" + ("admin" if number == 1 else "student"), "session": "s"},
        "principal",
        receipt("principal", "PRINCIPAL_AND_JDBC_ROLE"),
        None,
        None,
    )
    row = {"oracle": "record", "record": 113, "session": "s"}
    proof = oracle.observe(
        row, "target", receipt("target", basis), None, oracle.snapshot(None, row)
    )
    assert proof["label"] == label and proof["resource_owner_differs_from_actor"]
    events[-1]["session_hmac"] = "hmac-sha256:" + "c" * 64
    journal.write_text("".join(json.dumps(e) + "\n" for e in events))
    with pytest.raises(ValueError, match="ACTOR_POLICY_OWNER_NOT_STABLE"):
        oracle.observe(row, "target", receipt("target", basis), None, oracle.snapshot(None, row))
