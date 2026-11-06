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
