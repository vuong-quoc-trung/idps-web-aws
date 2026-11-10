"""Reports contain only fixed metadata, never payloads, credentials or response bodies."""
import csv
import io
import json
from pathlib import Path

def render(report, fmt='json'):
    if fmt == 'json':
        return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    out = io.StringIO(newline='')
    fields = ['scenario', 'stage', 'index', 'method', 'status_code', 'request_id', 'duration_ms', 'timestamp', 'error', 'result', 'target', 'scenario_name']
    w = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    results = {s['id']: s.get('result') for s in report.get('scenarios', [])}
    for original in report['requests']:
        row = {**original, 'target': report.get('target'), 'scenario_name': next((s.get('name') for s in report.get('scenarios', []) if s['id'] == original['scenario']), original['scenario']), 'result': results.get(original['scenario'])}
        safe = {k: ("'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else v) for k, v in row.items()}
        w.writerow(safe)
    return out.getvalue()

def save(report, filename):
    p = Path(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(report, 'csv' if p.suffix.lower() == '.csv' else 'json'), encoding='utf-8')
