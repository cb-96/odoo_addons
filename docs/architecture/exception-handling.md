# Exception handling

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

- Catch expected domain failures narrowly: `ValidationError`, `AccessError`,
  `UserError`.
- Integration boundaries may catch `Exception` only when they log with
  correlation context, classify the failure, persist operator feedback, and do
  not report success.
- Silent `except Exception: pass` is prohibited.
- Cron batches isolate individual records but retain error evidence (see
  operational jobs in the [technical reference](technical-reference.md#reliability-and-observability)).
- Authorization errors are never downgraded to not-found or success
  responses. Hiding a record that the user may not know exists is done with a
  deliberate `request.not_found()`, not by catching an access error.
- Side effects such as notifications record their failure and never roll back
  the business decision that triggered them.

## Notification delivery boundary

Event templates and direct-content fallbacks persist a notification log and
create `mail.mail` with no immediate SMTP call. Template rendering and mail
creation run in a savepoint so a failed render does not undo the business
transition. Queued mail stays `pending`; only observed `mail.mail.state == sent`
marks its log sent, meaning accepted by the outbound transport, not read or
received by the participant. Activities remain local transactional records.

The existing mail queue is the only SMTP transport for both event notifications
and actionable communications. Actionable deliveries keep their preference and
source-permission checks immediately before sending and their own retry owner.
Their logs link to the same mail but are excluded from the event-outbox retry
cron, avoiding competing retry owners.

The outbox reconciliation cron processes up to 200 logs every five minutes.
Transient transport failures can be requeued automatically up to three total
send attempts, with a five-minute-per-attempt delay. Permanent errors and
cancelled mail require operator review. Retry reuses the existing mail and log;
missing previously queued mail is never silently recreated. Mail and log locks
prevent reconciliation/retry from racing the active transport. Managers can
requeue failed event mail from the log, while actionable delivery retries route
to their permission-aware owner. Existing operation jobs remain compatible but
complete when mail is queued, not when it is delivered.

Pending logs linked to queued mail are excluded from age-based log purging.
Already sent/failed historical logs are not replayed during upgrade. Keep the
standard mail queue scheduler enabled; the reconciliation cron does not send
mail itself. Test this upgrade in an installed Odoo database before deployment.

## Complete producer isolation

The notification effect boundary covers recipient routing, log/receipt creation,
rendering and queueing. Business `write()` calls remain outside that boundary;
their authorization, validation and transaction failures still propagate.
Notification trigger routing runs after the authoritative write in its own
savepoint. Failure rolls back notification changes, records a manager-visible
failure in a separate savepoint when possible, and never claims successful
queueing. If failure evidence itself cannot be written, the server log records
that failure without undoing the decision. Serialization and deadlock failures
propagate so Odoo can retry the whole transaction safely.

Non-manager notification logs are recipient-partner scoped. Email-only legacy
logs without an explicit recipient partner are manager-only, not broadly readable
by federation users. Target display names use caller access and a user-dependent
compute cache, never elevated target lookup. Inbox receipts still revalidate
source access at presentation and mail transport time.

Inbox pages use an ID cursor, not a total-count/offset scan: at most 200 receipt
candidates and 20 authorized items are processed per page. A revoked-access window
can return an empty page with an older-page continuation. Legacy numbered-page
links return to the newest page. Digest processing refreshes the shared manager
queue once, prefetches preferences, and isolates each account's work. Failed
manager refresh prevents routing stale manager digests for that run.
