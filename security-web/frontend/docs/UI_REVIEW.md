# WebSentinel — UI review (2026-11-06)

## Scope and preservation inventory

Presentation-only update. No dependencies added. Existing seven-page navigation remains.

| Page | Preserved content and interactions |
| --- | --- |
| Overview | Range, four KPIs, trend and text equivalent, latest alerts/evidence, attack groups, source/destination IPs, severities, sources, block jobs, drill-down links |
| Alerts | Search, severity/date/source/action/destination filters, CSV, 25-row pagination, application evidence, detail and linked audit |
| Application Audit | Draft/applied filters, 25-row pagination, request-ID copy/correlation, collection/retention/watchers, canonical JSON and related events |
| Blocked IPs | DB/kernel union and difference descriptions, reason/time, unknown kernel state, admin-only block/unblock and existing confirmations |
| Operational Audit | Actor/source, linked event filter, creation/completion times, status, reason and details |
| Rules | Three existing sources and backend-derived counts, rule code/severity/threshold/action mode, search and severity filters |
| System Status | Database/firewall/sync, three watchers, last read/data/alert, pending bytes/errors, all backend resource metrics and caveats |

No AI page is currently rendered by this frontend; no invented AI scores or data added.

## Data lifecycle retained

Main App refresh requests alerts/search, stats, blocked-ips, audit, rules, status every 5 seconds with an in-flight guard. ApplicationAudit separately schedules 5 seconds after completion while visible, aborts on hide/unmount, coalesces refresh, and keeps old rows on background reload. Manual refresh and refreshSignal remain unchanged. API/auth/RBAC, source interpretation and severity calculations unchanged.

Existing loading, error, success and empty conditions remain. EmptyState standardizes presentation only, not request lifecycle. Existing initial empty-state behavior was not reinterpreted as part of this styling change.

## Findings and changes

- Consolidated duplicate root palette into navy/charcoal surfaces and teal accent, shared control/radius/panel tokens.
- Reduced decorative gradients; consistent table borders, readable headers/numeric typography, row hover/focus and keyboard-scroll regions.
- Filter panels have a distinct compact surface; all fields remain available, including existing advanced filters.
- Audit collection sources use a three-column layout which stacks on smaller screens.
- Service summary groups database/firewall/sync without changing their boolean semantics.
- Rule-source colors are consistent with source labels. No detection changes.
- Detail drawers share sticky close/header, structured field surfaces and readable evidence blocks.
- Shared empty-state component; skip-to-content link, column scope and visible keyboard focus.
- Mobile rules stack panels/controls, retain horizontal table scrolling and all columns. No data column is hidden.

## Validation

Passed: npm test (three test files, including polling serialization/visibility/unmount and audit query tests), npm run format:check, npm run build (TypeScript noEmit + Vite), git diff --check.
No lint script is configured in package.json. No browser rendering verification was completed: browser automation packages were unavailable in the local project and the sandbox denied socket inspection. No live admin action was executed.

## Browser acceptance checklist (remaining)

- Desktop 1440px, tablet 768px, phone 390px: verify navigation, no page-wide overflow, scrollable tables, labels and all controls.
- Open alert and audit detail; scroll evidence; ensure Close stays reachable and Escape/focus return work as before.
- Audit: apply filters, edit a draft, change page, wait through polling; confirm no reset or row flicker. Hide/show tab, leave/reenter page, use both refresh buttons.
- Verify real loading/error/empty/success responses; old data remains readable on background errors.
- Viewer remains unable to block/unblock; admin confirmation and linked operation audit remain intact. Only test actual firewall changes separately when explicitly authorized.

Rollback: revert only the frontend files in this change; no host service, DB or backend migration is involved.

## Second refinement pass

Overview now uses compact KPIs, trend alongside latest alerts on desktop, popular groups below trend, and a full-width three-source summary. All ten alerts retain their expandable evidence and investigation links. Chart preserves every API bucket/count (including zero); approximately six time ticks plus the final tick are visible, with full timestamps in the existing data list and hover/focus tooltip. No aggregation or severity calculation changed.

Tables now use document vertical scrolling rather than a capped inner vertical region. Horizontal scrolling and all columns remain. Header stickiness was removed intentionally because a horizontal overflow ancestor prevents reliable viewport sticky behavior without a larger layout rewrite. Rules, audit explanation and spacing are more compact.

### Read-only source-IP investigation

- overview.sql groups stored events by src_ip; frontend displays row.ip without replacing it.
- Repository NGINX config logs client_ip=$remote_addr and overwrites X-Forwarded-For with $remote_addr.
- Spring RequestAttribution trusts forwarding only for configured trusted peers; defaults trust loopback. It walks XFF right-to-left and ignores it for untrusted peers. Vite proxies /api to VM localhost:8080, so a loopback peer is expected in development.
- Actual local receiver log sampled on 2026-11-06 contained GET /api/auth/me events at 12:10:42–43 UTC (19:10:42–43 Vietnam) with client_ip=192.168.10.1 and peer_ip=127.0.0.1. This proves the IP exists upstream of the dashboard, not that its attribution is necessarily correct.
- No matching request IDs found in the last 3,000 JSON access-log lines inspected. Runtime routing inspection was denied by the sandbox. Live Web VM trusted-proxy settings and full proxy chain were not verified.
- Host-originated lab requests can legitimately appear as 192.168.10.1. Do not substitute Kali IP or rewrite dashboard values. If a known external client is misattributed, correlate the same request ID at ingress and audit, inspect effective NGINX real_ip directives and actual peer_ip, then explicitly trust only the intended proxy hops. Loopback trust alone does not authenticate all local proxy clients; do not broaden trust to all networks as a shortcut.

No attribution/security settings changed. Re-ran npm test, format check and production build successfully. Browser screenshots at 1440/768/390 and real-session interaction verification remain pending; responsive behavior was reviewed in CSS only. Existing polling tests pass, but do not constitute live browser verification of flicker, navigation or RBAC.
