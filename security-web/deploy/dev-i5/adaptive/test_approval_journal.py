"""Exercise the operator journal in disposable storage with independent publisher processes."""
import concurrent.futures
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from contextlib import closing
from approve_session import emergency_stop, initialize, publish


class JournalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.run_dir = Path(tmp.name) / "run"
        self.state.mkdir()
        self.run_dir.mkdir()
        initialize(self.state)
        now = int(time.time())
        self.plan = dict(action="BLOCK_REQUEST", request_id="a"*32, selector="dev-canary",
                         issued=now, expires=now+60)

    def call(self, cancel=False):
        return publish(self.plan, self.plan["request_id"], self.plan["action"],
                       self.run_dir, os.getgid(), cancel, state=self.state)

    def test_revocation_and_reboot(self):
        for action, selector in [("BLOCK_REQUEST", "dev-canary"), ("BLOCK_SESSION", "b"*64+"."+"c"*64), ("BLOCK_ACCOUNT", "account-"+"b"*64)]:
            self.plan.update(action=action, selector=selector)
            self.assertEqual(self.call(), "APPROVED")
            self.assertEqual(self.call(), "ALREADY_ACTIVE")
            for reboot in [False, True]:
                self.assertEqual(self.call(True), "REVOKED")
                if reboot:
                    shutil.rmtree(self.run_dir)
                    self.run_dir.mkdir()
                with self.assertRaisesRegex(ValueError, "Revoked"):
                    self.call()
                self.assertFalse((self.run_dir / selector).exists())

    def test_expiry_and_new_evidence(self):
        self.call()
        with patch("approve_session.time.time", return_value=self.plan["expires"]):
            with self.assertRaisesRegex(ValueError, "expired"):
                self.call()
        self.call(True)
        self.plan["request_id"] = "d"*32
        self.assertEqual(self.call(), "APPROVED")
        self.plan["request_id"] = "a"*32
        self.call(True)
        self.assertTrue((self.run_dir / "dev-canary").read_text().startswith("d"*32))

    def test_crash_before_lease(self):
        with patch("approve_session.install_record", side_effect=OSError):
            with self.assertRaises(OSError):
                self.call()
        with self.assertRaisesRegex(ValueError, "Consumed"):
            self.call()

    def test_process_death_after_unlink(self):
        self.call()
        # Kill the publisher between removing the lease and committing REVOKED.
        script = """
import os, sys
from pathlib import Path
import approve_session as publisher
publisher.sync_directory = lambda directory: os._exit(77)
publisher.publish(None, 'a'*32, 'BLOCK_REQUEST', Path(sys.argv[1]), os.getgid(),
                  True, state=Path(sys.argv[2]))
"""
        run = subprocess.run([sys.executable, "-B", "-c", script, self.run_dir, self.state],
                             cwd=Path(__file__).parent)
        self.assertEqual(run.returncode, 77)
        with self.assertRaisesRegex(ValueError, "Consumed"):
            self.call()
        self.assertEqual(self.call(True), "REVOKED")
        self.assertFalse((self.run_dir/"dev-canary").exists())

    def test_concurrent_operators(self):
        args = (self.plan, self.plan["request_id"], "BLOCK_REQUEST", self.run_dir, os.getgid())
        with concurrent.futures.ProcessPoolExecutor(4) as pool:
            jobs = [pool.submit(publish, *args, cancel=i==2, state=self.state) for i in range(8)]
            for job in jobs:
                try:
                    self.assertIn(job.result(), ["APPROVED", "ALREADY_ACTIVE", "REVOKED"])
                except ValueError as exc:
                    self.assertEqual(str(exc), "Revoked decision")
        self.assertFalse((self.run_dir / "dev-canary").exists())
        with closing(sqlite3.connect(self.state/"approvals.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT revoked FROM decisions").fetchall(), [(1,)])
            self.assertLessEqual(db.execute("SELECT count(*) FROM audit WHERE outcome='APPROVED'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE outcome!='RESERVED'").fetchone()[0], 8)

    def test_persistent_stop(self):
        self.call()
        for _ in range(2):
            emergency_stop(self.state, {"BLOCK_REQUEST":self.run_dir})
        self.assertFalse((self.run_dir/"dev-canary").exists())
        self.plan["request_id"] = "e"*32
        with self.assertRaisesRegex(ValueError, "stop latched"):
            self.call()

    def test_auto_canary_window_cooldown_and_stop(self):
        now=self.plan["issued"]
        self.plan.update(oldest=now,evidence=["a"*32,"b"*32],expires=now+15)
        def tick():
            return publish(self.plan,self.plan["request_id"],"BLOCK_REQUEST",self.run_dir,
                           os.getgid(),state=self.state,auto_window=(now,now+300))
        self.plan["oldest"]=now-1
        with self.assertRaisesRegex(ValueError,"Outside"):
            tick()
        self.plan["oldest"]=now
        self.assertEqual(tick(),"APPROVED")
        self.assertEqual(tick(),"ALREADY_ACTIVE")
        self.call(True)
        self.plan["request_id"]="c"*32
        with self.assertRaisesRegex(ValueError,"cooldown"):
            tick()
        with patch("approve_session.time.time",return_value=now+80):
            self.plan.update(oldest=now+80,issued=now+80,expires=now+95)
            with self.assertRaisesRegex(ValueError,"consumed evidence"):
                tick()
            emergency_stop(self.state,{"BLOCK_REQUEST":self.run_dir})
            with self.assertRaisesRegex(ValueError,"stop latched"):
                tick()

    def test_missing_journal_and_ip(self):
        self.plan["action"] = "BLOCK_IP"
        with self.assertRaisesRegex(ValueError, "verified direct peer"):
            self.call()
        (self.state/"approvals.sqlite3").unlink()
        with self.assertRaises(FileNotFoundError):
            self.call()


if __name__ == "__main__":
    unittest.main()
