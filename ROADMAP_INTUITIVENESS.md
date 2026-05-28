# ROADMAP_INTUITIVENESS — 2026-05-25 Repo-Wide Product Clarity Cycle

Last updated: 2026-05-25
Owner: Federation Platform Team
Last reviewed: 2026-05-25
Review cadence: Every release
Planning horizon: 2-3 release cycles

This roadmap is separate from feature-delivery roadmaps such as
`ROADMAP.md`. Its only purpose is to improve how intuitive the product feels
to federation administrators, competition planners, club representatives,
match officials, and public visitors.

It is based on a repo-wide pass across the top-level docs, workflow specs,
representative module READMEs, backend menu structure, portal surfaces,
public-site flows, and the Competition Workspace client action.

---

## What Intuitiveness Means Here

In this codebase, intuitiveness means:

- the same concept uses the same name across backend, portal, public site, and docs
- each major task has one obvious entry point and one obvious next action
- prerequisites are visible where work happens instead of being hidden in other modules
- user-facing labels are human and role-appropriate rather than model- or state-oriented
- cross-module handoffs feel like one product journey instead of several addon boundaries

This roadmap does **not** treat raw feature depth, performance, security,
maintainability, or CI quality as intuition work unless they directly affect
how understandable the product feels.

---

## Current Assessment

### What Already Points In The Right Direction

- The repo has strong workflow intent. The main federation journeys are already
  described in `_workflows/`, which gives the product a real operational spine.
- The Competition Workspace shows good intuition patterns in places: grouped
  validation, next-step framing, revision summaries, and role-aware actions.
- The rosters area is a good model for future work because readiness and
  blockers are already surfaced close to the point of action.
- Public publication is already slug-first and tournament-first in principle,
  even though some legacy language still leaks through.

### Main Intuition Gaps

- Core nouns are unstable: competition, competition template, competition
  edition, tournament, division, competition shell, round, and gameday are not
  yet a clean, durable mental model.
- Backend navigation is mostly module-first rather than journey-first.
- Scheduling and match-day work still expose overlapping primary surfaces.
- Cross-module prerequisites are real but often invisible until the operator
  hits a blocker.
- Portal task entry points compete with one another instead of collapsing into
  one clear work queue.
- Public pages still leak technical or transitional language in places.
- Publication and readiness rules are documented, but not yet expressed as one
  obvious release model from the UI itself.

---

## Evidence Anchors

This roadmap is primarily grounded in the following surfaces:

- `README.md`
- `CONTEXT.md`
- `TECHNICAL_NOTE.md`
- `_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md`
- `_workflows/WORKFLOW_MATCH_DAY_OPERATIONS.md`
- `_workflows/WORKFLOW_SEASON_REGISTRATION.md`
- `_workflows/WORKFLOW_PUBLIC_PUBLICATION.md`
- `sports_federation_competition_engine/README.md`
- `sports_federation_portal/README.md`
- `sports_federation_public_site/README.md`
- representative backend menu/view files in `sports_federation_base`,
  `sports_federation_tournament`, `sports_federation_portal`,
  `sports_federation_officiating`, `sports_federation_public_site`, and
  `sports_federation_competition_engine`

---

## Strategic Direction

- Make the product feel like one federation operating system, not a set of
  separately understandable addons.
- Prefer stable mental models over historically accurate internal naming.
- Prefer one primary path per high-frequency task, with alternate flows clearly
  marked as advanced, legacy, or specialist.
- Move prerequisites, blockers, and next actions into the surfaces where users
  actually work.
- Make backend, portal, and public language intentionally different only when
  the audience needs it, not because modules evolved separately.

---

## Phase 0 — Canonical Language And Mental Model

### Goal

Give operators and end users a stable vocabulary so the product stops teaching
different names for the same thing.

### Why This Comes First

Without a canonical noun set, every later navigation or copy improvement will
still feel inconsistent.

### Deliver

- Define the official terms for:
  - competition template
  - season competition
  - division
  - tournament
  - stage
  - round
  - gameday
  - workspace
  - registration
  - participant
  - publication
- Create a deprecated-term map for older language such as `competition shell`
  and any legacy competition-first copy that should now be tournament-first.
- Standardize where technical model names may appear and where they must not.
- Align workflow docs, README files, menu labels, action names, and empty-state
  copy with the canonical noun set.

### Priority Surfaces

- `sports_federation_tournament`
- `sports_federation_competition_engine`
- `sports_federation_portal`
- `sports_federation_public_site`
- top-level docs and workflow specs

### Exit Criteria

- The same business object is not described by multiple primary labels in user
  copy.
- A new operator can explain the difference between season competition,
  division, tournament, round, and gameday without reading code.

### Status (2026-05-27)

- Phase 0 slice 1 is implemented in the current baseline.
- `TECHNICAL_NOTE.md` now carries the canonical noun map and authoritative
  state-reference summary used by workflow docs.
- Workflow and README cleanup now align on these core rules:
  - use `season competition` instead of `competition shell` in operator copy
  - contested or corrected results leave official standings immediately until
    they are approved again
  - standings use `draft`, `computed`, and `frozen`, with public visibility
    handled separately through `website_published`
  - player licenses use `cancelled` in operator-facing language
  - `/tournaments/...` is the canonical public route family, while
    `/competitions...` remains compatibility-only

---

## Phase 1 — Journey-First Navigation And Entry Points

### Goal

Reorganize discovery so users start from the job they need to do, not the addon
that happens to own the records.

### Why This Matters

The backend and portal currently expect users to understand module boundaries.
That is efficient for maintainers, but not intuitive for operators.

### Deliver

- Redesign backend navigation around the main journeys:
  - Setup
  - Planning
  - Match Day
  - Publication
  - Administration
- Reduce duplicated top-level paths that lead to adjacent work queues.
- Define one primary entry point for scheduling work and visibly demote
  secondary paths.
- Define one primary entry point for club operational work in the portal.
- Make advanced or specialist paths clearly labeled rather than equal-weight
  peers.

### Priority Surfaces

- `sports_federation_base/views/menu_items.xml`
- `sports_federation_tournament/views/menu_items.xml`
- `sports_federation_portal/views/menu_items.xml`
- `sports_federation_officiating/views/menu_items.xml`
- portal home and tournament workspace templates

### Exit Criteria

- Each major actor has one obvious starting point for their daily work.
- Navigation labels describe the task, not just the model family.

### Status (2026-05-25)

- Implemented in the current baseline.
- Backend federation navigation now groups work under Setup, Planning, Match Day,
  Publication, and Administration instead of leaving the main root as a flat
  addon list.
- Planning Workspace is now the primary backend scheduling entry point, while
  classic generation buttons are explicitly labeled as advanced wizard paths.
- Club representatives now see Club Operations Workspace as the primary portal
  start, and direct match-day queues are framed as secondary or advanced paths.

---

## Phase 2 — Guided Setup And Cross-Module Handoffs

### Goal

Make setup and operational prerequisites visible at the point of work instead of
forcing users to discover them only after a validation failure.

### Why This Matters

The federation workflows are valid, but many gates are hidden across season,
registration, roster, scheduling, result, standings, and publication modules.

### Deliver

- Add first-run and first-use guidance for season setup, competition setup,
  tournament setup, and publication setup.
- Introduce readiness or next-step panels where one module depends on another.
- Standardize empty states so they explain what must exist first.
- Surface cross-module blockers early for these handoffs:
  - season registration -> team readiness
  - tournament registration -> participant confirmation
  - participant confirmation -> roster readiness
  - result approval -> standings publication
  - tournament publication -> standings visibility
- Add contextual links from blockers to the next valid place to act.

### Priority Surfaces

- `sports_federation_base`
- `sports_federation_tournament`
- `sports_federation_rosters`
- `sports_federation_result_control`
- `sports_federation_standings`
- `sports_federation_public_site`

### Exit Criteria

- Users do not need workflow docs to understand why a step is blocked.
- The system names the next valid action and where to perform it.

### Status (2026-05-25)

- Implemented in the current baseline.
- Season, competition, edition, and tournament forms now surface next-step
  banners and richer empty-state help so operators know what record to create
  or review next.
- Confirmed season registrations now open scoped roster work directly, and
  tournament participant forms surface roster-deadline readiness with a direct
  handoff into the relevant team roster.
- Match result, standings, and Website/publication surfaces now explain whether
  the next step is standings review, standings publication, tournament
  publication, or standings visibility.
- Follow-up slice (2026-05-26): portal roster detail now exposes the same
  undo-closure path as backend (`closed -> active`) so club representatives can
  recover from premature closure without leaving their primary workspace.
- Follow-up slice (2026-05-27): readiness and handoff copy now uses one
  blocker-list plus one next-action pattern across season registration,
  participant, roster, match-day preparation queue, result, standings, and
  publication surfaces. Participant confirmation now treats pre-deadline roster
  gaps as warning-only and escalates them to blocking once the deadline is
  reached.
- Follow-up slice (2026-05-27): exception/publication guidance now keeps
  Governance Override as the canonical engine, unifies dispute/exception entry
  wording on result surfaces, and introduces concise publication checklists on
  owning publication surfaces.

---

## Phase 3 — Canonical Planning And Match-Day Flows

### Goal

Remove ambiguity from the highest-friction operational journeys: planning and
match-day work.

### Why This Matters

These are the most interaction-dense flows in the repo, and they still expose
parallel primary surfaces with unclear ownership.

### Deliver

- Decide and document the canonical scheduling path:
  - when to use classic generation wizards
  - when to use Competition Workspace
  - who each flow is for
  - how to transition between them
- Clarify the match-day split between:
  - preparation
  - live operations
  - result follow-up
- Ensure one primary surface exists for each phase of match-day work.
- Reduce duplicate “workspace”, “board”, “queue”, and “match day” entry points
  that currently compete for attention.
- Make stage-aware and planner-specific concepts progressively disclosed rather
  than equally prominent from the start.

### Priority Surfaces

- `sports_federation_competition_engine`
- `sports_federation_portal`
- `sports_federation_rosters`
- `sports_federation_result_control`
- `_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md`
- `_workflows/WORKFLOW_MATCH_DAY_OPERATIONS.md`

### Exit Criteria

- Planners can tell which scheduling surface is primary without reading docs.
- Club representatives can tell where preparation ends and live operations begin.

### Status (2026-05-25)

- Implemented in the current baseline.
- Backend tournament and gameday records now frame the scheduling path in three
  phases: Planning Workspace for schedule building, Gameday Planner for
  day-level preparation, and Live Operations Board for in-progress play.
- Portal home, tournament workspace, match-day queue, live operations board,
  and results queue now label preparation, live operations, and result
  follow-up as distinct phases instead of competing peer destinations.
- Workflow and architecture docs now describe Competition Workspace as the
  canonical scheduling path, with classic generation wizards kept as advanced
  specialist tools.
- Follow-up slice (2026-05-27): remaining peer entry points now use explicit
  phase language. Portal home and club workspaces demote direct shortcuts
  behind the primary workspace, live operations navigation points back to Club
  Operations Workspace, Competition Workspace labels the day-level surface as
  Gameday Planner, and backend planning record lists are marked advanced.

---

## Phase 4 — Portal And Public Simplification

### Goal

Make portal and public surfaces feel intentionally designed for their audience,
not like backend concepts exposed through themed templates.

### Why This Matters

The portal currently offers too many adjacent cards and queues, while the public
site still leaks some migration-era or technical wording.

### Deliver

- Collapse portal entry points into a more obvious work queue model.
- Reduce overlapping tournament workspace, season, match-day, result, and duty
  CTAs on the portal home.
- Finish the tournament-first language cleanup on the public site.
- Replace technical or raw state labels on public pages with human labels.
- Make publication states and public visibility easier to understand from the UI
  without requiring workflow knowledge.
- Standardize portal/public empty-state patterns and CTA language.

### Priority Surfaces

- `sports_federation_portal/views/portal_templates.xml`
- `sports_federation_portal/views/portal_tournament_workspace_templates.xml`
- `sports_federation_portal/views/portal_roster_templates.xml`
- `sports_federation_public_site/views/website_menu.xml`
- `sports_federation_public_site/views/website_templates.xml`
- `sports_federation_public_site/views/website_hub_templates.xml`

### Exit Criteria

- Portal users can start work from one obvious home surface.
- Public visitors do not see internal state names, transitional language, or
  backend concepts they should not need.

### Status (2026-05-26)

- Implemented in the current baseline.
- Portal home and workflow pages now frame work as a clear queue sequence and
  remove remaining direct raw-state rendering.
- Public tournament and club/player surfaces now use audience-facing state
  labels, including tournament, match, participant, and license status labels.
- Follow-up slice (2026-05-26): officiating assignment pages now surface one
  explicit next-response action and pending/overdue urgency counters so linked
  match officials can prioritize confirmations without scanning all rows.
- Follow-up slice (2026-05-26): Competition Workspace now exposes editable
  division fairness rules in-place (minimum rest and max consecutive
  short-rest matches per team), and officiating readiness checks are deferred
  to post-planning states so slot planning can finish before staffing lock-in.

---

## Phase 5 — Copy, State, And Feedback Humanization

### Goal

Make the whole product speak like an operating tool for real federation staff
instead of a direct rendering of model states and implementation history.

### Why This Matters

Even strong workflows feel unintuitive when labels are technical, inconsistent,
or detached from the user’s next decision.

### Deliver

- Define standard business-facing labels for common states such as:
  - draft
  - submitted
  - confirmed
  - scheduled
  - in progress
  - published
  - archived
  - cancelled
- Remove raw internal state leakage from public and portal surfaces.
- Standardize warning, blocking, readiness, and success message patterns.
- Prefer action-oriented labels over record-oriented labels.
- Ensure every major action explains effect and consequence in human terms.

### Priority Surfaces

- `sports_federation_result_control`
- `sports_federation_standings`
- `sports_federation_public_site`
- `sports_federation_portal`
- `sports_federation_competition_engine`
- major backend forms and statusbars across the repo

### Exit Criteria

- Operators can infer record meaning from labels without knowing model states.
- Public and portal copy feel intentionally written for their audience.

### Status (2026-05-26)

- Implemented in the current baseline.
- Shared model helpers now provide human-facing state labels for portal and
  public surfaces, replacing direct selection/state rendering.
- Regression tests now guard against raw internal state leakage in both portal
  and public templates.

---

## Phase 6 — Intuitiveness Governance

### Goal

Keep intuition improvements from regressing as new features land.

### Deliver

- Add a lightweight intuition review checklist for future changes.
- Require new major flows to identify:
  - primary noun set
  - primary entry point
  - next-step guidance
  - user-facing state labels
  - cross-module handoffs
- Add a documentation rule that workflow and README updates must reflect any
  terminology or entry-point changes in the same patch.

### Exit Criteria

- New flows are reviewed for clarity, not only correctness.
- Naming drift and duplicate primary paths are caught during normal delivery.

### Status (2026-05-26)

- Implemented in the current baseline.
- Added [INTUITIVENESS_REVIEW_CHECKLIST.md](INTUITIVENESS_REVIEW_CHECKLIST.md)
  and linked it from contribution expectations to keep clarity reviews in the
  normal delivery path.
- Documentation now records the Phase 4-6 completion baseline and the
  corresponding state-label governance expectations.

---

## Cross-Cutting Standards

These standards should apply across all phases:

- One concept, one primary name.
- One high-frequency task, one primary starting point.
- Hidden prerequisites are defects in product clarity.
- Public copy must never expose raw internal states when a human label exists.
- Advanced paths should be available without being framed as equal defaults.
- Addon boundaries must not become user-facing information architecture.

---

## Suggested Validation Heuristics

Every intuitiveness change should be checked against these questions:

- Is the primary noun stable across backend, portal, public, and docs?
- Is there one obvious next action from the current screen?
- Are prerequisites explained where the user gets blocked?
- Does this surface expose an internal model or state name unnecessarily?
- Would a role-appropriate user know where to go next without reading a workflow document?
- Does this change reduce competing entry points or merely add another one?

---

## Explicitly Out Of Scope

This roadmap should **not** absorb general cleanup work.

Out of scope unless directly tied to clarity:

- performance and scaling work
- security or ACL hardening
- CI and test-harness cleanup
- generic refactors and service extraction
- schema redesign for maintainability alone
- new analytics, integrations, or exports
- feature expansion that adds power without reducing ambiguity

If a change does not improve comprehension, naming, discoverability, next-step
guidance, or user confidence, it belongs in a different roadmap.

---

## First Recommended Slice

If this roadmap is executed incrementally, start here:

1. Canonicalize competition/tournament/division/gameday language.
2. Pick the canonical scheduling path and visibly demote the alternate one.
3. Simplify the portal home into one primary work queue.
4. Humanize public-facing state labels and publication copy.
5. Add cross-module readiness guidance for registration -> roster -> planning -> publication.

That slice would improve intuitiveness across backend, portal, public, and docs
without waiting for a full navigation rewrite.