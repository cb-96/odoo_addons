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

The administrator account is a member of **Advanced Federation Tools** by
default, so it always sees the advanced map. Test the ordinary map with a user
that only has the Federation **Manager** group.

## Work areas

The **Federation** application opens on **Competitions > Competitions**, the
Competition Hub. It has these top-level work areas, in this order:

- **Competitions**: the Competition Hub and the Review Queue, plus planning tools and raw records (advanced).
- **Clubs & People**: clubs, teams, players, club representatives and membership work.
- **Match Operations**: game days and court operation; courts and venues, officiating and discipline (advanced).
- **Publishing**: schedule review, publication and public editorial content.
- **Finance & Assurance**: finance, compliance and governance overrides (advanced).
- **Reporting**: the operational health dashboard; checklists and performance reports (advanced).
- **Administration**: configuration, data exchange, notifications and system records (advanced).

## Ordinary manager map

A Federation Manager without specialist groups sees eleven entries:

```text
Federation
├── Competitions
│   ├── Competitions            (landing page)
│   └── Review Queue
├── Clubs & People
│   ├── Clubs
│   ├── Teams
│   ├── Players
│   └── Club Representatives
├── Match Operations
│   ├── Game Days
│   └── Run This Court
├── Publishing
│   ├── Schedules to Review
│   └── Public Editorial
└── Reporting
    └── Operational Health
```

The **Review Queue** lists decisions that are waiting for the federation
across all competitions: submitted competition entries, submitted game-day
line-ups and results to verify or approve. It refreshes the task projection
when opened. Club work, such as referee nominations, stays in the club portal
and the **Duty Coverage Board**.

The Competition Hub provides contextual actions for creating competitions,
teams, format, game days, schedule generation, publication, rosters, game-day
line-ups, officials, results and readiness. Contextual actions keep the active
competition scope and replace most global queue menus for ordinary work.

## Advanced map

Users in **Advanced Federation Tools** additionally see these sections. The
**System** section is only shown in developer mode. Entries marked *(optional)*
come from addons that are not part of the default installation.

```text
Federation
├── Competitions
│   ├── Planning Tools
│   │   ├── Saved Drafts
│   │   ├── Registration Desk
│   │   ├── Format Studio
│   │   ├── Calendar Planner
│   │   └── Schedule Planner
│   └── Records
│       ├── Seasons
│       ├── Season Registrations
│       ├── Divisions
│       ├── Matches
│       ├── Game-Day Lineups
│       └── Standings
├── Clubs & People
│   └── Membership                          (optional member services)
│       ├── Memberships, Member Requests, Renewals to Review
│       ├── Guardian Claims, Identity Review Queue
│       └── Family Relationships, Membership Retention
├── Match Operations
│   ├── Courts & Venues
│   │   ├── Venues
│   │   ├── Court Operators
│   │   └── Court Recovery
│   ├── Scoring Phones                      (prepared phones; revoke)
│   ├── Club Scorers                        (club-nominated scorers)
│   ├── Officiating
│   │   ├── Duty Coverage Board
│   │   ├── Referee Assignments
│   │   ├── Club Duties
│   │   ├── Referees
│   │   └── Reimbursements
│   └── Discipline
│       ├── Incidents
│       ├── Cases
│       └── Suspensions
├── Publishing
│   ├── Ready to Publish                    (schedule approvers)
│   └── Published Schedules                 (schedule approvers)
├── Finance & Assurance
│   ├── Finance
│   │   ├── Finance Events
│   │   ├── Charges & Invoice Balances      (optional accounting)
│   │   └── Season Budgets
│   ├── Compliance
│   │   ├── Submissions
│   │   ├── Checks
│   │   └── Check History
│   └── Override Requests
├── Reporting
│   ├── Operator Checklist
│   ├── Standings Reconciliation
│   ├── Trend Snapshots
│   └── Performance
│       ├── Operational KPIs, Season Portfolio, Participation
│       ├── Club Performance, Officiating, Referee Coverage
│       └── Compliance, Club Compliance Summary, Finance
└── Administration
    ├── Configuration
    │   ├── Competition Templates, Format Templates, Rule Sets
    │   ├── Club Role Types, Playing Area Capabilities
    │   ├── Fee Types, Fee Schedules, Document Requirements
    │   └── Report Schedules
    ├── Data Exchange
    │   ├── Import Clubs, Seasons, Players, Teams, Tournament Participants
    │   ├── Import History, Import Templates
    │   └── Integration Contracts, Integration Partners, Inbound Deliveries
    ├── Notifications
    │   ├── Delivery Recovery
    │   ├── Delivery History
    │   └── Notification Outcomes
    └── System                              (developer mode)
        ├── Operational Jobs, Standings Recompute Queue
        ├── Retention Policies, Retention Evidence
        ├── Competition Role Assignments, Game-Day Incidents, Operational Deviations
        ├── Member Changes, Duplicate Person Decisions, Member Evidence History
        └── Portal Audit, Token Rotation Audit, Journey Instrumentation
```

Required advanced path contracts:

```text
Federation > Competitions > Planning Tools > Registration Desk
Federation > Competitions > Planning Tools > Format Studio
Federation > Competitions > Planning Tools > Calendar Planner
Federation > Competitions > Planning Tools > Schedule Planner
Federation > Publishing > Schedules to Review
Federation > Administration > Configuration > Rule Sets
Federation > Administration > System > Operational Jobs
Federation > Administration > System > Competition Role Assignments
```

## Canonical path contracts

```text
Federation > Competitions > Competitions
Federation > Competitions > Review Queue
Federation > Clubs & People > Clubs
Federation > Clubs & People > Teams
Federation > Match Operations > Game Days
Federation > Reporting > Operational Health
```

## Screens without a menu

These actions are kept but have no menu because a form, the hub or a report
already opens them in context:

| Screen | Opened from |
|---|---|
| Create Competition, Generate Competition Schedule | Competition Hub |
| Competition Overview, Season Competitions | Competition Hub, competition template form |
| Stages, Groups | Division form |
| Points, tie-break, eligibility and qualification rules | Rule set form |
| Licences | Player form |
| Referee certifications | Referee form |
| Plan Match-Day Officials | Competition planner, game day |
| Sanctions | Disciplinary case form |
| Venue constraint windows | Venue form |
| Override outcomes | Override request form |
| Representative Workspace | Club Representatives (same records) |
| Workflow, finance and notification exceptions, compliance remediation, finance reconciliation, season checklists | Operator Checklist rows |

## Design rules

`ci/check_competition_ui_workflow.py` resolves the menus in install order and
enforces these rules:

- At most three levels below **Federation**: area > section > item.
- A menu with child menus has no action; Odoo cannot open it from the menu bar.
- No empty menu folders, no duplicate names in one dropdown, and no action
  exposed by more than one menu.
- The app opens on the Competition Hub for every role.
- An ordinary manager sees at most twelve entries, and **Competitions** and
  **Review Queue** are the only ordinary entries under Competitions.
- The top-level order and the path contracts above.

In addition:

- Hiding a menu never changes its action, ACL, record rule, protected command
  or external identifier.
- `sports_federation_navigation` is the single map of names, parents, ordering
  and groups for the addons it depends on. It assigns groups with
  `(6, 0, ...)` so upgrades converge on the map. Optional addons
  (`sports_federation_accounting`, `sports_federation_member_services`) place
  their own menus in the sections defined there or in `sports_federation_base`.
- The **Advanced Federation Tools** group controls discoverability only. It
  implies Manager, but Manager does not imply it.
- Audit, recovery and technical records belong under **Administration >
  System** (developer mode).

## Change checklist

1. Prefer a Competition Hub action or form smart button over a new menu.
2. Keep the active business scope in every contextual action domain and
   context.
3. Preserve action XML IDs and model permissions when changing discoverability.
4. Add the menu's final placement to `sports_federation_navigation/views/navigation.xml`.
5. Update this file and the [competition workflow](competition-workflow.md).
6. Run `python3 ci/check_competition_ui_workflow.py` and the browser tours.

## Competition vocabulary

Ordinary competition work follows:
**Competition -> Teams -> Format -> Game days -> Schedule -> Publish -> Play -> Finish**.
Participant sets, structure versions, fixtures, schedule publications and
execution sessions are engine and audit records. They remain available
through Advanced Federation Tools or contextual history, not as primary
workflow concepts. See the [competition model](../architecture/competition-model.md).
