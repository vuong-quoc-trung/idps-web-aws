#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import socket
import threading
import unittest
import tempfile
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('dev-up-and-verify.py'))
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class LauncherTests(unittest.TestCase):
    def test_http_up_does_not_mean_bootstrap_admin_transaction_is_committed(self):
        with patch.object(launcher,'sql',side_effect=['0','0','1']) as query,patch.object(launcher.time,'sleep'):
            launcher.wait_bootstrap_admin()
            self.assertEqual(query.call_count,3)

    def test_missing_or_recycled_pid_token_cannot_claim_liveness_or_kill(self):
        with patch.object(launcher,'process_token',return_value=None),patch.object(launcher.os,'killpg') as kill:
            self.assertFalse(launcher.owned_alive({'pid':123,'start_token':None}))
            launcher.stop_process('test',{'pid':123,'start_token':None})
            kill.assert_not_called()
        with patch.object(launcher,'process_token',return_value='new'):
            self.assertFalse(launcher.owned_alive({'pid':123,'start_token':'old'}))
            self.assertTrue(launcher.owned_alive({'pid':123,'start_token':'new'}))

    def test_delivery_probe_records_first_lost_datagram_and_recovers(self):
        class Response:
            def __init__(self,rid): self.headers={'X-Request-Id':rid}
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def read(self,*_): return b'{}'
        with tempfile.TemporaryDirectory() as folder:
            runtime=Path(folder);(runtime/'ai').mkdir()
            (runtime/'configuration.json').write_text('{"ports":{"edge":18780}}')
            with patch.object(launcher,'RUNTIME',runtime),patch.object(launcher.urllib.request,'urlopen',side_effect=[Response('a'*32),Response('b'*32)]),patch.object(launcher.time,'monotonic',side_effect=[0,11,12,13]),patch.object(launcher,'recent_ai_records',return_value=[{'worker_id':'worker','request_id':'b'*32,'status':'SCORED'}]):
                result=launcher.delivery_probe('worker')
            self.assertEqual(result['probe_count'],2)
            self.assertEqual(result['unscored_probe_ids'],['a'*32])
            self.assertEqual(result['transport'],'LOSSY_UNIX_DATAGRAM')
            self.assertEqual(__import__('json').loads((runtime/'ai/connection-check.json').read_text())['status'],'PASS')

    def test_recent_records_skip_partial_line_and_do_not_read_raw_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime=Path(folder);(runtime/'ai').mkdir()
            (runtime/'ai/results.jsonl').write_text('partial\n{"status":"READY"}\n')
            with patch.object(launcher,'RUNTIME',runtime):
                self.assertEqual(launcher.recent_ai_records(),[{'status':'READY'}])

    def test_opt_in_ai_sink_keeps_existing_sanitized_log_and_api_routing(self):
        snippet=(launcher.ROOT/'security-web/nginx/pbl4-local-demo.conf').read_text()
        generated=launcher.ai_shadow_nginx(snippet,Path('/tmp/private/nginx.sock'))
        self.assertIn('syslog:server=unix:/tmp/private/nginx.sock,tag=ai_shadow,nohostname',generated)
        self.assertIn('proxy_pass http://student_api;',generated)
        self.assertIn(str(launcher.RUNTIME/'nginx/access.log')+' idps_json;',generated)
        self.assertNotIn('$request_body',generated)
        self.assertNotIn('$http_cookie',generated)
        self.assertNotIn('$http_authorization',generated)

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
