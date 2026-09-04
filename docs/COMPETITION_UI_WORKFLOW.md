# Competition Workflow in the User Interface

Owner: Federation Competition Operations
Last verified against menu XML: 2026-09-04

## Purpose

This guide replaces conceptual module names with the menus that actually exist in the **Federation** application. A menu can be hidden if the current user lacks the required role or record access.

## Actual backend menu map

```text
Federation
├── Setup
│   ├── Core Records
│   │   ├── Clubs
│   │   └── Teams
│   ├── Seasons
│   ├── Season Registrations
│   └── Competition Setup
│       ├── Competition Templates
│       ├── Season Competitions
│       └── Rules & Policies
├── Competition Workflow
│   ├── Create Competition
│   ├── Competition Overview
│   ├── Registration Desk
│   ├── Format Studio
│   ├── Format Templates
│   ├── Calendar Planner
│   ├── Schedule Planner
│   ├── Schedule Review Queue
│   ├── Match-Day Control
│   └── Technical Records
├── Planning
│   ├── Operational Action Queue
│   └── Advanced Records
│       ├── Divisions & Tournaments
│       ├── Matches
│       └── Tournament Structure
├── Match Day
│   ├── Match Sheets
│   ├── Venues
│   ├── Officiating
│   └── Discipline
├── Publication
│   ├── Standings
│   ├── Approved Schedules
│   └── Schedule Publications
└── Administration
    ├── Reporting
    │   └── Operational Health
    ├── Retention and Recovery
    ├── Retention Evidence
    └── Operational Job Health
```

There is no backend menu named **Competitions**, **Registrations**, **Scheduling**, **Schedule Approval**, **Results**, or **Competition Engine**. Those are concepts or addon names, not current navigation labels.

## Actual club portal links

```text
My Account
├── Overview                 /my/competitions
├── Action items             /my/action-items
├── My teams                 /my/teams
├── Season registrations     /my/season-registrations
├── Match day                /my/match-day
├── Officials                /my/referee-duties
└── Results                  /my/results
```

## Complete workflow and recovery

### 1. Prepare reusable setup

Use:

```text
Federation > Setup > Seasons
Federation > Setup > Competition Setup > Competition Templates
Federation > Setup > Competition Setup > Rules & Policies > Rule Sets & Policies
Federation > Setup > Core Records > Clubs
Federation > Setup > Core Records > Teams
```

Create the season, reusable competition definition, rule set, clubs, and teams. Points, tie-break, eligibility, and qualification components are below **Rules & Policies > Advanced Components**.

**Recovery:** Edit unused records. Archive records that already have history. Do not delete referenced seasons, competitions, clubs, teams, or rule sets merely to restart a workflow.

### 2. Create the season competition

Preferred menu:

```text
Federation > Competition Workflow > Create Competition
```

The wizard selects the setup template, competition template, season, dates, optional rule set, registration dates, divisions, and responsibilities. It creates the season competition, divisions, registration windows, and role assignments, then opens the season competition.

Inspect the records through:

```text
Federation > Setup > Competition Setup > Season Competitions
Federation > Planning > Advanced Records > Divisions & Tournaments
Federation > Competition Workflow > Competition Overview
```

**Recovery:** Correct newly created records before clubs submit. There is no generic **Undo Competition Wizard** button. If downstream entries, fixtures, schedules, results, or publications exist, preserve the original records and create controlled replacements.

### 3. Open registration and accept entries

Backend:

```text
Federation > Competition Workflow > Registration Desk
```

Club portal:

```text
My Account > Season registrations
```

Use **Open Registration** on a draft registration window. Clubs prepare and submit entries. Managers review them in the Registration Desk.

**Recovery:** Use **Close Registration** to stop submissions. A submitted entry can be withdrawn by the club or returned by the manager with a reason. A returned entry can be corrected and resubmitted. Rejection remains historical evidence.

### 4. Finalize participants

Menu:

```text
Federation > Competition Workflow > Registration Desk
```

Close the registration window and press **Finalize Participants**. The finalized participant set feeds the format structure.

**Recovery:** Correct entries before finalization. If a finalized set is wrong and nothing depends on it, create a corrected set through the registration workflow. If fixtures or schedules exist, create a successor structure or schedule revision instead of mutating published history.

### 5. Configure and generate the format

Menus:

```text
Federation > Competition Workflow > Format Templates
Federation > Competition Workflow > Format Studio
```

**Format Templates** is manager-only. In **Format Studio**, select the season competition, division, finalized participant set, and format settings. Use **Check Feasibility**, then **Generate Fixtures**. For multi-stage structures use **Validate Stage Graph**. Once accepted, use **Freeze Structure**.

**Recovery:** Before freeze, correct and regenerate. Once operational matches or frozen stage snapshots exist, create a new structure version. The current UI has no generic structure-unfreeze command.

### 6. Prepare and progress stages

There is no standalone **Stage Progression** menu. Stage controls are on the structure opened from:

```text
Federation > Competition Workflow > Format Studio
```

Available stage actions are **Prepare**, **Start**, and **Freeze & Progress**.

**Recovery:** Correct a stage before starting it. Before progression, correct and recompute standings. Frozen snapshot lines are immutable; after progression use a corrected successor structure rather than editing evidence.

### 7. Plan calendar capacity

Menu:

```text
Federation > Competition Workflow > Calendar Planner
```

Create match days, slot windows, and capacity, then use **Mark Capacity Ready**. Venue setup and constraints are under:

```text
Federation > Match Day > Venues
```

**Recovery:** Edit draft calendar records. If a schedule already uses the calendar, make the deliberate calendar correction and refresh the working schedule. Stale assignments are flagged, not silently deleted.

### 8. Build the working schedule

Menu:

```text
Federation > Competition Workflow > Schedule Planner
```

Use **Refresh Calendar Fixtures**. Assign dates, times, venues, and courts manually, or use **Auto-schedule**, **Preview**, and **Apply Auto-schedule**. Review fairness warnings.

**Recovery:** Draft and change-requested schedules remain editable. A preview does not change the schedule until applied. Refresh fixtures, move assignments, or regenerate while mutable.

### 9. Submit and review the schedule

Planner menu:

```text
Federation > Competition Workflow > Schedule Planner
```

Use **Submit for Review**. Approver menu:

```text
Federation > Competition Workflow > Schedule Review Queue
```

The review exposes **Withdraw Submission**, **Request Changes**, and **Approve Schedule** according to state and role.

**Recovery:** Withdraw a pending submission to return it to editing. Request changes to return it to the planner. If an approval is mistaken, do not publish; correct it through a new review cycle while preserving separation of duties.

### 10. Publish the schedule

Use **Publish Schedule** on an approved review. The two real publication menus are:

```text
Federation > Publication > Approved Schedules
Federation > Publication > Schedule Publications
```

**Recovery:** Live publications are immutable. Open the published schedule under **Federation > Competition Workflow > Schedule Planner**, use **Amend Schedule**, enter a reason, and press **Create Amendment**. The replacement follows submit, review, approve, and publish again. The old publication becomes superseded. There is no in-place **Unpublish** button.

### 11. Operate match day

Menu:

```text
Federation > Competition Workflow > Match-Day Control
```

Use **Open Match Day** when ready. During operations use **Update Court**, **Report Incident**, or **Operational Schedule Change**. Finish with **Close Match Day**. Supporting records are under:

```text
Federation > Match Day > Match Sheets
Federation > Competition Workflow > Technical Records > Incidents
Federation > Competition Workflow > Technical Records > Operational Deviations
```

**Recovery:** Resolve incident and deviation records with **Resolve**. Operational changes are recorded rather than silently altering the approved publication. Correct the planning baseline through a schedule amendment.

### 12. Submit and approve results

Backend menu:

```text
Federation > Planning > Advanced Records > Matches
```

Result Control extends the match form; there is no separate backend **Results** menu. The form provides **Submit Result**, **Verify Result**, **Approve Result**, **Raise Dispute / Request Exception**, **Correct Result**, and **Reset to Draft**.

Club portal:

```text
My Account > Results
```

**Recovery:** Reset an incorrect in-progress result to draft. Raise a dispute for governed review. Correct contested or approved results through **Correct Result**. Never silently edit an approved score.

### 13. Recompute and freeze standings

Menu:

```text
Federation > Publication > Standings
```

Use **Recompute** or **Queue Recompute**, inspect lines and tie-break notes, and then use **Freeze**.

**Recovery:** Recompute while unfrozen. For a frozen standing, use **Unfreeze**, correct the source result or rule, use **Force Recompute**, and freeze again. Failed asynchronous work appears under the nested **Recompute Queue**.

### 14. Monitor exceptions

Menus:

```text
Federation > Planning > Operational Action Queue
Federation > Administration > Reporting > Operational Health
Federation > Administration > Operational Job Health
```

Use source links to correct business records in their owning workflow. Retry only retryable jobs.

## Required terminology in operator documentation

- Use **Federation > Competition Workflow**, not “Competition Engine”.
- Use **Registration Desk**, not “Registration Windows” as a menu.
- Use **Schedule Planner**, not “Scheduling > Schedules”.
- Use **Schedule Review Queue**, not “Schedule Approval > Reviews”.
- Use **Publication > Schedule Publications**, not “Schedule Approval > Publications”.
- Use **Planning > Advanced Records > Matches**, not “Results > Match Results”.
- Use **Publication > Standings**, not “Standings > Standings”.
- Use **Format Studio** for stage progression; there is no standalone progression menu.
