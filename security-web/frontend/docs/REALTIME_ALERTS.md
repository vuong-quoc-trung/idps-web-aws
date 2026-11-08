# Multi-source trend and alert feedback

## Data contract (additive /api/stats extension)

User approved the minimal API extension before implementation. Each trend item retains hour/count and adds sources (SURICATA, NGINX, STUDENT_AUDIT, OTHER). APPLICATION is grouped with STUDENT_AUDIT. Counts come directly from security_alerts, never joined to evidence rows. Unknown source counts remain in OTHER and the detail table; a notice explains any difference between the three visible lines and the total.

Buckets share one bounds CTE: 1h / 12 buckets (5 minutes), 24h / 24 buckets (1 hour), 7d / 7 buckets (24 hours). They are rolling UTC intervals anchored to the report's since, not local midnight calendar days. Browser labels show local time; full timestamps remain in details. All buckets are zero-filled. The line chart breaks at unexpected timestamp gaps. Legend changes visibility only, not totals or raw detail rows. No new chart library.

Optional after_alert_id >= 0 returns alert_updates in the same response: global max ID, count/min severity above cursor, and latest 100 ID/severity pairs. No additional polling request, migrations or detection changes. Old clients ignore added fields; new frontend disables source mode if old backend omits sources. Restart the backend with the new build to expose this data.

## Feedback

Session-memory tracker starts without a cursor. First successful response silently establishes the global baseline. Later successful responses advance monotonically; repeated/out-of-order API snapshots do not re-trigger. Filters/navigation do not reset the tracker; login does. Failed requests do not advance it. No payload, token or identity is stored in browser storage.

S1: red accent with two bounded 0.8s pulses and severity-1 KPI feedback. S2: amber with two pulses. S3–5: teal single fade. A single fixed polite live-region toast groups arrivals; arrivals during the six-second cooldown merge into it rather than creating more toasts. It expires six seconds after the latest grouped batch. No sound. Toggle disables feedback while cursor tracking continues. Reduced motion disables animation. Notification is global, even when current filters exclude the alert; it does not imply exploitation or blocking.

## Limits

- The max-ID cursor assumes newly committed alerts normally have increasing IDs. PostgreSQL sequences are not commit-order cursors: a long transaction committing a lower ID after the baseline can be absent from feedback. The alert remains in DB/search/chart. A durable commit-ordered feed/outbox would be required for stronger notification delivery guarantees and is outside this minimal API extension.
- Count/severity cover all rows above cursor; row highlights are limited to the newest 100 IDs per response (up to 200 retained while merging a batch). High-volume arrivals still produce aggregate counts, not thousands of animations.
- Manual refresh of the whole browser/login sets a new silent baseline. This is UI feedback, not a durable notification inbox.
- Actual browser rendering, 1440/768/390 screenshots, reduced-motion rendering and live incoming-event acceptance have not been verified. No host services/configuration changed.

## Validation

67 Rust tests passed on temporary network-isolated PostgreSQL; includes source bucket totals, zero filling, 7 daily buckets, silent baseline and exhausted cursor. Four frontend test files passed including tracker baseline/repeated/older response/reset and existing polling/query tests. TypeScript, Vite build, Prettier and git diff --check passed.

## Manual acceptance

1. Start updated backend/frontend; first load must not toast historical alerts.
2. Toggle column/line, toggle each legend; compare bucket rows and sum with total.
3. Generate one authorized lab event for each severity; verify matching highlight and grouped notification. Poll the same response again; no repeat.
4. Change range/filter/page, navigate away/back; no historical notification flood. Simulate an API failure/recovery; cursor remains unchanged during failure.
5. Check narrow screens, keyboard focus/readout, drawers and copying while the toast is present; enable OS reduced motion and disable feedback toggle.
