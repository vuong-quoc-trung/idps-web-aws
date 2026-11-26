"""Read the R59 enforcement prerequisites on the pinned AWS staging host."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

import refresh
import update

UNITS = ("nginx.service", update.STUDENT, update.SEC, update.SCORE,
         update.SENSOR, update.CORR, "postgresql@18-main.service")
APPROVAL = Path("/etc/ws-native/approval.json")
STATUS_SOCKET = Path("/run/ws-native-fw-status.sock")
LAB_CAPABILITY = Path("/run/websentinel-r56-lab")

SQL = """
BEGIN READ ONLY;
SELECT jsonb_build_object(
  'request_id', :'rid',
  'correlation', c.result->>'status',
  'sources', c.result->'sources',
  'late', c.result->'late_event',
  'edge_ip_present', EXISTS(SELECT 1 FROM normalized_events n
      WHERE n.request_id=:'rid' AND n.source='NGINX'
        AND n.client_ip IS NOT NULL AND NOT n.client_ip <<= '127.0.0.0/8'::inet),
  'edge_audit_agree', EXISTS(SELECT 1 FROM normalized_events n
      JOIN normalized_events a USING (request_id)
      WHERE n.request_id=:'rid' AND n.source='NGINX' AND a.source='STUDENT_AUDIT'
        AND n.client_ip=a.client_ip),
  'sensor_transaction_on_loopback', EXISTS(SELECT 1 FROM normalized_events s
      WHERE s.source='SURICATA'
        AND s.source_instance='suricata-'||(c.result->>'sensor_instance')
        AND s.canonical->>'flow_id'=c.result->>'flow_id'
        AND s.canonical#>>'{suricata_origin,tx_id}'=c.result->>'tx_id'
        AND s.canonical#>>'{suricata_origin,network_src_ip}' IN ('127.77.0.1','127.77.0.2')
        AND s.canonical#>>'{suricata_origin,post_proxy}'='true'),
  'trusted_hybrid_target', COALESCE(jsonb_typeof(i.decision->'trusted_client_ip')='string',false),
  'ai', a.observation->>'status',
  'model', a.observation->>'version',
  'ai_threshold', a.observation->'threshold',
  'ai_proof_ms', ((a.observation->>'available_ns')::numeric
                 -(a.observation->>'dispatch_ns')::numeric)/1000000,
  'hybrid', i.decision->>'policy_action',
  'hybrid_advisory_reason', i.decision->'policy_reason' ? 'REQUEST_BOUND_HTTPS_AI_ADVISORY',
  'automatic_block', i.decision->'automatic_block',
  'incidents', (SELECT count(*) FROM hybrid_incidents WHERE request_id=:'rid'),
  'pending_actions', (SELECT count(*) FROM firewall_actions WHERE status='PENDING'),
  'total_actions', (SELECT count(*) FROM firewall_actions),
  'active_database_leases', (SELECT count(*) FROM blocked_ips
       WHERE active AND (expires_at IS NULL OR expires_at>now()))
)
FROM request_correlations c
JOIN https_research_observations a USING (request_id)
JOIN hybrid_incidents i USING (request_id)
WHERE c.request_id=:'rid';
COMMIT;
"""


def status_socket_present():
    try:
        return stat.S_ISSOCK(STATUS_SOCKET.lstat().st_mode)
    except FileNotFoundError:
        return False


def nft_observation():
    try:
        result = subprocess.run(
            ["/usr/sbin/nft", "-j", "list", "tables"],
            check=True, capture_output=True, text=True, timeout=4,
        )
        tables = {item["table"]["name"] for item in json.loads(result.stdout)["nftables"]
                  if "table" in item}
        return {"readable": True, "table_count": len(tables),
                "native_lab_table_present": "ws_native_lab_peer" in tables,
                "r56_lab_table_present": "r56_prevention" in tables}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return {"readable": False, "error_kind": type(error).__name__}


def collect(request_id):
    if not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("Expected one read-only probe request ID")
    refresh.verify_host()
    refresh.verify_database()
    env = update.ENV.read_text().splitlines()
    settings = {}
    for key in ("ENFORCEMENT_MODE", "AUTO_BLOCK", "SURICATA_CAPTURE_MODE",
                "SURICATA_POST_PROXY_INTERFACE", "WS_NATIVE_FIREWALL_SOCKET"):
        values = [item.split("=", 1)[1] for item in env if item.startswith(key + "=")]
        settings[key] = values[0] if len(values) == 1 else None
    result = subprocess.run(
        ["runuser", "-u", "postgres", "--", "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
         "-v", f"rid={request_id}", "-d", "ws_r47_security"],
        input=SQL, check=True, capture_output=True, text=True, timeout=10,
    )
    request = json.loads(result.stdout) if result.stdout.strip() else None
    release = update.ACTIVE.resolve(strict=True)
    backup = Path("/var/backups/websentinel-r58")
    subprocess.run(["sha256sum", "--check", "--quiet", "SHA256SUMS"],
                   cwd=backup, check=True, timeout=100)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": {unit: update.run("systemctl", "is-active", unit, check=False)
                     for unit in UNITS},
        "configuration": settings,
        "model_sha256": refresh.MODEL_SHA,
        "security_binary_sha256": update.sha(release / "security/pbl4-security-demo"),
        "frontend_index_sha256": update.sha(release / "security/frontend/dist/index.html"),
        "rollback_backup_manifest_sha256": update.sha(backup / "SHA256SUMS"),
        "native_status_socket_present": status_socket_present(),
        "native_local_policy_file_present": APPROVAL.exists(),
        "lab_runtime_present": LAB_CAPABILITY.exists(),
        "kernel_readback": nft_observation(),
        "request": request,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected the request ID of a benign HTTPS smoke request")
    print(json.dumps(collect(sys.argv[1]), sort_keys=True), flush=True)
