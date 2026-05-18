# ROADMAP — 2026-05-12 Portal, Public Site & Finance Cycle

Last updated: 2026-05-12
Owner: Federation Platform Team
Last reviewed: 2026-05-12
Review cadence: Every release
Release train: 2026.10

The previous operating-period roadmap is archived in
`ROADMAP_archive_2026-05-12b.md`.
This roadmap is driven by a full codebase review conducted on 2026-05-12 (second
pass). It carries forward 7 open items from the previous cycle and adds 6 new
items surfaced by the audit.

---

## State of the Codebase

### What Has Been Completed

**Phase 1 test suites (items 1–5 of the May-12a cycle) are closed.** All five
previously untested modules — `officiating`, `notifications`, `import_tools`,
`governance`, `finance_bridge` — now have regression test suites. CI is green
across all 19 modules.

**The knockout bracket page (item 10 of the May-12a cycle) is live.**
`/tournaments/<slug>/bracket` renders a bracket tree for knockout tournaments;
non-knockout tournaments show a friendly message.

**All 13 items from the May-11 UX cycle are closed.** Portal navigation is
grouped into "Your Season / Match Day / Club Admin". Contextual `error_hint`
paragraphs appear on all portal error paths. Demo data covers a realistic
multi-club season with standings, compliance, discipline, and notification logs.

**Security baseline remains strong.** `_assert_portal_owns()` gate, token
hashing, upload guardrails, partial unique indexes, and no raw exception
surfacing are all intact.

### Focus for This Cycle

Seven open items carry forward from the previous cycle: the portal has no
result approval or dispute paths for club representatives; the public site has
no club or player pages; the finance bridge has no fee schedules, no
auto-trigger, and no invoice generation. Six new items are added from the audit: a usability gap that causes
"Match Day" to be empty when `date_scheduled` is not set on generated matches;
thin test coverage in `people` and `tournament`; under-tested reporting models;
an empty `venues/wizards/` directory; and several data-integrity constraints
that are missing.

---

## Phase 0 — Week 1: Officiating Workflow — Quick Match Assignment

### 0. Officiating — fast assignment UX and availability guardrails

Module: `sports_federation_officiating`

**Problem:** Assigning a referee to a match requires too many steps. The stat
button on the match form is hidden when no officials are assigned yet
(`invisible="not referee_assignment_count"`), so there is no visible entry
point for the first assignment. The only alternative is to navigate to the
global Assignments menu, choose the match manually, and then open each
assignment record individually to confirm it. There is no inline One2many
widget on the match form, no availability check to prevent double-booking, no
batch-assign wizard for a stage or round, and no search filter for referees
available on a given date.

Work:
- [x] **Inline assignment widget**: Replace the hidden stat button with a
  persistent `<field name="referee_assignment_ids">` One2many widget directly
  in the match form view (inside the existing "Officials" section or a new
  notebook page). Each row should show `referee_id`, `role`, `state`, and
  `assignment_ready` in an editable list so the operator can add, confirm, and
  review all assignments without leaving the match record.
- [x] **Stat button always visible**: Remove `invisible="not
  referee_assignment_count"` from the "Officials" stat button (or keep it as a
  count badge while the inline widget handles creation). The button should
  remain accessible at zero assignments so operators have a second path to the
  full assignment list.
- [x] **Conflict detection**: Add a `@api.constrains` check on
  `federation.match.referee` that raises a `ValidationError` when the same
  referee is assigned to two matches whose `date_scheduled` values are on the
  same day (or overlap within a configurable buffer). Provide a clear message:
  *"Referee <name> is already assigned to <other match> on this date."*
- [x] **Referee search filters**: Add search filters to the referee list/search
  view — "Has valid certification", "Available on date" (requires entering a
  date; filters out referees with a confirmed assignment on that date).
- [x] **Batch-assign wizard for a round**: Add a transient wizard
  `federation.round.assign.wizard` with fields `round_id`, `role` (selection),
  and `referee_id`. `action_apply` creates one `federation.match.referee`
  assignment record for every match in the selected round with the chosen
  referee and role, skipping any match that already has an assignment for that
  role. Add an "Assign Official to Round" button on the tournament round form.
- [x] **Tests**: assert inline creation via `referee_assignment_ids` works on
  `federation.match`; assert conflict detection raises when the same referee
  is assigned to two same-day matches; assert batch wizard creates the correct
  number of assignment records and skips already-assigned roles.

Done when: an operator can assign a referee to a single match without leaving
the match form; assigning the same referee to two same-day matches is blocked
with a clear message; the batch wizard can populate all matches in a round in
one action; CI passes.

---

## Phase 1 — Weeks 1–2: Portal Completeness

**Phase 1 complete — portal result approval and contest flows implemented and CI green.**

### 1. Portal — club rep result approval flow

Module: `sports_federation_portal`

**Problem:** Club representatives have no portal path to review and approve
match results. In the federation workflow, the **match official / referee
submits** the result (back-office or via a future referee portal), and a club
representative from either team then **approves** the score — confirming the
club agrees with what was entered. The `action_approve_result()` method is
currently back-office only and requires the `group_result_approver` security
group.

Work:
- [x] Create `controllers/result_portal.py` with:
  - `GET /my/results` — paginated list of the club's matches filtered to
    `result_state` in (submitted, verified, approved, contested); shows status
    column and current score.
  - `GET /my/results/<int:match_id>` — result detail showing current score,
    state, and any audit trail entries visible to the rep.
  - `POST /my/results/<int:match_id>/approve` — calls `action_approve_result()`
    via `sudo()` after verifying ownership with `_assert_portal_owns()` on the
    match's home or away team; only permitted when `result_state == 'verified'`;
    redirects with success/error flash.
- [x] Register `result_portal` in `controllers/__init__.py`.
- [x] Add portal menu item "Results" under the "Match Day" group (sequence
  between "Match Day" and "Match Sheets").
- [x] Add `_portal_get_domain` class method on `federation.match_result_control`
  scoped to the user's `portal_club_scope_ids` (home or away team belongs to
  club).
- [x] Update `portal_templates.xml`: add list template `portal_my_results` and
  detail template `portal_my_result_detail`; show an "Approve Result" button
  only when `result_state == 'verified'`.
- [x] Security: add `ir.model.access.csv` read ACL for
  `federation.match_result_control` for `base.group_portal`.
- [x] Tests: `HttpCase` asserting the result list renders for a portal user with
  club scope; POST to `/my/results/<id>/approve` when `result_state == 'verified'`
  advances it to `approved`; posting when `result_state != 'verified'` returns
  an error; a different club's rep gets an HTTP 403.

Done when: a club rep can approve a verified result from `/my/results`; the 403
guard is in place; the "Approve" button is only shown for `verified` results; CI
passes.

### 2. Portal — result contest flow

Module: `sports_federation_portal`

**Problem:** A club rep has no portal path to contest a result they disagree
with. The back-office `action_contest_result()` method (which sets
`result_state = 'contested'` and requires a reason) is unreachable from the
portal. A rep should be able to contest a result that is in any reviewable
state (`submitted`, `verified`, or `approved`).

Work:
- [x] Add `POST /my/results/<int:match_id>/contest` (in `result_portal.py`)
  that sets `result_contest_reason` from the form body and calls
  `action_contest_result()` via `sudo()`, guarded by `_assert_portal_owns()`.
- [x] Render a "Contest Result" button on the result detail page when
  `result_state` is in (`submitted`, `verified`, `approved`) — mirroring the
  back-office `action_contest_result()` guard.
- [x] Block re-contest if the result is already `contested`; show a contextual
  `error_hint`.
- [x] Require a non-empty reason text in the POST; return an `error_hint` if
  the reason field is blank.
- [x] Tests: assert contest button renders for a `verified` result; assert POST
  without a reason returns an `error_hint`; assert a second contest POST when
  already `contested` is blocked; assert a different club's rep gets HTTP 403.

Done when: club reps can contest reviewable results from the portal; empty reason
and double-contest are both blocked; CI passes.

---

## Phase 2 — Weeks 3–4: Public Site Completeness

**Phase 2 complete — club, team, and player public profile pages implemented and CI green.**

### 3. Public site — club and team profile pages

Module: `sports_federation_public_site`

**Problem:** The public site shows tournament schedules and standings but has no
individual club or team pages. External visitors (media, players considering
joining, partner clubs) cannot look up a club's teams, recent tournament
performance, or contact information.

Work:
- [x] Add route `/clubs` listing all `website_published` clubs, ordered by name.
- [x] Add route `/clubs/<slug>` showing club name, contact, linked teams, and
  recent tournament participation (last 3 seasons).
- [x] Add route `/teams/<slug>` showing team name, category, gender, and a
  table of public matches played (`date_scheduled` + score + opponent).
- [x] Use `website_published` as the guard — only clubs that have opted in
  appear on public pages; unpublished clubs return 404.
- [x] Templates: extend `public_site.public_layout`; apply `t-cache` to the
  club list (TTL 1 h) to reduce DB load.
- [x] Tests: smoke `HttpCase` asserting `/clubs` returns HTTP 200; assert an
  unpublished club does not appear on the list or via its slug.

Done when: public club and team pages are live; unpublished clubs are hidden.

### 4. Public site — player profile pages

Module: `sports_federation_public_site`

**Problem:** Players have no public presence. Scouts, fans, and players
themselves cannot view career summaries from the public site.

Work:
- [x] Add `public_visible` boolean field (default `False`) to
  `federation.player`; only federation manager or club admin can enable it.
- [x] Add `public_slug` to `federation.player` (use same helper pattern as
  existing tournament `public_slug`).
- [x] Add route `/players` listing players where `public_visible = True`.
- [x] Add route `/players/<slug>` showing full name, nationality, current
  team, season-by-season appearance counts, and licenses held.
- [x] Tests: `HttpCase` asserting `/players/<slug>` returns HTTP 200 for a
  `public_visible=True` player; returns 404 for `public_visible=False`; the
  `/players` list does not enumerate `public_visible=False` players.

Done when: public player profiles are accessible; private players are not
discoverable from public routes; CI passes.

---

## Phase 3 — Weeks 5–6: Finance Bridge Integration

**Phase 3 complete — fee schedules, auto-trigger, and invoice generation implemented and CI green.**

### 5. Fee schedules — category and season-based rate cards

Module: `sports_federation_finance_bridge`

**Problem:** `federation.finance.fee_type` holds flat fee codes but has no
seasonal or category-based rates. A youth team and a senior team pay the same
registration fee. Season-over-season rate changes require direct database edits.

Work:
- [x] Create `models/fee_schedule.py` with model `federation.fee.schedule`:
  fields `season_id`, `fee_type_id`, `category` (selection matching
  `federation.team.category`), `gender`, `amount`, `currency_id`.
- [x] Add `_sql_constraint` enforcing uniqueness on
  `(season_id, fee_type_id, category, gender)`.
- [x] Add `ir.model.access.csv` entry and tree/form view in `views/`.
- [x] Update `FinanceEvent` creation helpers to look up the schedule before
  falling back to `fee_type.default_amount`.
- [x] Tests: assert schedule lookup returns the correct amount for a youth team
  in a season that has a schedule row; falls back to default when no schedule
  row exists.

Done when: seasonal rate cards exist; events use schedule rates when available;
fallback is safe; CI passes.

### 6. Auto-trigger — registration confirmation creates finance event

Module: `sports_federation_finance_bridge`

**Problem:** Season registration confirmation does not automatically create a
`federation.finance.event`. Staff must manually enter registration fees, leading
to missed invoicing.

Work:
- [x] In `sports_federation_finance_bridge` via `_inherit` on
  `federation.season.registration`, hook the `write` method: when `state`
  transitions to `confirmed`, call
  `env['federation.finance.event'].sudo()._create_from_registration(reg)`.
- [x] `_create_from_registration`: resolve the correct fee schedule row
  (season + team category + gender); create the event with `origin_ref`
  pointing to the registration record.
- [x] Guard: if no matching fee type or schedule exists, log a warning and
  skip — never crash the confirmation flow.
- [x] Tests: assert confirming a registration creates exactly one finance event
  with the correct fee amount; assert a second confirmation of the same
  registration does not create a duplicate event.

Done when: every registration confirmation auto-creates a finance event; the
no-fee-type guard is verified; CI passes.

### 7. Invoice generation — finance event → account.move

Module: `sports_federation_finance_bridge`

**Problem:** Finance events are never converted to invoices. Accountants must
manually create `account.move` records. The bridge module exists but has no
invoice generation path. Currently `invoice_ref` is a plain `Char` field —
no relational link to accounting.

Work:
- [x] Add `invoice_id` Many2one (`account.move`, `ondelete='set null'`) to
  `federation.finance.event`; add the migration file.
- [x] Add method `action_create_invoice()`: creates an `account.move` of type
  `out_invoice` with the event amount and links the result via `invoice_id`.
- [x] Add "Create Invoice" button on the finance event form, visible only when
  `invoice_id` is not set and `state != 'cancelled'`.
- [x] Add a batch "Create Invoices" server action on the finance event list
  view for selected records.
- [x] Guard: skip silently if `account.move` model is not installed (optional
  Odoo Accounting dependency).
- [x] Tests: assert `action_create_invoice()` creates one `account.move` with
  the correct amount; assert calling it twice does not create a second invoice.

Done when: federation finance staff can generate invoices from events with one
click; batch action available for end-of-month runs; CI passes.

---

## Phase 4 — Weeks 7–8: Reliability, Coverage & UX Polish

**Phase 4 complete — all CI green (competition_engine 46/46, people 27/27, tournament 60/60, reporting 64/64, standings 22/22).**

### 8. Match Day empty — bulk schedule date wizard

Module: `sports_federation_competition_engine`

**Problem:** When the round-robin or knockout wizard generates matches,
`federation.match.date_scheduled` is often left `False`. The portal's "Match
Day" view filters on `match_kickoff != False` (a stored related field of
`date_scheduled`), so club representatives see an empty page even though
matches exist. Operators have no bulk tool to assign kickoff dates after
schedule generation.

Work:
- [x] Add wizard `federation.round.date.wizard` (transient) with fields:
  `stage_id`, `round_id` (domain filtered by stage), `date_scheduled`
  (Datetime), and an `action_apply` button that sets `date_scheduled` on all
  matches in the selected round.
- [x] Add "Set Kickoff Dates" smart button on the tournament stage form and on
  the round list view.
- [x] Validate that `date_scheduled` falls within the stage's date window if
  one is defined; raise a user-friendly `ValidationError` otherwise.
- [x] Tests: assert wizard sets `date_scheduled` on all targeted matches;
  assert matches in other rounds are not touched.

Done when: operators can bulk-assign kickoff dates to a round with one action;
Match Day portal shows the newly scheduled matches; CI passes.

### 9. People module — test coverage expansion

Module: `sports_federation_people`

**Problem:** `federation.player` and `federation.player_license` form the
foundational identity layer. Eight other modules inherit or extend this model.
Currently only one test file (`test_people.py`) exists — license lifecycle,
expiry, duplicate detection, and archive/restore guards are untested.

Work:
- [x] Add `tests/test_player_license.py` covering: license creation and state
  transitions (draft → active → expired / suspended); `is_eligible` computed
  field with an expired license; duplicate license detection for the same
  player and season.
- [x] Add `tests/test_player_archive.py` covering: archiving a player with an
  active roster line raises a `ValidationError` or surfaces an appropriate
  warning; restoring a player re-enables roster eligibility.
- [x] Tests: assert `is_eligible` is `False` when the player has no active
  license for the season; assert a duplicate license is blocked by constraint.

Done when: CI passes with ≥ 10 new test assertions covering license lifecycle
and archive/restore guards.

### 10. Tournament model — coverage expansion

Module: `sports_federation_tournament`

**Problem:** Eleven model files are covered by only 3 test files. The match
bracket linking fields (`source_match_*`, `next_match_ids`) and auto-advance
wiring (`_advance_bracket_teams()`) are entirely untested at the unit level.

Work:
- [x] Add `tests/test_bracket_linking.py` covering: source match wiring for a
  4-team knockout; `_advance_bracket_teams()` called on `action_done()` sets
  the winner into the next match's `team_home_id` or `team_away_id`; placeholder
  match state before/after advancement.
- [x] Add `tests/test_participant_lifecycle.py` covering: participant
  confirmation guard (active roster required after deadline); participant
  withdrawal; re-confirmation after correction.
- [x] Tests: assert `_advance_bracket_teams()` sets the correct team on the
  next bracket node; assert withdrawal sets participant `state` to
  `withdrawn`.

Done when: CI passes with ≥ 12 new test assertions covering bracket advancement
and participant lifecycle.

### 11. Reporting — targeted coverage for highest-risk models

Module: `sports_federation_reporting`

**Problem:** 17 model files are served by only 4 test files. The cron-driven
`report_schedule`, `report_operational`, `report_finance_reconciliation`, and
`report_standing_reconciliation` models have no focused unit tests. Silent
failures in the cron would go undetected.

Work:
- [x] Add `tests/test_report_schedule_cron.py` covering: `action_run_schedule()`
  creates a snapshot row for the expected report type; a failure in one report
  type does not crash the others; the generated file has a non-zero byte count.
- [x] Add `tests/test_report_reconciliation.py` covering: standing
  reconciliation detects a missing standing for a confirmed participant; finance
  reconciliation flags a finance event with no counterparty.
- [x] Tests: assert cron run creates ≥ 1 `report.schedule` output row; assert
  reconciliation note is non-empty when a mismatch is present.

Done when: CI passes with ≥ 8 new assertions covering the cron and two
reconciliation models.

### 12. Data integrity — missing constraints and ondelete guards

Modules: `sports_federation_tournament`, `sports_federation_people`,
`sports_federation_standings`

**Problem:** Three missing data-integrity guards were found in the audit that
can produce silent data corruption at scale:

1. **No `UNIQUE(tournament_id, team_id)` on `federation.tournament.participant`.**
   Duplicate participants silently skew standings and schedule generation.
2. **`federation.player.nationality_id` uses default `ondelete='restrict'`.**
   Deleting a country record raises an opaque DB error instead of `set null`.
3. **`federation.standing.competition_id` should use `ondelete='cascade'`**
   (currently `set null`): orphaned standing records with no competition
   reference accumulate over time.

Work:
- [x] Add `_sql_constraint` `UNIQUE(tournament_id, team_id)` to
  `federation.tournament.participant`; add migration.
- [x] Change `nationality_id` on `federation.player` to
  `ondelete='set null'`; add migration.
- [x] Change `competition_id` on `federation.standing` to
  `ondelete='cascade'`; add migration; update any tests that rely on current
  `set null` behaviour.
- [x] Tests: assert a duplicate participant creation raises a constraint error;
  assert deleting a country record does not raise an `IntegrityError` on the
  player.

Done when: all three constraints are in place; CI passes; no silent orphan
records can accumulate.

### 13. Housekeeping — venues wizard cleanup & tournament form UX

Modules: `sports_federation_venues`, `sports_federation_tournament`

**Problem (venues):** `sports_federation_venues/wizards/` exists but is
completely empty (only `__pycache__`). The directory causes confusion and may
surface warnings about unreferenced paths.

**Problem (tournament form):** The `federation.tournament` form view has 18+
fields in a flat layout with no notebook tabs. Staff must scroll through all
fields to reach scheduling or rules fields.

Work:
- [x] Remove the empty `wizards/` directory from `sports_federation_venues`;
  confirm nothing in `__manifest__.py` references it.
- [x] Add a `<notebook>` to the `federation.tournament` form view with four
  pages: "Basic Info" (name, code, type, status), "Scope" (season,
  competition, categories), "Schedule & Rounds" (dates, rounds, venue), and
  "Rules & Overrides" (rule set, override requests).
- [x] Update the tournament form view test (if any) to assert at least one
  notebook page renders without error.

Done when: `venues/wizards/` is removed; tournament form uses notebook tabs;
CI passes.

---

## Phase 5 — Weeks 9–10: Club-Provided Referee Duty

### 14. Club referee duty — obligation tracking, nomination, and confirmation

Modules: `sports_federation_officiating` (model + back-office),
`sports_federation_portal` (club-rep nomination flow)

**Background:** Some match formats require that each club supply one of their
own players or members as a table/assistant official for the opposing team's
game. Currently there is no way to record that obligation, ask the club to
nominate someone, or link the nomination back to the match's officiating
readiness. The existing `federation.match.referee` model tracks *certified*
standalone referees; club-supplied referees are a distinct concept — the
person's primary identity in the system is a `federation.player`, not a
`federation.referee`, and the assignment authority belongs to the club, not
the federation.

**Chosen approach:** A new `federation.match.club.referee.duty` model
represents the obligation. Once the club nominates a player and the federation
confirms, the system automatically creates a `federation.match.referee`
assignment (role = configurable, defaults to `table`) so that all existing
officiating-readiness logic keeps working without changes.

**Workflow states:**
```
draft  →  open  →  nominated  →  confirmed
                      ↓
                   rejected  →  nominated  (club re-nominates)
```

- `draft` — planner created the duty record; club not yet notified.
- `open` — planner published the duty; club portal shows it and can nominate.
- `nominated` — club rep submitted a player name from their roster.
- `confirmed` — federation admin confirmed; `federation.match.referee` record
  created automatically.
- `rejected` — federation admin rejected nomination; club can re-nominate.

Work:
- [x] **New model `federation.match.club.referee.duty`** in
  `sports_federation_officiating/models/`:
  - `match_id` Many2one `federation.match` (required, cascade)
  - `club_id` Many2one `federation.club` (required)
  - `role` Selection (same values as `federation.match.referee.role`,
    default `table`)
  - `state` Selection `draft/open/nominated/confirmed/rejected`
  - `nominated_player_id` Many2one `federation.player` (the club's nominee;
    domain restricts to players whose active roster includes `club_id`)
  - `nominated_by_id` Many2one `res.users` (set automatically on nomination)
  - `nominated_on` Datetime (set automatically)
  - `nomination_deadline` Datetime (computed: `match.date_scheduled − 72 h`)
  - `is_deadline_overdue` Boolean (computed)
  - `assignment_id` Many2one `federation.match.referee` (readonly; populated
    on confirmation)
  - `notes` Text
  - SQL constraint: unique `(match_id, club_id, role)` — a club can owe at
    most one duty per role per match.
- [x] **State actions** on the duty model:
  - `action_open` (planner): draft → open; triggers notification to club rep.
  - `action_nominate(player_id)` (club portal): open/rejected → nominated;
    validates player belongs to club.
  - `action_confirm` (federation admin): nominated → confirmed; creates
    `federation.match.referee` record linked in `assignment_id`.
  - `action_reject(reason)` (federation admin): nominated → rejected; stores
    reason in notes; returns duty to club for re-nomination.
  - `action_cancel`: any non-confirmed → draft (admin escape hatch).
- [x] **Match extension**: add `club_referee_duty_ids` One2many and
  `club_duty_pending_count` Integer computed field to
  `FederationMatchRefereeExtension` (already in `federation_match_referee.py`).
  Show a "Club Duties" stat button on the match form (always visible) and a
  second inline notebook sub-page alongside the Officials page.
- [x] **Portal controller** (`sports_federation_portal/controllers/`):
  - `GET /my/referee-duties` — lists open and nominated duties for the club
    rep's clubs.
  - `GET /my/referee-duties/<id>` — duty detail with nomination form.
  - `POST /my/referee-duties/<id>/nominate` — club rep submits
    `player_id`; calls `action_nominate(player_id)`; enforces club scope via
    `portal_club_scope_ids`.
  - Record-rule: club rep can read duties where `club_id ∈
    portal_club_scope_ids`; can write (nominate) only in state `open` or
    `rejected`.
- [x] **Portal templates** under
  `sports_federation_portal/views/templates/`:
  - `portal_referee_duty_list.xml` — duty list card, shows match name, role,
    deadline, state badge.
  - `portal_referee_duty_form.xml` — duty detail with player selection
    dropdown (filtered to club's rostered players) and submit button.
- [x] **Back-office views** in `sports_federation_officiating/views/`:
  - `federation_match_club_referee_duty_views.xml` — form (with header buttons
    for each state action), list (with deadline overdue decoration), search
    (filter by state/club/match).
  - Add menu item under Officiating > Club Duties.
- [x] **ACL**: add manager (full) and user (read-only) rows for
  `federation.match.club.referee.duty`.
- [x] **Tests** in `sports_federation_officiating/tests/`:
  - Duty lifecycle: draft → open → nominated → confirmed → assignment created.
  - Rejection path: nominated → rejected → re-nominated → confirmed.
  - `action_nominate` raises if player is not in club's roster.
  - Confirmation auto-creates `federation.match.referee` with correct role and
    `match_id`.
  - Portal controller: club rep can only nominate for their own club's duties;
    cross-club nomination raises `AccessError`.
  - Deadline overdue flag becomes True when duty is open past deadline.

Done when: a planner can create a club referee duty, the club rep can nominate
via portal, federation admin confirms and the match automatically gains a
`federation.match.referee` assignment; CI passes.

**Phase 5 complete — club referee duty obligation tracking, nomination, and confirmation implemented and CI green (55/55 tests passing).**

---

## Suggested Sequence

1. **Item 0 (Phase 0)**: self-contained to `officiating`; no model dependencies;
   can start immediately and run in parallel with any other phase.
2. Items 1–2 (Phase 1): portal-only changes; highest user-facing impact; can
   be developed in parallel.
3. Items 3–4 (Phase 2): public site additions; isolated to `public_site`;
   start after Portal CI is green.
4. Items 5–7 (Phase 3): model changes in `finance_bridge`; item 7 depends on
   item 6 (invoice_id requires the event hook to be in place first).
5. Items 8–13 (Phase 4): mostly independent; no cross-module model changes
   except item 12 (three modules, low risk).
6. **Item 14 (Phase 5)**: depends on Phase 0 (`federation.match.referee`
   already exists) and Phase 1 portal patterns (`portal_club_scope_ids`);
   start after both are green. Portal controller follows the same fixture
   pattern as roster/result portal flows.

---

## Security Invariants to Preserve

- `_assert_portal_owns()` must remain the sole write gate for all new portal
  controllers (items 1 and 2).
- Portal result approval (item 1): the `sudo()` call to `action_approve_result()`
  must only be reachable after `_assert_portal_owns()` confirms the rep's club
  owns the home or away team of the match.
- Portal result contest (item 2) must NOT allow a rep to contest a result for a
  match whose home and away teams are both outside their club scope.
- Club representatives must NOT be able to reach `action_submit_result()` via
  any portal route; submission is reserved for match officials / federation
  staff via back-office flows.
- Public player pages (item 4) must only render for `public_visible = True`
  players; the `/players` list must never enumerate private player IDs.
- Finance event → invoice generation (item 7) must not crash when `account.move`
  is not available; guard with `self.env.registry.get('account.move')`.
- Data integrity constraints (item 12) must be DB-level `_sql_constraints`
  (not just Python-level validation); each must have a migration file.

---

## Known Deferred Items (not in this cycle)

Items carried from the previous cycle's deferred list, updated with new findings:

- **Season closure checklist** — constraint blocking `federation.season`
  `state → closed` unless all linked tournaments are closed or cancelled.
- **Referee reimbursement queue** — `ReimbursementRequest` model aggregating
  per-referee amounts with a bank-transfer export action.
- **Club compliance summary report** — `ReportClubComplianceSummary` per
  season with submission counts, approval rates, and remediation queue size.
- **Referee assignment coverage KPI** — `ReportOfficiatingCoverage` tracking
  percentage of matches covered by the required referee count per tournament.
- **Standing lines visual ranking** — rank badge (gold/silver/bronze) on the
  standing lines list view.
- ~~**Rate limiting on public JSON API routes**~~ — ✅ Implemented via
  `federation.request.rate.limit` model (sliding-window, DB-backed, per-IP)
  applied to `/competitions/api/json`, `/api/v1/tournaments/*/feed`, and
  `/api/v1/teams/*/feed`. Limits are configurable via `ir.config_parameter`
  (`sports_federation.rate_limit.<scope>.limit/window_seconds`). 3 controller
  tests + 2 unit tests cover block-after-limit and window-rollover behaviour.
- **Integration partner token rotation** — `integration_partner_token_wizard.py`
  exists but no scheduled rotation reminder or forced-rotation policy is in
  place.

---

## Exit Criteria

- All 13 items have passing CI test suites.
- No module has a `[ ]` checkbox in this file.
- `bash addons/ci/run_tests.sh --module <each affected module>` exits 0.
- No new `flake8` violations introduced (run `flake8 addons/` before merge).
