"""Run the approved non-exploit canary on the single private staging ingress."""

from base64 import b64encode
from importlib.resources import files
import json
import os
import re
import secrets
import shutil
import subprocess
from time import monotonic


PROFILE = 'websecurity-staging'
REGION = 'ap-southeast-1'
INSTANCE = 'i-0b6f2e4f3ed32f514'
ACCOUNT = '680480584595'
PRINCIPAL = f'arn:aws:iam::{ACCOUNT}:user/Websecurity'
SESSION_ID = re.compile(rb'(?m)^Starting session with SessionId: ([A-Za-z0-9_-]{1,96})\r*$')
BLOCKERS = {
    'LAB_BUSY': 'Canary EC2 đang bận.',
    'LAB_ARTIFACT': 'Gói canary EC2 thiếu hoặc sai SHA.',
    'LAB_BASELINE': 'Binary gốc dành cho canary thiếu hoặc sai SHA.',
    'SSM_USER': 'SSM không chạy với tài khoản hệ thống dự kiến.',
}


class CanaryError(RuntimeError):
    """A bounded, safe-to-display live demo failure."""


def aws_command(*args):
    return ['aws', '--profile', PROFILE, '--region', REGION, '--output', 'json',
            '--no-cli-pager', '--no-cli-auto-prompt', '--cli-connect-timeout', '5',
            '--cli-read-timeout', '8', *args]


def aws_env():
    return os.environ | {'AWS_MAX_ATTEMPTS': '1', 'AWS_IGNORE_CONFIGURED_ENDPOINT_URLS': 'true'}


def identity():
    command = aws_command('sts', 'get-caller-identity')
    try:
        call = subprocess.run(command, env=aws_env(), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=18)
    except FileNotFoundError as error:
        raise CanaryError('Máy chạy simulator chưa có AWS CLI trong PATH.') from error
    except subprocess.TimeoutExpired as error:
        raise CanaryError('AWS CLI quá thời hạn. Hãy kiểm tra SSM trước khi chạy lại.') from error
    if call.returncode != 0:
        stderr = call.stderr.lower()
        if any(text in stderr for text in ('session has expired', 'expiredtoken', 'unable to locate credentials')):
            raise CanaryError(f'Phiên AWS CLI {PROFILE} chưa sẵn sàng hoặc đã hết hạn.')
        raise CanaryError('AWS CLI không xác minh được danh tính staging.')
    try:
        result = json.loads(call.stdout)
    except ValueError as error:
        raise CanaryError('AWS CLI trả kết quả không hợp lệ.') from error
    if not isinstance(result, dict):
        raise CanaryError('AWS CLI trả kết quả không hợp lệ.')
    return result


def readback(stdout):
    lines = stdout.splitlines()
    records = [line.removeprefix('R61_CANARY=') for line in lines if line.startswith('R61_CANARY=')]
    if len(records) != 1 or 'R60_HOST_READBACK_AND_CLEANUP=PASS' not in lines:
        raise CanaryError('Thiếu kết quả canary hoặc xác nhận dọn dẹp.')
    try:
        result = json.loads(records[0])
        rows = result['automatic']
        if len(rows) != 2 or result['db_kernel'] != 'SYNCED_EMPTY' or result['audit'] != '3 SUCCESS':
            raise ValueError
        unblock = result['manual_unblock']
        ttl = result['max_ttl_seconds']
        if type(unblock) is not int or unblock <= 0 or ttl != 6 or result['protected_scope'] != 'PASS':
            raise ValueError
        observations = []
        for row, expected in zip(rows, (('CANARY_RULE', 161001, 204), ('CANARY_HYBRID', 161002, 403))):
            rid, peer, action = row['request_id'], row['peer'], row['action_id']
            if (not re.fullmatch(r'[a-f0-9]{32}', rid) or len(peer) != 2 or peer[0] != '10.254.56.2'
                    or row['local'] != ['10.254.56.1', 18456] or type(action) is not int or action <= 0
                    or (row['source'], row['rule_sid'], row['status']) != expected):
                raise ValueError
            observations.append({key: row[key] for key in ('request_id', 'status', 'source', 'rule_sid', 'action_id')})
        if (len({row['request_id'] for row in observations}) != 2
                or len({unblock, *(row['action_id'] for row in observations)}) != 3):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise CanaryError('Bằng chứng canary không khớp phạm vi hoặc kết quả dự kiến.') from error
    return {'observations': observations, 'unblock_id': unblock, 'ttl_seconds': ttl,
            'db_kernel': result['db_kernel']}


def session(script):
    if os.name != 'posix' or not shutil.which('session-manager-plugin'):
        raise CanaryError('Chế độ live cần Session Manager plugin trong PATH trên Linux hoặc macOS.')
    import errno
    import pty
    import select
    import termios

    # A fresh Session Manager terminal runs only the fixed operator-side script.
    nonce = secrets.token_hex(16)
    encoded = b64encode(script.encode()).decode('ascii')
    command = (f"printf '%s' '{encoded}' | /usr/bin/base64 -d | /usr/bin/sudo -n /bin/sh; "
               f"status=$?; printf '\\nPBL4_RESULT_%s=%s\\n' '{nonce}' \"$status\"; exit \"$status\"\n").encode()
    terminal, child = pty.openpty()
    process = None
    transcript = bytearray()
    session_id = None
    try:
        attrs = termios.tcgetattr(child)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(child, termios.TCSANOW, attrs)
        process = subprocess.Popen(aws_command('ssm', 'start-session', '--target', INSTANCE),
                                   env=aws_env(), stdin=child, stdout=child, stderr=child)
        os.close(child)
        child = None
        deadline = monotonic() + 160
        while (remaining := deadline - monotonic()) > 0:
            if not select.select([terminal], [], [], min(1, remaining))[0]:
                continue
            try:
                data = os.read(terminal, 8192)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                break
            if not data:
                break
            transcript.extend(data)
            if len(transcript) > 160_000:
                raise CanaryError('Kết quả SSM vượt giới hạn.')
            if session_id is None and (matched := SESSION_ID.search(transcript)):
                session_id = matched[1].decode()
                if os.write(terminal, command) != len(command):
                    raise CanaryError('Không chuyển được toàn bộ lệnh canary vào SSM.')
            marker = re.search(rb'(?m)^PBL4_RESULT_' + nonce.encode() + rb'=([0-9]+)\r*$', transcript)
            if session_id is not None and marker:
                return session_id, int(marker[1]), transcript.decode(errors='replace')
        if b'AccessDenied' in transcript or b'is not authorized' in transcript:
            raise CanaryError(f'AWS từ chối ssm:StartSession cho profile {PROFILE}.')
        raise CanaryError('Không nhận được xác nhận kết thúc từ SSM. Kiểm tra phiên trước khi chạy lại.')
    finally:
        if child is not None:
            os.close(child)
        try:
            if process is not None:
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        finally:
            os.close(terminal)


def run():
    caller = identity()
    if caller.get('Account') != ACCOUNT or caller.get('Arn') != PRINCIPAL:
        raise CanaryError('AWS identity không khớp operator staging.')
    script = files('attack_simulator').joinpath('scripts', 'pbl4-canary.sh').read_text(encoding='utf-8')
    session_id, status, stdout = session(script)
    if status != 0:
        blocker = next((text for flag, text in BLOCKERS.items() if f'PBL4_BLOCKED={flag}' in stdout.splitlines()), None)
        raise CanaryError(f'{blocker or "Canary EC2 chưa hoàn tất thành công."} SSM {session_id}')
    return readback(stdout) | {'session_id': session_id}
