# Workflow: Tournament Lifecycle

Full lifecycle of a tournament — from competition definition and participant
enrolment through schedule generation, match execution, and final completion.

## Overview

A **competition** is a recurring series (e.g. "National League Division 1").
Each season has a **season competition** (competition edition) containing one
or more **divisions** (tournament records), each structured into stages, groups,
and matches. The backend Competition Planner guides the federation through
edition-wide setup; the owner modules remain authoritative for each transition.
This workflow covers setup through final completion.

Canonical setup and readiness chain:

1. Create the season competition, divisions, registration windows, and role assignments.
2. Representatives submit team entries; federation registration managers review and finalize participant sets.
3. Freeze a versioned format for each division from its latest finalized participant set.
4. Allocate every playable fixture to ready physical match days.
5. Generate a complete working schedule for each allocated day; independently review and publish each current schedule revision.
6. Run match-day operations from live publications, then approve results.
7. Recompute/review standings and publish tournament and standings surfaces.

Club representatives own only their scoped team entries and club operations.
Federation edition roles own edition-wide setup, format freeze, calendar and
scheduling, independent schedule approval, and publication.

Blocking vs warning-only model:

- Blocking: the step cannot proceed (for example, deadline-backed roster blockers
   or unresolved publication validation blockers).
- Warning-only: the step can proceed, but requires operator follow-up and may
   require manager override logging depending on the surface.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_base` | Seasons, clubs, teams |
| `sports_federation_rules` | Rule sets governing scoring, tie-breaks, eligibility |
| `sports_federation_tournament` | Competition, tournament, stage, group, participant, match models |
| `sports_federation_competition_core`, `sports_federation_registration` | Competition identity, lifecycle, registration, and participant finalization |
| `sports_federation_format` | Versioned logical structures and stage graphs |
| `sports_federation_calendar` | Physical match days, capacity, slots, and timelines |
| `sports_federation_scheduling` | Deterministic fixture assignment and schedule validation |
| `sports_federation_schedule_approval` | Schedule review and immutable publication snapshots |
| `sports_federation_matchday` | Live operations after schedule publication |
| `sports_federation_venues` | Venue and playing-area assignment |
| `sports_federation_standings` | Standings computation at each stage |
| `sports_federation_notifications` | Participant-confirmation and publication notifications |
| `sports_federation_public_site` | Public publication of tournament pages |

## Verified UI navigation

Use [`docs/COMPETITION_UI_WORKFLOW.md`](../docs/COMPETITION_UI_WORKFLOW.md). The ordinary journey is **Federation → Competitions → Competition Hub**; addon names below describe ownership, while raw workspaces are advanced or contextual.

## Step-by-Step Flow

### 1. Competition Setup

**Actor**: Federation administrator
**Modules**: `sports_federation_competition_core`, `sports_federation_setup_flow`,
`sports_federation_rules`

1. Define reusable competition, rule, and setup templates as needed.
2. Create the season competition from **Create Competition**. The setup flow
   creates the edition, divisions, registration windows, and role assignments.
3. Continue to **Competition Planner**. Its readiness projection identifies the
   next blocker across divisions and match days; setup commands still run in
   their owning modules.

### 2. Tournament Creation

**Actor**: Federation administrator
**Module**: `sports_federation_competition_core`, `sports_federation_tournament`

1. Create or review each **division** (tournament record) under the season competition (e.g. "NL Div 1 — Season 2025"). The setup wizard can create the initial divisions; use the division records for later corrections.
2. Set tournament type: `league`, `cup`, `friendly`, or `playoff`.
3. Assign date range, rule set (inherited from competition or overridden).
4. Set maximum participants if applicable.
5. If the competition is spread over multiple event days, plan the shared
   schedule blocks directly on the stage rounds. Each round can carry a
   calendar date and a venue, while the matches inside that round keep their
   own kickoff times.
6. Tournament starts in `draft` state.

### 3. Venue Assignment

**Actor**: Federation administrator
**Module**: `sports_federation_venues`

1. Create or select venues with address, capacity, and playing areas.
2. Link venues to the tournament via the `venues` Many2many field.
3. Individual matches can later reference specific venues and playing areas.

### 4. Competition Entries and Participant Finalization

**Actors**: Club representative for own-team submission and recovery; federation registration manager for review and finalization
**Modules**: `sports_federation_registration`, `sports_federation_portal`

1. A representative selects a team in their current portal scope and an open
   registration window. The club portal and public registration page use the
   same submission command. It validates window/division ownership, open dates,
   team scope and eligibility, duplicate entry, and division capacity.
2. Competition-entry states are `draft` → `submitted` → `approved`, or
   `rejected` / `withdrawn`. A returned entry is `draft` with a federation review
   note; representatives can update the submission note and resubmit while the
   window remains open.
   Resubmitting after withdrawal reuses the same team/window record. Approved
   entries cannot be withdrawn directly.
3. Federation registration managers review/approve, return, or reject entries.
   After closing the window, use **Finalize Participants** to create the
   finalized participant set from approved entries. Only federation roles can
   finalize that set; clubs cannot modify the division's participant roster.
4. Do not confuse competition entries with legacy
   `federation.tournament.participant` records. Where those records are used by
   tournament operations, their lifecycle remains `registered` → `confirmed` →
   `withdrawn` / `eliminated` and is governed by the tournament workflow.
5. For legacy/manual tournament participant workflows only, participant
   confirmation can happen before the team has an active roster, but
   only until one week before its first scheduled match, or one week before
   tournament start if no match has been scheduled yet. Once that deadline is
   reached, participant confirmation is blocked until the team has an active
   ready roster. When both a competition-specific roster and a season-wide
   roster are available, the competition-specific roster is used for readiness
   checks.
6. The legacy participant form surfaces current roster deadline feedback inline
   and exposes **Open Team Roster** when operators need to resolve the blocker
   in the rosters flow before confirmation can continue.
7. Confirming a legacy tournament participant sends an email to team and club
   contacts.
8. Move a tournament to `open` state once its operational enrolment is complete.

Bulk enrolment is available via the **Import Tournament Participants** wizard.

### 5. Stage & Group Structure

**Actor**: Federation administrator
**Module**: `sports_federation_tournament`

1. Create **stages** within the tournament (e.g. "Group Phase", "Quarter-Finals").
2. Set stage type: `group`, `knockout`, `playoff`, or `other`.
3. Order stages by sequence.
4. Within each stage, create **groups** (e.g. "Group A", "Pool 1").
5. Assign participants to groups.
6. Create or review the stage rounds that should exist for each phase. Example:
   rounds 1-4 for the round-robin stage, then knockout rounds on the final stage.

### 6. Schedule Generation

**Actor**: Federation administrator
**Modules**: `sports_federation_format`, `sports_federation_calendar`,
`sports_federation_scheduling`, `sports_federation_schedule_approval`, and
`sports_federation_matchday`

The path is an explicit sequence of handovers:

- Freeze the logical structure and stage graph in `sports_federation_format`.
- Prepare physical match days and playable capacity in
   `sports_federation_calendar`.
- Generate or assign fixtures and validate the complete draft in
   `sports_federation_scheduling`.
- Submit the draft for review and publish an immutable snapshot through
   `sports_federation_schedule_approval`.
- Start live operations only from the published snapshot through
   `sports_federation_matchday`.

Competition Planner readiness is complete only when each division has at least
two teams in its latest finalized participant set and a frozen structure built
from that set, all playable fixtures are allocated, and every allocated match
day has ready capacity, a complete schedule, and a live publication for that
schedule revision. Edition-form progress and the planner consume the same
readiness projection.

1. Continue in Competition Planner after the season competition and divisions
   exist; resolve the current blocker shown there.
2. Registration closes the applicable window and finalizes a participant set
   from approved competition entries. A corrected finalized set must be handled
   as a governed replacement before format generation.
3. Format freezes the structure and stage graph for the competition edition,
   using the latest finalized set for each division.
   Round-robin and knockout generation remain deterministic and scoped to the
   frozen structure.
4. Calendar creates match days and `federation.schedule.slot` capacity for the
   required venues and courts. Slot lifecycle and court timelines are owned by
   `sports_federation_calendar`.
5. Scheduling assigns fixtures to available slots, applies fairness and rest
   validation, and returns a complete draft schedule. Blocking conflicts must be
   resolved before review; warnings remain visible and auditable.
6. Schedule approval reviews the draft and publishes an immutable schedule
   snapshot. Federation managers may approve configured warning-only overrides,
   with the reason retained in the audit trail.
7. Match-day operations open and close only published schedules. Referee
   readiness, venue readiness, result follow-up, and incidents are handled by
   their owning modules without changing the approved snapshot.

**Round Robin**: The format service generates a complete deterministic pairing
set where every team plays every other team once or twice according to policy.

**Knockout**: The format service creates a seeded single-elimination bracket,
including byes and future-round wiring for non-power-of-two participant counts.

### 7. Match Execution

**Actor**: Federation staff, referees
**Module**: `sports_federation_tournament`

1. Matches are scheduled with date/time, venue, home/away teams.
2. Match states progress: `draft` → `scheduled` → `in_progress` → `done`.
3. Scores are entered on the match form (home_score, away_score).
4. Match-day details are handled by the [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md)
   workflow.

### 8. Standings Computation

**Actor**: Federation administrator
**Module**: `sports_federation_standings`

1. Create a **standings** record scoped to the tournament, stage, or group.
2. Link the rule set for scoring and tie-break rules.
3. Compute standings: aggregates match results into ranked lines.
4. States: `draft` → `computed` → `frozen`.
5. Frozen standings are the publication candidates for the public site.

### 9. Stage Progression

**Actor**: Federation administrator
**Module**: `sports_federation_tournament`

1. After a stage completes, review standings to determine qualifiers.
2. Qualification rules from the rule set indicate who advances.
3. Use `federation.stage.progression` rules to formalise advancement: these
   can be single-group, cross-group (e.g. "best third-placed teams"), and
   include seeding/placement strategies. A progression rule can be executed
   manually (`action_execute()`) or set to `auto_advance=True`.
    - When designing a versioned structure in Format Studio, use the
       structure-scoped `federation.structure.stage.progression` edges instead.
       These graph edges are separate from the competition engine's tournament
       progression rules and are validated before the structure is generated.
   - When a standings record is `frozen`/`computed`, any progression rules for
     that stage with `auto_advance=True` will be executed automatically — new
     participants are created in the target stage and (optionally) a new stage
     schedule can be generated automatically.
    - Structure-scoped progression edges reject overlapping source rank ranges
       and destination seed ranges before generation. A tied approved bracket
       result is also blocked until an explicit tie-break outcome exists.
4. Tournament templates (`federation.tournament.template`) let administrators
   scaffold common stage/group/progression combinations (for recurring
   tournaments). Use `action_apply()` from the template to create stages and
   progression rules for a tournament in a single step.
5. Resume **Federation → Competitions → Competition Hub**. Advanced stage-graph recovery uses **Federation → Competitions → Advanced Competition Tools → Format Studio**, then the contextual schedule planner.
6. Typical workflow: freeze the round-robin standing, auto-advance the top-ranked
   teams into the knockout stage through a `federation.stage.progression` rule,
   then schedule those knockout matches onto the planned knockout rounds.

### 10. Tournament Completion

**Actor**: Federation administrator
**Module**: `sports_federation_tournament`

1. After the final stage, review and approve all remaining results.
2. Compute and publish final standings.
3. Set tournament state to `closed`.
4. Competition can be closed at end of season.

### 11. Public Publication

**Actor**: Federation administrator
**Module**: `sports_federation_public_site`

1. Set `website_published = True` on the tournament.
2. Configure public slug, description, and toggle results/standings visibility.
   The tournament Website tab now states whether publication is blocked because
   the tournament is still unpublished, standings do not exist yet, or standings
   remain hidden, and it links back to the standings action when relevant.
3. Publish standings records. Standings forms also explain whether approved
   results are still pending or whether website publication is the next valid
   step.
4. Participant club and team contacts receive a tournament-publication email the first time the tournament is published.
5. Public pages become available at `/competitions/<edition-slug>` and the related
   canonical `/competitions/...` route family.

## State Diagram

```
Competition: draft → active → closed

Tournament: draft → open → in_progress → closed
                                       → cancelled

Match: draft → scheduled → in_progress → done
                                        → cancelled

Standings: draft → computed → frozen

Participant: registered → confirmed → withdrawn
                                    → eliminated

```

Competition entry states are `draft`, `submitted`, `approved`, `rejected`, and
`withdrawn`. A return is represented by `draft` plus a review note. Draft,
rejected, and withdrawn entries may be resubmitted while the window is open;
draft, submitted, and rejected entries may be withdrawn. Approved entries
cannot be withdrawn directly.

## Key Decision Points

| Question | Outcome |
|----------|---------|
| League or Cup format? | Determines round-robin vs. knockout wizard |
| How many stages? | Single-stage league or multi-stage tournament with progression |
| Power-of-two bracket? | Knockout wizard handles byes for odd counts |
| When to publish? | Standings should be computed and verified before publication |

## Related Workflows

- [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md) — detailed match-day process
- [Result Pipeline](WORKFLOW_RESULT_PIPELINE.md) — score verification and approval
- [Season Registration](WORKFLOW_SEASON_REGISTRATION.md) — prerequisite club/team registration

## Simplified competition workspace contract (2026-10-10)

Ordinary operators create and resume competitions through **Federation > Competitions > Competition Hub**. The workspace exposes one next action and unified readiness. Direct team selection must materialize the canonical registration entries and finalized participant set; format selection must call canonical generation/freeze commands; game-day setup must hand directly to complete-competition schedule planning; review/publication must preserve immutable snapshots and separation of duties when configured.

Raw registration, format, calendar, schedule, review, and technical records remain available only through contextual links or Advanced Federation Tools. Hiding their menus does not relax their ACL, role, transition, validation, versioning, or audit contracts.
