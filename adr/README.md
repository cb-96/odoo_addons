# Architecture Decision Records

Last updated: 2026-08-20
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Architecture Decision Records document accepted cross-module decisions that would otherwise be easy to rediscover or accidentally reverse.

## Accepted ADRs

- [ADR-0001: Portal Trust Boundaries](0001-portal-trust-boundaries.md)
- [ADR-0002: Reporting SQL Views](0002-reporting-sql-views.md)
- [ADR-0003: Public Route Ownership](0003-public-route-ownership.md)

## When to add or update an ADR

Add or update an ADR when a change alters a durable boundary, including:

- privilege elevation and ownership enforcement
- public or partner-facing route ownership
- persistence or reporting architecture
- cross-module extension contracts
- release or migration behavior with long-term consequences

Do not use ADRs for implementation checklists, temporary release tasks, or module-local notes. Supersede an accepted ADR instead of silently rewriting its original decision history.
