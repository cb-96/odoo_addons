# Module catalogue

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

The repository contains one addon per domain, named `sports_federation_<domain>`.
Each addon's `README.md` documents its models, behaviour and configuration.
Ownership is recorded in [`MODULE_OWNERS.yaml`](../../MODULE_OWNERS.yaml) and
validated by `ci/check_module_owners.py`; keep this table in sync with it when
an addon is added, removed or changes owner.

Install the production platform through `sports_federation_app`. The other
addons are implementation and upgrade units; install them individually only
for development or diagnosis. See the [architecture overview](../architecture/overview.md)
for the dependency direction and the rules for adding or merging addons.

## Entry points

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_app`](../../sports_federation_app/README.md) | Single supported installation entry point for the production platform | Federation Platform Team | entry point |
| [`sports_federation_navigation`](../../sports_federation_navigation/README.md) | Cross-addon ordinary and advanced menu discoverability | Federation Platform Team | yes |
| [`sports_federation_demo`](../../sports_federation_demo/README.md) | Demo-only sample federation data and onboarding fixtures | Federation Platform Team | no |

## Core data

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_base`](../../sports_federation_base/README.md) | Core clubs, teams, seasons, and shared registration models | Federation Platform Team | yes |
| [`sports_federation_people`](../../sports_federation_people/README.md) | Player master data, licenses, and person records | Federation Platform Team | yes |
| [`sports_federation_rules`](../../sports_federation_rules/README.md) | Rule sets, points systems, tie-breaks, and qualification logic | Federation Competition Operations | yes |
| [`sports_federation_venues`](../../sports_federation_venues/README.md) | Venue master data and schedule-level venue ownership | Federation Competition Operations | yes |

## Competition operations

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_tournament`](../../sports_federation_tournament/README.md) | Tournaments, stages, rounds, matches, and registrations | Federation Competition Operations | yes |
| [`sports_federation_competition_core`](../../sports_federation_competition_core/README.md) | Competition identity, roles, lifecycle, and events | Federation Competition Operations | yes |
| [`sports_federation_registration`](../../sports_federation_registration/README.md) | Competition registration queues and finalized participant sets | Federation Competition Operations | yes |
| [`sports_federation_format`](../../sports_federation_format/README.md) | Versioned competition structures and stage graphs | Federation Competition Operations | yes |
| [`sports_federation_calendar`](../../sports_federation_calendar/README.md) | Physical match days, capacity, slots, and timelines | Federation Competition Operations | yes |
| [`sports_federation_scheduling`](../../sports_federation_scheduling/README.md) | Deterministic fixture assignment, validation, and fairness | Federation Competition Operations | yes |
| [`sports_federation_schedule_approval`](../../sports_federation_schedule_approval/README.md) | Schedule review and immutable publication snapshots | Federation Competition Operations | yes |
| [`sports_federation_setup_flow`](../../sports_federation_setup_flow/README.md) | Guided competition setup and planner readiness projections | Federation Competition Operations | yes |
| [`sports_federation_matchday`](../../sports_federation_matchday/README.md) | Live match-day operations and incident control | Federation Competition Operations | yes |
| [`sports_federation_live_workspace`](../../sports_federation_live_workspace/README.md) | Scoped court capture, recovery evidence and governed visual planning | Federation Platform Team | yes |
| [`sports_federation_result_control`](../../sports_federation_result_control/README.md) | Result approval, dispute handling, and standings publication control | Federation Competition Operations | yes |
| [`sports_federation_standings`](../../sports_federation_standings/README.md) | Standings computation, freezing, and publication feeds | Federation Competition Operations | yes |

## Club operations

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_rosters`](../../sports_federation_rosters/README.md) | Team roster management, eligibility checks, and roster workflows | Federation Competition Operations | yes |
| [`sports_federation_officiating`](../../sports_federation_officiating/README.md) | Referee assignments, officiating availability, and match staffing | Federation Competition Operations | yes |
| [`sports_federation_duty_coverage`](../../sports_federation_duty_coverage/README.md) | Schedule-linked duty coverage, individual responses, attendance and replacement evidence | Federation Competition Operations | yes |
| [`sports_federation_compliance`](../../sports_federation_compliance/README.md) | Compliance requests, review queues, and evidence intake | Federation Finance and Compliance | yes |
| [`sports_federation_discipline`](../../sports_federation_discipline/README.md) | Disciplinary cases, sanctions, and review workflows | Federation Finance and Compliance | yes |

## Portal and public experience

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_portal`](../../sports_federation_portal/README.md) | Club representative portal dashboards and registration workflows | Federation Portal and Public Experience | yes |
| [`sports_federation_public_site`](../../sports_federation_public_site/README.md) | Public website routes, publication toggles, and SEO-facing pages | Federation Portal and Public Experience | yes |

## Platform operations

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_notifications`](../../sports_federation_notifications/README.md) | Notification rules, outbound delivery, and communication hooks | Federation Platform Team | yes |
| [`sports_federation_reporting`](../../sports_federation_reporting/README.md) | SQL-backed operational reports, exports, and operator checklists | Federation Finance and Compliance | yes |
| [`sports_federation_import_tools`](../../sports_federation_import_tools/README.md) | CSV import wizards, managed integration contracts, and delivery staging | Federation Platform Team | yes |
| [`sports_federation_governance`](../../sports_federation_governance/README.md) | Governance workflows, approvals, and shared operational controls | Federation Platform Team | yes |
| [`sports_federation_finance_bridge`](../../sports_federation_finance_bridge/README.md) | Finance events, fees, and accounting-facing hooks | Federation Finance and Compliance | yes |

## Optional add-ons

| Module | Responsibility | Primary owner | Installed by `sports_federation_app` |
| --- | --- | --- | --- |
| [`sports_federation_member_services`](../../sports_federation_member_services/README.md) | Verified personal relationships and scoped membership requests | Federation Platform Team | no |
| [`sports_federation_accounting`](../../sports_federation_accounting/README.md) | Native invoice linkage without a parallel accounting ledger | Federation Finance and Compliance | no |

## Dependency layers

Each addon depends only on addons in lower layers. The table is derived from
the manifest `depends` lists, which remain the final authority;
`ci/check_module_dependency_drift.py` detects drift.

| Level | Addons |
| --- | --- |
| 0 | `base` |
| 1 | `people`, `rules` |
| 2 | `tournament` |
| 3 | `competition_core`, `governance`, `import_tools`, `result_control`, `standings`, `venues` |
| 4 | `registration` |
| 5 | `format` |
| 6 | `calendar` |
| 7 | `scheduling` |
| 8 | `schedule_approval` |
| 9 | `matchday` |
| 10 | `officiating`, `rosters` |
| 11 | `discipline`, `portal`, `setup_flow` |
| 12 | `compliance`, `finance_bridge`, `public_site` |
| 13 | `accounting`, `member_services`, `notifications` |
| 14 | `demo`, `reporting` |
| 15 | `duty_coverage` |
| 16 | `live_workspace` |
| 17 | `navigation` |
| 18 | `app` |

Lower layers hold master data and the competition chain; higher layers are
surfaces and integrations (portal, public site, reporting, notifications) and
the assembly addons (`navigation`, `app`). An addon may import only from its
declared dependencies.
