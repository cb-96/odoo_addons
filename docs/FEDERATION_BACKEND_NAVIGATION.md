# Federation Backend Navigation

Owner: Federation Platform Team
Last verified against menu XML: 2026-10-10
Review cadence: Every release

## Goal

The normal competition journey has one discoverable entry: **Federation > Competitions > Competition Hub**. Opening a season competition resumes the same workspace and promotes exactly one next action. Operators do not need to choose between registration, format, calendar, scheduling, approval, or raw-record menus.

The underlying domain actions are not removed. They remain available through contextual links and to users assigned **Advanced Federation Tools**. This preserves recovery, compliance, audit, security, and specialist operations without presenting implementation structure to every operator.

## Stable work areas

The source menu tree retains seven durable responsibility areas:

1. **Competitions**
2. **Clubs & People**
3. **Match Operations**
4. **Publishing**
5. **Finance & Assurance**
6. **Insights**
7. **Administration**

Visibility is role based. A normal manager primarily sees Competition Hub, Clubs & People, and Match-Day Control. Publishing, assurance, insight, administration, and raw competition menus are available to the advanced or specialist groups that own them.

## Ordinary operator map

```text
Federation
├── Competitions
│   └── Competition Hub
├── Clubs & People
│   ├── Club Directory
│   │   ├── Clubs
│   │   └── Teams
│   ├── Players & Licensing
│   ├── Representatives & Access
│   └── Season Registrations
└── Match Operations
    └── Match-Day Control
```

The workspace itself provides contextual actions for teams, format, game days, schedules, publication, rosters, game-day lineups, officials, results, and readiness. Contextual actions keep the active competition scope and therefore replace most global queue menus for ordinary work.

## Advanced and administration map

```text
Federation
├── Competitions
│   ├── Competition Hub
│   ├── Advanced Competition Tools
│   │   ├── Create Competition
│   │   ├── Competition Overview
│   │   ├── Registration Desk
│   │   ├── Format Studio
│   │   ├── Calendar Planner
│   │   ├── Generate Competition Schedule
│   │   ├── Schedule Planner
│   │   └── Schedule Review Queue
│   ├── Seasons
│   ├── Season Competitions
│   ├── Competition Templates
│   ├── Format Templates
│   ├── Rules & Policies
│   └── Competition Records
├── Match Operations
│   ├── Match-Day Control
│   ├── Matches
│   ├── Game-Day Lineups
│   ├── Venues
│   ├── Officiating
│   └── Discipline
├── Publishing
├── Finance & Assurance
├── Insights
└── Administration
    ├── Action Queue
    ├── Notification Centre
    ├── Imports & Integrations
    ├── Competition Audit & Recovery
    │   └── Role Assignments
    └── System Health
        └── Operational Job Health
```

Required advanced path contracts include:

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

## Design rules

- A business journey has one ordinary menu entry. Raw models and duplicate queues are advanced or contextual.
- Hiding a menu never changes its action, ACL, record rule, protected command, or external identifier.
- Contextual deep links are the primary recovery path because they keep the active competition, division, game day, or team scope.
- The **Advanced Federation Tools** group controls discoverability only. It implies Manager but Manager does not imply it.
- The focused `sports_federation_navigation` integration addon owns cross-addon menu visibility and is loaded after its domain dependencies. `sports_federation_app` remains dependency-only; domain addons continue to own their actions and records.
- Compliance, immutable snapshots, audit events, operation jobs, retention evidence, and security configuration remain available to advanced users.
- New ordinary competition menus require an explicit product decision and an update to `ci/check_competition_ui_workflow.py`.

## Canonical path contracts

```text
Federation > Competitions > Competition Hub
Federation > Clubs & People > Club Directory > Clubs
Federation > Clubs & People > Club Directory > Teams
Federation > Match Operations > Match-Day Control
```

The static navigation contract also verifies that Competition Hub is the only non-advanced direct child of Competitions in the supported aggregate application.

## Change checklist

1. Prefer a workspace action or form smart button over a new ordinary menu.
2. Keep the active business scope in every contextual action domain and context.
3. Preserve action XML IDs and model permissions when changing discoverability.
4. Put audit, recovery, and raw queues under Advanced Competition Tools or Administration.
5. Update this file and `docs/COMPETITION_UI_WORKFLOW.md`.
6. Run `python3 ci/check_competition_ui_workflow.py` and the browser tours.
