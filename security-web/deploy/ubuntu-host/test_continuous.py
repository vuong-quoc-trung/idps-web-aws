"""Isolated lifecycle checks. No service, network or production journal."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dev-i5/adaptive"))
import approve_session
import native_policy


class Continuous(unittest.TestCase):
    def setUp(self):
        self.actor = "a"*64
        self.start = int(time.time())-3600
        actions = {}
        for action,(rules,events,ttl) in native_policy.PROFILES.items():
            cfg = dict(rules=rules,events=events,ttl=ttl,source_instance="test",window_seconds=60,cooldown=60,immediate=[])
            if action in ("BLOCK_SESSION","BLOCK_ACCOUNT"):
                cfg["lab_actor"] = self.actor
            actions[action] = cfg
        self.policy = dict(start=self.start,actions=actions,mode="CONTINUOUS",scope_sha256="b"*64)

    def test_lifetime_and_boot_marker(self):
        self.assertEqual(native_policy.limits(self.policy),(self.start,None))
        with self.assertRaises(ValueError):
            native_policy.limits(self.policy | {"end":self.start+600})
        with self.assertRaises(ValueError):
            native_policy.limits(dict(start=self.start,end=self.start+601))
        marker = json.dumps(native_policy.ready_generation(self.policy)).encode()
        with patch.object(native_policy,"trusted_bytes",return_value=marker):
            native_policy.require_ready(self.policy)
            with self.assertRaises(ValueError):
                native_policy.require_ready(self.policy | {"start":self.start+1})

    def test_four_actions_retry_and_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            leases = state/"leases"
            leases.mkdir()
            approve_session.initialize(state)
            selectors = ["request-"+"b"*64, self.actor+"."+"b"*64, "account-"+self.actor, "ip-192.168.1.44"]
            with patch.object(native_policy,"current",return_value=self.policy), patch.object(native_policy,"require_ready"), patch.object(
                approve_session,"Path",side_effect=lambda p:leases if p=="/run/ws-native-leases" else Path(p)):
                for i,(action,cfg) in enumerate(self.policy["actions"].items()):
                    now = int(time.time())
                    ids = [f"{100*i+j:032x}" for j in range(cfg["events"])]
                    plan = dict(request_id=ids[0],action=action,evidence=ids,selector=selectors[i],
                                oldest=now-2,issued=now,expires=now+cfg["ttl"])
                    args = (plan,ids[0],action,leases,os.getgid())
                    kw = dict(state=state,auto_window=(self.start,None),native=cfg|{"action":action})
                    self.assertEqual(approve_session.publish(*args,**kw),"APPROVED")
                    self.assertEqual(approve_session.publish(*args,**kw),"ALREADY_ACTIVE")
                approve_session.emergency_stop(state,dict.fromkeys(self.policy["actions"],leases))
                self.assertEqual(list(leases.iterdir()),[])
                with self.assertRaisesRegex(ValueError,"Emergency stop"):
                    approve_session.publish(*args,**kw)


if __name__ == "__main__":
    unittest.main()
