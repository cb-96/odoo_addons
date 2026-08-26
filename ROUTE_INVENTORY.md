# Route Inventory

Last updated: 2026-08-20
Owner: Federation Platform Team
Last reviewed: 2026-08-23
Review cadence: Every release

## Purpose

This file inventories critical browser, portal, public, reporting, and managed-integration entry points. It is not intended to duplicate every controller decorator. A route belongs here when it is public, partner-facing, privileged, contract-versioned, or operationally important.

The machine-readable route inventory and controller tests remain the authoritative completeness checks. Update this document, route tests, and ownership metadata in the same change.

## Portal and Operations Routes

### Tournament operations board

- `GET /sports/tournament/<tournament_id>/operations`
  - Owner: `sports_federation_portal`
  - Controller: `FederationTournamentOperationsPortal.portal_tournament_operations_page`
  - Downstream boundary: tournament operations access resolver
  - Purpose: authenticated operations-board shell

- `POST /sports/tournament/<tournament_id>/operations/data`
  - Owner: `sports_federation_portal`
  - Controller: `FederationTournamentOperationsPortal.portal_tournament_operations_data`
  - Downstream boundary: `federation.tournament._operations_get_payload`
  - Purpose: scoped JSON-RPC board payload
  - Safeguards: authenticated user, CSRF, model-owned access scope

- `POST /sports/tournament/<tournament_id>/operations/matches/<match_id>/action`
  - Owner: `sports_federation_portal`
  - Controller: `FederationTournamentOperationsPortal.portal_tournament_operations_action`
  - Downstream boundary: tournament operations action service
  - Purpose: result and operational match actions
  - Safeguards: authenticated user, CSRF, tournament and match scope checks

### Club self-service

- `POST /my/teams/new`
  - Owner: `sports_federation_portal`
  - Controller: `FederationClubPortal.portal_my_teams_create`
  - Downstream boundary: `federation.team._portal_create_team`

- `POST /my/players/new`
  - Owner: `sports_federation_portal`
  - Controller: `FederationClubPortal.portal_my_players_create`
  - Downstream boundary: `federation.player._portal_create_player`

- `POST /my/season-registration/new`
  - Owner: `sports_federation_portal`
  - Controller: `FederationRegistrationPortal.portal_season_registration_submit`
  - Downstream boundary: `federation.season.registration._portal_submit_registration_request`

- `POST /my/referee-assignments/<assignment_id>/respond`
  - Owner: `sports_federation_portal`
  - Controller: `FederationOfficiatingPortal.portal_my_referee_assignment_respond`
  - Downstream boundary: assignment portal access and confirmation/decline methods

All portal writes must resolve the request-user scope before calling a model-owned method. Raw controller `sudo()` writes are not an accepted boundary.

## Public Routes

Canonical public competition pages and match-day publication views are owned by `sports_federation_public_site` under `/competitions`. Tournament-named and numeric page routes are compatibility redirects. Versioned tournament feeds and calendars remain supported integration contracts until separately versioned.

Critical public contracts include:

- `GET /api/v1/tournaments/<slug>/feed`
- `GET /tournaments/<slug>/schedule.ics`
- `POST /tournaments/<slug>/register`

Public reads must enforce applicable publication flags. Public registration writes must use the shared registration model boundary.

## Reporting Routes

Authenticated reporting exports are owned by `sports_federation_reporting`:

- `GET /reporting/export/standings/<tournament_id>`
- `GET /reporting/export/participation/<season_id>`
- `GET /reporting/export/finance`
- `GET /reporting/export/finance/events`

Responses must retain their documented contract and version headers.

## Managed Integration Routes

Managed partner routes are owned by `sports_federation_import_tools`:

- `GET /integration/v1/contracts`
- `GET /integration/v1/outbound/finance/events`
- `POST /integration/v1/inbound/<contract_code>/deliveries`

These routes require partner authentication, subscription checks, stable error envelopes, bounded pagination where applicable, and documented idempotency behavior.

## Operator Surfaces

- Competition planning and schedule publication: `sports_federation_scheduling`, `sports_federation_schedule_approval`
- Tournament Operations Board: `sports_federation_portal`
- Reporting Operator Checklist: `sports_federation_reporting`
- Report Schedules: `sports_federation_reporting`
- Inbound Deliveries: `sports_federation_import_tools`

## Review Rules

A route change must include:

1. an explicit owner module
2. authentication and CSRF review
3. model or service write boundary
4. positive and negative access tests
5. route-inventory and OpenAPI updates when contract-facing
6. compatibility and removal notes when replacing an existing route

The previous `/web/login` entry was removed from this inventory because no matching `FederationWebsiteLogin.web_login` implementation was present in the reviewed source snapshot. Re-add it only with an implementation and smoke coverage.

## Portal competition routes

- `GET /my/competitions`: edition-based competition workspace.
- `GET /my/competitions/<edition_id>`: represented-team competition detail.
- `GET /my/match-days`: match days selected through current live publications.
- `GET /my/match-days/<matchday_id>`: club-scoped match-day detail.
- `POST /my/competition-entries/new`: competition entry through the portal privilege boundary.
- `GET /sports/match-days/<matchday_id>/operations`: publication-scoped operations board.
- `POST /sports/match-days/<matchday_id>/operations/data`: current live operations payload.
- `POST /sports/match-days/<matchday_id>/matches/<match_id>/action`: match action constrained to that publication.

The former tournament-workspace and tournament-operations URLs are temporary
redirects and are not data sources.
