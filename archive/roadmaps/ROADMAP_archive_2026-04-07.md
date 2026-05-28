# Sports Federation Platform Roadmap (code-aware)

This file has been revised to map roadmap outcomes directly to the repository
modules, recent model additions, and concrete developer work packages. Use
this as the working roadmap for engineering tickets and PRs.

Top-level sequence

1. Stabilize and make state/ownership explicit across core modules
2. Automate high-value operational actions (finance events, notifications)
3. Centralize eligibility & progression logic (explainable standings)
4. Improve public/portal self-service and reporting

Quick code signals (recent / already implemented)

- `sports_federation_venues` — adds `federation.gameday` to bundle matches by venue/day and helper `find_or_create`. See [odoo/sports_federation_venues/models](../../sports_federation_venues/models).
- `sports_federation_tournament` — materialised rounds: `federation.tournament.round`. See [odoo/sports_federation_tournament/models](../../sports_federation_tournament/models).
- `federation.match` extensions — bracket/linking fields and `action_done()` wiring so knockout brackets auto-advance winners. See [odoo/sports_federation_tournament/models/federation_match.py](../../sports_federation_tournament/models/federation_match.py).
- `sports_federation_competition_engine` — new progression and template models: `federation.stage.progression` and `federation.tournament.template`; services updated for per-round scheduling and full-bracket construction. See [odoo/sports_federation_competition_engine/models](../../sports_federation_competition_engine/models) and [odoo/sports_federation_competition_engine/services](../../sports_federation_competition_engine/services).
- `sports_federation_standings` — cross-group ranking helper and `generate_standings()` delegator; standings freeze can trigger `auto_advance` progressions. See [odoo/sports_federation_standings/models/standing.py](../../sports_federation_standings/models/standing.py).
- Finance passthrough helpers — match-level helper `action_create_venue_finance_event()` to create venue-related finance events (bridge to `sports_federation_finance_bridge`).

What this means for the roadmap

The high-level phases remain valid, but each deliverable should now be
expressed as concrete work packages tied to modules and test coverage. Below
are recommended priorities and ownerable tasks.

Phase 1 — Stabilize (high priority)

Goals:

- Ensure canonical state/ownership for core objects (`federation.match`, `federation.participant`, `federation.tournament`, `federation.standing`).
- Enforce that only `approved`/`published` results count in standings.
- Add blocking-policy matrix tests and implement enforcement where feasible.

Concrete tasks (example tickets):

- State matrix: author `odoo/STATE_AND_OWNERSHIP_MATRIX.md` and reconcile lifecycle enums in `odoo/sports_federation_tournament/models/*.py` and `odoo/sports_federation_result_control` (ensure consistent field names and values).
- Standings safety: add tests in `odoo/sports_federation_standings/tests/test_standings_result_filter.py` to assert contested/unapproved results are excluded; update compute code if needed (`odoo/sports_federation_standings/models/standing.py`).
- Gameday constraint validation: add tests in `odoo/sports_federation_venues/tests/test_gameday.py` verifying the "no duplicate same-category pairing on a gameday" rule and scheduling `schedule_by_round` behaviour.

Phase 2 — Operational automation (deliverables mapped to modules)

Goals:

- Automated finance events for registration/licensing/referee reimbursements.
- Event-driven notifications for state transitions (registration, referee, result approval).

Concrete tasks:

- Finance hooks: implement and test auto-event creation in `odoo/sports_federation_finance_bridge` (unit tests under `odoo/sports_federation_finance_bridge/tests/`). Ensure match-level `action_create_venue_finance_event()` correctly creates finance events.
- Notification matrix: author a trigger matrix doc and implement event dispatchers in `sports_federation_notifications` (or `competition_engine` where scheduling triggers exist).

Phase 3 — Eligibility & competition intelligence

Goals:

- Central eligibility service answering roster/match/registration queries.
- Explainable standings and explicit qualifier flags.

Concrete tasks:

- `eligibility_service`: create `odoo/sports_federation_rules/services/eligibility.py` (or colocate in `people`) with unit tests that validate roster/match eligibility decisions.
- Standings explanation: enhance `odoo/sports_federation_standings` to record tie-break reasons and add acceptance tests that assert the reason chain.

Phase 4/5 — Public experience, reporting, KPI

Goals:

- Richer portal pages and archives (map to `sports_federation_public_site`).
- KPI dashboards and data-quality monitors (instrument import and governance modules).

Concrete tasks:

- Public page improvements: add API endpoints and templates under `odoo/sports_federation_public_site/controllers` and tests covering public slugs and visibility rules.
- KPI reports: create lightweight reports in `odoo/sports_federation_reporting` and exportable CSV endpoints for leadership dashboards.

Documentation, tests and release hygiene (non-negotiable)

- Every change that introduces or modifies models/fields must include:
- `security/ir.model.access.csv` updates,
- updated `__manifest__.py` `data` entries if new XML/CSV data files are added,
- a short README in `odoo/<module>/README.md` describing behaviour and migration notes.
- Add focused unit/integration tests for all new scheduling and progression logic. Suggested tests to add first:
- `odoo/sports_federation_competition_engine/tests/test_round_robin.py`
- `odoo/sports_federation_competition_engine/tests/test_knockout_bracket.py`
- `odoo/sports_federation_competition_engine/tests/test_stage_progression.py`
- `odoo/sports_federation_venues/tests/test_gameday.py`

Immediate next steps (recommended)

1. Create the `STATE_AND_OWNERSHIP_MATRIX.md` doc and assign owners for `match`, `standing`, `participant`, `registration`.
2. Add the tests listed above and run the Odoo test runner in CI.
3. Audit `security/` files for new models (`gameday`, `tournament.round`, `stage.progression`, `tournament.template`, bracket fields on `match`).
4. Add migration notes in `TECHNICAL_NOTE.md` for DB-impacting changes.

If you want, I can:

- open PRs with the test skeletons and the `STATE_AND_OWNERSHIP_MATRIX.md` draft, or
- commit & push this roadmap update now and create a set of issues from the "Immediate next steps" list.
