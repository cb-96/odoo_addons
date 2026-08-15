# Migration Rollback Notes

## 2026-06-01 — sports_federation_tournament 19.0.1.1.0

Migration artifacts:
- `sports_federation_tournament/migrations/19.0.1.1.0/pre-migrate.py`
- `sports_federation_tournament/migrations/19.0.1.1.0/post-migrate.py`

### Forward changes

1. Backfill `federation_match.scheduled_date` where missing.
2. Backfill `federation_match.round_number` from linked round sequence where missing.
3. Add five non-unique operational indexes to `federation_match`.

### Rollback trigger

- Significant regression in match-list/filter performance.
- Unexpected planner/operations behavior linked to backfilled schedule columns.

### Rollback actions

1. Restore latest validated DB backup if data backfill must be reverted.
2. If only index rollback is needed, drop the migration-created indexes:

```sql
DROP INDEX IF EXISTS federation_match_tournament_state_idx;
DROP INDEX IF EXISTS federation_match_stage_state_idx;
DROP INDEX IF EXISTS federation_match_group_state_idx;
DROP INDEX IF EXISTS federation_match_scheduled_date_state_idx;
DROP INDEX IF EXISTS federation_match_date_scheduled_state_idx;
```

3. Re-run module tests and full CI before re-promoting the release branch.

### Owner

Federation Platform Team
