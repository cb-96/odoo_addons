# Sports Federation Club Roles and Portal

Version: 19.0.4.1.0
Owner: Federation Platform Team
Last reviewed: 2026-10-04
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

## competition portal

The active competition portal is edition-based. Participation comes from
competition entries and finalized participant sets. Match-day schedule data is
rendered only from each match day's current live publication. Draft schedules,
review evidence and superseded publications are intentionally unavailable.

Club representatives can create entries only for teams in their current portal
scope. Registration submission uses the selected window and validates its open
dates, division eligibility, duplicate entry, and capacity before creating or
reusing an entry. Representatives can update the submission note on returned or
rejected entries and resubmit them;
draft, submitted, or rejected entries can be withdrawn. A withdrawn entry is
reused if the same team submits again for that window, preserving the one-entry
per-team constraint. Review notes are visible on the entry detail page.

This portal is a participant workspace, not a competition organizer console.
Club-scoped entry, roster, and operational follow-up remain separate from
edition-wide federation assignments. Federation roles retain format design and
freeze, calendar/scheduling ownership, independent schedule approval, and
publication authority.

Primary routes:

- `/my/competitions`
- `/my/competition-entries`
- `/my/competition-entries/<id>`
- `/my/competition-entries/<id>/resubmit` (POST)
- `/my/competition-entries/<id>/withdraw` (POST)
- `/my/match-days`
- `/sports/match-days/<id>/operations`

Legacy tournament workspace routes are redirect-only and render no V1 data.
The backend tournament-registration action is loaded before the menus that use
it, so a fresh module install and an upgrade both build the registration menu
without relying on stale database metadata.


## Accessible error recovery and focus management

Portal forms move keyboard focus to server-rendered error summaries, connect
invalid controls to that summary with `aria-describedby`, and announce the
summary through an assertive live region. Bootstrap confirmation dialogs move
focus into the dialog and restore it to the invoking control when closed.
Keyboard focus uses a visible outline that does not depend on color-only status
cues. The focused accessibility suite covers these contracts together with
mobile table and action wrapping.


## Club competition data tutorial

Club representatives use **My Account > Data API** (`/my/data-api`) for live URLs, curl and JavaScript examples, privacy rules, and caching guidance.


## Owned portal command boundaries

Result approval and contesting call `federation.result.commands`, which
re-resolves the target inside the authenticated representative's current club
scope before applying an elevated transition. Season-registration cancellation
uses `federation.portal.privilege.portal_call` with an explicit club domain.
Competition entry creation follows a team-scope assertion before elevation;
correction, resubmission, and withdrawal pass through
`federation.portal.privilege` with an explicit team/window scope. The
public competition registration page and the club portal use the same entry
submission command; the public-site addon therefore depends on the portal
ownership services and registration owner.
Controllers may keep publication-gated or ownership-scoped elevated reads, but
must not mutate records that originated from those reads directly.

## Result handoff queues

Result follow-up tasks identify whether the next action belongs to the Result Submitter, Result Verifier, or Result Approver. Queue guidance names the required action while the underlying result commands continue to enforce separation of duties.

## Unified action projection (19.0.7.3.0)

`federation.operation.task` remains the only persistent task projection. It now also emits one missing-parental-consent task per affected roster line and one shared game-day-lineup task per team/day scope. Parental-consent tasks open the player's canonical approval action. Lineup tasks open the shared match-sheet source. Source models remain authoritative and stale projections still complete through the existing idempotent synchronization.
