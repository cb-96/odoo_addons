# Data retention

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

This document defines the default retention windows for operational logs,
staged inbound deliveries, and generated report files stored by the federation
addons, and lists the data that has no automated window yet.

## Review status

The policy remains the contract for terminal-state cleanup. Release review must verify the configured cron XML IDs, active defaults, date anchors, retention constants, attachment cleanup, and preservation of unresolved workflow records. A date update without those checks is not sufficient.

## Scope

The current automated retention policy covers these repository-owned surfaces:

- `federation.notification.log` records created by `sports_federation_notifications`
- `federation.integration.delivery` records and their staged payload attachments
  in `sports_federation_import_tools`
- `federation.report.schedule.generated_file` attachments created by
  `sports_federation_reporting`

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

## Data without an automated retention window

These records are deliberately retained until an approved retention period,
legal-hold handling and erasure procedure are defined. They are listed as open
items in the [roadmap](../roadmap.md#known-gaps).

| Surface | Owner | Current behaviour |
| --- | --- | --- |
| Participant inbox receipts and deliveries | `sports_federation_notifications` | Unresolved inbox work is never deleted silently; the existing notification-log windows above still apply to notification logs. |
| Member evidence revisions (current and replaced document bytes) | `sports_federation_member_services` (optional) | Immutable, reviewer-only records; ordinary editing and deletion are blocked. |
| Court score journals and exported recovery evidence | `sports_federation_live_workspace` | Stored on the operator's device; exports are operational evidence handled under the federation's access policy. No automatic expiry is applied to unresolved evidence. |

## Execution evidence

Every automated retention run appends a `federation.retention.evidence` record with its policy code, timestamps, outcome, and affected-record counts. Evidence is read-only to federation managers and is retained independently from the records cleaned by the policy.

## Recovery visibility

Federation managers use **Federation > Administration > System Health > Retention and Recovery** to verify policy freshness and outcomes. Failure evidence is committed independently before the owning cron re-raises, so transaction rollback cannot erase the recovery record.
