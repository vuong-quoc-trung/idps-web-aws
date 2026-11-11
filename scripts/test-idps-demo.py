#!/usr/bin/env python3
"""Demo approval/identity boundaries; fixture tests are never live evidence."""

import importlib.util
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


demo = module("idps-demo")
lab = module("hybrid-lab-proof")
sensor = module("three-source-shadow")
worker = module("ai-shadow-worker")
accept = module("hybrid-system-acceptance")


class DemoTests(unittest.TestCase):
    def test_health_refuses_backend_only_success_when_LAN_refuses(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); pointer=root/'pointer.json'
            pointer.write_text(json.dumps({'root':str(root),'pid':123,'start_ticks':456}))
            ready={'gateway':'http://192.168.1.28:18782','sensor':str(root/'sensor')}
            (root/'demo-ready.json').write_text(json.dumps(ready))
            (root/'guard').mkdir(); (root/'sensor').mkdir()
            (root/'guard/resource-status.json').write_text(json.dumps({'status':'RUNNING','heartbeat':__import__('time').time()}))
            (root/'sensor/status.json').write_text('{}')
            opener=Mock(); opener.open.side_effect=ConnectionRefusedError('LAN listener absent')
            with patch.object(demo,'POINTER',pointer), patch.object(demo,'process_identity',return_value=456), patch.object(demo.urllib.request,'build_opener',return_value=opener), patch.object(demo,'request',return_value={'status':'alive'}):
                value=demo.health_snapshot()
            self.assertEqual(value['status'],'UNHEALTHY')
            self.assertIn('LAN listener absent',value['errors'][0])

    def test_sensor_uses_distro_permitted_rootless_namespace(self):
        from unittest.mock import Mock
        with patch.object(sensor.shutil,'which',return_value='/usr/bin/podman'), patch.object(sensor.subprocess,'run',return_value=Mock(returncode=0)) as run:
            self.assertEqual(sensor.namespace_command(),['podman','unshare','unshare','-n'])
            self.assertEqual(run.call_args.args[0],['podman','unshare','unshare','-n','true'])

    def test_concurrent_heartbeat_and_final_writes_are_atomic(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wrapper-status.json'
            def write(i):
                for j in range(30):
                    accept.atomic(path, {'writer':i, 'step':j})
                    self.assertIn('writer', json.loads(path.read_text()))
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(8)))
            self.assertEqual(json.loads(path.read_text())['step'],29)
            self.assertEqual(list(Path(folder).glob('.writing-*')),[])

    def test_engine_readiness_ignores_previous_generation_log(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sensor.log'
            path.write_text('Engine started.\n')
            proc = Mock(); proc.poll.return_value = None
            with patch.object(sensor.time, 'monotonic', side_effect=[0, 1]), self.assertRaisesRegex(RuntimeError, 'readiness timed out'):
                sensor.wait_engine(proc, path, path.stat().st_size, timeout=.1)
            sensor.wait_engine(proc, path, 0, timeout=1)

    def test_dead_sensor_is_not_ready_even_if_log_has_engine_started(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sensor.log'; path.write_text('Engine started.\n')
            proc = Mock(); proc.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'before capture readiness'):
                sensor.wait_engine(proc, path, 0)

    def test_gateway_supports_explicit_all_source_and_legacy_subnet_modes(self):
        self.assertEqual(
            str(sensor.gateway_network("192.168.1.28", "192.168.1.0/24")),
            "192.168.1.0/24",
        )
        self.assertEqual(str(sensor.gateway_network("0.0.0.0", "0.0.0.0/0")), "0.0.0.0/0")
        for client in ["10.10.1.50", "192.168.122.224", "192.168.1.90", "203.0.113.5"]:
            self.assertIn(__import__('ipaddress').IPv4Address(client), sensor.gateway_network("0.0.0.0", "0.0.0.0/0"))
        for address, network in [
            ("8.8.8.8", "8.8.8.0/24"),
            ("192.168.2.28", "192.168.1.0/24"),
        ]:
            with self.assertRaises(ValueError):
                sensor.gateway_network(address, network)

    def test_gateway_rejects_outside_subnet_before_forwarding(self):
        class Journal:
            def __init__(self):
                self.rows = []

            def append(self, row):
                self.rows.append(row)

        with sensor.LabGateway(("127.0.0.1", 0), sensor.Relay) as server:
            server.allowed_network = sensor.gateway_network(
                "192.168.1.28", "192.168.1.0/24"
            )
            server.peer_journal = Journal()
            with socket.socket() as request:
                self.assertFalse(server.verify_request(request, ("192.168.2.2", 50000)))
                self.assertTrue(server.verify_request(request, ("192.168.1.20", 50000)))
            self.assertEqual(len(server.peer_journal.rows), 1)
            self.assertEqual(
                server.peer_journal.rows[0]["identity_scope"],
                "SOCKET_PEER_ONLY_NOT_REQUEST_CORRELATION",
            )

    def test_registry_cannot_promote_third_model_or_rewrite_pinned_model(self):
        path = worker.ROOT / "ai-training/MODEL_STRATEGY.json"
        worker.verify_active_strategy(path)
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "registry.json"
            for mutation in ["third", "promote", "weights", "threshold"]:
                value = json.loads(path.read_text())
                if mutation == "third":
                    value["strategic_models"].append(
                        {"id": "glu207", "live_allowed": False}
                    )
                elif mutation == "promote":
                    value["strategic_models"][1]["live_allowed"] = True
                elif mutation == "weights":
                    value["strategic_models"][0]["manifest_sha256"] = "0" * 64
                else:
                    value["strategic_models"][0]["threshold"] = 0.5
                target.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    worker.verify_active_strategy(target)

    def test_unattended_cli_cannot_approve_firewall(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pointer = root / "pointer.json"
            pointer.write_text(
                json.dumps({"root": str(root), "pid": os.getpid(), "start_ticks": 123})
            )
            with (
                patch.object(demo, "POINTER", pointer),
                patch.object(demo, "process_identity", return_value=123),
                patch.object(demo.sys, "argv", ["demo", "manual-proof"]),
                patch.object(demo.subprocess, "Popen") as spawn,
            ):
                with self.assertRaisesRegex(RuntimeError, "Explicit"):
                    demo.main()
                spawn.assert_not_called()
            self.assertFalse((root / "OPERATOR_PROOF_REQUEST.json").exists())

    def test_explicit_operator_action_only_queues_fixed_disposable_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pointer = root / "pointer.json"
            pointer.write_text(
                json.dumps({"root": str(root), "pid": os.getpid(), "start_ticks": 123})
            )
            (root / "demo-ready.json").write_text("{}")
            with (
                patch.object(demo, "POINTER", pointer),
                patch.object(demo, "process_identity", return_value=123),
                patch.object(
                    demo.sys,
                    "argv",
                    ["demo", "manual-proof", "--operator-approved-isolated-client"],
                ),
                patch.object(demo.subprocess, "Popen") as spawn,
            ):
                demo.main()
                spawn.assert_not_called()
            request = json.loads((root / "OPERATOR_PROOF_REQUEST.json").read_text())
            self.assertEqual(
                request["target"], "DISPOSABLE_NAMESPACE_CLIENT_10.203.17.2_ONLY"
            )
            self.assertEqual(request["actions"], ["BLOCK", "UNBLOCK", "TTL_EXPIRY"])
            self.assertFalse(request["host_firewall"])

    def test_stop_is_graceful_request_not_a_kill(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pointer = root / "pointer.json"
            pointer.write_text(
                json.dumps({"root": str(root), "pid": os.getpid(), "start_ticks": 123})
            )
            with (
                patch.object(demo, "POINTER", pointer),
                patch.object(demo, "process_identity", return_value=123),
                patch.object(demo.sys, "argv", ["demo", "stop"]),
                patch.object(demo.subprocess, "run") as run,
            ):
                demo.main()
                run.assert_not_called()
            self.assertTrue((root / "STOP").exists())

    def detector(self):
        return {
            "detectors": [
                {
                    "request_id": "a" * 32,
                    "correlation": {"status": "MATCHED", "late_event": False},
                    "request_ai": {"status": "SCORED", "request_id": "a" * 32},
                    "rules": [
                        {"id": 1, "source": "SURICATA", "basis": "SENSOR_TRANSACTION"}
                    ],
                }
            ]
        }

    def test_correlated_gate_requires_real_transaction_rule_and_matching_ai(self):
        value = self.detector()
        self.assertEqual(
            lab.verified_sensor_row(value, "a" * 32)["request_id"], "a" * 32
        )
        for source, basis in [("NGINX", "REQUEST_ID"), ("SURICATA", "FLOW_CONTEXT")]:
            value = self.detector()
            value["detectors"][0]["rules"][0].update(source=source, basis=basis)
            with self.assertRaises(AssertionError):
                lab.verified_sensor_row(value, "a" * 32)
        value = self.detector()
        value["detectors"][0]["request_ai"]["request_id"] = "b" * 32
        with self.assertRaises(AssertionError):
            lab.verified_sensor_row(value, "a" * 32)

    def test_late_or_ambiguous_correlation_is_not_certified(self):
        for field, value in [("status", "AMBIGUOUS"), ("late_event", True)]:
            page = self.detector()
            page["detectors"][0]["correlation"][field] = value
            with self.assertRaises(AssertionError):
                lab.verified_sensor_row(page, "a" * 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
