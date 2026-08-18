# Package 13: Operations, observability, and recovery

## Health

Run `env["federation.operational.health"].snapshot()` for a sanitized readiness snapshot. It checks database access, required registry models, overdue operational tasks when installed, and active competition integrity when its service is installed. `log_snapshot()` emits only check codes, states, and numeric metrics.

## Backup and restore gate

1. Stop writes or create a transactionally consistent database snapshot.
2. Back up PostgreSQL and the matching Odoo filestore.
3. Restore both into an empty acceptance environment.
4. Replace environment secrets. Never restore production secrets into lower environments.
5. Upgrade modules, run integrity and operational-health checks, then execute canonical smoke journeys.
6. Re-enable scheduled jobs only after verification.

## Incident runbooks

- Failed upgrade: stop traffic, retain logs and database evidence, restore the paired database and filestore, deploy the previous immutable artifact, and run health checks.
- Incorrect publication: preserve the live revision, create a corrective draft, validate, and publish with a reason. Do not mutate historical snapshots directly.
- Notification failure: inspect the sanitized failure category and queue depth, correct transport configuration, and retry eligible items only.
- Portal access incident: deactivate the representative assignment, preserve audit events, rotate credentials where required, and validate club scopes.
