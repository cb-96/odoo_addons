# Data Retention Policy

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

This document defines the default retention windows for operational logs,
staged inbound deliveries, and generated report files stored by the federation
addons.

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

## Retention Windows

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

## Operator Notes

- Delivery retention only applies to terminal states, so unresolved inbound
  partner handoffs remain visible in the operator checklist.
- Report schedule retention clears the stored export artifact but preserves the
  schedule definition, run metadata, and next execution date.
- If audit, legal, or incident-response requirements require a longer window,
  update the model retention constants and this document in the same branch.

## Change Management

When retention windows or cleanup scope change:

1. Update this document in the same branch as the code change.
2. Update the affected module README files and release/runbook guidance.
3. Re-run `python3 ci/check_doc_freshness.py` and `python3 ci/check_markdown_links.py`.
4. Re-run the affected module test suites to confirm the cleanup behavior still
   matches the documented policy.