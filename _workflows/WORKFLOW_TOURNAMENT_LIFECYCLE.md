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
| `sports_federation_competition_engine` | Round-robin and knockout schedule generation wizards |
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
       confirms the `federation.tournament.registration` record. That creates or links
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
**Module**: `sports_federation_competition_engine`

Two operator flows are supported: classic generation wizards and the guided
Competition Workspace.

Canonical path:

- Use **Planning Workspace** as the default scheduling surface when operators
   need to manage entries, generate matches, create gamedays, assign slots, and
   publish schedules as one guided flow.
- Use the classic **Round Robin Wizard** or **Knockout Wizard** only as
   advanced or specialist tools when the federation wants direct one-step format
   generation on an already prepared tournament.
- After Planning Workspace creates gamedays, use the round-level
   **Gameday Planner** for one-day preparation. Once matches are underway, move
   to the **Live Operations Board** for in-progress play and result handling.

1. Move tournament to `in_progress` state.
2. Open **Planning Workspace** from the competition edition, tournament, or
    gameday when the federation wants the canonical guided path.
3. Open the **Round Robin Wizard** or **Knockout Wizard** from the tournament form only when the advanced direct-generation path is the better fit.
4. Configure scheduling options in the wizard:
   - Select participants and (optionally) a group.
   - `Use All Confirmed Participants` only includes `federation.tournament.participant`
     records in state `confirmed` inside the selected stage/group scope. Tournament
     registration requests on their own are not enough.
   - Ensure the tournament or linked competition already has an effective rule set; the wizard will block generation otherwise.
   - Set `Start Date/Time` and `Interval (hours)` — the intra-round spacing.
   - Use `Full Cycles (repeats)` to repeat the entire round-robin cycle N times
     (useful for formats that play multiple cycles; combined with the double-round
     option this enables 4+ meetings per pair).
    - Toggle `Schedule By Round` to allocate each round as a shared date/time
       block. When enabled, `Round Interval (hours)` controls spacing between rounds
       (e.g., 24 hours for daily rounds). Intra-round spacing still uses
       `Interval (hours)`.
       - Generated matches always bind to `federation.tournament.round` records.
          Existing stage rounds are reused by sequence order; missing rounds are
          created automatically.
       - Round dates and venues live on the round. The scheduler can fill those
          from the wizard inputs, but if the stage already has planned rounds with
          dates or venues, those values are respected.
       - The round scheduler will attempt to alternate `male` / `female` fixtures
          inside each round to provide rest; this is a best-effort interleaving and
          does not change seeding or pairings.
   - Set a default `Venue` and enable `Overwrite Existing` to replace prior matches.
5. Preview the generated schedule via the wizard `Summary` (shows total matches
   given participants, cycles, and round type). When overwrite is enabled, the
   wizard shows an explicit warning before confirmation.
6. Confirm to create all match records automatically.
7. If venues or exact days were not known during initial planning, update the
   generated stage rounds later. Matches linked to those rounds will inherit the
   round venue, and any scheduled match times must stay on the same calendar date.

**Round Robin**: Circle method generates a complete schedule where every team plays
every other team once (single) or twice (double).

**Knockout**: Seeded single-elimination bracket with automatic byes for non-power-of-two counts.

Competition Workspace

**Actors**:
- Competition planner for draft planning work.
- Federation manager for publication and any warning-only overrides.

Use the Competition Workspace when the federation wants a guided workflow that
separates pairing generation from operational slot assignment:

1. Open **Competition Workspace** from the competition edition, division, or
   gameday form.
2. Create or select the season competition, then create a division and choose
   the planning format.
   - Use `season competition` for this top-level season record. Older
     technical notes may still call it the `competition shell`, but that term
     is deprecated in operator-facing guidance.
   - Federation managers create the competition from the empty workspace menu
     state; planners continue once a competition or division already exists.
   - If the selected competition template already has an edition for that
     season, the workspace reopens the existing competition instead of creating
     a duplicate edition.
3. Add team entries and confirm them. Only `confirmed`
   `federation.tournament.participant` records count for planning.
   - The workspace team picker uses server-side search and an optional club
     filter so large team catalogs remain manageable.
4. Lock the participant list. This prevents planning drift once round generation
   starts.
5. Generate unscheduled matches for a supported planning format.
   - Single round robin creates one cycle of pairings.
   - Double round robin creates home-and-away pairings.
   - Knockout creates a seeded bracket with byes and linked future rounds.
   - Manual divisions skip the guided generator.
    - Pool-then-bracket creates balanced pool play first and then wires a staged
       knockout bracket for the configured qualifiers from each pool.
   The workspace stores logical rounds on `federation.match.round_number`
   without forcing an immediate gameday assignment.
6. Create one or more gamedays (`federation.tournament.round`) and attach a
   venue when known.
    - Multi-stage divisions can target a specific stage so pool work and
       knockout work stay separated operationally.
   - A gameday may include multiple divisions from the same competition when
     they share one physical match day.
   - The workspace creates one slot-owning gameday plus one linked gameday per
     extra division so each scheduled match still keeps a division-local round.
7. Generate court/time slots. The workspace creates `federation.match.slot`
   records on the slot-owning gameday and reuses that physical grid for every
   linked division in the same shared day.
8. Open the visual planner and assign matches to slots.
   - Desktop and tablet users can drag and drop.
   - Mobile users use the tap-to-assign fallback.
   - Keyboard users can select one match and assign it into an empty slot
     without drag-and-drop.
   - Dragging one already scheduled match onto another occupied slot now
     performs a validated safe swap when both matches can legally exchange
     places.
   - When a gameday is shared, the unscheduled list can contain matches from
     every participating division and operators can filter the pool back down
     by division or team.
   - The planner selection toolbar can bulk-assign the current filtered
     unscheduled set into the next open slots and bulk-unassign selected
     scheduled matches from the active gameday.
   - Recent assignment, move, and unassignment actions stay visible in the
     planner history panel and can be undone or redone directly from the
     workspace.
   - The workspace remembers the current section, division, gameday, and
     planner filters across refreshes so operators can recover their place.
   - The planner also shows recent operator presence and warns when another
     user is active on the same gameday.
    - Stage labels stay visible on previews, gameday controls, and match cards,
       and the planner surfaces fairness metrics plus ranked slot suggestions for
       the selected unscheduled match.
    - Division-level fairness settings can be tuned from the workspace while
       planning: minimum rest minutes plus max consecutive short-rest matches per
       team.
9. Review validation results before publishing.
   - Blocking conflicts stop unscheduled reuse of an occupied slot and prevent
     any move that would create a team overlap across simultaneous matches.
   - Short-rest issues use the division's `minimum_rest_minutes` threshold and
     surface as warnings.
    - Consecutive short-rest streaks beyond the division limit
       (`max_consecutive_matches_per_team`) surface as warnings.
    - Optional venue extensions can add blackout, maintenance, and capability
       issues to the same planner review step.
    - Officiating extension checks are staged after planning (`published` and
       later) so referee readiness does not block early slot allocation.
   - Shared match days validate against the slot-owning root gameday so every
     linked division sees the same planner issues for that physical day.
   - Validation output is grouped by issue type and severity, includes
     operator-facing hints, and highlights the affected slot or match in the
     planner.
10. Publish the gameday or the overall competition schedule.
   - Federation managers alone can publish.
   - Federation managers alone can force assignments that only contain
     warnings.
   - Publishing a guest-linked gameday still checks the slot-owning root
     gameday before the shared day can move live.
   - Publishing now creates or updates explicit schedule revisions so live,
     draft, and superseded plans remain distinguishable.
   - Republishing a live plan or forcing warnings requires a manager reason
     that stays attached to the resulting planner operation or revision.
11. Maintain schedule changes from the same workspace.
   - Published gamedays lock routine planner edits for non-managers.
      - Planner writes carry the current `planner_revision`; if another operator
         changed the planner first, the stale session must refresh before writing
         again.
      - Planner history stays linear: when a new planner write happens after an
         undo, the old redo branch is superseded instead of silently mixing two
         competing edit branches.
      - Any assignment, unassignment, or slot-grid regeneration that changes a
         validated or published day reopens the linked gameday to `planned` and
         the linked divisions to `planning` so publication is an explicit second
         pass, not an accidental side effect of a late edit.
      - Later edits create a draft revision alongside the live schedule until a
         manager republishes the updated plan.

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
   canonical `/tournaments/...` route family.

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
