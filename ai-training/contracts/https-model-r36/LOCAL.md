# Local HTTPS research slot

The R35 proof edge still checks HMAC, TLS and peer ownership. Enable the private mirror for the Local integration profile with `stage-proof-host.py --https-ml-shadow`. Its socket is `/run/websentinel-edge-shadow/receiver.sock`. The Local acceptance runner reads the [active slot registry](../quality-freeze-r37/slots.json) and uses the R37 HistGradientBoosting release by default. Supplying an explicit R35 bundle to the historical runner selects historical acceptance instead.

Start the receiver using the existing delegated guardian. Set PY, ROOT, ORT and SCORER to absolute paths for the project Python, checkout, pinned ORT CPU library and URI100 Rust scorer. Set DB, JOURNAL and SOCKET to dedicated paths. The socket directory must belong to the receiver and only the owner may write it. Keep the SQLite DB in a separate private directory. For separate identities, grant directory traversal to the appropriate groups and set PEER_UID, PEER_GID and JOURNAL_GID to the actual NGINX worker UID, NGINX connecting group and Security Web read group.

```sh
"$PY" "$ROOT/ai-training/contracts/https-shadow-r35/guard.py" -- \
  "$PY" -B "$ROOT/ai-training/contracts/https-model-r36/serve.py" \
  --binary "$SCORER" --ort "$ORT" --socket "$SOCKET" --database "$DB" \
  --journal "$JOURNAL" --lineage "$RUN_ID" --peer-uid "$PEER_UID" \
  --peer-gid "$PEER_GID" --journal-gid "$JOURNAL_GID"
```

This command runs one bounded Local acceptance window. Set `AI_HTTPS_RESULTS_PATH` to the same journal in the Security Web process for that instance. SQLx migration 0019 creates a distinct observation table. Rust verifies the pinned slot, original request ID, finite score and cutoff and runs the ordinary Hybrid worker. The primary AI field for this request reflects the HTTPS scorer. Existing RI v2 control metadata is retained in `control_ai`. Research can raise an advisory ALERT; its score contributes zero to the risk calculation for a block proposal. A repeated conflicting observation causes abstention. The journal and database are local to this run; retain their cursor and data across scorer restarts.

The slot registry selects exactly one default model. Stop the owned receiver and start the same command with `--slot rollback` to restore the R36 ExtraTrees model. Restart without the override to restore R37. Historical R35 journal entries retain their pinned version and threshold when ingested. The registered digest and schema must pass before accepting traffic. Both slots are observation-only. Enabling the research profile on a persistent host or AWS is a separate deployment decision.
