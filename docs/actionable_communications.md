# Actionable communications: implementation and validation

## Delivery status

This change extends `sports_federation_notifications` against commit `5947c54c60abf41893de8760b40bb4b9d5f7d587` plus the uploaded worktree changes. Existing modified and untracked connected-role-journey files are preserved. It does not apply older patches, deploy to a running server, or claim staging acceptance.

Implemented:
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
- Acceptance evaluator for real usability and staging observations.

The adapters cover the workflows listed above. Other legacy notification categories, including finance, discipline and compliance-specific outbound templates, retain their existing delivery behaviour. The new preferences are not advertised as controlling those unrelated legacy emails. Contacts without a portal account, or legacy assignments without fixture/publication linkage, retain the existing assignment-email fallback; they cannot have an authenticated participant inbox.

## State boundaries

1. Business action commits with its inbox receipt and pending delivery intent in the same transaction.
2. Inbox availability does not wait for SMTP. The inbox is server-rendered; a user must open or refresh it to see newly committed alerts.
3. Dispatch queues a mail record. This is not delivery.
4. `sent` means acceptance by the outbound mail server, not confirmed external-provider delivery, reading or acknowledgement.
5. Acknowledgement records recipient and timestamp only. It never verifies a document, accepts an assignment, creates replacement coverage or completes an operation task.
6. Task status is derived from current source state and existing journey permissions. Schedule alerts require review; there is no invented business completion action for reading a changed venue.

No SMTP implementation can guarantee exactly-once delivery across an ambiguous connection failure after remote acceptance. Application receipt and delivery identities are deduplicated. Missing previously queued mail is quarantined rather than automatically recreated; investigate acceptance before recreating anything. External-provider receipts/webhooks are not added by this patch.

## Current-source regeneration

Use this current-source patch instead of the earlier communications patch, not in addition to it. The previous code already applied cleanly to this snapshot; no feature rewrite was necessary. The patch was regenerated with the current file contents as its baseline. Do not reset or discard your existing worktree changes.

## Apply and upgrade

Back up the database and filestore. Apply only to the supplied snapshot or a branch where the check succeeds. The ZIP contains changed files, not a complete repository.

```bash
git apply --check actionable_communications_current.patch
git apply actionable_communications_current.patch
odoo-bin -d STAGING_DB -u sports_federation_notifications --stop-after-init
```

Restart application workers after upgrading. The notifications addon version becomes `19.0.1.4.0`. Calendar and schedule-approval dependencies are explicit. Two scheduled actions are installed active: communication dispatch every minute and due-soon/digest processing hourly. Digests become eligible after 08:00 in the account timezone and run once per local calendar day. A later item can wait until the next day's digest; it is already in the inbox.

Ensure the existing mail queue and outbound server are configured. Set `web.base.url` to the externally reachable staging URL. Use a staging mail sink, not real participant addresses, for automated delivery-failure tests. Do not enable an additional legacy reminder job for the same tested workflow without checking its routing.

## Automated checks

Executed in the implementation environment:
- Repository Python/XML/manifest static checks passed.
- Existing notification side-effect contract passed.
- 12 pure policy tests passed.
- Secondary XML parsing and the supplied role-home inheritance anchor passed.
- Patch applicability and byte-for-byte reconstruction are checked when packaging.

Written, not executed here: 30 ORM tests and 6 HTTP tests tagged `actionable_communications`. There is no Odoo runtime or database in this environment. Tests use isolated fixture contacts and evidence, not measured participant outcomes.

```bash
PYTHONDONTWRITEBYTECODE=1 python ci/static_checks.py
PYTHONDONTWRITEBYTECODE=1 python ci/check_notification_side_effect_contract.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_communication_policy.py
odoo-bin -d STAGING_TEST_DB -u sports_federation_notifications \
  --test-enable --test-tags actionable_communications --stop-after-init
```

Also run the existing portal journey, notification, schedule-publication, officiating and document tests. Validate module upgrade and QWeb rendering in the real Odoo 19 registry; XML parsing alone does not establish runtime view validity.

## Required staging scenarios

### Changed venue and published schedule
1. Prepare a live publication with at least two teams, a club representative, a team-scoped representative, an assigned official and an organiser.
2. Give one user overlapping club/team/official responsibilities.
3. Change the physical match-day venue using the authorised workflow, or replace the approved published schedule with changed court/time assignments.
4. Check one receipt per affected user and no receipt for an unrelated club or an inactive account.
5. From the notification, identify the new venue/address and open the current schedule without searching. Verify the displayed courts and UTC-labelled times against the live publication.
6. Repeat a no-op write. No extra event should be created. An actual subsequent change is a new intentional event.
7. Revoke a representative's scope and retry the old inbox URL: private content and task links must no longer be available.

### Official declines and organiser fills the gap
1. Assign an eligible official to a portal-connected published match.
2. Decline through the existing portal response action with a reason.
3. The organiser receives an urgent coverage alert and reaches the relevant match directly.
4. Confirm a replacement for the same match/publication/role. Reopen the alert: it must no longer claim an unresolved coverage gap.
5. Acknowledging the alert must not assign or confirm an official.

### Returned document and corrected evidence
1. Upload a parental-approval document through the existing player portal.
2. Record a specific review note, then use Request replacement.
3. The submitting authorised club account sees the correction note and reaches that player's evidence page directly.
4. Upload corrected evidence. Check its `replaces_approval_id`, the old evidence remains retained, and the notification says waiting for federation review.
5. Verify the linked replacement in the authorised backend. The correction becomes complete independently of notification acknowledgement.
6. Test an unrelated club, a revoked representative and a forged notification ID. None may obtain private correction content.

### Preferences and digests
1. Save each category as inbox only, prompt email and digest in turn.
2. Verify inbox availability in every mode. Inbox only must not create outbound mail.
3. Change preferences after queueing but before sending; verify the send-time check prevents disabled email.
4. Prepare an actionable task due within seven days, a waiting task and a completed task. Only actionable due-soon work enters the reminder digest.
5. Run both the new digest cron and the existing task digest cron repeatedly on the same local day. One logical digest per user/day, no duplicate task links.
6. Test a user with both manager and club roles and accounts in different timezones.

### Failure, retry and escalation
1. Queue email into a controlled mail sink; force a confirmed mail exception.
2. Inspect delivery failure, its existing notification log and retry count.
3. Recover using Retry delivery only. The receipt ID, delivery ID and mail ID remain unchanged. Compare the business record state/write timestamp and business-event count before/after: no repeated business action.
4. Repeat retry and dispatch calls, including overlapping workers. One application receipt and one logical delivery must remain.
5. After three queue attempts fail, verify one manager escalation per manager and delivery, not repeated activities.
6. Remove the email address, then correct it and recover. Remove a previously queued mail record separately: automatic recreation must be blocked.
7. Revoke recipient scope between queueing and sending. No external send may occur.

## Success metrics: real evidence only

Use at least ten distinct recipients for the tested workflow. Without coaching, ask each to state the requested action and next owner, then open the relevant task. Record whether they understood and reached the correct task without searching. Keep the test workflow and baseline exposure comparable.

Measure urgent availability with an authenticated recipient session polling `/my/notifications` after the business action commits. Use a monotonic clock and a one-second polling interval. Record the time to the first response containing the expected notification ID. Database `occurred_on` and `available_on` are diagnostic timestamps, not proof of externally observed availability. Measure external-provider acceptance/delivery separately using provider or mail-sink evidence. The staging target is at most 60 seconds for inbox availability, not for email.

Record manual reminders before and after for the same workflow and comparable workload. If workload differs, normalise both counts to the same number of business cases before evaluation. A zero or missing baseline cannot establish a 50% reduction.

Save real observations in a JSON file with these keys:

```json
{
  "recipients": [],
  "permission_tests": {"executed": 0, "unauthorised_recipients": null},
  "duplicate_tests": {"retry_executed": 0, "multi_role_executed": 0, "unintended_duplicates": null},
  "urgent_inbox_latency_seconds": [],
  "manual_reminders_baseline": null,
  "manual_reminders_after": null
}
```

Each recipient observation contains `understands_action` and `correct_task_without_search` booleans. Empty values above are a schema template, not synthetic measurements. The evaluator fails missing evidence.

```bash
python ci/evaluate_communication_acceptance.py observations.json --output acceptance.json
```

Required gates: at least 90% action understanding, at least 90% correct-task navigation without searching, zero unauthorised recipients, zero unintended retry/multi-role duplicates, all recorded urgent inbox latencies at most 60 seconds, and manual reminder reduction at least 50%. None of these human or live-service gates has been claimed passed here.

## Operational follow-through

Review the new receipt/delivery retention policy with your existing data-retention requirements before production: this patch does not silently delete unresolved inbox work or introduce an arbitrary retention period. Existing notification-log retention remains in place. Monitor dispatch backlog and cron execution duration at representative scale; the dispatcher rotates its bounded batches by last-check timestamp. Confirm the send-time hook is exercised by your actual mail-provider integration, especially if a custom provider bypasses `mail.mail.send`.
