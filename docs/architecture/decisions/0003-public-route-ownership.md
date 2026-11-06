# ADR-0003: Public Route Ownership

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release
Status: Accepted

## Context

Public competition pages, feeds, calendars, registration entry points, and compatibility aliases can collide when several addons define overlapping controllers. Numeric and tournament-named legacy routes also create ambiguity about the canonical public contract.

## Decision

Public route ownership is competition-first and module-explicit:

- `/competitions` and `/competitions/<edition-slug>` are the canonical public page routes, and `/api/v1/competitions` is the canonical public data feed.
- `sports_federation_public_site` owns canonical public competition pages, match-day publication views, feeds and calendars.
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

## Revision history

- 2026-11-06: wording aligned with the completed route cutover. The former
  tournament-named routes and feeds are removed; only the competition namespace
  is documented (enforced by `ci/check_public_route_cutover_docs.py`).
