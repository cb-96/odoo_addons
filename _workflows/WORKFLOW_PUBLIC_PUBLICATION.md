# Workflow: Public Publication

Publishing tournaments, standings, schedules, and editorial coverage to the
public website.

## Overview

The federation website exposes published competition coverage without requiring
login. Publication is slug-first and tournament-first: operators publish a
tournament, control which result and standing surfaces are visible, and can add
editorial content around seasons, tournaments, or teams without editing website
templates.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_public_site` | Publication fields, editorial items, website controllers, templates |
| `sports_federation_tournament` | Tournament, match, and participant data |
| `sports_federation_standings` | Standings data |
| `sports_federation_result_control` | Approved results only |
| `sports_federation_notifications` | Tournament-publication emails |
| `sports_federation_venues` | Venue data on schedule pages |
| `website` | Odoo website framework |

## Step-by-Step Flow

### 1. Tournament Publication Setup

**Actor**: Federation administrator
**Module**: `sports_federation_public_site`

Before publishing, ensure the tournament has:

1. a completed setup with matches and public-facing text
2. approved results if the results page should be visible
3. computed standings if the standings page should be visible

Then configure the public-site fields on the tournament:

- `website_published`
- `public_slug`
- `public_description`
- `public_featured`
- `public_editorial_summary`
- `public_pinned_announcement`
- `show_public_results`
- `show_public_standings`

The first transition from unpublished to published sends the tournament
publication notification to participating club and team contacts.

### 2. Standings And Results Visibility

**Actor**: Federation administrator
**Modules**: `sports_federation_standings`, `sports_federation_result_control`

1. Publish the standings record itself with `website_published = True`.
2. Optionally set `public_title` for the public standings page.
3. Remember the public results page only shows approved results.
4. Public participant lists exclude withdrawn tournament participants.

### 3. Editorial Publication Workflow

**Actor**: Federation administrator or communications staff
**Module**: `sports_federation_public_site`

Editorial items can be anchored to a season, tournament, or team and use the
state machine below:

`draft` → `scheduled` → `published` → `archived`

Operator actions:

1. **Schedule** — allowed only from `draft`, and only when `publish_start` is set.
2. **Publish Now** — allowed from `draft` or `scheduled`.
3. **Archive** — allowed from `scheduled` or `published`.
4. **Reset to Draft** — allowed from `scheduled` or `archived`.

Statusbar behavior:

- The form statusbar shows the active publication pipeline:
  `draft`, `scheduled`, `published`.
- `archived` is still a real record state, but operators reach it and leave it
  through explicit actions and search filters rather than as a visible statusbar
  stop.

Visibility guards:

- Editorial items must be `active`.
- `draft` and `archived` items are never public.
- `scheduled` and `published` items are only public inside the
  `publish_start` / `publish_end` window.

### 4. Public Pages Go Live

**Actor**: System (automatic)
**Module**: `sports_federation_public_site`

Canonical public surfaces include:

| URL | Content |
|-----|---------|
| `/tournaments` | Main tournament hub with featured, live, recent, and archived sections |
| `/tournaments/<slug>` | Canonical tournament overview page |
| `/tournaments/<slug>/teams` | Published participant list excluding withdrawn entries |
| `/tournaments/<slug>/standings` | Public standings page when enabled |
| `/tournaments/<slug>/results` | Approved public results when enabled |
| `/tournaments/<slug>/schedule` | Upcoming fixtures |
| `/tournaments/<slug>/bracket` | Public bracket view when bracket data exists |
| `/tournaments/<slug>/schedule.ics` | Tournament schedule calendar export |
| `/api/v1/tournaments/<slug>/feed` | Stable v1 JSON feed |
| `/seasons/<slug>` | Season landing page with editorial and tournament aggregation |
| `/teams/<slug>` | Public team profile page |
| `/teams/<slug>/schedule` | Team-centric grouped upcoming schedule |
| `/teams/<slug>/results` | Team-centric recent approved results |
| `/teams/<slug>/schedule.ics` | Team schedule calendar export |
| `/api/v1/teams/<slug>/feed` | Stable v1 team follow feed |

Older `/competitions` and numeric routes remain as compatibility paths, but the
authoritative public URLs are the slug-based `/tournaments/...` routes.
Compatibility routes only redirect while the tournament still matches the
relevant publication guard; unpublished tournaments fail closed instead of
resolving through direct slug or numeric paths. Season detail routes apply the
same fail-closed rule for both `/seasons/<slug>` and numeric `/season/<id>`
compatibility paths, and team profile/follow routes only resolve teams that
still have a published competition footprint.

### 5. Ongoing Updates

**Actor**: Federation administrator

As the tournament progresses:

1. Approved results automatically feed the public result surfaces.
2. Recomputed standings refresh public tables.
3. Featured, live, recent, and archived hub sections update from current data.
4. Publication emails are only sent on the publish transition itself, not on
   every later content change.

### 6. Archive And Removal

**Actor**: Federation administrator

1. Published tournaments in `closed` or `cancelled` move into the public archive
   sections while `website_published` remains enabled.
2. Setting `website_published = False` removes public access immediately.
3. Editorial items can be archived without unpublishing the tournament itself.

## Publication Checklist

| Item | Required | Module |
|------|----------|--------|
| Tournament exists and is website-published | Yes | `public_site` |
| `public_slug` set and unique | Yes | `public_site` |
| Approved results available | Yes, for results page | `result_control` |
| Tournament results visibility enabled | Optional | `public_site` |
| Standings record website-published | Yes, for standings page | `standings` |
| Tournament standings visibility enabled | Optional | `public_site` |
| Editorial item linked to season/tournament/team | Yes, for editorial content | `public_site` |
| Editorial item publish window valid | Yes, when scheduling | `public_site` |

## Access Control

| Access | Level |
|--------|-------|
| Public pages | No authentication required |
| Publication settings and editorial actions | Federation administrator or owning backend staff |
| Data changes | Backend users only |

Public pages are read-only snapshots. Controllers resolve tournament, season,
and team records through publication- and visibility-scoped queries before
redirects, rendering, or feed and registration reads.

## Related Workflows

- [Tournament Lifecycle](WORKFLOW_TOURNAMENT_LIFECYCLE.md) — tournament setup and closure
- [Result Pipeline](WORKFLOW_RESULT_PIPELINE.md) — result approval before publication
- [Season Registration](WORKFLOW_SEASON_REGISTRATION.md) — published seasons and club context
