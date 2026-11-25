"""Keep the installed queue/filter/template intact; refuse unreviewed transport changes."""
from pathlib import Path
import re
import sys

role, original, reference, dest, canary, directory = sys.argv[1:]
module, kind = ("imrelp", "input") if role == "receiver" else ("omrelp", "action")
live = Path(original).read_text()
secure = Path(reference).read_text()
header = f'{kind}(type="{module}"'
start = secure.index(header)
end = secure.index('.key"', start) + len('.key"')
def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected {role} configuration near {old}")
    return text.replace(old, new)

if re.search(r'(?im)^\s*(?:include\s*\(|\$IncludeConfig)|tls\s*=|tls\.', live):
    raise ValueError("Existing transport needs manual review")
candidate = once(live, f'module(load="{module}")', f'module(load="{module}" tls.tlslib="gnutls")')
candidate = once(candidate, header, secure[start:end])
# Require semantic parity with the reviewed production config, allowing comments/blank lines.
def body(text):
    return [s.strip() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('#')]
if body(candidate) != body(secure):
    raise ValueError("Runtime differs from the reviewed sender/receiver; original preserved")
candidate = secure.splitlines()[0] + '\n' + '\n'.join(candidate.splitlines()[1:])+'\n' if candidate.startswith('#') else candidate
Path(dest).write_text(candidate)
probe = once(candidate, f'workDirectory="/var/lib/pbl4-audit-{role}"', f'workDirectory="{directory}"')
probe = once(probe, 'port="2514"', 'port="32514"')
probe = once(probe, '"192.168.20.1"', '"127.0.0.1"')
if role == "receiver":
    probe = once(probe, '"192.168.20.10"', '"127.0.0.1"')
    probe = once(probe, '"/var/log/pbl4/student-audit.log"', f'"{directory}/output.log"')
else:
    probe = once(probe, '"/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log*"', f'"{directory}/input.log"')
Path(canary).write_text(probe)
