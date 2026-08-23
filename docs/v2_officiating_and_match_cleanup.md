# V2 officiating and standalone-match cleanup

V2 keeps `federation.match` as the operational execution and result record. A
valid V2 operational match is backed one-to-one by `federation.fixture` through
`logical_fixture_id`. Referee assignments, club duties, match sheets and result
control therefore remain attached to `federation.match`.

New official assignments and club duties reject standalone matches. Match-day
bulk planning resolves matches exclusively through the match day's current live
schedule publication. Official history remains attached to retained publication
records, while pending and upcoming portal views show only the current live
publication.

The `sports_federation_tournament` 19.0.1.4.0 migration deletes test-only
standalone matches where `logical_fixture_id IS NULL`. It discovers installed
foreign keys and removes dependent records before deleting those matches.
Shared clubs, teams, players, referees, seasons, venues and V2 fixtures are not
removed.

Before upgrading, take a database backup and record the diagnostic count:

```sql
SELECT COUNT(*) FROM federation_match WHERE logical_fixture_id IS NULL;
```

After upgrading, that count must be zero. A non-zero count should block release.
