#!/usr/bin/env python3
"""Non-root filesystem/socket ACL inheritance test; no real AI socket touched."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('acl', Path(__file__).with_name('prepare-ai-socket-acl.py'))
acl=importlib.util.module_from_spec(spec);spec.loader.exec_module(acl)

class Tests(unittest.TestCase):
    def test_rebind_and_chmod_preserve_named_writer(self):
        # Numeric ACL does not require creating an account.
        uid = 65534 if os.getuid() != 65534 else 65533
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)
            directory.chmod(0o710)
            acl.apply(directory, uid)
            for _ in range(2):
                path=directory/'nginx.sock'
                with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
                    sock.bind(str(path));path.chmod(0o620)
                    output=subprocess.check_output(['getfacl','-ncp',str(path)],text=True)
                    self.assertIn(f'user:{uid}:-w-',output)
                    self.assertIn('mask::-w-',output)
                    self.assertIn('other::---',output)
                path.unlink()
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            link=Path(d)/'link';link.symlink_to(d)
            with self.assertRaises(ValueError): acl.apply(link,65534)

if __name__=='__main__': unittest.main(verbosity=2)
