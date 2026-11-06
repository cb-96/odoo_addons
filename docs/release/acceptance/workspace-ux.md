# Workspace and portal UX acceptance

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance scenarios for the role home (`/my/work`), team preparation, task
priority, context continuity, empty and error states, the Competition Hub
hierarchy, terminology and event time zones across the portal, planner,
court workspace and public site.

## Behaviour under test


| Area | Behaviour |
| --- | --- |
| Destination pages | Team preparation shows one next requirement; other checks and lineups are disclosed. Visual planning puts the grid first and configuration in one Planning settings disclosure. |
| Task priority | One To do list merges actionable buckets; blockers and overdue work precede future deadlines. Source queries prioritize urgent tasks before their record limit. |
| Context continuity | Club/team/registration filters are validated, retained in URLs and pager links, and applied before list counts. Registration context scopes roster/lineup seasons. Return navigation reuses one button and has server-rendered fallbacks. |
| Empty/error states | Empty views offer the owning workspace. Planner load failures show Retry and preserve prior data without permitting stale actions. Visual refresh failures block mutations until retry succeeds. |
| Competition hierarchy | One promoted action, a nonduplicated remaining-blocker list, collapsed division checks, and an explicit setup-progress lifecycle projection. |
| Terminology | User-facing lineup, scheduling-rule, blocker, status and return labels are consistent; technical model names and workflow state keys are unchanged. |
| Timezone consistency | Event-local server display across portal/public/official pages, event-aware public clock, UTC machine timestamps, and an audited historical-timezone review wizard. |

## Staging preparation


1. Back up the database and filestore together.
2. Upgrade the following installed modules using your existing Odoo deployment command:

sports_federation_base,sports_federation_calendar,sports_federation_portal,sports_federation_setup_flow,sports_federation_live_workspace,sports_federation_public_site,sports_federation_duty_coverage,sports_federation_rosters,sports_federation_navigation,sports_federation_notifications

3. Restart workers, rebuild/reload assets and clear the browser asset cache.
4. Run the local checks and the Odoo runtime groups below.
5. Review historical event time zones before operational rollout.

## Historical timezone review


The migration marks existing match days as requiring timezone review. It does not infer
venue timezones and does not change stored slot instants. New days retain their explicitly
captured event timezone. A calendar planner opens Review event timezone from the match-day
form, selects the timezone supported by event/venue records, and supplies evidence.
The private review command checks authority and write access, locks the day, records the
reason, and refreshes nonstored match timezone projections. A reviewed scheduled day cannot
be changed again through this workflow. Existing UTC instants remain untouched.

Until review, event pages label the timezone as needing review. A correct historical
location cannot be invented from the administrator's profile. Generic Odoo audit/accounting
datetime widgets remain profile-local; event-facing displays in this revision use the event
zone. Records with no event association are explicitly labelled UTC.

## Local executable checks


python -m unittest ci.test_complete_ux ci.test_minimal_ux ci.test_connected_journeys ci.test_live_workspace_policy ci.test_visual_policy ci.test_visual_acceptance
python ci/check_portal_sudo_guard.py
python ci/check_privileged_mutation_boundaries.py
python ci/check_addon_integrity.py
python ci/check_competition_ui_workflow.py
python ci/check_usability_patch.py

The new local suite tests urgency ordering, context IDs/URLs, summer/winter conversion,
layout contracts, and actual planner/visual methods under mocked service failures.
It does not render Owl or replace real browser testing.

## Odoo runtime checks


Run sf_role_journeys and sf_visual_scheduling using the repository's existing test runner.
New cases include forged context, collapsed preparation rendering, a real-browser disclosure
check, timezone-review authority/evidence, unchanged slot instants and event-time display.
Run the complete install/upgrade/full lanes after these focused groups. Do not suppress
existing unrelated release failures to obtain a green UX result.

## Browser acceptance matrix


Use ordinary accounts and staging-only players/documents. Repeat core tasks at desktop,
360px mobile and keyboard-only. Do not use an administrator to prove ordinary-user access.

- Club representative: open My work; verify one To do list and overdue-first order.
- Multi-club representative: select club, open preparation, roster, lineup and competition
  lists; check context, pager, return navigation and no foreign records.
- Team preparation: one missing consent requirement leads to the exact player document
  page. Resolve it; return; distinguish uploaded, verified, eligible and approved.
- Waiting/completed: no misleading empty headings; disclosures start collapsed and work
  with keyboard focus. Completed tasks never certify participation readiness.
- Planner: one primary action; no duplicate primary blocker; division checks collapsed;
  setup stepper does not dominate a running competition.
- Visual planner: grid first; settings collapsed; selected-fixture issues near the grid;
  keyboard/click alternatives to drag; preview and independent publication remain separate.
- Network failure: initial load is an error, not an empty competition. Refresh failure
  preserves prior information but pauses actions. Retry restores operation without double
  submission or accidental preview application.
- Court operator: save device draft, reconnect, synchronize, submit and reopen. Verify
  draft/server/submitted/approved distinctions and that conflicts remain visible.
- Official/reviewer: event times match public and planning pages despite different profile
  and browser zones; role switches do not grant access or bypass independent review.
- Timezone reviewer: review a historical day with evidence; compare UTC slot values before
  and after; confirm audit note and no silent rescheduling.
- Public site: live-board clock uses event timezone, schedule labels are explicit, UTC feed
  timestamps have Z, and no internal notes or personal data appear.
- Storage-disabled browser: server fallback return links still work; no duplicate return
  buttons when session navigation is available.

## Context selection checks

- Single-role user: My work opens directly, with no responsibility selector and
  no empty bucket headings.
- Multiple roles or clubs: change context with Apply, return, refresh, and
  verify the remembered selection. Club selection is session-scoped per user
  and rechecked against current access on every request.
- Foreign club or revoked access: deny explicit selection; never show foreign
  tasks or documents.
- Delegation: expand Details and submit with CSRF; existing assignment
  permissions still apply.
- Two browsers in different time zones show the same event grid and rule
  conversion; test Brussels winter and summer time. Ambiguous or nonexistent
  DST input is rejected, not silently shifted.

## Human acceptance


Observe at least five unfamiliar users for each major role journey. Record unaided task
completion, wrong destinations, time to find the next action, and comprehension of save,
submission, eligibility and approval. Require zero access, approval or data-loss incidents.
Do not claim novice acceptance from source tests or mocked JavaScript methods.

## Rollback


Restore the pre-upgrade database, filestore and previous code together. Code-only rollback
is not a safe substitute once historical timezone review or new operational writes occur.
