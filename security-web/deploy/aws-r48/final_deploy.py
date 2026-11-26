"""Install the dedicated ingress and the paired WebSentinel backend/frontend."""

import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

import r58
import refresh
import update

APP = Path('/opt/websentinel-final')
BACKUP = Path('/var/backups/websentinel-final')
UNIT = 'websentinel-aws-prevention.service'
UNIT_FILE = Path('/etc/systemd/system') / UNIT
DROP_IN = Path('/etc/systemd/system') / (update.SEC + '.d/95-final-prevention.conf')
OLD_BINARY = '64299518c6f18fbcc9d7ab54a304996e938e7463d0624765f892eee505a0935c'
OLD_INDEX = '876b73f3eafcb3811ca7f2f5a6abc8975c35194ddb023b9f5bdd35c715364e38'
SETTINGS = '''[Unit]
Wants=websentinel-aws-prevention.service
After=websentinel-aws-prevention.service

[Service]
EnvironmentFile=/opt/websentinel-final/prevention.env
'''
ENV = '''WS_AWS_SCOPED_PREVENTION=1
ENFORCEMENT_MODE=MANUAL
ENFORCE_ALLOWED_SUBNETS=10.254.63.2/32
'''
CORE = {'security.zst', 'security.sha256', 'final_deploy.py', 'scoped_actuator.py', UNIT, 'dist/index.html'}


def replace_dist(dist, source):
    # The parent stays on the serving filesystem for the rename.
    with tempfile.TemporaryDirectory(dir=dist.parent, prefix='.final-frontend-') as folder:
        staging = Path(folder)
        candidate = staging / 'candidate'
        shutil.copytree(source, candidate)
        previous = staging / 'previous'
        dist.rename(previous)
        try:
            candidate.rename(dist)
        except BaseException:
            previous.rename(dist)
            raise


def backup_dist(dist):
    shutil.copytree(dist, BACKUP / 'dist')
    manifest = {str(file.relative_to(BACKUP)): update.sha(file)
                for file in sorted(BACKUP.rglob('*')) if file.is_file()}
    update.replace(BACKUP / 'manifest.json', json.dumps(manifest, sort_keys=True))


def verify_backup():
    manifest = json.loads((BACKUP / 'manifest.json').read_bytes())
    assert manifest['security.bin'] == OLD_BINARY and manifest['dist/index.html'] == OLD_INDEX
    assert all(update.sha(BACKUP / name) == sha for name, sha in manifest.items())


def rollback():
    verify_backup()
    binary, dist = r58.paths()
    DROP_IN.unlink(missing_ok=True)
    update.run('systemctl', 'disable', '--now', UNIT, check=False)
    update.replace(binary, (BACKUP / 'security.bin').read_bytes(), 0o755)
    replace_dist(dist, BACKUP / 'dist')
    assert update.sha(update.ENV) == (BACKUP / 'environment.sha256').read_text()
    update.run('systemctl', 'daemon-reload')
    r58.restart()
    refresh.verify_host()
    r58.web_check(dist / 'index.html', True)
    print('FINAL_ROLLBACK=PASS', flush=True)


def install(stage):
    refresh.verify_host()
    refresh.verify_database()
    binary, dist = r58.paths()
    if any(path.exists() or path.is_symlink() for path in (BACKUP, DROP_IN, APP, UNIT_FILE)):
        raise RuntimeError('Previous final deployment artifacts exist')
    if update.sha(binary) != OLD_BINARY or update.sha(dist / 'index.html') != OLD_INDEX:
        raise RuntimeError('Unexpected serving version')
    manifest = json.loads((stage / 'manifest.json').read_bytes())
    assets = {name for name in manifest if re.fullmatch(r'dist/assets/[A-Za-z0-9_-]+\.(?:js|css|png|svg|webp|ico)', name)}
    if not assets or set(manifest) != CORE | assets:
        raise ValueError('Invalid deployment manifest')
    for name, digest in manifest.items():
        file = stage / name
        if file.is_symlink() or not file.is_file() or update.sha(file) != digest:
            raise ValueError(f'Artifact mismatch: {name}')
    for folder in (stage / 'dist', stage / 'dist/assets'):
        folder.chmod(0o755)
    for name in {'dist/index.html'} | assets:
        (stage / name).chmod(0o644)
    candidate = stage / 'candidate'
    update.run('zstd', '-qd', f'--patch-from={binary}', stage / 'security.zst', '-o', candidate)
    if update.sha(candidate) != (stage / 'security.sha256').read_text().strip():
        raise RuntimeError('Backend binary digest differs')
    BACKUP.mkdir(mode=0o700)
    update.replace(BACKUP / 'security.bin', binary.read_bytes())
    update.replace(BACKUP / 'environment.sha256', update.sha(update.ENV))
    backup_dist(dist)
    verify_backup()
    APP.mkdir(mode=0o750)
    serving_changed = False
    try:
        update.replace(APP / 'prevention.env', ENV)
        update.replace(APP / 'final_deploy.py', (stage / 'final_deploy.py').read_bytes())
        update.replace(APP / 'scoped_actuator.py', (stage / 'scoped_actuator.py').read_bytes())
        update.replace(UNIT_FILE, (stage / UNIT).read_bytes(), 0o644)
        update.run('systemctl', 'daemon-reload')
        update.run('systemd-analyze', 'verify', UNIT_FILE)
        update.run('systemctl', 'start', UNIT)
        socket = Path('/run/websentinel-aws-prevention/actuator.sock')
        for _ in range(40):
            if socket.is_socket():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('Actuator socket startup incomplete')
        update.run('ip', 'netns', 'exec', 'ws-c2-peer', 'curl', '-fsS', '--max-time', '4',
                   '--resolve', 'student-dut.duckdns.org:443:10.254.63.1',
                   '-o', '/dev/null', 'https://student-dut.duckdns.org/api/auth/csrf')
        DROP_IN.parent.mkdir(mode=0o755, exist_ok=True)
        serving_changed = True
        update.replace(DROP_IN, SETTINGS, 0o644)
        update.replace(binary, candidate.read_bytes(), 0o755)
        replace_dist(dist, stage / 'dist')
        update.run('systemctl', 'daemon-reload')
        r58.restart()
        r58.web_check(dist / 'index.html', True)
        update.run('systemctl', 'is-active', UNIT, update.SEC)
    except BaseException:
        if serving_changed:
            rollback()
        else:
            update.run('systemctl', 'stop', UNIT, check=False)
        UNIT_FILE.unlink(missing_ok=True)
        update.run('systemctl', 'daemon-reload')
        # Keep failed candidates and backup checksums outside the active paths.
        for path in (APP, BACKUP):
            attempt = Path(tempfile.mkdtemp(dir=path.parent, prefix='.websentinel-final-failed-'))
            path.rename(attempt / path.name)
        raise
    print('FINAL_DEPLOY=' + json.dumps({'backend_sha256': update.sha(binary),
                                           'frontend_sha256': update.sha(dist / 'index.html'),
                                           'rollback': str(BACKUP), 'unit': UNIT}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    if sys.argv[1:] == ['rollback']:
        rollback()
    else:
        install(Path(sys.argv[1]))
