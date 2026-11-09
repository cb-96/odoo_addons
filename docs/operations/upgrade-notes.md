# Upgrade notes

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Upgrade-sensitive changes, newest first. Each entry records the affected
modules, data changes, behaviour to verify, dry-run evidence and the rollback
path. The general upgrade, backup and rollback procedures are in the
[release runbook](release-runbook.md).

## Adding an entry

`ci/check_migration_review.py` requires an entry here whenever a change touches
`models/`, `views/` or `controllers/` of an addon, and requires the rollback
path when a migration script is added. Add a new section at the top of
[Entries](#entries), below this guidance:

```markdown
### <Short description of the change>

Affected modules: `sports_federation_x` 19.0.a.b.c → 19.0.a.b.d

**Data changes**: schema, migration scripts and what they do; "None" if none.

**Behaviour to verify**: what operators and testers check on staging.

**Dry-run evidence**: commands run and their outcome. State plainly which
runtime checks were not executed.

**Rollback**: backup restore, code-only rollback or data reversal steps.
```

Do not describe work that is not in the code, and do not mark runtime checks as
passed unless they ran.

## Entries

### Game-day printouts, club invoices, Dutch and French portal, optional player availability

Affected modules: `sports_federation_live_workspace` 19.0.1.7.0 → 19.0.1.8.0,
`sports_federation_accounting` 19.0.1.1.1 → 19.0.1.2.0,
`sports_federation_rosters`, `sports_federation_portal` (models, views,
translations; manifest versions unchanged).

**Data changes**: new stored field `federation.club.player_availability_enabled`
(default off) and new models `federation.player.availability.request` and
`federation.player.availability` with ACLs in the rosters CSV. New report
`action_report_gameday_schedule` with an A4 landscape paper format. The
accounting addon now depends on `sports_federation_portal`; the live workspace
declares its existing use of `sports_federation_calendar`. New
`i18n/nl.po` and `i18n/fr.po` in the portal, rosters, accounting and live
workspace addons. No migration script.

**Behaviour to verify**: on a game day with a live publication, **Print
schedule** shows courts across and event-local times down with teams,
officials and club duties; **Print score sheets** prints every published match.
A whole-club representative sees **Invoices** on the club overview with an
unpaid badge, and **View and pay** opens the invoice payment page. Activate
Dutch (Belgium) and French (Belgium) under Settings > Languages (this loads the
new files) and on the website, then check the club overview, rosters,
line-ups, officials and results pages in both languages. Under Club details,
switch **Player availability** on, ask players for an upcoming game day, answer
through the emailed link (outgoing mail must be configured), enter an answer for
a player without email, and check the badges on the line-up page and in the
backend line-up wizard. With the option off, nothing appears.

**Dry-run evidence**: Python syntax, XML well-formedness, template XPath
anchors, `.po` round-trip parsing and placeholder/markup checks of every
translation, and the static contract checks ran in the patch environment. No
Odoo upgrade, Odoo test run, PDF rendering, email delivery or browser check ran
there. Run the `sf_gameday_print`, `sf_club_invoices`, `sf_player_availability`
and `sf_portal_translations` tests and upgrade the four modules on a staging copy.

**Rollback**: code-only rollback removes the pages and buttons; restore the
pre-upgrade backup to remove the new tables and the club field.

### Portal overview replaces `/my/work`; club portal cleanup

Affected modules: `sports_federation_portal` 19.0.7.14.x → 19.0.7.15.0,
`sports_federation_rosters` 19.0.1.14.0 → 19.0.1.15.0 (models, views,
security), and view-only changes in `sports_federation_compliance`,
`sports_federation_duty_coverage`, `sports_federation_live_workspace`,
`sports_federation_member_services`, `sports_federation_notifications` and
`sports_federation_setup_flow`.

**Data changes**: no migration script and no stored-field change.
- Removed templates and routes: `role_home`, `portal_journey_entry` and the
  Data API page (`/my/data-api`, `portal_home_data_api_link`). The
  `/my/work` routes now only redirect (301) to `/my`, `/my/result-reviews`,
  `/my/action-items/<id>/open` and `/my/season-registrations/<id>/roster`.
  Task `journey_url`/`action_url` values are recomputed on the next task
  refresh. Inheriting views in the other modules were removed or retargeted
  to `portal_federation_links`; upgrade all affected modules in the same run.
- Parental-consent tasks are now one per player (`source_model`
  `federation.player`) instead of one per roster line. The first refresh
  closes the old per-line tasks and opens one per player.
- `federation.club.rank.promotion` ACLs moved from
  `security/club_rank_access.xml` to `security/ir.model.access.csv` (same
  xml ids, same rights). The orphan file `views/federation_tournament_views.xml`
  (never loaded, pointing at methods that do not exist) is deleted.
- Journey event retention defaults to 90 days (was 180) unless
  `federation.journey_event_retention_days` is set.

**Behaviour to verify**: `/my` for a club representative shows the club
hero, **Prepare your team** and the club areas; for an account with other
roles it shows a section per role with at most five cards and a link to the
full list; an account without any role sees the access notice. Old `/my/work`
bookmarks land on the overview. Other portal pages no longer refresh tasks on
every load. A representative of two clubs can switch `/my/club?club=<id>` and
must choose the club when adding a player. The backend roster picker and the
portal "Add players" page hide the same players (already on the roster,
blocked by club ranking, or on another club team in the same division), and
saving such a line is refused. Portal compliance uploads for officials and
club representatives are accepted (the create allowlist now contains
`referee_id` and `club_representative_id`).

**Dry-run evidence**: Python syntax, XML well-formedness, the pure-helper CI
tests and the static contract checks ran in the patch environment. No Odoo
upgrade, Odoo test run or browser check ran there.

**Rollback**: code-only rollback restores the previous routes and templates;
per-player consent tasks close and per-line tasks reopen on the next refresh.

### Players needing parental approval on the club portal

Affected modules: `sports_federation_portal` (portal template and a read-only
helper on the parental-approval model; manifest version unchanged).

**Data changes**: None. No stored field, migration, ACL or menu change. The
players page `/my/players` gains a summary card and a status per player.

**Behaviour to verify**: as a club representative, open `/my/players`. A card
shows a stacked bar and four tiles: needed now (player under 16 on an active
senior roster of the current season, no valid approval), needed for senior play
(under 16, not on a senior roster), awaiting review, approved. Rows that need
action are highlighted; each row shows a status badge with a short explanation
and *Upload approval*, *View status*, *Upload renewal* or *Manage document*.
*Show only players who need action* filters the list and keeps the gender and
status filters. Players who are 16 or older read *Not required*; a player
without a birth date reads *Birth date missing*. A verified approval that
expires within 30 days is shown as *Approved, expires soon*. The rule mirrors
roster eligibility: under 16 on the date, senior team, verified approval that
covers the date. A junior team entered in a senior tournament is not detected
from the roster alone.

**Dry-run evidence**: Python and XML syntax, the template XPaths against a
reconstruction of the base players template, and the status logic against test
doubles ran in the patch environment. No Odoo upgrade, Odoo test run or browser
check ran there. Run the `sf_player_parental_overview` tests and upgrade
`sports_federation_portal` on a staging copy.

**Rollback**: code-only; revert the change and upgrade the module.

### Club team ranking: playing up and promotion

Affected modules: `sports_federation_rosters` 19.0.1.13.0 → 19.0.1.14.0,
`sports_federation_portal` (template only; version unchanged).

**Data changes**: new stored field `federation.team.club_rank`, computed once
for existing teams from the name suffix (A-F, 1-9; otherwise 0) and editable
afterwards. New model `federation.club.rank.promotion` with access rules in
`security/club_rank_access.xml` (read for internal users, full for federation
managers). No migration script.

**Behaviour to verify**: check **Rank within club** on teams of clubs with
several teams, and set it by hand where the name has no suffix (for example a
first team without "A"). On the higher team's roster, players of the lower
team are offered and show *Playing up*; on the lower team's roster, players of
the higher team are not offered and adding one is refused. In the game-day
line-up wizard, on the match sheet and on the portal line-up page, a player
who would reach two matches for the higher team gets a warning. After the
second played match (line-up approved, not crossed out, match done) the
player has a team promotion, cannot be added to the lower roster, and the
lower line is removed or explained in the roster chatter.

**Dry-run evidence**: Python syntax and XML well-formedness were checked in the
patch environment. No Odoo upgrade, Odoo test run or browser check ran there.
Run the `sf_club_rank` tests and upgrade both modules on a staging copy.

**Rollback**: code-only rollback leaves the `club_rank` column and promotion
table unused; restore the pre-upgrade backup to remove them.

### Game-day handoff in the Competition Hub and event-time court times

Affected modules: `sports_federation_setup_flow`, `sports_federation_calendar`,
`sports_federation_live_workspace` (models, views and planner assets; manifest
versions unchanged).

**Data changes**: None. New non-stored computed fields:
`federation.schedule.slot.event_window`,
`federation.matchday.user_timezone_differs` and
`federation.matchday.timezone_notice`. The slot display name is now computed in
the event timezone of its game day instead of the viewer's timezone. No stored
column, migration, ACL or menu change.

**Behaviour to verify**: in the Competition Hub, every listed blocker of the
next game day has *Fix this*, which opens the exact record or list the blocker
names; a blocker solved in another tab is refused with a refresh message.
*Open game day* opens the game day. *Later game days* lists up to three
further open game days with their readiness and open items. On a game-day
form, *Courts and times* shows an *Event time* column; with a user timezone
whose clock differs from the event timezone, a notice explains which times are
yours and which teams see. Court-time names in schedule dropdowns read the
same for every user. The visual planner header reads *Start (event time)*.
Assets must be rebuilt for the planner changes.

**Dry-run evidence**: Python and XML syntax and a JavaScript parse check ran in
the patch environment. No Odoo upgrade, Odoo test run or browser check ran
there. Run the setup-flow, calendar and live-workspace module tests and the
`competition_planner_intent` tour, and upgrade the modules on a staging copy.

**Rollback**: code-only. Revert the change and upgrade the three modules; no
data needs to be restored.

### Clearer schedule generation and auto-schedule guidance

Affected modules: `sports_federation_scheduling` (views and a transient-model
extension; manifest version unchanged).

**Data changes**: None. The competition schedule wizard gains non-stored
computed fields (`guidance_status_html`, `mode_impact_html`,
`existing_slot_count`, `existing_draft_schedule_count`). No stored column,
migration script, ACL or menu change.

**Behaviour to verify**: open **Generate schedule** for a competition and
confirm the step strip and status card; without a check the card says
*Ready to check and generate*; with blocking findings it lists the count and
points to Feasibility; with only rest warnings it offers *Generate anyway*. As
an advanced operator, switch the rerun mode and confirm the explanation; for
*rebuild* it shows the number of court times and unpublished schedules that
will be deleted. On a draft schedule, run **Auto-schedule**: *Preview* is the
primary action, and a proposal with unplaced matches shows the explanation.
Generation, preview signatures, governance and publication behave as before.

**Dry-run evidence**: Python syntax and XML well-formedness were checked in the
patch environment. No Odoo upgrade, Odoo test run or browser check was executed
there. Run `bash ./ci/run_tests.sh --module sports_federation_scheduling` and
upgrade the module on a staging copy before release.

**Rollback**: code-only. Revert the change and upgrade
`sports_federation_scheduling`; no data needs to be restored.

### Offline court scoring on personal phones

Affected modules: `sports_federation_live_workspace` 19.0.1.6.3 → 19.0.1.7.0,
`sports_federation_result_control` 19.0.1.6.0 → 19.0.1.7.0,
`sports_federation_portal` 19.0.7.14.5 → 19.0.7.14.6,
`sports_federation_setup_flow` 19.0.4.11.2 (see the next entry).

**Data changes**: new models `federation.court.device` (prepared phones, token
hashes only) and `federation.match.scorer` (club scorer nominations). New
columns on `federation.court.capture` (device, scorer, scorer source and club,
referee confirmation, match log, conflict count), `federation.court.receipt`
(device) and `federation.referee` (PIN hash, set date, failures, lock). New
ACLs for match-day managers and result validators, two record rules, an
hourly cron that expires codes and tokens, and the menus **Match Operations >
Scoring Phones** and **Club Scorers** (Advanced Federation Tools). No
migration script; existing captures get empty evidence fields.

Behaviour changes for existing data: a result submitted from a court app
(backend **Run This Court** included) no longer auto-verifies or
auto-approves when the competition does not require review; it stays
*submitted* until a result approver clicks **Approve Result**. On the match
form and the result list, **Approve Result** now verifies and approves a
submitted result in one step; the submitter can still never approve their own
result. The Review Queue shows *Approve result* for submitted results.

**Behaviour to verify**: with a portal referee whose head-referee assignment
is confirmed, open **My court duties**, prepare a phone, open the court app,
switch the phone to aeroplane mode, reload the app, score sets, cross out
players and record a card, then reconnect: the changes arrive. Submit as head
referee; on the match, the **Court evidence** tab shows the scores, cards,
scorer, phone and confirmation; **Approve Result** makes it official. Repeat
with an assistant referee and the head referee's PIN, with a club scorer added
by a club representative, with a revoked phone and with a second phone taking
over a match. Test on Android Chrome and iPhone Safari, also installed on the
home screen. The site must be served over HTTPS for the service worker.

**Dry-run evidence**: `python -m unittest ci.test_court_app_logic` passes (21
shared scoring cases on the server rules, device-command validation, and the
32 Node.js tests of the phone logic). The phone app was run in headless
Chromium against a stand-in server (`ci/court_app_browser/run.py`): 24 checks
pass, including reloading the app without a network, keeping unsent changes,
sending them when back online, PIN confirmation, conflicts, a revoked phone,
and a 320 px dark-mode layout. The new Odoo tests
(`sports_federation_live_workspace/tests/test_court_devices.py`), the module
upgrade and real-device tests were not run in this change.

**Rollback**: code-only rollback followed by a module update removes the
routes, menus and cron; the new tables and columns remain unused. Court
results then auto-approve again where the competition does not require
review. Revoke all phones before rolling back.

### Readable Competition Hub next-action card

Affected modules (static assets only): `sports_federation_setup_flow`
19.0.4.11.1 → 19.0.4.11.2, `sports_federation_base` 19.0.1.6.1 → 19.0.1.6.2;
the `sports_federation_live_workspace` stylesheets ship with 19.0.1.7.0
(previous entry).

**Data changes**: none. `planner.scss` contained two rules for the
next-action card: the second replaced the purple background with white but
kept the white text. The file now has one rule set built on Bootstrap 5.3
theme variables. The same files in the live workspace, stage builder and base
UX stylesheet referenced CSS variables Odoo does not define (`--body-bg`,
`--border-color`, `--text-muted`, `--o-brand-primary`,
`--o-view-background-color`), so their light fallbacks were also used in dark
mode; they now use the `--bs-*` equivalents.

**Behaviour to verify**: in light and dark mode, the Competition Hub
**Next action** card, setup steps, season board and court workspace are
readable. Clear the browser cache or regenerate assets after the update.

**Dry-run evidence**: the new `ci/check_scss_contrast.py` passes and fails on
the previous `planner.scss`. The browser tours were not run in this change.

**Rollback**: code-only rollback followed by a module update.

### Printable match scoresheet, drawn sets and set points

Affected modules: `sports_federation_rosters` 19.0.1.12.0 → 19.0.1.13.0,
`sports_federation_live_workspace` 19.0.1.6.2 → 19.0.1.6.3.

**Data changes**: adds the `Scoresheet` PDF report on `federation.match`
(**Print** menu), its A4 paper format and a report stylesheet in
`web.report_assets_common`. Adds two stored integer fields on
`federation.competition.edition`: `court_set_win_points` (default 1) and
`court_set_draw_points` (default 0); the update fills existing rows with the
defaults, so existing competitions keep sets-won scoring. No migration
script. The court app capture policy no longer rejects a drawn set in `sets`
mode; the match score is the sum of set points, and a drawn set no longer
counts as an away win when a set target is configured.

**Behaviour to verify**: on a dodgeball competition, set **Points per won
set** to 2 and **Points per drawn set** to 1 with scoring mode **Sets**. In
the court app, a set with equal scores shows **Draw**; won 3-0, drawn 2-2 and
lost 1-4 sets give 3-3, and the result can be submitted. Result periods store
the set points. Print one match and a selection of matches: one A4 page per
match with the whole game-day line-up (14 rows, shirt-number order) and Out,
B1, B2, Y and R columns, players already crossed out printed struck through,
time-out boxes per half, challenges, team and staff cards, sets per half and
the configured set points in the legend.
Printing needs a working `wkhtmltopdf` on the server.

**Dry-run evidence**: `python -m pytest ci/test_live_workspace_policy.py`
passes (26 tests); the drawn-set tests fail on the previous policy. The
scoresheet template was rendered outside Odoo with sample data to check the
layout. The new `test_scoresheet` tests, an Odoo PDF print and the court-app
browser tour were not run in this change.

**Rollback**: code-only rollback followed by a module update removes the
report and restores the previous set validation; the two new columns are
left unused.

### Portal line-up save no longer fails with Access Denied

Affected modules: `sports_federation_portal` 19.0.7.14.4 → 19.0.7.14.5.

**Data changes**: none. The portal create allowlist for
`federation.match.sheet.line` named fields that do not exist (`shirt_number`,
`is_goalkeeper`) and missed fields the line-up form sends (`jersey_number`,
`is_starter`, `is_substitute`). Selecting a player who was not yet on the
line-up raised an `AccessError`, which the portal shows as **Access Denied**.
The allowlist now lists the real fields, and new lines no longer send the
starting-role flags; they use the model defaults.

**Behaviour to verify**: as a club representative, open a draft game-day
line-up, select players with jersey numbers and a captain, and use **Save** and
**Save and submit**. The players are saved and the line-up is submitted.

**Dry-run evidence**: `python -m pytest ci/test_security_hardening_contracts.py`
passes; its new allowlist check fails on the previous code. The extended
portal HTTP smoke test and the Odoo upgrade were not run in this change.

**Rollback**: code-only rollback; no data needs reversing.

### Competition Hub as the Federation landing page

Affected modules: `sports_federation_navigation` 19.0.1.2.0 → 19.0.1.3.0,
`sports_federation_portal` 19.0.7.14.3 → 19.0.7.14.4.

**Data changes**: no schema change and no migration script. The
`Needs Attention` menu and its window action, and the `Action Queue`/`All
Tasks` menu, are no longer loaded and are deleted by the module update.
`sports_federation_portal.action_federation_operation_task` is renamed
**Review Queue**, limited to manager tasks and no longer lists club referee
nominations. A new server action, `sports_federation_navigation.action_review_queue`,
refreshes the task projection and opens it.

**Behaviour to verify**: opening the Federation app lands on the Competition
Hub for managers and advanced operators. **Competitions > Review Queue** shows
current submitted entries, line-ups and results without first visiting a
portal page. Referee nominations stay visible on the Duty Coverage Board.

**Dry-run evidence**: `python3 ci/check_competition_ui_workflow.py` passes,
including the new landing-page rule. The Odoo upgrade and module tests were
not run in this change.

**Rollback**: code-only rollback followed by a module update restores the
previous menus; no data needs reversing.

### Backend menu clean-up

Affected modules (menu data only): `sports_federation_navigation` 19.0.1.1.1 → 19.0.1.2.0;
`sports_federation_accounting` 19.0.1.1.1, `sports_federation_base` 19.0.1.6.1,
`sports_federation_competition_core` 19.0.1.8.1, `sports_federation_discipline` 19.0.1.4.1,
`sports_federation_governance` 19.0.1.1.1, `sports_federation_matchday` 19.0.2.5.1,
`sports_federation_member_services` 19.0.1.3.1, `sports_federation_officiating` 19.0.2.1.1,
`sports_federation_people` 19.0.1.2.2, `sports_federation_portal` 19.0.7.14.3,
`sports_federation_registration` 19.0.1.4.1, `sports_federation_reporting` 19.0.1.5.1,
`sports_federation_rules` 19.0.2.2.1, `sports_federation_scheduling` 19.0.3.10.1,
`sports_federation_setup_flow` 19.0.4.11.1, `sports_federation_standings` 19.0.2.2.2,
`sports_federation_tournament` 19.0.1.6.1, `sports_federation_venues` 19.0.1.1.1
(patch bumps).

**Data changes**: no schema change and no migration script. Duplicate,
empty and contextual-only `ir.ui.menu` records are no longer loaded, so the
module update deletes them; their actions, ACLs and XML IDs are unchanged.
`sports_federation_portal/views/website_menus.xml` and
`sports_federation_setup_flow/views/menu.xml` were removed from the manifests
(the setup-flow file duplicated `menu_competition_setup_home`).
`sports_federation_navigation` now depends on duty coverage, finance bridge,
compliance and governance, which the application already installs, and
rewrites menu groups with `(6, 0, ...)`.

**Behaviour to verify**: as a Federation Manager without Advanced Federation
Tools, the menu shows the eleven entries listed in
[backend navigation](../user-guide/backend-navigation.md). As an advanced
operator, the sections match the advanced map; **Administration > System**
appears only in developer mode. Bookmarked URLs of removed menus still open
because the actions are unchanged.

**Dry-run evidence**: `python3 ci/check_competition_ui_workflow.py` passes
(install-order menu resolution, depth, openability, duplicate and budget
rules). The CI script suite gives the same results as before the change.
The Odoo upgrade and `sports_federation_navigation` tests were not run in
this change.

**Rollback**: code-only rollback followed by a module update restores the
previous menus; no data needs reversing.

### Practice competition readiness and planner routing

Affected modules: `sports_federation_accounting`, `sports_federation_app`,
`sports_federation_base`, `sports_federation_calendar`,
`sports_federation_competition_core`, `sports_federation_demo`,
`sports_federation_discipline`, `sports_federation_duty_coverage`,
`sports_federation_finance_bridge`, `sports_federation_format`,
`sports_federation_import_tools`, `sports_federation_live_workspace`,
`sports_federation_matchday`, `sports_federation_member_services`,
`sports_federation_notifications`, `sports_federation_officiating`,
`sports_federation_people`, `sports_federation_portal`,
`sports_federation_public_site`, `sports_federation_registration`,
`sports_federation_reporting`, `sports_federation_result_control`,
`sports_federation_rosters`, `sports_federation_schedule_approval`,
`sports_federation_scheduling`, `sports_federation_setup_flow` and
`sports_federation_tournament`. The demo addon now depends on
`sports_federation_setup_flow` (19.0.1.2.0 → 19.0.1.3.0).

**Data changes**: No stored fields or data migrations are added. Practice
competitions now create active, licensed sample roster lines sufficient for
the competition's roster rules. Planner team blockers open participant
selection for ordinary managers, and portal game-day rows fall back to the
effective roster rule when no roster-specific limit is set. Portal create
capabilities now explicitly cover the fields used for competition entries,
document submissions, player and team registration, rosters, and match-sheet
lines, and the portal can remove an owned roster line through its action
allowlist. Submitted game-day line-ups use the registered review task type.
Competition Hub end-of-competition counts are computed only when the caller can
read their source records, and the close action also requires edition write
access. The abstract lifecycle-postcondition and derived-record-reconciliation
services are owned by `sports_federation_setup_flow`; the application aggregate
remains dependency-only, with model names and behavior unchanged.

**Behaviour to verify**:

- The practice competition wizard creates teams with eligible active rosters
  and publishes the generated schedule.
- Ordinary managers selecting a planner team blocker reach participant
  selection; users with the advanced-operator role keep the registration
  window route.
- Portal game-day lineup limits use the roster rule when the roster has no
  explicit game-day limit.
- Connected planner journeys render for edition readers without exposing or
  computing end-of-competition actions outside their source-record access.
- Portal create workflows submit only fields explicitly permitted for their
  target model.
- Submitted game-day line-ups can be synchronized into manager review tasks.

**Dry-run evidence**: Strict repository lint and static CI contracts passed.
All five required Odoo CI matrix suites passed (1,255 tests), as did the
conditional release-surfaces suite (660 tests), with optional Chrome bootstrap
skipped. Browser-dependent checks and a database-upgrade run remain unverified.

**Rollback**: Restore the previous code and restart Odoo. No schema or data
rollback is required; the demo addon dependency can be reverted with its code.

### Retention controls, code-only imports and standings cleanup

Affected modules: `sports_federation_notifications` 19.0.1.4.1 → 19.0.1.5.0,
`sports_federation_member_services` 19.0.1.2.0 → 19.0.1.3.0 (optional),
`sports_federation_import_tools` 19.0.1.2.2 → 19.0.1.3.0,
`sports_federation_live_workspace` 19.0.1.6.1 → 19.0.1.6.2,
`sports_federation_standings` 19.0.2.2.0 → 19.0.2.2.1.

**Data changes**:

- New columns on `federation_member_evidence_revision`: `legal_hold`,
  `legal_hold_reason`, `legal_hold_by_id`, `legal_hold_on`. Existing rows get
  no hold. No migration script is needed.
- New transient model `federation.member.evidence.governance.wizard`, menu
  **Member evidence history** and ACL row.
- New retention policies `participant_inbox` and `member_evidence_revisions`
  and two daily scheduled actions (`noupdate`).
- The players, teams and tournament-participants import templates and their
  inbound integration contracts move from `csv_v1` to `csv_codes`.
- No data is deleted by the upgrade. The new retention runs delete nothing
  until `sports_federation_notifications.inbox_retention_days` or
  `sports_federation_member_services.evidence_retention_days` is set.

**Behaviour to verify**:

- Imports: a players CSV with only `name`, a teams CSV with `club_name` or
  `name`, and a participants CSV with `tournament_name`/`team_name` fail with a
  missing-column message; code-based files import as before. Notify integration
  partners that send these contracts: this is a breaking change for files that
  still use names.
- Import jobs approved before the upgrade for these three templates must be
  re-previewed and re-approved; the live run refuses approvals recorded under
  `csv_v1`.
- **Retention and Recovery** lists the two new policies; their first runs are
  recorded as dry runs while no period is set.
- Member evidence: hold, release and erasure from **Member evidence history**;
  erasure is refused under hold and is posted on the member request.
- Court workspace: opening it removes this user's fully synchronised journals
  older than 14 days from the device and keeps journals with unsent work.
- Freezing standings behaves as before; stage progression still runs through
  the format addon.

**Dry-run evidence**: static checks only in the authoring environment
(`py_compile`, CI documentation and contract checks,
`node ci/test_court_journal_pruning.mjs`). The new ORM tests
(`sf_notification_retention`, `sf_member_evidence_retention`, import-tools
tests) and the module upgrade were not run there; run them on staging.

**Rollback**: restore the pre-upgrade database and filestore together with the
previous code. If only the import change must be reverted and no `csv_codes`
approvals are pending, previous code and an upgrade of
`sports_federation_import_tools` restore `csv_v1`. Records deleted by a
configured retention run or an erasure cannot be restored without the backup;
set the periods only after the federation has approved them.

### Custom format setup and team spread

Affected modules: format, scheduling, setup_flow.

Scope: custom formats in the guided setup, safe re-generation of prepared
stages, and spreading each team's matches over its game days within the rest
limit.

Data changes: none. Upgrade sports_federation_format,
sports_federation_scheduling and sports_federation_setup_flow for the new code
and assets.

Behaviour changes to verify on staging:
- *Teams & format* keeps a draft custom format and opens the stage builder.
  The planner's format action for custom drafts opens the stage builder for
  every user.
- Generating a format whose stages were already prepared keeps their matches.
  Before this change it failed with "Fixtures with operational matches cannot
  be deleted". Different teams give a clear "make a new version" message.
- Plan Competition reports unfinished custom stages as a blocking issue.
- Plan Competition keeps each team within the rest limit per game day when the
  game days allow it. Rest warnings state the team's match total and its
  capacity.

Dry-run evidence: Python/XML/JavaScript syntax checks, the dependency-free
distributor tests (including team-spread cases) and repository static checks
were executed on the patched tree. Odoo upgrade and ORM tests
(`sf_competition_formats`) were NOT executed in this environment and must pass
on staging before release.

Rollback: restore the previous code. No data needs to be reverted.

### Stage builder, match board and format reuse

Affected modules: format 19.0.6.5.0, setup_flow 19.0.4.11.0, live_workspace 19.0.1.6.0.

Scope: the stage builder for custom formats, the season match board as the
planner's Schedule step, saved format templates, and reusing formats and game
days when a competition is copied to a new season.

Data changes (no migration scripts; upgrading installs the new columns and access rules):
- format 19.0.6.5.0: `federation.tournament.format_source_structure_id`
  (nullable). Templates accept the `custom` format type. Competition designers
  get create/write on stage progressions and create/write on format templates.
- setup_flow 19.0.4.11.0 and live_workspace 19.0.1.6.0: no stored fields. New
  client actions `federation_stage_builder` and `federation_season_board`, plus
  a "Match board" button on the competition.

Behaviour changes to verify on staging:
- The planner's Schedule step opens the match board. *Plan Competition* stays
  available as *Auto-plan the rest*.
- On the board, moves between game days update allocations and working
  schedules. They are logged as `board_move` and refused when the validator
  reports a new error. Published days stay locked.
- Custom formats open in the stage builder, and *Generate all matches* freezes
  them.
- *Copy competition setup* moves game days by whole weeks and keeps their
  divisions. Before this change, a game day limited to divisions could not be
  copied.

Dry-run evidence: Python/XML syntax checks, JavaScript syntax checks, the
board helper smoke test and repository static checks (access CSV, always-invisible
fields, privileged mutation boundaries, dependency drift, competition
workflow and usability checks) were executed on the patched tree. Odoo upgrade, ORM tests
(`sf_competition_formats`, `sf_live_workspace`) and browser checks of both
client actions were NOT executed in this environment and must pass on staging
before release.

Rollback: restore the previous code and upgrade the three modules. The
nullable field and the template rows can stay. Templates saved with the
`custom` type must be archived before a code-only rollback.

### End-to-end release check: lifecycle lane and walkthrough

Affected modules: release tooling only.

The release baseline now requires a `lifecycle` lane. It runs the scenarios
contracted in `ci/release_confidence/competition_lifecycle.json` from
`sports_federation_app/tests/test_competition_lifecycle_e2e.py` and fails when the
file is missing, uses shortcuts (elevation, policy bypass, direct state writes,
skips), or any required scenario did not run. Until the scenarios are written the
baseline is red by design.

`scripts/ci/run_end_to_end_release.sh` runs the lanes (and the migration rehearsal
when an approved backup is supplied), starts a disposable walkthrough server on the
host loopback, and combines automated, walkthrough and novice-session evidence into
`end-to-end-summary.json`. See the [end-to-end release check](../release/end-to-end-check.md).

View files in accounting, calendar, duty coverage, member services, rosters,
schedule approval and setup flow only gained XML rationale comments for
always-invisible fields; no view behaviour changed and no module upgrade is needed
for them.

Dry-run evidence: shell syntax, the new checker unit tests and the repository
static checks executed. The Odoo lanes, walkthrough server and seed script were NOT
executed in this environment.

Rollback: revert the commit. No data or schema change is involved.

### Registration, publication and club-duty automation

Affected modules: registration 19.0.1.4.0, rosters 19.0.1.12.0, schedule_approval 19.0.2.6.0.

**DB migrations**: three data migrations, all idempotent and logged.

| Module | Version | What it does |
|---|---|---|
| `sports_federation_registration` | 19.0.1.4.0 | Creates the missing confirmed participants of finalised team lists (one savepoint per set; ineligible teams are logged and skipped). |
| `sports_federation_rosters` | 19.0.1.12.0 | Prepares the roster of every participant in a running season and links existing rosters to the team's confirmed registration (one savepoint per participant). |
| `sports_federation_schedule_approval` | 19.0.2.6.0 | Sets playing area and venue from the published slot and moves published `draft` matches to `scheduled` (set-based SQL; no constraints re-run, no finance events created). |

Run the registration migration before the rosters one; the module order of an
upgrade already does this, and the rosters migration also covers participants
created before it.

**Behaviour changes**:

- Finalising a team list creates participants; participants create rosters.
- Publishing schedules matches, copies the slot's venue and playing area and, for
  rule sets with **Referees required per match** above 0 and **Ask clubs for
  officials on publication** on (default), creates the open club duties.
  Existing published schedules are not given duties retroactively; run
  **Plan Match-Day Officials** for them if wanted.
- The automatic venue-booking charge needs a configured `venue_booking` fee type
  with an amount; otherwise no charge and no implicit fee type.
- Roster, missing-roster, parental-consent, line-up and entry tasks now carry
  deadlines, so they sort, show as overdue and are covered by the due-soon reminder.

**Dry-run evidence**: `python ci/check_migration_review.py --files
sports_federation_rosters/migrations/19.0.1.12.0/post-migrate.py
sports_federation_registration/migrations/19.0.1.4.0/post-migrate.py
sports_federation_schedule_approval/migrations/19.0.2.6.0/post-migrate.py
docs/operations/release-runbook.md` exits with code 0. The Odoo database upgrade, ORM and HTTP
tests were not executed in the authoring environment; run the tagged tests
(`sf_participant_rosters`, `sf_task_deadlines`, `sf_auto_club_duties`,
`sf_publication`) and the migration rehearsal before promotion.

**Rollback**: restore the paired database and filestore taken before the upgrade
and deploy the previous code. Participants, rosters, duties and match states
created by the migrations or by publication are ordinary records; if only the
data must be undone, withdraw or delete the participants created for the
affected division, close the draft rosters, and set `state = 'draft'` and clear
`playing_area_id` for matches whose publication is removed. No schema change is
made, so no index or column needs dropping.

### Archived rosters, archived-competition list and permanent deletion

Affected upgrades:

- `sports_federation_portal` `19.0.7.11.0` to `19.0.7.12.0`
- `sports_federation_competition_core` `19.0.1.7.0` to `19.0.1.8.0`

No schema change except the transient deletion wizard. The portal also hides
rosters, roster lines, season registrations and their tasks when every
competition the team plays that season (or the roster's own competition) is
archived. The portal `post-migrate.py` closes those tasks for competitions that
are already archived. Competition Core adds an Archived filter, a Restore
button and the system-administrator-only Delete permanently wizard.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_competition_core,sports_federation_portal --dry-run
bash ./ci/run_tests.sh --module sports_federation_app
```

Rollback is the standard paired database and filestore backup restore.
Permanent deletion is irreversible by design; only a backup restore brings
deleted competitions back. Each deletion is logged at WARNING level and in
Settings > Technical > Logging under `sports_federation.force_delete`.

### Archived competitions hidden from the portal

Affected upgrade: `sports_federation_portal` `19.0.7.10.0` to `19.0.7.11.0`.

No schema change. Portal reads, the task projection and the portal ownership
checks now exclude entries, matches, lineups, referee duties and assignments,
game days and tasks of archived competitions and archived divisions. The
`post-migrate.py` script closes open operation tasks of competitions that were
already archived, so they leave the portal and the federation action queue.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_portal --dry-run
bash ./ci/run_tests.sh --module sports_federation_portal
```

The upgrade log reports how many tasks were closed. Rollback is the standard
backup restore procedure. Without a restore, restoring a competition and its
divisions makes everything visible again, and the next task sync reopens its
tasks. Do not reopen tasks manually while the competition stays archived.

### Competition lifecycle completion

Affected modules: result_control 19.0.1.6.0, format 19.0.6.1.0, discipline.

Scope: one definition of a finished match, one standings/progression engine,
knockout placeholders/ties/corrections, guided competition finish, forfeit/bye
points and dated suspensions, and the gameday-roster follow-ups.

Data changes:
- result_control 19.0.1.6.0 post-migrate: matches with an approved result that
  are not done or cancelled are set to done. Only the state column changes;
  scores, audit and publication data are untouched. Safe to repeat.
- format 19.0.6.1.0 post-migrate: every round-robin stage with participants gets
  its linked league table (one savepoint per stage; failures are logged, not
  fatal). Review the upgrade log for "No league table created for stage".
- discipline: daily cron "Discipline: Start and End Suspensions" activates
  suspensions on their start date and expires them after their end date.

Behaviour changes to verify on staging: approving a result completes the match;
contesting/correcting reopens it and withdraws an unplayed follow-up knockout
match (audited as follow_up_match_withdrawn); knockout fixtures with unknown
teams can be scheduled and are filled without republication; competitions move
through Open/In Progress/Closed via the guarded transition and close only
without blockers; forfeits and byes use rule-set points.

Dry-run evidence: Python/XML syntax checks and repository static checks
(privileged mutation, addon integrity, route ownership, ACL, workflow command,
sudo guard) executed on the patched tree. Odoo upgrade, ORM/HTTP/browser tests
and an end-to-end competition run were NOT executed in this environment and
must pass on staging before release.

Rollback: restore the pre-upgrade database and filestore with the previous
code. Code-only rollback leaves done matches, linked tables and suspension
states that the previous code does not expect.

### Game-day roster and per-match participation

Affected modules: rules, rosters, portal, live_workspace.

Candidate base: 4626ba2401ec05ca67ebac0e9f09b4d53d75338a.
Behaviour: one roster per team gameday, shared by all its matches; no starters or
substitutes declared in advance; at each match the coach crosses out the gameday
players who do not play. Crossing out is match-specific and never edits the roster.

Schema: federation.rule.set.gameday_roster_max_size and match_player_max_size
(integers, default 0 = unchanged behaviour) and federation.match.sheet.line.crossed_out
(boolean, default false). Odoo adds the columns on upgrade; no data migration runs and
existing sheets keep every listed player as playing. Legacy starter/substitute values
stay stored and synchronized, but new gameday rosters do not set them.

Upgrade sports_federation_rules, sports_federation_rosters, sports_federation_portal and
sports_federation_live_workspace, then set both limits (for example 14 and 12) on the
competition rule sets that use them. With limits at 0 nothing new is enforced.

New portal route: POST /my/match-sheets/<id>/participation (CSRF, ownership domain via
the portal privilege boundary). No new sudo statement is introduced. Sheet locking now
requires the per-match limit to be respected.

Dry-run evidence: Python/XML syntax checks, template xpath simulation against the
source templates, and repository static checks executed. Odoo upgrade, ORM/HTTP and
browser tests (sf_gameday_participation and existing roster tests) were NOT executed in
this environment and must pass on staging before release.

Rollback: restore the pre-upgrade database and filestore with the previous code. A
code-only rollback leaves unused columns and loses the record of crossed-out players.

### Workspace and portal UX consolidation

Affected modules: base, calendar, portal, setup_flow, live_workspace, public_site, duty_coverage, rosters, navigation, notifications.

Candidate base: a6411d877a37986920c4c8b0337e10c794dc646f.
See the [workspace UX acceptance suite](../release/acceptance/workspace-ux.md) for the scope, module upgrade list,
local checks, runtime groups, browser matrix, historical-timezone review and rollback.
The calendar migration marks historical event timezone evidence as unreviewed without
moving stored slot instants. Calendar planners confirm evidence through an audited,
write-authorised, row-locked command. Match timezone fields are nonstored projections
of nonpersonal event metadata, not a new source of truth or a new access grant.
Task/list context is a presentation filter intersected with existing ownership domains.
No task system, readiness model, approval state or publication bypass is introduced.
Local source/policy and mocked-service checks were executed. Odoo database upgrade,
ORM/HTTP/browser runtime and novice acceptance remain unexecuted in this environment.
Rollback requires the pre-upgrade database and filestore together with previous code.

### Minimal workspace and event time zones

Affected modules: base, calendar, portal, setup_flow, live_workspace.

Candidate source base: a9fbdebd0cd80e7122ae0e0a61637d6c5b763ebf.
The role and browser checks are part of the [workspace UX acceptance suite](../release/acceptance/workspace-ux.md).

Schema change: federation.matchday.event_timezone. Calendar pre-migration explicitly
backfills historical days to UTC without changing slot instants. New days capture the
creator's timezone. Existing draft days require timezone review before generating slots.
Scheduled days remain UTC unless a separately reviewed historical data migration is approved.
The visual planner and court queue use event-local display; generic Odoo datetime widgets
retain user-profile display. Constraints convert local input on the server under existing
schedule access, mutability and revision checks. No new public route or sudo mutation is added.

Dry-run evidence: source-policy tests and Python/XML/JavaScript syntax checks executed.
Database upgrade, ORM/HTTP tests, browser/mobile sessions and novice acceptance have NOT
been executed in this environment. This candidate is not production-qualified by these checks.

Rollback: restore the pre-upgrade database and filestore together with the previous code.
Do not roll back code alone after new event-local constraints or slot generation have occurred.
Retain backups until event timezone review and staging acceptance are complete.

### Simplified competition workflow and Competition Hub

Affected upgrades:

- `sports_federation_base` `19.0.1.3.0` → `19.0.1.4.0`
- `sports_federation_competition_core` `19.0.1.5.1` → `19.0.1.6.0`
- `sports_federation_registration` `19.0.1.2.2` → `19.0.1.3.0`
- `sports_federation_scheduling` `19.0.3.5.0` → `19.0.3.6.0`
- `sports_federation_setup_flow` `19.0.3.0.0` → `19.0.4.0.0`
- `sports_federation_rosters` `19.0.1.6.0` → `19.0.1.7.0`
- `sports_federation_portal` `19.0.7.2.0` → `19.0.7.3.0`
- `sports_federation_navigation` new at `19.0.1.0.0`
- `sports_federation_app` `19.0.1.0.0` → `19.0.2.0.0`
- `sports_federation_demo` `19.0.1.1.0` → `19.0.1.2.0`

The setup-flow upgrade adds remembered preset/default columns on season competitions. The `19.0.4.0.0` post-migration backfills league/cup preset and format defaults without changing existing workflow states. New team, format, and lineup wizard records are transient. New task types reuse the existing task table. The new navigation integration addon updates only `ir.ui.menu` visibility/parent data and does not remove actions or permissions; the app entry point remains dependency-only.

Upgrade order follows dependencies: base, competition core, registration, format/calendar/scheduling/approval/setup flow, matchday/rosters, portal, app, then demo. Use the aggregate app upgrade for the supported installation:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_base,sports_federation_competition_core,sports_federation_registration,sports_federation_scheduling,sports_federation_setup_flow,sports_federation_rosters,sports_federation_portal,sports_federation_navigation,sports_federation_app --dry-run
bash ./ci/run_tests.sh --suite competition_core
bash ./ci/run_tests.sh --suite people_rosters_rules
bash ./ci/run_tests.sh --suite portal_public_ops
scripts/ci/run_rc_validation.sh install
scripts/ci/run_rc_validation.sh upgrade
scripts/ci/run_rc_validation.sh acceptance
```

Before promotion, verify one ordinary manager sees only Competition Hub under Competitions, an advanced user retains all owner workspaces and Administration recovery, streamlined schedule, line-up and result transitions retain audit evidence, Independent Review retains separation of duties, and a missing parental approval blocks both roster and lineup submission.

Rollback requires the paired pre-upgrade database/filestore backup. Navigation can be restored by rolling back the app data update, but do not delete participant sets, entries, approvals, reviews, publications, match sheets, or audit/task records created after upgrade. Restore the full backup if persisted operations occurred.

### Parental approval and game-day line-up

Affected upgrades:

- `sports_federation_people` `19.0.1.1.0` to `19.0.1.2.0`
- `sports_federation_rosters` `19.0.1.5.1` to `19.0.1.6.0`

The People upgrade is additive: Odoo creates the new
`federation.player.parental.approval` table and its attachment-backed signed
document field. No existing player requires a backfill; the adult-league rule
only blocks players who are under 16 on the relevant participation date. The
Rosters upgrade changes workflow behavior but adds no stored schema: a team's
declared lineup is synchronized and approved once per explicit match day, with
tournament plus scheduled date as the legacy fallback.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_people,sports_federation_rosters --dry-run
bash ./ci/run_tests.sh --suite people_rosters_rules
```

Patch-environment status on 2026-10-10: Python compilation, XML parsing, addon
integrity, ACL integrity, dependency drift, workflow contracts, documentation,
and focused source checks passed. The database dry run and Odoo test suite were
not executed because this patch environment has no Docker/Podman or Odoo
runtime. They remain mandatory release gates.

Rollback trigger: module installation/upgrade failure, an unexpected eligibility
blocker for an adult player or youth league, or inconsistent approved lineups in
one game-day scope. Because signed approvals create database rows and filestore
attachments, take a paired database/filestore backup before upgrading and
restore both to roll back after operators have created approval records. Do not
delete verified approvals or bypass the game-day synchronization as a rollback
workaround.

### Format progression and fixture ownership

Affected modules: format and all installed addons.

The current format release hardens structure-scoped progression validation,
rejects ambiguous tied bracket results, makes Swiss pairing deterministic when
the first candidate pairing dead-ends, and synchronizes approved fixture
results through the authorized result-command boundary. These are model and
workflow ownership changes without a standalone schema migration. The normal
addon upgrade path remains the deployment mechanism, with database restore as
the rollback path.

Dry-run evidence captured on 2026-09-13:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Install: none
Upgrade: sports_federation_app,sports_federation_base,
sports_federation_calendar,sports_federation_competition_core,
sports_federation_compliance,sports_federation_demo,
sports_federation_discipline,sports_federation_finance_bridge,
sports_federation_format,sports_federation_governance,
sports_federation_import_tools,sports_federation_matchday,
sports_federation_notifications,sports_federation_officiating,
sports_federation_people,sports_federation_portal,
sports_federation_public_site,sports_federation_registration,
sports_federation_reporting,sports_federation_result_control,
sports_federation_rosters,sports_federation_rules,
sports_federation_schedule_approval,sports_federation_scheduling,
sports_federation_standings,sports_federation_tournament,
sports_federation_venues
```

Focused verification passed with the format addon and competition-core suite:

```text
bash ci/run_tests.sh --module sports_federation_format
Exit code: 0; 20 tests run, 20 passed, 0 failed, 0 errors

bash ci/run_tests.sh --suite competition_core
Exit code: 0; 248 tests run, 248 passed, 0 failed, 0 errors
```

Rollback requires restoring the pre-upgrade database and filestore backup;
do not bypass progression validation or fixture ownership checks as a
rollback workaround.

### Transactional command ownership

Affected modules: matchday, result_control, schedule_approval.

The current release diff changes model-owned match-day cleanup and command
boundaries in `sports_federation_matchday`, `sports_federation_result_control`,
and `sports_federation_schedule_approval`. The changes were reviewed as
application and ownership behavior changes; no standalone migration script is
required. The normal addon upgrade path remains the deployment mechanism, with
the backup restore procedure below as the rollback path.

Dry-run evidence captured on 2026-09-09:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Install: none
Upgrade: sports_federation_base,sports_federation_calendar,
sports_federation_competition_core,sports_federation_compliance,
sports_federation_demo,sports_federation_discipline,
sports_federation_finance_bridge,sports_federation_format,
sports_federation_governance,sports_federation_import_tools,
sports_federation_matchday,sports_federation_notifications,
sports_federation_officiating,sports_federation_people,
sports_federation_portal,sports_federation_public_site,
sports_federation_registration,sports_federation_reporting,
sports_federation_result_control,sports_federation_rosters,
sports_federation_rules,sports_federation_schedule_approval,
sports_federation_scheduling,sports_federation_standings,
sports_federation_tournament,sports_federation_venues
```

The dry run only resolved the installed addon plan and did not modify the
database. If the upgrade fails, preserve the logs and failed database state,
then restore the pre-upgrade database and filestore backup before restarting
the previous release.

### Formatting-only model changes

Affected modules: no schema change.

The 2026-09-03 formatting change touched model files in
`sports_federation_base`, `sports_federation_competition_core`,
`sports_federation_format`, `sports_federation_import_tools`,
`sports_federation_notifications`, `sports_federation_reporting`,
`sports_federation_schedule_approval`, and
`sports_federation_scheduling`. It made no schema, data, or workflow changes,
so no database migration is required. The migration-review dry run must include
this record and pass before release promotion.

Dry-run evidence captured on 2026-08-23:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Upgrade: sports_federation_base,...,sports_federation_portal,...,sports_federation_venues
Install: none
```

Focused verification:

```text
bash ci/run_tests.sh --module sports_federation_portal
Exit code: 0; 116 tests run, 116 passed, 0 failed, 0 errors; 30 post-tests
```

Rollback is the standard backup restore procedure in the release runbook. Do not
restore the deleted V1 controller or broaden portal publication access as a
rollback workaround.

### Portal controller-load repair

Affected modules: portal 19.0.4.1.0.

The portal repair removes the stale re-export of the deleted V1 workspace
controller, restores the tournament-registration view in the manifest data
order, and keeps officiating assignment visibility limited to live current
publications. No database migration is required; the portal manifest is bumped
from `19.0.4.0.0` to `19.0.4.1.0`.

### Public-site route ownership

Affected modules: public_site.

**DB migrations**: None. The public-site controller route ownership change
does not alter persisted data or the public API contract.

**Dry-run evidence**: `python ci/check_migration_review.py --files
sports_federation_public_site/controllers/public_competitions.py
docs/operations/release-runbook.md` exited with code 0, confirming that the controller change
has release-review evidence.

**Rollback**: Revert the controller change and redeploy the prior application
revision. No database restore or data backfill is required.

### Competition-entry cutover

Affected modules: registration, portal 19.0.5.0.0, public_site, reporting.

Upgrade registration, portal, public site and reporting together after a verified
backup. The portal migration permanently drops the test-only former tournament
registration table.

```bash
odoo-bin -d RC_DATABASE -u sports_federation_registration,sports_federation_portal,sports_federation_public_site,sports_federation_reporting --stop-after-init
python ci/check_registration_contract.py
python ci/check_access_csv_integrity.py
```

### Officials and standalone-match cleanup

Affected modules: tournament 19.0.1.4.0, officiating, portal.

Upgrade `sports_federation_tournament`, `sports_federation_officiating`, and
`sports_federation_portal` together after taking a verified database backup.
The tournament migration permanently removes test-only standalone matches and
their dependent records.

```bash
odoo-bin -d RC_DATABASE \
  -u sports_federation_tournament,sports_federation_officiating,sports_federation_portal \
  --stop-after-init
python ci/check_officiating_contract.py
```

Verify that the standalone-match count is zero, create officials through a
current live match-day publication, and confirm that the official self-service
portal shows current assignments plus retained history.

### Portal cutover

Affected modules: portal 19.0.4.0.0.

Upgrade `sports_federation_portal` after the competition, registration,
schedule-approval and match-day modules. The migration closes open operation
tasks projected from former tournament registrations. It does not delete business
records.

```bash
odoo-bin -d RC_DATABASE -u sports_federation_portal --stop-after-init
python ci/check_portal_competition_ownership.py
python ci/check_portal_sudo_guard.py
bash ci/run_tests.sh --module sports_federation_portal
```

Verify /my/competitions, /my/competition-entries, /my/match-days and one match-day operations page. Confirm that draft schedules and superseded publications do not appear.

Rollback requires a database restore if entries or portal audit events were created after cutover.

### Schedule publication and match-day operations

Affected upgrades:

- `sports_federation_schedule_approval` `19.0.2.1.0` to `19.0.2.2.0`
- `sports_federation_matchday` `19.0.2.0.0` to `19.0.2.1.0`

Dry-run procedure:

```bash
odoo-bin -d RC_DATABASE \
   -u sports_federation_schedule_approval,sports_federation_matchday \
   --stop-after-init
```

Verify that publication `matchday_id` values are populated, each match day has
at most one `live` publication, existing published matches have
`operational_slot_id = published_slot_id`, and the publication integrity contract
and module tests pass. The approval migration creates a partial unique index for
one live publication per match day. Existing data is safe because the preceding
implementation permitted at most one live publication for the broader edition.

Before upgrading, take a database backup. Rollback requires restoring that
backup because the new publication uniqueness semantics and operational audit
fields are persistent. Do not downgrade only the addon code after operators have
recorded live deviations.

### Release train 2026.08: demo fixture alignment

Affected modules: rosters, demo.

**DB migrations**: None. The roster match-sheet change only suppresses the
interactive match creation side effect while Odoo loads demo fixtures; normal
ORM-created matches still receive their draft home and away sheets. The demo
fixture was also aligned with current participant eligibility and compliance
expiry-date validation.

**Validation evidence**: A fresh isolated install with demo data enabled passed
the demo module tests (5 passed, 0 failed, 0 errors) and did not report the
`federation_match_sheet_unique_match_team_side` violation.

**Rollback**: Revert the additive code and fixture changes. No database
backfill, schema reversal, or migration artifact is required.

### Release train 2026.06: tournament indexes, rate limits and hashed partner tokens

Affected modules: tournament, base, import_tools.

For every migration-sensitive change, record the affected modules, migration
or ownership surfaces, command output summary, test result, and known warnings
in the release notes. Record rollback triggers, backup requirements, migration
artifacts, and any index or data reversal in the same release entry. The
validated 2026.06 tournament migration backfilled missing match schedule and
round fields and added five operational indexes; its rollback path is restoring
the paired database/filestore or dropping those indexes when only index
rollback is required. The 2026.08 workspace and portal ownership cleanup was
rollback-neutral.

**New `ir.config_parameter` keys**:

| Key | Purpose | Default |
|---|---|---|
| `sports_federation.rate_limit.<scope>.limit` | Per-scope rate-limit ceiling override | See `_POLICIES` in `request_rate_limit.py` |
| `sports_federation.rate_limit.<scope>.window_seconds` | Per-scope window override | See `_POLICIES` |

**Deprecated field removals**: None.

**Module install order changes**: None. Default install order (tier 1 → 2 → 3 → 4)
is unchanged; see `docs/operations/deployment.md`.

**Behaviour changes**:

- Rate-limit policies are now overridable at runtime via `ir.config_parameter`
  without a code deployment. See `openapi/ERROR_CODES.md` for per-scope limits.
- Integration partner tokens are now stored hashed. Existing plaintext tokens
  were migrated in place and flagged `token_rotation_required = True`. Rotate
  all partner tokens within one release cycle.

**Scheduled actions to verify**:

| Action | Expected state after upgrade |
|---|---|
| `Federation: GC Rate Limit Buckets` | Active, interval 1 hour |
| `Federation: GC Staged Deliveries` | Active, interval 1 day |
| `Federation: Expire Player Licenses` | Active, interval 1 day |

### Release train 2026.05

Affected modules: no database migration.

**DB migrations**: None.

## Notification authorization, bounded inbox and retention update

Upgrade `sports_federation_notifications` to `19.0.1.5.2` and
`sports_federation_navigation` to `19.0.1.1.1`, then restart Odoo. The notification
upgrade adds the mail-ownership marker and recipient/cursor index. Its migration
marks only mail already linked to federation logs or deliveries; it does not
send, recreate or delete mail. The navigation update leaves one publication-menu
assignment for federation managers and schedule approvers.

Validate the installed notification-operation regressions, existing trigger
queue-success tests and navigation visibility tests before deployment. Check
recipient-scoped legacy log access, revoked-source cursor pages, a routing/log
creation failure after a business decision, and shared/failed mail retention.
The isolated `ci.test_notification_operations` suite does not execute record
rules, PostgreSQL locks, migration SQL or browser rendering. Release qualification
still requires the installed ORM and browser suites.

Dry-run evidence for this update is pending: the isolated Python regressions
passed, but no Odoo upgrade or PostgreSQL migration was executed in the patch
creation environment. Before deployment, rehearse on a database/filestore copy
and verify the marker backfill, index, recipient rule and menu assignments.

Rollback: stop the notification and retention schedulers before reverting code.
Restore the approved pre-upgrade database and filestore if any retention cleanup
has run, since deleted mail content cannot be recovered by reverting Python.
The marker backfill and index creation alone do not delete or replay messages.
Do not restore the former permissive log rule as a routine security rollback;
keep the recipient restriction or disable legacy log access until corrected.
