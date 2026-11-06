# Backend navigation

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

The normal competition journey has one discoverable entry:
**Federation > Competitions > Competitions**. Opening a season competition
resumes the same Competition Hub and promotes exactly one next action.
Operators do not need to choose between registration, format, calendar,
scheduling, approval or raw-record menus.

The underlying domain actions are not removed. They remain available through
contextual links and to users in the **Advanced Federation Tools** group. This
keeps recovery, compliance, audit, security and specialist work possible
without presenting implementation structure to every operator.

## Work areas

The **Federation** application has these top-level work areas, in this order:

- **Needs Attention**: one inbox of manager tasks and referee duties that need a person.
- **Competitions**: create, plan, publish and finish competitions.
- **Clubs & People**: clubs, teams, players and licences, representatives, season registrations.
- **Match Operations**: game days, court operation, matches, line-ups, venues, officiating, discipline.
- **Publishing**: approved and published schedules, standings, public editorial content.
- **Finance & Assurance**: finance, compliance and governance (advanced).
- **Insights**: operational, performance and assurance reports (advanced).
- **Administration**: action queue, imports and integrations, notifications, member services, audit and recovery, system health (advanced).
- **Reports**: opens the operational health dashboard.

Visibility is role based. An ordinary manager mainly sees Needs Attention,
Competitions, Clubs & People, Match Operations, Publishing and Reports.
Finance & Assurance, Insights, Administration and the raw competition menus
are visible to the advanced or specialist groups that own them.

## Ordinary operator map

```text
Federation
├── Needs Attention
├── Competitions
│   └── Competitions
├── Clubs & People
│   ├── Clubs
│   ├── Club Directory
│   ├── Teams
│   ├── Players
│   ├── Players & Licensing
│   ├── Club Representatives
│   ├── Representatives & Access
│   └── Season Registrations
├── Match Operations
│   ├── Game Days
│   └── Run this court
├── Publishing
│   ├── Approved Schedules
│   ├── Published Schedules
│   ├── Standings
│   └── Public Editorial
└── Reports
```

The Competition Hub provides contextual actions for teams, format, game days,
schedules, publication, rosters, game-day line-ups, officials, results and
readiness. Contextual actions keep the active competition scope and replace
most global queue menus for ordinary work.

## Advanced and administration map

```text
Federation
├── Competitions
│   ├── Competitions
│   ├── Seasons
│   ├── Season Competitions
│   ├── Competition Templates
│   ├── Format Templates
│   ├── Rules & Policies
│   ├── Advanced Competition Tools
│   │   ├── My Creation Drafts
│   │   ├── Create Competition
│   │   ├── Competition Overview
│   │   ├── Registration Desk
│   │   ├── Format Studio
│   │   ├── Calendar Planner
│   │   ├── Generate Competition Schedule
│   │   ├── Schedule Planner
│   │   └── Schedule Review Queue
│   └── Competition Records
│       └── Divisions & Matches
├── Match Operations
│   ├── Game Days
│   ├── Assign court operators
│   ├── Run this court
│   ├── Court recovery and exceptions
│   ├── Matches
│   ├── Venues
│   ├── Game-Day Lineups
│   ├── Officiating
│   │   ├── Duty coverage board
│   │   ├── Plan Match-Day Officials
│   │   ├── Match Assignments
│   │   ├── Club Duties
│   │   ├── Referees
│   │   └── Reimbursements
│   └── Discipline
├── Publishing
│   └── Standings
│       └── Recompute Queue
├── Finance & Assurance
│   ├── Finance
│   ├── Compliance
│   └── Governance
├── Insights
│   └── Reports & Insights
│       ├── Overview & Readiness
│       ├── Performance
│       ├── Assurance & Exceptions
│       └── Automation & History
└── Administration
    ├── Action Queue
    ├── Imports & Integrations
    ├── Notification Centre
    ├── Participant delivery recovery
    ├── Charges and invoice balances          (optional accounting add-on)
    ├── Memberships, member requests, …       (optional member services add-on)
    ├── Competition Audit & Recovery
    │   ├── Role Assignments
    │   ├── Incidents
    │   └── Operational Deviations
    ├── System Health
    │   ├── Retention and Recovery
    │   ├── Retention Evidence
    │   └── Operational Job Health
    └── Journey instrumentation
```

Required advanced path contracts:

```text
Federation > Competitions > Advanced Competition Tools > Create Competition
Federation > Competitions > Advanced Competition Tools > Registration Desk
Federation > Competitions > Advanced Competition Tools > Format Studio
Federation > Competitions > Advanced Competition Tools > Calendar Planner
Federation > Competitions > Advanced Competition Tools > Schedule Planner
Federation > Competitions > Advanced Competition Tools > Schedule Review Queue
Federation > Administration > Competition Audit & Recovery > Role Assignments
Federation > Administration > Action Queue
Federation > Administration > System Health > Operational Job Health
```

## Canonical path contracts

```text
Federation > Competitions > Competitions
Federation > Clubs & People > Clubs
Federation > Clubs & People > Teams
Federation > Match Operations > Game Days
```

`ci/check_competition_ui_workflow.py` verifies the top-level order, these
paths, and that **Competitions** is the only non-advanced entry under
Competitions in the supported application.

## Design rules

- A business journey has one ordinary menu entry. Raw models and duplicate
  queues are advanced or contextual.
- Hiding a menu never changes its action, ACL, record rule, protected command
  or external identifier.
- Contextual deep links are the primary recovery path because they keep the
  active competition, division, game day or team scope.
- The **Advanced Federation Tools** group controls discoverability only. It
  implies Manager, but Manager does not imply it.
- `sports_federation_navigation` owns cross-addon menu visibility and loads
  after its domain dependencies. `sports_federation_app` stays dependency-only;
  domain addons keep owning their actions and records.
- Compliance, immutable snapshots, audit events, operation jobs, retention
  evidence and security configuration remain available to advanced users.
- A new ordinary competition menu needs an explicit product decision and an
  update to `ci/check_competition_ui_workflow.py`.

## Change checklist

1. Prefer a Competition Hub action or form smart button over a new ordinary
   menu.
2. Keep the active business scope in every contextual action domain and
   context.
3. Preserve action XML IDs and model permissions when changing discoverability.
4. Put audit, recovery and raw queues under Advanced Competition Tools or
   Administration.
5. Update this file and the [competition workflow](competition-workflow.md).
6. Run `python3 ci/check_competition_ui_workflow.py` and the browser tours.

## Competition vocabulary

Ordinary competition work follows:
**Competition -> Teams -> Format -> Game days -> Schedule -> Publish -> Play -> Finish**.
Participant sets, structure versions, fixtures, schedule publications and
execution sessions are engine and audit records. They remain available
through Advanced Federation Tools or contextual history, not as primary
workflow concepts. See the [competition model](../architecture/competition-model.md).
