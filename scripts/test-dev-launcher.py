#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import socket
import threading
import unittest

spec=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('dev-up-and-verify.py'))
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class LauncherTests(unittest.TestCase):
    def test_refuses_an_existing_listener(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1',0));server.listen();port=server.getsockname()[1]
            with self.assertRaises(OSError):launcher.free_port(port)

    def test_restart_probe_accepts_time_wait_without_claiming_a_live_port(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            server.bind(('127.0.0.1',0));server.listen();port=server.getsockname()[1]
            def accept():
                connection,_=server.accept();connection.shutdown(socket.SHUT_RDWR);connection.close()
            thread=threading.Thread(target=accept);thread.start()
            with socket.create_connection(('127.0.0.1',port)) as client:client.recv(1)
            thread.join(timeout=2)
        launcher.free_port(port)

if __name__=='__main__':unittest.main(verbosity=2)
