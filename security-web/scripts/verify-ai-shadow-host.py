#!/usr/bin/env python3
"""One harmless host/VM HTTP probe; verify its real inference journal result."""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--journal', type=Path, default=Path('/var/log/pbl4-ai-shadow/results.jsonl'))
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request('http://192.168.10.1/api/auth/me', headers={'User-Agent': 'PBL4-Host-AI-Acceptance'})
    try:
        response = opener.open(request, timeout=8)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        rid = response.headers.get('X-Request-Id', '')
        code = response.code
    if not re.fullmatch('[a-f0-9]{32}', rid):
        raise RuntimeError('Missing generated request ID; check installed NGINX config')
    print(f'HTTP={code}; request_id={rid}', flush=True)
    if code >= 500:
        raise RuntimeError('Upstream/server error: VM proxy acceptance has not passed')
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for path in [args.journal, Path(str(args.journal) + '.1')]:
            if not path.exists():
                continue
            with path.open() as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('request_id') == rid and event.get('kind') == 'inference':
                        if event.get('status') != 'SCORED':
                            raise RuntimeError('Inference was not SCORED')
                        print(json.dumps({key: event.get(key) for key in ['request_id', 'status', 'model_version', 'score', 'above_threshold', 'observed_at']}, indent=2))
                        print('PASS: HTTP + real worker result. DB/API/dashboard still require separate verification.')
                        return
        time.sleep(1)
    raise RuntimeError('No inference within 60s; inspect worker health, socket permissions and queue')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as exc:
        print('FAIL: ' + str(exc))
        raise SystemExit(1)
