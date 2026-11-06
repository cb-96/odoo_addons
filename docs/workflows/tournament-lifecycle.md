# Workflow: Tournament lifecycle

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Full lifecycle of a season competition and its divisions, from competition
definition and team enrolment through schedule generation, match execution and
final completion. The operator walkthrough is in the
[competition workflow](../user-guide/competition-workflow.md); the records and
handoffs are described in the [competition model](../architecture/competition-model.md).

## Overview

A **competition** is a recurring series (e.g. "National League Division 1").
Each season has a **season competition** (competition edition) containing one
or more **divisions** (tournament records), each structured into stages, groups,
and matches. The Competition Hub guides the federation through
edition-wide setup from the Competition Hub; the owner modules remain authoritative for each transition.
This workflow covers setup through final completion.

Canonical setup and readiness chain:

1. Create the season competition, divisions, registration windows, and role assignments.
2. Representatives submit team entries; federation registration managers review and finalize participant sets.
3. Freeze a versioned format for each division from its latest finalized participant set.
4. Allocate every playable fixture to ready physical match days.
5. Generate a complete working schedule for each allocated day; review according to the edition's workflow policy and publish each current schedule revision.
6. Run match-day operations from live publications, then approve results.
7. Recompute/review standings and publish tournament and standings surfaces.

Club representatives own only their scoped team entries and club operations.
Federation edition roles own edition-wide setup, format freeze, calendar and
scheduling, independent schedule approval, and publication.

Competition responsibility assignments are per-edition routing; they do not
grant federation-wide access groups. Operators need both the per-edition role
and the global groups for every work area they access: Federation User is the
base, Registration Manager covers team and participant setup, Calendar Planner
covers game days, Schedule Planner covers working schedules, and Schedule
Approver enables independent review. Streamlined schedule approval follows the
edition's self-approval policy, while Independent Review enforces a different
approver.

Competition-wide generation stores each distributed fixture subset as an exact
game-day allocation. Fixtures already allocated on another day are not
replanned by a partial run, and duplicate cross-day allocations block
generation before schedules are reviewed or published.

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
| `sports_federation_tournament` | Competition, division, stage, group, participant, match models |
| `sports_federation_setup_flow` | Competition Hub planner and guided setup |
| `sports_federation_competition_core`, `sports_federation_registration` | Competition identity, lifecycle, registration, and participant finalization |
| `sports_federation_format` | Versioned logical structures and stage graphs |
| `sports_federation_calendar` | Physical match days, capacity, slots, and timelines |
| `sports_federation_scheduling` | Deterministic fixture assignment and schedule validation |
| `sports_federation_schedule_approval` | Schedule review and immutable publication snapshots |
| `sports_federation_matchday` | Live operations after schedule publication |
| `sports_federation_venues` | Venue and playing-area assignment |
| `sports_federation_standings` | Standings computation at each stage |
| `sports_federation_notifications` | Participant-confirmation and publication notifications |
| `sports_federation_public_site` | Public competition pages |

## Verified UI navigation

The ordinary journey starts at **Federation > Competitions > Competitions**
(the Competition Hub); see the [competition workflow](../user-guide/competition-workflow.md).
Addon names below describe ownership; raw workspaces are advanced or
contextual.

## Step-by-Step Flow

### 1. Competition Setup

**Actor**: Federation administrator
**Modules**: `sports_federation_competition_core`, `sports_federation_setup_flow`,
`sports_federation_rules`

1. Define reusable competition, rule, and setup templates as needed.
2. Create the season competition from **Create Competition**. The setup flow
   creates the edition, divisions, registration windows, and role assignments.
3. Continue in the **Competition Hub**. Its readiness projection identifies the
   next blocker across divisions and match days; setup commands still run in
   their owning modules. Edition readers may see the scoped readiness summary,
   while registration-window records remain restricted to registration
   managers.

### 2. Divisions

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
4. Finalizing the participant set creates the confirmed division participants
   (`federation.tournament.participant`, states `registered` → `confirmed` →
   `withdrawn` / `eliminated`), and each participant gets a roster prepared.
   Teams that fail eligibility are logged and skipped.
5. Manual participant confirmation is possible before the team has an active
   roster only until one week before its first scheduled match (or one week
   before the division starts if no match is scheduled). After that deadline,
   confirmation requires an active ready roster; a competition-specific roster
   is preferred over a season-wide one. The participant form shows the deadline
   feedback and offers **Open Team Roster**.
6. Confirming a participant sends an email to team and club contacts.
7. Move a division to `open` once its enrolment is complete.

In the Competition Hub, **Select Teams** performs steps 1–4 in one command for
federation-selected teams: it materializes the registration window, approved
entries and finalized participant set.

Bulk enrolment is available via the **Import Tournament Participants** wizard.

### 5. Format

**Actor**: Competition designer
**Module**: `sports_federation_format`

1. Choose the format for each division in the Competition Hub (**Teams &
   format** or **Format options**): league, home-and-away league, knockout,
   pools then knockout, or a custom stage graph built in the stage builder. See
   [competition formats](../user-guide/competition-formats.md).
2. Generating the format creates the versioned structure, its stages, groups
   and every fixture, including placeholders for later stages, and freezes it.
3. Specialists can edit complex stage graphs in **Format Studio** (advanced).

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

Competition Hub readiness is complete only when each division has at least
two teams in its latest finalized participant set and a frozen structure built
from that set, all playable fixtures are allocated, and every allocated match
day has ready capacity, a complete schedule, and a live publication for that
schedule revision. Edition-form progress and the planner consume the same
readiness projection.

1. Continue in the Competition Hub after the season competition and divisions
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

**Pools then knockout**: Choose the group count in the format picker. Seeds are
distributed in a snake pattern, groups play a single round robin, and the top
two teams from each frozen group table advance to a seeded bracket. Knockout
placeholders are part of the original publication; after all group tables are
frozen, progression fills the scheduled bracket without a replacement
publication. For a tied knockout score, record the resolution and advancing team
on the match before submitting the result.

### 7. Match Execution

**Actor**: Federation staff, referees
**Modules**: `sports_federation_matchday`, `sports_federation_result_control`

1. Matches are scheduled with date/time, venue, home/away teams.
2. Match states progress: `draft` → `scheduled` → `in_progress` → `done`.
   Immediately before play, every listed non-crossed-out player is rechecked
   against current eligibility; a newly suspended or otherwise ineligible
   player must be crossed out for that match before it can start.
3. Scores are entered by court operators or on the match form and follow the
   [result pipeline](result-pipeline.md).
4. Match-day details are handled by the [match-day operations](match-day-operations.md)
   workflow.

### 8. Standings

**Actor**: Results officer, federation administrator
**Modules**: `sports_federation_standings`, `sports_federation_format`

1. Every round-robin stage has a linked league table. It recomputes
   automatically when results are approved, contested or corrected.
2. States: `draft` → `computed` → `frozen`. A table cannot be frozen while
   results still need completion or approval.
3. Frozen or computed standings are the publication candidates for the public
   site. See the [standings lifecycle](standings-lifecycle.md).

### 9. Stage Progression

**Actor**: Federation administrator
**Module**: `sports_federation_format`

1. Stage-to-stage progression is defined by the structure's progression edges
   (`federation.structure.stage.progression`): which ranks of which source stage
   or group move to which seeds of the target stage.
2. Edges are validated before generation: overlapping source rank ranges and
   destination seed ranges are rejected.
3. Freezing a stage's league table freezes the stage snapshot and applies its
   outgoing edges. The placeholders of the next stage ("#1 Group A") are filled
   with the qualified teams; already published matches keep their slots, so no
   replacement publication is needed.
4. A tied knockout result is blocked until the tie resolution and advancing
   team are recorded on the match.
5. Advanced stage-graph recovery uses **Federation > Competitions > Planning
   Tools > Format Studio**, then the contextual schedule planner.

### 10. Finish

**Actor**: Federation administrator
**Modules**: `sports_federation_setup_flow`, `sports_federation_competition_core`

1. After operations, the Competition Hub keeps proposing one next action until
   the competition is closed: close finished game days, approve remaining
   results, freeze final tables, then close the competition.
2. Closing moves the season competition through the guarded Open, In Progress
   and Closed transition and is refused while anything is unfinished.
3. Publishing on the website is proposed as soon as the competition is open.
4. Archive the competition when it is over. Archived competitions disappear
   from portal workflows (entries, rosters, line-ups, duties, tasks); **Restore**
   brings them back.

### 11. Public Publication

**Actor**: Federation administrator
**Module**: `sports_federation_public_site`

1. Set `website_published = True` on the division.
2. Configure public slug, description, and toggle results/standings visibility.
   The division Website tab states whether publication is blocked because
   the tournament is still unpublished, standings do not exist yet, or standings
   remain hidden, and it links back to the standings action when relevant.
3. Publish standings records. Standings forms also explain whether approved
   results are still pending or whether website publication is the next valid
   step.
4. Participant club and team contacts receive a publication email the first
   time the division is published.
5. Public pages become available at `/competitions/<edition-slug>` and the related
   canonical `/competitions/...` route family.

## State Diagram

```
Competition: draft → active → closed

Division: draft → open → in_progress → closed
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
| League or cup format? | Chosen per division in the Competition Hub format picker |
| How many stages? | Single-stage league, pools then knockout, or a custom stage graph |
| Power-of-two bracket? | Knockout generation adds byes for other team counts |
| When to publish? | Standings should be computed and verified before publication |

## Related Workflows

- [Match Day Operations](match-day-operations.md) — detailed match-day process
- [Result Pipeline](result-pipeline.md) — score verification and approval
- [Season Registration](season-registration.md) — prerequisite club/team registration

## Competition Hub contract

Ordinary operators create and resume competitions through **Federation >
Competitions > Competitions**. The Competition Hub exposes one next action and
unified readiness. Federation managers can use the team picker without general
registration-window read access; it projects only the selected edition and
division, while changes still pass through the role-checked registration
command. Direct team selection must materialize the canonical registration
entries and finalized participant set; format selection must call the
canonical generation and freeze commands; game-day setup must hand directly to
complete-competition schedule planning; review and publication must preserve
immutable snapshots and separation of duties when configured.

Raw registration, format, calendar, schedule, review and technical records
remain available only through contextual links or Advanced Federation Tools.
Hiding their menus does not relax their ACL, role, transition, validation,
versioning or audit contracts.
