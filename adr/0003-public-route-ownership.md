# ADR-0003: Public Route Ownership

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

## Status

Accepted

## Context

Public tournament, feed, and schedule routes span browser pages, JSON feeds,
and compatibility aliases. Those surfaces were historically prone to drift when
multiple modules exposed overlapping controllers or when older numeric routes
remained undocumented.

## Decision

Public route ownership follows a tournament-first and module-explicit model:

- `sports_federation_public_site` owns the canonical public tournament pages,
  feed routes, and publication helpers
- compatibility aliases may remain temporarily, but the canonical slug-first
  routes must be the only routes documented for new integrations
- public routes stay read-only and must enforce publication toggles such as
  `website_published`, `show_public_results`, and `show_public_standings`
- route inventory, contract docs, and smoke coverage are treated as part of the
  ownership boundary, not optional documentation

## Consequences

- controller precedence becomes easier to review because ownership is explicit
- new public surfaces must update route inventory and compatibility docs in the
  same change set
- shadow public controllers should be retired rather than left as silent
  duplicates