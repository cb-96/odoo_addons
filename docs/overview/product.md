# Product overview

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

The Sports Federation platform is a set of Odoo 19 addons that runs a sports
federation: clubs, teams, seasons, players and licences, competitions from
registration to final standings, match-day operations, officiating, rosters,
results, a club portal, a public website, and the reporting, finance and
governance work around them.

## Who uses it

| Role | Main surface | Typical work |
| --- | --- | --- |
| Federation manager / competition organiser | Back office, **Federation > Competitions** | Create competitions, select teams, choose formats, plan game days, publish schedules, finish competitions |
| Schedule approver | Back office review queue | Independently review and publish schedules when the competition requires it |
| Match-day manager / court operator | **Match Operations > Game Days**, **Run this court**, mobile match-day pages | Open game days, record scores, handle incidents and delays |
| Results officer | Back office and `/my/work/reviews` | Verify and approve results, handle corrections |
| Club representative | Club portal (`/my/club`, `/my/work`) | Register teams, maintain rosters and line-ups, nominate officials, upload documents |
| Official (referee, table official) | Portal assignments and mobile match day | Accept assignments, request check-in |
| Member or guardian | `/my/family` (optional member services) | Renew memberships, upload requested evidence |
| Public visitor and partner systems | Public website, public feeds, managed integration API | Follow competitions, consume published data |

## Product surfaces

- **Core data:** clubs, teams, seasons, people, licences, rules and venues.
- **Competition operations:** registrations, formats, fixtures, calendar,
  scheduling, approval and publication, match-day control, results and
  standings.
- **Club operations:** rosters and line-ups, officiating and duty coverage,
  compliance documents and discipline.
- **Club portal:** representative access, club-owned tasks and self-service.
- **Public experience:** published competitions, schedules, results,
  standings, brackets and stable public feeds.
- **Platform operations:** reporting, imports and integrations, notifications,
  governance overrides, finance handoff, retention and recovery.

These are product boundaries, not a reason to create more addons. See the
[architecture overview](../architecture/overview.md) for the addon structure
and the [module catalogue](modules.md) for the addon list.

## Default product and optional capabilities

The default product, installed through `sports_federation_app`, is the
competition lifecycle, publication, match-day operations, rosters,
officiating, standings, portal and public site, together with the platform
operations that support them.

`sports_federation_member_services` (member and family services) and
`sports_federation_accounting` (native invoice linkage) are optional and are
not installed by the application entry point. `sports_federation_demo` is for
development and demonstrations only.

An optional capability stays separate only when it is legally required,
independently deployed, actively used, separately owned, or materially
reduces operational risk.

## Scope review

Review optional addons with:

```bash
python3 ci/audit_product_scope.py --json artifacts/product-scope.json
```

For each optional addon, record an owner and one decision: keep, consolidate,
disable or retire. Absence of usage evidence is not evidence that deletion is
safe. Check database records, XML IDs, routes, scheduled jobs and downstream
dependencies before retiring anything.

The report catalogue model and view are not part of the installed product.
Review existing reports through their owning reporting models, menus,
schedules, exports and retention requirements before consolidating or retiring
a report.

## Release status

The platform is feature-complete for its first release candidate and scope is
frozen except for release blockers. The [roadmap](../roadmap.md) lists the
remaining qualification work and known gaps.
