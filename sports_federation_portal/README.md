# Sports Federation Portal

## Solution Design

### Overview
The `sports_federation_portal` module adds public website pages and portal flows for club representatives to register for tournaments and seasons, to work from a unified active-tournament workspace, to review operational rosters and match sheets with their audit history, and for linked match officials to respond to their own officiating assignments. It sits on top of `sports_federation_base`, `sports_federation_tournament`, `sports_federation_officiating`, `sports_federation_rosters`, and `sports_federation_result_control`, using `website` and `portal` from Odoo core.

### Key Design Decisions

#### 1. Ownership Mapping Strategy

**Club Representative Model (`federation.club.representative`)**

A dedicated model links `res.users` to `federation.club` records. This is the single source of truth for "which portal user owns which club."

- One user can represent multiple clubs (rare but supported).
- One club can have multiple representatives (primary + secondary).
- Controllers use `_get_clubs_for_user()` to resolve ownership before every operation.

**Why a dedicated model instead of a Many2many on `res.users`?**
- Keeps the portal layer cleanly separated from the base module.
- Allows adding role, active flag, and audit fields without touching `federation.club`.
- Record rules can reference `user.representative_ids.mapped('club_id')` directly.

#### 2. Tournament Registration Model (`federation.tournament.registration`)

A new intermediate model captures portal-side registration requests with a full workflow:

```
draft -> submitted -> confirmed / rejected / cancelled
```

**Why not reuse `federation.tournament.participant` directly?**
- `federation.tournament.participant` is a backend-managed record. It should only be created after federation staff reviews the request.
- The registration model adds a review step, rejection reason, and links back to the submitting user.
- On confirmation, the system auto-creates a `federation.tournament.participant` record.

#### 3. Season Registration Extension

The existing `federation.season.registration` model is extended with a `submitted` state and portal fields (`user_id`, `partner_id`, `rejection_reason`). This avoids creating a duplicate model while adding the portal workflow.
The same model now also enforces club ownership at ORM level so portal-created season registrations cannot bypass controller checks.
Federation staff review the same record in the backend, where they can submit, confirm, reject back to draft with a reason, or cancel the registration without creating a second review model. There is no persistent `rejected` state on season registrations; rejection is represented by `state='draft'` plus `rejection_reason`.

#### 4. Public vs Portal Separation

| Layer | Auth | Access |
|-------|------|--------|
| Public (`/tournaments`, `/tournament/<id>`) | `auth="public"` | Anyone can view open/in-progress/closed tournaments. Read-only. Uses `sudo()`. |
| Registration form (`/tournament/<id>/register`) | `auth="user"` | Logged-in users only. Ownership verified server-side. |
| Portal (`/my/*`) | `auth="user"` | Only records belonging to user's club. Record rules enforce this. |

#### 5. Match-Official Self-Service

Referee assignments now support a second portal ownership path alongside club representation.

- `federation.referee.user_id` links an official profile to a portal user.
- officials in `group_federation_portal_official` can see only their own referee profile and assignment records.
- the portal exposes `/my/referee-assignments` and assignment-detail response pages.
- officials can confirm or decline draft assignments from the portal while reusing the existing officiating readiness checks.

**Why keep this separate from club representative ownership?**
- officials are not club-owned records and often work across unrelated clubs and tournaments.
- a dedicated official access path avoids leaking club data just to allow assignment confirmation.
- the self-service flow reuses the same `federation.match.referee` lifecycle rather than inventing a parallel response model.

#### 6. Active Tournament Workspace

Club and team-scoped portal users now get a tournament-first workspace for active obligations.

- `/my/tournament-workspaces` groups visible teams by active tournament (`open` or `in_progress`).
- each entry summarizes registration state, the preferred roster checkpoint, upcoming match-day sheet work, and done matches whose results still need follow-up.
- `/my/tournament-workspaces/<tournament>/<team>` expands that entry into operational detail with direct links to the roster, match-day queue, and team match sheets.
- the workspace model itself revalidates team scope and active-tournament scope through `federation.portal.privilege` before any elevated reads, so direct model or RPC callers cannot bypass the controller filters.
- current whole-club access comes only from `portal_club_scope_ids`, while current team-scoped roles stay pinned to `portal_team_scope_ids`; historical or inactive representative rows do not widen workspace visibility.

**Why add a separate workspace instead of more dashboard counters?**
- recurring club operations are tournament-scoped, not model-scoped.
- operators need to answer “what still needs attention for this team in this tournament?” without jumping across registration, roster, and result pages.
- the workspace reuses existing portal security and underlying record pages rather than duplicating those workflows.

#### 7. Record Rule Strategy

Portal users (`group_federation_portal_club`) get these record rules:

| Model | Rule | Effect |
|-------|------|--------|
| `federation.club.representative` | `('user_id', '=', user.id)` | See only own representative records |
| `federation.club` | `('id', 'in', user.representative_ids.mapped('club_id').ids)` | See only own clubs |
| `federation.team` | `('club_id', 'in', ...)` | See only own teams |
| `federation.season.registration` | `('club_id', 'in', ...)` | See only own season registrations |
| `federation.tournament.registration` | `('club_id', 'in', ...)` | See only own tournament registrations |
| `federation.tournament` | `[(1, '=', 1)]` | See all tournaments (read-only, for listing) |
| `federation.tournament.participant` | `('club_id', 'in', ...)` | See only own participants |
| `federation.team.roster` | `('club_id', 'in', ...)` | See only own season rosters |
| `federation.team.roster.line` | `('roster_id.club_id', 'in', ...)` | See only own roster lines |
| `federation.match.sheet` | `('team_id.club_id', 'in', ...)` | See only own match sheets |
| `federation.match.sheet.line` | `('match_sheet_id.team_id.club_id', 'in', ...)` | See only own match-sheet lines |
| `federation.participation.audit` | `('team_id.club_id', 'in', ...)` | See only own participation audit events |
| `federation.match.result.audit` | home/away team club ownership | See only own result dispute and approval history |

Additionally, controllers validate ownership on every write operation as defense-in-depth and then delegate the privileged create or submit step into explicit model entry points.
Official portal users also receive own-record rules for `federation.referee` and
`federation.match.referee`.
For season and tournament registrations, the models also enforce that `user_id` can only submit teams for represented clubs.

## Module Tree

```
sports_federation_portal/
    __init__.py
    __manifest__.py
    controllers/
        __init__.py
        main.py
        officiating.py
        rosters.py
        web_auth.py
    data/
        ir_sequence.xml
    models/
        __init__.py
        federation_club.py
        federation_club_representative.py
        federation_club_role_type.py
        federation_match_referee.py
        federation_match_sheet.py
        federation_referee.py
        federation_season_registration.py
        federation_team.py
        federation_team_roster.py
        federation_tournament.py
        federation_tournament_registration.py
        res_partner.py
        res_users.py
    security/
        ir.model.access.csv
        ir_rule.xml
        res_groups.xml
    views/
        federation_club_representative_portal_views.xml
        federation_club_representative_views.xml
        federation_club_role_type_views.xml
        federation_club_views.xml
        federation_referee_views.xml
        federation_season_registration_views.xml
        federation_tournament_registration_views.xml
        federation_tournament_views.xml
        menu_items.xml
        portal_officiating_templates.xml
        portal_templates.xml
        portal_tournament_workspace_templates.xml
        portal_roster_templates.xml
        res_partner_views.xml
        res_users_views.xml
        website_menus.xml
```

## Security Explanation

### Groups
- **`group_federation_portal_club`**: Portal Club Representative. Implies `base.group_portal`. Users in this group get ACL and record rules that restrict them to their club's data.
- **`group_federation_portal_official`**: Portal Match Official. Implies `base.group_portal`. Users in this group get ACL and record rules that restrict them to their own referee profile and officiating assignments.

### ACL (Access Control List)
Portal group gets:
- **Read** on clubs, teams, seasons, tournaments, participants (for display).
- **Read/Create/Write** on season registrations and tournament registrations (to submit and cancel).
- **Read-only** on club representatives (to resolve ownership).
- **No unlink** on anything (portal users cannot delete records).

Official portal group gets:
- **Read-only** on referee profiles and match-referee assignments.
- portal-driven confirm and decline actions execute through controller helpers with explicit ownership checks and `sudo()`.

Manager group gets full CRUD on all new models.

### Record Rules
Portal access now distinguishes between current whole-club scope and current team scope. Match-day record rules use `user.portal_club_scope_ids` for whole-club visibility and `user.portal_team_scope_ids` for assigned-team visibility so inactive or historical representative rows do not widen access.

### Controller-Level Validation
Every write operation in the controllers:
1. Resolves the user's clubs via `_get_clubs_for_user()`.
2. Verifies the target team/registration belongs to those clubs.
3. Checks for duplicates and capacity limits.
4. Hands the mutation to a model helper such as `federation.team._portal_create_team()`, `federation.season.registration._portal_submit_registration_request()`, or `federation.tournament.registration._portal_submit_registration_request()`.

The same ownership rules are also enforced in the ORM for portal-managed registration models. That second layer matters whenever data is created from tests, server actions, imports, or future controllers.
Roster portal helpers also revalidate roster and season-registration scope through `federation.portal.privilege` before any elevated reuse or create lookup, so team-scoped representatives cannot reach same-club rosters outside their assigned team through helper calls.
Roster-line player submission now reuses the same portal-scoped player domain as the picker, so forged POST values cannot add inactive or wrong-gender players that the form intentionally hid.
Roster detail, roster-line route helpers, and roster-line license submission now also resolve ids through `federation.portal.privilege`, so hidden roster, roster-line, or license ids cannot be recovered through raw elevated browse paths.

### Public Routes
Public routes use `sudo()` to bypass ACL (since anonymous users have no federation access). They only expose:
- Tournament name, dates, location, status, participant count.
- No sensitive internal data (no email, phone, notes from clubs, etc.).

## Verification Checklist

### Security Flows
- [ ] **Public user cannot access `/my/club`** - Should redirect to login.
- [ ] **Portal user without representative record sees "not assigned" message** on `/my/club`.
- [ ] **Portal user A cannot see portal user B's registrations** - Record rules prevent this.
- [ ] **Portal user cannot register a team from another club** - Controller validates `team.club_id in clubs`.
- [ ] **Portal user cannot cancel a registration from another club** - Controller checks ownership.
- [ ] **Anonymous user cannot POST to `/tournament/<id>/register`** - `auth="user"` blocks it.
- [ ] **CSRF tokens are required on all POST forms** - All forms include `csrf_token`.

### Functional Flows
- [ ] **Tournament listing** (`/tournaments`) shows open/in_progress/closed tournaments.
- [ ] **Tournament detail** (`/tournament/<id>`) shows participants and register button when state is `open`.
- [ ] **Tournament registration** creates a `federation.tournament.registration` in `submitted` state.
- [ ] **Roster portal pages** (`/my/rosters`, `/my/rosters/<id>`) show only the representative's clubs, including lock feedback and audit events.
- [ ] **Team-scoped portal users** only see their assigned team's rosters, teams, match sheets, and workspace entries; same-club foreign-team records stay hidden.
- [ ] **Inactive or expired representatives** lose live team, roster, match-sheet, and workspace visibility.
- [ ] **Match-sheet portal pages** (`/my/match-sheets`, `/my/match-sheets/<id>`) show substitutions plus related result disputes and corrections.
- [ ] **Duplicate registration** is rejected with an error message.
- [ ] **Max participants** limit is enforced.
- [ ] **Season registration** creates a `federation.season.registration` in `submitted` state.
- [ ] **Season registration backend review** shows submit, confirm, reject, and portal metadata (`user_id`, `partner_id`, `rejection_reason`).
- [ ] **Season registration rejection** returns the record to `draft` and preserves the rejection reason for the submitting representative.
- [ ] **Cancel registration** sets state to `cancelled`.
- [ ] **Confirm registration** in backend creates `federation.tournament.participant`.
- [ ] **Portal dashboard** shows federation cards for club representatives.
- [ ] **Tournament workspace** (`/my/tournament-workspaces`) groups active tournament obligations by visible team.
- [ ] **Tournament workspace detail** shows registration checkpoint, roster checkpoint, upcoming match-day sheets, and result follow-up links.
- [ ] **Portal dashboard** shows officiating cards for linked match officials.
- [ ] **Match official portal** (`/my/referee-assignments`) shows only the current official's assignments.
- [ ] **Match official response** can confirm or decline draft assignments with an optional or required response note respectively.
- [ ] **Breadcrumb navigation** works on all pages.

### Backend Flows
- [ ] **Tournament registration form** shows statusbar, buttons, and chatter.
- [ ] **Tournament registration form** explains why teams are unavailable in backend dropdowns.
- [ ] **Submit/Confirm/Reject/Cancel** buttons work with correct visibility.
- [ ] **Club representative** can be created from club form view.
- [ ] **Menu items** appear under Federation > Portal.
- [ ] **Search/filters** work on tournament registration tree view.

## Live Browser Verification

Use this procedure when you need to validate the real website flow against the running Docker stack instead of only relying on tests.

### 1. Seed deterministic portal data

Create or update a small set of records through Odoo shell so the browser check is repeatable.

```bash
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo
```

Recommended dataset:
- one club with a representative user
- one open tournament with explicit `category` and `gender`
- one eligible team for that tournament
- one ineligible team for that tournament

Important details:
- use `group_ids` on `res.users`, not `groups_id`
- write a plain password value if helper signatures differ across versions
- call `env.cr.commit()` before leaving the shell so the browser can see the records

### 2. Restart Odoo after model or view changes

If Python models, XML views, or manifests changed, restart the running service before opening the website.

```bash
docker compose restart odoo
```

Without a restart, the browser may hit stale-runtime errors even when tests passed. During verification of the tournament registration page, a stale process raised an `AttributeError` for a newly added tournament field until the container was restarted.

### 3. Verify the website flow in a browser

Open the registration page directly:

```text
http://localhost:10019/tournament/<tournament_id>/register
```

Then confirm all of the following:
- anonymous access redirects to login because the route uses `auth="user"`
- after login, the page renders without server errors
- the Team dropdown only shows selectable teams
- the page shows an "Unavailable Teams" section with explicit reasons for exclusions
- tournament category and gender badges match the seeded data

### 4. Check live logs when the browser does not match expectations

Use the running container logs immediately after reproducing the issue:

```bash
docker compose logs --tail=200 odoo
```

This is the fastest way to distinguish between:
- routing issues
- stale runtime state
- missing upgraded fields
- template rendering errors

## Required Changes in Existing Modules

**None.** The module is designed to work purely as an extension. It:
- Inherits `federation.season.registration` to add states and fields (no breaking changes).
- Inherits `federation.club` to add `representative_ids` One2many (additive only).
- Uses existing `federation.tournament` and `federation.tournament.participant` models as-is.

## Dependencies

- `website` - For public pages and website layout.
- `portal` - For portal layout, pager, and `CustomerPortal` base class.
- `sports_federation_base` - For clubs, teams, seasons, season registrations.
- `sports_federation_tournament` - For tournaments and participants.