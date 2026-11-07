# Workflow: Match-day operations

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Everything that happens around a single match — roster management, match-sheet
submission, referee assignment, and match execution.

## Overview

On match day, several parallel preparation streams converge: the team rosters
must be active, match sheets must be submitted with eligible players, referees
must be assigned and confirmed, and the venue must be set. This workflow covers
the operational sequence from pre-match preparation through to the final whistle.

Primary surfaces by phase:

- **Preparation** — start from the portal **Rosters** page: open a roster to
   see its game days and prepare the game-day line-up from it. The **Game days**
   list (`/my/match-sheets`) is a direct shortcut to every upcoming game day of
   the club, and the backend **Gameday Planner** is the staff-only day-level
   surface for slot assignment and final one-day adjustments.
- **Live operations** — federation staff use **Match Operations > Game Days**
   (Match-Day Control) and court operators use **Run this court**; the portal
   operations board at `/sports/match-days/<matchday_id>/operations` shows the
   live state of one game day once matches are underway.
- **Result follow-up** — use the portal **Results** pages (`/my/results`) after full
   time when results still need approval, contests, or standings follow-up.
   Backend match and tournament records are specialist follow-up surfaces, not
   the default club starting point.

Direct queues and record pages exist as shortcuts, but they should not be
treated as equal-weight starting points for club representatives.

Draft match days may be deleted during preparation. Any draft or
change-requested working schedules are removed with the match day so the
restrictive schedule foreign key cannot leave an unusable planning record.
Match days with review or publication history, or with live operations, remain
protected and must use schedule revision or operational correction workflows.

For test cleanup or an explicitly authorized destructive correction, a closed
match day exposes **Delete Match Day** to federation and match-day managers. The
wizard reports the affected schedule, publication, session, deviation, and
match counts before requiring a reason and showing a final confirmation popup.
It removes the match-day execution and publication evidence, while retaining
competition match records detached from the deleted publication and slots.

## Operational Control Layer

The portal action-items page (`/my/action-items`) is a compact control layer
over the preparation and result follow-up phases. It projects unresolved work
from the authoritative registration, roster, club-duty, and result records
into `federation.operation.task` records. Re-running synchronization is
idempotent; resolving a source closes its task, while a newly blocking source
state reopens the same task by its stable source key.

Club representatives receive only tasks for clubs they represent. Federation
managers use **Federation > Competitions > Review Queue**, which refreshes the
projection when opened, to filter blocking work by club, tournament, type,
priority, deadline, and state. A task acknowledgement
does not override a sporting blocker; the linked domain action remains the
required resolution path.

The manager queue is served at `/federation/operations/action-items`. Team-only
representatives see tasks for their assigned team and may assign those tasks
only to that team or a whole-club representative; the model rejects forged
cross-team assignee IDs. Elevated task lookup does not determine source
readiness: the portal projection checks the current viewer's source ownership
and reports inaccessible sources as unavailable.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_rosters` | Season rosters and match-day squad sheets |
| `sports_federation_officiating` | Referee assignment to matches |
| `sports_federation_venues` | Venue and playing-area assignment |
| `sports_federation_tournament` | Match record management |
| `sports_federation_people` | Player eligibility verification |
| `sports_federation_rules` | Squad-size limits and eligibility rules |
| `sports_federation_discipline` | Suspension checks |
| `sports_federation_notifications` | Referee assignment emails and staffing alert activities |

## Step-by-Step Flow

### 1. Roster Preparation (Pre-Season)

**Actor**: Club administrator or federation staff
**Module**: `sports_federation_rosters`

1. Create a **team roster** for the season/competition.
2. Link to the team, season, and optionally the competition and rule set.
3. Add **roster lines** — each line links a player and can mark captain or vice-captain responsibilities.
4. Validate squad size and player eligibility against the rule set, including
   season registration, suspensions, and season/club-scoped license checks.
5. Portal roster editing only offers licenses that match the selected roster,
   season, and player, and manually posted hidden ids are rejected by the same
   server-side scope.
6. Review readiness feedback and set roster status: `draft` → `active`.
7. An active roster is the pool from which match sheets draw players.

### 2. Match Sheet Creation

**Actor**: Club administrator or team manager
**Module**: `sports_federation_rosters`

1. Match sheets are created automatically for the home and away team of every
   match. Prepare them once per team and game day with **Prepare Gameday
   Rosters** (see [one game-day roster per team](#one-game-day-roster-per-team)),
   which fills every sheet of that team on the day.
2. Each sheet links the match, team, side (`home` or `away`) and source roster.
3. Sheet lines are drawn from active lines of the team's source roster.
4. No starters or substitutes are declared in advance; at each match, players
   who do not play are crossed out.
5. Assign jersey numbers and captaincy where needed.
6. Add coach and manager names.
7. Validate: selected players must belong to active roster lines for the same
   team, satisfy license and registration rules for the match context, and any
   blockers are shown as readable feedback before submission.
8. If a submitted sheet needs correction, use **Reset to Draft**, update the
   lineup, and resubmit. Only `submitted` sheets can take this correction path.
9. After approval, the sheet line-up is frozen; only substitution timing fields
    remain editable until the sheet is explicitly locked.

Match sheet states: `draft` → `submitted` → `approved` → `locked`.

Portal workspace note:

- Club representatives only see match-day tasks of active, non-archived
   competitions and for teams inside their current whole-club scope or explicit
   current team scope. Inactive or expired
   representative rows do not keep match-day visibility alive.

### 3. Referee Assignment

**Actor**: Federation referee coordinator
**Module**: `sports_federation_officiating`

1. Select referees from the registry based on certification level and availability.
2. Create **match referee** assignments with defined roles:
   - `head` — Main referee
   - `assistant_1` / `assistant_2` — Assistant referees
   - `fourth` — Fourth official
   - `table` — Table or desk official
3. Each assignment has a state: `draft` (displayed as Assigned) → `confirmed` → `done` / `cancelled`.
4. Assignments inherit a 48-hour confirmation deadline from the scheduled match time and stay visible as overdue until confirmed, cancelled, or the match closes.
5. Confirmation is blocked if the official is inactive, their certification is missing / expired for the match date, or another assignment overlaps the same match window.
6. Matches aggregate readiness from the rule set's `referee_required_count`, confirmed assignments, overdue confirmations, and assignment-level readiness issues.
7. Scheduling and schedule approval apply these readiness rules before publication: double-booked officials block assignment moves while uncovered availability remains a warning.
8. Creating an assignment sends an email to the assigned referee with the role and confirmation deadline.
9. The scheduled notification scan creates federation-manager activities for overdue confirmations and staffing shortages.
10. SQL constraint prevents duplicate (match, referee, role) combinations.
11. The rule set's `referee_required_count` indicates how many officials are needed.

For automatic club-duty allocation, a club is considered to be playing during
the target match whenever one of its teams is assigned to a published match
whose time window overlaps the target window, even when the matches use
different courts. The allocator therefore prefers an eligible club outside
the whole concurrent set, not merely outside the target match's two clubs.

### 4. Venue Confirmation

**Actor**: Federation administrator
**Module**: `sports_federation_venues`

1. Confirm the match venue is set (via `venue_id` on the match).
2. Verify the playing area is available and suitable.
   - Calendar capacity preparation excludes unavailable venue or
      playing-area windows.
    - Scheduling validates the selected court against the effective division
       requirements before assignment.
3. Contact venue via stored contact details if needed.
4. If the venue incurs passthrough costs, scheduling the match with a venue
   automatically creates or reuses a draft venue booking finance event. Staff can
   still call `match.action_create_venue_finance_event()` to adjust the default
   `venue_booking` charge when needed.
5. Round scheduling and constraints:
    - Matches belong to a `federation.tournament.round` (`match.round_id`). The
       round carries the shared calendar date and venue; each match keeps the
       exact kickoff time and optional playing area.
    - The venues module enforces a constraint that prevents teams in the same
       `category` from playing the same opponent more than once inside the same
       round. This avoids repeated pairings in one shared round block.
    - Updating a round's venue propagates that venue to its matches. Updating a
       round's date preserves each match's time-of-day while moving the match to
       the round's calendar date.

### 5. Pre-Match Checks

**Actor**: Federation staff
**Modules**: Multiple

Before the match starts, verify:

| Check | Module | Detail |
|-------|--------|--------|
| Match sheets submitted | `rosters` | Both teams have approved sheets |
| Squad sizes valid | `rules` | Within min/max from rule set |
| Player licenses active | `people` | All listed players have active season licenses |
| No active suspensions | `discipline` | No player on the sheet is currently suspended |
| Referees confirmed | `officiating` | Required referee roles are filled, confirmable, and not double-booked |
| Venue set | `venues` | Match has a valid venue assignment that avoids blackout and capability issues |

Operational traceability additions:

- Once a roster line is used on a submitted, approved, or locked match sheet,
   that referenced roster line can no longer be structurally changed or removed.
- Match sheets record substitution timing (`entered_minute`, `left_minute`) on
   the declared squad instead of adding late lineup changes.
- Roster and match-sheet lifecycle events are written to participation audit
   history so club reps and staff can review what changed and when.

### 6. Match Execution

**Actor**: Referees, federation staff
**Module**: `sports_federation_tournament`

1. Set match state to `in_progress` at kick-off.
2. During the match, record:
   - Substitutions (update `entered_minute` / `left_minute` on approved match-sheet lines)
   - Incidents (yellow/red cards, misconduct) → feeds into discipline workflow
3. At full time, enter final scores (`home_score`, `away_score`).
4. Set match state to `done`.

### 7. Post-Match Actions

**Actor**: Various
**Modules**: Multiple

After the match completes:

| Action | Module | Detail |
|--------|--------|--------|
| Lock match sheets | `rosters` | Sheets move to `locked` state |
| Complete referee assignments | `officiating` | Assignments marked `done` |
| Submit result for verification | `result_control` | Feeds into result pipeline |
| Record incidents | `discipline` | Incidents logged during match |
| Log finance events | `finance_bridge` | Reimbursements for assignments marked `done`, venue booking charges for scheduled venue matches, and any linked fines |
| Recompute standings | `standings` | Updated with new result |

Operational readiness additions:

- Match forms expose official counts, overdue confirmations, and aggregated readiness issues so staffing gaps remain visible before kick-off.
- The notification scan creates follow-up activities for overdue confirmations and matches that still fail the officiating readiness check.

## State Diagram

```
Roster: draft ↔ active → closed → active

Match Sheet: draft → submitted → approved → locked
                          ↘ draft

Referee Assignment: assigned → confirmed → done
                                          → cancelled

Match: draft → scheduled → in_progress → done
                                    → cancelled
```

## Typical Timeline

| Timing | Action |
|--------|--------|
| Pre-season | Create and activate team rosters |
| 1 week before | Assign referees to match |
| 48 hours before | Confirm referee assignments |
| 24 hours before | Submit match sheets |
| Match day | Approve match sheets, verify eligibility |
| Kick-off | Set match to in_progress |
| During match | Record substitutions on the approved sheet |
| Full time | Enter scores, log incidents |
| Post-match | Lock sheets, submit result, update standings |

## Related Workflows

- [Result Pipeline](result-pipeline.md) — what happens after score entry
- [Discipline Pipeline](discipline-pipeline.md) — incident follow-up
- [Tournament Lifecycle](tournament-lifecycle.md) — tournament-level context

## Match-day operations board

The operations board at `/sports/match-days/<matchday_id>/operations` serves
game-day staff (organizers, court managers, result-table volunteers) for one
game day:

- **Access**: portal users with club or team activity on that game day, and
  federation staff through their normal session. Data and actions are
  constrained to the game day's current live publication.
- **Not for preparation**: line-up and roster work stays in the portal
  preparation pages until play is underway.
- **Sections**: header with match counts, a ranked action queue, summary
  filters (now playing, next, missing results, needs validation, court issues,
  completed), court status strip, match cards per court with one primary
  action, and a result-entry panel.
- **Result actions** call the result-control commands on the server
  (`action_submit_result`, `action_verify_result`, `action_approve_result`,
  `action_contest_result`, `action_correct_result`). All validation and
  separation-of-duties guards stay server-side; standings recompute through the
  result-control hooks.
- The board polls for updates; it has no live push.

Court operators using the authenticated **Run this court** workspace have a
separate capture path: score edits persist to the device draft as they are
entered, while **Save draft** queues the signed command for synchronization.
Queued work syncs when connectivity returns. Device drafts are not official
until the result review and approval process completes. See
[`sports_federation_live_workspace/README.md`](../../sports_federation_live_workspace/README.md).

## Schedule approval handoff

Before match-day preparation can start, the planner submits the complete working
schedule through **Submit for Review**. A different schedule approver uses the
**Schedule Review Queue** to request changes or approve the immutable submitted
revision. Approved schedules move to **Publishing > Approved Schedules**, where
**Publish Schedule** creates the live immutable publication. Match-day sessions
must continue to resolve their matches from that exact current publication.
The approver needs both the Schedule Approver group and an active
edition-specific `schedule_approver` responsibility. Approval revalidation reads
the submitted schedule's calendar and venue data internally; venue or calendar
management rights are not required. Publishing the approved schedule
materializes any missing operational matches for its assigned fixtures before
linking them to the immutable publication.

## Paper fallback: scoresheets

Before every game day, the match-day manager prints the scoresheets: select
the game day's matches and use **Print > Scoresheet** (one A4 page per
match, prefilled with officials and the game-day line-ups). Keep one printed
sheet per court. Before each match, the scorekeeper crosses out the game-day
players who do not play that match (**X** in **Out**), because the match
selection is made after printing. When the court app is unavailable, the head referee completes the
paper sheet, both captains and the head referee sign it, and the result is
entered from the sheet (the QR code opens the match) after the match. The
signed sheet is kept until the result is approved. See the
[rosters module](../../sports_federation_rosters/README.md#printable-scoresheet).

## Live operations and controlled deviations

1. Open **Match-Day Control** and resolve all readiness blockers.
2. Select **Open Match Day** to create an execution session pinned to the exact
   live publication and digest.
3. Use **Update Court** and **Report Incident** for operational conditions.
4. Use **Delay or Move Match** for a move, delay, postponement or
   cancellation. A reason is mandatory. The published slot never changes;
   `operational_slot_id` and `operational_status` represent the live reality.
5. Resolve incidents and complete or cancel every published match.
6. Select **Close Match Day**. Forced closure requires a reason and retains the
   blocker IDs in the competition event.

Publication replacement is impossible while a match day is open. Different
match days in the same edition retain independent live publications and version
sequences.

## One game-day roster per team

Use **Prepare Gameday Rosters** on the published game day, or the next
Competition Hub action. The form preselects a team with an active roster; if
none is available, activate a roster first. Choose the roster, the players who
come to that game day, the captain and jersey numbers. Saving writes the
canonical match sheet and synchronizes it to every match of that team on the
game day. No starters or substitutes are declared in advance: at each match
the coach crosses out the players who do not play, which never changes the
game-day roster. Rule sets may limit both the game-day roster size and the
number of players per match.

Submission enforces roster eligibility and verified parental approval for
under-16 players in senior competitions. Immediately before a match starts,
every listed player who is not crossed out is rechecked. Streamlined policy
records the approval automatically; Independent Review leaves the roster
submitted for another person.
