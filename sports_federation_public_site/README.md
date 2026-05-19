# Sports Federation Public Site

Public website coverage for tournaments, now integrated into the main
Tournaments navigation instead of a separate Competitions surface.

## Purpose

This module turns published tournaments into a coherent public product for fans,
clubs, and media. It provides a tournament hub, overview pages, schedule and
results pages, standings snapshots, team profile pages, JSON feed access, and
calendar export while keeping older competition URLs working.

## Dependencies

| Module | Reason |
|--------|--------|
| `website` | Odoo website framework |
| `sports_federation_portal` | Main tournament website hub and navigation |
| `sports_federation_tournament` | Tournaments, matches, participants |
| `sports_federation_standings` | Standings data |
| `sports_federation_venues` | Venue information |
| `sports_federation_result_control` | Approved result visibility |

## Model extensions

### `federation.tournament`

| Field | Type | Description |
|-------|------|-------------|
| `website_published` | Boolean | Enables public visibility |
| `public_slug` | Char | Canonical public slug used in `/tournaments/<slug>` |
| `public_description` | Html | Long-form website description |
| `public_featured` | Boolean | Marks the tournament for featured hub sections |
| `public_editorial_summary` | Text | Short editorial summary for cards and overview layouts |
| `public_pinned_announcement` | Text | Announcement banner content for the overview page |
| `public_hero_image` | Binary | Hero image for the public overview page |
| `show_public_results` | Boolean | Enables the public results page |
| `show_public_standings` | Boolean | Enables the public standings page |

Key helper methods expose canonical public URLs, published tournament queries,
team/result/standings/schedule datasets, JSON feed payloads, and ICS calendar
export content.

### `federation.team`

| Field | Type | Description |
|-------|------|-------------|
| `public_slug` | Char | Canonical public slug used in `/teams/<slug>` |

Team helpers provide stable team profile URLs and public tournament links.
Their public slug resolver accepts an extra publication domain so controller
lookups can fail closed before rendering profile, follow, feed, or calendar
surfaces.

### `federation.season`

| Field | Type | Description |
|-------|------|-------------|
| `website_published` | Boolean | Enables season-wide discovery on the website |
| `public_slug` | Char | Canonical public slug used in `/seasons/<slug>` |
| `public_summary` | Text | Short summary used on season discovery pages |
| `public_description` | Html | Long-form season landing page content |

Season helpers provide canonical season URLs, featured and recent tournament
queries, editorial aggregation for season landing pages, and fail-closed public
slug resolution for published-season routes.

### `federation.public.editorial.item`

| Field | Type | Description |
|-------|------|-------------|
| `publication_state` | Selection | draft / scheduled / published / archived |
| `content_type` | Selection | highlight / announcement / update |
| `publish_start` / `publish_end` | Datetime | Optional publication window |
| `season_id` / `tournament_id` / `team_id` | Many2one | Public anchor for the item |
| `summary` | Text | Card-friendly editorial summary |
| `body_html` | Html | Long-form editorial content |

Editorial items let operators schedule season-, tournament-, or team-linked
highlights without editing website templates. Scheduling requires a publish
start while the item is still in draft; items can publish from draft or
scheduled, archive from scheduled or published, and reset from scheduled or
archived back to draft.

### `federation.standing`

| Field | Type | Description |
|-------|------|-------------|
| `website_published` | Boolean | Allows standings publication |
| `public_title` | Char | Public-facing table title |

## Controllers

### `PublicTournamentHubController`

Canonical public routes:

| Route | Auth | Description |
|-------|------|-------------|
| `GET /tournaments` | public | Main public tournament hub with featured, live, recent, and archive sections |
| `POST /tournaments/api/json` | public | JSON list of published tournaments |
| `GET /tournaments/<slug>` | public | Canonical tournament overview page |
| `GET /tournaments/<slug>/teams` | public | Published participant list excluding withdrawn entries |
| `GET /tournaments/<slug>/standings` | public | Published standings page |
| `GET /tournaments/<slug>/results` | public | Approved public results |
| `GET /tournaments/<slug>/schedule` | public | Public schedule grouped for easier browsing |
| `GET /tournaments/<slug>/bracket` | public | Public bracket sections when bracket data exists |
| `GET /tournaments/<slug>/schedule.ics` | public | ICS calendar export for the tournament schedule |
| `GET /api/v1/tournaments/<slug>/feed` | public | Stable v1 JSON tournament feed |
| `GET /teams/<slug>` | public | Public team profile page |
| `GET /tournaments/<slug>/register` | user | Website registration form |
| `POST /tournaments/<slug>/register` | user | Website registration submission via `federation.tournament.registration._portal_submit_registration_request()` |

Compatibility routes remain available for older links, including `/competitions`,
`/competitions/archive`, numeric `/tournament/<id>` paths, numeric register/feed
paths, and older coverage aliases. Team profile routes and season follow routes
resolve through publication-scoped domains before redirects or rendering.

### `PublicFollowController`

Canonical follow and discovery routes:

| Route | Auth | Description |
|-------|------|-------------|
| `GET /seasons` | public | Season discovery page for published seasons |
| `GET /seasons/<slug>` | public | Canonical season landing page with editorial and tournament sections |
| `GET /teams/<slug>/schedule` | public | Team-centric grouped upcoming schedule |
| `GET /teams/<slug>/results` | public | Team-centric recent approved results |
| `GET /teams/<slug>/schedule.ics` | public | Team schedule calendar export |
| `GET /api/v1/teams/<slug>/feed` | public | Stable v1 team follow feed |

## Public-site behaviour

1. Tournament-first navigation: the visible website now centers tournaments and nests published coverage under the existing Tournaments area.
2. Slug-first URLs: tournaments and teams use canonical slug routes, with numeric routes preserved only for backward compatibility.
3. Editorial control: operators can feature tournaments, add summaries, pin announcements, and assign hero imagery without editing templates.
4. Better hub discovery: the main hub separates featured, live, recent, and archived tournaments instead of showing one flat list.
5. Team-aware public pages: standings, results, schedule, and teams pages link through to public team profiles when available.
6. Sticky section navigation: tournament sub-pages share one consistent local navigation model.
7. Calendar export: schedules can be consumed as `.ics` for personal or club calendars.
8. Stable feed contract: the v1 feed includes slug-aware public URLs alongside tournament, standings, schedule, bracket, and result data.
9. Visibility enforcement: results and standings respect per-tournament publication toggles.
10. Sanitized website rendering: public descriptions and website content render through standard website field handling.
11. Backward compatibility: legacy competition routes keep resolving while the visible product language is tournament-first.
12. Season discovery and editorial planning: published seasons aggregate featured tournaments, recent tournaments, and live editorial items with publication windows.
13. Automatic menu cleanup: module installs and upgrades normalize stale `/competitions` website menus into the Tournaments submenu and remove leftover duplicates.
14. Shared privileged-write boundary: website registration POST routes validate HTTP input and then reuse the same tournament registration helper as the portal layer.

## Publication guards

- Controllers resolve tournaments, seasons, and team public routes through publication- and visibility-scoped queries before canonical redirects, page rendering, feed reads, or registration handling.
- Unpublished tournaments lose public access immediately, regardless of related data still present in the database.
- Legacy numeric compatibility routes redirect only while the tournament still satisfies the relevant public visibility guard.
- Season slug and numeric detail routes only resolve website-published seasons.
- Team profile, schedule, results, ICS, and feed routes only resolve teams with a published competition footprint.
- Public results are limited to approved results.
- Public participant lists exclude withdrawn entries.
- Standings exposure depends on both tournament publication and the standings visibility controls.
