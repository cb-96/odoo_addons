Sports Federation Competition Engine
====================================

Schedule generation wizards for round-robin and knockout formats. Given a
tournament with participants, the engine creates matches, assigns venues, and
sets kickoff times automatically. It also provides the backend Competition
Workspace for guided league planning, slot-based scheduling, and controlled
publication.

Purpose
-------

Automates fixture creation. Instead of manually entering dozens or hundreds of
matches, federation staff run a wizard that generates a complete schedule for
the chosen format, seeding mode, and time intervals. For staged operational
planning, the Competition Workspace guides administrators from competition
creation through team confirmation, round generation, gameday setup, visual slot
planning, validation, and publication. In the current backend navigation,
`Planning Workspace` is the primary scheduling entry point and the direct
round-robin or knockout buttons on tournament forms are explicitly labeled as
advanced wizard paths.

Dependencies
------------

Depends on sports_federation_tournament for tournaments, stages, groups,
participants, and matches. Depends on sports_federation_venues for venue and
playing-area scheduling and on web assets for the backend Owl client action.

Competition Workspace
---------------------

The Planning Workspace is a backend client action anchored on
`federation.competition.edition`, `federation.tournament`, and
`federation.tournament.round`.

Operators reach it from the `Planning` menu bucket or from the `Open Planning
Workspace` buttons on competition editions and divisions.

In workspace and operator copy, use `season competition` for the season-specific
`federation.competition.edition` record that holds the divisions, schedule
planning, and publication status for one competition season. Older notes may
still refer to this record as the `competition shell`, but that term is
deprecated outside compatibility discussions.

Guided flow
~~~~~~~~~~~~

1. Create the season competition or open an existing edition.
  If the selected competition template already has an edition for that season,
  the workspace reopens the existing competition instead of creating a
  duplicate season record.
2. Create a division and choose its planning format.
3. Add and confirm team entries.
  The team picker now uses server-side search with an optional club filter so
  large catalogs stay usable on mobile and desktop.
4. Lock the participant list.
5. Generate unscheduled matches for single round robin, double round robin,
  knockout, or pool-then-bracket planning.
   Pool-then-bracket creates balanced pool play first and a linked knockout
   stage for the configured qualifiers per pool.
6. Create gamedays.
  Multi-stage divisions can target a specific stage so pool work and knockout
  work stay separate in the planner.
  A gameday can now include one or more additional divisions from the same
  competition when they share the same physical match day.
7. Generate court and timeslot slots for a gameday.
8. Open the visual planner and assign matches to slots.
  The planner now supports selected-match bulk assign and bulk unassign,
  a dedicated unassign-all action with a confirmation prompt,
  quick undo and redo of recent planner actions, and a visible action history
  panel for the active gameday. Desktop users can still drag and drop, while
  keyboard and mobile users can select one match and assign it directly into an
  empty slot. Dragging one already scheduled match onto another occupied slot
  now performs a validated safe swap when both matches can trade places.
  Planner UI actions are grouped by intent (selection, scheduling, destructive),
  report live selection and busy-state feedback, and support `Esc` to quickly
  clear planner selection during high-volume scheduling edits.
  Stage labels stay visible on previews, gamedays, and match cards, the
  planner shows a fairness summary for the active division, and selecting one
  unscheduled match surfaces ranked slot suggestions backed by the current
  planner rules. Division planning fairness rules (minimum rest and maximum
  consecutive short-rest matches per team) can be adjusted directly in the
  workspace after creation.
9. Refresh or reopen the workspace without losing the current section,
  division, gameday, or planner filters.
10. Review blocking conflicts and warnings.
   Validation now groups blocking and warning issues by type, includes
   operator-facing hints, and highlights affected slots or matches in the
   planner. When the officiating and venues addons are installed, the same
   review step also shows officiating readiness and venue-readiness issues.
11. Publish a gameday or the full competition schedule.
   Publish review now shows current draft and live revision status for each
   gameday, and managers must record a reason before forcing warnings or
   replacing a live schedule.
12. Maintain schedule changes with server-side guardrails.
   The workspace tracks live, draft, and superseded schedule revisions and
   shows active operator presence so same-gameday edits are visible before a
   stale write reaches the server.

The workspace shell scrolls vertically inside the backend action, while the
planner grid keeps its own horizontal overflow handling. This keeps long
timeslot lists reachable without clipping the planner to a single viewport.

Key models and services
~~~~~~~~~~~~~~~~~~~~~~~

- `federation.match.slot` stores the operational slot grid used by the visual
  planner. A slot belongs to a gameday and may hold at most one match.
- `federation.competition.schedule.revision` stores draft, live, and
  superseded schedule snapshots so publication is revisioned instead of being a
  single mutable state flip.
- `federation.competition.workspace.presence` stores recent operator heartbeat
  data for collaboration warnings and same-gameday edit indicators.
- `federation.competition.planner.operation` stores recent planner actions so
  assignment, move, unassignment, undo, and redo flows can be reviewed and
  reversed without leaving the workspace.
- `federation.competition.workspace.service` owns competition creation,
  division creation, team-entry confirmation, format-aware schedule generation,
  gameday creation, slot generation, assignment validation, bulk planner
  actions, planner history, revisioned publication, collaboration heartbeat,
  and payload building for the Owl action.
- `federation.competition.workspace.validation.service` centralizes planner
  assignment, gameday, and competition validation so the write service and the
  read-model payload stay aligned.
- `federation.competition.workspace.read.model.service` builds the workspace
  payloads and can skip planner hydration until the UI explicitly opens a
  gameday.
- `federation.competition.workspace.extension.*` models are optional addon
  extension points that can add validation issues, payload enrichments, score
  components, and slot-suggestion logic without hard-coding every federation
  rule into the core engine.
- `federation.tournament.workspace_state` tracks the guided planning lifecycle
  for a division without replacing the tournament lifecycle in
  `sports_federation_tournament`.
- `federation.tournament.round.planner_state` tracks operational gameday
  planning and publication state.
- `federation.tournament.round.planner_revision` increments whenever slot
  assignments, slot grids, or publication state change so stale tabs are forced
  to refresh before they overwrite newer planner data.
- Shared match days reuse `federation.tournament.round` as a linked set of
  per-division gamedays. One round owns the physical slot grid, while guest
  divisions keep their own legal `round_id` records so match scope remains
  inside the correct tournament and stage.

Shared gamedays
~~~~~~~~~~~~~~~

- Create a shared gameday from one division and add the other participating
  divisions in the same form.
- The workspace creates one slot-owning root gameday plus one linked gameday
  per extra division.
- The visual planner shows one combined slot grid and can schedule matches from
  all participating divisions in the same day.
- Validation and publication always resolve through the slot-owning root
  gameday so host and guest divisions see the same empty-slot, warning, and
  blocking results before a manager publishes the day.
- Match cards show their division label and the planner filters can narrow the
  unscheduled list back down to one division when needed.
- The planner selection toolbar can bulk-assign the current filtered
  unscheduled set into the next open slots or bulk-unassign selected scheduled
  matches from the active shared day.
- A guest-division match keeps its own division round even when it is assigned
  into a shared physical slot grid.

Roles and safeguards
~~~~~~~~~~~~~~~~~~~~

- `Competition Planner` can open the workspace, prepare divisions, generate
  rounds and slots, and plan assignments.
- Federation managers keep full access and are the only users allowed to
  create competitions from the workspace menu, publish schedules, or force
  warning-only assignments.
- Blocking validations stop unscheduled reuse of an occupied slot and prevent
  any move that would create a team overlap across simultaneous matches.
- When both matches are already assigned on the same planner root, the planner
  can perform a validated safe swap across occupied slots instead of forcing an
  unassign-first workflow.
- Short-rest situations are warnings, not blocking errors, and require a
  manager to force the assignment when accepted operationally.
- Consecutive short-rest streaks are also validated using the division policy.
  The planner warns when a placement would exceed
  `max_consecutive_matches_per_team`.
- Forced warning-only assignments and republishing a live schedule require a
  manager override reason that is stored on the planner operation or schedule
  revision.
- Officiating readiness checks are deferred until the gameday moves beyond
  planning (`published` and later) so planners can complete slot allocation
  before final referee staffing decisions.
- Planner writes carry the current `planner_revision`; stale sessions must
  reload before they can generate slots, assign matches, unassign matches, or
  publish a gameday.
- The planner records assignment, move, and unassignment actions, exposes the
  recent action history in the UI, and supports quick undo and redo on the
  active gameday. A new planner write clears the redo branch so history stays
  linear and auditable.
- Planner presence heartbeats surface who else is active in the same workspace
  and warn when another operator is editing the same gameday.
- Validation payloads now include grouped blocking and warning sections,
  actionable hints, and focus metadata that the UI uses to highlight affected
  slots or matches.
- Validation issue dedupe now keys on code plus match, slot, and team context
  so distinct slot-specific conflicts stay visible while exact duplicates are
  collapsed.
- Write-path planner validation merges now use the same context-aware issue
  signature so forced or batched operations do not collapse distinct conflicts
  that happen on different slots.
- Extension-provided validation issues are now contract-normalized before they
  enter planner validation: malformed issue payloads are ignored, identifier
  fields are coerced, and `team_ids` are normalized to integer lists.
- Extension payload enrichments are now contract-normalized: non-dict payload
  updates are ignored so malformed extensions cannot break workspace payload
  assembly.
- Extension slot-score components are now contract-normalized: components must
  be dicts with a key, score values are coerced and clamped, and malformed
  component shapes are skipped.
- Extension hook execution is now fault-isolated: exceptions inside a single
  extension hook are caught, logged, and ignored so other hooks can continue.
  Validation hook failures emit a structured `extension_hook_failed` warning
  payload with hook and extension model metadata.
- Extension outputs now support schema-versioned contracts (`schema_version: 1`)
  for payload enrichments (`payload`), validation issues (`issues`), and slot
  score components (`components`) while keeping legacy shapes backward
  compatible.
- Planner write endpoints now accept optional idempotency keys on assignment and
  unassignment paths. Replayed keys return a deterministic success payload with
  `replayed=true` and do not create duplicate planner operation rows.
- Planner write endpoints now return a standardized conflict envelope for stale
  or invalid revision tokens, including `code`, `operation`,
  `expected_planner_revision`, and `current_planner_revision` metadata.
- Validation issue severity now follows a centralized policy (`blocking`,
  `warning`, alias support like `error`/`info`) so core and extension issues
  are grouped consistently.
- Planner read-model consistency payloads now expose source metadata
  (`source_planner_root_id`, `source_planner_root_revision`) and
  `normalization_warnings` when filter or expected-revision inputs are malformed.
- Workspace ACL regressions now include a compact matrix covering planner,
  manager, and regular-user behavior across read, assign, and publish
  entrypoints.
- Concurrency regressions now include deterministic interleaving checks for
  stale revision handling on bulk-unassign and undo planner operations.
- Planner stale/invalid revision conflicts and extension hook failures now emit
  correlation IDs for faster support triage and log cross-referencing.
- Destructive planner and publication actions now use an in-workspace
  confirmation dialog instead of browser-native confirms, keeping operator
  context and keyboard focus inside the client action.
- Dedicated contract tags now exist for competition workspace reliability slices:
  `sf_ws_read_model_contract`, `sf_ws_write_guard_contract`,
  `sf_ws_extension_contract`, `sf_ws_concurrency_contract`, and
  `sf_ws_acl_contract` (runnable via `ci/run_tests.sh --contract-suite ...`).
- Frontend helper regressions for planner busy-state and keyboard-clear behavior
  are now covered by `static/tests/competition_workspace_ui_tests.js` and
  loaded through `web.qunit_suite_tests`.
- Planner unscheduled match lists are now sliced by the active gameday sequence
  (per linked division round), instead of showing every unscheduled match in the
  stage.
- Gameday creation now supports explicit round targeting via `round_number`.
  Shared gamedays can also provide `shared_round_numbers` to map each shared
  division to its own round number while still sharing one planner root grid.
  Shared gamedays can additionally provide `shared_stage_ids` so each shared
  division targets its own stage on that same planner root.
  In the Competition Workspace UI, this is selected through the existing
  Round options (not a separate round model).
- Planner unscheduled slices now stay strict to each linked gameday round number
  (no stage-wide fallback when a selected round has no unscheduled matches).
- Auto-scheduling is available through `auto_schedule_gameday` with a full
  fairness-driven rollout:
  - deterministic base fill from the active gameday unscheduled slice;
  - weighted global fairness objective (rest variance, home/away imbalance,
    and timeslot variance);
  - warning-aware ranking that prefers warning-free placements while still
    allowing warning-only placements;
  - configurable solver modes (`heuristic`, `hybrid`, `advanced`) and repair
    controls (`enable_repair`, `repair_step_limit`, and fairness `weights`);
  - bounded augmentation search (`enable_augmentation`,
    `augmentation_step_limit`) that can re-route already scheduled matches into
    open slots to unlock otherwise stuck unscheduled matches before giving up;
  - bounded post-fill repair pass (swap in `hybrid`; swap + move in `advanced`)
    to improve global fairness without breaking hard constraints;
  - expanded diagnostics: per-assignment objective penalties/components,
    `fairness_before`, `fairness_after`, `fairness_delta`, `augmentation`, `repair`, and
    `auto_schedule_config` payloads, plus `skipped_reason_summary`.
- Planner read-model inputs now tolerate malformed numeric filters
  (`division_id`, `round_number`, `team_id`) and malformed `gameday_id`
  selectors by ignoring invalid values instead of raising server errors.
- Planner payloads now expose a `consistency` object with
  `current_planner_revision`, optional `expected_planner_revision`, and
  `is_stale` / `invalid_expected_planner_revision` flags so clients can detect
  stale read-model snapshots before issuing write operations.
- Write operations now normalize expected planner revision tokens consistently:
  blank tokens are treated as missing, numeric tokens are coerced, and invalid
  tokens are rejected with a clear validation error.
- Any change that touches a validated or published day reopens the linked
  gameday back to `planned` and the affected divisions back to `planning`
  before another publication pass.
- Published gamedays lock routine schedule edits for planners.

Supported workspace generation modes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- `single_round_robin` generates one full cycle of unscheduled pairings.
- `double_round_robin` generates home-and-away pairings while keeping later
  gameday assignment separate.
- `knockout` generates a seeded single-elimination bracket with linked future
  rounds and byes when needed.
- `manual` leaves match creation outside the guided generator.
- `pool_then_bracket` generates balanced pool rounds first, then wires a staged
  knockout bracket for the configured qualifiers from each pool.

Wizards
-------

Round-robin wizard
~~~~~~~~~~~~~~~~~~

Generates a full round-robin schedule where every participant plays every other
participant once, or twice in a double round-robin.

Main fields:

- `tournament_id`
- `stage_id`
- `group_id`
- `participant_ids`
- `use_all_participants`
- `round_type`
- `start_datetime`
- `interval_hours`
- `venue`
- `overwrite`
- computed `summary` preview

Algorithm details: the wizard uses the circle method with deterministic
ordering, ensures no team plays itself, schedules each pairing once or twice,
and inserts bye rounds automatically when participant counts are odd.

Knockout wizard
~~~~~~~~~~~~~~~

Generates a single-elimination bracket.

Main fields:

- `tournament_id`
- `stage_id`
- `participant_source`
- `participant_ids`
- `source_stage_id`
- `seeding`
- `bracket_size`
- `start_datetime`
- `interval_hours`
- `venue`
- `overwrite`
- computed `summary` preview

Algorithm details: the wizard builds seeded single-elimination brackets,
inserts byes when the participant count is not a power of two, and keeps top
seeds separated when power-of-two placement is selected.

Key Behaviours
--------------

- Overwrite protection keeps existing matches unless overwrite is explicitly
  checked.
- Tournament state checks require the tournament to be open or in_progress
  before either wizard generates fixtures.
- Rule-set requirements force an effective rule set on the tournament or linked
  competition before matches are created.
- Preview-first UI shows a computed summary before confirmation, and the
  knockout overwrite warning uses an explicit alert role so Odoo 19 view
  validation stays clean.
- At least 2 teams are required before schedule generation can proceed.
- Tournament templates let `federation.tournament.template.action_apply()`
  scaffold stages, groups, and progression rules with regression coverage.
- Stage progression clears any stale source-group assignment when advancing an
  existing participant into a target stage that has no explicit target group.
- Wizard launch buttons are added to the tournament form view.

Validation and safeguards
-------------------------

- Round-robin generation rejects stages or groups that do not belong to the
  selected tournament.
- Knockout generation validates source-stage ownership before it seeds a
  bracket from prior standings.
- Both wizards require an effective rule set from the tournament or linked
  competition before persisting matches.
- Preview summaries are intended to be reviewed before confirmation, and
  overwrite mode warns that existing matches in the selected scope will be
  replaced.
- Workspace publication requires all blocking validation issues to be cleared
  and restricts warning-only overrides to federation managers.
- Slot generation enforces one match per slot and one slot start time per
  playing area and gameday.
