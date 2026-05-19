# Workflow: Roster Management

End-to-end lifecycle for managing team rosters — from pre-season draft through
active season use, match-day locking, and post-season closure.

## Overview

A **team roster** (`federation.team.roster`) is the official squad declaration
for a team in a given season and competition. Clubs assemble their rosters, get
them activated by federation staff, and use them as the source pool for
match-day squad sheets. Roster changes after activation require explicit admin
steps; match-day locks prevent post-match tampering.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_rosters` | Roster, roster line, match sheet, match sheet line, participation audit |
| `sports_federation_base` | Team, season, club, season registration |
| `sports_federation_people` | Player records and player licenses |
| `sports_federation_rules` | Squad-size and eligibility rule sets |
| `sports_federation_discipline` | Suspension checks during eligibility validation |
| `sports_federation_portal` | Club representative self-service roster editing |

## Models

| Model | Purpose |
|-------|---------|
| `federation.team.roster` | Master roster for a team/season/competition |
| `federation.team.roster.line` | Individual player slot within a roster |
| `federation.match.sheet` | Match-day squad declaration for one team |
| `federation.match.sheet.line` | Individual player/staff entry on a match sheet |
| `federation.participation.audit` | Immutable audit log of roster and sheet events |

## Step-by-Step Flow

### 1. Roster Creation

**Actor**: Club administrator or federation staff
**Module**: `sports_federation_rosters`

1. Navigate to **Federation → Rosters → Team Rosters** and click **New**.
2. Select the **team**, **season**, and optionally the **competition** and **rule set**.
3. Odoo auto-generates a name (`{Team} – {Competition} – {Season} Roster`);
   leave blank to trigger auto-generation, or supply a custom name.
4. Set minimum/maximum squad sizes if a rule set is not attached.
5. Add **roster lines** — one per player. Each line stores:
   - player reference
   - optional captain/vice-captain flag
   - linked player license (auto-scoped to the roster's team and season)
6. Portal users editing a roster only see licenses that match the roster's team and
   season; any attempt to supply out-of-scope IDs is rejected server-side.

Roster status starts at **`draft`**.

### 2. Eligibility & Readiness Check

**Actor**: Federation staff or automated validation
**Module**: `sports_federation_rosters`

1. The system computes `ready_for_activation` (stored Boolean) whenever roster
   lines, players, or licenses change.
2. `readiness_feedback` (stored Text) lists blocking reasons, e.g.:
   - Player has no active license for this season.
   - Squad size is below the required minimum.
   - Player is currently serving a suspension.
3. All checks must pass before the roster can be activated.

### 3. Roster Activation

**Actor**: Federation administrator
**Module**: `sports_federation_rosters`

1. Once readiness is confirmed, change status: **`draft` → `active`**.
2. An active roster is visible to club representatives in the portal and available
   as a source for match sheets.
3. A `federation.participation.audit` entry is created for the activation event.

### 4. Player Additions and Changes Post-Activation

**Actor**: Federation administrator
**Module**: `sports_federation_rosters`

1. Minor changes (e.g. adding a new player mid-season) require temporarily setting
   the roster back to `draft`, making changes, re-running the readiness check, and
   re-activating.
2. The re-activation creates a new audit log entry recording the responsible user
   and timestamp.

### 5. Match Sheet Creation

**Actor**: Club administrator / team manager
**Module**: `sports_federation_rosters`

1. For each fixture, create a **match sheet** (`federation.match.sheet`) linked to
   the match, the team, and the source roster.
2. Set the **side** (home / away / other).
3. Add **match sheet lines** — typically by selecting from the active roster lines.
   Mark starters vs. substitutes and assign jersey numbers.
4. Add coach and manager names if required.
5. Computed `ready_for_submission` reflects the same license/discipline/squad-size
   checks as the parent roster. `readiness_feedback` lists any blockers.

Match sheet states: `draft` → `submitted` → `approved` → `locked`.

### 6. Match Sheet Submission and Approval

**Actor**: Club administrator → Federation staff
**Module**: `sports_federation_rosters`

1. Club submits the sheet (`draft` → `submitted`).
2. Federation staff reviews the lineup and **approves** it (`submitted` → `approved`).
3. If corrections are needed, staff resets to `draft` for the club to amend.
4. Once approved, the listed players are locked in; only substitution-timing fields
   remain editable until the sheet reaches `locked`.

### 7. Match-Day Lock

**Actor**: System (automated after match completion) or federation staff
**Module**: `sports_federation_rosters`

1. After the match concludes (match state reaches `done`), the match sheet is
   locked: status → **`locked`**, `locked_on` timestamp and `locked_by_id` are
   recorded.
2. `match_day_locked` (computed on the roster) reflects whether any linked sheet
   is locked, surfacing a read-only message in the roster form.
3. No further lineup changes are possible once locked; a new protest/appeal must
   be filed through the **Discipline** module.

### 8. Roster Closure

**Actor**: Federation administrator (end of season)
**Module**: `sports_federation_rosters`

1. When the season closes, change status: **`active` → `closed`**.
2. Closed rosters are read-only and no longer available for new match sheets.
3. Audit trail remains fully queryable for historical analysis.

## State Diagrams

```
Roster:      draft → active → closed

Match Sheet: draft → submitted → approved → locked
                  ↑← reset (from submitted to draft)
```

## Portal Access

- Club representatives with an active `federation.club.representative` record can
  view and edit **draft** roster lines for their club's teams.
- Only licenses scoped to the roster's team and season are shown in the portal;
  server-side validation rejects any attempt to select out-of-scope records.
- **Active** or **closed** rosters are read-only in the portal.

## Audit Trail

Every significant roster event (creation, activation, reset, line additions,
match sheet approval, lock) records a `federation.participation.audit` entry
with actor, timestamp, and event type. These entries are immutable and form the
official record for disputes.

## Key Decision Points

| Question | Outcome |
|----------|---------|
| Player license inactive for this season? | Block activation; list in readiness_feedback |
| Player suspended? | Block activation / sheet submission |
| Squad below minimum size? | Block activation |
| Match sheet already locked? | No further lineup changes allowed |
| Season closed? | Roster moved to `closed`; no new sheets accepted |

## Related Workflows

- [Season Registration](WORKFLOW_SEASON_REGISTRATION.md) — rosters are created after confirmed season registration
- [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md) — match sheet submission and approval detail
- [Discipline Pipeline](WORKFLOW_DISCIPLINE_PIPELINE.md) — suspensions that block roster eligibility
