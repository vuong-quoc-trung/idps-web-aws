# Seven additional detection rules

These changes add catalog metadata and detection, not automatic IP blocking.
Keep AUTO_BLOCK=false and ENFORCEMENT_MODE=OFF. Existing rules are unchanged.

| Layer | ID | Condition |
|---|---|---|
| Student Audit | APP-1017 | Same source instance/IP: 5 RATE_LIMITED + HTTP 429 in 60 seconds |
| Student Audit | APP-1018 | Same source instance/IP: 5 CSRF_INVALID + HTTP 403 in 60 seconds |
| Student Audit | APP-1019 | Same source instance/IP: 5 RECOVERY_TOKEN_INVALID + HTTP 400 in 600 seconds |
| NGINX | SENSITIVE_PATH_PROBE | Request for /.env (including dot/slash suffixes), /.git/, /actuator/env or /actuator/heapdump (including slash suffixes) |
| NGINX | PATH_ENUMERATION_BURST | Same source instance/IP: 20 distinct sanitized paths returning 404 in 60 seconds; static assets excluded |
| Suricata | 1000026 | XSS patterns in JSON/form POST/PUT/PATCH bodies on selected data APIs |
| Suricata | 1000027 | Command injection patterns in JSON/form POST/PUT/PATCH bodies on selected data APIs |

All new rules are severity 2 except SID 1000027 (severity 1).
Catalog totals: 27 Suricata, 13 NGINX, 19 Student Audit.

## Scope and privacy

Spring emits reason codes from actual rejection branches; HTTP status alone is
not treated as confirmed CSRF/token/rate-limit abuse. Existing Spring rejection
logic remains authoritative. No request body, password, token or reset code is
added to audit logs. Recovery signals cover invalid activation tokens and failed
password-reset verification; they do not prove the target account exists.
Rate-limit signals cover the existing auth-route limiter, not every possible 429.
Old Student Web versions cannot emit these three new signals.

The canonical contract adds three enum values and raises the reason count limit
to ten. Deploy the Rust consumer before the Spring producer: old consumers reject
unknown reason codes. The AI canonical schema snapshot/checksum is synchronized;
AI feature definitions and model inputs are unchanged.

Enumeration stores only the already-sanitized path in migration 0009. It uses
the existing transactional receipt/window pipeline, excludes redacted paths,
and retains the existing bounded observation state. Paths collapsed by privacy
normalization are counted as one path. Thresholds are lab defaults; shared NAT
and legitimate clients may trigger them.

Suricata body rules cover /api/students, /api/me, /api/classes, /api/faculties,
/api/majors and /api/training-programs. Authentication/password routes and multipart
uploads are excluded. They detect signatures, not successful exploitation.
Sensor visibility, HTTP decoding and body inspection limits still apply; encrypted
SSH/HTTPS traffic cannot be inspected as plaintext by a sensor outside termination.

## Deployment

1. Back up the database and deployed configs using the existing operational procedure.
2. Deploy/restart Rust backend first; SQLx applies migration 0009 automatically.
   Do not manually create the new column or edit migration history.
3. Deploy Student Web to emit the three new security reasons.
4. Validate the deployed Suricata configuration with suricata -T before loading
   the updated pbl4.rules using the normal operator procedure.
5. For NGINX, merge only the sensitive-path deny location from nginx/pbl4-proxy.conf
   into the existing host server block, validate nginx -t, then reload if valid.
   Do not replace the host's listen 192.168.10.1:80 or its existing upstream layout
   with the repository development example.
6. Verify forwarding, ingestion and alert filters independently. Reload the rule
   catalog and check all three sources. Keep automatic enforcement disabled.

The sensitive-path location returns 403 directly; Rust emits the corresponding
alert from the access log. Updating repository code alone does not deploy this
location or the Suricata rules to host services.

## Verification / rollback

Automated checks cover positive and negative signatures, distinct-path counting,
thresholds, replay, out-of-order observations, server reason generation, catalog
metadata and frontend evidence handling. Production end-to-end verification is
still required after deployment.

Rollback the Spring producer first, then Rust if necessary; preserve all audit
logs, receipts and database history. Leave migration 0009 and its nullable column
in place rather than dropping state. Restore only the changed Suricata rule file
and NGINX location from their backups, validate each configuration before reloading.
No SSHFS, firewall, forwarding or AI migration is needed.
