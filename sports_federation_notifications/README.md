# Sports Federation Notifications

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Central notification templates, dispatch helpers, delivery logs, and scheduled reminders for federation workflows.

## Responsibilities

- email and activity dispatch through a shared service
- notification templates and scheduled actions
- non-blocking business-event notifications
- delivery outcome, retry metadata, failure category, and correlation ID logging
- season-registration and other module-triggered notification hooks

## Reliability contract

Notification delivery must not roll back the business transaction. Failures are sanitized, categorized, recorded, and made available for retry or operator investigation.

## Retention

Notification log cleanup follows [data retention](../docs/reference/data-retention.md). Changes to state-specific retention windows must update the policy, cleanup code, cron configuration, and tests together.

Participant inbox items and their deliveries are removed by **Federation: Participant inbox retention** only after the federation sets `sports_federation_notifications.inbox_retention_days` (at least 30 days). Only closed items (acted upon, expired or superseded) past the period are removed, never items with a waiting, queued or failed delivery. Each run records evidence under policy `participant_inbox`. See `models/communication_retention.py`.

## Tests

The test suite covers dispatch, triggers, templates, scheduled actions, failure handling, and post-install availability.

## Participant inbox and actionable communications

- Participant inbox at `/my/notifications`, linked from the portal home and `/my/work`.
- Current action, next owner, correction feedback, relevant-task links, urgent-change labels and separate delivery/acknowledgement/task status.
- Published match-day schedule and venue alerts, including current venue address and courts. Draft schedule edits do not alert participants.
- Official assignment notifications for portal-connected assignments and organiser coverage alerts on cancellation/decline.
- Parental-approval return notifications with the reviewer's correction note. Corrected portal uploads link to the returned evidence; pending review is not completion, and verification of linked replacement evidence establishes correction completion.
- Due-soon notifications for actionable operation tasks with deadlines in the next seven days. Waiting and completed work is excluded.
- Per-category preferences: prompt email, daily digest, inbox only. Urgent inbox availability is independent of email preference.
- One receipt per event/user across overlapping roles, database uniqueness and transaction locks, one digest per recipient/local calendar day, duplicate source links suppressed within digests.
- Queued outbound email, existing notification logs, reuse of the same mail record on retry, bounded retry attempts, manager recovery activities and inbox escalation.
- Permission checks at routing, inbox rendering, link opening, queueing and immediately before `mail.mail.send`.
- Existing operation-task digest cron delegates to the same digest service rather than generating a second activity digest.

The adapters cover the workflows listed above. Other legacy notification categories, including finance, discipline and compliance-specific outbound templates, retain their existing delivery behaviour. The new preferences are not advertised as controlling those unrelated legacy emails. Contacts without a portal account, or legacy assignments without fixture/publication linkage, retain the existing assignment-email fallback; they cannot have an authenticated participant inbox.

Two scheduled actions run this: communication dispatch every minute, and due-soon and digest processing hourly. Digests become eligible after 08:00 in the account time zone, once per local calendar day. `sent` means accepted by the outbound mail server, not delivered or read; acknowledging a notification never completes the underlying task. Acceptance scenarios are in the [communications acceptance suite](../docs/release/acceptance/communications.md).
