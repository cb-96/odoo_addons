# ADR-0003: Public Route Ownership

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release
Status: Accepted

## Context

Public tournament pages, feeds, calendars, registration entry points, and compatibility aliases can collide when several addons define overlapping controllers. Numeric legacy routes also create ambiguity about the canonical public contract.

## Decision

Public route ownership is tournament-first and module-explicit:

- `sports_federation_public_site` owns canonical public tournament pages, feeds, calendars, and publication helpers.
- Slug-first routes are canonical for new consumers.
- Numeric and competition-named routes may remain only as documented compatibility aliases with an owner and review date.
- Public reads enforce applicable publication controls such as `website_published`, `show_public_results`, and `show_public_standings`.
- Public write entry points use a model-owned request boundary and must not broaden portal or backend privileges.
- Route inventory, OpenAPI contracts, compatibility notes, and smoke coverage are part of the ownership boundary.
- Duplicate or shadow public controllers are removed rather than kept as silent fallbacks.

## Consequences

- Controller precedence and deprecation become reviewable.
- New public surfaces must update route and contract documentation in the same change.
- Compatibility routes carry an explicit maintenance cost and sunset decision.
- Publication defaults remain deny-by-default.
