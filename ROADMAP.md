# ROADMAP — 2026-05-11 UX Improvement Program

Last updated: 2026-05-11
Owner: Federation Platform Team
Last reviewed: 2026-05-11
Review cadence: Every release
Release train: 2026.07

The previous operating-period roadmap is archived in
`ROADMAP_archive_2026-05-11.md`.
This roadmap is driven by a full UX audit conducted on 2026-05-11. All 8 items
from the 2026-05-10 cycle are closed. This cycle focuses on user experience —
feedback clarity, form usability, navigation completeness, and portal polish —
while preserving the strong security baseline already in place.

---

## State of the Codebase

### What Has Gone Well (2026-05-10 → 2026-05-11)

**All 8 items from the previous roadmap are closed.** The May-10 cycle delivered:
portal ownership guard (`_assert_portal_owns()`), club-rep URL guessing protection
(HTTP 403 for wrong-owner access), roster uniqueness constraint corrected
(removed ineffective name-based constraint, kept 19.0.1.4.0 partial indexes),
name-generation race condition eliminated, O(n²) participant lookup in
`_build_standing_table()` fixed with dict lookup, performance regression test
(200 matches, ≤10 queries), and Phase 4 docs/UX polish (standings README
corrected, `help=` added to 6 ambiguous fields).

**Security baseline is strong.** Token hashing, upload guardrails, exception
sanitization, `_assert_portal_owns()` gate, partial unique indexes for active
rosters, and no raw `IntegrityError` surfacing to users are all in place.

### Focus for This Cycle

The codebase has good backend correctness. The user-facing layer — admin forms,
wizards, portals, and notifications — still has friction that slows down federation
administrators, club representatives, and end users. This cycle addresses the 22
most impactful issues found in the audit.

---

## Phase 1 — Weeks 1–2: Feedback & Notifications

### 1. Wizard success notifications after schedule generation

Module: `sports_federation_competition_engine`

**Problem:** The round-robin and knockout schedule wizards close silently after
execution. Users must navigate away to verify matches were actually created. The
import wizards show a `result_message` field after import but no toast notification
and no link to immediately view the created records.

**Impact:** Administrators don't know if the wizard ran successfully. Silent closes
cause double-execution ("nothing happened so I clicked again").

Work:
- [x] In `RoundRobinWizard.action_generate()` and `KnockoutWizard.action_generate()`,
  return an `ir.actions.client` `display_notification` action with a match count
  message and a `next` action opening the generated matches list.
- [x] In the import wizards (`PlayerImportWizard`, etc.), add the same
  `display_notification` result after a successful import, followed by an action
  opening the newly created records.
- [x] Tests: assert the wizard return value contains `display_notification` tag and
  the correct match/record count in the message.

Done when: every schedule/import wizard shows a count notification and offers a
one-click link to the results.

### 2. Styled readiness feedback on roster and match sheet forms

Module: `sports_federation_rosters`

**Problem:** `readiness_feedback` (roster) and `readiness_feedback` (match sheet)
are plain readonly `<field>` elements. System-generated validation text is
visually indistinguishable from user notes — no colour, no icon, no contrast.
The boolean `ready_for_activation` / `ready_for_submission` indicator is a raw
checkbox with no visual emphasis.

**Impact:** Administrators miss blocking issues before attempting activation or
submission.

Work:
- [x] Wrap each feedback field in a styled alert div
  (`class="alert alert-warning mb-3"`) with a warning icon, shown only when
  `readiness_feedback` is set.
- [x] Replace the bare `ready_for_activation` / `ready_for_submission` booleans
  with colour-coded badges: green "Ready" when true, amber "Not Ready" when false.
- [x] Apply the same pattern to `match_day_lock_feedback` on the roster form.
- [x] Tests: run CI — view XML changes are load-time validated by Odoo.

Done when: feedback is visually distinct from user-editable notes and the ready
state is clearly colour-coded.

### 3. Portal access-denied page differentiated from 404

Module: `sports_federation_portal`

**Problem:** When a club representative accesses a roster or match-sheet URL
belonging to another club, `_assert_portal_owns()` raises `AccessError`, which is
caught and rendered as a generic 404. The user cannot distinguish "this record does
not exist" from "you are not allowed to see it".

This is a security-usability item: the 403 page should be helpful without leaking
record existence or ownership.

Work:
- [x] In each portal controller, catch `AccessError` separately from `NotFound`/404.
- [x] Render a dedicated `403_access_denied` template (extends
  `portal.portal_layout`) with a plain message ("You don't have permission to view
  this record.") and a "Go to my dashboard" button.
- [x] The template must NOT reveal the record's owner, title, or content.
- [x] Tests: assert that accessing another club's roster URL returns HTTP 200 with
  the 403 template body (not a redirect to the generic 404 page).

Done when: access-denied shows a helpful 403 page; 404 is only shown for truly
missing records.

---

## Phase 2 — Weeks 3–4: Form Clarity

### 4. Compliance document submission — target entity selection

Module: `sports_federation_compliance`

**Problem:** The document submission form shows 5 separate `Many2one` fields
(`club_id`, `player_id`, `referee_id`, `venue_id`, `club_representative_id`) each
gated by `invisible="target_model != '...'"`. In read mode, users see the one
relevant field surrounded by blank labels for the 4 irrelevant ones.

Work:
- [x] Add a computed `target_entity_label` char field that returns the
  `display_name` of the resolved target record based on `target_model`.
- [x] In the form view, show `target_entity_label` (read-only) above the
  conditional entity fields with a clear "Applies To:" label.
- [x] Keep the existing entity `Many2one` fields for draft editing, but move them
  under a collapsible group visible only in draft state.
- [x] Tests: CI view validation; assert `target_entity_label` returns the correct
  name for each `target_model` variant.

Done when: in read mode, users see "Applies To: Player — João Silva" rather than
4 empty dropdowns.

### 5. Discipline case form — workflow guidance

Module: `sports_federation_discipline`

**Problem:** The disciplinary case form has 4–5 action buttons (Submit, Review,
Decide, Appeal, Close) with no explanation of the workflow or when each is valid.
Federation officers new to the system cannot self-serve.

Work:
- [x] Add `title=` tooltip attributes to each action button explaining the
  precondition and effect (e.g. "Submit this case for panel review. Only Draft
  cases can be submitted.").
- [x] Add a final `<page string="Workflow Guide">` tab containing a brief plain-text
  description of the 5 states and which roles can perform each transition.
- [x] Tests: CI view validation.

Done when: hovering any action button shows an actionable tooltip; the guide tab
is present and renders without errors.

### 6. Result control — dual statusbar clarity

Module: `sports_federation_result_control`

**Problem:** The match form displays two statusbars side-by-side: one for
`federation.match.state` (draft → done) and one for `result_status`
(draft → submitted → verified → approved / contested). Managers see two parallel
progress bars with no indication of their relationship or sequencing.

Work:
- [x] Add a brief inline `<div class="alert alert-info py-1 px-2 small">` above the
  result statusbar, shown only when `state == 'done'`:
  "Match complete — use Result Status below to track the approval pipeline."
- [x] Add `readonly="state != 'done'"` to the `result_status` statusbar so it
  cannot be changed before the match is complete.
- [x] Tests: CI view validation.

Done when: the two statusbars are visually and textually connected; the result
status cannot be advanced before the match is done.

### 7. Override request form — conditional field discoverability

Module: `sports_federation_governance`

**Problem:** `implementation_note` only appears when `state` is `approved` or
`implemented`. Users in `draft` or `submitted` don't know the field exists and
may not notice it unlocked after approval.

Work:
- [x] Show `implementation_note` at all times but with
  `readonly="state not in ('approved', 'implemented')"` and
  `placeholder="Add implementation notes once this request is approved."`.
- [x] Add a small `<p class="text-muted small">` note below the field in readonly
  mode: "This field unlocks after the request is approved."
- [x] Tests: CI view validation.

Done when: the field is always visible; its locked state is self-explanatory.

---

## Phase 3 — Weeks 5–6: Navigation & Smart Buttons

### 8. Notification log — navigation to the triggering record

Module: `sports_federation_notifications`

**Problem:** The notification log form shows `target_model` and `target_res_id` as
plain text. There is no way to jump to the tournament, match, or player that
triggered the notification without copying the ID and navigating manually.

Work:
- [x] Add a computed `target_display_name` char field on the log model that
  resolves `env.get(target_model).sudo().browse(target_res_id).display_name`.
  Guard `env.get()` for `None` (optional addons).
- [x] Add `action_view_target()` returning an `act_window` for the target model
  filtered to `target_res_id`.
- [x] Add a smart button (`type="object"`, icon `fa-external-link`) showing the
  display name, hidden when `target_res_id` is not set.
- [x] Tests: assert `action_view_target` returns a valid `act_window` for a log
  whose `target_model` is `federation.match`.

Done when: notification log records have a one-click link to the triggering record.

### 9. Missing smart buttons — club representatives and season registration breakdown

Modules: `sports_federation_base`, `sports_federation_portal`

**Problem A:** The base club form has only a "Teams" smart button. Federation
managers have no quick view of how many club representatives exist without leaving
the club form.

**Problem B:** The season form has a total `registration_count` smart button but no
breakdown by state (confirmed vs. draft/pending). Planning for a new season
requires knowing how many clubs are confirmed.

Work (Club):
- [x] Add `representative_count` computed Integer field on `federation.club`.
- [x] Add smart button using `type="object"` backed by a Python method (see
  `odoo-patterns.md` for the correct `_for_xml_id` pattern).

Work (Season):
- [x] Add `confirmed_registration_count` and `pending_registration_count` computed
  Integer fields on `federation.season`.
- [x] Add two state-specific smart buttons opening filtered list views.
- [x] Tests: assert each computed field returns the correct count after creating
  registrations in different states.

Done when: club form shows rep count; season form shows confirmed vs. pending
registration counts as separate smart buttons.

### 10. Standing form — default ordering and tournament breadcrumb

Module: `sports_federation_standings`

**Problem:** The standings list view has `_order = "name"` — with dozens of
standings it appears as an unsorted flat list across tournaments. The form has no
visual indication of the tournament → stage → group hierarchy.

Work:
- [x] Change `_order` on `FederationStanding` to
  `"tournament_id, stage_id, group_id, name"`.
- [x] Add a compact `<group string="Context">` at the top of the form view showing
  `tournament_id` (readonly link), `stage_id`, and `group_id`.
- [x] Add default search filters to the standings list action context:
  a "Group By Tournament" filter and a "My Tournaments" domain filter.
- [x] Tests: CI view validation; assert model `_order` value.

Done when: the list is ordered by tournament by default; the form context is
self-explanatory.

---

## Phase 4 — Weeks 7–8: Portal Polish & Demo Data

### 11. Portal error messages — raw exception text replaced with guided messages

Module: `sports_federation_portal`

**Problem:** Portal templates render `<t t-esc="error"/>` directly, where `error`
can be a raw Python `ValidationError` message (e.g. "Min players required: 15 not
met"). Club representatives see technical language with no guidance.

Work:
- [x] In portal controllers, translate caught `ValidationError` into a
  user-friendly message and pass a separate `error_hint` to the template.
- [x] Update portal templates to render `error_hint` as a `<p class="small
  text-muted mt-1">` below the error box.
- [x] Audit all portal controller `except` blocks for raw exception passthrough.
- [x] Tests: assert that submitting an invalid roster via portal renders the
  expected `error_hint` text (not a raw Python string).

Done when: portal error messages always end with an actionable suggestion; no raw
Python exception strings reach club representatives.

### 12. Portal menu — consistent naming and grouping

Module: `sports_federation_portal`

**Problem:** Portal navigation uses inconsistent terminology ("Tournament
Workspace", "Season Registrations", "Match Day") with no grouping. Mobile users
see a long flat list in arbitrary order.

Work:
- [x] Audit all `portal_home_menuitem` entries and standardise into three groups:
  "Your Season" (registrations, rosters), "Match Day" (sheets, results),
  "Club Admin" (compliance, representatives).
- [x] Use `sequence` values to enforce group order.
- [x] Add `<hr/>` separators between groups in the portal home template.
- [x] Tests: `HttpCase` smoke test that portal home renders without errors.

Done when: portal home groups related items with clear headings matching the user's
workflow context.

### 13. Demo data — realistic end-to-end scenario

Module: `sports_federation_demo`

**Problem:** Demo data includes only 3 clubs, 6 teams, and 1 season. There are no
tournaments, matches, standings, rosters, or results. A fresh install looks empty
and cannot be used for evaluation or onboarding.

Work:
- [x] Expand `demo/` to include at minimum:
  - 1 tournament with 2 stages (group + knockout) and 2 groups of 4.
  - 16 players distributed across 6 teams.
  - 1 active season-scoped roster per team.
  - 6 completed matches (group stage) with scores.
  - 2 computed standings (group A, group B).
  - 2 document submissions per team (license + medical).
  - 2 disciplinary cases (1 open, 1 closed).
  - 1 notification rule and 3 log entries.
- [x] Keep records isolated under `sports_federation_demo` as source module.
- [x] Tests: assert that after installing `sports_federation_demo`, at least
  1 tournament, 6 matches, and 2 standings exist.

Done when: a fresh demo install shows a realistic federation with an ongoing season
that can be explored without creating test records manually.

---

## Suggested Sequence

1. Items 1–3 (Phase 1): no model changes; high visibility; can be developed in
   parallel.
2. Items 4–7 (Phase 2): form-only changes except Item 4 (new computed field).
3. Items 8–10 (Phase 3): require new computed fields and methods.
4. Items 11–13 (Phase 4): portal and demo; Item 13 is the largest scope.

---

## Security Invariants to Preserve

The following properties must not be regressed during this cycle:

- `_assert_portal_owns()` must remain the sole write gate for all portal
  controllers.
- Portal 403 pages (Item 3) must not reveal record ownership or content.
- Notification log target navigation (Item 8) must use `sudo()` only for display
  name resolution — never for write access.
- Smart button actions (Item 9) must be guarded by the same group ACL as the
  underlying model.
- Import wizard improvements (Item 1) must not alter existing file-size or
  MIME-type validation logic.

---

## Exit Criteria

- Every schedule/import wizard shows a success notification with a record count
  and a direct link to the results.
- Roster and match sheet readiness feedback is shown in a styled alert box;
  the ready/not-ready state is colour-coded.
- Accessing another club's portal URL returns a helpful 403 page, not a generic 404.
- The compliance submission form shows "Applies To: [Entity]" in read mode with no
  surplus empty dropdowns.
- All discipline case action buttons have tooltip text; a workflow guide tab exists.
- The result control dual statusbar includes an inline explanation of the two flows.
- Override request `implementation_note` is always visible (readonly until approved).
- Notification log records have a one-click jump to the triggering record.
- Club form shows representative count smart button; season form shows
  confirmed/pending registration breakdown.
- Standings list has a meaningful default order; form shows tournament hierarchy
  context.
- Portal error messages always include an actionable hint; no raw exception text
  reaches club representatives.
- Portal home groups navigation by workflow phase with consistent naming.
- Fresh demo install shows a realistic federation with a tournament, matches,
  standings, rosters, and compliance records.
