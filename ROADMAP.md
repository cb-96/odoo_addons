# ROADMAP — 2026-05-24 Competition Workspace Cycle

Last updated: 2026-05-25
Owner: Federation Platform Team
Last reviewed: 2026-05-25
Review cadence: Every release
Release train: 2026.11

The previous operating-period roadmap is archived in
`ROADMAP_archive_2026-05-24.md`.

This cycle narrows the roadmap to the Competition Workspace in
`sports_federation_competition_engine`. It is based on the current workspace
models, the central service, the Owl client action, the linked-round shared
gameday implementation, the service regression suite, and the browser smoke
coverage.

---

## Current Assessment

### What Is Working Well

- The workspace already supports a real end-to-end flow: create competition,
  create division, confirm and lock entries, generate match structure, create
  gamedays, generate slots, assign matches, validate, and publish.
- The shared-gameday design is pragmatic. Reusing linked
  `federation.tournament.round` records preserves `federation.match.round_id`
  scope instead of weakening the tournament model.
- Shared-day validation and publication now resolve through the planner root,
  so host and guest-linked rounds see the same blocking, warning, and empty-slot
  results.
- The implementation takes server-side guardrails seriously: access checks,
  assignment validation, publish locks, and force-override restrictions are all
  present.
- Planner writes are now revision-aware and reject stale assignment or publish
  attempts instead of silently accepting last-write-wins behavior.
- Team selection is now search-backed and filterable, and the workspace restores
  section, division, gameday, and planner filters after reloads or navigation.
- Planner collaboration is now visible in the product: operators can see active
  workspace presence, same-gameday edit warnings, grouped validation hints,
  revision summaries, and manager-audited override reasons without leaving the
  planner.
- Large-event planner reads are slimmer than the original implementation:
  planner hydration is lazy, repeated refreshes reuse a smaller payload shape,
  and unscheduled matches can be loaded incrementally instead of forcing one
  eager list.
- Bulk planner throughput has crossed the spreadsheet-replacement threshold:
  bulk assign, bulk unassign, undo, redo, action history, and validated safe
  swaps across occupied slots are all available in the same workflow.
- Rule depth is no longer theoretical: officiating readiness, venue blackout
  and capability constraints, fairness analytics, and stage-aware
  `pool_then_bracket` planning are now part of the delivered workspace.
- The workspace service has been split into orchestration, validation, and
  read-model responsibilities, which makes the codebase easier to extend.
- The workspace has meaningful regression coverage. It is not just a UI demo;
  it already has service tests and browser smoke coverage for the most visible
  paths.

### What Is Lacking Today

- Travel limits, protected-date intake, and exception-handling tools are still
  future work even though the planner now understands officiating, venue, and
  fairness constraints.
- Collaboration remains advisory rather than fully locking: operators get soft
  warnings and presence signals, but the planner does not yet claim hard
  short-lived locks on individual matches or slots.
- The extension seam is now live for validation, payload enrichment, scoring,
  and slot suggestions, but it still needs more federation-specific addon
  implementations over time.

### Strategic Direction

- Keep the Competition Workspace focused on planning, validation, publication,
  and governed change management.
- Keep live match-day execution as a separate future Operations Board rather
  than overloading the planner with real-time incident handling.
- Preserve round-scope integrity and avoid shortcuts that break core tournament
  invariants.
- Grow the workspace by tightening workflow boundaries and extension seams, not
  by growing one giant service file forever.

---

## Status Snapshot — 2026-05-25

Completed in code, tests, and docs:

- Phase 0 through Phase 3 are fully delivered.
- Phase 0 items 1 through 5 hardened shared-day validation, service
  boundaries, workflow transitions, concurrency protection, and regression
  coverage.
- Phase 1 items 6 through 10 delivered search-backed team selection,
  persisted workspace state, planner history and undo/redo, bulk actions and
  safe swaps, plus scalable planner payload loading.
- Phase 2 items 11 through 15 delivered schedule revisions, manager-recorded
  override reasons, collaborative presence indicators, grouped conflict
  guidance, and keyboard-plus-mobile planner parity.
- Phase 3 items 16 through 20 delivered officiating-aware validation, venue
  blackout and capability rules, fairness analytics, stage-aware
  `pool_then_bracket` planning, and extension-backed slot suggestions.

Validation snapshot:

- Focused direct `ci-odoo` validation passed on 2026-05-25 for
  `sports_federation_competition_engine`, `sports_federation_officiating`, and
  `sports_federation_venues`, with zero failures and zero errors on the Phase 3
  workspace surface.
- Final verification reruns on 2026-05-25 included 119 officiating tests and 17
  venues tests, with the venues suite now executing its two post-install
  workspace venue-constraint regressions after the CI tagging fix.

---

## Phase 0 — Weeks 1–2: Correctness, Shared-Day Safety, and Service Boundaries

Module: `sports_federation_competition_engine`

### 1. Shared-gameday validation must always resolve through the planner root — Delivered 2026-05-25

Why:
Shared days currently work, but validation paths are still too dependent on the
specific round used to enter the method.

Deliver:
- Normalize `validate_gameday()` and all publication checks through the planner
  root round.
- Make empty-slot, warning, and blocking issue reporting consistent for host and
  guest-linked rounds.
- Add explicit regression coverage for validating and publishing guest rounds.

### 2. Split the workspace service by responsibility — Delivered 2026-05-25

Why:
One service currently owns orchestration, validation, serialization, and write
commands. That will slow down every future change.

Deliver:
- Extract planner validation helpers into a dedicated validation service.
- Extract payload serialization into dedicated read-model helpers.
- Keep the top-level workspace service as the thin orchestration entrypoint.

### 3. Introduce explicit workflow transition methods — Delivered 2026-05-25

Why:
The current implementation mutates `workspace_state` and `planner_state`
directly in several flows. That is workable now, but it weakens auditability.

Deliver:
- Replace ad-hoc state writes with named transition helpers.
- Centralize allowed transitions for divisions and gamedays.
- Log transition reason and actor where state changes affect publication.

### 4. Add concurrency protection to planner writes — Delivered 2026-05-25

Why:
Two planners can currently race on assignment or publication in a way that is
not modeled explicitly.

Deliver:
- Add optimistic concurrency tokens or equivalent stale-write checks.
- Reject outdated slot assignments with a clear retry message.
- Cover concurrent planner write scenarios in tests.

### 5. Expand regression coverage around the critical workflow edges — Delivered 2026-05-25

Why:
The existing tests are good, but the most fragile behavior will now be shared
days, publish transitions, overrides, and stale state.

Deliver:
- Add tests for host vs guest shared-day validation and publication.
- Add tests for forced warning-only assignment and its permissions.
- Add tests for state rollback after unassign and republish paths.

---

## Phase 1 — Weeks 3–5: Planner UX, Throughput, and Scale

Module: `sports_federation_competition_engine`

### 6. Replace eager team loading with search-backed selection — Delivered 2026-05-25

Why:
The planner currently loads teams with a fixed `search_read(..., limit=200)`.
That is not federation-scale.

Deliver:
- Replace the eager team dropdown with search/autocomplete RPCs.
- Support server-side filtering by division and club.
- Remove the hard-coded 200-team ceiling from the workspace flow.

### 7. Persist workspace UI state across refresh and navigation — Delivered 2026-05-25

Why:
Operators should not lose selected division, gameday, section, and filters on
every reload.

Deliver:
- Persist current section, division, gameday, and planner filters.
- Restore planner context when returning from form views or a hard refresh.
- Clear persisted state safely when the underlying competition changes.

### 8. Add undo, redo, and planner action history — Delivered 2026-05-25

Why:
The planner needs reversible operations if it is to replace spreadsheet-based
planning confidently.

Deliver:
- Record assignment, unassignment, and move actions as planner operations.
- Add quick undo and redo for recent planner actions.
- Expose a user-readable planner action history panel.

### 9. Add bulk planner actions — Delivered 2026-05-25

Why:
Single-card assignment is correct but slow for large rounds and tournament days.

Deliver:
- Bulk unassign selected matches.
- Bulk assign by round or by filtered set.
- Add safe swap and move operations across slots and courts.

Delivered so far:
- Bulk assign uses the current filtered selected unscheduled set and fills the
  next available slots on the active gameday.
- Bulk unassign removes selected scheduled matches from the active gameday.
- Single-match move across slots and courts remains available through drag and
  drop or mobile assignment.
- Dropping an already scheduled match onto another occupied slot now performs a
  validated safe swap when both matches can legally trade places.

### 10. Make large-event planner payloads scalable — Delivered 2026-05-25

Why:
The current payload shape is fine for modest tournaments, but it will become
heavy when slot grids, teams, and mixed divisions grow.

Deliver:
- Introduce lazy planner payload loading where possible.
- Virtualize or paginate unscheduled match lists.
- Reduce redundant payload fields in repeated planner refreshes.

---

## Phase 2 — Weeks 6–8: Governance, Collaboration, and Publish Control

Module: `sports_federation_competition_engine`

### 11. Introduce schedule revisions instead of one mutable published state — Delivered 2026-05-25

Why:
Published schedules need governed changes, not just lock-or-unlock semantics.

Deliver:
- Add schedule revision records or equivalent version tracking.
- Allow draft revisions after publication without overwriting the live plan
  immediately.
- Keep a clear distinction between draft, current live, and superseded plans.

Delivered so far:
- `federation.competition.schedule.revision` persists draft, live, and
  superseded planner snapshots.
- Gamedays now keep explicit live and draft revision links and expose revision
  summaries in the planner and publish views.

### 12. Require manager override reasons — Delivered 2026-05-25

Why:
Manager-only force assignment and publication overrides should be explainable to
operators and auditors.

Deliver:
- Require a reason when forcing warning-only assignments.
- Require a reason when republishing or bypassing planner warnings.
- Store those reasons on the relevant planner action or revision record.

Delivered so far:
- Forced warning-only assignment requires a manager override reason and stores
  it on the planner operation history.
- Republishing or publishing with warnings records the manager reason on the
  resulting schedule revision.

### 13. Add collaborative presence and soft locks — Delivered 2026-05-25

Why:
The workspace is moving from a single-operator tool toward a multi-operator
planning surface.

Deliver:
- Show who else is currently in the same competition workspace.
- Add soft locks or edit indicators for active gameday planning.
- Warn before conflicting edits rather than failing silently.

Delivered so far:
- `federation.competition.workspace.presence` tracks active operators and their
  current section or gameday context.
- Planner and publish views now show active workspace users and same-gameday
  warnings before overlapping edits.

### 14. Make conflict output explainable and operator-friendly — Delivered 2026-05-25

Why:
Current validation tells operators what is wrong; the next step is to help them
fix it faster.

Deliver:
- Group planner conflicts by blocking type and severity.
- Add actionable resolution hints to each conflict payload.
- Highlight the affected slot, match, or team in the planner UI.

Delivered so far:
- Validation payloads now group blocking and warning issues and include
  operator-facing resolution hints.
- The planner highlights the affected slots and matches while grouped conflicts
  remain visible in both planner review and publish review panels.

### 15. Improve keyboard, accessibility, and mobile parity — Delivered 2026-05-25

Why:
The workspace is already mobile-aware, but it still behaves primarily like a
desktop planner.

Deliver:
- Make all planner actions keyboard reachable.
- Improve focus management, button semantics, and screen-reader output.
- Close the remaining gaps between drag-and-drop and tap-to-assign flows.

Delivered so far:
- Empty-slot assign buttons now let keyboard users select one match and assign
  it without drag-and-drop.
- Validation panels use grouped live updates, cards expose focus-visible state,
  and assignment dialogs keep explicit dialog semantics.
- The planner now keeps a consistent desktop, mobile, and tap-to-assign path
  for the common assignment flow.

---

## Phase 3 — Weeks 9–12: Rule Depth, Format Coverage, and Extension Seams

Module: `sports_federation_competition_engine`

### 16. Make officiating availability part of planner validation — Delivered 2026-05-25

Why:
Missing referees are currently only a warning. Eventually the workspace must be
able to schedule with officiating feasibility in mind.

Deliver:
- Add optional officiating-aware validation rules.
- Flag unavailable or double-booked officials before publication.
- Expose officiating readiness in planner and publish summaries.

Delivered so far:
- The officiating addon now extends workspace validation and payloads so
  double-booked referee assignments block planning and publication while
  uncovered availability remains visible as a warning.
- Match-assignment readiness and publish summaries now include officiating
  readiness details without forcing the core engine to hard-code refereeing
  rules.

### 17. Model venue blackout, capability, and maintenance constraints — Delivered 2026-05-25

Why:
Courts are not interchangeable in real operations.

Deliver:
- Add venue blackout windows and maintenance closures.
- Support court capability tags or sport-specific restrictions.
- Block or warn on assignments that ignore those constraints.

Delivered so far:
- `sports_federation_venues` now models blackout windows and playing-area
  capabilities and lets divisions require specific court capabilities.
- Workspace validation blocks blackout, maintenance, and capability mismatch
  assignments and exposes venue-readiness summaries in match, gameday,
  division, and overview payloads.

### 18. Add fairness and balance analytics to the planner model — Delivered 2026-05-25

Why:
The planner should optimize more than simple slot occupancy.

Deliver:
- Track rest fairness, court fairness, and timeslot fairness by team.
- Expose these metrics in division and competition overview payloads.
- Provide warning thresholds or scoring hooks for future automation.

Delivered so far:
- Division, planner, and competition overview payloads now carry fairness
  summaries with tracked-team counts, per-team metrics, and threshold-aware
  score components.
- The planner UI now shows fairness metrics directly and reuses the same
  scoring structure for future automation.

### 19. Implement `pool_then_bracket` and broader multi-stage planning — Delivered 2026-05-25

Why:
The current workspace stops at round robin, double round robin, knockout, and
manual planning.

Deliver:
- Implement pool-stage generation with bracket progression.
- Support stage-aware gameday planning and stage-specific previews.
- Add workflow documentation and regression tests for the new path.

Delivered so far:
- The workspace now generates balanced pool stages plus seeded knockout stages
  for `pool_then_bracket` divisions.
- Gamedays, previews, planner filters, and match cards are stage-aware and let
  operators target pool or knockout work explicitly.

### 20. Add extension hooks for federation-specific planning rules — Delivered 2026-05-25

Why:
The workspace needs to become more configurable without turning into a giant set
of hard-coded special cases.

Deliver:
- Define extension hooks for validation, scoring, and planner suggestion logic.
- Separate stable base payloads from rule-specific enrichments.
- Document the extension points for future addon-level customization.

Delivered so far:
- Workspace extensions now register by model prefix and can enrich validation,
  payloads, and scoring without modifying the base planner service.
- The planner exposes ranked slot suggestions backed by the shared scoring hook
  path, so addon-specific rules can now influence future placement guidance.

---

## Potential New Features — Next-Layer Product Differentiators

These features are intentionally not committed to the current 12-week delivery
sequence. They are candidates once the delivered planner baseline needs a new
round of automation, decision support, and operator differentiation.

### 1. Explainable auto-scheduler

Generate a draft schedule automatically and explain why each match landed in a
given slot, court, or gameday.

### 2. Scenario sandbox and branch planning

Let planners create multiple schedule variants, compare them side by side, and
promote one branch into the working revision.

### 3. Fairness dashboard

Show home-away balance, rest balance, court balance, and early/late slot
distribution by division and by team.

### 4. Matchday incident mode

Handle late starts, venue outages, and court closures with controlled, guided
reflow tools distinct from normal planning mode.

### 5. Team availability and blackout intake

Collect team availability, protected dates, and blackout windows before the
planner starts assigning matches.

### 6. Travel-aware scheduling

Score or optimize schedules based on travel burden across clubs, divisions, and
same-day journeys.

### 7. Broadcast and featured-court planning

Reserve certain courts or timeslots for broadcast, streaming, or marquee match
placement and surface those constraints in the planner.

### 8. Schedule change notification center

Track who has been notified of schedule changes, who has acknowledged them, and
which changes still need operator follow-up.

### 9. Downstream qualification and progression preview

Show how schedule changes affect later-stage readiness, playoff qualification
timelines, or linked bracket progression windows.

### 10. Schedule diff and release-note viewer

Give operators a human-readable summary of what changed between two schedule
revisions so they can publish changes clearly.

---

## Recommended Delivery Order

If time pressure forces prioritization, deliver the roadmap in this order:

1. Item 1 — planner-root validation and publication normalization.
2. Item 6 — search-backed team loading and removal of the fixed team cap.
3. Item 8 — undo/redo and planner history.
4. Item 11 — revisioned publication model.
5. Item 19 — `pool_then_bracket` and multi-stage workflow support.

This sequence protects correctness first, then scale, then operator confidence,
then governance, and finally scope expansion.
