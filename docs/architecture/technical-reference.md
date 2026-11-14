# Technical reference

Owner: Federation Platform Team
Last reviewed: 2026-11-13
Review cadence: Every release

Conventions and patterns that apply across the `sports_federation_*` addons.
Read the [architecture overview](overview.md) first. Module-specific behaviour
is documented in each addon's `README.md`; business processes are in the
[workflows](../workflows/README.md); canonical states are in
[state and ownership](state-and-ownership.md).

## Code layout

| Directory | Contents |
| --- | --- |
| `models/` | Persistent models and model-owned commands. Export every file in `models/__init__.py`. |
| `services/` | Stateless algorithms (pairing, scheduling, validation). Unit-testable without the ORM where possible. |
| `wizards/` | Transient models for interactive preview-and-confirm flows. |
| `controllers/` | Portal, public and integration HTTP endpoints. Thin: parse, call a model command, render. |
| `views/` | Back-office views, menus and QWeb templates, registered in the manifest `data` list. |
| `security/` | Groups, `ir.model.access.csv` and record rules. |
| `data/` | Sequences, scheduled actions, mail templates and seed data. |
| `migrations/<version>/` | Pre- and post-migration scripts for upgrade-sensitive changes. |
| `tests/` | `TransactionCase` and `HttpCase` tests, tagged for suite selection. |

Do not create empty directories. A new addon uses the same layout and must
declare every direct dependency and data file in `__manifest__.py`.

## Data model conventions

- Domain models use the `federation.` prefix (`federation.player`,
  `federation.match`). Many2one fields end in `_id`, x2many fields in `_ids`.
- Lifecycle uses a `state` selection field. Transitions are explicit methods
  (`action_confirm()`, `action_close()`) that check invariants before writing
  and emit side effects after.
- Keep selection tuples and state-role predicates in a small helper module
  when one addon reuses the same vocabulary across models, for example
  `sports_federation_import_tools/workflow_states.py` and
  `sports_federation_governance/workflow_states.py`. Prefer predicates such as
  `is_import_job_approved(...)` over raw string comparisons.
- Centralize `ir.sequence` definitions in the addon that issues the numbers.
- Use SQL constraints for uniqueness and `index=True` on frequently filtered
  fields. `ci/check_constraint_index_contracts.py` validates the curated list in
  `ci/contracts/constraint_index_contracts.json`.
- Use `@api.depends` for computed fields; store a computed field only when it
  is filtered or sorted frequently.
- Use `read_group` for aggregates and batch `create()` calls with lists of
  values for large volumes such as fixture generation.
- Reference models from other addons through the ORM (`env["federation.x"]`),
  never by importing their Python classes, and only from declared
  dependencies.
- Core master data (clubs, teams, seasons, divisions) is retired through
  explicit archive and restore actions with guardrails, not direct writes to
  `active`. See [state and ownership](state-and-ownership.md#archive-behaviour).

## Workflow commands

- Every protected transition has exactly one command on the owning model.
  Controllers, wizards and other addons call that command; they never write
  `state` directly. `ci/check_workflow_command_boundaries.py` and
  `ci/check_privileged_command_contracts.py` enforce this.
- Workflow transition responses return record IDs as strings in
  `previous_states` so they serialize for both JSON-RPC and XML-RPC clients.
- **Blocking vs warning-only:** a blocking issue stops the current step. A
  warning lets the step continue but requires follow-up; where configured,
  a manager reason is mandatory and is stored on the operation or revision
  (for example warning-only assignment overrides and republishing a live
  schedule).
- **Exceptions and recovery:** governance overrides are the single exception
  engine ([governance override](../workflows/governance-override.md)). After a
  disputed or corrected outcome, use one recovery loop: resolve the exception,
  restore result and standings officiality, then republish the affected
  public surfaces.
- **Readiness chain:** season registration confirmation → participant
  confirmation → roster and game-day readiness → result approval → standings
  review and recompute → division and standings publication.
- Readiness shown to users uses the six shared words of the
  [readiness vocabulary](readiness-vocabulary.md); "can this game day run?"
  is answered by one service.

## Competition algorithms

### Principles

- **Deterministic:** the same participants, seeding and start time produce
  the same fixtures. Sort participants by an unambiguous key (explicit seed,
  then id) before generating.
- **Testable:** keep algorithms in services and test them with small fixed
  datasets.
- **Preview first:** wizards validate, show a summary and require explicit
  confirmation. Overwriting is opt-in and warned about before it happens.

### Formats

`sports_federation_format` owns the versioned structure graph. Stage-to-stage
edges use `federation.structure.stage.progression` (structure, source stage,
target stage). Supported deterministic formats are single and double league,
seeded knockout cups, placement brackets, match series, pools followed by
knockout, championship/relegation splits and custom acyclic multi-stage
graphs. Feasibility checks report fixture and round estimates and reject
invalid configurations before generation. Swiss pairing, ladders and double
elimination are deliberately excluded until their dynamic pairing semantics
can be represented completely.

- **Round robin (circle method):** odd participant counts get a bye; single
  or repeated cycles; `n·(n−1)/2` matches per cycle.
- **Knockout:** the full bracket tree is created up front. Later-round matches
  are placeholders linked to their source matches and are filled when results
  are approved.
- **Pools to knockout:** seeds are distributed across pools, pool fixtures are
  generated, and seeded knockout placeholders are prepared for the first
  publication. Freezing each pool applies its progression edge; the bracket
  fills only after every pool has a frozen table. Tie resolution is recorded on
  the operational match before result submission.
- Every match of every stage exists after the format is confirmed, so later
  stages can be scheduled and published with placeholders. See
  [competition formats](../user-guide/competition-formats.md).

### Rounds and matches

- `federation.tournament.round` is a logical round inside a stage. Rounds own
  sequence and calendar metadata; `sports_federation_venues` adds `venue_id`
  to rounds.
- `federation.match` carries bracket fields (`round_id`, `round_number`,
  `bracket_position`, `bracket_type`, `source_match_1_id`,
  `source_match_2_id`, `source_type_1/2`, `next_match_ids`). Matches use
  `venue_id`; there is no free-text venue field.
- Teams of the same category cannot meet twice inside the same round.
- A `federation.standing` linked to a structure stage (`structure_stage_id`,
  see `sports_federation_format/models/standing_stage_bridge.py`) is the live
  table of that stage. Freezing the table freezes the stage snapshot and
  applies its outgoing progression edges, filling the placeholders of the next
  stage.

### Scheduling validation

- Slot occupancy and team overlap conflicts are blocking. Two already
  scheduled matches on the same planner may swap slots when both post-swap
  validations pass.
- Rest below the schedule's `preferred_rest_minutes` is a warning. A
  mandatory minimum-rest constraint is blocking.
- Validation payloads group conflicts, include resolution hints and carry
  focus metadata so the UI can highlight the affected slots and matches.
- Published game days protect routine schedule edits; corrections use a
  reviewed replacement revision.

## Rosters and eligibility

- `sports_federation_rules` evaluates licence rules with season, club,
  selected licence and reference date. Registration rules validate the actual
  `federation.season.registration` team/season record.
- Rosters compute `ready_for_activation` and `readiness_feedback`; activation
  blocks until active lines meet the rule-set size limits and every player
  passes eligibility.
- Match sheets compute `ready_for_submission` and `readiness_feedback`;
  submission blocks when players are not on valid active roster lines, fail
  licence or registration rules, or the squad size is out of bounds. A player
  under 16 in a senior competition needs a verified parental approval covering
  the participation date.
- Participant confirmation warns before the roster deadline and, once it is
  reached, requires an active ready roster (competition-specific rosters are
  preferred over generic season rosters). Future match scheduling enforces the
  same requirement.
- One line-up per team and game day is shared by all that team's matches on
  the day; players who do not play a given match are crossed out on that
  match only.
- Roster, line-up and substitution events are logged in
  `federation.participation.audit`. A roster line referenced by a live match
  sheet cannot be changed structurally; approved sheets freeze the line-up
  while still allowing substitution timing until final lock.

## Results and standings

- Result states: `draft → submitted → verified → approved`, with `contested`
  and `corrected` as exception states. Only approved results count in
  official standings.
- Separation of duties is configurable per competition: in Independent Review
  the same user must not submit, verify and approve the same result. Approved
  scores are immutable until the result leaves the approved state.
- Approving, contesting, correcting or resetting a result recomputes linked
  non-frozen standings. Approving a result completes the match; contesting or
  correcting reopens it and withdraws an unplayed follow-up knockout match.
- Every result transition is logged in `federation.match.result.audit`,
  including dispute and correction reasons.
- Standings recomputation can run as an asynchronous, idempotent job
  (`federation.standing.recompute.job`). Pass a correlation ID when invoking
  or replaying it.

## Portal and public site

- `federation.club.representative` maps `res.users` to clubs (and optionally
  teams) for portal ownership and record rules.
- Controllers resolve the represented club/team scope before every write and
  call a model-owned method. Privileged portal writes go through
  `federation.portal.privilege` with an explicit ownership domain. Record
  rules are the enforcement layer; controller checks are defence in depth; ORM
  constraints mirror controller checks so bypassing a controller does not
  widen access. See [ADR-0001](decisions/0001-portal-trust-boundaries.md).
- Every privileged portal call is listed in
  `ci/contracts/portal_sudo_inventory.json` and checked by
  `ci/check_portal_sudo_guard.py`.
- Templates render state labels through helper methods
  (`get_portal_state_label`, `get_portal_result_state_label`,
  `get_public_site_state_label`) from `portal_status_labels.py` and
  `public_status_labels.py`. Template tests forbid raw state rendering.
- Public controllers use `auth="public"` and read only published data:
  enforce `website_published` and the relevant visibility toggle
  (`show_public_results`, `show_public_standings`) before any elevated read.
  Expose only non-sensitive fields. `public_slug` is unique.
- Render public rich text through sanitized field rendering, not raw output.
- To hide a portal or public record, `raise request.not_found()` rather than
  returning it, so fail-closed paths stay quiet in logs.
- Every POST form carries a `csrf_token`.
- The match-day operations board
  (`/sports/match-days/<matchday_id>/operations`) is scoped to the current
  live publication of that game day and is read-only.

Routes are inventoried in the [route inventory](../reference/routes.md).

## Security

- Least privilege: narrow groups, explicit rights in
  `security/ir.model.access.csv`, row ownership through record rules.
- Do not use `sudo()` to bypass authorization for writes. When elevation is
  unavoidable (public reads, scoped portal commands), restrict the fields and
  the domain, validate inputs, and inventory the call.
- Odoo 19 classifies groups through `res.groups.privilege`. Assign groups a
  `privilege_id`; `category_id` belongs on the privilege (for example
  `base.module_category_services`), not on `res.groups`.
- Per-competition role assignments (`federation.competition.role.assignment`)
  scope responsibility inside one competition. They do not grant model access;
  the matching global federation groups are still required.
- Schedule planners have read-only access to `federation.fixture` (needed to
  resolve allocations during preview, submission and publication checks);
  fixture changes stay in the format workflow. Competition administrators have
  read-only access to `federation.competition.edition` for the planning
  workspace; edition changes use the owner commands.
- An official's mobile check-in first validates access to the specific
  assignment, then reads only its linked match under scoped elevation to
  compute the publication/slot signature, and returns only the digest. A
  check-in request is not organiser-confirmed attendance.

## Notifications

`sports_federation_notifications` sends email and activities for workflow
events (registration decisions, publication, participant confirmation,
results, frozen standings, finance confirmations, referee assignments) and
creates manager activities for overdue confirmations and officiating
shortages. Recipients are deduplicated, and delivery failures write a
`failed` notification log instead of rolling back the business action. The
dispatcher methods map to the notification matrix in the
[integration contracts](../reference/integration-contracts.md#notification-matrix).
Participant inbox, preferences and digests are described in the addon
README.

## Reporting

- Operational reports (`federation.report.operational`, standing and finance
  reconciliation views) expose readiness and follow-up queues with
  operator-readable notes.
- `sports_federation_reporting/services/report_schedule_builders.py` owns the
  scheduled-report registry (labels, builders, actions, season scoping).
  `federation.report.schedule` owns cadence, CSV serialization, generated-file
  retention and failure capture. A new scheduled report is one registry entry
  plus tests.
- Large reporting views are SQL views; see
  [ADR-0002](decisions/0002-reporting-sql-views.md) and the explain snapshots in
  `ci/explain_snapshots/`.

## Imports

All import wizards share `federation.import.wizard.mixin`: UTF-8 BOM handling,
comma or semicolon delimiters, mapping guidance, dry-run statistics and
categorized row-level failures. Team, player-club and participant imports
reference clubs, divisions and teams by code; players require `first_name`
and `last_name`. Imports report and skip duplicates instead of overwriting. A
live import is refused when its approval was recorded under another template
version. See the [data import workflow](../workflows/data-import.md).

## Reliability and observability

- `federation.operation.job` is the shared reliability envelope for retryable
  operational work: source ownership, attempts, retry timing, correlation ID,
  stale-worker recovery, terminal operator action and idempotent manual retry.
  Domain execution stays in the owning addon. **Administration > System >
  Operational Jobs** (developer mode) groups jobs by state and source.
- Integration API calls, scheduled reports and notification flows propagate
  correlation IDs (`federation_correlation_id`) for cross-module tracing.
- Use named loggers (`logging.getLogger(__name__)`): INFO for milestones,
  WARNING for recoverable issues, ERROR for failures. Use `message_post` for
  user-visible audit trails.
- Follow the [exception handling policy](exception-handling.md).
- Scheduled jobs that touch many records use
  `sports_federation_base/batch_jobs.py`: `process_each` runs each record in
  its own savepoint (a failing record is logged and skipped, concurrency
  errors are re-raised for a retry) and `for_each_chunk` handles set-based
  work such as retention purges in batches. Both commit between batches when
  running as a scheduled job (`cron_id` in the context), never in tests.
  Suspension start/end, coverage escalation and the five retention purges
  (integration deliveries, member evidence, inbox, notification logs,
  generated report files) use them.

## Performance

- Portal pages share the operation-task projection instead of rebuilding it
  on every view: once per HTTP request, reused by page views (GET) for
  `sports_federation_portal.task_projection_max_age` seconds (system parameter,
  default 30, 0 disables), discarded by any portal change of the same user,
  and skipped while another transaction rebuilds the same clubs
  (transaction-level advisory lock per club). Outside HTTP requests it always
  rebuilds.

- Index `tournament_id`, `stage_id`, `group_id`, `match_date`, `state` and
  other frequently filtered fields.
- Use `ir.cron` for scheduled recomputation; run large batch jobs on a worker
  with suitable `limit_time_cpu`, `limit_time_real` and memory limits.
- Public, portal and reporting hot paths carry `assertQueryCount` budgets; see
  the [testing guide](../development/testing.md#query-count-budgets).

## Upgrades and migrations

- Keep `__manifest__.py` `version`, `depends` and `data` accurate. Bump the
  version for every change that needs a module upgrade.
- Prefer small, idempotent migration scripts under `migrations/<version>/`
  over large one-off changes. Keep `pre_init_hook` and `post_init_hook` logic
  idempotent and tested.
- Odoo does not delete records whose XML IDs disappear from data files; remove
  retired UI records explicitly in a migration.
- Model, view or controller changes must pass `ci/check_migration_review.py`
  and add an entry to the [upgrade notes](../operations/upgrade-notes.md) with
  the dry run and the rollback path.
- The retired `sports_federation_competition_engine` addon must be uninstalled
  through the reviewed procedure in the
  [release runbook](../operations/release-runbook.md#retiring-the-legacy-competition-engine)
  before an upgrade is clean.

## Testing

Every behavioural change ships with a focused test. The test taxonomy,
fixtures, query budgets, tags and suites are described in the
[testing guide](../development/testing.md); the CI pipeline is described in
[CI and quality gates](../development/ci.md).

## Focused workflow implementation files

The existing ORM models remain the public interfaces. Focused same-addon model
extensions separate responsibilities without new models, fields, tables, service
registries or forwarding wrappers:

- Scheduling: `wizards/competition_schedule_wizard.py` owns interactive fields,
  reports, preview/generate/apply commands and persistence. Its sibling
  `competition_schedule_proposal.py` owns proposal calculation, input signatures,
  scope validation, capacity/rest checks and fixture distribution inputs. The
  scheduling algorithms remain in the existing services.
- Planner: `models/planner_projection.py` authorizes the request and assembles
  the response. `planner_readiness.py` owns division rows, issues, step status
  and presentation labels. It does not perform lifecycle transitions.
- Rosters: `models/match_sheet.py` owns fields, eligibility, protected writes and
  submit/approve/lock commands. `match_sheet_gameday.py` owns shared declaration
  scope, source selection and copying/synchronization. It is not an alternate
  eligibility or approval entrypoint; existing lifecycle commands still govern
  when these helpers are called.

Each extension is imported immediately after its original model definition,
using the existing Odoo `_inherit` mechanism. Method names, signatures and
existing decorators are preserved, so downstream overrides still use the same
ORM interface. No cross-addon imports are introduced.

Run `python -m unittest ci.test_workflow_responsibilities` for isolated behavior
and ownership checks. The extraction was also compared against the pre-change
method ASTs, including decorators. This is a refactoring check, not a permanent
source-fingerprint gate that would obstruct future intentional changes.
Installed scheduling, planner and roster tests must still run to validate the
actual Odoo registry and inherited method resolution. Restart Odoo after applying
Python changes; no schema migration is required by this extraction.
