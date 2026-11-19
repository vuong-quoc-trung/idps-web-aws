#!/usr/bin/env python3
"""Run ONLY in disposable user+network namespace; no host network access.
Example: unshare --user --map-root-user --net python3 this-script.py
"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import http.client
import ssl
import argparse
import yaml

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('egress_tests', HERE / 'test-nginx-egress.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)

class CaptureStack(tests.EgressTests):
    @classmethod
    def config_snippet(cls):
        snippet = super().config_snippet()
        snippet = snippet.replace(f'127.77.0.2:{cls.egress_port}', '127.77.0.2:18080')
        cls.egress_port = 18080
        return snippet

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, help='New directory for sanitized EVE evidence only; no key or packet files')
    parser.add_argument('--kernel-cgroup', type=Path, help='Internal isolated privileged harness only')
    args = parser.parse_args()
    # Refuse root in the initial user namespace or any namespace with external interfaces.
    mappings = Path('/proc/self/uid_map').read_text().splitlines()
    if not args.kernel_cgroup and (len(mappings) != 1 or mappings[0].split()[2] != '1'):
        raise RuntimeError('Requires disposable single-user mapped namespace')
    links = json.loads(subprocess.check_output(['ip', '-j', 'link'], text=True))
    if {item['ifname'] for item in links} != {'lo'}:
        raise RuntimeError('Refusing namespace with non-loopback interfaces')
    guard = None
    if args.kernel_cgroup:
        import re
        if (os.geteuid() != 0 or os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net')
            or args.kernel_cgroup.parent != Path('/sys/fs/cgroup')
            or not re.fullmatch(r'ws-egress-test-[0-9a-f]{32}', args.kernel_cgroup.name)):
            raise RuntimeError('Invalid isolated cgroup/network scope')
        manager = tests.load('manager', 'local-egress-guard.py')
        guard = manager.Guard(args.kernel_cgroup.name + '/allowed', 65534)
        guard.arm()
        guard.grant()
        assert guard.ready()
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True)
    # Synthetic client identity, local to this namespace, not a forged header.
    subprocess.run(['ip', 'addr', 'add', '192.0.2.10/32', 'dev', 'lo'], check=True)
    # NGINX default nobody user is unmapped in this single-user namespace.
    # Patch only the temporary harness config write, never a runtime file.
    from unittest.mock import patch
    original_write = Path.write_text
    def namespace_config(path, text, *args, **kwargs):
        if path.name == 'nginx.conf':
            text = ('user nobody nogroup;\n' if guard else 'user root root;\n') + text
            if guard: path.parent.chmod(0o755)
        return original_write(path, text, *args, **kwargs)
    original_popen = subprocess.Popen
    def isolated_nginx(command, *a, **kw):
        if guard and Path(command[0]).name == 'nginx':
            command = [part.replace('master_process off;', 'master_process on;') for part in command]
            # Enter the dedicated cgroup before exec; workers inherit it. Avoid
            # preexec_fn in the threaded mock-upstream process.
            command = [os.sys.executable, '-c',
                "import os,sys;open(sys.argv[1], 'w').write(str(os.getpid()));os.execv(sys.argv[2],sys.argv[2:])",
                str(args.kernel_cgroup / 'allowed/cgroup.procs')] + command
        return original_popen(command, *a, **kw)
    with patch.object(Path, 'write_text', namespace_config), patch.object(subprocess, 'Popen', isolated_nginx):
        try:
            CaptureStack.setUpClass()
        except subprocess.CalledProcessError as error:
            raise RuntimeError(error.stderr) from error
    stack = CaptureStack
    process = None
    try:
        if guard:
            def stop_nginx():
                if stack.process.poll() is None:
                    stack.process.terminate()
                    stack.process.wait(timeout=5)
            def start_nginx():
                import socket
                stack.process = isolated_nginx(stack.command + ['-g', 'daemon off; master_process on;'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 3
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1', stack.port), timeout=.1): break
                    except OSError:
                        if time.monotonic() > deadline: raise RuntimeError('NGINX restart failed')
                        time.sleep(.02)
            lifecycle = manager.Lifecycle(guard, start_nginx, stop_nginx,
                lambda: stack.process.send_signal(signal.SIGHUP), lambda: stack.process.poll() is None)
            lifecycle.reload()
            time.sleep(.2)
            lifecycle.restart()
            assert lifecycle.tick()
            print('NGINX_LIFECYCLE: reload/restart completed; guard snapshot ready', flush=True)
        base = yaml.safe_load((HERE.parent / 'config/suricata/suricata.yaml').read_text())
        config = tests.sensor.render(base, 'local-egress')
        config.pop('run-as', None)
        config['unix-command'] = {'enabled': False}
        config['default-log-dir'] = str(stack.work)
        config['classification-file'] = '/etc/suricata/classification.config'
        config['reference-config-file'] = '/etc/suricata/reference.config'
        for output in config['outputs']:
            if 'eve-log' in output:
                output['eve-log']['filename'] = 'eve.json'
        path = stack.work / 'sensor.yaml'
        path.write_text('%YAML 1.1\n---\n' + yaml.safe_dump(config))
        command = ['suricata', '-c', str(path), '-S', str(HERE.parent / 'suricata/pbl4.rules'),
                   '-l', str(stack.work), '--pidfile', str(stack.work / 'suricata.pid')]
        subprocess.run(command + ['-T'], check=True, capture_output=True)
        output = (stack.work / 'capture-console.log').open('w')
        process = subprocess.Popen(command + ['--af-packet=lo', '--runmode', 'single'], stdout=output, stderr=output)
        deadline = time.monotonic() + 15
        while True:
            console = (stack.work / 'capture-console.log').read_text()
            log = (stack.work / 'suricata.log').read_text() if (stack.work / 'suricata.log').exists() else ''
            if 'Engine started' in console + log: break
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Sensor startup failed: ' + console + log)
            time.sleep(.1)
        context = ssl.create_default_context(cafile=str(stack.cert))
        connection = http.client.HTTPSConnection('127.0.0.1', stack.tls_port, context=context,
            source_address=('192.0.2.10', 0), timeout=5)
        cases = [('baseline', '/api/probe'), ('sqli', '/api/probe?q=%27%20OR%201=1'),
                 ('xss', '/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E'),
                 ('traversal', '/api/probe?file=../../etc/passwd')]
        for name, target in cases:
            connection.request('GET', target)
            response = connection.getresponse()
            response.read()
            print(json.dumps({'probe': name, 'status': response.status,
                              'request_id': response.getheader('X-Request-Id')}), flush=True)
            assert response.status == 204
        connection.close()
        forged = http.client.HTTPConnection('127.77.0.2', 18080,
            source_address=('127.77.0.1', 0), timeout=5)
        try:
            forged.request('GET', '/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E', headers={
                'X-Request-Id':'b'*32, 'X-Forwarded-For':'192.0.2.99', 'X-Forwarded-Proto':'https'})
            response = forged.getresponse()
            response.read()
            if guard: raise AssertionError('Forged request reached egress')
            print(json.dumps({'probe':'forged', 'status':response.status}), flush=True)
        except (OSError, http.client.HTTPException):
            if not guard: raise
            print(json.dumps({'probe':'forged', 'blocked':True}), flush=True)
        finally:
            forged.close()
        time.sleep(2)
        process.send_signal(signal.SIGINT)
        process.wait(timeout=15)
        output.close()
        rows = [json.loads(line) for line in (stack.work / 'eve.json').read_text().splitlines()]
        alerts = [r for r in rows if r.get('event_type') == 'alert']
        http_rows = [r for r in rows if r.get('event_type') == 'http']
        safe = []
        for r in alerts + http_rows:
            safe.append({k:r.get(k) for k in ['event_type','src_ip','dest_ip','in_iface','flow_id','tx_id','app_proto']} | {
                'sid':r.get('alert',{}).get('signature_id'),
                'xff':r.get('alert',{}).get('xff',r.get('http',{}).get('xff')),
                'method':r.get('http',{}).get('http_method'), 'status':r.get('http',{}).get('status')})
        if args.evidence:
            args.evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
            # Keep only actual parser inputs required for attribution/detection.
            selected = []
            for r in alerts + http_rows:
                row = {k:r[k] for k in ['timestamp','event_type','src_ip','src_port','dest_ip','dest_port',
                    'proto','in_iface','flow_id','tx_id','app_proto','direction'] if k in r}
                for section, keys in [('alert', ['signature_id','severity','xff']),
                                      ('http', ['http_method','status','xff'])]:
                    if section in r:
                        row[section] = {k:r[section][k] for k in keys if k in r[section]}
                selected.append(row)
            (args.evidence / 'eve.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in selected))
        for r in safe: print('EVE ' + json.dumps(r), flush=True)
        for r in safe:
            assert r['src_ip'] == '127.77.0.1' and r['dest_ip'] == '127.77.0.2'
            assert r['in_iface'] == 'lo' and r['flow_id'] is not None and r['tx_id'] is not None
        for sid in [1000002,1000003,1000004]:
            assert sum(r.get('alert',{}).get('signature_id') == sid and r['alert'].get('xff') == '192.0.2.10' for r in alerts) == 1, sid
        assert len(http_rows) == (4 if guard else 5), len(http_rows)
        assert all(r.get('http',{}).get('status') == 204 for r in http_rows)
        assert sum(r.get('alert',{}).get('signature_id') == 1000003 and r['alert'].get('xff') == '192.0.2.99' for r in alerts) == (0 if guard else 1)
        # Passive sensor has actually stopped; verify proxy still serves.
        connection = http.client.HTTPSConnection('127.0.0.1', stack.tls_port, context=context, timeout=5)
        connection.request('GET','/api/probe')
        response = connection.getresponse(); response.read(); connection.close()
        assert response.status == 204
        if guard:
            assert guard.ready()
            print('GUARDED_CAPTURE_PASS: 4 HTTP; 3 SIDs once each; no forged HTTP/alert; sensor-stop HTTP=204', flush=True)
            subprocess.run(['nft', 'delete', 'table', 'inet', manager.TABLE], check=True)
            assert not guard.ready()
            assert not lifecycle.tick()
            assert stack.process.poll() is not None
            assert not guard.ready()  # restored deny table must not restore trust
            print('DELETION_DETECTED: NGINX stopped; deny-only restored; trust remains false. Detection gap is NOT claimed closed.', flush=True)
            return
        print('CAPTURE_PASS: 5 HTTP transactions; 3 legitimate SIDs once each; forged XSS captured; sensor-stop HTTP=204', flush=True)
        print('TRUST_BOUNDARY_FAIL: source-bound local process supplied accepted forged XFF; trust must remain false', flush=True)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        stack.tearDownClass()
        if guard: guard.revoke()

if __name__ == '__main__': main()
