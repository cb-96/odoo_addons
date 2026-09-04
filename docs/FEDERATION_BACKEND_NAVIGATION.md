# Federation Backend Navigation

Owner: Federation Platform Team
Last verified against menu XML: 2026-09-04
Review cadence: Every release

## Goal

The Federation backend is organized around operator intent, not addon names or implementation layers. A user should be able to decide where to go from the business task they are performing. The root navigation therefore has seven stable work areas:

1. **Competitions**: define, create, register, structure, schedule, and review competitions.
2. **Clubs & People**: maintain clubs, teams, players, licenses, representatives, and season registrations.
3. **Match Operations**: run match days and manage fixtures, match sheets, venues, officials, and discipline.
4. **Publishing**: expose approved schedules, standings, and editorial content.
5. **Finance & Assurance**: manage finance, compliance, and governed exceptions.
6. **Insights**: review readiness, performance, assurance signals, trends, and scheduled reports.
7. **Administration**: process operational tasks, integrations, notifications, retention, and technical job health.

## Design rules

- Root tabs represent durable business responsibilities. They must not mirror addon names.
- A record has one primary navigation home. Cross-links on forms may provide shortcuts, but duplicate root entries are avoided.
- Daily workflow entries precede configuration and technical records.
- Technical and audit records remain available, but are grouped at the end of their owning area.
- Manager-only items stay role-gated. Reparenting a menu must not broaden its groups or model access.
- Empty compatibility categories are not retained. Existing XML IDs are reused where practical so upgrades move menus instead of creating duplicates.
- New menus must fit one of the seven work areas. Adding another root tab requires an update to this document and the navigation contract check.

## Intended menu map

```text
Federation
├── Competitions
│   ├── Seasons
│   ├── Season Competitions
│   ├── Competition Operations
│   │   ├── Create Competition
│   │   ├── Competition Overview
│   │   ├── Registration Desk
│   │   ├── Format Studio
│   │   ├── Calendar Planner
│   │   ├── Schedule Planner
│   │   ├── Schedule Review Queue
│   │   └── Audit & Technical Records
│   ├── Competition Templates
│   ├── Format Templates
│   ├── Rules & Policies
│   └── Competition Records
├── Clubs & People
│   ├── Club Directory
│   ├── Players & Licensing
│   ├── Representatives & Access
│   └── Season Registrations
├── Match Operations
│   ├── Match-Day Control
│   ├── Matches
│   ├── Match Sheets
│   ├── Officiating
│   ├── Venues
│   └── Discipline
├── Publishing
│   ├── Approved Schedules
│   ├── Schedule Publications
│   ├── Standings
│   └── Public Editorial
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
    ├── Notification Centre
    ├── Imports & Integrations
    └── System Health
```

Menus hidden by security groups are omitted for users who do not own that responsibility. The structure, labels, and ordering remain the same for every role.

## Canonical path contracts

The following operator paths are release contracts and are checked against the XML menu tree:

```text
Federation > Competitions > Seasons
Federation > Competitions > Season Competitions
Federation > Competitions > Competition Operations > Create Competition
Federation > Competitions > Competition Operations > Competition Overview
Federation > Competitions > Competition Operations > Registration Desk
Federation > Competitions > Competition Operations > Format Studio
Federation > Competitions > Competition Operations > Calendar Planner
Federation > Competitions > Competition Operations > Schedule Planner
Federation > Competitions > Competition Operations > Schedule Review Queue
Federation > Clubs & People > Club Directory > Clubs
Federation > Clubs & People > Club Directory > Teams
Federation > Match Operations > Match-Day Control
Federation > Match Operations > Matches
Federation > Match Operations > Match Sheets
Federation > Publishing > Approved Schedules
Federation > Publishing > Schedule Publications
Federation > Publishing > Standings
Federation > Finance & Assurance > Finance
Federation > Finance & Assurance > Compliance
Federation > Finance & Assurance > Governance
Federation > Insights > Reports & Insights > Overview & Readiness > Operational Health
Federation > Administration > Action Queue
Federation > Administration > System Health > Operational Job Health
```

## Ownership guidance

- Competition lifecycle records belong under **Competitions**, even when implemented by separate registration, format, calendar, or scheduling addons.
- Live execution records belong under **Match Operations**. Match-Day Control is intentionally not duplicated under Competitions.
- Approved output and public visibility controls belong under **Publishing**.
- Compliance and governance are assurance activities, not system administration.
- Reports are separated from operational administration to prevent the Administration tab becoming a miscellaneous catch-all.
- Imports, delivery logs, retention evidence, and background-job recovery remain under **Administration** because they support the platform rather than one business workflow.

## Change checklist

When adding or moving a backend menu:

1. Select its primary operator intent and owning work area.
2. Place daily actions before configuration and technical records.
3. Preserve security groups and action access.
4. Update `docs/COMPETITION_UI_WORKFLOW.md` if the competition journey changes.
5. Update `ci/check_competition_ui_workflow.py` when a required path or root work area changes.
6. Run the menu contract check and the affected addon tests.
