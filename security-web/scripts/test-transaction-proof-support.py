#!/usr/bin/env python3
"""Offline capability probe only. Synthetic proofs, no cryptography or live traffic."""
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import yaml


def pcap(path, transactions=None):
    packets = []
    client, server = socket.inet_aton('127.77.0.1'), socket.inet_aton('127.77.0.2')
    def add(reverse, seq, ack, flags, payload=b''):
        src, dst = (server, client) if reverse else (client, server)
        ports = (18080, 40000) if reverse else (40000, 18080)
        tcp = struct.pack('!HHIIBBHHH', *ports, seq, ack, 80, flags, 65535, 0, 0) + payload
        ip = struct.pack('!BBHHHBBH4s4s', 69, 0, 20 + len(tcp), 0, 0, 64, 6, 0, src, dst)
        packets.append(b'\0' * 12 + b'\x08\x00' + ip + tcp)
    add(False, 100, 0, 2); add(True, 200, 101, 18); add(False, 101, 201, 16)
    c, s = 101, 201
    for i in range(len(transactions) if transactions is not None else 2):
        req = (f'GET /probe{i} HTTP/1.1\r\nHost: lab\r\nX-WS-Proof: proof{i}\r\nCookie: SECRET_CANARY\r\n\r\n').encode()
        resp = (f'HTTP/1.1 204 No Content\r\nX-WS-Receipt: receipt{i}\r\n\r\n').encode()
        if transactions is not None: req, resp = transactions[i]
        add(False, c, s, 24, req); c += len(req)
        add(True, s, c, 24, resp); s += len(resp)
        add(False, c, s, 16)
    add(False, c, s, 17); add(True, s, c + 1, 17); add(False, c + 1, s + 1, 16)
    with path.open('wb') as f:
        f.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        for i, packet in enumerate(packets):
            f.write(struct.pack('<IIII', 1700000000, i * 10000, len(packet), len(packet)))
            f.write(packet)


def main():
    with tempfile.TemporaryDirectory(prefix='ws-proof-support-') as directory:
        work = Path(directory)
        nginx = work / 'nginx.conf'
        nginx.write_text(f'pid {work}/nginx.pid; error_log stderr; events {{}} http {{ js_shared_dict_zone zone=probe:64k; }}')
        result = subprocess.run(['nginx', '-t', '-p', directory, '-c', str(nginx)], capture_output=True, text=True)
        print('NGINX_NJS_CONFIG:', 'PASS' if result.returncode == 0 else 'UNAVAILABLE', result.stderr.strip())
        lua = work / 'proof.lua'
        lua.write_text('''local http = require("suricata.http")
local flow = require("suricata.flow")
local config = require("suricata.config")
function init(args) return {protocol="http"} end
function setup(args) file = assert(io.open(config.log_path() .. "/proof.tsv", "a")) end
function log(args)
 local tx = http.get_tx()
 local f = flow.get()
 local proof = tx:request_header("X-WS-Proof") or "missing"
 local receipt = tx:response_header("X-WS-Receipt") or "missing"
 local id = "unavailable"
 if args and type(args.tx_id) == "number" then id = string.format("%.0f", args.tx_id) end
 file:write(tostring(f:id()) .. "\\t" .. id .. "\\t" .. proof .. "\\t" .. receipt .. "\\n")
 file:flush()
end
function deinit(args) file:close() end
''')
        cfg = yaml.safe_load(Path('/etc/suricata/suricata.yaml').read_text())
        cfg.pop('run-as', None)
        cfg['default-log-dir'] = directory
        cfg['unix-command'] = {'enabled': False}
        cfg['stats'] = {'enabled': False}
        cfg['outputs'] = [{'eve-log': {'enabled': True, 'filetype': 'regular', 'filename': 'eve.json', 'types': [{'http': {'extended': True, 'dump-all-headers': 'none'}}]}}, {'lua': {'enabled': True, 'scripts-dir': directory, 'scripts': ['proof.lua']}}]
        cfg['rule-files'] = []
        conf = work / 'suricata.yaml'; conf.write_text('%YAML 1.1\n---\n' + yaml.safe_dump(cfg))
        capture = work / 'test.pcap'; pcap(capture)
        result = subprocess.run(['suricata', '-c', str(conf), '-r', str(capture), '-l', directory, '-k', 'none', '--runmode', 'single'], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        proof = (work / 'proof.tsv').read_text()
        eve = (work / 'eve.json').read_text()
        assert 'SECRET_CANARY' not in proof + eve
        rows = [line.split('\t') for line in proof.splitlines()]
        events = [json.loads(line) for line in eve.splitlines() if json.loads(line).get('event_type') == 'http']
        assert len(rows) == len(events) == 2, (rows, events)
        for i, row in enumerate(rows):
            assert row[2:] == [f'proof{i}', f'receipt{i}'], rows
            assert row[0] == str(events[i]['flow_id']), (rows, events)
        print('SELECTIVE_HEADERS_204_KEEPALIVE: PASS', rows)
        print('EVE_TRANSACTION_IDS:', [(r['flow_id'], r['tx_id']) for r in events])
        print('LUA_TX_ID:', 'PASS' if all(row[1] == str(events[i]['tx_id']) for i, row in enumerate(rows)) else 'NOT_VERIFIED')
        print('COOKIE_EXCLUSION: PASS; synthetic PCAP only; checksums disabled for generated packets')

if __name__ == '__main__': main()
