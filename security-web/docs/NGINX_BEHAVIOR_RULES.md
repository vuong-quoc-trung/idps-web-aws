# NGINX behavior rules

Five additional rules bring the NGINX catalog to 11. All Rust alerts are severity 2, ALERT_ONLY, never automatic IP blocking. Thresholds are lab defaults.

| Code | Condition |
|---|---|
| HTTP_REQUEST_BURST | 120 requests per IP/source instance in 30s; exclude health routes and /assets/, /static/, /images/ |
| HTTP_REJECTION_BURST | 10 responses 400/413/414/431 per IP in 60s |
| UNEXPECTED_HTTP_METHOD | TRACE, CONNECT, PROPFIND, PROPPATCH, MKCOL, COPY, MOVE, LOCK, UNLOCK, REPORT, SEARCH, MKACTIVITY, CHECKOUT, MERGE; inspected before method redaction |
| LARGE_RESPONSE_BURST | At least 30 GET 2xx with known response_bytes and sum at least 10 MiB in 60s; exact /api/users, /api/students, /api/access-logs only |
| GATEWAY_ERROR_BURST | 10 responses 502/504 in 60s per source instance across all IPs; src_ip is null, operational alert only |

The window is (latest observed event time - window, latest time]. Counts survive backend restart; dedup by canonical event key. Late events within the current window can complete a threshold. State expires five minutes after receipt and is capped at 100,000 rows. Very late delivery or extreme volume can lose counting context. Alerts have one cooldown window; evidence records the triggering count, not a live counter. No extra request bodies or arbitrary method values are persisted. Combined logs without response size cannot trigger LARGE_RESPONSE_BURST.

Repository NGINX config adds an allowlist GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS and returns 405 for other methods. This is inline request rejection, not IP blocking. CONNECT may be rejected by NGINX's parser earlier. Rust only detects observed completed access-log entries; it does not undo requests or detect unfinished slow connections. 502/504 can simply mean the Web VM is down.

## Deployment

1. Back up Security DB. Build the backend; SQLx applies `0008_nginx_behavior.sql` when starting the new backend. Do NOT manually create its table. No live database was migrated during implementation.
2. Existing JSON access logging already supplies the needed fields. No Spring change or canonical/AI feature schema change is required. Metadata automatically appears under Web/Proxy in /api/rules.
3. Review the method allowlist against legitimate clients before applying it to the live server. Preserve the host's existing listen address, upstreams and log paths: the repository config may differ from the installed deployment. Do not copy the entire proxy file blindly.
4. Back up the actual installed NGINX site before editing. Insert only the method allowlist block inside its server. Run `sudo nginx -t`; only if successful run `sudo systemctl reload nginx`. These commands are for the operator; no reload was performed.
5. Keep AUTO_BLOCK=false and ENFORCEMENT_MODE=OFF. On the lab, verify source NGINX/action ALERT, threshold boundaries, unchanged normal requests, and proxy-wide 502 alerts without attributing an attacker IP. Gateway and response-volume alerts are not proof of compromise.

Rollback method enforcement by restoring the backed-up site, `sudo nginx -t`, then reload. Retain migrations, canonical events, cursor/receipts and rsyslog queues. Do not remove tables to roll back a rule.
