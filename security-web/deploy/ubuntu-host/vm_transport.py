import json
import subprocess


def deliver(op, plan=None):
    msg = {"op": op}
    if plan:
        msg.update(rid=plan["request_id"], **{k: plan[k] for k in ("selector", "issued", "expires")})
    args = ["ssh", "-F", "/dev/null", "-T", "-oBatchMode=yes", "-oIdentitiesOnly=yes",
            "-oStrictHostKeyChecking=yes", "-oUserKnownHostsFile=/etc/ws-native/student-known-hosts",
            "-oGlobalKnownHostsFile=/dev/null", "-oConnectTimeout=3", "-i", "/etc/ws-native/lease-ssh",
            "ws-lease@192.168.20.10"]
    response = subprocess.run(args, input=json.dumps(msg), text=True, capture_output=True,
                              timeout=6, check=True).stdout.strip()
    if response != {"ready": "READY", "apply": "APPLIED", "revoke": "REVOKED"}[op]:
        raise RuntimeError("VM lease acknowledgement missing")
    return response
