"""Compare one new request without exposing the audit record."""
import hashlib, json, sys, time
from pathlib import Path
path = Path(sys.argv[1])
for _ in range(30):
    with path.open('rb') as f:
        f.seek(0,2)
        offset = max(0,f.tell()-4*1024*1024)
        f.seek(offset)
        if offset: f.readline()
        for line in f:
            if sys.argv[2].encode() not in line or not line.endswith(b'\n'): continue
            row = json.loads(line)
            if row.get('request_id')==sys.argv[2] and row.get('source')=='STUDENT_AUDIT':
                print(hashlib.sha256(line).hexdigest())
                sys.exit(0)
    time.sleep(1)
sys.exit("Fresh audit ID missing")
