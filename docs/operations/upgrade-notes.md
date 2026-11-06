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
