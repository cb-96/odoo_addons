# Odoo 19 — Sports Federation Addons (quick context)

Owner: Federation Platform Team
Last reviewed: 2026-05-25
Review cadence: Every release

Purpose

This workspace contains a collection of Odoo 19 custom addons that implement a sports federation management system: clubs, teams, seasons, tournaments, rules, refereeing, rosters, results verification, standings, portal and public website integration, and reporting.

Where to find things

- Modules: `odoo/` — each addon is named `sports_federation_<domain>` (e.g. `sports_federation_base`, `sports_federation_tournament`, `sports_federation_competition_engine`).
- Authoritative behaviour: `odoo/_workflows/` (e.g. `WORKFLOW_TOURNAMENT_LIFECYCLE.md`, `WORKFLOW_MATCH_DAY_OPERATIONS.md`, `WORKFLOW_RESULT_PIPELINE.md`).
- Architecture notes and developer guidance: `odoo/TECHNICAL_NOTE.md`.
- Module-level implementation notes: `odoo/<module>/README.md` and `_logs/INSTALL_LOG_*.md`.

Core modules (quick)

- `sports_federation_base`: Master data — clubs, teams, seasons, registrations, base security groups.
- `sports_federation_tournament`: Competitions, tournaments, stages, groups, participants, matches and match lifecycle.
- `sports_federation_competition_engine`: Scheduling algorithms, wizards, and the backend Competition Workspace for guided division planning and slot-based scheduling.
- `sports_federation_people`: Player master data and licensing.
- `sports_federation_rosters`: Season rosters and match-sheet management.
- `sports_federation_officiating`: Referee registry and assignments.
- `sports_federation_result_control`: Result submit/verify/approve pipeline and contest/correction flows.
- `sports_federation_standings`: Standings computation and publishing.
- `sports_federation_public_site` / `sports_federation_portal`: Website and portal controllers/templates.

Key workflows (at-a-glance)

- Tournament lifecycle — competition setup, participant enrolment, stage progression, schedule generation, completion. See `odoo/_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md`.
- Match-day operations — roster checks, referee confirmation, match execution, incident logging. See `odoo/_workflows/WORKFLOW_MATCH_DAY_OPERATIONS.md`.
- Result pipeline — submit → verify → approve (with contested/corrected exceptions). See `odoo/_workflows/WORKFLOW_RESULT_PIPELINE.md`.
- Public publication — `website_published` toggles, public slugs, and safe public pages for tournaments and standings. See `odoo/_workflows/WORKFLOW_PUBLIC_PUBLICATION.md`.

Developer quick-start (most common tasks)

1. Add models: `odoo/<module>/models/<file>.py` and export in `models/__init__.py`.
2. Security: add `security/ir.model.access.csv` and `security/*.xml` record rules.
3. Views: add `views/*.xml` and register in `__manifest__.py` `data`.
4. Wizards/services: put transient models in `wizards/` and algorithmic code in `services/` (competition engine is the canonical location).
5. Tests: put unit/integration tests under `odoo/<module>/tests/` and include at least one focused test for new business logic.
6. Run module tests: `odoo-bin -d <db> -i <module> --test-enable --stop-after-init`.

PR checklist (quick)

- Tests added or updated for the core business behaviour.
- Security ACLs/record rules added.
- `__manifest__.py` updated (depends/data/version) when database changes are introduced.
- Short README or notes added to the module.

Notes for agents/readers

- Prefer the `_workflows` files and `TECHNICAL_NOTE.md` as the source of truth for business behaviour and extension points.
- When proposing code changes, keep modules focused, prefer service classes for algorithms, and add tests demonstrating deterministic behaviour (especially for schedule generation).

If you want, I can expand this summary into a short onboarding checklist, open a PR with the change, or scan `_logs/` and module READMEs to pull in extra context.

Recent additions (2026-04-07)

The competition engine and related modules received several new models to support per-round scheduling and automated stage progression. Quick pointers:

- `sports_federation_competition_engine/models/stage_progression.py` — stage-to-stage progression rules (`auto_advance`, `cross_group`, seeding options).
- `sports_federation_competition_engine/models/tournament_template.py` — tournament templates and `action_apply()` to scaffold stages/groups/progressions.
- `sports_federation_tournament/models/federation_tournament_round.py` — persistent `tournament.round` objects used by per-round scheduling, reporting, and round-owned calendar dates.
- `sports_federation_venues/models/federation_tournament_round_inherit.py` — extends rounds with venue ownership so shared round logistics live in one place.
- `sports_federation_tournament/models/federation_match.py` — bracket/linking fields and auto-advance wiring for knockout flows.

See `odoo/TECHNICAL_NOTE.md` → "New competition models and behaviours (2026-04-07)" for details.

Recent additions (2026-05-25)

- `sports_federation_competition_engine/models/competition_workspace_models.py` — guided planning fields on competition editions, divisions, and gamedays, plus backend entrypoints to open the workspace.
- `sports_federation_competition_engine/models/competition_schedule_revision.py` — persistent live, draft, and superseded publication snapshots for each planner root gameday.
- `sports_federation_competition_engine/models/competition_workspace_presence.py` — active-operator heartbeat records for collaboration warnings and same-gameday edit indicators.
- `sports_federation_competition_engine/models/federation_match_slot.py` — persistent `federation.match.slot` records for court and time-slot planning.
- `sports_federation_competition_engine/services/competition_workspace.py` — server-side workflow orchestration, planner payloads, safe-swap-aware assignment validation, collaboration heartbeat, revisioned publication guards, pool-then-bracket planning, fairness summaries, and ranked slot suggestions.
- `sports_federation_competition_engine/static/src/client_actions/competition_workspace/` — Owl backend client action for role-aware, mobile-friendly scheduling with grouped validation, presence, stage-aware planning controls, fairness visibility, and slot suggestions.
- `sports_federation_venues/models/competition_workspace_extension.py` — venue blackout, maintenance, and playing-area capability validation plus venue-readiness summaries for the Competition Workspace.
- `sports_federation_officiating/models/competition_workspace_extension.py` — officiating readiness validation, uncovered-availability warnings, and double-booking blocks for Competition Workspace planning.
- `sports_federation_base/views/menu_items.xml` and related addon menu files — backend navigation now uses journey-first buckets (`Setup`, `Planning`, `Match Day`, `Publication`, `Administration`), with Planning Workspace as the primary scheduling entry point.
- `sports_federation_portal/views/portal_templates.xml` and `portal_tournament_workspace_templates.xml` — club representatives now start from a clearly primary Club Operations Workspace, while direct queues remain available as secondary or advanced links.
- `sports_federation_base`, `sports_federation_tournament`, `sports_federation_rosters`, `sports_federation_result_control`, `sports_federation_standings`, and `sports_federation_public_site` form views now surface inline next-step guidance and direct cross-module handoffs, including season-registration-to-roster, participant-to-roster, result-to-tournament, and tournament-to-standings/publication flows.
- `sports_federation_competition_engine` and `sports_federation_portal` now expose a clearer phase model for scheduling and match day: Planning Workspace is the primary schedule-building surface, Gameday Planner is the one-day preparation surface, Live Operations Board is for in-progress play, and portal result pages are the result follow-up surface.

See `odoo/TECHNICAL_NOTE.md` → "Competition Workspace planning flow (2026-05-25)" for details.
See `odoo/TECHNICAL_NOTE.md` → "Guided setup and cross-module handoffs (2026-05-25)" for the Phase 2 intuitiveness baseline.
See `odoo/TECHNICAL_NOTE.md` → "Canonical planning and match-day flows (2026-05-25)" for the Phase 3 intuitiveness baseline.

Recent additions (2026-05-26)

- `sports_federation_portal/models/portal_status_labels.py` introduces shared
	portal-facing state label helpers so operational pages stop leaking raw model
	values.
- `sports_federation_public_site/models/public_status_labels.py` now includes
	player license labels for club/player public pages.
- Portal and public templates now consistently render state labels through
	helper methods (`get_portal_state_label`,
	`get_portal_result_state_label`, `get_public_site_state_label`).
- Template accessibility tests in `sports_federation_portal` and
	`sports_federation_public_site` now include regression checks that forbid raw
	state rendering fragments.
- `INTUITIVENESS_REVIEW_CHECKLIST.md` now defines the lightweight governance
	gate for major naming, entry-point, and UX-state changes.

See `odoo/TECHNICAL_NOTE.md` → "Portal/public intuitiveness baseline
(2026-05-26)" for details.

Priority 0 hardening snapshot (2026-04-10)

- Core master data now uses explicit archive and restore actions with guardrails on clubs, teams, seasons, and tournaments so operational records are retired intentionally rather than disappearing through direct writes to `active`.
- Portal season registration review is now closed-loop: only open seasons accept submissions, federation staff review the same record in the backend, and confirmation or rejection notifications are logged for the submitting representative.
- Competition setup wizards now validate tournament state, effective rule set, stage and group ownership, and minimum participant counts before they will generate fixtures. Overwrite mode is previewed and warned explicitly.
- Result control now enforces separation of duties across submit, verify, and approve actions, keeps approved scores immutable, and automatically recomputes linked non-frozen standings whenever official-result eligibility changes.
- Portal and public publication surfaces now document the same ownership and visibility rules enforced by the code: portal writes are club-scoped, public routes are toggle-gated, and `public_slug` is uniqueness-guarded metadata.
- Contributor workflow is now centered on `ci/run_tests.sh` named suites plus `CONTRIBUTING.md`, keeping CI env-driven and focused on the highest-risk federation flows.

Use this file as the quick orientation layer, then rely on the workflow docs and module READMEs for the operational details.
For contributor-facing local setup and focused CI commands, continue with `CONTRIBUTING.md`.

