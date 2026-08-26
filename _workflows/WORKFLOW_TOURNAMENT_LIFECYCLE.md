# Workflow: Tournament Lifecycle

Full lifecycle of a tournament — from competition definition and participant
enrolment through schedule generation, match execution, and final completion.

## Overview

A **competition** is a recurring series (e.g. "National League Division 1").
Within each season, competitions host one or more **tournaments** which are
structured into stages, groups, and matches. This workflow covers the entire
journey from initial setup to final completion.

Canonical readiness chain (registration to publication):

1. Confirm season registration.
2. Confirm tournament participant.
3. Prepare active ready roster and match-day sheets.
4. Publish schedule and run live operations.
5. Approve results.
6. Recompute/review standings.
7. Publish tournament and standings surfaces.

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

## Step-by-Step Flow

### 1. Competition Setup

**Actor**: Federation administrator
**Module**: `sports_federation_rules`, `sports_federation_tournament`

1. Define a **rule set** with scoring values (win/draw/loss points), tie-break
   criteria, squad-size limits, and eligibility rules.
2. Create a **competition** (e.g. "National League Division 1").
3. Link the competition to the active season and the rule set.
4. Set competition state to `active`.

### 2. Tournament Creation

**Actor**: Federation administrator
**Module**: `sports_federation_tournament`

1. Under the competition, create a **tournament** (e.g. "NL Div 1 — Season 2025").
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

### 4. Participant Enrolment

**Actor**: Federation administrator (or via import)
**Module**: `sports_federation_tournament`, `sports_federation_import_tools`

1. Add **participants** to the tournament — each links a team to the tournament.
    - If the flow starts from portal registration requests, an administrator first
       confirms the `federation.competition.entry` record. That creates or links
       a `federation.tournament.participant` record in state `registered`.
    - That participant must still be moved to state `confirmed` before schedule
       generation can use it.
2. Optionally assign participants to specific stages and groups.
3. Set seeding ranks for bracket placement.
4. Participant states: `registered` → `confirmed` → `withdrawn` / `eliminated`.
5. Participant confirmation can happen before the team has an active roster, but
   only until one week before its first scheduled match, or one week before
   tournament start if no match has been scheduled yet. Once that deadline is
   reached, participant confirmation is blocked until the team has an active
   ready roster. When both a competition-specific roster and a season-wide
   roster are available, the competition-specific roster is used for readiness
   checks.
6. The participant form now surfaces the current roster deadline feedback inline
   and exposes **Open Team Roster** when operators need to resolve the blocker
   in the rosters flow before confirmation can continue.
7. Confirming a participant sends an email to the team and club contacts.
8. Move tournament to `open` state once enrolment is complete.

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

1. Move the competition into the state that permits scheduling.
2. Registration finalizes and locks the confirmed participant set.
3. Format freezes the structure and stage graph for the competition edition.
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
4. Tournament templates (`federation.tournament.template`) let administrators
   scaffold common stage/group/progression combinations (for recurring
   tournaments). Use `action_apply()` from the template to create stages and
   progression rules for a tournament in a single step.
5. Generate the next stage's schedule using competition engine wizards.
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
5. Public pages become available at `/tournaments/<slug>` and the related
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
