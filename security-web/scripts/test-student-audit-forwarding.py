#!/usr/bin/env python3
"""Isolated real RELP test on loopback + temp files. No DB/system service changes.
RSYSLOG_MODULE_DIR may point to unpacked modules; set LD_LIBRARY_PATH for librelp.
"""
import json, os, pathlib, signal, socket, subprocess, tempfile, time, unittest
BIN=os.environ.get('RSYSLOG_BIN','rsyslogd')
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ForwardingTest(unittest.TestCase):
    def test_relp_restart_queue_rotation_and_large_json(self):
        with tempfile.TemporaryDirectory(prefix='pbl4-relp-test-') as temp:
            work=pathlib.Path(temp);logs=work/'logs';logs.mkdir();src=logs/'student-audit.log';src.touch()
            dest=work/'received.log';procs={}
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            for role in ('sender','receiver'):
                state=work/role;state.mkdir()
                conf=(ROOT/f'deploy/rsyslog/student-audit-{role}.conf').read_text()
                conf=conf.replace('/var/lib/pbl4-audit-'+role,str(state)).replace('192.168.20.1','127.0.0.1').replace('192.168.20.10','127.0.0.1').replace('port="2514"',f'port="{port}"')
                # Avoid overlapping IP replacement (.10 contains .1).
                conf=conf.replace('127.0.0.10','127.0.0.1')
                conf=conf.replace('/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log',str(src)).replace('/var/log/pbl4/student-audit.log',str(dest))
                modules=os.environ.get('RSYSLOG_MODULE_DIR')
                if modules:
                    for name in ('imrelp','omrelp'):conf=conf.replace(f'load="{name}"',f'load="{modules}/{name}.so"')
                (work/(role+'.conf')).write_text(conf)
                subprocess.run([BIN,'-N1','-f',str(work/(role+'.conf'))],check=True,capture_output=True)
            def start(role):
                output=open(work/(role+'.stderr'),'ab')
                procs[role]=subprocess.Popen([BIN,'-n','-i',str(work/(role+'.pid')),'-f',str(work/(role+'.conf'))],stdout=output,stderr=output)
                output.close()
            def stop(role):
                proc=procs.pop(role,None)
                if proc:
                    proc.terminate()
                    try:proc.wait(timeout=60)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
            events={}
            def append(identity,large=False):
                event={'schema_version':'1.0','source':'STUDENT_AUDIT','source_instance':'fixture','event_id':identity,'timestamp':'2026-10-30T00:00:00Z','fixture':('x'*12000 if large else 'safe')}
                events[identity]=event
                with src.open('a') as f:f.write(json.dumps(event,separators=(',',':'))+'\n')
            def received():
                result={}
                for path in work.glob('received.log*'):
                    for line in path.read_text().splitlines():
                        row=json.loads(line);result[row['event_id']]=row
                return result
            def wait_for(ids):
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    if ids<=received().keys():return
                    for role,proc in procs.items():
                        if proc.poll() is not None:self.fail(f'{role} exited: '+(work/(role+'.stderr')).read_text())
                    time.sleep(.1)
                self.fail('Timed out; '+''.join((work/(r+'.stderr')).read_text() for r in procs))
            try:
                start('receiver');start('sender');append('normal',True);wait_for({'normal'})
                stop('receiver');append('queued');time.sleep(1);stop('sender')
                start('sender');start('receiver');wait_for({'normal','queued'})
                # Receiver rename + HUP; sender rename/create while running.
                dest.rename(work/'received.log.1');procs['receiver'].send_signal(signal.SIGHUP)
                src.rename(logs/'student-audit.log.1');src.touch();append('rotated');wait_for({'rotated'})
                stop('sender');append('after-restart');start('sender');wait_for(set(events))
                self.assertEqual(received(),events)
                print('PASS: normal, >8KiB JSON, outage backlog, sender/receiver restart, both rotations; identities/content unchanged.')
            finally:
                for role in list(procs):stop(role)
if __name__=='__main__':unittest.main(verbosity=2)
