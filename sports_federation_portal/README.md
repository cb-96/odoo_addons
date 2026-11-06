# Sports Federation Club Roles and Portal

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Role-oriented self-service portal for club representatives, officials and match-day staff. All portal routes are listed in the [route inventory](../docs/reference/routes.md#club-portal).

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

### Match-day staff

- use the match-day operations board (`/sports/match-days/<matchday_id>/operations`)
- monitor courts, matches, readiness, and action queues
- execute scoped result and operational actions

## Trust boundary

All privileged portal writes must use a model-owned method and the shared `federation.portal.privilege` boundary. Controllers validate input and resolve scope but do not perform raw elevated business writes. See [ADR-0001](../docs/architecture/decisions/0001-portal-trust-boundaries.md); the test files are the authoritative live coverage map.

Every new privileged route requires:

1. positive in-scope coverage
2. negative out-of-scope coverage
3. direct-ID or guessed-record coverage
4. model/helper ownership assertions when elevation is used
5. CSRF enforcement for state-changing browser or JSON-RPC routes

## Portal UX direction

The landing page should remain task-first. Common tasks are teams, registrations, upcoming matches, and action items. Specialist tools should be progressively disclosed instead of presented as an undifferentiated module catalogue.

## Operations board

The match-day operations board loads through scoped JSON-RPC, supports polling and structured failures, and exposes only matches and actions available to the current user. Server-side checks remain authoritative.

## Tests

The module includes HTTP smoke, ownership, access-denied, team, player, roster, registration, officiating, result, accessibility, mobile, operations-board, and end-to-end portal workflow tests.

## Competition portal

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

The former tournament workspace routes have been removed. The backend
tournament-registration action is loaded before the menus that use it, so a
fresh install and an upgrade both build the registration menu without relying
on stale database metadata.


## Accessible error recovery and focus management

Portal forms move keyboard focus to server-rendered error summaries, connect
invalid controls to that summary with `aria-describedby`, and announce the
summary through an assertive live region. Bootstrap confirmation dialogs move
focus into the dialog and restore it to the invoking control when closed.
Keyboard focus uses a visible outline that does not depend on color-only status
cues. The focused accessibility suite covers these contracts together with
mobile table and action wrapping.


## Club representative home

**My account** (`/my` and `/my/home`) opens the club overview for club
representatives: one page with teams, players, rosters, competitions,
game-day preparation, officials, results, compliance and club details.
**My work** (`/my/work`) stays one click away and links back with
**Club overview**. Users without a club representative record are still
redirected to **My work** when they have another federation role.

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

## Unified action projection
`federation.operation.task` remains the only persistent task projection. It now also emits one missing-parental-consent task per affected roster line and one shared game-day-lineup task per team/day scope. When an explicit game-day scope is unavailable, lineup tasks group by tournament and match kickoff date; unscheduled matches remain scoped to their individual sheet. Parental-consent tasks open the player's canonical approval action. Lineup tasks open the shared match-sheet source. Source models remain authoritative and stale projections still complete through the existing idempotent synchronization.

Manager and club portal refreshes reuse operational tasks by their global source key, even when the task's audience differs from the current refresh scope. This keeps repeated dashboard visits idempotent while each queue continues to show only its intended audience.

Task queues expose overdue status for unfinished tasks whose deadline has passed. Tasks without a deadline and completed tasks are not overdue.

## Role workspaces and scoped handoffs
`/my/work` is the role switchboard for club/team preparation, referee
assignments, competition planning, result review, and manager operations. It
links to existing workflow owners rather than introducing a second task or
approval system. The manager queue route is
`/federation/operations/action-items`.

Team-scoped representatives see and assign work only for their assigned team;
whole-club representatives can still own club-wide work. Assignment checks are
enforced by the task model, so posting another team's representative ID cannot
reassign a team task. Task presentation resolves the source using the actual
portal viewer's current ownership scope, even when the projection is searched
with elevated read access. An unreadable or missing source is presented as
unavailable, never as ready.

Refreshing the work inbox also projects a roster-readiness task from each
confirmed season registration that has no roster; refresh never creates the
roster itself. Club tasks are visible only through a current representative
relationship or an explicit team scope, so expired representatives do not keep
access through stale task projections.

The result-review queue shows submitted or verified results only to users with
the corresponding result role and only when the configured self-verification
or self-approval policy allows that user to act. Result commands remain the
authority for every decision. The official-assignment return link preserves
only the allowlisted `filterby` values `upcoming`, `pending`, `history`, and
`all`; arbitrary redirects and query parameters are discarded.

Automated role-journey test mapping is recorded in
`ci/role_journeys/acceptance.json` and is explicitly partial. Focused Odoo
`HttpCase` tests exercise ordinary role accounts, but they are not browser
qualification or real novice sessions. Staging/manual, keyboard/mobile, novice,
and fresh release-confidence gates remain separate sign-off requirements.

The referee assignment work list uses semantic work cards rather than a data
table. Portal templates use model-provided human state labels so internal state
keys are not exposed as user-facing copy. Competition administrators have
read-only edition access for their planning workspace; edition changes remain
owned by the existing setup and workflow commands.


## Rosters, game days and line-ups

Club representatives follow one flow: **team → roster → game days → line-up**.

- A **roster** (`/my/rosters`) is the team's player pool for a season. The
  page lists the current rosters with the next game day of each, and the roster
  page lists every game day of the roster's season with the state of its
  line-up (not started, draft, submitted, approved, locked), how many players
  are selected, and a **Prepare line-up** button.
- A **line-up** (`/my/match-sheets/<id>`) is the set of players available on
  one game day. It is shared by all matches the team plays that day. One form
  saves the roster, coach, manager and the selected players; **Save and
  submit** submits it for every match of the game day. At each match the coach
  only crosses out the players who do not play (**Players for this match**).
- `/my/match-sheets` is the single game-day list (upcoming first, earlier game
  days collapsed). `/my/match-day`, the former preparation queue, redirects
  there.

Clubs only see what is current. `federation.team.roster._portal_current_season_ids`
defines current seasons: draft or open and not yet ended. Rosters, registrations
that need a roster and preparation checks of other seasons are listed under a
collapsed **Past seasons** section or left out. Closing, cancelling or archiving
a season closes its active rosters. A line-up only offers rosters of the same
team, season and competition; the choice is skipped when only one roster fits.

`federation.portal.gameday` is the single place that groups match sheets into
game days and decides what is upcoming or earlier, so the roster page, the
game-day list and the line-up page always agree.

Upgrade 19.0.7.14.0 disables obsolete inherited game-day and line-up views
before their replacement pages are loaded. It changes no roster or match data.

## Task deadlines and the season roster

Work that depends on a team's roster carries the date it becomes blocking as its
deadline: the roster-readiness, missing-roster and parental-consent tasks use the
roster deadline (seven days before the team's first match in the season, or the
tournament start while no match is scheduled, as the match roster-deadline rule
computes it), the game-day line-up task is due at the first kick-off of the game
day, and competition-entry tasks when their registration window closes. The
work inbox sorts by it, overdue work is marked, and the due-soon reminder covers
it. `federation.operation.task._prefetch_roster_deadlines` resolves all rosters
of a refresh with a fixed number of queries.

The portal's primary-roster lookup falls back to the team's season baseline
roster (`federation.team.roster._pick_season_baseline`) when no roster is linked
to the registration, so a roster created for a competition is found and adopted
instead of a second roster being offered.
