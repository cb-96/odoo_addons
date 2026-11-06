# Data retention

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

This document defines the retention windows for operational logs, staged
inbound deliveries and generated report files, the configurable retention of
personal communication and evidence data, and how court-scoring data on
devices is handled.

## Review status

The policy remains the contract for terminal-state cleanup. Release review must verify the configured cron XML IDs, active defaults, date anchors, retention constants, attachment cleanup, and preservation of unresolved workflow records. A date update without those checks is not sufficient.

## Scope

The current automated retention policy covers these repository-owned surfaces:

- `federation.notification.log` records created by `sports_federation_notifications`
- `federation.integration.delivery` records and their staged payload attachments
  in `sports_federation_import_tools`
- `federation.report.schedule.generated_file` attachments created by
  `sports_federation_reporting`
- `federation.communication.receipt` and `federation.communication.delivery`
  (participant inbox) in `sports_federation_notifications`, once a period is
  configured
- `federation.member.evidence.revision` in the optional
  `sports_federation_member_services`, once a period is configured

Non-terminal workflow records are intentionally excluded from automated purge.
If a delivery is still waiting for preview, approval, or live processing, it is
retained until an operator resolves it.

## Retention windows

| Surface | State / Condition | Retention Window | Cleanup Anchor | Cleanup Result |
|---------|-------------------|------------------|----------------|----------------|
| Notification logs | `pending` | 30 days | `create_date` | Delete old log row |
| Notification logs | `sent` | 90 days | `create_date` | Delete old log row |
| Notification logs | `failed` | 180 days | `create_date` | Delete old log row |
| Inbound deliveries | `cancelled` | 90 days | `received_on` | Delete delivery and staged payload attachment |
| Inbound deliveries | `processed` | 180 days | `processed_on` | Delete delivery and staged payload attachment |
| Inbound deliveries | `processed_with_errors` | 180 days | `processed_on` | Delete delivery and staged payload attachment |
| Inbound deliveries | `failed` | 365 days | `received_on` | Delete delivery and staged payload attachment |
| Generated report files | Last successful export snapshot | 60 days | `last_run_on` | Clear stored file payload and filename, keep schedule |

## Automation

The cleanup routines run through daily scheduled actions that ship with the
affected addons:

- `sports_federation_notifications.ir_cron_notification_log_retention`
- `sports_federation_import_tools.ir_cron_federation_integration_delivery_retention`
- `sports_federation_reporting.ir_cron_federation_report_schedule_retention`
- `sports_federation_notifications.ir_cron_participant_inbox_retention`
- `sports_federation_member_services.ir_cron_member_evidence_retention`

These jobs are active by default and call the corresponding model cleanup
helpers during normal Odoo cron execution.

## Operator notes

- Delivery retention only applies to terminal states, so unresolved inbound
  partner handoffs remain visible in the operator checklist.
- Report schedule retention clears the stored export artifact but preserves the
  schedule definition, run metadata, and next execution date.
- If audit, legal, or incident-response requirements require a longer window,
  update the model retention constants and this document in the same branch.

## Change management

When retention windows or cleanup scope change:

1. Update this document in the same branch as the code change.
2. Update the affected module README files and add an entry to the
   [upgrade notes](../operations/upgrade-notes.md).
3. Re-run `python3 ci/check_doc_freshness.py` and `python3 ci/check_markdown_links.py`.
4. Re-run the affected module test suites to confirm the cleanup behavior still
   matches the documented policy.

## Configurable retention for personal data

The federation decides how long participant communications and member evidence
are kept. The platform ships the mechanism but no period: until a period is
configured, nothing is deleted and each daily run records a dry-run evidence
entry saying so. Set the periods under **Settings > Technical > Parameters >
System Parameters** after the federation has approved them.

| Surface | System parameter | Removed after the period | Always kept |
|---------|------------------|--------------------------|-------------|
| Participant inbox items and their deliveries | `sports_federation_notifications.inbox_retention_days` | Inbox items that are closed (acted upon, expired or superseded) and whose closing date is older than the period; their deliveries once finished (`sent`, `cancelled`, `suppressed`) and no longer used by another item | Open items; items with a waiting, queued or failed delivery |
| Member evidence revisions (optional member services) | `sports_federation_member_services.evidence_retention_days` | Replaced revisions, and revisions of cancelled requests, older than the period | The current revision of an open request; revisions under legal hold |

Rules:

- The value is a whole number of days. Empty or `0` disables deletion.
- The inbox period must be at least 30 days. Inbox items also prevent the same
  event from notifying a person twice, so a shorter period is refused: the run
  deletes nothing and records a failed evidence entry with the reason.
- An invalid value (not a whole number) is reported the same way.
- Notification logs keep their own windows (see the table above).

### Legal hold and erasure of member evidence

Federation managers open **Federation > Administration > Member evidence
history**, select revisions and use **Action > Legal hold or erasure**:

- **Place legal hold** excludes the revisions from scheduled retention and
  from erasure. The reason, person and time are recorded on the revision and
  posted on the member request.
- **Release legal hold** requires a reason and is posted the same way.
- **Erase permanently** deletes the selected revisions and their files, for
  example on a data-subject erasure request. It requires a reason and an
  explicit confirmation, is refused for held revisions, is posted on the member
  request and is recorded as retention evidence with policy
  `member_evidence_erasure`.

Revisions stay immutable otherwise: ordinary editing and deletion remain
blocked for every user.

### Court-scoring data on devices

The court workspace keeps a score journal per match in the browser's local
storage. When the workspace opens, it removes journals of the same database
and user that are fully synchronised (no queued commands, no unsent edits) and
were last saved more than 14 days ago; such a journal only repeats what the
server already holds. Journals that cannot be read, or that still hold unsent
work, are never removed automatically: they may be the only evidence and must
be exported and reconciled by a person.

Exported recovery evidence (`court-<match>-evidence.json`) is a file on the
operator's device and cannot be governed by the platform. Attach it to the
incident or result-correction record where it is needed, then delete the local
copy. Do not keep exports in personal storage.

## Execution evidence

Every automated retention run appends a `federation.retention.evidence` record with its policy code, timestamps, outcome, and affected-record counts. Evidence is read-only to federation managers and is retained independently from the records cleaned by the policy.

## Recovery visibility

Federation managers use **Federation > Administration > System Health > Retention and Recovery** to verify policy freshness and outcomes. Failure evidence is committed independently before the owning cron re-raises, so transaction rollback cannot erase the recovery record.

## Coordinated notification mail retention

Notification mail has an explicit `federation_notification_owned` marker. Only
mail created by the notification producers or linked during upgrade is marked.
Unlinked historical and unrelated mail is not inferred to belong to this policy.

Expired sent logs are removed together with their owned mail only when no other
log or communication delivery references the mail. Pending/failed mail and its
log remain protected for retry or investigation. A live communication delivery
protects its log even when sent. Once closed inbox retention removes the last
finished delivery, its unshared terminal log and owned mail can be removed too.

The daily log-retention cron also retries orphan cleanup in batches of 200 for
owned sent/cancelled mail older than 90 days, recording execution evidence under
`notification_mail_content`. This handles previously locked records without
sweeping unrelated mail. Mail locks and a final reference check prevent cleanup
from deleting mail still referenced by a delivery or log. Failed/outgoing mail
is never selected by the orphan sweep. Cancelled legacy mail remains protected
while its review-needed log exists.
