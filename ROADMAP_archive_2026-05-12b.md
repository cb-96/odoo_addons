# ROADMAP — 2026-05-12 Completeness & Correctness Program (ARCHIVED)

Last updated: 2026-05-12
Archived: 2026-05-12
Owner: Federation Platform Team
Release train: 2026.09

Archived by: full codebase review on 2026-05-12 (second cycle of the day).

**Completion status at archive:** Items 1–5 (test suites) ✅ done. Item 10
(bracket page) ✅ done. Items 6–9 and 11–13 carried forward into the next
roadmap (`ROADMAP.md`).

The previous operating-period roadmap is archived in
`ROADMAP_archive_2026-05-12.md`.
This roadmap is driven by a full codebase audit conducted on 2026-05-12. All 13
items from the 2026-05-11 UX cycle are closed. This cycle addresses four
structural gaps found in the audit: missing test suites on five modules, an
incomplete portal flow for result submission, a minimal public site missing
club/player/bracket pages, and a finance bridge that creates events but never
generates invoices.

---

## State of the Codebase

### What Has Gone Well (2026-05-11 → 2026-05-12)

**All 13 items from the UX improvement cycle are closed.** The May-11 cycle
delivered: contextual `error_hint` on all portal error paths, portal navigation
restructured into three workflow-grouped sections ("Your Season", "Match Day",
"Club Admin"), and demo data expanded into a realistic end-to-end scenario (2
tournament stages, 8 teams, 20 players, 6 completed matches, standings,
compliance, disciplinary cases, notification logs).

**Security baseline remains strong.** `_assert_portal_owns()` gate, token
hashing, upload guardrails, partial unique indexes, and no raw exception
surfacing are all intact.

### Focus for This Cycle

Five modules — `officiating`, `notifications`, `import_tools`, `governance`,
`finance_bridge` — have zero test coverage, making them unsafe to refactor or
extend. The portal has no path for club representatives to submit match results.
The public site has no club, player, or bracket pages. The finance bridge
creates events but has no invoice generation, fee schedules, or auto-trigger on
registration confirmation. This cycle closes those gaps.

---

## Phase 1 — Weeks 1–2: Missing Test Suites

### 1. Officiating — first regression tests

Module: `sports_federation_officiating`

**Problem:** Three models (`FederationReferee`, `FederationMatchReferee`,
`FederationRefereeCertification`) have no test directory. State transitions
(draft → confirmed → done / cancelled), readiness computation, and
certification-level validation have never been regression-tested.

Work:
- [x] Create `tests/__init__.py` and `tests/test_officiating.py`.
- [x] Cover: referee creation and certification validation; match referee
  assignment creation; `assignment_readiness` computation with missing
  certifications; state transitions (confirm, execute, cancel) including
  guard conditions; and duplicate assignment detection.
- [x] Tests: assert `assignment_readiness` is `False` when certification level
  is below the required threshold; assert `action_confirm` raises for
  referee with no valid certification.

Done when: CI passes with ≥ 8 test assertions covering the four main assignment
lifecycle paths.

### 2. Notifications — first regression tests

Module: `sports_federation_notifications`

**Problem:** Four models (log, service, dispatcher, season-registration hooks)
have no test coverage. Email dispatch, activity creation, retry logic, and
deduplication are entirely untested.

Work:
- [x] Create `tests/__init__.py` and `tests/test_notifications.py`.
- [x] Cover: notification log creation on registration decision (confirmed /
  rejected); activity creation for validators; dispatch failure handling
  (state → failed, retry count incremented); deduplication (second identical
  trigger does not create duplicate log).
- [x] Mock email send via `mail.test_mode` or `self.env['mail.mail'].sudo()`.
- [x] Tests: assert log entry exists with correct `target_model` and
  `target_res_id`; assert duplicate suppression.

Done when: CI passes with ≥ 6 test assertions covering dispatch and deduplication.

### 3. Import tools — first regression tests

Module: `sports_federation_import_tools`

**Problem:** Five import wizards (club, team, player, season, participant) share
a mixin with UTF-8 BOM handling, delimiter detection, dry-run statistics, and
code-based matching. None are regression-tested.

Work:
- [x] Create `tests/__init__.py` and `tests/test_import_wizards.py`.
- [x] Cover: UTF-8 BOM stripping; semicolon vs. comma auto-detection; dry-run
  statistics (created_count, updated_count, skipped_count, error_rows); code-based
  matching (existing record updated, not duplicated); row-level failure
  categorisation (missing required column → error row, not crash).
- [x] Provide minimal in-memory CSV bytes for each test case (no file system
  needed).
- [x] Tests: assert dry-run does not persist records; assert code-match updates
  existing player rather than creating duplicate.

Done when: CI passes with ≥ 10 test assertions covering the mixin's main paths.

### 4. Governance — first regression tests

Module: `sports_federation_governance`

**Problem:** Four models (override request, decision, audit note, outcome) have
no tests. State machine (draft → submitted → approved / rejected → implemented)
is untested.

Work:
- [x] Create `tests/__init__.py` and `tests/test_governance.py`.
- [x] Cover: override request creation in draft; submit transition; approve and
  reject decision paths; audit note creation; outcome record assignment on
  approval; guard preventing transition from non-draft state without right group.
- [x] Tests: assert `action_submit` raises `ValidationError` if request lacks
  a reason; assert audit trail length increases on each transition.

Done when: CI passes with ≥ 6 test assertions covering the 5 workflow states.

### 5. Finance bridge — first regression tests

Module: `sports_federation_finance_bridge`

**Problem:** Fee types, finance events, season budgets, and hooks for
sanctions/results/venues exist but have no tests. No baseline prevents
regression when the bridge is extended in Phase 4.

Work:
- [x] Create `tests/__init__.py` and `tests/test_finance_bridge.py`.
- [x] Cover: fee type creation and uniqueness constraint; finance event creation
  with correct fee type linkage; season budget creation and balance tracking;
  hook execution when a sanction is issued (event created); hook guard when fee
  type is missing (warning logged, no crash).
- [x] Tests: assert a created finance event has a non-null `fee_type_id`; assert
  sanction hook creates exactly one event per sanction.

Done when: CI passes with ≥ 8 test assertions covering event creation and the
sanction hook.

---

## Phase 2 — Weeks 3–4: Portal Result Submission

### 6. Portal — club rep result submission flow

Module: `sports_federation_portal`

**Problem:** Club representatives have a portal path for rosters, match sheets,
squad submission, and officiating responses — but no way to submit match results.
`federation.match_result_control.action_submit_result` is back-office only.
Reps must contact federation staff to submit results.

Work:
- [ ] Create `controllers/result_portal.py` with:
  - `GET /my/results` — paginated list of the club's matches with result status
    column (draft / submitted / verified / approved / contested).
  - `GET /my/results/<int:match_id>` — result detail showing current score,
    status, and any audit trail entries.
  - `POST /my/results/<int:match_id>/submit` — calls
    `action_submit_result()` guarded by `_assert_portal_owns()` on the
    match's home or away team; redirects with success/error flash.
- [ ] Add portal menu item "Results" under the "Match Day" group (sequence
  between Match Day and Match Sheets).
- [ ] Add `_portal_get_domain` on `federation.match_result_control` scoped
  to the user's `portal_club_scope_ids`.
- [ ] Update `portal_templates.xml`: list view template
  `portal_my_results` and detail template `portal_my_result_detail`.
- [ ] Security: add `ir.model.access.csv` read ACL for
  `federation.match_result_control` for `base.group_portal`.
- [ ] Tests: `HttpCase` asserting that the result list renders for a portal
  user with club scope; assert that posting to `/my/results/<id>/submit`
  advances `result_status` to `submitted`; assert that a different club's
  rep gets a 403 page.

Done when: a club rep can submit a result from `/my/results`; the 403 guard
is in place; CI passes.

### 7. Portal — result dispute flow

Module: `sports_federation_portal`

**Problem:** After a result is approved, a club rep has no portal path to
contest it. The back-office `federation.match_result_audit` model exists but
is unreachable from the portal.

Work:
- [ ] Add `POST /my/results/<int:match_id>/dispute` creating a
  `federation.match_result_audit` record with `audit_type = 'contest'` and
  the rep's stated reason; guard with `_assert_portal_owns()`.
- [ ] Show a "Dispute Result" button on the result detail page only when
  `result_status == 'approved'`.
- [ ] Block re-dispute if an open contest audit already exists for this match.
- [ ] Tests: assert dispute button only renders when `result_status == 'approved'`;
  assert second dispute POST is blocked with a friendly error.

Done when: club reps can dispute approved results from the portal; duplicate
disputes are prevented.

---

## Phase 3 — Weeks 5–6: Public Site Completeness

### 8. Public site — club and team profile pages

Module: `sports_federation_public_site`

**Problem:** The public site shows tournament schedules and standings but has no
individual club or team pages. External visitors (media, players considering
joining, partner clubs) cannot look up a club's teams, recent tournament
performance, or contact information.

Work:
- [ ] Add route `/clubs` listing all `website_published` clubs ordered by name.
- [ ] Add route `/clubs/<slug>` showing club name, contact, linked teams, and
  recent tournament participation (last 3 seasons).
- [ ] Add route `/teams/<slug>` showing team name, category, gender, and a table
  of matches played (public matches only, `date_scheduled` + score + opponent).
- [ ] Use `website_published` (or a new `public_visible` boolean) as the guard
  — only clubs that have opted in appear on public pages.
- [ ] Templates: extend `public_site.public_layout`; use `t-cache` for club
  list (TTL 1 h) to reduce DB load.
- [ ] Tests: smoke `HttpCase` asserting `/clubs` returns HTTP 200; assert an
  unpublished club does not appear on the list.

Done when: public club and team pages are live; unpublished clubs are hidden.

### 9. Public site — player profile pages

Module: `sports_federation_public_site`

**Problem:** Players have no public presence. Scouts, fans, and players
themselves cannot view career summaries from the public site.

Work:
- [ ] Add route `/players` listing players whose profile is `public_visible`.
- [ ] Add route `/players/<slug>` showing: full name, nationality, current team,
  season-by-season appearance counts, goals/assists (if tracked), and
  licenses held.
- [ ] `public_visible` defaults to `False`; club admin or federation manager
  can enable it per player.
- [ ] Add `public_slug` to `federation.player` (use same pattern as existing
  tournament public slugs).
- [ ] Tests: `HttpCase` asserting `/players/<slug>` returns 200 for a
  `public_visible=True` player; returns 404 for `public_visible=False`.

Done when: public player profiles are accessible; private players are not
discoverable from public routes.

### 10. Public site — knockout bracket page

Module: `sports_federation_public_site`

**Problem:** Knockout tournaments have a bracket structure in the data model
(`source_match_1_id`, `source_match_2_id`, `next_match_ids`) but the public
site shows only a flat match schedule. Visitors cannot follow the elimination
tree.

Work:
- [x] Add route `/competitions/<slug>/bracket` returning bracket data.
- [x] Backend: add a service method on `FederationTournament` (or
  `sports_federation_competition_engine`) that returns the bracket tree as a
  nested Python dict.
- [x] Template: render the tree as a nested `<div class="bracket-round">` HTML
  structure (pure CSS flexbox bracket; no external JS library required).
- [x] Only show for tournaments with `tournament_type == 'knockout'`; show
  "Not available for group-stage tournaments" otherwise.
- [x] Tests: unit test on the bracket-builder service asserting correct tree
  structure for a 4-team knockout (semifinal → final node tree).

Done when: `/competitions/<slug>/bracket` renders a correct bracket tree for
knockout tournaments; service method has a unit test.

---

## Phase 4 — Weeks 7–8: Finance Bridge Integration

### 11. Fee schedules — category and season-based rate cards

Module: `sports_federation_finance_bridge`

**Problem:** `federation.finance.fee_type` holds flat fee codes but has no
seasonal or category-based rates. A youth team and a senior team pay the same
registration fee. Season-over-season rate changes require direct database edits.

Work:
- [ ] Create `models/fee_schedule.py` with model `federation.fee.schedule`:
  fields `season_id`, `fee_type_id`, `category` (selection matching
  `federation.team.category`), `gender`, `amount`, `currency_id`.
- [ ] Add `_sql_constraint` ensuring uniqueness on
  `(season_id, fee_type_id, category, gender)`.
- [ ] Add `ir.model.access.csv` entry; add tree/form view in `views/`.
- [ ] Update `FinanceEvent` creation helpers to look up the schedule before
  falling back to the flat `fee_type.default_amount`.
- [ ] Tests: assert schedule lookup returns correct amount for a youth team in
  a season that has a schedule; falls back to default when no schedule row
  exists.

Done when: seasonal rate cards exist; events use schedule rates; fallback is
safe.

### 12. Auto-trigger — registration confirmation creates finance event

Module: `sports_federation_finance_bridge`

**Problem:** Season registration confirmation does not automatically create a
`federation.finance.event`. Staff must manually enter registration fees, leading
to missed invoicing.

Work:
- [ ] In `sports_federation_base` (or `finance_bridge` via `_inherit`), hook
  `federation.season.registration` write: when `state` transitions to
  `confirmed`, call `env['federation.finance.event'].sudo()._create_from_registration(reg)`.
- [ ] `_create_from_registration` resolves the correct fee schedule row
  (season + category + gender); creates the event with `origin_ref` pointing
  to the registration record.
- [ ] Guard: if no matching fee type exists, log a warning and skip (never
  crash the confirmation flow).
- [ ] Tests: assert confirming a registration creates exactly one finance event
  with correct fee amount; assert second confirmation does not duplicate the
  event.

Done when: every registration confirmation auto-creates a finance event; CI
passes.

### 13. Invoice generation — finance event → account.move

Module: `sports_federation_finance_bridge`

**Problem:** Finance events are never converted to invoices. Accountants must
manually create `account.move` records. The bridge module exists but has no
invoice generation path.

Work:
- [ ] Add method `action_create_invoice()` on `federation.finance.event`:
  creates an `account.move` (type `out_invoice`) with the event amount and
  links the resulting invoice via `invoice_id` Many2one.
- [ ] Add "Create Invoice" button on the finance event form, visible when
  `invoice_id` is not set and `state != 'cancelled'`.
- [ ] Add batch "Create Invoices" server action on the finance event list view
  for selected records.
- [ ] Add `invoice_id` Many2one (→ `account.move`, `ondelete='set null'`) to
  `federation.finance.event`.
- [ ] Guard: skip if `account.move` model is not installed (optional bridge).
- [ ] Tests: assert `action_create_invoice()` creates one `account.move`
  with the correct amount; assert calling it twice does not create a second
  invoice.

Done when: federation finance staff can generate invoices from events with one
click; batch action available for end-of-month runs.

---

## Suggested Sequence

1. Items 1–5 (Phase 1): no model changes; highest-risk gap (zero-coverage
   modules); can be developed in parallel per module.
2. Items 6–7 (Phase 2): portal changes only; depend on existing result control
   model being stable (Phase 1 tests verify this).
3. Items 8–10 (Phase 3): new public routes and templates; isolated to
   `public_site`; can start as soon as Phase 1 is green.
4. Items 11–13 (Phase 4): model and hook changes in `finance_bridge`; item 13
   depends on item 12 having the event creation hook in place.

---

## Security Invariants to Preserve

- `_assert_portal_owns()` must remain the sole write gate for all new portal
  controllers (items 6 and 7).
- Portal result dispute (item 7) must NOT allow a rep to dispute a result for a
  match whose home and away teams are both outside their club scope.
- Public player pages (item 9) must only render for `public_visible = True`
  players; the route must never enumerate all player IDs.
- Finance event → invoice generation (item 13) must not crash when
  `account.move` is not available (optional dependency guard).
- Import audit trail (noted gap): do not remove or weaken the mixin's
  row-level failure reporting while adding tests in item 3.

---

## Known Deferred Items (not in this cycle)

The audit surfaced additional lower-priority issues recorded here for the next
cycle:

- **Tournament form grouping** — 18+ fields with no notebook tabs; suggested
  split: Basic Info / Scope / Details / Rules & Schedule.
- **Referee reimbursement queue** — `ReimbursementRequest` model aggregating
  per-referee amounts with a bank-transfer export action.
- **Club compliance summary report** — `ReportClubComplianceSummary` per
  season with submission counts, approval rates, and remediation queue size.
- **Referee assignment coverage KPI** — `ReportOfficiatingCoverage` tracking
  % of matches covered by the required referee count per tournament.
- **Season closure checklist** — constraint blocking `federation.season`
  `state → closed` unless all linked tournaments are closed/cancelled.
- **`nationality_id` ondelete** — `federation.player.nationality_id` should
  use `ondelete="set null"` rather than the default restrict.
- **Standing cascade on competition delete** — `competition_id` on
  `federation.standing` should be `ondelete="cascade"` (currently set null).
- **Tournament participant uniqueness constraint** — missing
  `UNIQUE(tournament_id, team_id)` on `federation.tournament.participant`.
- **Rate limiting on public JSON API routes** — `/api/competitions`,
  `/api/standings`, `/api/matches` receive no rate limiting.
- **Standing lines visual ranking** — rank badge (gold/silver/bronze for top 3)
  on the standing lines list view.

---

## Exit Criteria

- All five previously zero-coverage modules have passing CI test suites (≥ 6
  assertions each).
- Club representatives can submit match results from `/my/results` and dispute
  approved results from the same page; both paths have the 403 guard in place.
- Public club, team, player, and bracket pages are live; unpublished/private
  records are not accessible.
- `federation.fee.schedule` model exists; confirming a season registration
  auto-creates a finance event using the correct schedule rate.
- Finance events have a "Create Invoice" action that produces a correct
  `account.move`; batch action available.
- Full CI green (all existing suites continue to pass).
