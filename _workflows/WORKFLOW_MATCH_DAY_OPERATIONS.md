# Workflow: Match Day Operations

Everything that happens around a single match — roster management, match-sheet
submission, referee assignment, and match execution.

## Overview

On match day, several parallel preparation streams converge: the team rosters
must be active, match sheets must be submitted with eligible players, referees
must be assigned and confirmed, and the venue must be set. This workflow covers
the operational sequence from pre-match preparation through to the final whistle.

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

1. For each match, create a **match sheet** for each participating team (home/away).
2. Link the match sheet to the match, team, and source roster.
3. Set the side (`home` or `away`).
4. Add **match sheet lines** — typically by selecting active roster lines from
   the team's source roster.
5. Mark starters vs. substitutes.
6. Assign jersey numbers and captaincy where needed.
7. Add coach and manager names.
8. Validate: selected players must belong to active roster lines for the same
   team, satisfy license and registration rules for the match context, and any
   blockers are shown as readable feedback before submission.
9. If a submitted sheet needs correction, use **Reset to Draft**, update the
   lineup, and resubmit. Only `submitted` sheets can take this correction path.
10. After approval, the sheet lineup is frozen; only substitution timing fields
    remain editable until the sheet is explicitly locked.

Match sheet states: `draft` → `submitted` → `approved` → `locked`.

Portal workspace note:

- Club representatives using the tournament workspace only see match-day tasks
   for active tournaments (`open` or `in_progress`) and for teams inside their
   current whole-club scope or explicit current team scope. Inactive or expired
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
5. Confirmation is blocked if the official is inactive or their certification is missing / expired for the match date.
6. Matches aggregate readiness from the rule set's `referee_required_count`, confirmed assignments, overdue confirmations, and assignment-level readiness issues.
7. Creating an assignment sends an email to the assigned referee with the role and confirmation deadline.
8. The scheduled notification scan creates federation-manager activities for overdue confirmations and staffing shortages.
9. SQL constraint prevents duplicate (match, referee, role) combinations.
10. The rule set's `referee_required_count` indicates how many officials are needed.

### 4. Venue Confirmation

**Actor**: Federation administrator
**Module**: `sports_federation_venues`

1. Confirm the match venue is set (via `venue_id` on the match).
2. Verify the playing area is available and suitable.
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
| Referees confirmed | `officiating` | Required referee roles are filled and confirmed |
| Venue set | `venues` | Match has a valid venue assignment |

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
Roster: draft → active → closed

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

- [Result Pipeline](WORKFLOW_RESULT_PIPELINE.md) — what happens after score entry
- [Discipline Pipeline](WORKFLOW_DISCIPLINE_PIPELINE.md) — incident follow-up
- [Tournament Lifecycle](WORKFLOW_TOURNAMENT_LIFECYCLE.md) — tournament-level context
