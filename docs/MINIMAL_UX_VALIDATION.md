# Minimal workspace and portal revision

## Scope

The existing role home remains canonical. No new task, readiness or dashboard model is introduced.
Actionable work is visible; waiting, history, delegation and advanced controls are disclosed on demand.
The role selector appears only for multiple roles. The club selector appears only for multiple authorised clubs.
Club selection is session-scoped per user and is checked against current access on every request.
Team and competition context stays on the existing source record rather than adding more selectors.

Court scoring keeps save, submit and next-match controls. Synchronisation appears for queued work.
Recovery is contextual; conflicts and storage errors remain visible. Existing result guards are unchanged.

## Upgrade

Apply to source commit a9fbdebd0cd80e7122ae0e0a61637d6c5b763ebf or rebase against newer changes.
Back up the database and filestore. Upgrade sports_federation_base, sports_federation_calendar,
sports_federation_portal, sports_federation_setup_flow and sports_federation_live_workspace on staging.
Restart workers and reload assets. Do not deploy solely on source-test results.

The calendar migration sets existing match days to UTC, without moving stored slot instants.
New match days capture the creator's timezone once. Verify the event timezone on existing draft days
before generating new slots. Scheduled days retain UTC until a reviewed data migration establishes
historical venue timezones; do not infer them from the upgrading administrator's profile.
The visual planner and its rule inputs use the stored event timezone. Generic Odoo datetime widgets
outside the visual planner still use the user's profile timezone. Ambiguous or nonexistent DST input
is rejected, not silently shifted. No automatic rescheduling or publication occurs.

## Local checks

python -m unittest ci.test_minimal_ux ci.test_connected_journeys ci.test_live_workspace_policy ci.test_visual_policy ci.test_visual_acceptance

Run the existing Odoo test groups sf_role_journeys and sf_visual_scheduling after upgrading.
New HTTP/model cases cover invalid club context, minimal role controls, event-local conversion,
stale revisions, invalid fields and timezone locking. These require Odoo/PostgreSQL.

## Browser acceptance

- Single-role user: My work opens directly, no responsibility selector, no empty bucket headings.
- Multiple roles/clubs: change context with Apply, return, refresh, and verify remembered selection.
- Foreign club or revoked access: deny explicit selection; never show foreign tasks or documents.
- Waiting/history: collapsed initially, keyboard-openable, one action per card, owner/deadline visible.
- Delegation: expand Details; submit with CSRF; preserve existing assignment permissions.
- Planner: one promoted action; More exposes details/advanced tools; zero-count task controls absent.
- Court: enter score, save, submit, reopen; distinguish device draft, server draft, submitted and approved.
- Interrupt network: queued sync appears; conflict stays visible; evidence export remains reachable.
- Two browsers in different timezones: same event grid and rule conversion; test Brussels winter/summer.
- Keyboard and 360px mobile: no clipped controls, focus visible, disclosures usable, errors announced.
- Confirm no eligibility, independent-review or publication guard can be bypassed.

## Evidence boundary

Source parsing, policy tests and syntax checks are not live-browser, ORM or novice acceptance.
Record staging results and at least five novice sessions before calling this UX release qualified.
