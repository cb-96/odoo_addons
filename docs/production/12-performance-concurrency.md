# Package 12: Performance and concurrency

The migrations add composite indexes for planner, stage, match, gameday, registration, roster, and action-queue domains. Every index is created only when its real table contains all required columns. Skipped indexes are logged instead of aborting the module upgrade.

Before production, inspect the upgrade log and validate resulting indexes with `EXPLAIN (ANALYZE, BUFFERS)` on a production-like anonymized database.

Concurrency gate: slot assignment, publication, stage deletion, registration acceptance, roster editing, and result approval must preserve revision and domain invariants. Bulk and scheduled operations must remain bounded.
