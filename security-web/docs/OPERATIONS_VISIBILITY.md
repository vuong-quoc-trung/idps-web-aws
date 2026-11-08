# Operational visibility and alert triage

## Source health

/api/status now includes checked_at, operations and collection timestamps:
last_ingested_at is the latest retained normalized event's observed_at;
last_ingested_event_at is that event's producer timestamp. These are different
from watcher last_success_at (file scan succeeds) and last_data_at (a file change
was observed, including existing data at startup).

The host probes pbl4-audit-receiver.service and suricata.service read-only every
15 seconds, with two-second command timeouts. No sudo/SSH/restart is used.
Unknown is retained when systemd is unavailable. Sender health on the Web VM,
RELP port binding, queue health and end-to-end delivery are NOT inferred from a
local service being active. Check the remote sender separately. Silence is shown
as elapsed time, never automatically classified as a failed connection.

When COLLECT_ALL_EVENTS is off, normalized-event timestamps can remain historical.
Retention can also remove older timestamps. Generate a known request and compare
file changes, DB timestamps and the corresponding audit record for an end-to-end test.

## Rule verification

/api/rules preserves the existing array and adds verification metadata:
- backend rule logic is included in the running binary;
- sensor rule-file bytes are compared with the build's embedded pbl4.rules;
- SURICATA_RULES_DEPLOYED_PATH optionally overrides the default
  /var/lib/suricata/rules/pbl4.rules;
- matching bytes DO NOT prove Suricata loaded the file;
- latest persisted alert is matched by exact rule code and linked to its detail;
- historical alerts DO NOT certify the current deployment or a passed test.

Legacy alerts without an unambiguous code remain unclassified. Offline tests are
not presented as live deployment acceptance. Run the existing validation/replay
and end-to-end probes after deployment.

## Alert lifecycle

Migration 0010 adds NEW / INVESTIGATING / RESOLVED / FALSE_POSITIVE, a version,
last actor/time, append-only API history, exact rule-code classification and indexes.
Existing alerts start NEW; their evidence/action remain unchanged.
Admin POST /api/alerts/{id}/triage requires status, version and a 1–1000 character
note. Viewer is read-only. A transaction locks the alert and atomically records
the state/history; stale version returns 409. Reopening and adding another note
at the same state are allowed. API does not delete or edit previous history.
The detail shows the latest 50 entries; older entries remain in DB.
Triage does not change firewall state, detection, or automatic blocking.

Frontend filters include triage_status and CSV includes the processing label.
On conflict, use "Tải lại trạng thái"; draft notes are preserved for review.
Do not put secrets or passwords in notes.

## Deployment and acceptance

Deploy Rust and frontend together; the normal startup migration runner applies
0010. No live host services or project DB were modified while implementing.
Back up DB before normal deployment. Keep AUTO_BLOCK=false / ENFORCEMENT_MODE=OFF.

- Verify /api/status timestamps after a fresh event, not only dashboard refresh.
- Confirm receiver unknown/inactive remains distinguishable from active.
- Confirm source silence is informational and a missing log remains an error.
- Open a known rule's evidence; confirm an unseen rule is not labelled broken.
- Use admin to investigate/resolve/reopen with a note; viewer cannot mutate.
- Open the same alert in two tabs: after one saves, the other receives conflict.
- Verify filter counts and history after reloading; no firewall action is created.

Rollback binaries/frontend together if needed. Retain migration and triage data;
do not drop tables/columns or reset SQLx history. Older clients ignore additive
fields. No sender, firewall, SSHFS or network changes are part of this release.
