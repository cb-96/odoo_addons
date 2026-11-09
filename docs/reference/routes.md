# Route inventory

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Every HTTP route served by the `sports_federation_*` addons, grouped by
audience. Paginated variants (`…/page/<int:page>`) exist for most portal and
public lists and are not repeated below.

The machine-readable registry of governed routes with smoke coverage is
`ci/contracts/route_inventory.json` (loaded by
`sports_federation_base/tests/route_inventory.py`); controller tests and
`ci/check_http_route_ownership.py` are the completeness checks. This document
explains ownership and review rules and is not parsed by CI, except for the
canonical-namespace checks in `ci/check_public_route_cutover_docs.py` and
`ci/check_release_qualification.py`.

## Review rules

A route change must include:

1. an explicit owner module;
2. an authentication and CSRF review;
3. a model or service write boundary (no raw controller `sudo()` writes);
4. positive and negative access tests;
5. an update of this document, `ci/contracts/route_inventory.json` and, when
   partner-facing, the OpenAPI contract and [integration contracts](integration-contracts.md);
6. compatibility and removal notes when replacing an existing route.

All portal writes resolve the request user's club or team scope before calling
a model-owned method; see [ADR-0001](../architecture/decisions/0001-portal-trust-boundaries.md).
Public reads enforce publication flags; see
[ADR-0003](../architecture/decisions/0003-public-route-ownership.md).

## Public website

Owner: `sports_federation_public_site`. Auth: public, except registration.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/competitions` | Competition hub (canonical public entry) |
| GET | `/competitions/archive` | Finished competitions |
| GET | `/competitions/<edition-slug>` | Competition page |
| GET | `/competitions/<edition-slug>/schedule`, `/results`, `/standings`, `/format` | Published schedule, approved results, standings, format and brackets |
| GET | `/competitions/<edition-slug>/gamedays/<matchday_id>` | Published game day |
| GET | `/competitions/<edition-slug>/gamedays/<matchday_id>/status.json` | Live game-day board data |
| GET | `/competitions/<edition-slug>/divisions/<division-slug>/schedule.ics` | Division calendar feed |
| GET, POST | `/competitions/<edition-slug>/register?division_id=<division-id>` | Competition registration (authenticated); uses the shared registration model boundary |
| POST | `/competitions/api/json` | JSON-RPC data for public competition pages |
| GET | `/clubs`, `/clubs/<club-slug>` | Public club directory |
| GET | `/players`, `/players/<player-slug>` | Public player pages (non-sensitive fields only) |
| GET | `/seasons`, `/seasons/<season-slug>`, `/season/<season_id>` | Season pages |
| GET | `/teams/<team-slug>`, `/teams/<team-slug>/schedule`, `/teams/<team-slug>/results` | Team pages |
| GET | `/teams/<team-slug>/schedule.ics` | Team calendar feed |

## Public data API

Owner: `sports_federation_public_site`. Auth: public. Contract details are in
[integration contracts](integration-contracts.md#public-competition-feed).

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/v1/competitions` | Public competition index |
| GET | `/api/v1/competitions/<edition-slug>` | Complete published competition feed |
| GET | `/api/v1/teams/<team-slug>/feed` | Published team feed |

## Club portal

Owner: `sports_federation_portal` unless noted. Auth: user (portal).

### Home and tasks

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/my`, `/my/home` | Portal overview: the club first, then one section per other role (official, planning, result review, federation work queue) |
| GET | `/my/club` | Club details; `?club=<id>` for representatives of several clubs |
| GET | `/my/journey-context` | User and database id for return navigation (not cached) |
| GET | `/my/result-reviews` | Results waiting for the user's verification or approval |
| GET | `/my/season-registrations/<registration_id>/roster` | Missing-roster explanation for a confirmed registration |
| GET | `/my/action-items/<task_id>/open` | Open the source record of a task after rechecking access |
| GET | `/my/work`, `/my/work/…` | Retired: permanent redirects to the routes above |
| GET | `/my/action-items` | Club task list |
| POST | `/my/action-items/assign` | Assign a task to a team or club representative |
| GET | `/my/milestones` | Club milestones |
| GET | `/my/preparation` | Team preparation: registration, roster, line-ups and consent documents |

### Teams, players and registrations

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/my/teams`; GET, POST `/my/teams/new` | Club teams; create a team (`federation.team._portal_create_team`) |
| GET | `/my/players`; GET, POST `/my/players/new` | Club players; create a player (`federation.player._portal_create_player`) |
| GET, POST | `/my/players/<player_id>/parental-approvals[/upload]`, GET `…/<approval_id>/download` | Parental approval evidence |
| GET | `/my/season-registrations`; GET, POST `/my/season-registration/new`; POST `/my/season-registration/<reg_id>/cancel` | Season registrations (`federation.season.registration._portal_submit_registration_request`) |
| GET | `/my/competitions`, `/my/competitions/<edition_id>` | Competitions the club's teams take part in |
| GET | `/my/competition-entries`, `/my/competition-entries/<entry_id>` | Competition entries |
| POST | `/my/competition-entries/new`, `…/<entry_id>/resubmit`, `…/<entry_id>/withdraw` | Submit, correct and withdraw entries through the portal privilege boundary |
| GET | `/my/compliance`, `/my/compliance/<requirement_id>/<target_model>/<target_id>`; POST `…/submit` | Compliance documents (owner: `sports_federation_compliance`) |

### Rosters, line-ups and results

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/my/rosters`, `/my/rosters/<roster_id>` | Team rosters |
| POST | `/my/rosters/create/<registration_id>` | Create the roster for a confirmed registration |
| GET, POST | `/my/rosters/<roster_id>/edit`, `…/lines/new`, `…/lines/bulk`, `…/lines/<line_id>/edit` | Edit a roster and its lines |
| POST | `/my/rosters/<roster_id>/activate`, `/close`, `/draft`, `/reopen`, `/copy-lines`, `/lines/<line_id>/delete` | Roster commands |
| GET | `/my/match-day` | Upcoming game days for the club's teams |
| GET | `/my/match-days`, `/my/match-days/<matchday_id>` | Game days selected through current live publications |
| GET | `/my/match-sheets`, `/my/match-sheets/<sheet_id>` | Game-day line-ups |
| POST | `/my/match-sheets/<sheet_id>/prep`, `/squad`, `/lineup` | Prepare and submit a line-up |
| POST | `/my/match-sheets/<sheet_id>/participation` | Cross out players for one match |
| GET | `/my/results`, `/my/results/<match_id>`; POST `…/approve`, `…/contest` | Result follow-up |

### Officials and duties

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/my/referee-duties`, `/my/referee-duties/<duty_id>`; POST `…/nominate` | Club official duties and nominations |
| GET | `/my/referee-assignments`, `/my/referee-assignments/<assignment_id>`; POST `…/respond` | Legacy individual assignment pages; they lead to the duty workspace and do not mutate records from old forms |
| GET | `/my/duty-assignments`, `/my/duty-assignments/<assignment_id>`; POST `…/respond` | Individual official assignment workspace (owner: `sports_federation_duty_coverage`) |
| POST | `/my/duty-assignments/<assignment_id>/checkin` | Signed check-in request (owner: `sports_federation_live_workspace`) |
| GET | `/my/matchday-mobile` | Mobile match-day entry (owner: `sports_federation_live_workspace`) |
| GET | `/my/court-duties`; POST `/my/court-duties/prepare`, `/my/court-duties/devices/<device_id>/revoke`, `/my/court-duties/pin`, `/my/court-duties/scorers`, `/my/court-duties/scorers/<scorer_id>/withdraw` | Matches to score, phone preparation, own phones, referee PIN, club scorers (owner: `sports_federation_live_workspace`) |
| GET | `/court/app`, `/court/sw.js`, `/court/manifest.webmanifest` | Offline court app shell, service worker and manifest; public, no data |
| POST | `/court/api/activate`, `/court/api/pack`, `/court/api/sync`, `/court/api/claim`, `/court/api/forget` | Offline court app API; bearer device token except `activate` (one-time code); rate limited |
| POST | `/my/matchday-mobile/assignments/<assignment_id>/present`; GET, POST `…/replace` | Manager attendance confirmation and official replacement |

### Notifications and family

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/my/notifications`, `/my/notifications/<receipt_id>` | Participant inbox (owner: `sports_federation_notifications`) |
| POST | `/my/notifications/<receipt_id>/acknowledge` | Acknowledge a notification (records recipient and time only) |
| GET | `/my/notifications/<receipt_id>/open`, `/my/notifications/schedule/<day_id>` | Open the related task or current schedule |
| GET, POST | `/my/notifications/preferences` | Delivery preferences |
| GET | `/my/family` | Family workspace (owner: optional `sports_federation_member_services`) |
| POST | `/my/family/memberships/<membership_id>/renew`, `/change`, `/licence`; `/my/family/guardian-request` | Membership and guardian requests |
| GET, POST | `/my/family/requests/<request_id>/download`, `/upload` | Requested evidence |

## Match-day operations board

Owner: `sports_federation_portal`. Auth: user. Scoped to the game day's
current live publication.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/sports/match-days/<matchday_id>/operations` | Operations board |
| POST (JSON-RPC) | `/sports/match-days/<matchday_id>/operations/data` | Current live operations payload |
| POST (JSON-RPC) | `/sports/match-days/<matchday_id>/matches/<match_id>/action` | Match action constrained to that publication |

## Federation staff (front end)

Owner: `sports_federation_portal`. Auth: user with federation roles.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/federation/operations/action-items` | Manager task queue |
| POST | `/federation/operations/bulk-registrations` | Bulk registration decisions |
| POST | `/federation/operations/send-reminders` | Send task reminders |
| GET | `/federation/search` | Cross-module search returning typed links |

## Reporting exports

Owner: `sports_federation_reporting`. Auth: user with reporting rights.
Responses keep their documented contract and version headers.

| Method | Route |
| --- | --- |
| GET | `/reporting/export/standings/<tournament_id>` |
| GET | `/reporting/export/participation/<season_id>` |
| GET | `/reporting/export/finance` |
| GET | `/reporting/export/finance/events` |

## Managed integration API

Owner: `sports_federation_import_tools`. Auth: partner credentials. Defined in
`openapi/integration_v1.yaml`.

| Method | Route |
| --- | --- |
| GET | `/integration/v1/contracts` |
| GET | `/integration/v1/outbound/finance/events` |
| POST | `/integration/v1/inbound/<contract_code>/deliveries` |

These routes require partner authentication, subscription checks, stable error
envelopes, bounded pagination where applicable, and documented idempotency.

## Removed routes

The former tournament-named public pages and feeds, the numeric public
competition routes, the tournament operations board and the tournament workspace portal
pages have been removed. Only the `/competitions` and `/api/v1/competitions`
namespaces are documented and supported.
