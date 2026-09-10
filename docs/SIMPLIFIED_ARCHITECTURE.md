# Simplified Federation Architecture

Owner: Federation Platform Team

## Decision

The platform has one supported installation entry point:
`sports_federation_app`.

The existing domain addons remain implementation units for now. Immediate
physical merging would complicate migrations and add risk without simplifying
the operator experience. Consolidation is allowed only when it removes real
coupling and has a rehearsed upgrade path.

## Product surfaces

- **Core data:** clubs, teams, seasons, people, rules, and venues.
- **Competition operations:** registrations, formats, fixtures, calendar,
  scheduling, approval, match-day control, results, and standings.
- **Club operations:** rosters, officiating, compliance, and discipline.
- **Club portal:** representative access and club-owned tasks.
- **Public experience:** published competitions, schedules, results, standings,
  and stable public feeds.
- **Platform operations:** reporting, imports, integrations, notifications,
  governance, finance handoff, retention, and recovery.

These are product boundaries, not a reason to create more addons.

## KISS rules

1. Put behavior in the addon that owns the record being changed.
2. Use one explicit command for every protected workflow transition.
3. Keep controllers thin: parse input, call a model command, render output.
4. Do not add a second model for a concept already represented canonically.
5. Do not add a new addon unless it can be installed or upgraded independently.
6. Use normal ACLs and record rules first; narrowly scoped elevation is the exception.
7. Published schedules, approved results, and audit evidence are immutable.
8. Side effects must not roll back business decisions.
9. Add a migration only when persisted data or ownership changes.
10. Prefer deleting obsolete compatibility code over adding another abstraction.

## Supported installation

Production:

```bash
odoo -d DATABASE -i sports_federation_app --stop-after-init
```

Development and demonstrations:

```bash
odoo -d DATABASE -i sports_federation_app,sports_federation_demo \
  --stop-after-init
```

Existing databases continue upgrading their installed domain addons. The app
addon is additive and does not move or rewrite data.

## Consolidation rule

A physical addon merge is justified only when:

- the addons cannot be deployed independently;
- their models share one lifecycle owner;
- the merge removes a dependency or duplicate implementation;
- model names, tables, XML IDs, and security identifiers remain stable;
- fresh install, same-version upgrade, supported-version upgrade, and rollback pass.
