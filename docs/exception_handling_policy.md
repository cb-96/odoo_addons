# Exception Handling Policy

Catch expected domain failures narrowly (`ValidationError`, `AccessError`, `UserError`). Integration boundaries may catch `Exception` only when they log with correlation context, classify the failure, persist operator feedback, and do not report success. Silent `except Exception: pass` is prohibited. Cron batches isolate individual records but retain error evidence. Authorization errors must never be downgraded to not-found or success responses.
