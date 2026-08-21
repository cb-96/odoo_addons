# Sports Federation Club Roles and Portal

Version: 19.0.2.2.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Role-oriented self-service portal for club representatives, officials, and tournament operators.

## Primary user journeys

### Club representative

- manage club teams and players
- submit season and tournament registrations
- prepare and activate rosters
- complete match sheets and readiness tasks
- nominate officials
- review result actions and deadlines

### Official

- view assignments
- confirm or decline within the authorized scope
- access relevant match information

### Tournament operator

- use the tournament operations board
- monitor courts, matches, readiness, and action queues
- execute scoped result and operational actions

## Trust boundary

All privileged portal writes must use a model-owned method and the shared `federation.portal.privilege` boundary. Controllers validate input and resolve scope but do not perform raw elevated business writes. See `adr/0001-portal-trust-boundaries.md`.

Every new privileged route requires:

1. positive in-scope coverage
2. negative out-of-scope coverage
3. direct-ID or guessed-record coverage
4. model/helper ownership assertions when elevation is used
5. CSRF enforcement for state-changing browser or JSON-RPC routes

## Portal UX direction

The landing page should remain task-first. Common tasks are teams, registrations, upcoming matches, and action items. Specialist tools should be progressively disclosed instead of presented as an undifferentiated module catalogue.

## Operations board

The board loads through scoped JSON-RPC, supports polling and structured failures, and exposes only matches and actions available to the current user. Server-side checks remain authoritative.

## Tests

The module includes HTTP smoke, ownership, access-denied, team, player, roster, registration, officiating, result, accessibility, mobile, operations-board, and end-to-end portal workflow tests.

## Consolidated documentation

`PORTAL_OWNERSHIP_COVERAGE.md`, `PORTAL_OWNERSHIP_TEST_MATRIX.md`, and `ROADMAP_RC.md` are deleted. Their durable rules are consolidated here and in ADR-0001; the test files are the authoritative live coverage map.
