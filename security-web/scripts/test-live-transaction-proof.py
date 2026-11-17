#!/usr/bin/env python3
"""Live njs -> AF_PACKET/Lua -> Rust acceptance in a disposable user/net namespace.
No synthetic packets or Python-issued proofs. Optional isolated kernel guard tests.
Run only after explicit authorization for namespace capture.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import ssl
import subprocess
import time
import threading
from unittest.mock import patch
import yaml
import importlib.util

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

njs = load('live_njs', 'test-njs-proof.py')
bridge = load('live_bridge', 'proof-chain-offline.py')

def index_http(events):
    result = {}
    for event in events:
        if event.get('event_type') != 'http':
            continue
        key = (str(event['flow_id']), event['tx_id'])
        if key in result:
            raise ValueError('Duplicate observed HTTP transaction: ' + str(key))
        result[key] = event
    return result


REQUIRED_CASES = (
    'key_dac', 'baseline_capture', 'guard_deletion_under_load',
    'fake_after_deletion', 'replay_after_deletion', 'aborted_headers',
    'incomplete_response', 'missing_receipt', 'nginx_restart', 'nginx_crash',
    'restart_key_rotation', 'crash_key_rotation', 'rust_verification', 'passive_stop',
)

class Results:
    def __init__(self):
        self.cases = {name: {'status': 'NOT_RUN'} for name in REQUIRED_CASES}
        self.active = None

    def start(self, name):
        if name not in self.cases: raise ValueError(name)
        self.active = name

    def passed(self, name, **evidence):
        if name not in self.cases:
            raise ValueError('Unknown case: ' + name)
        if 'status' in evidence:
            raise ValueError('status is reserved for execution state; use http_status')
        if self.cases[name]['status'] == 'FAIL':
            raise ValueError('Cannot overwrite a failed case')
        self.cases[name] = {'status': 'PASS', **evidence}
        if self.active == name: self.active = None
        print(json.dumps({'case': name, **self.cases[name]}), flush=True)

    def failed(self, error):
        name = self.active or 'harness'
        self.cases[name] = {'status': 'FAIL', 'error_type': type(error).__name__}

    def summary(self):
        states = [value['status'] for value in self.cases.values()]
        result = 'FAIL' if 'FAIL' in states else ('PASS' if all(s == 'PASS' for s in states) else 'INCOMPLETE')
        return {'result': result, 'cases': self.cases,
                'pending': [name for name, value in self.cases.items() if value['status'] == 'NOT_RUN']}


class Stack(njs.Stack):
    guarded = False

    @classmethod
    def rotate(cls):
        super().rotate()
        if cls.guarded:
            os.chown(cls.keyfile, 0, 65534)
            cls.keyfile.chmod(0o640)


    @classmethod
    def config_snippet(cls):
        text = super().config_snippet()
        text = text.replace(f'127.77.0.2:{cls.egress_port}', '127.77.0.2:18080')
        cls.egress_port = 18080
        if cls.guarded:
            cls.work.chmod(0o750)
            os.chown(cls.work, 0, 65534)
            text = text.replace('js_var $probe_key_gid;', 'js_var $probe_key_gid 65534;')
        # Test upstream pool forces real Edge->Egress keepalive transactions.
        text = 'upstream proof_capture { server 127.77.0.2:18080; keepalive 16; }\n' + text
        text = text.replace('proxy_pass http://127.77.0.2:18080;', 'proxy_pass http://proof_capture;')
        text = text.replace('proxy_set_header Host $http_host;', 'proxy_set_header Host $http_host;\n proxy_set_header Connection "";')
        text = 'map $request_uri $live_receipt { default $probe_receipt; /api/no-receipt ""; }\n' + text
        text = text.replace('add_header X-WS-Receipt $probe_receipt always;', 'add_header X-WS-Receipt $live_receipt always;')
        return text

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--isolated-root', action='store_true', help='Explicit root mode in an already isolated network namespace')
    parser.add_argument('--rust-test-binary', type=Path, help='Prebuilt Rust test executable; required for root mode')
    parser.add_argument('--kernel-cgroup', type=Path, help='Internal outer isolated harness only')
    args = parser.parse_args()
    if not __debug__:
        parser.error('Do not run acceptance with Python -O; assertions are required')
    results = Results()
    mappings = Path('/proc/self/uid_map').read_text().splitlines()
    if args.isolated_root and (os.geteuid() != 0 or args.rust_test_binary is None):
        parser.error('Root capture requires a prebuilt Rust test binary')
    if not args.isolated_root and (len(mappings) != 1 or mappings[0].split()[2] != '1'):
        parser.error('Requires disposable single-user mapped namespace; refuses host root')
    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        parser.error('Refusing host network namespace')
    links = json.loads(subprocess.check_output(['ip', '-j', 'link'], text=True))
    if {r['ifname'] for r in links} != {'lo'}:
        parser.error('Refusing namespace with external interfaces')
    guard = None
    if args.kernel_cgroup:
        import re
        if not args.isolated_root or args.kernel_cgroup.parent != Path('/sys/fs/cgroup') or not re.fullmatch(r'ws-egress-test-[0-9a-f]{32}', args.kernel_cgroup.name):
            parser.error('Invalid isolated cgroup scope')
        manager = load('live_guard', 'local-egress-guard.py')
        guard = manager.Guard(args.kernel_cgroup.name + '/allowed', 65534)
        Stack.guarded = True
    module = args.module.resolve(strict=True)
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True)
    subprocess.run(['ip', 'addr', 'add', '192.0.2.10/32', 'dev', 'lo'], check=True)
    original_write, original_popen = Path.write_text, subprocess.Popen
    def write(path, text, *a, **kw):
        if path.name == 'nginx.conf':
            identity = 'nobody nogroup' if guard else 'root root'
            text = f'load_module {module};\nuser {identity};\nworker_processes 4;\n' + text
        return original_write(path, text, *a, **kw)
    def popen(command, *a, **kw):
        if Path(command[0]).name == 'nginx':
            command = [v.replace('master_process off;', 'master_process on;') for v in command]
            if guard:
                command = [os.sys.executable, '-c',
                    "import os,sys;open(sys.argv[1],'w').write(str(os.getpid()));os.execv(sys.argv[2],sys.argv[2:])",
                    str(args.kernel_cgroup / 'allowed/cgroup.procs')] + command
        return original_popen(command, *a, **kw)
    sensor = None
    console = None
    with patch.object(Path, 'write_text', write), patch.object(subprocess, 'Popen', popen):
        Stack.setUpClass()
    try:
        if guard:
            results.start('key_dac')
            guard.arm(); guard.grant()
            assert guard.ready()
            # Privileged fixture uses existing numeric nobody solely in this isolated test.
            # Verify DAC from real child processes without printing any key bytes.
            for uid, gid, expected in [(65533, 65533, False), (65534, 65534, True)]:
                probe = subprocess.run([os.sys.executable, '-c',
                    "import os,sys;os.setgroups([]);os.setgid(int(sys.argv[2]));os.setuid(int(sys.argv[1]));open(sys.argv[3],'rb').read()",
                    str(uid), str(gid), str(Stack.keyfile)], capture_output=True)
                assert (probe.returncode == 0) == expected
            results.passed('key_dac', foreign_uid_read=False, worker_uid_read=True)
            print('KEY_DAC: foreign UID denied; worker UID readable (inside trust boundary)', flush=True)
        handler = Stack.upstream.RequestHandlerClass
        original_get = handler.do_GET
        load_entered = threading.Event()
        load_release = threading.Event()
        load_lock = threading.Lock()
        load_count = [0]
        def fault_response(self):
            if self.path.startswith('/api/probe?guard-delete='):
                with load_lock:
                    load_count[0] += 1
                    if load_count[0] == 4: load_entered.set()
                if not load_release.wait(10):
                    self.close_connection = True
                    return
            if self.path == '/api/incomplete':
                Stack.upstream_headers.append(dict(self.headers))
                self.send_response(200)
                self.send_header('Content-Length', '100000')
                self.end_headers()
                self.wfile.write(b'partial'); self.wfile.flush()
                self.close_connection = True
            else:
                original_get(self)
        handler.do_GET = fault_response
        generation = secrets.token_hex(16)  # Fresh generation per actual sensor invocation.
        bridge.write_lua(Stack.work)
        config = njs.egress.sensor.render(yaml.safe_load((HERE.parent / 'config/suricata/suricata.yaml').read_text()), 'local-egress')
        config.pop('run-as', None)
        config.update({'unix-command': {'enabled': False}, 'default-log-dir': str(Stack.work),
                       'classification-file': '/etc/suricata/classification.config',
                       'reference-config-file': '/etc/suricata/reference.config'})
        config['outputs'] = [
            {'eve-log': {'enabled': True, 'filetype': 'regular', 'filename': 'live-eve.json',
                         'types': ['alert', {'http': {'extended': True, 'dump-all-headers': 'none'}}]}},
            {'lua': {'enabled': True, 'scripts-dir': str(Stack.work), 'scripts': ['chain.lua']}}]
        config_path = Stack.work / 'live.yaml'
        config_path.write_text('%YAML 1.1\n---\n' + yaml.safe_dump(config))
        command = ['suricata', '-c', str(config_path), '-S', str(HERE.parent / 'suricata/pbl4.rules'),
                   '-l', str(Stack.work), '--pidfile', str(Stack.work / 'sensor.pid')]
        subprocess.run(command + ['-T'], check=True, capture_output=True, timeout=30)
        console = (Stack.work / 'sensor-console.log').open('w')
        sensor = subprocess.Popen(command + ['--af-packet=lo', '--runmode', 'single'], stdout=console, stderr=console)
        deadline = time.monotonic() + 20
        while True:
            logs = ''.join(p.read_text() for p in [Stack.work / 'sensor-console.log', Stack.work / 'suricata.log'] if p.exists())
            if 'Engine started' in logs: break
            if sensor.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Live sensor did not become ready')
            time.sleep(.1)
        context = ssl.create_default_context(cafile=str(Stack.cert))
        def connection():
            return http.client.HTTPSConnection('127.0.0.1', Stack.tls_port, context=context,
                                              source_address=('192.0.2.10', 0), timeout=5)
        def request(target, conn=None):
            c = conn or connection()
            c.request('GET', target, headers={'X-Forwarded-For': '192.0.2.99',
                                            'X-Request-Id': 'b'*32, 'X-WS-Proof': 'forged'})
            r = c.getresponse(); r.read()
            assert r.status == 204, r.status
            assert r.getheader('X-WS-Receipt') is None and r.getheader('X-WS-Proof') is None
            rid = r.getheader('X-Request-Id')
            assert rid and rid != 'b'*32
            if conn is None: c.close()
            return rid
        c = connection()
        targets = ['/api/probe', '/api/probe?q=%27%20OR%201=1',
                   '/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E', '/api/probe?file=../../etc/passwd']
        ids = [request(t, c) for t in targets]
        c.close()
        # Stay below the existing 20 r/s + burst40 policy; do not disable Edge Protection.
        with ThreadPoolExecutor(max_workers=8) as pool:
            for batch in range(8):
                ids.extend(pool.map(lambda i: request('/api/probe?live='+str(i)), range(batch*8, batch*8+8)))
                time.sleep(.5)
        assert len(set(ids)) == 68
        if guard:
            results.start('guard_deletion_under_load')
            blocked = http.client.HTTPConnection('127.77.0.2', 18080,
                source_address=('127.77.0.1', 0), timeout=.5)
            try:
                blocked.request('GET', '/api/guard-forged', headers={'X-WS-Proof': 'fake'})
                blocked.getresponse()
                raise AssertionError('Kernel guard admitted foreign socket')
            except (OSError, http.client.HTTPException):
                pass
            finally: blocked.close()
            # Genuine Edge traffic overlaps deletion of the real UID+cgroup table.
            # HMAC, not polling readiness, must protect the now unguarded listener.
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(request, '/api/probe?guard-delete='+str(i)) for i in range(4)]
                try:
                    assert load_entered.wait(4), 'four live upstream requests required before deletion'
                    subprocess.run(['nft', 'delete', 'table', 'inet', manager.TABLE], check=True)
                finally:
                    load_release.set()
                ids.extend(f.result() for f in futures)
            assert not guard.ready()
            results.passed('guard_deletion_under_load', active_mock_requests=load_count[0], completed_requests=4)
            print('GUARD_DELETED_UNDER_LOAD: direct fake/replay probes follow without kernel policy', flush=True)
        # Abort before a complete request exists. Edge must not forward partial headers.
        results.start('aborted_headers')
        aborted_before = len(Stack.upstream_headers)
        c = connection(); c.connect()
        c.sock.sendall(b'GET /api/aborted HTTP/1.1\r\nHost: lab\r\nX-Incomplete: ')
        c.close()
        time.sleep(.1)
        assert len(Stack.upstream_headers) == aborted_before
        results.passed('aborted_headers', scope='partial headers only', mock_delta=0)
        rejected_ids = []
        fault_ids = {}
        fault_status = {}
        for target in ('/api/no-receipt', '/api/incomplete'):
            results.start('missing_receipt' if target == '/api/no-receipt' else 'incomplete_response')
            c = connection()
            c.request('GET', target)
            r = c.getresponse()
            fault_rid = r.getheader('X-Request-Id')
            assert fault_rid
            rejected_ids.append(fault_rid)
            fault_ids[target] = fault_rid
            fault_status[target] = r.status
            if target == '/api/no-receipt': assert r.status == 204
            try:
                r.read()
                assert target == '/api/no-receipt' or r.status == 502
            except http.client.IncompleteRead:
                assert target == '/api/incomplete'
            finally: c.close()
        results.start('fake_after_deletion')
        before = len(Stack.upstream_headers)
        c = http.client.HTTPConnection('127.77.0.2', 18080, source_address=('127.77.0.1', 0), timeout=5)
        c.request('GET', '/api/forged', headers={'X-WS-Proof': 'invalid', 'X-Forwarded-For': '192.0.2.99',
                                               'X-Request-Id': 'b'*32, 'X-Forwarded-Proto': 'https'})
        r = c.getresponse(); r.read()
        assert r.status in (400, 403) and r.getheader('X-WS-Receipt') is None
        c.close()
        assert len(Stack.upstream_headers) == before
        assert all(not any(k.lower() in ('x-ws-proof', 'x-ws-receipt') for k in h) for h in Stack.upstream_headers)
        if guard: results.passed('fake_after_deletion', http_status=r.status, mock_delta=0, receipt=False)
        # Replay only a real Edge-issued proof observed by Lua; never synthesize a MAC.
        deadline = time.monotonic() + 5
        captured = None
        while time.monotonic() < deadline:
            chain = Stack.work / 'chain.tsv'
            for line in chain.read_text().splitlines() if chain.exists() else []:
                fields = line.split('\t')
                if len(fields) == 8 and fields[5] == ids[0]: captured = fields
            if captured: break
            time.sleep(.1)
        assert captured is not None, 'Lua did not emit baseline transaction'
        _, _, token, _, client, rid, scheme, host = captured
        results.start('replay_after_deletion')
        for label, proof, changes in [
            ('replay', token, {}),
            ('forged_xff', token, {'X-Forwarded-For': '192.0.2.99'}),
            ('forged_request_id', token, {'X-Request-Id': 'c'*32}),
            ('invalid_mac', token[:-64]+'0'*64, {})]:
            headers = {'Host': host, 'X-WS-Proof': proof, 'X-Forwarded-For': client,
                       'X-Real-IP': client, 'X-Request-Id': rid, 'X-Forwarded-Proto': scheme}
            headers.update(changes)
            c = http.client.HTTPConnection('127.77.0.2', 18080, source_address=('127.77.0.1', 0), timeout=5)
            c.request('GET', '/api/probe', headers=headers)
            r = c.getresponse(); r.read()
            assert r.status == 403 and r.getheader('X-WS-Receipt') is None, label
            c.close()
            assert len(Stack.upstream_headers) == before
        if guard: results.passed('replay_after_deletion', probes=4, http_status=403, mock_delta=0, receipt=False)
        captured_material = dict(Stack.material)
        # Rotate after closing the original master, before starting new workers.
        # Sensor stays live across restart; rejected old proofs must have no receipt.
        for crash in (False, True):
            lifecycle_case = 'nginx_crash' if crash else 'nginx_restart'
            rotation_case = 'crash_key_rotation' if crash else 'restart_key_rotation'
            results.start(lifecycle_case)
            previous_material = dict(Stack.material)
            if crash:
                children = Path(f'/proc/{Stack.process.pid}/task/{Stack.process.pid}/children').read_text().split()
                assert children, 'crash test requires observed worker processes'
                Stack.process.kill(); Stack.process.wait(timeout=5)
                for pid in children:
                    try: os.kill(int(pid), signal.SIGKILL)
                    except ProcessLookupError: pass
            else:
                Stack.process.terminate()
                Stack.process.wait(timeout=5)
            Stack.rotate()
            assert Stack.material['key'] != previous_material['key']
            assert Stack.material['epoch'] != previous_material['epoch']
            Stack.process = popen(Stack.command + ['-g', 'daemon off; master_process on;'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 5
            while True:
                c = http.client.HTTPConnection('127.77.0.2', 18080, source_address=('127.77.0.1', 0), timeout=1)
                try:
                    c.request('GET', '/api/probe', headers={'Host': host, 'X-WS-Proof': token,
                        'X-Forwarded-For': client, 'X-Real-IP': client, 'X-Request-Id': rid,
                        'X-Forwarded-Proto': scheme})
                    r = c.getresponse(); r.read()
                    assert r.status == 403 and r.getheader('X-WS-Receipt') is None
                    break
                except ConnectionRefusedError:
                    if time.monotonic() > deadline: raise
                    time.sleep(.05)
                finally: c.close()
            assert len(Stack.upstream_headers) == before
            assert sensor.poll() is None
            results.passed(lifecycle_case, http_status=403, mock_delta=0, sensor_alive=True)
            results.passed(rotation_case, epoch_changed=True, key_changed=True)
        results.start('baseline_capture')
        time.sleep(2)
        sensor.send_signal(signal.SIGINT); sensor.wait(timeout=15)
        console.close(); console = None
        events = [json.loads(line) for line in (Stack.work / 'live-eve.json').read_text().splitlines()]
        http_events = index_http(events)
        evidence, observations = [], []
        rejected, rejected_observations = [], []
        for line in (Stack.work / 'chain.tsv').read_text().splitlines():
            flow, tx, proof, receipt, client, rid, scheme, host = line.split('\t')
            if rid not in ids and rid not in rejected_ids:
                assert not receipt  # Rejected direct traffic never gains acceptance evidence.
                continue
            if rid in ids and not receipt:
                continue  # Captured replay rejection; original acceptance is counted separately.
            event = http_events[(flow, int(tx))]
            assert event['src_ip'] == '127.77.0.1' and event['dest_ip'] == '127.77.0.2'
            assert event['in_iface'] == 'lo'
            assert client == '192.0.2.10' and proof
            if rid in ids: assert receipt
            key = {'generation': generation, 'flow_id': flow, 'tx_id': int(tx)}
            row_list = rejected if rid in rejected_ids else evidence
            obs_list = rejected_observations if rid in rejected_ids else observations
            row_list.append({'tx': key, 'proof': proof, 'receipt': receipt})
            obs_list.append({'response_complete': rid != fault_ids['/api/incomplete'], 'tx': key, 'client': client, 'request_id': rid, 'scheme': scheme, 'host': host,
                'method': event['http']['http_method'], 'target_sha256': hashlib.sha256(event['http']['url'].encode()).hexdigest(),
                'observed_ms': int(datetime.fromisoformat(event['timestamp']).timestamp()*1000)})
        results.start('missing_receipt')
        assert len(rejected) == 2
        by_rid = {o['request_id']: e for e, o in zip(rejected, rejected_observations)}
        assert set(by_rid) == set(fault_ids.values())
        assert not by_rid[fault_ids['/api/no-receipt']]['receipt']
        assert len(evidence) == len(ids) and len({(e['tx']['flow_id'], e['tx']['tx_id']) for e in evidence}) == len(ids)
        flows = Counter(e['tx']['flow_id'] for e in evidence)
        assert max(flows.values()) > 1, 'No captured upstream keepalive'
        sids = Counter(e['alert']['signature_id'] for e in events if e.get('event_type') == 'alert')
        assert all(sids[sid] == 1 for sid in (1000002, 1000003, 1000004)), sids
        results.passed('baseline_capture', transactions=len(ids), sids=dict(sids))
        results.start('rust_verification')
        fixture = Stack.work / 'live-rust.json'
        with os.fdopen(os.open(fixture, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as f:
            json.dump({'key_hex': captured_material['key'], 'kid': captured_material['kid'], 'epoch': captured_material['epoch'],
                       'rows': evidence, 'observations': observations, 'rejected': rejected, 'rejected_observations': rejected_observations}, f)
        rust_command = ([str(args.rust_test_binary.resolve(strict=True)),
                         'transaction_proof::external_njs_suricata_batch', '--ignored', '--nocapture']
                        if args.rust_test_binary else
                        ['cargo', 'test', '--offline', '--manifest-path', str(HERE.parent/'Cargo.toml'),
                         'transaction_proof::external_njs_suricata_batch', '--', '--ignored', '--nocapture'])
        subprocess.run(rust_command, env=dict(os.environ, WS_PROOF_TEST_FIXTURE=str(fixture)),
                       check=True, timeout=120)
        results.passed('rust_verification', accepted=len(evidence), rejected=len(rejected))
        results.passed('missing_receipt', http_status=fault_status['/api/no-receipt'], receipt=False, rust_verified=False)
        results.passed('incomplete_response', http_status=fault_status['/api/incomplete'], rust_verified=False, completion_source='controlled fixture')
        results.start('passive_stop')
        request('/api/probe?sensor=stopped')
        results.passed('passive_stop', http_status=204)
        summary = results.summary()
        summary.update({'transport': 'live AF_PACKET', 'transactions': len(ids),
                        'sensor_generation': generation,
                        'runtime_readiness': 'NOT_ACCEPTED',
                        'limitations': ['timing unverified', 'journal rollback/revocation unresolved',
                                        'mid-body abort not tested', 'completion from controlled fixture',
                                        'crash replays initial epoch proof, not immediately preceding epoch']})
        print(json.dumps(summary), flush=True)
        if summary['result'] != 'PASS': raise RuntimeError('Required acceptance cases incomplete')
    except BaseException as error:
        results.failed(error)
        print(json.dumps(results.summary()), flush=True)
        raise
    finally:
        if sensor is not None and sensor.poll() is None:
            sensor.terminate()
            try: sensor.wait(timeout=10)
            except subprocess.TimeoutExpired: sensor.kill(); sensor.wait()
        if console is not None: console.close()
        Stack.tearDownClass()
        if guard and guard.owned: guard.revoke()

if __name__ == '__main__': main()
