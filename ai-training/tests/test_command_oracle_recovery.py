"""Packet validation/error taxonomy; fixtures never become supervised examples."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "command_oracle", Path(__file__).parents[1] / "scripts/verify-command-oracle.py"
)
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
VALID = b"PING localhost (::1) 56 data bytes\n4 packets transmitted, 4 received, 0% packet loss, time 3000ms\n"


def test_real_summary_is_numeric_coherent_and_not_an_intent_label():
    s = o.ping_summary(VALID)
    assert s["valid"] and s["transmitted"] == s["received"] == 4 and s["loss_percent"] == 0
    assert o.decision(s, returncode=0) == "VERIFIED_EXECUTION"
    assert "BENIGN" not in str(s)


@pytest.mark.parametrize(
    "blob",
    [
        b"HTTP200 OK",
        VALID.replace(b"0% packet loss", b"100% packet loss"),
        VALID.replace(b"4 received", b"0 received"),
        VALID.replace(b"4 packets transmitted", b"1 packets transmitted"),
        VALID + VALID,
        b"4 packets transmitted, 4 received, 0% packet loss\n",
    ],
)
def test_invalid_incoherent_or_duplicate_summaries_fail(blob):
    assert not o.ping_summary(blob)["valid"]


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"error_class": "PERMISSION_DENIED", "returncode": 2}, "UNKNOWN_PERMISSION_DENIED"),
        ({"returncode": 127}, "UNKNOWN_COMMAND_NOT_FOUND"),
        ({"timed_out": True}, "UNKNOWN_COMMAND_TIMEOUT"),
        ({"returncode": 1}, "UNKNOWN_COMMAND_FAILED"),
        ({"packets": False}, "UNKNOWN_PACKET_OBSERVATION_FAILURE"),
        ({"session": False}, "UNKNOWN_SESSION_MISMATCH"),
        ({"app_ok": False}, "UNKNOWN_APPLICATION_ERROR"),
    ],
)
def test_failures_cannot_be_rescued_by_a_good_looking_summary(kwargs, expected):
    assert o.decision(o.ping_summary(VALID), **({"returncode": 0} | kwargs)) == expected


def test_missing_or_mismatched_packet_observation_fails():
    assert not o.echo_delta({"netns": "a", "counters": {}}, {"netns": "a", "counters": {}})["valid"]
    assert not o.echo_delta({"netns": "a", "counters": {}}, {"netns": "b", "counters": {}})["valid"]
    d = o.echo_delta(
        {"netns": "a", "counters": {"Icmp6OutEchos": 0, "Icmp6InEchoReplies": 0}},
        {"netns": "a", "counters": {"Icmp6OutEchos": 4, "Icmp6InEchoReplies": 4}},
    )
    assert d["valid"] and d["echo_requests_sent"] == d["echo_replies_received"] == 4


def test_lab_fix_is_app_only_and_preserves_no_new_privileges(monkeypatch):
    c = o.module("request-v3-final-controls")
    calls = []

    def pm(*args):
        import json

        calls.append(args)
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "NetworkSettings": {
                            "Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(c.PORT)}]}
                        }
                    }
                ]
            )
        if args[:2] == ("network", "inspect"):
            return json.dumps([{"internal": True}])
        return ""

    q, d = c.configured_helpers()
    q.pm = pm
    c.launch(q, d, "dvwa")
    runs = [a for a in calls if a[0] == "run"]
    assert len(runs) == 2
    assert "--sysctl" not in runs[0]
    assert "net.ipv4.ping_group_range=33 33" in runs[1]
    assert all("--security-opt=no-new-privileges" in a for a in runs)
    assert not any(
        "--privileged" in a or any(str(v).startswith("--cap-add") for v in a) for a in runs
    )


def test_missing_exit_status_is_never_assumed_zero():
    assert o.decision(o.ping_summary(VALID)) == "UNKNOWN_EXIT_STATUS_NOT_OBSERVED"
