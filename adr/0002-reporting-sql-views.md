# ADR-0002: Reporting SQL Views

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release
Status: Accepted

## Context

Federation reporting combines finance, standings, compliance, notification, planning, and workflow data across multiple addons. Rebuilding those joins in controllers or repeated ORM loops would duplicate logic and create unpredictable performance.

## Decision

Operational and planning projections remain read-only analytical models backed by PostgreSQL views when their data is naturally cross-module or aggregation-heavy.

- SQL-backed report models use `_auto = False`.
- View definitions are recreated deterministically from `init()` or the repository's approved view helper.
- Controllers and exports consume report models instead of embedding substantial SQL or cross-module aggregation logic.
- Report models are read-only and must not masquerade as writable business records.
- Heavy reports retain query budgets, representative fixtures, and performance watchpoints.
- SQL view changes are upgrade-sensitive and require migration review evidence.
- A normal stored Odoo model is preferred when the data has its own lifecycle or must be edited.

## Consequences

- Cross-module reporting logic remains centralized.
- Export and operator surfaces share the same projection semantics.
- View dependencies and upgrade order require explicit review.
- Maintainers must preserve query plans, migration safety, and read-only behavior.
