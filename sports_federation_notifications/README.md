# Sports Federation Notifications

Version: 19.0.1.3.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
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

Notification log cleanup follows `DATA_RETENTION_POLICY.md`. Changes to state-specific retention windows must update the policy, cleanup code, cron configuration, and tests together.

## Tests

The test suite covers dispatch, triggers, templates, scheduled actions, failure handling, and post-install availability.

## Removed document

`ROADMAP_RC.md` is deleted. Its remaining one-line item was not a durable roadmap and is now represented by the module's reliability contract and repository roadmap.
