# Constraint and Index Audit (Wave 1 / Item 5)

Date: 2026-06-01
Owner: Federation Platform Team
Scope: major high-traffic workflow models across tournament, portal, and result control

## Audit Method

1. Reviewed model-level SQL constraints (`models.Constraint`) on key workflow models.
2. Reviewed indexed filter fields used by operations board, planner, reporting, and result lifecycle flows.
3. Added schema hardening migration where index coverage was weak for common match filters.

## Coverage Snapshot

| Model | Constraint status | Index status | Audit result |
|---|---|---|---|
| `federation.season.registration` | `unique(team_id, season_id)` present | relational filter fields present | OK |
| `federation.tournament.participant` | `unique(team_id, tournament_id)` present | relational filter fields present | OK |
| `federation.tournament.registration` | `UNIQUE(team_id, tournament_id)` present | relational filter fields present | OK |
| `federation.match` | Python integrity guards present (`home != away`) | gaps on state/date-heavy filters were identified | HARDENED |
| `federation.match.result.audit` | append-only event model | `event_type` and `match_id` indexed | OK |

## Hardening Delivered

### Schema migration

Module: `sports_federation_tournament`
Version: `19.0.1.1.0`

- Added migration index pack in:
  - `sports_federation_tournament/migrations/19.0.1.1.0/post-migrate.py`
- Added data normalization backfill in:
  - `sports_federation_tournament/migrations/19.0.1.1.0/pre-migrate.py`

### Indexes added

- `federation_match_tournament_state_idx` on `(tournament_id, state)`
- `federation_match_stage_state_idx` on `(stage_id, state)`
- `federation_match_group_state_idx` on `(group_id, state)`
- `federation_match_scheduled_date_state_idx` on `(scheduled_date, state)`
- `federation_match_date_scheduled_state_idx` on `(date_scheduled, state)`

### Data-fix / backfill

- Backfill `scheduled_date` from `date_scheduled` when missing.
- Backfill `round_number` from `federation_tournament_round.sequence` when missing.

## Follow-up Watchpoints

- Re-run this audit on each release train when `federation.match` filters or standings/result workflows change.
- If a future release adds DB-level `home_team_id != away_team_id` constraints, include a pre-migration duplicate cleanup script first.
