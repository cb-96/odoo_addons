# ADR-0002: Reporting SQL Views

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

## Status

Accepted

## Context

The reporting module aggregates finance, standings, compliance, notification,
and workflow data across multiple addons. Those rollups are too expensive and
too cross-cutting to duplicate in controllers or ad hoc ORM loops.

## Decision

Operational and planning reports will remain read-only analytical models backed
by PostgreSQL views:

- report models use `_auto = False` and rebuild their SQL view definitions in
  `init()`
- export controllers and operator screens consume the reporting models instead
  of issuing inline SQL or assembling large cross-module joins in controllers
- the heaviest planning reports keep explicit query budgets and `EXPLAIN`
  watchpoints in CI so plan regressions are visible before release
- SQL view changes are treated as upgrade-sensitive and must travel with
  migration review evidence

## Consequences

- large cross-module reporting logic stays centralized in one reporting layer
- read-only analytical surfaces remain easier to reason about than mixed ORM and
  controller implementations
- maintainers must preserve migration discipline and performance baselines when a
  reporting view changes