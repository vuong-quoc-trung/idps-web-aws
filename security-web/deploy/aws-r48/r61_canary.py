"""Run the R61 automatic response canary with a real, private AWS ingress."""

import json
import os
from pathlib import Path
import re
import sys
import time

from r56_prevention_lab import PEER, TABLE, main, run, wait_for
from r60_ingress import CANARY, Ingress


class Canary(Ingress):
    canary = True

    def sensor_rules(self):
        return "".join(
            f'alert http any any -> $HOME_NET $HTTP_PORTS (msg:"R61 isolated benign marker"; '
            f'flow:established,to_server; http.uri; content:"{path}"; startswith; endswith; sid:{sid}; rev:1;)\n'
            for path, (sid, _) in CANARY.items()
        )

    def receipt(self, rid):
        proof = self.active_receipt
        if (proof and proof["request_id"] == rid and self.authorized()
                and CANARY.get(proof["path"]) == (proof["sid"], proof["status"])
                and proof["application_denied"] == (proof["path"] == "/api/profile")):
            return proof

    def verify(self, call, mutate, synced, audit, connects, restart, block, authorize):
        endpoint = "/api/blocked-ips"
        assert not authorize() and self.receipt("0" * 32) is None and synced(False)
        with self.proof("/health", publish=False) as denied:
            rid = denied["request_id"]
            wait_for(lambda: call("/api/hybrid-incidents?request_id=" + rid)[1]["incidents"])
            assert self.receipt(rid) is None and call("/api/audit")[1] == [] and connects()
        with self.proof("/api/profile", authorized_session=True) as legitimate:
            rid = legitimate["request_id"]
            wait_for(lambda: call("/api/hybrid-incidents?request_id=" + rid)[1]["incidents"])
            assert legitimate["status"] == 204 and self.receipt(rid) is None
            assert call("/api/audit")[1] == [] and connects()
        results = []
        for path, source in (("/health", "CANARY_RULE"), ("/api/profile", "CANARY_HYBRID")):
            with self.proof(path) as receipt:
                rid = receipt["request_id"]
                assert self.receipt("0" * 32) is None

                def success():
                    rows = [row for row in call("/api/audit")[1] if row["reason"] == rid]
                    assert len(rows) <= 1
                    if rows:
                        assert rows[0]["status"] != "ERROR", rows[0].get("details")
                        if rows[0]["status"] == "SUCCESS":
                            return rows[0]

                applied = wait_for(success)
                assert applied["source"] == source and applied["actor"] == "system"
                assert synced(True) and not connects()
                assert re.search(r"counter packets [1-9]\d*", run("nft", "list", "table", "inet", TABLE))
                decision = call("/api/hybrid-incidents?request_id=" + rid)[1]["incidents"][0]
                assert decision["trusted_client_ip"] == PEER
                assert decision["ingress_attestation"]["suricata_flow"] == receipt["suricata_flow"]
                assert decision["ingress_attestation"]["application_denied"] == (source == "CANARY_HYBRID")
                results.append(receipt | {"action_id": applied["id"], "source": source})

            assert self.receipt(rid) is None
            if source == "CANARY_RULE":
                unblock = mutate(endpoint + "/" + PEER, "DELETE")
                assert synced(False) and connects()
                time.sleep(31)  # Keep the existing per-target cooldown.
            else:
                wait_for(lambda: synced(False))
                assert connects()

        restart()
        assert synced(False) and connects()
        history = call("/api/audit")[1]
        assert {row["id"] for row in history} == {unblock, *(row["action_id"] for row in results)}
        assert all(row["status"] == "SUCCESS" for row in history)
        assert audit(unblock)["actor"] == "admin"
        print("R61_CANARY=" + json.dumps({"automatic": results, "missing_attestation": denied,
              "authorized_session": legitimate,
              "negative_result": "NO_ACTION", "manual_unblock": unblock, "max_ttl_seconds": 6,
              "db_kernel": "SYNCED_EMPTY", "audit": "3 SUCCESS", "restart_without_replay": True,
              "protected_scope": "PASS", "rbac": [401, 403]}), flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), ingress=Canary())
