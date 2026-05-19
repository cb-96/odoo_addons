# Performance Baselines

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

This document records the query-count budgets enforced in CI for the slowest
public, portal, and reporting helpers. The budgets are intentionally small so
N+1 regressions become visible before release, while the SQL plan watchpoints
highlight which operators usually dominate the heavy reporting views.

## Public And Portal Budgets

- `federation.tournament.get_public_featured_tournaments(limit=4)`: `1` query.
- `federation.tournament.get_public_live_tournaments(limit=4)`: `1` query.
- `federation.tournament.get_public_recent_result_tournaments(limit=4)`: `3` queries after batching approved-match lookups and ranking the latest approved match per tournament.
- `federation.tournament.get_public_schedule_sections()`: `4` queries.
- `federation.team.roster.line._portal_get_available_players()`: `7` queries with the current portal ownership and team-scope checks.

## Reporting Budgets

- `federation.report.schedule._build_season_portfolio_rows()`: `3` queries.
- `federation.report.schedule._build_club_performance_rows()`: `4` queries.

## SQL Plan Watchpoints

- `federation_report_season_portfolio`: expect aggregate and sort or window operators because the view rolls up season registrations, finance events, budgets, and compliance checks through multiple CTEs.
- `federation_report_club_performance`: expect aggregate and sort or window operators because the view unions match sides before club-level rollups and season ordering.

Committed snapshots:

- `ci/explain_snapshots/federation_report_season_portfolio.txt`
- `ci/explain_snapshots/federation_report_club_performance.txt`

Refresh the snapshots from a live or restored database when the underlying SQL
views change materially:

```bash
python3 addons/ci/capture_explain_snapshots.py --db odoo_restore_drill
```

## Slow-Query Logging Recipe

Use PostgreSQL slow-query logging on a staging or restore-drill database before
and after reporting view changes when the query budgets or plan snapshots move:

```bash
docker compose exec -T db psql -U odoo -d postgres -c "ALTER SYSTEM SET log_min_duration_statement = '200ms';"
docker compose exec -T db psql -U odoo -d postgres -c "SELECT pg_reload_conf();"
```

After the sampling window, reset the override:

```bash
docker compose exec -T db psql -U odoo -d postgres -c "ALTER SYSTEM RESET log_min_duration_statement;"
docker compose exec -T db psql -U odoo -d postgres -c "SELECT pg_reload_conf();"
```

## Regression Coverage

- Public-site budgets are asserted in `sports_federation_public_site/tests/test_public_api.py`.
- Portal roster budgets are asserted in `sports_federation_portal/tests/test_roster_portal_access.py`.
- Reporting budgets and plan watchpoints are asserted in `sports_federation_reporting/tests/test_operational_reporting.py`.

---

## Performance Tuning Reference

### Recommended PostgreSQL Indexes

Odoo creates standard B-tree indexes on all `Many2one` columns (`_id` suffix)
and `unique` constraint columns. The following indexes go beyond the Odoo
defaults and are recommended for the federation workload:

| Table | Column(s) | Type | Reason |
|---|---|---|---|
| `federation_match` | `(tournament_id, state)` | B-tree composite | Schedule and result queries filter on both |
| `federation_match` | `(stage_id, scheduled_date)` | B-tree composite | Match-day schedule sections ordered by date |
| `federation_standings_line` | `(standings_id, position)` | B-tree composite | Public standings ordered by position |
| `federation_request_rate_limit` | `(scope, subject, window_start)` | B-tree composite | Rate-limit bucket lookup (covered by unique constraint) |
| `federation_player_license` | `(player_id, season_id, state)` | B-tree composite | Eligibility service hot path |
| `federation_report_schedule` | `(state, next_run)` | B-tree composite | Scheduler scan |

To add an index outside the ORM (use a migration script or `init` hook for
persistent indexes):

```python
# In a migration script or post_init_hook:
self.env.cr.execute("""
    CREATE INDEX IF NOT EXISTS idx_federation_match_tournament_state
    ON federation_match (tournament_id, state);
""")
```

### Caching Strategies for Public Feed Routes

The public competition feed (`/competitions/api/json`) and tournament detail
pages are the highest-traffic routes. They hit read-replicas or benefit from
HTTP-layer caching:

- **HTTP `Cache-Control`**: the public JSON endpoint includes
  `Cache-Control: public, max-age=60` by default. Reverse proxies (nginx,
  Cloudflare) will cache the response for 60 seconds.
- **Odoo `ormcache`**: the `get_public_featured_tournaments` and related
  methods are candidates for `@tools.ormcache()` if the feed volume grows
  beyond the current 1-query budget. Add invalidation in the result-approval
  path if you enable ORM-level caching.
- **Read replica**: for > 500 concurrent public users, point the public-site
  controller to a PostgreSQL read replica by setting `db_replica_host` in
  `odoo.conf` (Odoo 17+ feature).

### Interpreting `assertQueryCount` Failures

A `assertQueryCount(N)` failure in CI means the block executed a different
number of queries than `N` — either more (regression) or fewer (test data
change that masks missing queries):

```
AssertionError: 4 queries executed, 1 expected
```

To diagnose:

```bash
# Run with SQL logging to see the actual queries
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo <<'EOF'
import logging
logging.getLogger('odoo.sql_db').setLevel(logging.DEBUG)
# ... call the method here ...
EOF
```

Common causes of query-count increases:
- A new `Many2one` field added to the response without prefetch
- A new `@api.depends` trigger that fetches related records
- A missing `sudo()` that forces an additional ACL check query
- A new `search()` call inside a computed field

**Updating a budget**: if your change legitimately requires more queries,
update the `assertQueryCount(N)` call in the test and add a comment explaining
why. Update the baseline in this document's "Public And Portal Budgets" section.

### Adding EXPLAIN Snapshots to CI

EXPLAIN snapshots protect against query plan regressions (e.g. a sequential
scan replacing an index scan on a large table).

**Step 1**: Capture the baseline from a database with realistic data:

```bash
# Capture all configured snapshots
python3 addons/ci/capture_explain_snapshots.py --db odoo_restore_drill

# Or capture a single query manually
docker compose exec db psql -U odoo -d odoo_restore_drill \
  -c "EXPLAIN (FORMAT TEXT) SELECT ..." \
  > addons/ci/explain_snapshots/my_query_name.txt
```

**Step 2**: Add the snapshot file to version control:

```bash
git add addons/ci/explain_snapshots/my_query_name.txt
```

**Step 3**: Register the snapshot in `ci/check_explain_snapshots.py` if it
is not auto-discovered.

**When a snapshot changes**: CI will fail when the plan changes. Review the
diff. If the new plan is better (e.g. an index was added), update the snapshot
file with the new output. If the plan is worse (e.g. the planner chose a
sequential scan), add the missing index or adjust the query before updating
the snapshot.

**Snapshot freshness**: refresh all snapshots after any bulk data change or
index addition on a production-sized restore-drill database:

```bash
python3 addons/ci/capture_explain_snapshots.py --db odoo_restore_drill
git diff addons/ci/explain_snapshots/
```